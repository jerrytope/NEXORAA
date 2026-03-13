# SOCIAL_INTELLIGENCE/api/urls.py
"""
URL Configuration for Social Intelligence API

Provides REST API endpoints for all social intelligence features.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from SOCIAL_INTELLIGENCE.views import (

    TrackedEntityViewSet,
    EntityKeywordViewSet,
    EntityCompetitorViewSet,
    
    MentionViewSet,
    MentionEntityViewSet,
    MentionSentimentViewSet,
    
    MentionTopicViewSet,
    ExtractedKeywordViewSet,
    
    EntityDailyStatViewSet,
    
    AlertViewSet,
    
    CampaignAnalyticsViewSet,
    CreatorAnalyticsViewSet,
    ContentAnalyticsViewSet,
)


router = DefaultRouter()

# Register viewsets
router.register(r'entities', TrackedEntityViewSet, basename='entity')
router.register(r'keywords', EntityKeywordViewSet, basename='keyword')
router.register(r'competitors', EntityCompetitorViewSet, basename='competitor')
router.register(r'mentions', MentionViewSet, basename='mention')
router.register(r'mention-entities', MentionEntityViewSet, basename='mention-entity')
router.register(r'mention-sentiments', MentionSentimentViewSet, basename='mention-sentiment')
router.register(r'topics', MentionTopicViewSet, basename='topic')
router.register(r'extracted-keywords', ExtractedKeywordViewSet, basename='extracted-keyword')
router.register(r'entity-stats', EntityDailyStatViewSet, basename='entity-stat')
router.register(r'alerts', AlertViewSet, basename='alert')

# Analytics endpoints (non-model viewsets)
router.register(r'campaign-analytics', CampaignAnalyticsViewSet, basename='campaign-analytics')
router.register(r'creator-analytics', CreatorAnalyticsViewSet, basename='creator-analytics')
router.register(r'content-analytics', ContentAnalyticsViewSet, basename='content-analytics')

urlpatterns = [
    path('', include(router.urls)),
]

