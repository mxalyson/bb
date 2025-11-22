"""
🤖 LIVE TRADING BOT - SNIPER MODE
Baseado na análise de otimização do 1.py
"""

import sys
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')
sys.path.append(str(Path(__file__).parent))

import pandas as pd
import numpy as np
import logging
import pickle
import time
import requests
import json
from datetime import datetime, timedelta
from typing import Dict, Optional
from pathlib import Path as PathLib
import os
from dotenv import load_dotenv

from core.utils import load_config, setup_logging
from core.bybit_rest import BybitRESTClient
from core.data import DataManager
from core.features import FeatureStore
from decimal import Decimal, ROUND_DOWN, getcontext

# Load environment variables
load_dotenv()

logger = None
getcontext().prec = 28


# ============================================================================
# BYBIT HELPERS (tick/step rounding + market meta)
# ============================================================================

def _to_decimal(x):
    """Convert to Decimal safely."""
    try:
        return Decimal(str(x))
    except:
        return Decimal(0)


def round_to_step(value: float, step: float) -> float:
    """Round value to step size."""
    step_d = _to_decimal(step)
    if step_d <= 0:
        return float(value)
    v = _to_decimal(value)
    q = (v // step_d) * step_d
    return float(q)


def round_price(value: float, tick: float) -> float:
    """Round price to tick size."""
    return round_to_step(value, tick)


def round_qty(value: float, step: float, min_qty: float) -> float:
    """Round quantity to step size, ensuring minimum."""
    q = round_to_step(value, step)
    if q < min_qty:
        q = _to_decimal(min_qty)
    return float(q)


def fetch_market_meta(rest_client, symbol: str):
    """
    Fetch tickSize, qtyStep, minOrderQty from exchange.
    Fallbacks for BTCUSDT/ETHUSDT if API fails.
    """
    # Default values by symbol
    if 'ETH' in symbol:
        tick = 0.01
        step = 0.01
        min_qty = 0.01
    elif 'BTC' in symbol:
        tick = 0.1
        step = 0.001
        min_qty = 0.001
    else:
        tick = 0.01
        step = 0.01
        min_qty = 0.01

    try:
        meta = rest_client.get_instruments_info(symbol=symbol)

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
                logger.info(f"   ✅ Market meta: tick={tick}, step={step}, min_qty={min_qty}")
        else:
            logger.warning(f"   ⚠️ API error, using fallback")
    except Exception as e:
        logger.warning(f"   ⚠️ fetch_market_meta error: {e}, using fallback")

    return tick, step, min_qty


def retry_with_backoff(func, max_retries: int = 3, initial_delay: float = 1.0):
    """Execute function with exponential backoff retry."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"   Retry {attempt + 1}/{max_retries} failed: {e}. Waiting {delay}s...")
                time.sleep(delay)
                delay = min(delay * 2, 16.0)
            else:
                logger.error(f"   All {max_retries} retries failed: {e}")
    return None


# ============================================================================
# TELEGRAM NOTIFICATIONS
# ============================================================================

class TelegramNotifier:
    """Send notifications to Telegram with interactive commands support."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        self.last_update_id = 0  # Track last processed update
        self.bot_instance = None  # Reference to TradingBot for commands

        if self.enabled:
            logger.info("📱 Telegram notifications: ENABLED")
            logger.info("📱 Telegram commands: ENABLED (/help para listar)")
        else:
            logger.warning("📱 Telegram notifications: DISABLED (missing credentials)")

    def set_bot_instance(self, bot_instance):
        """Set reference to TradingBot for command execution."""
        self.bot_instance = bot_instance

    def send(self, message: str):
        """Send message to Telegram."""
        if not self.enabled:
            return

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, data=data, timeout=10)

            if response.status_code != 200:
                logger.warning(f"Telegram error: {response.text}")
        except Exception as e:
            logger.error(f"Failed to send Telegram: {e}")

    def get_updates(self):
        """Get new updates from Telegram."""
        if not self.enabled:
            return []

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {
                "offset": self.last_update_id + 1,
                "timeout": 1,
                "allowed_updates": ["message"]
            }
            response = requests.get(url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    updates = data.get("result", [])
                    if updates:
                        self.last_update_id = updates[-1]["update_id"]
                    return updates
        except Exception as e:
            logger.debug(f"Error getting Telegram updates: {e}")

        return []

    def process_command(self, command: str, args: list):
        """Process Telegram command and return response."""
        if not self.bot_instance:
            return "❌ Bot not initialized"

        bot = self.bot_instance

        # Help command
        if command == "/help":
            return (
                "🤖 <b>Comandos Disponíveis:</b>\n\n"
                "<b>📊 Informações:</b>\n"
                "/status - Status geral do bot\n"
                "/position - Posição aberta atual\n"
                "/capital - Capital atual\n\n"
                "<b>⚙️ Controle:</b>\n"
                "/pause - Pausar bot (não abre novos trades)\n"
                "/resume - Retomar bot\n\n"
                "<b>🔧 Configuração:</b>\n"
                "/setconf &lt;0-100&gt; - Mudar confiança mínima (%)\n"
                "/setrisk &lt;0.1-2.0&gt; - Mudar risco por trade (%)"
            )

        # Status command
        elif command == "/status":
            mode = "🔵 DRY RUN" if bot.dry_run else "🔴 LIVE"
            network = "TESTNET" if bot.bybit_testnet else "MAINNET"
            paused = "⏸️ PAUSADO" if hasattr(bot, 'paused') and bot.paused else "▶️ ATIVO"

            return (
                f"🤖 <b>Status do Bot</b>\n\n"
                f"Estado: {paused}\n"
                f"Modo: {mode}\n"
                f"Network: {network}\n"
                f"Symbol: {bot.symbol}\n"
                f"Timeframe: {bot.timeframe}m\n\n"
                f"⚙️ Config:\n"
                f"Confiança Min: {bot.min_confidence*100:.0f}%\n"
                f"Risco/Trade: {bot.risk_per_trade*100:.2f}%\n"
                f"SL: {bot.sl_atr_mult}x ATR\n"
                f"TP: {bot.tp_atr_mult}x ATR\n"
                f"Cooldown: {bot.trade_cooldown/60:.0f}min"
            )

        # Position command
        elif command == "/position":
            if not bot.position:
                return "📭 Nenhuma posição aberta"

            pos = bot.position
            direction_emoji = "🟢" if pos['direction'] == 'long' else "🔴"

            # Calculate current PnL if we have last price
            if bot.last_price:
                if pos['direction'] == 'long':
                    pnl_pct = ((bot.last_price - pos['entry_price']) / pos['entry_price']) * 100
                else:
                    pnl_pct = ((pos['entry_price'] - bot.last_price) / pos['entry_price']) * 100

                pnl_usd = pos['size'] * (pnl_pct / 100)
                fee = pos['size'] * 0.00055 * 2
                pnl_net = pnl_usd - fee
                pnl_emoji = "🟢" if pnl_net > 0 else "🔴"
            else:
                pnl_emoji = "⚪"
                pnl_pct = 0
                pnl_net = 0

            duration = datetime.now() - pos['entry_time']
            hours = int(duration.total_seconds() / 3600)
            minutes = int((duration.total_seconds() % 3600) / 60)

            return (
                f"{direction_emoji} <b>Posição {pos['direction'].upper()}</b>\n\n"
                f"Entrada: ${pos['entry_price']:,.2f}\n"
                f"Atual: ${bot.last_price:,.2f}\n"
                f"Qtd: {pos['qty_btc']} BTC\n\n"
                f"{pnl_emoji} PnL: {pnl_pct:+.2f}% (${pnl_net:+,.2f})\n"
                f"Duração: {hours}h {minutes}m\n\n"
                f"🛑 SL: ${pos['stop_loss']:,.2f}\n"
                f"🎯 TP: ${pos['take_profit']:,.2f}\n"
                f"📊 Confiança: {pos.get('confidence', 0)*100:.0f}%"
            )

        # Capital command
        elif command == "/capital":
            return (
                f"💰 <b>Capital</b>\n\n"
                f"Atual: ${bot.capital:,.2f}\n"
                f"Inicial: ${bot.initial_capital:,.2f}\n"
                f"Variação: {((bot.capital/bot.initial_capital - 1)*100):+.2f}%"
            )

        # Pause command
        elif command == "/pause":
            if not hasattr(bot, 'paused'):
                bot.paused = False

            if bot.paused:
                return "⏸️ Bot já está pausado"

            bot.paused = True
            logger.info("⏸️ Bot pausado via Telegram")
            return "⏸️ <b>Bot Pausado</b>\n\nNão abrirá novos trades.\nPosições abertas continuam sendo monitoradas.\n\nUse /resume para retomar."

        # Resume command
        elif command == "/resume":
            if not hasattr(bot, 'paused'):
                bot.paused = False
                return "▶️ Bot já está ativo"

            if not bot.paused:
                return "▶️ Bot já está ativo"

            bot.paused = False
            logger.info("▶️ Bot retomado via Telegram")
            return "▶️ <b>Bot Retomado</b>\n\nVoltará a abrir trades conforme sinais."

        # Set confidence command
        elif command == "/setconf":
            if not args:
                return "❌ Uso: /setconf &lt;valor&gt;\n\nExemplo: /setconf 40"

            try:
                new_conf = float(args[0])
                if not (0 <= new_conf <= 100):
                    return "❌ Confiança deve estar entre 0 e 100"

                old_conf = bot.min_confidence * 100
                bot.min_confidence = new_conf / 100
                logger.info(f"⚙️ Confiança alterada via Telegram: {old_conf:.0f}% → {new_conf:.0f}%")

                return f"✅ <b>Confiança Atualizada</b>\n\n{old_conf:.0f}% → {new_conf:.0f}%"
            except ValueError:
                return "❌ Valor inválido. Use um número entre 0 e 100."

        # Set risk command
        elif command == "/setrisk":
            if not args:
                return "❌ Uso: /setrisk &lt;valor&gt;\n\nExemplo: /setrisk 0.75"

            try:
                new_risk = float(args[0])
                if not (0.1 <= new_risk <= 2.0):
                    return "❌ Risco deve estar entre 0.1 e 2.0"

                old_risk = bot.risk_per_trade * 100
                bot.risk_per_trade = new_risk / 100
                logger.info(f"⚙️ Risco alterado via Telegram: {old_risk:.2f}% → {new_risk:.2f}%")

                return f"✅ <b>Risco Atualizado</b>\n\n{old_risk:.2f}% → {new_risk:.2f}%"
            except ValueError:
                return "❌ Valor inválido. Use um número entre 0.1 e 2.0."

        else:
            return f"❌ Comando desconhecido: {command}\n\nUse /help para ver comandos disponíveis."

    def check_commands(self):
        """Check for new commands and process them."""
        if not self.enabled or not self.bot_instance:
            return

        updates = self.get_updates()

        for update in updates:
            if "message" in update and "text" in update["message"]:
                text = update["message"]["text"].strip()

                # Check if it's a command (starts with /)
                if text.startswith("/"):
                    parts = text.split()
                    command = parts[0].lower()
                    args = parts[1:] if len(parts) > 1 else []

                    logger.info(f"📱 Comando Telegram recebido: {command}")

                    # Process command and send response
                    response = self.process_command(command, args)
                    self.send(response)


# ============================================================================
# MODEL LOADING (from 1.py)
# ============================================================================

class ModelWrapper:
    """Generic wrapper for models saved with custom classes."""
    def __init__(self, model=None, feature_names=None, **kwargs):
        self.model = model
        self.feature_names = feature_names
        self.__dict__.update(kwargs)


class UniversalUnpickler(pickle.Unpickler):
    """Custom unpickler that can handle missing classes."""
    def find_class(self, module, name):
        if name == 'ModelWrapper':
            return ModelWrapper
        try:
            return super().find_class(module, name)
        except (AttributeError, ModuleNotFoundError):
            return type(name, (), {})


def load_model_universal(model_path: str) -> dict:
    """Universal model loader."""
    logger.info(f"🔍 Loading model: {model_path}")

    try:
        with open(model_path, 'rb') as f:
            data = pickle.load(f)
        logger.info(f"   ✅ Loaded with standard pickle")
    except Exception:
        with open(model_path, 'rb') as f:
            data = UniversalUnpickler(f).load()
        logger.info(f"   ✅ Loaded with custom unpickler")

    result = {
        'model': None,
        'feature_names': None,
        'optimal_threshold': 0.5,
        'raw_data': data
    }

    data_type = type(data).__name__
    logger.info(f"   📦 Type: {data_type}")

    # Extract model info
    if isinstance(data, dict):
        result['model'] = data.get('model')
        result['feature_names'] = data.get('feature_names', [])
        result['optimal_threshold'] = data.get('optimal_threshold', 0.5)
    elif hasattr(data, 'models_list'):
        result['model'] = data
        result['feature_names'] = getattr(data, 'feature_columns', [])
        result['optimal_threshold'] = getattr(data, 'long_threshold', 0.5)
    else:
        result['model'] = data
        if hasattr(data, 'feature_names_in_'):
            result['feature_names'] = list(data.feature_names_in_)

    logger.info(f"   📊 Features: {len(result['feature_names'])}")
    logger.info(f"   🎯 Threshold: {result['optimal_threshold']:.3f}")

    return result


# ============================================================================
# FEATURE ENGINEERING (from 1.py)
# ============================================================================

def create_features_for_bot(df: pd.DataFrame) -> pd.DataFrame:
    """Create features matching train_with_real_data.py"""
    logger.info("   Creating features (matching training data)...")

    df_feat = df.copy()

    # === BASIC FEATURES ===
    df_feat['returns'] = df_feat['close'].pct_change()
    df_feat['returns_5'] = df_feat['close'].pct_change(5)
    df_feat['returns_10'] = df_feat['close'].pct_change(10)

    # Volatility
    df_feat['volatility_5'] = df_feat['returns'].rolling(5).std()
    df_feat['volatility_20'] = df_feat['returns'].rolling(20).std()
    df_feat['volatility_ratio'] = df_feat['volatility_5'] / (df_feat['volatility_20'] + 1e-8)

    # ATR
    high_low = df_feat['high'] - df_feat['low']
    high_close = abs(df_feat['high'] - df_feat['close'].shift())
    low_close = abs(df_feat['low'] - df_feat['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df_feat['atr'] = true_range.rolling(14).mean()
    df_feat['atr_pct'] = df_feat['atr'] / df_feat['close'] * 100

    # === MOMENTUM FEATURES ===
    for period in [3, 5, 8, 13, 21]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100

    df_feat['momentum_accel'] = df_feat['momentum_5'].diff(3)

    # === MOVING AVERAGES ===
    for period in [7, 14, 21, 50, 100]:
        df_feat[f'sma_{period}'] = df_feat['close'].rolling(period).mean()
        df_feat[f'ema_{period}'] = df_feat['close'].ewm(span=period, adjust=False).mean()

    df_feat['price_vs_sma7'] = (df_feat['close'] - df_feat['sma_7']) / df_feat['sma_7'] * 100
    df_feat['price_vs_sma21'] = (df_feat['close'] - df_feat['sma_21']) / df_feat['sma_21'] * 100
    df_feat['price_vs_ema14'] = (df_feat['close'] - df_feat['ema_14']) / df_feat['ema_14'] * 100

    df_feat['sma7_above_sma21'] = (df_feat['sma_7'] > df_feat['sma_21']).astype(int)
    df_feat['ema7_above_ema21'] = (df_feat['ema_7'] > df_feat['ema_21']).astype(int)

    # === RSI ===
    delta = df_feat['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df_feat['rsi'] = 100 - (100 / (1 + rs))

    df_feat['rsi_oversold'] = (df_feat['rsi'] < 30).astype(int)
    df_feat['rsi_overbought'] = (df_feat['rsi'] > 70).astype(int)
    df_feat['rsi_neutral'] = ((df_feat['rsi'] >= 40) & (df_feat['rsi'] <= 60)).astype(int)

    # === MACD ===
    ema12 = df_feat['close'].ewm(span=12, adjust=False).mean()
    ema26 = df_feat['close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    df_feat['macd_hist'] = macd - macd_signal
    df_feat['macd_hist_increasing'] = (df_feat['macd_hist'] > df_feat['macd_hist'].shift(1)).astype(int)

    # === BOLLINGER BANDS ===
    sma20 = df_feat['close'].rolling(20).mean()
    std20 = df_feat['close'].rolling(20).std()
    df_feat['bb_upper'] = sma20 + (2 * std20)
    df_feat['bb_lower'] = sma20 - (2 * std20)
    df_feat['bb_width'] = (df_feat['bb_upper'] - df_feat['bb_lower']) / sma20 * 100
    df_feat['bb_position'] = (df_feat['close'] - df_feat['bb_lower']) / (df_feat['bb_upper'] - df_feat['bb_lower'] + 1e-8)

    # === VOLUME FEATURES ===
    df_feat['volume_sma_20'] = df_feat['volume'].rolling(20).mean()
    df_feat['volume_ratio'] = df_feat['volume'] / (df_feat['volume_sma_20'] + 1e-8)
    df_feat['high_volume'] = (df_feat['volume_ratio'] > 1.5).astype(int)

    # Volume ratios for different periods (needed by model)
    for period in [3, 5, 8, 13, 21]:
        vol_sma = df_feat['volume'].rolling(period).mean()
        df_feat[f'volume_ratio_{period}'] = df_feat['volume'] / (vol_sma + 1e-8)

    # Volume momentum
    df_feat['volume_momentum'] = df_feat['volume'].pct_change(5)

    # === CANDLE PATTERNS ===
    body = abs(df_feat['close'] - df_feat['open'])
    upper_wick = df_feat['high'] - df_feat[['close', 'open']].max(axis=1)
    lower_wick = df_feat[['close', 'open']].min(axis=1) - df_feat['low']

    df_feat['body_pct'] = body / df_feat['close'] * 100
    df_feat['upper_wick_pct'] = upper_wick / df_feat['close'] * 100
    df_feat['lower_wick_pct'] = lower_wick / df_feat['close'] * 100
    df_feat['total_wick'] = upper_wick + lower_wick
    df_feat['wick_body_ratio'] = df_feat['total_wick'] / (body + 1e-8)

    is_green = (df_feat['close'] > df_feat['open']).astype(int)
    is_red = (df_feat['close'] < df_feat['open']).astype(int)

    df_feat['green_streak'] = (is_green * (is_green.groupby((is_green != is_green.shift()).cumsum()).cumcount() + 1))
    df_feat['red_streak'] = (is_red * (is_red.groupby((is_red != is_red.shift()).cumsum()).cumcount() + 1))

    # === PRICE ACTION ===
    df_feat['higher_high'] = (df_feat['high'] > df_feat['high'].shift(1)).astype(int)
    df_feat['lower_low'] = (df_feat['low'] < df_feat['low'].shift(1)).astype(int)
    df_feat['hh_count'] = df_feat['higher_high'].rolling(10).sum()
    df_feat['ll_count'] = df_feat['lower_low'].rolling(10).sum()

    for period in [14, 50]:
        high_period = df_feat['high'].rolling(period).max()
        low_period = df_feat['low'].rolling(period).min()
        df_feat[f'price_position_{period}'] = (df_feat['close'] - low_period) / (high_period - low_period + 1e-8)

    # Price position (general) - needed by model
    high_20 = df_feat['high'].rolling(20).max()
    low_20 = df_feat['low'].rolling(20).min()
    df_feat['price_position'] = (df_feat['close'] - low_20) / (high_20 - low_20 + 1e-8)

    # Price acceleration - needed by model
    df_feat['price_acceleration'] = df_feat['returns'].diff(3)

    # Trend strength - needed by model
    df_feat['trend_strength'] = abs(df_feat['close'] - df_feat['sma_21']) / df_feat['atr']

    # Volatility regime - needed by model
    current_vol = df_feat['volatility_20']
    vol_ma = current_vol.rolling(50).mean()
    df_feat['volatility_regime'] = current_vol / (vol_ma + 1e-8)

    # === ORDER FLOW (simulated) ===
    close_position = (df_feat['close'] - df_feat['low']) / (df_feat['high'] - df_feat['low'] + 1e-8)
    df_feat['taker_buy_ratio'] = close_position
    df_feat['taker_sell_ratio'] = 1 - close_position

    df_feat['buy_pressure'] = df_feat['taker_buy_ratio'].rolling(20).mean()
    df_feat['sell_pressure'] = df_feat['taker_sell_ratio'].rolling(20).mean()
    df_feat['pressure_delta'] = df_feat['buy_pressure'] - df_feat['sell_pressure']

    # Fill NaN
    df_feat = df_feat.fillna(method='bfill').fillna(0)

    logger.info("   ✅ Features created (matching training)")
    return df_feat


def make_prediction(model, model_data, df, feature_names):
    """Make prediction using ensemble model."""

    # Check if using ModelWrapper ensemble
    if hasattr(model, 'models_list'):
        logger.info("   🔄 Using ensemble prediction from ModelWrapper")

        # Prepare features
        X = df[feature_names].values

        # Apply scaler if exists
        if hasattr(model, 'scaler') and model.scaler is not None:
            X_scaled = model.scaler.transform(X)
        else:
            X_scaled = X

        # Get predictions from all models
        predictions = []
        for i, sub_model in enumerate(model.models_list):
            try:
                # Check if deep learning model
                model_type = type(sub_model).__name__
                is_dl = model_type in ['Sequential', 'Functional', 'Model']

                if is_dl:
                    pred = sub_model.predict(X_scaled, verbose=0)
                    if pred.ndim > 1:
                        pred = pred[:, -1]
                else:
                    pred = sub_model.predict_proba(X_scaled)[:, 1]

                predictions.append(pred)
            except Exception as e:
                logger.warning(f"   ⚠️  Model {i} failed: {e}")
                continue

        if not predictions:
            raise ValueError("All models failed!")

        # Weighted average
        if hasattr(model, 'model_weights'):
            weights = np.array(model.model_weights[:len(predictions)])
            weights = weights / weights.sum()
        else:
            weights = np.ones(len(predictions)) / len(predictions)

        final_pred = np.zeros_like(predictions[0])
        for pred, weight in zip(predictions, weights):
            final_pred += pred * weight

        logger.info(f"   📊 Ensemble: {len(predictions)}/{len(model.models_list)} models succeeded")

    else:
        # Standard model
        X = df[feature_names].values

        if hasattr(model, 'predict_proba'):
            final_pred = model.predict_proba(X)[:, 1]
        else:
            final_pred = model.predict(X)

    return final_pred


# ============================================================================
# LIVE TRADING BOT
# ============================================================================

class LiveTradingBot:
    """Live trading bot with sniper optimization."""

    def __init__(self, config_path: str = 'config.yaml'):
        global logger

        # Load config
        self.config = load_config('standard')
        logger = setup_logging('INFO', log_to_file=True)

        # Environment variables
        self.symbol = os.getenv('SYMBOL', 'BTCUSDT')
        self.timeframe = os.getenv('TIMEFRAME', '15')
        self.model_path = os.getenv('MODEL_PATH', 'ml_model_master_scalper_365d.pkl')  # Modelo otimizado (2788% ROI em 365 dias)

        # Trading parameters
        self.min_confidence = float(os.getenv('MIN_ML_CONFIDENCE', '0.25'))
        self.risk_per_trade = float(os.getenv('RISK_PER_TRADE_PCT', '0.75')) / 100
        self.initial_capital = float(os.getenv('INITIAL_CAPITAL', '125.0'))

        # Stop loss / Take profit multipliers
        self.sl_atr_mult = float(os.getenv('SL_ATR_MULT', '2.0'))
        self.tp_atr_mult = float(os.getenv('TP_ATR_MULT', '0.7'))  # Otimizado: 100% WR nos testes!

        # Cooldown between trades (seconds)
        self.trade_cooldown = int(os.getenv('TRADE_COOLDOWN_SEC', '900'))  # 15 minutes default

        # Dry run mode
        self.dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'

        # Telegram
        telegram_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        telegram_chat = os.getenv('TELEGRAM_CHAT_ID', '')
        self.telegram = TelegramNotifier(telegram_token, telegram_chat)
        self.telegram.set_bot_instance(self)  # Enable commands

        # Control flags
        self.paused = False  # Can be controlled via Telegram /pause

        # Exchange client
        self.bybit_testnet = os.getenv('BYBIT_TESTNET', 'true').lower() == 'true'
        self.rest_client = BybitRESTClient(
            api_key=os.getenv('BYBIT_API_KEY', ''),
            api_secret=os.getenv('BYBIT_API_SECRET', ''),
            testnet=self.bybit_testnet
        )
        self.data_manager = DataManager(self.rest_client)
        self.feature_store = FeatureStore(self.config)

        # Load model
        self.model_data = load_model_universal(self.model_path)
        self.model = self.model_data['model']
        self.feature_names = self.model_data['feature_names']
        self.optimal_threshold = self.model_data['optimal_threshold']

        # Fetch market meta (tick size, qty step, min qty)
        logger.info("📊 Fetching market metadata...")
        try:
            self.tick_size, self.qty_step, self.min_qty = fetch_market_meta(self.rest_client, self.symbol)
        except Exception as e:
            logger.warning(f"   ⚠️ Error fetching market meta: {e}. Using fallback.")
            # Fallback for BTCUSDT
            self.tick_size = 0.1
            self.qty_step = 0.001
            self.min_qty = 0.001

        # State
        self.position: Optional[Dict] = None
        self.last_trade_time: Optional[datetime] = None
        self.capital = self.initial_capital
        self.last_price: Optional[float] = None
        self.last_analyzed_candle_time: Optional[datetime] = None  # Track last candle to avoid re-analysis

        # State persistence file (unique per symbol)
        symbol_clean = self.symbol.replace('USDT', '').lower()
        self.state_file = PathLib(f'storage/bot_state_{symbol_clean}.json')

        # Load previous state (for cooldown persistence)
        self._load_state()

        logger.info("=" * 80)
        logger.info("🤖 LIVE TRADING BOT - SNIPER MODE")
        logger.info("=" * 80)
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}m")
        logger.info(f"Model: {Path(self.model_path).name}")
        logger.info(f"Min Confidence: {self.min_confidence*100:.0f}%")
        logger.info(f"Risk per Trade: {self.risk_per_trade*100:.2f}%")
        logger.info(f"SL: {self.sl_atr_mult}x ATR | TP: {self.tp_atr_mult}x ATR")
        logger.info(f"Trade Cooldown: {self.trade_cooldown}s ({self.trade_cooldown/60:.1f}min)")
        logger.info(f"Mode: {'🔵 DRY RUN' if self.dry_run else '🔴 LIVE TRADING'}")
        logger.info(f"Exchange: {'TESTNET' if self.bybit_testnet else 'MAINNET'}")
        logger.info("=" * 80)

        # Warning for live trading
        if not self.dry_run and not self.bybit_testnet:
            logger.warning("⚠️" * 20)
            logger.warning("⚠️ REAL TRADING MODE ON MAINNET!")
            logger.warning("⚠️" * 20)

        # Send startup notification
        network = 'TESTNET' if self.bybit_testnet else 'MAINNET'
        self.telegram.send(
            f"🤖 <b>Bot Started</b>\n\n"
            f"Symbol: {self.symbol}\n"
            f"Timeframe: {self.timeframe}m\n"
            f"Min Confidence: {self.min_confidence*100:.0f}%\n"
            f"Risk: {self.risk_per_trade*100:.2f}%\n"
            f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}\n"
            f"Network: {network}"
        )

    def _load_state(self):
        """Load bot state from file to persist cooldown across restarts."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)

                # Load last_trade_time if exists
                if 'last_trade_time' in state and state['last_trade_time']:
                    self.last_trade_time = datetime.fromisoformat(state['last_trade_time'])

                    # Check if cooldown is still active
                    if self.last_trade_time:
                        time_since_last = (datetime.now() - self.last_trade_time).total_seconds()
                        if time_since_last < self.trade_cooldown:
                            remaining = self.trade_cooldown - time_since_last
                            logger.info(f"⏰ Cooldown ativo do trade anterior: {remaining:.0f}s restantes ({remaining/60:.1f}min)")
                        else:
                            logger.info(f"✅ Cooldown do trade anterior expirou")
                            self.last_trade_time = None
        except Exception as e:
            logger.warning(f"⚠️ Erro ao carregar estado: {e}")

    def _save_state(self):
        """Save bot state to file for persistence."""
        try:
            # Ensure storage directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            state = {
                'last_trade_time': self.last_trade_time.isoformat() if self.last_trade_time else None,
                'updated_at': datetime.now().isoformat()
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Erro ao salvar estado: {e}")

    def get_current_data(self) -> pd.DataFrame:
        """Download latest data and build features."""

        # Download data (30 days lookback for indicators)
        lookback_days = 30

        try:
            # DataManager.get_data expects positional args: (symbol, timeframe, lookback_days, use_cache)
            df = self.data_manager.get_data(
                self.symbol,
                f'{self.timeframe}m',
                lookback_days,
                False  # use_cache=False
            )

            if df.empty:
                raise ValueError("No data received")

            logger.info(f"📥 Downloaded {len(df)} candles")

            # Build features using FeatureStore
            df_features = self.feature_store.build_features(df, normalize=False)

            # Create features matching training data
            df_features = create_features_for_bot(df_features)

            return df_features

        except Exception as e:
            logger.error(f"❌ Error fetching data: {e}")
            raise

    def show_position_status(self, current_price: float):
        """Display current position status with unrealized PnL."""
        if not self.position:
            return

        entry_price = self.position['entry_price']
        direction = self.position['direction']
        sl = self.position['stop_loss']
        tp = self.position['take_profit']

        # Calculate unrealized PnL (gross)
        if direction == 'long':
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100

        pnl_amount = self.position['size'] * (pnl_pct / 100)

        # Calculate fees (0.055% taker x2 for entry+exit)
        fee = self.position['size'] * 0.00055 * 2
        pnl_amount_net = pnl_amount - fee
        pnl_pct_net = (pnl_amount_net / self.position['size']) * 100

        # Calculate distance to SL/TP
        if direction == 'long':
            dist_sl = ((current_price - sl) / sl) * 100
            dist_tp = ((tp - current_price) / current_price) * 100
        else:
            dist_sl = ((sl - current_price) / current_price) * 100
            dist_tp = ((current_price - tp) / tp) * 100

        # Duration
        duration = datetime.now() - self.position['entry_time']
        hours = duration.total_seconds() / 3600
        minutes = (duration.total_seconds() % 3600) / 60

        # Format output
        pnl_emoji = "🟢" if pnl_amount_net > 0 else "🔴" if pnl_amount_net < 0 else "⚪"
        direction_emoji = "🟢" if direction == 'long' else "🔴"

        logger.info("")
        logger.info(f"{direction_emoji} {direction.upper()} | Entrada: ${entry_price:,.2f} | Atual: ${current_price:,.2f}")
        logger.info(f"{pnl_emoji} PnL Líquido: {pnl_pct_net:+.2f}% (${pnl_amount_net:+,.2f}) | Duração: {int(hours)}h {int(minutes)}m")
        logger.info(f"🛑 SL: ${sl:,.2f} ({dist_sl:+.2f}%) | 🎯 TP: ${tp:,.2f} ({dist_tp:+.2f}%)")

    def check_position_exit(self, current_candle) -> bool:
        """Check if current position should be exited."""
        if not self.position:
            return False

        # Update last_price for tracking
        self.last_price = current_candle['close']

        # Show current position status
        self.show_position_status(current_candle['close'])

        # For REAL trading, check if Bybit closed the position
        if not self.position.get('is_paper', True):
            closed = self.check_position_closed()
            if closed:
                exit_price, reason = closed
                self.close_position(current_candle, reason, close=exit_price)
                return True
            return False

        # For PAPER mode, check locally
        high = current_candle['high']
        low = current_candle['low']
        close = current_candle['close']
        direction = self.position['direction']

        # Check stop loss and take profit
        if direction == 'long':
            if low <= self.position['stop_loss']:
                self.close_position(current_candle, 'stop_loss', close=self.position['stop_loss'])
                return True
            if high >= self.position['take_profit']:
                self.close_position(current_candle, 'take_profit', close=self.position['take_profit'])
                return True
        else:  # short
            if high >= self.position['stop_loss']:
                self.close_position(current_candle, 'stop_loss', close=self.position['stop_loss'])
                return True
            if low <= self.position['take_profit']:
                self.close_position(current_candle, 'take_profit', close=self.position['take_profit'])
                return True

        return False

    def calculate_position_size(self, price: float, sl_price: float) -> float:
        """
        Calculate BTC quantity based on risk.

        CRITICAL PROTECTION: Limits position to 95% of capital (same as backtest)
        """
        sl_dist = abs((sl_price - price) / price)
        risk_amt = self.capital * self.risk_per_trade

        # Calculate quantity based on risk
        qty_btc = (risk_amt / sl_dist) / price if sl_dist > 0 else self.min_qty
        qty_btc = max(self.min_qty, qty_btc)

        # CRITICAL: Limit to 95% of capital (same as 1.py line 1082)
        size_usd = qty_btc * price
        max_size_usd = self.capital * 0.95
        if size_usd > max_size_usd:
            qty_btc = max_size_usd / price
            qty_btc = max(self.min_qty, qty_btc)  # Ensure still above minimum

        return qty_btc

    def open_position(self, current_candle, signal, confidence):
        """Open a new position with automatic SL/TP on Bybit."""

        direction = 'long' if signal == 1 else 'short'
        price = current_candle['close']
        atr = current_candle.get('atr', price * 0.01)

        # Calculate SL and TP (raw values)
        if direction == 'long':
            sl = price - (atr * self.sl_atr_mult)
            tp = price + (atr * self.tp_atr_mult)
            side = 'Buy'
        else:
            sl = price + (atr * self.sl_atr_mult)
            tp = price - (atr * self.tp_atr_mult)
            side = 'Sell'

        # Calculate quantity in BTC
        qty_btc = self.calculate_position_size(price, sl)

        # Round prices and quantities using market meta
        sl = round_price(sl, self.tick_size)
        tp = round_price(tp, self.tick_size)
        qty_btc = round_qty(qty_btc, self.qty_step, self.min_qty)
        price = round_price(price, self.tick_size)
        size_usd = qty_btc * price

        # VALIDATIONS
        if qty_btc < self.min_qty:
            logger.error(f"❌ Quantity {qty_btc} BTC below minimum {self.min_qty}!")
            return

        if size_usd < 10:
            logger.warning(f"⚠️ Size too small: ${size_usd:,.2f} < $10")
            return

        # Validate SL makes sense
        if direction == 'long' and sl >= price:
            logger.error(f"❌ Invalid SL for LONG: ${sl:,.2f} >= ${price:,.2f}")
            return
        if direction == 'short' and sl <= price:
            logger.error(f"❌ Invalid SL for SHORT: ${sl:,.2f} <= ${price:,.2f}")
            return

        # Validate TP makes sense
        if direction == 'long' and tp <= price:
            logger.error(f"❌ Invalid TP for LONG: ${tp:,.2f} <= ${price:,.2f}")
            return
        if direction == 'short' and tp >= price:
            logger.error(f"❌ Invalid TP for SHORT: ${tp:,.2f} >= ${price:,.2f}")
            return

        # Log position details
        direction_emoji = "🟢" if direction == 'long' else "🔴"
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"{direction_emoji} ABRINDO POSIÇÃO {direction.upper()}")
        logger.info("=" * 80)
        logger.info(f"📍 Baseado no candle: {current_candle.name}")
        logger.info(f"📍 Close do candle: ${current_candle['close']:,.2f}")
        logger.info(f"⏰ Executando AGORA: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Preço entrada (estimado): ${price:,.2f}")
        logger.info(f"Confiança: {confidence:.1%}")
        logger.info(f"Qtd: {qty_btc} BTC = ${size_usd:,.2f}")
        logger.info(f"🛑 SL: ${sl:,.2f} ({-abs((sl-price)/price)*100:.1f}%)")
        logger.info(f"🎯 TP: ${tp:,.2f} ({abs((tp-price)/price)*100:.1f}%)")
        logger.info(f"ATR: ${atr:,.2f}")
        logger.info("=" * 80)

        order_id = None
        actual_entry_price = price
        is_paper = self.dry_run

        # Execute real order if not dry run
        if not self.dry_run:
            try:
                logger.info(f"💰 Sending REAL {side} order...")

                # Place Market order
                order = self.rest_client.place_order(
                    symbol=self.symbol,
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

                            # Get actual fill price if available
                            if 'price' in result and result['price']:
                                try:
                                    actual_entry_price = float(result['price'])
                                except:
                                    actual_entry_price = price

                        # Configure SL/TP with retry
                        logger.info(f"📍 Setting SL/TP on Bybit...")
                        logger.info(f"   SL: ${sl:,.1f} | TP: ${tp:,.1f}")

                        # Wait for position to be created (CRITICAL!)
                        logger.info("⏳ Waiting for position to be created...")
                        time.sleep(3)

                        # Verify position exists
                        position_exists = False
                        try:
                            positions = self.rest_client.get_positions(symbol=self.symbol)
                            positions_list = positions.get('result', {}).get('list', [])
                            for pos in positions_list:
                                if float(pos.get('size', 0)) > 0:
                                    position_exists = True
                                    logger.info(f"✅ Position confirmed: {pos.get('size')} BTC")
                                    break
                        except Exception as e:
                            logger.warning(f"⚠️ Error verifying position: {e}")

                        if not position_exists:
                            logger.error(f"❌ Position not created - cannot set SL/TP!")
                        else:
                            # Set SL/TP with retry
                            def _set_sl_tp():
                                sl_tp_result = self.rest_client.set_trading_stop(
                                    category='linear',
                                    symbol=self.symbol,
                                    stopLoss=str(sl),
                                    takeProfit=str(tp),
                                    positionIdx=0
                                )

                                if sl_tp_result and 'retCode' in sl_tp_result and sl_tp_result['retCode'] == 0:
                                    logger.info(f"✅ SL/TP configured on Bybit!")
                                    return True
                                else:
                                    error_msg = sl_tp_result.get('retMsg', 'Unknown') if sl_tp_result else 'No response'
                                    raise Exception(f"API error: {error_msg}")

                            result = retry_with_backoff(_set_sl_tp, max_retries=3, initial_delay=2.0)
                            if not result:
                                logger.error(f"❌ Failed to set SL/TP after retries!")

                else:
                    raise Exception("API error - order failed")

            except Exception as e:
                logger.error(f"❌ Order execution failed: {e}")
                self.telegram.send(f"❌ <b>Order Failed</b>\n\n{e}")
                return

        # Save position
        self.position = {
            'symbol': self.symbol,
            'direction': direction,
            'entry_price': actual_entry_price,
            'entry_time': datetime.now(),  # Store as datetime object, not string
            'qty': qty_btc,
            'size': size_usd,
            'stop_loss': sl,
            'take_profit': tp,
            'confidence': confidence,
            'order_id': order_id,
            'is_paper': is_paper,
            'atr': atr
        }

        self.last_price = actual_entry_price

        # Telegram notification
        mode_str = "📝 PAPER" if is_paper else "💰 REAL"
        self.telegram.send(
            f"{direction_emoji} <b>ENTRADA {direction.upper()}</b> {mode_str}\n\n"
            f"Preço: ${actual_entry_price:,.2f}\n"
            f"Qtd: {qty_btc} BTC (${size_usd:,.2f})\n"
            f"Confiança: {confidence:.1%}\n\n"
            f"🛑 SL: ${sl:,.2f}\n"
            f"🎯 TP: ${tp:,.2f}\n\n"
            f"Order ID: {order_id if order_id else 'N/A'}"
        )

    def check_position_closed(self) -> Optional[tuple]:
        """
        Check if Bybit closed the position (SL/TP hit).
        Only checks - does NOT close locally.
        Returns: (exit_price, reason) if closed, None if still open
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

                            # Position still open
                            if size > 0:
                                # Update last_price for tracking
                                mark_price = float(pos.get('markPrice', 0))
                                if mark_price > 0:
                                    self.last_price = mark_price
                                return None

                            # Position closed
                            else:
                                logger.info("✅ Posição fechada pela Bybit")

                                # Use last_price as exit_price
                                exit_price = self.last_price if self.last_price else self.position['entry_price']

                                # Determine reason
                                entry = self.position['entry_price']
                                direction = self.position['direction']
                                sl = self.position['stop_loss']
                                tp = self.position['take_profit']

                                tolerance = entry * 0.001

                                if abs(exit_price - sl) <= tolerance:
                                    reason = 'stop_loss'
                                elif abs(exit_price - tp) <= tolerance:
                                    reason = 'take_profit'
                                else:
                                    # Fallback logic
                                    if direction == 'long':
                                        reason = 'stop_loss' if exit_price < entry else 'take_profit'
                                    else:
                                        reason = 'stop_loss' if exit_price > entry else 'take_profit'

                                logger.info(f"✅ Saída: ${exit_price:,.2f} ({reason})")
                                return (exit_price, reason)

                    # Position not found = was closed
                    logger.info("✅ Position not found - was closed")
                    exit_price = self.last_price if self.last_price else self.position['take_profit']
                    return (exit_price, 'take_profit')

        except Exception as e:
            logger.error(f"⚠️ Error checking position: {e}")
            return None

        return None

    def close_position(self, current_candle, reason, close=None):
        """Close current position."""
        if not self.position:
            return

        exit_price = close if close else current_candle['close']
        entry_price = self.position['entry_price']
        direction = self.position['direction']

        # Calculate PnL
        if direction == 'long':
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100

        pnl_amount = self.position['size'] * (pnl_pct / 100)

        # Fees (0.055% taker)
        fee = self.position['size'] * 0.00055 * 2  # entry + exit
        pnl_amount_after_fees = pnl_amount - fee
        pnl_pct_after_fees = (pnl_amount_after_fees / self.position['size']) * 100

        # Duration
        duration = current_candle.name - self.position['entry_time']

        # Log
        is_win = pnl_amount_after_fees > 0
        result_emoji = "✅" if is_win else "❌"
        reason_emoji = "🎯" if reason == 'take_profit' else "🛑"
        reason_text = "GAIN/TAKE PROFIT" if reason == 'take_profit' else "STOP LOSS"

        logger.info("")
        logger.info("=" * 80)
        logger.info(f"{result_emoji} FECHANDO POSIÇÃO {direction.upper()} - {reason_emoji} {reason_text}")
        logger.info("=" * 80)
        logger.info(f"Entrada: ${entry_price:,.2f} @ {self.position['entry_time']}")
        logger.info(f"Saída:   ${exit_price:,.2f} @ {current_candle.name}")
        logger.info(f"Duração: {duration}")
        logger.info(f"PnL Líquido: {pnl_pct_after_fees:+.2f}% (${pnl_amount_after_fees:+,.2f})")
        logger.info(f"Taxas: ${fee:.2f}")
        logger.info("=" * 80)

        # Telegram notification
        self.telegram.send(
            f"{result_emoji} <b>SAÍDA {direction.upper()}</b> - {reason_emoji} {reason_text}\n\n"
            f"Entrada: ${entry_price:,.2f}\n"
            f"Saída: ${exit_price:,.2f}\n"
            f"Duração: {duration}\n\n"
            f"<b>PnL Líquido: {pnl_pct_after_fees:+.2f}% (${pnl_amount_after_fees:+,.2f})</b>\n"
            f"Taxas: ${fee:.2f}"
        )

        # TODO: Execute actual close if not dry_run
        if not self.dry_run:
            # self.close_order(self.position['direction'])
            pass

        # Clear position
        self.position = None
        self.last_trade_time = datetime.now()

        # Save state to persist cooldown across restarts
        self._save_state()

    def recover_open_positions(self):
        """
        Recover any open positions from Bybit when bot starts.
        This allows bot to resume monitoring existing positions.
        """
        if self.dry_run:
            logger.info("📋 Paper trading mode - no positions to recover")
            return

        try:
            logger.info("🔍 Checking for open positions on Bybit...")
            positions = self.rest_client.get_positions(symbol=self.symbol)

            if positions and 'retCode' in positions and positions['retCode'] == 0:
                if 'result' in positions and 'list' in positions['result']:
                    pos_list = positions['result']['list']

                    for pos in pos_list:
                        if pos['symbol'] == self.symbol:
                            size = float(pos.get('size', 0))

                            if size > 0:
                                # Found open position!
                                side = pos.get('side', '')
                                entry_price = float(pos.get('avgPrice', 0))
                                mark_price = float(pos.get('markPrice', 0))
                                sl = float(pos.get('stopLoss', 0)) if pos.get('stopLoss') else None
                                tp = float(pos.get('takeProfit', 0)) if pos.get('takeProfit') else None

                                direction = 'long' if side == 'Buy' else 'short'

                                logger.info("")
                                logger.info("=" * 80)
                                logger.info("🔄 POSIÇÃO RECUPERADA DA BYBIT")
                                logger.info("=" * 80)
                                logger.info(f"Direção: {direction.upper()}")
                                logger.info(f"Tamanho: {size} BTC")
                                logger.info(f"Entrada: ${entry_price:,.2f}")
                                logger.info(f"Preço Atual: ${mark_price:,.2f}")
                                if sl:
                                    logger.info(f"SL: ${sl:,.2f}")
                                if tp:
                                    logger.info(f"TP: ${tp:,.2f}")
                                logger.info("=" * 80)

                                # Recreate position state
                                self.position = {
                                    'symbol': self.symbol,
                                    'direction': direction,
                                    'entry_price': entry_price,
                                    'entry_time': datetime.now(),  # Unknown actual entry time
                                    'qty': size,
                                    'size': size * entry_price,
                                    'stop_loss': sl,
                                    'take_profit': tp,
                                    'confidence': 0.0,  # Unknown
                                    'order_id': None,
                                    'is_paper': False,
                                    'atr': 0
                                }

                                self.last_price = mark_price

                                # Telegram notification
                                direction_emoji = "🟢" if direction == 'long' else "🔴"
                                self.telegram.send(
                                    f"{direction_emoji} <b>POSIÇÃO RECUPERADA</b>\n\n"
                                    f"Direção: {direction.upper()}\n"
                                    f"Tamanho: {size} BTC\n"
                                    f"Entrada: ${entry_price:,.2f}\n"
                                    f"Atual: ${mark_price:,.2f}\n\n"
                                    f"Bot vai monitorar esta posição"
                                )

                                return

                    logger.info("✅ No open positions found")
            else:
                logger.warning(f"⚠️ API error checking positions: {positions}")

        except Exception as e:
            logger.error(f"❌ Error recovering positions: {e}")
            import traceback
            traceback.print_exc()

    def run(self):
        """Main trading loop."""

        logger.info("🚀 Starting trading loop...")
        logger.info("Press Ctrl+C to stop")
        logger.info("")

        # Try to recover any open positions from Bybit
        self.recover_open_positions()

        try:
            while True:
                try:
                    # Check for Telegram commands
                    self.telegram.check_commands()

                    # Get current data
                    df = self.get_current_data()

                    # DEBUG: Log últimos candles
                    logger.info(f"📊 Últimos 3 candles:")
                    for i in range(-3, 0):
                        candle = df.iloc[i]
                        logger.info(f"   [{i}] {candle.name} | Close: ${candle['close']:,.2f}")

                    # Get last CLOSED candle (penultimate = último fechado)
                    # iloc[-1] = candle atual (incompleto)
                    # iloc[-2] = último candle fechado ✅
                    current = df.iloc[-2]
                    current_candle_time = current.name  # Candle timestamp

                    # DEBUG: Mostrar horários
                    now = datetime.now()
                    logger.info(f"⏰ Sistema: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                    logger.info(f"🕐 Candle analisando: {current_candle_time}")
                    logger.info(f"🕑 Último analisado: {self.last_analyzed_candle_time}")

                    # Check if we have an open position
                    if self.position:
                        # Check exit conditions
                        self.check_position_exit(current)

                    # Check if we can open a new position
                    else:
                        # Check if bot is paused
                        if self.paused:
                            logger.info("⏸️ Bot pausado - aguardando /resume")
                            time.sleep(10)
                            continue

                        # 🔥 FIX: Check if candle is "fresh" (fechou recentemente)
                        # Prevent opening trades on old candles when bot first starts
                        candle_close_time = pd.Timestamp(current_candle_time)
                        if candle_close_time.tz is None:
                            candle_close_time = candle_close_time.tz_localize('UTC')

                        now_utc = pd.Timestamp.now(tz='UTC')
                        seconds_since_candle_close = (now_utc - candle_close_time).total_seconds()

                        # For 15min timeframe (900s), candle is "fresh" if closed within last 120s (2min)
                        max_candle_age = 120  # 2 minutes

                        if seconds_since_candle_close > max_candle_age:
                            logger.info(f"⏭️ Candle antigo ({seconds_since_candle_close:.0f}s desde fechamento) - aguardando novo candle")
                            time.sleep(10)
                            continue

                        # CRITICAL: Only analyze if this is a NEW candle (same as backtest)
                        if self.last_analyzed_candle_time and current_candle_time == self.last_analyzed_candle_time:
                            logger.info(f"⏭️ Mesmo candle ({current_candle_time}) - aguardando novo candle")
                            time.sleep(10)
                            continue
                        # Check cooldown
                        if self.last_trade_time:
                            time_since_last_trade = (datetime.now() - self.last_trade_time).total_seconds()
                            if time_since_last_trade < self.trade_cooldown:
                                remaining = self.trade_cooldown - time_since_last_trade
                                logger.info(f"⏳ Cooldown: {remaining:.0f}s restantes ({remaining/60:.1f}min)")
                                time.sleep(10)
                                continue

                        # Make prediction
                        try:
                            # Get prediction for ONLY the last closed candle (iloc[-2])
                            df_single = df.iloc[[-2]].copy()

                            predictions = make_prediction(
                                self.model,
                                self.model_data,
                                df_single,
                                self.feature_names
                            )

                            # Get prediction
                            pred = predictions[0]  # Only one prediction

                            # Calculate confidence (CORRETO - same as 2.py)
                            ml_confidence = abs(pred - self.optimal_threshold) * 2

                            # 🔥 FIX: Determine signal EXACTLY same as 2.py
                            # 2.py usa: (pred > threshold) não (pred >= threshold)
                            # 2.py gera signal=0 (NEUTRO) quando pred == threshold ou confidence baixa
                            signal = 0  # Start as NEUTRO
                            if pred > self.optimal_threshold and ml_confidence >= self.min_confidence:
                                signal = 1  # long
                            elif pred < self.optimal_threshold and ml_confidence >= self.min_confidence:
                                signal = -1  # short

                            sig_name = 'LONG' if signal == 1 else 'SHORT' if signal == -1 else 'NEUTRO'
                            logger.info(f"🔮 Previsão: {pred:.3f} | Sinal: {sig_name} | Confiança: {ml_confidence:.1%}")

                            # Mark this candle as analyzed (regardless of whether we trade)
                            self.last_analyzed_candle_time = current_candle_time

                            # Check if we have a valid signal (not NEUTRO)
                            if signal != 0:
                                logger.info(f"✅ Sinal válido: {sig_name} com confiança {ml_confidence:.1%} >= {self.min_confidence:.1%}")
                                self.open_position(current, signal, ml_confidence)
                            else:
                                logger.info(f"⏭️  Sinal NEUTRO (pred={pred:.3f} ou confiança {ml_confidence:.1%} < {self.min_confidence:.1%}) - pulando")

                        except Exception as e:
                            logger.error(f"Prediction error: {e}")
                            import traceback
                            traceback.print_exc()

                    # Wait before next iteration (no loop cooldown, just sleep a bit)
                    time.sleep(5)

                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    import traceback
                    traceback.print_exc()
                    time.sleep(30)

        except KeyboardInterrupt:
            logger.info("")
            logger.info("🛑 Parando bot...")

            # Don't close position - let it continue on Bybit
            if self.position:
                logger.info("⚠️ Posição deixada aberta na Bybit (será recuperada no restart)")
                logger.info(f"   {self.position['direction'].upper()} @ ${self.position['entry_price']:,.2f}")

            self.telegram.send("🛑 <b>Bot Parado</b>\n\n⚠️ Posição deixada aberta (se houver)")
            logger.info("✅ Bot parado com sucesso")


# ============================================================================
# MAIN
# ============================================================================

def main():
    bot = LiveTradingBot()
    bot.run()


if __name__ == '__main__':
    main()
