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

logger = None


class RROptimizer:
    """Otimiza Risk:Reward testando diferentes SL/TP."""

    def __init__(self, config: dict, model_path: str, min_confidence: float = 0.0):
        self.config = config
        self.min_confidence = min_confidence

        # Load model
        with open(model_path, 'rb') as f:
            self.model_data = pickle.load(f)

        # Extract model and features
        if hasattr(self.model_data, 'feature_columns'):
            self.feature_names = self.model_data.feature_columns
            self.model = self.model_data
        else:
            self.model = self.model_data.get('model')
            self.feature_names = self.model_data.get('feature_names')

        self.initial_capital = config.get('initial_capital', 300)
        self.risk_per_trade = config.get('risk_per_trade_pct', 0.75) / 100
        self.trading_fee = 0.00055  # Bybit taker 0.055%

    def test_configuration(self, df: pd.DataFrame, sl_mult: float, tp_mult: float,
                          use_partial_tp: bool = False) -> Dict:
        """Test uma configuração específica de SL/TP."""

        # Get ML predictions
        X = df[self.feature_names].fillna(0)

        # Predict using ensemble if available
        if hasattr(self.model, 'predict'):
            ml_probs = self.model.predict(X)
        else:
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
    logger = setup_logging('INFO', log_to_file=False)

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
    print("📥 Downloading data...")
    rest_client = BybitRESTClient(
        api_key=config['bybit_api_key'],
        api_secret=config['bybit_api_secret'],
        testnet=config['bybit_testnet']
    )

    dm = DataManager(rest_client)
    df = dm.get_data(args.symbol, '15m', args.days, use_cache=False)

    if df.empty:
        print("❌ No data")
        return

    print(f"✅ Downloaded {len(df):,} candles")
    print()

    # Build features
    print("🔨 Building features...")
    fs = FeatureStore(config)
    df_features = fs.build_features(df, normalize=False)

    # Add ultra scalper features if needed
    try:
        from create_ultra_scalper_features import create_ultra_scalper_features
        df_features = create_ultra_scalper_features(df_features)
    except:
        pass

    print(f"✅ Features ready")
    print()

    # Load model
    model_path = f"storage/models/{args.model}"
    optimizer = RROptimizer(config, model_path, args.confidence)

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

    print("🧪 Testing configurations...")
    print()

    results = []
    for sl, tp, partial in configs:
        stats = optimizer.test_configuration(df_features.copy(), sl, tp, partial)
        results.append(stats)

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
