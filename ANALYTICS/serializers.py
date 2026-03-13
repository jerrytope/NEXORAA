# ANALYTICS/serializers.py
"""
DRF Serializers for Analytics Models

Converts database models to JSON for API responses.
Includes read-only, write, and nested serializers.
"""

from rest_framework import serializers
from decimal import Decimal
from django.utils import timezone

from ANALYTICS.models import (
    Platform,
    Brand,
    Creator,
    Campaign,
    Content,
    TrackingLink,
    AnalyticsEvent,
    LinkDailyStat,
    ContentSnapshot,
    CampaignExpense,
    CreatorContract,
)


# ============================================================================
# FOUNDATION MODELS
# ============================================================================

class PlatformSerializer(serializers.ModelSerializer):
    """Serialize Platform model"""
    
    class Meta:
        model = Platform
        fields = [
            'id',
            'name',
            'slug',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']


class BrandSerializer(serializers.ModelSerializer):
    """Serialize Brand model"""
    
    owner_username = serializers.CharField(
        source='owner.username',
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = Brand
        fields = [
            'id',
            'name',
            'owner',
            'owner_username',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'owner_username']


class CreatorSerializer(serializers.ModelSerializer):
    """Serialize Creator model"""
    
    class Meta:
        model = Creator
        fields = [
            'id',
            'name',
            'email',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ============================================================================
# CAMPAIGN & BUDGET
# ============================================================================

class CampaignSerializer(serializers.ModelSerializer):
    """Serialize Campaign model with budget info"""
    
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    
    # Computed fields
    budget_remaining = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    budget_utilization_pct = serializers.FloatField(read_only=True)
    
    class Meta:
        model = Campaign
        fields = [
            'id',
            'name',
            'brand',
            'brand_name',
            'start_date',
            'end_date',
            'budget_total',
            'budget_spent',
            'budget_remaining',
            'budget_currency',
            'budget_utilization_pct',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'budget_spent',
            'budget_remaining',
            'budget_utilization_pct',
            'created_at',
            'updated_at',
            'brand_name',
        ]


class CampaignExpenseSerializer(serializers.ModelSerializer):
    """Serialize Campaign Expense"""
    
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    creator_name = serializers.CharField(
        source='creator.name',
        read_only=True,
        allow_null=True
    )
    approved_by_username = serializers.CharField(
        source='approved_by.username',
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = CampaignExpense
        fields = [
            'id',
            'campaign',
            'campaign_name',
            'expense_type',
            'amount',
            'currency',
            'creator',
            'creator_name',
            'contract',
            'description',
            'expense_date',
            'receipt_url',
            'invoice_number',
            'is_approved',
            'approved_by',
            'approved_by_username',
            'approved_at',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
            'campaign_name',
            'creator_name',
            'approved_by_username',
        ]


class CreatorContractSerializer(serializers.ModelSerializer):
    """Serialize Creator Contract"""
    
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    creator_name = serializers.CharField(source='creator.name', read_only=True)
    
    # Computed fields
    amount_remaining = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    payment_progress_pct = serializers.FloatField(read_only=True)
    
    class Meta:
        model = CreatorContract
        fields = [
            'id',
            'campaign',
            'campaign_name',
            'creator',
            'creator_name',
            'contracted_amount',
            'amount_paid',
            'amount_remaining',
            'currency',
            'payment_status',
            'payment_progress_pct',
            'payment_due_date',
            'payment_completed_date',
            'deliverable_status',
            'deliverables',
            'deliverables_completed',
            'contract_start_date',
            'contract_end_date',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'amount_remaining',
            'payment_progress_pct',
            'created_at',
            'updated_at',
            'campaign_name',
            'creator_name',
        ]


# ============================================================================
# CONTENT & TRACKING
# ============================================================================

class ContentSerializer(serializers.ModelSerializer):
    """Serialize Content model"""
    
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    creator_name = serializers.CharField(source='creator.name', read_only=True)
    campaign_name = serializers.CharField(
        source='campaign.name',
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = Content
        fields = [
            'id',
            'title',
            'platform',
            'platform_name',
            'creator',
            'creator_name',
            'campaign',
            'campaign_name',
            'external_id',
            'url',
            'published_at',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'platform_name',
            'creator_name',
            'campaign_name',
        ]


class TrackingLinkSerializer(serializers.ModelSerializer):
    """Serialize Tracking Link"""
    
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    creator_name = serializers.CharField(
        source='creator.name',
        read_only=True,
        allow_null=True
    )
    
    # Computed field
    full_url = serializers.URLField(read_only=True)
    
    class Meta:
        model = TrackingLink
        fields = [
            'id',
            'short_code',
            'destination_url',
            'full_url',
            'utm_source',
            'utm_medium',
            'utm_campaign',
            'utm_content',
            'utm_term',
            'campaign',
            'campaign_name',
            'creator',
            'creator_name',
            'content',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'short_code',
            'full_url',
            'created_at',
            'updated_at',
            'campaign_name',
            'creator_name',
        ]


# ============================================================================
# ANALYTICS EVENTS
# ============================================================================

class AnalyticsEventSerializer(serializers.ModelSerializer):
    """
    Serialize Analytics Event
    
    Note: This is primarily for reading events.
    For writing, use the Ingestion API which handles entity linking.
    """
    
    # Related entity names (read-only)
    platform_name = serializers.CharField(
        source='platform.name',
        read_only=True,
        allow_null=True
    )
    brand_name = serializers.CharField(
        source='brand.name',
        read_only=True,
        allow_null=True
    )
    campaign_name = serializers.CharField(
        source='campaign.name',
        read_only=True,
        allow_null=True
    )
    creator_name = serializers.CharField(
        source='creator.name',
        read_only=True,
        allow_null=True
    )
    content_title = serializers.CharField(
        source='content.title',
        read_only=True,
        allow_null=True
    )
    link_short_code = serializers.CharField(
        source='link.short_code',
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = AnalyticsEvent
        fields = [
            'id',
            'event_type',
            'occurred_at',
            
            # Entity relationships
            'platform',
            'platform_name',
            'brand',
            'brand_name',
            'campaign',
            'campaign_name',
            'creator',
            'creator_name',
            'content',
            'content_title',
            'link',
            'link_short_code',
            
            # Visitor tracking
            'visitor_id',
            'session_id',
            'user',
            
            # Conversion
            'conversion_value',
            'conversion_attributed_to_link',
            
            # Deduplication
            'external_event_id',
            'dedupe_hash',
            
            # Data
            'metrics',
            'meta',
            
            'created_at',
        ]
        read_only_fields = [
            'id',
            'dedupe_hash',
            'created_at',
            'platform_name',
            'brand_name',
            'campaign_name',
            'creator_name',
            'content_title',
            'link_short_code',
        ]


class AnalyticsEventListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing events (fewer fields)
    """
    
    event_type_display = serializers.CharField(
        source='get_event_type_display',
        read_only=True
    )
    
    class Meta:
        model = AnalyticsEvent
        fields = [
            'id',
            'event_type',
            'event_type_display',
            'occurred_at',
            'campaign',
            'link',
            'visitor_id',
            'conversion_value',
        ]
        read_only_fields = [
            'id', 'event_type', 'event_type_display', 'occurred_at',
            'campaign', 'link', 'visitor_id', 'conversion_value',
        ]


# ============================================================================
# AGGREGATED DATA
# ============================================================================

class LinkDailyStatSerializer(serializers.ModelSerializer):
    """Serialize Link Daily Statistics"""
    
    link_short_code = serializers.CharField(source='link.short_code', read_only=True)
    link_destination = serializers.URLField(
        source='link.destination_url',
        read_only=True
    )
    campaign_name = serializers.CharField(
        source='link.campaign.name',
        read_only=True
    )
    
    class Meta:
        model = LinkDailyStat
        fields = [
            'id',
            'link',
            'link_short_code',
            'link_destination',
            'campaign_name',
            'date',
            
            # Click metrics
            'total_clicks',
            'unique_visitors',
            'unique_sessions',
            'unique_users',
            
            # Conversion metrics
            'conversions',
            'conversion_rate',
            'revenue',
            
            # Breakdowns
            'geo_data',
            'device_data',
            
            'calculated_at',
        ]
        read_only_fields = [
            'id', 'link', 'link_short_code', 'link_destination', 'campaign_name',
            'date', 'total_clicks', 'unique_visitors', 'unique_sessions', 'unique_users',
            'conversions', 'conversion_rate', 'revenue', 'geo_data', 'device_data',
            'calculated_at',
        ]


class ContentSnapshotSerializer(serializers.ModelSerializer):
    """Serialize Content Snapshot"""
    
    content_title = serializers.CharField(source='content.title', read_only=True)
    content_url = serializers.URLField(source='content.url', read_only=True)
    platform_name = serializers.CharField(
        source='content.platform.name',
        read_only=True
    )
    
    class Meta:
        model = ContentSnapshot
        fields = [
            'id',
            'content',
            'content_title',
            'content_url',
            'platform_name',
            'captured_at',
            
            # Metrics
            'likes_count',
            'comments_count',
            'shares_count',
            'saves_count',
            'views_count',
            'reach',
            'impressions',
            'engagement_rate',
            
            # Deltas
            'likes_delta',
            'comments_delta',
            'shares_delta',
            'views_delta',
            
            # Platform-specific
            'platform_metrics',
            
            'created_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'content_title',
            'content_url',
            'platform_name',
        ]


# ============================================================================
# NESTED/DETAILED SERIALIZERS (for related data)
# ============================================================================

class CampaignDetailSerializer(serializers.ModelSerializer):
    """
    Detailed Campaign serializer with nested related data
    """
    
    brand = BrandSerializer(read_only=True)
    
    # Expense summary
    total_expenses = serializers.SerializerMethodField()
    approved_expenses = serializers.SerializerMethodField()
    pending_expenses = serializers.SerializerMethodField()
    
    # Contract summary
    total_contracts = serializers.SerializerMethodField()
    total_contracted_amount = serializers.SerializerMethodField()
    
    # Content summary
    total_content = serializers.SerializerMethodField()
    total_links = serializers.SerializerMethodField()
    
    # Budget info
    budget_remaining = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    budget_utilization_pct = serializers.FloatField(read_only=True)
    
    class Meta:
        model = Campaign
        fields = [
            'id',
            'name',
            'brand',
            'start_date',
            'end_date',
            
            # Budget
            'budget_total',
            'budget_spent',
            'budget_remaining',
            'budget_currency',
            'budget_utilization_pct',
            
            # Summaries
            'total_expenses',
            'approved_expenses',
            'pending_expenses',
            'total_contracts',
            'total_contracted_amount',
            'total_content',
            'total_links',
            
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'name', 'brand', 'start_date', 'end_date', 'budget_total',
            'budget_spent', 'budget_remaining', 'budget_currency', 'budget_utilization_pct',
            'total_expenses', 'approved_expenses', 'pending_expenses', 'total_contracts',
            'total_contracted_amount', 'total_content', 'total_links', 'is_active',
            'created_at', 'updated_at',
        ]
    
    def get_total_expenses(self, obj):
        return obj.expenses.count()
    
    def get_approved_expenses(self, obj):
        return obj.expenses.filter(is_approved=True).count()
    
    def get_pending_expenses(self, obj):
        return obj.expenses.filter(is_approved=False).count()
    
    def get_total_contracts(self, obj):
        return obj.creator_contracts.count()
    
    def get_total_contracted_amount(self, obj):
        from django.db.models import Sum
        total = obj.creator_contracts.aggregate(
            total=Sum('contracted_amount')
        )['total']
        return str(total) if total else "0.00"
    
    def get_total_content(self, obj):
        return obj.content_items.count()
    
    def get_total_links(self, obj):
        return obj.tracking_links.count()


class LinkDetailSerializer(serializers.ModelSerializer):
    """
    Detailed Link serializer with performance stats
    """
    
    campaign = CampaignSerializer(read_only=True)
    creator = CreatorSerializer(read_only=True)
    content = ContentSerializer(read_only=True)
    
    # Performance summary (last 30 days)
    total_clicks_30d = serializers.SerializerMethodField()
    unique_visitors_30d = serializers.SerializerMethodField()
    conversions_30d = serializers.SerializerMethodField()
    revenue_30d = serializers.SerializerMethodField()
    
    # Computed field
    full_url = serializers.URLField(read_only=True)
    
    class Meta:
        model = TrackingLink
        fields = [
            'id',
            'short_code',
            'destination_url',
            'full_url',
            
            # UTM
            'utm_source',
            'utm_medium',
            'utm_campaign',
            'utm_content',
            'utm_term',
            
            # Relationships
            'campaign',
            'creator',
            'content',
            
            # Performance
            'total_clicks_30d',
            'unique_visitors_30d',
            'conversions_30d',
            'revenue_30d',
            
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'short_code', 'destination_url', 'full_url', 'utm_source',
            'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'campaign',
            'creator', 'content', 'total_clicks_30d', 'unique_visitors_30d',
            'conversions_30d', 'revenue_30d', 'is_active', 'created_at', 'updated_at',
        ]
    
    def get_total_clicks_30d(self, obj):
        from django.db.models import Sum
        from datetime import timedelta
        from django.utils import timezone
        
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        return obj.daily_stats.filter(
            date__gte=thirty_days_ago
        ).aggregate(total=Sum('total_clicks'))['total'] or 0
    
    def get_unique_visitors_30d(self, obj):
        from django.db.models import Sum
        from datetime import timedelta
        from django.utils import timezone
        
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        return obj.daily_stats.filter(
            date__gte=thirty_days_ago
        ).aggregate(total=Sum('unique_visitors'))['total'] or 0
    
    def get_conversions_30d(self, obj):
        from django.db.models import Sum
        from datetime import timedelta
        from django.utils import timezone
        
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        return obj.daily_stats.filter(
            date__gte=thirty_days_ago
        ).aggregate(total=Sum('conversions'))['total'] or 0
    
    def get_revenue_30d(self, obj):
        from django.db.models import Sum
        from datetime import timedelta
        from django.utils import timezone
        
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        total = obj.daily_stats.filter(
            date__gte=thirty_days_ago
        ).aggregate(total=Sum('revenue'))['total']
        return str(total) if total else "0.00"


class ContentDetailSerializer(serializers.ModelSerializer):
    """
    Detailed Content serializer with latest snapshot
    """
    
    platform = PlatformSerializer(read_only=True)
    creator = CreatorSerializer(read_only=True)
    campaign = CampaignSerializer(read_only=True)
    
    # Latest snapshot
    latest_snapshot = serializers.SerializerMethodField()
    
    # Snapshot count
    total_snapshots = serializers.SerializerMethodField()
    
    class Meta:
        model = Content
        fields = [
            'id',
            'title',
            'platform',
            'creator',
            'campaign',
            'external_id',
            'url',
            'published_at',
            
            # Snapshots
            'latest_snapshot',
            'total_snapshots',
            
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'title', 'platform', 'creator', 'campaign', 'external_id',
            'url', 'published_at', 'latest_snapshot', 'total_snapshots',
            'is_active', 'created_at', 'updated_at',
        ]
    
    def get_latest_snapshot(self, obj):
        latest = obj.snapshots.order_by('-captured_at').first()
        if latest:
            return ContentSnapshotSerializer(latest).data
        return None
    
    def get_total_snapshots(self, obj):
        return obj.snapshots.count()


# ============================================================================
# INGESTION SERIALIZERS (for API input)
# ============================================================================

class EventIngestionSerializer(serializers.Serializer):
    """
    Serializer for ingesting analytics events via API
    """
    
    # Required fields
    event_type = serializers.ChoiceField(
        choices=[
            'page_view', 'impression', 'click', 'like', 'share', 'comment',
            'signup', 'login', 'purchase', 'add_to_cart', 'refund',
            'download', 'search', 'custom'
        ]
    )
    occurred_at = serializers.DateTimeField()
    
    # Identifiers (at least one required)
    link_id = serializers.UUIDField(required=False, allow_null=True)
    content_id = serializers.UUIDField(required=False, allow_null=True)
    platform_id = serializers.UUIDField(required=False, allow_null=True)
    external_id = serializers.CharField(
        max_length=255,
        required=False,
        allow_null=True,
        allow_blank=True
    )
    
    # Optional entity overrides
    campaign_id = serializers.UUIDField(required=False, allow_null=True)
    creator_id = serializers.UUIDField(required=False, allow_null=True)
    brand_id = serializers.UUIDField(required=False, allow_null=True)
    
    # Visitor tracking
    visitor_id = serializers.CharField(
        max_length=255,
        required=False,
        allow_null=True,
        allow_blank=True
    )
    session_id = serializers.CharField(
        max_length=255,
        required=False,
        allow_null=True,
        allow_blank=True
    )
    user_id = serializers.IntegerField(required=False, allow_null=True)
    
    # Conversion
    conversion_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True
    )
    conversion_attributed_to_link_id = serializers.UUIDField(
        required=False,
        allow_null=True
    )
    
    # Deduplication
    external_event_id = serializers.CharField(
        max_length=255,
        required=False,
        allow_null=True,
        allow_blank=True
    )
    
    # Flexible data
    metrics = serializers.JSONField(required=False, default=dict)
    meta = serializers.JSONField(required=False, default=dict)
    
    def validate(self, data):
        """
        Validate that at least one identifier is provided
        """
        identifiers = [
            data.get('link_id'),
            data.get('content_id'),
            (data.get('platform_id') and data.get('external_id'))
        ]
        
        if not any(identifiers):
            raise serializers.ValidationError(
                "At least one identifier required: link_id, content_id, "
                "or (platform_id + external_id)"
            )
        
        return data


class SnapshotCreationSerializer(serializers.Serializer):
    """
    Serializer for creating content snapshots via API
    """
    
    content_id = serializers.UUIDField()
    captured_at = serializers.DateTimeField(required=False)
    
    # Metrics
    likes_count = serializers.IntegerField(default=0, min_value=0)
    comments_count = serializers.IntegerField(default=0, min_value=0)
    shares_count = serializers.IntegerField(default=0, min_value=0)
    saves_count = serializers.IntegerField(default=0, min_value=0)
    views_count = serializers.IntegerField(default=0, min_value=0)
    reach = serializers.IntegerField(default=0, min_value=0)
    impressions = serializers.IntegerField(default=0, min_value=0)
    
    # Platform-specific
    platform_metrics = serializers.JSONField(required=False, default=dict)