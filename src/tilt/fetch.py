"""Incremental yfinance fetcher into data/prices.parquet.

Top up only — re-runs pull only the days since last cached close.
"""
from __future__ import annotations

import datetime as dt
import warnings
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent.parent
PRICES_PATH = ROOT / "data" / "prices.parquet"
INITIAL_START = dt.date(2014, 1, 1)

warnings.filterwarnings("ignore", category=FutureWarning, module="yfinance")


def _read_cache() -> pd.DataFrame:
    if not PRICES_PATH.exists():
        return pd.DataFrame(columns=["ticker", "date", "close", "volume"])
    df = pd.read_parquet(PRICES_PATH)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _write_cache(df: pd.DataFrame) -> None:
    PRICES_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = df.drop_duplicates(["ticker", "date"], keep="last").sort_values(["ticker", "date"])
    df.to_parquet(PRICES_PATH, index=False)


def _download_one(tk: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    raw = yf.download(tk, start=start.isoformat(), end=end.isoformat(),
                      auto_adjust=True, progress=False, threads=False)
    if raw.empty:
        return pd.DataFrame(columns=["ticker", "date", "close", "volume"])
    c = raw["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    v = raw["Volume"] if "Volume" in raw.columns else None
    if v is not None and isinstance(v, pd.DataFrame):
        v = v.iloc[:, 0]
    rows = []
    for d, px in c.items():
        if pd.isna(px):
            continue
        vol = float(v.loc[d]) if v is not None and d in v.index else 0.0
        rows.append({"ticker": tk, "date": d.date(), "close": float(px), "volume": vol})
    return pd.DataFrame(rows)


def fetch_all(tickers: list[str]) -> pd.DataFrame:
    cached = _read_cache()
    last_by_tk = cached.groupby("ticker")["date"].max().to_dict() if not cached.empty else {}
    today = dt.date.today()
    new_frames = []
    for tk in tickers:
        last = last_by_tk.get(tk)
        start = last + dt.timedelta(days=1) if last else INITIAL_START
        if start >= today:
            continue
        try:
            df = _download_one(tk, start, today)
            if not df.empty:
                new_frames.append(df)
        except Exception as exc:
            print(f"  FAIL {tk}: {exc!r}")
    merged = pd.concat([cached, *new_frames], ignore_index=True) if new_frames else cached
    _write_cache(merged)
    return pd.read_parquet(PRICES_PATH)


def load_prices() -> pd.DataFrame:
    """Read cached prices long-format."""
    df = pd.read_parquet(PRICES_PATH)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df
