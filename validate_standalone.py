"""
STANDALONE MODEL VALIDATOR - Works without bot infrastructure
Tests any .pkl model with downloaded data
"""

import sys
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from typing import Dict, List
import logging
import argparse
import pickle
from datetime import datetime, timedelta
import requests
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# UNIVERSAL MODEL LOADING - Works with ANY pickle model
# ============================================================================

class ModelWrapper:
    """Generic wrapper for models saved with custom classes."""
    def __init__(self, model=None, feature_names=None, **kwargs):
        self.model = model
        self.feature_names = feature_names
        self.__dict__.update(kwargs)


class UniversalUnpickler(pickle.Unpickler):
    """Custom unpickler that can handle missing classes."""
    def find_class(self, module, name):
        if name == 'ModelWrapper':
            return ModelWrapper
        try:
            return super().find_class(module, name)
        except (AttributeError, ModuleNotFoundError):
            return type(name, (), {})


def load_model_universal(model_path: str) -> dict:
    """
    Universal model loader that works with any pickle format.
    Returns: {'model': ..., 'feature_names': [...], 'optimal_threshold': 0.5}
    """
    logger.info(f"🔍 Loading model: {model_path}")

    try:
        with open(model_path, 'rb') as f:
            data = pickle.load(f)
        logger.info(f"   ✅ Loaded with standard pickle")
    except Exception as e1:
        logger.info(f"   ⚠️  Standard load failed, trying custom unpickler...")
        try:
            with open(model_path, 'rb') as f:
                data = UniversalUnpickler(f).load()
            logger.info(f"   ✅ Loaded with custom unpickler")
        except Exception as e2:
            raise ValueError(f"Failed to load model: {e2}")

    result = {
        'model': None,
        'feature_names': None,
        'optimal_threshold': 0.5,
        'raw_data': data
    }

    data_type = type(data).__name__
    logger.info(f"   📦 Type: {data_type}")

    # Case 1: Standard dict format
    if isinstance(data, dict):
        result['model'] = data.get('model')
        result['feature_names'] = data.get('feature_names') or data.get('features')
        result['optimal_threshold'] = data.get('optimal_threshold', 0.5)
        logger.info(f"   📦 Format: Dict with {len(data)} keys")

    # Case 2: Object with attributes
    else:
        # Try to find model
        if hasattr(data, 'model'):
            result['model'] = data.model
        elif hasattr(data, 'models'):
            result['model'] = data.models
        else:
            result['model'] = data

        # Try to find feature names
        for attr in ['feature_names', 'features', 'feature_columns', 'feature_cols', 'cols']:
            if hasattr(data, attr):
                feat = getattr(data, attr)
                if feat is not None and len(feat) > 0:
                    result['feature_names'] = feat
                    break

        result['optimal_threshold'] = getattr(data, 'optimal_threshold', 0.5)

    # Validate
    if result['model'] is None:
        raise ValueError("Could not extract model from pickle file")

    # Try to get feature_names from model if not found
    if result['feature_names'] is None:
        if hasattr(result['model'], 'feature_name_'):
            try:
                result['feature_names'] = result['model'].feature_name_()
            except:
                pass
        elif hasattr(result['model'], 'feature_names_in_'):
            try:
                result['feature_names'] = list(result['model'].feature_names_in_)
            except:
                pass

    if result['feature_names'] is None:
        raise ValueError("Could not find feature_names in model")

    logger.info(f"   ✅ Model loaded successfully")
    logger.info(f"   📊 Features: {len(result['feature_names'])}")
    logger.info(f"   🎯 Threshold: {result['optimal_threshold']:.3f}")

    return result


# ============================================================================
# DATA DOWNLOAD (Bybit public API - no authentication needed)
# ============================================================================

def download_bybit_data(symbol: str, interval: str, days: int) -> pd.DataFrame:
    """Download historical data from Bybit public API."""

    logger.info(f"📥 Downloading {symbol} data ({days} days, {interval} interval)...")

    # Calculate time range
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

    # Bybit public API endpoint
    url = "https://api.bybit.com/v5/market/kline"

    all_data = []
    current_end = end_time

    while current_end > start_time:
        params = {
            'category': 'linear',
            'symbol': symbol,
            'interval': interval,
            'end': current_end,
            'limit': 1000
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data['retCode'] != 0:
                raise ValueError(f"API error: {data['retMsg']}")

            klines = data['result']['list']

            if not klines:
                break

            all_data.extend(klines)
            current_end = int(klines[-1][0]) - 1

        except Exception as e:
            logger.error(f"❌ Download error: {e}")
            break

    if not all_data:
        raise ValueError("No data downloaded")

    # Convert to DataFrame
    df = pd.DataFrame(all_data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
    ])

    # Convert types
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

    df = df.set_index('timestamp').sort_index()
    df = df[['open', 'high', 'low', 'close', 'volume']]

    # Filter to requested time range
    df = df[df.index >= pd.Timestamp.now() - pd.Timedelta(days=days)]

    logger.info(f"✅ Downloaded {len(df):,} candles")
    logger.info(f"   Period: {df.index[0]} to {df.index[-1]}")

    return df


# ============================================================================
# FEATURE ENGINEERING
# ============================================================================

def create_base_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create basic technical indicators."""

    df_feat = df.copy()

    # ATR
    high_low = df_feat['high'] - df_feat['low']
    high_close = np.abs(df_feat['high'] - df_feat['close'].shift())
    low_close = np.abs(df_feat['low'] - df_feat['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df_feat['atr'] = true_range.rolling(14).mean()

    # EMAs
    df_feat['ema50'] = df_feat['close'].ewm(span=50, adjust=False).mean()
    df_feat['ema200'] = df_feat['close'].ewm(span=200, adjust=False).mean()

    return df_feat


def create_classical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create classical technical analysis features.
    Used by older models that expect standard TA indicators.
    """

    df_feat = df.copy()

    logger.info("   🔨 Creating classical TA features...")

    # Returns
    df_feat['returns'] = df_feat['close'].pct_change()
    df_feat['log_returns'] = np.log(df_feat['close'] / df_feat['close'].shift(1))

    # Volatility
    df_feat['volatility'] = df_feat['returns'].rolling(20).std()
    df_feat['volatility_30'] = df_feat['returns'].rolling(30).std()

    # ATR
    high_low = df_feat['high'] - df_feat['low']
    high_close = np.abs(df_feat['high'] - df_feat['close'].shift())
    low_close = np.abs(df_feat['low'] - df_feat['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df_feat['atr_14'] = true_range.rolling(14).mean()
    df_feat['atr_20'] = true_range.rolling(20).mean()

    # SMA/EMA
    for period in [7, 14, 21, 50, 100, 200]:
        df_feat[f'sma_{period}'] = df_feat['close'].rolling(period).mean()
        df_feat[f'ema_{period}'] = df_feat['close'].ewm(span=period, adjust=False).mean()

    # Price vs MA
    df_feat['price_vs_sma50'] = (df_feat['close'] - df_feat['sma_50']) / df_feat['sma_50'] * 100
    df_feat['price_vs_sma200'] = (df_feat['close'] - df_feat['sma_200']) / df_feat['sma_200'] * 100

    # Momentum (CRITICAL: includes 5, 10, 20, 30)
    for period in [5, 10, 20, 30]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100

    # ROC (CRITICAL: includes 5, 10, 20, 30)
    for period in [5, 10, 20, 30]:
        df_feat[f'roc_{period}'] = ((df_feat['close'] - df_feat['close'].shift(period)) /
                                     (df_feat['close'].shift(period) + 1e-10)) * 100

    # RSI
    delta = df_feat['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df_feat['rsi_14'] = 100 - (100 / (1 + rs))

    # Stochastic RSI
    rsi = df_feat['rsi_14']
    rsi_low = rsi.rolling(14).min()
    rsi_high = rsi.rolling(14).max()
    df_feat['stoch_rsi'] = ((rsi - rsi_low) / (rsi_high - rsi_low + 1e-10)) * 100

    # Volume
    df_feat['volume_sma'] = df_feat['volume'].rolling(20).mean()
    df_feat['volume_roc'] = df_feat['volume'].pct_change(10) * 100

    # Channel
    df_feat['high_20'] = df_feat['high'].rolling(20).max()
    df_feat['low_20'] = df_feat['low'].rolling(20).min()
    df_feat['channel_pos'] = ((df_feat['close'] - df_feat['low_20']) /
                              (df_feat['high_20'] - df_feat['low_20'] + 1e-10)) * 100

    return df_feat


def create_advanced_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add V1 advanced features."""

    df_feat = df.copy()

    logger.info("   🔨 Creating V1 advanced features...")

    # Multi-period momentum
    for period in [3, 5, 8, 13, 21]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100
        df_feat[f'volume_ratio_{period}'] = df_feat['volume'] / df_feat['volume'].rolling(period).mean()

    # Trend strength
    if 'ema50' in df_feat.columns and 'ema200' in df_feat.columns:
        df_feat['trend_strength'] = (df_feat['ema50'] - df_feat['ema200']) / df_feat['ema200'] * 100

    # Volatility regimes
    if 'atr' in df_feat.columns:
        df_feat['volatility_regime'] = (df_feat['atr'] / df_feat['atr'].rolling(50).mean())

    # Price position
    df_feat['price_position'] = (
        (df_feat['close'] - df_feat['low'].rolling(20).min()) /
        (df_feat['high'].rolling(20).max() - df_feat['low'].rolling(20).min())
    ).fillna(0.5)

    # Volume momentum
    df_feat['volume_momentum'] = df_feat['volume'].pct_change(5)

    # Acceleration
    df_feat['price_acceleration'] = df_feat['close'].diff(2) - df_feat['close'].diff(1)

    return df_feat


def create_advanced_features_v2(df: pd.DataFrame) -> pd.DataFrame:
    """Add V2 ADVANCED features - Must match training exactly!"""

    df_feat = df.copy()

    logger.info("   🔨 Creating V2 advanced features...")

    # Basic momentum
    for period in [3, 5, 8, 13, 21, 34]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100
        df_feat[f'volume_ratio_{period}'] = df_feat['volume'] / df_feat['volume'].rolling(period).mean()

    # Trend
    df_feat['trend_strength'] = (df_feat['ema50'] - df_feat['ema200']) / df_feat['ema200'] * 100
    df_feat['trend_consistency'] = df_feat['close'].rolling(20).apply(
        lambda x: (x.iloc[-1] > x.iloc[0]) == (x.diff().mean() > 0)
    )

    # Volatility regime
    df_feat['volatility_regime'] = df_feat['atr'] / df_feat['atr'].rolling(50).mean()
    df_feat['volatility_change'] = df_feat['atr'].pct_change(5)

    # Price position in range
    for period in [10, 20, 50]:
        high_period = df_feat['high'].rolling(period).max()
        low_period = df_feat['low'].rolling(period).min()
        df_feat[f'price_position_{period}'] = (
            (df_feat['close'] - low_period) / (high_period - low_period + 1e-8)
        )

    # Volume
    df_feat['volume_momentum'] = df_feat['volume'].pct_change(5)
    df_feat['volume_acceleration'] = df_feat['volume'].diff(2) - df_feat['volume'].diff(1)
    df_feat['price_volume_corr'] = df_feat['close'].rolling(20).corr(df_feat['volume'])

    # Acceleration & jerk
    df_feat['price_velocity'] = df_feat['close'].diff(1)
    df_feat['price_acceleration'] = df_feat['price_velocity'].diff(1)
    df_feat['price_jerk'] = df_feat['price_acceleration'].diff(1)

    # Higher order moments
    for period in [10, 20, 50]:
        returns = df_feat['close'].pct_change()
        df_feat[f'returns_skew_{period}'] = returns.rolling(period).skew()
        df_feat[f'returns_kurt_{period}'] = returns.rolling(period).kurt()
        df_feat[f'returns_std_{period}'] = returns.rolling(period).std()

    # Market microstructure
    df_feat['spread_proxy'] = (df_feat['high'] - df_feat['low']) / df_feat['close'] * 100

    for period in [10, 20]:
        ma = df_feat['close'].rolling(period).mean()
        df_feat[f'price_efficiency_{period}'] = (df_feat['close'] - ma) / ma * 100

    # Regime detection
    df_feat['adx_proxy'] = df_feat['atr'] / df_feat['close'] * 100
    median_volume = df_feat['volume'].rolling(100).median()
    df_feat['volume_regime'] = (df_feat['volume'] > median_volume).astype(int)

    # RSI multi-period
    for period in [5, 10, 20]:
        gains = df_feat['close'].diff().clip(lower=0)
        losses = -df_feat['close'].diff().clip(upper=0)
        avg_gain = gains.rolling(period).mean()
        avg_loss = losses.rolling(period).mean()
        rs = avg_gain / (avg_loss + 1e-8)
        df_feat[f'rsi_{period}'] = 100 - (100 / (1 + rs))

    # ROC multi-period
    for period in [5, 10, 20]:
        df_feat[f'roc_{period}'] = (
            (df_feat['close'] - df_feat['close'].shift(period)) /
            df_feat['close'].shift(period) * 100
        )

    # Bollinger Bands
    for period in [20, 50]:
        sma = df_feat['close'].rolling(period).mean()
        std = df_feat['close'].rolling(period).std()
        df_feat[f'bb_position_{period}'] = (df_feat['close'] - sma) / (2 * std + 1e-8)
        df_feat[f'bb_width_{period}'] = (4 * std) / sma * 100

    # Candle patterns
    body = abs(df_feat['close'] - df_feat['open'])
    upper_shadow = df_feat['high'] - df_feat[['close', 'open']].max(axis=1)
    lower_shadow = df_feat[['close', 'open']].min(axis=1) - df_feat['low']

    df_feat['body_size'] = body / df_feat['close'] * 100
    df_feat['upper_shadow_ratio'] = upper_shadow / (body + 1e-8)
    df_feat['lower_shadow_ratio'] = lower_shadow / (body + 1e-8)

    return df_feat


# ============================================================================
# BACKTESTING
# ============================================================================

class StrategyValidator:
    """Validates strategy with different configurations."""

    def __init__(self, model_path: str, initial_capital: float = 10000, risk_per_trade: float = 0.0075):
        self.model_path = Path(model_path)

        if not self.model_path.exists():
            raise ValueError(f"Model not found: {model_path}")

        # Load model
        self.model_data = load_model_universal(str(self.model_path))
        self.model = self.model_data['model']
        self.feature_names = self.model_data['feature_names']
        self.optimal_threshold = self.model_data['optimal_threshold']

        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade

    def backtest_with_confidence(self, df: pd.DataFrame, min_confidence: float) -> Dict:
        """Run backtest with minimum confidence filter."""

        # Check if all required features are present
        missing_features = [f for f in self.feature_names if f not in df.columns]

        if missing_features:
            logger.error(f"❌ Missing features in dataframe: {missing_features[:10]}")
            logger.error(f"   Total missing: {len(missing_features)} features")
            logger.info(f"   Available columns: {len(df.columns)}")
            raise KeyError(f"Missing features: {missing_features[:5]}")

        # Get ML predictions
        X = df[self.feature_names].fillna(0)
        X = X.replace([np.inf, -np.inf], 0)

        # Predict
        try:
            ml_probs = self.model.predict(X)
        except AttributeError:
            if hasattr(self.model, '__call__'):
                ml_probs = self.model(X)
            else:
                raise ValueError("Model has no predict() or __call__() method")

        df['ml_prob_up'] = ml_probs
        df['ml_prob_down'] = 1 - ml_probs
        df['ml_confidence'] = np.abs(ml_probs - self.optimal_threshold) * 2

        # Generate signals
        df['signal'] = 0
        mask_long = (df['ml_prob_up'] > self.optimal_threshold) & (df['ml_confidence'] >= min_confidence)
        mask_short = (df['ml_prob_down'] > (1 - self.optimal_threshold)) & (df['ml_confidence'] >= min_confidence)

        df.loc[mask_long, 'signal'] = 1
        df.loc[mask_short, 'signal'] = -1

        # Simulate trades
        trades = self._simulate(df)

        # Calculate stats
        stats = self._calculate_stats(trades, df, min_confidence)

        return stats

    def _simulate(self, df: pd.DataFrame) -> List[Dict]:
        """Simulate trading."""
        trades = []
        position = None
        capital = self.initial_capital
        cooldown = 0

        for i in range(len(df)):
            current = df.iloc[i]

            if cooldown > 0:
                cooldown -= 1

            # Check exit
            if position:
                exit_reason = self._check_exit(position, current, i)
                if exit_reason:
                    trade = self._close_trade(position, current, exit_reason)
                    trades.append(trade)
                    capital += trade['pnl_amount']
                    position = None
                    cooldown = 4

            # Check entry
            if not position and current['signal'] != 0 and cooldown == 0 and i < len(df) - 20:
                position = self._open_trade(current, capital, i)

        # Close final position
        if position:
            trade = self._close_trade(position, df.iloc[-1], 'end_of_data')
            trades.append(trade)

        return trades

    def _open_trade(self, current, capital, idx):
        """Open a new trade."""
        direction = 'long' if current['signal'] == 1 else 'short'
        price = current['close']
        atr = current.get('atr', price * 0.01)

        if direction == 'long':
            sl = price - (atr * 2.0)
            tp1 = price + (atr * 1.0)
            tp2 = price + (atr * 2.0)
            tp3 = price + (atr * 3.0)
        else:
            sl = price + (atr * 2.0)
            tp1 = price - (atr * 1.0)
            tp2 = price - (atr * 2.0)
            tp3 = price - (atr * 3.0)

        sl_dist = abs((sl - price) / price)
        risk_amt = capital * self.risk_per_trade
        size = risk_amt / sl_dist if sl_dist > 0 else capital * 0.1
        size = min(size, capital * 0.95)

        return {
            'entry_idx': idx,
            'entry_time': current.name,
            'entry_price': price,
            'direction': direction,
            'size': size,
            'stop_loss': sl,
            'tp1': tp1,
            'tp2': tp2,
            'tp3': tp3,
            'ml_confidence': current['ml_confidence']
        }

    def _check_exit(self, position, current, idx):
        """Check if position should be exited."""
        high = current['high']
        low = current['low']
        direction = position['direction']

        if direction == 'long':
            if low <= position['stop_loss']:
                return 'stop_loss'
            if high >= position['tp3']:
                return 'take_profit_3'
            if high >= position['tp2']:
                return 'take_profit_2'
            if high >= position['tp1']:
                return 'take_profit_1'
        else:
            if high >= position['stop_loss']:
                return 'stop_loss'
            if low <= position['tp3']:
                return 'take_profit_3'
            if low <= position['tp2']:
                return 'take_profit_2'
            if low <= position['tp1']:
                return 'take_profit_1'

        # Time exit (48h = 192 * 15min candles)
        if idx - position['entry_idx'] > 192:
            return 'time_exit'

        return None

    def _close_trade(self, position, current, reason):
        """Close a trade."""
        if reason == 'stop_loss':
            exit_price = position['stop_loss']
        elif reason == 'take_profit_1':
            exit_price = position['tp1']
        elif reason == 'take_profit_2':
            exit_price = position['tp2']
        elif reason == 'take_profit_3':
            exit_price = position['tp3']
        else:
            exit_price = current['close']

        entry = position['entry_price']
        direction = position['direction']

        if direction == 'long':
            pnl_pct = ((exit_price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - exit_price) / entry) * 100

        pnl_amount = position['size'] * (pnl_pct / 100)

        return {
            'entry_time': position['entry_time'],
            'exit_time': current.name,
            'direction': direction,
            'entry_price': entry,
            'exit_price': exit_price,
            'size': position['size'],
            'pnl_pct': pnl_pct,
            'pnl_amount': pnl_amount,
            'reason': reason,
            'ml_confidence': position['ml_confidence']
        }

    def _calculate_stats(self, trades, df, min_confidence):
        """Calculate trading statistics."""
        if not trades:
            return {
                'error': 'No trades',
                'total_trades': 0,
                'min_confidence': min_confidence
            }

        df_trades = pd.DataFrame(trades)

        total = len(df_trades)
        winning = df_trades[df_trades['pnl_amount'] > 0]
        losing = df_trades[df_trades['pnl_amount'] <= 0]

        win_rate = len(winning) / total if total > 0 else 0

        total_pnl = df_trades['pnl_amount'].sum()
        roi = (total_pnl / self.initial_capital) * 100

        avg_win = winning['pnl_amount'].mean() if len(winning) > 0 else 0
        avg_loss = abs(losing['pnl_amount'].mean()) if len(losing) > 0 else 0

        pf = (winning['pnl_amount'].sum() / abs(losing['pnl_amount'].sum())
              if len(losing) > 0 and losing['pnl_amount'].sum() != 0 else 0)

        returns = df_trades['pnl_pct'].values
        sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)
                 if len(returns) > 1 and np.std(returns) > 0 else 0)

        equity = self.initial_capital + df_trades['pnl_amount'].cumsum()
        peak = equity.expanding().max()
        dd = ((equity - peak) / peak * 100).min()

        # Direction stats
        longs = df_trades[df_trades['direction'] == 'long']
        shorts = df_trades[df_trades['direction'] == 'short']

        long_wr = (len(longs[longs['pnl_amount'] > 0]) / len(longs) * 100) if len(longs) > 0 else 0
        short_wr = (len(shorts[shorts['pnl_amount'] > 0]) / len(shorts) * 100) if len(shorts) > 0 else 0

        # Confidence stats
        avg_confidence = df_trades['ml_confidence'].mean()

        return {
            'min_confidence': min_confidence,
            'total_trades': total,
            'winning_trades': len(winning),
            'losing_trades': len(losing),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'roi': roi,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': pf,
            'max_drawdown': dd,
            'sharpe_ratio': sharpe,
            'final_capital': self.initial_capital + total_pnl,
            'avg_ml_confidence': avg_confidence,
            'long_trades': len(longs),
            'short_trades': len(shorts),
            'long_wr': long_wr,
            'short_wr': short_wr,
        }


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', type=str, default='BTCUSDT')
    parser.add_argument('--days', type=int, default=180)
    parser.add_argument('--model', type=str, required=True, help='Path to model .pkl file')

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("🔬 STANDALONE MODEL VALIDATOR")
    logger.info("=" * 80)
    logger.info(f"Symbol: {args.symbol}")
    logger.info(f"Period: {args.days} days")
    logger.info(f"Model: {args.model}")
    logger.info("")

    # Download data
    try:
        df = download_bybit_data(args.symbol, '15m', args.days)
    except Exception as e:
        logger.error(f"❌ Failed to download data: {e}")
        return

    logger.info("")

    # Load model to detect version
    try:
        model_data = load_model_universal(args.model)
        feature_names = model_data['feature_names']
    except Exception as e:
        logger.error(f"❌ Failed to load model: {e}")
        return

    logger.info("")

    # Detect model version
    classical_features = ['returns', 'log_returns', 'atr_14', 'rsi_14', 'sma_7', 'ema_7']
    v2_features = ['returns_kurt_50', 'returns_skew_50', 'rsi_5', 'roc_20', 'bb_width_50']
    v1_features = ['momentum_3', 'volume_ratio_3', 'price_position']

    has_classical = any(f in feature_names for f in classical_features)
    has_v2 = any(f in feature_names for f in v2_features)
    has_v1 = any(f in feature_names for f in v1_features)

    if has_classical:
        model_version = "Classical"
    elif has_v2:
        model_version = "V2"
    elif has_v1:
        model_version = "V1"
    else:
        model_version = "Unknown"

    logger.info(f"📌 Detected model version: {model_version}")
    logger.info(f"   Required features: {len(feature_names)}")
    logger.info("")

    # Build features
    logger.info("🔨 Building features...")

    # Start with base features
    df_features = create_base_features(df)

    # Add version-specific features
    if model_version == "Classical":
        df_features = create_classical_features(df_features)
    elif model_version == "V2":
        df_features = create_advanced_features_v2(df_features)
    elif model_version == "V1":
        df_features = create_advanced_features(df_features)
    else:
        logger.warning("   ⚠️  Unknown model type - creating all features...")
        df_features = create_classical_features(df_features)
        df_features = create_advanced_features(df_features)
        df_features = create_advanced_features_v2(df_features)

    logger.info(f"✅ Features ready: {len(df_features.columns)} columns")

    # Debug: Check if required features are present
    missing = [f for f in feature_names if f not in df_features.columns]
    if missing:
        logger.error(f"❌ Still missing features after engineering: {missing[:20]}")
        logger.error(f"   Total missing: {len(missing)}")
        logger.info("")
        logger.info("🔍 Checking which features are present:")
        present = [f for f in feature_names if f in df_features.columns]
        logger.info(f"   Present: {len(present)}/{len(feature_names)}")
        return

    logger.info(f"✅ All {len(feature_names)} required features are present!")
    logger.info("")

    # Validate strategy
    try:
        validator = StrategyValidator(args.model)
        logger.info(f"🎯 Using threshold: {validator.optimal_threshold:.3f}")
        if validator.optimal_threshold != 0.5:
            logger.info(f"   (Optimized threshold)")
        logger.info("")
    except Exception as e:
        logger.error(f"❌ Failed to initialize validator: {e}")
        return

    # Test different confidence levels
    confidence_levels = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]

    logger.info("=" * 80)
    logger.info("🧪 TESTING DIFFERENT CONFIDENCE LEVELS")
    logger.info("=" * 80)
    logger.info("")

    results = []

    for min_conf in confidence_levels:
        logger.info(f"Testing min confidence: {min_conf:.0%}...")
        try:
            stats = validator.backtest_with_confidence(df_features.copy(), min_conf)
            results.append(stats)
        except Exception as e:
            logger.error(f"   ❌ Error: {e}")
            results.append({
                'min_confidence': min_conf,
                'total_trades': 0,
                'error': str(e)
            })

    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 COMPARATIVE RESULTS")
    logger.info("=" * 80)
    logger.info("")

    # Print comparison table
    header = f"{'Conf':<6} | {'Trades':<7} | {'WR':<6} | {'ROI':<8} | {'ROI/yr':<8} | {'PF':<6} | {'Sharpe':<7} | {'DD':<7} | {'Avg Conf':<9}"
    logger.info(header)
    logger.info("-" * len(header))

    for r in results:
        if r.get('total_trades', 0) > 0:
            roi_yearly = r['roi'] / (args.days / 365)
            line = (f"{r['min_confidence']*100:>5.0f}% | "
                   f"{r['total_trades']:>7,} | "
                   f"{r['win_rate']*100:>5.1f}% | "
                   f"{r['roi']:>+7.1f}% | "
                   f"{roi_yearly:>+7.1f}% | "
                   f"{r['profit_factor']:>5.2f} | "
                   f"{r['sharpe_ratio']:>6.2f} | "
                   f"{r['max_drawdown']:>6.1f}% | "
                   f"{r['avg_ml_confidence']*100:>8.1f}%")
            logger.info(line)
        else:
            error_msg = r.get('error', 'No trades')
            logger.info(f"{r['min_confidence']*100:>5.0f}% | {error_msg}")

    logger.info("")
    logger.info("=" * 80)

    # Find best configuration
    valid_results = [r for r in results if r.get('total_trades', 0) > 20]

    if valid_results:
        # Score each config
        scores = []
        for r in valid_results:
            score = 0
            score += (r['roi'] / max(x['roi'] for x in valid_results)) * 0.3
            score += (r['sharpe_ratio'] / max(x['sharpe_ratio'] for x in valid_results)) * 0.25
            score += (r['win_rate'] / max(x['win_rate'] for x in valid_results)) * 0.2
            score += (1 - abs(r['max_drawdown']) / max(abs(x['max_drawdown']) for x in valid_results)) * 0.15
            score += (r['total_trades'] / max(x['total_trades'] for x in valid_results)) * 0.1
            scores.append((r, score))

        best = max(scores, key=lambda x: x[1])
        r = best[0]

        logger.info("🏆 RECOMMENDED CONFIGURATION")
        logger.info("=" * 80)
        logger.info("")
        logger.info(f"   MIN_ML_CONFIDENCE={r['min_confidence']:.2f}")
        logger.info("")
        logger.info(f"📊 Metrics:")
        logger.info(f"   Total Trades: {r['total_trades']}")
        logger.info(f"   Win Rate: {r['win_rate']*100:.1f}%")
        logger.info(f"   ROI: {r['roi']:+.2f}%")
        logger.info(f"   Sharpe: {r['sharpe_ratio']:.2f}")
        logger.info(f"   Max DD: {r['max_drawdown']:.2f}%")
        logger.info(f"   Profit Factor: {r['profit_factor']:.2f}")
        logger.info("")

    logger.info("=" * 80)


if __name__ == "__main__":
    main()
