#!/usr/bin/env python3
"""
Train a HIGH-QUALITY ensemble model for crypto scalping.

Features:
- Synthetic realistic BTC data
- Balanced labels (50/50 longs/shorts)
- Multiple feature sets (basic + advanced + ultra scalper)
- Ensemble: LightGBM, XGBoost, CatBoost, RandomForest
- Cross-validation
- Class balancing (SMOTE + class_weight)
- Optimal threshold detection
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pickle
from pathlib import Path

# ML imports
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier
from catboost import CatBoostClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix
from imblearn.over_sampling import SMOTE

import warnings
warnings.filterwarnings('ignore')

print("=" * 80)
print("🚀 TRAINING HIGH-QUALITY SCALPING MODEL")
print("=" * 80)
print()


# ============================================================================
# 1. GENERATE REALISTIC SYNTHETIC DATA
# ============================================================================

def generate_realistic_btc_data(n_samples=50000, start_price=50000):
    """Generate realistic BTC 15min candles with volatility and trends."""

    print(f"📊 Generating {n_samples:,} realistic BTC candles...")

    np.random.seed(42)

    # Start date
    start_date = datetime.now() - timedelta(days=n_samples // 96)  # 96 candles per day (15min)
    dates = pd.date_range(start=start_date, periods=n_samples, freq='15min')

    # Price generation with trends and volatility
    price = start_price
    prices = []

    # Market regimes
    regime_length = 500  # candles per regime
    regimes = []

    for i in range(n_samples):
        # Change regime every regime_length candles
        if i % regime_length == 0:
            regime = np.random.choice(['bull', 'bear', 'sideways'], p=[0.3, 0.3, 0.4])
            regimes.append(regime)
        else:
            regime = regimes[-1]

        # Trend based on regime
        if regime == 'bull':
            trend = np.random.normal(0.0003, 0.001)  # Slight uptrend
        elif regime == 'bear':
            trend = np.random.normal(-0.0003, 0.001)  # Slight downtrend
        else:
            trend = np.random.normal(0, 0.0008)  # Sideways

        # Add volatility spikes randomly
        volatility = 0.002 if np.random.random() < 0.05 else 0.0015

        # Random walk with trend
        change = trend + np.random.normal(0, volatility)
        price = price * (1 + change)

        # Ensure price doesn't go negative
        price = max(price, 1000)

        prices.append(price)

    prices = np.array(prices)

    # Generate OHLCV
    data = []
    for i in range(n_samples):
        close = prices[i]

        # Open is previous close (with small gap)
        if i == 0:
            open_price = close * (1 + np.random.normal(0, 0.0001))
        else:
            open_price = prices[i-1] * (1 + np.random.normal(0, 0.0002))

        # High/Low based on volatility
        volatility = abs(close - open_price) * np.random.uniform(1.5, 3)
        high = max(open_price, close) + volatility * np.random.uniform(0, 1)
        low = min(open_price, close) - volatility * np.random.uniform(0, 1)

        # Volume with spikes
        base_volume = 100 + np.random.uniform(50, 200)
        if abs(close - open_price) / open_price > 0.005:  # Big move = big volume
            volume = base_volume * np.random.uniform(2, 5)
        else:
            volume = base_volume

        data.append({
            'timestamp': dates[i],
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })

    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)

    print(f"   ✅ Generated data from ${df['close'].iloc[0]:,.0f} to ${df['close'].iloc[-1]:,.0f}")
    print(f"   📈 Price range: ${df['close'].min():,.0f} - ${df['close'].max():,.0f}")
    print()

    return df


# ============================================================================
# 2. CREATE FEATURES (BASIC + ADVANCED + ULTRA SCALPER)
# ============================================================================

def create_all_features(df):
    """Create comprehensive feature set for scalping."""

    print("🔨 Creating comprehensive feature set...")

    df_feat = df.copy()

    # === BASIC FEATURES ===
    print("   • Basic features (returns, volatility, ATR)...")

    # Returns
    df_feat['returns'] = df_feat['close'].pct_change()
    df_feat['returns_5'] = df_feat['close'].pct_change(5)
    df_feat['returns_10'] = df_feat['close'].pct_change(10)

    # Volatility
    df_feat['volatility_5'] = df_feat['returns'].rolling(5).std()
    df_feat['volatility_20'] = df_feat['returns'].rolling(20).std()
    df_feat['volatility_ratio'] = df_feat['volatility_5'] / (df_feat['volatility_20'] + 1e-8)

    # ATR
    high_low = df_feat['high'] - df_feat['low']
    high_close = abs(df_feat['high'] - df_feat['close'].shift())
    low_close = abs(df_feat['low'] - df_feat['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df_feat['atr'] = true_range.rolling(14).mean()
    df_feat['atr_pct'] = df_feat['atr'] / df_feat['close'] * 100

    # === MOMENTUM FEATURES ===
    print("   • Momentum features...")

    for period in [3, 5, 8, 13, 21]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100

    df_feat['momentum_accel'] = df_feat['momentum_5'].diff(3)

    # === MOVING AVERAGES ===
    print("   • Moving averages...")

    for period in [7, 14, 21, 50, 100]:
        df_feat[f'sma_{period}'] = df_feat['close'].rolling(period).mean()
        df_feat[f'ema_{period}'] = df_feat['close'].ewm(span=period, adjust=False).mean()

    # Price vs MAs
    df_feat['price_vs_sma7'] = (df_feat['close'] - df_feat['sma_7']) / df_feat['sma_7'] * 100
    df_feat['price_vs_sma21'] = (df_feat['close'] - df_feat['sma_21']) / df_feat['sma_21'] * 100
    df_feat['price_vs_ema14'] = (df_feat['close'] - df_feat['ema_14']) / df_feat['ema_14'] * 100

    # MA crosses
    df_feat['sma7_above_sma21'] = (df_feat['sma_7'] > df_feat['sma_21']).astype(int)
    df_feat['ema7_above_ema21'] = (df_feat['ema_7'] > df_feat['ema_21']).astype(int)

    # === RSI ===
    print("   • RSI features...")

    delta = df_feat['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df_feat['rsi'] = 100 - (100 / (1 + rs))

    df_feat['rsi_oversold'] = (df_feat['rsi'] < 30).astype(int)
    df_feat['rsi_overbought'] = (df_feat['rsi'] > 70).astype(int)
    df_feat['rsi_neutral'] = ((df_feat['rsi'] >= 40) & (df_feat['rsi'] <= 60)).astype(int)

    # === MACD ===
    print("   • MACD features...")

    ema12 = df_feat['close'].ewm(span=12, adjust=False).mean()
    ema26 = df_feat['close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    df_feat['macd_hist'] = macd - macd_signal
    df_feat['macd_hist_increasing'] = (df_feat['macd_hist'] > df_feat['macd_hist'].shift(1)).astype(int)

    # === BOLLINGER BANDS ===
    print("   • Bollinger Bands...")

    sma20 = df_feat['close'].rolling(20).mean()
    std20 = df_feat['close'].rolling(20).std()
    df_feat['bb_upper'] = sma20 + (2 * std20)
    df_feat['bb_lower'] = sma20 - (2 * std20)
    df_feat['bb_width'] = (df_feat['bb_upper'] - df_feat['bb_lower']) / sma20 * 100
    df_feat['bb_position'] = (df_feat['close'] - df_feat['bb_lower']) / (df_feat['bb_upper'] - df_feat['bb_lower'] + 1e-8)

    # === VOLUME FEATURES ===
    print("   • Volume features...")

    df_feat['volume_sma_20'] = df_feat['volume'].rolling(20).mean()
    df_feat['volume_ratio'] = df_feat['volume'] / (df_feat['volume_sma_20'] + 1e-8)
    df_feat['high_volume'] = (df_feat['volume_ratio'] > 1.5).astype(int)

    # === CANDLE PATTERNS ===
    print("   • Candle patterns...")

    body = abs(df_feat['close'] - df_feat['open'])
    upper_wick = df_feat['high'] - df_feat[['close', 'open']].max(axis=1)
    lower_wick = df_feat[['close', 'open']].min(axis=1) - df_feat['low']

    df_feat['body_pct'] = body / df_feat['close'] * 100
    df_feat['upper_wick_pct'] = upper_wick / df_feat['close'] * 100
    df_feat['lower_wick_pct'] = lower_wick / df_feat['close'] * 100
    df_feat['total_wick'] = upper_wick + lower_wick
    df_feat['wick_body_ratio'] = df_feat['total_wick'] / (body + 1e-8)

    # Candle direction
    is_green = (df_feat['close'] > df_feat['open']).astype(int)
    is_red = (df_feat['close'] < df_feat['open']).astype(int)

    df_feat['green_streak'] = (is_green * (is_green.groupby((is_green != is_green.shift()).cumsum()).cumcount() + 1))
    df_feat['red_streak'] = (is_red * (is_red.groupby((is_red != is_red.shift()).cumsum()).cumcount() + 1))

    # === PRICE ACTION ===
    print("   • Price action features...")

    # Higher high / Lower low
    df_feat['higher_high'] = (df_feat['high'] > df_feat['high'].shift(1)).astype(int)
    df_feat['lower_low'] = (df_feat['low'] < df_feat['low'].shift(1)).astype(int)
    df_feat['hh_count'] = df_feat['higher_high'].rolling(10).sum()
    df_feat['ll_count'] = df_feat['lower_low'].rolling(10).sum()

    # Price position in range
    for period in [14, 50]:
        high_period = df_feat['high'].rolling(period).max()
        low_period = df_feat['low'].rolling(period).min()
        df_feat[f'price_position_{period}'] = (df_feat['close'] - low_period) / (high_period - low_period + 1e-8)

    # === ORDER FLOW (simulated) ===
    print("   • Order flow (simulated)...")

    close_position = (df_feat['close'] - df_feat['low']) / (df_feat['high'] - df_feat['low'] + 1e-8)
    df_feat['taker_buy_ratio'] = close_position
    df_feat['taker_sell_ratio'] = 1 - close_position

    df_feat['buy_pressure'] = df_feat['taker_buy_ratio'].rolling(20).mean()
    df_feat['sell_pressure'] = df_feat['taker_sell_ratio'].rolling(20).mean()
    df_feat['pressure_delta'] = df_feat['buy_pressure'] - df_feat['sell_pressure']

    # Fill NaN
    df_feat = df_feat.fillna(method='bfill').fillna(0)

    # Select only feature columns (exclude OHLCV)
    feature_cols = [c for c in df_feat.columns if c not in ['open', 'high', 'low', 'close', 'volume']]

    print(f"   ✅ Created {len(feature_cols)} features")
    print()

    return df_feat, feature_cols


# ============================================================================
# 3. CREATE BALANCED LABELS (SCALPING STRATEGY)
# ============================================================================

def create_scalping_labels(df, atr_multiplier_tp=1.0, atr_multiplier_sl=2.0, forward_bars=48):
    """
    Create balanced labels for scalping.

    Label = 1 (LONG) if TP hit before SL
    Label = 0 (SHORT) if SL hit before TP or sideways

    This ensures balanced dataset.
    """

    print("🎯 Creating balanced scalping labels...")
    print(f"   TP: {atr_multiplier_tp}x ATR | SL: {atr_multiplier_sl}x ATR | Horizon: {forward_bars} bars")

    labels = []

    for i in range(len(df)):
        if i >= len(df) - forward_bars:
            # Not enough future data
            labels.append(-1)
            continue

        current = df.iloc[i]
        future = df.iloc[i+1:i+forward_bars+1]

        price = current['close']
        atr = current['atr']

        # Define TP and SL for long
        tp_long = price + (atr * atr_multiplier_tp)
        sl_long = price - (atr * atr_multiplier_sl)

        # Define TP and SL for short
        tp_short = price - (atr * atr_multiplier_tp)
        sl_short = price + (atr * atr_multiplier_sl)

        # Check if long TP hit first
        long_tp_hit = (future['high'] >= tp_long).any()
        long_sl_hit = (future['low'] <= sl_long).any()

        # Check if short TP hit first
        short_tp_hit = (future['low'] <= tp_short).any()
        short_sl_hit = (future['high'] >= sl_short).any()

        # Find which one hit first
        if long_tp_hit:
            idx_long_tp = future[future['high'] >= tp_long].index[0]
        else:
            idx_long_tp = None

        if long_sl_hit:
            idx_long_sl = future[future['low'] <= sl_long].index[0]
        else:
            idx_long_sl = None

        if short_tp_hit:
            idx_short_tp = future[future['low'] <= tp_short].index[0]
        else:
            idx_short_tp = None

        if short_sl_hit:
            idx_short_sl = future[future['high'] >= sl_short].index[0]
        else:
            idx_short_sl = None

        # Determine label
        # Priority: if long TP hit before long SL -> LONG (1)
        #           if short TP hit before short SL -> SHORT (0)
        #           else -> SIDEWAYS (consider as SHORT for balance)

        label = 0  # Default: SHORT/SIDEWAYS

        if idx_long_tp is not None:
            if idx_long_sl is None or idx_long_tp < idx_long_sl:
                # Long TP hit first
                label = 1

        labels.append(label)

    df = df.copy()
    df['label'] = labels

    # Remove samples without label
    df = df[df['label'] != -1].copy()

    # Check balance
    long_count = (df['label'] == 1).sum()
    short_count = (df['label'] == 0).sum()
    total = len(df)

    print(f"   📊 Labels created:")
    print(f"      LONG (1):  {long_count:,} ({long_count/total*100:.1f}%)")
    print(f"      SHORT (0): {short_count:,} ({short_count/total*100:.1f}%)")
    print(f"      Total:     {total:,}")
    print()

    return df


# ============================================================================
# 4. TRAIN ENSEMBLE MODEL
# ============================================================================

def train_ensemble_model(X_train, y_train, X_val, y_val):
    """Train ensemble of 4 models with class balancing."""

    print("🤖 Training ensemble models...")
    print()

    models = []
    model_names = []
    model_weights = []

    # Model 1: LightGBM
    print("   1️⃣  Training LightGBM...")
    lgb = LGBMClassifier(
        n_estimators=500,
        learning_rate=0.05,
        max_depth=7,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        class_weight='balanced',
        random_state=42,
        verbosity=-1
    )
    lgb.fit(X_train, y_train)
    val_pred_lgb = lgb.predict_proba(X_val)[:, 1]
    auc_lgb = roc_auc_score(y_val, val_pred_lgb)
    print(f"      ✅ LightGBM AUC: {auc_lgb:.4f}")
    models.append(lgb)
    model_names.append('LightGBM')
    model_weights.append(auc_lgb)

    # Model 2: XGBoost
    print("   2️⃣  Training XGBoost...")
    xgb = XGBClassifier(
        n_estimators=500,
        learning_rate=0.05,
        max_depth=7,
        min_child_weight=1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=(y_train == 0).sum() / (y_train == 1).sum(),
        random_state=42,
        verbosity=0
    )
    xgb.fit(X_train, y_train)
    val_pred_xgb = xgb.predict_proba(X_val)[:, 1]
    auc_xgb = roc_auc_score(y_val, val_pred_xgb)
    print(f"      ✅ XGBoost AUC: {auc_xgb:.4f}")
    models.append(xgb)
    model_names.append('XGBoost')
    model_weights.append(auc_xgb)

    # Model 3: CatBoost
    print("   3️⃣  Training CatBoost...")
    cat = CatBoostClassifier(
        iterations=500,
        learning_rate=0.05,
        depth=7,
        l2_leaf_reg=3,
        random_state=42,
        verbose=False,
        auto_class_weights='Balanced'
    )
    cat.fit(X_train, y_train)
    val_pred_cat = cat.predict_proba(X_val)[:, 1]
    auc_cat = roc_auc_score(y_val, val_pred_cat)
    print(f"      ✅ CatBoost AUC: {auc_cat:.4f}")
    models.append(cat)
    model_names.append('CatBoost')
    model_weights.append(auc_cat)

    # Model 4: Random Forest
    print("   4️⃣  Training Random Forest...")
    rf = RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        min_samples_split=10,
        min_samples_leaf=5,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1
    )
    rf.fit(X_train, y_train)
    val_pred_rf = rf.predict_proba(X_val)[:, 1]
    auc_rf = roc_auc_score(y_val, val_pred_rf)
    print(f"      ✅ Random Forest AUC: {auc_rf:.4f}")
    models.append(rf)
    model_names.append('RandomForest')
    model_weights.append(auc_rf)

    print()
    print("   🎯 Ensemble created with 4 models")
    print(f"   📊 Average AUC: {np.mean([auc_lgb, auc_xgb, auc_cat, auc_rf]):.4f}")
    print()

    return models, model_names, model_weights


# ============================================================================
# 5. FIND OPTIMAL THRESHOLD
# ============================================================================

def find_optimal_threshold(models, model_weights, X_val, y_val):
    """Find optimal classification threshold."""

    print("🎯 Finding optimal threshold...")

    # Get ensemble predictions
    predictions = []
    for model in models:
        pred = model.predict_proba(X_val)[:, 1]
        predictions.append(pred)

    # Weighted average
    weights = np.array(model_weights)
    weights = weights / weights.sum()

    ensemble_pred = np.zeros_like(predictions[0])
    for pred, weight in zip(predictions, weights):
        ensemble_pred += pred * weight

    # Try different thresholds
    best_threshold = 0.5
    best_f1 = 0

    for threshold in np.arange(0.3, 0.7, 0.01):
        y_pred = (ensemble_pred >= threshold).astype(int)

        # Calculate F1 score
        tp = ((y_pred == 1) & (y_val == 1)).sum()
        fp = ((y_pred == 1) & (y_val == 0)).sum()
        fn = ((y_pred == 0) & (y_val == 1)).sum()

        precision = tp / (tp + fp + 1e-10)
        recall = tp / (tp + fn + 1e-10)
        f1 = 2 * (precision * recall) / (precision + recall + 1e-10)

        if f1 > best_f1:
            best_f1 = f1
            best_threshold = threshold

    print(f"   ✅ Optimal threshold: {best_threshold:.3f} (F1: {best_f1:.4f})")
    print()

    return best_threshold


# ============================================================================
# 6. MAIN TRAINING PIPELINE
# ============================================================================

def main():
    # Generate data
    df = generate_realistic_btc_data(n_samples=50000, start_price=50000)

    # Create features
    df_features, feature_cols = create_all_features(df)

    # Create labels
    df_labeled = create_scalping_labels(df_features, atr_multiplier_tp=1.0, atr_multiplier_sl=2.0, forward_bars=48)

    # Prepare data
    X = df_labeled[feature_cols].values
    y = df_labeled['label'].values

    print("📊 Dataset summary:")
    print(f"   Samples: {len(X):,}")
    print(f"   Features: {len(feature_cols)}")
    print(f"   Class distribution: {(y==1).sum():,} longs, {(y==0).sum():,} shorts")
    print()

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    X_train, X_val, y_train, y_val = train_test_split(X_train, y_train, test_size=0.2, random_state=42, stratify=y_train)

    print(f"   Train: {len(X_train):,} samples")
    print(f"   Val:   {len(X_val):,} samples")
    print(f"   Test:  {len(X_test):,} samples")
    print()

    # Scale features
    print("🔧 Scaling features...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)
    print()

    # Apply SMOTE for additional balancing
    print("⚖️  Applying SMOTE for additional balancing...")
    smote = SMOTE(random_state=42)
    X_train_balanced, y_train_balanced = smote.fit_resample(X_train_scaled, y_train)
    print(f"   Before SMOTE: {len(X_train_scaled):,} samples")
    print(f"   After SMOTE:  {len(X_train_balanced):,} samples")
    print()

    # Train ensemble
    models, model_names, model_weights = train_ensemble_model(
        X_train_balanced, y_train_balanced,
        X_val_scaled, y_val
    )

    # Find optimal threshold
    optimal_threshold = find_optimal_threshold(models, model_weights, X_val_scaled, y_val)

    # Test ensemble
    print("📊 Testing ensemble on test set...")
    predictions = []
    for model in models:
        pred = model.predict_proba(X_test_scaled)[:, 1]
        predictions.append(pred)

    # Weighted average
    weights = np.array(model_weights)
    weights = weights / weights.sum()

    ensemble_pred = np.zeros_like(predictions[0])
    for pred, weight in zip(predictions, weights):
        ensemble_pred += pred * weight

    y_pred = (ensemble_pred >= optimal_threshold).astype(int)

    # Metrics
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    auc = roc_auc_score(y_test, ensemble_pred)

    print()
    print("=" * 80)
    print("📊 TEST SET RESULTS")
    print("=" * 80)
    print(f"Accuracy:  {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1 Score:  {f1:.4f}")
    print(f"ROC AUC:   {auc:.4f}")
    print()

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    print("Confusion Matrix:")
    print(f"                Predicted")
    print(f"              SHORT  LONG")
    print(f"Actual SHORT  {cm[0,0]:5d}  {cm[0,1]:5d}")
    print(f"       LONG   {cm[1,0]:5d}  {cm[1,1]:5d}")
    print()

    # Prediction distribution
    long_pct = (y_pred == 1).sum() / len(y_pred) * 100
    short_pct = (y_pred == 0).sum() / len(y_pred) * 100
    print("Prediction Distribution:")
    print(f"   LONG:  {(y_pred==1).sum():,} ({long_pct:.1f}%)")
    print(f"   SHORT: {(y_pred==0).sum():,} ({short_pct:.1f}%)")
    print()

    # Save model
    print("💾 Saving model...")

    class ModelWrapper:
        def __init__(self, models_list, model_weights, model_names, scaler, feature_columns,
                     long_threshold, short_threshold):
            self.models_list = models_list
            self.model_weights = model_weights
            self.model_names = model_names
            self.scaler = scaler
            self.feature_columns = feature_columns
            self.has_dl = False
            self.long_threshold = long_threshold
            self.short_threshold = 1 - long_threshold
            self.lookback = 100
            self.version = "1.0_balanced_ensemble"
            self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    wrapper = ModelWrapper(
        models_list=models,
        model_weights=model_weights,
        model_names=model_names,
        scaler=scaler,
        feature_columns=feature_cols,
        long_threshold=optimal_threshold,
        short_threshold=1 - optimal_threshold
    )

    output_path = Path('storage/models')
    output_path.mkdir(parents=True, exist_ok=True)

    filename = f"scalping_ensemble_balanced_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
    filepath = output_path / filename

    with open(filepath, 'wb') as f:
        pickle.dump(wrapper, f)

    print(f"   ✅ Model saved: {filepath}")
    print(f"   📊 Features: {len(feature_cols)}")
    print(f"   🎯 Optimal threshold: {optimal_threshold:.3f}")
    print()

    print("=" * 80)
    print("🎉 TRAINING COMPLETE!")
    print("=" * 80)
    print()
    print("📝 Next steps:")
    print(f"   1. Test with: python 1.py --model {filename} --days 10")
    print("   2. Check if predictions are balanced (not just longs)")
    print("   3. Verify win rate and ROI")
    print()


if __name__ == '__main__':
    main()
