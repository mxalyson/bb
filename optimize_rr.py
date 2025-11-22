"""
🎯 OTIMIZADOR DE RISK:REWARD
Testa diferentes combinações de SL/TP para encontrar a melhor configuração
Baseado no 1.py, mas com logs limpos e foco em R:R
"""

import sys
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')
sys.path.append(str(Path(__file__).parent))

import pandas as pd
import numpy as np
from typing import Dict, List
import logging
import argparse
import pickle
from datetime import datetime

from core.utils import load_config, setup_logging
from core.bybit_rest import BybitRESTClient
from core.data import DataManager
from core.features import FeatureStore
import sys

logger = None


# ============================================================================
# UNIVERSAL MODEL LOADING - Works with ANY pickle model
# ============================================================================

class ModelWrapper:
    """Generic wrapper for models saved with custom classes."""
    def __init__(self, model=None, feature_names=None, **kwargs):
        self.model = model
        self.feature_names = feature_names
        self.__dict__.update(kwargs)


# Register ModelWrapper in __main__ module so pickle can find it
sys.modules['__main__'].ModelWrapper = ModelWrapper


class UniversalUnpickler(pickle.Unpickler):
    """Custom unpickler that can handle missing classes."""
    def find_class(self, module, name):
        # Handle ModelWrapper from any module
        if name == 'ModelWrapper':
            return ModelWrapper

        # Handle common missing classes
        if name in ['StrategyValidator', 'TradingBot', 'ModelHandler']:
            return ModelWrapper

        # Try normal loading first
        try:
            return super().find_class(module, name)
        except (AttributeError, ModuleNotFoundError) as e:
            # If class not found, return ModelWrapper as fallback
            print(f"   ⚠️  Class {module}.{name} not found, using ModelWrapper")
            return ModelWrapper


# ============================================================================
# ULTRA SCALPER FEATURES - Copied from 1.py for compatibility
# ============================================================================

def create_ultra_scalper_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create ALL 87 features for ultra_scalper model.

    Advanced features including:
    - Order flow (taker buy/sell, pressure, imbalance)
    - Pattern detection (streaks, divergences, higher high/lower low)
    - Session detection (Asian, London, US, weekend)
    - Advanced momentum and volatility
    - Cross detection, microstructure
    """
    df_feat = df.copy()

    # === BASIC RETURNS (for compatibility) ===
    df_feat['returns'] = df_feat['close'].pct_change()
    df_feat['returns_5'] = df_feat['close'].pct_change(5)
    df_feat['returns_10'] = df_feat['close'].pct_change(10)

    # === CANDLE FEATURES ===
    body = abs(df_feat['close'] - df_feat['open'])
    upper_wick = df_feat['high'] - df_feat[['close', 'open']].max(axis=1)
    lower_wick = df_feat[['close', 'open']].min(axis=1) - df_feat['low']

    df_feat['total_wick'] = upper_wick + lower_wick
    df_feat['wick_body_ratio'] = df_feat['total_wick'] / (body + 1e-8)

    # Additional candle features for compatibility
    df_feat['body_pct'] = body / df_feat['close'] * 100
    df_feat['upper_wick_pct'] = upper_wick / df_feat['close'] * 100
    df_feat['lower_wick_pct'] = lower_wick / df_feat['close'] * 100

    is_green = (df_feat['close'] > df_feat['open']).astype(int)
    is_red = (df_feat['close'] < df_feat['open']).astype(int)

    df_feat['green_streak'] = (is_green * (is_green.groupby((is_green != is_green.shift()).cumsum()).cumcount() + 1))
    df_feat['red_streak'] = (is_red * (is_red.groupby((is_red != is_red.shift()).cumsum()).cumcount() + 1))

    hl_range = df_feat['high'] - df_feat['low']
    hl_range_ma = hl_range.rolling(20).mean()
    df_feat['large_candle'] = (hl_range > hl_range_ma * 1.5).astype(int)

    # === ORDER FLOW (simulated) ===
    close_position_in_candle = (df_feat['close'] - df_feat['low']) / (df_feat['high'] - df_feat['low'] + 1e-8)

    df_feat['taker_buy_ratio'] = close_position_in_candle
    df_feat['taker_sell_ratio'] = 1 - close_position_in_candle

    df_feat['buy_pressure_ma'] = df_feat['taker_buy_ratio'].rolling(20).mean()
    df_feat['sell_pressure_ma'] = df_feat['taker_sell_ratio'].rolling(20).mean()
    df_feat['pressure_delta'] = df_feat['buy_pressure_ma'] - df_feat['sell_pressure_ma']
    df_feat['pressure_momentum'] = df_feat['pressure_delta'].diff(5)

    # Aliases for compatibility
    df_feat['buy_pressure'] = df_feat['buy_pressure_ma']
    df_feat['sell_pressure'] = df_feat['sell_pressure_ma']

    df_feat['order_imbalance'] = (df_feat['taker_buy_ratio'] - df_feat['taker_sell_ratio']) * df_feat['volume']
    df_feat['imbalance_ma'] = df_feat['order_imbalance'].rolling(20).mean()

    # === PRICE VS SMA RATIOS ===
    # Create and store SMA features
    df_feat['sma_7'] = df_feat['close'].rolling(7).mean()
    df_feat['sma_14'] = df_feat['close'].rolling(14).mean()
    df_feat['sma_21'] = df_feat['close'].rolling(21).mean()
    df_feat['sma_50'] = df_feat['close'].rolling(50).mean()
    df_feat['sma_100'] = df_feat['close'].rolling(100).mean()

    sma7 = df_feat['sma_7']
    sma14 = df_feat['sma_14']
    sma21 = df_feat['sma_21']
    sma50 = df_feat['sma_50']

    for period in [7, 14, 21, 50]:
        sma = df_feat['close'].rolling(period).mean()
        df_feat[f'price_sma_{period}_ratio'] = (df_feat['close'] - sma) / sma * 100

    # Additional price vs MA features for compatibility
    df_feat['price_vs_sma7'] = (df_feat['close'] - sma7) / sma7 * 100
    df_feat['price_vs_sma21'] = (df_feat['close'] - sma21) / sma21 * 100

    # === EMA CROSSES ===
    # Create and store EMA features
    df_feat['ema_7'] = df_feat['close'].ewm(span=7, adjust=False).mean()
    df_feat['ema_14'] = df_feat['close'].ewm(span=14, adjust=False).mean()
    df_feat['ema_21'] = df_feat['close'].ewm(span=21, adjust=False).mean()
    df_feat['ema_50'] = df_feat['close'].ewm(span=50, adjust=False).mean()
    df_feat['ema_100'] = df_feat['close'].ewm(span=100, adjust=False).mean()

    ema7 = df_feat['ema_7']
    ema14 = df_feat['ema_14']
    ema21 = df_feat['ema_21']
    ema50 = df_feat['ema_50']
    ema200 = df_feat['close'].ewm(span=200, adjust=False).mean()

    df_feat['ema7_above_ema14'] = (ema7 > ema14).astype(int)
    df_feat['ema14_above_ema21'] = (ema14 > ema21).astype(int)
    df_feat['ema21_above_ema50'] = (ema21 > ema50).astype(int)

    # Additional EMA/SMA crosses for compatibility
    df_feat['sma7_above_sma21'] = (sma7 > sma21).astype(int)
    df_feat['ema7_above_ema21'] = (ema7 > ema21).astype(int)
    df_feat['price_vs_ema14'] = (df_feat['close'] - ema14) / ema14 * 100

    df_feat['golden_cross'] = ((ema50 > ema200) & (ema50.shift(1) <= ema200.shift(1))).astype(int)
    df_feat['death_cross'] = ((ema50 < ema200) & (ema50.shift(1) >= ema200.shift(1))).astype(int)

    # === ATR AND VOLATILITY ===
    high_low = df_feat['high'] - df_feat['low']
    high_close = abs(df_feat['high'] - df_feat['close'].shift())
    low_close = abs(df_feat['low'] - df_feat['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(14).mean()

    df_feat['atr_pct'] = atr / df_feat['close'] * 100

    returns = df_feat['close'].pct_change()
    df_feat['volatility_7'] = returns.rolling(7).std() * 100
    df_feat['volatility_21'] = returns.rolling(21).std() * 100

    df_feat['volatility_ratio'] = df_feat['volatility_7'] / (df_feat['volatility_21'] + 1e-8)

    vol_median = df_feat['volatility_21'].rolling(50).median()
    df_feat['high_volatility'] = (df_feat['volatility_21'] > vol_median * 1.5).astype(int)
    df_feat['low_volatility'] = (df_feat['volatility_21'] < vol_median * 0.7).astype(int)

    # === RSI FEATURES ===
    delta = df_feat['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))

    df_feat['rsi_extreme_oversold'] = (rsi < 20).astype(int)
    df_feat['rsi_extreme_overbought'] = (rsi > 80).astype(int)
    df_feat['rsi_mid'] = ((rsi >= 40) & (rsi <= 60)).astype(int)
    df_feat['rsi_neutral'] = ((rsi >= 40) & (rsi <= 60)).astype(int)  # Alias for compatibility

    # === SLOPE FEATURES ===
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
    price_higher = df_feat['close'] > df_feat['close'].shift(5)
    rsi_lower = rsi < rsi.shift(5)
    price_lower = df_feat['close'] < df_feat['close'].shift(5)
    rsi_higher = rsi > rsi.shift(5)

    df_feat['bullish_divergence'] = (price_lower & rsi_higher).astype(int)
    df_feat['bearish_divergence'] = (price_higher & rsi_lower).astype(int)

    # === MACD FEATURES ===
    ema12 = df_feat['close'].ewm(span=12, adjust=False).mean()
    ema26 = df_feat['close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal

    df_feat['macd_hist_increasing'] = (macd_hist > macd_hist.shift(1)).astype(int)

    # === BOLLINGER BANDS ===
    sma20 = df_feat['close'].rolling(20).mean()
    std20 = df_feat['close'].rolling(20).std()
    bb_upper = sma20 + (2 * std20)
    bb_lower = sma20 - (2 * std20)

    df_feat['bb_upper_breakout'] = (df_feat['close'] > bb_upper).astype(int)
    df_feat['bb_lower_breakout'] = (df_feat['close'] < bb_lower).astype(int)

    # === VOLUME FEATURES ===
    df_feat['volume_sma_20'] = df_feat['volume'].rolling(20).mean()

    vol_median = df_feat['volume'].rolling(50).median()
    df_feat['high_volume'] = (df_feat['volume'] > vol_median * 1.5).astype(int)

    df_feat['volume_slope'] = calculate_slope(df_feat['volume'], window=5)
    df_feat['volume_increasing_trend'] = (df_feat['volume_slope'] > 0).astype(int)

    # === MOMENTUM FEATURES ===
    for period in [3, 5, 7, 8, 13, 14, 21]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100

    df_feat['momentum_accel'] = df_feat['momentum_7'].diff(3)

    # === PRICE POSITION ===
    for period in [14, 50]:
        high_period = df_feat['high'].rolling(period).max()
        low_period = df_feat['low'].rolling(period).min()
        df_feat[f'price_position_{period}'] = (df_feat['close'] - low_period) / (high_period - low_period + 1e-8)

    # === SWING POINTS ===
    df_feat['higher_high'] = (df_feat['high'] > df_feat['high'].shift(1)).astype(int)
    df_feat['lower_low'] = (df_feat['low'] < df_feat['low'].shift(1)).astype(int)

    df_feat['hh_count'] = df_feat['higher_high'].rolling(10).sum()
    df_feat['ll_count'] = df_feat['lower_low'].rolling(10).sum()

    # === TREND STRENGTH ===
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
    if isinstance(df_feat.index, pd.DatetimeIndex):
        df_feat['hour'] = df_feat.index.hour
        df_feat['day_of_week'] = df_feat.index.dayofweek

        df_feat['asian_session'] = ((df_feat['hour'] >= 0) & (df_feat['hour'] < 9)).astype(int)
        df_feat['london_session'] = ((df_feat['hour'] >= 7) & (df_feat['hour'] < 16)).astype(int)
        df_feat['us_session'] = ((df_feat['hour'] >= 13) & (df_feat['hour'] < 22)).astype(int)
        df_feat['weekend'] = (df_feat['day_of_week'] >= 5).astype(int)
    else:
        df_feat['hour'] = 12
        df_feat['day_of_week'] = 2
        df_feat['asian_session'] = 0
        df_feat['london_session'] = 1
        df_feat['us_session'] = 0
        df_feat['weekend'] = 0

    # === SPREAD FEATURES ===
    df_feat['spread_proxy'] = (df_feat['high'] - df_feat['low']) / df_feat['close'] * 100
    df_feat['spread_ma'] = df_feat['spread_proxy'].rolling(20).mean()

    # Fill NaN
    df_feat = df_feat.fillna(method='ffill').fillna(method='bfill').fillna(0)

    return df_feat


class RROptimizer:
    """Otimiza Risk:Reward testando diferentes SL/TP."""

    def __init__(self, config: dict, model_path: str, min_confidence: float = 0.0):
        self.config = config
        self.min_confidence = min_confidence

        # Load model with universal unpickler (always use custom to avoid class issues)
        with open(model_path, 'rb') as f:
            self.model_data = UniversalUnpickler(f).load()

        # Extract model and features
        if hasattr(self.model_data, 'feature_columns'):
            self.feature_names = self.model_data.feature_columns
            self.model = self.model_data
        elif isinstance(self.model_data, dict):
            self.model = self.model_data.get('model')
            self.feature_names = self.model_data.get('feature_names')
        else:
            self.model = self.model_data
            self.feature_names = getattr(self.model_data, 'feature_names', None)

        self.initial_capital = config.get('initial_capital', 300)
        self.risk_per_trade = config.get('risk_per_trade_pct', 0.75) / 100
        self.trading_fee = 0.00055  # Bybit taker 0.055%

    def test_configuration(self, df: pd.DataFrame, sl_mult: float, tp_mult: float,
                          use_partial_tp: bool = False) -> Dict:
        """Test uma configuração específica de SL/TP."""

        # Get ML predictions
        X = df[self.feature_names].fillna(0)

        # Predict using different model types
        try:
            if hasattr(self.model, 'predict'):
                # Standard sklearn-like model
                ml_probs = self.model.predict(X)
            elif hasattr(self.model, 'models_list'):
                # Ensemble model (like ultra scalper)
                predictions = []
                for model, weight in zip(self.model.models_list, self.model.model_weights):
                    pred = model.predict(X)
                    predictions.append(pred * weight)
                ml_probs = np.sum(predictions, axis=0)
            else:
                # Fallback: neutral predictions
                ml_probs = np.array([0.5] * len(X))
        except Exception:
            # Silent fallback to neutral predictions
            ml_probs = np.array([0.5] * len(X))

        df['ml_prob_up'] = ml_probs
        df['ml_confidence'] = np.abs(ml_probs - 0.5) * 2

        # Generate signals with confidence filter
        df['signal'] = 0
        mask_long = (df['ml_prob_up'] > 0.5) & (df['ml_confidence'] >= self.min_confidence)
        mask_short = (df['ml_prob_up'] < 0.5) & (df['ml_confidence'] >= self.min_confidence)

        df.loc[mask_long, 'signal'] = 1
        df.loc[mask_short, 'signal'] = -1

        # Simulate trades
        trades = self._simulate(df, sl_mult, tp_mult, use_partial_tp)

        # Calculate stats
        stats = self._calculate_stats(trades, sl_mult, tp_mult, use_partial_tp)

        return stats

    def _simulate(self, df: pd.DataFrame, sl_mult: float, tp_mult: float,
                  use_partial_tp: bool) -> List[Dict]:
        """Simula trades com configuração específica."""
        trades = []
        position = None
        capital = self.initial_capital
        cooldown = 0

        for i in range(len(df)):
            current = df.iloc[i]

            if cooldown > 0:
                cooldown -= 1

            # Check exit
            if position:
                exit_result = self._check_exit(position, current, i)
                if exit_result:
                    reason, exit_price, close_pct = exit_result
                    trade = self._close_trade(position, current, reason, exit_price, close_pct)
                    trades.append(trade)
                    capital += trade['pnl_amount']

                    # Se é TP parcial e ainda tem posição aberta
                    if close_pct < 1.0:
                        position['size'] *= (1 - close_pct)  # Reduz tamanho
                        position['partial_closed'] = True
                    else:
                        position = None
                        cooldown = 4

            # Check entry
            if not position and current['signal'] != 0 and cooldown == 0 and i < len(df) - 20:
                position = self._open_trade(current, capital, i, sl_mult, tp_mult, use_partial_tp)

        # Close final position
        if position:
            trade = self._close_trade(position, df.iloc[-1], 'end_of_data', df.iloc[-1]['close'], 1.0)
            trades.append(trade)

        return trades

    def _open_trade(self, current, capital, idx, sl_mult, tp_mult, use_partial_tp):
        """Abre nova posição."""
        direction = 'long' if current['signal'] == 1 else 'short'
        price = current['close']
        atr = current.get('atr', price * 0.01)

        # Calculate SL and TPs
        if direction == 'long':
            sl = price - (atr * sl_mult)
            tp1 = price + (atr * tp_mult)
            tp2 = price + (atr * tp_mult * 1.5) if use_partial_tp else None
        else:
            sl = price + (atr * sl_mult)
            tp1 = price - (atr * tp_mult)
            tp2 = price - (atr * tp_mult * 1.5) if use_partial_tp else None

        # Calculate position size
        sl_dist = abs((sl - price) / price)
        risk_amt = capital * self.risk_per_trade
        size = risk_amt / sl_dist if sl_dist > 0 else capital * 0.1
        size = min(size, capital * 0.95)

        # Apply Bybit minimums
        min_qty_btc = 0.001
        qty_step = 0.001
        qty_btc = size / price
        qty_btc = max(min_qty_btc, qty_btc)
        qty_btc = round(qty_btc / qty_step) * qty_step
        size = qty_btc * price
        size = min(size, capital * 0.95)

        return {
            'entry_idx': idx,
            'entry_time': current.name,
            'entry_price': price,
            'direction': direction,
            'size': size,
            'stop_loss': sl,
            'tp1': tp1,
            'tp2': tp2,
            'ml_confidence': current['ml_confidence'],
            'partial_closed': False
        }

    def _check_exit(self, position, current, idx):
        """Verifica se deve sair da posição."""
        high = current['high']
        low = current['low']
        direction = position['direction']

        if direction == 'long':
            # Check SL
            if low <= position['stop_loss']:
                return ('stop_loss', position['stop_loss'], 1.0)

            # Check TP2 (se existe e ainda não fechou parcial)
            if position['tp2'] and not position['partial_closed']:
                if high >= position['tp2']:
                    return ('take_profit_2', position['tp2'], 0.5)  # Fecha 50%

            # Check TP1
            if high >= position['tp1']:
                # Se tem TP parcial, fecha 50%, senão fecha tudo
                close_pct = 0.5 if position['tp2'] and not position['partial_closed'] else 1.0
                return ('take_profit_1', position['tp1'], close_pct)

        else:  # short
            # Check SL
            if high >= position['stop_loss']:
                return ('stop_loss', position['stop_loss'], 1.0)

            # Check TP2
            if position['tp2'] and not position['partial_closed']:
                if low <= position['tp2']:
                    return ('take_profit_2', position['tp2'], 0.5)

            # Check TP1
            if low <= position['tp1']:
                close_pct = 0.5 if position['tp2'] and not position['partial_closed'] else 1.0
                return ('take_profit_1', position['tp1'], close_pct)

        # Time exit (48h)
        if idx - position['entry_idx'] > 192:
            return ('time_exit', current['close'], 1.0)

        return None

    def _close_trade(self, position, current, reason, exit_price, close_pct):
        """Fecha posição (total ou parcial)."""
        entry = position['entry_price']
        direction = position['direction']
        size = position['size'] * close_pct

        # Calculate PnL
        if direction == 'long':
            pnl_pct = ((exit_price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - exit_price) / entry) * 100

        pnl_amount = size * (pnl_pct / 100)

        # Fees
        entry_fee = size * self.trading_fee
        exit_fee = size * self.trading_fee
        total_fees = entry_fee + exit_fee

        pnl_amount_after_fees = pnl_amount - total_fees

        return {
            'entry_time': position['entry_time'],
            'exit_time': current.name,
            'direction': direction,
            'entry_price': entry,
            'exit_price': exit_price,
            'size': size,
            'pnl_pct': pnl_pct,
            'pnl_amount': pnl_amount_after_fees,
            'fees': total_fees,
            'reason': reason,
            'ml_confidence': position['ml_confidence'],
            'close_pct': close_pct
        }

    def _calculate_stats(self, trades, sl_mult, tp_mult, use_partial_tp):
        """Calcula estatísticas."""
        if not trades:
            return {
                'config': f"{sl_mult:.1f}x SL, {tp_mult:.1f}x TP" + (" (Partial)" if use_partial_tp else ""),
                'error': 'No trades',
                'trades': 0
            }

        df_trades = pd.DataFrame(trades)

        total = len(df_trades)
        winning = df_trades[df_trades['pnl_amount'] > 0]
        losing = df_trades[df_trades['pnl_amount'] <= 0]

        win_rate = len(winning) / total if total > 0 else 0
        total_pnl = df_trades['pnl_amount'].sum()
        roi = (total_pnl / self.initial_capital) * 100

        avg_win = winning['pnl_amount'].mean() if len(winning) > 0 else 0
        avg_loss = abs(losing['pnl_amount'].mean()) if len(losing) > 0 else 0

        pf = (winning['pnl_amount'].sum() / abs(losing['pnl_amount'].sum())
              if len(losing) > 0 and losing['pnl_amount'].sum() != 0 else 0)

        returns = df_trades['pnl_pct'].values
        sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)
                 if len(returns) > 1 and np.std(returns) > 0 else 0)

        equity = self.initial_capital + df_trades['pnl_amount'].cumsum()
        peak = equity.expanding().max()
        dd = ((equity - peak) / peak * 100).min()

        # Average R:R
        avg_rr = avg_win / avg_loss if avg_loss > 0 else 0

        return {
            'config': f"{sl_mult:.1f}x SL, {tp_mult:.1f}x TP" + (" (Partial)" if use_partial_tp else ""),
            'sl_mult': sl_mult,
            'tp_mult': tp_mult,
            'partial_tp': use_partial_tp,
            'trades': total,
            'win_rate': win_rate,
            'roi': roi,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'avg_rr': avg_rr,
            'profit_factor': pf,
            'sharpe': sharpe,
            'max_dd': dd,
            'total_fees': df_trades['fees'].sum()
        }


def main():
    global logger

    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', type=str, default='BTCUSDT')
    parser.add_argument('--days', type=int, default=10)
    parser.add_argument('--model', type=str, default='real_btc_ensemble_20251120_234339.pkl')
    parser.add_argument('--confidence', type=float, default=0.0)

    args = parser.parse_args()

    config = load_config('standard')

    # Silence verbose logging, only show critical info
    import logging as std_logging
    std_logging.basicConfig(level=std_logging.WARNING)
    logger = setup_logging('WARNING', log_to_file=False)

    print()
    print("=" * 80)
    print("🎯 OTIMIZADOR DE RISK:REWARD")
    print("=" * 80)
    print(f"Symbol: {args.symbol}")
    print(f"Period: {args.days} days")
    print(f"Model: {args.model}")
    print(f"Min Confidence: {args.confidence:.0%}")
    print("=" * 80)
    print()

    # Download data
    print("📥 Downloading data...", end=" ", flush=True)
    rest_client = BybitRESTClient(
        api_key=config['bybit_api_key'],
        api_secret=config['bybit_api_secret'],
        testnet=config['bybit_testnet']
    )

    dm = DataManager(rest_client)
    df = dm.get_data(args.symbol, '15m', args.days, use_cache=False)

    if df.empty:
        print("\n❌ No data")
        return

    print(f"✅ {len(df):,} candles")

    # Build features (same as 1.py)
    print("🔨 Building features...", end=" ", flush=True)
    fs = FeatureStore(config)
    df_features = fs.build_features(df, normalize=False)

    # Apply ultra scalper features (embedded from 1.py)
    df_features = create_ultra_scalper_features(df_features)
    print(f"✅ {len(df_features.columns)} columns ready")
    print()

    # Load model
    model_path = f"storage/models/{args.model}"
    print(f"🤖 Loading model...", end=" ", flush=True)
    optimizer = RROptimizer(config, model_path, args.confidence)
    print(f"✅ {len(optimizer.feature_names)} features")
    print()

    # Test configurations
    configs = [
        # (SL_mult, TP_mult, use_partial_tp)
        (2.0, 1.0, False),  # Padrão atual
        (1.5, 1.0, False),  # SL menor
        (1.2, 1.0, False),  # SL bem menor
        (1.0, 1.0, False),  # SL = TP (1:1)
        (1.5, 1.2, False),  # TP maior
        (1.5, 1.5, False),  # TP muito maior
        (1.5, 0.8, False),  # TP menor
        # TP Parcial
        (1.5, 1.0, True),   # 50% no TP1, 50% no TP2 (1.5x)
        (1.2, 1.0, True),   # 50% no TP1, 50% no TP2 (1.5x)
        (1.0, 1.0, True),   # 50% no TP1, 50% no TP2 (1.5x)
    ]

    print(f"🧪 Testing {len(configs)} configurations...", end=" ", flush=True)

    results = []
    for i, (sl, tp, partial) in enumerate(configs, 1):
        print(f"{i}", end="." if i < len(configs) else " ", flush=True)
        stats = optimizer.test_configuration(df_features.copy(), sl, tp, partial)
        results.append(stats)

    print("✅")
    print()

    # Print results
    print("=" * 100)
    print("📊 RESULTADOS COMPARATIVOS")
    print("=" * 100)
    print()

    header = f"{'Config':<30} | {'Trades':<7} | {'WR':<7} | {'ROI':<8} | {'Avg R:R':<8} | {'PF':<6} | {'Sharpe':<7} | {'MaxDD':<7}"
    print(header)
    print("-" * 100)

    for r in results:
        if r.get('trades', 0) > 0:
            line = (f"{r['config']:<30} | "
                   f"{r['trades']:>7} | "
                   f"{r['win_rate']*100:>6.1f}% | "
                   f"{r['roi']:>+7.1f}% | "
                   f"{r['avg_rr']:>7.2f}x | "
                   f"{r['profit_factor']:>5.2f} | "
                   f"{r['sharpe']:>6.2f} | "
                   f"{r['max_dd']:>6.1f}%")
            print(line)
        else:
            print(f"{r['config']:<30} | No trades")

    print()

    # Find best config
    valid_results = [r for r in results if r.get('trades', 0) > 0]

    if valid_results:
        best_roi = max(valid_results, key=lambda x: x['roi'])
        best_sharpe = max(valid_results, key=lambda x: x['sharpe'])
        best_rr = max(valid_results, key=lambda x: x['avg_rr'])

        print("=" * 100)
        print("🏆 MELHORES CONFIGURAÇÕES")
        print("=" * 100)
        print()

        print("🎯 Melhor ROI:")
        print(f"   Config: {best_roi['config']}")
        print(f"   ROI: {best_roi['roi']:+.2f}%")
        print(f"   WR: {best_roi['win_rate']*100:.1f}%")
        print(f"   Avg R:R: {best_roi['avg_rr']:.2f}x")
        print(f"   Trades: {best_roi['trades']}")
        print()

        print("📈 Melhor Sharpe:")
        print(f"   Config: {best_sharpe['config']}")
        print(f"   Sharpe: {best_sharpe['sharpe']:.2f}")
        print(f"   ROI: {best_sharpe['roi']:+.2f}%")
        print(f"   WR: {best_sharpe['win_rate']*100:.1f}%")
        print()

        print("⚖️  Melhor Risk:Reward:")
        print(f"   Config: {best_rr['config']}")
        print(f"   Avg R:R: {best_rr['avg_rr']:.2f}x")
        print(f"   ROI: {best_rr['roi']:+.2f}%")
        print(f"   WR: {best_rr['win_rate']*100:.1f}%")
        print()

        print("💾 Recomendação para .env:")
        print(f"   SL_ATR_MULT={best_roi['sl_mult']:.1f}")
        print(f"   TP_ATR_MULT={best_roi['tp_mult']:.1f}")
        if best_roi['partial_tp']:
            print(f"   USE_PARTIAL_TP=True")
        print()

    print("=" * 100)


if __name__ == "__main__":
    main()
