#!/usr/bin/env python3
"""
Debug script to check why live bot is not opening trades.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime
from core.data import DataManager
from core.bybit_rest import BybitRESTClient
from core.utils import load_config
from core.features import FeatureStore
import pickle

def find_model():
    """Find model in common locations."""
    possible_paths = [
        'storage/models/ml_model_master_scalper_365d.pkl',
        'ml_model_master_scalper_365d.pkl',
        'models/ml_model_master_scalper_365d.pkl',
        '../storage/models/ml_model_master_scalper_365d.pkl',
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    # Last resort: find it anywhere
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file == 'ml_model_master_scalper_365d.pkl':
                return os.path.join(root, file)

    return None

print("=" * 80)
print("🔍 LIVE BOT SIGNAL DEBUG")
print("=" * 80)
print()

# Find model
print("🔎 Searching for ML model...")
model_path = find_model()
if not model_path:
    print("❌ ERROR: Could not find ml_model_master_scalper_365d.pkl")
    print("   Please make sure the model file exists in:")
    print("   - storage/models/")
    print("   - Current directory")
    sys.exit(1)

print(f"✅ Found model: {model_path}")
print()

# Load config
print("📋 Loading config...")
try:
    config = load_config('standard')
    print("✅ Config loaded")
except Exception as e:
    print(f"❌ ERROR loading config: {e}")
    sys.exit(1)
print()

# Create REST client
print("🔗 Creating Bybit REST client...")
try:
    rest_client = BybitRESTClient(
        api_key=config['bybit_api_key'],
        api_secret=config['bybit_api_secret'],
        testnet=config['bybit_testnet']
    )
    print("✅ REST client created")
except Exception as e:
    print(f"❌ ERROR creating client: {e}")
    sys.exit(1)
print()

# Download data
print("📥 Downloading last 1 day of BTCUSDT data...")
try:
    data_manager = DataManager(rest_client)
    df = data_manager.get_data('BTCUSDT', '15m', 1, use_cache=False)
    print(f"✅ Downloaded {len(df)} candles")
    print(f"   From: {df.index[0]}")
    print(f"   To:   {df.index[-1]}")
except Exception as e:
    print(f"❌ ERROR downloading data: {e}")
    sys.exit(1)
print()

# Build features
print("🔨 Building features...")
try:
    fs = FeatureStore(config)
    df_feat = fs.build_features(df)
    print(f"✅ Features built: {df_feat.shape}")
except Exception as e:
    print(f"❌ ERROR building features: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
print()

# Load model
print("🤖 Loading ML model...")
try:
    with open(model_path, 'rb') as f:
        model = pickle.load(f)
    print("✅ Model loaded")
except Exception as e:
    print(f"❌ ERROR loading model: {e}")
    sys.exit(1)
print()

# Get feature columns
feature_cols = [c for c in df_feat.columns if c not in ['signal', 'ml_prob_up', 'ml_prob_down', 'ml_confidence']]
X = df_feat[feature_cols].values

# Make predictions
print("🔮 Making predictions...")
try:
    ml_probs = model.predict(X)
    print(f"✅ Predictions made: {len(ml_probs)} rows")
except Exception as e:
    print(f"❌ ERROR making predictions: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
print()

# Analyze signals for different confidence thresholds
optimal_threshold = 0.5
thresholds = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]

print("=" * 80)
print("📊 SIGNALS BY CONFIDENCE THRESHOLD (Last 24 hours)")
print("=" * 80)
print()

for min_conf in thresholds:
    df_test = df_feat.copy()
    df_test['ml_prob_up'] = ml_probs
    df_test['ml_prob_down'] = 1 - ml_probs
    df_test['ml_confidence'] = np.abs(ml_probs - optimal_threshold) * 2

    # Generate signals
    df_test['signal'] = 0
    mask_long = (df_test['ml_prob_up'] > optimal_threshold) & (df_test['ml_confidence'] >= min_conf)
    mask_short = (df_test['ml_prob_down'] > (1 - optimal_threshold)) & (df_test['ml_confidence'] >= min_conf)

    df_test.loc[mask_long, 'signal'] = 1
    df_test.loc[mask_short, 'signal'] = -1

    # Count signals
    num_long = (df_test['signal'] == 1).sum()
    num_short = (df_test['signal'] == -1).sum()
    num_total = num_long + num_short

    status = "✅" if num_total > 0 else "⚪"
    print(f"{status} Confidence ≥ {min_conf*100:>3.0f}%: {num_total:>3} signals ({num_long:>2} LONG, {num_short:>2} SHORT)")

print()
print("=" * 80)
print()

# Show last 20 predictions with details
print("🔍 LAST 20 CANDLES (Most Recent First):")
print("=" * 80)
print()

df_final = df_feat.copy()
df_final['ml_prob_up'] = ml_probs
df_final['ml_confidence'] = np.abs(ml_probs - optimal_threshold) * 2

# Use 40% as default (what the bot is using)
min_conf_display = 0.40
df_final['signal'] = 0
mask_long = (df_final['ml_prob_up'] > optimal_threshold) & (df_final['ml_confidence'] >= min_conf_display)
mask_short = (df_final['ml_prob_up'] < optimal_threshold) & (df_final['ml_confidence'] >= min_conf_display)
df_final.loc[mask_long, 'signal'] = 1
df_final.loc[mask_short, 'signal'] = -1

last_20 = df_final.iloc[-20:].copy()
last_20 = last_20.iloc[::-1]  # Reverse to show most recent first

for idx, row in last_20.iterrows():
    time_str = idx.strftime('%Y-%m-%d %H:%M')
    pred = row['ml_prob_up']
    conf = row['ml_confidence']
    close = row['close']

    # Determine signal at 40% confidence
    if row['signal'] == 1:
        sig_str = "🟢 LONG  "
    elif row['signal'] == -1:
        sig_str = "🔴 SHORT "
    else:
        sig_str = "⚪ NEUTRO"

    # Add indicator if confidence is close to threshold
    conf_indicator = ""
    if conf >= 0.35 and conf < 0.40:
        conf_indicator = " ⚠️ (quase!)"
    elif conf >= 0.40:
        conf_indicator = " ✅"

    print(f"{time_str} | ${close:>8,.2f} | Pred: {pred:.3f} | Conf: {conf:>5.1%}{conf_indicator} | {sig_str}")

print()
print("=" * 80)
print()
print("💡 INTERPRETAÇÃO:")
print()
print("   • Pred > 0.500 = Modelo prevê subida (LONG)")
print("   • Pred < 0.500 = Modelo prevê descida (SHORT)")
print("   • Pred ≈ 0.500 = Modelo indeciso (NEUTRO)")
print("   • Conf < 40% = Sinal ignorado pelo bot")
print("   • Conf ≥ 40% = Sinal válido para abrir trade")
print()
print("=" * 80)
