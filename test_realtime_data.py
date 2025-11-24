"""
Test if Bybit API is returning fresh real-time data
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.utils import load_config
from core.bybit_rest import BybitRESTClient
from core.data import DataManager
from datetime import datetime
import pandas as pd

def main():
    config = load_config()

    rest_client = BybitRESTClient(
        api_key=config['bybit_api_key'],
        api_secret=config['bybit_api_secret'],
        testnet=config['bybit_testnet']
    )

    dm = DataManager(rest_client)

    print("=" * 80)
    print("🔍 TESTING REAL-TIME DATA FROM BYBIT API")
    print("=" * 80)
    print()

    # Download data
    print("📥 Downloading last 30 days of BTCUSDT 15m data...")
    df = dm.get_data('BTCUSDT', '15m', 30, use_cache=False)  # NO CACHE!

    print(f"✅ Downloaded {len(df)} candles")
    print()

    # Show last 5 candles
    print("📊 LAST 5 CANDLES:")
    print("=" * 80)
    last_5 = df.tail(5)
    for idx, row in last_5.iterrows():
        print(f"{idx} | Close: ${row['close']:,.2f} | Volume: {row['volume']:,.2f}")

    print()
    print("=" * 80)

    # Check timestamps
    now_local = datetime.now()
    now_utc = pd.Timestamp.now(tz='UTC')

    last_candle = df.iloc[-1]
    second_last = df.iloc[-2]

    last_candle_time = pd.Timestamp(last_candle.name)
    if last_candle_time.tz is None:
        last_candle_time = last_candle_time.tz_localize('UTC')
    else:
        last_candle_time = last_candle_time.tz_convert('UTC')

    second_last_time = pd.Timestamp(second_last.name)
    if second_last_time.tz is None:
        second_last_time = second_last_time.tz_localize('UTC')
    else:
        second_last_time = second_last_time.tz_convert('UTC')

    print(f"⏰ System Time (Local): {now_local}")
    print(f"⏰ System Time (UTC):   {now_utc}")
    print()
    print(f"📍 Last candle (iloc[-1]):")
    print(f"   Time: {last_candle_time}")
    print(f"   Close: ${last_candle['close']:,.2f}")
    print(f"   Age: {(now_utc - last_candle_time).total_seconds():.0f}s")
    print()
    print(f"📍 Second last candle (iloc[-2]) - THIS IS WHAT BOT USES:")
    print(f"   Time: {second_last_time}")
    print(f"   Close: ${second_last['close']:,.2f}")
    print(f"   Age: {(now_utc - second_last_time).total_seconds():.0f}s")
    print()

    # Add 15min to get CLOSE time
    last_close_time = last_candle_time + pd.Timedelta(minutes=15)
    second_last_close_time = second_last_time + pd.Timedelta(minutes=15)

    print(f"🔍 Candle CLOSE times (candle start + 15min):")
    print(f"   Last candle closes at: {last_close_time}")
    print(f"   Second last closed at: {second_last_close_time}")
    print()

    seconds_since_last_close = (now_utc - last_close_time).total_seconds()
    seconds_since_second_last_close = (now_utc - second_last_close_time).total_seconds()

    print(f"⏱️  Time since last candle CLOSED: {seconds_since_last_close:.0f}s")
    print(f"⏱️  Time since second last CLOSED: {seconds_since_second_last_close:.0f}s")
    print()

    if seconds_since_last_close < -60:
        print("❌ Last candle hasn't closed yet (closes in future)")
    elif seconds_since_last_close > 90:
        print("⚠️ Last candle closed long ago (>90s) - might be stale data")
    else:
        print("✅ Last candle closed recently (<90s) - data is fresh!")

    print()
    print("=" * 80)

if __name__ == "__main__":
    main()
