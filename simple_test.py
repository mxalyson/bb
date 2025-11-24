#!/usr/bin/env python3
"""Simple test without logger issues."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import pickle
from core.data import DataManager
from core.bybit_rest import BybitRESTClient
from core.utils import load_config, setup_logging
from core.features import FeatureStore

# Setup logging first to avoid logger errors
setup_logging()

# Now import after logging is setup
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
print("🔍 SIMPLE PREDICTION TEST")
print("="*80 + "\n")

# Load model
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

# Method 1: CORRECT (like final_check.py)
print("🔨 Method 1: FeatureStore + add_v1_features (CORRECT)")
fs = FeatureStore(config)
df1 = fs.build_features(df.copy())
df1 = add_v1_features(df1)
X1 = df1[expected_features].fillna(0).replace([np.inf, -np.inf], 0).iloc[[-2]]
pred1 = model.predict(X1.values)[0]
conf1 = abs(pred1 - 0.5) * 2
print(f"   Prediction: {pred1:.3f} | Confidence: {conf1:.1%}\n")

# Method 2: SUSPECT (like live_bot)
print("🔨 Method 2: FeatureStore + create_features_for_bot (LIVE BOT)")
df2 = fs.build_features(df.copy())
df2 = create_features_for_bot(df2)
X2 = df2[expected_features].fillna(0).replace([np.inf, -np.inf], 0).iloc[[-2]]
pred2 = model.predict(X2.values)[0]
conf2 = abs(pred2 - 0.5) * 2
print(f"   Prediction: {pred2:.3f} | Confidence: {conf2:.1%}\n")

# Compare
print("="*80)
print("📊 RESULT")
print("="*80 + "\n")

diff = abs(pred1 - pred2)
if diff < 0.01:
    print(f"✅ PREDICTIONS MATCH!")
    print(f"   Method 1: {pred1:.3f} ({conf1:.1%})")
    print(f"   Method 2: {pred2:.3f} ({conf2:.1%})")
    print(f"   Difference: {diff:.4f} (OK - <0.01)")
    print("\n   🎉 Bot is creating features CORRECTLY!")
else:
    print(f"❌ PREDICTIONS DIFFER!")
    print(f"   Method 1 (correct): {pred1:.3f} ({conf1:.1%})")
    print(f"   Method 2 (bot):     {pred2:.3f} ({conf2:.1%})")
    print(f"   Difference: {diff:.3f}")
    print("\n   ⚠️ Bot is creating features INCORRECTLY!")
    print("   This explains why bot doesn't open trades!")

print("\n" + "="*80)
