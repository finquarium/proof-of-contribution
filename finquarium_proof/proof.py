import hashlib
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import requests
from sqlalchemy.exc import SQLAlchemyError

from finquarium_proof.db import db
from finquarium_proof.models.db_models import UserContribution, ContributionProof
from finquarium_proof.models.proof_response import ProofResponse


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

    def get_transactions(self, account_id: str, starting_after: Optional[str] = None) -> tuple:
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

    def get_all_transactions(self) -> list:
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

    def get_formatted_history(self) -> dict:
        """Format data same way as frontend CoinbaseService"""
        # Get user info and transactions
        user = self.get_user_info()['data']
        # Create hashed account ID for privacy
        account_id_hash = hashlib.sha256(user['id'].encode()).hexdigest()

        # Get all transactions with pagination
        all_transactions = self.get_all_transactions()

        # Calculate statistics
        stats = self._calculate_stats(all_transactions)

        return {
            'user': {
                'id_hash': account_id_hash,
                'transaction_count': len(all_transactions)
            },
            'stats': stats,
            'transactions': [self._format_transaction(t) for t in all_transactions]
        }

    def _calculate_stats(self, transactions: list) -> dict:
        """Calculate transaction statistics"""
        stats = {
            'totalVolume': 0,
            'transactionCount': len(transactions),
            'uniqueAssets': set(),
            'firstTransactionDate': None,
            'lastTransactionDate': None
        }

        for t in transactions:
            # Calculate volume in native currency
            stats['totalVolume'] += abs(float(t['native_amount']['amount']))
            # Track unique assets
            stats['uniqueAssets'].add(t['amount']['currency'])

            # Track transaction dates
            date = datetime.strptime(t['created_at'], "%Y-%m-%dT%H:%M:%SZ")
            if not stats['firstTransactionDate'] or date < datetime.strptime(stats['firstTransactionDate'], "%Y-%m-%dT%H:%M:%SZ"):
                stats['firstTransactionDate'] = t['created_at']
            if not stats['lastTransactionDate'] or date > datetime.strptime(stats['lastTransactionDate'], "%Y-%m-%dT%H:%M:%SZ"):
                stats['lastTransactionDate'] = t['created_at']

        # Calculate activity period
        if stats['firstTransactionDate'] and stats['lastTransactionDate']:
            first_date = datetime.strptime(stats['firstTransactionDate'], "%Y-%m-%dT%H:%M:%SZ")
            last_date = datetime.strptime(stats['lastTransactionDate'], "%Y-%m-%dT%H:%M:%SZ")
            stats['activityPeriodDays'] = (last_date - first_date).days
        else:
            stats['activityPeriodDays'] = 0

        return {
            **stats,
            'uniqueAssets': list(stats['uniqueAssets'])
        }

    def _format_transaction(self, t: dict) -> dict:
        """Format a single transaction"""
        native_amount = abs(float(t['native_amount']['amount']))
        quantity = abs(float(t['amount']['amount']))

        formatted = {
            'id': t['id'],
            'timestamp': t['created_at'],
            'type': t['type'],
            'asset': t['amount']['currency'],
            'quantity': quantity,
            'native_currency': t['native_amount']['currency'],
            'native_amount': native_amount,
            'price_at_transaction': native_amount / quantity if quantity != 0 else 0
        }

        # Add fees if present
        if 'fees' in t and t['fees']:
            fee_amount = sum(float(fee['amount']['amount']) for fee in t['fees'])
            formatted['total'] = native_amount + fee_amount
            formatted['fees'] = fee_amount
        else:
            formatted['total'] = native_amount
            formatted['fees'] = 0

        return formatted


class Proof:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.proof_response = ProofResponse(dlp_id=config['dlp_id'])

    class Proof:
        def __init__(self, config: Dict[str, Any]):
            self.config = config
            self.proof_response = ProofResponse(dlp_id=config['dlp_id'])

    def _check_existing_contribution(self, account_id_hash: str) -> Tuple[bool, Optional[Dict]]:
        """Check if user has already contributed and get their contribution record"""
        try:
            with db.session() as session:
                contribution = session.query(UserContribution).filter_by(
                    account_id_hash=account_id_hash
                ).first()

                if contribution:
                    return True, {
                        'times_rewarded': contribution.times_rewarded,
                        'transaction_count': contribution.transaction_count,
                        'total_volume': contribution.total_volume,
                        'activity_period_days': contribution.activity_period_days,
                        'unique_assets': contribution.unique_assets,
                        'latest_score': contribution.latest_score
                    }
                return False, None
        except SQLAlchemyError as e:
            logging.error(f"Database error checking existing contribution: {e}")
            raise

    def _calculate_uniqueness_score(self, has_existing_contribution: bool) -> float:
        """Calculate uniqueness score based on previous contributions"""
        # For now, simple binary scoring
        # TODO: Future implementation could consider:
        # - Time since last contribution
        # - Amount of new data since last contribution
        # - Quality of previous contributions
        return 0.0 if has_existing_contribution else 1.0

    def _store_contribution(self,
                            account_id_hash: str,
                            stats: dict,
                            proof_response: ProofResponse) -> None:
        """Store contribution details in database"""
        try:
            with db.session() as session:
                # Only store if score > 0
                if proof_response.score > 0:
                    # Update or create user contribution record
                    contribution = session.query(UserContribution).filter_by(
                        account_id_hash=account_id_hash
                    ).first()

                    # Anonymize the data by removing personal identifiers
                    anonymized_data = {
                        'stats': stats,
                        'transactions': [
                            {
                                'type': tx['type'],
                                'asset': tx['asset'],
                                'quantity': tx['quantity'],
                                'native_amount': tx['native_amount'],
                                'timestamp': tx['timestamp']
                            } for tx in proof_response.attributes.get('transactions', [])
                        ]
                    }

                    if contribution:
                        # Update existing record
                        contribution.transaction_count = stats['transactionCount']
                        contribution.total_volume = stats['totalVolume']
                        contribution.activity_period_days = stats['activityPeriodDays']
                        contribution.unique_assets = len(stats['uniqueAssets'])
                        contribution.latest_score = proof_response.score
                        contribution.latest_contribution_at = datetime.utcnow()
                        contribution.raw_data = anonymized_data
                    else:
                        # Create new record
                        contribution = UserContribution(
                            account_id_hash=account_id_hash,
                            transaction_count=stats['transactionCount'],
                            total_volume=stats['totalVolume'],
                            activity_period_days=stats['activityPeriodDays'],
                            unique_assets=len(stats['uniqueAssets']),
                            latest_score=proof_response.score,
                            times_rewarded=0,
                            raw_data=anonymized_data
                        )
                        session.add(contribution)

                    # Store proof details
                    proof = ContributionProof(
                        account_id_hash=account_id_hash,
                        file_id=int(self.config['env_vars'].get('FILE_ID', 0)),
                        file_url=self.config['env_vars'].get('FILE_URL', ''),
                        job_id=self.config['env_vars'].get('JOB_ID', ''),
                        owner_address=self.config['env_vars'].get('OWNER_ADDRESS', ''),
                        score=proof_response.score,
                        authenticity=proof_response.authenticity,
                        ownership=proof_response.ownership,
                        quality=proof_response.quality,
                        uniqueness=proof_response.uniqueness
                    )
                    session.add(proof)

        except SQLAlchemyError as e:
            logging.error(f"Database error storing contribution: {e}")
            raise

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

        # Check for existing contribution
        has_existing, existing_data = self._check_existing_contribution(
            fresh_data['user']['id_hash']
        )

        # Compare key data points
        matches = self._validate_data(decrypted_data, fresh_data)

        # Set proof scores
        self.proof_response.authenticity = 1.0 if matches else 0.0
        self.proof_response.ownership = 1.0  # User has proven ownership by providing valid token
        self.proof_response.quality = 1.0 if fresh_data['stats']['transactionCount'] > 0 else 0.0
        self.proof_response.uniqueness = self._calculate_uniqueness_score(has_existing)

        # Calculate overall score (0-1) which is used to reward the user
        # User is rewarded in tokens using this formula:
        # score * REWARD_FACTOR = NUMBER OF TOKENS
        # REWARD_FACTOR = The factor used to calculate file rewards. (E.g. **2e18** => the reward multiplier is 2)
        # Calculate points
        reward_data = self.calculate_reward_points(fresh_data['stats'])

        # Convert points to score (0-1 range)

        # Update this if max points change
        MAX_POSSIBLE_POINTS = 630

        self.proof_response.score = min(reward_data['total_points'] / MAX_POSSIBLE_POINTS, 1.0)

        # Store points breakdown in attributes
        self.proof_response.attributes = {
            'account_id_hash': fresh_data['user']['id_hash'],
            'transaction_count': fresh_data['stats']['transactionCount'],
            'total_volume': fresh_data['stats']['totalVolume'],
            'data_validated': matches,
            'activity_period_days': fresh_data['stats']['activityPeriodDays'],
            'unique_assets': len(fresh_data['stats']['uniqueAssets']),
            'previously_contributed': has_existing,
            'times_rewarded': existing_data['times_rewarded'] if existing_data else 0,
            'points': reward_data['total_points'],
            'points_breakdown': reward_data['breakdown']
        }

        self.proof_response.valid = (
                matches and
                not has_existing  # Only valid if this is first contribution
        )

        # Add validation details to attributes
        self.proof_response.attributes = {
            'account_id_hash': fresh_data['user']['id_hash'],
            'transaction_count': fresh_data['stats']['transactionCount'],
            'total_volume': fresh_data['stats']['totalVolume'],
            'data_validated': matches,
            'activity_period_days': fresh_data['stats']['activityPeriodDays'],
            'unique_assets': len(fresh_data['stats']['uniqueAssets']),
            'previously_contributed': has_existing,
            'times_rewarded': existing_data['times_rewarded'] if existing_data else 0
        }

        self.proof_response.metadata = {
            'dlp_id': self.config['dlp_id'],
            'version': '1.0.1'
        }

        # Store contribution data
        self._store_contribution(
            fresh_data['user']['id_hash'],
            fresh_data['stats'],
            self.proof_response,
        )

        return self.proof_response

    def calculate_reward_points(self, stats: dict) -> dict:
        """Calculate reward points based on various criteria"""
        points = 0
        breakdown = {}

        # Trading volume points
        volume = stats['totalVolume']
        if volume >= 1_000_000:
            points += 500
            breakdown['volume'] = "500 (1M+ volume)"
        elif volume >= 100_000:
            points += 150
            breakdown['volume'] = "150 (100k+ volume)"
        elif volume >= 10_000:
            points += 50
            breakdown['volume'] = "50 (10k+ volume)"
        elif volume >= 1_000:
            points += 25
            breakdown['volume'] = "25 (1k+ volume)"
        elif volume >= 100:
            points += 5
            breakdown['volume'] = "5 (100+ volume)"

        # Portfolio diversity
        unique_assets = len(stats['uniqueAssets'])
        if unique_assets >= 5:
            points += 30
            breakdown['diversity'] = "30 (5+ assets)"
        elif unique_assets >= 3:
            points += 10
            breakdown['diversity'] = "10 (3-4 assets)"

        # Historical data
        days_active = stats['activityPeriodDays']
        if days_active >= 1095:  # 3 years
            points += 100
            breakdown['history'] = "100 (3+ years)"
        elif days_active >= 365:  # 1 year
            points += 50
            breakdown['history'] = "50 (1+ year)"

        # TODO: Implement other criteria once we have the data:
        # - Monthly trade frequency
        # - Loss recognition
        # - Active position rewards

        return {
            'total_points': points,
            'breakdown': breakdown
        }

    def _validate_data(self, saved_data: dict, fresh_data: dict) -> bool:
        """
        Compare saved data with fresh data from Coinbase.
        Focus on immutable properties that can't change between fetches.
        """
        try:
            # Compare hashed user ID
            saved_user_id = saved_data['user'].get('id')
            if saved_user_id:
                # Hash the saved ID if it's not already hashed
                saved_hash = (saved_user_id
                              if len(saved_user_id) == 64
                              else hashlib.sha256(saved_user_id.encode()).hexdigest())

                if saved_hash != fresh_data['user']['id_hash']:
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
            logging.error(f"Validation error: {str(e)}")
            return False