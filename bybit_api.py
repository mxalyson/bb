"""
Bybit API Wrapper - Paper Trading & Live Trading
Supports both simulated and real trading on Bybit mainnet.
"""

import os
import time
import hmac
import hashlib
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class BybitAPI:
    """
    Unified Bybit API wrapper with paper and live trading modes.

    Paper mode: Simulates trades using real market prices
    Live mode: Executes real trades on Bybit
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        mode: str = 'paper',
        api_url: str = 'https://api.bybit.com',
        paper_balance: float = 10000.0,
        slippage_pct: float = 0.05,
        fee_pct: float = 0.055
    ):
        """
        Initialize Bybit API.

        Args:
            api_key: Bybit API key
            api_secret: Bybit API secret
            mode: 'paper' or 'live'
            api_url: Bybit API endpoint
            paper_balance: Initial balance for paper trading
            slippage_pct: Slippage simulation for paper trading
            fee_pct: Trading fee percentage
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.mode = mode.lower()
        self.api_url = api_url.rstrip('/')
        self.fee_pct = fee_pct / 100.0  # Convert to decimal

        # Paper trading state
        if self.mode == 'paper':
            self.paper_balance = paper_balance
            self.paper_positions = {}  # symbol -> position dict
            self.paper_orders = []
            self.paper_trades = []
            self.slippage_pct = slippage_pct / 100.0
            logger.info(f"📄 PAPER TRADING MODE - Initial balance: ${paper_balance:,.2f}")
        else:
            logger.info(f"🔴 LIVE TRADING MODE - Using real money!")

        # Validate connection
        self._validate_connection()

    def _validate_connection(self):
        """Validate API connection and credentials."""
        try:
            server_time = self.get_server_time()
            logger.info(f"✅ Connected to Bybit - Server time: {server_time}")

            if self.mode == 'live':
                # Test authentication
                balance = self.get_balance()
                logger.info(f"✅ Authentication successful - Balance: ${balance:,.2f}")
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            raise

    def _generate_signature(self, params: Dict) -> str:
        """Generate HMAC SHA256 signature for Bybit API."""
        # Sort parameters
        sorted_params = sorted(params.items())
        query_string = '&'.join([f"{k}={v}" for k, v in sorted_params])

        # Generate signature
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        signed: bool = False
    ) -> Dict:
        """Make HTTP request to Bybit API."""
        if params is None:
            params = {}

        # Add timestamp for signed requests
        if signed:
            params['api_key'] = self.api_key
            params['timestamp'] = str(int(time.time() * 1000))
            params['sign'] = self._generate_signature(params)

        url = f"{self.api_url}{endpoint}"

        try:
            if method == 'GET':
                response = requests.get(url, params=params, timeout=10)
            elif method == 'POST':
                response = requests.post(url, data=params, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            data = response.json()

            if data.get('ret_code') != 0:
                raise Exception(f"API error: {data.get('ret_msg')}")

            return data.get('result', {})

        except Exception as e:
            logger.error(f"API request failed: {e}")
            raise

    def get_server_time(self) -> datetime:
        """Get Bybit server time."""
        result = self._make_request('GET', '/v2/public/time')
        timestamp = result.get('time_now', time.time())
        return datetime.fromtimestamp(float(timestamp))

    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Get historical klines/candles.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Candle interval ('1', '3', '5', '15', '30', '60', '120', '240', 'D', 'W')
            limit: Number of candles (max 200)
            start_time: Start timestamp in seconds

        Returns:
            DataFrame with OHLCV data
        """
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }

        if start_time:
            params['from'] = start_time

        result = self._make_request('GET', '/v2/public/kline/list', params=params)

        # Convert to DataFrame
        if not result:
            return pd.DataFrame()

        df = pd.DataFrame(result)
        df['timestamp'] = pd.to_datetime(df['open_time'], unit='s')
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)

        return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].sort_values('timestamp').reset_index(drop=True)

    def get_latest_price(self, symbol: str) -> float:
        """Get latest price for symbol."""
        params = {'symbol': symbol}
        result = self._make_request('GET', '/v2/public/tickers', params=params)

        if isinstance(result, list) and len(result) > 0:
            return float(result[0]['last_price'])
        return 0.0

    def get_balance(self) -> float:
        """Get account balance in USD."""
        if self.mode == 'paper':
            # Return paper balance
            total = self.paper_balance

            # Add unrealized PnL from open positions
            for symbol, position in self.paper_positions.items():
                current_price = self.get_latest_price(symbol)
                pnl = self._calculate_pnl(position, current_price)
                total += pnl

            return total
        else:
            # Get real balance
            params = {'coin': 'USDT'}
            result = self._make_request('GET', '/v2/private/wallet/balance', params=params, signed=True)

            if isinstance(result, dict):
                usdt_balance = result.get('USDT', {})
                return float(usdt_balance.get('available_balance', 0))
            return 0.0

    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get current position for symbol."""
        if self.mode == 'paper':
            return self.paper_positions.get(symbol)
        else:
            params = {'symbol': symbol}
            result = self._make_request('GET', '/v2/private/position/list', params=params, signed=True)

            if isinstance(result, dict):
                side = result.get('side')
                size = float(result.get('size', 0))

                if size > 0:
                    return {
                        'symbol': symbol,
                        'side': side.lower(),
                        'size': size,
                        'entry_price': float(result.get('entry_price', 0)),
                        'leverage': int(result.get('leverage', 1))
                    }
            return None

    def open_position(
        self,
        symbol: str,
        side: str,  # 'long' or 'short'
        size_usd: float,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float,
        take_profit_3: float
    ) -> Dict:
        """
        Open a new position.

        Args:
            symbol: Trading pair
            side: 'long' or 'short'
            size_usd: Position size in USD
            stop_loss: Stop loss price
            take_profit_1: First take profit level
            take_profit_2: Second take profit level
            take_profit_3: Third take profit level

        Returns:
            Dict with order details
        """
        current_price = self.get_latest_price(symbol)

        if self.mode == 'paper':
            # Simulate order with slippage
            if side == 'long':
                entry_price = current_price * (1 + self.slippage_pct)
            else:
                entry_price = current_price * (1 - self.slippage_pct)

            # Calculate position size in BTC
            qty = size_usd / entry_price

            # Calculate fees
            fee = size_usd * self.fee_pct
            self.paper_balance -= fee

            # Create position
            position = {
                'symbol': symbol,
                'side': side,
                'entry_price': entry_price,
                'qty': qty,
                'size_usd': size_usd,
                'stop_loss': stop_loss,
                'take_profit_1': take_profit_1,
                'take_profit_2': take_profit_2,
                'take_profit_3': take_profit_3,
                'opened_at': datetime.now(),
                'status': 'open'
            }

            self.paper_positions[symbol] = position

            logger.info(f"📄 [PAPER] Opened {side.upper()} position: {symbol} @ ${entry_price:,.2f} | Size: ${size_usd:,.2f}")

            return {
                'order_id': f"paper_{int(time.time() * 1000)}",
                'symbol': symbol,
                'side': side,
                'entry_price': entry_price,
                'qty': qty,
                'status': 'filled'
            }
        else:
            # Place real market order
            bybit_side = 'Buy' if side == 'long' else 'Sell'
            qty = round(size_usd / current_price, 4)

            params = {
                'symbol': symbol,
                'side': bybit_side,
                'order_type': 'Market',
                'qty': qty,
                'time_in_force': 'GoodTillCancel',
                'reduce_only': False,
                'close_on_trigger': False,
                'stop_loss': stop_loss,
                'take_profit': take_profit_3  # Use TP3 as main TP
            }

            result = self._make_request('POST', '/v2/private/order/create', params=params, signed=True)

            logger.info(f"🔴 [LIVE] Opened {side.upper()} position: {symbol} @ ${current_price:,.2f} | Size: ${size_usd:,.2f}")

            return result

    def close_position(self, symbol: str, reason: str = 'manual') -> Dict:
        """Close an open position."""
        position = self.get_position(symbol)

        if not position:
            logger.warning(f"No position to close for {symbol}")
            return {}

        current_price = self.get_latest_price(symbol)

        if self.mode == 'paper':
            # Calculate PnL
            pnl = self._calculate_pnl(position, current_price)

            # Apply slippage and fees
            if position['side'] == 'long':
                exit_price = current_price * (1 - self.slippage_pct)
            else:
                exit_price = current_price * (1 + self.slippage_pct)

            fee = position['size_usd'] * self.fee_pct
            net_pnl = pnl - fee

            # Update balance
            self.paper_balance += position['size_usd'] + net_pnl

            # Record trade
            trade = {
                'symbol': symbol,
                'side': position['side'],
                'entry_price': position['entry_price'],
                'exit_price': exit_price,
                'size_usd': position['size_usd'],
                'pnl': net_pnl,
                'pnl_pct': (net_pnl / position['size_usd']) * 100,
                'reason': reason,
                'opened_at': position['opened_at'],
                'closed_at': datetime.now(),
                'duration': str(datetime.now() - position['opened_at'])
            }

            self.paper_trades.append(trade)

            # Remove position
            del self.paper_positions[symbol]

            logger.info(f"📄 [PAPER] Closed {position['side'].upper()} position: {symbol} @ ${exit_price:,.2f} | PnL: ${net_pnl:,.2f} ({trade['pnl_pct']:.2f}%) | Reason: {reason}")

            return trade
        else:
            # Close real position
            bybit_side = 'Sell' if position['side'] == 'long' else 'Buy'

            params = {
                'symbol': symbol,
                'side': bybit_side,
                'order_type': 'Market',
                'qty': position['size'],
                'time_in_force': 'GoodTillCancel',
                'reduce_only': True,
                'close_on_trigger': False
            }

            result = self._make_request('POST', '/v2/private/order/create', params=params, signed=True)

            logger.info(f"🔴 [LIVE] Closed {position['side'].upper()} position: {symbol} @ ${current_price:,.2f} | Reason: {reason}")

            return result

    def check_exit_conditions(self, symbol: str) -> Optional[Tuple[bool, str]]:
        """
        Check if position should be closed based on SL/TP levels.

        Returns:
            (should_close, reason) or None
        """
        position = self.get_position(symbol)

        if not position:
            return None

        current_price = self.get_latest_price(symbol)
        side = position['side']

        # Paper mode uses stored SL/TP levels
        if self.mode == 'paper':
            sl = position.get('stop_loss')
            tp1 = position.get('take_profit_1')
            tp2 = position.get('take_profit_2')
            tp3 = position.get('take_profit_3')

            # Check exits in priority order (TP3 → TP2 → TP1 → SL)
            if side == 'long':
                if current_price >= tp3:
                    return (True, 'take_profit_3')
                if current_price >= tp2:
                    return (True, 'take_profit_2')
                if current_price >= tp1:
                    return (True, 'take_profit_1')
                if current_price <= sl:
                    return (True, 'stop_loss')
            else:  # short
                if current_price <= tp3:
                    return (True, 'take_profit_3')
                if current_price <= tp2:
                    return (True, 'take_profit_2')
                if current_price <= tp1:
                    return (True, 'take_profit_1')
                if current_price >= sl:
                    return (True, 'stop_loss')

        return None

    def _calculate_pnl(self, position: Dict, current_price: float) -> float:
        """Calculate unrealized PnL for a position."""
        side = position['side']
        entry_price = position['entry_price']
        size_usd = position['size_usd']

        if side == 'long':
            pnl_pct = (current_price - entry_price) / entry_price
        else:  # short
            pnl_pct = (entry_price - current_price) / entry_price

        return size_usd * pnl_pct

    def get_performance_stats(self) -> Dict:
        """Get trading performance statistics (paper mode only)."""
        if self.mode != 'paper' or not self.paper_trades:
            return {}

        trades_df = pd.DataFrame(self.paper_trades)

        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['pnl'] > 0])
        losing_trades = len(trades_df[trades_df['pnl'] < 0])

        total_pnl = trades_df['pnl'].sum()
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

        avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
        avg_loss = abs(trades_df[trades_df['pnl'] < 0]['pnl'].mean()) if losing_trades > 0 else 0

        profit_factor = (winning_trades * avg_win) / (losing_trades * avg_loss) if losing_trades > 0 else 0

        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'current_balance': self.get_balance(),
            'roi': ((self.get_balance() - 10000) / 10000) * 100
        }
