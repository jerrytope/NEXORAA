# SOCIAL_INTELLIGENCE/services/sentiment.py
"""
Sentiment Processing Service for Social Intelligence

Processes sentiment from:
- Social mentions (Mention model)
- Campaign content (Content model via AnalyticsEvent)
- Rollups to campaign/creator level
"""

import logging
from typing import Optional, Dict, Tuple
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Q

from SOCIAL_INTELLIGENCE.models import (
    Mention,
    MentionSentiment,
    TrackedEntity,
)
from ANALYTICS.models import Content, Campaign, Creator

logger = logging.getLogger(__name__)


class SentimentProcessor:
    """
    Process sentiment for mentions and campaign content
    
    ML-ready placeholder: Uses rule-based logic now, can be replaced with ML
    """
    
    def __init__(self):
        self.logger = logger
    
    def analyze_mention(
        self,
        mention: Mention,
        entity: TrackedEntity,
        analyzer: str = 'default',
    ) -> MentionSentiment:
        """
        Analyze sentiment for a mention-entity pair
        
        Args:
            mention: Mention instance
            entity: TrackedEntity instance
            analyzer: Which analyzer to use (future: ML model)
        
        Returns:
            MentionSentiment instance
        """
        # Placeholder sentiment analysis (ML-ready)
        sentiment_score, sentiment_label, confidence = self._analyze_text(
            mention.text,
            analyzer=analyzer
        )
        
        # Create or update sentiment
        sentiment, created = MentionSentiment.objects.update_or_create(
            mention=mention,
            entity=entity,
            defaults={
                'sentiment': sentiment_label,
                'sentiment_score': sentiment_score,
                'confidence': confidence,
                'analyzer': analyzer,
                'sentiment_context': self._extract_context(mention.text),
            }
        )
        
        action = 'Created' if created else 'Updated'
        self.logger.info(
            f"{action} sentiment for {entity.name} in mention {mention.id}: "
            f"{sentiment_label} ({sentiment_score:.2f})"
        )
        
        return sentiment
    
    def _analyze_text(
        self,
        text: str,
        analyzer: str = 'default',
    ) -> Tuple[float, str, float]:
        """
        Analyze text and return sentiment
        
        Returns:
            (score, label, confidence)
            - score: -1.0 to 1.0
            - label: positive/neutral/negative/mixed
            - confidence: 0.0 to 1.0
        
        TODO: Replace with actual ML model
        """
        # Placeholder rule-based logic
        text_lower = text.lower()
        
        # Simple keyword matching (to be replaced)
        positive_words = ['love', 'great', 'awesome', 'excellent', 'amazing', 'best']
        negative_words = ['hate', 'terrible', 'awful', 'worst', 'bad', 'disappointing']
        
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        if pos_count > neg_count:
            score = min(0.8, 0.3 + (pos_count * 0.2))
            label = 'positive'
            confidence = 0.7
        elif neg_count > pos_count:
            score = max(-0.8, -0.3 - (neg_count * 0.2))
            label = 'negative'
            confidence = 0.7
        elif pos_count == neg_count and pos_count > 0:
            score = 0.0
            label = 'mixed'
            confidence = 0.6
        else:
            score = 0.0
            label = 'neutral'
            confidence = 0.5
        
        return score, label, confidence
    
    def _extract_context(self, text: str, max_length: int = 200) -> str:
        """Extract relevant context from text"""
        return text[:max_length] if len(text) > max_length else text
    
    def get_campaign_sentiment_rollup(
        self,
        campaign: Campaign,
    ) -> Dict:
        """
        Get sentiment rollup for campaign
        
        Aggregates sentiment from:
        - Campaign content mentions
        - Related tracked entities
        
        Returns:
            Dict with sentiment metrics
        """
        # Get all entities linked to this campaign
        entities = TrackedEntity.objects.filter(campaign=campaign)
        
        # Get sentiment stats
        sentiments = MentionSentiment.objects.filter(entity__in=entities)
        
        stats = sentiments.aggregate(
            total=Count('id'),
            avg_score=Avg('sentiment_score'),
            positive=Count('id', filter=Q(sentiment='positive')),
            negative=Count('id', filter=Q(sentiment='negative')),
            neutral=Count('id', filter=Q(sentiment='neutral')),
            mixed=Count('id', filter=Q(sentiment='mixed')),
        )
        
        return {
            'campaign_id': str(campaign.id),
            'campaign_name': campaign.name,
            'total_mentions': stats['total'] or 0,
            'avg_sentiment_score': float(stats['avg_score'] or 0),
            'positive_mentions': stats['positive'] or 0,
            'negative_mentions': stats['negative'] or 0,
            'neutral_mentions': stats['neutral'] or 0,
            'mixed_mentions': stats['mixed'] or 0,
            'sentiment_distribution': {
                'positive': stats['positive'] or 0,
                'negative': stats['negative'] or 0,
                'neutral': stats['neutral'] or 0,
                'mixed': stats['mixed'] or 0,
            }
        }
    
    def get_creator_sentiment_rollup(
        self,
        creator: Creator,
    ) -> Dict:
        """Get sentiment rollup for creator's content"""
        # Get entities linked to this creator
        entities = TrackedEntity.objects.filter(creator=creator)
        
        sentiments = MentionSentiment.objects.filter(entity__in=entities)
        
        stats = sentiments.aggregate(
            total=Count('id'),
            avg_score=Avg('sentiment_score'),
            positive=Count('id', filter=Q(sentiment='positive')),
            negative=Count('id', filter=Q(sentiment='negative')),
            neutral=Count('id', filter=Q(sentiment='neutral')),
        )
        
        return {
            'creator_id': str(creator.id),
            'creator_name': creator.name,
            'total_mentions': stats['total'] or 0,
            'avg_sentiment_score': float(stats['avg_score'] or 0),
            'positive_mentions': stats['positive'] or 0,
            'negative_mentions': stats['negative'] or 0,
            'neutral_mentions': stats['neutral'] or 0,
        }


# Convenience functions
def analyze_mention_sentiment(mention: Mention, entity: TrackedEntity) -> MentionSentiment:
    """Convenience function to analyze sentiment"""
    processor = SentimentProcessor()
    return processor.analyze_mention(mention, entity)


def get_campaign_sentiment(campaign: Campaign) -> Dict:
    """Convenience function to get campaign sentiment"""
    processor = SentimentProcessor()
    return processor.get_campaign_sentiment_rollup(campaign)