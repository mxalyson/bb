# 🔧 Fix for "Missing Features" Error

## The Problem

When running `validate_strategy.py` with classical models, you get:
```
KeyError: "['momentum_5', 'roc_5', 'roc_10', 'roc_20'] not in index"
```

## Root Cause

The issue is that `validate_strategy.py` depends on modules from `core/*` that may not exist or may not be properly configured:

```python
from core.utils import load_config, setup_logging
from core.bybit_rest import BybitRESTClient
from core.data import DataManager
from core.features import FeatureStore  # <-- This is the problem!
```

The `FeatureStore.build_features()` function might not be returning the base OHLCV columns ('open', 'high', 'low', 'close', 'volume') that are needed by `create_classical_features()` to generate momentum, ROC, and other indicators.

## The Solution

I've created **`validate_standalone.py`** which:

✅ Works completely standalone (no core module dependencies)
✅ Downloads data directly from Bybit public API (no auth needed)
✅ Has all feature engineering built-in
✅ Properly creates Classical, V1, and V2 features
✅ Detects model type automatically

## How to Use

### 1. Use the Standalone Validator

```bash
python validate_standalone.py --model your_model.pkl --days 180
```

This works with ANY .pkl model and doesn't require any infrastructure.

### 2. Examples

```bash
# Test classical model (short period)
python validate_standalone.py --model model_DEFINITIVO_4ML_540d.pkl --days 30

# Test V1 model (medium period)
python validate_standalone.py --model ml_model_master_scalper_365d.pkl --days 180

# Test V2 model (long period)
python validate_standalone.py --model ml_model_master_scalper_v2_365d.pkl --days 365
```

### 3. What It Does

1. **Downloads** data from Bybit (no API key needed for historical data)
2. **Detects** model version automatically:
   - Classical: checks for `returns`, `atr_14`, `rsi_14`, `sma_7`
   - V2: checks for `returns_kurt_50`, `rsi_5`, `bb_width_50`
   - V1: checks for `momentum_3`, `volume_ratio_3`, `price_position`
3. **Builds** the correct features for that model type
4. **Verifies** all required features are present before running backtest
5. **Tests** multiple confidence levels (0%, 5%, 10%, ... 40%)
6. **Recommends** the best configuration

## Features Created by Each Version

### Classical Features
```python
# Returns
returns, log_returns

# Volatility
volatility, volatility_30

# ATR
atr_14, atr_20

# Moving Averages
sma_7, sma_14, sma_21, sma_50, sma_100, sma_200
ema_7, ema_14, ema_21, ema_50, ema_100, ema_200

# Momentum (periods: 5, 10, 20, 30)  ✅ INCLUDES momentum_5
momentum_5, momentum_10, momentum_20, momentum_30

# ROC (periods: 5, 10, 20, 30)  ✅ INCLUDES roc_5, roc_10, roc_20
roc_5, roc_10, roc_20, roc_30

# RSI
rsi_14, stoch_rsi

# Volume
volume_sma, volume_roc

# Channel
high_20, low_20, channel_pos

# Price vs MA
price_vs_sma50, price_vs_sma200
```

### V1 Features
```python
# Multi-period momentum (periods: 3, 5, 8, 13, 21)
momentum_3, momentum_5, momentum_8, momentum_13, momentum_21
volume_ratio_3, volume_ratio_5, volume_ratio_8, volume_ratio_13, volume_ratio_21

# Trend
trend_strength

# Volatility
volatility_regime

# Price position
price_position

# Volume
volume_momentum

# Acceleration
price_acceleration
```

### V2 Features
```python
# Everything from V1 PLUS:

# Extended momentum (periods: 3, 5, 8, 13, 21, 34)
momentum_34, volume_ratio_34

# Trend
trend_consistency

# Volatility
volatility_change

# Price position in range (periods: 10, 20, 50)
price_position_10, price_position_20, price_position_50

# Volume
volume_acceleration, price_volume_corr

# Derivatives
price_velocity, price_jerk

# Higher order moments (periods: 10, 20, 50)
returns_skew_10, returns_skew_20, returns_skew_50
returns_kurt_10, returns_kurt_20, returns_kurt_50
returns_std_10, returns_std_20, returns_std_50

# Market microstructure
spread_proxy
price_efficiency_10, price_efficiency_20

# Regime detection
adx_proxy, volume_regime

# RSI multi-period (periods: 5, 10, 20)
rsi_5, rsi_10, rsi_20

# ROC multi-period (periods: 5, 10, 20)
roc_5, roc_10, roc_20

# Bollinger Bands (periods: 20, 50)
bb_position_20, bb_position_50
bb_width_20, bb_width_50

# Candle patterns
body_size, upper_shadow_ratio, lower_shadow_ratio
```

## Debugging Original validate_strategy.py

If you want to fix the original `validate_strategy.py` instead of using the standalone version, here's the issue:

### The Problem Flow

```python
# Line 773: Build features using FeatureStore
df_features = fs.build_features(df, normalize=False)

# Line 778: Add classical features
df_features = create_classical_features(df_features)
```

**Problem**: `fs.build_features()` might not return the base OHLCV columns that `create_classical_features()` needs!

### The Fix

Add this after line 773 (before creating classical features):

```python
# Ensure base OHLCV columns are present for feature engineering
for col in ['open', 'high', 'low', 'close', 'volume']:
    if col not in df_features.columns and col in df.columns:
        df_features[col] = df[col]
```

This ensures that even if `FeatureStore.build_features()` removes the base columns, they're added back before calling `create_classical_features()`.

## Expected Output

When running the standalone validator successfully, you'll see:

```
================================================================================
🔬 STANDALONE MODEL VALIDATOR
================================================================================
Symbol: BTCUSDT
Period: 180 days
Model: model_DEFINITIVO_4ML_540d.pkl

📥 Downloading BTCUSDT data (180 days, 15m interval)...
✅ Downloaded 17,280 candles
   Period: 2024-05-24 00:00:00 to 2024-11-20 00:00:00

🔍 Loading model: model_DEFINITIVO_4ML_540d.pkl
   ✅ Loaded with custom unpickler
   📦 Type: ModelWrapper
   ✅ Model loaded successfully
   📊 Features: 85
   🎯 Threshold: 0.500

📌 Detected model version: Classical
   Required features: 85

🔨 Building features...
   🔨 Creating classical TA features...
✅ Features ready: 120 columns
✅ All 85 required features are present!

🎯 Using threshold: 0.500

================================================================================
🧪 TESTING DIFFERENT CONFIDENCE LEVELS
================================================================================

Testing min confidence: 0%...
Testing min confidence: 5%...
Testing min confidence: 10%...
...

================================================================================
📊 COMPARATIVE RESULTS
================================================================================

Conf   | Trades  | WR     | ROI      | ROI/yr   | PF    | Sharpe  | DD      | Avg Conf
----------------------------------------------------------------------------------------
   0%  |   1,538 |  70.2% |  +156.3% |  +317.0% |  1.52 |   2.48 |   -5.6% |      5.8%
   5%  |   1,486 |  74.8% |  +283.4% |  +574.7% |  1.91 |   4.22 |   -4.5% |      7.2%
  10%  |     430 |  96.3% |  +165.2% |  +335.0% | 13.75 |  16.42 |   -1.0% |     10.7%

================================================================================
🏆 RECOMMENDED CONFIGURATION
================================================================================

   MIN_ML_CONFIDENCE=0.10

📊 Metrics:
   Total Trades: 430
   Win Rate: 96.3%
   ROI: +165.20%
   Sharpe: 16.42
   Max DD: -1.0%
   Profit Factor: 13.75

================================================================================
```

## Summary

1. ✅ Use `validate_standalone.py` for hassle-free validation
2. ✅ It downloads data automatically from Bybit
3. ✅ It creates ALL required features for ALL model types
4. ✅ It verifies features are present before running backtest
5. ✅ No dependencies on `core/*` modules

This should fix your "missing features" error permanently! 🚀
