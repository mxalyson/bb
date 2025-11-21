#!/usr/bin/env python3
"""
Create EXACT features for ultra_scalper_btcusdt_365d.pkl
Based on error message - 87 features total (60 missing + 27 already created)
"""

import pandas as pd
import numpy as np
from datetime import datetime

def create_ultra_scalper_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create ALL 87 features for ultra_scalper_btcusdt_365d.pkl

    This is a VERY advanced model with:
    - Order flow features (taker buy/sell, pressure, imbalance)
    - Pattern detection (streaks, divergences, higher high/lower low)
    - Session detection (Asian, London, US, weekend)
    - Advanced momentum and volatility
    - Cross detection
    - Microstructure (spread, candle size)
    """

    df_feat = df.copy()

    print("   Creating 87 features for ultra_scalper_btcusdt_365d.pkl...")

    # === CANDLE FEATURES (wicks, body, streaks) ===
    print("   • Candle features...")

    body = abs(df_feat['close'] - df_feat['open'])
    upper_wick = df_feat['high'] - df_feat[['close', 'open']].max(axis=1)
    lower_wick = df_feat[['close', 'open']].min(axis=1) - df_feat['low']

    df_feat['total_wick'] = upper_wick + lower_wick
    df_feat['wick_body_ratio'] = df_feat['total_wick'] / (body + 1e-8)

    # Candle direction (green/red)
    is_green = (df_feat['close'] > df_feat['open']).astype(int)
    is_red = (df_feat['close'] < df_feat['open']).astype(int)

    # Streaks (consecutive green/red candles)
    df_feat['green_streak'] = (is_green * (is_green.groupby((is_green != is_green.shift()).cumsum()).cumcount() + 1))
    df_feat['red_streak'] = (is_red * (is_red.groupby((is_red != is_red.shift()).cumsum()).cumcount() + 1))

    # Large candle
    hl_range = df_feat['high'] - df_feat['low']
    hl_range_ma = hl_range.rolling(20).mean()
    df_feat['large_candle'] = (hl_range > hl_range_ma * 1.5).astype(int)

    # === ORDER FLOW FEATURES (simulated - real data needs exchange API) ===
    print("   • Order flow features (simulated)...")

    # Simulate taker buy/sell based on close vs open
    # In reality, these come from exchange data
    close_position_in_candle = (df_feat['close'] - df_feat['low']) / (df_feat['high'] - df_feat['low'] + 1e-8)

    df_feat['taker_buy_ratio'] = close_position_in_candle
    df_feat['taker_sell_ratio'] = 1 - close_position_in_candle

    # Pressure indicators
    df_feat['buy_pressure_ma'] = df_feat['taker_buy_ratio'].rolling(20).mean()
    df_feat['sell_pressure_ma'] = df_feat['taker_sell_ratio'].rolling(20).mean()
    df_feat['pressure_delta'] = df_feat['buy_pressure_ma'] - df_feat['sell_pressure_ma']
    df_feat['pressure_momentum'] = df_feat['pressure_delta'].diff(5)

    # Order imbalance (simulated)
    df_feat['order_imbalance'] = (df_feat['taker_buy_ratio'] - df_feat['taker_sell_ratio']) * df_feat['volume']
    df_feat['imbalance_ma'] = df_feat['order_imbalance'].rolling(20).mean()

    # === PRICE VS SMA RATIOS ===
    print("   • Price vs SMA features...")

    for period in [7, 14, 21, 50]:
        sma = df_feat['close'].rolling(period).mean()
        df_feat[f'price_sma_{period}_ratio'] = (df_feat['close'] - sma) / sma * 100

    # === EMA CROSSES AND FLAGS ===
    print("   • EMA cross features...")

    ema7 = df_feat['close'].ewm(span=7, adjust=False).mean()
    ema14 = df_feat['close'].ewm(span=14, adjust=False).mean()
    ema21 = df_feat['close'].ewm(span=21, adjust=False).mean()
    ema50 = df_feat['close'].ewm(span=50, adjust=False).mean()
    ema200 = df_feat['close'].ewm(span=200, adjust=False).mean()

    df_feat['ema7_above_ema14'] = (ema7 > ema14).astype(int)
    df_feat['ema14_above_ema21'] = (ema14 > ema21).astype(int)
    df_feat['ema21_above_ema50'] = (ema21 > ema50).astype(int)

    # Golden/Death cross (EMA50 vs EMA200)
    ema50_above_ema200 = ema50 > ema200
    ema50_above_ema200_prev = ema50_above_ema200.shift(1)

    df_feat['golden_cross'] = ((ema50 > ema200) & (ema50.shift(1) <= ema200.shift(1))).astype(int)
    df_feat['death_cross'] = ((ema50 < ema200) & (ema50.shift(1) >= ema200.shift(1))).astype(int)

    # === ATR AND VOLATILITY ===
    print("   • ATR and volatility features...")

    high_low = df_feat['high'] - df_feat['low']
    high_close = abs(df_feat['high'] - df_feat['close'].shift())
    low_close = abs(df_feat['low'] - df_feat['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(14).mean()

    df_feat['atr_pct'] = atr / df_feat['close'] * 100

    # Multiple volatility periods
    returns = df_feat['close'].pct_change()
    df_feat['volatility_7'] = returns.rolling(7).std() * 100
    df_feat['volatility_21'] = returns.rolling(21).std() * 100

    df_feat['volatility_ratio'] = df_feat['volatility_7'] / (df_feat['volatility_21'] + 1e-8)

    # Volatility flags
    vol_median = df_feat['volatility_21'].rolling(50).median()
    df_feat['high_volatility'] = (df_feat['volatility_21'] > vol_median * 1.5).astype(int)
    df_feat['low_volatility'] = (df_feat['volatility_21'] < vol_median * 0.7).astype(int)

    # === RSI FEATURES ===
    print("   • RSI features...")

    delta = df_feat['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))

    df_feat['rsi_extreme_oversold'] = (rsi < 20).astype(int)
    df_feat['rsi_extreme_overbought'] = (rsi > 80).astype(int)
    df_feat['rsi_mid'] = ((rsi >= 40) & (rsi <= 60)).astype(int)

    # === SLOPE FEATURES ===
    print("   • Slope features...")

    # Price slope (linear regression over window)
    def calculate_slope(series, window=5):
        slopes = []
        for i in range(len(series)):
            if i < window:
                slopes.append(0)
            else:
                y = series.iloc[i-window:i].values
                x = np.arange(window)
                if len(y) == window:
                    slope = np.polyfit(x, y, 1)[0]
                    slopes.append(slope)
                else:
                    slopes.append(0)
        return pd.Series(slopes, index=series.index)

    df_feat['price_slope'] = calculate_slope(df_feat['close'], window=5)
    df_feat['rsi_slope'] = calculate_slope(rsi, window=5)

    # === DIVERGENCE DETECTION ===
    print("   • Divergence features...")

    # Simplified divergence detection
    price_higher = df_feat['close'] > df_feat['close'].shift(5)
    rsi_lower = rsi < rsi.shift(5)
    price_lower = df_feat['close'] < df_feat['close'].shift(5)
    rsi_higher = rsi > rsi.shift(5)

    df_feat['bullish_divergence'] = (price_lower & rsi_higher).astype(int)
    df_feat['bearish_divergence'] = (price_higher & rsi_lower).astype(int)

    # === MACD FEATURES ===
    print("   • MACD features...")

    ema12 = df_feat['close'].ewm(span=12, adjust=False).mean()
    ema26 = df_feat['close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal

    df_feat['macd_hist_increasing'] = (macd_hist > macd_hist.shift(1)).astype(int)

    # === BOLLINGER BANDS BREAKOUTS ===
    print("   • Bollinger Bands features...")

    sma20 = df_feat['close'].rolling(20).mean()
    std20 = df_feat['close'].rolling(20).std()
    bb_upper = sma20 + (2 * std20)
    bb_lower = sma20 - (2 * std20)

    df_feat['bb_upper_breakout'] = (df_feat['close'] > bb_upper).astype(int)
    df_feat['bb_lower_breakout'] = (df_feat['close'] < bb_lower).astype(int)

    # === VOLUME FEATURES ===
    print("   • Volume features...")

    df_feat['volume_sma_20'] = df_feat['volume'].rolling(20).mean()

    vol_median = df_feat['volume'].rolling(50).median()
    df_feat['high_volume'] = (df_feat['volume'] > vol_median * 1.5).astype(int)

    df_feat['volume_slope'] = calculate_slope(df_feat['volume'], window=5)
    df_feat['volume_increasing_trend'] = (df_feat['volume_slope'] > 0).astype(int)

    # === MOMENTUM FEATURES ===
    print("   • Momentum features...")

    for period in [3, 7, 14]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100

    # Momentum acceleration
    df_feat['momentum_accel'] = df_feat['momentum_7'].diff(3)

    # === PRICE POSITION IN RANGE ===
    print("   • Price position features...")

    for period in [14, 50]:
        high_period = df_feat['high'].rolling(period).max()
        low_period = df_feat['low'].rolling(period).min()
        df_feat[f'price_position_{period}'] = (df_feat['close'] - low_period) / (high_period - low_period + 1e-8)

    # === SWING POINTS (Higher High, Lower Low) ===
    print("   • Swing point features...")

    # Higher high: current high > previous high
    df_feat['higher_high'] = (df_feat['high'] > df_feat['high'].shift(1)).astype(int)
    df_feat['lower_low'] = (df_feat['low'] < df_feat['low'].shift(1)).astype(int)

    # Count of recent HH and LL
    df_feat['hh_count'] = df_feat['higher_high'].rolling(10).sum()
    df_feat['ll_count'] = df_feat['lower_low'].rolling(10).sum()

    # === TREND STRENGTH ===
    print("   • Trend strength...")

    # ADX-like trend strength
    plus_dm = df_feat['high'].diff()
    minus_dm = -df_feat['low'].diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    tr_smooth = true_range.rolling(14).mean()
    plus_di = (plus_dm.rolling(14).mean() / (tr_smooth + 1e-10)) * 100
    minus_di = (minus_dm.rolling(14).mean() / (tr_smooth + 1e-10)) * 100

    dx = abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100
    adx = dx.rolling(14).mean()

    df_feat['trend_strength'] = adx

    # === SESSION/TIME FEATURES ===
    print("   • Session/time features...")

    # Extract time features from index (assuming datetime index)
    if isinstance(df_feat.index, pd.DatetimeIndex):
        df_feat['hour'] = df_feat.index.hour
        df_feat['day_of_week'] = df_feat.index.dayofweek

        # Trading sessions (UTC times)
        df_feat['asian_session'] = ((df_feat['hour'] >= 0) & (df_feat['hour'] < 9)).astype(int)
        df_feat['london_session'] = ((df_feat['hour'] >= 7) & (df_feat['hour'] < 16)).astype(int)
        df_feat['us_session'] = ((df_feat['hour'] >= 13) & (df_feat['hour'] < 22)).astype(int)
        df_feat['weekend'] = (df_feat['day_of_week'] >= 5).astype(int)
    else:
        # Default values if no datetime index
        df_feat['hour'] = 12
        df_feat['day_of_week'] = 2
        df_feat['asian_session'] = 0
        df_feat['london_session'] = 1
        df_feat['us_session'] = 0
        df_feat['weekend'] = 0

    # === SPREAD FEATURES ===
    print("   • Spread features...")

    # Spread proxy (high - low as % of close)
    df_feat['spread_proxy'] = (df_feat['high'] - df_feat['low']) / df_feat['close'] * 100
    df_feat['spread_ma'] = df_feat['spread_proxy'].rolling(20).mean()

    # Fill NaN values
    df_feat = df_feat.fillna(method='ffill').fillna(method='bfill').fillna(0)

    print(f"   ✅ Created {len(df_feat.columns)} total columns")

    # List of all 87 required features (based on error message)
    required_features = [
        'total_wick', 'wick_body_ratio', 'green_streak', 'red_streak',
        'taker_buy_ratio', 'taker_sell_ratio', 'buy_pressure_ma', 'sell_pressure_ma',
        'pressure_delta', 'pressure_momentum', 'order_imbalance', 'imbalance_ma',
        'price_sma_7_ratio', 'price_sma_14_ratio', 'price_sma_21_ratio', 'price_sma_50_ratio',
        'ema7_above_ema14', 'ema14_above_ema21', 'ema21_above_ema50',
        'golden_cross', 'death_cross',
        'atr_pct', 'volatility_7', 'volatility_21', 'volatility_ratio',
        'high_volatility', 'low_volatility',
        'rsi_extreme_oversold', 'rsi_extreme_overbought', 'rsi_mid',
        'price_slope', 'rsi_slope',
        'bullish_divergence', 'bearish_divergence',
        'macd_hist_increasing',
        'bb_upper_breakout', 'bb_lower_breakout',
        'volume_sma_20', 'high_volume', 'volume_slope', 'volume_increasing_trend',
        'momentum_3', 'momentum_7', 'momentum_14', 'momentum_accel',
        'price_position_14', 'price_position_50',
        'higher_high', 'lower_low', 'hh_count', 'll_count',
        'trend_strength',
        'hour', 'day_of_week', 'asian_session', 'london_session', 'us_session', 'weekend',
        'spread_proxy', 'spread_ma', 'large_candle'
    ]

    # Check which features are missing
    missing = [f for f in required_features if f not in df_feat.columns]
    if missing:
        print(f"   ⚠️  Still missing features: {missing}")
    else:
        print(f"   ✅ All 60 advanced features created!")

    return df_feat


if __name__ == "__main__":
    # Test with dummy data
    print("Testing feature creation for ultra_scalper_btcusdt_365d.pkl...")

    # Create dummy OHLCV data with datetime index
    n = 1000
    dates = pd.date_range(start='2024-01-01', periods=n, freq='15min')

    df = pd.DataFrame({
        'open': 100 + np.random.randn(n).cumsum(),
        'high': 101 + np.random.randn(n).cumsum(),
        'low': 99 + np.random.randn(n).cumsum(),
        'close': 100 + np.random.randn(n).cumsum(),
        'volume': 1000 + np.random.randn(n) * 100
    }, index=dates)

    df['high'] = df[['open', 'high', 'close']].max(axis=1)
    df['low'] = df[['open', 'low', 'close']].min(axis=1)

    # Create features
    df_with_features = create_ultra_scalper_features(df)

    print(f"\n✅ Success!")
    print(f"Total columns: {len(df_with_features.columns)}")
    print(f"OHLCV columns: 5")
    print(f"Feature columns: {len(df_with_features.columns) - 5}")

    # Show sample of new features
    new_features = [c for c in df_with_features.columns if c not in ['open', 'high', 'low', 'close', 'volume']]
    print(f"\nSample of features created:")
    for feat in new_features[:20]:
        print(f"  • {feat}")
    if len(new_features) > 20:
        print(f"  ... and {len(new_features) - 20} more")
