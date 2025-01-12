"""Application configuration and environment settings"""
from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class S3Settings(BaseModel):
    """S3 specific settings"""
    access_key_id: Optional[str] = Field(None, description="AWS access key ID")
    secret_access_key: Optional[str] = Field(None, description="AWS secret access key")
    region: str = Field(default="us-east-1", description="AWS region")

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    # Required settings
    POSTGRES_URL: str = Field(..., description="PostgreSQL connection URL")

    # Authentication - made optional with defaults
    COINBASE_TOKEN: Optional[str] = Field(default=None, description="Coinbase API access token")
    COINBASE_ENCRYPTED_REFRESH_TOKEN: Optional[str] = Field(default=None, description="Encrypted Coinbase refresh token")
    ENCRYPTION_KEY: Optional[str] = Field(default=None, description="Encryption key for the file")

    # Optional settings with defaults
    REWARD_FACTOR: int = Field(default=630, description="Token reward multiplier (x10^18)")
    MAX_POINTS: int = Field(default=630, description="Maximum possible points for scoring")

    # Optional context settings with defaults
    DLP_ID: Optional[int] = Field(default=13, description="Data Liquidity Pool ID")
    FILE_ID: Optional[int] = Field(default=0, description="File ID being processed")
    FILE_URL: Optional[str] = Field(
        default='https://coinbase-exports.s3.us-east-1.amazonaws.com/encrypted_1734838315613_coinbase_export_1734838314926.json',
        description="URL of the encrypted file"
    )
    JOB_ID: Optional[int] = Field(default=0, description="TEE job ID")
    OWNER_ADDRESS: Optional[str] = Field(
        default="0x34A3706B00B20C7AE4cff145Ab255e9E0818fE20",
        description="Owner's wallet address"
    )

    # File paths with defaults
    INPUT_DIR: str = Field(default="/input", description="Directory containing input files")
    OUTPUT_DIR: str = Field(default="/output", description="Directory for output files")

    # S3 credentials - all optional with defaults
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default='', description="AWS access key ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default='', description="AWS secret access key")
    AWS_REGION: str = Field(default="us-east-1", description="AWS region")

    @property
    def s3_settings(self) -> S3Settings:
        """Get S3 settings as a separate model"""
        return S3Settings(
            access_key_id=self.AWS_ACCESS_KEY_ID,
            secret_access_key=self.AWS_SECRET_ACCESS_KEY,
            region=self.AWS_REGION
        )

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        validate_default=True
    )

settings = Settings()