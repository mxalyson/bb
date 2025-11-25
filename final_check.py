#!/usr/bin/env python3
"""Final signal checker with missing features fix."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
import pickle
from core.data import DataManager
from core.bybit_rest import BybitRESTClient
from core.utils import load_config
from core.features import FeatureStore

def add_missing_features(df):
    """Add V1 advanced features that model expects."""
    df_feat = df.copy()

    # Multi-period momentum (V1 features)
    for period in [3, 5, 8, 13, 21]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100
        df_feat[f'volume_ratio_{period}'] = df_feat['volume'] / df_feat['volume'].rolling(period).mean()

    # Trend strength
    if 'ema50' in df_feat.columns and 'ema200' in df_feat.columns:
        df_feat['trend_strength'] = (df_feat['ema50'] - df_feat['ema200']) / df_feat['ema200'] * 100
    else:
        df_feat['trend_strength'] = 0

    # Volatility regimes
    if 'atr' in df_feat.columns:
        df_feat['volatility_regime'] = (df_feat['atr'] / df_feat['atr'].rolling(50).mean())
    else:
        df_feat['volatility_regime'] = 1.0

    # Price position
    df_feat['price_position'] = (
        (df_feat['close'] - df_feat['low'].rolling(20).min()) /
        (df_feat['high'].rolling(20).max() - df_feat['low'].rolling(20).min())
    ).fillna(0.5)

    # Volume momentum
    df_feat['volume_momentum'] = df_feat['volume'].pct_change(5)

    # Acceleration
    df_feat['price_acceleration'] = df_feat['close'].diff(2) - df_feat['close'].diff(1)

    return df_feat

print("="*80)
print("🔍 FINAL BOT SIGNAL CHECKER")
print("="*80 + "\n")

# Find model
model_path = 'storage/models/ml_model_master_scalper_365d.pkl'
if not os.path.exists(model_path):
    model_path = 'ml_model_master_scalper_365d.pkl'

print(f"✅ Model: {model_path}\n")

# Load everything
config = load_config('standard')
rest_client = BybitRESTClient(config['bybit_api_key'], config['bybit_api_secret'], config['bybit_testnet'])
print("📥 Downloading 30 days (same as bot)...")
dm = DataManager(rest_client)
df = dm.get_data('BTCUSDT', '15m', 30, use_cache=False)
print(f"✅ {len(df)} candles\n")

print("🔨 Building features...")
fs = FeatureStore(config)
df_feat = fs.build_features(df)
print(f"✅ Base features: {df_feat.shape}")

# Add missing V1 features
print("🔧 Adding V1 advanced features...")
df_feat = add_missing_features(df_feat)
print(f"✅ After V1 features: {df_feat.shape}\n")

print("🤖 Loading model...")
with open(model_path, 'rb') as f:
    data = pickle.load(f)

model = data['model']
feature_names = data['feature_names']
threshold = data.get('optimal_threshold', 0.5)
print(f"✅ Model: {len(feature_names)} features needed\n")

# Check missing features
missing = [f for f in feature_names if f not in df_feat.columns]
if missing:
    print(f"❌ Still missing: {missing[:10]}")
    print(f"   Total missing: {len(missing)}")
    sys.exit(1)

print("✅ All features present!\n")

# Prepare X
X = df_feat[feature_names].fillna(0).replace([np.inf, -np.inf], 0)
print(f"✅ X prepared: {X.shape}\n")

print("🔮 Predicting...")
preds = model.predict(X.values)
print(f"✅ {len(preds)} predictions\n")

# Calculate confidence
df_feat['ml_prob'] = preds
df_feat['ml_conf'] = np.abs(preds - threshold) * 2

# Count signals
print("="*80)
print("📊 SIGNALS BY CONFIDENCE (Last 24h)")
print("="*80 + "\n")

for conf in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
    long = ((df_feat['ml_prob'] > threshold) & (df_feat['ml_conf'] >= conf)).sum()
    short = ((df_feat['ml_prob'] < threshold) & (df_feat['ml_conf'] >= conf)).sum()
    total = long + short
    status = "✅" if total > 0 else "⚪"
    print(f"{status} ≥{conf*100:>3.0f}%: {total:>3} signals ({long:>2} LONG, {short:>2} SHORT)")

print("\n" + "="*80)
print("🔍 LAST 15 CANDLES (Most Recent First)")
print("="*80 + "\n")

for idx, row in df_feat.iloc[-15:].iloc[::-1].iterrows():
    prob = row['ml_prob']
    conf = row['ml_conf']
    close = row['close']

    if prob > threshold and conf >= 0.40:
        sig = "🟢 LONG"
    elif prob < threshold and conf >= 0.40:
        sig = "🔴 SHORT"
    else:
        sig = "⚪ NEUTRO"

    mark = " ✅" if conf >= 0.40 else (" ⚠️" if conf >= 0.35 else "")
    time_str = idx.strftime('%H:%M')
    print(f"{time_str} | ${close:>8,.2f} | Pred:{prob:.3f} | Conf:{conf:>5.1%}{mark} | {sig}")

print("\n" + "="*80)
print("\n💡 RESULTADO:")
total_40 = ((df_feat['ml_conf'] >= 0.40) & (df_feat['ml_prob'] != threshold)).sum()
if total_40 == 0:
    print("   ⚠️ NENHUM sinal com confiança ≥40% nas últimas 24h")
    print("   Isso é NORMAL - mercado está neutro/indeciso")
    print("   O bot está correto em não abrir trades!")
else:
    print(f"   ✅ {total_40} sinais válidos nas últimas 24h")
    print("   Se o bot não abriu trades, verifique:")
    print("   - Configuração MIN_ML_CONFIDENCE no .env")
    print("   - Se o bot está usando a versão otimizada")
print("\n" + "="*80)
