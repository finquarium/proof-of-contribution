#!/bin/bash
set -e

# Activate virtual environment
source venv/bin/activate

# Set environment variables
export POSTGRES_URL="postgresql://finquarium:finquarium@localhost:5432/finquarium"
export COINBASE_TOKEN="${COINBASE_TOKEN:-your_test_token_here}"
export INPUT_DIR="./input"
export OUTPUT_DIR="./output"

# Run the proof with test data
PYTHONPATH=. python -m finquarium_proof