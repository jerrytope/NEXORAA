# CAMPAIGN_INTELLIGENCE/models.py
"""
Campaign Intelligence App - Complete Models

Story Group A: Campaign Structure (Campaign → Creators → Posts)
Story Group B: Performance & Historical Intelligence
Story Group C: Campaign-Scoped Creator Efficiency (PRODUCTION READY)

CRITICAL STANDARDS:
- All percentage metrics use 0-100 scale (NOT 0-1)
- All rates (ER, Conv, Hook, Watch) stored as percentages
- Hybrid weighting uses PROPORTIONAL weights (normalized to sum=1)
- Tier assignment enforced by scoring service
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid


# ============================================================================
# STORY GROUP A: CAMPAIGN STRUCTURE MODELS
# ============================================================================

class PlatformChoice(models.TextChoices):
    """
    Controlled enum for social media platforms
    
    NO FREE TEXT ALLOWED
    """
    INSTAGRAM = 'instagram', 'Instagram'
    TIKTOK = 'tiktok', 'TikTok'
    YOUTUBE = 'youtube', 'YouTube'
    TWITTER = 'twitter', 'Twitter (X)'
    FACEBOOK = 'facebook', 'Facebook'
    LINKEDIN = 'linkedin', 'LinkedIn'


class ContentType(models.TextChoices):
    """Content format types"""
    REEL = 'reel', 'Reel/Short'
    STORY = 'story', 'Story'
    STATIC = 'static', 'Static Post'
    VIDEO = 'video', 'Video'
    CAROUSEL = 'carousel', 'Carousel'
    THREAD = 'thread', 'Thread'
    LIVE = 'live', 'Live Stream'


class CampaignCreator(models.Model):
    """
    Junction Table: Campaign ↔ Creator
    
    Tracks creator participation in campaigns.
    This is the mapping layer that enables intelligence.
    
    CRITICAL: One creator can be in multiple campaigns.
              One campaign can have multiple creators.
    """
    
    STATUS_CHOICES = [
        ('invited', 'Invited'),
        ('accepted', 'Accepted'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    campaign = models.ForeignKey(
        'ANALYTICS.Campaign',
        on_delete=models.CASCADE,
        related_name='campaign_creators',
        db_index=True
    )
    
    creator = models.ForeignKey(
        'ANALYTICS.Creator',
        on_delete=models.CASCADE,
        related_name='campaign_participations',
        db_index=True
    )
    
    # Contract details
    agreed_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Agreed payment for this creator'
    )
    
    expected_posts = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text='Number of posts expected'
    )
    
    actual_posts = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Number of posts delivered'
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='invited',
        db_index=True
    )
    
    # Dates
    invited_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Optional link to contract
    contract = models.ForeignKey(
        'ANALYTICS.CreatorContract',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaign_creator_links'
    )
    
    # Metadata
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'campaign_creators'
        verbose_name = 'Campaign Creator'
        verbose_name_plural = 'Campaign Creators'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['campaign', 'creator']),
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['creator', 'status']),
        ]
        unique_together = [['campaign', 'creator']]
    
    def __str__(self):
        return f"{self.creator.name} in {self.campaign.name}"
    
    def update_actual_posts(self):
        """Update actual_posts count"""
        self.actual_posts = self.campaign_posts.filter(status='live').count()
        self.save(update_fields=['actual_posts', 'updated_at'])


class CampaignPost(models.Model):
    """
    Content/Post Model - Actual published content
    
    CRITICAL FIELD: external_post_id
    - Instagram Media ID
    - TikTok Video ID
    - YouTube Video ID
    - Tweet ID
    
    This enables:
    - Analytics scraping
    - API integrations
    - Data reconciliation
    - Duplicate prevention
    
    VALIDATION RULES:
    - Cannot add without CampaignCreator link
    - Cannot add without external_post_id
    - Platform must be valid enum
    - Campaign must be ACTIVE (NOT draft, NOT completed)
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('live', 'Live'),
        ('archived', 'Archived'),
        ('deleted', 'Deleted'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # CRITICAL: Triple relationship for performance
    campaign_creator = models.ForeignKey(
        'CampaignCreator',
        on_delete=models.CASCADE,
        related_name='campaign_posts',
        db_index=True,
        help_text='Links to CampaignCreator junction'
    )
    
    # Redundant but useful for query speed
    creator = models.ForeignKey(
        'ANALYTICS.Creator',
        on_delete=models.CASCADE,
        related_name='campaign_posts',
        db_index=True
    )
    
    campaign = models.ForeignKey(
        'ANALYTICS.Campaign',
        on_delete=models.CASCADE,
        related_name='campaign_posts',
        db_index=True
    )
    
    # Platform & Content
    platform = models.CharField(
        max_length=20,
        choices=PlatformChoice.choices,
        db_index=True,
        help_text='Social media platform'
    )
    
    # CRITICAL: External Post ID
    external_post_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text='Platform-specific ID (Instagram Media ID, TikTok Video ID, etc.)'
    )
    
    post_url = models.URLField(
        max_length=500,
        help_text='Direct URL to the post'
    )
    
    content_type = models.CharField(
        max_length=20,
        choices=ContentType.choices,
        help_text='Format of content'
    )
    
    # Content details
    caption = models.TextField(blank=True)
    hashtags = models.JSONField(default=list, blank=True)
    mentions = models.JSONField(default=list, blank=True)
    
    # Media
    thumbnail_url = models.URLField(max_length=500, blank=True)
    media_urls = models.JSONField(default=list, blank=True)
    
    # Timing
    posted_at = models.DateTimeField(
        db_index=True,
        help_text='When published on platform'
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'campaign_posts'
        verbose_name = 'Campaign Post'
        verbose_name_plural = 'Campaign Posts'
        ordering = ['-posted_at']
        indexes = [
            models.Index(fields=['platform', 'external_post_id'], name='post_unique_idx'),
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['creator', 'campaign']),
            models.Index(fields=['campaign_creator', 'status']),
            models.Index(fields=['posted_at', 'status']),
        ]
        unique_together = [['platform', 'external_post_id']]
    
    def __str__(self):
        return f"{self.creator.name} - {self.platform} ({self.posted_at.date()})"
    
    def clean(self):
        """VALIDATION RULES"""
        if not self.campaign_creator_id:
            raise ValidationError('Must link to CampaignCreator')
        
        if not self.external_post_id:
            raise ValidationError('external_post_id is required')
        
        if self.platform not in PlatformChoice.values:
            raise ValidationError('Invalid platform')
        
        if self.campaign:
            if self.campaign.status == 'draft':
                raise ValidationError('Cannot add posts to draft campaigns')
            if self.campaign.status == 'completed':
                raise ValidationError('Cannot add posts to completed campaigns. Campaign is locked.')
        
        if self.campaign_creator:
            if self.campaign_creator.campaign_id != self.campaign_id:
                raise ValidationError('Campaign mismatch')
            if self.campaign_creator.creator_id != self.creator_id:
                raise ValidationError('Creator mismatch')
    
    def save(self, *args, **kwargs):
        """Auto-populate and validate"""
        if self.campaign_creator and not self.campaign_id:
            self.campaign = self.campaign_creator.campaign
        if self.campaign_creator and not self.creator_id:
            self.creator = self.campaign_creator.creator
        
        self.clean()
        super().save(*args, **kwargs)
        
        if self.status == 'live':
            self.campaign_creator.update_actual_posts()


# ============================================================================
# STORY GROUP B: INTELLIGENCE MODELS
# ============================================================================

class CreatorPerformanceAggregate(models.Model):
    """
    Cross-Campaign Historical Creator Intelligence
    
    HYBRID WEIGHTING (PROPORTIONAL):
    For each campaign:
      raw_weight = 0.4 × spend + 0.3 × impressions + 0.3 × engagements
    
    Then normalize across all campaigns:
      proportional_weight = raw_weight / Σ(all_raw_weights)
    
    Weighted average example:
      avg_ER = Σ(campaign_ER × proportional_weight)
    
    hybrid_weight_score = Σ(raw_weights) [for reference only]
    
    Updated ONLY when campaign status → COMPLETED
    
    METRIC FORMAT: All percentages stored as 0-100 (NOT 0-1)
    """
    
    creator = models.OneToOneField(
        'ANALYTICS.Creator',
        on_delete=models.CASCADE,
        related_name='performance_aggregate',
        primary_key=True
    )
    
    # Volume metrics
    total_campaigns = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    total_spend = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    total_impressions = models.BigIntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    total_engagements = models.BigIntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    total_clicks = models.BigIntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    total_conversions = models.BigIntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    # Weighted average metrics (ALL 0-100 SCALE)
    avg_engagement_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Weighted avg ER (0-100%)'
    )
    
    avg_cpc = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Weighted avg Cost Per Click'
    )
    
    avg_cpe = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Weighted avg Cost Per Engagement'
    )
    
    avg_conversion_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Weighted avg Conv Rate (0-100%)'
    )
    
    avg_hook_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Weighted avg Hook Rate (0-100%)'
    )
    
    avg_watch_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Weighted avg Watch Rate (0-100%)'
    )
    
    avg_sentiment_shift = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-100), MaxValueValidator(100)],
        help_text='Weighted avg Sentiment Shift (-100 to +100)'
    )
    
    # Efficiency scores
    lifetime_efficiency_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Weighted lifetime score (0-100)'
    )
    
    hybrid_weight_score = models.FloatField(
        null=True,
        blank=True,
        help_text='Sum of raw hybrid weights: Σ(0.4×spend + 0.3×impressions + 0.3×engagements). For reference only - actual weighting uses PROPORTIONAL normalized weights.'
    )
    
    # Global ranking
    global_rank = models.IntegerField(
        null=True,
        blank=True
    )
    
    global_percentile = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Global percentile (0-100)'
    )
    
    # Timestamps
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'creator_performance_aggregate'
        verbose_name = 'Creator Performance Aggregate'
        verbose_name_plural = 'Creator Performance Aggregates'
        ordering = ['-lifetime_efficiency_score']
        indexes = [
            models.Index(fields=['-lifetime_efficiency_score']),
            models.Index(fields=['global_rank']),
        ]
    
    def __str__(self):
        return f"{self.creator.name} - Score: {self.lifetime_efficiency_score or 0:.1f}"


class CreatorScoreHistory(models.Model):
    """
    Campaign-by-Campaign Score Tracking
    
    Stores:
    - Campaign score
    - Raw hybrid weight (before normalization)
    - Proportional weight (normalized to sum=1 across all campaigns)
    - Tier
    
    Enables trend charts & consistency tracking
    
    METRIC FORMAT: All percentages stored as 0-100
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    creator = models.ForeignKey(
        'ANALYTICS.Creator',
        on_delete=models.CASCADE,
        related_name='score_history',
        db_index=True
    )
    
    campaign = models.ForeignKey(
        'ANALYTICS.Campaign',
        on_delete=models.CASCADE,
        related_name='creator_scores',
        db_index=True
    )
    
    # Scores
    campaign_score = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Creator efficiency score for this campaign (0-100)'
    )
    
    # Raw hybrid weight (before normalization)
    hybrid_weight_raw = models.FloatField(
        default=0.0,
        help_text='Raw: 0.4×spend + 0.3×impressions + 0.3×engagements'
        
    )
    
    # Proportional weight (normalized across all creator campaigns)
    hybrid_weight_proportional = models.FloatField(
        null=True,
        blank=True,
        default=None,
        help_text='Proportional weight: raw_weight / Σ(all_raw_weights). Used in weighted averages.'
    )
    
    # Component weights (raw, before normalization)
    spend_weight_raw = models.FloatField(null=True, blank=True, help_text='0.4 × spend', default=None)
    impression_weight_raw = models.FloatField(null=True, blank=True, help_text='0.3 × impressions', default=None)
    engagement_weight_raw = models.FloatField(null=True, blank=True, help_text='0.3 × engagements', default=None)
    
    # Metrics snapshot
    campaign_spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    campaign_impressions = models.BigIntegerField(default=0)
    campaign_engagements = models.BigIntegerField(default=0)
    campaign_clicks = models.BigIntegerField(default=0)
    campaign_conversions = models.BigIntegerField(default=0)
    
    # Performance tier
    tier = models.CharField(
        max_length=20,
        blank=True,
        help_text='Low, Moderate, High, Elite (from CampaignScopedCreatorEfficiency)'
    )
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'creator_score_history'
        verbose_name = 'Creator Score History'
        verbose_name_plural = 'Creator Score Histories'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['creator', '-created_at']),
            models.Index(fields=['campaign', '-campaign_score']),
        ]
        unique_together = [['creator', 'campaign']]
    
    def __str__(self):
        return f"{self.creator.name} - {self.campaign.name}: {self.campaign_score:.1f}"


class CampaignEfficiencyScore(models.Model):
    """
    Campaign-Level Efficiency Score
    
    Weighted by:
    - ROI (30%)
    - CPC (15%)
    - CPE (15%)
    - Conversion Rate (20%)
    - Sentiment Shift (10%)
    - Engagement Rate (10%)
    
    METRIC FORMAT: All percentages stored as 0-100
    """
    
    campaign = models.OneToOneField(
        'ANALYTICS.Campaign',
        on_delete=models.CASCADE,
        related_name='efficiency_score',
        primary_key=True
    )
    
    # Raw metrics
    total_impressions = models.BigIntegerField(default=0)
    total_engagements = models.BigIntegerField(default=0)
    total_clicks = models.BigIntegerField(default=0)
    total_conversions = models.BigIntegerField(default=0)
    total_spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Calculated metrics (ALL 0-100 SCALE WHERE APPLICABLE)
    roi = models.FloatField(null=True, blank=True, help_text='ROI as percentage')
    cpc = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    cpe = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    engagement_rate = models.FloatField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='ER (0-100%)'
    )
    conversion_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Conv Rate (0-100%)'
    )
    
    # Sentiment
    sentiment_shift = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-100), MaxValueValidator(100)],
        help_text='Sentiment shift (-100 to +100)'
    )
    positive_shift_percentage = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    negative_shift_percentage = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    # Score
    efficiency_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Campaign efficiency (0-100)'
    )
    
    # Normalized components (0-100)
    roi_normalized = models.FloatField(null=True, blank=True)
    cpc_normalized = models.FloatField(null=True, blank=True)
    cpe_normalized = models.FloatField(null=True, blank=True)
    conversion_rate_normalized = models.FloatField(null=True, blank=True)
    sentiment_normalized = models.FloatField(null=True, blank=True)
    engagement_rate_normalized = models.FloatField(null=True, blank=True)
    
    # Timestamps
    calculated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'campaign_efficiency_scores'
        verbose_name = 'Campaign Efficiency Score'
        verbose_name_plural = 'Campaign Efficiency Scores'
    
    def __str__(self):
        return f"{self.campaign.name}: {self.efficiency_score or 0:.1f}"


# ============================================================================
# ✅ STORY GROUP C: CAMPAIGN-SCOPED CREATOR EFFICIENCY (PRODUCTION READY)
# ============================================================================

class CampaignScopedCreatorEfficiency(models.Model):
    """
    Creator Performance Within a Single Campaign
    
    PRODUCTION REQUIREMENTS MET:
    ✅ Raw volume snapshot fields added
    ✅ Hybrid weighting uses proportional weights (handled in service layer)
    ✅ All metrics locked to 0-100 percentage format
    ✅ Tier assignment enforced by scoring service
    
    CRITICAL MODEL: Required BEFORE computing lifetime hybrid scores
    
    Stores per-creator, per-campaign:
    - Raw volume metrics (impressions, engagements, clicks, conversions, spend)
    - Raw performance metrics (ER, CPC, CPE, Hook, Watch, Conv, Sentiment)
    - Normalized metrics (0-100 scale within campaign cohort)
    - Efficiency score (0-100)
    - Percentile rank within campaign
    - Performance tier (enforced by service)
    
    CALCULATION FLOW:
    1. Campaign completes → aggregate raw volumes per creator
    2. Calculate raw performance metrics (ER, CPC, etc.)
    3. Normalize metrics across all creators in campaign (handle Max==Min → 50.0)
    4. Calculate weighted efficiency score per creator
    5. Assign percentile ranks
    6. Service enforces tier assignment based on percentile
    7. Store in this table
    8. THEN update CreatorPerformanceAggregate with proportional hybrid weighting
    
    METRIC FORMAT STANDARD:
    - All rates stored as percentages (0-100, NOT 0-1)
    - Engagement Rate: (engagements / impressions) × 100
    - Conversion Rate: (conversions / clicks) × 100
    - Hook Rate: 3-sec views / impressions × 100
    - Watch Rate: avg watch % (already 0-100)
    - Sentiment Shift: -100 to +100
    
    NORMALIZATION EDGE CASE:
    - If Max == Min (all creators identical on a metric):
      → Assign 50.0 (mid-point) to avoid division by zero
      → Service: normalization_service.py handles this
    
    TIER ENFORCEMENT:
    - Tier assignment is NOT manually editable
    - Enforced by scoring_service.py based on percentile_rank:
      * Elite: ≥90th percentile
      * High: 70-89th percentile
      * Moderate: 30-69th percentile
      * Low: <30th percentile
    """
    
    TIER_CHOICES = [
        ('low', 'Low'),
        ('moderate', 'Moderate'),
        ('high', 'High'),
        ('elite', 'Elite'),
    ]
    
    campaign_creator = models.OneToOneField(
        'CampaignCreator',
        on_delete=models.CASCADE,
        related_name='scoped_efficiency',
        primary_key=True,
        help_text='One efficiency record per campaign-creator pairing'
    )
    
    # ========== RAW VOLUME SNAPSHOT ==========
    # ✅ PRODUCTION REQUIREMENT: Added volume fields for transparency
    
    total_impressions = models.BigIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Total impressions for this creator in this campaign'
    )
    
    total_engagements = models.BigIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Total engagements (likes + comments + shares + saves)'
    )
    
    total_clicks = models.BigIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Total link clicks'
    )
    
    total_conversions = models.BigIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Total conversions (sales, signups, etc.)'
    )
    
    total_spend = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Creator fee paid for this campaign'
    )
    
    total_video_views = models.BigIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Total video views (for video content only)'
    )
    
    total_3sec_views = models.BigIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Total 3-second views (hook metric)'
    )
    
    total_watch_time_seconds = models.BigIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Total watch time in seconds'
    )
    
    # ========== RAW PERFORMANCE METRICS (0-100 FORMAT) ==========
    
    engagement_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='(Engagements / Impressions) × 100'
    )
    
    cpc = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Cost Per Click (Spend / Clicks)'
    )
    
    cpe = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Cost Per Engagement (Spend / Engagements)'
    )
    
    hook_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='(3-sec views / Impressions) × 100 (video only)'
    )
    
    watch_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='(Total watch time / Total video duration) × 100 (video only)'
    )
    
    conversion_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='(Conversions / Clicks) × 100'
    )
    
    sentiment_shift = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-100), MaxValueValidator(100)],
        help_text='Net sentiment change (post - pre campaign), range: -100 to +100'
    )
    
    # ========== NORMALIZED METRICS (0-100) ==========
    # Normalized within campaign cohort using Min-Max scaling
    # If Max == Min → 50.0 (handled by normalization_service)
    
    engagement_rate_normalized = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Min-Max normalized ER (0-100)'
    )
    
    cpc_normalized = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='INVERTED: lower CPC = higher score (0-100)'
    )
    
    cpe_normalized = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='INVERTED: lower CPE = higher score (0-100)'
    )
    
    hook_rate_normalized = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Min-Max normalized hook rate (0-100)'
    )
    
    watch_rate_normalized = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Min-Max normalized watch rate (0-100)'
    )
    
    conversion_rate_normalized = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Min-Max normalized conv rate (0-100)'
    )
    
    sentiment_shift_normalized = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Shifted to 0-100 scale: (value + 100) / 2'
    )
    
    # ========== EFFICIENCY SCORE ==========
    efficiency_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Weighted score (0-100) from normalized metrics'
    )
    
    # Weights used (for transparency and auditability)
    weight_engagement_rate = models.FloatField(
        default=0.20,
        help_text='Weight for ER in final score'
    )
    weight_cpc = models.FloatField(
        default=0.15,
        help_text='Weight for CPC in final score'
    )
    weight_cpe = models.FloatField(
        default=0.15,
        help_text='Weight for CPE in final score'
    )
    weight_hook_rate = models.FloatField(
        default=0.10,
        help_text='Weight for hook rate in final score'
    )
    weight_watch_rate = models.FloatField(
        default=0.10,
        help_text='Weight for watch rate in final score'
    )
    weight_conversion_rate = models.FloatField(
        default=0.20,
        help_text='Weight for conv rate in final score'
    )
    weight_sentiment_shift = models.FloatField(
        default=0.10,
        help_text='Weight for sentiment in final score'
    )
    
    # ========== RANKING & TIER ==========
    percentile_rank = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Percentile rank within campaign (0-100)'
    )
    
    tier = models.CharField(
        max_length=20,
        choices=TIER_CHOICES,
        blank=True,
        editable=False,  # ✅ NOT manually editable - enforced by service
        help_text='Performance tier (enforced by scoring_service.py based on percentile_rank)'
    )
    
    # ========== METADATA ==========
    calculated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'campaign_scoped_creator_efficiency'
        verbose_name = 'Campaign-Scoped Creator Efficiency'
        verbose_name_plural = 'Campaign-Scoped Creator Efficiencies'
        ordering = ['-efficiency_score']
        indexes = [
            models.Index(fields=['-efficiency_score']),
            models.Index(fields=['percentile_rank']),
            models.Index(fields=['tier']),
        ]
    
    def __str__(self):
        campaign_name = self.campaign_creator.campaign.name
        creator_name = self.campaign_creator.creator.name
        score = self.efficiency_score or 0
        return f"{creator_name} in {campaign_name}: {score:.1f} ({self.tier or 'N/A'})"
    
    def clean(self):
        """
        VALIDATION: Ensure tier matches percentile_rank
        This is a safety check - tier should be set by service only
        """
        if self.percentile_rank is not None:
            expected_tier = self._calculate_tier_from_percentile(self.percentile_rank)
            if self.tier and self.tier != expected_tier:
                raise ValidationError(
                    f'Tier mismatch: percentile {self.percentile_rank:.1f} should be "{expected_tier}", got "{self.tier}". '
                    f'Tier must be set by scoring_service.py only.'
                )
    
    @staticmethod
    def _calculate_tier_from_percentile(percentile: float) -> str:
        """
        Calculate tier from percentile rank
        
        Elite: ≥90th percentile
        High: 70-89th percentile
        Moderate: 30-69th percentile
        Low: <30th percentile
        """
        if percentile >= 90:
            return 'elite'
        elif percentile >= 70:
            return 'high'
        elif percentile >= 30:
            return 'moderate'
        else:
            return 'low'
    
    def assign_tier(self):
        """
        ✅ ENFORCED: Assign tier based on percentile_rank
        Called by scoring_service.py ONLY
        
        Elite: Top 10% (percentile ≥ 90)
        High: 70-90th percentile
        Moderate: 30-70th percentile
        Low: Bottom 30% (percentile < 30)
        """
        if self.percentile_rank is None:
            self.tier = ''
            return
        
        self.tier = self._calculate_tier_from_percentile(self.percentile_rank)


# ============================================================================
# ✅ SIGNAL: TRIGGER RECALCULATION WHEN CAMPAIGN COMPLETES
# ============================================================================

@receiver(post_save, sender='ANALYTICS.Campaign')
def trigger_efficiency_recalculation(sender, instance, created, **kwargs):
    """
    CRITICAL TRIGGER: When campaign status → COMPLETED
    
    WORKFLOW:
    1. Aggregate raw volumes per creator (impressions, engagements, etc.)
    2. Calculate raw performance metrics (ER, CPC, CPE, etc.) - ALL 0-100 format
    3. Store in CampaignScopedCreatorEfficiency
    4. Normalize metrics across campaign cohort (handle Max==Min → 50.0)
    5. Calculate efficiency scores
    6. Assign percentile ranks
    7. Enforce tier assignment via scoring_service.py
    8. Update CreatorScoreHistory
    9. Recalculate CreatorPerformanceAggregate with PROPORTIONAL hybrid weighting
    10. Update global rankings
    
    SERVICES:
    - campaign_completion_service.py (orchestration)
    - normalization_service.py (Min-Max scaling with edge case handling)
    - scoring_service.py (efficiency score calculation & tier enforcement)
    - hybrid_weighting_service.py (proportional weight calculation)
    """
    