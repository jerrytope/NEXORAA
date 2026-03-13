# SOCIAL_INTELLIGENCE/api/viewsets.py
"""
DRF ViewSets for Social Intelligence (UPDATED - Architecture Corrected)

ARCHITECTURE CHANGE:
- KPI calculations moved to ANALYTICS domain
- Social Intelligence focuses on perception (mentions, sentiment, topics)
- Uses read-only KPI API from Analytics

Provides REST API for:
- Tracked entities and keywords
- Mentions and sentiment
- Entity daily stats (social metrics only)
- Alerts
"""

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from datetime import date, timedelta

from SOCIAL_INTELLIGENCE.models import (
    TrackedEntity,
    EntityKeyword,
    EntityCompetitor,
    Mention,
    MentionEntity,
    MentionSentiment,
    MentionTopic,
    ExtractedKeyword,
    EntityDailyStat,
    Alert,
)

from SOCIAL_INTELLIGENCE.serializers import (
    TrackedEntitySerializer,
    TrackedEntityDetailSerializer,
    EntityKeywordSerializer,
    EntityCompetitorSerializer,
    MentionSerializer,
    MentionListSerializer,
    MentionDetailSerializer,
    MentionEntitySerializer,
    MentionSentimentSerializer,
    MentionTopicSerializer,
    ExtractedKeywordSerializer,
    EntityDailyStatSerializer,
    AlertSerializer,
    CampaignKPISerializer,
    CreatorKPISerializer,
    ContentKPISerializer,
    SentimentRollupSerializer,
)

# ARCHITECTURE CORRECTION: Import KPIs from Analytics domain (read-only)
from ANALYTICS.services.kpis import (
    get_campaign_kpis,
    get_creator_kpis,
    get_content_kpis,
)

# Social Intelligence services (perception only)
from SOCIAL_INTELLIGENCE.services.sentiment import SentimentProcessor

from ANALYTICS.models import Campaign, Creator, Content


# ============================================================================
# TRACKED ENTITIES
# ============================================================================

class TrackedEntityViewSet(viewsets.ModelViewSet):
    """
    ViewSet for TrackedEntity
    
    Filters:
    - entity_type: Filter by type (brand, person, product, etc.)
    - status: Filter by status (active, paused, archived)
    - brand: Filter by linked brand
    - creator: Filter by linked creator
    - campaign: Filter by linked campaign
    
    Actions:
    - sentiment: Get sentiment rollup
    - daily_stats: Get daily statistics
    """
    
    queryset = TrackedEntity.objects.select_related(
        'brand', 'creator', 'campaign'
    ).all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['entity_type', 'status', 'brand', 'creator', 'campaign']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'name']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Use detailed serializer for retrieve"""
        if self.action == 'retrieve':
            return TrackedEntityDetailSerializer
        return TrackedEntitySerializer
    
    @action(detail=True, methods=['get'])
    def sentiment(self, request, pk=None):
        """Get sentiment rollup for entity"""
        entity = self.get_object()
        
        from django.db.models import Avg, Count, Q
        
        stats = entity.sentiments.aggregate(
            total=Count('id'),
            avg_score=Avg('sentiment_score'),
            positive=Count('id', filter=Q(sentiment='positive')),
            negative=Count('id', filter=Q(sentiment='negative')),
            neutral=Count('id', filter=Q(sentiment='neutral')),
            mixed=Count('id', filter=Q(sentiment='mixed')),
        )
        
        serializer = SentimentRollupSerializer({
            'total_mentions': stats['total'] or 0,
            'avg_sentiment_score': float(stats['avg_score'] or 0),
            'positive_mentions': stats['positive'] or 0,
            'negative_mentions': stats['negative'] or 0,
            'neutral_mentions': stats['neutral'] or 0,
            'mixed_mentions': stats['mixed'] or 0,
            'sentiment_distribution': {
                'positive': stats['positive'] or 0,
                'negative': stats['negative'] or 0,
                'neutral': stats['neutral'] or 0,
                'mixed': stats['mixed'] or 0,
            }
        })
        
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def daily_stats(self, request, pk=None):
        """Get daily statistics for entity"""
        entity = self.get_object()
        
        # Get date range from query params
        days = int(request.query_params.get('days', 30))
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        stats = EntityDailyStat.objects.filter(
            entity=entity,
            date__gte=start_date,
            date__lte=end_date,
        ).order_by('date')
        
        serializer = EntityDailyStatSerializer(stats, many=True)
        
        return Response({
            'entity_id': str(entity.id),
            'entity_name': entity.name,
            'date_range': {
                'start': str(start_date),
                'end': str(end_date),
            },
            'stats': serializer.data,
        })


class EntityKeywordViewSet(viewsets.ModelViewSet):
    """
    ViewSet for EntityKeyword
    
    Filters:
    - entity: Filter by entity
    - keyword_type: Filter by type
    - is_active: Filter by active status
    """
    
    queryset = EntityKeyword.objects.select_related('entity').all()
    serializer_class = EntityKeywordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['entity', 'keyword_type', 'is_active']
    search_fields = ['keyword']
    ordering_fields = ['priority', 'created_at']
    ordering = ['-priority', 'keyword']


class EntityCompetitorViewSet(viewsets.ModelViewSet):
    """ViewSet for EntityCompetitor"""
    
    queryset = EntityCompetitor.objects.select_related('entity', 'competitor').all()
    serializer_class = EntityCompetitorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['entity', 'competitor']
    ordering_fields = ['priority', 'created_at']
    ordering = ['-priority']


# ============================================================================
# MENTIONS
# ============================================================================

class MentionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Mention (social posts)
    
    Filters:
    - platform: Filter by platform
    - creator: Filter by creator
    - language: Filter by language
    - is_processed: Filter by processing status
    - published_at__gte/lte: Filter by date
    
    Actions:
    - analyze_sentiment: Trigger sentiment analysis
    """
    
    queryset = Mention.objects.select_related('platform', 'creator').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        'platform': ['exact'],
        'creator': ['exact'],
        'language': ['exact'],
        'is_processed': ['exact'],
        'published_at': ['gte', 'lte', 'date'],
    }
    search_fields = ['text', 'author_username']
    ordering_fields = ['published_at', 'detected_at', 'likes_count']
    ordering = ['-published_at']
    
    def get_serializer_class(self):
        """Use appropriate serializer based on action"""
        if self.action == 'list':
            return MentionListSerializer
        elif self.action == 'retrieve':
            return MentionDetailSerializer
        return MentionSerializer
    
    @action(detail=True, methods=['post'])
    def analyze_sentiment(self, request, pk=None):
        """Trigger sentiment analysis for this mention"""
        mention = self.get_object()
        
        # Get entity_id from request
        entity_id = request.data.get('entity_id')
        if not entity_id:
            return Response(
                {'error': 'entity_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            entity = TrackedEntity.objects.get(id=entity_id)
        except TrackedEntity.DoesNotExist:
            return Response(
                {'error': 'Entity not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Analyze sentiment
        processor = SentimentProcessor()
        sentiment = processor.analyze_mention(mention, entity)
        
        serializer = MentionSentimentSerializer(sentiment)
        return Response(serializer.data)


class MentionEntityViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for MentionEntity (read-only)"""
    
    queryset = MentionEntity.objects.select_related(
        'mention', 'entity', 'keyword_matched'
    ).all()
    serializer_class = MentionEntitySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['mention', 'entity', 'keyword_matched']
    ordering = ['-created_at']


class MentionSentimentViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for MentionSentiment (read-only)"""
    
    queryset = MentionSentiment.objects.select_related('mention', 'entity').all()
    serializer_class = MentionSentimentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['mention', 'entity', 'sentiment']
    ordering = ['-analyzed_at']


# ============================================================================
# TOPICS & KEYWORDS
# ============================================================================

class MentionTopicViewSet(viewsets.ModelViewSet):
    """ViewSet for MentionTopic"""
    
    queryset = MentionTopic.objects.all()
    serializer_class = MentionTopicSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['mention', 'topic_category']
    ordering = ['-relevance_score']


class ExtractedKeywordViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for ExtractedKeyword (trending terms)
    
    Filters:
    - entity: Filter by entity
    - platform: Filter by platform
    
    Actions:
    - trending: Get trending keywords
    """
    
    queryset = ExtractedKeyword.objects.select_related('entity', 'platform').all()
    serializer_class = ExtractedKeywordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['entity', 'platform']
    ordering_fields = ['trending_score', 'mention_count', 'first_seen']
    ordering = ['-trending_score']
    
    @action(detail=False, methods=['get'])
    def trending(self, request):
        """Get top trending keywords"""
        limit = int(request.query_params.get('limit', 20))
        entity_id = request.query_params.get('entity')
        platform_id = request.query_params.get('platform')
        
        queryset = self.get_queryset()
        
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id)
        if platform_id:
            queryset = queryset.filter(platform_id=platform_id)
        
        trending = queryset.order_by('-trending_score')[:limit]
        serializer = self.get_serializer(trending, many=True)
        
        return Response(serializer.data)


# ============================================================================
# AGGREGATED STATS
# ============================================================================

class EntityDailyStatViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for EntityDailyStat (read-only)
    
    Filters:
    - entity: Filter by entity
    - platform: Filter by platform
    - date__gte/lte: Filter by date range
    """
    
    queryset = EntityDailyStat.objects.select_related('entity', 'platform').all()
    serializer_class = EntityDailyStatSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {
        'entity': ['exact'],
        'platform': ['exact'],
        'date': ['exact', 'gte', 'lte'],
    }
    ordering_fields = ['date', 'total_mentions']
    ordering = ['-date']


# ============================================================================
# ALERTS
# ============================================================================

class AlertViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Alert
    
    Filters:
    - entity: Filter by entity
    - alert_type: Filter by type
    - severity: Filter by severity
    - status: Filter by status
    
    Actions:
    - acknowledge: Acknowledge alert
    - resolve: Resolve alert
    - dismiss: Dismiss alert
    """
    
    queryset = Alert.objects.select_related(
        'entity', 'acknowledged_by', 'resolved_by'
    ).all()
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['entity', 'alert_type', 'severity', 'status']
    ordering_fields = ['triggered_at', 'severity']
    ordering = ['-triggered_at']
    
    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        """Acknowledge an alert"""
        alert = self.get_object()
        
        alert.status = 'acknowledged'
        alert.acknowledged_by = request.user
        alert.acknowledged_at = timezone.now()
        alert.save()
        
        serializer = self.get_serializer(alert)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Resolve an alert"""
        alert = self.get_object()
        
        alert.status = 'resolved'
        alert.resolved_by = request.user
        alert.resolved_at = timezone.now()
        alert.save()
        
        serializer = self.get_serializer(alert)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def dismiss(self, request, pk=None):
        """Dismiss an alert"""
        alert = self.get_object()
        
        alert.status = 'dismissed'
        alert.save()
        
        serializer = self.get_serializer(alert)
        return Response(serializer.data)


# ============================================================================
# ANALYTICS VIEWSETS (USING READ-ONLY ANALYTICS API)
# ============================================================================
# ARCHITECTURE NOTE:
# These ViewSets consume the Analytics KPI service (read-only).
# No KPI calculations happen in Social Intelligence domain.
# ============================================================================

class CampaignAnalyticsViewSet(viewsets.ViewSet):
    """
    ViewSet for Campaign Analytics
    
    ARCHITECTURE: Consumes Analytics domain KPIs (read-only)
    
    Provides KPIs and performance metrics for campaigns
    """
    
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'], url_path='(?P<campaign_id>[^/.]+)/kpis')
    def kpis(self, request, campaign_id=None):
        """
        Get KPIs for a campaign
        
        Uses: ANALYTICS.services.influencer_kpis.get_campaign_kpis()
        """
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return Response(
                {'error': 'Campaign not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # ARCHITECTURE CORRECTION: Use read-only API from Analytics
        kpis = get_campaign_kpis(
            campaign_id=str(campaign.id),
            start_date=request.query_params.get('start_date'),
            end_date=request.query_params.get('end_date'),
        )
        
        serializer = CampaignKPISerializer(kpis)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='(?P<campaign_id>[^/.]+)/sentiment')
    def sentiment(self, request, campaign_id=None):
        """
        Get sentiment rollup for a campaign
        
        Social Intelligence perception metrics (not performance KPIs)
        """
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return Response(
                {'error': 'Campaign not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        processor = SentimentProcessor()
        sentiment_data = processor.get_campaign_sentiment_rollup(campaign)
        
        serializer = SentimentRollupSerializer(sentiment_data)
        return Response(serializer.data)


class CreatorAnalyticsViewSet(viewsets.ViewSet):
    """
    ViewSet for Creator Analytics
    
    ARCHITECTURE: Consumes Analytics domain KPIs (read-only)
    
    Provides KPIs and performance metrics for creators
    """
    
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'], url_path='(?P<creator_id>[^/.]+)/kpis')
    def kpis(self, request, creator_id=None):
        """
        Get KPIs for a creator
        
        Uses: ANALYTICS.services.influencer_kpis.get_creator_campaign_kpis()
        """
        try:
            creator = Creator.objects.get(id=creator_id)
        except Creator.DoesNotExist:
            return Response(
                {'error': 'Creator not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Optional campaign filter
        campaign_id = request.query_params.get('campaign')
        
        if not campaign_id:
            return Response(
                {'error': 'campaign parameter required for creator KPIs'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return Response(
                {'error': 'Campaign not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # ARCHITECTURE CORRECTION: Use read-only API from Analytics
        kpis = get_creator_kpis(
            creator_id=str(creator.id),
            campaign_id=campaign_id,
            start_date=request.query_params.get('start_date'),
            end_date=request.query_params.get('end_date'),
        )
        
        serializer = CreatorKPISerializer(kpis)
        return Response(serializer.data)


class ContentAnalyticsViewSet(viewsets.ViewSet):
    """
    ViewSet for Content Analytics
    
    ARCHITECTURE: Consumes Analytics domain KPIs (read-only)
    
    Provides KPIs and performance metrics for content
    """
    
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'], url_path='(?P<content_id>[^/.]+)/kpis')
    def kpis(self, request, content_id=None):
        """
        Get KPIs for content
        
        Uses: ANALYTICS.services.influencer_kpis.get_content_kpis()
        """
        try:
            content = Content.objects.get(id=content_id)
        except Content.DoesNotExist:
            return Response(
                {'error': 'Content not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # ARCHITECTURE CORRECTION: Use read-only API from Analytics
        kpis = get_content_kpis(content_id=str(content.id))
        
        serializer = ContentKPISerializer(kpis)
        return Response(serializer.data)