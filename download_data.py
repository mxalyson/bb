#!/usr/bin/env python3
"""
Simple script to download Bybit data and save to CSV
No dependencies except standard library + requests
"""

import json
import csv
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
import time
import sys

def download_bybit_data(symbol='BTCUSDT', interval='15', days=180):
    """Download data from Bybit API and save to CSV."""

    print(f"Downloading {symbol} data ({days} days, {interval}min interval)...")

    # Calculate time range
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

    print(f"Time range: {datetime.fromtimestamp(start_time/1000)} to {datetime.fromtimestamp(end_time/1000)}")

    url = "https://api.bybit.com/v5/market/kline"

    all_data = []
    current_start = start_time
    requests_made = 0
    max_requests = 50

    while current_start < end_time and requests_made < max_requests:
        params = f"category=linear&symbol={symbol}&interval={interval}&start={current_start}&limit=1000"
        full_url = f"{url}?{params}"

        try:
            print(f"\rRequest {requests_made + 1}...", end='', flush=True)

            req = Request(full_url)
            req.add_header('User-Agent', 'Mozilla/5.0')

            with urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())

            if data.get('retCode') != 0:
                print(f"\nAPI Error: {data.get('retMsg')}")
                break

            klines = data['result']['list']

            if not klines:
                print("\nNo more data")
                break

            all_data.extend(klines)

            last_timestamp = int(klines[-1][0])
            current_start = last_timestamp + 1

            if len(klines) < 1000:
                break

            requests_made += 1
            time.sleep(0.1)  # Rate limit

        except (HTTPError, URLError) as e:
            print(f"\nNetwork error: {e}")
            break
        except Exception as e:
            print(f"\nError: {e}")
            break

    print(f"\n\nTotal candles: {len(all_data)}")

    if not all_data:
        print("ERROR: No data downloaded!")
        return None

    # Save to CSV
    filename = f"{symbol}_{interval}m_{days}d.csv"

    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])

        for candle in all_data:
            # Convert timestamp to readable format
            ts = datetime.fromtimestamp(int(candle[0])/1000).strftime('%Y-%m-%d %H:%M:%S')
            writer.writerow([ts] + candle[1:])

    print(f"✅ Data saved to: {filename}")
    print(f"   Candles: {len(all_data):,}")

    return filename

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else 'BTCUSDT'
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 180
    interval = sys.argv[3] if len(sys.argv) > 3 else '15'

    download_bybit_data(symbol, interval, days)
