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

from ..models.binance import BinanceTransaction, BinanceValidationData

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
                    print(f"Response for {symbol}: {response.text}")

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
                        print(f"Failed to get trades for {symbol} after 3 attempts: {str(e)}")
                        raise
                    wait_time = (2 ** attempt) * 0.1  # 0.1s, 0.2s, 0.4s
                    time.sleep(wait_time)

            return trades

        except Exception as e:
            print(f"Error getting trades for {symbol}: {str(e)}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")
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
        Validate transactions with improved error handling and time range handling.
        """
        # Group transactions by symbol and time range
        symbol_groups = {}
        for tx in transactions:
            symbol = tx.symbol
            if symbol not in symbol_groups:
                symbol_groups[symbol] = []
            symbol_groups[symbol].append(tx)

        for symbol, txs in symbol_groups.items():
            # Get time range for these transactions with some buffer
            start_time = int(min(tx.timestamp for tx in txs).timestamp() * 1000) - (24 * 60 * 60 * 1000)  # 1 day before
            end_time = int(max(tx.timestamp for tx in txs).timestamp() * 1000) + (24 * 60 * 60 * 1000)  # 1 day after

            try:
                # Get trades from API
                # api_trades = self.api.get_my_trades(symbol, start_time, end_time)
                api_trades = self.api.get_my_trades(symbol)

                if not api_trades:
                    print(f"No trades found for {symbol} between {start_time} and {end_time}")
                    continue

                # Create lookup of API trades with rounding to handle floating point differences
                api_trades_lookup = {}
                for trade in api_trades:
                    key = (
                        datetime.fromtimestamp(trade['time'] / 1000),
                        round(float(trade['price']), 8),
                        round(float(trade['qty']), 8),
                        round(float(trade['commission']), 8)
                    )
                    api_trades_lookup[key] = trade

                # Verify each transaction exists in API response
                for tx in txs:
                    key = (
                        tx.timestamp,
                        round(float(tx.price), 8),
                        round(float(tx.quantity), 8),
                        round(float(tx.fee), 8)
                    )
                    if key not in api_trades_lookup:
                        return False, f"Transaction validation failed for {symbol} at {tx.timestamp}"

            except Exception as e:
                print(f"Error validating {symbol}: {str(e)}")
                return False, f"Validation failed for {symbol}: {str(e)}"

        return True, "All transactions validated successfully"

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