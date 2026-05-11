"""Top up data/prices.parquet for the full Tilt universe + overlay signal."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tilt.fetch import fetch_all  # noqa: E402
from tilt.universe import all_tickers  # noqa: E402


def main() -> None:
    tickers = all_tickers()
    print(f"Fetching {len(tickers)} tickers...")
    df = fetch_all(tickers)
    print(f"Cache now: {len(df):,} rows, {df['ticker'].nunique()} tickers, "
          f"range {df['date'].min()} -> {df['date'].max()}")


if __name__ == "__main__":
    main()
