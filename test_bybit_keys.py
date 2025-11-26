#!/usr/bin/env python3
"""Test Bybit API Keys"""
import os
import sys
import hashlib
import hmac
import time
import requests
from urllib.parse import urlencode

def test_bybit_api():
    """Test if Bybit API keys work"""

    # Get keys from environment
    api_key = os.getenv('BYBIT_API_KEY', '')
    api_secret = os.getenv('BYBIT_API_SECRET', '')
    testnet = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

    print("=" * 80)
    print("🔍 BYBIT API KEY TEST")
    print("=" * 80)

    # Check if keys are set
    if not api_key or not api_secret:
        print("❌ API keys not set in environment variables!")
        print(f"   BYBIT_API_KEY: {'SET' if api_key else 'MISSING'}")
        print(f"   BYBIT_API_SECRET: {'SET' if api_secret else 'MISSING'}")
        return False

    print(f"✅ API Key: {api_key[:8]}...{api_key[-4:]} (length: {len(api_key)})")
    print(f"✅ API Secret: {api_secret[:4]}...{api_secret[-4:]} (length: {len(api_secret)})")
    print(f"✅ Network: {'TESTNET' if testnet else 'MAINNET'}")
    print()

    # Base URL
    base_url = "https://api-testnet.bybit.com" if testnet else "https://api.bybit.com"

    # Test 1: Public endpoint (no auth)
    print("📡 Test 1: Public endpoint (no authentication)")
    print("-" * 80)
    try:
        response = requests.get(f"{base_url}/v5/market/time", timeout=10)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        if response.status_code == 200:
            print("   ✅ Public endpoint works!")
        else:
            print("   ⚠️  Public endpoint issue - might be network/firewall")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    print()

    # Test 2: Private endpoint (with auth)
    print("🔐 Test 2: Private endpoint (with authentication)")
    print("-" * 80)
    try:
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"

        # Build params
        params = {
            "api_key": api_key,
            "timestamp": timestamp,
            "recv_window": recv_window
        }

        # Create signature
        param_str = urlencode(sorted(params.items()))
        signature = hmac.new(
            api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Add signature
        params['sign'] = signature

        # Make request
        url = f"{base_url}/v5/user/query-api"
        response = requests.get(url, params=params, timeout=10)

        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:500]}")

        if response.status_code == 200:
            print("   ✅ Authentication successful!")
            print("   ✅ API keys are VALID!")
            return True
        elif response.status_code == 403:
            print("   ❌ 403 Forbidden - Possible causes:")
            print("      1. Keys don't have required permissions")
            print("      2. IP restriction is enabled")
            print("      3. Keys were created for testnet but using mainnet (or vice versa)")
            print("      4. Account has restrictions")
        elif response.status_code == 401:
            print("   ❌ 401 Unauthorized - Keys are invalid or signature is wrong")
        else:
            print(f"   ⚠️  Unexpected status code: {response.status_code}")

        return False

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

if __name__ == "__main__":
    print()
    success = test_bybit_api()
    print()
    print("=" * 80)
    if success:
        print("🎉 SUCCESS - API keys are working correctly!")
    else:
        print("❌ FAILED - Please check your API keys configuration")
    print("=" * 80)
    print()
    sys.exit(0 if success else 1)
