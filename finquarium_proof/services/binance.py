# finquarium_proof/services/binance.py
import csv
import hashlib
import hmac
import io
import time
import zipfile
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Tuple
import requests
import logging
from ..models.binance import BinanceTransaction, BinanceValidationData

logger = logging.getLogger(__name__)

class BinanceAPI:
    def __init__(self, api_key: str, api_secret: str):
        self.API_URL = "https://api.binance.com"
        self.api_key = api_key
        self.api_secret = api_secret

    def _get_signature(self, query_string: str) -> str:
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def get_account_info(self) -> Dict:
        endpoint = "/api/v3/account"
        timestamp = int(time.time() * 1000)
        query_string = f"timestamp={timestamp}"
        signature = self._get_signature(query_string)

        headers = {'X-MBX-APIKEY': self.api_key}
        response = requests.get(
            f"{self.API_URL}{endpoint}?{query_string}&signature={signature}",
            headers=headers
        )
        return response.json()

    def get_my_trades(self, symbol: str, start_time: int = None, end_time: int = None) -> List[Dict]:
        """
        Get trades for a specific symbol with proper error handling and pagination.
        """
        endpoint = "/api/v3/myTrades"
        limit = 1000  # Maximum allowed limit
        trades = []

        try:
            # Convert symbol to proper format (remove USDT suffix)
            base_symbol = symbol.replace('USDT', '')

            params = {
                "symbol": symbol,  # Keep original symbol for API call
                "limit": limit,
                "timestamp": int(time.time() * 1000)
            }

            if start_time:
                params["startTime"] = start_time
            if end_time:
                params["endTime"] = end_time

            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            signature = self._get_signature(query_string)

            headers = {'X-MBX-APIKEY': self.api_key}

            # Add retries with exponential backoff
            for attempt in range(3):
                try:
                    response = requests.get(
                        f"{self.API_URL}{endpoint}?{query_string}&signature={signature}",
                        headers=headers
                    )
                    response.raise_for_status()

                    # Log response for debugging
                    logger.info(f"Response for {symbol}: {response.text}")

                    current_trades = response.json()
                    trades.extend(current_trades)

                    # If we got less than the limit, we've got all trades
                    if len(current_trades) < limit:
                        break

                    # Update params for next page using the last trade ID
                    if current_trades:
                        params["fromId"] = current_trades[-1]["id"]

                    break  # Success, exit retry loop

                except requests.exceptions.RequestException as e:
                    if attempt == 2:  # Last attempt
                        logger.info(f"Failed to get trades for {symbol} after 3 attempts: {str(e)}")
                        raise
                    wait_time = (2 ** attempt) * 0.1  # 0.1s, 0.2s, 0.4s
                    time.sleep(wait_time)

            return trades

        except Exception as e:
            logger.info(f"Error getting trades for {symbol}: {str(e)}")
            if hasattr(e, 'response'):
                logger.info(f"Response: {e.response.text}")
            raise

class BinanceValidator:
    def __init__(self, api_key: str, api_secret: str):
        self.api = BinanceAPI(api_key, api_secret)

    def parse_csv_file(self, csv_lines: List[str]) -> List[BinanceTransaction]:
        transactions = []
        csv_data = io.StringIO('\n'.join(csv_lines))
        reader = csv.DictReader(csv_data)

        # Get the actual column name for Date(UTC) from headers
        date_column = next(name for name in reader.fieldnames if 'Date(UTC)' in name)

        for row in reader:
            # Parse fee and fee asset
            fee_str = row['Fee']
            numeric_end = 0
            for i, c in enumerate(fee_str):
                if c.isdigit() or c == '.':
                    numeric_end = i + 1
                else:
                    break

            fee_amount = Decimal(fee_str[:numeric_end])
            fee_asset = fee_str[numeric_end:]

            # Parse executed quantity
            executed_str = row['Executed']
            numeric_end = 0
            for i, c in enumerate(executed_str):
                if c.isdigit() or c == '.':
                    numeric_end = i + 1
                else:
                    break

            executed_qty = Decimal(executed_str[:numeric_end])

            # Parse amount
            amount_str = row['Amount']
            numeric_end = 0
            for i, c in enumerate(amount_str):
                if c.isdigit() or c == '.':
                    numeric_end = i + 1
                else:
                    break

            amount = Decimal(amount_str[:numeric_end])

            transaction = BinanceTransaction(
                timestamp=datetime.strptime(row[date_column], '%Y-%m-%d %H:%M:%S'),
                symbol=row['Pair'],
                side=row['Side'],
                price=Decimal(row['Price']),
                quantity=executed_qty,
                amount=amount,
                fee=fee_amount,
                fee_asset=fee_asset
            )
            transactions.append(transaction)

        return transactions

    def process_zip_file(self, zip_file_path: str) -> List[BinanceTransaction]:
        all_transactions = []

        with zipfile.ZipFile(zip_file_path) as zip_ref:
            for file_name in zip_ref.namelist():
                if file_name.endswith('.csv'):
                    with zip_ref.open(file_name) as csv_file:
                        # Read as bytes and decode to string
                        csv_text = csv_file.read().decode('utf-8')
                        # Split into lines and pass to parse_csv_file
                        csv_lines = csv_text.splitlines()
                        transactions = self.parse_csv_file(csv_lines)
                        all_transactions.extend(transactions)

        return all_transactions

    def validate_transactions(self, transactions: List[BinanceTransaction]) -> Tuple[bool, str]:
        """
        Validate transactions with timezone-aware comparison.
        """
        # Group transactions by symbol
        symbol_groups = {}
        for tx in transactions:
            symbol = tx.symbol
            if symbol not in symbol_groups:
                symbol_groups[symbol] = []
            symbol_groups[symbol].append(tx)

        for symbol, txs in symbol_groups.items():
            try:
                # Get trades from API without time range filtering
                api_trades = self.api.get_my_trades(symbol)

                if not api_trades:
                    logger.info(f"No trades found for {symbol}")
                    continue

                # Create lookup of API trades with normalized values
                api_trades_lookup = {}
                for trade in api_trades:
                    # Convert API trade timestamp to UTC datetime for comparison
                    trade_time = datetime.utcfromtimestamp(trade['time'] / 1000)

                    # Round values to 8 decimal places for consistent comparison
                    trade_tuple = (
                        trade_time,
                        float(trade['price']),
                        float(trade['qty']),
                        float(trade['commission']),
                        trade['commissionAsset'],
                        trade['isBuyer']
                    )
                    api_trades_lookup[trade_tuple] = trade

                logger.info(f"\nValidating trades for {symbol}:")
                logger.info(f"Found {len(api_trades)} trades in API response")
                logger.info(f"Found {len(txs)} trades in CSV export")

                # Verify each transaction exists in API response
                for tx in txs:
                    # Convert transaction data to match API format
                    is_buyer = tx.side.upper() == 'BUY'
                    # Assume tx.timestamp is already in UTC since it came from CSV with UTC marker
                    tx_tuple = (
                        tx.timestamp,
                        float(tx.price),
                        float(tx.quantity),
                        float(tx.fee),
                        tx.fee_asset,
                        is_buyer
                    )

                    # Debug print transaction details with timezone info
                    logger.info(f"\nLooking for transaction (UTC):")
                    logger.info(f"Time: {tx.timestamp} UTC")
                    logger.info(f"Price: {tx.price}")
                    logger.info(f"Quantity: {tx.quantity}")
                    logger.info(f"Fee: {tx.fee} {tx.fee_asset}")
                    logger.info(f"Side: {tx.side}")

                    # Try to find matching trade with some tolerance for timestamp
                    found_match = False
                    for api_tuple in api_trades_lookup.keys():
                        # Debug print API trade details for comparison
                        logger.info(f"\nComparing with API trade (UTC):")
                        logger.info(f"Time: {api_tuple[0]} UTC")
                        logger.info(f"Price: {api_tuple[1]}")
                        logger.info(f"Quantity: {api_tuple[2]}")
                        logger.info(f"Fee: {api_tuple[3]} {api_tuple[4]}")
                        logger.info(f"Side: {'BUY' if api_tuple[5] else 'SELL'}")

                        # Check if values match within tolerance
                        time_diff = abs((tx_tuple[0] - api_tuple[0]).total_seconds())
                        price_matches = abs(tx_tuple[1] - api_tuple[1]) < 0.00000001
                        qty_matches = abs(tx_tuple[2] - api_tuple[2]) < 0.00000001
                        fee_matches = abs(tx_tuple[3] - api_tuple[3]) < 0.00000001
                        asset_matches = tx_tuple[4] == api_tuple[4]
                        side_matches = tx_tuple[5] == api_tuple[5]

                        logger.info(f"Time difference: {time_diff} seconds")
                        logger.info(f"Price matches: {price_matches}")
                        logger.info(f"Quantity matches: {qty_matches}")
                        logger.info(f"Fee matches: {fee_matches}")
                        logger.info(f"Asset matches: {asset_matches}")
                        logger.info(f"Side matches: {side_matches}")

                        if (time_diff < 5 and price_matches and qty_matches and
                                fee_matches and asset_matches and side_matches):
                            found_match = True
                            logger.info("FOUND MATCH!")
                            break

                    if not found_match:
                        logger.info("\nNo matching trade found!")
                        return False, f"Transaction validation failed for {symbol} at {tx.timestamp}"
                    else:
                        logger.info("Trade validated successfully!")

                return True, "All transactions validated successfully"

            except Exception as e:
                logger.info(f"Error validating {symbol}: {str(e)}")
                return False, f"Validation failed for {symbol}: {str(e)}"

    def calculate_rewards(self, transactions: List[BinanceTransaction]) -> BinanceValidationData:
        # Calculate metrics
        total_volume = Decimal(sum(tx.amount for tx in transactions))
        unique_assets = len(set(tx.symbol for tx in transactions))
        start_time = min(tx.timestamp for tx in transactions)
        end_time = max(tx.timestamp for tx in transactions)

        # Get account info for ID hash
        account_info = self.api.get_account_info()
        account_id_hash = hashlib.sha256(str(account_info['accountType']).encode()).hexdigest()

        return BinanceValidationData(
            account_id_hash=account_id_hash,
            transactions=transactions,
            total_volume=total_volume,
            asset_count=unique_assets,
            start_time=start_time,
            end_time=end_time
        )