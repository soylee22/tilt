"""Monthly job — append today's pick to history.jsonl, re-render dashboard.

Idempotent: if today's month already has an entry, replace it (so re-runs
on the same month don't duplicate).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tilt.engine import TiltConfig, backtest  # noqa: E402
from tilt.fetch import fetch_all, load_prices  # noqa: E402
from tilt.universe import all_tickers  # noqa: E402
from tilt.dashboard import render  # noqa: E402

HISTORY = ROOT / "data" / "history.jsonl"


def main() -> None:
    print("Top up prices...")
    fetch_all(all_tickers())

    prices = load_prices()
    cfg = TiltConfig(start=dt.date(2019, 4, 1))
    print("Recomputing full backtest (idempotent)...")
    result = backtest(prices, cfg)
    history = result["history"]

    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("w") as f:
        for entry in history:
            f.write(json.dumps(entry, default=str) + "\n")

    m = result["metrics"]
    last = history[-1] if history else None
    if last:
        print(f"Latest pick ({last['asof']}): "
              f"factor={last['factor_pick']} ({(last['factor_return_12m'] or 0)*100:+.1f}%) · "
              f"sector={last['sector_pick']} ({(last['sector_return_12m'] or 0)*100:+.1f}%)")
    print(f"CAGR={m.get('cagr', 0)*100:.1f}%  Sharpe={m.get('sharpe', 0):.2f}  "
          f"DD={m.get('max_drawdown', 0)*100:.1f}%  NAV=£{m.get('end_value', 0)/1000:.1f}k")

    print("Rendering dashboard...")
    out = render()
    print(f"  -> {out}")


if __name__ == "__main__":
    main()
