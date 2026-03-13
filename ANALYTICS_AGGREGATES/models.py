import uuid
from django.db import models
from django.core.exceptions import ValidationError

from ANALYTICS.models import EventType


class AggregationBucket(models.TextChoices):
    """Time bucket choices for aggregation periods"""
    DAY = 'day', 'Day'
    WEEK = 'week', 'Week'
    MONTH = 'month', 'Month'


class AnalyticsAggregate(models.Model):
    """
    Pre-aggregated analytics metrics.

    One row represents a single aggregation bucket
    (day/week/month) for a specific event type
    and optional dimension combination.
    """

    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    
    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
        db_index=True,
        help_text="Type of analytics event (static choices for MVP)"
    )

    
    platform = models.ForeignKey(
        'ANALYTICS.Platform',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='analytics_aggregates',
        db_index=True,
        help_text="Platform dimension"
    )

    brand = models.ForeignKey(
        'ANALYTICS.Brand',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='analytics_aggregates',
        db_index=True,
        help_text="Brand dimension"
    )

    campaign = models.ForeignKey(
        'ANALYTICS.Campaign',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='analytics_aggregates',
        db_index=True,
        help_text="Campaign dimension"
    )

    creator = models.ForeignKey(
        'ANALYTICS.Creator',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='analytics_aggregates',
        db_index=True,
        help_text="Creator dimension"
    )

    content = models.ForeignKey(
        'ANALYTICS.Content',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='analytics_aggregates',
        db_index=True,
        help_text="Content dimension"
    )

    link = models.ForeignKey(
        'ANALYTICS.TrackingLink',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='analytics_aggregates',
        db_index=True,
        help_text="Tracking link dimension"
    )

    
    bucket = models.CharField(
        max_length=10,
        choices=AggregationBucket.choices,
        db_index=True,
        help_text="Aggregation time bucket (day/week/month)"
    )

    bucket_date = models.DateField(
        db_index=True,
        help_text="""Start date of the aggregation window.
        Rules:
        - DAY: exact day (e.g., 2025-01-26)
        - WEEK: Monday of that week (e.g., 2025-01-20)
        - MONTH: first day of the month (e.g., 2025-01-01)
        """
    )

    
    event_count = models.PositiveBigIntegerField(
        default=0,
        help_text="Total number of events in this bucket"
    )

    metrics_sum = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Aggregated numeric metrics.
        Example:
        {
          "impressions": 12000,
          "views": 4500,
          "clicks": 890,
          "revenue": 320.50
        }
        """
    )

    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_aggregates'
        verbose_name = 'Analytics Aggregate'
        verbose_name_plural = 'Analytics Aggregates'
        ordering = ['-bucket_date', 'event_type']

        
        constraints = [
            models.UniqueConstraint(
                fields=[
                    'event_type',
                    'platform',
                    'brand',
                    'campaign',
                    'creator',
                    'content',
                    'bucket',
                    'bucket_date',
                    'link',
                ],
                name='uniq_analytics_aggregate_bucket'
            )
        ]

        
        indexes = [
            
            models.Index(
                fields=['bucket', 'bucket_date'],
                name='idx_agg_bucket_date'
            ),
            models.Index(
                fields=['event_type', 'bucket', 'bucket_date'],
                name='idx_agg_event_bucket'
            ),
            
            models.Index(
                fields=['campaign', 'bucket_date'],
                name='idx_agg_campaign_date'
            ),
            models.Index(
                fields=['creator', 'bucket_date'],
                name='idx_agg_creator_date'
            ),
            models.Index(
                fields=['brand', 'bucket_date'],
                name='idx_agg_brand_date'
            ),
            models.Index(
                fields=['link', 'bucket_date'],
                name='idx_agg_link_date'
            )   
        ]

    def __str__(self):
        return (
            f"{self.get_event_type_display()} | "
            f"{self.get_bucket_display()} | {self.bucket_date}"
        )

    def clean(self):
        """Validate model data before saving"""
        if self.event_count < 0:
            raise ValidationError("event_count cannot be negative")
        
        
        if self.metrics_sum is None:
            self.metrics_sum = {}
        
    
        if self.metrics_sum:
            for key, value in self.metrics_sum.items():
                if not isinstance(value, (int, float)):
                    raise ValidationError(
                        f"Metric '{key}' must be numeric, got {type(value).__name__}"
                    )