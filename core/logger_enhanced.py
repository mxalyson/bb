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
        """Info message"""
        print(f"  {emoji} {message}")

    def success(self, message: str):
        """Success message"""
        print(f"  {Colors.GREEN}✅ {message}{Colors.RESET}")

    def warning(self, message: str):
        """Warning message"""
        print(f"  {Colors.YELLOW}⚠️  {message}{Colors.RESET}")

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
