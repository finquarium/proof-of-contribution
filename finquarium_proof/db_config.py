# finquarium_proof/db_config.py
"""Database configuration and credentials management for TEE"""
from dataclasses import dataclass
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from urllib.parse import urlparse

from finquarium_proof.config import settings

# Network-specific database configurations
MAINNET_CONFIG = {
    'HOST': 'ep-old-dew-a5puhh9f.us-east-2.aws.neon.tech',
    'PORT': '5432',
    'NAME': 'finquarium',
    'USER': 'finquarium-admin',
    'SSL_MODE': 'require'
}

TESTNET_CONFIG = {
    'HOST': 'ep-old-dew-a5puhh9f.us-east-2.aws.neon.tech',
    'PORT': '5432',
    'NAME': 'finquarium-dev',
    'USER': 'finquarium-dev_owner',
    'SSL_MODE': 'require'
}

LOCAL_CONFIG = {
    'HOST': 'localhost',
    'PORT': '5432',
    'NAME': 'finquarium',
    'USER': 'finquarium',
    'SSL_MODE': 'disable'
}

def determine_network_config() -> dict:
    """Determine database configuration based on DLP_ID."""
    if not settings.DLP_ID:
        raise ValueError("DLP_ID setting is required")

    if settings.DLP_ID == 13:
        return MAINNET_CONFIG
    elif settings.DLP_ID == 25:
        return TESTNET_CONFIG
    elif settings.DLP_ID == 0:
        return LOCAL_CONFIG
    else:
        raise ValueError(f"Invalid DLP_ID {settings.DLP_ID}. Must be 13 (mainnet) or 25 (testnet) or 0 (local)")

# Select configuration based on DLP_ID
DB_CONFIG = determine_network_config()

@dataclass
class DatabaseCredentials:
    """Database credentials container with validation"""
    host: str
    port: str
    name: str
    user: str
    password: str
    ssl_mode: str = 'require'

    def to_connection_string(self) -> str:
        """Generate database connection string with proper escaping"""
        return (
            f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/"
            f"{self.name}?sslmode={self.ssl_mode}"
        )

    @classmethod
    def from_config(cls, password: str) -> 'DatabaseCredentials':
        """Create credentials from config and provided password"""
        return cls(
            host=DB_CONFIG['HOST'],
            port=DB_CONFIG['PORT'],
            name=DB_CONFIG['NAME'],
            user=DB_CONFIG['USER'],
            password=password,
            ssl_mode=DB_CONFIG['SSL_MODE']
        )

    @classmethod
    def validate_url(cls, url: str) -> bool:
        """Validate database URL format and parameters"""
        try:
            parsed = urlparse(url)
            if parsed.scheme != 'postgresql':
                return False

            # Validate hostname matches config
            if parsed.hostname != DB_CONFIG['HOST']:
                return False

            # Validate port matches config
            if str(parsed.port) != DB_CONFIG['PORT']:
                return False

            # Validate database name matches config
            path = parsed.path.lstrip('/')
            if path != DB_CONFIG['NAME']:
                return False

            # Validate username matches config
            if parsed.username != DB_CONFIG['USER']:
                return False

            return True
        except Exception:
            return False

class DatabasePasswordEncryption:
    """Handles encryption of database passwords for TEE"""

    @staticmethod
    def encrypt_password(
            password: str,
            public_key_path: str,
            proof_url: str
    ) -> str:
        """
        Encrypt database password for TEE with proof URL binding

        Args:
            password: Database password to encrypt
            public_key_path: Path to TEE public key PEM file
            proof_url: URL of proof that will use this password

        Returns:
            Hex string of encrypted password
        """
        # Read TEE public key
        with open(public_key_path, 'rb') as key_file:
            public_key = serialization.load_pem_public_key(key_file.read())

        # Bind password to proof URL
        protected_secret = f"{password}::proof_url::{proof_url}"

        # Encrypt the password
        encrypted = public_key.encrypt(
            protected_secret.encode(),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        return encrypted.hex()

class DatabaseManager:
    """Manages database connections in TEE environment"""

    @staticmethod
    def get_connection_string(db_password: str) -> str:
        """
        Generate database connection string from config and password

        Args:
            db_password: Decrypted database password

        Returns:
            Complete database connection string
        """
        credentials = DatabaseCredentials.from_config(db_password)
        return credentials.to_connection_string()

    @classmethod
    def initialize_from_env(cls) -> str:
        """
        Initialize database connection from environment variables

        Returns:
            Database connection string

        Raises:
            ValueError: If required environment variables are missing
        """
        if not settings.DB_PASSWORD:
            raise ValueError("DB_PASSWORD setting is required")

        return cls.get_connection_string(settings.DB_PASSWORD)
