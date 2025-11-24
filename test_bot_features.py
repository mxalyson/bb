#!/usr/bin/env python3
"""Test if live bot is creating features correctly."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import pickle
from core.data import DataManager
from core.bybit_rest import BybitRESTClient
from core.utils import load_config
from core.features import FeatureStore

# Import bot's feature creation function
from live_bot import create_features_for_bot

def add_v1_features(df):
    """Add V1 features like final_check.py does."""
    df_feat = df.copy()

    for period in [3, 5, 8, 13, 21]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100
        df_feat[f'volume_ratio_{period}'] = df_feat['volume'] / df_feat['volume'].rolling(period).mean()

    if 'ema50' in df_feat.columns and 'ema200' in df_feat.columns:
        df_feat['trend_strength'] = (df_feat['ema50'] - df_feat['ema200']) / df_feat['ema200'] * 100
    else:
        df_feat['trend_strength'] = 0

    if 'atr' in df_feat.columns:
        df_feat['volatility_regime'] = (df_feat['atr'] / df_feat['atr'].rolling(50).mean())
    else:
        df_feat['volatility_regime'] = 1.0

    df_feat['price_position'] = (
        (df_feat['close'] - df_feat['low'].rolling(20).min()) /
        (df_feat['high'].rolling(20).max() - df_feat['low'].rolling(20).min())
    ).fillna(0.5)

    df_feat['volume_momentum'] = df_feat['volume'].pct_change(5)
    df_feat['price_acceleration'] = df_feat['close'].diff(2) - df_feat['close'].diff(1)

    return df_feat

print("="*80)
print("🔍 TESTING LIVE BOT FEATURES")
print("="*80 + "\n")

# Load model to get expected features
model_path = 'storage/models/ml_model_master_scalper_365d.pkl'
with open(model_path, 'rb') as f:
    model_data = pickle.load(f)

expected_features = model_data['feature_names']
model = model_data['model']
print(f"✅ Model expects: {len(expected_features)} features\n")

# Download data
config = load_config('standard')
rest_client = BybitRESTClient(config['bybit_api_key'], config['bybit_api_secret'], config['bybit_testnet'])
dm = DataManager(rest_client)
df = dm.get_data('BTCUSDT', '15m', 1, use_cache=False)
print(f"📥 Downloaded {len(df)} candles\n")

# Method 1: How final_check.py does it (CORRECT)
print("🔨 Method 1: FeatureStore + V1 features (CORRECT - like final_check.py)")
fs = FeatureStore(config)
df1 = fs.build_features(df.copy())
df1 = add_v1_features(df1)
print(f"   Total features: {df1.shape[1]}")
missing1 = [f for f in expected_features if f not in df1.columns]
print(f"   Missing: {len(missing1)} {('- ' + str(missing1[:5])) if missing1 else '✅'}")

# Make prediction
X1 = df1[expected_features].fillna(0).replace([np.inf, -np.inf], 0).iloc[[-2]]
pred1 = model.predict(X1.values)[0]
print(f"   Prediction (last candle): {pred1:.3f}\n")

# Method 2: How live_bot does it (SUSPECT)
print("🔨 Method 2: FeatureStore + create_features_for_bot (SUSPECT - like live_bot)")
df2 = fs.build_features(df.copy())
df2 = create_features_for_bot(df2)
print(f"   Total features: {df2.shape[1]}")
missing2 = [f for f in expected_features if f not in df2.columns]
print(f"   Missing: {len(missing2)} {('- ' + str(missing2[:5])) if missing2 else '✅'}")

# Make prediction
X2 = df2[expected_features].fillna(0).replace([np.inf, -np.inf], 0).iloc[[-2]]
pred2 = model.predict(X2.values)[0]
print(f"   Prediction (last candle): {pred2:.3f}\n")

# Compare
print("="*80)
print("📊 COMPARISON")
print("="*80 + "\n")

if abs(pred1 - pred2) < 0.001:
    print(f"✅ PREDICTIONS MATCH: {pred1:.3f} ≈ {pred2:.3f}")
    print("   Bot is working correctly!")
else:
    print(f"❌ PREDICTIONS DIFFER: {pred1:.3f} vs {pred2:.3f}")
    print(f"   Difference: {abs(pred1-pred2):.3f}")
    print("   🔍 Investigating...")

    # Check which features differ
    print("\n   Checking feature values...")
    for feat in expected_features[:10]:  # Check first 10
        val1 = X1[feat].values[0]
        val2 = X2[feat].values[0]
        if abs(val1 - val2) > 0.01:
            print(f"   ⚠️ {feat}: {val1:.3f} vs {val2:.3f}")

print("\n" + "="*80)
