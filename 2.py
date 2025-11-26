"""
VALIDAÇÃO SEM COOLDOWN
Versão do backtest sem cooldown entre trades - permite abertura imediata após fechar posição
Ideal para testar máximo de oportunidades e evitar perder sinais válidos
"""

import sys
from pathlib import Path
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning, message='.*Boolean Series key.*')
sys.path.append(str(Path(__file__).parent))

import pandas as pd
import numpy as np
from typing import Dict, List
import logging
import argparse
import pickle
from datetime import datetime

from core.utils import load_config, setup_logging
from core.bybit_rest import BybitRESTClient
from core.data import DataManager
from core.features import FeatureStore
from scipy import stats

logger = None


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
        # Handle missing ModelWrapper class
        if name == 'ModelWrapper':
            return ModelWrapper
        # Try normal loading first
        try:
            return super().find_class(module, name)
        except (AttributeError, ModuleNotFoundError):
            # If class not found, return a generic wrapper
            return type(name, (), {})


def load_model_universal(model_path: str) -> dict:
    """
    Universal model loader that works with any pickle format.

    Supports:
    - Standard dict format: {'model': ..., 'feature_names': ...}
    - ModelWrapper format
    - Direct model objects
    - Any custom format

    Returns standardized dict with:
    - model: The actual ML model
    - feature_names: List of feature names
    - optimal_threshold: float (default 0.5)
    """
    logger.info(f"🔍 Loading model: {model_path}")

    try:
        # Method 1: Standard pickle load
        with open(model_path, 'rb') as f:
            data = pickle.load(f)

        logger.info(f"   ✅ Loaded with standard pickle")

    except Exception as e1:
        logger.info(f"   ⚠️ Standard load failed: {str(e1)[:50]}")

        # Method 2: Custom unpickler
        try:
            with open(model_path, 'rb') as f:
                data = UniversalUnpickler(f).load()
            logger.info(f"   ✅ Loaded with custom unpickler")
        except Exception as e2:
            raise ValueError(f"Failed to load model: {e2}")

    # Now extract model information from whatever format we got
    result = {
        'model': None,
        'feature_names': None,
        'optimal_threshold': 0.5,
        'raw_data': data
    }

    # First, log what we're dealing with
    data_type = type(data).__name__
    logger.info(f"   📦 Type: {data_type}")

    # Try to get all attributes available
    attrs = []
    if hasattr(data, '__dict__'):
        try:
            attrs = [k for k in data.__dict__.keys() if not k.startswith('_')]
            logger.info(f"   📋 Object attributes: {', '.join(attrs[:15])}")
            if len(attrs) > 15:
                logger.info(f"      ... and {len(attrs) - 15} more")
        except:
            pass

    # Case 1: Standard dict format
    if isinstance(data, dict):
        result['model'] = data.get('model')
        result['feature_names'] = data.get('feature_names') or data.get('features')
        result['optimal_threshold'] = data.get('optimal_threshold', 0.5)
        logger.info(f"   📦 Format: Dict with keys: {list(data.keys())}")

    # Case 2: Object with attributes (ModelWrapper, custom objects, etc.)
    else:
        logger.info(f"   📦 Format: Object")

        # Extract model - try multiple possible locations
        if hasattr(data, 'model'):
            result['model'] = getattr(data, 'model')
            logger.info(f"   ✅ Found model in: data.model")
        elif hasattr(data, 'models'):
            # Ensemble model (multiple models)
            result['model'] = getattr(data, 'models')
            logger.info(f"   ✅ Found model in: data.models (ensemble)")
        elif hasattr(data, 'lgb_model'):
            result['model'] = getattr(data, 'lgb_model')
            logger.info(f"   ✅ Found model in: data.lgb_model")
        elif hasattr(data, 'ml_model'):
            result['model'] = getattr(data, 'ml_model')
            logger.info(f"   ✅ Found model in: data.ml_model")
        else:
            # Maybe the object itself IS the model wrapper
            result['model'] = data
            logger.info(f"   ⚠️ Using entire object as model wrapper")

        # Try multiple attribute names for feature_names
        possible_feature_attrs = [
            'feature_names', 'features', 'feature_cols', 'cols',
            'feature_list', 'columns', 'feature_names_',
            'input_features', 'selected_features', 'feature_columns'
        ]

        for attr_name in possible_feature_attrs:
            if hasattr(data, attr_name):
                feat = getattr(data, attr_name)
                if feat is not None and len(feat) > 0:
                    result['feature_names'] = feat
                    logger.info(f"   ✅ Found feature_names in: data.{attr_name} ({len(feat)} features)")
                    break

        result['optimal_threshold'] = getattr(data, 'optimal_threshold', 0.5)

    # Validate we got the essentials
    if result['model'] is None:
        raise ValueError("Could not extract model from pickle file")

    # Try to detect feature_names from model if not found
    if result['feature_names'] is None:
        logger.info("   🔍 Trying to extract feature_names from model object...")

        # Try LightGBM methods
        if hasattr(result['model'], 'feature_name_'):
            try:
                result['feature_names'] = result['model'].feature_name_()
                logger.info(f"   ✅ Extracted feature_names from model.feature_name_()")
            except Exception as e:
                logger.info(f"      Failed: {str(e)[:50]}")

        # Try sklearn methods
        elif hasattr(result['model'], 'feature_names_in_'):
            try:
                result['feature_names'] = list(result['model'].feature_names_in_)
                logger.info(f"   ✅ Extracted feature_names from model.feature_names_in_")
            except Exception as e:
                logger.info(f"      Failed: {str(e)[:50]}")

        # Try other common attributes
        elif hasattr(result['model'], 'feature_name'):
            try:
                result['feature_names'] = result['model'].feature_name
                logger.info(f"   ✅ Extracted feature_names from model.feature_name")
            except Exception as e:
                logger.info(f"      Failed: {str(e)[:50]}")

    # Last resort: check if model has __dict__ and show what's inside
    if result['feature_names'] is None:
        logger.warning("   ⚠️ Could not auto-detect feature_names")

        # Show what's in the model
        if hasattr(result['model'], '__dict__'):
            model_attrs = [k for k in result['model'].__dict__.keys() if not k.startswith('_')]
            if model_attrs:
                logger.info(f"   📋 Model attributes: {', '.join(model_attrs[:10])}")

        # Show what's in raw_data if it's an object
        if hasattr(result['raw_data'], '__dict__'):
            data_attrs = [k for k in result['raw_data'].__dict__.keys() if not k.startswith('_')]
            if data_attrs:
                logger.info(f"   📋 Raw data has these attributes: {', '.join(data_attrs)}")
                logger.info("")
                logger.info("   💡 TIP: Try one of these names for feature_names!")

        raise ValueError(
            "Could not find feature_names in model.\n"
            "Please check the attribute names above and update the model or code."
        )

    logger.info(f"   ✅ Model loaded successfully")
    logger.info(f"   📊 Features: {len(result['feature_names'])}")
    logger.info(f"   🎯 Threshold: {result['optimal_threshold']:.3f}")

    return result


def create_classical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create classical technical analysis features.

    Used by older models that expect standard TA indicators:
    - returns, log_returns, volatility
    - ATR (14, 20)
    - SMA/EMA (7, 14, 21, 50, 100, 200)
    - momentum, ROC, RSI, Stoch RSI
    - volume indicators
    - channel position
    """
    df_feat = df.copy()

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

    # Momentum
    for period in [10, 20, 30]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100

    # ROC
    df_feat['roc_30'] = ((df_feat['close'] - df_feat['close'].shift(30)) / df_feat['close'].shift(30)) * 100

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
    """Add MASTER TRADER advanced features - V1 (original)"""

    df_features = df.copy()

    # Multi-period momentum
    for period in [3, 5, 8, 13, 21]:
        df_features[f'momentum_{period}'] = df_features['close'].pct_change(period) * 100
        df_features[f'volume_ratio_{period}'] = df_features['volume'] / df_features['volume'].rolling(period).mean()

    # Trend strength
    df_features['trend_strength'] = (df_features['ema50'] - df_features['ema200']) / df_features['ema200'] * 100

    # Volatility regimes
    df_features['volatility_regime'] = (df_features['atr'] / df_features['atr'].rolling(50).mean())

    # Price position in recent range
    df_features['price_position'] = (
        (df_features['close'] - df_features['low'].rolling(20).min()) /
        (df_features['high'].rolling(20).max() - df_features['low'].rolling(20).min())
    )

    # Volume momentum
    df_features['volume_momentum'] = df_features['volume'].pct_change(5)

    # Acceleration
    df_features['price_acceleration'] = df_features['close'].diff(2) - df_features['close'].diff(1)

    return df_features


def create_advanced_features_v2(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add V2 ADVANCED features - MUST match train_master_scalper_v2.py exactly!

    NEW FEATURES:
    - Market microstructure
    - Higher order moments (skewness, kurtosis)
    - Regime detection
    - Order flow proxies
    - Multi-timeframe confluence
    """

    df_features = df.copy()

    # === BASIC MOMENTUM (Multiple timeframes) ===
    for period in [3, 5, 8, 13, 21, 34]:
        df_features[f'momentum_{period}'] = df_features['close'].pct_change(period) * 100
        df_features[f'volume_ratio_{period}'] = df_features['volume'] / df_features['volume'].rolling(period).mean()

    # === TREND STRENGTH ===
    df_features['trend_strength'] = (df_features['ema50'] - df_features['ema200']) / df_features['ema200'] * 100
    df_features['trend_consistency'] = df_features['close'].rolling(20).apply(
        lambda x: (x.iloc[-1] > x.iloc[0]) == (x.diff().mean() > 0)
    )

    # === VOLATILITY REGIME ===
    df_features['volatility_regime'] = df_features['atr'] / df_features['atr'].rolling(50).mean()
    df_features['volatility_change'] = df_features['atr'].pct_change(5)

    # === PRICE POSITION IN RANGE ===
    for period in [10, 20, 50]:
        high_period = df_features['high'].rolling(period).max()
        low_period = df_features['low'].rolling(period).min()
        df_features[f'price_position_{period}'] = (
            (df_features['close'] - low_period) / (high_period - low_period + 1e-8)
        )

    # === VOLUME ANALYSIS ===
    df_features['volume_momentum'] = df_features['volume'].pct_change(5)
    df_features['volume_acceleration'] = df_features['volume'].diff(2) - df_features['volume'].diff(1)

    # Price-volume correlation
    df_features['price_volume_corr'] = df_features['close'].rolling(20).corr(df_features['volume'])

    # === ACCELERATION & JERK ===
    df_features['price_velocity'] = df_features['close'].diff(1)
    df_features['price_acceleration'] = df_features['price_velocity'].diff(1)
    df_features['price_jerk'] = df_features['price_acceleration'].diff(1)

    # === HIGHER ORDER MOMENTS (Robustness) ===
    for period in [10, 20, 50]:
        returns = df_features['close'].pct_change()
        df_features[f'returns_skew_{period}'] = returns.rolling(period).skew()
        df_features[f'returns_kurt_{period}'] = returns.rolling(period).kurt()
        df_features[f'returns_std_{period}'] = returns.rolling(period).std()

    # === MARKET MICROSTRUCTURE ===
    # Bid-ask spread proxy (high-low as % of close)
    df_features['spread_proxy'] = (df_features['high'] - df_features['low']) / df_features['close'] * 100

    # Price efficiency (how much price deviates from moving average)
    for period in [10, 20]:
        ma = df_features['close'].rolling(period).mean()
        df_features[f'price_efficiency_{period}'] = (df_features['close'] - ma) / ma * 100

    # === REGIME DETECTION ===
    # Trending vs ranging market
    df_features['adx_proxy'] = df_features['atr'] / df_features['close'] * 100

    # Volume regime (high vs low volume periods)
    median_volume = df_features['volume'].rolling(100).median()
    df_features['volume_regime'] = (df_features['volume'] > median_volume).astype(int)

    # === RELATIVE STRENGTH ===
    for period in [5, 10, 20]:
        gains = df_features['close'].diff().clip(lower=0)
        losses = -df_features['close'].diff().clip(upper=0)

        avg_gain = gains.rolling(period).mean()
        avg_loss = losses.rolling(period).mean()

        rs = avg_gain / (avg_loss + 1e-8)
        df_features[f'rsi_{period}'] = 100 - (100 / (1 + rs))

    # === MOMENTUM OSCILLATORS ===
    # Rate of change
    for period in [5, 10, 20]:
        df_features[f'roc_{period}'] = (
            (df_features['close'] - df_features['close'].shift(period)) /
            df_features['close'].shift(period) * 100
        )

    # === BOLLINGER BANDS FEATURES ===
    for period in [20, 50]:
        sma = df_features['close'].rolling(period).mean()
        std = df_features['close'].rolling(period).std()

        df_features[f'bb_position_{period}'] = (df_features['close'] - sma) / (2 * std + 1e-8)
        df_features[f'bb_width_{period}'] = (4 * std) / sma * 100

    # === CANDLE PATTERNS (Simple) ===
    body = abs(df_features['close'] - df_features['open'])
    upper_shadow = df_features['high'] - df_features[['close', 'open']].max(axis=1)
    lower_shadow = df_features[['close', 'open']].min(axis=1) - df_features['low']

    df_features['body_size'] = body / df_features['close'] * 100
    df_features['upper_shadow_ratio'] = upper_shadow / (body + 1e-8)
    df_features['lower_shadow_ratio'] = lower_shadow / (body + 1e-8)

    return df_features


def create_ultra_scalper_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create ALL 87 features for ultra_scalper model.

    Advanced features including:
    - Order flow (taker buy/sell, pressure, imbalance)
    - Pattern detection (streaks, divergences, higher high/lower low)
    - Session detection (Asian, London, US, weekend)
    - Advanced momentum and volatility
    - Cross detection, microstructure
    """
    df_feat = df.copy()

    # Creating ultra_scalper features...

    # === BASIC RETURNS (for compatibility) ===
    df_feat['returns_5'] = df_feat['close'].pct_change(5)
    df_feat['returns_10'] = df_feat['close'].pct_change(10)

    # === CANDLE FEATURES ===
    body = abs(df_feat['close'] - df_feat['open'])
    upper_wick = df_feat['high'] - df_feat[['close', 'open']].max(axis=1)
    lower_wick = df_feat[['close', 'open']].min(axis=1) - df_feat['low']

    df_feat['total_wick'] = upper_wick + lower_wick
    df_feat['wick_body_ratio'] = df_feat['total_wick'] / (body + 1e-8)

    # Additional candle features for compatibility
    df_feat['body_pct'] = body / df_feat['close'] * 100
    df_feat['upper_wick_pct'] = upper_wick / df_feat['close'] * 100
    df_feat['lower_wick_pct'] = lower_wick / df_feat['close'] * 100

    is_green = (df_feat['close'] > df_feat['open']).astype(int)
    is_red = (df_feat['close'] < df_feat['open']).astype(int)

    df_feat['green_streak'] = (is_green * (is_green.groupby((is_green != is_green.shift()).cumsum()).cumcount() + 1))
    df_feat['red_streak'] = (is_red * (is_red.groupby((is_red != is_red.shift()).cumsum()).cumcount() + 1))

    hl_range = df_feat['high'] - df_feat['low']
    hl_range_ma = hl_range.rolling(20).mean()
    df_feat['large_candle'] = (hl_range > hl_range_ma * 1.5).astype(int)

    # === ORDER FLOW (simulated) ===
    close_position_in_candle = (df_feat['close'] - df_feat['low']) / (df_feat['high'] - df_feat['low'] + 1e-8)

    df_feat['taker_buy_ratio'] = close_position_in_candle
    df_feat['taker_sell_ratio'] = 1 - close_position_in_candle

    df_feat['buy_pressure_ma'] = df_feat['taker_buy_ratio'].rolling(20).mean()
    df_feat['sell_pressure_ma'] = df_feat['taker_sell_ratio'].rolling(20).mean()
    df_feat['pressure_delta'] = df_feat['buy_pressure_ma'] - df_feat['sell_pressure_ma']
    df_feat['pressure_momentum'] = df_feat['pressure_delta'].diff(5)

    # Aliases for compatibility
    df_feat['buy_pressure'] = df_feat['buy_pressure_ma']
    df_feat['sell_pressure'] = df_feat['sell_pressure_ma']

    df_feat['order_imbalance'] = (df_feat['taker_buy_ratio'] - df_feat['taker_sell_ratio']) * df_feat['volume']
    df_feat['imbalance_ma'] = df_feat['order_imbalance'].rolling(20).mean()

    # === PRICE VS SMA RATIOS ===
    sma7 = df_feat['close'].rolling(7).mean()
    sma14 = df_feat['close'].rolling(14).mean()
    sma21 = df_feat['close'].rolling(21).mean()
    sma50 = df_feat['close'].rolling(50).mean()

    for period in [7, 14, 21, 50]:
        sma = df_feat['close'].rolling(period).mean()
        df_feat[f'price_sma_{period}_ratio'] = (df_feat['close'] - sma) / sma * 100

    # Additional price vs MA features for compatibility
    df_feat['price_vs_sma7'] = (df_feat['close'] - sma7) / sma7 * 100
    df_feat['price_vs_sma21'] = (df_feat['close'] - sma21) / sma21 * 100

    # === EMA CROSSES ===
    ema7 = df_feat['close'].ewm(span=7, adjust=False).mean()
    ema14 = df_feat['close'].ewm(span=14, adjust=False).mean()
    ema21 = df_feat['close'].ewm(span=21, adjust=False).mean()
    ema50 = df_feat['close'].ewm(span=50, adjust=False).mean()
    ema200 = df_feat['close'].ewm(span=200, adjust=False).mean()

    df_feat['ema7_above_ema14'] = (ema7 > ema14).astype(int)
    df_feat['ema14_above_ema21'] = (ema14 > ema21).astype(int)
    df_feat['ema21_above_ema50'] = (ema21 > ema50).astype(int)

    # Additional EMA/SMA crosses for compatibility
    df_feat['sma7_above_sma21'] = (sma7 > sma21).astype(int)
    df_feat['ema7_above_ema21'] = (ema7 > ema21).astype(int)
    df_feat['price_vs_ema14'] = (df_feat['close'] - ema14) / ema14 * 100

    df_feat['golden_cross'] = ((ema50 > ema200) & (ema50.shift(1) <= ema200.shift(1))).astype(int)
    df_feat['death_cross'] = ((ema50 < ema200) & (ema50.shift(1) >= ema200.shift(1))).astype(int)

    # === ATR AND VOLATILITY ===
    high_low = df_feat['high'] - df_feat['low']
    high_close = abs(df_feat['high'] - df_feat['close'].shift())
    low_close = abs(df_feat['low'] - df_feat['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(14).mean()

    df_feat['atr_pct'] = atr / df_feat['close'] * 100

    returns = df_feat['close'].pct_change()
    df_feat['volatility_7'] = returns.rolling(7).std() * 100
    df_feat['volatility_21'] = returns.rolling(21).std() * 100

    df_feat['volatility_ratio'] = df_feat['volatility_7'] / (df_feat['volatility_21'] + 1e-8)

    vol_median = df_feat['volatility_21'].rolling(50).median()
    df_feat['high_volatility'] = (df_feat['volatility_21'] > vol_median * 1.5).astype(int)
    df_feat['low_volatility'] = (df_feat['volatility_21'] < vol_median * 0.7).astype(int)

    # === RSI FEATURES ===
    delta = df_feat['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))

    df_feat['rsi_extreme_oversold'] = (rsi < 20).astype(int)
    df_feat['rsi_extreme_overbought'] = (rsi > 80).astype(int)
    df_feat['rsi_mid'] = ((rsi >= 40) & (rsi <= 60)).astype(int)
    df_feat['rsi_neutral'] = ((rsi >= 40) & (rsi <= 60)).astype(int)  # Alias for compatibility

    # === SLOPE FEATURES ===
    def calculate_slope(series, window=5):
        slopes = []
        for i in range(len(series)):
            if i < window:
                slopes.append(0)
            else:
                y = series.iloc[i-window:i].values
                x = np.arange(window)
                if len(y) == window:
                    slope = np.polyfit(x, y, 1)[0]
                    slopes.append(slope)
                else:
                    slopes.append(0)
        return pd.Series(slopes, index=series.index)

    df_feat['price_slope'] = calculate_slope(df_feat['close'], window=5)
    df_feat['rsi_slope'] = calculate_slope(rsi, window=5)

    # === DIVERGENCE DETECTION ===
    price_higher = df_feat['close'] > df_feat['close'].shift(5)
    rsi_lower = rsi < rsi.shift(5)
    price_lower = df_feat['close'] < df_feat['close'].shift(5)
    rsi_higher = rsi > rsi.shift(5)

    df_feat['bullish_divergence'] = (price_lower & rsi_higher).astype(int)
    df_feat['bearish_divergence'] = (price_higher & rsi_lower).astype(int)

    # === MACD FEATURES ===
    ema12 = df_feat['close'].ewm(span=12, adjust=False).mean()
    ema26 = df_feat['close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal

    df_feat['macd_hist_increasing'] = (macd_hist > macd_hist.shift(1)).astype(int)

    # === BOLLINGER BANDS ===
    sma20 = df_feat['close'].rolling(20).mean()
    std20 = df_feat['close'].rolling(20).std()
    bb_upper = sma20 + (2 * std20)
    bb_lower = sma20 - (2 * std20)

    df_feat['bb_upper_breakout'] = (df_feat['close'] > bb_upper).astype(int)
    df_feat['bb_lower_breakout'] = (df_feat['close'] < bb_lower).astype(int)

    # === VOLUME FEATURES ===
    df_feat['volume_sma_20'] = df_feat['volume'].rolling(20).mean()

    vol_median = df_feat['volume'].rolling(50).median()
    df_feat['high_volume'] = (df_feat['volume'] > vol_median * 1.5).astype(int)

    df_feat['volume_slope'] = calculate_slope(df_feat['volume'], window=5)
    df_feat['volume_increasing_trend'] = (df_feat['volume_slope'] > 0).astype(int)

    # === MOMENTUM FEATURES ===
    for period in [3, 5, 7, 8, 13, 14, 21]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100

    df_feat['momentum_accel'] = df_feat['momentum_7'].diff(3)

    # === PRICE POSITION ===
    for period in [14, 50]:
        high_period = df_feat['high'].rolling(period).max()
        low_period = df_feat['low'].rolling(period).min()
        df_feat[f'price_position_{period}'] = (df_feat['close'] - low_period) / (high_period - low_period + 1e-8)

    # === SWING POINTS ===
    df_feat['higher_high'] = (df_feat['high'] > df_feat['high'].shift(1)).astype(int)
    df_feat['lower_low'] = (df_feat['low'] < df_feat['low'].shift(1)).astype(int)

    df_feat['hh_count'] = df_feat['higher_high'].rolling(10).sum()
    df_feat['ll_count'] = df_feat['lower_low'].rolling(10).sum()

    # === TREND STRENGTH ===
    plus_dm = df_feat['high'].diff()
    minus_dm = -df_feat['low'].diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    tr_smooth = true_range.rolling(14).mean()
    plus_di = (plus_dm.rolling(14).mean() / (tr_smooth + 1e-10)) * 100
    minus_di = (minus_dm.rolling(14).mean() / (tr_smooth + 1e-10)) * 100

    dx = abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100
    adx = dx.rolling(14).mean()

    df_feat['trend_strength'] = adx

    # === SESSION/TIME FEATURES ===
    if isinstance(df_feat.index, pd.DatetimeIndex):
        df_feat['hour'] = df_feat.index.hour
        df_feat['day_of_week'] = df_feat.index.dayofweek

        df_feat['asian_session'] = ((df_feat['hour'] >= 0) & (df_feat['hour'] < 9)).astype(int)
        df_feat['london_session'] = ((df_feat['hour'] >= 7) & (df_feat['hour'] < 16)).astype(int)
        df_feat['us_session'] = ((df_feat['hour'] >= 13) & (df_feat['hour'] < 22)).astype(int)
        df_feat['weekend'] = (df_feat['day_of_week'] >= 5).astype(int)
    else:
        df_feat['hour'] = 12
        df_feat['day_of_week'] = 2
        df_feat['asian_session'] = 0
        df_feat['london_session'] = 1
        df_feat['us_session'] = 0
        df_feat['weekend'] = 0

    # === SPREAD FEATURES ===
    df_feat['spread_proxy'] = (df_feat['high'] - df_feat['low']) / df_feat['close'] * 100
    df_feat['spread_ma'] = df_feat['spread_proxy'].rolling(20).mean()

    # Fill NaN
    df_feat = df_feat.fillna(method='ffill').fillna(method='bfill').fillna(0)

    # Ultra scalper features created

    return df_feat


class StrategyValidator:
    """Valida a estratégia com diferentes configurações."""

    def __init__(self, config: dict, model_path: str, verbose_trades: bool = False, fee_type: str = 'taker',
                 sl_atr_mult: float = 2.0, tp_atr_mult: float = 1.0):
        self.config = config
        self.model_path = Path(model_path)
        self.verbose_trades = verbose_trades  # Control trade-by-trade logging
        self.fee_type = fee_type  # 'maker' or 'taker'
        self.sl_atr_mult = sl_atr_mult  # Stop loss ATR multiplier
        self.tp_atr_mult = tp_atr_mult  # Take profit ATR multiplier

        if not self.model_path.exists():
            raise ValueError(f"Model not found: {model_path}")

        # Load model using universal loader
        self.model_data = load_model_universal(str(self.model_path))

        self.model = self.model_data['model']
        self.feature_names = self.model_data['feature_names']
        self.optimal_threshold = self.model_data['optimal_threshold']

        self.initial_capital = config.get('initial_capital', 10000)
        self.risk_per_trade = config.get('risk_per_trade_pct', 0.75) / 100

        # Bybit trading fees
        if fee_type == 'maker':
            self.trading_fee = config.get('maker_fee', 0.0002)  # 0.02% maker fee (or rebate)
        else:
            self.trading_fee = config.get('taker_fee', 0.00055)  # 0.055% taker fee

        # Detect model type based on features
        self.model_type = self._detect_model_type()
        logger.info(f"   🎯 Detected model type: {self.model_type}")
        logger.info(f"   💰 Fee mode: {fee_type.upper()} ({self.trading_fee*100:.3f}%)")

    def _detect_model_type(self) -> str:
        """Detect model type based on required features."""
        features_set = set(self.feature_names)

        # Ultra Scalper signatures
        ultra_scalper_features = {
            'total_wick', 'wick_body_ratio', 'green_streak', 'taker_buy_ratio',
            'order_imbalance', 'asian_session', 'spread_proxy'
        }

        # V2 Advanced signatures
        v2_features = {
            'returns_kurt_50', 'rsi_5', 'bb_width_50', 'order_flow_imbalance',
            'taker_buy_sell_ratio', 'price_momentum_3'
        }

        # V1 Advanced signatures
        v1_features = {
            'momentum_3', 'momentum_5', 'volume_ratio_3', 'swing_high', 'swing_low'
        }

        # Classical signatures
        classical_features = {
            'roc_5', 'roc_10', 'roc_20', 'roc_30', 'stoch_rsi'
        }

        # Check for ultra scalper
        if len(ultra_scalper_features & features_set) >= 3:
            return 'Ultra Scalper'

        # Check for V2
        if len(v2_features & features_set) >= 2:
            return 'V2 Advanced'

        # Check for V1
        if len(v1_features & features_set) >= 2:
            return 'V1 Advanced'

        # Check for Classical
        if len(classical_features & features_set) >= 2:
            return 'Classical'

        return 'Unknown'

    def _add_missing_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add missing features based on model type."""
        missing = [f for f in self.feature_names if f not in df.columns]

        if not missing:
            return df

        logger.info(f"   ⚠️  Missing {len(missing)} features, creating them...")

        # Create features based on model type
        if self.model_type == 'Ultra Scalper':
            df = create_ultra_scalper_features(df)
        elif self.model_type == 'V2 Advanced':
            df = create_advanced_features_v2(df)
        elif self.model_type == 'V1 Advanced':
            df = create_advanced_features(df)
        elif self.model_type == 'Classical':
            df = create_classical_features(df)
        else:
            logger.warning(f"   ⚠️  Unknown model type, trying all feature sets...")
            # Try creating all features
            df = create_classical_features(df)
            df = create_advanced_features(df)
            df = create_advanced_features_v2(df)
            df = create_ultra_scalper_features(df)

        # Check if all features are now present
        still_missing = [f for f in self.feature_names if f not in df.columns]
        if still_missing:
            logger.error(f"   ❌ Still missing {len(still_missing)} features: {still_missing[:10]}")
            raise KeyError(f"Missing features after creation: {still_missing}")

        return df

    def _predict_from_wrapper(self, X):
        """Make predictions from ModelWrapper ensemble."""
        # ModelWrapper structure:
        # - models_list: list of models
        # - model_weights: weights for each model
        # - scaler: scaler for normalization (optional)

        import warnings

        try:
            # Apply scaler if exists
            if hasattr(self.model, 'scaler') and self.model.scaler is not None:
                # Suppress sklearn feature name warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    X_scaled = self.model.scaler.transform(X)
            else:
                X_scaled = X.values if hasattr(X, 'values') else X

            # Get predictions from each model
            if hasattr(self.model, 'models_list') and self.model.models_list:
                predictions = []
                model_names = getattr(self.model, 'model_names', [f'Model_{i}' for i in range(len(self.model.models_list))])

                for i, model in enumerate(self.model.models_list):
                    model_name = model_names[i] if i < len(model_names) else f'Model_{i}'
                    model_type = type(model).__name__

                    try:
                        # Detect Deep Learning models (Keras/TensorFlow)
                        is_dl = model_type in ['Sequential', 'Functional', 'Model'] or 'keras' in str(type(model)).lower()

                        if is_dl:
                            # Deep Learning models
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore")
                                # DL models need numpy array, may need reshape
                                X_dl = np.array(X_scaled)
                                if len(X_dl.shape) == 1:
                                    X_dl = X_dl.reshape(-1, 1)

                                pred = model.predict(X_dl, verbose=0)

                                # Squeeze if needed
                                if len(pred.shape) > 1:
                                    if pred.shape[1] == 1:
                                        pred = pred.squeeze()
                                    else:
                                        # Multi-class, get positive class
                                        pred = pred[:, -1] if pred.shape[1] > 1 else pred.squeeze()
                        else:
                            # Traditional ML models (LightGBM, XGBoost, etc.)
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore")

                                if hasattr(model, 'predict_proba'):
                                    pred = model.predict_proba(X_scaled)
                                    # Get probability of class 1
                                    if len(pred.shape) > 1 and pred.shape[1] > 1:
                                        pred = pred[:, 1]
                                elif hasattr(model, 'predict'):
                                    pred = model.predict(X_scaled)
                                else:
                                    continue

                        predictions.append(pred)

                    except Exception as e:
                        # Log error but continue with other models
                        error_msg = str(e)[:80]
                        if i == 0:
                            # Only show first error to avoid spam
                            logger.debug(f"   ⚠️  {model_name} ({model_type}) failed: {error_msg}")
                        continue

                if not predictions:
                    raise ValueError("No model could make predictions")

                # Report success rate
                success_count = len(predictions)
                total_count = len(self.model.models_list)
                if success_count < total_count:
                    logger.info(f"   📊 Ensemble: {success_count}/{total_count} models succeeded")

                # Combine predictions with weights if available
                if hasattr(self.model, 'model_weights') and self.model.model_weights:
                    # Weighted average (only for successful models)
                    weights = np.array(self.model.model_weights[:len(predictions)])
                    weights = weights / weights.sum()  # Normalize

                    final_pred = np.zeros_like(predictions[0])
                    for pred, weight in zip(predictions, weights):
                        final_pred += pred * weight
                else:
                    # Simple average
                    final_pred = np.mean(predictions, axis=0)

                return final_pred
            else:
                raise ValueError("ModelWrapper has no models_list")

        except Exception as e:
            logger.error(f"   ❌ Error in _predict_from_wrapper: {str(e)}")
            raise

    def backtest_with_confidence(self, df: pd.DataFrame, min_confidence: float) -> Dict:
        """Run backtest com filtro de confiança mínima."""

        # Add missing features if needed
        df = self._add_missing_features(df)

        # Get ML predictions
        X = df[self.feature_names].fillna(0)

        # Replace inf values
        X = X.replace([np.inf, -np.inf], 0)

        # Try to predict - model could be a wrapper with custom predict
        try:
            ml_probs = self.model.predict(X)
        except AttributeError:
            # If model doesn't have predict, maybe it's an ensemble wrapper
            if hasattr(self.model, '__call__'):
                ml_probs = self.model(X)
            elif hasattr(self.model, 'models_list'):
                # ModelWrapper with ensemble
                logger.info(f"   🔄 Using ensemble prediction from ModelWrapper")
                ml_probs = self._predict_from_wrapper(X)
            else:
                raise ValueError("Model has no predict() or __call__() method")

        df['ml_prob_up'] = ml_probs
        df['ml_prob_down'] = 1 - ml_probs
        df['ml_confidence'] = np.abs(ml_probs - self.optimal_threshold) * 2

        # Generate signals with confidence filter using optimal threshold
        df['signal'] = 0
        mask_long = (df['ml_prob_up'] > self.optimal_threshold) & (df['ml_confidence'] >= min_confidence)
        mask_short = (df['ml_prob_down'] > (1 - self.optimal_threshold)) & (df['ml_confidence'] >= min_confidence)

        df.loc[mask_long, 'signal'] = 1
        df.loc[mask_short, 'signal'] = -1
        
        # Simulate
        trades = self._simulate(df)
        
        # Stats
        stats = self._calculate_stats(trades, df, min_confidence)
        
        return stats
    
    def _simulate(self, df: pd.DataFrame) -> List[Dict]:
        trades = []
        position = None
        capital = self.initial_capital

        # Backtest simulation starting (logs suppressed for clean output)

        for i in range(len(df)):
            current = df.iloc[i]

            # Check exit
            if position:
                exit_reason = self._check_exit(position, current, i)
                if exit_reason:
                    trade = self._close_trade(position, current, exit_reason)
                    trades.append(trade)
                    capital += trade['pnl_amount']
                    position = None

            # Check entry (SEM COOLDOWN)
            if not position and current['signal'] != 0 and i < len(df) - 20:
                position = self._open_trade(current, capital, i)

        # Close final position
        if position:
            trade = self._close_trade(position, df.iloc[-1], 'end_of_data')
            trades.append(trade)

        # Grid search mode: skip detailed logs
        return trades
    
    def _open_trade(self, current, capital, idx):
        direction = 'long' if current['signal'] == 1 else 'short'
        price = current['close']
        atr = current.get('atr', price * 0.01)

        if direction == 'long':
            sl = price - (atr * self.sl_atr_mult)
            tp1 = price + (atr * self.tp_atr_mult)
        else:
            sl = price + (atr * self.sl_atr_mult)
            tp1 = price - (atr * self.tp_atr_mult)

        sl_dist = abs((sl - price) / price)
        risk_amt = capital * self.risk_per_trade
        size = risk_amt / sl_dist if sl_dist > 0 else capital * 0.1
        size = min(size, capital * 0.95)

        # ============================================================================
        # REALISMO: Aplicar mínimo e arredondamento da Bybit (igual ao live_bot.py)
        # ============================================================================
        # Bybit exige mínimo de 0.001 BTC e arredondamento em steps de 0.001 BTC
        min_qty_btc = 0.001
        qty_step = 0.001

        # Converter size (USD) para quantidade em BTC
        qty_btc = size / price

        # Forçar mínimo da Bybit
        qty_btc = max(min_qty_btc, qty_btc)

        # Arredondar para step size (0.001 BTC)
        qty_btc = round(qty_btc / qty_step) * qty_step

        # Reconverter para USD (mantém compatibilidade com resto do código)
        size = qty_btc * price

        # Garantir que não ultrapassa 95% do capital
        size = min(size, capital * 0.95)

        # DEBUG: Log trade entry (if verbose)
        if self.verbose_trades:
            direction_emoji = "🟢" if direction == 'long' else "🔴"
            logger.info(f"{direction_emoji} ENTRY #{idx}: {direction.upper()} @ ${price:,.2f}")
            logger.info(f"   Confidence: {current['ml_confidence']:.1%} | Size: ${size:,.2f} | Capital: ${capital:,.2f}")
            logger.info(f"   SL: ${sl:,.2f} ({-abs((sl-price)/price)*100:.1f}%) | TP: ${tp1:,.2f} ({abs((tp1-price)/price)*100:.1f}%)")

        return {
            'entry_idx': idx,
            'entry_time': current.name,
            'entry_price': price,
            'direction': direction,
            'size': size,
            'stop_loss': sl,
            'tp1': tp1,
            'ml_confidence': current['ml_confidence']
        }
    
    def _check_exit(self, position, current, idx):
        high = current['high']
        low = current['low']
        direction = position['direction']

        if direction == 'long':
            if low <= position['stop_loss']:
                return 'stop_loss'
            if high >= position['tp1']:
                return 'take_profit_1'
        else:
            if high >= position['stop_loss']:
                return 'stop_loss'
            if low <= position['tp1']:
                return 'take_profit_1'

        # Time exit (48h)
        if idx - position['entry_idx'] > 192:
            return 'time_exit'

        return None
    
    def _close_trade(self, position, current, reason):
        if reason == 'stop_loss':
            exit_price = position['stop_loss']
        elif reason == 'take_profit_1':
            exit_price = position['tp1']
        else:
            exit_price = current['close']

        entry = position['entry_price']
        direction = position['direction']

        if direction == 'long':
            pnl_pct = ((exit_price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - exit_price) / entry) * 100

        pnl_amount = position['size'] * (pnl_pct / 100)

        # Calculate Bybit trading fees (entry + exit)
        entry_fee = position['size'] * self.trading_fee
        exit_fee = position['size'] * self.trading_fee
        total_fees = entry_fee + exit_fee

        # Subtract fees from PnL
        pnl_amount_after_fees = pnl_amount - total_fees
        pnl_pct_after_fees = (pnl_amount_after_fees / position['size']) * 100

        # DEBUG: Log trade exit (if verbose)
        if self.verbose_trades:
            is_win = pnl_amount_after_fees > 0
            result_emoji = "✅" if is_win else "❌"

            # Reason emoji
            reason_map = {
                'stop_loss': '🛑 STOP LOSS',
                'take_profit_1': '🎯 TP',
                'time_exit': '⏰ TIME EXIT',
                'end_of_data': '🏁 END'
            }
            reason_display = reason_map.get(reason, reason.upper())

            direction_emoji = "🟢" if direction == 'long' else "🔴"
            logger.info(f"{result_emoji} EXIT {direction_emoji} {direction.upper()}: {reason_display}")
            logger.info(f"   Entry: ${entry:,.2f} → Exit: ${exit_price:,.2f}")
            logger.info(f"   PnL: {pnl_pct_after_fees:+.2f}% (${pnl_amount_after_fees:+,.2f}) | Fees: ${total_fees:.2f}")
            logger.info(f"   Duration: {position['entry_time']} → {current.name}")
            logger.info("")

        return {
            'entry_time': position['entry_time'],
            'exit_time': current.name,
            'direction': direction,
            'entry_price': entry,
            'exit_price': exit_price,
            'size': position['size'],
            'pnl_pct': pnl_pct_after_fees,
            'pnl_amount': pnl_amount_after_fees,
            'fees': total_fees,
            'reason': reason,
            'ml_confidence': position['ml_confidence']
        }


    def _calculate_stats(self, trades, df, min_confidence):
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

        long_win = len(longs[longs['pnl_amount'] > 0]) if len(longs) > 0 else 0
        long_loss = len(longs[longs['pnl_amount'] <= 0]) if len(longs) > 0 else 0
        short_win = len(shorts[shorts['pnl_amount'] > 0]) if len(shorts) > 0 else 0
        short_loss = len(shorts[shorts['pnl_amount'] <= 0]) if len(shorts) > 0 else 0

        long_wr = (long_win / len(longs) * 100) if len(longs) > 0 else 0
        short_wr = (short_win / len(shorts) * 100) if len(shorts) > 0 else 0

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
            'long_win': long_win,
            'long_loss': long_loss,
            'short_win': short_win,
            'short_loss': short_loss,
            'long_wr': long_wr,
            'short_wr': short_wr,
        }


def main():
    global logger
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', type=str, default='BTCUSDT')
    parser.add_argument('--days', type=int, default=180)
    parser.add_argument('--model', type=str, default='ml_model_master_scalper_365d.pkl')
    parser.add_argument('--verbose-trades', action='store_true', help='Show detailed log for each trade (entry/exit)')
    parser.add_argument('--fee-type', type=str, default='taker', choices=['maker', 'taker'], help='Fee type: maker (0.02%%) or taker (0.055%%)')

    args = parser.parse_args()
    
    config = load_config('standard')
    logger = setup_logging('INFO', log_to_file=False)
    
    logger.info("=" * 80)
    logger.info("🔬 VALIDAÇÃO COMPLETA DA ESTRATÉGIA")
    logger.info("=" * 80)
    logger.info(f"Symbol: {args.symbol}")
    logger.info(f"Period: {args.days} days")
    logger.info(f"Model: {args.model}")
    logger.info("")
    
    # Download data
    logger.info("📥 Downloading data...")
    rest_client = BybitRESTClient(
        api_key=config['bybit_api_key'],
        api_secret=config['bybit_api_secret'],
        testnet=config['bybit_testnet']
    )
    
    dm = DataManager(rest_client)
    df = dm.get_data(args.symbol, '15m', args.days, use_cache=False)
    
    if df.empty:
        logger.error("❌ No data")
        return
    
    logger.info(f"✅ Downloaded {len(df):,} candles")
    logger.info("")
    
    # Load model first to detect version
    model_path = f"storage/models/{args.model}"

    try:
        model_data = load_model_universal(model_path)
        feature_names = model_data['feature_names']
    except Exception as e:
        logger.error(f"❌ Failed to load model: {e}")
        return

    # Detect model version by checking feature names
    classical_features = ['returns', 'log_returns', 'atr_14', 'rsi_14', 'sma_7', 'ema_7', 'volatility']
    v2_features = ['returns_kurt_50', 'returns_skew_50', 'rsi_5', 'roc_20', 'bb_width_50', 'price_position_10']
    v1_features = ['momentum_3', 'momentum_5', 'volume_ratio_3', 'price_position']

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

    logger.info(f"📌 Detected model type: {model_version}")
    logger.info(f"   Required features: {len(feature_names)}")
    logger.info("")

    # Features
    logger.info("🔨 Building features...")
    fs = FeatureStore(config)
    df_features = fs.build_features(df, normalize=False)

    # Apply correct feature engineering based on model version
    if model_version == "Classical":
        logger.info("   Applying Classical TA features...")
        df_features = create_classical_features(df_features)
    elif model_version == "V2":
        logger.info("   Applying V2 advanced features...")
        df_features = create_advanced_features_v2(df_features)
    elif model_version == "V1":
        logger.info("   Applying V1 advanced features...")
        df_features = create_advanced_features(df_features)
    else:
        logger.warning(f"   ⚠️ Unknown model type - trying all features...")
        df_features = create_classical_features(df_features)
        df_features = create_advanced_features(df_features)
        df_features = create_advanced_features_v2(df_features)

    logger.info(f"✅ Features ready: {len(df_features.columns)} columns")
    logger.info("")

    # Validate strategy
    try:
        validator = StrategyValidator(config, model_path, verbose_trades=args.verbose_trades, fee_type=args.fee_type)
        logger.info(f"🎯 Using threshold: {validator.optimal_threshold:.3f}")
        if validator.optimal_threshold != 0.5:
            logger.info(f"   (Optimized threshold from V2 model)")
        if args.verbose_trades:
            logger.info(f"   📢 Verbose trade logging: ENABLED")
        logger.info("")
    except Exception as e:
        logger.error(f"❌ Failed to load model: {e}")
        return

    # ========================================================================
    # GRID SEARCH COMPLETO: Confiança x SL x TP
    # ========================================================================
    logger.info("=" * 80)
    logger.info("🔥 GRID SEARCH - Testando todas as combinações de Confiança x SL x TP")
    logger.info("=" * 80)
    logger.info("")

    # Grid parameters
    confidence_levels = [0.0, 0.25, 0.40, 0.50, 0.60]
    sl_mults = [1.5, 2.0]
    tp_mults = [0.7, 1.0, 1.2]

    total_configs = len(confidence_levels) * len(sl_mults) * len(tp_mults)

    grid_results = []
    count = 0

    for conf in confidence_levels:
        for sl in sl_mults:
            for tp in tp_mults:
                count += 1

                # Create validator with specific ATR settings
                validator_grid = StrategyValidator(
                    config,
                    model_path,
                    verbose_trades=False,
                    fee_type=args.fee_type,
                    sl_atr_mult=sl,
                    tp_atr_mult=tp
                )

                # Run backtest
                stats = validator_grid.backtest_with_confidence(df_features.copy(), conf)

                grid_results.append({
                    'conf': conf,
                    'sl': sl,
                    'tp': tp,
                    'trades': stats.get('total_trades', 0),
                    'wr': stats.get('win_rate', 0),
                    'roi': stats.get('roi', 0),
                    'sharpe': stats.get('sharpe_ratio', 0),
                    'pf': stats.get('profit_factor', 0),
                    'dd': stats.get('max_drawdown', 0),
                    'long_win': stats.get('long_win', 0),
                    'long_loss': stats.get('long_loss', 0),
                    'short_win': stats.get('short_win', 0),
                    'short_loss': stats.get('short_loss', 0)
                })

                logger.info(f"   [{count:>2}/{total_configs}] Conf={conf:>4.0%}, SL={sl:.1f}x, TP={tp:.1f}x → {stats.get('total_trades', 0)} trades, {stats.get('win_rate', 0)*100:.0f}% WR, {stats.get('roi', 0):+.2f}% ROI")

    # Display ALL results
    logger.info("")
    logger.info("=" * 140)
    logger.info("📊 TODAS AS CONFIGURAÇÕES TESTADAS (por ROI)")
    logger.info("=" * 140)
    logger.info("")

    # Sort by ROI
    grid_sorted = sorted(grid_results, key=lambda x: x['roi'], reverse=True)

    header = f"{'#':<3} | {'Conf':<5} | {'SL':<4} | {'TP':<4} | {'Trades':<6} | {'WR':<6} | {'ROI':<8} | {'Sharpe':<6} | {'PF':<5} | {'DD':<6} | {'Long W/L':<9} | {'Short W/L':<9}"
    logger.info(header)
    logger.info("-" * 140)

    for i, r in enumerate(grid_sorted, 1):
        if r['trades'] > 0:
            long_wl = f"{r['long_win']}/{r['long_loss']}"
            short_wl = f"{r['short_win']}/{r['short_loss']}"
            logger.info(
                f"{i:<3} | "
                f"{r['conf']*100:>4.0f}% | "
                f"{r['sl']:>3.1f}x | "
                f"{r['tp']:>3.1f}x | "
                f"{r['trades']:>6} | "
                f"{r['wr']*100:>5.1f}% | "
                f"{r['roi']:>+7.2f}% | "
                f"{r['sharpe']:>6.2f} | "
                f"{r['pf']:>5.2f} | "
                f"{r['dd']:>5.1f}% | "
                f"{long_wl:>9} | "
                f"{short_wl:>9}"
            )

    # Best configuration
    best = grid_sorted[0]

    logger.info("")
    logger.info("=" * 100)
    logger.info("🏆 MELHOR CONFIGURAÇÃO GLOBAL")
    logger.info("=" * 100)
    logger.info("")
    logger.info(f"🎯 Confiança: {best['conf']*100:.0f}%")
    logger.info(f"🛑 SL: {best['sl']:.1f}x ATR")
    logger.info(f"✅ TP: {best['tp']:.1f}x ATR")
    logger.info("")
    logger.info(f"📊 Resultados:")
    logger.info(f"   Trades: {best['trades']}")
    logger.info(f"   Win Rate: {best['wr']*100:.1f}%")
    logger.info(f"   ROI: {best['roi']:+.2f}%")
    logger.info(f"   Sharpe: {best['sharpe']:.2f}")
    logger.info(f"   Profit Factor: {best['pf']:.2f}")
    logger.info(f"   Max Drawdown: {best['dd']:.2f}%")
    logger.info("")
    logger.info("💾 Adicione no seu .env:")
    logger.info(f"   MIN_ML_CONFIDENCE={best['conf']:.2f}")
    logger.info(f"   SL_ATR_MULT={best['sl']:.1f}")
    logger.info(f"   TP_ATR_MULT={best['tp']:.1f}")
    logger.info("")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
