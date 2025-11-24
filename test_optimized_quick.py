#!/usr/bin/env python3
"""Quick test to verify structure_pa_optimized works correctly."""

import sys
import pandas as pd
import numpy as np

# Test data - small DataFrame
data = {
    'timestamp': pd.date_range('2024-01-01', periods=20, freq='15min'),
    'open': [100 + i for i in range(20)],
    'high': [105 + i for i in range(20)],
    'low': [95 + i for i in range(20)],
    'close': [100 + i for i in range(20)],
    'volume': [1000] * 20
}

df = pd.DataFrame(data)
df.set_index('timestamp', inplace=True)

print(f"✅ Test DataFrame created: {len(df)} rows")
print(f"   Columns: {list(df.columns)}")
print(f"   Shape: {df.shape}")
print()

# Test optimized version
try:
    from core.structure_pa_optimized import PriceActionAnalyzer

    config = {
        'swing_lookback': 5,
        'fvg_threshold_pct': 0.1
    }

    print("🔨 Testing OPTIMIZED version...")
    analyzer = PriceActionAnalyzer(config)
    df_result = analyzer.analyze(df.copy())

    print(f"✅ OPTIMIZED version completed!")
    print(f"   Result shape: {df_result.shape}")
    print(f"   Swing highs detected: {df_result['swing_high'].sum()}")
    print(f"   Swing lows detected: {df_result['swing_low'].sum()}")
    print(f"   Columns added: {len(df_result.columns) - len(df.columns)}")
    print()

    # Check for critical columns
    required_cols = ['swing_high', 'swing_low', 'trend', 'fvg_bullish', 'fvg_bearish']
    missing = [c for c in required_cols if c not in df_result.columns]
    if missing:
        print(f"❌ Missing columns: {missing}")
        sys.exit(1)

    # Check for NaN corruption
    if df_result.isnull().all().any():
        print(f"❌ Some columns are all NaN!")
        sys.exit(1)

    # Check DataFrame is not empty
    if df_result.empty or len(df_result) == 0:
        print(f"❌ Result DataFrame is EMPTY!")
        sys.exit(1)

    print("✅ ALL CHECKS PASSED! Optimized version is working correctly.")

except Exception as e:
    print(f"❌ OPTIMIZED version FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
