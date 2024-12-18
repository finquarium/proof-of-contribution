from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, BigInteger
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class UserContribution(Base):
    """
    Tracks user contributions and rewards.
    Uses hashed account IDs for privacy.
    """
    __tablename__ = 'user_contributions'

    id = Column(Integer, primary_key=True)
    account_id_hash = Column(String, unique=True, nullable=False)
    transaction_count = Column(Integer, nullable=False)
    total_volume = Column(Float, nullable=False)
    activity_period_days = Column(Integer, nullable=False)
    unique_assets = Column(Integer, nullable=False)
    latest_score = Column(Float, nullable=False)
    times_rewarded = Column(Integer, default=0)
    first_contribution_at = Column(DateTime, default=datetime.utcnow)
    latest_contribution_at = Column(DateTime, default=datetime.utcnow)

    # TODO: For future implementation of incremental rewards
    # latest_transaction_id = Column(String)
    # latest_transaction_timestamp = Column(DateTime)

class ContributionProof(Base):
    """
    Stores proof details for each contribution.
    Links to user_contributions through account_id_hash.
    """
    __tablename__ = 'contribution_proofs'

    id = Column(Integer, primary_key=True)
    account_id_hash = Column(String, nullable=False)
    dlp_id = Column(Integer, nullable=False)
    file_id = Column(BigInteger, nullable=False)
    score = Column(Float, nullable=False)
    authenticity = Column(Float, nullable=False)
    ownership = Column(Float, nullable=False)
    quality = Column(Float, nullable=False)
    uniqueness = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)