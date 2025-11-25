"""
MASTER SCALPER - BTC [V6.0 SIMPLIFICADO - CORREÇÕES TÉCNICAS]

✅ V6.0 - CORREÇÕES TÉCNICAS:
   🔴 Symbol como parâmetro do construtor
   🔴 fetch_market_meta() com tick correto para BTC (0.1)
   🔴 Validações de segurança completas
   🔴 Retry logic com exponential backoff
   🔴 Arredondamento correto (Decimal)

✅ LÓGICA SIMPLES (mantida):
   - Apenas SL + TP1
   - Gerenciamento 100% pela Bybit
   - Bot só monitora se posição fechou
   - Rate limit: espera 10s entre requisições
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
from core.risk import RiskManager

logger = None

# ======== EXECUTION HELPERS: tick/step rounding + fetch_market_meta ========
from decimal import Decimal, ROUND_DOWN, getcontext
getcontext().prec = 28

def _to_decimal(x):
    try:
        return Decimal(str(x))
    except:
        return Decimal(0)

def round_to_step(value: float, step: float) -> float:
    step_d = _to_decimal(step)
    if step_d <= 0:
        return float(value)
    v = _to_decimal(value)
    q = (v // step_d) * step_d
    return float(q)

def round_price(value: float, tick: float) -> float:
    return round_to_step(value, tick)

def round_qty(value: float, step: float, min_qty: float) -> float:
    q = round_to_step(value, step)
    if q < min_qty:
        q = _to_decimal(min_qty)
    return float(q)

def fetch_market_meta(rest, symbol: str):
    """
    Fetch tickSize, qtyStep, minOrderQty from instruments. Fallbacks if API unavailable.
    Usa valores hardcoded otimizados para ETHUSDT/BTCUSDT se API falhar.
    """
    # Valores padrão otimizados por símbolo
    if 'ETH' in symbol:
        tick = 0.01    # ETHUSDT tick size
        step = 0.01    # ETHUSDT qty step (0.01 ETH)
        min_qty = 0.01 # Mínimo 0.01 ETH
    elif 'BTC' in symbol:
        tick = 0.1     # BTCUSDT tick size
        step = 0.001   # BTCUSDT qty step (0.001 BTC)
        min_qty = 0.001 # Mínimo 0.001 BTC
    else:
        tick = 0.01
        step = 0.01
        min_qty = 0.01

    try:
        # Usa o método correto do BybitRESTClient (verificado em core/bybit_rest.py:184)
        meta = rest.get_instruments_info(symbol=symbol)

        if meta and meta.get('retCode') == 0:
            lst = meta.get('result', {}).get('list', [])
            if lst:
                info = lst[0]
                if 'priceFilter' in info and 'tickSize' in info['priceFilter']:
                    tick = float(info['priceFilter']['tickSize'])
                if 'lotSizeFilter' in info:
                    lf = info['lotSizeFilter']
                    if 'qtyStep' in lf:
                        step = float(lf['qtyStep'])
                    if 'minOrderQty' in lf:
                        min_qty = float(lf['minOrderQty'])
                logger.info(f"✅ Market meta via API: tick={tick}, step={step}, min_qty={min_qty}")
        else:
            retMsg = meta.get('retMsg', 'Unknown error') if meta else 'No response'
            logger.warning(f'⚠️ API retornou erro: {retMsg}. Usando fallback.')
    except AttributeError as e:
        logger.warning(f'⚠️ Método get_instruments_info não disponível: {e}. Usando fallback.')
    except Exception as e:
        logger.warning(f'⚠️ fetch_market_meta usando fallback ({e.__class__.__name__}: {e})')

    return tick, step, min_qty

def retry_with_backoff(func, max_retries: int = 3, initial_delay: float = 1.0, max_delay: float = 16.0):
    """
    Executa função com retry exponential backoff
    Args:
        func: Função a executar (sem argumentos)
        max_retries: Número máximo de tentativas
        initial_delay: Delay inicial em segundos
        max_delay: Delay máximo em segundos
    Returns:
        Resultado da função ou None se falhar
    """
    delay = initial_delay
    last_error = None

    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.warning(f"Tentativa {attempt + 1}/{max_retries} falhou: {e}. Retry em {delay}s...")
                time.sleep(delay)
                delay = min(delay * 2, max_delay)
            else:
                logger.error(f"Todas as {max_retries} tentativas falharam: {last_error}")

    return None


STATE_FILE = "storage/bot_state_btc.json"

# Rate limiting
MIN_REQUEST_INTERVAL = 10  # 10 segundos entre requisições de dados

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
            if logger:
                logger.error(f"Telegram error: {e}")
            return False

    def send_trade_open(self, trade: Dict):
        direction_emoji = "🟢" if trade['direction'] == 'long' else "🔴"
        mode = "📝 PAPER" if trade.get('is_paper', False) else "💰 REAL"

        message = f"""{direction_emoji} NOVA OPERAÇÃO {mode}

Direção: {trade['direction'].upper()}
Entrada: ${trade['entry_price']:,.1f}
Tamanho: {trade.get('qty', 'N/A')} BTC (${trade.get('size', 0):,.2f})
Confiança ML: {trade['ml_confidence']*100:.1f}%

🛑 SL: ${trade['stop_loss']:,.1f}
🎯 TP1: ${trade['tp1']:,.1f}

Order ID: {trade.get('order_id', 'N/A')}"""
        self.send_message(message)

    def send_trade_close(self, trade: Dict, pnl_amount: float, pnl_pct: float):
        result = "✅" if pnl_amount > 0 else "❌"
        mode = "📝 PAPER" if trade.get('is_paper', False) else "💰 REAL"

        reason_map = {
            'stop_loss': '🛑 Stop Loss',
            'take_profit_1': '🎯 TP1',
            'trailing_stop': '📈 Trailing Stop'
        }
        reason_display = reason_map.get(trade['exit_reason'], trade['exit_reason'])

        message = f"""{result} FECHADO {mode}

Direção: {trade['direction'].upper()}
Entrada: ${trade['entry_price']:,.1f}
Saída: ${trade['exit_price']:,.1f}

💰 PnL: ${pnl_amount:+,.2f} ({pnl_pct:+.2f}%)
📌 Motivo: {reason_display}"""
        self.send_message(message)

    def send_error(self, error_msg: str):
        message = f"""⚠️ ERRO

{error_msg}"""
        self.send_message(message)

    def send_status(self, stats: Dict):
        message = f"""📊 STATUS BTC

Trades: {stats['total_trades']}
Win Rate: {stats['win_rate']:.1f}%
PnL Total: ${stats['total_pnl']:+,.2f}
PnL Médio: ${stats['avg_pnl']:+,.2f}"""
        self.send_message(message)


def create_advanced_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add MASTER TRADER advanced features"""
    df_features = df.copy()

    for period in [3, 5, 8, 13, 21]:
        df_features[f'momentum_{period}'] = df_features['close'].pct_change(period) * 100
        df_features[f'volume_ratio_{period}'] = df_features['volume'] / df_features['volume'].rolling(period).mean()

    if 'ema50' in df_features.columns and 'ema200' in df_features.columns:
        df_features['trend_strength'] = (df_features['ema50'] - df_features['ema200']) / df_features['ema200'] * 100

    if 'atr' in df_features.columns:
        df_features['volatility_regime'] = df_features['atr'] / df_features['atr'].rolling(50).mean()

    df_features['price_position'] = ((df_features['close'] - df_features['low'].rolling(20).min()) /
                                      (df_features['high'].rolling(20).max() - df_features['low'].rolling(20).min())).fillna(0.5)

    df_features['volume_momentum'] = df_features['volume'].pct_change(5)
    df_features['price_acceleration'] = df_features['close'].diff(2) - df_features['close'].diff(1)

    return df_features


class MasterLiveTrader:
    def __init__(self, config: dict, model_path: str, telegram: TelegramNotifier, symbol: str = 'BTCUSDT'):
        self.config = config
        self.symbol = symbol
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
        self.min_confidence = float(os.getenv('MIN_ML_CONFIDENCE', '0.25'))

        # PAPER MODE CHECK
        self.paper_mode = os.getenv('PAPER_MODE', 'true').lower() == 'true'

        logger.info("="*70)
        logger.info("📋 CONFIGURAÇÕES - BTC [V6.0 SIMPLIFICADO + CORREÇÕES]")
        logger.info("="*70)
        logger.info(f"Símbolo: {self.symbol}")
        logger.info(f"Modelo: {self.model_path.name}")
        logger.info(f"Features: {len(self.feature_names)}")
        logger.info(f"Capital Inicial: ${self.initial_capital:,.2f}")
        logger.info(f"Risco por Trade: {self.risk_per_trade:.2%}")
        logger.info(f"MIN_ML_CONFIDENCE: {self.min_confidence:.2%}")
        logger.info(f"PAPER MODE: {'✅ ENABLED' if self.paper_mode else '❌ DISABLED (REAL!)'}")
        logger.info(f"✅ Apenas SL + TP1 (sem TP2/TP3)")
        logger.info(f"✅ Gerenciamento pela Bybit")
        logger.info(f"✅ Rate limit: {MIN_REQUEST_INTERVAL}s")
        logger.info(f"✅ V6.0: Validações + Retry + Arredondamento correto")
        logger.info("="*70)

        self.position = None
        self.capital = self.initial_capital
        self.trades_history = []
        self.cooldown_until = 0
        self.last_price = None
        self.last_analyzed_candle_time = None  # 🔥 FIX: Track last analyzed candle to prevent duplicate analysis

        self.bybit_testnet = os.getenv('BYBIT_TESTNET', 'true').lower() == 'true'
        self.rest_client = BybitRESTClient(
            api_key=os.getenv('BYBIT_API_KEY'),
            api_secret=os.getenv('BYBIT_API_SECRET'),
            testnet=self.bybit_testnet
        )

        # ✅ V7.0: RiskManager com circuit breakers
        self.risk_manager = RiskManager({
            'initial_capital': self.initial_capital,
            'risk_per_trade': self.risk_per_trade,
            'circuit_breaker_max_loss_pct': float(os.getenv('MAX_DAILY_LOSS_PCT', '5.0')),
            'circuit_breaker_consec_losses': int(os.getenv('MAX_CONSEC_LOSSES', '3')),
            'max_trades_per_day': int(os.getenv('MAX_TRADES_PER_DAY', '5')),
            'cooldown_min': int(os.getenv('COOLDOWN_MIN', '30')),
            'max_positions': 1,
            'fees_taker': 0.0006,
            'max_order_value_usdt': 10000
        })

        # ✅ Busca market meta (tick_size, qty_step, min_qty)
        try:
            self.tick_size, self.qty_step, self.min_qty = fetch_market_meta(self.rest_client, self.symbol)
        except Exception as e:
            logger.warning(f"⚠️ Erro ao buscar market meta: {e}. Usando fallback.")
            # Fallback específico para BTCUSDT
            self.tick_size = 0.1
            self.qty_step = 0.001
            self.min_qty = 0.001

        self.dm = DataManager(self.rest_client)
        self.fs = FeatureStore(config)

        mode = 'TESTNET' if self.bybit_testnet else 'MAINNET'
        logger.info(f"✅ Bot inicializado ({mode})")

        if not self.paper_mode and not self.bybit_testnet:
            logger.warning("⚠️" * 20)
            logger.warning("⚠️ REAL TRADING MODE!")
            logger.warning("⚠️" * 20)

    def save_state(self):
        state = {
            'capital': self.capital,
            'position': self.position,
            'trades_history': self.trades_history,
            'cooldown_until': self.cooldown_until or 0,
            'last_price': self.last_price
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
                logger.warning("State too old - ignored")
                return

            self.capital = state.get('capital', self.initial_capital)
            self.trades_history = state.get('trades_history', [])
            self.cooldown_until = state.get('cooldown_until', 0)
            self.position = state.get('position')
            self.last_price = state.get('last_price')

            if self.position:
                logger.info(f"🔄 Recovered {self.position['direction']} @ ${self.position['entry_price']:,.2f}")

        except Exception as e:
            logger.warning(f"Recover failed: {e}")

    def health_check(self) -> bool:
        """✅ V7.0: Verifica saúde do sistema antes de operar"""
        try:
            start = time.time()
            server_time = self.rest_client.get_server_time()
            latency_ms = (time.time() - start) * 1000

            if latency_ms > 500:
                logger.warning(f"⚠️ Alta latência: {latency_ms:.0f}ms")
                return False

            server_ts = int(server_time.get('result', {}).get('timeSecond', 0))
            clock_diff = abs(server_ts - int(time.time()))

            if clock_diff > 5:
                logger.error(f"❌ Clock desync: {clock_diff}s")
                return False

            balance = self.rest_client.get_wallet_balance()
            if not balance.get('result'):
                logger.error("❌ Erro ao buscar balance")
                return False

            logger.info(f"✅ Health Check OK (latência: {latency_ms:.0f}ms)")
            return True
        except Exception as e:
            logger.error(f"❌ Health check falhou: {e}")
            return False

    def reconcile_positions_on_startup(self):
        """✅ V7.0: Sincroniza posições bot vs exchange"""
        logger.info("🔄 Reconciliando posições com Bybit...")
        try:
            positions = self.rest_client.get_positions(symbol=self.symbol)
            positions_list = positions.get('result', {}).get('list', [])

            active_pos = None
            for pos in positions_list:
                if float(pos.get('size', 0)) > 0:
                    active_pos = pos
                    break

            if active_pos and not self.position:
                logger.warning("⚠️ Posição no exchange mas não no bot - sincronizando...")
                self.position = {
                    'direction': active_pos.get('side', '').lower(),
                    'entry_price': float(active_pos.get('avgPrice', 0)),
                    'qty': float(active_pos.get('size', 0)),
                    'symbol': self.symbol,
                    'is_live': not self.paper_mode
                }
                self.save_state()
                logger.info("✅ Sincronizado")
            elif not active_pos and self.position:
                logger.warning("⚠️ Bot tem posição mas exchange não - limpando...")
                self.position = None
                self.save_state()
                logger.info("✅ Limpo")
            else:
                logger.info("✅ Sincronizado")
        except Exception as e:
            logger.error(f"❌ Reconciliação falhou: {e}")

    def get_session_stats(self):
        """✅ V7.0: Métricas consolidadas"""
        if not self.risk_manager.trade_history:
            logger.info("📊 Nenhum trade nesta sessão")
            return

        stats = self.risk_manager.get_risk_stats()
        logger.info("="*70)
        logger.info(f"📊 Capital: ${stats['equity']:,.2f} | DD: {stats['current_drawdown']:.2f}%")
        logger.info(f"   Trades: {stats['total_trades']} | WR: {stats['win_rate']*100:.1f}%")
        logger.info(f"   PnL: ${stats['total_pnl']:+,.2f} | Fees: ${stats['total_fees']:,.2f}")
        if stats['is_halted']:
            logger.warning(f"🚨 HALTED: {stats['halt_reason']}")
        logger.info("="*70)

    def get_current_data(self, symbol: str, timeframe: str = '15m', lookback_days: int = 30) -> pd.DataFrame:
        """
        ✅ V5: Com retry e tratamento de rate limit
        """
        max_retries = 3
        retry_delay = 15  # 15 segundos entre retries

        for attempt in range(max_retries):
            try:
                df = self.dm.get_data(symbol, timeframe, lookback_days, use_cache=False)

                if df.empty:
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠️ Empty data - retry {attempt+1}/{max_retries} in {retry_delay}s")
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise ValueError("No data after retries")

                df = self.fs.build_features(df, normalize=False)
                df = create_advanced_features(df)
                return df

            except Exception as e:
                if "Rate Limit" in str(e) or "Too many visits" in str(e):
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠️ Rate limit hit - waiting {retry_delay}s")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error("❌ Rate limit - max retries reached")
                        raise
                else:
                    logger.error(f"❌ Data fetch error: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise

        raise ValueError("Failed to fetch data")

    def get_signal(self, df: pd.DataFrame) -> tuple:
        try:
            # 🔥 FIX: Use CLOSED candle (iloc[-2]) not incomplete candle (iloc[-1])
            latest = df.iloc[-2]
            X = df[self.feature_names].fillna(0).iloc[-2:-1].values

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
            return 0, 0.0, df.iloc[-2]  # 🔥 FIX: Use closed candle

    def calculate_position_size(self, price: float, sl_price: float) -> float:
        """Calcula quantidade de BTC baseado no risco"""
        sl_dist = abs((sl_price - price) / price)
        risk_amt = self.capital * self.risk_per_trade

        qty_btc = (risk_amt / sl_dist) / price if sl_dist > 0 else 0.001
        qty_btc = max(0.001, round(qty_btc, 3))

        return qty_btc

    def open_position(self, symbol: str, signal: int, current_data: pd.Series, ml_confidence: float):
        direction = 'long' if signal == 1 else 'short'
        price = current_data['close']
        atr = current_data.get('atr', price * 0.01)

        # Calcula SL e TP1
        if direction == 'long':
            sl = price - (atr * 2)
            tp1 = price + (atr * 1)
            side = 'Buy'
        else:
            sl = price + (atr * 2)
            tp1 = price - (atr * 1)
            side = 'Sell'

        qty_btc = self.calculate_position_size(price, sl)

        # ✅ Arredondamento correto usando market meta
        tick = getattr(self, 'tick_size', 0.1)
        step = getattr(self, 'qty_step', 0.001)
        min_qty = getattr(self, 'min_qty', 0.001)

        sl = round_price(sl, tick)
        tp1 = round_price(tp1, tick)
        qty_btc = round_qty(qty_btc, step, min_qty)
        price = round_price(price, tick)
        size_usd = qty_btc * price

        # ✅ VALIDAÇÕES DE SEGURANÇA
        if qty_btc < min_qty:
            logger.error(f"❌ Quantidade {qty_btc} BTC menor que mínimo {min_qty}!")
            return

        if size_usd < 10:
            logger.warning(f"⚠️ Tamanho muito pequeno: ${size_usd:,.2f} < $10")
            return

        # Valida que SL faz sentido
        if direction == 'long' and sl >= price:
            logger.error(f"❌ SL inválido para LONG: ${sl:,.2f} >= ${price:,.2f}")
            return
        if direction == 'short' and sl <= price:
            logger.error(f"❌ SL inválido para SHORT: ${sl:,.2f} <= ${price:,.2f}")
            return

        # Valida que TP1 faz sentido
        if direction == 'long' and tp1 <= price:
            logger.error(f"❌ TP1 inválido para LONG: ${tp1:,.2f} <= ${price:,.2f}")
            return
        if direction == 'short' and tp1 >= price:
            logger.error(f"❌ TP1 inválido para SHORT: ${tp1:,.2f} >= ${price:,.2f}")
            return

        logger.info(f"📊 Position: {qty_btc} BTC = ${size_usd:,.2f}")
        logger.info(f"✅ Validações de segurança: OK")

        order_id = None
        actual_entry_price = price
        is_paper = self.paper_mode

        if not self.paper_mode:
            try:
                logger.info(f"💰 Sending REAL {side} order...")

                order = self.rest_client.place_order(
                    symbol=symbol,
                    side=side,
                    order_type='Market',
                    qty=qty_btc
                )

                logger.info(f"📥 API Response: {order}")

                if order and 'retCode' in order and order['retCode'] == 0:
                    if 'result' in order and isinstance(order['result'], dict):
                        result = order['result']

                        if 'orderId' in result:
                            order_id = result['orderId']
                            logger.info(f"✅ Order executed! ID: {order_id}")

                            if 'price' in result and result['price']:
                                try:
                                    actual_entry_price = float(result['price'])
                                except:
                                    actual_entry_price = price

                        # ✅ CONFIGURA SL + TP1 com retry
                        logger.info(f"📍 Setting SL/TP1...")
                        logger.info(f"   SL: ${sl:,.1f} | TP1: ${tp1:,.1f}")

                        # ⏳ Aguarda posição ser criada no exchange (critical fix!)
                        logger.info("⏳ Aguardando posição ser criada no exchange...")
                        time.sleep(3)  # 3 segundos para Bybit processar

                        # Verifica se posição foi criada
                        position_exists = False
                        try:
                            positions = self.rest_client.get_positions(symbol=symbol)
                            positions_list = positions.get('result', {}).get('list', [])
                            for pos in positions_list:
                                if float(pos.get('size', 0)) > 0:
                                    position_exists = True
                                    logger.info(f"✅ Posição confirmada: {pos.get('size')} BTC")
                                    break
                        except Exception as e:
                            logger.warning(f"⚠️ Erro ao verificar posição: {e}")

                        if not position_exists:
                            logger.error(f"❌ Posição não foi criada - não é possível configurar SL/TP!")
                        else:
                            def _set_sl_tp():
                                sl_tp_result = self.rest_client.set_trading_stop(
                                    category='linear',
                                    symbol=symbol,
                                    stopLoss=str(sl),
                                    takeProfit=str(tp1),
                                    positionIdx=0
                                )

                                if sl_tp_result and 'retCode' in sl_tp_result and sl_tp_result['retCode'] == 0:
                                    logger.info(f"✅ SL/TP1 configured!")
                                    return True
                                else:
                                    error_msg = sl_tp_result.get('retMsg', 'Unknown') if sl_tp_result else 'No response'
                                    raise Exception(f"API error: {error_msg}")

                            result = retry_with_backoff(_set_sl_tp, max_retries=3, initial_delay=2.0)
                            if not result:
                                logger.error(f"❌ Failed to set SL/TP after retries!")

                else:
                    raise Exception("API error")

            except Exception as e:
                logger.error(f"❌ Failed order: {e}")
                self.telegram.send_error(f"Failed: {e}")
                return

        # Salva posição
        self.position = {
            'symbol': symbol,
            'direction': direction,
            'entry_price': actual_entry_price,
            'entry_time': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'qty': qty_btc,
            'size': size_usd,
            'stop_loss': sl,
            'tp1': tp1,
            'ml_confidence': ml_confidence,
            'order_id': order_id,
            'is_paper': is_paper
        }

        self.last_price = price

        mode_str = "📝 PAPER" if is_paper else "💰 REAL"
        logger.info(f"🟢 OPENED {direction.upper()} {mode_str} @ ${actual_entry_price:,.1f}")
        logger.info(f"   Qty: {qty_btc} BTC | Size: ${size_usd:,.2f}")
        logger.info(f"   SL: ${sl:,.1f} | TP1: ${tp1:,.1f}")
        logger.info(f"   ML Confidence: {ml_confidence:.1%}")

        # 📊 Busca detalhes de execução real (preço médio, fees, slippage)
        if not is_paper and order_id:
            try:
                time.sleep(0.5)  # Aguarda ordem ser processada
                order_history = self.rest_client.get_order_history(
                    symbol=symbol,
                    order_id=order_id,
                    limit=1
                )

                if order_history and 'result' in order_history:
                    orders_list = order_history['result'].get('list', [])
                    if orders_list and len(orders_list) > 0:
                        order_info = orders_list[0]
                        avg_price = float(order_info.get('avgPrice', 0))
                        cum_exec_fee = float(order_info.get('cumExecFee', 0))
                        cum_exec_qty = float(order_info.get('cumExecQty', 0))

                        if avg_price > 0:
                            # Calcula slippage
                            expected_price = price
                            slippage_abs = avg_price - expected_price
                            slippage_pct = (slippage_abs / expected_price) * 100

                            # Calcula fee rate
                            exec_value = avg_price * cum_exec_qty
                            fee_rate = (cum_exec_fee / exec_value * 100) if exec_value > 0 else 0

                            logger.info(f"📊 EXECUTION DETAILS:")
                            logger.info(f"   Expected: ${expected_price:,.1f} | Filled: ${avg_price:,.1f}")
                            logger.info(f"   Slippage: ${slippage_abs:+,.1f} ({slippage_pct:+.3f}%)")
                            logger.info(f"   Fees: ${cum_exec_fee:.4f} USDT ({fee_rate:.4f}%)")

            except Exception as e:
                logger.warning(f"⚠️ Could not fetch execution details: {e}")

        try:
            self.telegram.send_trade_open(self.position)
        except Exception as e:
            logger.error(f"Telegram failed: {e}")

        self.save_state()

    def check_position_closed(self) -> Optional[tuple]:
        """
        ✅ V5: Verifica se Bybit fechou a posição
        Não fecha localmente - apenas detecta
        """
        if not self.position or self.position.get('is_paper', True):
            return None

        try:
            positions = self.rest_client.get_positions(symbol=self.position['symbol'])

            if positions and 'retCode' in positions and positions['retCode'] == 0:
                if 'result' in positions and 'list' in positions['result']:
                    pos_list = positions['result']['list']

                    for pos in pos_list:
                        if pos['symbol'] == self.position['symbol']:
                            size = float(pos.get('size', 0))

                            # Posição ainda aberta
                            if size > 0:
                                # Atualiza last_price
                                mark_price = float(pos.get('markPrice', 0))
                                if mark_price > 0:
                                    self.last_price = mark_price
                                return None

                            # Posição fechada
                            else:
                                logger.info("✅ Posição fechada pela Bybit")

                                # Usa last_price como exit_price
                                exit_price = self.last_price if self.last_price else self.position['entry_price']

                                # Determina motivo
                                entry = self.position['entry_price']
                                direction = self.position['direction']
                                sl = self.position['stop_loss']
                                tp1 = self.position['tp1']

                                tolerance = entry * 0.001

                                if abs(exit_price - sl) <= tolerance:
                                    reason = 'stop_loss'
                                elif abs(exit_price - tp1) <= tolerance:
                                    reason = 'take_profit_1'
                                else:
                                    if direction == 'long':
                                        reason = 'stop_loss' if exit_price < entry else 'take_profit_1'
                                    else:
                                        reason = 'stop_loss' if exit_price > entry else 'take_profit_1'

                                logger.info(f"✅ Exit: ${exit_price:,.2f} ({reason})")
                                return (exit_price, reason)

                    # Posição não encontrada = foi fechada
                    logger.info("✅ Posição não encontrada - fechada")
                    exit_price = self.last_price if self.last_price else self.position['tp1']
                    return (exit_price, 'take_profit_1')

        except Exception as e:
            logger.error(f"⚠️ Erro ao verificar posição: {e}")
            return None

    def close_position(self, exit_price: float, reason: str):
        if not self.position:
            return

        entry = self.position['entry_price']
        direction = self.position['direction']
        qty = self.position['qty']

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
            'qty': qty,
            'size': self.position['size'],
            'pnl_pct': pnl_pct,
            'pnl_amount': pnl_amount,
            'exit_reason': reason,
            'ml_confidence': self.position['ml_confidence'],
            'is_paper': self.position.get('is_paper', True)
        }

        self.trades_history.append(trade)

        result = "✅" if pnl_amount > 0 else "❌"
        mode_str = "📝 PAPER" if trade['is_paper'] else "💰 REAL"
        logger.info(f"{result} CLOSED {direction.upper()} {mode_str}")
        logger.info(f"   ${entry:,.2f} → ${exit_price:,.2f}")
        logger.info(f"   PnL: ${pnl_amount:+,.2f} ({pnl_pct:+.2f}%)")

        try:
            self.telegram.send_trade_close(trade, pnl_amount, pnl_pct)
        except Exception as e:
            logger.error(f"Telegram failed: {e}")

        self.position = None
        self.last_price = None
        self.cooldown_until = time.time() + (30 * 60)
        self.save_state()

    def get_stats(self) -> Dict:
        if not self.trades_history:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0
            }

        df = pd.DataFrame(self.trades_history)
        total = len(df)
        wins = len(df[df['pnl_amount'] > 0])
        win_rate = wins / total * 100
        total_pnl = df['pnl_amount'].sum()
        avg_pnl = total_pnl / total if total > 0 else 0

        return {
            'total_trades': total,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl
        }

    def run(self, symbol: str, check_interval: int = 30):
        """Main loop"""
        mode_str = "📝 PAPER MODE" if self.paper_mode else "💰 REAL TRADING"
        network_str = "TESTNET" if self.bybit_testnet else "MAINNET"
        logger.info(f"🚀 MASTER SCALPER BOT - BTC [V7.0 PRODUCTION GRADE] ({mode_str} - {network_str})")

        self.telegram.send_message(f"""🤖 BOT BTC INICIADO [V7.0 - PRODUCTION GRADE]

Símbolo: {self.symbol}
Modo: {mode_str} ({network_str})
🎯 Confidence Min: {self.min_confidence:.0%}
💰 Risco/Trade: {self.risk_per_trade:.1%}
⏱️ Loop: {check_interval}s

📊 Estratégia:
• SL: 2.0x ATR
• TP1: 1.0x ATR (gerenciado pela Bybit)

✅ V7.0: RiskManager + Health Check + Reconcile + Circuit Breakers
✅ Validações + Retry logic + Rate limit""")

        # ✅ V7.0: Health check no startup
        if not self.health_check():
            logger.error("❌ Health check falhou - abortando")
            return

        self.recover_state()

        # ✅ V7.0: Reconciliação de posições
        self.reconcile_positions_on_startup()

        iteration_count = 0
        last_status_time = time.time()
        last_request_time = 0

        try:
            while True:
                try:
                    now = time.time()

                    # ✅ Rate limit: espera mínimo entre requisições
                    if now - last_request_time < MIN_REQUEST_INTERVAL:
                        sleep_time = MIN_REQUEST_INTERVAL - (now - last_request_time)
                        logger.info(f"⏳ Rate limit: waiting {sleep_time:.1f}s")
                        time.sleep(sleep_time)
                        continue

                    iteration_count += 1
                    logger.info("="*70)
                    logger.info(f"🔄 ITERATION #{iteration_count} - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
                    logger.info("="*70)

                    start_time = time.time()
                    df = self.get_current_data(symbol, '15m', 30)
                    last_request_time = time.time()

                    if df.empty:
                        logger.warning("⚠️ No data")
                        time.sleep(check_interval)
                        continue

                    fetch_time = time.time() - start_time

                    # 🔥 FIX: Use CLOSED candle (iloc[-2]) not incomplete candle (iloc[-1])
                    current = df.iloc[-2]
                    current_candle_time = current.name
                    price = current['close']

                    # 🔥 FIX: Skip if already analyzed this candle
                    if self.last_analyzed_candle_time and current_candle_time == self.last_analyzed_candle_time:
                        logger.info(f"⏭️ Mesmo candle ({current_candle_time}) - aguardando novo candle")
                        time.sleep(check_interval)
                        continue

                    # 🔥 NEW: Wait for API consolidation when new candle detected
                    # This ensures we get EXACT same data as backtest (complete candle)
                    logger.info(f"🆕 Novo candle detectado: {current_candle_time}")
                    logger.info(f"⏳ Aguardando 10s para API consolidar dados...")
                    time.sleep(10)

                    # Re-download data to get fully consolidated candle
                    logger.info(f"📥 Re-baixando dados para garantir candle consolidado...")
                    start_time_refetch = time.time()
                    df = self.get_current_data(symbol, '15m', 30)
                    fetch_time = time.time() - start_time_refetch

                    if df.empty:
                        logger.warning("⚠️ No data on re-fetch")
                        time.sleep(check_interval)
                        continue

                    # Get the SAME candle again (now fully consolidated)
                    current = df.iloc[-2]
                    new_candle_time = current.name

                    # Verify we got the same candle (sanity check)
                    if new_candle_time != current_candle_time:
                        logger.warning(f"⚠️ Candle mudou após re-fetch: {current_candle_time} → {new_candle_time}")
                        current_candle_time = new_candle_time

                    price = current['close']

                    if self.position:
                        self.last_price = price

                    logger.info(f"📊 Price: ${price:,.2f} | Candle: {current_candle_time} | Fetch: {fetch_time:.1f}s")

                    if self.position:
                        entry = self.position['entry_price']
                        direction = self.position['direction']

                        if direction == 'long':
                            pnl_pct = ((price - entry) / entry) * 100
                        else:
                            pnl_pct = ((entry - price) / entry) * 100

                        pnl_usd = self.position['size'] * (pnl_pct / 100)
                        logger.info(f"🟢 {direction.upper()} @ ${entry:,.2f} | PnL: ${pnl_usd:+,.2f} ({pnl_pct:+.2f}%)")

                        # ✅ Apenas VERIFICA se fechou (não fecha localmente)
                        closed = self.check_position_closed()
                        if closed:
                            exit_price, reason = closed
                            self.close_position(exit_price, reason)

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

                            logger.info(f"🎯 Signal: {sig_name} | Conf: {ml_confidence:.2%} | {status}")

                            # 🔥 FIX: Mark this candle as analyzed
                            self.last_analyzed_candle_time = current_candle_time

                            if signal != 0 and passes:
                                logger.info("="*70)
                                logger.info(f"🚨 OPENING {sig_name} POSITION")
                                logger.info("="*70)

                                try:
                                    self.open_position(symbol, signal, current_data, ml_confidence)
                                except Exception as e:
                                    logger.error(f"❌ Failed: {e}")
                                    import traceback
                                    traceback.print_exc()
                                    self.telegram.send_error(f"Failed: {e}")

                    if time.time() - last_status_time > (4 * 3600):
                        self.telegram.send_status(self.get_stats())
                        last_status_time = time.time()

                    time.sleep(check_interval)

                except Exception as e:
                    logger.error(f"❌ Loop error: {e}")
                    import traceback
                    traceback.print_exc()
                    time.sleep(check_interval if 'check_interval' in locals() else 30)

        except KeyboardInterrupt:
            logger.info("\n⏹️ Bot stopped")
            if self.position:
                logger.info("⚠️ Posição aberta - será gerenciada pela Bybit")

            stats = self.get_stats()
            logger.info(f"📊 Stats: {stats['total_trades']} trades | WR: {stats['win_rate']:.1f}% | PnL: ${stats['total_pnl']:+,.2f}")
            self.telegram.send_status(stats)


def main():
    global logger

    parser = argparse.ArgumentParser(description='MASTER SCALPER - BTC [V6.0 SIMPLIFICADO + CORREÇÕES]')
    parser.add_argument('--symbol', default='BTCUSDT', help='Trading symbol')
    parser.add_argument('--model', default='ml_model_master_scalper_365d.pkl', help='Model filename')
    parser.add_argument('--interval', type=int, default=30, help='Check interval')

    args = parser.parse_args()
    config = load_config('standard')
    logger = setup_logging('INFO', log_to_file=True)

    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
    telegram_chat = os.getenv('TELEGRAM_CHAT_ID')

    if not telegram_token or not telegram_chat:
        logger.error("❌ Missing Telegram config")
        return

    telegram = TelegramNotifier(telegram_token, telegram_chat)

    model_path = f"storage/models/{args.model}"
    if not Path(model_path).exists():
        logger.error(f"❌ Model not found: {model_path}")
        return

    try:
        trader = MasterLiveTrader(config, model_path, telegram, symbol=args.symbol)
        trader.run(args.symbol, args.interval)

    except Exception as e:
        logger.error(f"❌ Fatal: {e}")
        import traceback
        traceback.print_exc()
        telegram.send_error(f"Fatal: {e}")


if __name__ == "__main__":
    main()
