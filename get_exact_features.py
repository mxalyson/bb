#!/usr/bin/env python3
"""
Get exact feature list from model - clean version
"""

import re
import sys

def get_exact_features(filepath):
    """Extract exact feature names"""

    with open(filepath, 'rb') as f:
        data = f.read()

    # Extract strings
    strings = re.findall(b'[ -~]{3,100}', data)
    strings = [s.decode('ascii', errors='ignore') for s in strings]

    # Known technical indicators (must match exactly)
    exact_features = set()

    # Momentum patterns
    for i in [3, 5, 8, 13, 21]:
        if f'momentum_{i}' in strings:
            exact_features.add(f'momentum_{i}')

    # Volume ratio patterns
    for i in [3, 5, 8, 13, 21]:
        if f'volume_ratio_{i}' in strings:
            exact_features.add(f'volume_ratio_{i}')

    # Returns
    for i in [1, 5, 10, 20]:
        if f'return_{i}' in strings:
            exact_features.add(f'return_{i}')

    # Volatility
    for i in [5, 20]:
        if f'volatility_{i}' in strings:
            exact_features.add(f'volatility_{i}')

    # Single word features
    singles = [
        'volume_ratio', 'volume_ma', 'volume_std', 'volume_momentum',
        'volatility_regime', 'price_position', 'price_acceleration',
        'price_vs_ema21', 'price_vs_ema50', 'price_vs_ema200',
        'ema21_vs_ema50', 'ema50_vs_ema200',
        'bb_lower', 'bb_middle', 'bb_upper', 'bb_position', 'bb_width',
        'rsi_ma', 'rsi_std', 'rsi_overbought', 'rsi_oversold',
        'atr_normalized', 'atr_ratio',
        'macd_signal', 'macd_hist', 'macd_hist_change', 'macd_positive',
        'adx_strong', 'adx_very_strong',
        'trend_strength', 'trend_numeric',
        'swing_high', 'swing_low',
        'fvg_bullish', 'fvg_bearish',
        'close_vs_vwap',
        'dist_to_resistance_pct', 'dist_to_support_pct',
        'body_size', 'upper_wick', 'lower_wick',
        'hl_range', 'hl_range_ma',
        'is_green'
    ]

    for feat in singles:
        if feat in strings:
            exact_features.add(feat)

    return sorted(exact_features)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_exact_features.py <model.pkl>")
        sys.exit(1)

    features = get_exact_features(sys.argv[1])

    print(f"Found {len(features)} exact features:")
    print()

    # Categorize
    cats = {
        'Momentum': [f for f in features if 'momentum' in f],
        'Volume': [f for f in features if 'volume' in f and 'momentum' not in f],
        'Returns': [f for f in features if 'return' in f],
        'Volatility': [f for f in features if 'volatility' in f],
        'Price': [f for f in features if 'price' in f],
        'EMA': [f for f in features if 'ema' in f],
        'Bollinger': [f for f in features if 'bb_' in f],
        'RSI': [f for f in features if 'rsi' in f],
        'ATR': [f for f in features if 'atr' in f],
        'MACD': [f for f in features if 'macd' in f],
        'ADX': [f for f in features if 'adx' in f],
        'Trend': [f for f in features if 'trend' in f],
        'Swing': [f for f in features if 'swing' in f],
        'FVG': [f for f in features if 'fvg' in f],
        'Candle': [f for f in features if any(x in f for x in ['body', 'wick', 'hl_range', 'is_green'])],
        'Other': [f for f in features if 'close_vs' in f or 'dist_to' in f],
    }

    for cat, feats in cats.items():
        if feats:
            print(f"{cat:12} ({len(feats):2}): {', '.join(feats)}")

    print()
    print("=" * 70)
    print("Python list:")
    print("=" * 70)
    print("feature_names = [")
    for f in features:
        print(f"    '{f}',")
    print("]")
    print()
    print(f"Total: {len(features)} features")
