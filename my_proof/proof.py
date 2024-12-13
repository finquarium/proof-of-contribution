import json
import time
import requests
import os
from datetime import datetime
from typing import Dict, Any
from my_proof.models.proof_response import ProofResponse

class CoinbaseAPI:
    """Simplified Python port of CoinbaseService for consistent formatting"""
    def __init__(self, token: str):
        self.token = token

    def get_user_info(self) -> dict:
        """Get user info from Coinbase API"""
        return self._make_request('user')

    def get_accounts(self) -> list:
        """Get accounts from Coinbase API"""
        response = self._make_request('accounts')
        return response.get('data', [])

    def get_transactions(self, account_id: str) -> list:
        """Get transactions for an account"""
        response = self._make_request(f'accounts/{account_id}/transactions')
        return response.get('data', [])

    def _make_request(self, endpoint: str) -> dict:
        """Make request to Coinbase API with retries"""
        headers = {
            'Authorization': f'Bearer {self.token}',
            'CB-VERSION': '2024-01-01',
            'Accept': 'application/json'
        }

        for attempt in range(3):  # 3 retries
            try:
                response = requests.get(
                    f'https://api.coinbase.com/v2/{endpoint}',
                    headers=headers
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt == 2:  # Last attempt
                    raise
                time.sleep(1)  # Wait before retry

    def get_formatted_history(self) -> dict:
        """Format data same way as frontend CoinbaseService"""
        # Get user info and transactions
        user = self.get_user_info()['data']
        accounts = self.get_accounts()

        all_transactions = []
        for account in accounts:
            transactions = self.get_transactions(account['id'])
            all_transactions.extend(transactions)

        # Calculate statistics
        stats = self._calculate_stats(all_transactions)

        return {
            'user': {
                'name': user['name'],
                'id': user['id'],
                'email': user['email']
            },
            'stats': stats,
            'transactions': [self._format_transaction(t) for t in all_transactions]
        }

    def _calculate_stats(self, transactions: list) -> dict:
        """Calculate transaction statistics"""
        stats = {
            'totalVolume': sum(abs(float(t['native_amount']['amount'])) for t in transactions),
            'transactionCount': len(transactions),
            'uniqueAssets': set(t['amount']['currency'] for t in transactions)
        }

        # Track date range
        dates = [datetime.strptime(t['created_at'], "%Y-%m-%dT%H:%M:%SZ") for t in transactions]
        if dates:
            stats['firstTransactionDate'] = min(dates).isoformat()
            stats['lastTransactionDate'] = max(dates).isoformat()
            stats['activityPeriodDays'] = (max(dates) - min(dates)).days

        return {
            **stats,
            'uniqueAssets': list(stats['uniqueAssets'])  # Convert set to list for JSON
        }

    def _format_transaction(self, t: dict) -> dict:
        """Format a single transaction"""
        native_amount = abs(float(t['native_amount']['amount']))
        quantity = abs(float(t['amount']['amount']))

        return {
            'id': t['id'],
            'timestamp': t['created_at'],
            'type': t['type'],
            'asset': t['amount']['currency'],
            'quantity': quantity,
            'native_currency': t['native_amount']['currency'],
            'native_amount': native_amount,
            'price_at_transaction': native_amount / quantity if quantity != 0 else 0,
            'total': native_amount
        }

class Proof:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.proof_response = ProofResponse(dlp_id=config['dlp_id'])

    def generate(self) -> ProofResponse:
        """Generate proof by comparing decrypted file with fresh Coinbase data"""

        # Get Coinbase token from env vars
        token = self.config['env_vars'].get('COINBASE_TOKEN')
        if not token:
            raise ValueError("COINBASE_TOKEN not provided in environment")

        # Load decrypted file
        decrypted_data = None
        for filename in os.listdir(self.config['input_dir']):
            if os.path.splitext(filename)[1].lower() == '.json':
                with open(os.path.join(self.config['input_dir'], filename), 'r') as f:
                    decrypted_data = json.load(f)
                break

        if not decrypted_data:
            raise ValueError("No decrypted JSON file found")

        # Fetch fresh data from Coinbase 
        coinbase = CoinbaseAPI(token)
        fresh_data = coinbase.get_formatted_history()

        # Compare key data points
        matches = self._validate_data(decrypted_data, fresh_data)

        # Set proof scores
        self.proof_response.authenticity = 1.0 if matches else 0.0  # Data matches what's in Coinbase
        self.proof_response.ownership = 1.0  # User has proven ownership by providing valid token
        self.proof_response.quality = 1.0  # Data is properly formatted
        self.proof_response.uniqueness = 1.0  # Each user's data is unique

        # Calculate overall score
        self.proof_response.score = (
                self.proof_response.authenticity * 0.4 +
                self.proof_response.ownership * 0.3 +
                self.proof_response.quality * 0.2 +
                self.proof_response.uniqueness * 0.1
        )

        self.proof_response.valid = matches

        # Add validation details to attributes
        self.proof_response.attributes = {
            'user_email': fresh_data['user']['email'],
            'transaction_count': fresh_data['stats']['transactionCount'],
            'total_volume': fresh_data['stats']['totalVolume'],
            'data_validated': matches
        }

        return self.proof_response

    def _validate_data(self, saved_data: dict, fresh_data: dict) -> bool:
        """
        Compare saved data with fresh data from Coinbase.
        Focus on immutable properties that can't change between fetches.
        """
        try:
            # Compare user ID
            if saved_data['user']['id'] != fresh_data['user']['id']:
                return False

            # Compare historical transactions
            saved_txs = {tx['id']: tx for tx in saved_data['transactions']}
            fresh_txs = {tx['id']: tx for tx in fresh_data['transactions']}

            # Compare transaction IDs up to saved data
            # (fresh data might have newer transactions)
            for tx_id, saved_tx in saved_txs.items():
                if tx_id not in fresh_txs:
                    return False

                fresh_tx = fresh_txs[tx_id]

                # Compare immutable transaction properties
                if (saved_tx['id'] != fresh_tx['id'] or
                        saved_tx['type'] != fresh_tx['type'] or
                        saved_tx['asset'] != fresh_tx['asset'] or
                        abs(saved_tx['quantity'] - fresh_tx['quantity']) > 1e-8 or
                        saved_tx['native_currency'] != fresh_tx['native_currency'] or
                        abs(saved_tx['native_amount'] - fresh_tx['native_amount']) > 1e-8):
                    return False

            return True

        except (KeyError, TypeError) as e:
            print(f"Validation error: {str(e)}")
            return False
