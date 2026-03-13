# ANALYTICS/services/rollups.py
"""
Rollup Jobs for Analytics Data Aggregation

Handles:
- Campaign budget/spend calculation
- Link daily statistics aggregation
- Content snapshot delta calculation

FIX: bulk_update used in rollup_campaign_spend for efficiency.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from django.db.models import Sum, Count, Q, F, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from ANALYTICS.models import (
    Campaign,
    CampaignExpense,
    TrackingLink,
    LinkDailyStat,
    Content,
    ContentSnapshot,
    AnalyticsEvent,
    EventType,
)

logger = logging.getLogger(__name__)


# =============================================================================
# BUDGET / SPEND ROLLUPS
# =============================================================================

class BudgetRollupService:
    """
    Calculate and update Campaign.budget_spent from CampaignExpense records.

    Rules:
    - By default only approved expenses (is_approved=True) are summed.
    - Pass include_unapproved=True to include all expenses.
    - Idempotent: re-running produces the same result.
    - FIX (minor): uses bulk_update instead of individual save() per campaign.
    """

    def __init__(self):
        self.logger = logger

    def rollup_campaign_spend(
        self,
        campaign_id: Optional[str] = None,
        include_unapproved: bool = False,
    ) -> Dict[str, Any]:
        """
        Calculate and update Campaign.budget_spent from CampaignExpense.

        Args:
            campaign_id: Specific campaign UUID to update (None = all campaigns).
            include_unapproved: Include unapproved expenses in total.

        Returns:
            {campaigns_updated, total_spend_calculated, campaigns: [...]}
        """
        campaigns = Campaign.objects.all()
        if campaign_id:
            campaigns = campaigns.filter(id=campaign_id)

        # Build expense filter
        expense_filter = Q(campaign__in=campaigns)
        if not include_unapproved:
            expense_filter &= Q(is_approved=True)

        # Single aggregation query — one DB round trip for all campaigns
        spend_by_campaign = (
            CampaignExpense.objects
            .filter(expense_filter)
            .values('campaign_id')
            .annotate(
                total=Coalesce(
                    Sum('amount'),
                    Decimal('0.00'),
                    output_field=DecimalField(),
                )
            )
        )

        spend_map = {
            str(row['campaign_id']): row['total']
            for row in spend_by_campaign
        }

        # FIX (minor): bulk_update — one DB write for all campaigns
        campaign_list = list(campaigns)
        total_spend = Decimal('0.00')
        result_rows = []

        for campaign in campaign_list:
            new_spent = spend_map.get(str(campaign.id), Decimal('0.00'))
            campaign.budget_spent = new_spent
            total_spend += new_spent
            result_rows.append({
                'id': str(campaign.id),
                'name': campaign.name,
                'budget_spent': str(new_spent),
                'budget_total': str(campaign.budget_total) if campaign.budget_total else None,
                'budget_remaining': str(campaign.budget_remaining) if campaign.budget_total else None,
            })

        with transaction.atomic():
            Campaign.objects.bulk_update(campaign_list, ['budget_spent'])

        self.logger.info(
            "Budget rollup complete: %d campaigns updated, $%s total spend",
            len(campaign_list), total_spend,
        )

        return {
            'campaigns_updated': len(campaign_list),
            'total_spend_calculated': total_spend,
            'campaigns': result_rows,
        }

    def check_budget_overspend(self) -> list:
        """
        Return campaigns where budget_spent > budget_total.

        Returns:
            [{id, name, budget_spent, budget_total, overspend, utilization_pct}]
        """
        overspent_campaigns = (
            Campaign.objects
            .filter(budget_total__isnull=False, budget_total__gt=0)
            .annotate(
                overspend=ExpressionWrapper(
                    F('budget_spent') - F('budget_total'),
                    output_field=DecimalField(),
                )
            )
            .filter(overspend__gt=0)
        )

        results = []
        for campaign in overspent_campaigns:
            results.append({
                'id': str(campaign.id),
                'name': campaign.name,
                'budget_total': str(campaign.budget_total),
                'budget_spent': str(campaign.budget_spent),
                'overspend': str(campaign.budget_spent - campaign.budget_total),
                'utilization_pct': campaign.budget_utilization_pct,
            })

        if results:
            self.logger.warning(
                "%d campaign(s) are over budget: %s",
                len(results), [r['name'] for r in results],
            )

        return results


# =============================================================================
# LINK DAILY STATS AGGREGATION
# =============================================================================

class LinkStatsAggregationService:
    """
    Aggregate AnalyticsEvent data into LinkDailyStat for fast queries.

    Rules:
    - total_clicks      = COUNT of click events for link on date
    - unique_visitors   = COUNT DISTINCT visitor_id (NULLs excluded)
    - unique_sessions   = COUNT DISTINCT session_id (NULLs excluded)
    - conversions       = COUNT of purchase events attributed to link
    - revenue           = SUM of conversion_value attributed to link
    - conversion_rate   = conversions / unique_visitors * 100
    - Idempotent: update_or_create so reruns update existing rows.
    """

    def __init__(self):
        self.logger = logger

    def aggregate_link_stats(
        self,
        target_date: Optional[date] = None,
        link_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate link statistics for a specific date.

        Args:
            target_date: Date to aggregate (default: yesterday).
            link_id: Specific link UUID (None = all active links).

        Returns:
            {date, links_processed, stats_created, stats_updated, links: [...]}
        """
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()

        links = TrackingLink.objects.filter(is_active=True)
        if link_id:
            links = links.filter(id=link_id)

        links = list(links)
        stats_created = stats_updated = 0
        link_summaries = []

        for link in links:
            try:
                stat_data, created = self._aggregate_single_link(link, target_date)

                if created:
                    stats_created += 1
                else:
                    stats_updated += 1

                link_summaries.append({
                    'link_id': str(link.id),
                    'short_code': link.short_code,
                    'total_clicks': stat_data['total_clicks'],
                    'unique_visitors': stat_data['unique_visitors'],
                    'conversions': stat_data['conversions'],
                })

            except Exception as exc:
                self.logger.error(
                    "Failed to aggregate stats for link %s: %s",
                    link.id, exc, exc_info=True,
                )

        self.logger.info(
            "Link stats aggregation for %s: %d links, %d created, %d updated",
            target_date, len(links), stats_created, stats_updated,
        )

        return {
            'date': str(target_date),
            'links_processed': len(links),
            'stats_created': stats_created,
            'stats_updated': stats_updated,
            'links': link_summaries,
        }

    def _aggregate_single_link(
        self,
        link: TrackingLink,
        target_date: date,
    ) -> tuple:
        """
        Aggregate stats for one link on one date.
        Returns (stat_data_dict, created_bool).
        """
        with transaction.atomic():
            click_events = AnalyticsEvent.objects.filter(
                link=link,
                event_type=EventType.CLICK,
                occurred_at__date=target_date,
            )

            total_clicks = click_events.count()

            unique_visitors = (
                click_events
                .filter(visitor_id__isnull=False)
                .values('visitor_id')
                .distinct()
                .count()
            )
            unique_sessions = (
                click_events
                .filter(session_id__isnull=False)
                .values('session_id')
                .distinct()
                .count()
            )
            unique_users = (
                click_events
                .filter(user__isnull=False)
                .values('user_id')
                .distinct()
                .count()
            )

            conversion_qs = AnalyticsEvent.objects.filter(
                conversion_attributed_to_link=link,
                event_type=EventType.PURCHASE,
                occurred_at__date=target_date,
            )
            conversions = conversion_qs.count()
            revenue = (
                conversion_qs.aggregate(
                    total=Coalesce(
                        Sum('conversion_value'),
                        Decimal('0.00'),
                        output_field=DecimalField(),
                    )
                )['total']
            )

            conversion_rate = (
                round((conversions / unique_visitors) * 100, 4)
                if unique_visitors > 0 else None
            )

            # Geographic breakdown from meta JSON
            geo_data = {}
            for item in (
                click_events
                .values('meta__country')
                .annotate(count=Count('id'))
                .order_by('-count')[:10]
            ):
                country = item['meta__country']
                if country:
                    geo_data[country] = item['count']

            # Device breakdown from meta JSON
            device_data = {}
            for item in (
                click_events
                .values('meta__device_type')
                .annotate(count=Count('id'))
                .order_by('-count')
            ):
                device = item['meta__device_type']
                if device:
                    device_data[device] = item['count']

            stat_data = {
                'total_clicks': total_clicks,
                'unique_visitors': unique_visitors,
                'unique_sessions': unique_sessions,
                'unique_users': unique_users,
                'conversions': conversions,
                'conversion_rate': conversion_rate,
                'revenue': revenue,
                'geo_data': geo_data,
                'device_data': device_data,
            }

            _, created = LinkDailyStat.objects.update_or_create(
                link=link,
                date=target_date,
                defaults=stat_data,
            )

            self.logger.info(
                "%s LinkDailyStat for %s on %s: %d clicks, %d unique, %d conversions",
                'Created' if created else 'Updated',
                link.short_code, target_date,
                total_clicks, unique_visitors, conversions,
            )

            return stat_data, created


# =============================================================================
# CONTENT SNAPSHOT SERVICE
# =============================================================================

class ContentSnapshotService:
    """
    Creates ContentSnapshot records with delta computation.

    Rules:
    - (content, captured_at) must be unique — enforced at DB level.
    - Delta fields are computed vs the most recent prior snapshot.
    - create_snapshots_from_events aggregates AnalyticsEvent rows
      into snapshots for all content on a given date.
    """

    # Mapping from EventType to snapshot count field
    EVENT_TO_SNAPSHOT_FIELD = {
        EventType.LIKE:       'likes_count',
        EventType.COMMENT:    'comments_count',
        EventType.SHARE:      'shares_count',
        EventType.PAGE_VIEW:  'views_count',
        EventType.IMPRESSION: 'impressions',
    }

    def __init__(self):
        self.logger = logger

    def create_snapshot(
        self,
        content_id: str,
        captured_at=None,
        likes_count: int = 0,
        comments_count: int = 0,
        shares_count: int = 0,
        saves_count: int = 0,
        views_count: int = 0,
        reach: int = 0,
        impressions: int = 0,
        engagement_rate=None,
        platform_metrics: Optional[Dict] = None,
    ) -> ContentSnapshot:
        """
        Create a single ContentSnapshot with computed deltas.

        Args:
            content_id: UUID of the Content record.
            captured_at: Snapshot timestamp (default: now).

        Returns:
            ContentSnapshot instance.
        """
        if captured_at is None:
            captured_at = timezone.now()

        try:
            with transaction.atomic():
                content = Content.objects.get(id=content_id)

                # Delta vs most recent prior snapshot
                prior = (
                    ContentSnapshot.objects
                    .filter(content=content, captured_at__lt=captured_at)
                    .order_by('-captured_at')
                    .first()
                )

                if prior:
                    likes_delta = likes_count - prior.likes_count
                    comments_delta = comments_count - prior.comments_count
                    shares_delta = shares_count - prior.shares_count
                    views_delta = views_count - prior.views_count
                else:
                    likes_delta = comments_delta = shares_delta = views_delta = 0

                # Auto-compute engagement_rate if not supplied
                if engagement_rate is None and impressions > 0:
                    total_eng = likes_count + comments_count + shares_count + saves_count
                    engagement_rate = round((total_eng / impressions) * 100, 4)

                snapshot = ContentSnapshot.objects.create(
                    content=content,
                    captured_at=captured_at,
                    likes_count=likes_count,
                    comments_count=comments_count,
                    shares_count=shares_count,
                    saves_count=saves_count,
                    views_count=views_count,
                    reach=reach,
                    impressions=impressions,
                    engagement_rate=engagement_rate,
                    platform_metrics=platform_metrics or {},
                    likes_delta=likes_delta,
                    comments_delta=comments_delta,
                    shares_delta=shares_delta,
                    views_delta=views_delta,
                )

                self.logger.info(
                    "Created snapshot for '%s' at %s: "
                    "%d likes (+%d), %d views (+%d)",
                    content.title, captured_at,
                    likes_count, likes_delta,
                    views_count, views_delta,
                )

                return snapshot

        except Content.DoesNotExist:
            raise ValueError(f"Content not found: {content_id}")
        except Exception as exc:
            self.logger.error(
                "Failed to create snapshot for content %s: %s",
                content_id, exc, exc_info=True,
            )
            raise

    def create_snapshots_from_events(
        self,
        target_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate AnalyticsEvent rows into ContentSnapshot records
        for all content that had events on target_date.

        Args:
            target_date: Date to aggregate (default: yesterday).

        Returns:
            {content_processed, snapshots_created, errors}
        """
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()

        content_ids = (
            AnalyticsEvent.objects
            .filter(occurred_at__date=target_date, content__isnull=False)
            .values_list('content_id', flat=True)
            .distinct()
        )

        content_list = list(Content.objects.filter(id__in=content_ids))
        snapshots_created = 0
        errors = []

        captured_at = timezone.datetime.combine(
            target_date,
            timezone.datetime.max.time(),
        ).replace(tzinfo=timezone.get_current_timezone())

        for content in content_list:
            try:
                counts = self._aggregate_event_counts(content, target_date)

                self.create_snapshot(
                    content_id=str(content.id),
                    captured_at=captured_at,
                    likes_count=counts.get('likes_count', 0),
                    comments_count=counts.get('comments_count', 0),
                    shares_count=counts.get('shares_count', 0),
                    views_count=counts.get('views_count', 0),
                    impressions=counts.get('impressions', 0),
                )
                snapshots_created += 1

            except Exception as exc:
                self.logger.error(
                    "Failed to create snapshot for content %s on %s: %s",
                    content.id, target_date, exc,
                )
                errors.append({'content_id': str(content.id), 'error': str(exc)})

        self.logger.info(
            "Snapshot creation for %s: %d processed, %d created, %d errors",
            target_date, len(content_list), snapshots_created, len(errors),
        )

        return {
            'content_processed': len(content_list),
            'snapshots_created': snapshots_created,
            'errors': errors,
        }

    def _aggregate_event_counts(self, content: Content, target_date: date) -> Dict:
        """Count events per type for one content item on one date."""
        counts = {}
        for event_type, field_name in self.EVENT_TO_SNAPSHOT_FIELD.items():
            counts[field_name] = AnalyticsEvent.objects.filter(
                content=content,
                occurred_at__date=target_date,
                event_type=event_type,
            ).count()
        return counts


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def rollup_campaign_budgets(**kwargs) -> Dict[str, Any]:
    """Convenience wrapper for BudgetRollupService.rollup_campaign_spend()."""
    return BudgetRollupService().rollup_campaign_spend(**kwargs)


def aggregate_link_stats(**kwargs) -> Dict[str, Any]:
    """Convenience wrapper for LinkStatsAggregationService.aggregate_link_stats()."""
    return LinkStatsAggregationService().aggregate_link_stats(**kwargs)


def create_content_snapshot(**kwargs) -> ContentSnapshot:
    """Convenience wrapper for ContentSnapshotService.create_snapshot()."""
    return ContentSnapshotService().create_snapshot(**kwargs)