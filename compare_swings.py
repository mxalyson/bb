#!/usr/bin/env python3
"""
Compare swing detection between original and optimized versions.
"""

import sys
sys.path.insert(0, '/home/user/bb')

import pandas as pd
from core.structure_pa import PriceActionAnalyzer as OldAnalyzer
from core.structure_pa_optimized import PriceActionAnalyzer as NewAnalyzer
from core.data import DataManager

# Download real data (1 day)
print("📥 Downloading 1 day of BTCUSDT data...")
data_manager = DataManager()
df = data_manager.get_data('BTCUSDT', '15m', 1, use_cache=False)
print(f"   Got {len(df)} candles")
print()

# Config
config = {
    'swing_lookback': 5,
    'fvg_threshold_pct': 0.1
}

# Analyze with BOTH versions
print("🔨 Analyzing with ORIGINAL version...")
old_analyzer = OldAnalyzer(config)
df_old = old_analyzer.analyze(df.copy())
old_swings_high = df_old[df_old['swing_high']].index.tolist()
old_swings_low = df_old[df_old['swing_low']].index.tolist()
print(f"   Swing highs: {len(old_swings_high)}")
print(f"   Swing lows: {len(old_swings_low)}")
print()

print("⚡ Analyzing with OPTIMIZED version...")
new_analyzer = NewAnalyzer(config)
df_new = new_analyzer.analyze(df.copy())
new_swings_high = df_new[df_new['swing_high']].index.tolist()
new_swings_low = df_new[df_new['swing_low']].index.tolist()
print(f"   Swing highs: {len(new_swings_high)}")
print(f"   Swing lows: {len(new_swings_low)}")
print()

# Compare
print("=" * 80)
print("🔍 COMPARISON")
print("=" * 80)
print()

print(f"Swing highs: OLD={len(old_swings_high)}, NEW={len(new_swings_high)}, diff={abs(len(old_swings_high) - len(new_swings_high))}")
print(f"Swing lows:  OLD={len(old_swings_low)}, NEW={len(new_swings_low)}, diff={abs(len(old_swings_low) - len(new_swings_low))}")
print()

# Find differences
old_high_set = set(old_swings_high)
new_high_set = set(new_swings_high)

only_in_old_high = old_high_set - new_high_set
only_in_new_high = new_high_set - old_high_set

old_low_set = set(old_swings_low)
new_low_set = set(new_swings_low)

only_in_old_low = old_low_set - new_low_set
only_in_new_low = new_low_set - old_low_set

if only_in_old_high or only_in_new_high:
    print("⚠️  SWING HIGH DIFFERENCES:")
    if only_in_old_high:
        print(f"   Only in ORIGINAL: {len(only_in_old_high)} swings")
        for ts in sorted(list(only_in_old_high))[:5]:
            print(f"      {ts}")
    if only_in_new_high:
        print(f"   Only in OPTIMIZED: {len(only_in_new_high)} swings")
        for ts in sorted(list(only_in_new_high))[:5]:
            print(f"      {ts}")
    print()

if only_in_old_low or only_in_new_low:
    print("⚠️  SWING LOW DIFFERENCES:")
    if only_in_old_low:
        print(f"   Only in ORIGINAL: {len(only_in_old_low)} swings")
        for ts in sorted(list(only_in_old_low))[:5]:
            print(f"      {ts}")
    if only_in_new_low:
        print(f"   Only in OPTIMIZED: {len(only_in_new_low)} swings")
        for ts in sorted(list(only_in_new_low))[:5]:
            print(f"      {ts}")
    print()

# Calculate percentage match
high_match_pct = len(old_high_set & new_high_set) / max(len(old_high_set), len(new_high_set), 1) * 100
low_match_pct = len(old_low_set & new_low_set) / max(len(old_low_set), len(new_low_set), 1) * 100

print("=" * 80)
print(f"📊 MATCH PERCENTAGE:")
print(f"   Swing highs: {high_match_pct:.1f}% match")
print(f"   Swing lows: {low_match_pct:.1f}% match")
print()

if high_match_pct >= 95 and low_match_pct >= 95:
    print("✅ EXCELLENT: >95% match - Versions are nearly identical!")
elif high_match_pct >= 90 and low_match_pct >= 90:
    print("✅ GOOD: >90% match - Minor differences, acceptable")
elif high_match_pct >= 80 and low_match_pct >= 80:
    print("⚠️  WARNING: 80-90% match - Significant differences detected")
else:
    print("❌ ERROR: <80% match - Versions produce very different results!")

print("=" * 80)
