"""
DRF Serializers for Social Intelligence Models

Provides JSON serialization for:
- TrackedEntity (brands, people, products being monitored)
- Mention (social posts detected)
- EntityKeyword (detection rules)
- MentionSentiment (sentiment analysis)
- EntityDailyStat (aggregated daily stats)
- Alert (notifications)
"""

from rest_framework import serializers
from django.utils import timezone

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


# ============================================================================
# TRACKED ENTITIES
# ============================================================================

class TrackedEntitySerializer(serializers.ModelSerializer):
    """Serializer for TrackedEntity"""
    
    # Related entity names
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    creator_name = serializers.CharField(source='creator.name', read_only=True)
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    
    # Stats
    total_mentions = serializers.SerializerMethodField()
    avg_sentiment = serializers.SerializerMethodField()
    
    class Meta:
        model = TrackedEntity
        fields = [
            'id',
            'name',
            'entity_type',
            'description',
            'status',
            
            # Links to Nexora entities
            'brand',
            'brand_name',
            'creator',
            'creator_name',
            'campaign',
            'campaign_name',
            
            # Stats
            'total_mentions',
            'avg_sentiment',
            
            # Metadata
            'metadata',
            'created_at',
            'updated_at',
            'tracking_started_at',
            'tracking_ended_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_mentions(self, obj):
        """Get total mentions count"""
        return obj.mentions.count()
    
    def get_avg_sentiment(self, obj):
        """Get average sentiment score"""
        from django.db.models import Avg
        result = obj.sentiments.aggregate(avg=Avg('sentiment_score'))
        avg = result['avg']
        return round(float(avg), 2) if avg else None


class EntityKeywordSerializer(serializers.ModelSerializer):
    """Serializer for EntityKeyword"""
    
    entity_name = serializers.CharField(source='entity.name', read_only=True)
    
    class Meta:
        model = EntityKeyword
        fields = [
            'id',
            'entity',
            'entity_name',
            'keyword',
            'keyword_type',
            'match_rule',
            'case_sensitive',
            'priority',
            'is_active',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class EntityCompetitorSerializer(serializers.ModelSerializer):
    """Serializer for EntityCompetitor"""
    
    entity_name = serializers.CharField(source='entity.name', read_only=True)
    competitor_name = serializers.CharField(source='competitor.name', read_only=True)
    
    class Meta:
        model = EntityCompetitor
        fields = [
            'id',
            'entity',
            'entity_name',
            'competitor',
            'competitor_name',
            'relationship_type',
            'priority',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        """Prevent self-competition"""
        entity = data.get('entity')
        competitor = data.get('competitor')
        
        if entity and competitor and entity.id == competitor.id:
            raise serializers.ValidationError(
                'An entity cannot be its own competitor'
            )
        
        return data


# ============================================================================
# MENTIONS
# ============================================================================

class MentionSerializer(serializers.ModelSerializer):
    """Serializer for Mention (social posts)"""
    
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    creator_name = serializers.CharField(source='creator.name', read_only=True)
    
    # Detected entities
    detected_entity_names = serializers.SerializerMethodField()
    
    class Meta:
        model = Mention
        fields = [
            'id',
            'platform',
            'platform_name',
            'external_post_id',
            
            # Content
            'text',
            'author_username',
            'author_display_name',
            'author_profile_url',
            
            # Creator link
            'creator',
            'creator_name',
            
            # Post details
            'post_url',
            'post_type',
            'language',
            
            # Media
            'has_image',
            'has_video',
            'media_urls',
            
            # Engagement metrics (snapshot)
            'likes_count',
            'comments_count',
            'shares_count',
            'views_count',
            
            # Detected entities
            'detected_entity_names',
            
            # Timing
            'published_at',
            'detected_at',
            'is_processed',
            
            # Raw data
            'raw_data',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'detected_at', 'created_at', 'updated_at']
    
    def get_detected_entity_names(self, obj):
        """Get list of detected entity names"""
        return list(
            obj.detected_entities.values_list('entity__name', flat=True)
        )


class MentionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing mentions"""
    
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    
    class Meta:
        model = Mention
        fields = [
            'id',
            'platform_name',
            'author_username',
            'text',
            'published_at',
            'likes_count',
            'comments_count',
            'shares_count',
        ]
        read_only_fields = [
            'id', 'platform_name', 'author_username', 'text',
            'published_at', 'likes_count', 'comments_count', 'shares_count',
        ]


class MentionEntitySerializer(serializers.ModelSerializer):
    """Serializer for MentionEntity (join table)"""
    
    entity_name = serializers.CharField(source='entity.name', read_only=True)
    keyword_text = serializers.CharField(source='keyword_matched.keyword', read_only=True)
    mention_text = serializers.CharField(source='mention.text', read_only=True)
    
    class Meta:
        model = MentionEntity
        fields = [
            'id',
            'mention',
            'mention_text',
            'entity',
            'entity_name',
            'keyword_matched',
            'keyword_text',
            'match_score',
            'match_context',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


# ============================================================================
# SENTIMENT
# ============================================================================

class MentionSentimentSerializer(serializers.ModelSerializer):
    """Serializer for MentionSentiment"""
    
    entity_name = serializers.CharField(source='entity.name', read_only=True)
    mention_author = serializers.CharField(source='mention.author_username', read_only=True)
    mention_text = serializers.CharField(source='mention.text', read_only=True)
    
    class Meta:
        model = MentionSentiment
        fields = [
            'id',
            'mention',
            'mention_author',
            'mention_text',
            'entity',
            'entity_name',
            'sentiment',
            'sentiment_score',
            'confidence',
            'analyzer',
            'sentiment_context',
            'analysis_metadata',
            'analyzed_at',
        ]
        read_only_fields = ['id', 'analyzed_at']


# ============================================================================
# TOPICS & KEYWORDS
# ============================================================================

class MentionTopicSerializer(serializers.ModelSerializer):
    """Serializer for MentionTopic"""
    
    class Meta:
        model = MentionTopic
        fields = [
            'id',
            'mention',
            'topic_name',
            'topic_category',
            'relevance_score',
            'topic_metadata',
            'detected_at',
        ]
        read_only_fields = ['id', 'detected_at']


class ExtractedKeywordSerializer(serializers.ModelSerializer):
    """Serializer for ExtractedKeyword (trending terms)"""
    
    entity_name = serializers.CharField(source='entity.name', read_only=True)
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    
    class Meta:
        model = ExtractedKeyword
        fields = [
            'id',
            'keyword',
            'entity',
            'entity_name',
            'platform',
            'platform_name',
            'mention_count',
            'first_seen',
            'last_seen',
            'trending_score',
            'growth_rate',
            'keyword_type',
            'metadata',
        ]
        read_only_fields = ['id', 'first_seen', 'last_seen']


# ============================================================================
# AGGREGATED STATS
# ============================================================================

class EntityDailyStatSerializer(serializers.ModelSerializer):
    """Serializer for EntityDailyStat"""
    
    entity_name = serializers.CharField(source='entity.name', read_only=True)
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    
    # Calculated fields
    engagement_total = serializers.SerializerMethodField()
    sentiment_ratio = serializers.SerializerMethodField()
    
    class Meta:
        model = EntityDailyStat
        fields = [
            'id',
            'entity',
            'entity_name',
            'date',
            'platform',
            'platform_name',
            
            # Volume metrics
            'total_mentions',
            'unique_authors',
            
            # Engagement totals
            'total_likes',
            'total_comments',
            'total_shares',
            'total_views',
            'engagement_total',
            
            # Sentiment aggregates
            'positive_mentions',
            'negative_mentions',
            'neutral_mentions',
            'avg_sentiment_score',
            'sentiment_ratio',
            
            # Reach
            'estimated_reach',
            'estimated_impressions',
            
            # Metadata
            'top_keywords',
            'metadata',
            'calculated_at',
        ]
        read_only_fields = ['id', 'calculated_at']
    
    def get_engagement_total(self, obj):
        """Total engagement across all types"""
        return obj.total_likes + obj.total_comments + obj.total_shares
    
    def get_sentiment_ratio(self, obj):
        """Positive to negative ratio"""
        if obj.negative_mentions == 0:
            return None
        return round(obj.positive_mentions / obj.negative_mentions, 2)


# ============================================================================
# ALERTS
# ============================================================================

class AlertSerializer(serializers.ModelSerializer):
    """Serializer for Alert"""
    
    entity_name = serializers.CharField(source='entity.name', read_only=True)
    acknowledged_by_username = serializers.CharField(
        source='acknowledged_by.username',
        read_only=True
    )
    resolved_by_username = serializers.CharField(
        source='resolved_by.username',
        read_only=True
    )
    
    # Related mentions count
    related_mentions_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Alert
        fields = [
            'id',
            'entity',
            'entity_name',
            'alert_type',
            'severity',
            'status',
            
            # Details
            'title',
            'message',
            'trigger_value',
            'threshold_value',
            
            # Related data
            'related_mentions_count',
            
            # Metadata
            'metadata',
            
            # Timestamps
            'triggered_at',
            'acknowledged_at',
            'resolved_at',
            
            # User tracking
            'acknowledged_by',
            'acknowledged_by_username',
            'resolved_by',
            'resolved_by_username',
        ]
        read_only_fields = [
            'id',
            'triggered_at',
            'acknowledged_at',
            'resolved_at',
            'acknowledged_by',
            'resolved_by',
        ]
    
    def get_related_mentions_count(self, obj):
        """Count of related mentions"""
        return obj.related_mentions.count()


# ============================================================================
# KPI SERIALIZERS (for API responses)
# ============================================================================

class CampaignKPISerializer(serializers.Serializer):
    """Serializer for campaign KPI response"""
    
    campaign_id = serializers.UUIDField()
    campaign_name = serializers.CharField()
    budget_spent = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    # Raw metrics
    impressions = serializers.IntegerField()
    clicks = serializers.IntegerField()
    engagements = serializers.IntegerField()
    video_views = serializers.IntegerField()
    conversions = serializers.IntegerField()
    
    # Engagement breakdown
    engagement_breakdown = serializers.DictField()
    
    # Calculated KPIs
    engagement_rate = serializers.FloatField(allow_null=True)
    cpc = serializers.FloatField(allow_null=True)
    cpm = serializers.FloatField(allow_null=True)
    cpe = serializers.FloatField(allow_null=True)
    video_watch_rate = serializers.FloatField(allow_null=True)
    conversion_rate = serializers.FloatField(allow_null=True)


class CreatorKPISerializer(serializers.Serializer):
    """Serializer for creator KPI response"""
    
    creator_id = serializers.UUIDField()
    creator_name = serializers.CharField()
    campaign_id = serializers.UUIDField(allow_null=True)
    creator_cost = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    # Raw metrics
    impressions = serializers.IntegerField()
    clicks = serializers.IntegerField()
    engagements = serializers.IntegerField()
    video_views = serializers.IntegerField()
    conversions = serializers.IntegerField()
    
    # Calculated KPIs
    engagement_rate = serializers.FloatField(allow_null=True)
    cpc = serializers.FloatField(allow_null=True)
    cpm = serializers.FloatField(allow_null=True)
    cpe = serializers.FloatField(allow_null=True)
    video_watch_rate = serializers.FloatField(allow_null=True)


class ContentKPISerializer(serializers.Serializer):
    """Serializer for content KPI response"""
    
    content_id = serializers.UUIDField()
    content_title = serializers.CharField()
    
    # Raw metrics
    impressions = serializers.IntegerField()
    clicks = serializers.IntegerField()
    engagements = serializers.IntegerField()
    video_views = serializers.IntegerField()
    
    # Engagement breakdown
    engagement_breakdown = serializers.DictField()
    
    # Calculated KPIs
    engagement_rate = serializers.FloatField(allow_null=True)
    video_watch_rate = serializers.FloatField(allow_null=True)
    hook_rate = serializers.FloatField(allow_null=True)
    avg_watch_time = serializers.FloatField()


class DailyStatsSerializer(serializers.Serializer):
    """Serializer for daily stats response"""
    
    date = serializers.DateField()
    impressions = serializers.IntegerField()
    clicks = serializers.IntegerField()
    engagements = serializers.IntegerField()
    video_views = serializers.IntegerField()
    conversions = serializers.IntegerField()
    breakdown = serializers.DictField()


class SentimentRollupSerializer(serializers.Serializer):
    """Serializer for sentiment rollup response"""
    
    total_mentions = serializers.IntegerField()
    avg_sentiment_score = serializers.FloatField()
    positive_mentions = serializers.IntegerField()
    negative_mentions = serializers.IntegerField()
    neutral_mentions = serializers.IntegerField()
    mixed_mentions = serializers.IntegerField()
    sentiment_distribution = serializers.DictField()



class TrackedEntityDetailSerializer(TrackedEntitySerializer):
    """Detailed TrackedEntity with related data"""
    
    keywords = EntityKeywordSerializer(many=True, read_only=True)
    competitors = EntityCompetitorSerializer(many=True, read_only=True)
    
    # Recent mentions
    recent_mentions = serializers.SerializerMethodField()
    
    # Sentiment stats
    sentiment_breakdown = serializers.SerializerMethodField()
    
    class Meta(TrackedEntitySerializer.Meta):
        fields = TrackedEntitySerializer.Meta.fields + [
            'keywords',
            'competitors',
            'recent_mentions',
            'sentiment_breakdown',
        ]
    
    def get_recent_mentions(self, obj):
        """Get 5 most recent mentions"""
        recent = Mention.objects.filter(
            detected_entities__entity=obj
        ).order_by('-published_at')[:5]
        
        return MentionListSerializer(recent, many=True).data
    
    def get_sentiment_breakdown(self, obj):
        """Get sentiment distribution"""
        from django.db.models import Count, Q
        
        stats = obj.sentiments.aggregate(
            positive=Count('id', filter=Q(sentiment='positive')),
            negative=Count('id', filter=Q(sentiment='negative')),
            neutral=Count('id', filter=Q(sentiment='neutral')),
            mixed=Count('id', filter=Q(sentiment='mixed')),
        )
        
        return {
            'positive': stats['positive'] or 0,
            'negative': stats['negative'] or 0,
            'neutral': stats['neutral'] or 0,
            'mixed': stats['mixed'] or 0,
        }


class MentionDetailSerializer(MentionSerializer):
    """Detailed Mention with detected entities and sentiment"""
    
    detected_entities = MentionEntitySerializer(many=True, read_only=True)
    sentiments = MentionSentimentSerializer(many=True, read_only=True)
    topics = MentionTopicSerializer(many=True, read_only=True)
    
    class Meta(MentionSerializer.Meta):
        fields = MentionSerializer.Meta.fields + [
            'detected_entities',
            'sentiments',
            'topics',
        ]