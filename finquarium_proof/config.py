"""Application configuration and environment settings"""
from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    # Required settings
    POSTGRES_URL: str = Field(..., description="PostgreSQL connection URL")
    COINBASE_TOKEN: str = Field(..., description="Coinbase API access token")

    # Optional settings with defaults
    REWARD_FACTOR: int = Field(632, description="Token reward multiplier (x10^18)")
    MAX_POINTS: int = Field(630, description="Maximum possible points for scoring")

    # Optional context settings - can be None if not provided
    DLP_ID: Optional[int] = Field(1234, description="Data Liquidity Pool ID")
    FILE_ID: Optional[int] = Field(0, description="File ID being processed")
    FILE_URL: Optional[str] = Field('', description="URL of the encrypted file")
    JOB_ID: Optional[int] = Field(0, description="TEE job ID")
    OWNER_ADDRESS: Optional[str] = Field("0x34A3706B00B20C7AE4cff145Ab255e9E0818fE20", description="Owner's wallet address")

    # Input/Output directories with defaults
    INPUT_DIR: str = Field("/input", description="Directory containing input files")
    OUTPUT_DIR: str = Field("/output", description="Directory for output files")

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True,

        # If you want to validate all env vars have appropriate prefix
        # env_prefix='FINQUARIUM_'
    )

settings = Settings()