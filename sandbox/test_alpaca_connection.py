"""
Verify Alpaca paper trading connection.

NOT part of the application — manual testing only.

Usage:
    python sandbox/test_alpaca_connection.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow importing core.config from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import get_settings


def main() -> None:
    s = get_settings()

    if not s.ALPACA_API_KEY or not s.ALPACA_API_SECRET:
        print("ERROR: ALPACA_API_KEY and ALPACA_API_SECRET must be set in .env")
        sys.exit(1)

    print(f"BROKER_PROVIDER = {s.BROKER_PROVIDER}")
    print(f"ALPACA_BASE_URL = {s.ALPACA_BASE_URL}")
    print()

    # --- Step 1: Check trading API connection ---
    print("=" * 60)
    print("STEP 1: Trading API — Account Status")
    print("=" * 60)

    from alpaca.trading.client import TradingClient

    trading_client = TradingClient(
        api_key=s.ALPACA_API_KEY,
        secret_key=s.ALPACA_API_SECRET,
        paper=True,
    )

    try:
        account = trading_client.get_account()
        print(f"  Account ID:     {account.id}")
        print(f"  Status:         {account.status}")
        print(f"  Cash:           ${float(account.cash):,.2f}")
        print(f"  Equity:         ${float(account.equity):,.2f}")
        print(f"  Buying Power:   ${float(account.buying_power):,.2f}")
        print(f"  Day Trade Count:{account.daytrade_count}")
        print()
        print("  >> Trading API connection OK")
    except Exception as e:
        print(f"  >> FAILED: {e}")
        sys.exit(1)

    # --- Step 2: Check data API connection ---
    print()
    print("=" * 60)
    print("STEP 2: Data API — Latest Bar for SPY")
    print("=" * 60)

    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestBarRequest

    data_client = StockHistoricalDataClient(
        api_key=s.ALPACA_API_KEY,
        secret_key=s.ALPACA_API_SECRET,
    )

    try:
        req = StockLatestBarRequest(symbol_or_symbols=["SPY"])
        bars = data_client.get_stock_latest_bar(req)
        bar = bars["SPY"]
        print(f"  Symbol:    SPY")
        print(f"  Timestamp: {bar.timestamp}")
        print(f"  Open:      ${float(bar.open):,.2f}")
        print(f"  High:      ${float(bar.high):,.2f}")
        print(f"  Low:       ${float(bar.low):,.2f}")
        print(f"  Close:     ${float(bar.close):,.2f}")
        print(f"  Volume:    {bar.volume:,}")
        print()
        print("  >> Data API connection OK")
    except Exception as e:
        print(f"  >> FAILED: {e}")
        sys.exit(1)

    # --- Step 3: Show current positions ---
    print()
    print("=" * 60)
    print("STEP 3: Current Paper Positions")
    print("=" * 60)

    positions = trading_client.get_all_positions()
    if not positions:
        print("  (no open positions)")
    else:
        for p in positions:
            print(f"  {p.symbol}: {p.qty} shares @ ${float(p.avg_entry_price):,.2f}"
                  f"  (P&L: ${float(p.unrealized_pl):,.2f})")
    print()

    # --- Step 4: Ask before placing a test order ---
    print("=" * 60)
    print("STEP 4: Place Test Order (1 share of SPY)")
    print("=" * 60)
    print()
    answer = input("  Place a test BUY order for 1 share of SPY? [y/N] ").strip().lower()

    if answer != "y":
        print("  Skipped. No order placed.")
        return

    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    try:
        order_req = MarketOrderRequest(
            symbol="SPY",
            qty=1,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        order = trading_client.submit_order(order_req)
        print()
        print(f"  Order ID:     {order.id}")
        print(f"  Symbol:       {order.symbol}")
        print(f"  Side:         {order.side}")
        print(f"  Qty:          {order.qty}")
        print(f"  Status:       {order.status}")
        print(f"  Fill Price:   {order.filled_avg_price or 'pending'}")
        print(f"  Submitted At: {order.submitted_at}")
        print()
        print("  >> Order submitted! Check your Alpaca paper dashboard.")
    except Exception as e:
        print(f"  >> Order FAILED: {e}")
        print()
        print("  This may mean the market is closed. Alpaca paper trading")
        print("  only fills market orders during NYSE hours (9:30-16:00 ET).")
        print("  The order may still appear as 'pending' on your dashboard.")


if __name__ == "__main__":
    main()
