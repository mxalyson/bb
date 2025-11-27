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
import websocket
import threading

from core.utils import load_config, setup_logging
from core.bybit_rest import BybitRESTClient
from core.data import DataManager
from core.features import FeatureStore
from decimal import Decimal, ROUND_DOWN, getcontext

# Load environment variables
load_dotenv()

logger = None
getcontext().prec = 28

# ================================================================================
# ENHANCED LOGGER
# ================================================================================

"""
Enhanced Logger with Beautiful Formatting
"""

import logging
from datetime import datetime
from typing import Optional
import sys

class Colors:
    """ANSI color codes for terminal"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # Colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # Bright colors
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'

    # Backgrounds
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'


class EnhancedLogger:
    """Beautiful, informative logger for trading bot"""

    def __init__(self, name: str = "TradingBot"):
        self.logger = logging.getLogger(name)
        self.name = name

    def _format_time(self) -> str:
        """Format current time"""
        return datetime.now().strftime("%H:%M:%S")

    def _print_box(self, text: str, color: str = Colors.CYAN, width: int = 80):
        """Print text in a box"""
        border = "═" * width
        print(f"{color}╔{border}╗{Colors.RESET}")

        # Center text
        padding = (width - len(text)) // 2
        line = " " * padding + text + " " * (width - padding - len(text))
        print(f"{color}║{Colors.RESET}{Colors.BOLD}{line}{Colors.RESET}{color}║{Colors.RESET}")

        print(f"{color}╚{border}╝{Colors.RESET}")

    def _print_section(self, title: str, color: str = Colors.BLUE, width: int = 80):
        """Print section header"""
        border = "─" * (width - len(title) - 4)
        print(f"\n{color}{Colors.BOLD}┌─ {title} {border}┐{Colors.RESET}")

    def _print_section_end(self, width: int = 80):
        """Print section footer"""
        print(f"{Colors.BLUE}└{'─' * width}┘{Colors.RESET}\n")

    def startup(self, config: dict):
        """Beautiful startup banner"""
        print("\n" * 2)
        self._print_box("🤖 TRADING BOT LIVE", Colors.BRIGHT_CYAN, 60)
        print()

        # Config table
        self._print_section("⚙️  CONFIGURATION", Colors.BRIGHT_BLUE, 60)

        rows = [
            ("Symbol", config.get('symbol', 'N/A'), Colors.CYAN),
            ("Timeframe", f"{config.get('timeframe', 'N/A')}m", Colors.CYAN),
            ("Model", config.get('model', 'N/A'), Colors.GREEN),
            ("Min Confidence", f"{config.get('min_confidence', 0)*100:.0f}%", Colors.YELLOW),
            ("Risk per Trade", f"{config.get('risk_per_trade', 0)*100:.2f}%", Colors.YELLOW),
            ("Stop Loss", f"{config.get('sl_atr_mult', 0):.1f}x ATR", Colors.RED),
            ("Take Profit", f"{config.get('tp_atr_mult', 0):.1f}x ATR", Colors.GREEN),
            ("Trade Cooldown", f"{config.get('trade_cooldown', 0)/60:.0f} min", Colors.MAGENTA),
        ]

        for label, value, color in rows:
            print(f"  {Colors.DIM}{label}:{Colors.RESET} {color}{Colors.BOLD}{value}{Colors.RESET}")

        self._print_section_end(60)

        # Mode warning
        mode = config.get('mode', 'DRY RUN')
        network = config.get('network', 'TESTNET')

        if mode == 'LIVE' and network == 'MAINNET':
            self._print_box("⚠️  REAL TRADING MODE - MAINNET ⚠️", Colors.BG_RED + Colors.BRIGHT_WHITE, 60)
        elif mode == 'LIVE':
            print(f"{Colors.YELLOW}{'─' * 60}{Colors.RESET}")
            print(f"{Colors.YELLOW}  🔴 LIVE TRADING - {network}{Colors.RESET}")
            print(f"{Colors.YELLOW}{'─' * 60}{Colors.RESET}")
        else:
            print(f"{Colors.BLUE}{'─' * 60}{Colors.RESET}")
            print(f"{Colors.BLUE}  🔵 DRY RUN MODE - {network}{Colors.RESET}")
            print(f"{Colors.BLUE}{'─' * 60}{Colors.RESET}")

        print("\n")

    def candle_detected(self, candle_time: datetime, price: float, wait_time: int = 60):
        """New candle detected"""
        print(f"\n{Colors.BRIGHT_GREEN}{'━' * 80}{Colors.RESET}")
        print(f"{Colors.BRIGHT_GREEN}{Colors.BOLD}🆕 NEW CANDLE DETECTED{Colors.RESET}")
        print(f"{Colors.BRIGHT_GREEN}{'━' * 80}{Colors.RESET}")
        print(f"  ⏰ Time:  {Colors.CYAN}{candle_time}{Colors.RESET}")
        print(f"  💰 Price: {Colors.YELLOW}${price:,.2f}{Colors.RESET}")
        print(f"  ⏳ Waiting {Colors.MAGENTA}{wait_time}s{Colors.RESET} for API consolidation...")
        print(f"{Colors.BRIGHT_GREEN}{'━' * 80}{Colors.RESET}\n")

    def prediction(self, data: dict):
        """Beautiful prediction display"""
        pred = data.get('prediction', 0)
        conf = data.get('confidence', 0)
        signal = data.get('signal', 'NEUTRO')
        threshold = data.get('threshold', 0.5)
        min_conf = data.get('min_confidence', 0)

        # Signal color
        if signal == 'LONG':
            signal_color = Colors.BRIGHT_GREEN
            signal_emoji = "🟢"
        elif signal == 'SHORT':
            signal_color = Colors.BRIGHT_RED
            signal_emoji = "🔴"
        else:
            signal_color = Colors.YELLOW
            signal_emoji = "⚪"

        print(f"\n{Colors.BRIGHT_CYAN}{'═' * 80}{Colors.RESET}")
        print(f"{Colors.BRIGHT_CYAN}{Colors.BOLD}🔮 PREDICTION{Colors.RESET}")
        print(f"{Colors.BRIGHT_CYAN}{'═' * 80}{Colors.RESET}")

        # Prediction bar
        bar_width = 50
        pred_pos = int(pred * bar_width)
        threshold_pos = int(threshold * bar_width)

        bar = ""
        for i in range(bar_width):
            if i == threshold_pos:
                bar += f"{Colors.YELLOW}|{Colors.RESET}"
            elif i < pred_pos:
                if pred > threshold:
                    bar += f"{Colors.GREEN}█{Colors.RESET}"
                else:
                    bar += f"{Colors.RED}█{Colors.RESET}"
            else:
                bar += f"{Colors.DIM}░{Colors.RESET}"

        print(f"\n  {bar}")
        print(f"  {Colors.DIM}0%{' ' * 44}50%{' ' * 42}100%{Colors.RESET}")

        print(f"\n  📊 Probability: {Colors.BOLD}{pred:.4f}{Colors.RESET} ({pred*100:.1f}%)")
        print(f"  🎯 Threshold:   {Colors.YELLOW}{threshold:.4f}{Colors.RESET} ({threshold*100:.0f}%)")
        print(f"  📈 Confidence:  {Colors.BOLD}{conf:.1f}%{Colors.RESET}")
        print(f"  🎲 Signal:      {signal_color}{Colors.BOLD}{signal_emoji} {signal}{Colors.RESET}")

        if conf < min_conf:
            print(f"\n  {Colors.RED}❌ FILTERED{Colors.RESET}: Confidence {conf:.1f}% < {min_conf:.0f}% (minimum)")
        else:
            print(f"\n  {Colors.GREEN}✅ VALID{Colors.RESET}: Confidence {conf:.1f}% ≥ {min_conf:.0f}%")

        print(f"{Colors.BRIGHT_CYAN}{'═' * 80}{Colors.RESET}\n")

    def trade_opened(self, data: dict):
        """Trade opened notification"""
        direction = data.get('direction', 'UNKNOWN')
        entry = data.get('entry_price', 0)
        size = data.get('size', 0)
        sl = data.get('stop_loss', 0)
        tp = data.get('take_profit', 0)

        color = Colors.BRIGHT_GREEN if direction == 'LONG' else Colors.BRIGHT_RED
        emoji = "🟢" if direction == 'LONG' else "🔴"

        print(f"\n{color}{'━' * 80}{Colors.RESET}")
        print(f"{color}{Colors.BOLD}{emoji} TRADE OPENED - {direction.upper()}{Colors.RESET}")
        print(f"{color}{'━' * 80}{Colors.RESET}")
        print(f"  💰 Entry:  {Colors.YELLOW}${entry:,.2f}{Colors.RESET}")
        print(f"  📏 Size:   {Colors.CYAN}{size:.4f} BTC{Colors.RESET}")
        print(f"  🛑 SL:     {Colors.RED}${sl:,.2f}{Colors.RESET} ({((sl-entry)/entry*100):+.2f}%)")
        print(f"  🎯 TP:     {Colors.GREEN}${tp:,.2f}{Colors.RESET} ({((tp-entry)/entry*100):+.2f}%)")
        print(f"{color}{'━' * 80}{Colors.RESET}\n")

    def trade_closed(self, data: dict):
        """Trade closed notification"""
        direction = data.get('direction', 'UNKNOWN')
        entry = data.get('entry_price', 0)
        exit_price = data.get('exit_price', 0)
        pnl = data.get('pnl', 0)
        pnl_pct = data.get('pnl_pct', 0)
        reason = data.get('reason', 'Unknown')

        color = Colors.BRIGHT_GREEN if pnl > 0 else Colors.BRIGHT_RED
        emoji = "✅" if pnl > 0 else "❌"

        print(f"\n{color}{'━' * 80}{Colors.RESET}")
        print(f"{color}{Colors.BOLD}{emoji} TRADE CLOSED - {reason.upper()}{Colors.RESET}")
        print(f"{color}{'━' * 80}{Colors.RESET}")
        print(f"  📍 Direction: {direction.upper()}")
        print(f"  💵 Entry:     ${entry:,.2f}")
        print(f"  💵 Exit:      ${exit_price:,.2f}")
        print(f"  💰 PnL:       {color}{Colors.BOLD}${pnl:+,.2f} ({pnl_pct:+.2f}%){Colors.RESET}")
        print(f"{color}{'━' * 80}{Colors.RESET}\n")

    def position_status(self, data: dict):
        """Current position status"""
        direction = data.get('direction', 'UNKNOWN')
        entry = data.get('entry_price', 0)
        current = data.get('current_price', 0)
        pnl_pct = data.get('pnl_pct', 0)
        sl = data.get('stop_loss', 0)
        tp = data.get('take_profit', 0)

        color = Colors.GREEN if pnl_pct > 0 else Colors.RED
        emoji = "🟢" if direction == 'LONG' else "🔴"

        print(f"  {emoji} {direction.upper()} @ ${entry:,.2f} | Current: ${current:,.2f} | PnL: {color}{pnl_pct:+.2f}%{Colors.RESET}")

    def error(self, message: str):
        """Error message"""
        print(f"\n{Colors.BRIGHT_RED}{'!' * 80}{Colors.RESET}")
        print(f"{Colors.BRIGHT_RED}{Colors.BOLD}❌ ERROR{Colors.RESET}")
        print(f"{Colors.BRIGHT_RED}{'!' * 80}{Colors.RESET}")
        print(f"  {Colors.RED}{message}{Colors.RESET}")
        print(f"{Colors.BRIGHT_RED}{'!' * 80}{Colors.RESET}\n")

    def info(self, message: str, emoji: str = "ℹ️"):
        """Info message in GREEN"""
        """Info message"""
        timestamp = self._format_time()
        print(f"{Colors.DIM}[{timestamp}]{Colors.RESET} {Colors.GREEN}{emoji} {message}{Colors.RESET}")

    def success(self, message: str):
        """Success message"""
        timestamp = self._format_time()
        print(f"{Colors.DIM}[{timestamp}]{Colors.RESET} {Colors.GREEN}✅ {message}{Colors.RESET}")



    def debug(self, message: str):
        """Log debug message (dimmed)."""
        timestamp = self._format_time()
        print(f"{Colors.DIM}[{timestamp}] 🐛 {message}{Colors.RESET}")
    def warning(self, message: str):
        """Warning message"""
        timestamp = self._format_time()
        print(f"{Colors.DIM}[{timestamp}]{Colors.RESET} {Colors.YELLOW}⚠️  {message}{Colors.RESET}")

    def progress(self, current: int, total: int, prefix: str = "Progress"):
        """Progress bar"""
        bar_width = 40
        progress = current / total
        filled = int(bar_width * progress)

        bar = f"{Colors.GREEN}{'█' * filled}{Colors.DIM}{'░' * (bar_width - filled)}{Colors.RESET}"
        percent = progress * 100

        print(f"\r  {prefix}: {bar} {percent:.0f}%", end='', flush=True)

        if current == total:
            print()  # New line when complete

    def waiting(self, message: str, seconds: int):
        """Waiting message with countdown"""
        print(f"  {Colors.MAGENTA}⏳ {message}{Colors.RESET}")

        for i in range(seconds, 0, -1):
            print(f"\r  {Colors.DIM}   {i}s remaining...{Colors.RESET}", end='', flush=True)
            import time
            time.sleep(1)

        print(f"\r  {Colors.GREEN}   ✓ Done!{Colors.RESET}          ")


# Singleton instance
_enhanced_logger = None

def get_enhanced_logger(name: str = "TradingBot") -> EnhancedLogger:
    """Get enhanced logger singleton"""
    global _enhanced_logger
    if _enhanced_logger is None:
        _enhanced_logger = EnhancedLogger(name)
    return _enhanced_logger


# Global display instance
display = EnhancedLogger('TradingBot')



# ============================================================================
# WEBSOCKET HANDLER
# ============================================================================

class BybitWebSocketHandler:
    """Real-time candle detection via WebSocket."""

    def __init__(self, symbol, timeframe, on_candle_close_callback):
        self.symbol = symbol
        self.timeframe = timeframe
        self.on_candle_close = on_candle_close_callback
        self.ws = None
        self.ws_thread = None
        self.running = False
        self.connected = False
        self.last_confirmed_candle_time = None
        self.reconnect_delay = 1.0
        self.max_reconnect_delay = 60.0
        display.info("📡 WebSocket handler created")

    def start(self):
        if self.running:
            return
        self.running = True
        self.ws_thread = threading.Thread(target=self._run, daemon=True)
        self.ws_thread.start()
        display.info("🚀 WebSocket started")

    def stop(self):
        self.running = False
        if self.ws:
            self.ws.close()
        display.info("🛑 WebSocket stopped")

    def _run(self):
        while self.running:
            try:
                self._connect()
            except Exception as e:
                if self.running:
                    display.warning(f"🔄 WS reconnect in {self.reconnect_delay:.0f}s")
                    time.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    def _connect(self):
        url = "wss://stream.bybit.com/v5/public/linear"
        self.ws = websocket.WebSocketApp(url, on_open=self._on_open, on_message=self._on_message, 
                                          on_error=self._on_error, on_close=self._on_close)
        self.ws.run_forever()

    def _on_open(self, ws):
        self.connected = True
        self.reconnect_delay = 1.0
        ws.send(json.dumps({"op": "subscribe", "args": [f"kline.{self.timeframe}.{self.symbol}"]}))
        display.info(f"✅ Subscribed: kline.{self.timeframe}.{self.symbol}")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            if 'topic' in data and 'kline' in data['topic']:
                kline_list = data.get('data', [])
                if kline_list:
                    kline = kline_list[0]
                    if kline.get('confirm', False):
                        ct = datetime.fromtimestamp(kline.get('start', 0) / 1000)
                        if ct != self.last_confirmed_candle_time:
                            self.last_confirmed_candle_time = ct
                            cdata = {'time': ct, 'close': float(kline.get('close', 0))}
                            display.info(f"🕐 WS: Candle @ {ct} | ${cdata['close']:,.2f}")
                            if self.on_candle_close:
                                self.on_candle_close(cdata)
        except:
            pass

    def _on_error(self, ws, error):
        self.connected = False

    def _on_close(self, ws, code, msg):
        self.connected = False
        display.warning("📡 WS disconnected")


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
                display.info(f"   ✅ Market meta: tick={tick}, step={step}, min_qty={min_qty}")
        else:
            display.warning(f"   ⚠️ API error, using fallback")
    except Exception as e:
        display.warning(f"   ⚠️ fetch_market_meta error: {e}, using fallback")

    return tick, step, min_qty


def retry_with_backoff(func, max_retries: int = 3, initial_delay: float = 1.0):
    """Execute function with exponential backoff retry."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt < max_retries - 1:
                display.warning(f"   Retry {attempt + 1}/{max_retries} failed: {e}. Waiting {delay}s...")
                time.sleep(delay)
                delay = min(delay * 2, 16.0)
            else:
                display.error(f"   All {max_retries} retries failed: {e}")
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
            display.info("📱 Telegram notifications: ENABLED")
            display.info("📱 Telegram commands: ENABLED (/help para listar)")
        else:
            display.warning("📱 Telegram notifications: DISABLED (missing credentials)")

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
                display.warning(f"Telegram error: {response.text}")
        except Exception as e:
            display.error(f"Failed to send Telegram: {e}")

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
            display.debug(f"Error getting Telegram updates: {e}")

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
                "/config - Ver todas configurações\n"
                "/position - Posição aberta atual\n"
                "/capital - Capital atual\n\n"
                "<b>⚙️ Controle:</b>\n"
                "/pause - Pausar bot (não abre novos trades)\n"
                "/resume - Retomar bot\n"
                "/forcecheck - Forçar verificação de novo candle\n\n"
                "<b>🔧 Configuração:</b>\n"
                "/setconf &lt;0-100&gt; - Confiança mínima (%)\n"
                "/setrisk &lt;0.1-2.0&gt; - Risco por trade (%)\n"
                "/setsl &lt;1-10&gt; - Stop Loss (x ATR)\n"
                "/settp &lt;1-20&gt; - Take Profit (x ATR)\n"
                "/setcooldown &lt;5-120&gt; - Cooldown entre trades (min)"
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
            display.info("⏸️ Bot pausado via Telegram")
            return "⏸️ <b>Bot Pausado</b>\n\nNão abrirá novos trades.\nPosições abertas continuam sendo monitoradas.\n\nUse /resume para retomar."

        # Resume command
        elif command == "/resume":
            if not hasattr(bot, 'paused'):
                bot.paused = False
                return "▶️ Bot já está ativo"

            if not bot.paused:
                return "▶️ Bot já está ativo"

            bot.paused = False
            display.info("▶️ Bot retomado via Telegram")
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
                display.info(f"⚙️ Confiança alterada via Telegram: {old_conf:.0f}% → {new_conf:.0f}%")

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
                display.info(f"⚙️ Risco alterado via Telegram: {old_risk:.2f}% → {new_risk:.2f}%")

                return f"✅ <b>Risco Atualizado</b>\n\n{old_risk:.2f}% → {new_risk:.2f}%"
            except ValueError:
                return "❌ Valor inválido. Use um número entre 0.1 e 2.0."

        # Set SL command
        elif command == "/setsl":
            if not args:
                return "❌ Uso: /setsl &lt;valor&gt;\n\nExemplo: /setsl 3.5"

            try:
                new_sl = float(args[0])
                if not (1.0 <= new_sl <= 10.0):
                    return "❌ SL deve estar entre 1.0 e 10.0 (x ATR)"

                old_sl = bot.sl_atr_mult
                bot.sl_atr_mult = new_sl
                display.info(f"⚙️ SL alterado via Telegram: {old_sl:.1f}x → {new_sl:.1f}x ATR")

                return f"✅ <b>Stop Loss Atualizado</b>\n\n{old_sl:.1f}x → {new_sl:.1f}x ATR"
            except ValueError:
                return "❌ Valor inválido. Use um número entre 1.0 e 10.0."

        # Set TP command
        elif command == "/settp":
            if not args:
                return "❌ Uso: /settp &lt;valor&gt;\n\nExemplo: /settp 5.0"

            try:
                new_tp = float(args[0])
                if not (1.0 <= new_tp <= 20.0):
                    return "❌ TP deve estar entre 1.0 e 20.0 (x ATR)"

                old_tp = bot.tp_atr_mult
                bot.tp_atr_mult = new_tp
                display.info(f"⚙️ TP alterado via Telegram: {old_tp:.1f}x → {new_tp:.1f}x ATR")

                return f"✅ <b>Take Profit Atualizado</b>\n\n{old_tp:.1f}x → {new_tp:.1f}x ATR"
            except ValueError:
                return "❌ Valor inválido. Use um número entre 1.0 e 20.0."

        # Set cooldown command
        elif command == "/setcooldown":
            if not args:
                return "❌ Uso: /setcooldown &lt;minutos&gt;\n\nExemplo: /setcooldown 30"

            try:
                new_cooldown_min = int(args[0])
                if not (5 <= new_cooldown_min <= 120):
                    return "❌ Cooldown deve estar entre 5 e 120 minutos"

                old_cooldown_min = bot.trade_cooldown / 60
                bot.trade_cooldown = new_cooldown_min * 60
                display.info(f"⚙️ Cooldown alterado via Telegram: {old_cooldown_min:.0f}min → {new_cooldown_min}min")

                return f"✅ <b>Cooldown Atualizado</b>\n\n{old_cooldown_min:.0f}min → {new_cooldown_min}min"
            except ValueError:
                return "❌ Valor inválido. Use um número inteiro entre 5 e 120."

        # Config command - show all settings
        elif command == "/config":
            return (
                f"⚙️ <b>Configurações Atuais</b>\n\n"
                f"<b>Trading:</b>\n"
                f"Confiança Min: {bot.min_confidence*100:.0f}%\n"
                f"Risco/Trade: {bot.risk_per_trade*100:.2f}%\n"
                f"Stop Loss: {bot.sl_atr_mult:.1f}x ATR\n"
                f"Take Profit: {bot.tp_atr_mult:.1f}x ATR\n"
                f"Cooldown: {bot.trade_cooldown/60:.0f}min\n\n"
                f"<b>Modelo:</b>\n"
                f"Threshold: {bot.optimal_threshold:.3f}\n"
                f"Timeframe: {bot.timeframe}m\n\n"
                f"<b>Sistema:</b>\n"
                f"Modo: {'🔵 DRY RUN' if bot.dry_run else '🔴 LIVE'}\n"
                f"Network: {'TESTNET' if bot.bybit_testnet else 'MAINNET'}\n"
                f"Estado: {'⏸️ PAUSADO' if hasattr(bot, 'paused') and bot.paused else '▶️ ATIVO'}"
            )

        # Force check command
        elif command == "/forcecheck":
            # Mark last analyzed as None to force new analysis
            bot.last_analyzed_candle_time = None
            display.info("🔄 Forçando nova verificação via Telegram")
            return "🔄 <b>Verificação Forçada</b>\n\nO bot verificará novo candle na próxima iteração."

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

                    display.info(f"📱 Comando Telegram recebido: {command}")

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
    display.info(f"🔍 Loading model: {model_path}")

    try:
        with open(model_path, 'rb') as f:
            data = pickle.load(f)
        display.info(f"   ✅ Loaded with standard pickle")
    except Exception:
        with open(model_path, 'rb') as f:
            data = UniversalUnpickler(f).load()
        display.info(f"   ✅ Loaded with custom unpickler")

    result = {
        'model': None,
        'feature_names': None,
        'optimal_threshold': 0.5,
        'raw_data': data
    }

    data_type = type(data).__name__
    display.info(f"   📦 Type: {data_type}")

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

    display.info(f"   📊 Features: {len(result['feature_names'])}")
    display.info(f"   🎯 Threshold: {result['optimal_threshold']:.3f}")

    return result


# ============================================================================
# FEATURE ENGINEERING (from 1.py)
# ============================================================================

def create_advanced_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add MASTER TRADER advanced features (matching train_master_scalper.py EXACTLY).

    This function replicates the create_advanced_features() from train_master_scalper.py
    to ensure bot generates SAME features as training.
    """
    display.info("   Creating advanced features (matching train_master_scalper.py)...")

    df_features = df.copy()

    # Multi-period momentum
    for period in [3, 5, 8, 13, 21]:
        df_features[f'momentum_{period}'] = df_features['close'].pct_change(period) * 100
        df_features[f'volume_ratio_{period}'] = df_features['volume'] / df_features['volume'].rolling(period).mean()

    # Trend strength
    df_features['trend_strength'] = (df_features['ema50'] - df_features['ema200']) / df_features['ema200'] * 100

    # Volatility regimes
    df_features['volatility_regime'] = (df_features['atr'] / df_features['atr'].rolling(50).mean())

    # Price position in recent range
    df_features['price_position'] = (
        (df_features['close'] - df_features['low'].rolling(20).min()) /
        (df_features['high'].rolling(20).max() - df_features['low'].rolling(20).min())
    )

    # Volume momentum
    df_features['volume_momentum'] = df_features['volume'].pct_change(5)

    # Acceleration
    df_features['price_acceleration'] = df_features['close'].diff(2) - df_features['close'].diff(1)

    display.info(f"   ✅ Advanced features added: {len(df_features.columns)} total columns")

    return df_features


def create_advanced_features_v2(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add V2 ADVANCED features - MUST match train_master_scalper_v2.py exactly!
    (Copied from 2.py for compatibility)
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
    df_features['price_volume_corr'] = df_features['close'].rolling(20).corr(df_features['volume'])

    # === ACCELERATION & JERK ===
    df_features['price_velocity'] = df_features['close'].diff(1)
    df_features['price_acceleration'] = df_features['price_velocity'].diff(1)
    df_features['price_jerk'] = df_features['price_acceleration'].diff(1)

    # === HIGHER ORDER MOMENTS ===
    for period in [10, 20, 50]:
        returns = df_features['close'].pct_change()
        df_features[f'returns_skew_{period}'] = returns.rolling(period).skew()
        df_features[f'returns_kurt_{period}'] = returns.rolling(period).kurt()
        df_features[f'returns_std_{period}'] = returns.rolling(period).std()

    # === MARKET MICROSTRUCTURE ===
    df_features['spread_proxy'] = (df_features['high'] - df_features['low']) / df_features['close'] * 100

    for period in [10, 20]:
        ma = df_features['close'].rolling(period).mean()
        df_features[f'price_efficiency_{period}'] = (df_features['close'] - ma) / ma * 100

    # === REGIME DETECTION ===
    df_features['adx_proxy'] = df_features['atr'] / df_features['close'] * 100
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

    # === CANDLE PATTERNS ===
    body = abs(df_features['close'] - df_features['open'])
    upper_shadow = df_features['high'] - df_features[['close', 'open']].max(axis=1)
    lower_shadow = df_features[['close', 'open']].min(axis=1) - df_features['low']

    df_features['body_size'] = body / df_features['close'] * 100
    df_features['upper_shadow_ratio'] = upper_shadow / (body + 1e-8)
    df_features['lower_shadow_ratio'] = lower_shadow / (body + 1e-8)

    return df_features


def create_features_for_bot(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create features matching train_master_scalper.py.

    This adds advanced features on top of FeatureStore features to ensure
    compatibility with ml_model_master_scalper_365d.pkl.
    """
    display.info("   Creating advanced features (matching train_master_scalper.py)...")

    df_feat = df.copy()

    # Log initial columns
    initial_cols = set(df_feat.columns)
    display.info(f"   📊 Starting with {len(initial_cols)} columns from FeatureStore")

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

    # Log final columns
    final_cols = set(df_feat.columns)
    added_cols = final_cols - initial_cols
    display.info(f"   ✅ Features created: {len(final_cols)} total ({len(added_cols)} added)")

    # Save feature list to file for comparison
    try:
        with open('/tmp/live_bot_features.txt', 'w') as f:
            for feat in sorted(df_feat.columns):
                f.write(f"{feat}\n")
        display.info(f"   📝 Feature list saved to /tmp/live_bot_features.txt")
    except:
        pass

    return df_feat


def make_prediction(model, model_data, df, feature_names):
    """Make prediction using ensemble model."""

    # CRITICAL: Ensure df is DataFrame, not Series
    if isinstance(df, pd.Series):
        df = df.to_frame().T  # Convert Series to DataFrame
    """Make prediction using ensemble model."""

    # 🔥 CRITICAL: Check for missing features
    df_features = set(df.columns)
    model_features = set(feature_names)
    missing_features = model_features - df_features

    if missing_features:
        display.warning(f"⚠️ MISSING {len(missing_features)} FEATURES:")
        for feat in list(missing_features)[:10]:
            display.warning(f"   - {feat}")
        if len(missing_features) > 10:
            display.warning(f"   ... and {len(missing_features) - 10} more")

        # Fill missing features with 0
        for feat in missing_features:
            df[feat] = 0
        display.warning(f"⚠️ Filled missing features with 0 (may affect predictions!)")

    # Check if using ModelWrapper ensemble
    if hasattr(model, 'models_list'):
        display.info("   🔄 Using ensemble prediction from ModelWrapper")

        # Prepare features - ensure correct order
        X = df[feature_names].fillna(0).values

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
                display.warning(f"   ⚠️  Model {i} failed: {e}")
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

        display.info(f"   📊 Ensemble: {len(predictions)}/{len(model.models_list)} models succeeded")

    else:
        # Standard model
        X = df[feature_names].fillna(0).values

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
        global display

        # Load config
        self.config = load_config('standard')
        pass  # Usando EnhancedLogger('INFO', log_to_file=True)

        # Environment variables
        self.symbol = os.getenv('SYMBOL', 'BTCUSDT')
        self.timeframe = os.getenv('TIMEFRAME', '15')
        self.model_path = os.getenv('MODEL_PATH', 'ml_model_master_scalper_365d.pkl')  # Modelo otimizado (2788% ROI em 365 dias)

        # Trading parameters - Sistema de TRÊS Confianças
        # Confiança BAIXA (25%) - SL 1.5x, TP 1.0x, Risco 0.5%
        self.min_confidence_low = float(os.getenv('MIN_ML_CONFIDENCE_LOW', '0.25'))
        self.risk_low = float(os.getenv('RISK_LOW_PCT', '0.50')) / 100
        self.sl_low = float(os.getenv('SL_LOW_MULT', '1.5'))
        self.tp_low = float(os.getenv('TP_LOW_MULT', '1.0'))

        # Confiança ALTA (40%) - SL 1.5x, TP 1.0x, Risco 0.75%
        self.min_confidence_high = float(os.getenv('MIN_ML_CONFIDENCE_HIGH', '0.40'))
        self.risk_high = float(os.getenv('RISK_HIGH_PCT', '0.75')) / 100
        self.sl_high = float(os.getenv('SL_HIGH_MULT', '1.5'))
        self.tp_high = float(os.getenv('TP_HIGH_MULT', '1.0'))

        # Confiança ULTRA (60%) - SL 2.0x, TP 0.7x, Risco 1.0%
        self.min_confidence_ultra = float(os.getenv('MIN_ML_CONFIDENCE_ULTRA', '0.60'))
        self.risk_ultra = float(os.getenv('RISK_ULTRA_PCT', '1.0')) / 100
        self.sl_ultra = float(os.getenv('SL_ULTRA_MULT', '2.0'))
        self.tp_ultra = float(os.getenv('TP_ULTRA_MULT', '0.7'))

        # Compatibilidade com código antigo (usa valores da LOW)
        self.min_confidence = self.min_confidence_low
        self.risk_per_trade = self.risk_low

        self.initial_capital = float(os.getenv('INITIAL_CAPITAL', '125.0'))

        # ===================================================================
        # LOGS INICIAIS - Sistema de Três Níveis de Confiança
        # ===================================================================
        display.info("=" * 80)
        display.info("📝 Variáveis de Ambiente - Sistema de Três Níveis de Confiança")
        display.info("=" * 80)
        display.info("")
        display.info("# LOW (25%)")
        display.info(f"MIN_ML_CONFIDENCE_LOW={self.min_confidence_low:.2f}")
        display.info(f"RISK_LOW_PCT={self.risk_low * 100:.2f}%")
        display.info(f"SL_LOW_MULT={self.sl_low}x")
        display.info(f"TP_LOW_MULT={self.tp_low}x")
        display.info("")
        display.info("# HIGH (40%)")
        display.info(f"MIN_ML_CONFIDENCE_HIGH={self.min_confidence_high:.2f}")
        display.info(f"RISK_HIGH_PCT={self.risk_high * 100:.2f}%")
        display.info(f"SL_HIGH_MULT={self.sl_high}x")
        display.info(f"TP_HIGH_MULT={self.tp_high}x")
        display.info("")
        display.info("# ULTRA (60%)")
        display.info(f"MIN_ML_CONFIDENCE_ULTRA={self.min_confidence_ultra:.2f}")
        display.info(f"RISK_ULTRA_PCT={self.risk_ultra * 100:.2f}%")
        display.info(f"SL_ULTRA_MULT={self.sl_ultra}x")
        display.info(f"TP_ULTRA_MULT={self.tp_ultra}x")
        display.info("")
        display.info("=" * 80)
        display.info("🎯 Como Funciona:")
        display.info("=" * 80)
        display.info("O bot agora verifica a confiança da predição e:")
        display.info(f"• Se >= {self.min_confidence_ultra:.0%}: usa nível ULTRA (SL {self.sl_ultra}x, TP {self.tp_ultra}x, Risco {self.risk_ultra*100:.2f}%)")
        display.info(f"• Se >= {self.min_confidence_high:.0%}: usa nível HIGH (SL {self.sl_high}x, TP {self.tp_high}x, Risco {self.risk_high*100:.2f}%)")
        display.info(f"• Se >= {self.min_confidence_low:.0%}: usa nível LOW (SL {self.sl_low}x, TP {self.tp_low}x, Risco {self.risk_low*100:.2f}%)")
        display.info(f"• Se < {self.min_confidence_low:.0%}: FILTERED (não entra)")
        display.info("")
        display.info("Cada trade agora mostrará nos logs qual nível foi usado e")
        display.info("exatamente quais parâmetros estão sendo aplicados!")
        display.info("=" * 80)
        display.info("")


        # Stop loss / Take profit multipliers (fallback - agora cada nível tem seus próprios)
        self.sl_atr_mult = float(os.getenv('SL_ATR_MULT', '2.0'))
        self.tp_atr_mult = float(os.getenv('TP_ATR_MULT', '0.7'))

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

        # Detect model version (same as 2.py)
        self.model_version = self._detect_model_version()
        display.info(f"📌 Detected model type: {self.model_version}")
        display.info(f"   Required features: {len(self.feature_names)}")

        # Fetch market meta (tick size, qty step, min qty)
        display.info("📊 Fetching market metadata...")
        try:
            self.tick_size, self.qty_step, self.min_qty = fetch_market_meta(self.rest_client, self.symbol)
        except Exception as e:
            display.warning(f"   ⚠️ Error fetching market meta: {e}. Using fallback.")
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

        # Analysis control flag
        self.analysis_in_progress = False
        # WebSocket will be started after __init__ completes

        # Load previous state (for cooldown persistence)
        self._load_state()

        display.info("=" * 80)
        display.info("🤖 LIVE TRADING BOT - SNIPER MODE")
        display.info("=" * 80)
        display.info(f"Symbol: {self.symbol}")
        display.info(f"Timeframe: {self.timeframe}m")
        display.info(f"Model: {Path(self.model_path).name}")
        display.info("")
        display.info("⚙️ Sistema de Três Níveis de Confiança:")
        display.info(f"   🟡 LOW:   {self.min_confidence_low*100:.0f}% confiança → Risco {self.risk_low*100:.2f}% | SL {self.sl_low}x | TP {self.tp_low}x")
        display.info(f"   🟠 HIGH:  {self.min_confidence_high*100:.0f}% confiança → Risco {self.risk_high*100:.2f}% | SL {self.sl_high}x | TP {self.tp_high}x")
        display.info(f"   🔴 ULTRA: {self.min_confidence_ultra*100:.0f}% confiança → Risco {self.risk_ultra*100:.2f}% | SL {self.sl_ultra}x | TP {self.tp_ultra}x")
        display.info("")
        display.info(f"SL: {self.sl_atr_mult}x ATR | TP: {self.tp_atr_mult}x ATR")
        display.info(f"Trade Cooldown: {self.trade_cooldown}s ({self.trade_cooldown/60:.1f}min)")
        display.info(f"Mode: {'🔵 DRY RUN' if self.dry_run else '🔴 LIVE TRADING'}")
        display.info(f"Exchange: {'TESTNET' if self.bybit_testnet else 'MAINNET'}")
        display.info("=" * 80)

        # Warning for live trading
        if not self.dry_run and not self.bybit_testnet:
            display.warning("⚠️" * 20)
            display.warning("⚠️ REAL TRADING MODE ON MAINNET!")
            display.warning("⚠️" * 20)

        # Send startup notification
        network = 'TESTNET' if self.bybit_testnet else 'MAINNET'
        self.telegram.send(
            f"🤖 <b>Bot Started</b>\n\n"
            f"Symbol: {self.symbol}\n"
            f"Timeframe: {self.timeframe}m\n\n"
            f"<b>Sistema de 3 Níveis:</b>\n"
            f"🔥 ULTRA ({self.min_confidence_ultra*100:.0f}%): SL {self.sl_ultra}x | TP {self.tp_ultra}x | R {self.risk_ultra*100:.2f}%\n"
            f"🟢 HIGH ({self.min_confidence_high*100:.0f}%): SL {self.sl_high}x | TP {self.tp_high}x | R {self.risk_high*100:.2f}%\n"
            f"🟡 LOW ({self.min_confidence_low*100:.0f}%): SL {self.sl_low}x | TP {self.tp_low}x | R {self.risk_low*100:.2f}%\n\n"
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
                            display.info(f"⏰ Cooldown ativo do trade anterior: {remaining:.0f}s restantes ({remaining/60:.1f}min)")
                        else:
                            display.info(f"✅ Cooldown do trade anterior expirou")
                            self.last_trade_time = None
        except Exception as e:
            display.warning(f"⚠️ Erro ao carregar estado: {e}")

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
            display.error(f"❌ Erro ao salvar estado: {e}")

    def _detect_model_version(self) -> str:
        """
        Detect model version based on feature names (same as 2.py).

        Returns:
            str: Model version ("V1", "V2", "Classical", or "Unknown")
        """
        feature_names = self.feature_names

        # Feature signatures for each version
        classical_features = ['sma_7', 'sma_21', 'ema_7', 'ema_21']
        v2_features = ['returns_kurt_50', 'returns_skew_50', 'rsi_5', 'roc_20', 'bb_width_50', 'price_position_10']
        v1_features = ['momentum_3', 'momentum_5', 'volume_ratio_3', 'price_position']

        has_classical = any(f in feature_names for f in classical_features)
        has_v2 = any(f in feature_names for f in v2_features)
        has_v1 = any(f in feature_names for f in v1_features)

        if has_classical:
            return "Classical"
        elif has_v2:
            return "V2"
        elif has_v1:
            return "V1"
        else:
            return "Unknown"

    def get_current_data(self) -> pd.DataFrame:
        """Download latest data and build features with timeout protection."""

        # Download data (30 days lookback for indicators)
        lookback_days = 30

        try:
            import signal
            from contextlib import contextmanager

            @contextmanager
            def timeout_context(seconds):
                """Context manager for timeout protection."""
                def timeout_handler(signum, frame):
                    raise TimeoutError(f"Operation timed out after {seconds}s")

                # Set alarm (only works on Unix)
                if hasattr(signal, 'SIGALRM'):
                    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(seconds)
                    try:
                        yield
                    finally:
                        signal.alarm(0)
                        signal.signal(signal.SIGALRM, old_handler)
                else:
                    # Windows doesn't support SIGALRM, skip timeout
                    yield

            # Quick data download (OPTIMIZED - no logs)
            with timeout_context(120):
                df = self.data_manager.get_data(
                    self.symbol,
                    f'{self.timeframe}m',
                    lookback_days,
                    False  # use_cache=False
                )

            if df.empty:
                raise ValueError("No data received")

            # Build features (FAST - no logs)
            df_features = self.feature_store.build_features(df, normalize=False)

            # Add advanced features based on model version
            if self.model_version == "V1":
                df_features = create_advanced_features(df_features)
            elif self.model_version == "V2":
                df_features = create_advanced_features_v2(df_features)
            elif self.model_version == "Classical":
                pass  # Classical doesn't need extra features
            else:
                df_features = create_advanced_features(df_features)

            return df_features

        except TimeoutError as e:
            display.error(f"❌ Download TIMEOUT: {e}")
            raise
        except Exception as e:
            display.error(f"❌ Error fetching data: {e}")
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

        display.info("")
        display.info(f"{direction_emoji} {direction.upper()} | Entrada: ${entry_price:,.2f} | Atual: ${current_price:,.2f}")
        display.info(f"{pnl_emoji} PnL Líquido: {pnl_pct_net:+.2f}% (${pnl_amount_net:+,.2f}) | Duração: {int(hours)}h {int(minutes)}m")
        display.info(f"🛑 SL: ${sl:,.2f} ({dist_sl:+.2f}%) | 🎯 TP: ${tp:,.2f} ({dist_tp:+.2f}%)")

    def check_position_exit(self, current_candle) -> bool:
        """Check if current position should be exited."""
        if not self.position:
            return False

        # Update last_price for tracking
        self.last_price = current_candle['close']

        # Show current position status
        # self.show_position_status(current_candle['close'])  # Removido - duplicado

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

    def calculate_position_size(self, price: float, sl_price: float, risk_pct: float = None) -> float:
        """
        Calculate BTC quantity based on risk.

        Args:
            price: Current price
            sl_price: Stop loss price
            risk_pct: Risk percentage (optional, uses self.risk_per_trade if None)

        CRITICAL PROTECTION: Limits position to 95% of capital (same as backtest)
        """
        # Use provided risk or default
        risk_to_use = risk_pct if risk_pct is not None else self.risk_per_trade

        sl_dist = abs((sl_price - price) / price)
        risk_amt = self.capital * risk_to_use

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

    def open_position(self, current_candle, signal, confidence, risk_used: float = None, conf_level: str = "STANDARD", sl_mult: float = None, tp_mult: float = None):
        """Open a new position with automatic SL/TP on Bybit.

        Args:
            current_candle: Current candle data
            signal: Trade signal (1=long, -1=short)
            confidence: ML confidence level
            risk_used: Risk percentage to use (optional)
            conf_level: Confidence level name for logging (LOW/HIGH/ULTRA/STANDARD)
            sl_mult: Stop loss ATR multiplier (optional, uses default if not provided)
            tp_mult: Take profit ATR multiplier (optional, uses default if not provided)
        """

        direction = 'long' if signal == 1 else 'short'
        price = current_candle['close']
        atr = current_candle.get('atr', price * 0.01)

        # Use custom multipliers or fallback to defaults
        sl_multiplier = sl_mult if sl_mult is not None else self.sl_atr_mult
        tp_multiplier = tp_mult if tp_mult is not None else self.tp_atr_mult

        # Calculate SL and TP (raw values)
        if direction == 'long':
            sl = price - (atr * sl_multiplier)
            tp = price + (atr * tp_multiplier)
            side = 'Buy'
        else:
            sl = price + (atr * sl_multiplier)
            tp = price - (atr * tp_multiplier)
            side = 'Sell'

        # Calculate quantity in BTC with custom risk
        qty_btc = self.calculate_position_size(price, sl, risk_pct=risk_used)

        # Round prices and quantities using market meta
        sl = round_price(sl, self.tick_size)
        tp = round_price(tp, self.tick_size)
        qty_btc = round_qty(qty_btc, self.qty_step, self.min_qty)
        price = round_price(price, self.tick_size)
        size_usd = qty_btc * price

        # VALIDATIONS
        if qty_btc < self.min_qty:
            display.error(f"❌ Quantity {qty_btc} BTC below minimum {self.min_qty}!")
            return

        if size_usd < 10:
            display.warning(f"⚠️ Size too small: ${size_usd:,.2f} < $10")
            return

        # Validate SL makes sense
        if direction == 'long' and sl >= price:
            display.error(f"❌ Invalid SL for LONG: ${sl:,.2f} >= ${price:,.2f}")
            return
        if direction == 'short' and sl <= price:
            display.error(f"❌ Invalid SL for SHORT: ${sl:,.2f} <= ${price:,.2f}")
            return

        # Validate TP makes sense
        if direction == 'long' and tp <= price:
            display.error(f"❌ Invalid TP for LONG: ${tp:,.2f} <= ${price:,.2f}")
            return
        if direction == 'short' and tp >= price:
            display.error(f"❌ Invalid TP for SHORT: ${tp:,.2f} >= ${price:,.2f}")
            return

        # Log position details
        direction_emoji = "🟢" if direction == 'long' else "🔴"
        conf_emoji = "🟡" if conf_level == "LOW" else "🟢" if conf_level == "HIGH" else "🔥" if conf_level == "ULTRA" else "⚪"
        risk_pct = (risk_used if risk_used else self.risk_per_trade) * 100

        display.info("")
        display.info("=" * 80)
        display.info(f"{direction_emoji} ABRINDO POSIÇÃO {direction.upper()} ({conf_emoji} {conf_level})")
        display.info("=" * 80)
        display.info(f"Preço: ${price:,.2f}")
        display.info(f"Confiança: {confidence:.1%} | Nível: {conf_emoji} {conf_level}")
        display.info(f"Risco: {risk_pct:.2f}% do capital")
        display.info(f"Qtd: {qty_btc} BTC = ${size_usd:,.2f}")
        display.info(f"🛑 SL: ${sl:,.2f} ({-abs((sl-price)/price)*100:.1f}%) [ATR×{sl_multiplier}]")
        display.info(f"🎯 TP: ${tp:,.2f} ({abs((tp-price)/price)*100:.1f}%) [ATR×{tp_multiplier}]")
        display.info(f"ATR: ${atr:,.2f}")
        display.info("=" * 80)

        order_id = None
        actual_entry_price = price
        is_paper = self.dry_run

        # Execute real order if not dry run
        if not self.dry_run:
            try:
                display.info(f"💰 Sending REAL {side} order...")

                # Place Market order
                order = self.rest_client.place_order(
                    symbol=self.symbol,
                    side=side,
                    order_type='Market',
                    qty=qty_btc
                )

                display.info(f"📥 API Response: {order}")

                if order and 'retCode' in order and order['retCode'] == 0:
                    if 'result' in order and isinstance(order['result'], dict):
                        result = order['result']

                        if 'orderId' in result:
                            order_id = result['orderId']
                            display.info(f"✅ Order executed! ID: {order_id}")

                            # Get actual fill price if available
                            if 'price' in result and result['price']:
                                try:
                                    actual_entry_price = float(result['price'])
                                except:
                                    actual_entry_price = price

                        # Configure SL/TP with retry
                        display.info(f"📍 Setting SL/TP on Bybit...")
                        display.info(f"   SL: ${sl:,.1f} | TP: ${tp:,.1f}")

                        # Wait for position to be created (CRITICAL!)
                        display.info("⏳ Waiting for position to be created...")
                        time.sleep(3)

                        # Verify position exists
                        position_exists = False
                        try:
                            positions = self.rest_client.get_positions(symbol=self.symbol)
                            positions_list = positions.get('result', {}).get('list', [])
                            for pos in positions_list:
                                if float(pos.get('size', 0)) > 0:
                                    position_exists = True
                                    display.info(f"✅ Position confirmed: {pos.get('size')} BTC")
                                    break
                        except Exception as e:
                            display.warning(f"⚠️ Error verifying position: {e}")

                        if not position_exists:
                            display.error(f"❌ Position not created - cannot set SL/TP!")
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
                                    display.info(f"✅ SL/TP configured on Bybit!")
                                    return True
                                else:
                                    error_msg = sl_tp_result.get('retMsg', 'Unknown') if sl_tp_result else 'No response'
                                    raise Exception(f"API error: {error_msg}")

                            result = retry_with_backoff(_set_sl_tp, max_retries=3, initial_delay=2.0)
                            if not result:
                                display.error(f"❌ Failed to set SL/TP after retries!")

                else:
                    raise Exception("API error - order failed")

            except Exception as e:
                display.error(f"❌ Order execution failed: {e}")
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
            f"{direction_emoji} <b>ENTRADA {direction.upper()}</b> {mode_str} {conf_emoji} <b>{conf_level}</b>\n\n"
            f"Preço: ${actual_entry_price:,.2f}\n"
            f"Qtd: {qty_btc} BTC (${size_usd:,.2f})\n"
            f"Confiança: {confidence:.1%} ({conf_level})\n"
            f"Risco: {risk_pct:.2f}% do capital\n\n"
            f"🛑 SL: ${sl:,.2f} [ATR×{sl_multiplier}]\n"
            f"🎯 TP: ${tp:,.2f} [ATR×{tp_multiplier}]\n"
            f"ATR: ${atr:,.2f}\n\n"
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
                                display.info("✅ Posição fechada pela Bybit")

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

                                display.info(f"✅ Saída: ${exit_price:,.2f} ({reason})")
                                return (exit_price, reason)

                    # Position not found = was closed
                    display.info("✅ Position not found - was closed")
                    exit_price = self.last_price if self.last_price else self.position['take_profit']
                    return (exit_price, 'take_profit')

        except Exception as e:
            display.error(f"⚠️ Error checking position: {e}")
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

        display.info("")
        display.info("=" * 80)
        display.info(f"{result_emoji} FECHANDO POSIÇÃO {direction.upper()} - {reason_emoji} {reason_text}")
        display.info("=" * 80)
        display.info(f"Entrada: ${entry_price:,.2f} @ {self.position['entry_time']}")
        display.info(f"Saída:   ${exit_price:,.2f} @ {current_candle.name}")
        display.info(f"Duração: {duration}")
        display.info(f"PnL Líquido: {pnl_pct_after_fees:+.2f}% (${pnl_amount_after_fees:+,.2f})")
        display.info(f"Taxas: ${fee:.2f}")
        display.info("=" * 80)

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
            display.info("📋 Paper trading mode - no positions to recover")
            return

        try:
            display.info("🔍 Checking for open positions on Bybit...")
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

                                display.info("")
                                display.info("=" * 80)
                                display.info("🔄 POSIÇÃO RECUPERADA DA BYBIT")
                                display.info("=" * 80)
                                display.info(f"Direção: {direction.upper()}")
                                display.info(f"Tamanho: {size} BTC")
                                display.info(f"Entrada: ${entry_price:,.2f}")
                                display.info(f"Preço Atual: ${mark_price:,.2f}")
                                if sl:
                                    display.info(f"SL: ${sl:,.2f}")
                                if tp:
                                    display.info(f"TP: ${tp:,.2f}")
                                display.info("=" * 80)

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

                    display.info("✅ No open positions found")
            else:
                display.warning(f"⚠️ API error checking positions: {positions}")

        except Exception as e:
            display.error(f"❌ Error recovering positions: {e}")
            import traceback
            traceback.print_exc()

    def calculate_seconds_until_candle_close(self, timeframe_minutes: int) -> int:
        """
        Calculate seconds until next candle closes.

        Args:
            timeframe_minutes: Candle timeframe in minutes (e.g., 15)

        Returns:
            Seconds until next candle close
        """
        from datetime import timezone

        now_utc = datetime.now(timezone.utc)
        current_minute = now_utc.minute
        current_second = now_utc.second

        # Calculate how many minutes into the current candle period we are
        minutes_into_candle = current_minute % timeframe_minutes

        # Calculate minutes until candle closes
        minutes_until_close = timeframe_minutes - minutes_into_candle

        # If we're at exactly 0 seconds, the candle just closed
        if minutes_until_close == timeframe_minutes and current_second == 0:
            minutes_until_close = 0

        # Calculate total seconds
        seconds_until_close = (minutes_until_close * 60) - current_second

        # Ensure positive
        if seconds_until_close < 0:
            seconds_until_close += timeframe_minutes * 60

        return seconds_until_close


    def _check_feature_compatibility(self):
        """Verifica compatibilidade de features (uma vez no inicio)."""
        display.info("Checking feature compatibility...")
        try:
            df_test = self.get_current_data()
            if df_test is not None and not df_test.empty:
                df_features = set(df_test.columns)
                model_features = set(self.feature_names)

                missing = model_features - df_features
                extra = df_features - model_features

                display.info(f"  Model expects: {len(model_features)} features")
                display.info(f"  Bot generates: {len(df_features)} features")

                if missing:
                    display.warning(f"  MISSING {len(missing)} features")
                    for feat in sorted(missing):
                        display.warning(f"    - {feat}")
                    display.warning("  These will be filled with 0 - may affect predictions!")
                else:
                    display.info("  All features present!")

                if extra:
                    display.info(f"  {len(extra)} extra features (unused by model)")
        except Exception as e:
            display.warning(f"  Could not check features: {e}")
        display.info("")

    def run(self):
        """
        LOOP SIMPLIFICADO - Igual no_sleep

        - Checa a cada 30s
        - Entra em qualquer momento (nao espera candle fechar)
        - Usa iloc[-1] (ultimo candle, mesmo se aberto)
        - 93% das features sao de historico (funciona!)
        """
        display.info("="*80)
        display.info("BOT INICIADO - LOOP SIMPLIFICADO (30s)")
        display.info("="*80)
        display.info(f"Symbol: {self.symbol}")
        display.info(f"Timeframe: {self.timeframe}m")
        display.info(f"Check Interval: 30s")
        display.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        display.info(f"Network: {'TESTNET' if self.bybit_testnet else 'MAINNET'}")
        display.info("")

        # Inicializacao
        iteration = 0
        last_heartbeat = datetime.now()
        heartbeat_interval = 300  # 5 minutos
        check_interval = 30  # Loop a cada 30s

        # Verificar features
        self._check_feature_compatibility()

        # Recuperar posicoes abertas (se LIVE mode)
        if not self.dry_run:
            self.recover_open_positions()

        try:
            while True:
                iteration += 1

                try:
                    # STEP 1: Baixar dados (SEMPRE)
                    display.info("="*80)
                    display.info(f"ITERATION {iteration} - {datetime.now().strftime('%H:%M:%S')}")
                    display.info("="*80)

                    df = self.get_current_data()
                    if df is None or df.empty:
                        display.warning("No data received")
                        continue

                    # STEP 2: Pegar ULTIMO candle (iloc[-1])
                    current = df.iloc[-1]  # Ultimo candle
                    current_candle_time = current.name
                    price = current['close']

                    display.info(f"Price: {price:.2f}")
                    display.info(f"Candle: {current_candle_time}")

                    # STEP 3: Se tem posicao, monitora e checa saida
                    if self.position:
                        self.show_position_status(price)

                        # Checar saida
                        if self.check_position_exit(current):
                            display.info("Position closed")
                            continue

                    # STEP 4: Se NAO tem posicao, checa entrada
                    if not self.position:
                        # Checar cooldown
                        if self.last_trade_time:
                            elapsed = (datetime.now() - self.last_trade_time).total_seconds()
                            if elapsed < self.trade_cooldown:
                                remaining = int((self.trade_cooldown - elapsed) / 60)
                                display.info(f"Cooldown: {remaining}min restantes")
                                continue

                        # Checar se bot esta pausado
                        if hasattr(self, 'paused') and self.paused:
                            display.info("Bot pausado - aguardando /resume")
                            continue

                        # Fazer predicao no ULTIMO candle (iloc[-1:]) - FAST
                        df_single = df.iloc[-1:].copy()  # Ultimo candle como DataFrame
                        predictions = make_prediction(
                            self.model, 
                            self.model_data, 
                            df_single, 
                            self.feature_names
                        )

                        if predictions is None or len(predictions) == 0:
                            display.warning("No predictions")
                            continue

                        pred = predictions[0]

                        # Converter predicao
                        if isinstance(pred, (int, float)):
                            ml_prob_up = float(pred)
                        else:
                            ml_prob_up = float(pred[0]) if len(pred) > 0 else 0.5

                        # Calcular confianca
                        ml_confidence = abs(ml_prob_up - 0.5) * 2.0

                        # Determinar sinal
                        if ml_prob_up > 0.5:
                            signal = 1
                            sig_name = "LONG"
                        elif ml_prob_up < 0.5:
                            signal = -1
                            sig_name = "SHORT"
                        else:
                            signal = 0
                            sig_name = "NEUTRO"

                        # Sistema de 3 niveis
                        passes = False
                        if ml_confidence >= self.min_confidence_ultra:
                            conf_level = "ULTRA"
                            risk_to_use = self.risk_ultra
                            sl_to_use = self.sl_ultra
                            tp_to_use = self.tp_ultra
                            passes = True
                        elif ml_confidence >= self.min_confidence_high:
                            conf_level = "HIGH"
                            risk_to_use = self.risk_high
                            sl_to_use = self.sl_high
                            tp_to_use = self.tp_high
                            passes = True
                        elif ml_confidence >= self.min_confidence_low:
                            conf_level = "LOW"
                            risk_to_use = self.risk_low
                            sl_to_use = self.sl_low
                            tp_to_use = self.tp_low
                            passes = True
                        else:
                            conf_level = "FILTERED"
                            passes = False

                        status = "PASS" if (signal != 0 and passes) else "FILTERED"

                        display.info(f"Signal: {sig_name}")
                        display.info(f"Confidence: {ml_confidence:.1%}")
                        display.info(f"Level: {conf_level}")
                        display.info(f"Status: {status}")

                        # Abrir posicao se sinal valido
                        if signal != 0 and passes:
                            display.info("="*80)
                            display.info(f"OPENING {sig_name} POSITION - {conf_level}")
                            display.info("="*80)

                            self.open_position(
                                current, 
                                signal, 
                                ml_confidence,
                                risk_used=risk_to_use,
                                conf_level=conf_level,
                                sl_mult=sl_to_use,
                                tp_mult=tp_to_use
                            )

                    # STEP 5: Heartbeat (log a cada 5min)
                    now = datetime.now()
                    if (now - last_heartbeat).total_seconds() >= heartbeat_interval:
                        display.info(f"Heartbeat #{iteration} - Status: {'Position open' if self.position else 'No position'}")
                        last_heartbeat = now

                    # STEP 6: Checar comandos Telegram
                    if self.telegram:
                        self.telegram.check_commands()

                    # STEP 7: Loop continuo (SEM SLEEP - modo no_sleep)
                    # Nao aguarda - roda o mais rapido possivel

                except Exception as e:
                    display.error(f"Loop error: {e}")
                    import traceback
                    traceback.print_exc()

        except KeyboardInterrupt:
            display.info("")
            display.info("="*80)
            display.info("BOT STOPPED BY USER")
            display.info("="*80)

            if self.position:
                display.warning("Position still open - close manually!")


def main():
    try:
        bot = LiveTradingBot()
        bot.run()
    except KeyboardInterrupt:
        display.info("Bot stopped by user")
    except Exception as e:
        display.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
