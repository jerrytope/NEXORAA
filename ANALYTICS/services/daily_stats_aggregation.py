# ANALYTICS/services/daily_stats.py
"""
Daily Statistics Aggregation Service

Idempotent aggregation of daily stats from AnalyticsEvent and ContentSnapshot.

Explicitly computes and stores:
- total_clicks, total_comments, total_shares, total_saves
- total_engagements (sum of all engagement types)
- All aggregations derived from events (no manual increments)
- Re-running does NOT double-count (update_or_create pattern)

FIX: NULL visitor_id values are excluded from unique visitor counts
     across all three aggregator methods.
"""

import logging
from datetime import date, timedelta
from typing import Optional, Dict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone

from ANALYTICS.models import (
    Campaign,
    Creator,
    Content,
    AnalyticsEvent,
    ContentSnapshot,
    CampaignExpense,
    ContentDailyStat,
    CreatorDailyStat,
    CampaignDailyStat,
)

logger = logging.getLogger(__name__)


class DailyStatsAggregator:
    """
    Aggregate daily performance stats with explicit engagement metrics.

    All operations are idempotent — safe to rerun without double-counting.
    """

    def __init__(self):
        self.logger = logger

    # =========================================================================
    # CONTENT DAILY STATS
    # =========================================================================

    def aggregate_content_daily(
        self,
        content: Content,
        target_date: Optional[date] = None,
    ) -> Dict:
        """
        Aggregate daily stats for a single content item.
        Idempotent: uses update_or_create.
        """
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()

        with transaction.atomic():
            # Latest snapshot on this date
            snapshot = ContentSnapshot.objects.filter(
                content=content,
                captured_at__date=target_date,
            ).order_by('-captured_at').first()

            # Click events for this date
            click_events = AnalyticsEvent.objects.filter(
                content=content,
                event_type='click',
                occurred_at__date=target_date,
            )

            total_clicks = click_events.count()

            # FIX: filter out NULL visitor_id / session_id before distinct count
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

            # Conversion events
            conversions_qs = AnalyticsEvent.objects.filter(
                content=content,
                event_type='purchase',
                occurred_at__date=target_date,
            )
            conversion_count = conversions_qs.count()
            conversion_value = (
                conversions_qs.aggregate(total=Sum('conversion_value'))['total']
                or Decimal('0.00')
            )

            # Extract metrics from snapshot
            if snapshot:
                impressions = snapshot.impressions
                reach = snapshot.reach
                video_views = snapshot.views_count
                total_likes = snapshot.likes_count
                total_comments = snapshot.comments_count
                total_shares = snapshot.shares_count
                total_saves = snapshot.saves_count or 0
                platform_metrics = snapshot.platform_metrics or {}
                avg_watch_time = platform_metrics.get('avg_watch_time')
                video_completion_rate = platform_metrics.get('completion_rate')
            else:
                impressions = reach = video_views = 0
                total_likes = total_comments = total_shares = total_saves = 0
                avg_watch_time = video_completion_rate = None

            stat, created = ContentDailyStat.objects.update_or_create(
                content=content,
                date=target_date,
                defaults={
                    'impressions': impressions,
                    'reach': reach,
                    'video_views': video_views,
                    'total_likes': total_likes,
                    'total_comments': total_comments,
                    'total_shares': total_shares,
                    'total_saves': total_saves,
                    'total_clicks': total_clicks,
                    'unique_visitors': unique_visitors,
                    'unique_sessions': unique_sessions,
                    'conversions': conversion_count,
                    'conversion_value': conversion_value,
                    'avg_watch_time': avg_watch_time,
                    'video_completion_rate': video_completion_rate,
                }
            )

            action = 'Created' if created else 'Updated'
            self.logger.info(
                "%s ContentDailyStat for '%s' on %s",
                action, content.title, target_date,
            )

            return {
                'content_id': str(content.id),
                'date': str(target_date),
                'impressions': impressions,
                'total_clicks': total_clicks,
                'total_likes': total_likes,
                'total_comments': total_comments,
                'total_shares': total_shares,
                'total_saves': total_saves,
                'total_engagements': (
                    total_likes + total_comments + total_shares + total_saves
                ),
            }

    # =========================================================================
    # CREATOR DAILY STATS
    # =========================================================================

    def aggregate_creator_daily(
        self,
        creator: Creator,
        target_date: Optional[date] = None,
        campaign: Optional[Campaign] = None,
    ) -> Dict:
        """
        Aggregate daily stats for a creator, optionally scoped to a campaign.
        Idempotent: uses update_or_create.
        """
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()

        with transaction.atomic():
            # Creator's content (optionally campaign-scoped)
            content_qs = Content.objects.filter(creator=creator)
            if campaign:
                content_qs = content_qs.filter(campaign=campaign)

            # Snapshot metrics
            snapshots = ContentSnapshot.objects.filter(
                content__in=content_qs,
                captured_at__date=target_date,
            )
            snapshot_stats = snapshots.aggregate(
                total_impressions=Sum('impressions'),
                total_reach=Sum('reach'),
                total_views=Sum('views_count'),
                total_likes=Sum('likes_count'),
                total_comments=Sum('comments_count'),
                total_shares=Sum('shares_count'),
                total_saves=Sum('saves_count'),
            )

            impressions = snapshot_stats['total_impressions'] or 0
            reach = snapshot_stats['total_reach'] or 0
            video_views = snapshot_stats['total_views'] or 0
            total_likes = snapshot_stats['total_likes'] or 0
            total_comments = snapshot_stats['total_comments'] or 0
            total_shares = snapshot_stats['total_shares'] or 0
            total_saves = snapshot_stats['total_saves'] or 0

            # Click events
            click_filter = Q(
                creator=creator,
                event_type='click',
                occurred_at__date=target_date,
            )
            if campaign:
                click_filter &= Q(campaign=campaign)

            click_events = AnalyticsEvent.objects.filter(click_filter)
            total_clicks = click_events.count()

            # FIX: filter out NULL visitor_id / session_id before distinct count
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

            # Conversion events
            conversion_filter = Q(
                creator=creator,
                event_type='purchase',
                occurred_at__date=target_date,
            )
            if campaign:
                conversion_filter &= Q(campaign=campaign)

            conversions_qs = AnalyticsEvent.objects.filter(conversion_filter)
            conversion_count = conversions_qs.count()
            conversion_value = (
                conversions_qs.aggregate(total=Sum('conversion_value'))['total']
                or Decimal('0.00')
            )

            # Content posted this day
            content_posted = content_qs.filter(
                published_at__date=target_date
            ).count()

            stat, created = CreatorDailyStat.objects.update_or_create(
                creator=creator,
                date=target_date,
                campaign=campaign,
                defaults={
                    'impressions': impressions,
                    'reach': reach,
                    'video_views': video_views,
                    'total_likes': total_likes,
                    'total_comments': total_comments,
                    'total_shares': total_shares,
                    'total_saves': total_saves,
                    'total_clicks': total_clicks,
                    'unique_visitors': unique_visitors,
                    'unique_sessions': unique_sessions,
                    'conversions': conversion_count,
                    'conversion_value': conversion_value,
                    'content_posted': content_posted,
                }
            )

            action = 'Created' if created else 'Updated'
            campaign_str = f" (campaign: {campaign.name})" if campaign else ""
            self.logger.info(
                "%s CreatorDailyStat for '%s'%s on %s",
                action, creator.name, campaign_str, target_date,
            )

            return {
                'creator_id': str(creator.id),
                'date': str(target_date),
                'campaign_id': str(campaign.id) if campaign else None,
                'impressions': impressions,
                'total_clicks': total_clicks,
                'total_likes': total_likes,
                'total_comments': total_comments,
                'total_shares': total_shares,
                'total_saves': total_saves,
                'total_engagements': (
                    total_likes + total_comments + total_shares + total_saves
                ),
            }

    # =========================================================================
    # CAMPAIGN DAILY STATS
    # =========================================================================

    def aggregate_campaign_daily(
        self,
        campaign: Campaign,
        target_date: Optional[date] = None,
    ) -> Dict:
        """
        Aggregate daily stats for a campaign.
        Idempotent: uses update_or_create.

        NOTE on budget_spent_today: we filter by expense_date (the date the
        expense was incurred), not approved_at. This means the daily figure
        reflects what was spent on that day regardless of when it was approved.
        Change to approved_at__date if you prefer approval-date accounting.
        """
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()

        with transaction.atomic():
            content_qs = Content.objects.filter(campaign=campaign)

            # Snapshot metrics
            snapshots = ContentSnapshot.objects.filter(
                content__in=content_qs,
                captured_at__date=target_date,
            )
            snapshot_stats = snapshots.aggregate(
                total_impressions=Sum('impressions'),
                total_reach=Sum('reach'),
                total_views=Sum('views_count'),
                total_likes=Sum('likes_count'),
                total_comments=Sum('comments_count'),
                total_shares=Sum('shares_count'),
                total_saves=Sum('saves_count'),
            )

            impressions = snapshot_stats['total_impressions'] or 0
            reach = snapshot_stats['total_reach'] or 0
            video_views = snapshot_stats['total_views'] or 0
            total_likes = snapshot_stats['total_likes'] or 0
            total_comments = snapshot_stats['total_comments'] or 0
            total_shares = snapshot_stats['total_shares'] or 0
            total_saves = snapshot_stats['total_saves'] or 0

            # Click events
            click_events = AnalyticsEvent.objects.filter(
                campaign=campaign,
                event_type='click',
                occurred_at__date=target_date,
            )
            total_clicks = click_events.count()

            # FIX: filter out NULL visitor_id / session_id before distinct count
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

            # Conversion events
            conversions_qs = AnalyticsEvent.objects.filter(
                campaign=campaign,
                event_type='purchase',
                occurred_at__date=target_date,
            )
            conversion_count = conversions_qs.count()
            conversion_value = (
                conversions_qs.aggregate(total=Sum('conversion_value'))['total']
                or Decimal('0.00')
            )

            # FIX (minor): use expense_date not approved_at__date
            # so today's spend reflects what was incurred today
            budget_spent_today = (
                CampaignExpense.objects.filter(
                    campaign=campaign,
                    is_approved=True,
                    expense_date=target_date,      # ← was approved_at__date
                ).aggregate(total=Sum('amount'))['total']
                or Decimal('0.00')
            )

            content_posted = content_qs.filter(
                published_at__date=target_date
            ).count()

            active_creators = (
                content_qs
                .filter(published_at__date=target_date)
                .values('creator')
                .distinct()
                .count()
            )

            stat, created = CampaignDailyStat.objects.update_or_create(
                campaign=campaign,
                date=target_date,
                defaults={
                    'impressions': impressions,
                    'reach': reach,
                    'video_views': video_views,
                    'total_likes': total_likes,
                    'total_comments': total_comments,
                    'total_shares': total_shares,
                    'total_saves': total_saves,
                    'total_clicks': total_clicks,
                    'unique_visitors': unique_visitors,
                    'unique_sessions': unique_sessions,
                    'conversions': conversion_count,
                    'conversion_value': conversion_value,
                    'budget_spent_today': budget_spent_today,
                    'content_posted': content_posted,
                    'active_creators': active_creators,
                }
            )

            action = 'Created' if created else 'Updated'
            self.logger.info(
                "%s CampaignDailyStat for '%s' on %s",
                action, campaign.name, target_date,
            )

            return {
                'campaign_id': str(campaign.id),
                'date': str(target_date),
                'impressions': impressions,
                'total_clicks': total_clicks,
                'total_likes': total_likes,
                'total_comments': total_comments,
                'total_shares': total_shares,
                'total_saves': total_saves,
                'total_engagements': (
                    total_likes + total_comments + total_shares + total_saves
                ),
            }

    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================

    def aggregate_all_content_for_date(
        self,
        target_date: Optional[date] = None,
    ) -> Dict:
        """Aggregate stats for all active content on a specific date."""
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()

        content_items = Content.objects.filter(is_active=True)
        total = content_items.count()
        success = errors = 0

        for content in content_items:
            try:
                self.aggregate_content_daily(content, target_date)
                success += 1
            except Exception as exc:
                self.logger.error(
                    "Error aggregating content %s: %s", content.id, exc
                )
                errors += 1

        self.logger.info(
            "Content daily stats done: %d/%d succeeded, %d errors",
            success, total, errors,
        )
        return {'date': str(target_date), 'total': total,
                'success': success, 'errors': errors}

    def aggregate_all_creators_for_date(
        self,
        target_date: Optional[date] = None,
    ) -> Dict:
        """Aggregate stats for all active creators on a specific date."""
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()

        creators = Creator.objects.filter(is_active=True)
        total = creators.count()
        success = errors = 0

        for creator in creators:
            try:
                self.aggregate_creator_daily(creator, target_date)
                success += 1
            except Exception as exc:
                self.logger.error(
                    "Error aggregating creator %s: %s", creator.id, exc
                )
                errors += 1

        return {'date': str(target_date), 'total': total,
                'success': success, 'errors': errors}

    def aggregate_all_campaigns_for_date(
        self,
        target_date: Optional[date] = None,
    ) -> Dict:
        """Aggregate stats for all active campaigns on a specific date."""
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()

        campaigns = Campaign.objects.filter(is_active=True)
        total = campaigns.count()
        success = errors = 0

        for campaign in campaigns:
            try:
                self.aggregate_campaign_daily(campaign, target_date)
                success += 1
            except Exception as exc:
                self.logger.error(
                    "Error aggregating campaign %s: %s", campaign.id, exc
                )
                errors += 1

        return {'date': str(target_date), 'total': total,
                'success': success, 'errors': errors}


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def aggregate_daily_stats(target_date: Optional[date] = None) -> Dict:
    """
    Aggregate all daily stats (content, creator, campaign) for a date.
    Idempotent: safe to run multiple times.
    """
    aggregator = DailyStatsAggregator()
    resolved_date = target_date or (timezone.now() - timedelta(days=1)).date()

    return {
        'date': str(resolved_date),
        'content': aggregator.aggregate_all_content_for_date(resolved_date),
        'creators': aggregator.aggregate_all_creators_for_date(resolved_date),
        'campaigns': aggregator.aggregate_all_campaigns_for_date(resolved_date),
    }