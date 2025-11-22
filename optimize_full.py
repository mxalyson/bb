"""
🎯 OTIMIZADOR COMPLETO - GRID SEARCH
Testa TODAS as combinações de: Confiança + SL + TP
Encontra a configuração PERFEITA para maximizar lucros!
"""

import sys
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')
sys.path.append(str(Path(__file__).parent))

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import argparse
from datetime import datetime
import pickle

from core.utils import load_config, setup_logging
from core.bybit_rest import BybitRESTClient
from core.data import DataManager
from core.features import FeatureStore

# Import ultra scalper features from optimize_rr.py
from optimize_rr import create_ultra_scalper_features, UniversalUnpickler, ModelWrapper

logger = None


class FullOptimizer:
    """Grid search completo: Confiança x SL x TP"""

    def __init__(self, config: dict, model_path: str):
        self.config = config

        # Load model
        with open(model_path, 'rb') as f:
            self.model_data = UniversalUnpickler(f).load()

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
        self.trading_fee = 0.00055

    def test_config(self, df: pd.DataFrame, min_conf: float, sl_mult: float, tp_mult: float) -> Dict:
        """Testa uma configuração específica."""

        # Get predictions
        X = df[self.feature_names].fillna(0)

        try:
            if hasattr(self.model, 'predict'):
                ml_probs = self.model.predict(X)
            elif hasattr(self.model, 'models_list'):
                predictions = []
                for model, weight in zip(self.model.models_list, self.model.model_weights):
                    pred = model.predict(X)
                    predictions.append(pred * weight)
                ml_probs = np.sum(predictions, axis=0)
            else:
                ml_probs = np.array([0.5] * len(X))
        except:
            ml_probs = np.array([0.5] * len(X))

        df['ml_prob_up'] = ml_probs
        df['ml_confidence'] = np.abs(ml_probs - 0.5) * 2

        # Generate signals with confidence filter
        df['signal'] = 0
        mask_long = (df['ml_prob_up'] > 0.5) & (df['ml_confidence'] >= min_conf)
        mask_short = (df['ml_prob_up'] < 0.5) & (df['ml_confidence'] >= min_conf)

        df.loc[mask_long, 'signal'] = 1
        df.loc[mask_short, 'signal'] = -1

        # Simulate
        trades = self._simulate(df, sl_mult, tp_mult)

        # Stats
        return self._calculate_stats(trades, min_conf, sl_mult, tp_mult)

    def _simulate(self, df: pd.DataFrame, sl_mult: float, tp_mult: float) -> List[Dict]:
        """Simula trades."""
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
                if self._check_exit(position, current):
                    trade = self._close_trade(position, current)
                    trades.append(trade)
                    capital += trade['pnl_amount']
                    position = None
                    cooldown = 4

            # Check entry
            if not position and current['signal'] != 0 and cooldown == 0 and i < len(df) - 20:
                position = self._open_trade(current, capital, i, sl_mult, tp_mult)

        # Close final
        if position:
            trade = self._close_trade(position, df.iloc[-1])
            trades.append(trade)

        return trades

    def _open_trade(self, current, capital, idx, sl_mult, tp_mult):
        """Abre trade."""
        direction = 'long' if current['signal'] == 1 else 'short'
        price = current['close']
        atr = current.get('atr', price * 0.01)

        if direction == 'long':
            sl = price - (atr * sl_mult)
            tp = price + (atr * tp_mult)
        else:
            sl = price + (atr * sl_mult)
            tp = price - (atr * tp_mult)

        # Position size
        sl_dist = abs((sl - price) / price)
        risk_amt = capital * self.risk_per_trade
        size = risk_amt / sl_dist if sl_dist > 0 else capital * 0.1
        size = min(size, capital * 0.95)

        # Bybit minimums
        qty_btc = size / price
        qty_btc = max(0.001, qty_btc)
        qty_btc = round(qty_btc / 0.001) * 0.001
        size = qty_btc * price
        size = min(size, capital * 0.95)

        return {
            'entry_idx': idx,
            'entry_price': price,
            'direction': direction,
            'size': size,
            'sl': sl,
            'tp': tp,
            'confidence': current['ml_confidence']
        }

    def _check_exit(self, position, current):
        """Checa saída."""
        direction = position['direction']

        if direction == 'long':
            if current['low'] <= position['sl']:
                position['exit_reason'] = 'SL'
                position['exit_price'] = position['sl']
                return True
            if current['high'] >= position['tp']:
                position['exit_reason'] = 'TP'
                position['exit_price'] = position['tp']
                return True
        else:
            if current['high'] >= position['sl']:
                position['exit_reason'] = 'SL'
                position['exit_price'] = position['sl']
                return True
            if current['low'] <= position['tp']:
                position['exit_reason'] = 'TP'
                position['exit_price'] = position['tp']
                return True

        return False

    def _close_trade(self, position, current):
        """Fecha trade."""
        if 'exit_price' not in position:
            position['exit_reason'] = 'EOD'
            position['exit_price'] = current['close']

        entry = position['entry_price']
        exit_price = position['exit_price']
        direction = position['direction']

        if direction == 'long':
            pnl_pct = ((exit_price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - exit_price) / entry) * 100

        pnl_amount = position['size'] * (pnl_pct / 100)

        # Fees
        fees = position['size'] * self.trading_fee * 2
        pnl_amount -= fees

        return {
            'pnl_amount': pnl_amount,
            'pnl_pct': pnl_pct,
            'reason': position['exit_reason'],
            'size': position['size']
        }

    def _calculate_stats(self, trades, min_conf, sl_mult, tp_mult):
        """Calcula estatísticas."""
        if not trades:
            return {
                'conf': min_conf,
                'sl': sl_mult,
                'tp': tp_mult,
                'trades': 0,
                'wr': 0,
                'roi': 0,
                'sharpe': 0,
                'pf': 0
            }

        df_trades = pd.DataFrame(trades)

        total = len(df_trades)
        wins = df_trades[df_trades['pnl_amount'] > 0]
        losses = df_trades[df_trades['pnl_amount'] <= 0]

        wr = len(wins) / total if total > 0 else 0
        total_pnl = df_trades['pnl_amount'].sum()
        roi = (total_pnl / self.initial_capital) * 100

        returns = df_trades['pnl_pct'].values
        sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)
                 if len(returns) > 1 and np.std(returns) > 0 else 0)

        pf = (wins['pnl_amount'].sum() / abs(losses['pnl_amount'].sum())
              if len(losses) > 0 and losses['pnl_amount'].sum() != 0 else 0)

        return {
            'conf': min_conf,
            'sl': sl_mult,
            'tp': tp_mult,
            'trades': total,
            'wr': wr,
            'roi': roi,
            'sharpe': sharpe,
            'pf': pf
        }


def main():
    global logger

    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', type=str, default='BTCUSDT')
    parser.add_argument('--days', type=int, default=10)
    parser.add_argument('--model', type=str, default='real_btc_ensemble_20251120_234339.pkl')

    args = parser.parse_args()

    config = load_config('standard')

    import logging as std_logging
    std_logging.basicConfig(level=std_logging.WARNING)
    logger = setup_logging('WARNING', log_to_file=False)

    print()
    print("=" * 100)
    print("🔥 OTIMIZADOR COMPLETO - GRID SEARCH")
    print("=" * 100)
    print(f"Symbol: {args.symbol}")
    print(f"Period: {args.days} days")
    print(f"Model: {args.model}")
    print("=" * 100)
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

    # Build features
    print("🔨 Building features...", end=" ", flush=True)
    fs = FeatureStore(config)
    df_features = fs.build_features(df, normalize=False)
    df_features = create_ultra_scalper_features(df_features)
    print(f"✅ {len(df_features.columns)} columns")
    print()

    # Load model
    model_path = f"storage/models/{args.model}"
    print(f"🤖 Loading model...", end=" ", flush=True)
    optimizer = FullOptimizer(config, model_path)
    print(f"✅ {len(optimizer.feature_names)} features")
    print()

    # Grid search configurations
    confidences = [0.0, 0.25, 0.40, 0.50, 0.60]
    sl_mults = [1.5, 2.0]
    tp_mults = [0.7, 1.0, 1.2]

    total_configs = len(confidences) * len(sl_mults) * len(tp_mults)

    print(f"🧪 Testing {total_configs} configurations...")
    print(f"   Confidences: {confidences}")
    print(f"   SL: {sl_mults}")
    print(f"   TP: {tp_mults}")
    print()

    results = []
    count = 0

    for conf in confidences:
        for sl in sl_mults:
            for tp in tp_mults:
                count += 1
                print(f"   [{count}/{total_configs}] Conf={conf:.0%}, SL={sl:.1f}x, TP={tp:.1f}x...", end=" ", flush=True)

                stats = optimizer.test_config(df_features.copy(), conf, sl, tp)
                results.append(stats)

                print(f"✓ ({stats['trades']} trades, {stats['wr']*100:.0f}% WR, {stats['roi']:+.2f}% ROI)")

    print()
    print("=" * 100)
    print("📊 TOP 10 CONFIGURAÇÕES (por ROI)")
    print("=" * 100)
    print()

    # Sort by ROI
    results_sorted = sorted(results, key=lambda x: x['roi'], reverse=True)[:10]

    header = f"{'Rank':<6} | {'Conf':<6} | {'SL':<5} | {'TP':<5} | {'Trades':<7} | {'WR':<7} | {'ROI':<9} | {'Sharpe':<7} | {'PF':<6}"
    print(header)
    print("-" * 100)

    for i, r in enumerate(results_sorted, 1):
        line = (f"{i:<6} | "
               f"{r['conf']*100:>5.0f}% | "
               f"{r['sl']:>4.1f}x | "
               f"{r['tp']:>4.1f}x | "
               f"{r['trades']:>7} | "
               f"{r['wr']*100:>6.1f}% | "
               f"{r['roi']:>+8.2f}% | "
               f"{r['sharpe']:>6.2f} | "
               f"{r['pf']:>5.2f}")
        print(line)

    print()
    print("=" * 100)
    print("🏆 MELHOR CONFIGURAÇÃO")
    print("=" * 100)

    best = results_sorted[0]

    print()
    print(f"🎯 Confiança: {best['conf']*100:.0f}%")
    print(f"🛑 SL: {best['sl']:.1f}x ATR")
    print(f"✅ TP: {best['tp']:.1f}x ATR")
    print()
    print(f"📊 Resultados:")
    print(f"   Trades: {best['trades']}")
    print(f"   Win Rate: {best['wr']*100:.1f}%")
    print(f"   ROI: {best['roi']:+.2f}%")
    print(f"   Sharpe: {best['sharpe']:.2f}")
    print(f"   Profit Factor: {best['pf']:.2f}")
    print()
    print("💾 Adicione no seu .env:")
    print(f"   MIN_ML_CONFIDENCE={best['conf']:.2f}")
    print(f"   SL_ATR_MULT={best['sl']:.1f}")
    print(f"   TP_ATR_MULT={best['tp']:.1f}")
    print()
    print("=" * 100)


if __name__ == "__main__":
    main()
