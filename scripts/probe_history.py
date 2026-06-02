"""Probe yfinance history length for the London non-leveraged ETF pool.

The gating filter for any universe-expansion test: a fund needs enough history to
be backtestable. Records first/last available close + years + row count per
ticker, writes data/etf_history.csv incrementally (resumable). This is the step
that shrinks ~1,500 candidates down to the few hundred with real track records.
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
CAT = ROOT / "data" / "etf_catalogue.csv"
OUT = ROOT / "data" / "etf_history.csv"

rows = list(csv.DictReader(CAT.open()))
pool = [r for r in rows if r["yf_ticker"].endswith(".L") and not int(r["leveraged"]) and r["yf_ticker"]]
tickers = sorted({r["yf_ticker"] for r in pool})

done = set()
if OUT.exists():
    done = {r["yf_ticker"] for r in csv.DictReader(OUT.open())}
todo = [t for t in tickers if t not in done]
print(f"Pool: {len(tickers)} London non-lev tickers; {len(done)} done; {len(todo)} to probe", flush=True)

write_header = not OUT.exists()
f = OUT.open("a", newline="")
w = csv.DictWriter(f, fieldnames=["yf_ticker", "first", "last", "years", "n_rows"])
if write_header:
    w.writeheader()

CHUNK = 40
for i in range(0, len(todo), CHUNK):
    chunk = todo[i:i + CHUNK]
    try:
        data = yf.download(chunk, start="2010-01-01", auto_adjust=True,
                           progress=False, threads=True, group_by="ticker")
    except Exception as e:
        print(f"chunk {i} error {e}", flush=True)
        continue
    for t in chunk:
        try:
            if len(chunk) == 1:
                c = data["Close"]
            else:
                c = data[t]["Close"]
            c = c.dropna()
        except Exception:
            c = pd.Series(dtype=float)
        if len(c) == 0:
            w.writerow({"yf_ticker": t, "first": "", "last": "", "years": 0, "n_rows": 0})
            continue
        first, last = c.index[0], c.index[-1]
        yrs = round((last - first).days / 365.25, 2)
        w.writerow({"yf_ticker": t, "first": first.date(), "last": last.date(),
                    "years": yrs, "n_rows": len(c)})
    f.flush()
    print(f"  probed {min(i+CHUNK, len(todo))}/{len(todo)}", flush=True)

f.close()
print("DONE", flush=True)
