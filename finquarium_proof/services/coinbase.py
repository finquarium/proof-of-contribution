"""Coinbase API integration service"""
import hashlib
import logging
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import requests

from finquarium_proof.models.contribution import Transaction, TradingStats, ContributionData

logger = logging.getLogger(__name__)

class CoinbaseAPI:
    """Handles all Coinbase API interactions with consistent formatting"""

    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.coinbase.com/v2"
        self.api_version = "2024-01-01"

    def get_user_info(self) -> dict:
        """Get user info from Coinbase API"""
        return self._make_request('user')

    def get_accounts(self) -> list:
        """Get accounts from Coinbase API"""
        response = self._make_request('accounts')
        return response.get('data', [])

    def get_transactions(self, account_id: str, starting_after: Optional[str] = None) -> Tuple[List, Optional[str]]:
        """Get transactions for an account with pagination"""
        endpoint = f'accounts/{account_id}/transactions'
        if starting_after:
            endpoint += f'?starting_after={starting_after}'

        response = self._make_request(endpoint)
        return response.get('data', []), response.get('pagination', {}).get('next_uri')

    def _make_request(self, endpoint: str) -> dict:
        """Make request to Coinbase API with retries"""
        headers = {
            'Authorization': f'Bearer {self.token}',
            'CB-VERSION': self.api_version,
            'Accept': 'application/json'
        }

        for attempt in range(3):  # 3 retries
            try:
                response = requests.get(
                    f'{self.base_url}/{endpoint}',
                    headers=headers
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt == 2:  # Last attempt
                    raise
                logger.warning(f"Retrying request after error: {e}")
                time.sleep(1)  # Wait before retry

    def get_all_transactions(self) -> List[Dict]:
        """Get all transactions with pagination handling"""
        accounts = self.get_accounts()
        all_transactions = []

        for account in accounts:
            has_more = True
            starting_after = None

            while has_more:
                transactions, next_uri = self.get_transactions(account['id'], starting_after)
                all_transactions.extend(transactions)

                if next_uri:
                    try:
                        starting_after = next_uri.split('starting_after=')[1].split('&')[0]
                        has_more = True
                    except (IndexError, AttributeError):
                        has_more = False
                else:
                    has_more = False

                time.sleep(0.1)  # Rate limiting

        return all_transactions

    def _format_transaction(self, tx: Dict) -> Transaction:
        """Format a single transaction into our domain model"""
        native_amount = abs(float(tx['native_amount']['amount']))
        quantity = abs(float(tx['amount']['amount']))

        return Transaction(
            type=tx['type'],
            asset=tx['amount']['currency'],
            quantity=quantity,
            native_amount=native_amount,
            timestamp=datetime.strptime(tx['created_at'], "%Y-%m-%dT%H:%M:%SZ")
        )

    def _calculate_stats(self, transactions: List[Dict]) -> TradingStats:
        """Calculate trading statistics"""
        unique_assets = set()
        total_volume = 0
        first_date = None
        last_date = None

        for tx in transactions:
            # Calculate volume in native currency
            total_volume += abs(float(tx['native_amount']['amount']))
            # Track unique assets
            unique_assets.add(tx['amount']['currency'])
            # Track transaction dates
            date = datetime.strptime(tx['created_at'], "%Y-%m-%dT%H:%M:%SZ")
            if not first_date or date < first_date:
                first_date = date
            if not last_date or date > last_date:
                last_date = date

        activity_days = (last_date - first_date).days if first_date and last_date else 0

        return TradingStats(
            total_volume=total_volume,
            transaction_count=len(transactions),
            unique_assets=list(unique_assets),
            activity_period_days=activity_days,
            first_transaction_date=first_date,
            last_transaction_date=last_date
        )

    def get_formatted_history(self) -> ContributionData:
        """Get formatted trading history with anonymized user data"""
        # Get user info and create hash
        user = self.get_user_info()['data']
        account_id_hash = hashlib.sha256(user['id'].encode()).hexdigest()

        # Get transactions and calculate stats
        transactions = self.get_all_transactions()
        stats = self._calculate_stats(transactions)
        formatted_transactions = [self._format_transaction(tx) for tx in transactions]

        # Create anonymized raw data
        raw_data = {
            'stats': stats.__dict__,
            'transactions': [tx.__dict__ for tx in formatted_transactions]
        }

        return ContributionData(
            account_id_hash=account_id_hash,
            stats=stats,
            transactions=formatted_transactions,
            raw_data=raw_data
        )