import json
import logging
import os
import sys
import traceback
from typing import Dict, Any

from finquarium_proof.proof import Proof
from finquarium_proof.db import db

INPUT_DIR = os.environ.get('INPUT_DIR', '/input')
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', '/output')


logging.basicConfig(level=logging.INFO, format='%(message)s')

def load_config() -> Dict[str, Any]:
    """Load proof configuration from environment variables."""
    config = {
        'dlp_id': 1234,  # TODO: Update DLP after registration with DLP root network
        'input_dir': INPUT_DIR,
        'env_vars': dict(os.environ)  # Convert os.environ to a standard dictionary
    }
    logging.info(f"Using config: {json.dumps(config, indent=2)}")
    return config

def run() -> None:
    """Generate proofs for all input files."""
    try:
        # Initialize database connection
        db.init()

        config = load_config()
        input_files_exist = os.path.isdir(INPUT_DIR) and bool(os.listdir(INPUT_DIR))

        if not input_files_exist:
            raise FileNotFoundError(f"No input files found in {INPUT_DIR}")

        proof = Proof(config)
        proof_response = proof.generate()

        output_path = os.path.join(OUTPUT_DIR, "results.json")
        with open(output_path, 'w') as f:
            json.dump(proof_response.dict(), f, indent=2)
        logging.info(f"Proof generation complete: {proof_response}")

    except Exception as e:
        logging.error(f"Error during proof generation: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run()