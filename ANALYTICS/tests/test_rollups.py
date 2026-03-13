# ANALYTICS/tests/test_rollups.py
"""
Tests for Analytics Rollup Services

Tests:
- Budget rollup accuracy
- Link stats aggregation
- Content snapshot creation
- Idempotency (re-running doesn't duplicate)
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone

from ANALYTICS.models import (
    Campaign,
    CampaignExpense,
    TrackingLink,
    LinkDailyStat,
    Content,
    ContentSnapshot,
    AnalyticsEvent,
    Platform,
    Brand,
    Creator,
)
from ANALYTICS.services.rollups import (
    BudgetRollupService,
    LinkStatsAggregationService,
    ContentSnapshotService,
)


@pytest.fixture
def setup_campaign(db):
    """Create test campaign with expenses"""
    brand = Brand.objects.create(name='Test Brand')
    campaign = Campaign.objects.create(
        name='Test Campaign',
        brand=brand,
        budget_total=Decimal('10000.00'),
        budget_spent=Decimal('0.00'),
    )
    
    # Add expenses
    CampaignExpense.objects.create(
        campaign=campaign,
        expense_type='creator_fee',
        amount=Decimal('1000.00'),
        expense_date=date.today(),
        is_approved=True,
    )
    CampaignExpense.objects.create(
        campaign=campaign,
        expense_type='ad_spend',
        amount=Decimal('500.00'),
        expense_date=date.today(),
        is_approved=True,
    )
    CampaignExpense.objects.create(
        campaign=campaign,
        expense_type='production',
        amount=Decimal('250.00'),
        expense_date=date.today(),
        is_approved=False,  # Unapproved
    )
    
    return campaign


@pytest.fixture
def setup_link_with_events(db):
    """Create link with analytics events"""
    platform = Platform.objects.create(name='Instagram')
    brand = Brand.objects.create(name='Test Brand')
    creator = Creator.objects.create(name='Test Creator')
    campaign = Campaign.objects.create(name='Test Campaign', brand=brand)
    
    link = TrackingLink.objects.create(
        short_code='test123',
        destination_url='https://example.com',
        campaign=campaign,
        creator=creator,
    )
    
    target_date = date.today() - timedelta(days=1)
    
    # Create click events
    for i in range(10):
        AnalyticsEvent.objects.create(
            event_type='click',
            occurred_at=timezone.datetime.combine(
                target_date,
                timezone.datetime.min.time()
            ).replace(tzinfo=timezone.get_current_timezone()) + timedelta(hours=i),
            link=link,
            campaign=campaign,
            visitor_id=f'visitor_{i}',  # 10 unique visitors
            session_id=f'session_{i}',
        )
    
    # Create duplicate clicks (same visitor)
    for i in range(5):
        AnalyticsEvent.objects.create(
            event_type='click',
            occurred_at=timezone.datetime.combine(
                target_date,
                timezone.datetime.min.time()
            ).replace(tzinfo=timezone.get_current_timezone()) + timedelta(hours=i, minutes=30),
            link=link,
            campaign=campaign,
            visitor_id=f'visitor_{i}',  # Duplicate visitors
            session_id=f'session_{i}_2',  # New session
        )
    
    # Create conversion events
    for i in range(3):
        AnalyticsEvent.objects.create(
            event_type='purchase',
            occurred_at=timezone.datetime.combine(
                target_date,
                timezone.datetime.min.time()
            ).replace(tzinfo=timezone.get_current_timezone()) + timedelta(hours=i + 1),
            campaign=campaign,
            visitor_id=f'visitor_{i}',
            conversion_value=Decimal('99.99'),
            conversion_attributed_to_link=link,
        )
    
    return {
        'link': link,
        'campaign': campaign,
        'target_date': target_date,
    }


@pytest.fixture
def setup_content_with_events(db):
    """Create content with analytics events"""
    platform = Platform.objects.create(name='Instagram')
    brand = Brand.objects.create(name='Test Brand')
    creator = Creator.objects.create(name='Test Creator')
    campaign = Campaign.objects.create(name='Test Campaign', brand=brand)
    
    content = Content.objects.create(
        title='Test Post',
        platform=platform,
        creator=creator,
        campaign=campaign,
    )
    
    target_date = date.today() - timedelta(days=1)
    
    # Create engagement events
    event_counts = {
        'like': 100,
        'comment': 20,
        'share': 10,
        'page_view': 500,
    }
    
    for event_type, count in event_counts.items():
        for i in range(count):
            AnalyticsEvent.objects.create(
                event_type=event_type,
                occurred_at=timezone.datetime.combine(
                    target_date,
                    timezone.datetime.min.time()
                ).replace(tzinfo=timezone.get_current_timezone()) + timedelta(minutes=i),
                content=content,
                campaign=campaign,
            )
    
    return {
        'content': content,
        'target_date': target_date,
        'expected_counts': event_counts,
    }


class TestBudgetRollup:
    """Test campaign budget rollup"""
    
    def test_rollup_approved_expenses(self, setup_campaign):
        """Should sum only approved expenses"""
        service = BudgetRollupService()
        
        results = service.rollup_campaign_spend(
            campaign_id=str(setup_campaign.id),
            include_unapproved=False,
        )
        
        assert results['campaigns_updated'] == 1
        assert results['total_spend_calculated'] == Decimal('1500.00')
        
        # Check campaign updated
        setup_campaign.refresh_from_db()
        assert setup_campaign.budget_spent == Decimal('1500.00')
    
    def test_rollup_all_expenses(self, setup_campaign):
        """Should sum all expenses when include_unapproved=True"""
        service = BudgetRollupService()
        
        results = service.rollup_campaign_spend(
            campaign_id=str(setup_campaign.id),
            include_unapproved=True,
        )
        
        assert results['total_spend_calculated'] == Decimal('1750.00')
        
        setup_campaign.refresh_from_db()
        assert setup_campaign.budget_spent == Decimal('1750.00')
    
    def test_check_overspend(self, setup_campaign):
        """Should detect campaigns over budget"""
        # Set budget lower than spend
        setup_campaign.budget_total = Decimal('1000.00')
        setup_campaign.budget_spent = Decimal('1500.00')
        setup_campaign.save()
        
        service = BudgetRollupService()
        overspent = service.check_budget_overspend()
        
        assert len(overspent) == 1
        assert overspent[0]['id'] == str(setup_campaign.id)
        assert Decimal(overspent[0]['overspend']) == Decimal('500.00')
    
    def test_rollup_idempotent(self, setup_campaign):
        """Should be idempotent - running twice gives same result"""
        service = BudgetRollupService()
        
        # First run
        results1 = service.rollup_campaign_spend(
            campaign_id=str(setup_campaign.id)
        )
        
        # Second run
        results2 = service.rollup_campaign_spend(
            campaign_id=str(setup_campaign.id)
        )
        
        assert results1['total_spend_calculated'] == results2['total_spend_calculated']
        
        setup_campaign.refresh_from_db()
        assert setup_campaign.budget_spent == Decimal('1500.00')


class TestLinkStatsAggregation:
    """Test link daily stats aggregation"""
    
    def test_aggregate_clicks(self, setup_link_with_events):
        """Should accurately count total and unique clicks"""
        service = LinkStatsAggregationService()
        
        results = service.aggregate_link_stats(
            target_date=setup_link_with_events['target_date'],
            link_id=str(setup_link_with_events['link'].id),
        )
        
        assert results['links_processed'] == 1
        assert results['stats_created'] == 1
        
        # Check created stat
        stat = LinkDailyStat.objects.get(
            link=setup_link_with_events['link'],
            date=setup_link_with_events['target_date'],
        )
        
        assert stat.total_clicks == 15  # 10 unique + 5 duplicates
        assert stat.unique_visitors == 10  # Only 10 unique visitor_ids
        assert stat.unique_sessions == 15  # 15 unique session_ids
    
    def test_aggregate_conversions(self, setup_link_with_events):
        """Should accurately count conversions and revenue"""
        service = LinkStatsAggregationService()
        
        results = service.aggregate_link_stats(
            target_date=setup_link_with_events['target_date'],
            link_id=str(setup_link_with_events['link'].id),
        )
        
        stat = LinkDailyStat.objects.get(
            link=setup_link_with_events['link'],
            date=setup_link_with_events['target_date'],
        )
        
        assert stat.conversions == 3
        assert stat.revenue == Decimal('299.97')  # 3 * 99.99
        assert stat.conversion_rate == (3 / 10) * 100  # 3 conversions / 10 unique visitors
    
    def test_aggregate_idempotent(self, setup_link_with_events):
        """Should be idempotent - rerunning updates existing stat"""
        service = LinkStatsAggregationService()
        
        # First run
        results1 = service.aggregate_link_stats(
            target_date=setup_link_with_events['target_date'],
            link_id=str(setup_link_with_events['link'].id),
        )
        
        assert results1['stats_created'] == 1
        
        # Second run (should update, not create)
        results2 = service.aggregate_link_stats(
            target_date=setup_link_with_events['target_date'],
            link_id=str(setup_link_with_events['link'].id),
        )
        
        assert results2['stats_created'] == 0
        assert results2['stats_updated'] == 1
        
        # Should only be one stat record
        assert LinkDailyStat.objects.filter(
            link=setup_link_with_events['link'],
            date=setup_link_with_events['target_date'],
        ).count() == 1


class TestContentSnapshots:
    """Test content snapshot creation"""
    
    def test_create_snapshot_with_deltas(self):
        """Should calculate deltas from last snapshot"""
        platform = Platform.objects.create(name='Instagram')
        brand = Brand.objects.create(name='Test Brand')
        creator = Creator.objects.create(name='Test Creator')
        campaign = Campaign.objects.create(name='Test Campaign', brand=brand)
        
        content = Content.objects.create(
            title='Test Post',
            platform=platform,
            creator=creator,
            campaign=campaign,
        )
        
        service = ContentSnapshotService()
        
        # First snapshot
        snapshot1 = service.create_snapshot(
            content_id=str(content.id),
            captured_at=timezone.now() - timedelta(hours=24),
            likes_count=100,
            comments_count=20,
            shares_count=10,
            views_count=1000,
        )
        
        assert snapshot1.likes_delta == 0  # No previous snapshot
        assert snapshot1.comments_delta == 0
        
        # Second snapshot (24 hours later)
        snapshot2 = service.create_snapshot(
            content_id=str(content.id),
            captured_at=timezone.now(),
            likes_count=150,  # +50
            comments_count=25,  # +5
            shares_count=15,  # +5
            views_count=1500,  # +500
        )
        
        assert snapshot2.likes_delta == 50
        assert snapshot2.comments_delta == 5
        assert snapshot2.shares_delta == 5
        assert snapshot2.views_delta == 500
    
    def test_create_from_events(self, setup_content_with_events):
        """Should aggregate events into snapshot"""
        service = ContentSnapshotService()
        
        results = service.create_snapshots_from_events(
            target_date=setup_content_with_events['target_date']
        )
        
        assert results['content_processed'] == 1
        assert results['snapshots_created'] == 1
        
        # Check snapshot values
        snapshot = ContentSnapshot.objects.get(
            content=setup_content_with_events['content'],
        )
        
        expected = setup_content_with_events['expected_counts']
        assert snapshot.likes_count == expected['like']
        assert snapshot.comments_count == expected['comment']
        assert snapshot.shares_count == expected['share']
        assert snapshot.views_count == expected['page_view']
    
    def test_snapshot_uniqueness(self, setup_content_with_events):
        """Should enforce unique (content, captured_at)"""
        from django.db import IntegrityError
        
        service = ContentSnapshotService()
        captured_at = timezone.now()
        
        # First snapshot
        snapshot1 = service.create_snapshot(
            content_id=str(setup_content_with_events['content'].id),
            captured_at=captured_at,
            likes_count=100,
        )
        
        # Duplicate (same content + captured_at)
        with pytest.raises(IntegrityError):
            snapshot2 = service.create_snapshot(
                content_id=str(setup_content_with_events['content'].id),
                captured_at=captured_at,
                likes_count=200,
            )


