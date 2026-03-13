# ANALYTICS/tasks.py
"""
Celery tasks for analytics data processing.

Scheduled tasks:
- Daily: Aggregate link stats, create content snapshots
- Hourly: Rollup campaign budgets
- On-demand: Backfill, reprocess
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import date, timedelta
from django.utils import timezone

from ANALYTICS.services.ingestion import AnalyticsIngestionService
from ANALYTICS.services.rollups import (
    BudgetRollupService,
    LinkStatsAggregationService,
    ContentSnapshotService,
)

logger = get_task_logger(__name__)


# ============================================================================
# SCHEDULED TASKS
# ============================================================================

@shared_task(name='analytics.rollup_campaign_budgets')
def rollup_campaign_budgets_task(
    campaign_id=None,
    include_unapproved=False,
):
    """
    Rollup campaign budgets from expenses.
    
    Schedule: Hourly or on-demand
    
    Args:
        campaign_id: Specific campaign to update (None = all)
        include_unapproved: Include unapproved expenses
    
    Returns:
        Dict with rollup results
    """
    logger.info("Starting campaign budget rollup...")
    
    service = BudgetRollupService()
    results = service.rollup_campaign_spend(
        campaign_id=campaign_id,
        include_unapproved=include_unapproved,
    )
    
    logger.info(
        f"Budget rollup complete: {results['campaigns_updated']} campaigns updated, "
        f"${results['total_spend_calculated']} total spend"
    )
    
    # Check for overspend
    overspent = service.check_budget_overspend()
    if overspent:
        logger.warning(f"Found {len(overspent)} campaigns over budget!")
        # TODO: Send alerts via email/Slack
    
    return {
        'success': True,
        'campaigns_updated': results['campaigns_updated'],
        'total_spend': str(results['total_spend_calculated']),
        'overspent_campaigns': len(overspent),
    }


@shared_task(name='analytics.aggregate_link_stats_daily')
def aggregate_link_stats_daily_task(
    target_date=None,
    link_id=None,
):
    """
    Aggregate link statistics for yesterday (or specific date).
    
    Schedule: Daily at 1:00 AM
    
    Args:
        target_date: Date to aggregate (default: yesterday)
        link_id: Specific link (None = all active links)
    
    Returns:
        Dict with aggregation results
    """
    if target_date is None:
        target_date = (timezone.now() - timedelta(days=1)).date()
    elif isinstance(target_date, str):
        target_date = date.fromisoformat(target_date)
    
    logger.info(f"Starting link stats aggregation for {target_date}...")
    
    service = LinkStatsAggregationService()
    results = service.aggregate_link_stats(
        target_date=target_date,
        link_id=link_id,
    )
    
    logger.info(
        f"Link stats aggregation complete: {results['links_processed']} links processed, "
        f"{results['stats_created']} created, {results['stats_updated']} updated"
    )
    
    return {
        'success': True,
        'date': str(target_date),
        'links_processed': results['links_processed'],
        'stats_created': results['stats_created'],
        'stats_updated': results['stats_updated'],
    }


@shared_task(name='analytics.create_content_snapshots_daily')
def create_content_snapshots_daily_task(target_date=None):
    """
    Create content snapshots from events for yesterday.
    
    Schedule: Daily at 2:00 AM (after link stats aggregation)
    
    Args:
        target_date: Date to create snapshots (default: yesterday)
    
    Returns:
        Dict with snapshot creation results
    """
    if target_date is None:
        target_date = (timezone.now() - timedelta(days=1)).date()
    elif isinstance(target_date, str):
        target_date = date.fromisoformat(target_date)
    
    logger.info(f"Starting content snapshot creation for {target_date}...")
    
    service = ContentSnapshotService()
    results = service.create_snapshots_from_events(
        target_date=target_date
    )
    
    logger.info(
        f"Content snapshot creation complete: {results['snapshots_created']} snapshots created"
    )
    
    return {
        'success': True,
        'date': str(target_date),
        'content_processed': results['content_processed'],
        'snapshots_created': results['snapshots_created'],
        'errors': len(results['errors']),
    }


# ============================================================================
# BACKFILL TASKS
# ============================================================================

@shared_task(name='analytics.backfill_link_stats')
def backfill_link_stats_task(
    start_date,
    end_date=None,
    link_id=None,
):
    """
    Backfill link statistics for a date range.
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (default: yesterday)
        link_id: Specific link (None = all)
    
    Returns:
        Dict with backfill results
    """
    start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    end = date.fromisoformat(end_date) if end_date and isinstance(end_date, str) else (timezone.now() - timedelta(days=1)).date()
    
    logger.info(f"Starting link stats backfill from {start} to {end}...")
    
    service = LinkStatsAggregationService()
    
    current_date = start
    total_created = 0
    total_updated = 0
    
    while current_date <= end:
        results = service.aggregate_link_stats(
            target_date=current_date,
            link_id=link_id,
        )
        
        total_created += results['stats_created']
        total_updated += results['stats_updated']
        
        current_date += timedelta(days=1)
    
    logger.info(
        f"Backfill complete: {total_created} created, {total_updated} updated"
    )
    
    return {
        'success': True,
        'start_date': str(start),
        'end_date': str(end),
        'total_created': total_created,
        'total_updated': total_updated,
    }


# ============================================================================
# ON-DEMAND PROCESSING
# ============================================================================

@shared_task(name='analytics.ingest_events_batch')
def ingest_events_batch_task(events, skip_errors=False):
    """
    Ingest batch of events asynchronously.
    
    Args:
        events: List of event dicts
        skip_errors: Continue on errors
    
    Returns:
        Dict with ingestion results
    """
    logger.info(f"Starting batch ingestion of {len(events)} events...")
    
    service = AnalyticsIngestionService()
    results = service.ingest_batch(
        events=events,
        skip_errors=skip_errors,
    )
    
    logger.info(
        f"Batch ingestion complete: {results['created']} created, "
        f"{results['deduplicated']} deduplicated, {len(results['errors'])} errors"
    )
    
    return {
        'success': True,
        'total': results['total'],
        'created': results['created'],
        'deduplicated': results['deduplicated'],
        'errors': len(results['errors']),
    }


# ============================================================================
# CELERY BEAT SCHEDULE
# ============================================================================

"""
Add to your celery.py or settings.py:

from celery.schedules import crontab

app.conf.beat_schedule = {
    # Rollup campaign budgets every hour
    'rollup-budgets-hourly': {
        'task': 'analytics.rollup_campaign_budgets',
        'schedule': crontab(minute=0),  # Every hour
    },
    
    # Aggregate link stats daily at 1:00 AM
    'aggregate-link-stats-daily': {
        'task': 'analytics.aggregate_link_stats_daily',
        'schedule': crontab(hour=1, minute=0),  # 1:00 AM daily
    },
    
    # Create content snapshots daily at 2:00 AM
    'create-snapshots-daily': {
        'task': 'analytics.create_content_snapshots_daily',
        'schedule': crontab(hour=2, minute=0),  # 2:00 AM daily
    },
}
"""