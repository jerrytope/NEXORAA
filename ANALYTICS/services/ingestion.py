# ANALYTICS/services/ingestion.py
"""
Unified Analytics Ingestion Service

Handles ingestion of events from multiple sources with:
- Entity linking (campaign, creator, content, platform, link)
- Deduplication
- Visitor/session tracking
- Validation and error handling
"""

import hashlib
import logging
from datetime import datetime
from typing import Dict, Optional, Any, Tuple
from decimal import Decimal

from django.db import transaction
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
    EventType,
)

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Base exception for ingestion errors"""
    pass


class EntityLinkingError(IngestionError):
    """Raised when entity linking fails"""
    pass


class DeduplicationError(IngestionError):
    """Raised when deduplication fails"""
    pass


class AnalyticsIngestionService:
    """
    Central service for ingesting analytics events from any source.
    
    Supports:
    - Multiple event types (clicks, impressions, conversions, etc.)
    - Entity linking with precedence rules
    - Automatic deduplication
    - Visitor/session tracking
    """
    
    def __init__(self):
        self.logger = logger
    
    def ingest_event(
        self,
        event_type: str,
        occurred_at: datetime,
        
        # Identifiers (at least one required)
        link_id: Optional[str] = None,
        content_id: Optional[str] = None,
        platform_id: Optional[str] = None,
        external_id: Optional[str] = None,
        
        # Optional entity overrides
        campaign_id: Optional[str] = None,
        creator_id: Optional[str] = None,
        brand_id: Optional[str] = None,
        
        # Visitor tracking
        visitor_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
        
        # Conversion tracking
        conversion_value: Optional[Decimal] = None,
        conversion_attributed_to_link_id: Optional[str] = None,
        
        # Deduplication
        external_event_id: Optional[str] = None,
        
        # Flexible data
        metrics: Optional[Dict] = None,
        meta: Optional[Dict] = None,
        
        # Flags
        skip_deduplication: bool = False,
    ) -> Tuple[AnalyticsEvent, bool]:
        """
        Ingest a single analytics event.
        
        Returns:
            Tuple[AnalyticsEvent, bool]: (event, created)
            - event: The AnalyticsEvent instance
            - created: True if new event was created, False if deduplicated
        
        Raises:
            IngestionError: If ingestion fails
            ValidationError: If data validation fails
        """
        try:
            with transaction.atomic():
                # 1. Validate minimum requirements
                self._validate_event(event_type, occurred_at, link_id, content_id, platform_id, external_id)
                
                # 2. Check deduplication
                if not skip_deduplication:
                    existing_event = self._check_deduplication(
                        external_event_id=external_event_id,
                        event_type=event_type,
                        occurred_at=occurred_at,
                        link_id=link_id,
                        content_id=content_id,
                        visitor_id=visitor_id,
                    )
                    if existing_event:
                        self.logger.info(
                            f"Event deduplicated: {event_type} at {occurred_at} "
                            f"(matched existing event {existing_event.id})"
                        )
                        return existing_event, False
                
                # 3. Resolve entities using linking rules
                entities = self._resolve_entities(
                    link_id=link_id,
                    content_id=content_id,
                    platform_id=platform_id,
                    external_id=external_id,
                    campaign_id=campaign_id,
                    creator_id=creator_id,
                    brand_id=brand_id,
                )
                
                # 4. Generate dedupe_hash
                dedupe_hash = self._generate_dedupe_hash(
                    external_event_id=external_event_id,
                    event_type=event_type,
                    occurred_at=occurred_at,
                )
                
                # 5. Create event
                event = AnalyticsEvent.objects.create(
                    event_type=event_type,
                    occurred_at=occurred_at,
                    
                    # Entities
                    platform_id=entities.get('platform_id'),
                    brand_id=entities.get('brand_id'),
                    campaign_id=entities.get('campaign_id'),
                    creator_id=entities.get('creator_id'),
                    content_id=entities.get('content_id'),
                    link_id=entities.get('link_id'),
                    
                    # Visitor tracking
                    visitor_id=visitor_id,
                    session_id=session_id,
                    user_id=user_id,
                    
                    # Conversion
                    conversion_value=conversion_value,
                    conversion_attributed_to_link_id=conversion_attributed_to_link_id,
                    
                    # Deduplication
                    external_event_id=external_event_id,
                    dedupe_hash=dedupe_hash,
                    
                    # Data
                    metrics=metrics or {},
                    meta={
                        **(meta or {}),
                        '_linking_source': entities.get('_linking_source'),
                        '_raw_identifiers': {
                            'link_id': link_id,
                            'content_id': content_id,
                            'platform_id': platform_id,
                            'external_id': external_id,
                        },
                    },
                )
                
                self.logger.info(
                    f"Event ingested: {event_type} at {occurred_at} "
                    f"(event_id={event.id}, campaign={entities.get('campaign_id')})"
                )
                
                return event, True
        
        except Exception as e:
            self.logger.error(f"Ingestion failed: {str(e)}", exc_info=True)
            raise IngestionError(f"Failed to ingest event: {str(e)}") from e
    
    def ingest_batch(
        self,
        events: list[Dict[str, Any]],
        skip_errors: bool = False,
    ) -> Dict[str, Any]:
        """
        Ingest multiple events in batch.
        
        Args:
            events: List of event dictionaries
            skip_errors: If True, continue on errors and return error list
        
        Returns:
            Dict with results:
            {
                'total': int,
                'created': int,
                'deduplicated': int,
                'errors': list[Dict],
            }
        """
        results = {
            'total': len(events),
            'created': 0,
            'deduplicated': 0,
            'errors': [],
        }
        
        for idx, event_data in enumerate(events):
            try:
                event, created = self.ingest_event(**event_data)
                if created:
                    results['created'] += 1
                else:
                    results['deduplicated'] += 1
            except Exception as e:
                error_info = {
                    'index': idx,
                    'event_data': event_data,
                    'error': str(e),
                }
                results['errors'].append(error_info)
                
                if not skip_errors:
                    raise IngestionError(
                        f"Batch ingestion failed at index {idx}: {str(e)}"
                    ) from e
        
        self.logger.info(
            f"Batch ingestion complete: {results['created']} created, "
            f"{results['deduplicated']} deduplicated, {len(results['errors'])} errors"
        )
        
        return results
    
    # ========================================================================
    # VALIDATION
    # ========================================================================
    
    def _validate_event(
        self,
        event_type: str,
        occurred_at: datetime,
        link_id: Optional[str],
        content_id: Optional[str],
        platform_id: Optional[str],
        external_id: Optional[str],
    ):
        """Validate event has minimum required fields"""
        # Check event_type is valid
        if event_type not in dict(EventType.choices):
            raise ValidationError(f"Invalid event_type: {event_type}")
        
        # Check occurred_at is provided
        if not occurred_at:
            raise ValidationError("occurred_at is required")
        
        # Check at least one identifier is provided
        if not any([link_id, content_id, (platform_id and external_id)]):
            raise ValidationError(
                "At least one identifier required: link_id, content_id, "
                "or (platform_id + external_id)"
            )
    
    # ========================================================================
    # DEDUPLICATION
    # ========================================================================
    
    def _check_deduplication(
        self,
        external_event_id: Optional[str],
        event_type: str,
        occurred_at: datetime,
        link_id: Optional[str],
        content_id: Optional[str],
        visitor_id: Optional[str],
    ) -> Optional[AnalyticsEvent]:
        """
        Check if event already exists.
        
        Deduplication strategies (in order):
        1. external_event_id (if provided)
        2. dedupe_hash (external_event_id + occurred_at + event_type)
        3. Fuzzy match (link + visitor + event_type + occurred_at within 1 minute)
        
        Returns:
            AnalyticsEvent if duplicate found, None otherwise
        """
        # Strategy 1: external_event_id
        if external_event_id:
            existing = AnalyticsEvent.objects.filter(
                external_event_id=external_event_id
            ).first()
            if existing:
                return existing
        
        # Strategy 2: dedupe_hash
        dedupe_hash = self._generate_dedupe_hash(
            external_event_id=external_event_id,
            event_type=event_type,
            occurred_at=occurred_at,
        )
        if dedupe_hash:
            existing = AnalyticsEvent.objects.filter(
                dedupe_hash=dedupe_hash
            ).first()
            if existing:
                return existing
        
        # Strategy 3: Fuzzy match (for events without external_event_id)
        # Match on: link + visitor + event_type + occurred_at (within 1 min)
        if link_id and visitor_id:
            from datetime import timedelta
            time_window_start = occurred_at - timedelta(minutes=1)
            time_window_end = occurred_at + timedelta(minutes=1)
            
            existing = AnalyticsEvent.objects.filter(
                link_id=link_id,
                visitor_id=visitor_id,
                event_type=event_type,
                occurred_at__gte=time_window_start,
                occurred_at__lte=time_window_end,
            ).first()
            if existing:
                return existing
        
        return None
    
    def _generate_dedupe_hash(
        self,
        external_event_id: Optional[str],
        event_type: str,
        occurred_at: datetime,
    ) -> Optional[str]:
        """Generate MD5 hash for deduplication"""
        if not external_event_id:
            return None
        
        hash_input = f"{external_event_id}:{occurred_at.isoformat()}:{event_type}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    # ========================================================================
    # ENTITY LINKING
    # ========================================================================
    
    def _resolve_entities(
        self,
        link_id: Optional[str],
        content_id: Optional[str],
        platform_id: Optional[str],
        external_id: Optional[str],
        campaign_id: Optional[str],
        creator_id: Optional[str],
        brand_id: Optional[str],
    ) -> Dict[str, Optional[str]]:
        """
        Resolve entity relationships using precedence rules.
        
        LINKING PRECEDENCE:
        1. If link exists → derive campaign/creator/content from TrackingLink
        2. Else if content exists → use Content.campaign + Content.creator + Content.platform
        3. Else if (platform + external_id) → resolve to Content(platform, external_id)
        4. Else use provided overrides (campaign_id, creator_id, etc.)
        5. If still missing → store null but log identifiers in meta
        
        Returns:
            Dict with resolved entity IDs and linking source
        """
        entities = {
            'platform_id': platform_id,
            'brand_id': brand_id,
            'campaign_id': campaign_id,
            'creator_id': creator_id,
            'content_id': content_id,
            'link_id': link_id,
            '_linking_source': None,
        }
        
        # Rule 1: Link exists → derive from TrackingLink
        if link_id:
            try:
                link = TrackingLink.objects.select_related(
                    'campaign', 'creator', 'content', 'campaign__brand'
                ).get(id=link_id)
                
                entities.update({
                    'link_id': str(link.id),
                    'campaign_id': str(link.campaign.id) if link.campaign else None,
                    'creator_id': str(link.creator.id) if link.creator else None,
                    'content_id': str(link.content.id) if link.content else None,
                    'brand_id': str(link.campaign.brand.id) if link.campaign and link.campaign.brand else None,
                    '_linking_source': 'link',
                })
                
                # If content exists, get platform too
                if link.content:
                    entities['platform_id'] = str(link.content.platform.id)
                
                return entities
            except TrackingLink.DoesNotExist:
                self.logger.warning(f"Link not found: {link_id}")
                # Fall through to next rules
        
        # Rule 2: Content exists → derive from Content
        if content_id:
            try:
                content = Content.objects.select_related(
                    'campaign', 'creator', 'platform', 'campaign__brand'
                ).get(id=content_id)
                
                entities.update({
                    'content_id': str(content.id),
                    'campaign_id': str(content.campaign.id) if content.campaign else campaign_id,
                    'creator_id': str(content.creator.id) if content.creator else creator_id,
                    'platform_id': str(content.platform.id) if content.platform else platform_id,
                    'brand_id': str(content.campaign.brand.id) if content.campaign and content.campaign.brand else brand_id,
                    '_linking_source': 'content',
                })
                
                return entities
            except Content.DoesNotExist:
                self.logger.warning(f"Content not found: {content_id}")
                # Fall through to next rules
        
        # Rule 3: (platform + external_id) → resolve to Content
        if platform_id and external_id:
            try:
                content = Content.objects.select_related(
                    'campaign', 'creator', 'platform', 'campaign__brand'
                ).get(platform_id=platform_id, external_id=external_id)
                
                entities.update({
                    'content_id': str(content.id),
                    'campaign_id': str(content.campaign.id) if content.campaign else campaign_id,
                    'creator_id': str(content.creator.id) if content.creator else creator_id,
                    'platform_id': str(content.platform.id),
                    'brand_id': str(content.campaign.brand.id) if content.campaign and content.campaign.brand else brand_id,
                    '_linking_source': 'platform_external_id',
                })
                
                return entities
            except Content.DoesNotExist:
                self.logger.info(
                    f"Content not found for platform={platform_id}, external_id={external_id}. "
                    "Consider creating Content record."
                )
                # Fall through to use provided overrides
        
        # Rule 4: Use provided overrides
        entities['_linking_source'] = 'override'
        
        # Rule 5: Log missing entities
        missing_entities = [
            key for key, value in entities.items() 
            if value is None and key != '_linking_source'
        ]
        if missing_entities:
            self.logger.warning(
                f"Could not link entities: {missing_entities}. "
                f"Event will be stored with partial linking."
            )
        
        return entities


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def ingest_event(**kwargs) -> Tuple[AnalyticsEvent, bool]:
    """
    Convenience function to ingest a single event.
    
    Usage:
        from ANALYTICS.services.ingestion import ingest_event
        
        event, created = ingest_event(
            event_type='click',
            occurred_at=timezone.now(),
            link_id='abc-123',
            visitor_id='visitor-xyz',
        )
    """
    service = AnalyticsIngestionService()
    return service.ingest_event(**kwargs)


def ingest_batch(events: list[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    Convenience function to ingest batch of events.
    
    Usage:
        from ANALYTICS.services.ingestion import ingest_batch
        
        results = ingest_batch([
            {
                'event_type': 'click',
                'occurred_at': timezone.now(),
                'link_id': 'abc-123',
            },
            {
                'event_type': 'impression',
                'occurred_at': timezone.now(),
                'content_id': 'def-456',
            },
        ])
    """
    service = AnalyticsIngestionService()
    return service.ingest_batch(events, **kwargs)