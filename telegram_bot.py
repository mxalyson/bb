"""
Telegram Bot Integration
Provides remote control and monitoring via Telegram.
"""

import os
import logging
from datetime import datetime
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

logger = logging.getLogger(__name__)


class TelegramBot:
    """
    Telegram bot for controlling and monitoring the trading bot.
    """

    def __init__(
        self,
        token: str,
        chat_id: str,
        trading_bot: Optional[object] = None
    ):
        """
        Initialize Telegram bot.

        Args:
            token: Telegram bot token
            chat_id: Authorized chat ID
            trading_bot: TradingBot instance to control
        """
        self.token = token
        self.chat_id = str(chat_id)
        self.trading_bot = trading_bot
        self.app = None

        logger.info(f"🤖 Telegram bot initialized - Chat ID: {self.chat_id}")

    def set_trading_bot(self, trading_bot: object):
        """Set the trading bot instance to control."""
        self.trading_bot = trading_bot

    async def _check_authorization(self, update: Update) -> bool:
        """Check if user is authorized."""
        user_id = str(update.effective_user.id)

        if user_id != self.chat_id:
            await update.message.reply_text("❌ Unauthorized access denied.")
            logger.warning(f"⚠️  Unauthorized access attempt from user {user_id}")
            return False

        return True

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if not await self._check_authorization(update):
            return

        keyboard = [
            [
                InlineKeyboardButton("▶️ Start Bot", callback_data='start_bot'),
                InlineKeyboardButton("⏸️ Stop Bot", callback_data='stop_bot')
            ],
            [
                InlineKeyboardButton("📊 Status", callback_data='status'),
                InlineKeyboardButton("💰 Balance", callback_data='balance')
            ],
            [
                InlineKeyboardButton("📈 Stats", callback_data='stats'),
                InlineKeyboardButton("📋 Position", callback_data='position')
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🤖 *BTC Scalper Bot Control Panel*\n\n"
            "Choose an action:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not await self._check_authorization(update):
            return

        help_text = """
🤖 *BTC Scalper Bot - Commands*

*Bot Control:*
/start - Show control panel
/startbot - Start trading bot
/stopbot - Stop trading bot

*Monitoring:*
/status - Bot status
/balance - Account balance
/position - Current position
/stats - Trading statistics

*Safety:*
/closeposition - Close current position
/emergency - Emergency stop (close all and stop)

*Info:*
/help - Show this help message
        """

        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def startbot_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /startbot command."""
        if not await self._check_authorization(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("❌ Trading bot not initialized!")
            return

        if self.trading_bot.is_running:
            await update.message.reply_text("⚠️  Bot is already running!")
            return

        self.trading_bot.start()
        await update.message.reply_text(
            f"✅ *Bot Started*\n\n"
            f"Symbol: {self.trading_bot.symbol}\n"
            f"Timeframe: {self.trading_bot.timeframe}m\n"
            f"Mode: {self.trading_bot.api.mode.upper()}\n\n"
            f"🚀 Bot is now monitoring the market...",
            parse_mode='Markdown'
        )

    async def stopbot_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stopbot command."""
        if not await self._check_authorization(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("❌ Trading bot not initialized!")
            return

        if not self.trading_bot.is_running:
            await update.message.reply_text("⚠️  Bot is not running!")
            return

        self.trading_bot.stop()
        await update.message.reply_text(
            "🛑 *Bot Stopped*\n\n"
            "Bot has been stopped. No new trades will be opened.\n"
            "Existing positions remain open.",
            parse_mode='Markdown'
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not await self._check_authorization(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("❌ Trading bot not initialized!")
            return

        status = self.trading_bot.get_status()

        status_emoji = "🟢 Running" if status['is_running'] else "🔴 Stopped"
        position_emoji = "📈 Yes" if status['has_position'] else "⏸️ No"

        message = (
            f"🤖 *Bot Status*\n\n"
            f"Status: {status_emoji}\n"
            f"Mode: {status['mode'].upper()}\n"
            f"Symbol: {status['symbol']}\n\n"
            f"Position: {position_emoji}\n"
            f"Trades Today: {status['trades_today']}\n"
            f"Daily PnL: ${status['daily_pnl']:.2f}\n"
            f"Balance: ${status['balance']:.2f}"
        )

        await update.message.reply_text(message, parse_mode='Markdown')

    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /balance command."""
        if not await self._check_authorization(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("❌ Trading bot not initialized!")
            return

        balance = self.trading_bot.api.get_balance()
        mode = self.trading_bot.api.mode

        message = (
            f"💰 *Account Balance*\n\n"
            f"Mode: {mode.upper()}\n"
            f"Balance: ${balance:,.2f}"
        )

        if mode == 'paper':
            stats = self.trading_bot.api.get_performance_stats()
            if stats:
                message += (
                    f"\n\n📊 *Paper Trading Stats*\n"
                    f"ROI: {stats['roi']:.2f}%\n"
                    f"Total PnL: ${stats['total_pnl']:.2f}"
                )

        await update.message.reply_text(message, parse_mode='Markdown')

    async def position_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /position command."""
        if not await self._check_authorization(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("❌ Trading bot not initialized!")
            return

        position = self.trading_bot.api.get_position(self.trading_bot.symbol)

        if not position:
            await update.message.reply_text("⏸️ No open position.")
            return

        current_price = self.trading_bot.api.get_latest_price(self.trading_bot.symbol)

        # Calculate unrealized PnL
        if position['side'] == 'long':
            pnl_pct = ((current_price - position['entry_price']) / position['entry_price']) * 100
        else:
            pnl_pct = ((position['entry_price'] - current_price) / position['entry_price']) * 100

        side_emoji = "📈 LONG" if position['side'] == 'long' else "📉 SHORT"
        pnl_emoji = "🟢" if pnl_pct > 0 else "🔴"

        message = (
            f"📋 *Current Position*\n\n"
            f"Side: {side_emoji}\n"
            f"Entry: ${position['entry_price']:,.2f}\n"
            f"Current: ${current_price:,.2f}\n"
            f"Size: ${position.get('size_usd', 0):,.2f}\n\n"
            f"Unrealized PnL: {pnl_emoji} {pnl_pct:+.2f}%\n\n"
        )

        if self.trading_bot.api.mode == 'paper':
            message += (
                f"SL: ${position.get('stop_loss', 0):,.2f}\n"
                f"TP1: ${position.get('take_profit_1', 0):,.2f}\n"
                f"TP2: ${position.get('take_profit_2', 0):,.2f}\n"
                f"TP3: ${position.get('take_profit_3', 0):,.2f}"
            )

        await update.message.reply_text(message, parse_mode='Markdown')

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command."""
        if not await self._check_authorization(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("❌ Trading bot not initialized!")
            return

        if self.trading_bot.api.mode != 'paper':
            await update.message.reply_text("⚠️  Stats only available in paper mode!")
            return

        stats = self.trading_bot.api.get_performance_stats()

        if not stats:
            await update.message.reply_text("📊 No trades yet!")
            return

        message = (
            f"📈 *Trading Statistics*\n\n"
            f"Total Trades: {stats['total_trades']}\n"
            f"Win Rate: {stats['win_rate']:.1f}%\n"
            f"Winning: {stats['winning_trades']} | Losing: {stats['losing_trades']}\n\n"
            f"Total PnL: ${stats['total_pnl']:.2f}\n"
            f"ROI: {stats['roi']:.2f}%\n\n"
            f"Avg Win: ${stats['avg_win']:.2f}\n"
            f"Avg Loss: ${stats['avg_loss']:.2f}\n"
            f"Profit Factor: {stats['profit_factor']:.2f}\n\n"
            f"Current Balance: ${stats['current_balance']:,.2f}"
        )

        await update.message.reply_text(message, parse_mode='Markdown')

    async def closeposition_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /closeposition command."""
        if not await self._check_authorization(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("❌ Trading bot not initialized!")
            return

        position = self.trading_bot.api.get_position(self.trading_bot.symbol)

        if not position:
            await update.message.reply_text("⏸️ No position to close.")
            return

        # Close position
        trade = self.trading_bot.api.close_position(self.trading_bot.symbol, reason='manual')

        if trade:
            pnl_emoji = "🟢" if trade.get('pnl', 0) > 0 else "🔴"
            message = (
                f"✅ *Position Closed*\n\n"
                f"PnL: {pnl_emoji} ${trade.get('pnl', 0):.2f} ({trade.get('pnl_pct', 0):.2f}%)\n"
                f"Reason: Manual close"
            )
            await update.message.reply_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Failed to close position!")

    async def emergency_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /emergency command - stop bot and close all positions."""
        if not await self._check_authorization(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("❌ Trading bot not initialized!")
            return

        # Stop bot
        self.trading_bot.stop()

        # Close position if exists
        position = self.trading_bot.api.get_position(self.trading_bot.symbol)

        if position:
            self.trading_bot.api.close_position(self.trading_bot.symbol, reason='emergency')

        await update.message.reply_text(
            "🚨 *EMERGENCY STOP*\n\n"
            "✅ Bot stopped\n"
            "✅ All positions closed\n\n"
            "System is now safe.",
            parse_mode='Markdown'
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        query = update.callback_query
        await query.answer()

        # Map callbacks to command functions
        callbacks = {
            'start_bot': self.startbot_command,
            'stop_bot': self.stopbot_command,
            'status': self.status_command,
            'balance': self.balance_command,
            'position': self.position_command,
            'stats': self.stats_command
        }

        callback_func = callbacks.get(query.data)

        if callback_func:
            # Create a mock update for the command
            await callback_func(update, context)

    def setup_handlers(self):
        """Setup command and callback handlers."""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("startbot", self.startbot_command))
        self.app.add_handler(CommandHandler("stopbot", self.stopbot_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("balance", self.balance_command))
        self.app.add_handler(CommandHandler("position", self.position_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("closeposition", self.closeposition_command))
        self.app.add_handler(CommandHandler("emergency", self.emergency_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))

        logger.info("✅ Telegram handlers registered")

    async def send_message(self, message: str, parse_mode: str = 'Markdown'):
        """Send a message to the authorized chat."""
        try:
            await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram message: {e}")

    async def notify_trade_opened(self, signal: dict):
        """Send notification when a trade is opened."""
        side_emoji = "📈" if signal['direction'] == 'long' else "📉"

        message = (
            f"🔔 *Trade Opened*\n\n"
            f"{side_emoji} {signal['direction'].upper()}\n"
            f"Entry: ${signal['entry_price']:,.2f}\n"
            f"Size: ${signal['position_size_usd']:,.2f}\n"
            f"Confidence: {signal['confidence']:.1%}\n"
            f"Regime: {signal['regime']}\n\n"
            f"SL: ${signal['stop_loss']:,.2f}\n"
            f"TP3: ${signal['take_profit_3']:,.2f}"
        )

        await self.send_message(message)

    async def notify_trade_closed(self, trade: dict):
        """Send notification when a trade is closed."""
        pnl_emoji = "🟢" if trade.get('pnl', 0) > 0 else "🔴"
        side_emoji = "📈" if trade['side'] == 'long' else "📉"

        message = (
            f"🔔 *Trade Closed*\n\n"
            f"{side_emoji} {trade['side'].upper()}\n"
            f"Entry: ${trade['entry_price']:,.2f}\n"
            f"Exit: ${trade['exit_price']:,.2f}\n\n"
            f"PnL: {pnl_emoji} ${trade['pnl']:.2f} ({trade['pnl_pct']:.2f}%)\n"
            f"Reason: {trade['reason']}\n"
            f"Duration: {trade['duration']}"
        )

        await self.send_message(message)

    def run(self):
        """Run the Telegram bot (blocking)."""
        self.app = Application.builder().token(self.token).build()
        self.setup_handlers()

        logger.info("🚀 Telegram bot starting...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

    def start_async(self):
        """Start the Telegram bot asynchronously."""
        self.app = Application.builder().token(self.token).build()
        self.setup_handlers()

        logger.info("🚀 Telegram bot starting (async)...")
        return self.app
