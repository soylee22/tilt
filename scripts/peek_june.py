"""Read-only month-end probe: top up prices, print the latest 12m ranking.

Run this at month-end (before the cron fires on the 1st) to see next month's
picks. Does NOT touch history.jsonl or re-render the dashboard, it only prints
the factor and sector leaders so you can build the holdings card.

    python scripts/peek_june.py   # despite the name, always prints the latest
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
from tilt.engine import long_to_wide, last_trading_days_of_month, trailing_return  # noqa: E402
from tilt.fetch import fetch_all, load_prices  # noqa: E402
from tilt.universe import all_tickers, factor_tickers, sector_tickers  # noqa: E402

print("Topping up prices (read-only on history)...")
fetch_all(all_tickers())
prices = load_prices()
wide = long_to_wide(prices)

meks = last_trading_days_of_month(wide.index)
asof = meks[-1]
latest_close = wide.index[-1]
print(f"\nLast available close: {latest_close.date()}")
print(f"Latest month-end used: {asof.date()}\n")

ret = trailing_return(wide, asof, 12)

fac = [(t, ret.get(t)) for t in factor_tickers()]
sec = [(t, ret.get(t)) for t in sector_tickers()]
fac = sorted([(t, r) for t, r in fac if pd.notna(r)], key=lambda x: -x[1])
sec = sorted([(t, r) for t, r in sec if pd.notna(r)], key=lambda x: -x[1])

print("FACTOR basket 12m ranking:")
for t, r in fac:
    print(f"  {t:8s} {r*100:+7.1f}%")
print(f"  -> FACTOR PICK: {fac[0][0]} ({fac[0][1]*100:+.1f}%)\n")

print("SECTOR basket 12m ranking:")
for t, r in sec:
    print(f"  {t:8s} {r*100:+7.1f}%")
print(f"  -> SECTOR PICK: {sec[0][0]} ({sec[0][1]*100:+.1f}%)")
