# Finquarium Proof of Contribution

A proof of contribution system for Finquarium's Data Liquidity Pool (DLP) that validates and rewards Coinbase trading history contributions while preserving user privacy through data hashing.

## Overview

The proof system validates that:
- Submitted data authentically matches Coinbase's records
- The contributor owns the data through valid Coinbase access token
- The contribution is unique (one reward per user)
- The data meets quality and completeness requirements

Privacy is protected by:
- Storing only hashed account IDs
- Exposing aggregate statistics only
- Anonymizing transaction data

### Reward System

Contribution scores are calculated based on:

#### Trading Volume
- $100+ trading volume = 5 points
- $1,000+ trading volume = 25 points
- $10,000+ trading volume = 50 points
- $100,000+ trading volume = 150 points
- $1,000,000+ trading volume = 500 points

#### Portfolio Diversity
- 3-4 assets = 10 points
- 5+ assets = 30 points

#### Historical Data
- 1+ year = 50 points
- 3+ years = 100 points

Final score is normalized to 0-1 range and multiplied by REWARD_FACTOR to determine token reward amount.

### Proof Output Format

```json
{
  "dlp_id": 1234,
  "valid": true,
  "score": 0.95,
  "authenticity": 1.0,
  "ownership": 1.0,
  "quality": 1.0,
  "uniqueness": 1.0,
  "attributes": {
    "account_id_hash": "hash_of_coinbase_account_id",
    "transaction_count": 157,
    "total_volume": 25000.50,
    "data_validated": true,
    "activity_period_days": 365,
    "unique_assets": 12,
    "previously_contributed": false,
    "times_rewarded": 0,
    "points": 175,
    "points_breakdown": {
      "volume": "150 (100k+ volume)",
      "diversity": "25 (5+ assets)",
      "history": "0 (< 1 year)"
    }
  },
  "metadata": {
    "dlp_id": 1234,
    "version": "1.0.0",
    "file_id": 5678,
    "job_id": "job-123",
    "owner_address": "0x..."
  }
}
```

## Installation

### Prerequisites
- Python 3.12+
- PostgreSQL database
- Docker (optional)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/finquarium/finquarium-proof
cd finquarium-proof
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
```env
# Required for dev. In TEE this will come from the environment
POSTGRES_URL=postgresql://user:pass@localhost:5432/dbname
COINBASE_TOKEN=your_coinbase_token

# Optional with defaults
INPUT_DIR=/input
OUTPUT_DIR=/output
REWARD_FACTOR=630
MAX_POINTS=630

# Context variables
DLP_ID=1234
FILE_ID=5678
FILE_URL=https://...
JOB_ID=job-123
OWNER_ADDRESS=0x...
```

## Usage

### Local Development

Run the proof generation:
```bash
python -m finquarium_proof
```

### Docker Deployment

1. Build container:
```bash
docker build -t finquarium-proof .
```

2. Run with Docker:
```bash
docker run \
  --rm \
  --env-file .env \
  --volume $(pwd)/input:/input \
  --volume $(pwd)/output:/output \
  finquarium-proof
```

## Project Structure

```
finquarium-proof/
├── finquarium_proof/
│   ├── models/
│   │   ├── db.py            # Database models
│   │   ├── contribution.py  # Domain models
│   │   └── proof.py        # ProofResponse model
│   ├── services/
│   │   ├── coinbase.py     # Coinbase API service
│   │   └── storage.py      # Database operations
│   ├── utils/
│   │   └── json_encoder.py # JSON utilities
│   ├── config.py           # Configuration
│   ├── db.py              # Database connection
│   ├── proof.py           # Main proof logic
│   └── scoring.py         # Points calculation
├── alembic/               # Database migrations
├── Dockerfile
├── README.md
└── requirements.txt
```

## Development

### Error Handling

The proof handles common errors:
- Invalid/expired Coinbase tokens
- API rate limits
- Data format mismatches
- Network issues
- Duplicate submissions

## Security Considerations

1. Data Privacy:
    - All user IDs are hashed using SHA-256
    - Only aggregate statistics are stored
    - Personal information is stripped before storage

2. Data Validation:
    - Transaction matching with epsilon for floating point
    - Timestamp verification
    - Immutable properties validation

## License

MIT License - see LICENSE file for details

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## Contact

For issues or questions, please open a GitHub issue in this repository.