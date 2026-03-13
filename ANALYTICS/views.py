"""
DRF ViewSets for Analytics Models

Provides complete CRUD operations and filtering for all analytics data.
"""

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from datetime import date, timedelta

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

from ANALYTICS.serializers import (
    PlatformSerializer,
    BrandSerializer,
    CreatorSerializer,
    CampaignSerializer,
    CampaignDetailSerializer,
    ContentSerializer,
    ContentDetailSerializer,
    TrackingLinkSerializer,
    LinkDetailSerializer,
    AnalyticsEventSerializer,
    AnalyticsEventListSerializer,
    LinkDailyStatSerializer,
    ContentSnapshotSerializer,
    CampaignExpenseSerializer,
    CreatorContractSerializer,
    EventIngestionSerializer,
    SnapshotCreationSerializer,
)

from ANALYTICS.services.ingestion import AnalyticsIngestionService
from ANALYTICS.services.rollups import (
    BudgetRollupService,
    LinkStatsAggregationService,
    ContentSnapshotService,
)


# ============================================================================
# FOUNDATION MODELS
# ============================================================================

class PlatformViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Platform model
    
    list: Get all platforms
    retrieve: Get single platform
    create: Create new platform
    update: Update platform
    destroy: Delete platform
    """
    
    queryset = Platform.objects.all()
    serializer_class = PlatformSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'slug']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class BrandViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Brand model
    
    Filters:
    - is_active: Filter by active status
    - owner: Filter by owner user
    """
    
    queryset = Brand.objects.select_related('owner').all()
    serializer_class = BrandSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'owner']
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        """Filter brands by current user if not staff"""
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(owner=self.request.user)
        return queryset

    def perform_create(self, serializer):
        """Automatically set the brand owner to the current user"""
        if not self.request.user.is_staff or 'owner' not in self.request.data:
            serializer.save(owner=self.request.user)
        else:
            serializer.save()


class CreatorViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Creator model
    
    Filters:
    - is_active: Filter by active status
    """
    
    queryset = Creator.objects.all()
    serializer_class = CreatorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'email']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


# ============================================================================
# CAMPAIGN & BUDGET
# ============================================================================

class CampaignViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Campaign model
    
    Filters:
    - brand: Filter by brand
    - is_active: Filter by active status
    - start_date: Filter by start date
    
    Actions:
    - rollup_budget: Recalculate budget_spent
    - check_overspend: Check if over budget
    """
    
    queryset = Campaign.objects.select_related('brand').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['brand', 'is_active']
    search_fields = ['name', 'brand__name']
    ordering_fields = ['name', 'start_date', 'budget_spent', 'created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Use detailed serializer for retrieve"""
        if self.action == 'retrieve':
            return CampaignDetailSerializer
        return CampaignSerializer
    
    @action(detail=True, methods=['post'])
    def rollup_budget(self, request, pk=None):
        """Recalculate campaign budget from expenses"""
        campaign = self.get_object()
        
        service = BudgetRollupService()
        results = service.rollup_campaign_spend(
            campaign_id=str(campaign.id),
            include_unapproved=request.data.get('include_unapproved', False)
        )
        
        campaign.refresh_from_db()
        serializer = self.get_serializer(campaign)
        
        return Response({
            'success': True,
            'campaign': serializer.data,
            'budget_spent': str(campaign.budget_spent),
        })
    
    @action(detail=False, methods=['get'])
    def overspent(self, request):
        """Get campaigns that are over budget"""
        service = BudgetRollupService()
        overspent = service.check_budget_overspend()
        
        return Response({
            'count': len(overspent),
            'campaigns': overspent,
        })


class CampaignExpenseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Campaign Expenses
    
    Filters:
    - campaign: Filter by campaign
    - expense_type: Filter by type
    - is_approved: Filter by approval status
    - creator: Filter by creator
    
    Actions:
    - approve: Approve expense
    - reject: Reject/unapprove expense
    """
    
    queryset = CampaignExpense.objects.select_related(
        'campaign', 'creator', 'approved_by'
    ).all()
    serializer_class = CampaignExpenseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['campaign', 'expense_type', 'is_approved', 'creator']
    ordering_fields = ['expense_date', 'amount', 'created_at']
    ordering = ['-expense_date']
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve an expense"""
        expense = self.get_object()
        
        expense.is_approved = True
        expense.approved_by = request.user
        expense.approved_at = timezone.now()
        expense.save()
        
        # Trigger budget rollup
        service = BudgetRollupService()
        service.rollup_campaign_spend(campaign_id=str(expense.campaign.id))
        
        serializer = self.get_serializer(expense)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject/unapprove an expense"""
        expense = self.get_object()
        
        expense.is_approved = False
        expense.approved_by = None
        expense.approved_at = None
        expense.save()
        
        # Trigger budget rollup
        service = BudgetRollupService()
        service.rollup_campaign_spend(campaign_id=str(expense.campaign.id))
        
        serializer = self.get_serializer(expense)
        return Response(serializer.data)


class CreatorContractViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Creator Contracts
    
    Filters:
    - campaign: Filter by campaign
    - creator: Filter by creator
    - payment_status: Filter by payment status
    - deliverable_status: Filter by deliverable status
    """
    
    queryset = CreatorContract.objects.select_related('campaign', 'creator').all()
    serializer_class = CreatorContractSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['campaign', 'creator', 'payment_status', 'deliverable_status']
    ordering_fields = ['contracted_amount', 'payment_due_date', 'created_at']
    ordering = ['-created_at']


# ============================================================================
# CONTENT & TRACKING
# ============================================================================

class ContentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Content model
    
    Filters:
    - platform: Filter by platform
    - creator: Filter by creator
    - campaign: Filter by campaign
    - is_active: Filter by active status
    """
    
    queryset = Content.objects.select_related(
        'platform', 'creator', 'campaign'
    ).all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['platform', 'creator', 'campaign', 'is_active']
    search_fields = ['title', 'external_id']
    ordering_fields = ['published_at', 'created_at']
    ordering = ['-published_at']
    
    def get_serializer_class(self):
        """Use detailed serializer for retrieve"""
        if self.action == 'retrieve':
            return ContentDetailSerializer
        return ContentSerializer


class TrackingLinkViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Tracking Links
    
    Filters:
    - campaign: Filter by campaign
    - creator: Filter by creator
    - is_active: Filter by active status
    
    Actions:
    - stats: Get performance stats
    - aggregate: Trigger stats aggregation
    """
    
    queryset = TrackingLink.objects.select_related(
        'campaign', 'creator', 'content'
    ).all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['campaign', 'creator', 'is_active']
    search_fields = ['short_code', 'destination_url']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Use detailed serializer for retrieve"""
        if self.action == 'retrieve':
            return LinkDetailSerializer
        return TrackingLinkSerializer
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get link performance stats"""
        link = self.get_object()
        
        # Get date range from query params
        days = int(request.query_params.get('days', 30))
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        stats = LinkDailyStat.objects.filter(
            link=link,
            date__gte=start_date,
            date__lte=end_date
        ).order_by('date')
        
        serializer = LinkDailyStatSerializer(stats, many=True)
        
        return Response({
            'link_id': str(link.id),
            'short_code': link.short_code,
            'date_range': {
                'start': str(start_date),
                'end': str(end_date),
            },
            'stats': serializer.data,
        })
    
    @action(detail=True, methods=['post'])
    def aggregate(self, request, pk=None):
        """Trigger stats aggregation for this link"""
        link = self.get_object()
        
        target_date = request.data.get('date')
        if target_date:
            target_date = date.fromisoformat(target_date)
        else:
            target_date = timezone.now().date() - timedelta(days=1)
        
        service = LinkStatsAggregationService()
        results = service.aggregate_link_stats(
            target_date=target_date,
            link_id=str(link.id)
        )
        
        return Response({
            'success': True,
            'date': str(target_date),
            'results': results,
        })


# ============================================================================
# ANALYTICS EVENTS
# ============================================================================

class AnalyticsEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Analytics Events (READ-ONLY)
    
    For creating events, use the Ingestion API endpoints.
    
    Filters:
    - event_type: Filter by event type
    - campaign: Filter by campaign
    - creator: Filter by creator
    - link: Filter by link
    - visitor_id: Filter by visitor
    - occurred_at__gte: Events after date
    - occurred_at__lte: Events before date
    """
    
    queryset = AnalyticsEvent.objects.select_related(
        'platform', 'brand', 'campaign', 'creator', 'content', 'link'
    ).all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {
        'event_type': ['exact'],
        'campaign': ['exact'],
        'creator': ['exact'],
        'link': ['exact'],
        'visitor_id': ['exact'],
        'occurred_at': ['gte', 'lte', 'date'],
    }
    ordering_fields = ['occurred_at', 'created_at']
    ordering = ['-occurred_at']
    
    def get_serializer_class(self):
        """Use lightweight serializer for list"""
        if self.action == 'list':
            return AnalyticsEventListSerializer
        return AnalyticsEventSerializer


# ============================================================================
# AGGREGATED DATA
# ============================================================================

class LinkDailyStatViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Link Daily Statistics (READ-ONLY)
    
    Filters:
    - link: Filter by link
    - date__gte: Stats after date
    - date__lte: Stats before date
    
    Actions:
    - aggregate_all: Trigger aggregation for all links
    """
    
    queryset = LinkDailyStat.objects.select_related('link', 'link__campaign').all()
    serializer_class = LinkDailyStatSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {
        'link': ['exact'],
        'date': ['exact', 'gte', 'lte'],
    }
    ordering_fields = ['date', 'total_clicks', 'unique_visitors', 'conversions']
    ordering = ['-date']
    
    @action(detail=False, methods=['post'])
    def aggregate_all(self, request):
        """Trigger aggregation for all links"""
        target_date = request.data.get('date')
        if target_date:
            target_date = date.fromisoformat(target_date)
        else:
            target_date = timezone.now().date() - timedelta(days=1)
        
        service = LinkStatsAggregationService()
        results = service.aggregate_link_stats(target_date=target_date)
        
        return Response({
            'success': True,
            'date': str(target_date),
            'results': results,
        })


class ContentSnapshotViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Content Snapshots
    
    Filters:
    - content: Filter by content
    - captured_at__gte: Snapshots after date
    - captured_at__lte: Snapshots before date
    
    Actions:
    - create_from_events: Create snapshots from events
    """
    
    queryset = ContentSnapshot.objects.select_related('content', 'content__platform').all()
    serializer_class = ContentSnapshotSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {
        'content': ['exact'],
        'captured_at': ['exact', 'gte', 'lte', 'date'],
    }
    ordering_fields = ['captured_at', 'likes_count', 'views_count']
    ordering = ['-captured_at']
    
    @action(detail=False, methods=['post'])
    def create_from_events(self, request):
        """Create snapshots from aggregated events"""
        target_date = request.data.get('date')
        if target_date:
            target_date = date.fromisoformat(target_date)
        else:
            target_date = timezone.now().date() - timedelta(days=1)
        
        service = ContentSnapshotService()
        results = service.create_snapshots_from_events(target_date=target_date)
        
        return Response({
            'success': True,
            'date': str(target_date),
            'results': results,
        })


# ============================================================================
# INGESTION ENDPOINTS (from previous implementation)
# ============================================================================

class AnalyticsIngestionViewSet(viewsets.ViewSet):
    """
    API endpoints for analytics event ingestion.
    
    Endpoints:
    - POST /api/analytics/ingest/ - Ingest single event
    - POST /api/analytics/ingest/batch/ - Ingest multiple events
    """
    
    permission_classes = [IsAuthenticated]
    
    def create(self, request):
        """Ingest a single analytics event"""
        serializer = EventIngestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = AnalyticsIngestionService()
        
        try:
            event, created = service.ingest_event(**serializer.validated_data)
            
            return Response({
                'success': True,
                'event_id': str(event.id),
                'created': created,
                'message': 'Event ingested' if created else 'Event deduplicated',
            }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def batch(self, request):
        """Ingest multiple events in batch"""
        events = request.data.get('events', [])
        skip_errors = request.data.get('skip_errors', False)
        
        # Validate all events
        errors = []
        validated_events = []
        
        for idx, event_data in enumerate(events):
            serializer = EventIngestionSerializer(data=event_data)
            if serializer.is_valid():
                validated_events.append(serializer.validated_data)
            else:
                errors.append({
                    'index': idx,
                    'errors': serializer.errors,
                })
        
        if errors and not skip_errors:
            return Response({
                'success': False,
                'validation_errors': errors,
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Ingest validated events
        service = AnalyticsIngestionService()
        
        try:
            results = service.ingest_batch(
                events=validated_events,
                skip_errors=skip_errors,
            )
            
            return Response({
                'success': True,
                'total': results['total'],
                'created': results['created'],
                'deduplicated': results['deduplicated'],
                'errors': results['errors'],
                'validation_errors': errors,
            }, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
            }, status=status.HTTP_400_BAD_REQUEST)