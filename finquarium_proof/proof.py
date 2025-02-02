"""Main proof generation logic"""
import hashlib
import json
import logging
import os
from typing import Dict, Any, Tuple
import tempfile
import gnupg
import boto3
from urllib.parse import urlparse


from finquarium_proof.config import Settings, MAX_POINTS
from finquarium_proof.models.proof import ProofResponse
from finquarium_proof.models.contribution import ContributionType, TradingStats, ContributionData, Transaction
from finquarium_proof.models.binance import BinanceValidationData
from .services.coinbase import CoinbaseAPI
from finquarium_proof.services.binance import BinanceValidator
from finquarium_proof.services.storage import StorageService
from finquarium_proof.scoring import ContributionScorer
from finquarium_proof.db import db
from finquarium_proof.utils.json_encoder import DateTimeEncoder

logger = logging.getLogger(__name__)

class Proof:
    """Handles proof generation and validation"""

    def __init__(self, settings: Settings):
        """Initialize proof generator with settings"""
        self.settings = settings
        self.scorer = ContributionScorer()
        self.storage = StorageService(db.get_session())
        self.s3_client = boto3.client('s3')
        self.gpg = gnupg.GPG()

        # Initialize API clients based on provided credentials
        if self.settings.COINBASE_TOKEN:
            self.coinbase = CoinbaseAPI(self.settings.COINBASE_TOKEN)
        else:
            self.coinbase = None

        if self.settings.BINANCE_API_KEY and self.settings.BINANCE_API_SECRET:
            self.binance_validator = BinanceValidator(
                self.settings.BINANCE_API_KEY,
                self.settings.BINANCE_API_SECRET,
                self.settings.PROXY_URL,
                self.settings.PROXY_API_KEY,
            )
        else:
            self.binance_validator = None

    def _load_and_validate_user_id_hash(self) -> Tuple[str, str]:
        """Load and validate hashed user ID from saved file"""
        if not self.coinbase:
            raise ValueError("Coinbase credentials not provided")

        for filename in os.listdir(self.settings.INPUT_DIR):
            if os.path.splitext(filename)[1].lower() == '.json':
                file_path = os.path.join(self.settings.INPUT_DIR, filename)
                with open(file_path, 'r') as f:
                    saved_data = json.load(f)

                # Extract hashed user ID from saved data
                saved_user_id_hash = saved_data.get('user', {}).get('id_hash')
                if not saved_user_id_hash:
                    raise ValueError("No hashed user ID found in saved data")

                # Get fresh user info and hash it
                fresh_user = self.coinbase.get_user_info()['data']
                fresh_user_id_hash = hashlib.sha256(fresh_user['id'].encode()).hexdigest()

                if saved_user_id_hash != fresh_user_id_hash:
                    print(f"Saved: {saved_user_id_hash}")
                    print(f"Fresh: {fresh_user_id_hash}")
                    raise ValueError("User ID hash mismatch")

                return saved_user_id_hash, self.settings.FILE_URL

        raise FileNotFoundError("No decrypted JSON file found in input directory")

    def calculate_checksum(self, path: str) -> str:
        """Calculate SHA256 checksum of a file."""
        checksum = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                checksum.update(chunk)
        return checksum.hexdigest()

    def _encrypt_and_upload(self, data: Dict[str, Any], s3_url: str) -> Tuple[str, str]:
        """
        Encrypt data using GPG and upload to S3.

        Returns:
            Tuple[str, str]: (encrypted_checksum, decrypted_checksum)
        """
        try:
            # Create temporary directory for file operations
            with tempfile.TemporaryDirectory() as temp_dir:
                # Write data to temporary file
                unencrypted_path = os.path.join(temp_dir, "data.json")
                with open(unencrypted_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, cls=DateTimeEncoder)

                # Calculate decrypted checksum
                decrypted_checksum = self.calculate_checksum(unencrypted_path)

                # Encrypt the file using GPG
                encrypted_path = os.path.join(temp_dir, "encrypted_data")
                with open(unencrypted_path, 'rb') as f:
                    status = self.gpg.encrypt_file(
                        fileobj_or_path=f,
                        recipients='',
                        output=encrypted_path,
                        passphrase=self.settings.ENCRYPTION_KEY,
                        armor=False,
                        symmetric=True
                    )

                if not status.ok:
                    raise Exception(f"Encryption failed: {status.status}")

                # Calculate encrypted checksum
                encrypted_checksum = self.calculate_checksum(encrypted_path)

                # Parse S3 URL
                s3_url_parsed = urlparse(s3_url)
                bucket = s3_url_parsed.netloc.split('.')[0]
                key = s3_url_parsed.path.lstrip('/')

                # Upload encrypted file to S3
                with open(encrypted_path, 'rb') as f:
                    self.s3_client.put_object(
                        Bucket=bucket,
                        Key=key,
                        Body=f,
                        ContentType='application/octet-stream',
                        ACL='public-read'
                    )
                logger.info(f"Successfully uploaded encrypted file to s3://{bucket}/{key}")

                return encrypted_checksum, decrypted_checksum

        except Exception as e:
            logger.error(f"Error encrypting and uploading file: {e}")
            raise

    def _convert_binance_to_contribution_data(self, validation_data: BinanceValidationData) -> ContributionData:
        """Convert BinanceValidationData to ContributionData for storage compatibility"""

        # Convert BinanceTransactions to common Transaction format
        transactions = []
        for tx in validation_data.transactions:
            transactions.append(Transaction(
                type='trade',
                asset=tx.symbol,
                quantity=float(tx.quantity),
                native_amount=float(tx.amount),
                timestamp=tx.timestamp
            ))

        # Create TradingStats from validation data
        stats = TradingStats(
            total_volume=float(validation_data.total_volume),
            transaction_count=len(validation_data.transactions),
            unique_assets=list(set(tx.symbol for tx in validation_data.transactions)),
            activity_period_days=(validation_data.end_time - validation_data.start_time).days,
            first_transaction_date=validation_data.start_time,
            last_transaction_date=validation_data.end_time
        )

        # Create raw data structure matching Coinbase format
        raw_data = {
            'user': {
                'id_hash': validation_data.account_id_hash
            },
            'stats': stats.__dict__,
            'transactions': [tx.__dict__ for tx in transactions]
        }

        return ContributionData(
            account_id_hash=validation_data.account_id_hash,
            stats=stats,
            transactions=transactions,
            raw_data=raw_data,
            contribution_type=ContributionType.BINANCE,
            first_transaction_date=validation_data.start_time,
            last_transaction_date=validation_data.end_time
        )

    def generate(self, contribution_type: ContributionType = ContributionType.COINBASE) -> ProofResponse:
        """Generate proof by verifying user ID and fetching fresh data"""
        if contribution_type == ContributionType.COINBASE:
            if not self.coinbase:
                raise ValueError("Coinbase credentials not provided")
            return self._generate_coinbase_proof()
        elif contribution_type == ContributionType.BINANCE:
            if not self.binance_validator:
                raise ValueError("Binance credentials not provided")
            return self._generate_binance_proof()
        else:
            raise ValueError(f"Unsupported contribution type: {contribution_type}")

    def _generate_coinbase_proof(self) -> ProofResponse:
        """Coinbase proof generation logic"""
        try:
            # Validate user ID ownership
            user_id, file_url = self._load_and_validate_user_id_hash()

            # Fetch fresh data from Coinbase
            fresh_data = self.coinbase.get_formatted_history()

            # Check for existing contribution
            has_existing, existing_data = self.storage.check_existing_contribution(
                fresh_data.account_id_hash
            )

            # Calculate fresh scores
            points_breakdown = self.scorer.calculate_score(fresh_data.stats)
            fresh_points = points_breakdown.total_points
            fresh_score = self.scorer.normalize_score(fresh_points, MAX_POINTS, not has_existing)

            # Initialize variables for differential scoring
            differential_points = fresh_points
            final_score = fresh_score
            previously_rewarded = False

            if has_existing:
                # Calculate points from previous contribution
                previous_points = int(existing_data.latest_score * MAX_POINTS)

                # Only count the additional points above previous contribution
                differential_points = max(0, fresh_points - previous_points)
                final_score = self.scorer.normalize_score(differential_points, MAX_POINTS, False)
                previously_rewarded = existing_data.times_rewarded > 0

            # Encrypt and update file in S3
            encrypted_checksum, decrypted_checksum = self._encrypt_and_upload(
                fresh_data.raw_data,
                file_url
            )

            # Create proof response with differential scoring
            proof_response = ProofResponse(
                dlp_id=self.settings.DLP_ID,
                valid=True,        # Always valid now, we just adjust the score
                score=final_score,
                authenticity=1.0,  # Data is fresh from Coinbase
                ownership=1.0,     # Verified through user ID
                quality=1.0 if fresh_data.stats.transaction_count > 0 else 0.0,
                uniqueness=1.0 if not has_existing else 0.99,
                attributes={
                    'account_id_hash': fresh_data.account_id_hash,
                    'transaction_count': fresh_data.stats.transaction_count,
                    'total_volume': float(fresh_data.stats.total_volume),
                    'data_validated': True,
                    'activity_period_days': fresh_data.stats.activity_period_days,
                    'unique_assets': len(fresh_data.stats.unique_assets),
                    'previously_contributed': has_existing,
                    'previously_rewarded': previously_rewarded,
                    'times_rewarded': existing_data.times_rewarded if existing_data else 0,
                    'total_points': fresh_points,
                    'differential_points': differential_points,
                    'points_breakdown': points_breakdown,
                },
                metadata={
                    'dlp_id': self.settings.DLP_ID or 0,
                    'version': '1.0.0',
                    'file_id': self.settings.FILE_ID or 0,
                    'job_id': self.settings.JOB_ID or '',
                    'owner_address': self.settings.OWNER_ADDRESS or '',
                    'file': {
                        'id': self.settings.FILE_ID or 0,
                        'source': 'TEE',
                        'url': file_url,
                        'checksums': {
                            'encrypted': encrypted_checksum,
                            'decrypted': decrypted_checksum
                        }
                    }
                }
            )

            # Store contribution if there are new points to award
            if differential_points > 0:
                self.storage.store_contribution(
                    fresh_data,
                    proof_response,
                    self.settings.FILE_ID or 0,
                    self.settings.FILE_URL or '',
                    self.settings.JOB_ID or '',
                    self.settings.OWNER_ADDRESS or '',
                    self.settings.COINBASE_ENCRYPTED_REFRESH_TOKEN or ''
                )

            return proof_response

        except Exception as e:
            logger.error(f"Error generating coinbase proof: {e}")
            raise

    def _generate_binance_proof(self) -> ProofResponse:
        """Generate proof for Binance contribution"""
        try:
            # Find zip file
            zip_file_path = None
            for filename in os.listdir(self.settings.INPUT_DIR):
                if filename.endswith('.zip'):
                    zip_file_path = os.path.join(self.settings.INPUT_DIR, filename)
                    break

            if not zip_file_path:
                raise FileNotFoundError("No zip file found in input directory")

            transactions = self.binance_validator.process_zip_file(zip_file_path)
            is_valid, message = self.binance_validator.validate_transactions(transactions)

            if not is_valid:
                raise ValueError(message)

            validation_data = self.binance_validator.calculate_rewards(transactions)

            # Convert validation data to contribution data format
            contribution_data = self._convert_binance_to_contribution_data(validation_data)

            # Check for existing contribution
            has_existing, existing_data = self.storage.check_existing_contribution(
                validation_data.account_id_hash
            )

            # Calculate fresh scores
            points_breakdown = self.scorer.calculate_score(contribution_data.stats)
            fresh_points = points_breakdown.total_points
            fresh_score = self.scorer.normalize_score(fresh_points, MAX_POINTS, not has_existing)

            # Initialize variables for differential scoring
            differential_points = fresh_points
            final_score = fresh_score
            previously_rewarded = False

            if has_existing:
                # Calculate points from previous contribution
                previous_points = int(existing_data.latest_score * MAX_POINTS)

                # Only count the additional points above previous contribution
                differential_points = max(0, fresh_points - previous_points)
                final_score = self.scorer.normalize_score(differential_points, MAX_POINTS, False)
                previously_rewarded = existing_data.times_rewarded > 0

            # Encrypt and upload data
            encrypted_checksum, decrypted_checksum = self._encrypt_and_upload(
                contribution_data.raw_data,
                self.settings.FILE_URL
            )

            proof_response = ProofResponse(
                dlp_id=self.settings.DLP_ID,
                valid=True,  # Always valid now, we just adjust the score
                score=final_score,
                authenticity=1.0,
                ownership=1.0,
                quality=1.0 if len(transactions) > 0 else 0.0,
                uniqueness=1.0 if not has_existing else 0.99,
                attributes={
                    'account_id_hash': validation_data.account_id_hash,
                    'transaction_count': len(transactions),
                    'total_volume': float(validation_data.total_volume),
                    'data_validated': True,
                    'activity_period_days': (validation_data.end_time - validation_data.start_time).days,
                    'unique_assets': len(contribution_data.stats.unique_assets),
                    'previously_contributed': has_existing,
                    'previously_rewarded': previously_rewarded,
                    'times_rewarded': existing_data.times_rewarded if existing_data else 0,
                    'total_points': fresh_points,
                    'differential_points': differential_points,
                    'points_breakdown': points_breakdown,
                    'checksums': {
                        'encrypted': encrypted_checksum,
                        'decrypted': decrypted_checksum
                    }
                },
                metadata={
                    'dlp_id': self.settings.DLP_ID or 0,
                    'version': '1.0.0',
                    'file_id': self.settings.FILE_ID or 0,
                    'job_id': self.settings.JOB_ID or '',
                    'owner_address': self.settings.OWNER_ADDRESS or '',
                    'file': {
                        'id': self.settings.FILE_ID or 0,
                        'source': 'TEE',
                        'url': self.settings.FILE_URL,
                        'checksums': {
                            'encrypted': encrypted_checksum,
                            'decrypted': decrypted_checksum
                        }
                    }
                }
            )

            # Store contribution if there are new points to award
            if differential_points > 0:
                self.storage.store_contribution(
                    contribution_data,
                    proof_response,
                    self.settings.FILE_ID or 0,
                    self.settings.FILE_URL or '',
                    self.settings.JOB_ID or '',
                    self.settings.OWNER_ADDRESS or '',
                    ''  # No refresh token for Binance
                )

            return proof_response

        except Exception as e:
            logger.error(f"Error generating Binance proof: {e}")
            raise
