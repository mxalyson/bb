#!/usr/bin/env python3
"""
Test how many signals the model would generate today.
"""

import sys
sys.path.insert(0, '/home/user/bb')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from core.data import DataManager
from core.bybit_rest import BybitRESTClient
from core.utils import load_config
from core.features import FeatureStore
import pickle

# Load config
config = load_config('standard')
rest_client = BybitRESTClient(
    api_key=config['bybit_api_key'],
    api_secret=config['bybit_api_secret'],
    testnet=config['bybit_testnet']
)

# Download last 1 day of data
print("📥 Downloading last 1 day of BTCUSDT data...")
data_manager = DataManager(rest_client)
df = data_manager.get_data('BTCUSDT', '15m', 1, use_cache=False)
print(f"   Got {len(df)} candles")
print(f"   From: {df.index[0]} to {df.index[-1]}")
print()

# Build features
print("🔨 Building features...")
fs = FeatureStore(config)
df_feat = fs.build_features(df)
print(f"   Features shape: {df_feat.shape}")
print()

# Load model
print("🤖 Loading ML model...")
model_path = 'storage/models/ml_model_master_scalper_365d.pkl'
with open(model_path, 'rb') as f:
    model = pickle.load(f)
print(f"   Model loaded from: {model_path}")
print()

# Get feature columns (same as training)
feature_cols = [c for c in df_feat.columns if c not in ['signal', 'ml_prob_up', 'ml_prob_down', 'ml_confidence']]
X = df_feat[feature_cols].values

# Make predictions
print("🔮 Making predictions...")
ml_probs = model.predict(X)
optimal_threshold = 0.5

# Calculate confidence and signals for different thresholds
thresholds = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]

print("=" * 80)
print("📊 SIGNALS BY CONFIDENCE THRESHOLD")
print("=" * 80)
print()

for min_conf in thresholds:
    df_feat['ml_prob_up'] = ml_probs
    df_feat['ml_prob_down'] = 1 - ml_probs
    df_feat['ml_confidence'] = np.abs(ml_probs - optimal_threshold) * 2

    # Generate signals
    df_feat['signal'] = 0
    mask_long = (df_feat['ml_prob_up'] > optimal_threshold) & (df_feat['ml_confidence'] >= min_conf)
    mask_short = (df_feat['ml_prob_down'] > (1 - optimal_threshold)) & (df_feat['ml_confidence'] >= min_conf)

    df_feat.loc[mask_long, 'signal'] = 1
    df_feat.loc[mask_short, 'signal'] = -1

    # Count signals
    num_long = (df_feat['signal'] == 1).sum()
    num_short = (df_feat['signal'] == -1).sum()
    num_total = num_long + num_short

    print(f"Confidence ≥ {min_conf*100:>3.0f}%: {num_total:>3} signals ({num_long:>2} LONG, {num_short:>2} SHORT)")

print()
print("=" * 80)

# Show last 10 predictions with details
print()
print("🔍 LAST 10 CANDLES (Most Recent First):")
print("=" * 80)

last_10 = df_feat.iloc[-10:].copy()
last_10 = last_10.iloc[::-1]  # Reverse to show most recent first

for idx, row in last_10.iterrows():
    time_str = idx.strftime('%Y-%m-%d %H:%M')
    pred = row['ml_prob_up']
    conf = row['ml_confidence']
    sig = row['signal']

    if sig == 1:
        sig_str = "🟢 LONG"
    elif sig == -1:
        sig_str = "🔴 SHORT"
    else:
        sig_str = "⚪ NEUTRO"

    print(f"{time_str} | Close: ${row['close']:>8,.2f} | Pred: {pred:.3f} | Conf: {conf:>5.1%} | {sig_str}")

print("=" * 80)
