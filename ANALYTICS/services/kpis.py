# SOCIAL_INTELLIGENCE/services/kpis.py
"""
Influencer Campaign KPI Calculator

Computes:
- Engagement Rate
- CPC (Cost per Click)
- CPM (Cost per 1,000 Impressions)
- CPE (Cost per Engagement)
- Hook Rate (video-specific)
- Video Watch Rate
- Conversion Rate

All metrics are derived from existing data, not stored.

FIX: CreatorContract moved to top-level imports.
FIX: _calculate_cpc/cpm/cpe return Decimal for precision — callers
     should convert to float/str only at serialization time.
"""

import logging
from typing import Optional, Dict
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum

from ANALYTICS.models import (
    Campaign,
    Creator,
    Content,
    AnalyticsEvent,
    ContentSnapshot,
    CreatorContract,       # FIX: moved from inside calculate_creator_kpis()
)

logger = logging.getLogger(__name__)

# Rounding precision for KPI output
_TWO_PLACES = Decimal('0.01')


class InfluencerKPICalculator:
    """
    Calculate influencer marketing KPIs.

    All metrics are computed on-the-fly, never stored.
    Cost metrics (CPC, CPM, CPE) are returned as Decimal to preserve
    precision — convert to float/str at the serialization layer.
    """

    def __init__(self):
        self.logger = logger

    # =========================================================================
    # PUBLIC: CAMPAIGN KPIs
    # =========================================================================

    def calculate_campaign_kpis(
        self,
        campaign: Campaign,
        start_date=None,
        end_date=None,
    ) -> Dict:
        """
        Calculate all KPIs for a campaign.

        Returns a comprehensive KPI dict. Cost metrics are Decimal;
        rate metrics are float percentages (or None if undefinable).
        """
        budget_spent = campaign.budget_spent  # Decimal

        # Event counts
        events = AnalyticsEvent.objects.filter(campaign=campaign)
        if start_date:
            events = events.filter(occurred_at__gte=start_date)
        if end_date:
            events = events.filter(occurred_at__lte=end_date)

        clicks = events.filter(event_type='click').count()
        conversions = events.filter(event_type='purchase').count()

        # Content snapshots (latest per content — PostgreSQL distinct on)
        snapshots = ContentSnapshot.objects.filter(content__campaign=campaign)
        if start_date:
            snapshots = snapshots.filter(captured_at__gte=start_date)
        if end_date:
            snapshots = snapshots.filter(captured_at__lte=end_date)

        latest_snapshots = (
            snapshots.order_by('content', '-captured_at').distinct('content')
        )

        agg = latest_snapshots.aggregate(
            total_impressions=Sum('impressions'),
            total_likes=Sum('likes_count'),
            total_comments=Sum('comments_count'),
            total_shares=Sum('shares_count'),
            total_views=Sum('views_count'),
        )

        impressions = agg['total_impressions'] or 0
        likes       = agg['total_likes']       or 0
        comments    = agg['total_comments']    or 0
        shares      = agg['total_shares']      or 0
        video_views = agg['total_views']       or 0
        engagements = likes + comments + shares

        return {
            'campaign_id':   str(campaign.id),
            'campaign_name': campaign.name,
            'budget_spent':  str(budget_spent),

            # Raw metrics
            'impressions':  impressions,
            'clicks':       clicks,
            'engagements':  engagements,
            'video_views':  video_views,
            'conversions':  conversions,

            'engagement_breakdown': {
                'likes':    likes,
                'comments': comments,
                'shares':   shares,
            },

            # Calculated KPIs
            'engagement_rate': self._calculate_engagement_rate(engagements, impressions),
            'cpc':             self._to_str(self._calculate_cpc(budget_spent, clicks)),
            'cpm':             self._to_str(self._calculate_cpm(budget_spent, impressions)),
            'cpe':             self._to_str(self._calculate_cpe(budget_spent, engagements)),
            'video_watch_rate': self._calculate_video_watch_rate(video_views, impressions),
            'conversion_rate':  self._calculate_conversion_rate(conversions, clicks),
        }

    # =========================================================================
    # PUBLIC: CREATOR KPIs
    # =========================================================================

    def calculate_creator_kpis(
        self,
        creator: Creator,
        campaign: Optional[Campaign] = None,
        start_date=None,
        end_date=None,
    ) -> Dict:
        """
        Calculate KPIs for a creator, optionally scoped to a campaign.
        """
        content_qs = Content.objects.filter(creator=creator)
        if campaign:
            content_qs = content_qs.filter(campaign=campaign)

        events = AnalyticsEvent.objects.filter(creator=creator)
        if campaign:
            events = events.filter(campaign=campaign)
        if start_date:
            events = events.filter(occurred_at__gte=start_date)
        if end_date:
            events = events.filter(occurred_at__lte=end_date)

        clicks      = events.filter(event_type='click').count()
        conversions = events.filter(event_type='purchase').count()

        snapshots = ContentSnapshot.objects.filter(content__in=content_qs)
        if start_date:
            snapshots = snapshots.filter(captured_at__gte=start_date)
        if end_date:
            snapshots = snapshots.filter(captured_at__lte=end_date)

        latest_snapshots = (
            snapshots.order_by('content', '-captured_at').distinct('content')
        )

        agg = latest_snapshots.aggregate(
            total_impressions=Sum('impressions'),
            total_likes=Sum('likes_count'),
            total_comments=Sum('comments_count'),
            total_shares=Sum('shares_count'),
            total_views=Sum('views_count'),
        )

        impressions = agg['total_impressions'] or 0
        likes       = agg['total_likes']       or 0
        comments    = agg['total_comments']    or 0
        shares      = agg['total_shares']      or 0
        video_views = agg['total_views']       or 0
        engagements = likes + comments + shares

        # FIX: CreatorContract is now imported at the top of the file
        creator_cost = Decimal('0.00')
        if campaign:
            contract = CreatorContract.objects.filter(
                campaign=campaign,
                creator=creator,
            ).first()
            if contract:
                creator_cost = contract.contracted_amount

        return {
            'creator_id':   str(creator.id),
            'creator_name': creator.name,
            'campaign_id':  str(campaign.id) if campaign else None,
            'creator_cost': str(creator_cost),

            # Raw metrics
            'impressions':  impressions,
            'clicks':       clicks,
            'engagements':  engagements,
            'video_views':  video_views,
            'conversions':  conversions,

            # Calculated KPIs
            'engagement_rate':  self._calculate_engagement_rate(engagements, impressions),
            'cpc':              self._to_str(self._calculate_cpc(creator_cost, clicks)),
            'cpm':              self._to_str(self._calculate_cpm(creator_cost, impressions)),
            'cpe':              self._to_str(self._calculate_cpe(creator_cost, engagements)),
            'video_watch_rate': self._calculate_video_watch_rate(video_views, impressions),
        }

    # =========================================================================
    # PUBLIC: CONTENT KPIs
    # =========================================================================

    def calculate_content_kpis(self, content: Content) -> Dict:
        """
        Calculate KPIs for a specific piece of content.
        """
        snapshot = (
            ContentSnapshot.objects
            .filter(content=content)
            .order_by('-captured_at')
            .first()
        )

        clicks = AnalyticsEvent.objects.filter(
            content=content, event_type='click'
        ).count()

        if snapshot:
            impressions = snapshot.impressions
            likes       = snapshot.likes_count
            comments    = snapshot.comments_count
            shares      = snapshot.shares_count
            video_views = snapshot.views_count
            engagements = likes + comments + shares

            platform_metrics = snapshot.platform_metrics or {}
            three_sec_views  = platform_metrics.get('3s_views', 0)
            avg_watch_time   = platform_metrics.get('avg_watch_time', 0)
        else:
            impressions = likes = comments = shares = video_views = engagements = 0
            three_sec_views = avg_watch_time = 0

        return {
            'content_id':    str(content.id),
            'content_title': getattr(content, 'title', str(content.id)),

            # Raw metrics
            'impressions':  impressions,
            'clicks':       clicks,
            'engagements':  engagements,
            'video_views':  video_views,

            'engagement_breakdown': {
                'likes':    likes,
                'comments': comments,
                'shares':   shares,
            },

            # Calculated KPIs
            'engagement_rate':  self._calculate_engagement_rate(engagements, impressions),
            'video_watch_rate': self._calculate_video_watch_rate(video_views, impressions),
            'hook_rate':        self._calculate_hook_rate(three_sec_views, impressions),
            'avg_watch_time':   avg_watch_time,
        }

    # =========================================================================
    # PRIVATE: KPI CALCULATIONS
    # All rate methods return float % or None.
    # All cost methods return Decimal or None (precision preserved).
    # =========================================================================

    def _calculate_engagement_rate(
        self, engagements: int, impressions: int
    ) -> Optional[float]:
        """Engagement Rate = (engagements / impressions) × 100"""
        if not impressions:
            return None
        return round((engagements / impressions) * 100, 2)

    def _calculate_cpc(
        self, budget_spent: Decimal, clicks: int
    ) -> Optional[Decimal]:
        """
        CPC = budget_spent / clicks

        FIX: Returns Decimal (not float) to preserve monetary precision.
        Use _to_str() when serializing to JSON.
        """
        if not clicks:
            return None
        return (budget_spent / clicks).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    def _calculate_cpm(
        self, budget_spent: Decimal, impressions: int
    ) -> Optional[Decimal]:
        """
        CPM = (budget_spent / impressions) × 1000

        FIX: Returns Decimal (not float) to preserve monetary precision.
        """
        if not impressions:
            return None
        return (
            (budget_spent / impressions) * 1000
        ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    def _calculate_cpe(
        self, budget_spent: Decimal, engagements: int
    ) -> Optional[Decimal]:
        """
        CPE = budget_spent / engagements

        FIX: Returns Decimal (not float) to preserve monetary precision.
        """
        if not engagements:
            return None
        return (budget_spent / engagements).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    def _calculate_video_watch_rate(
        self, video_views: int, impressions: int
    ) -> Optional[float]:
        """Video Watch Rate = (video_views / impressions) × 100"""
        if not impressions:
            return None
        return round((video_views / impressions) * 100, 2)

    def _calculate_hook_rate(
        self, three_sec_views: int, impressions: int
    ) -> Optional[float]:
        """Hook Rate = (3s_views / impressions) × 100"""
        if not impressions:
            return None
        return round((three_sec_views / impressions) * 100, 2)

    def _calculate_conversion_rate(
        self, conversions: int, clicks: int
    ) -> Optional[float]:
        """Conversion Rate = (conversions / clicks) × 100"""
        if not clicks:
            return None
        return round((conversions / clicks) * 100, 2)

    @staticmethod
    def _to_str(value: Optional[Decimal]) -> Optional[str]:
        """
        Convert Decimal KPI to string for JSON serialization.
        Returns None as-is so the API response shows null when undefined.
        """
        return str(value) if value is not None else None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_campaign_kpis(campaign: Campaign) -> Dict:
    return InfluencerKPICalculator().calculate_campaign_kpis(campaign)


def get_creator_kpis(creator: Creator, campaign: Campaign = None) -> Dict:
    return InfluencerKPICalculator().calculate_creator_kpis(creator, campaign)


def get_content_kpis(content: Content) -> Dict:
    return InfluencerKPICalculator().calculate_content_kpis(content)