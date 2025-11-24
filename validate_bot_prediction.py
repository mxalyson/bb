"""
Validate that live_bot prediction matches backtest (3.py) prediction
"""
import pandas as pd
import numpy as np
import pickle
from datetime import datetime, timezone
from pathlib import Path
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import load_config
from core.data import DataManager
from core.features import FeatureStore

# Import feature functions from 3.py
exec(open('3.py').read(), globals())

def main():
    """Validate bot prediction"""
    config = load_config()

    # Load model
    model_path = 'storage/models/ml_model_master_scalper_365d.pkl'
    logger.info(f"Loading model: {model_path}")
    with open(model_path, 'rb') as f:
        model_data = pickle.load(f)

    model = model_data['model']
    feature_names = model_data['feature_names']
    scaler_mean = model_data['scaler_mean']
    scaler_std = model_data['scaler_std']

    logger.info(f"Model features: {len(feature_names)}")

    # Detect model version
    v1_features = ['momentum_3', 'momentum_5', 'volume_ratio_3', 'price_position']
    if any(f in feature_names for f in v1_features):
        model_version = "V1"
    else:
        model_version = "Unknown"

    logger.info(f"Model version: {model_version}")

    # Download data (30 days like the bot)
    dm = DataManager(config)
    logger.info("\nDownloading last 30 days of data...")
    df = dm.download_data(
        symbol='BTCUSDT',
        interval='15m',
        days=30
    )

    logger.info(f"Downloaded {len(df)} candles")
    logger.info(f"Last candle: {df.index[-1]} | Close: ${df['close'].iloc[-1]:,.2f}")

    # Build features exactly like bot
    logger.info("\nBuilding features...")
    fs = FeatureStore(config)
    df_features = fs.build_features(df, normalize=False)
    logger.info(f"After build_features: {df_features.shape}")

    # Apply V1 features
    if model_version == "V1":
        logger.info("Applying V1 advanced features...")
        df_features = create_advanced_features(df_features)

    logger.info(f"Features ready: {df_features.shape}")

    # Get last row
    last_row = df_features.iloc[-1:][feature_names]

    # Normalize
    X = (last_row - scaler_mean) / (scaler_std + 1e-8)

    # Predict
    pred = model.predict_proba(X)[0][1]

    # Calculate confidence
    threshold = 0.5
    confidence = abs(pred - threshold) / 0.5 * 100

    if pred > threshold:
        signal = "LONG"
    elif pred < threshold:
        signal = "SHORT"
    else:
        signal = "NEUTRO"

    logger.info(f"\n{'='*60}")
    logger.info(f"🔮 VALIDATION RESULT:")
    logger.info(f"{'='*60}")
    logger.info(f"Candle: {df_features.index[-1]}")
    logger.info(f"Close: ${df['close'].iloc[-1]:,.2f}")
    logger.info(f"Prediction: {pred:.3f}")
    logger.info(f"Signal: {signal}")
    logger.info(f"Confidence: {confidence:.1f}%")
    logger.info(f"{'='*60}")
    logger.info(f"\n✅ Bot prediction should match this value!")

if __name__ == "__main__":
    main()
