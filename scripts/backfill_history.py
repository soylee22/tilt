"""Backfill data/history.jsonl from existing price cache.

For each historical month-end since the configured start date, run the
rotation engine and append a record. Equity values are the actual portfolio
NAV simulated from £100k starting capital.

Idempotent: deletes existing history.jsonl and rebuilds from scratch.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tilt.engine import TiltConfig, backtest  # noqa: E402
from tilt.fetch import load_prices  # noqa: E402

HISTORY = ROOT / "data" / "history.jsonl"


def main() -> None:
    prices = load_prices()
    cfg = TiltConfig(
        start=dt.date(2019, 4, 1),
        drawdown_sma_months=10,       # per-leg drawdown filter ON
        drawdown_confirm_months=2,
        overlay_sma_months=None,      # market-wide overlay OFF
        starting_capital=100_000.0,
    )
    print(f"Backtesting from {cfg.start} to today...")
    result = backtest(prices, cfg)
    history = result["history"]

    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("w") as f:
        for entry in history:
            f.write(json.dumps(entry, default=str) + "\n")

    m = result["metrics"]
    print(f"Wrote {len(history)} months to {HISTORY.relative_to(ROOT)}")
    print(f"  CAGR={m.get('cagr', 0)*100:.1f}%  Sharpe={m.get('sharpe', 0):.2f}  "
          f"DD={m.get('max_drawdown', 0)*100:.1f}%  End=£{m.get('end_value', 0)/1000:.1f}k")


if __name__ == "__main__":
    main()
