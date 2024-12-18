"""Main proof generation logic"""
import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any

from finquarium_proof.config import Settings
from finquarium_proof.models.proof import ProofResponse
from finquarium_proof.services.coinbase import CoinbaseAPI
from finquarium_proof.services.storage import StorageService
from finquarium_proof.scoring import ContributionScorer
from finquarium_proof.db import db

logger = logging.getLogger(__name__)

class Proof:
    """Handles proof generation and validation"""

    def __init__(self, settings: Settings):
        """Initialize proof generator with settings"""
        self.settings = settings
        self.scorer = ContributionScorer()
        self.storage = StorageService(db.get_session())
        self.coinbase = CoinbaseAPI(settings.COINBASE_TOKEN)

    def _load_decrypted_data(self) -> Dict[str, Any]:
        """Load and parse decrypted JSON data from input directory"""
        for filename in os.listdir(self.settings.INPUT_DIR):
            if os.path.splitext(filename)[1].lower() == '.json':
                file_path = os.path.join(self.settings.INPUT_DIR, filename)
                with open(file_path, 'r') as f:
                    return json.load(f)
        raise FileNotFoundError("No decrypted JSON file found in input directory")

    def generate(self) -> ProofResponse:
        """Generate proof by comparing decrypted file with fresh Coinbase data"""
        try:
            # Load decrypted file
            decrypted_data = self._load_decrypted_data()

            # Fetch fresh data from Coinbase
            fresh_data = self.coinbase.get_formatted_history()

            # Check for existing contribution
            has_existing, existing_data = self.storage.check_existing_contribution(
                fresh_data.account_id_hash
            )

            # Compare data for authenticity
            matches = self._validate_data(decrypted_data, fresh_data.raw_data)

            # Calculate validity - only valid if data matches and this is first contribution
            is_valid = matches and not has_existing

            # If not valid, score should be 0
            if not is_valid:
                score = 0
                points = 0
                points_breakdown = {
                    'volume': '0 (invalid contribution)',
                    'diversity': '0 (invalid contribution)',
                    'history': '0 (invalid contribution)'
                }
            else:
                # Calculate scores for valid contribution
                points_breakdown = self.scorer.calculate_score(fresh_data.stats)
                points = points_breakdown.total_points
                score = self.scorer.normalize_score(points_breakdown.total_points, self.settings.MAX_POINTS)

            # Create proof response
            proof_response = ProofResponse(
                dlp_id=self.settings.DLP_ID or 0,
                valid=is_valid,
                score=score,
                authenticity=1.0 if matches else 0.0,
                ownership=1.0,  # Proven by valid Coinbase token
                quality=1.0 if fresh_data.stats.transaction_count > 0 else 0.0,
                uniqueness=0.0 if has_existing else 1.0,
                attributes={
                    'account_id_hash': fresh_data.account_id_hash,
                    'transaction_count': fresh_data.stats.transaction_count,
                    'total_volume': fresh_data.stats.total_volume,
                    'data_validated': matches,
                    'activity_period_days': fresh_data.stats.activity_period_days,
                    'unique_assets': len(fresh_data.stats.unique_assets),
                    'previously_contributed': has_existing,
                    'times_rewarded': existing_data.times_rewarded if existing_data else 0,
                    'points': points,
                    'points_breakdown': points_breakdown
                },
                metadata={
                    'dlp_id': self.settings.DLP_ID or 0,
                    'version': '1.0.0',
                    'file_id': self.settings.FILE_ID or 0,
                    'job_id': self.settings.JOB_ID or '',
                    'owner_address': self.settings.OWNER_ADDRESS or ''
                }
            )

            # Store contribution if score > 0
            if score > 0:
                self.storage.store_contribution(
                    fresh_data,
                    proof_response,
                    self.settings.FILE_ID or 0,
                    self.settings.FILE_URL or '',
                    self.settings.JOB_ID or '',
                    self.settings.OWNER_ADDRESS or ''
                )

            return proof_response

        except Exception as e:
            logger.error(f"Error generating proof: {e}")
            raise

    def _validate_data(self, saved_data: dict, fresh_data: dict) -> bool:
        """
        Compare saved data with fresh data.
        We validate by matching transaction properties since fresh data doesn't have IDs.
        """
        try:
            logger.debug(f"Validating data:\nSaved: {saved_data}\nFresh: {fresh_data}")

            # Check transaction counts match
            saved_txs = saved_data.get('transactions', [])
            fresh_txs = fresh_data.get('transactions', [])

            if len(saved_txs) != len(fresh_txs):
                logger.warning(f"Transaction count mismatch: saved={len(saved_txs)}, fresh={len(fresh_txs)}")
                return False

            # Sort both lists by timestamp and type to ensure same order
            saved_txs = sorted(saved_txs, key=lambda x: (x.get('timestamp', ''), x.get('type', '')))
            fresh_txs = sorted(fresh_txs, key=lambda x: (x.get('timestamp', ''), x.get('type', '')))

            # Compare each transaction's immutable properties
            for saved_tx, fresh_tx in zip(saved_txs, fresh_txs):
                # Compare key properties with tolerance for floating point values
                if not self._match_transactions(saved_tx, fresh_tx):
                    logger.warning(f"Transaction mismatch:\nSaved: {saved_tx}\nFresh: {fresh_tx}")
                    return False

            # Compare statistics
            if not self._match_stats(saved_data.get('stats', {}), fresh_data.get('stats', {})):
                return False

            return True

        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            return False

    def _match_transactions(self, saved_tx: dict, fresh_tx: dict) -> bool:
        """Compare individual transactions for matching properties"""
        try:
            # Parse timestamps to compare datetime values
            saved_time = datetime.strptime(saved_tx['timestamp'], "%Y-%m-%dT%H:%M:%SZ")
            fresh_time = fresh_tx['timestamp'] if isinstance(fresh_tx['timestamp'], datetime) else datetime.strptime(fresh_tx['timestamp'], "%Y-%m-%dT%H:%M:%SZ")

            return (
                    saved_tx['type'] == fresh_tx['type'] and
                    saved_tx['asset'] == fresh_tx['asset'] and
                    abs(float(saved_tx['quantity']) - float(fresh_tx['quantity'])) < 1e-8 and
                    abs(float(saved_tx['native_amount']) - float(fresh_tx['native_amount'])) < 1e-8 and
                    saved_time == fresh_time
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error matching transactions: {e}")
            return False

    def _match_stats(self, saved_stats: dict, fresh_stats: dict) -> bool:
        """Compare statistics with tolerance for floating point values"""
        try:
            # Normalize stats keys
            saved_volume = float(saved_stats.get('totalVolume', 0))
            fresh_volume = float(fresh_stats.get('total_volume', 0))

            saved_count = int(saved_stats.get('transactionCount', 0))
            fresh_count = int(fresh_stats.get('transaction_count', 0))

            saved_assets = set(saved_stats.get('uniqueAssets', []))
            fresh_assets = set(fresh_stats.get('unique_assets', []))

            # Compare with appropriate tolerances
            volume_matches = abs(saved_volume - fresh_volume) < 1e-8
            count_matches = saved_count == fresh_count
            assets_match = saved_assets == fresh_assets

            if not all([volume_matches, count_matches, assets_match]):
                logger.warning(
                    f"Stats mismatch:\n"
                    f"Volume: {saved_volume} vs {fresh_volume} - {volume_matches}\n"
                    f"Count: {saved_count} vs {fresh_count} - {count_matches}\n"
                    f"Assets: {saved_assets} vs {fresh_assets} - {assets_match}"
                )
                return False

            return True

        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error matching stats: {e}")
            return False