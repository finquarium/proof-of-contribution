"""Database storage service for contributions and proofs"""
import logging
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from finquarium_proof.models.db import UserContribution, ContributionProof
from finquarium_proof.models.contribution import ContributionData, ExistingContribution
from finquarium_proof.models.proof import ProofResponse

logger = logging.getLogger(__name__)

class StorageService:
    """Handles all database operations"""

    def __init__(self, session: Session):
        self.session = session

    def check_existing_contribution(self, account_id_hash: str) -> Tuple[bool, Optional[ExistingContribution]]:
        """Check if user has already contributed and get their contribution record"""
        try:
            contribution = self.session.query(UserContribution).filter_by(
                account_id_hash=account_id_hash
            ).first()

            if contribution:
                return True, ExistingContribution(
                    times_rewarded=contribution.times_rewarded,
                    transaction_count=contribution.transaction_count,
                    total_volume=contribution.total_volume,
                    activity_period_days=contribution.activity_period_days,
                    unique_assets=contribution.unique_assets,
                    latest_score=contribution.latest_score
                )
            return False, None
        except SQLAlchemyError as e:
            logger.error(f"Database error checking existing contribution: {e}")
            raise

    def store_contribution(self, data: ContributionData, proof: ProofResponse,
                           file_id: int, file_url: str, job_id: str, owner_address: str,
                           encrypted_refresh_token: str = None) -> None:
        """Store contribution and proof data if score > 0"""
        try:
            if proof.score > 0:
                # Prepare data for storage
                raw_data = {
                    'stats': {
                        'total_volume': data.stats.total_volume,
                        'transaction_count': data.stats.transaction_count,
                        'unique_assets': [asset for asset in data.stats.unique_assets],
                        'activity_period_days': data.stats.activity_period_days,
                        'first_transaction_date': data.stats.first_transaction_date.isoformat() if data.stats.first_transaction_date else None,
                        'last_transaction_date': data.stats.last_transaction_date.isoformat() if data.stats.last_transaction_date else None
                    },
                    'transactions': [
                        {
                            'type': tx.type,
                            'asset': tx.asset,
                            'quantity': tx.quantity,
                            'native_amount': tx.native_amount,
                            'timestamp': tx.timestamp.isoformat() if tx.timestamp else None
                        }
                        for tx in data.transactions
                    ]
                }

                # Update or create user contribution record
                contribution = self.session.query(UserContribution).filter_by(
                    account_id_hash=data.account_id_hash
                ).first()

                if contribution:
                    contribution.transaction_count = data.stats.transaction_count
                    contribution.total_volume = data.stats.total_volume
                    contribution.activity_period_days = data.stats.activity_period_days
                    contribution.unique_assets = len(data.stats.unique_assets)
                    contribution.latest_score = proof.score
                    contribution.latest_contribution_at = datetime.utcnow()
                    contribution.raw_data = raw_data
                    # Update encrypted refresh token if provided
                    if encrypted_refresh_token:
                        contribution.encrypted_refresh_token = encrypted_refresh_token
                else:
                    contribution = UserContribution(
                        account_id_hash=data.account_id_hash,
                        transaction_count=data.stats.transaction_count,
                        total_volume=data.stats.total_volume,
                        activity_period_days=data.stats.activity_period_days,
                        unique_assets=len(data.stats.unique_assets),
                        latest_score=proof.score,
                        times_rewarded=0,
                        raw_data=raw_data,
                        encrypted_refresh_token=encrypted_refresh_token
                    )
                    self.session.add(contribution)

                # Store proof details
                proof_record = ContributionProof(
                    account_id_hash=data.account_id_hash,
                    file_id=file_id,
                    file_url=file_url,
                    job_id=job_id,
                    owner_address=owner_address,
                    score=proof.score,
                    authenticity=proof.authenticity,
                    ownership=proof.ownership,
                    quality=proof.quality,
                    uniqueness=proof.uniqueness
                )
                self.session.add(proof_record)

                self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Database error storing contribution: {e}")
            raise