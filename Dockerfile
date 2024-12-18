FROM python:3.12-slim

WORKDIR /app

# Install dependencies required for psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Make sure input/output directories exist
RUN mkdir -p /input /output

CMD ["python", "-m", "finquarium_proof"]