"""Entry point for proof generation"""
import json
import logging
import os
import sys
import traceback

from finquarium_proof.config import settings
from finquarium_proof.proof import Proof
from finquarium_proof.db import db

# Allow overriding input/output directories through env vars
INPUT_DIR = os.environ.get('INPUT_DIR', '/input')
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', '/output')

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def run() -> None:
    """Generate proofs for all input files."""
    try:
        # Initialize database connection
        db.init()

        # Validate input directory
        if not os.path.isdir(INPUT_DIR) or not os.listdir(INPUT_DIR):
            raise FileNotFoundError(f"No input files found in {INPUT_DIR}")

        # Log config (excluding sensitive data)
        logger.info("Using configuration:")
        safe_config = settings.model_dump(exclude={'COINBASE_TOKEN', 'POSTGRES_URL'})
        logger.info(json.dumps(safe_config, indent=2))

        # Initialize and run proof generation
        proof = Proof(settings)
        proof_response = proof.generate()

        # Save results
        output_path = os.path.join(OUTPUT_DIR, "results.json")
        with open(output_path, 'w') as f:
            json.dump(proof_response.model_dump(), f, indent=2)

        logger.info(f"Proof generation complete: {proof_response.model_dump()}")

    except Exception as e:
        logger.error(f"Error during proof generation: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run()