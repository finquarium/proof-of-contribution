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


from finquarium_proof.config import Settings
from finquarium_proof.models.proof import ProofResponse
from finquarium_proof.services.coinbase import CoinbaseAPI
from finquarium_proof.services.storage import StorageService
from finquarium_proof.services.insights import MarketInsightsService
from finquarium_proof.models.insights import MarketInsights, InsightsMetadata, MarketExperience, Strategy, Psychology, Contact
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
        self.session = db.get_session()
        self.storage = StorageService(self.session)

        # Initialize Coinbase client only if token is provided
        self.coinbase = CoinbaseAPI(settings.COINBASE_TOKEN) if settings.COINBASE_TOKEN else None

        # Initialize S3 client only if credentials are provided
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
        else:
            self.s3_client = None

        self.gpg = gnupg.GPG()

    def __del__(self):
        """Cleanup database session"""
        if hasattr(self, 'session'):
            self.session.close()

    def _load_and_validate_user_id_hash(self) -> Tuple[str, str]:
        """Load and validate hashed user ID from saved file"""
        if not self.coinbase:
            raise ValueError("Coinbase client not initialized - token missing")

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

                # If no encryption key provided, just return checksums
                if not self.settings.ENCRYPTION_KEY:
                    logger.warning("No encryption key provided, skipping encryption")
                    return decrypted_checksum, decrypted_checksum

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

                # Skip S3 upload if no client
                if not self.s3_client:
                    logger.warning("No S3 client configured, skipping upload")
                    return encrypted_checksum, decrypted_checksum

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
            logger.error(f"Error in _encrypt_and_upload: {e}")
            if not self.s3_client:
                return decrypted_checksum, decrypted_checksum
            raise

    def _detect_submission_type(self, data: dict) -> str:
        """Detect if submission is market insights or coinbase data"""
        if 'user' in data and 'id_hash' in data['user']:
            return 'coinbase'
        elif 'metadata' in data and 'expertise' in data:
            return 'insights'
        else:
            raise ValueError("Unknown submission type")

    def _process_market_insights(self, data: dict, file_url: str) -> ProofResponse:
        """Process market insights submission"""
        try:
            # Parse insights data
            insights = MarketInsights(
                metadata=InsightsMetadata(**data['metadata']),
                expertise=MarketExperience(**data['expertise']),
                strategy=Strategy(**data['strategy']),
                psychology=Psychology(**data['psychology']),
                contact=Contact(**data['contact']) if 'contact' in data else None
            )

            # Encrypt full data and update file in S3
            encrypted_checksum, decrypted_checksum = self._encrypt_and_upload(
                data,
                file_url
            )

            # Store submission
            insights_service = MarketInsightsService(self.session)
            insights_service.store_submission(
                insights=insights,
                file_id=self.settings.FILE_ID or 0,
                owner_address=self.settings.OWNER_ADDRESS or '',
                file_url=file_url,
                file_checksum=decrypted_checksum
            )

            # Create proof response - valid but with 0 score since it's insights only
            return ProofResponse(
                dlp_id=self.settings.DLP_ID or 0,
                valid=True,
                score=0.0,  # Market insights don't contribute to DLP score
                authenticity=1.0,  # Data is authentic since it's signed by user
                ownership=1.0,  # Ownership verified through wallet signature
                quality=1.0,  # Quality is binary - valid submission
                uniqueness=1.0,  # Each insights submission is unique
                attributes={
                    'submission_type': 'market_insights',
                    'base_points': insights.metadata.basePoints,
                    'prediction_points': insights.metadata.predictionPoints,
                    'total_points': insights.metadata.basePoints + insights.metadata.predictionPoints,
                    'expertise_markets': len(insights.expertise.marketExperience),
                    'strategy_indicators': len(insights.strategy.technicalIndicators),
                    'contact_provided': insights.contact is not None
                },
                metadata={
                    'dlp_id': self.settings.DLP_ID or 0,
                    'version': insights.metadata.version,
                    'file_id': self.settings.FILE_ID or 0,
                    'job_id': self.settings.JOB_ID or '',
                    'owner_address': self.settings.OWNER_ADDRESS or '',
                    'submission_type': 'market_insights',
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

        except Exception as e:
            logger.error(f"Error processing market insights: {e}")
            raise

    def _process_coinbase_data(self, data: dict, file_url: str) -> ProofResponse:
        """Process coinbase trading data submission"""
        try:
            if not self.coinbase:
                raise ValueError("Cannot process Coinbase data - client not initialized")

            # Validate user ID ownership
            user_id, file_url = self._load_and_validate_user_id_hash()

            # Fetch fresh data from Coinbase
            fresh_data = self.coinbase.get_formatted_history()

            # Check for existing contribution
            has_existing, existing_data = self.storage.check_existing_contribution(
                fresh_data.account_id_hash
            )

            # Calculate validity:
            # - Must have valid user ID (already checked)
            # - Must have transactions
            # - Must not have been previously rewarded
            # - Account must be at least 30 days old
            is_valid = (
                    fresh_data.stats.transaction_count > 0 and
                    not has_existing and
                    fresh_data.stats.activity_period_days >= 30  # Minimum account age requirement
            )

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

            # Encrypt full data and update file in S3
            encrypted_checksum, decrypted_checksum = self._encrypt_and_upload(
                fresh_data.raw_data,
                file_url
            )

            # Create proof response
            proof_response = ProofResponse(
                dlp_id=self.settings.DLP_ID or 0,
                valid=is_valid,
                score=score,
                authenticity=1.0,  # Data is fresh from Coinbase
                ownership=1.0,  # Verified through user ID
                quality=1.0 if fresh_data.stats.transaction_count > 0 else 0.0,
                uniqueness=0.0 if has_existing else 1.0,
                attributes={
                    'submission_type': 'coinbase_trading',
                    'account_id_hash': fresh_data.account_id_hash,
                    'transaction_count': fresh_data.stats.transaction_count,
                    'total_volume': fresh_data.stats.total_volume,
                    'data_validated': True,
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
                    'owner_address': self.settings.OWNER_ADDRESS or '',
                    'submission_type': 'coinbase_trading',
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

            # Store contribution if score > 0
            if score > 0:
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
            logger.error(f"Error processing Coinbase data: {e}")
            raise

    def generate(self) -> ProofResponse:
        """Generate proof by verifying user ID and fetching fresh data"""
        try:
            # Load decrypted data
            for filename in os.listdir(self.settings.INPUT_DIR):
                if os.path.splitext(filename)[1].lower() == '.json':
                    file_path = os.path.join(self.settings.INPUT_DIR, filename)
                    with open(file_path, 'r') as f:
                        data = json.load(f)

            # Detect submission type and process accordingly
            submission_type = self._detect_submission_type(data)
            if submission_type == 'insights':
                return self._process_market_insights(data, self.settings.FILE_URL)
            else:
                return self._process_coinbase_data(data, self.settings.FILE_URL)

        except Exception as e:
            logger.error(f"Error generating proof: {e}")
            raise