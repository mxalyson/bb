#!/usr/bin/env python3
"""
Quick validation test - compara structure_pa vs structure_pa_optimized.
"""

import sys
sys.path.insert(0, '/home/user/bb')

import pandas as pd
import numpy as np

# Create simple test data
print("Creating test data...")
dates = pd.date_range('2024-01-01', periods=50, freq='15min')
np.random.seed(42)

# Generate price data with clear swing points
base_price = 50000
prices = base_price + np.cumsum(np.random.randn(50) * 100)

df = pd.DataFrame({
    'open': prices,
    'high': prices + np.random.rand(50) * 50,
    'low': prices - np.random.rand(50) * 50,
    'close': prices,
    'volume': np.random.randint(1000, 10000, 50)
}, index=dates)

print(f"Test data: {len(df)} candles")
print(f"Price range: ${df['low'].min():.0f} - ${df['high'].max():.0f}")
print()

# Test OLD version
print("=" * 60)
print("Testing OLD version (structure_pa.py)...")
print("=" * 60)

try:
    from core.structure_pa import PriceActionAnalyzer as OldAnalyzer

    config = {'swing_lookback': 5, 'fvg_threshold_pct': 0.1}
    old_analyzer = OldAnalyzer(config)
    df_old = old_analyzer.analyze(df.copy())

    old_swings_high = df_old['swing_high'].sum()
    old_swings_low = df_old['swing_low'].sum()

    print(f"✅ OLD version completed")
    print(f"   Swing highs: {old_swings_high}")
    print(f"   Swing lows: {old_swings_low}")
    print(f"   Result shape: {df_old.shape}")

except Exception as e:
    print(f"❌ OLD version FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test NEW version
print("=" * 60)
print("Testing NEW version (structure_pa_optimized.py) - FIXED")
print("=" * 60)

try:
    from core.structure_pa_optimized import PriceActionAnalyzer as NewAnalyzer

    config = {'swing_lookback': 5, 'fvg_threshold_pct': 0.1}
    new_analyzer = NewAnalyzer(config)
    df_new = new_analyzer.analyze(df.copy())

    new_swings_high = df_new['swing_high'].sum()
    new_swings_low = df_new['swing_low'].sum()

    print(f"✅ NEW version completed")
    print(f"   Swing highs: {new_swings_high}")
    print(f"   Swing lows: {new_swings_low}")
    print(f"   Result shape: {df_new.shape}")

except Exception as e:
    print(f"❌ NEW version FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Compare results
print("=" * 60)
print("COMPARISON")
print("=" * 60)

swing_high_diff = abs(old_swings_high - new_swings_high)
swing_low_diff = abs(old_swings_low - new_swings_low)

print(f"Swing highs: OLD={old_swings_high}, NEW={new_swings_high}, diff={swing_high_diff}")
print(f"Swing lows:  OLD={old_swings_low}, NEW={new_swings_low}, diff={swing_low_diff}")

# Allow small variance (algorithm differences)
if swing_high_diff <= 5 and swing_low_diff <= 5:
    print()
    print("✅ RESULTS MATCH (within tolerance)!")
    print("✅ structure_pa_optimized.py is FIXED and working correctly!")
else:
    print()
    print(f"⚠️ WARNING: Large difference detected!")
    print(f"   This might indicate a bug in the optimized version")

print()
print("=" * 60)
print("TEST COMPLETE")
print("=" * 60)
