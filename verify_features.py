#!/usr/bin/env python3
"""
Verify that live_bot.py and btc_real_v5.py generate the same features as training.
"""

import sys
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')
sys.path.append(str(Path(__file__).parent))

import pandas as pd
import numpy as np
import pickle

from core.utils import load_config, setup_logging
from core.bybit_rest import BybitRESTClient
from core.data import DataManager
from core.features import FeatureStore

# Load config
config = load_config('config.json')
logger = setup_logging()

# Initialize clients
rest_client = BybitRESTClient(
    api_key=config['bybit_api_key'],
    api_secret=config['bybit_api_secret'],
    testnet=config['bybit_testnet']
)

data_manager = DataManager(rest_client)
feature_store = FeatureStore(config)

# Load model to get expected features
print("\n" + "=" * 80)
print("🔍 FEATURE VERIFICATION")
print("=" * 80)

with open('ml_model_master_scalper_365d.pkl', 'rb') as f:
    model_data = pickle.load(f)

model_features = set(model_data['feature_names'])
print(f"\n📊 Model expects: {len(model_features)} features")
print()

# Download sample data
print("📥 Downloading sample data...")
df = data_manager.get_data(
    symbol='BTCUSDT',
    interval='15m',
    days_back=7,
    use_cache=False
)
print(f"✅ Downloaded {len(df):,} candles")
print()

# Test FeatureStore + create_advanced_features (train_master_scalper.py approach)
print("🧪 Testing FeatureStore + create_advanced_features...")

def create_advanced_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add MASTER TRADER advanced features (from train_master_scalper.py)."""
    df_features = df.copy()

    # Multi-period momentum
    for period in [3, 5, 8, 13, 21]:
        df_features[f'momentum_{period}'] = df_features['close'].pct_change(period) * 100
        df_features[f'volume_ratio_{period}'] = df_features['volume'] / df_features['volume'].rolling(period).mean()

    # Trend strength
    if 'ema50' in df_features.columns and 'ema200' in df_features.columns:
        df_features['trend_strength'] = (df_features['ema50'] - df_features['ema200']) / df_features['ema200'] * 100

    # Volatility regimes
    if 'atr' in df_features.columns:
        df_features['volatility_regime'] = (df_features['atr'] / df_features['atr'].rolling(50).mean())

    # Price position in recent range
    df_features['price_position'] = (
        (df_features['close'] - df_features['low'].rolling(20).min()) /
        (df_features['high'].rolling(20).max() - df_features['low'].rolling(20).min())
    ).fillna(0.5)

    # Volume momentum
    df_features['volume_momentum'] = df_features['volume'].pct_change(5)

    # Acceleration
    df_features['price_acceleration'] = df_features['close'].diff(2) - df_features['close'].diff(1)

    return df_features

# Build features (same as bots)
df_bot = feature_store.build_features(df, normalize=False)
df_bot = create_advanced_features(df_bot)

# Remove non-feature columns (same as training)
exclude_cols = ['close', 'high', 'low', 'open', 'volume', 'target', 'vote_confidence']
bot_feature_cols = [col for col in df_bot.columns if col not in exclude_cols]

# Remove object types
object_cols = df_bot[bot_feature_cols].select_dtypes(include=['object']).columns
if len(object_cols) > 0:
    print(f"   Removing {len(object_cols)} object columns: {list(object_cols)}")
    bot_feature_cols = [col for col in bot_feature_cols if col not in object_cols]

bot_features = set(bot_feature_cols)

print(f"✅ Bot generates: {len(bot_features)} features (after excluding OHLCV)")
print()

# Compare
print("=" * 80)
print("📊 COMPARISON")
print("=" * 80)

missing_in_bot = model_features - bot_features
extra_in_bot = bot_features - model_features

if not missing_in_bot and not extra_in_bot:
    print("✅ PERFECT MATCH! Bot generates EXACTLY the same features as model!")
    print()
else:
    if missing_in_bot:
        print(f"❌ MISSING {len(missing_in_bot)} features in bot:")
        for feat in sorted(missing_in_bot)[:20]:
            print(f"   - {feat}")
        if len(missing_in_bot) > 20:
            print(f"   ... and {len(missing_in_bot) - 20} more")
        print()

    if extra_in_bot:
        print(f"⚠️ EXTRA {len(extra_in_bot)} features in bot (not in model):")
        for feat in sorted(extra_in_bot)[:20]:
            print(f"   + {feat}")
        if len(extra_in_bot) > 20:
            print(f"   ... and {len(extra_in_bot) - 20} more")
        print()

# Save feature lists for comparison
print("📝 Saving feature lists...")
with open('/tmp/model_features.txt', 'w') as f:
    for feat in sorted(model_features):
        f.write(f"{feat}\n")
print(f"   Model features: /tmp/model_features.txt")

with open('/tmp/bot_features.txt', 'w') as f:
    for feat in sorted(bot_features):
        f.write(f"{feat}\n")
print(f"   Bot features:   /tmp/bot_features.txt")
print()

# Show sample of both lists
print("=" * 80)
print("📋 SAMPLE FEATURES")
print("=" * 80)
print("\nModel features (first 20):")
for feat in sorted(model_features)[:20]:
    print(f"   {feat}")

print("\nBot features (first 20):")
for feat in sorted(bot_features)[:20]:
    print(f"   {feat}")
print()

print("=" * 80)
if not missing_in_bot and not extra_in_bot:
    print("✅ VERIFICATION COMPLETE: PERFECT MATCH! 🎉")
else:
    print("⚠️ VERIFICATION COMPLETE: DIFFERENCES FOUND")
    print(f"   Missing: {len(missing_in_bot)}")
    print(f"   Extra: {len(extra_in_bot)}")
print("=" * 80)
print()
