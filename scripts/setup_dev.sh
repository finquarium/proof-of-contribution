#!/bin/bash
set -e

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r dev-requirements.txt

# Start PostgreSQL with docker-compose
docker-compose -f docker-compose.dev.yml up -d

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
until PGPASSWORD=finquarium psql -h localhost -U finquarium -d finquarium -c '\q' 2>/dev/null; do
  sleep 1
done
echo "PostgreSQL is ready!"