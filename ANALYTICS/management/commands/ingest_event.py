# ANALYTICS/management/commands/ingest_events.py
"""
Management command to ingest analytics events from file or stdin.

Usage:
    python manage.py ingest_events --file events.json
    python manage.py ingest_events --stdin < events.json
    python manage.py ingest_events --example  # Show example payload
"""

import json
import sys
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ANALYTICS.services.ingestion import AnalyticsIngestionService


class Command(BaseCommand):
    help = 'Ingest analytics events from JSON file or stdin'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            help='Path to JSON file containing events',
        )
        parser.add_argument(
            '--stdin',
            action='store_true',
            help='Read events from stdin',
        )
        parser.add_argument(
            '--skip-errors',
            action='store_true',
            help='Continue on errors (default: stop on first error)',
        )
        parser.add_argument(
            '--example',
            action='store_true',
            help='Show example event payload and exit',
        )
    
    def handle(self, *args, **options):
        if options['example']:
            self._show_example()
            return
        
        # Read events
        if options['file']:
            events = self._read_from_file(options['file'])
        elif options['stdin']:
            events = self._read_from_stdin()
        else:
            raise CommandError('Must specify --file or --stdin')
        
        # Ingest
        self.stdout.write(f"Ingesting {len(events)} events...")
        
        service = AnalyticsIngestionService()
        results = service.ingest_batch(
            events,
            skip_errors=options['skip_errors'],
        )
        
        # Report results
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Ingestion complete:\n"
                f"  Total: {results['total']}\n"
                f"  Created: {results['created']}\n"
                f"  Deduplicated: {results['deduplicated']}\n"
                f"  Errors: {len(results['errors'])}"
            )
        )
        
        if results['errors']:
            self.stdout.write(
                self.style.WARNING(f"\nErrors ({len(results['errors'])}):")
            )
            for error in results['errors'][:10]:  # Show first 10
                self.stdout.write(
                    f"  Index {error['index']}: {error['error']}"
                )
    
    def _read_from_file(self, filepath):
        """Read events from JSON file"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            if isinstance(data, dict) and 'events' in data:
                return data['events']
            elif isinstance(data, list):
                return data
            else:
                raise CommandError('JSON must be list of events or {"events": [...]}')\
        
        except FileNotFoundError:
            raise CommandError(f'File not found: {filepath}')
        except json.JSONDecodeError as e:
            raise CommandError(f'Invalid JSON: {str(e)}')
    
    def _read_from_stdin(self):
        """Read events from stdin"""
        try:
            data = json.load(sys.stdin)
            
            if isinstance(data, dict) and 'events' in data:
                return data['events']
            elif isinstance(data, list):
                return data
            else:
                raise CommandError('JSON must be list of events or {"events": [...]}')
        
        except json.JSONDecodeError as e:
            raise CommandError(f'Invalid JSON from stdin: {str(e)}')
    
    def _show_example(self):
        """Show example event payload"""
        example = {
            "events": [
                {
                    "event_type": "click",
                    "occurred_at": "2024-02-05T10:30:00Z",
                    "link_id": "abc-123-def-456",
                    "visitor_id": "visitor-xyz-789",
                    "session_id": "session-abc-123",
                    "meta": {
                        "user_agent": "Mozilla/5.0...",
                        "ip": "203.0.113.42",
                        "referrer": "https://instagram.com",
                        "country": "US",
                        "device_type": "mobile"
                    }
                },
                {
                    "event_type": "purchase",
                    "occurred_at": "2024-02-05T10:35:00Z",
                    "campaign_id": "campaign-uuid",
                    "visitor_id": "visitor-xyz-789",
                    "conversion_value": "99.99",
                    "conversion_attributed_to_link_id": "abc-123-def-456",
                    "metrics": {
                        "order_id": "ORD-12345",
                        "items_count": 3,
                        "currency": "USD"
                    }
                },
                {
                    "event_type": "like",
                    "occurred_at": "2024-02-05T11:00:00Z",
                    "platform_id": "platform-instagram-uuid",
                    "external_id": "instagram_post_123456",
                    "visitor_id": "ig_user_789012",
                    "external_event_id": "ig_like_event_abc123"
                }
            ]
        }
        
        self.stdout.write(
            self.style.SUCCESS("Example event payload:\n")
        )
        self.stdout.write(
            json.dumps(example, indent=2)
        )