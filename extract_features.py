#!/usr/bin/env python3
"""
Extract feature names from pickle file by parsing binary data
Works without any ML library dependencies
"""

import sys
import re

def extract_strings_from_binary(filepath, min_length=3, max_length=100):
    """Extract printable strings from binary file"""

    with open(filepath, 'rb') as f:
        data = f.read()

    # Find all printable ASCII strings
    pattern = b'[ -~]{%d,%d}' % (min_length, max_length)
    strings = re.findall(pattern, data)

    # Decode to text
    strings = [s.decode('ascii', errors='ignore') for s in strings]

    return strings

def find_feature_names(strings):
    """Find strings that look like feature names"""

    # Common feature name patterns
    feature_patterns = [
        r'momentum_\d+',
        r'roc_\d+',
        r'rsi_\d+',
        r'sma_\d+',
        r'ema_\d+',
        r'atr_\d+',
        r'returns?',
        r'log_returns?',
        r'volatility',
        r'volume.*',
        r'price_.*',
        r'bb_.*',
        r'.*_kurt_.*',
        r'.*_skew_.*',
        r'stoch_.*',
    ]

    potential_features = set()

    for s in strings:
        # Check if it matches feature patterns
        for pattern in feature_patterns:
            if re.match(pattern, s, re.IGNORECASE):
                potential_features.add(s)
                break

        # Also include strings with underscores that look like features
        if '_' in s and len(s) < 50 and s.replace('_', '').replace('0', '').replace('1', '').replace('2', '').replace('3', '').replace('4', '').replace('5', '').replace('6', '').replace('7', '').replace('8', '').replace('9', '').isalpha():
            potential_features.add(s)

    return sorted(potential_features)

def analyze_features(features):
    """Analyze and categorize features"""

    print(f"\n📊 Found {len(features)} potential feature names:")
    print()

    # Categorize
    categories = {
        'momentum': [],
        'roc': [],
        'rsi': [],
        'sma': [],
        'ema': [],
        'atr': [],
        'returns': [],
        'volume': [],
        'volatility': [],
        'bb': [],
        'price': [],
        'other': []
    }

    for feat in features:
        feat_lower = feat.lower()
        categorized = False

        for category in categories.keys():
            if category in feat_lower:
                categories[category].append(feat)
                categorized = True
                break

        if not categorized:
            categories['other'].append(feat)

    # Print by category
    for category in sorted(categories.keys()):
        items = categories[category]
        if items:
            print(f"  {category.upper():12} ({len(items):3}): {', '.join(items[:15])}")
            if len(items) > 15:
                print(f"               ... and {len(items) - 15} more")

    # Check for specific features
    print()
    print("🎯 Checking for specific features:")

    target_features = [
        'momentum_5', 'momentum_10', 'momentum_20', 'momentum_30',
        'roc_5', 'roc_10', 'roc_20', 'roc_30',
        'returns', 'log_returns',
        'atr_14', 'rsi_14',
        'sma_7', 'ema_7'
    ]

    found_count = 0
    for feat in target_features:
        if feat in features:
            print(f"  ✅ {feat}")
            found_count += 1
        else:
            print(f"  ❌ {feat}")

    print()
    print(f"Found {found_count}/{len(target_features)} target features")

    return categories

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_features.py <model.pkl>")
        return

    filepath = sys.argv[1]

    print("=" * 80)
    print("🔬 FEATURE NAME EXTRACTOR (Binary Analysis)")
    print("=" * 80)
    print()
    print(f"Analyzing: {filepath}")

    # Extract strings
    print("\nExtracting strings from binary data...")
    strings = extract_strings_from_binary(filepath)
    print(f"Found {len(strings)} strings")

    # Find features
    print("\nSearching for feature names...")
    features = find_feature_names(strings)

    if not features:
        print("\n❌ No feature names found")
        print("\nTrying to find ANY strings that might be features...")
        # Show all strings with underscores
        underscore_strings = [s for s in strings if '_' in s and len(s) < 100]
        print(f"\nStrings with underscores ({len(underscore_strings)}):")
        for s in underscore_strings[:50]:
            print(f"  {s}")
        return

    # Analyze
    categories = analyze_features(features)

    # Detect model version
    print()
    print("🎯 Model version detection:")

    has_classical = any('atr_14' in f or 'rsi_14' in f for f in features)
    has_v2 = any('kurt' in f or 'skew' in f for f in features)
    has_v1 = any('momentum_3' in f for f in features)

    if has_classical:
        print("  Detected: Classical TA model")
    elif has_v2:
        print("  Detected: V2 Advanced model")
    elif has_v1:
        print("  Detected: V1 Advanced model")
    else:
        print("  Detected: Unknown model type")

    print("\n" + "=" * 80)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"  • Total features found: {len(features)}")
    print(f"  • Feature categories: {len([c for c in categories.values() if c])}")
    print()
    print("These features should be created in validate_standalone.py:")
    print()
    print("All features:")
    for i in range(0, len(features), 5):
        print("  " + ", ".join(features[i:i+5]))
    print()
    print("=" * 80)

if __name__ == "__main__":
    main()
