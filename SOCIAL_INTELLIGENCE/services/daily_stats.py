"""
Daily Performance Stats Aggregation

Aggregates daily metrics for:
- Campaigns
- Creators
- Content

Sources: AnalyticsEvent, ContentSnapshot, LinkDailyStat
"""

import logging
from datetime import date, timedelta
from typing import Optional, Dict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Count, Avg, Max, Q
from django.utils import timezone

from ANALYTICS.models import (
    Campaign,
    Creator,
    Content,
    AnalyticsEvent,
    ContentSnapshot,
    LinkDailyStat,
)
from SOCIAL_INTELLIGENCE.models import EntityDailyStat, TrackedEntity

logger = logging.getLogger(__name__)


class DailyStatsAggregator:
    """
    Aggregate daily performance stats from various sources
    """
    
    def __init__(self):
        self.logger = logger
    
    def aggregate_campaign_daily(
        self,
        campaign: Campaign,
        target_date: Optional[date] = None,
    ) -> Dict:
        """
        Aggregate daily stats for campaign
        
        Metrics:
        - impressions (from ContentSnapshot)
        - clicks (from AnalyticsEvent/LinkDailyStat)
        - engagements (likes + comments + shares from ContentSnapshot)
        - video_views (from ContentSnapshot)
        - conversions (from AnalyticsEvent)
        """
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()
        
        with transaction.atomic():
            # Get clicks from events
            clicks = AnalyticsEvent.objects.filter(
                campaign=campaign,
                event_type='click',
                occurred_at__date=target_date,
            ).count()
            
            # Get conversions
            conversions = AnalyticsEvent.objects.filter(
                campaign=campaign,
                event_type='purchase',
                occurred_at__date=target_date,
            ).count()
            
            # Get content snapshots for this campaign on this date
            snapshots = ContentSnapshot.objects.filter(
                content__campaign=campaign,
                captured_at__date=target_date,
            )
            
            snapshot_stats = snapshots.aggregate(
                total_impressions=Sum('impressions'),
                total_views=Sum('views_count'),
                total_likes=Sum('likes_count'),
                total_comments=Sum('comments_count'),
                total_shares=Sum('shares_count'),
            )
            
            # Calculate engagements
            impressions = snapshot_stats['total_impressions'] or 0
            video_views = snapshot_stats['total_views'] or 0
            likes = snapshot_stats['total_likes'] or 0
            comments = snapshot_stats['total_comments'] or 0
            shares = snapshot_stats['total_shares'] or 0
            engagements = likes + comments + shares
            
            stats = {
                'campaign_id': str(campaign.id),
                'campaign_name': campaign.name,
                'date': str(target_date),
                'impressions': impressions,
                'clicks': clicks,
                'engagements': engagements,
                'video_views': video_views,
                'conversions': conversions,
                'breakdown': {
                    'likes': likes,
                    'comments': comments,
                    'shares': shares,
                }
            }
            
            self.logger.info(
                f"Campaign {campaign.name} daily stats for {target_date}: "
                f"{impressions} impressions, {clicks} clicks, {engagements} engagements"
            )
            
            return stats
    
    def aggregate_creator_daily(
        self,
        creator: Creator,
        target_date: Optional[date] = None,
        campaign: Optional[Campaign] = None,
    ) -> Dict:
        """
        Aggregate daily stats for creator
        
        Optionally filtered by campaign
        """
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()
        
        # Base filters
        content_filter = Q(creator=creator)
        event_filter = Q(creator=creator)
        
        if campaign:
            content_filter &= Q(campaign=campaign)
            event_filter &= Q(campaign=campaign)
        
        with transaction.atomic():
            # Get clicks
            clicks = AnalyticsEvent.objects.filter(
                event_filter,
                event_type='click',
                occurred_at__date=target_date,
            ).count()
            
            # Get conversions
            conversions = AnalyticsEvent.objects.filter(
                event_filter,
                event_type='purchase',
                occurred_at__date=target_date,
            ).count()
            
            # Get content snapshots
            snapshots = ContentSnapshot.objects.filter(
                content__in=Content.objects.filter(content_filter),
                captured_at__date=target_date,
            )
            
            snapshot_stats = snapshots.aggregate(
                total_impressions=Sum('impressions'),
                total_views=Sum('views_count'),
                total_likes=Sum('likes_count'),
                total_comments=Sum('comments_count'),
                total_shares=Sum('shares_count'),
            )
            
            impressions = snapshot_stats['total_impressions'] or 0
            video_views = snapshot_stats['total_views'] or 0
            likes = snapshot_stats['total_likes'] or 0
            comments = snapshot_stats['total_comments'] or 0
            shares = snapshot_stats['total_shares'] or 0
            engagements = likes + comments + shares
            
            stats = {
                'creator_id': str(creator.id),
                'creator_name': creator.name,
                'date': str(target_date),
                'campaign_id': str(campaign.id) if campaign else None,
                'impressions': impressions,
                'clicks': clicks,
                'engagements': engagements,
                'video_views': video_views,
                'conversions': conversions,
                'breakdown': {
                    'likes': likes,
                    'comments': comments,
                    'shares': shares,
                }
            }
            
            return stats
    
    def aggregate_content_daily(
        self,
        content: Content,
        target_date: Optional[date] = None,
    ) -> Dict:
        """
        Aggregate daily stats for specific content
        """
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()
        
        # Get snapshot
        snapshot = ContentSnapshot.objects.filter(
            content=content,
            captured_at__date=target_date,
        ).order_by('-captured_at').first()
        
        # Get clicks from events
        clicks = AnalyticsEvent.objects.filter(
            content=content,
            event_type='click',
            occurred_at__date=target_date,
        ).count()
        
        if snapshot:
            impressions = snapshot.impressions
            video_views = snapshot.views_count
            likes = snapshot.likes_count
            comments = snapshot.comments_count
            shares = snapshot.shares_count
            engagements = likes + comments + shares
        else:
            impressions = video_views = likes = comments = shares = engagements = 0
        
        return {
            'content_id': str(content.id),
            'content_title': content.title,
            'date': str(target_date),
            'impressions': impressions,
            'clicks': clicks,
            'engagements': engagements,
            'video_views': video_views,
            'breakdown': {
                'likes': likes,
                'comments': comments,
                'shares': shares,
            }
        }
    
    def aggregate_entity_daily(
        self,
        entity: TrackedEntity,
        target_date: Optional[date] = None,
        platform=None,
    ) -> EntityDailyStat:
        """
        Aggregate EntityDailyStat from mentions
        """
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()
        
        from SOCIAL_INTELLIGENCE.models import Mention, MentionEntity, MentionSentiment
        
        # Get mentions for this entity on this date
        mention_entities = MentionEntity.objects.filter(
            entity=entity,
            mention__published_at__date=target_date,
        )
        
        if platform:
            mention_entities = mention_entities.filter(mention__platform=platform)
        
        mentions = [me.mention for me in mention_entities]
        
        # Get sentiment stats
        sentiments = MentionSentiment.objects.filter(
            entity=entity,
            mention__published_at__date=target_date,
        )
        
        if platform:
            sentiments = sentiments.filter(mention__platform=platform)
        
        sentiment_stats = sentiments.aggregate(
            positive=Count('id', filter=Q(sentiment='positive')),
            negative=Count('id', filter=Q(sentiment='negative')),
            neutral=Count('id', filter=Q(sentiment='neutral')),
            avg_score=Avg('sentiment_score'),
        )
        
        # Aggregate mention metrics
        total_mentions = len(mentions)
        unique_authors = len(set(m.author_username for m in mentions))
        total_likes = sum(m.likes_count for m in mentions)
        total_comments = sum(m.comments_count for m in mentions)
        total_shares = sum(m.shares_count for m in mentions)
        total_views = sum(m.views_count for m in mentions)
        
        # Create or update stat
        stat, created = EntityDailyStat.objects.update_or_create(
            entity=entity,
            date=target_date,
            platform=platform,
            defaults={
                'total_mentions': total_mentions,
                'unique_authors': unique_authors,
                'total_likes': total_likes,
                'total_comments': total_comments,
                'total_shares': total_shares,
                'total_views': total_views,
                'positive_mentions': sentiment_stats['positive'] or 0,
                'negative_mentions': sentiment_stats['negative'] or 0,
                'neutral_mentions': sentiment_stats['neutral'] or 0,
                'avg_sentiment_score': sentiment_stats['avg_score'],
            }
        )
        
        action = 'Created' if created else 'Updated'
        self.logger.info(
            f"{action} EntityDailyStat for {entity.name} on {target_date}: "
            f"{total_mentions} mentions, {unique_authors} authors"
        )
        
        return stat


# Convenience functions
def get_campaign_daily_stats(campaign: Campaign, target_date: date = None) -> Dict:
    """Get daily stats for campaign"""
    aggregator = DailyStatsAggregator()
    return aggregator.aggregate_campaign_daily(campaign, target_date)


def get_creator_daily_stats(creator: Creator, target_date: date = None, campaign: Campaign = None) -> Dict:
    """Get daily stats for creator"""
    aggregator = DailyStatsAggregator()
    return aggregator.aggregate_creator_daily(creator, target_date, campaign)