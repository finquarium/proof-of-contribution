import json
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from finquarium_proof.models.insights import MarketInsights
from finquarium_proof.models.db import MarketInsightSubmission

logger = logging.getLogger(__name__)

class MarketInsightsError(Exception):
    """Base exception for market insights service errors"""
    pass

class MarketInsightsService:
    """Service for processing market insights submissions"""
    def __init__(self, session: Session):
        if not session:
            raise ValueError("Database session is required")
        self.session = session

    def store_submission(
            self,
            insights: MarketInsights,
            file_id: int,
            owner_address: str,
            file_url: str,
            file_checksum: str
    ) -> None:
        """Store a market insights submission"""
        if not insights:
            raise MarketInsightsError("Market insights data is required")

        if not owner_address:
            raise MarketInsightsError("Owner address is required")

        submission = MarketInsightSubmission(
            file_id=file_id,
            owner_address=owner_address,
            base_points=insights.metadata.basePoints,
            prediction_points=insights.metadata.predictionPoints,
            total_points=insights.metadata.basePoints + insights.metadata.predictionPoints,
            expertise=insights.expertise.__dict__,
            strategy=insights.strategy.__dict__,
            psychology=insights.psychology.__dict__,
            contact_method=insights.contact.method if insights.contact else None,
            contact_value=insights.contact.value if insights.contact else None,
            allow_updates=insights.contact.allowUpdates if insights.contact else False,
            created_at=datetime.fromtimestamp(insights.metadata.timestamp / 1000),
            file_url=file_url,
            file_checksum=file_checksum
        )

        try:
            self.session.add(submission)
            self.session.commit()
            logger.info(f"Stored market insights submission for {owner_address}")
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Database error storing market insights: {e}")
            raise MarketInsightsError(f"Failed to store market insights: {str(e)}")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Unexpected error storing market insights: {e}")
            raise MarketInsightsError(f"Unexpected error storing market insights: {str(e)}")