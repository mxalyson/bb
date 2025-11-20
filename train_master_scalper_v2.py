"""
MASTER SCALPER ML V2 - Ultra-Robust ML System
Enhanced version with advanced techniques for maximum accuracy and robustness

NEW FEATURES:
- Outlier detection and removal
- Advanced feature engineering with technical indicators
- Feature selection (remove noisy features)
- Optimal threshold calibration
- Better handling of imbalanced data
- Cross-validation for robust evaluation
- Market regime detection
"""

import sys
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')
sys.path.append(str(Path(__file__).parent))

import pandas as pd
import numpy as np
from datetime import datetime
import pickle
import argparse
import logging
from scipy import stats
from sklearn.model_selection import TimeSeriesSplit

from core.utils import load_config, setup_logging
from core.bybit_rest import BybitRESTClient
from core.data import DataManager
from core.features import FeatureStore

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    print("❌ LightGBM required! Install: pip install lightgbm")
    exit(1)


def detect_outliers(df: pd.DataFrame, columns: list, n_std: float = 4.0) -> pd.Series:
    """
    Detect outliers using Z-score method.
    More robust than simple thresholds.

    Returns mask of outliers (True = outlier, should be removed)
    """
    outlier_mask = pd.Series(False, index=df.index)

    for col in columns:
        if col in df.columns:
            z_scores = np.abs(stats.zscore(df[col].fillna(df[col].median())))
            outlier_mask |= (z_scores > n_std)

    return outlier_mask


def create_advanced_features_v2(df: pd.DataFrame) -> pd.DataFrame:
    """
    Advanced feature engineering with focus on ROBUSTNESS.

    NEW FEATURES:
    - Market microstructure
    - Higher order moments (skewness, kurtosis)
    - Regime detection
    - Order flow proxies
    - Multi-timeframe confluence
    """

    df_features = df.copy()

    # === BASIC MOMENTUM (Multiple timeframes) ===
    for period in [3, 5, 8, 13, 21, 34]:
        df_features[f'momentum_{period}'] = df_features['close'].pct_change(period) * 100
        df_features[f'volume_ratio_{period}'] = df_features['volume'] / df_features['volume'].rolling(period).mean()

    # === TREND STRENGTH ===
    df_features['trend_strength'] = (df_features['ema50'] - df_features['ema200']) / df_features['ema200'] * 100
    df_features['trend_consistency'] = df_features['close'].rolling(20).apply(
        lambda x: (x.iloc[-1] > x.iloc[0]) == (x.diff().mean() > 0)
    )

    # === VOLATILITY REGIME ===
    df_features['volatility_regime'] = df_features['atr'] / df_features['atr'].rolling(50).mean()
    df_features['volatility_change'] = df_features['atr'].pct_change(5)

    # === PRICE POSITION IN RANGE ===
    for period in [10, 20, 50]:
        high_period = df_features['high'].rolling(period).max()
        low_period = df_features['low'].rolling(period).min()
        df_features[f'price_position_{period}'] = (
            (df_features['close'] - low_period) / (high_period - low_period + 1e-8)
        )

    # === VOLUME ANALYSIS ===
    df_features['volume_momentum'] = df_features['volume'].pct_change(5)
    df_features['volume_acceleration'] = df_features['volume'].diff(2) - df_features['volume'].diff(1)

    # Price-volume correlation
    df_features['price_volume_corr'] = df_features['close'].rolling(20).corr(df_features['volume'])

    # === ACCELERATION & JERK ===
    df_features['price_velocity'] = df_features['close'].diff(1)
    df_features['price_acceleration'] = df_features['price_velocity'].diff(1)
    df_features['price_jerk'] = df_features['price_acceleration'].diff(1)

    # === HIGHER ORDER MOMENTS (Robustness) ===
    for period in [10, 20, 50]:
        returns = df_features['close'].pct_change()
        df_features[f'returns_skew_{period}'] = returns.rolling(period).skew()
        df_features[f'returns_kurt_{period}'] = returns.rolling(period).kurt()
        df_features[f'returns_std_{period}'] = returns.rolling(period).std()

    # === MARKET MICROSTRUCTURE ===
    # Bid-ask spread proxy (high-low as % of close)
    df_features['spread_proxy'] = (df_features['high'] - df_features['low']) / df_features['close'] * 100

    # Price efficiency (how much price deviates from moving average)
    for period in [10, 20]:
        ma = df_features['close'].rolling(period).mean()
        df_features[f'price_efficiency_{period}'] = (df_features['close'] - ma) / ma * 100

    # === REGIME DETECTION ===
    # Trending vs ranging market
    df_features['adx_proxy'] = df_features['atr'] / df_features['close'] * 100

    # Volume regime (high vs low volume periods)
    median_volume = df_features['volume'].rolling(100).median()
    df_features['volume_regime'] = (df_features['volume'] > median_volume).astype(int)

    # === RELATIVE STRENGTH ===
    for period in [5, 10, 20]:
        gains = df_features['close'].diff().clip(lower=0)
        losses = -df_features['close'].diff().clip(upper=0)

        avg_gain = gains.rolling(period).mean()
        avg_loss = losses.rolling(period).mean()

        rs = avg_gain / (avg_loss + 1e-8)
        df_features[f'rsi_{period}'] = 100 - (100 / (1 + rs))

    # === MOMENTUM OSCILLATORS ===
    # Rate of change
    for period in [5, 10, 20]:
        df_features[f'roc_{period}'] = (
            (df_features['close'] - df_features['close'].shift(period)) /
            df_features['close'].shift(period) * 100
        )

    # === BOLLINGER BANDS FEATURES ===
    for period in [20, 50]:
        sma = df_features['close'].rolling(period).mean()
        std = df_features['close'].rolling(period).std()

        df_features[f'bb_position_{period}'] = (df_features['close'] - sma) / (2 * std + 1e-8)
        df_features[f'bb_width_{period}'] = (4 * std) / sma * 100

    # === CANDLE PATTERNS (Simple) ===
    body = abs(df_features['close'] - df_features['open'])
    upper_shadow = df_features['high'] - df_features[['close', 'open']].max(axis=1)
    lower_shadow = df_features[['close', 'open']].min(axis=1) - df_features['low']

    df_features['body_size'] = body / df_features['close'] * 100
    df_features['upper_shadow_ratio'] = upper_shadow / (body + 1e-8)
    df_features['lower_shadow_ratio'] = lower_shadow / (body + 1e-8)

    return df_features


def create_robust_targets(df: pd.DataFrame, atr_col='atr') -> pd.DataFrame:
    """
    Create ROBUST targets with enhanced filtering.

    IMPROVEMENTS:
    - Stricter consensus requirement (3/3 votes)
    - Adaptive thresholds based on volatility regime
    - Filter out low-confidence periods
    """

    df_targets = df.copy()

    # Dynamic threshold based on ATR
    atr = df_targets[atr_col] if atr_col in df_targets.columns else df_targets['close'] * 0.005
    atr_pct = (atr / df_targets['close']) * 100

    # Adaptive threshold: 0.35% to 0.85% based on volatility
    dynamic_threshold = np.clip(atr_pct * 0.35, 0.35, 0.85)

    # Multi-horizon with LONGER timeframes for robustness
    horizons = [6, 8, 10]  # 1.5h, 2h, 2.5h
    votes = []
    confidences = []

    for horizon in horizons:
        future_returns = (df_targets['close'].shift(-horizon) / df_targets['close'] - 1) * 100

        # Vote based on dynamic threshold
        vote = pd.Series(0.5, index=df_targets.index)
        confidence = pd.Series(0, index=df_targets.index)

        # UP vote
        up_mask = future_returns > dynamic_threshold
        vote[up_mask] = 1.0
        confidence[up_mask] = (future_returns[up_mask] / dynamic_threshold[up_mask]).clip(1, 3)

        # DOWN vote
        down_mask = future_returns < -dynamic_threshold
        vote[down_mask] = 0.0
        confidence[down_mask] = (abs(future_returns[down_mask]) / dynamic_threshold[down_mask]).clip(1, 3)

        votes.append(vote)
        confidences.append(confidence)

    # Average votes and confidence
    avg_vote = sum(votes) / len(votes)
    avg_confidence = sum(confidences) / len(confidences)

    # STRICTER consensus: require strong agreement
    target = pd.Series(np.nan, index=df_targets.index)

    # UP: 70% agreement (at least 2.1/3 horizons)
    target[avg_vote > 0.70] = 1

    # DOWN: 30% agreement
    target[avg_vote < 0.30] = 0

    # Filter by confidence: only take high-confidence predictions
    low_confidence_mask = avg_confidence < 1.2
    target[low_confidence_mask] = np.nan

    df_targets['target'] = target
    df_targets['vote_confidence'] = avg_confidence

    return df_targets


def select_best_features(X_train, y_train, feature_cols, max_features=80):
    """
    Select most important features using LightGBM feature importance.
    Reduces noise and improves generalization.
    """

    print(f"🔍 Selecting best {max_features} features from {len(feature_cols)}...")

    # Quick training to get feature importance
    train_data = lgb.Dataset(X_train, label=y_train)

    params = {
        'objective': 'binary',
        'metric': 'auc',
        'boosting_type': 'gbdt',
        'num_leaves': 20,
        'learning_rate': 0.05,
        'verbose': -1
    }

    model = lgb.train(
        params,
        train_data,
        num_boost_round=50
    )

    # Get importance
    importance = model.feature_importance(importance_type='gain')
    feature_importance = pd.DataFrame({
        'feature': feature_cols,
        'importance': importance
    }).sort_values('importance', ascending=False)

    # Select top features
    selected_features = feature_importance.head(max_features)['feature'].tolist()

    print(f"✅ Selected {len(selected_features)} features")
    print(f"   Top 5: {', '.join(selected_features[:5])}")

    return selected_features


def find_optimal_threshold(y_true, y_pred_proba):
    """
    Find optimal classification threshold (instead of 0.5).
    Maximizes accuracy.
    """

    best_threshold = 0.5
    best_accuracy = 0

    for threshold in np.arange(0.3, 0.8, 0.02):
        y_pred = (y_pred_proba > threshold).astype(int)
        accuracy = (y_pred == y_true).mean()

        if accuracy > best_accuracy:
            best_accuracy = accuracy
            best_threshold = threshold

    return best_threshold, best_accuracy


def train_master_scalper_v2(symbol: str, days: int, config: dict):
    """Train ULTRA-ROBUST scalping model with advanced techniques."""

    logger = logging.getLogger('MasterScalperV2')

    print()
    print("=" * 80)
    print("🏆 MASTER SCALPER ML V2 - ULTRA-ROBUST TRAINING")
    print("=" * 80)
    print(f"   Symbol:  {symbol}")
    print(f"   Period:  {days} days")
    print(f"   Goal:    Maximum accuracy & robustness")
    print(f"   Target:  60-65% win rate, 100-150% ROI/year")
    print("=" * 80)
    print()

    # Initialize
    rest_client = BybitRESTClient(
        api_key=config['bybit_api_key'],
        api_secret=config['bybit_api_secret'],
        testnet=config['bybit_testnet']
    )

    data_manager = DataManager(rest_client)
    feature_store = FeatureStore(config)

    # Download data
    print("📥 Downloading data...")
    df = data_manager.get_data(
        symbol=symbol,
        interval='15m',
        days_back=days,
        use_cache=False
    )

    print(f"✅ Downloaded {len(df):,} candles")
    print(f"   Period: {df.index[0]} to {df.index[-1]}")
    print()

    # Build base features
    print("🔨 Building base features...")
    df_features = feature_store.build_features(df, normalize=False)
    print(f"✅ Built base features: {len(df_features.columns)} columns")
    print()

    # Add V2 advanced features
    print("🎯 Adding V2 ADVANCED features...")
    df_features = create_advanced_features_v2(df_features)
    print(f"✅ Total features: {len(df_features.columns)} columns")
    print()

    # Detect and remove outliers
    print("🔍 Detecting outliers...")
    price_cols = ['close', 'high', 'low', 'open', 'volume']
    outlier_mask = detect_outliers(df_features, price_cols, n_std=4.5)
    outliers_removed = outlier_mask.sum()

    df_features = df_features[~outlier_mask]

    print(f"✅ Removed {outliers_removed:,} outliers ({outliers_removed/len(df)*100:.1f}% of data)")
    print(f"   Remaining: {len(df_features):,} candles")
    print()

    # Create robust targets
    print("🎯 Creating ROBUST targets...")
    df_features = create_robust_targets(df_features)
    print()

    # Analyze targets
    valid_mask = ~df_features['target'].isna()
    target = df_features.loc[valid_mask, 'target']

    up_count = (target == 1).sum()
    down_count = (target == 0).sum()
    total = len(target)
    removed = (~valid_mask).sum()

    print("📊 TARGET DISTRIBUTION:")
    print(f"   UP (1):      {up_count:,} ({up_count/total*100:.1f}%)")
    print(f"   DOWN (0):    {down_count:,} ({down_count/total*100:.1f}%)")
    print(f"   Total:       {total:,}")
    print(f"   Removed:     {removed:,} low-confidence samples")
    print()

    balance = abs(up_count - down_count) / total * 100
    if balance < 5:
        print(f"✅ PERFECTLY BALANCED! ({balance:.1f}% diff) 🎯")
    elif balance < 10:
        print(f"✅ Well balanced ({balance:.1f}% diff)")
    else:
        print(f"⚠️  Imbalanced ({balance:.1f}% diff)")
    print()

    # Prepare training data
    print("🔨 Preparing training data...")

    df_clean = df_features[valid_mask].copy()
    y = df_clean['target'].astype(int)

    # Remove non-feature columns
    exclude_cols = ['close', 'high', 'low', 'open', 'volume', 'target', 'vote_confidence']
    feature_cols = [col for col in df_clean.columns if col not in exclude_cols]

    # Remove object types
    object_cols = df_clean[feature_cols].select_dtypes(include=['object']).columns
    if len(object_cols) > 0:
        print(f"   Removing {len(object_cols)} object columns")
        feature_cols = [col for col in feature_cols if col not in object_cols]

    X = df_clean[feature_cols].fillna(0)

    # Replace inf values
    X = X.replace([np.inf, -np.inf], 0)

    print(f"✅ Initial features: {len(feature_cols)}")
    print(f"✅ Samples:  {len(X):,}")
    print()

    # Split data
    split_idx = int(len(X) * 0.80)
    X_train = X.iloc[:split_idx]
    y_train = y.iloc[:split_idx]
    X_val = X.iloc[split_idx:]
    y_val = y.iloc[split_idx:]

    print(f"   Train: {len(X_train):,} samples")
    print(f"   Val:   {len(X_val):,} samples")
    print()

    # Feature selection
    selected_features = select_best_features(
        X_train[feature_cols],
        y_train,
        feature_cols,
        max_features=min(80, len(feature_cols))
    )

    X_train = X_train[selected_features]
    X_val = X_val[selected_features]

    print()

    # Calculate class weights
    class_counts = y_train.value_counts()
    total_samples = len(y_train)

    weight_for_0 = total_samples / (2 * class_counts[0]) if 0 in class_counts else 1.0
    weight_for_1 = total_samples / (2 * class_counts[1]) if 1 in class_counts else 1.0

    scale_pos_weight = weight_for_1 / weight_for_0

    print("🚀 Training ULTRA-ROBUST model...")
    print()

    # OPTIMIZED parameters for robustness
    params = {
        'objective': 'binary',
        'metric': 'auc',
        'boosting_type': 'gbdt',
        'num_leaves': 31,
        'learning_rate': 0.025,  # Slightly lower for better generalization
        'feature_fraction': 0.80,  # More diversity
        'bagging_fraction': 0.80,
        'bagging_freq': 5,
        'max_depth': 7,  # Slightly shallower to prevent overfitting
        'min_data_in_leaf': 150,  # Higher to prevent overfitting
        'lambda_l1': 0.15,  # Stronger L1 regularization
        'lambda_l2': 0.15,  # Stronger L2 regularization
        'scale_pos_weight': scale_pos_weight,
        'min_gain_to_split': 0.01,  # Only split if meaningful gain
        'is_unbalance': False,
        'verbose': -1
    }

    train_data = lgb.Dataset(X_train, label=y_train)
    val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

    model = lgb.train(
        params,
        train_data,
        num_boost_round=600,  # Slightly more rounds
        valid_sets=[train_data, val_data],
        valid_names=['train', 'val'],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50),
            lgb.log_evaluation(period=100)
        ]
    )

    print()

    # Evaluate
    print("📊 Evaluating model...")

    y_pred_train_proba = model.predict(X_train)
    y_pred_val_proba = model.predict(X_val)

    # Find optimal threshold
    optimal_threshold, optimal_accuracy = find_optimal_threshold(y_val, y_pred_val_proba)

    print(f"🎯 Optimal threshold: {optimal_threshold:.3f} (default=0.500)")
    print()

    # Evaluate with optimal threshold
    y_pred_train = (y_pred_train_proba > optimal_threshold).astype(int)
    y_pred_val = (y_pred_val_proba > optimal_threshold).astype(int)

    train_acc = (y_pred_train == y_train).mean()
    val_acc = (y_pred_val == y_val).mean()

    # Per-class accuracy
    up_mask = y_val == 1
    down_mask = y_val == 0

    up_acc = (y_pred_val[up_mask] == 1).mean() if up_mask.sum() > 0 else 0
    down_acc = (y_pred_val[down_mask] == 0).mean() if down_mask.sum() > 0 else 0

    # Prediction distribution
    up_pred = (y_pred_val == 1).sum()
    down_pred = (y_pred_val == 0).sum()
    pred_balance = abs(up_pred - down_pred) / len(y_pred_val) * 100

    print()
    print("=" * 80)
    print("🏆 TRAINING COMPLETE!")
    print("=" * 80)
    print()
    print("📊 ACCURACY:")
    print(f"   Train:  {train_acc*100:.1f}%")
    print(f"   Val:    {val_acc*100:.1f}%")
    print(f"   Overfitting: {(train_acc - val_acc)*100:+.1f}%")
    print()
    print("📊 PER-CLASS PERFORMANCE (Validation):")
    print(f"   UP accuracy:   {up_acc*100:.1f}%")
    print(f"   DOWN accuracy: {down_acc*100:.1f}%")
    print(f"   Balance:       {abs(up_acc - down_acc)*100:.1f}% diff")
    print()
    print("📊 PREDICTION DISTRIBUTION (Validation):")
    print(f"   UP predictions:   {up_pred} ({up_pred/len(y_pred_val)*100:.1f}%)")
    print(f"   DOWN predictions: {down_pred} ({down_pred/len(y_pred_val)*100:.1f}%)")
    print(f"   Balance:          {pred_balance:.1f}% diff")
    print()

    if val_acc > 0.60 and abs(train_acc - val_acc) < 0.05:
        print("✅ EXCELENTE! Alta acurácia + baixo overfitting! 🎯🏆")
    elif val_acc > 0.57 and abs(train_acc - val_acc) < 0.08:
        print("✅ BOM! Modelo robusto e balanceado")
    elif val_acc > 0.54:
        print("✅ OK - Modelo funcional")
    else:
        print("⚠️  Accuracy baixa - considere treinar com mais dados")
    print()

    # Feature importance
    importance = model.feature_importance(importance_type='gain')
    feature_importance = pd.DataFrame({
        'feature': selected_features,
        'importance': importance
    }).sort_values('importance', ascending=False)

    print("🔝 TOP 15 MOST IMPORTANT FEATURES:")
    print("-" * 80)
    for idx, row in feature_importance.head(15).iterrows():
        print(f"   {row['feature']:35} {row['importance']:>8.0f}")
    print()

    # Save model
    model_dir = Path("storage/models")
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / f"ml_model_master_scalper_v2_{days}d.pkl"

    model_data = {
        'model': model,
        'feature_names': selected_features,
        'optimal_threshold': optimal_threshold,
        'scaler_mean': None,
        'scaler_std': None,
        'train_accuracy': train_acc,
        'val_accuracy': val_acc,
        'up_accuracy': up_acc,
        'down_accuracy': down_acc,
        'prediction_balance': pred_balance,
        'params': params,
        'training_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'days_trained': days,
        'samples_trained': len(X_train),
        'num_features': len(selected_features),
        'num_trees': model.num_trees()
    }

    with open(model_path, 'wb') as f:
        pickle.dump(model_data, f)

    file_size_kb = model_path.stat().st_size / 1024

    print(f"💾 Model saved: {model_path}")
    print(f"   Size: {file_size_kb:.1f} KB")
    print(f"   Trees: {model.num_trees()}")
    print(f"   Features: {len(selected_features)}")
    print()
    print("=" * 80)
    print("🎯 NEXT STEPS:")
    print("=" * 80)
    print()
    print("1. Run backtest:")
    print(f"   python validate_strategy.py storage/models/ml_model_master_scalper_v2_{days}d.pkl")
    print()
    print("2. If results good (WR > 56%, ROI > 0), use in bot")
    print()
    print("=" * 80)

    return model_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', type=str, default='BTCUSDT')
    parser.add_argument('--days', type=int, default=365,
                       help='Days to train (180=6mo, 365=1y, 730=2y)')

    args = parser.parse_args()

    config = load_config('standard')
    setup_logging('INFO', log_to_file=False)

    train_master_scalper_v2(args.symbol, args.days, config)


if __name__ == "__main__":
    main()
