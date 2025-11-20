#!/usr/bin/env python3
"""
Create EXACT features for ml_model_master_scalper_365d.pkl
Based on binary analysis - 60 features total
"""

import pandas as pd
import numpy as np

def create_exact_model_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create the EXACT 60 features that ml_model_master_scalper_365d.pkl expects.

    Features identified via binary analysis:
    - 5 momentum indicators (periods: 3, 5, 8, 13, 21)
    - 6 volume ratios (periods: 3, 5, 8, 13, 21 + general)
    - 4 returns (periods: 1, 5, 10, 20)
    - 3 volatility indicators
    - 5 price features
    - 5 Bollinger Bands
    - 4 RSI features
    - 2 ATR features
    - 4 MACD features
    - 2 ADX features
    - 2 trend features
    - 2 swing high/low
    - 2 FVG (Fair Value Gaps)
    - 6 candle features
    - 3 other (VWAP, resistance/support distance)
    """

    df_feat = df.copy()

    print("   Creating 60 features for ml_model_master_scalper_365d.pkl...")

    # === 1. MOMENTUM (5 features) ===
    print("   • Momentum features (5)...")
    for period in [3, 5, 8, 13, 21]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100

    # === 2. VOLUME RATIOS (6 features) ===
    print("   • Volume features (8)...")
    for period in [3, 5, 8, 13, 21]:
        volume_ma_period = df_feat['volume'].rolling(period).mean()
        df_feat[f'volume_ratio_{period}'] = df_feat['volume'] / (volume_ma_period + 1e-10)

    # General volume features
    df_feat['volume_ratio'] = df_feat['volume'] / df_feat['volume'].rolling(20).mean()
    df_feat['volume_ma'] = df_feat['volume'].rolling(20).mean()
    df_feat['volume_std'] = df_feat['volume'].rolling(20).std()
    df_feat['volume_momentum'] = df_feat['volume'].pct_change(5)

    # === 3. RETURNS (4 features) ===
    print("   • Returns (4)...")
    for period in [1, 5, 10, 20]:
        df_feat[f'return_{period}'] = df_feat['close'].pct_change(period) * 100

    # === 4. VOLATILITY (3 features) ===
    print("   • Volatility (3)...")
    returns = df_feat['close'].pct_change()
    df_feat['volatility_5'] = returns.rolling(5).std() * 100
    df_feat['volatility_20'] = returns.rolling(20).std() * 100

    # ATR for volatility regime
    high_low = df_feat['high'] - df_feat['low']
    high_close = np.abs(df_feat['high'] - df_feat['close'].shift())
    low_close = np.abs(df_feat['low'] - df_feat['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    atr = true_range.rolling(14).mean()

    df_feat['volatility_regime'] = atr / atr.rolling(50).mean()

    # === 5. PRICE FEATURES (5 features) ===
    print("   • Price features (5)...")
    # Price position in recent range
    high_20 = df_feat['high'].rolling(20).max()
    low_20 = df_feat['low'].rolling(20).min()
    df_feat['price_position'] = (df_feat['close'] - low_20) / (high_20 - low_20 + 1e-10)

    # Price acceleration
    df_feat['price_acceleration'] = df_feat['close'].diff(2) - df_feat['close'].diff(1)

    # === 6. EMAs and relationships (5 features) ===
    print("   • EMA features (5)...")
    ema21 = df_feat['close'].ewm(span=21, adjust=False).mean()
    ema50 = df_feat['close'].ewm(span=50, adjust=False).mean()
    ema200 = df_feat['close'].ewm(span=200, adjust=False).mean()

    df_feat['price_vs_ema21'] = (df_feat['close'] - ema21) / ema21 * 100
    df_feat['price_vs_ema50'] = (df_feat['close'] - ema50) / ema50 * 100
    df_feat['price_vs_ema200'] = (df_feat['close'] - ema200) / ema200 * 100
    df_feat['ema21_vs_ema50'] = (ema21 - ema50) / ema50 * 100
    df_feat['ema50_vs_ema200'] = (ema50 - ema200) / ema200 * 100

    # === 7. BOLLINGER BANDS (5 features) ===
    print("   • Bollinger Bands (5)...")
    sma_20 = df_feat['close'].rolling(20).mean()
    std_20 = df_feat['close'].rolling(20).std()

    df_feat['bb_middle'] = sma_20
    df_feat['bb_upper'] = sma_20 + (2 * std_20)
    df_feat['bb_lower'] = sma_20 - (2 * std_20)
    df_feat['bb_width'] = (df_feat['bb_upper'] - df_feat['bb_lower']) / df_feat['bb_middle'] * 100
    df_feat['bb_position'] = (df_feat['close'] - df_feat['bb_lower']) / (df_feat['bb_upper'] - df_feat['bb_lower'] + 1e-10)

    # === 8. RSI (4 features) ===
    print("   • RSI features (4)...")
    delta = df_feat['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))

    df_feat['rsi_ma'] = rsi.rolling(14).mean()
    df_feat['rsi_std'] = rsi.rolling(14).std()
    df_feat['rsi_overbought'] = (rsi > 70).astype(int)
    df_feat['rsi_oversold'] = (rsi < 30).astype(int)

    # === 9. ATR (2 features) ===
    print("   • ATR features (2)...")
    df_feat['atr_normalized'] = atr / df_feat['close'] * 100
    df_feat['atr_ratio'] = atr / df_feat['close']

    # === 10. MACD (4 features) ===
    print("   • MACD features (4)...")
    ema12 = df_feat['close'].ewm(span=12, adjust=False).mean()
    ema26 = df_feat['close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal

    df_feat['macd_signal'] = signal
    df_feat['macd_hist'] = hist
    df_feat['macd_hist_change'] = hist.diff()
    df_feat['macd_positive'] = (macd > 0).astype(int)

    # === 11. ADX (2 features) ===
    print("   • ADX features (2)...")
    plus_dm = df_feat['high'].diff()
    minus_dm = -df_feat['low'].diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    tr_smooth = true_range.rolling(14).mean()
    plus_di = (plus_dm.rolling(14).mean() / (tr_smooth + 1e-10)) * 100
    minus_di = (minus_dm.rolling(14).mean() / (tr_smooth + 1e-10)) * 100

    dx = np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100
    adx = dx.rolling(14).mean()

    df_feat['adx_strong'] = (adx > 25).astype(int)
    df_feat['adx_very_strong'] = (adx > 50).astype(int)

    # === 12. TREND (2 features) ===
    print("   • Trend features (2)...")
    df_feat['trend_strength'] = (ema50 - ema200) / ema200 * 100
    df_feat['trend_numeric'] = np.where(ema21 > ema50, 1, np.where(ema21 < ema50, -1, 0))

    # === 13. SWING HIGH/LOW (2 features) ===
    print("   • Swing features (2)...")
    df_feat['swing_high'] = df_feat['high'].rolling(5, center=True).apply(
        lambda x: 1.0 if len(x) == 5 and x.iloc[2] == max(x) else 0.0, raw=False
    ).fillna(0)
    df_feat['swing_low'] = df_feat['low'].rolling(5, center=True).apply(
        lambda x: 1.0 if len(x) == 5 and x.iloc[2] == min(x) else 0.0, raw=False
    ).fillna(0)

    # === 14. FAIR VALUE GAPS (2 features) ===
    print("   • FVG features (2)...")
    df_feat['fvg_bullish'] = (df_feat['low'] > df_feat['high'].shift(2)).astype(int)
    df_feat['fvg_bearish'] = (df_feat['high'] < df_feat['low'].shift(2)).astype(int)

    # === 15. CANDLE FEATURES (6 features) ===
    print("   • Candle features (6)...")
    body = np.abs(df_feat['close'] - df_feat['open'])
    upper_shadow = df_feat['high'] - df_feat[['close', 'open']].max(axis=1)
    lower_shadow = df_feat[['close', 'open']].min(axis=1) - df_feat['low']

    df_feat['body_size'] = body / df_feat['close'] * 100
    df_feat['upper_wick'] = upper_shadow / (body + 1e-8)
    df_feat['lower_wick'] = lower_shadow / (body + 1e-8)
    df_feat['is_green'] = (df_feat['close'] > df_feat['open']).astype(int)
    df_feat['hl_range'] = df_feat['high'] - df_feat['low']
    df_feat['hl_range_ma'] = df_feat['hl_range'].rolling(20).mean()

    # === 16. OTHER (3 features) ===
    print("   • Other features (3)...")
    # VWAP
    typical_price = (df_feat['high'] + df_feat['low'] + df_feat['close']) / 3
    vwap = (typical_price * df_feat['volume']).rolling(20).sum() / df_feat['volume'].rolling(20).sum()
    df_feat['close_vs_vwap'] = (df_feat['close'] - vwap) / vwap * 100

    # Support/Resistance (simplified - based on swing points)
    resistance = df_feat['high'].rolling(50).max()
    support = df_feat['low'].rolling(50).min()

    df_feat['dist_to_resistance_pct'] = (resistance - df_feat['close']) / df_feat['close'] * 100
    df_feat['dist_to_support_pct'] = (df_feat['close'] - support) / df_feat['close'] * 100

    # Fill NaN values
    df_feat = df_feat.fillna(method='ffill').fillna(method='bfill').fillna(0)

    print(f"   ✅ Created {len(df_feat.columns)} total columns")

    # Verify we have all 60 features
    required_features = [
        'adx_strong', 'adx_very_strong', 'atr_normalized', 'atr_ratio',
        'bb_lower', 'bb_middle', 'bb_position', 'bb_upper', 'bb_width',
        'body_size', 'close_vs_vwap', 'dist_to_resistance_pct', 'dist_to_support_pct',
        'ema21_vs_ema50', 'ema50_vs_ema200', 'fvg_bearish', 'fvg_bullish',
        'hl_range', 'hl_range_ma', 'is_green', 'lower_wick',
        'macd_hist', 'macd_hist_change', 'macd_positive', 'macd_signal',
        'momentum_13', 'momentum_21', 'momentum_3', 'momentum_5', 'momentum_8',
        'price_acceleration', 'price_position', 'price_vs_ema200', 'price_vs_ema21', 'price_vs_ema50',
        'return_1', 'return_10', 'return_20', 'return_5',
        'rsi_ma', 'rsi_overbought', 'rsi_oversold', 'rsi_std',
        'swing_high', 'swing_low', 'trend_numeric', 'trend_strength', 'upper_wick',
        'volatility_20', 'volatility_5', 'volatility_regime',
        'volume_ma', 'volume_momentum', 'volume_ratio',
        'volume_ratio_13', 'volume_ratio_21', 'volume_ratio_3', 'volume_ratio_5', 'volume_ratio_8',
        'volume_std'
    ]

    missing = [f for f in required_features if f not in df_feat.columns]
    if missing:
        print(f"   ⚠️  Missing features: {missing}")
    else:
        print(f"   ✅ All 60 required features present!")

    return df_feat


if __name__ == "__main__":
    # Test with dummy data
    import sys

    print("Testing feature creation...")

    # Create dummy OHLCV data
    n = 1000
    df = pd.DataFrame({
        'open': 100 + np.random.randn(n).cumsum(),
        'high': 101 + np.random.randn(n).cumsum(),
        'low': 99 + np.random.randn(n).cumsum(),
        'close': 100 + np.random.randn(n).cumsum(),
        'volume': 1000 + np.random.randn(n) * 100
    })

    df['high'] = df[['open', 'high', 'close']].max(axis=1)
    df['low'] = df[['open', 'low', 'close']].min(axis=1)

    # Create features
    df_with_features = create_exact_model_features(df)

    print(f"\nTotal columns: {len(df_with_features.columns)}")
    print(f"OHLCV columns: 5")
    print(f"Feature columns: {len(df_with_features.columns) - 5}")
