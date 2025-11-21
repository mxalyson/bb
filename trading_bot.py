"""
Trading Bot - Main Trading Engine
Orchestrates ML predictions, signal generation, and trade execution.
"""

import os
import sys
import time
import pickle
import yaml
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import logging

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.bybit_api import BybitAPI

logger = logging.getLogger(__name__)


class TradingBot:
    """
    Main trading bot that combines ML predictions with risk management.
    """

    def __init__(
        self,
        api: BybitAPI,
        config_path: str,
        model_path: str,
        symbol: str = 'BTCUSDT',
        timeframe: str = '15',
        max_position_size_usd: float = 1000.0
    ):
        """
        Initialize Trading Bot.

        Args:
            api: BybitAPI instance
            config_path: Path to trading configuration YAML
            model_path: Path to trained ML model
            symbol: Trading pair
            timeframe: Candle timeframe
            max_position_size_usd: Maximum position size in USD
        """
        self.api = api
        self.symbol = symbol
        self.timeframe = timeframe
        self.max_position_size_usd = max_position_size_usd

        # Load configuration
        self.config = self._load_config(config_path)

        # Load ML model
        self.model = self._load_model(model_path)

        # Trading state
        self.is_running = False
        self.last_signal_time = None
        self.trades_today = 0
        self.daily_pnl = 0.0

        logger.info(f"🤖 Trading Bot initialized - {symbol} {timeframe}m - Mode: {api.mode}")

    def _load_config(self, config_path: str) -> Dict:
        """Load trading configuration from YAML."""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"✅ Loaded config from: {config_path}")
            return config
        except Exception as e:
            logger.error(f"❌ Failed to load config: {e}")
            raise

    def _load_model(self, model_path: str) -> object:
        """Load trained ML model."""
        try:
            with open(model_path, 'rb') as f:
                model = pickle.load(f)
            logger.info(f"✅ Loaded ML model from: {model_path}")
            return model
        except Exception as e:
            logger.error(f"❌ Failed to load model: {e}")
            raise

    def build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Build ML features from OHLCV data.
        Uses same feature engineering as training.
        """
        # Technical indicators
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))

        # Volatility
        df['volatility'] = df['returns'].rolling(window=20).std()
        df['atr'] = self._calculate_atr(df, window=14)

        # Moving averages
        for period in [7, 14, 21, 50, 100, 200]:
            df[f'sma_{period}'] = df['close'].rolling(window=period).mean()
            df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()

        # Price momentum
        for period in [5, 10, 20]:
            df[f'momentum_{period}'] = df['close'] - df['close'].shift(period)
            df[f'roc_{period}'] = (df['close'] - df['close'].shift(period)) / df['close'].shift(period) * 100

        # RSI
        df['rsi_14'] = self._calculate_rsi(df['close'], 14)

        # MACD
        df['macd'], df['macd_signal'], df['macd_hist'] = self._calculate_macd(df['close'])

        # Bollinger Bands
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = self._calculate_bollinger_bands(df['close'])

        # Volume indicators
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']

        # Regime detection
        df = self._detect_regime(df)

        return df

    def _calculate_atr(self, df: pd.DataFrame, window: int = 14) -> pd.Series:
        """Calculate Average True Range."""
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)

        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=window).mean()

        return atr

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = prices.diff()

        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple:
        """Calculate MACD indicator."""
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()

        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        macd_hist = macd - macd_signal

        return macd, macd_signal, macd_hist

    def _calculate_bollinger_bands(self, prices: pd.Series, period: int = 20, std_dev: int = 2) -> Tuple:
        """Calculate Bollinger Bands."""
        middle = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()

        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        return upper, middle, lower

    def _detect_regime(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect market regime (volatility + trend).
        Uses rolling window to avoid look-ahead bias.
        """
        # Rolling volatility quantiles (NO LOOK-AHEAD BIAS!)
        quantile_window = 500
        df['vol_low'] = df['volatility'].rolling(window=quantile_window, min_periods=100).quantile(0.33)
        df['vol_high'] = df['volatility'].rolling(window=quantile_window, min_periods=100).quantile(0.67)

        # Classify volatility
        df['vol_regime'] = 'medium'
        df.loc[df['volatility'] < df['vol_low'], 'vol_regime'] = 'low'
        df.loc[df['volatility'] > df['vol_high'], 'vol_regime'] = 'high'

        # Trend detection (SMA crossover)
        df['trend'] = 'neutral'
        df.loc[df['ema_50'] > df['ema_200'], 'trend'] = 'bull'
        df.loc[df['ema_50'] < df['ema_200'], 'trend'] = 'bear'

        # Combined regime
        df['regime'] = df['vol_regime'] + '_vol_' + df['trend']

        # Simplify regime names
        regime_map = {
            'high_vol_bull': 'high_vol_bull',
            'medium_vol_bull': 'medium_bull',
            'low_vol_bull': 'low_vol_bull',
            'high_vol_bear': 'high_vol_bear',
            'medium_vol_bear': 'medium_bear',
            'low_vol_bear': 'low_vol_bear',
            'high_vol_neutral': 'medium_bear',  # Default to medium_bear
            'medium_vol_neutral': 'medium_bear',
            'low_vol_neutral': 'low_vol_bear'
        }

        df['regime'] = df['regime'].map(regime_map).fillna('medium_bear')

        return df

    def get_ml_signal(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Get trading signal from ML model.

        Returns:
            Dict with signal details or None if no signal
        """
        # Build features
        df = self.build_features(df)

        # Get latest row
        latest = df.iloc[-1]

        # Check if enough data
        if pd.isna(latest['sma_200']):
            logger.warning("⚠️  Not enough data for ML prediction")
            return None

        # Prepare features for model
        feature_columns = [col for col in df.columns if col not in [
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'regime', 'trend', 'vol_regime', 'vol_low', 'vol_high'
        ]]

        X = df[feature_columns].iloc[-1:].fillna(0)

        # Get prediction
        try:
            prediction = self.model.predict(X)[0]
            confidence = max(self.model.predict_proba(X)[0])

            # Determine direction
            direction = 'long' if prediction == 1 else 'short'

            # Get current regime
            regime = latest['regime']

            # Check regime filter
            regime_config = self.config['regime_filter']['regimes'].get(regime, {})

            if not regime_config.get('enabled', False):
                logger.info(f"⏭️  Skipping signal - Regime '{regime}' is blocked")
                return None

            # Check confidence threshold
            min_confidence = regime_config.get('min_confidence', 0.5)

            if confidence < min_confidence:
                logger.info(f"⏭️  Skipping signal - Confidence {confidence:.2%} < {min_confidence:.2%} (regime: {regime})")
                return None

            # Get position sizing
            base_size = self.config['position_sizing'].get('base_size_usd', 100.0)
            regime_multiplier = regime_config.get('position_multiplier', 1.0)
            position_size = min(base_size * regime_multiplier, self.max_position_size_usd)

            # Calculate SL/TP levels
            current_price = float(latest['close'])
            atr = float(latest['atr'])

            sl_mult = regime_config.get('stop_atr_mult', 1.0)
            tp_config = self.config['take_profit']['regimes'].get(regime, {})
            tp_mult = tp_config.get('tp_atr_mult', 2.0)

            if direction == 'long':
                stop_loss = current_price - (atr * sl_mult)
                sl_distance = current_price - stop_loss
                take_profit_1 = current_price + (sl_distance * 1.5)
                take_profit_2 = current_price + (sl_distance * 2.5)
                take_profit_3 = current_price + (sl_distance * 3.5)
            else:  # short
                stop_loss = current_price + (atr * sl_mult)
                sl_distance = stop_loss - current_price
                take_profit_1 = current_price - (sl_distance * 1.5)
                take_profit_2 = current_price - (sl_distance * 2.5)
                take_profit_3 = current_price - (sl_distance * 3.5)

            signal = {
                'direction': direction,
                'confidence': confidence,
                'regime': regime,
                'entry_price': current_price,
                'stop_loss': stop_loss,
                'take_profit_1': take_profit_1,
                'take_profit_2': take_profit_2,
                'take_profit_3': take_profit_3,
                'position_size_usd': position_size,
                'atr': atr,
                'timestamp': latest['timestamp']
            }

            logger.info(f"✅ ML Signal: {direction.upper()} @ ${current_price:,.2f} | Conf: {confidence:.2%} | Regime: {regime}")

            return signal

        except Exception as e:
            logger.error(f"❌ ML prediction failed: {e}")
            return None

    def execute_signal(self, signal: Dict) -> bool:
        """Execute a trading signal."""
        try:
            # Open position
            order = self.api.open_position(
                symbol=self.symbol,
                side=signal['direction'],
                size_usd=signal['position_size_usd'],
                stop_loss=signal['stop_loss'],
                take_profit_1=signal['take_profit_1'],
                take_profit_2=signal['take_profit_2'],
                take_profit_3=signal['take_profit_3']
            )

            self.last_signal_time = datetime.now()
            self.trades_today += 1

            logger.info(f"✅ Position opened successfully: {order}")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to execute signal: {e}")
            return False

    def monitor_position(self):
        """Monitor open position for exit conditions."""
        position = self.api.get_position(self.symbol)

        if not position:
            return

        # Check SL/TP
        exit_check = self.api.check_exit_conditions(self.symbol)

        if exit_check:
            should_close, reason = exit_check
            if should_close:
                trade = self.api.close_position(self.symbol, reason=reason)

                if trade:
                    self.daily_pnl += trade.get('pnl', 0)
                    logger.info(f"📊 Daily PnL: ${self.daily_pnl:,.2f} | Trades: {self.trades_today}")

    def run_cycle(self):
        """Run one trading cycle (check signal + monitor position)."""
        try:
            # 1. Monitor existing position
            self.monitor_position()

            # 2. Check if can open new position
            position = self.api.get_position(self.symbol)

            if position:
                logger.debug(f"⏸️  Position already open - skipping signal check")
                return

            # 3. Get latest data
            df = self.api.get_klines(
                symbol=self.symbol,
                interval=self.timeframe,
                limit=200
            )

            if df.empty:
                logger.warning("⚠️  No data received")
                return

            # 4. Get ML signal
            signal = self.get_ml_signal(df)

            if signal:
                # 5. Execute signal
                self.execute_signal(signal)

        except Exception as e:
            logger.error(f"❌ Trading cycle error: {e}")

    def start(self):
        """Start the trading bot."""
        self.is_running = True
        logger.info(f"🚀 Trading bot started - {self.symbol} {self.timeframe}m")

    def stop(self):
        """Stop the trading bot."""
        self.is_running = False
        logger.info(f"🛑 Trading bot stopped")

        # Print final stats
        if self.api.mode == 'paper':
            stats = self.api.get_performance_stats()
            logger.info(f"📊 Final Stats: {stats}")

    def get_status(self) -> Dict:
        """Get current bot status."""
        position = self.api.get_position(self.symbol)
        balance = self.api.get_balance()

        status = {
            'is_running': self.is_running,
            'symbol': self.symbol,
            'mode': self.api.mode,
            'balance': balance,
            'has_position': position is not None,
            'position': position,
            'trades_today': self.trades_today,
            'daily_pnl': self.daily_pnl,
            'last_signal': self.last_signal_time
        }

        if self.api.mode == 'paper':
            stats = self.api.get_performance_stats()
            status.update(stats)

        return status
