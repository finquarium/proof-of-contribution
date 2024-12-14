# Finquarium Proof of Contribution

This repository contains a proof of contribution implementation for Finquarium's Data Liquidity Pool (DLP).
It validates Coinbase trading history authenticity while preserving user privacy through data hashing.

## Overview

The proof verifies that:
- The submitted data is authentic by comparing it with a fresh Coinbase API fetch
- The contributor owns the data by validating their access token
- The data is properly formatted and complete
- Each contribution is unique

This proof is designed to protect user privacy by:
- Using hashed account IDs instead of user identifiers
- Exposing only aggregate statistics
- Validating data without storing personal information

### Scoring Method

The final score (0 to 1) is calculated from:
- Authenticity (40%): Data matches current Coinbase records
- Ownership (30%): Valid Coinbase access verified
- Quality (20%): Format and completeness
- Uniqueness (10%): Unique contribution verification

### Proof Output Format

```json
{
  "dlp_id": 1234,
  "valid": true,
  "score": 0.95,
  "authenticity": 1.0,
  "ownership": 1.0,
  "quality": 1.0,
  "uniqueness": 0.75,
  "attributes": {
    "account_id_hash": "hash_of_coinbase_account_id",
    "transaction_count": 157,
    "total_volume": 25000.50,
    "data_validated": true,
    "activity_period_days": 365,
    "unique_assets": 12
  },
  "metadata": {
    "dlp_id": 1234,
    "version": "1.0.0"
  }
}
```

## Installation

### Prerequisites
- Python 3.12+
- Docker
- Coinbase API token for testing

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

## Usage

### Local Development

1. Set up environment variables:
```env
COINBASE_TOKEN=your_test_token_here
```

2. Run locally:
```bash
python -m my_proof
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
  --volume $(pwd)/demo/input:/input \
  --volume $(pwd)/demo/output:/output \
  --env COINBASE_TOKEN=your_coinbase_token \
  finquarium-proof
```

## Project Structure

```
finquarium-proof/
├── my_proof/
│   ├── models/
│   │   └── proof_response.py    # Proof response model
│   ├── __init__.py
│   ├── __main__.py             # Entry point
│   └── proof.py                # Core proof logic
├── demo/                       # Test files
│   ├── input/                  # Sample input
│   └── output/                 # Proof results
├── Dockerfile
├── README.md
└── requirements.txt
```

## Development

### Making Changes

1. The main proof logic is in `my_proof/proof.py`
2. Key components:
  - `CoinbaseAPI`: Handles Coinbase data fetching
  - `Proof`: Main proof logic and validation
  - `ProofResponse`: Output data model

### Testing

1. Create test data in `demo/input/`
2. Run the proof locally
3. Verify output in `demo/output/results.json`

### Rate Limiting

The proof includes built-in rate limiting for Coinbase API calls:
- Automatic retries with backoff
- Pagination handling
- Request delays to prevent rate limits

## Integration Guide

### Input Requirements

1. Decrypted file should be a JSON containing:
```json
{
  "user": {
    "id": "coinbase_account_id"
  },
  "transactions": [
    {
      "id": "tx_id",
      "type": "buy/sell",
      "asset": "BTC",
      "quantity": 1.0,
      "native_currency": "USD",
      "native_amount": 50000.00
    }
  ]
}
```

2. Environment variables:
```
COINBASE_TOKEN=valid_oauth_token
```

### Error Handling

The proof handles common errors:
- Invalid/expired tokens
- API rate limits
- Data format mismatches
- Network issues

## Security Considerations

1. Privacy Protection:
  - All user IDs are hashed using SHA-256
  - Only aggregate statistics are exposed
  - No personal information in output

2. Data Validation:
  - Strict transaction matching
  - Immutable properties validation
  - Floating point comparison with epsilon

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Contact

For issues or questions, please open a GitHub issue in this repository.