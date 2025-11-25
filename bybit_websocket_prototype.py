#!/usr/bin/env python3
"""
Bybit WebSocket Prototype
Real-time candle monitoring using WebSocket

Usage:
    python3 bybit_websocket_prototype.py
"""

import websocket
import json
import time
import threading
from datetime import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class BybitWebSocketKline:
    """
    Bybit WebSocket client for real-time kline (candle) data.

    Features:
    - Auto-reconnect on disconnect
    - Heartbeat/ping to keep connection alive
    - Detects when candle closes
    - Thread-safe
    """

    def __init__(self, symbol: str = "BTCUSDT", interval: str = "15"):
        """
        Initialize WebSocket client.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            interval: Candle interval in minutes (1, 3, 5, 15, 30, 60, etc.)
        """
        self.symbol = symbol
        self.interval = interval
        self.ws = None
        self.connected = False
        self.last_candle_time = None

        # Callback when candle closes
        self.on_candle_close_callback = None

    def on_message(self, ws, message):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)

            # Pong response
            if data.get('op') == 'pong':
                logger.debug("Received pong")
                return

            # Subscription confirmation
            if data.get('op') == 'subscribe':
                logger.info(f"✅ Subscribed to: {data.get('args', [])}")
                return

            # Kline data
            if 'topic' in data and 'kline' in data['topic']:
                self.handle_kline(data['data'])

        except Exception as e:
            logger.error(f"Error parsing message: {e}")

    def handle_kline(self, kline_data):
        """Process kline (candle) data"""
        try:
            # Bybit sends array with one candle
            if not kline_data or len(kline_data) == 0:
                return

            candle = kline_data[0]

            start_time = int(candle['start'])
            end_time = int(candle['end'])
            open_price = float(candle['open'])
            high_price = float(candle['high'])
            low_price = float(candle['low'])
            close_price = float(candle['close'])
            volume = float(candle['volume'])
            confirm = candle['confirm']  # True if candle closed

            # Convert timestamp to datetime
            start_dt = datetime.fromtimestamp(start_time / 1000)
            end_dt = datetime.fromtimestamp(end_time / 1000)

            # Log candle update
            logger.debug(f"📊 {start_dt} | O:{open_price} H:{high_price} L:{low_price} C:{close_price} | Confirm:{confirm}")

            # Check if candle just closed
            if confirm:
                # Only trigger if this is a NEW closed candle
                if self.last_candle_time != start_dt:
                    self.last_candle_time = start_dt

                    logger.info("")
                    logger.info("=" * 80)
                    logger.info(f"🆕 CANDLE CLOSED")
                    logger.info("=" * 80)
                    logger.info(f"  ⏰ Time:   {start_dt} → {end_dt}")
                    logger.info(f"  💰 Open:   ${open_price:,.2f}")
                    logger.info(f"  📈 High:   ${high_price:,.2f}")
                    logger.info(f"  📉 Low:    ${low_price:,.2f}")
                    logger.info(f"  💵 Close:  ${close_price:,.2f}")
                    logger.info(f"  📊 Volume: {volume:,.2f}")
                    logger.info("=" * 80)
                    logger.info("")

                    # Call callback if defined
                    if self.on_candle_close_callback:
                        self.on_candle_close_callback(start_dt, close_price)

        except Exception as e:
            logger.error(f"Error handling kline: {e}")

    def on_error(self, ws, error):
        """Handle WebSocket error"""
        logger.error(f"❌ WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        self.connected = False
        logger.warning(f"⚠️ WebSocket closed: {close_status_code} - {close_msg}")
        logger.info("🔄 Reconnecting in 5 seconds...")
        time.sleep(5)
        self.connect()

    def on_open(self, ws):
        """Handle WebSocket open"""
        self.connected = True
        logger.info("✅ WebSocket connected")

        # Subscribe to kline (candle) updates
        subscribe_msg = {
            "op": "subscribe",
            "args": [f"kline.{self.interval}.{self.symbol}"]
        }

        ws.send(json.dumps(subscribe_msg))
        logger.info(f"📡 Subscribing to: kline.{self.interval}.{self.symbol}")

        # Start heartbeat thread
        heartbeat_thread = threading.Thread(target=self.send_heartbeat, daemon=True)
        heartbeat_thread.start()

    def send_heartbeat(self):
        """Send ping every 20 seconds to keep connection alive"""
        while self.connected:
            try:
                if self.ws:
                    ping_msg = {"op": "ping"}
                    self.ws.send(json.dumps(ping_msg))
                    logger.debug("Sent ping")
                time.sleep(20)
            except Exception as e:
                logger.error(f"Error sending ping: {e}")
                break

    def connect(self):
        """Connect to Bybit WebSocket"""
        url = "wss://stream.bybit.com/v5/public/linear"

        logger.info(f"🔌 Connecting to Bybit WebSocket...")
        logger.info(f"   URL: {url}")
        logger.info(f"   Symbol: {self.symbol}")
        logger.info(f"   Interval: {self.interval}m")

        self.ws = websocket.WebSocketApp(
            url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )

        # Run in separate thread
        ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        ws_thread.start()

    def disconnect(self):
        """Disconnect from WebSocket"""
        if self.ws:
            self.connected = False
            self.ws.close()
            logger.info("WebSocket disconnected")

    def set_on_candle_close(self, callback):
        """
        Set callback function to be called when candle closes.

        Args:
            callback: Function with signature: callback(candle_time: datetime, close_price: float)
        """
        self.on_candle_close_callback = callback


# Example usage
def on_candle_closed(candle_time, close_price):
    """Example callback when candle closes"""
    logger.info(f"🎯 CALLBACK TRIGGERED!")
    logger.info(f"   Candle Time: {candle_time}")
    logger.info(f"   Close Price: ${close_price:,.2f}")
    logger.info(f"   → Now you can make prediction with this candle!")
    logger.info("")


def main():
    """Main function - example usage"""
    logger.info("")
    logger.info("=" * 80)
    logger.info("🤖 BYBIT WEBSOCKET PROTOTYPE")
    logger.info("=" * 80)
    logger.info("")

    # Create WebSocket client
    ws_client = BybitWebSocketKline(symbol="BTCUSDT", interval="15")

    # Set callback for when candle closes
    ws_client.set_on_candle_close(on_candle_closed)

    # Connect
    ws_client.connect()

    logger.info("✅ Bot running! Waiting for candles...")
    logger.info("   Press Ctrl+C to stop")
    logger.info("")

    try:
        # Keep running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("\n👋 Stopping bot...")
        ws_client.disconnect()
        logger.info("✅ Bot stopped")


if __name__ == "__main__":
    main()
