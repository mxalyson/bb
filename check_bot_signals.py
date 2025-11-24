#!/usr/bin/env python3
"""Check why bot is not opening trades."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import pickle
from core.data import DataManager
from core.bybit_rest import BybitRESTClient
from core.utils import load_config
from core.features import FeatureStore

print("="*80)
print("🔍 BOT SIGNAL CHECKER")
print("="*80 + "\n")

# Find model
model_paths = ['storage/models/ml_model_master_scalper_365d.pkl', 'ml_model_master_scalper_365d.pkl']
model_path = None
for p in model_paths:
    if os.path.exists(p):
        model_path = p
        break

if not model_path:
    print("❌ Model not found!"); sys.exit(1)

print(f"✅ Model: {model_path}\n")

# Load config and download data
config = load_config('standard')
rest_client = BybitRESTClient(config['bybit_api_key'], config['bybit_api_secret'], config['bybit_testnet'])

print("📥 Downloading 1 day data...")
dm = DataManager(rest_client)
df = dm.get_data('BTCUSDT', '15m', 1, use_cache=False)
print(f"✅ Got {len(df)} candles\n")

# Build features
print("🔨 Building features...")
fs = FeatureStore(config)
df_feat = fs.build_features(df)
print(f"✅ Shape: {df_feat.shape}\n")

# Load model
print("🤖 Loading model...")
with open(model_path, 'rb') as f:
    data = pickle.load(f)

# Handle different formats
if isinstance(data, dict):
    print("   Format: dict")
    print(f"   Keys: {list(data.keys())}")
    actual_model = data.get('model')
    feature_names = data.get('feature_names') or data.get('features')
    threshold = data.get('optimal_threshold', 0.5)
else:
    print("   Format: object")
    actual_model = getattr(data, 'model', data)
    feature_names = getattr(data, 'feature_names', None)
    threshold = getattr(data, 'optimal_threshold', 0.5)

print(f"   Threshold: {threshold:.3f}")
print(f"   Model type: {type(actual_model)}")
print(f"   Features: {len(feature_names) if feature_names else 'unknown'}\n")

# Get features using model's feature_names (CRITICAL - avoids 'trend' string issue!)
if feature_names:
    X = df_feat[feature_names].fillna(0).replace([np.inf, -np.inf], 0).values
else:
    # Fallback: exclude known non-numeric columns
    feature_cols = [c for c in df_feat.columns if c not in ['signal', 'ml_prob_up', 'ml_prob_down', 'ml_confidence', 'trend']]
    X = df_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0).values

# Predict
print("🔮 Predicting...")
try:
    preds = actual_model.predict(X)
    print(f"✅ Got {len(preds)} predictions\n")
except Exception as e:
    print(f"⚠️ Direct predict failed: {e}")
    # Try ensemble
    if hasattr(actual_model, 'models_list'):
        print("   Trying ensemble...")
        all_preds = []
        for m in actual_model.models_list:
            all_preds.append(m.predict(X))
        preds = np.mean(all_preds, axis=0) if hasattr(actual_model, 'model_weights') else np.mean(all_preds, axis=0)
        print(f"✅ Ensemble predictions: {len(preds)}\n")
    else:
        print(f"❌ Cannot predict!"); sys.exit(1)

# Calculate confidence
df_feat['ml_prob'] = preds
df_feat['ml_conf'] = np.abs(preds - threshold) * 2

# Count signals at different confidence levels
print("="*80)
print("📊 SIGNALS BY CONFIDENCE LEVEL")
print("="*80 + "\n")

for conf_level in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
    mask_long = (df_feat['ml_prob'] > threshold) & (df_feat['ml_conf'] >= conf_level)
    mask_short = (df_feat['ml_prob'] < threshold) & (df_feat['ml_conf'] >= conf_level)
    n_long = mask_long.sum()
    n_short = mask_short.sum()
    n_total = n_long + n_short
    status = "✅" if n_total > 0 else "⚪"
    print(f"{status} Conf ≥ {conf_level*100:>3.0f}%: {n_total:>3} signals ({n_long:>2} LONG, {n_short:>2} SHORT)")

print("\n" + "="*80)
print("🔍 LAST 15 CANDLES")
print("="*80 + "\n")

last15 = df_feat.iloc[-15:].copy()
last15 = last15.iloc[::-1]

for idx, row in last15.iterrows():
    prob = row['ml_prob']
    conf = row['ml_conf']
    close = row['close']
    
    # Signal at 40%
    if prob > threshold and conf >= 0.40:
        sig = "🟢 LONG"
    elif prob < threshold and conf >= 0.40:
        sig = "🔴 SHORT"
    else:
        sig = "⚪ NEUTRO"
    
    conf_mark = " ✅" if conf >= 0.40 else (" ⚠️" if conf >= 0.35 else "")
    print(f"{idx.strftime('%Y-%m-%d %H:%M')} | ${close:>8,.2f} | Pred:{prob:.3f} | Conf:{conf:>5.1%}{conf_mark} | {sig}")

print("\n" + "="*80)
