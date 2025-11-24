"""
Test performance of structure_pa vs structure_pa_optimized.
"""

import pandas as pd
import time
from core.structure_pa import PriceActionAnalyzer as OldAnalyzer
from core.structure_pa_optimized import PriceActionAnalyzer as NewAnalyzer
from core.data import DataManager

# Config
config = {
    'swing_lookback': 5,
    'fvg_threshold_pct': 0.1
}

# Download real data
print("📥 Downloading 30 days of BTCUSDT data...")
data_manager = DataManager()
df = data_manager.get_data('BTCUSDT', '15m', 30, use_cache=False)
print(f"   Got {len(df)} candles")

# Test OLD version
print("\n🐌 Testing OLD version (Python loops)...")
old_analyzer = OldAnalyzer(config)
start = time.time()
df_old = old_analyzer.analyze(df.copy())
old_time = time.time() - start
print(f"   ⏱️ Time: {old_time:.2f}s")

# Test NEW version
print("\n⚡ Testing NEW version (Vectorized)...")
new_analyzer = NewAnalyzer(config)
start = time.time()
df_new = new_analyzer.analyze(df.copy())
new_time = time.time() - start
print(f"   ⏱️ Time: {new_time:.2f}s")

# Compare
speedup = old_time / new_time
print(f"\n{'='*50}")
print(f"🚀 SPEEDUP: {speedup:.1f}x faster!")
print(f"   Old: {old_time:.2f}s → New: {new_time:.2f}s")
print(f"   Saved: {old_time - new_time:.2f}s per analysis")
print(f"{'='*50}")

# Validate results are similar
print("\n✅ Validating results match...")
cols_to_check = ['swing_high', 'swing_low', 'trend', 'fvg_bullish', 'fvg_bearish']
for col in cols_to_check:
    old_sum = df_old[col].sum() if df_old[col].dtype == bool else df_old[col].notna().sum()
    new_sum = df_new[col].sum() if df_new[col].dtype == bool else df_new[col].notna().sum()
    match = "✅" if abs(old_sum - new_sum) < 50 else "❌"  # Allow small variance
    print(f"   {match} {col}: old={old_sum}, new={new_sum}")

print("\n✨ Performance test complete!")
