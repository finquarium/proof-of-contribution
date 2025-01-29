# finquarium_proof/models/binance.py
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

@dataclass
class BinanceTransaction:
    timestamp: datetime  # Date(UTC)
    symbol: str         # Pair
    side: str          # BUY/SELL
    price: Decimal     # Price
    quantity: Decimal  # Executed qty
    amount: Decimal    # Total quote amount
    fee: Decimal       # Fee amount
    fee_asset: str     # Fee asset parsed from Fee column

@dataclass
class BinanceValidationData:
    account_id_hash: str
    transactions: List[BinanceTransaction]
    total_volume: Decimal
    asset_count: int
    start_time: datetime
    end_time: datetime