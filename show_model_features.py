#!/usr/bin/env python3
"""
Extract and display the exact 73 features expected by the model.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import pickle

# Load model
print("\n" + "=" * 80)
print("🔍 FEATURES ESPERADAS PELO MODELO")
print("=" * 80)
print()

try:
    with open('ml_model_master_scalper_365d.pkl', 'rb') as f:
        model_data = pickle.load(f)

    feature_names = model_data.get('feature_names', [])

    print(f"✅ Modelo espera {len(feature_names)} features:")
    print()

    # Group features by category
    categories = {
        'OHLCV': ['open', 'high', 'low', 'close', 'volume'],
        'EMAs': [f for f in feature_names if f.startswith('ema')],
        'Price vs EMAs': [f for f in feature_names if f.startswith('price_vs_ema')],
        'Returns': [f for f in feature_names if f.startswith('returns')],
        'Volatility': [f for f in feature_names if 'volatility' in f or 'vol_' in f],
        'Momentum': [f for f in feature_names if f.startswith('momentum')],
        'RSI': [f for f in feature_names if f.startswith('rsi')],
        'MACD': [f for f in feature_names if f.startswith('macd')],
        'Bollinger': [f for f in feature_names if f.startswith('bb_')],
        'ATR': [f for f in feature_names if f.startswith('atr')],
        'Volume': [f for f in feature_names if f.startswith('volume') and 'ratio' in f],
        'Price Action': [f for f in feature_names if any(x in f for x in ['swing', 'choch', 'bos', 'fvg', 'trend'])],
        'Derived': [f for f in feature_names if any(x in f for x in ['slope', 'change', 'trend', 'position', 'regime', 'strength', 'acceleration'])],
    }

    # Display by category
    for category, features in categories.items():
        if features:
            print(f"📊 {category} ({len(features)} features):")
            for feat in sorted(features):
                print(f"   • {feat}")
            print()

    # Find features not in any category
    categorized = set()
    for features in categories.values():
        categorized.update(features)

    uncategorized = set(feature_names) - categorized
    if uncategorized:
        print(f"📊 Other ({len(uncategorized)} features):")
        for feat in sorted(uncategorized):
            print(f"   • {feat}")
        print()

    # Full sorted list
    print("=" * 80)
    print("📋 LISTA COMPLETA (ordem alfabética):")
    print("=" * 80)
    for i, feat in enumerate(sorted(feature_names), 1):
        print(f"{i:3d}. {feat}")
    print()

    # Save to file
    with open('/tmp/model_features_expected.txt', 'w') as f:
        f.write("# Features esperadas pelo modelo (73 total)\n\n")
        for i, feat in enumerate(sorted(feature_names), 1):
            f.write(f"{i:3d}. {feat}\n")

    print("=" * 80)
    print(f"✅ Lista salva em: /tmp/model_features_expected.txt")
    print("=" * 80)
    print()

except Exception as e:
    print(f"❌ Erro ao carregar modelo: {e}")
    print()
    print("💡 Possível causa: LightGBM não instalado")
    print("   Solução: pip install lightgbm")
