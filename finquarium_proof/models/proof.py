"""ProofResponse model definition"""
from typing import Dict, Optional, Any
from pydantic import BaseModel

class ProofResponse(BaseModel):
    """
    Represents the response of a proof of contribution. 
    Only the score and metadata will be written onchain, the rest lives offchain.

    Onchain attributes:
        score: A score between 0 and 1 determining contribution value
        metadata: Additional proof metadata

    Offchain attributes:
        dlp_id: The DLP ID from the DLP Root Network contract
        valid: Boolean indicating if the file is valid for this DLP
        authenticity: Score 0-1 rating if file is tampered
        ownership: Score 0-1 verifying file ownership
        quality: Score 0-1 showing data quality
        uniqueness: Score 0-1 showing data uniqueness vs others
        attributes: Extra context about the encrypted file
    """
    dlp_id: int
    valid: bool = False
    score: float = 0.0
    authenticity: float = 0.0
    ownership: float = 0.0
    quality: float = 0.0
    uniqueness: float = 0.0
    attributes: Optional[Dict[str, Any]] = {}
    metadata: Optional[Dict[str, Any]] = {}