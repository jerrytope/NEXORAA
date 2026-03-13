import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'NEXORAA.settings')

app = Celery('NEXORAA')

# Load config from Django settings (CELERY_ prefix)
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Configure Beat Schedule
app.conf.beat_schedule = {
    # Rollup campaign budgets every hour
    'rollup-budgets-hourly': {
        'task': 'analytics.rollup_campaign_budgets',
        'schedule': crontab(minute=0),  # Every hour at :00
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

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')