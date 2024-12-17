#!/bin/bash

# Activate virtual environment
source venv/bin/activate

# Set environment variables
export POSTGRES_URL="postgresql://finquarium:finquarium@localhost:5432/finquarium"
export COINBASE_TOKEN="${COINBASE_TOKEN:-your_test_token_here}"

# Create test directories if they don't exist
mkdir -p test_input test_output

# Run the proof with test data
PYTHONPATH=. python -m finquarium_proof