"""Application configuration and environment settings"""
from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class S3Settings(BaseModel):
    """S3 specific settings"""
    access_key_id: str = Field(..., description="AWS access key ID")
    secret_access_key: str = Field(..., description="AWS secret access key")
    region: str = Field(..., description="AWS region")

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    # Required settings
    DB_PASSWORD: str = Field(..., description="Database password")

    # Coinbase settings
    COINBASE_TOKEN: Optional[str] = Field(None, description="Coinbase API access token")
    COINBASE_ENCRYPTED_REFRESH_TOKEN: Optional[str] = Field(None, description="Encrypted Coinbase refresh token")

    # Binance settings
    BINANCE_API_KEY: Optional[str] = Field(None, description="Binance API key")
    BINANCE_API_SECRET: Optional[str] = Field(None, description="Binance API secret")

    # Proxy settings
    PROXY_URL: Optional[str] = Field(None, description="Proxy URL")
    PROXY_API_KEY: Optional[str] = Field(None, description="Proxy API key")

    ENCRYPTION_KEY: Optional[str] = Field(..., description="Encryption key for the file")

    # S3 credentials
    AWS_ACCESS_KEY_ID: str = Field(..., description="AWS access key ID")
    AWS_SECRET_ACCESS_KEY: str = Field(..., description="AWS secret access key")
    AWS_REGION: str = Field(default="us-east-1", description="AWS region")

    # Proof settings
    MAX_POINTS: int = 630

    # Optional context settings - can be None if not provided
    DLP_ID: Optional[int] = Field(25, description="Data Liquidity Pool ID")
    FILE_ID: Optional[int] = Field(0, description="File ID being processed")
    FILE_URL: Optional[str] = Field('https://coinbase-exports.s3.us-east-1.amazonaws.com/encrypted_1734838315613_coinbase_export_1734838314926.json', description="URL of the encrypted file")
    JOB_ID: Optional[int] = Field(0, description="TEE job ID")
    OWNER_ADDRESS: Optional[str] = Field("0x34A3706B00B20C7AE4cff145Ab255e9E0818fE20", description="Owner's wallet address")

    # Input/Output directories with defaults
    INPUT_DIR: str = Field("/input", description="Directory containing input files")
    OUTPUT_DIR: str = Field("/output", description="Directory for output files")

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
        case_sensitive=True
    )

settings = Settings()