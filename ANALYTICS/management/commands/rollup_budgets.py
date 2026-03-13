# ANALYTICS/management/commands/rollup_budgets.py
"""
Management command to rollup campaign budgets from expenses.

Usage:
    python manage.py rollup_budgets
    python manage.py rollup_budgets --campaign <campaign_id>
    python manage.py rollup_budgets --include-unapproved
    python manage.py rollup_budgets --check-overspend
"""

from django.core.management.base import BaseCommand
from ANALYTICS.services.rollups import BudgetRollupService


class Command(BaseCommand):
    help = 'Rollup campaign budgets from expenses'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--campaign',
            type=str,
            help='Specific campaign ID to update (default: all campaigns)',
        )
        parser.add_argument(
            '--include-unapproved',
            action='store_true',
            help='Include unapproved expenses in rollup',
        )
        parser.add_argument(
            '--check-overspend',
            action='store_true',
            help='Check for campaigns over budget',
        )
    
    def handle(self, *args, **options):
        service = BudgetRollupService()
        
        # Rollup budgets
        self.stdout.write("Rolling up campaign budgets...")
        
        results = service.rollup_campaign_spend(
            campaign_id=options.get('campaign'),
            include_unapproved=options['include_unapproved'],
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Budget rollup complete:\n"
                f"  Campaigns updated: {results['campaigns_updated']}\n"
                f"  Total spend calculated: ${results['total_spend_calculated']}"
            )
        )
        
        # Show campaign details
        if results['campaigns']:
            self.stdout.write("\nCampaign budgets:")
            for campaign in results['campaigns']:
                status = "✓" if campaign['budget_remaining'] and float(campaign['budget_remaining']) > 0 else "⚠"
                self.stdout.write(
                    f"  {status} {campaign['name']}: "
                    f"${campaign['budget_spent']} / ${campaign['budget_total'] or 'N/A'}"
                )
        
        # Check overspend
        if options['check_overspend']:
            self.stdout.write("\nChecking for budget overspend...")
            overspent = service.check_budget_overspend()
            
            if overspent:
                self.stdout.write(
                    self.style.WARNING(
                        f"\n⚠ Found {len(overspent)} campaigns over budget:"
                    )
                )
                for campaign in overspent:
                    self.stdout.write(
                        f"  • {campaign['name']}: "
                        f"${campaign['budget_spent']} / ${campaign['budget_total']} "
                        f"(over by ${campaign['overspend']})"
                    )
            else:
                self.stdout.write(
                    self.style.SUCCESS("\n✓ All campaigns within budget")
                )


# ============================================================================
# ANALYTICS/management/commands/aggregate_link_stats.py
# ============================================================================

"""
Management command to aggregate link daily statistics.

Usage:
    python manage.py aggregate_link_stats
    python manage.py aggregate_link_stats --date 2024-02-04
    python manage.py aggregate_link_stats --link <link_id>
    python manage.py aggregate_link_stats --last-n-days 7
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from ANALYTICS.services.rollups import LinkStatsAggregationService


class Command(BaseCommand):
    help = 'Aggregate link daily statistics from events'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Specific date to aggregate (YYYY-MM-DD, default: yesterday)',
        )
        parser.add_argument(
            '--link',
            type=str,
            help='Specific link ID to aggregate (default: all active links)',
        )
        parser.add_argument(
            '--last-n-days',
            type=int,
            help='Aggregate last N days',
        )
    
    def handle(self, *args, **options):
        service = LinkStatsAggregationService()
        
        # Determine dates to process
        if options.get('last_n_days'):
            dates = [
                (timezone.now() - timedelta(days=i)).date()
                for i in range(options['last_n_days'])
            ]
        elif options.get('date'):
            dates = [date.fromisoformat(options['date'])]
        else:
            dates = [(timezone.now() - timedelta(days=1)).date()]
        
        # Aggregate for each date
        total_stats_created = 0
        total_stats_updated = 0
        
        for target_date in dates:
            self.stdout.write(f"\nAggregating stats for {target_date}...")
            
            results = service.aggregate_link_stats(
                target_date=target_date,
                link_id=options.get('link'),
            )
            
            total_stats_created += results['stats_created']
            total_stats_updated += results['stats_updated']
            
            self.stdout.write(
                f"  Processed {results['links_processed']} links: "
                f"{results['stats_created']} created, {results['stats_updated']} updated"
            )
            
            # Show top links by clicks
            if results['links']:
                top_links = sorted(
                    results['links'],
                    key=lambda x: x['total_clicks'],
                    reverse=True
                )[:5]
                
                self.stdout.write("  Top links:")
                for link in top_links:
                    self.stdout.write(
                        f"    {link['short_code']}: {link['total_clicks']} clicks, "
                        f"{link['unique_visitors']} unique, {link['conversions']} conversions"
                    )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Aggregation complete:\n"
                f"  Dates processed: {len(dates)}\n"
                f"  Stats created: {total_stats_created}\n"
                f"  Stats updated: {total_stats_updated}"
            )
        )


# ============================================================================
# ANALYTICS/management/commands/create_content_snapshots.py
# ============================================================================

"""
Management command to create content snapshots.

Usage:
    python manage.py create_content_snapshots
    python manage.py create_content_snapshots --date 2024-02-04
    python manage.py create_content_snapshots --from-events
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date
from ANALYTICS.services.rollups import ContentSnapshotService


class Command(BaseCommand):
    help = 'Create content snapshots from events'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Specific date to create snapshots (YYYY-MM-DD, default: yesterday)',
        )
        parser.add_argument(
            '--from-events',
            action='store_true',
            help='Create snapshots from aggregated events',
        )
    
    def handle(self, *args, **options):
        service = ContentSnapshotService()
        
        # Parse date
        if options.get('date'):
            target_date = date.fromisoformat(options['date'])
        else:
            target_date = (timezone.now() - timedelta(days=1)).date()
        
        if options['from_events']:
            self.stdout.write(f"Creating snapshots from events for {target_date}...")
            
            results = service.create_snapshots_from_events(
                target_date=target_date
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Snapshot creation complete:\n"
                    f"  Content processed: {results['content_processed']}\n"
                    f"  Snapshots created: {results['snapshots_created']}\n"
                    f"  Errors: {len(results['errors'])}"
                )
            )
            
            if results['errors']:
                self.stdout.write(
                    self.style.WARNING("\nErrors:")
                )
                for error in results['errors'][:10]:
                    self.stdout.write(
                        f"  Content {error['content_id']}: {error['error']}"
                    )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Please specify --from-events or implement platform API integration"
                )
            )