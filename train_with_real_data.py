#!/usr/bin/env python3
"""
Train scalping model with REAL BTC data from Bybit.

This solves the synthetic vs real data mismatch problem.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pickle
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# ML imports
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier
from catboost import CatBoostClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix, accuracy_score, precision_score, recall_score, f1_score
from imblearn.over_sampling import SMOTE

import warnings
warnings.filterwarnings('ignore')


# Import ModelWrapper from train_scalping_model
exec(open('train_scalping_model.py').read().split('# ============================================================================')[0])


print("=" * 80)
print("🚀 TRAINING MODEL WITH REAL BTC DATA")
print("=" * 80)
print()


def download_btc_data(days=365):
    """Download real BTC data from Bybit."""
    print(f"📥 Downloading {days} days of real BTC data from Bybit...")

    try:
        # Import Bybit client
        from core.data_manager import DataManager
        from core.rest_client import RestClient

        rest = RestClient()
        data_mgr = DataManager(rest)

        # Download data
        df = data_mgr.download_historical_data(
            symbol='BTCUSDT',
            interval='15',
            days=days
        )

        print(f"   ✅ Downloaded {len(df):,} candles")
        print(f"   📊 Date range: {df.index[0]} to {df.index[-1]}")
        print(f"   💰 Price range: ${df['close'].min():,.0f} - ${df['close'].max():,.0f}")
        print()

        return df

    except Exception as e:
        print(f"   ❌ Error downloading data: {e}")
        print(f"   💡 Make sure the bot is properly configured")
        return None


def create_features_for_training(df):
    """Create same features as train_scalping_model.py"""

    print("🔨 Creating features...")

    df_feat = df.copy()

    # === BASIC FEATURES ===
    print("   • Basic features...")

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

    df_feat['price_vs_sma7'] = (df_feat['close'] - df_feat['sma_7']) / df_feat['sma_7'] * 100
    df_feat['price_vs_sma21'] = (df_feat['close'] - df_feat['sma_21']) / df_feat['sma_21'] * 100
    df_feat['price_vs_ema14'] = (df_feat['close'] - df_feat['ema_14']) / df_feat['ema_14'] * 100

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

    is_green = (df_feat['close'] > df_feat['open']).astype(int)
    is_red = (df_feat['close'] < df_feat['open']).astype(int)

    df_feat['green_streak'] = (is_green * (is_green.groupby((is_green != is_green.shift()).cumsum()).cumcount() + 1))
    df_feat['red_streak'] = (is_red * (is_red.groupby((is_red != is_red.shift()).cumsum()).cumcount() + 1))

    # === PRICE ACTION ===
    print("   • Price action features...")
    df_feat['higher_high'] = (df_feat['high'] > df_feat['high'].shift(1)).astype(int)
    df_feat['lower_low'] = (df_feat['low'] < df_feat['low'].shift(1)).astype(int)
    df_feat['hh_count'] = df_feat['higher_high'].rolling(10).sum()
    df_feat['ll_count'] = df_feat['lower_low'].rolling(10).sum()

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

    # Select feature columns
    feature_cols = [c for c in df_feat.columns if c not in ['open', 'high', 'low', 'close', 'volume']]

    print(f"   ✅ Created {len(feature_cols)} features")
    print()

    return df_feat, feature_cols


def create_labels_from_real_data(df, tp_atr=1.5, sl_atr=2.0, horizon=32):
    """Create labels using same strategy as train_scalping_model.py"""

    print(f"🎯 Creating labels (TP: {tp_atr}x ATR, SL: {sl_atr}x ATR, Horizon: {horizon} bars)...")

    labels = []
    long_wins = 0
    short_wins = 0

    for i in range(len(df)):
        if i >= len(df) - horizon:
            labels.append(-1)
            continue

        current = df.iloc[i]
        future = df.iloc[i+1:i+horizon+1]

        price = current['close']
        atr = current['atr']

        # LONG
        tp_long = price + (atr * tp_atr)
        sl_long = price - (atr * sl_atr)

        long_pnl = 0
        for _, row in future.iterrows():
            if row['low'] <= sl_long:
                long_pnl = (sl_long - price) / price
                break
            if row['high'] >= tp_long:
                long_pnl = (tp_long - price) / price
                break

        if long_pnl == 0:
            long_pnl = (future.iloc[-1]['close'] - price) / price

        # SHORT
        tp_short = price - (atr * tp_atr)
        sl_short = price + (atr * sl_atr)

        short_pnl = 0
        for _, row in future.iterrows():
            if row['high'] >= sl_short:
                short_pnl = (price - sl_short) / price
                break
            if row['low'] <= tp_short:
                short_pnl = (price - tp_short) / price
                break

        if short_pnl == 0:
            short_pnl = (price - future.iloc[-1]['close']) / price

        # Compare
        if long_pnl > short_pnl:
            label = 1
            long_wins += 1
        else:
            label = 0
            short_wins += 1

        labels.append(label)

    df = df.copy()
    df['label'] = labels
    df = df[df['label'] != -1].copy()

    long_count = (df['label'] == 1).sum()
    short_count = (df['label'] == 0).sum()
    total = len(df)

    print(f"   📊 Labels:")
    print(f"      LONG:  {long_count:,} ({long_count/total*100:.1f}%)")
    print(f"      SHORT: {short_count:,} ({short_count/total*100:.1f}%)")
    print(f"      Total: {total:,}")
    print()

    return df


def main():
    # Download real data
    df = download_btc_data(days=180)  # 6 months

    if df is None:
        print("❌ Failed to download data")
        return

    # Create features
    df_features, feature_cols = create_features_for_training(df)

    # Create labels
    df_labeled = create_labels_from_real_data(df_features, tp_atr=1.5, sl_atr=2.0, horizon=32)

    # Prepare data
    X = df_labeled[feature_cols].values
    y = df_labeled['label'].values

    print(f"📊 Dataset: {len(X):,} samples, {len(feature_cols)} features")
    print(f"   Balance: {(y==1).sum():,} longs ({(y==1).sum()/len(y)*100:.1f}%), {(y==0).sum():,} shorts ({(y==0).sum()/len(y)*100:.1f}%)")
    print()

    # Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    X_train, X_val, y_train, y_val = train_test_split(X_train, y_train, test_size=0.2, random_state=42, stratify=y_train)

    print(f"   Train: {len(X_train):,} | Val: {len(X_val):,} | Test: {len(X_test):,}")
    print()

    # Scale
    print("🔧 Scaling...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)
    print()

    # SMOTE
    print("⚖️  Applying SMOTE...")
    smote = SMOTE(random_state=42)
    X_train_balanced, y_train_balanced = smote.fit_resample(X_train_scaled, y_train)
    print(f"   {len(X_train_scaled):,} → {len(X_train_balanced):,} samples")
    print()

    # Train ensemble (import from train_scalping_model)
    from train_scalping_model import train_ensemble_model, find_optimal_threshold

    models, model_names, model_weights = train_ensemble_model(
        X_train_balanced, y_train_balanced,
        X_val_scaled, y_val
    )

    optimal_threshold = find_optimal_threshold(models, model_weights, X_val_scaled, y_val)

    # Test
    print("📊 Testing on holdout set...")
    predictions = []
    for model in models:
        pred = model.predict_proba(X_test_scaled)[:, 1]
        predictions.append(pred)

    weights = np.array(model_weights)
    weights = weights / weights.sum()

    ensemble_pred = np.zeros_like(predictions[0])
    for pred, weight in zip(predictions, weights):
        ensemble_pred += pred * weight

    y_pred = (ensemble_pred >= optimal_threshold).astype(int)

    # Metrics
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    auc = roc_auc_score(y_test, ensemble_pred)

    print()
    print("=" * 80)
    print("📊 TEST RESULTS")
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

    # Save
    print("💾 Saving model...")

    wrapper = ModelWrapper(
        models_list=models,
        model_weights=model_weights,
        model_names=model_names,
        scaler=scaler,
        feature_columns=feature_cols,
        long_threshold=optimal_threshold,
        short_threshold=1.0 - optimal_threshold
    )

    output_path = Path('storage/models')
    output_path.mkdir(parents=True, exist_ok=True)

    filename = f"real_btc_ensemble_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
    filepath = output_path / filename

    with open(filepath, 'wb') as f:
        pickle.dump(wrapper, f)

    print(f"   ✅ Saved: {filepath}")
    print(f"   📊 Features: {len(feature_cols)}")
    print(f"   🎯 Threshold: {optimal_threshold:.3f}")
    print()

    print("=" * 80)
    print("🎉 TRAINING COMPLETE!")
    print("=" * 80)
    print()
    print("📝 Test with:")
    print(f"   python 1.py --model {filename} --days 10")
    print()


if __name__ == '__main__':
    main()
