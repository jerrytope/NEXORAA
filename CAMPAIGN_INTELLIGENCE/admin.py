from django.contrib import admin
from .models import (
    CampaignCreator,
    CampaignPost,
    CreatorPerformanceAggregate,
    CreatorScoreHistory,
    CampaignEfficiencyScore,
)


@admin.register(CampaignCreator)
class CampaignCreatorAdmin(admin.ModelAdmin):
    list_display = [
        'campaign', 'creator', 'agreed_fee', 
        'expected_posts', 'actual_posts', 'status'
    ]
    list_filter = ['status', 'invited_at']
    search_fields = ['campaign__name', 'creator__name']
    readonly_fields = ['invited_at', 'accepted_at', 'completed_at']


@admin.register(CampaignPost)
class CampaignPostAdmin(admin.ModelAdmin):
    list_display = [
        'campaign', 'creator', 'platform', 
        'content_type', 'posted_at', 'status'
    ]
    list_filter = ['platform', 'content_type', 'status']
    search_fields = ['external_post_id', 'caption']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(CreatorPerformanceAggregate)
class CreatorPerformanceAggregateAdmin(admin.ModelAdmin):
    list_display = [
        'creator', 'lifetime_efficiency_score', 
        'global_rank', 'total_campaigns', 'total_spend'
    ]
    readonly_fields = [
        'last_updated', 'created_at', 'global_rank', 
        'global_percentile', 'lifetime_efficiency_score'
    ]
    search_fields = ['creator__name']


@admin.register(CreatorScoreHistory)
class CreatorScoreHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'creator', 'campaign', 'campaign_score', 
        'tier', 'created_at'
    ]
    list_filter = ['tier', 'created_at']
    readonly_fields = ['created_at']
    search_fields = ['creator__name', 'campaign__name']


@admin.register(CampaignEfficiencyScore)
class CampaignEfficiencyScoreAdmin(admin.ModelAdmin):
    list_display = [
        'campaign', 'efficiency_score', 'roi', 
        'total_spend', 'calculated_at'
    ]
    readonly_fields = ['calculated_at', 'created_at']