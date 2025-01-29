"""Entry point for proof generation"""
import json
import logging
import os
import sys
import traceback
from pathlib import Path

from finquarium_proof.config import settings
from finquarium_proof.proof import Proof
from finquarium_proof.db import db
from finquarium_proof.models.contribution import ContributionType

# Allow overriding input/output directories through env vars
INPUT_DIR = os.environ.get('INPUT_DIR', '/input')
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', '/output')

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def determine_contribution_type() -> ContributionType:
    """
    Determine contribution type based on input directory contents.
    Default to Coinbase for backward compatibility.
    """
    input_dir = Path(settings.INPUT_DIR)

    # TODO: This should come from a request
    has_zip = any(input_dir.glob("*.zip"))

    if has_zip:
        return ContributionType.BINANCE

    # Default to Coinbase
    return ContributionType.COINBASE

def run() -> None:
    """Generate proofs for all input files."""
    try:
        # Initialize database connection
        db.init()

        # Validate input directory
        if not os.path.isdir(settings.INPUT_DIR) or not os.listdir(settings.INPUT_DIR):
            raise FileNotFoundError(f"No input files found in {settings.INPUT_DIR}")

        # Determine contribution type
        contribution_type = determine_contribution_type()
        logger.info(f"Processing {contribution_type.value} contribution")

        # Log config (excluding sensitive data)
        safe_config = settings.model_dump(exclude={'COINBASE_TOKEN', 'POSTGRES_URL'})
        logger.info("Using configuration:")
        logger.info(json.dumps(safe_config, indent=2))

        # Initialize and run proof generation
        proof = Proof(settings)
        proof_response = proof.generate(contribution_type)

        # Save results
        output_path = os.path.join(settings.OUTPUT_DIR, "results.json")
        with open(output_path, 'w') as f:
            json.dump(proof_response.model_dump(), f, indent=2)

        logger.info(f"Proof generation complete: {proof_response.model_dump()}")

    except Exception as e:
        logger.error(f"Error during proof generation: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run()