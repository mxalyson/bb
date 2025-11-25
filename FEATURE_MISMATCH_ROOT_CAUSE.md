# 🚨 ROOT CAUSE: Feature Mismatch Between Training and Bots

## 🔍 Problem Discovered

The bots are using **DIFFERENT** feature engineering than the training script!

---

## 📊 Comparison: Training vs Bots

### train_master_scalper.py (TRAINING - Correct):
```python
# Line 170: Base features from FeatureStore
df_features = feature_store.build_features(df, normalize=False)

# Line 176: Add advanced features
df_features = create_advanced_features(df_features)

# Line 217: Exclude OHLCV from model features
exclude_cols = ['close', 'high', 'low', 'open', 'volume', 'target', 'vote_confidence']
feature_cols = [col for col in df_clean.columns if col not in exclude_cols]
```

**Features from create_advanced_features():**
```python
# Multi-period momentum (5 features)
for period in [3, 5, 8, 13, 21]:
    df[f'momentum_{period}'] = df['close'].pct_change(period) * 100

# Multi-period volume ratio (5 features)
for period in [3, 5, 8, 13, 21]:
    df[f'volume_ratio_{period}'] = df['volume'] / df['volume'].rolling(period).mean()

# Additional features (5 features)
df['trend_strength'] = (df['ema50'] - df['ema200']) / df['ema200'] * 100
df['volatility_regime'] = df['atr'] / df['atr'].rolling(50).mean()
df['price_position'] = (close - low_20) / (high_20 - low_20)
df['volume_momentum'] = df['volume'].pct_change(5)
df['price_acceleration'] = df['close'].diff(2) - df['close'].diff(1)
```

**Total: FeatureStore (~54) + Advanced (15) - OHLCV (5) = ~64-73 features**

---

### btc_real_v5.py (WRONG - Missing Advanced Features):
```python
# Line 476: Only FeatureStore
df = self.fs.build_features(df, normalize=False)

# ❌ MISSING: Does NOT call create_advanced_features()!
```

**Problem:**
- Missing momentum_3, momentum_8, momentum_13, momentum_21
- Missing volume_ratio_3, volume_ratio_8, volume_ratio_13, volume_ratio_21
- Missing trend_strength (or different calculation)
- Missing volatility_regime (or different calculation)
- Missing price_position
- Missing volume_momentum
- Missing price_acceleration

**Result:** ~**54 features instead of 73** ❌

---

### live_bot.py (WRONG - Different Features):
```python
# Line 984: FeatureStore
df_features = self.feature_store.build_features(df, normalize=False)

# Line 987: Creates DIFFERENT features!
df_features = create_features_for_bot(df_features)
```

**Problem:**
`create_features_for_bot()` creates ~70 features but they are NOT the same as training!
- Creates different SMAs (sma_7, sma_14, sma_21, sma_50, sma_100)
- Creates different EMAs (ema_7, ema_14, ema_21, ema_50, ema_100)
- Many features that training didn't use!
- May overwrite FeatureStore features with different calculations

**Result:** ~**130 total columns but wrong set!** ❌

---

## ✅ Solution

Both bots MUST use EXACTLY what training used:

### 1. Create create_advanced_features() function in both bots:
```python
def create_advanced_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add MASTER TRADER advanced features (matching train_master_scalper.py)."""

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
```

### 2. Update btc_real_v5.py:
```python
# Line 476: Add after build_features
df = self.fs.build_features(df, normalize=False)
df = create_advanced_features(df)  # ✅ ADD THIS!
```

### 3. Update live_bot.py:
```python
# Line 984-987: Replace create_features_for_bot with create_advanced_features
df_features = self.feature_store.build_features(df, normalize=False)
df_features = create_advanced_features(df_features)  # ✅ CHANGE THIS!
```

---

## 🎯 Expected Result

After fix:
- **Training:** FeatureStore + Advanced = 73 features ✅
- **btc_real_v5.py:** FeatureStore + Advanced = 73 features ✅
- **live_bot.py:** FeatureStore + Advanced = 73 features ✅

**All three should generate IDENTICAL features!**

---

## 📝 Why This Caused Prediction Differences

**Before (WRONG):**
```
Training:     73 features (correct set)
btc_real_v5:  54 features (missing 19) → fills with 0 → WRONG predictions
live_bot:    130 features (wrong set)  → wrong order → WRONG predictions
```

**After (CORRECT):**
```
Training:     73 features (correct set)
btc_real_v5:  73 features (same set) → CORRECT predictions ✅
live_bot:     73 features (same set) → CORRECT predictions ✅
```

---

## ⚠️ Critical Notes

1. **FeatureStore overlaps:** Some features from create_advanced_features() may already exist in FeatureStore (momentum_5, momentum_21, etc.). The training script overwrites them, so bots should do the same.

2. **OHLCV columns:** Training excludes them from model features, but they're kept in DataFrame for calculations.

3. **Feature order:** Must match training exactly! Model expects features in specific order.

---

*Root cause identified: 2025-11-25*
*Fix implementation: IN PROGRESS*
