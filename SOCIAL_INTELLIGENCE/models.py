"""
Social Intelligence Models for Nexora Platform
Tracks brand mentions, sentiment, competitors, and social media intelligence.

CRITICAL RULES:
1. Reuses existing Nexora identity tables (platforms, creators, campaigns, brands)
2. Unifies campaign content and organic mentions via (platform_id + external_post_id)
3. Metrics stored as immutable snapshots in analytics_events
4. No duplication of identity data
"""

from django.db import models
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone

from ANALYTICS.models import EventType
class TrackedEntity(models.Model):
    """
    Central entity being tracked (brand, person, product, topic, etc.)
    Represents what we're monitoring across social platforms.
    """
    ENTITY_TYPES = [
        ('brand', 'Brand'),
        ('person', 'Person'),
        ('product', 'Product'),
        ('topic', 'Topic'),
        ('campaign', 'Campaign'),
        ('competitor', 'Competitor'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('archived', 'Archived'),
    ]
    
    # Core fields
    name = models.CharField(max_length=255, db_index=True)
    entity_type = models.CharField(max_length=50, choices=ENTITY_TYPES, db_index=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    
    # Optional link to existing Nexora entities (reuse rule)
    brand = models.ForeignKey(
        'ANALYTICS.Brand',  # Reuses existing Nexora brand table
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='tracked_entities',
        help_text='Link to Nexora brand if tracking a brand'
    )
    
    creator = models.ForeignKey(
        'ANALYTICS.Creator',# Reuses existing Nexora creator table
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='tracked_entities',
        help_text='Link to Nexora creator if tracking a person/influencer'
    )
    
    campaign = models.ForeignKey(
        'ANALYTICS.Campaign',  # Reuses existing Nexora campaign table
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='tracked_entities',
        help_text='Link to Nexora campaign if tracking a campaign'
    )
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Tracking control
    tracking_started_at = models.DateTimeField(default=timezone.now)
    tracking_ended_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'tracked_entities'
        verbose_name = 'Tracked Entity'
        verbose_name_plural = 'Tracked Entities'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['entity_type', 'status']),
            models.Index(fields=['created_at', 'status']),
            models.Index(fields=['brand', 'status']),
            models.Index(fields=['creator', 'status']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.entity_type})"


class EntityKeyword(models.Model):
    """
    Detection logic for tracked entities.
    Defines hashtags, phrases, handles, and match rules for finding mentions.
    """
    KEYWORD_TYPES = [
        ('hashtag', 'Hashtag'),
        ('phrase', 'Phrase'),
        ('handle', 'Handle'),
        ('exact_match', 'Exact Match'),
        ('regex', 'Regex Pattern'),
    ]
    
    MATCH_RULES = [
        ('exact', 'Exact Match'),
        ('contains', 'Contains'),
        ('starts_with', 'Starts With'),
        ('ends_with', 'Ends With'),
        ('regex', 'Regular Expression'),
        ('fuzzy', 'Fuzzy Match'),
    ]
    
    entity = models.ForeignKey(
        TrackedEntity,
        on_delete=models.CASCADE,
        related_name='keywords',
        db_index=True
    )
    
    keyword = models.CharField(
        max_length=255,
        db_index=True,
        help_text='The actual keyword/phrase/hashtag to detect'
    )
    
    keyword_type = models.CharField(
        max_length=50,
        choices=KEYWORD_TYPES,
        db_index=True
    )
    
    match_rule = models.CharField(
        max_length=50,
        choices=MATCH_RULES,
        default='contains'
    )
    
    # Match settings
    case_sensitive = models.BooleanField(default=False)
    priority = models.IntegerField(
        default=0,
        help_text='Higher priority keywords matched first'
    )
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    
    # Metadata
    notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'entity_keywords'
        verbose_name = 'Entity Keyword'
        verbose_name_plural = 'Entity Keywords'
        ordering = ['-priority', 'keyword']
        indexes = [
            models.Index(fields=['entity', 'is_active']),
            models.Index(fields=['keyword_type', 'is_active']),
            models.Index(fields=['keyword', 'keyword_type']),
        ]
        unique_together = [['entity', 'keyword', 'keyword_type']]
    
    def __str__(self):
        return f"{self.entity.name}: {self.keyword} ({self.keyword_type})"


class EntityCompetitor(models.Model):
    """
    Entity ↔ Competitor mapping.
    Tracks competitive relationships between entities.
    """
    entity = models.ForeignKey(
        TrackedEntity,
        on_delete=models.CASCADE,
        related_name='competitors',
        db_index=True
    )
    
    competitor = models.ForeignKey(
        TrackedEntity,
        on_delete=models.CASCADE,
        related_name='competing_with',
        db_index=True
    )
    
    # Relationship metadata
    relationship_type = models.CharField(
        max_length=50,
        default='direct',
        help_text='direct, indirect, substitute, etc.'
    )
    
    priority = models.IntegerField(
        default=0,
        help_text='Priority/importance of this competitor'
    )
    
    notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'entity_competitors'
        verbose_name = 'Entity Competitor'
        verbose_name_plural = 'Entity Competitors'
        ordering = ['-priority', 'competitor__name']
        indexes = [
            models.Index(fields=['entity', 'competitor']),
        ]
        unique_together = [['entity', 'competitor']]
        # Note: CheckConstraint not supported in older Django versions
        # Self-competition is prevented via clean() method
    
    def __str__(self):
        return f"{self.entity.name} vs {self.competitor.name}"
    
    def clean(self):
        """Validate that entity != competitor"""
        if self.entity_id and self.competitor_id and self.entity_id == self.competitor_id:
            raise ValidationError('An entity cannot be its own competitor.')
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)




class Mention(models.Model):
    """
    Raw social posts detected across platforms.
    
    CRITICAL UNIFICATION RULE:
    - Uses (platform_id + external_post_id) as unique identifier
    - Links to campaign content via same (platform_id, external_post_id)
    - Prevents double-counting in dashboards
    """
    
    # CRITICAL: Platform & External ID for unification
    platform = models.ForeignKey(
        'ANALYTICS.Platform',  # Reuses existing Nexora platform table
        on_delete=models.CASCADE,
        related_name='mentions',
        db_index=True
    )
    
    external_post_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text='Platform-specific post ID (e.g., tweet ID, Instagram post ID)'
    )
    
    # Optional link to campaign content (unification)
    campaign_content = models.ForeignKey(
        'ANALYTICS.Platform',  # Reuses existing Nexora content table
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='social_mentions',
        help_text='Link if this mention is actually campaign content'
    )
    
    # Post content
    text = models.TextField(blank=True)
    author_username = models.CharField(max_length=255, db_index=True)
    author_display_name = models.CharField(max_length=255, blank=True)
    author_profile_url = models.URLField(max_length=500, blank=True)
    
    # Optional link to known creator
    creator = models.ForeignKey(
        'ANALYTICS.Creator',  # Reuses existing Nexora creator table
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mentions',
        help_text='Link to Nexora creator if author is known'
    )
    
    # Post metadata
    post_url = models.URLField(max_length=500, blank=True)
    post_type = models.CharField(
        max_length=50,
        default='post',
        help_text='post, retweet, reply, story, reel, etc.'
    )
    
    language = models.CharField(max_length=10, blank=True, db_index=True)
    
    # Media
    has_image = models.BooleanField(default=False)
    has_video = models.BooleanField(default=False)
    media_urls = ArrayField(
        models.URLField(max_length=500),
        default=list,
        blank=True
    )
    
    # Engagement metrics snapshot (NOT source of truth - use analytics_events)
    # These are stored for quick reference but analytics_events is authoritative
    likes_count = models.IntegerField(default=0)
    comments_count = models.IntegerField(default=0)
    shares_count = models.IntegerField(default=0)
    views_count = models.IntegerField(default=0)
    
    # Timing
    published_at = models.DateTimeField(db_index=True)
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # Processing
    is_processed = models.BooleanField(default=False, db_index=True)
    
    # Raw data
    raw_data = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'mentions'
        verbose_name = 'Mention'
        verbose_name_plural = 'Mentions'
        ordering = ['-published_at']
        indexes = [
            # CRITICAL: Unification index
            models.Index(fields=['platform', 'external_post_id'], name='mention_unification_idx'),
            
            # Query optimization indexes
            models.Index(fields=['published_at', 'is_processed']),
            models.Index(fields=['author_username', 'platform']),
            models.Index(fields=['detected_at', 'is_processed']),
            models.Index(fields=['creator', 'published_at']),
            models.Index(fields=['language', 'published_at']),
        ]
        unique_together = [['platform', 'external_post_id']]
    
    def __str__(self):
        return f"{self.author_username} on {self.platform.name} - {self.published_at}"


class MentionEntity(models.Model):
    """
    Join table: mention ↔ entity + keyword matched.
    Tracks which entities were detected in which mentions and how.
    """
    mention = models.ForeignKey(
        Mention,
        on_delete=models.CASCADE,
        related_name='detected_entities',
        db_index=True
    )
    
    entity = models.ForeignKey(
        TrackedEntity,
        on_delete=models.CASCADE,
        related_name='mentions',
        db_index=True
    )
    
    keyword_matched = models.ForeignKey(
        EntityKeyword,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='matched_mentions',
        help_text='Which keyword triggered this detection'
    )
    
    # Match details
    match_score = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='Confidence score of the match (0.0 to 1.0)'
    )
    
    match_context = models.TextField(
        blank=True,
        help_text='Text snippet where match was found'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'mention_entities'
        verbose_name = 'Mention Entity'
        verbose_name_plural = 'Mention Entities'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['mention', 'entity']),
            models.Index(fields=['entity', 'created_at']),
            models.Index(fields=['keyword_matched', 'entity']),
        ]
        unique_together = [['mention', 'entity']]
    
    def __str__(self):
        return f"{self.entity.name} in mention {self.mention.id}"


class MentionSentiment(models.Model):
    """
    Per-entity sentiment per mention.
    Tracks sentiment analysis results for each entity detected in a mention.
    """
    SENTIMENT_CHOICES = [
        ('positive', 'Positive'),
        ('negative', 'Negative'),
        ('neutral', 'Neutral'),
        ('mixed', 'Mixed'),
    ]
    
    mention = models.ForeignKey(
        Mention,
        on_delete=models.CASCADE,
        related_name='sentiments',
        db_index=True
    )
    
    entity = models.ForeignKey(
        TrackedEntity,
        on_delete=models.CASCADE,
        related_name='sentiments',
        db_index=True
    )
    
    # Sentiment analysis
    sentiment = models.CharField(
        max_length=20,
        choices=SENTIMENT_CHOICES,
        db_index=True
    )
    
    sentiment_score = models.FloatField(
        validators=[MinValueValidator(-1.0), MaxValueValidator(1.0)],
        help_text='Sentiment score from -1.0 (negative) to 1.0 (positive)'
    )
    
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='Confidence in sentiment analysis (0.0 to 1.0)'
    )
    
    # Analysis details
    analyzer = models.CharField(
        max_length=100,
        default='default',
        help_text='Which sentiment analyzer was used'
    )
    
    # Context
    sentiment_context = models.TextField(
        blank=True,
        help_text='Specific text that influenced sentiment'
    )
    
    # Metadata
    analysis_metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    analyzed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'mention_sentiment'
        verbose_name = 'Mention Sentiment'
        verbose_name_plural = 'Mention Sentiments'
        ordering = ['-analyzed_at']
        indexes = [
            models.Index(fields=['mention', 'entity']),
            models.Index(fields=['entity', 'sentiment']),
            models.Index(fields=['entity', 'analyzed_at']),
            models.Index(fields=['sentiment', 'analyzed_at']),
        ]
        unique_together = [['mention', 'entity']]
    
    def __str__(self):
        return f"{self.entity.name}: {self.sentiment} ({self.sentiment_score:.2f})"


class MentionTopic(models.Model):
    """
    Topics/themes detected in mentions.
    Optional for MVP but included in schema for future use.
    """
    mention = models.ForeignKey(
        Mention,
        on_delete=models.CASCADE,
        related_name='topics',
        db_index=True
    )
    
    topic_name = models.CharField(max_length=255, db_index=True)
    
    topic_category = models.CharField(
        max_length=100,
        blank=True,
        help_text='Broader category this topic belongs to'
    )
    
    relevance_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='How relevant this topic is to the mention'
    )
    
    # Metadata
    topic_metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    detected_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'mention_topics'
        verbose_name = 'Mention Topic'
        verbose_name_plural = 'Mention Topics'
        ordering = ['-relevance_score']
        indexes = [
            models.Index(fields=['mention', 'topic_name']),
            models.Index(fields=['topic_name', 'detected_at']),
            models.Index(fields=['topic_category', 'detected_at']),
        ]
    
    def __str__(self):
        return f"{self.topic_name} in mention {self.mention.id}"


class ExtractedKeyword(models.Model):
    """
    Trending terms and keywords extracted from mentions.
    Optional for MVP - tracks emerging keywords and trends.
    """
    keyword = models.CharField(max_length=255, db_index=True)
    
    entity = models.ForeignKey(
        TrackedEntity,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='extracted_keywords',
        help_text='Entity this keyword is associated with (if any)'
    )
    
    platform = models.ForeignKey(
        'ANALYTICS.Platform',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='extracted_keywords'
    )
    
    # Statistics
    mention_count = models.IntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen = models.DateTimeField(auto_now=True, db_index=True)
    
    # Trending metrics
    trending_score = models.FloatField(
        default=0.0,
        help_text='Calculated trending score'
    )
    
    growth_rate = models.FloatField(
        default=0.0,
        help_text='Rate of growth in mentions'
    )
    
    # Metadata
    keyword_type = models.CharField(max_length=50, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'extracted_keywords'
        verbose_name = 'Extracted Keyword'
        verbose_name_plural = 'Extracted Keywords'
        ordering = ['-trending_score', '-mention_count']
        indexes = [
            models.Index(fields=['keyword', 'entity']),
            models.Index(fields=['entity', 'trending_score']),
            models.Index(fields=['platform', 'trending_score']),
            models.Index(fields=['first_seen', 'trending_score']),
            models.Index(fields=['last_seen', 'mention_count']),
        ]
    
    def __str__(self):
        return f"{self.keyword} ({self.mention_count} mentions)"



class EntityDailyStat(models.Model):
    """
    Derived daily statistics per entity.
    Aggregated data for faster dashboard queries.
    """
    entity = models.ForeignKey(
        TrackedEntity,
        on_delete=models.CASCADE,
        related_name='daily_stats',
        db_index=True
    )
    
    date = models.DateField(db_index=True)
    
    platform = models.ForeignKey(
        'ANALYTICS.Platform',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='entity_daily_stats',
        help_text='Optional: stats per platform'
    )
    
    # Volume metrics
    total_mentions = models.IntegerField(default=0)
    unique_authors = models.IntegerField(default=0)
    
    # Engagement totals (snapshot, not source of truth)
    total_likes = models.BigIntegerField(default=0)
    total_comments = models.BigIntegerField(default=0)
    total_shares = models.BigIntegerField(default=0)
    total_views = models.BigIntegerField(default=0)
    
    # Sentiment aggregates
    positive_mentions = models.IntegerField(default=0)
    negative_mentions = models.IntegerField(default=0)
    neutral_mentions = models.IntegerField(default=0)
    
    avg_sentiment_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-1.0), MaxValueValidator(1.0)]
    )
    
    # Reach estimates
    estimated_reach = models.BigIntegerField(default=0)
    estimated_impressions = models.BigIntegerField(default=0)
    
    # Metadata
    top_keywords = ArrayField(
        models.CharField(max_length=255),
        default=list,
        blank=True,
        help_text='Top trending keywords for this day'
    )
    
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'entity_daily_stats'
        verbose_name = 'Entity Daily Stat'
        verbose_name_plural = 'Entity Daily Stats'
        ordering = ['-date', 'entity']
        indexes = [
            models.Index(fields=['entity', 'date']),
            models.Index(fields=['date', 'entity']),
            models.Index(fields=['entity', 'platform', 'date']),
        ]
        unique_together = [['entity', 'date', 'platform']]
    
    def __str__(self):
        return f"{self.entity.name} - {self.date}"


class Alert(models.Model):
    """
    Rule-based alerts for mention spikes, sentiment changes, etc.
    """
    ALERT_TYPES = [
        ('mention_spike', 'Mention Spike'),
        ('negative_spike', 'Negative Sentiment Spike'),
        ('positive_spike', 'Positive Sentiment Spike'),
        ('competitor_activity', 'Competitor Activity'),
        ('keyword_trend', 'Trending Keyword'),
        ('influencer_mention', 'Influencer Mention'),
        ('custom', 'Custom Alert'),
    ]
    
    SEVERITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    STATUS_CHOICES = [
        ('new', 'New'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]
    
    entity = models.ForeignKey(
        TrackedEntity,
        on_delete=models.CASCADE,
        related_name='alerts',
        db_index=True
    )
    
    alert_type = models.CharField(
        max_length=50,
        choices=ALERT_TYPES,
        db_index=True
    )
    
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_LEVELS,
        default='medium',
        db_index=True
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='new',
        db_index=True
    )
    
    # Alert details
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Trigger data
    trigger_value = models.FloatField(
        null=True,
        blank=True,
        help_text='The value that triggered the alert'
    )
    
    threshold_value = models.FloatField(
        null=True,
        blank=True,
        help_text='The threshold that was exceeded'
    )
    
    # References
    related_mentions = models.ManyToManyField(
        Mention,
        blank=True,
        related_name='alerts'
    )
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    triggered_at = models.DateTimeField(auto_now_add=True, db_index=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # User tracking
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_alerts'
    )
    
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_alerts'
    )
    
    class Meta:
        db_table = 'alerts'
        verbose_name = 'Alert'
        verbose_name_plural = 'Alerts'
        ordering = ['-triggered_at']
        indexes = [
            models.Index(fields=['entity', 'status']),
            models.Index(fields=['alert_type', 'status']),
            models.Index(fields=['severity', 'status']),
            models.Index(fields=['triggered_at', 'status']),
        ]
    
    def __str__(self):
        return f"{self.alert_type}: {self.title} ({self.severity})"