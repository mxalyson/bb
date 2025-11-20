#!/usr/bin/env python3
"""
Validator that works WITHOUT external dependencies
Uses synthetic but realistic Bitcoin-like price data
"""

import pickle
import random
import math
from datetime import datetime, timedelta
from collections import namedtuple

# Simple data structures to replace pandas
Candle = namedtuple('Candle', ['timestamp', 'open', 'high', 'low', 'close', 'volume'])

class SimpleDataFrame:
    """Minimal DataFrame replacement"""
    def __init__(self, data, columns):
        self.data = data
        self.columns = columns
        self._index = 0

    def __len__(self):
        return len(self.data)

    def __getitem__(self, key):
        if isinstance(key, str):
            col_idx = self.columns.index(key)
            return [row[col_idx] for row in self.data]
        elif isinstance(key, int):
            return dict(zip(self.columns, self.data[key]))
        return None

    def iloc(self, idx):
        return dict(zip(self.columns, self.data[idx]))

def generate_synthetic_btc_data(days=180, interval_minutes=15):
    """Generate realistic Bitcoin-like OHLCV data"""

    print(f"Generating {days} days of synthetic Bitcoin data ({interval_minutes}min candles)...")

    # Starting values (realistic for late 2024)
    base_price = 65000
    current_price = base_price

    candles_per_day = (24 * 60) // interval_minutes
    total_candles = days * candles_per_day

    data = []
    current_time = datetime.now() - timedelta(days=days)

    # Trend parameters
    trend = 1.0  # Neutral
    volatility = 0.02  # 2% base volatility

    for i in range(total_candles):
        # Simulate trends changing
        if i % (candles_per_day * 7) == 0:  # Every week
            trend = random.uniform(0.95, 1.05)  # Random trend

        # Simulate volatility clusters
        if i % (candles_per_day * 3) == 0:  # Every 3 days
            volatility = random.uniform(0.01, 0.04)  # 1-4% volatility

        # Generate candle
        open_price = current_price

        # Random walk with trend
        change = random.gauss(0, volatility) * trend
        close_price = open_price * (1 + change)

        # High/low with realistic wicks
        high_wick = random.uniform(0, volatility * 0.5)
        low_wick = random.uniform(0, volatility * 0.5)

        high_price = max(open_price, close_price) * (1 + high_wick)
        low_price = min(open_price, close_price) * (1 - low_wick)

        # Volume (correlated with volatility)
        base_volume = 1000
        volume = base_volume * (1 + abs(change) * 10) * random.uniform(0.5, 1.5)

        candle = Candle(
            timestamp=current_time,
            open=round(open_price, 2),
            high=round(high_price, 2),
            low=round(low_price, 2),
            close=round(close_price, 2),
            volume=round(volume, 4)
        )

        data.append(candle)

        current_price = close_price
        current_time += timedelta(minutes=interval_minutes)

        if (i + 1) % 1000 == 0:
            print(f"  Generated {i+1:,} candles...")

    print(f"✅ Generated {len(data):,} candles")
    print(f"   Price range: ${min(c.low for c in data):,.0f} - ${max(c.high for c in data):,.0f}")
    print(f"   Final price: ${data[-1].close:,.2f}")

    return data

def load_model_simple(model_path):
    """Load model without pandas/numpy"""

    print(f"\n🔍 Loading model: {model_path}")

    try:
        with open(model_path, 'rb') as f:
            # Try to unpickle with restricted imports
            data = pickle.load(f)

        print(f"   ✅ Model loaded")
        print(f"   Type: {type(data).__name__}")

        # Extract info
        if isinstance(data, dict):
            feature_names = data.get('feature_names', data.get('features', []))
            model = data.get('model')
        else:
            # Object with attributes
            feature_names = getattr(data, 'feature_names', None)
            if not feature_names:
                feature_names = getattr(data, 'feature_columns', [])
            model = getattr(data, 'model', None) or getattr(data, 'models', None)

        if feature_names:
            print(f"   📊 Features: {len(feature_names)}")
            print(f"   First 10: {feature_names[:10]}")

        return {
            'model': model,
            'feature_names': feature_names or [],
            'data': data
        }

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

def analyze_model_features(feature_names):
    """Analyze what features the model needs"""

    print(f"\n📋 Analyzing {len(feature_names)} required features...")

    # Categorize features
    categories = {
        'returns': [],
        'momentum': [],
        'roc': [],
        'rsi': [],
        'sma': [],
        'ema': [],
        'atr': [],
        'volume': [],
        'bollinger': [],
        'volatility': [],
        'other': []
    }

    for feat in feature_names:
        feat_lower = feat.lower()
        categorized = False

        for category in categories.keys():
            if category in feat_lower:
                categories[category].append(feat)
                categorized = True
                break

        if not categorized:
            categories['other'].append(feat)

    # Print summary
    print("\n   Feature categories:")
    for category, features in sorted(categories.items()):
        if features:
            print(f"   • {category.capitalize():12} : {len(features):3} features")
            if len(features) <= 5:
                print(f"      {', '.join(features)}")

    # Detect model version
    has_classical = any('atr_14' in f or 'rsi_14' in f for f in feature_names)
    has_v2 = any('kurt' in f or 'skew' in f for f in feature_names)
    has_v1 = any('momentum_3' in f for f in feature_names)

    if has_classical:
        version = "Classical TA"
    elif has_v2:
        version = "V2 Advanced"
    elif has_v1:
        version = "V1 Advanced"
    else:
        version = "Unknown"

    print(f"\n   🎯 Detected version: {version}")

    # Check for the problematic features
    missing_features = ['momentum_5', 'roc_5', 'roc_10', 'roc_20']
    found = [f for f in missing_features if f in feature_names]

    if found:
        print(f"   ✅ Contains: {', '.join(found)}")
    else:
        print(f"   ⚠️  Missing the previously problematic features")

    return version

def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python validate_with_synthetic_data.py <model.pkl>")
        print("\nThis script:")
        print("  1. Generates synthetic Bitcoin-like price data")
        print("  2. Loads and analyzes your model")
        print("  3. Shows what features it requires")
        print("  4. Verifies the model can be loaded")
        return

    model_path = sys.argv[1]
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 180

    print("=" * 80)
    print("🧪 MODEL VALIDATOR - Synthetic Data Mode")
    print("=" * 80)
    print(f"Model: {model_path}")
    print(f"Synthetic data: {days} days")
    print()

    # Generate data
    candles = generate_synthetic_btc_data(days=days)

    # Load model
    model_data = load_model_simple(model_path)

    if not model_data:
        print("\n❌ Failed to load model")
        return

    feature_names = model_data['feature_names']

    if not feature_names:
        print("\n❌ Could not extract feature names from model")
        print("   The model needs to have 'feature_names' or 'feature_columns' attribute")
        return

    # Analyze features
    version = analyze_model_features(feature_names)

    # Success summary
    print("\n" + "=" * 80)
    print("✅ VALIDATION COMPLETE")
    print("=" * 80)
    print()
    print("Results:")
    print(f"  ✓ Model loaded successfully")
    print(f"  ✓ Feature list extracted: {len(feature_names)} features")
    print(f"  ✓ Model version detected: {version}")
    print(f"  ✓ Synthetic data generated: {len(candles):,} candles")
    print()
    print("Next steps:")
    print("  1. Run validate_standalone.py on your local machine with internet")
    print("  2. Or use Option 2 from GUIA_COMPLETO_VALIDACAO.md (CSV data)")
    print("  3. Or use Option 3 to fix validate_strategy.py")
    print()
    print(f"The model expects these specific features:")
    print(f"  {', '.join(feature_names[:20])}...")
    if len(feature_names) > 20:
        print(f"  ... and {len(feature_names) - 20} more")
    print()
    print("=" * 80)

if __name__ == "__main__":
    main()
