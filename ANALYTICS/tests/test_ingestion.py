# ANALYTICS/tests/test_ingestion.py
"""
Tests for Analytics Ingestion Service

Tests:
- Event validation
- Entity linking precedence
- Deduplication strategies
- Visitor/session tracking
- Batch ingestion
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError

from ANALYTICS.models import (
    AnalyticsEvent,
    Platform,
    Brand,
    Campaign,
    Creator,
    Content,
    TrackingLink,
)
from ANALYTICS.services.ingestion import (
    AnalyticsIngestionService,
    IngestionError,
)


@pytest.fixture
def setup_entities(db):
    """Create test entities for linking"""
    platform = Platform.objects.create(name='Instagram', slug='instagram')
    brand = Brand.objects.create(name='Test Brand')
    creator = Creator.objects.create(name='Test Creator')
    campaign = Campaign.objects.create(
        name='Test Campaign',
        brand=brand,
        budget_total=Decimal('10000.00')
    )
    content = Content.objects.create(
        title='Test Post',
        platform=platform,
        creator=creator,
        campaign=campaign,
        external_id='ig_post_123'
    )
    link = TrackingLink.objects.create(
        short_code='test123',
        destination_url='https://example.com',
        campaign=campaign,
        creator=creator,
        content=content
    )
    
    return {
        'platform': platform,
        'brand': brand,
        'creator': creator,
        'campaign': campaign,
        'content': content,
        'link': link,
    }


class TestEventValidation:
    """Test event validation rules"""
    
    def test_invalid_event_type(self):
        """Should reject invalid event types"""
        service = AnalyticsIngestionService()
        
        with pytest.raises(ValidationError) as exc:
            service.ingest_event(
                event_type='invalid_type',
                occurred_at=timezone.now(),
                link_id='test',
            )
        
        assert 'Invalid event_type' in str(exc.value)
    
    def test_missing_occurred_at(self):
        """Should reject events without occurred_at"""
        service = AnalyticsIngestionService()
        
        with pytest.raises(ValidationError) as exc:
            service.ingest_event(
                event_type='click',
                occurred_at=None,
                link_id='test',
            )
        
        assert 'occurred_at is required' in str(exc.value)
    
    def test_missing_identifiers(self):
        """Should reject events without any identifier"""
        service = AnalyticsIngestionService()
        
        with pytest.raises(ValidationError) as exc:
            service.ingest_event(
                event_type='click',
                occurred_at=timezone.now(),
            )
        
        assert 'At least one identifier required' in str(exc.value)
    
    def test_valid_event_with_link_id(self, setup_entities):
        """Should accept valid event with link_id"""
        service = AnalyticsIngestionService()
        
        event, created = service.ingest_event(
            event_type='click',
            occurred_at=timezone.now(),
            link_id=str(setup_entities['link'].id),
        )
        
        assert created is True
        assert event.event_type == 'click'
        assert event.link_id == setup_entities['link'].id


class TestEntityLinking:
    """Test entity linking precedence rules"""
    
    def test_link_precedence(self, setup_entities):
        """Rule 1: Link should derive campaign/creator/content"""
        service = AnalyticsIngestionService()
        
        event, created = service.ingest_event(
            event_type='click',
            occurred_at=timezone.now(),
            link_id=str(setup_entities['link'].id),
        )
        
        # Should link to all entities from TrackingLink
        assert event.link_id == setup_entities['link'].id
        assert event.campaign_id == setup_entities['campaign'].id
        assert event.creator_id == setup_entities['creator'].id
        assert event.content_id == setup_entities['content'].id
        assert event.platform_id == setup_entities['platform'].id
        assert event.brand_id == setup_entities['brand'].id
        assert event.meta['_linking_source'] == 'link'
    
    def test_content_precedence(self, setup_entities):
        """Rule 2: Content should derive campaign/creator/platform"""
        service = AnalyticsIngestionService()
        
        event, created = service.ingest_event(
            event_type='like',
            occurred_at=timezone.now(),
            content_id=str(setup_entities['content'].id),
        )
        
        # Should link to entities from Content
        assert event.content_id == setup_entities['content'].id
        assert event.campaign_id == setup_entities['campaign'].id
        assert event.creator_id == setup_entities['creator'].id
        assert event.platform_id == setup_entities['platform'].id
        assert event.meta['_linking_source'] == 'content'
    
    def test_platform_external_id_precedence(self, setup_entities):
        """Rule 3: Platform + external_id should resolve to Content"""
        service = AnalyticsIngestionService()
        
        event, created = service.ingest_event(
            event_type='share',
            occurred_at=timezone.now(),
            platform_id=str(setup_entities['platform'].id),
            external_id='ig_post_123',
        )
        
        # Should resolve to Content and derive entities
        assert event.content_id == setup_entities['content'].id
        assert event.campaign_id == setup_entities['campaign'].id
        assert event.meta['_linking_source'] == 'platform_external_id'
    
    def test_override_precedence(self, setup_entities):
        """Rule 4: Should use provided overrides when no linking possible"""
        service = AnalyticsIngestionService()
        
        event, created = service.ingest_event(
            event_type='impression',
            occurred_at=timezone.now(),
            campaign_id=str(setup_entities['campaign'].id),
            platform_id=str(setup_entities['platform'].id),
            external_id='unknown_post',  # Does not exist
        )
        
        # Should use override
        assert event.campaign_id == setup_entities['campaign'].id
        assert event.platform_id == setup_entities['platform'].id
        assert event.meta['_linking_source'] == 'override'


class TestDeduplication:
    """Test deduplication strategies"""
    
    def test_dedupe_by_external_event_id(self, setup_entities):
        """Should dedupe by external_event_id"""
        service = AnalyticsIngestionService()
        
        # First event
        event1, created1 = service.ingest_event(
            event_type='click',
            occurred_at=timezone.now(),
            link_id=str(setup_entities['link'].id),
            external_event_id='ext_event_123',
        )
        
        assert created1 is True
        
        # Duplicate event (same external_event_id)
        event2, created2 = service.ingest_event(
            event_type='click',
            occurred_at=timezone.now(),
            link_id=str(setup_entities['link'].id),
            external_event_id='ext_event_123',
        )
        
        assert created2 is False
        assert event2.id == event1.id
    
    def test_dedupe_by_hash(self, setup_entities):
        """Should dedupe by dedupe_hash"""
        service = AnalyticsIngestionService()
        occurred_at = timezone.now()
        
        # First event
        event1, created1 = service.ingest_event(
            event_type='click',
            occurred_at=occurred_at,
            link_id=str(setup_entities['link'].id),
            external_event_id='ext_event_456',
        )
        
        assert created1 is True
        
        # Duplicate (same hash)
        event2, created2 = service.ingest_event(
            event_type='click',
            occurred_at=occurred_at,
            link_id=str(setup_entities['link'].id),
            external_event_id='ext_event_456',
        )
        
        assert created2 is False
        assert event2.id == event1.id
    
    def test_dedupe_fuzzy_match(self, setup_entities):
        """Should dedupe by fuzzy match (link + visitor + time window)"""
        service = AnalyticsIngestionService()
        occurred_at = timezone.now()
        
        # First event
        event1, created1 = service.ingest_event(
            event_type='click',
            occurred_at=occurred_at,
            link_id=str(setup_entities['link'].id),
            visitor_id='visitor_xyz',
        )
        
        assert created1 is True
        
        # Duplicate (within 1 minute window)
        event2, created2 = service.ingest_event(
            event_type='click',
            occurred_at=occurred_at + timedelta(seconds=30),
            link_id=str(setup_entities['link'].id),
            visitor_id='visitor_xyz',
        )
        
        assert created2 is False
        assert event2.id == event1.id
    
    def test_no_dedupe_different_visitor(self, setup_entities):
        """Should NOT dedupe if visitor_id differs"""
        service = AnalyticsIngestionService()
        occurred_at = timezone.now()
        
        # First event
        event1, created1 = service.ingest_event(
            event_type='click',
            occurred_at=occurred_at,
            link_id=str(setup_entities['link'].id),
            visitor_id='visitor_1',
        )
        
        # Different visitor
        event2, created2 = service.ingest_event(
            event_type='click',
            occurred_at=occurred_at,
            link_id=str(setup_entities['link'].id),
            visitor_id='visitor_2',
        )
        
        assert created1 is True
        assert created2 is True
        assert event2.id != event1.id


class TestBatchIngestion:
    """Test batch ingestion"""
    
    def test_batch_success(self, setup_entities):
        """Should ingest batch of events successfully"""
        service = AnalyticsIngestionService()
        
        events = [
            {
                'event_type': 'click',
                'occurred_at': timezone.now(),
                'link_id': str(setup_entities['link'].id),
                'visitor_id': f'visitor_{i}',
            }
            for i in range(10)
        ]
        
        results = service.ingest_batch(events)
        
        assert results['total'] == 10
        assert results['created'] == 10
        assert results['deduplicated'] == 0
        assert len(results['errors']) == 0
    
    def test_batch_with_errors_skip(self, setup_entities):
        """Should skip errors when skip_errors=True"""
        service = AnalyticsIngestionService()
        
        events = [
            # Valid event
            {
                'event_type': 'click',
                'occurred_at': timezone.now(),
                'link_id': str(setup_entities['link'].id),
            },
            # Invalid event (no identifiers)
            {
                'event_type': 'click',
                'occurred_at': timezone.now(),
            },
            # Valid event
            {
                'event_type': 'like',
                'occurred_at': timezone.now(),
                'content_id': str(setup_entities['content'].id),
            },
        ]
        
        results = service.ingest_batch(events, skip_errors=True)
        
        assert results['total'] == 3
        assert results['created'] == 2
        assert len(results['errors']) == 1
    
    def test_batch_deduplication(self, setup_entities):
        """Should dedupe within batch"""
        service = AnalyticsIngestionService()
        occurred_at = timezone.now()
        
        events = [
            {
                'event_type': 'click',
                'occurred_at': occurred_at,
                'link_id': str(setup_entities['link'].id),
                'external_event_id': 'duplicate_event',
            },
            {
                'event_type': 'click',
                'occurred_at': occurred_at,
                'link_id': str(setup_entities['link'].id),
                'external_event_id': 'duplicate_event',  # Duplicate
            },
        ]
        
        results = service.ingest_batch(events)
        
        assert results['total'] == 2
        assert results['created'] == 1
        assert results['deduplicated'] == 1


class TestVisitorTracking:
    """Test visitor and session tracking"""
    
    def test_visitor_tracking(self, setup_entities):
        """Should store visitor_id and session_id"""
        service = AnalyticsIngestionService()
        
        event, created = service.ingest_event(
            event_type='click',
            occurred_at=timezone.now(),
            link_id=str(setup_entities['link'].id),
            visitor_id='visitor_abc123',
            session_id='session_xyz789',
        )
        
        assert event.visitor_id == 'visitor_abc123'
        assert event.session_id == 'session_xyz789'
    
    def test_authenticated_user_tracking(self, setup_entities, django_user_model):
        """Should link to authenticated user"""
        user = django_user_model.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        service = AnalyticsIngestionService()
        
        event, created = service.ingest_event(
            event_type='purchase',
            occurred_at=timezone.now(),
            campaign_id=str(setup_entities['campaign'].id),
            user_id=user.id,
            visitor_id=f'user_{user.id}',
        )
        
        assert event.user_id == user.id
        assert event.visitor_id == f'user_{user.id}'


class TestConversionTracking:
    """Test conversion attribution"""
    
    def test_conversion_attribution(self, setup_entities):
        """Should track conversion value and attribution"""
        service = AnalyticsIngestionService()
        
        event, created = service.ingest_event(
            event_type='purchase',
            occurred_at=timezone.now(),
            campaign_id=str(setup_entities['campaign'].id),
            visitor_id='visitor_123',
            conversion_value=Decimal('99.99'),
            conversion_attributed_to_link_id=str(setup_entities['link'].id),
        )
        
        assert event.conversion_value == Decimal('99.99')
        assert event.conversion_attributed_to_link_id == setup_entities['link'].id


# Run tests:
# pytest ANALYTICS/tests/test_ingestion.py -v