"""Domain models for handling contribution data"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any

@dataclass
class Transaction:
    """Anonymized transaction data"""
    type: str
    asset: str
    quantity: float
    native_amount: float
    timestamp: datetime

@dataclass
class TradingStats:
    """Trading statistics for scoring"""
    total_volume: float
    transaction_count: int
    unique_assets: List[str]
    activity_period_days: int
    first_transaction_date: Optional[datetime]
    last_transaction_date: Optional[datetime]

@dataclass
class ContributionData:
    """Complete contribution data"""
    account_id_hash: str
    stats: TradingStats
    transactions: List[Transaction]
    raw_data: Dict[str, Any]  # Original anonymized data

@dataclass
class ExistingContribution:
    """Data about previous contributions"""
    times_rewarded: int
    transaction_count: int
    total_volume: float
    activity_period_days: int
    unique_assets: int
    latest_score: float