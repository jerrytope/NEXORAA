from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    # Foundation
    PlatformViewSet,
    BrandViewSet,
    CreatorViewSet,
    
    # Campaign & Budget
    CampaignViewSet,
    CampaignExpenseViewSet,
    CreatorContractViewSet,
    
    # Content & Tracking
    ContentViewSet,
    TrackingLinkViewSet,
    
    # Analytics Events
    AnalyticsEventViewSet,
    
    # Aggregated Data
    LinkDailyStatViewSet,
    ContentSnapshotViewSet,
    
    # Ingestion
    AnalyticsIngestionViewSet,
)

# Create router
router = DefaultRouter()

# Register viewsets
router.register(r'platforms', PlatformViewSet, basename='platform')
router.register(r'brands', BrandViewSet, basename='brand')
router.register(r'creators', CreatorViewSet, basename='creator')
router.register(r'campaigns', CampaignViewSet, basename='campaign')
router.register(r'expenses', CampaignExpenseViewSet, basename='expense')
router.register(r'contracts', CreatorContractViewSet, basename='contract')
router.register(r'content', ContentViewSet, basename='content')
router.register(r'links', TrackingLinkViewSet, basename='link')
router.register(r'events', AnalyticsEventViewSet, basename='event')
router.register(r'link-stats', LinkDailyStatViewSet, basename='linkstat')
router.register(r'snapshots', ContentSnapshotViewSet, basename='snapshot')
router.register(r'ingest', AnalyticsIngestionViewSet, basename='ingest')

urlpatterns = [
    path('', include(router.urls)),
]

