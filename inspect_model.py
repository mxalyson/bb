#!/usr/bin/env python3
"""
Inspect model pickle file without needing all dependencies
"""

import pickle
import sys
import io

class DummyModule:
    """Dummy module to fake missing imports"""
    def __init__(self, name):
        self.name = name

    def __getattr__(self, item):
        return DummyClass(f"{self.name}.{item}")

class DummyClass:
    """Dummy class to fake missing classes"""
    def __init__(self, name):
        self.__name__ = name
        self.__module__ = name.rsplit('.', 1)[0] if '.' in name else ''

    def __call__(self, *args, **kwargs):
        return DummyClass(self.__name__)

    def __getattr__(self, item):
        return DummyClass(f"{self.__name__}.{item}")

class RobustUnpickler(pickle.Unpickler):
    """Unpickler that handles missing modules"""

    def find_class(self, module, name):
        # List of modules we want to fake
        fake_modules = ['lightgbm', 'sklearn', 'xgboost', 'catboost', 'torch', 'tensorflow']

        if any(module.startswith(fm) for fm in fake_modules):
            print(f"   Faking import: {module}.{name}")
            return DummyClass(f"{module}.{name}")

        try:
            return super().find_class(module, name)
        except (AttributeError, ModuleNotFoundError) as e:
            print(f"   Faking missing: {module}.{name}")
            return DummyClass(f"{module}.{name}")

def load_pickle_robust(filepath):
    """Load pickle with robust unpickler"""

    print(f"Loading: {filepath}")

    with open(filepath, 'rb') as f:
        try:
            data = RobustUnpickler(f).load()
            print(f"✅ Loaded successfully")
            return data
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

def inspect_object(obj, indent=0):
    """Recursively inspect an object"""

    prefix = "  " * indent

    obj_type = type(obj).__name__

    if isinstance(obj, dict):
        print(f"{prefix}Dictionary with {len(obj)} keys:")
        for key, value in obj.items():
            value_type = type(value).__name__
            value_str = str(value)[:50] if not isinstance(value, (dict, list, tuple)) else ""

            print(f"{prefix}  '{key}': {value_type} {value_str}")

            # Recurse into nested structures
            if isinstance(value, dict) and indent < 2:
                inspect_object(value, indent + 2)
            elif isinstance(value, (list, tuple)) and len(value) > 0 and indent < 2:
                print(f"{prefix}    First item: {type(value[0]).__name__}")
                if len(value) < 20:
                    for i, item in enumerate(value[:10]):
                        print(f"{prefix}      [{i}]: {str(item)[:40]}")

    elif isinstance(obj, (list, tuple)):
        print(f"{prefix}{obj_type} with {len(obj)} items")
        if obj and indent < 2:
            print(f"{prefix}  First item type: {type(obj[0]).__name__}")
            if len(obj) < 20:
                for i, item in enumerate(obj[:10]):
                    print(f"{prefix}    [{i}]: {str(item)[:40]}")

    elif hasattr(obj, '__dict__'):
        print(f"{prefix}Object of type: {obj_type}")
        attrs = [k for k in dir(obj) if not k.startswith('_')]
        print(f"{prefix}  Attributes: {', '.join(attrs[:20])}")

        for attr in attrs[:15]:
            try:
                value = getattr(obj, attr)
                value_type = type(value).__name__
                value_str = str(value)[:40] if not callable(value) else "(method)"

                print(f"{prefix}    {attr}: {value_type} {value_str}")

                # Check if it's feature names
                if 'feature' in attr.lower() and isinstance(value, (list, tuple)):
                    print(f"{prefix}      Length: {len(value)}")
                    if len(value) < 20:
                        print(f"{prefix}      Items: {', '.join(str(v) for v in value[:10])}")
                    else:
                        print(f"{prefix}      First 10: {', '.join(str(v) for v in value[:10])}...")

            except Exception as e:
                print(f"{prefix}    {attr}: Error accessing - {e}")

    else:
        print(f"{prefix}{obj_type}: {str(obj)[:60]}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python inspect_model.py <model.pkl>")
        return

    filepath = sys.argv[1]

    print("=" * 80)
    print("🔍 MODEL INSPECTOR")
    print("=" * 80)
    print()

    data = load_pickle_robust(filepath)

    if data is None:
        print("\n❌ Failed to load pickle file")
        return

    print("\n" + "=" * 80)
    print("📋 MODEL STRUCTURE")
    print("=" * 80)
    print()

    inspect_object(data)

    print("\n" + "=" * 80)
    print("🔎 FEATURE EXTRACTION ATTEMPT")
    print("=" * 80)
    print()

    # Try to extract feature names
    feature_names = None

    if isinstance(data, dict):
        # Try common keys
        for key in ['feature_names', 'features', 'feature_columns', 'cols', 'feature_list']:
            if key in data:
                feature_names = data[key]
                print(f"✅ Found features in data['{key}']")
                break

    else:
        # Try common attributes
        for attr in ['feature_names', 'features', 'feature_columns', 'cols', 'feature_list', 'selected_features']:
            if hasattr(data, attr):
                feature_names = getattr(data, attr)
                if feature_names and len(feature_names) > 0:
                    print(f"✅ Found features in data.{attr}")
                    break

    if feature_names:
        print(f"\n📊 FEATURE NAMES ({len(feature_names)} total):")
        print()

        # Group by category
        categories = {}
        for feat in feature_names:
            category = 'other'
            for cat in ['momentum', 'roc', 'rsi', 'sma', 'ema', 'atr', 'returns', 'volume', 'volatility', 'bb']:
                if cat in feat.lower():
                    category = cat
                    break

            if category not in categories:
                categories[category] = []
            categories[category].append(feat)

        # Print categorized
        for category in sorted(categories.keys()):
            features = categories[category]
            print(f"  {category.upper():12} ({len(features):3}): {', '.join(features[:10])}")
            if len(features) > 10:
                print(f"               ... and {len(features) - 10} more")

        # Check for problematic features
        print()
        print("🎯 Checking for previously missing features:")
        problematic = ['momentum_5', 'momentum_10', 'roc_5', 'roc_10', 'roc_20']
        for feat in problematic:
            status = "✅ PRESENT" if feat in feature_names else "❌ MISSING"
            print(f"  {feat:15} : {status}")

    else:
        print("\n❌ Could not extract feature names")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
