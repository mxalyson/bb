"""
MASTER SCALPER - Live Trading (PRODUCTION READY)

✅ Loop 30s
✅ SEM time exit
✅ Conversão robusta de predições NumPy
✅ Lógica 100% idêntica ao validate
"""

import sys
from pathlib import Path
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning)

sys.path.append(str(Path(__file__).parent))

import pandas as pd
import numpy as np
from typing import Dict, Optional
import logging
import argparse
import pickle
import time
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import requests

load_dotenv()

from core.utils import load_config, setup_logging
from core.bybit_rest import BybitRESTClient
from core.data import DataManager
from core.features import FeatureStore

logger = None
STATE_FILE = "storage/bot_state.json"

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, message: str, parse_mode: str = "HTML"):
        try:
            url = f"{self.base_url}/sendMessage"
            data = {"chat_id": self.chat_id, "text": message, "parse_mode": parse_mode}
            response = requests.post(url, data=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False
    
    def send_trade_open(self, trade: Dict):
        direction_emoji = "🟢" if trade['direction'] == 'long' else "🔴"
        message = f"""{direction_emoji} NOVA OPERAÇÃO

Direção: {trade['direction'].upper()}
Entrada: ${trade['entry_price']:,.2f}
Tamanho: ${trade['size']:,.2f}
Confiança: {trade['ml_confidence']*100:.1f}%

SL: ${trade['stop_loss']:,.2f}
TP1: ${trade['tp1']:,.2f}
TP2: ${trade['tp2']:,.2f}
TP3: ${trade['tp3']:,.2f}"""
        self.send_message(message)
    
    def send_trade_close(self, trade: Dict, pnl_amount: float, pnl_pct: float):
        result = "✅" if pnl_amount > 0 else "❌"
        message = f"""{result} FECHADO

Direção: {trade['direction'].upper()}
Entrada: ${trade['entry_price']:,.2f}
Saída: ${trade['exit_price']:,.2f}
PnL: ${pnl_amount:+,.2f} ({pnl_pct:+.2f}%)
Motivo: {trade['exit_reason']}"""
        self.send_message(message)
    
    def send_error(self, error_msg: str):
        message = f"""⚠️ ERRO

{error_msg}"""
        self.send_message(message)
    
    def send_status(self, stats: Dict):
        message = f"""📊 STATUS

Capital: ${stats['capital']:,.2f}
Trades: {stats['total_trades']}
Win Rate: {stats['win_rate']:.1f}%
PnL Total: ${stats['total_pnl']:+,.2f}
ROI: {stats['roi']:+.2f}%"""
        self.send_message(message)

def create_advanced_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add MASTER TRADER advanced features"""
    df_features = df.copy()
    
    for period in [3, 5, 8, 13, 21]:
        df_features[f'momentum_{period}'] = df_features['close'].pct_change(period) * 100
        df_features[f'volume_ratio_{period}'] = df_features['volume'] / df_features['volume'].rolling(period).mean()

    # Trend strength (NO IF - ema50/ema200 always exist)
    df_features['trend_strength'] = (df_features['ema50'] - df_features['ema200']) / df_features['ema200'] * 100

    # Volatility regime (NO IF - atr always exists)
    df_features['volatility_regime'] = df_features['atr'] / df_features['atr'].rolling(50).mean()

    # Price position (NO .fillna - matches train_master_scalper.py)
    df_features['price_position'] = (
        (df_features['close'] - df_features['low'].rolling(20).min()) /
        (df_features['high'].rolling(20).max() - df_features['low'].rolling(20).min())
    )

    df_features['volume_momentum'] = df_features['volume'].pct_change(5)
    df_features['price_acceleration'] = df_features['close'].diff(2) - df_features['close'].diff(1)
    
    return df_features

class MasterLiveTrader:
    def __init__(self, config: dict, model_path: str, telegram: TelegramNotifier):
        self.config = config
        self.model_path = Path(model_path)
        self.telegram = telegram
        
        if not self.model_path.exists():
            raise ValueError(f"Model not found: {model_path}")
        
        with open(self.model_path, 'rb') as f:
            self.model_data = pickle.load(f)
            self.model = self.model_data['model']
            self.feature_names = self.model_data['feature_names']
        
        self.initial_capital = float(os.getenv('INITIAL_CAPITAL', '10000'))
        risk_value = float(os.getenv('RISK_PER_TRADE', '0.0075'))
        self.risk_per_trade = risk_value if risk_value < 1 else risk_value / 100
        self.min_confidence = float(os.getenv('MIN_ML_CONFIDENCE', '0.0'))
        
        logger.info("="*70)
        logger.info("📋 CONFIGURAÇÕES")
        logger.info("="*70)
        logger.info(f"Modelo: {self.model_path.name}")
        logger.info(f"Features: {len(self.feature_names)}")
        logger.info(f"Capital Inicial: ${self.initial_capital:,.2f}")
        logger.info(f"Risco por Trade: {self.risk_per_trade:.2%}")
        logger.info(f"MIN_ML_CONFIDENCE: {self.min_confidence:.2%}")
        logger.info(f"Loop: 30s")
        logger.info(f"Time Exit: DISABLED")
        logger.info("="*70)
        
        self.position = None
        self.capital = self.initial_capital
        self.trades_history = []
        self.cooldown_until = 0
        
        self.bybit_testnet = os.getenv('BYBIT_TESTNET', 'true').lower() == 'true'
        self.rest_client = BybitRESTClient(
            api_key=os.getenv('BYBIT_API_KEY'),
            api_secret=os.getenv('BYBIT_API_SECRET'),
            testnet=self.bybit_testnet
        )
        
        self.dm = DataManager(self.rest_client)
        self.fs = FeatureStore(config)
        
        logger.info(f"✅ Bot inicializado ({'TESTNET' if self.bybit_testnet else 'MAINNET'})")
    
    def save_state(self):
        state = {
            'capital': self.capital,
            'position': self.position,
            'trades_history': self.trades_history,
            'cooldown_until': self.cooldown_until or 0
        }
        try:
            os.makedirs("storage", exist_ok=True)
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Save error: {e}")
    
    def recover_state(self):
        if not Path(STATE_FILE).exists():
            logger.info("📝 Starting fresh")
            return
        
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
            
            file_age = datetime.now().timestamp() - Path(STATE_FILE).stat().st_mtime
            if file_age > 3600:
                logger.warning("State too old")
                return
            
            self.capital = state.get('capital', self.initial_capital)
            self.trades_history = state.get('trades_history', [])
            self.cooldown_until = state.get('cooldown_until', 0)
            self.position = state.get('position')
            
            if self.position:
                logger.info(f"🔄 Recovered {self.position['direction']} @ ${self.position['entry_price']:,.2f}")
        except Exception as e:
            logger.warning(f"Recover failed: {e}")
    
    def get_current_data(self, symbol: str, timeframe: str = '15m', lookback_days: int = 30) -> pd.DataFrame:
        df = self.dm.get_data(symbol, timeframe, lookback_days, use_cache=False)
        if df.empty:
            raise ValueError("No data received from API")
        
        df = self.fs.build_features(df, normalize=False)
        df = create_advanced_features(df)
        
        return df
    
    def get_signal(self, df: pd.DataFrame) -> tuple:
        try:
            latest = df.iloc[-1]
            X = df[self.feature_names].fillna(0).iloc[-1:].values
            
            ml_probs = self.model.predict(X)
            
            if isinstance(ml_probs, np.ndarray):
                if ml_probs.ndim > 0 and len(ml_probs) > 0:
                    ml_prob_up = float(ml_probs.flatten()[0])
                else:
                    ml_prob_up = float(ml_probs)
            elif isinstance(ml_probs, (np.floating, np.integer)):
                ml_prob_up = float(ml_probs)
            else:
                ml_prob_up = float(ml_probs)
            
            ml_prob_down = 1.0 - ml_prob_up
            ml_confidence = abs(ml_prob_up - 0.5) * 2.0
            
            signal = 0
            if ml_prob_up > 0.5 and ml_confidence >= self.min_confidence:
                signal = 1
            elif ml_prob_down > 0.5 and ml_confidence >= self.min_confidence:
                signal = -1
            
            return signal, ml_confidence, latest
            
        except Exception as e:
            logger.error(f"Error in get_signal: {e}")
            import traceback
            traceback.print_exc()
            return 0, 0.0, df.iloc[-1]
    
    def open_position(self, symbol: str, signal: int, current_data: pd.Series, ml_confidence: float):
        direction = 'long' if signal == 1 else 'short'
        price = current_data['close']
        atr = current_data.get('atr', price * 0.01)
        
        if direction == 'long':
            sl = price - (atr * 2)
            tp1 = price + (atr * 1)
            tp2 = price + (atr * 2)
            tp3 = price + (atr * 3)
        else:
            sl = price + (atr * 2)
            tp1 = price - (atr * 1)
            tp2 = price - (atr * 2)
            tp3 = price - (atr * 3)
        
        sl_dist = abs((sl - price) / price)
        risk_amt = self.capital * self.risk_per_trade
        size = min(
            risk_amt / sl_dist if sl_dist > 0 else self.capital * 0.1,
            self.capital * 0.95
        )
        
        self.position = {
            'symbol': symbol,
            'direction': direction,
            'entry_price': price,
            'entry_time': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'size': size,
            'stop_loss': sl,
            'tp1': tp1,
            'tp2': tp2,
            'tp3': tp3,
            'ml_confidence': ml_confidence
        }
        
        logger.info(f"🟢 OPENED {direction.upper()} @ ${price:,.2f} | Conf: {ml_confidence:.1%} | Size: ${size:,.2f}")
        
        try:
            self.telegram.send_trade_open(self.position)
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")
        
        self.save_state()
    
    def check_exit(self, current_data: pd.Series) -> Optional[str]:
        """Check exit - NO TIME EXIT"""
        if not self.position:
            return None
        
        high, low = current_data['high'], current_data['low']
        direction = self.position['direction']
        
        if direction == 'long':
            if low <= self.position['stop_loss']:
                return 'stop_loss'
            if high >= self.position['tp3']:
                return 'take_profit_3'
            if high >= self.position['tp2']:
                return 'take_profit_2'
            if high >= self.position['tp1']:
                return 'take_profit_1'
        else:
            if high >= self.position['stop_loss']:
                return 'stop_loss'
            if low <= self.position['tp3']:
                return 'take_profit_3'
            if low <= self.position['tp2']:
                return 'take_profit_2'
            if low <= self.position['tp1']:
                return 'take_profit_1'
        
        return None
    
    def close_position(self, current_data: pd.Series, reason: str):
        if not self.position:
            return
        
        if reason == 'stop_loss':
            exit_price = self.position['stop_loss']
        elif reason.startswith('take_profit'):
            tp_num = int(reason.split('_')[-1])
            exit_price = self.position[f'tp{tp_num}']
        else:
            exit_price = current_data['close']
        
        entry = self.position['entry_price']
        direction = self.position['direction']
        
        if direction == 'long':
            pnl_pct = ((exit_price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - exit_price) / entry) * 100
        
        pnl_amount = self.position['size'] * (pnl_pct / 100)
        self.capital += pnl_amount
        
        trade = {
            'entry_time': self.position['entry_time'],
            'exit_time': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'direction': direction,
            'entry_price': entry,
            'exit_price': exit_price,
            'size': self.position['size'],
            'pnl_pct': pnl_pct,
            'pnl_amount': pnl_amount,
            'exit_reason': reason,
            'ml_confidence': self.position['ml_confidence']
        }
        self.trades_history.append(trade)
        
        result = "✅" if pnl_amount > 0 else "❌"
        logger.info(f"{result} CLOSED {direction.upper()} | ${entry:,.2f}→${exit_price:,.2f} | PnL: ${pnl_amount:+,.2f} ({pnl_pct:+.2f}%)")
        
        try:
            self.telegram.send_trade_close(trade, pnl_amount, pnl_pct)
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")
        
        self.position = None
        self.cooldown_until = time.time() + (2 * 15 * 60)
        self.save_state()
    
    def get_stats(self) -> Dict:
        if not self.trades_history:
            return {
                'capital': self.capital,
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'roi': 0
            }
        
        df = pd.DataFrame(self.trades_history)
        total = len(df)
        wins = len(df[df['pnl_amount'] > 0])
        win_rate = wins / total * 100
        total_pnl = df['pnl_amount'].sum()
        roi = (total_pnl / self.initial_capital) * 100
        
        return {
            'capital': self.capital,
            'total_trades': total,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'roi': roi
        }
    
    def run(self, symbol: str, check_interval: int = 30):
        """Main loop - 30s"""
        logger.info("🚀 MASTER SCALPER BOT STARTED")
        
        self.telegram.send_message(f"""🤖 BOT INICIADO

Capital: ${self.initial_capital:,.2f}
Threshold: {self.min_confidence:.0%}
Loop: {check_interval}s
Time Exit: DISABLED""")
        
        self.recover_state()
        
        candle_count = 0
        last_status_time = time.time()
        
        try:
            while True:
                try:
                    logger.info("="*70)
                    logger.info(f"🔄 ITERATION #{candle_count+1} - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
                    logger.info("="*70)
                    
                    start_time = time.time()
                    
                    df = self.get_current_data(symbol, '15m', 30)
                    if df.empty:
                        logger.warning("⚠️ No data received")
                        continue
                    
                    fetch_time = time.time() - start_time
                    current = df.iloc[-1]
                    candle_count += 1
                    price = current['close']
                    
                    logger.info(f"📊 Price: ${price:,.2f} | Capital: ${self.capital:,.2f} | Fetch: {fetch_time:.1f}s")
                    
                    if self.position:
                        entry = self.position['entry_price']
                        direction = self.position['direction']
                        
                        if direction == 'long':
                            pnl_pct = ((price - entry) / entry) * 100
                        else:
                            pnl_pct = ((entry - price) / entry) * 100
                        
                        pnl_usd = self.position['size'] * (pnl_pct / 100)
                        
                        logger.info(f"🟢 {direction.upper()} @ ${entry:,.2f} | PnL: ${pnl_usd:+,.2f} ({pnl_pct:+.2f}%)")
                        
                        exit_reason = self.check_exit(current)
                        if exit_reason:
                            self.close_position(current, exit_reason)
                    
                    else:
                        now = time.time()
                        in_cooldown = now < self.cooldown_until
                        
                        if in_cooldown:
                            remaining = int((self.cooldown_until - now) / 60)
                            logger.info(f"⏳ Cooldown: {remaining}min")
                        else:
                            signal, ml_confidence, current_data = self.get_signal(df)
                            
                            sig_name = 'LONG' if signal == 1 else 'SHORT' if signal == -1 else 'NEUTRO'
                            passes = ml_confidence >= self.min_confidence
                            status = '✅ PASS' if passes else '❌ FILTERED'
                            
                            logger.info(f"🎯 Signal: {sig_name} | Confidence: {ml_confidence:.2%} | {status}")
                            
                            if signal != 0 and passes:
                                logger.info("="*70)
                                logger.info(f"🚨 OPENING {sig_name} POSITION")
                                logger.info("="*70)
                                
                                try:
                                    self.open_position(symbol, signal, current_data, ml_confidence)
                                except Exception as e:
                                    logger.error(f"❌ Failed to open position: {e}")
                                    import traceback
                                    traceback.print_exc()
                                    self.telegram.send_error(f"Failed to open position: {e}")
                    
                    if time.time() - last_status_time > (4 * 3600):
                        self.telegram.send_status(self.get_stats())
                        last_status_time = time.time()
                    
                
                except Exception as e:
                    logger.error(f"❌ Loop error: {e}")
                    import traceback
                    traceback.print_exc()
        
        except KeyboardInterrupt:
            logger.info("\n⏹️ Bot stopped by user")
            if self.position:
                df = self.get_current_data(symbol, '15m', 30)
                self.close_position(df.iloc[-1], 'manual_stop')
            
            stats = self.get_stats()
            logger.info(f"📊 Final: {stats['total_trades']} trades | WR: {stats['win_rate']:.1f}% | ROI: {stats['roi']:+.2f}%")
            self.telegram.send_status(stats)

def main():
    global logger
    
    parser = argparse.ArgumentParser(description='MASTER SCALPER Live Trading Bot')
    parser.add_argument('--symbol', default='BTCUSDT', help='Trading symbol')
    parser.add_argument('--model', default='ml_model_master_scalper_365d.pkl', help='Model filename')
    parser.add_argument('--interval', type=int, default=30, help='Check interval (default: 30s)')
    args = parser.parse_args()
    
    config = load_config('standard')
    logger = setup_logging('INFO', log_to_file=True)
    
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
    telegram_chat = os.getenv('TELEGRAM_CHAT_ID')
    
    if not telegram_token or not telegram_chat:
        logger.error("❌ Missing Telegram configuration")
        return
    
    telegram = TelegramNotifier(telegram_token, telegram_chat)
    model_path = f"storage/models/{args.model}"
    
    if not Path(model_path).exists():
        logger.error(f"❌ Model not found: {model_path}")
        return
    
    try:
        trader = MasterLiveTrader(config, model_path, telegram)
        trader.run(args.symbol, args.interval)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        telegram.send_error(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
