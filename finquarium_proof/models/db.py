"""SQLAlchemy database models for storing contribution data"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, BigInteger, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class UserContribution(Base):
    """
    Tracks user contributions and rewards.
    Uses hashed account IDs for privacy.
    """
    __tablename__ = 'user_contributions'

    id = Column(Integer, primary_key=True)
    account_id_hash = Column(String, unique=True, nullable=False, index=True)
    transaction_count = Column(Integer, nullable=False)
    total_volume = Column(Float, nullable=False)
    activity_period_days = Column(Integer, nullable=False)
    unique_assets = Column(Integer, nullable=False)
    latest_score = Column(Float, nullable=False)
    times_rewarded = Column(Integer, default=0)
    first_contribution_at = Column(DateTime, default=datetime.utcnow)
    latest_contribution_at = Column(DateTime, default=datetime.utcnow)
    raw_data = Column(JSON, nullable=True)
    encrypted_refresh_token = Column(String, nullable=True)

class ContributionProof(Base):
    """
    Stores proof details for each contribution attempt.
    Links to user_contributions through account_id_hash.
    """
    __tablename__ = 'contribution_proofs'

    id = Column(Integer, primary_key=True)
    account_id_hash = Column(String, nullable=False, index=True)
    file_id = Column(BigInteger, nullable=False)
    file_url = Column(String, nullable=False)
    job_id = Column(String, nullable=False)
    owner_address = Column(String, nullable=False)
    score = Column(Float, nullable=False)
    authenticity = Column(Float, nullable=False)
    ownership = Column(Float, nullable=False)
    quality = Column(Float, nullable=False)
    uniqueness = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class MarketInsightSubmission(Base):
    """
    Stores market insight submissions
    """
    __tablename__ = 'market_insight_submissions'

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, nullable=False)
    owner_address = Column(String, nullable=False, index=True)
    base_points = Column(Integer, nullable=False)
    prediction_points = Column(Integer, nullable=False)
    total_points = Column(Integer, nullable=False)
    expertise = Column(JSON, nullable=False)
    strategy = Column(JSON, nullable=False)
    psychology = Column(JSON, nullable=False)
    contact_method = Column(String)
    contact_value = Column(String)
    allow_updates = Column(Boolean)
    created_at = Column(DateTime, nullable=False)
    file_url = Column(String, nullable=False)
    file_checksum = Column(String, nullable=False)