import uuid
import hashlib
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils.text import slugify


class EventType(models.TextChoices):
    """
    Static event type choices for MVP.
    Dynamic event type configuration will be added post-MVP validation.
    """
    
    PAGE_VIEW = 'page_view', 'Page View'
    IMPRESSION = 'impression', 'Impression'

    CLICK = 'click', 'Click'
    LIKE = 'like', 'Like'
    SHARE = 'share', 'Share'
    COMMENT = 'comment', 'Comment'
    

    SIGNUP = 'signup', 'Sign Up'
    LOGIN = 'login', 'Login'
    
    
    PURCHASE = 'purchase', 'Purchase'
    ADD_TO_CART = 'add_to_cart', 'Add to Cart'
    REFUND = 'refund', 'Refund'
    
    
    DOWNLOAD = 'download', 'Download'
    SEARCH = 'search', 'Search'
    CUSTOM = 'custom', 'Custom'


class Platform(models.Model):
    """
    Social media or content platforms (e.g., Instagram, YouTube, TikTok)
    Foundation entity for content distribution tracking.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'platforms'
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug'], name='idx_platform_slug'),
            models.Index(fields=['is_active'], name='idx_platform_active'),
        ]
    
    def save(self, *args, **kwargs):
        """Auto-generate slug from name if not provided"""
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            
            while Platform.objects.filter(slug=slug).exclude(id=self.id).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            self.slug = slug
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name


class Brand(models.Model):
    """
    Brand/Company entity for campaign ownership.
    Foundation entity for business tracking.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='brands',
        null=True,
        blank=True,
        help_text="User who owns this brand"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'brands'
        ordering = ['name']
        unique_together = [['owner', 'name']]
        indexes = [
            models.Index(fields=['owner', 'name'], name='idx_brand_owner_name'),
        ]
    
    def __str__(self):
        return self.name


class Creator(models.Model):
    """
    Content creator/influencer entity.
    Foundation entity for creator tracking and partnerships.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)  
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'creators'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name'], name='idx_creator_name'),
        ]
    
    def __str__(self):
        return self.name


class Campaign(models.Model):
    """
    Marketing campaign entity.
    Foundation entity owned by brands, tracks marketing initiatives.
    
    UPDATED: Added budget and spend tracking fields
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name='campaigns'
    )
    
    # Campaign timing
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    
    # ✅ NEW: Budget & Spend Tracking (A. Spend/Cost)
    budget_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total allocated budget for this campaign"
    )
    
    budget_spent = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total amount spent to date (calculated from expenses)"
    )
    
    budget_currency = models.CharField(
        max_length=3,
        default='USD',
        help_text="ISO 4217 currency code (USD, EUR, GBP, etc.)"
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'campaigns'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['brand', '-created_at'], name='idx_campaign_brand_created'),
            models.Index(fields=['is_active'], name='idx_campaign_active'),
            models.Index(fields=['start_date', 'end_date'], name='idx_campaign_dates'),
        ]
    
    @property
    def budget_remaining(self):
        """Calculate remaining budget"""
        if self.budget_total is None:
            return None
        return self.budget_total - self.budget_spent
    
    @property
    def budget_utilization_pct(self):
        """Calculate budget utilization percentage"""
        if not self.budget_total or self.budget_total == 0:
            return 0
        return (self.budget_spent / self.budget_total) * 100
    
    def __str__(self):
        return f"{self.brand.name} - {self.name}"



class CreatorContract(models.Model):
    """
    Contract/agreement between brand and creator for a campaign.
    Tracks deliverables, payment terms, and fulfillment.
    
    NEW MODEL for spend tracking
    """
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid in Full'),
        ('disputed', 'Disputed'),
        ('cancelled', 'Cancelled'),
    ]
    
    DELIVERABLE_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted for Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='creator_contracts'
    )
    
    creator = models.ForeignKey(
        Creator,
        on_delete=models.CASCADE,
        related_name='contracts'
    )
    
    # Contract amount
    contracted_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total amount agreed to pay creator"
    )
    
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Amount paid to date"
    )
    
    currency = models.CharField(max_length=3, default='USD')
    
    # Payment tracking
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    
    payment_due_date = models.DateField(null=True, blank=True)
    payment_completed_date = models.DateField(null=True, blank=True)
    
    # Deliverables (what creator needs to produce)
    deliverable_status = models.CharField(
        max_length=20,
        choices=DELIVERABLE_STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    
    deliverables = models.JSONField(
        default=dict,
        blank=True,
        help_text="Expected deliverables: {'instagram_posts': 3, 'stories': 5, 'reels': 1}"
    )
    
    deliverables_completed = models.JSONField(
        default=dict,
        blank=True,
        help_text="Completed deliverables count"
    )
    
    # Contract terms
    contract_start_date = models.DateField(null=True, blank=True)
    contract_end_date = models.DateField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'creator_contracts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['campaign', 'creator'], name='idx_contract_campaign_creator'),
            models.Index(fields=['payment_status'], name='idx_contract_payment_status'),
            models.Index(fields=['deliverable_status'], name='idx_contract_deliv_status'),
        ]
        unique_together = [['campaign', 'creator']]
    
    @property
    def amount_remaining(self):
        """Calculate remaining payment amount"""
        return self.contracted_amount - self.amount_paid
    
    @property
    def payment_progress_pct(self):
        """Calculate payment progress percentage"""
        if self.contracted_amount == 0:
            return 0
        return (self.amount_paid / self.contracted_amount) * 100
    
    def __str__(self):
        return f"{self.creator.name} - {self.campaign.name} (${self.contracted_amount})"


class CampaignExpense(models.Model):
    """
    Track all campaign expenses (creator fees, ad spend, production costs, etc.)
    
    NEW MODEL for comprehensive spend tracking
    """
    
    EXPENSE_TYPE_CHOICES = [
        ('creator_fee', 'Creator Fee'),
        ('ad_spend', 'Paid Advertising'),
        ('production', 'Content Production'),
        ('influencer_gifting', 'Product Gifting'),
        ('platform_fees', 'Platform Fees'),
        ('agency_fees', 'Agency Fees'),
        ('software', 'Software/Tools'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='expenses'
    )
    
    expense_type = models.CharField(
        max_length=50,
        choices=EXPENSE_TYPE_CHOICES,
        db_index=True
    )
    
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    currency = models.CharField(max_length=3, default='USD')
    
    # Optional links
    creator = models.ForeignKey(
        Creator,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='expenses',
        help_text="If expense is for a specific creator"
    )
    
    contract = models.ForeignKey(
        CreatorContract,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='expenses',
        help_text="Link to creator contract if applicable"
    )
    
    # Expense details
    description = models.TextField(blank=True)
    expense_date = models.DateField(db_index=True)
    
    # Receipt/proof
    receipt_url = models.URLField(max_length=2048, blank=True, null=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    
    # Approval tracking
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_expenses'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'campaign_expenses'
        ordering = ['-expense_date']
        indexes = [
            models.Index(fields=['campaign', '-expense_date'], name='idx_expense_campaign_date'),
            models.Index(fields=['expense_type', '-expense_date'], name='idx_expense_type_date'),
            models.Index(fields=['creator', '-expense_date'], name='idx_expense_creator_date'),
            models.Index(fields=['is_approved'], name='idx_expense_approved'),
        ]
    
    def __str__(self):
        return f"{self.get_expense_type_display()} - ${self.amount} ({self.campaign.name})"


# ============================================================================
# CONTENT & TRACKING
# ============================================================================

class Content(models.Model):
    """
    Content piece entity (posts, videos, articles, etc.).
    Foundation entity linking platforms, creators, and campaigns.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500, default='Untitled Content')
    platform = models.ForeignKey(
        Platform,
        on_delete=models.CASCADE,
        related_name='content_items'
    )
    creator = models.ForeignKey(
        Creator,
        on_delete=models.CASCADE,
        related_name='content_items'
    )
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='content_items'
    )
    external_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Platform-specific content ID"
    )
    url = models.URLField(max_length=2048, blank=True, null=True)  
    published_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'content'
        ordering = ['-published_at', '-created_at']
        unique_together = [['platform', 'external_id']]
        indexes = [
            models.Index(fields=['platform', 'external_id'], name='idx_content_platform_extid'),
            models.Index(fields=['campaign', '-published_at'], name='idx_content_campaign_pub'),
            models.Index(fields=['creator', '-published_at'], name='idx_content_creator_pub'),
        ]
    
    def __str__(self):
        return self.title


# ============================================================================
# ✅ NEW: CONTENT PERFORMANCE SNAPSHOTS (C. Post Performance Snapshots)
# ============================================================================

class ContentSnapshot(models.Model):
    """
    Time-series snapshots of content performance metrics.
    Captures how post metrics evolve over time (not just final numbers).
    
    NEW MODEL for post performance tracking over time
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    content = models.ForeignKey(
        Content,
        on_delete=models.CASCADE,
        related_name='snapshots'
    )
    
    # Snapshot timestamp
    captured_at = models.DateTimeField(
        db_index=True,
        help_text="When these metrics were captured"
    )
    
    # Core engagement metrics
    likes_count = models.IntegerField(default=0)
    comments_count = models.IntegerField(default=0)
    shares_count = models.IntegerField(default=0)
    saves_count = models.IntegerField(default=0)
    views_count = models.BigIntegerField(default=0)
    
    # Reach & impressions
    reach = models.BigIntegerField(
        default=0,
        help_text="Unique users who saw the content"
    )
    impressions = models.BigIntegerField(
        default=0,
        help_text="Total times content was displayed"
    )
    
    # Engagement rate (calculated)
    engagement_rate = models.FloatField(
        null=True,
        blank=True,
        help_text="Engagement rate at time of capture"
    )
    
    # Platform-specific metrics (flexible JSON)
    platform_metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text="""Platform-specific metrics:
        Instagram: {"profile_visits": 200, "website_clicks": 50}
        YouTube: {"watch_time_hours": 1200, "avg_view_duration": 180}
        TikTok: {"completion_rate": 0.65, "average_watch_time": 12}
        """
    )
    
    # Growth since last snapshot
    likes_delta = models.IntegerField(
        default=0,
        help_text="Change in likes since last snapshot"
    )
    comments_delta = models.IntegerField(default=0)
    shares_delta = models.IntegerField(default=0)
    views_delta = models.BigIntegerField(default=0)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'content_snapshots'
        ordering = ['-captured_at']
        indexes = [
            models.Index(fields=['content', '-captured_at'], name='idx_snapshot_content_time'),
            models.Index(fields=['captured_at'], name='idx_snapshot_captured_at'),
        ]
        unique_together = [['content', 'captured_at']]
    
    def __str__(self):
        return f"{self.content.title} - {self.captured_at}"


# ============================================================================
# TRACKING LINKS
# ============================================================================

class TrackingLink(models.Model):
    """
    Tracking link entity for attribution and analytics.
    Foundation entity for link-level performance tracking.
    
    UPDATED: Added UTM parameter storage for better attribution
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    short_code = models.CharField(
        max_length=50,
        null=True,
        unique=True,
        blank=True,  
        help_text="Unique short code for the tracking link"
    )
    destination_url = models.URLField(
        max_length=2048,
        help_text="The URL where the tracking link redirects"
    )
    
    # ✅ NEW: UTM Parameters for attribution (B. Click Attribution)
    utm_source = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Traffic source (e.g., instagram, youtube)"
    )
    utm_medium = models.CharField(
        max_length=255,
        blank=True,
        help_text="Marketing medium (e.g., social, influencer)"
    )
    utm_campaign = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Campaign identifier"
    )
    utm_content = models.CharField(
        max_length=255,
        blank=True,
        help_text="Content variant (e.g., story, post, bio_link)"
    )
    utm_term = models.CharField(
        max_length=255,
        blank=True,
        help_text="Paid search keywords"
    )
    
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='tracking_links'
    )
    creator = models.ForeignKey(
        Creator,
        on_delete=models.CASCADE,
        related_name='tracking_links',
        null=True,
        blank=True
    )
    content = models.ForeignKey(
        Content,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tracking_links'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tracking_links'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['short_code'], name='idx_link_short_code'),
            models.Index(fields=['campaign', '-created_at'], name='idx_link_campaign_created'),
            models.Index(fields=['utm_source', 'utm_campaign'], name='idx_link_utm'),
        ]
    
    def save(self, *args, **kwargs):
        """Auto-generate short_code if not provided"""
        if not self.short_code:
            self.short_code = self._generate_unique_short_code()
        super().save(*args, **kwargs)
    
    def _generate_unique_short_code(self):
        """Generate a unique 8-character short code"""
        while True:
            code = uuid.uuid4().hex[:8]
            if not TrackingLink.objects.filter(short_code=code).exists():
                return code
    
    @property
    def full_url(self):
        """Generate full tracking URL with UTM parameters"""
        from urllib.parse import urlencode, urlparse, urlunparse, parse_qs
        
        parsed = urlparse(self.destination_url)
        query_params = parse_qs(parsed.query)
        
        # Add UTM parameters if set
        if self.utm_source:
            query_params['utm_source'] = [self.utm_source]
        if self.utm_medium:
            query_params['utm_medium'] = [self.utm_medium]
        if self.utm_campaign:
            query_params['utm_campaign'] = [self.utm_campaign]
        if self.utm_content:
            query_params['utm_content'] = [self.utm_content]
        if self.utm_term:
            query_params['utm_term'] = [self.utm_term]
        
        # Flatten query params (convert lists to single values)
        query_string = urlencode({k: v[0] for k, v in query_params.items()})
        
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            query_string,
            parsed.fragment
        ))
    
    def __str__(self):
        return f"{self.short_code} → {self.campaign.name}"


# ============================================================================
# ✅ NEW: LINK DAILY STATS (B. Click Attribution - Aggregates)
# ============================================================================

class LinkDailyStat(models.Model):
    """
    Daily aggregated statistics for tracking links.
    Pre-computed for fast reporting without querying individual events.
    
    NEW MODEL for fast click analytics
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    link = models.ForeignKey(
        TrackingLink,
        on_delete=models.CASCADE,
        related_name='daily_stats'
    )
    
    date = models.DateField(db_index=True)
    
    # Click metrics
    total_clicks = models.IntegerField(
        default=0,
        help_text="Total number of clicks (all events)"
    )
    
    unique_visitors = models.IntegerField(
        default=0,
        help_text="Unique visitors (distinct visitor_id) - most accurate unique count"
    )
    
    unique_sessions = models.IntegerField(
        default=0,
        help_text="Unique sessions (distinct session_id)"
    )
    
    unique_users = models.IntegerField(
        default=0,
        help_text="Unique authenticated users (distinct user_id)"
    )
    
    # Conversion metrics
    conversions = models.IntegerField(
        default=0,
        help_text="Number of conversions attributed to this link"
    )
    
    conversion_rate = models.FloatField(
        null=True,
        blank=True,
        help_text="Conversion rate (conversions / unique_visitors * 100)"
    )
    
    revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Revenue attributed to this link"
    )
    
    # Geographic data (top countries/cities)
    geo_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Geographic breakdown: {'US': 100, 'UK': 50}"
    )
    
    # Device data
    device_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Device breakdown: {'mobile': 150, 'desktop': 50}"
    )
    
    # Metadata
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'link_daily_stats'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['link', '-date'], name='idx_linkstat_link_date'),
            models.Index(fields=['date'], name='idx_linkstat_date'),
        ]
        unique_together = [['link', 'date']]
    
    def __str__(self):
        return f"{self.link.short_code} - {self.date} ({self.total_clicks} clicks)"


# ============================================================================
# ANALYTICS EVENTS
# ============================================================================

class AnalyticsEvent(models.Model):
    """
    Append-only event stream for analytics tracking.
    
    Foundation-owned table with proper ForeignKey relationships to entity models.
    Stores all analytics events with support for deduplication and flexible JSON metadata.
    
    UPDATED: Added conversion_value for revenue attribution
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the event"
    )
    
    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
        db_index=True,
        help_text="Type of analytics event (static choices for MVP)"
    )
    
    occurred_at = models.DateTimeField(
        db_index=True,
        help_text="When the event actually occurred (may differ from created_at)"
    )
    
    # Entity relationships
    platform = models.ForeignKey(
        Platform,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analytics_events',
        db_index=True,
        help_text="Platform where event occurred"
    )
    
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analytics_events',
        db_index=True,
        help_text="Brand associated with event"
    )
    
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analytics_events',
        db_index=True,
        help_text="Campaign associated with event"
    )
    
    creator = models.ForeignKey(
        Creator,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analytics_events',
        db_index=True,
        help_text="Creator associated with event"
    )
    
    content = models.ForeignKey(
        Content,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analytics_events',
        db_index=True,
        help_text="Content associated with event"
    )
    
    link = models.ForeignKey(
        TrackingLink,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analytics_events',
        db_index=True,
        help_text="Tracking link associated with event"
    )
    
    # ✅ NEW: Stable visitor & session tracking for accurate unique counts
    visitor_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="""Stable visitor identifier (cookie/fingerprint/device_id).
        Used for unique user counting. Should be consistent across sessions.
        Example: UUID from cookie, hashed fingerprint, authenticated user_id"""
    )
    
    session_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="""Session identifier (browser session, app session).
        Used for sessionized analytics. Expires after inactivity period.
        Example: Session UUID, expires after 30min inactivity"""
    )
    
    # User context (for authenticated users)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analytics_events',
        db_index=True,
        help_text="Authenticated user (if logged in)"
    )
    
    # Deduplication
    external_event_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="External system event ID for cross-system tracking"
    )
    
    dedupe_hash = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        help_text="Hash for deduplication - unique constraint prevents duplicate events"
    )
    
    # ✅ NEW: Conversion tracking (B. Click Attribution)
    conversion_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Revenue value for purchase/conversion events"
    )
    
    conversion_attributed_to_link = models.ForeignKey(
        TrackingLink,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attributed_conversions',
        help_text="Link that gets attribution credit for this conversion"
    )
    
    # Flexible data
    metrics = models.JSONField(
        null=True,
        blank=True,
        default=dict,
        help_text="Event-specific metrics (e.g., {'clicks': 10, 'revenue': 100.50})"
    )
    
    meta = models.JSONField(
        null=True,
        blank=True,
        default=dict,
        help_text="Additional metadata (e.g., {'user_agent': '...', 'ip': '...'})"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the event was inserted into the database"
    )
    
    class Meta:
        db_table = 'analytics_events'
        verbose_name = 'Analytics Event'
        verbose_name_plural = 'Analytics Events'
        ordering = ['-occurred_at']
        
        indexes = [
            models.Index(fields=['event_type', '-occurred_at'], name='idx_type_occurred'),
            models.Index(fields=['-created_at'], name='idx_created_at'),
            
            # Entity-time indexes
            models.Index(fields=['campaign', 'occurred_at'], name='idx_evt_campaign_time'),
            models.Index(fields=['creator', 'occurred_at'], name='idx_evt_creator_time'),
            models.Index(fields=['content', 'occurred_at'], name='idx_evt_content_time'),
            models.Index(fields=['brand', 'occurred_at'], name='idx_evt_brand_time'),
            models.Index(fields=['platform', 'occurred_at'], name='idx_evt_platform_time'),
            models.Index(fields=['link', 'occurred_at'], name='idx_evt_link_time'),
            
            
            models.Index(fields=['visitor_id', 'occurred_at'], name='idx_evt_visitor_time'),
            models.Index(fields=['session_id', 'occurred_at'], name='idx_evt_session_time'),
            models.Index(fields=['user', 'occurred_at'], name='idx_evt_user_time'),
            
            # Unique user/session queries
            models.Index(fields=['link', 'visitor_id'], name='idx_evt_link_visitor'),
            models.Index(fields=['campaign', 'visitor_id'], name='idx_evt_campaign_visitor'),
            models.Index(fields=['content', 'visitor_id'], name='idx_evt_content_visitor'),
            
            # Deduplication
            models.Index(fields=['dedupe_hash'], name='idx_evt_dedupe_hash'),
            models.Index(fields=['external_event_id'], name='idx_evt_external_id'),
            
            # Conversion attribution
            models.Index(fields=['conversion_attributed_to_link', 'occurred_at'], name='idx_evt_conversion_attr'),
        ]
        
        permissions = [
            ('cannot_update', 'Cannot update analytics events'),
        ]
    
    def __str__(self):
        return f"{self.get_event_type_display()} at {self.occurred_at}"
    
    def save(self, *args, **kwargs):
        """
        Override save to enforce append-only behavior and auto-generate dedupe_hash.
        """
        if self.pk and AnalyticsEvent.objects.filter(pk=self.pk).exists():
            raise ValidationError(
                "Cannot update existing analytics events. This is an append-only table."
            )
        
        
        if not self.dedupe_hash and self.external_event_id:
            hash_input = f"{self.external_event_id}:{self.occurred_at}:{self.event_type}"
            self.dedupe_hash = hashlib.md5(hash_input.encode()).hexdigest()
        
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Prevent deletion of events (append-only enforcement)"""
        raise ValidationError(
            "Cannot delete analytics events. This is an append-only table."
        )


class ContentDailyStat(models.Model):
    """
    Daily statistics per content item
    
    Aggregates all engagement metrics from AnalyticsEvent and ContentSnapshot
    """
    
    content = models.ForeignKey(
        'Content',
        on_delete=models.CASCADE,
        related_name='daily_stats',
        db_index=True
    )
    
    date = models.DateField(db_index=True)
    
    # Core metrics from ContentSnapshot
    impressions = models.BigIntegerField(default=0)
    reach = models.BigIntegerField(default=0)
    video_views = models.BigIntegerField(default=0)
    
    # Engagement metrics (explicit aggregation)
    total_likes = models.BigIntegerField(default=0)
    total_comments = models.BigIntegerField(default=0)
    total_shares = models.BigIntegerField(default=0)
    total_saves = models.BigIntegerField(default=0)
    total_engagements = models.BigIntegerField(
        default=0,
        help_text='Sum of likes + comments + shares + saves'
    )
    
    # Click metrics from AnalyticsEvent
    total_clicks = models.BigIntegerField(default=0)
    unique_visitors = models.IntegerField(default=0)
    unique_sessions = models.IntegerField(default=0)
    
    # Conversion metrics
    conversions = models.IntegerField(default=0)
    conversion_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    
    # Calculated metrics
    engagement_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0)],
        help_text='Engagement rate percentage'
    )
    
    # Video-specific
    video_completion_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0)],
    )
    avg_watch_time = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0)],
        help_text='Average watch time in seconds'
    )
    
    # Metadata
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'content_daily_stats'
        verbose_name = 'Content Daily Stat'
        verbose_name_plural = 'Content Daily Stats'
        ordering = ['-date', 'content']
        indexes = [
            models.Index(fields=['content', 'date']),
            models.Index(fields=['date', 'content']),
        ]
        unique_together = [['content', 'date']]
    
    def __str__(self):
        return f"{self.content.title} - {self.date}"
    
    def save(self, *args, **kwargs):
        """Auto-calculate total_engagements and engagement_rate"""
        # Calculate total engagements
        self.total_engagements = (
            self.total_likes +
            self.total_comments +
            self.total_shares +
            self.total_saves
        )
        
        # Calculate engagement rate
        if self.impressions > 0:
            self.engagement_rate = round(
                (self.total_engagements / self.impressions) * 100,
                2
            )
        else:
            self.engagement_rate = None
        
        super().save(*args, **kwargs)


class CreatorDailyStat(models.Model):
    """
    Daily statistics per creator
    
    Aggregates metrics across all creator's content for the day
    """
    
    creator = models.ForeignKey(
        'Creator',
        on_delete=models.CASCADE,
        related_name='daily_stats',
        db_index=True
    )
    
    date = models.DateField(db_index=True)
    
    # Optional campaign filter
    campaign = models.ForeignKey(
        'Campaign',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='creator_daily_stats',
        help_text='Optional: stats per creator per campaign'
    )
    
    # Core metrics
    impressions = models.BigIntegerField(default=0)
    reach = models.BigIntegerField(default=0)
    video_views = models.BigIntegerField(default=0)
    
    # Engagement metrics (explicit aggregation)
    total_likes = models.BigIntegerField(default=0)
    total_comments = models.BigIntegerField(default=0)
    total_shares = models.BigIntegerField(default=0)
    total_saves = models.BigIntegerField(default=0)
    total_engagements = models.BigIntegerField(
        default=0,
        help_text='Sum of likes + comments + shares + saves'
    )
    
    # Click metrics
    total_clicks = models.BigIntegerField(default=0)
    unique_visitors = models.IntegerField(default=0)
    unique_sessions = models.IntegerField(default=0)
    
    # Conversion metrics
    conversions = models.IntegerField(default=0)
    conversion_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    
    # Calculated metrics
    engagement_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0)],
    )
    
    # Volume metrics
    content_posted = models.IntegerField(
        default=0,
        help_text='Number of content items posted this day'
    )
    
    # Metadata
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'creator_daily_stats'
        verbose_name = 'Creator Daily Stat'
        verbose_name_plural = 'Creator Daily Stats'
        ordering = ['-date', 'creator']
        indexes = [
            models.Index(fields=['creator', 'date']),
            models.Index(fields=['creator', 'campaign', 'date']),
            models.Index(fields=['date', 'creator']),
        ]
        unique_together = [['creator', 'date', 'campaign']]
    
    def __str__(self):
        if self.campaign:
            return f"{self.creator.name} - {self.campaign.name} - {self.date}"
        return f"{self.creator.name} - {self.date}"
    
    def save(self, *args, **kwargs):
        """Auto-calculate total_engagements and engagement_rate"""
        self.total_engagements = (
            self.total_likes +
            self.total_comments +
            self.total_shares +
            self.total_saves
        )
        
        if self.impressions > 0:
            self.engagement_rate = round(
                (self.total_engagements / self.impressions) * 100,
                2
            )
        else:
            self.engagement_rate = None
        
        super().save(*args, **kwargs)


class CampaignDailyStat(models.Model):
    """
    Daily statistics per campaign
    
    Aggregates metrics across all campaign content for the day
    """
    
    campaign = models.ForeignKey(
        'Campaign',
        on_delete=models.CASCADE,
        related_name='daily_stats',
        db_index=True
    )
    
    date = models.DateField(db_index=True)
    
    # Core metrics
    impressions = models.BigIntegerField(default=0)
    reach = models.BigIntegerField(default=0)
    video_views = models.BigIntegerField(default=0)
    
    # Engagement metrics (explicit aggregation)
    total_likes = models.BigIntegerField(default=0)
    total_comments = models.BigIntegerField(default=0)
    total_shares = models.BigIntegerField(default=0)
    total_saves = models.BigIntegerField(default=0)
    total_engagements = models.BigIntegerField(
        default=0,
        help_text='Sum of likes + comments + shares + saves'
    )
    
    # Click metrics
    total_clicks = models.BigIntegerField(default=0)
    unique_visitors = models.IntegerField(default=0)
    unique_sessions = models.IntegerField(default=0)
    
    # Conversion metrics
    conversions = models.IntegerField(default=0)
    conversion_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    
    # Calculated metrics
    engagement_rate = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0)],
    )
    
    # ROI metrics (computed from budget_spent)
    budget_spent_today = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Expenses approved on this day'
    )
    
    # Cost metrics (computed)
    cpc = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Cost per click (cumulative campaign budget / total clicks)'
    )
    cpm = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Cost per 1000 impressions'
    )
    cpe = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Cost per engagement'
    )
    
    # Volume metrics
    content_posted = models.IntegerField(
        default=0,
        help_text='Number of content items posted this day'
    )
    active_creators = models.IntegerField(
        default=0,
        help_text='Number of creators who posted content this day'
    )
    
    # Metadata
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'campaign_daily_stats'
        verbose_name = 'Campaign Daily Stat'
        verbose_name_plural = 'Campaign Daily Stats'
        ordering = ['-date', 'campaign']
        indexes = [
            models.Index(fields=['campaign', 'date']),
            models.Index(fields=['date', 'campaign']),
        ]
        unique_together = [['campaign', 'date']]
    
    def __str__(self):
        return f"{self.campaign.name} - {self.date}"
    
    def save(self, *args, **kwargs):
        """Auto-calculate metrics"""
        from decimal import Decimal
        
        # Calculate total engagements
        self.total_engagements = (
            self.total_likes +
            self.total_comments +
            self.total_shares +
            self.total_saves
        )
        
        # Calculate engagement rate
        if self.impressions > 0:
            self.engagement_rate = round(
                (self.total_engagements / self.impressions) * 100,
                2
            )
        else:
            self.engagement_rate = None
        
        # Calculate cost metrics (using campaign's cumulative budget_spent)
        if hasattr(self, 'campaign') and self.campaign:
            budget = self.campaign.budget_spent
            
            if budget and budget > 0:
                if self.total_clicks > 0:
                    self.cpc = round(budget / self.total_clicks, 4)
                
                if self.impressions > 0:
                    self.cpm = round((budget / self.impressions) * 1000, 4)
                
                if self.total_engagements > 0:
                    self.cpe = round(budget / self.total_engagements, 4)
        
        super().save(*args, **kwargs)