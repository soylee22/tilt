"""Build an organised, deduped catalogue of T212-tradeable ETFs mapped to yfinance.

Reads the T212 instruments metadata (live API, Basic auth from env), keeps ETFs,
dedups by ISIN (one row per fund, preferring the London listing), derives the
yfinance ticker, tags an asset-class category and a leveraged/inverse flag, and
writes data/etf_catalogue.csv.

This is METADATA ONLY. It deliberately does NOT score or rank anything by
performance. Candidate selection for a backtest must be made ex-ante on economic
grounds from this catalogue, never by mining the backtest. History availability
is probed per-experiment (see probe_history), not here, to avoid 6k yfinance hits.

Env: T212_KEY_ID, T212_SECRET  (Basic auth = base64 "keyId:secret").
"""
from __future__ import annotations
import base64
import csv
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "etf_catalogue.csv"
CACHE = Path("/tmp/t212_instruments.json")
BASE = "https://live.trading212.com/api/v0"

def fetch_instruments() -> list[dict]:
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    kid, sec = os.environ["T212_KEY_ID"], os.environ["T212_SECRET"]
    tok = base64.b64encode(f"{kid}:{sec}".encode()).decode()
    req = urllib.request.Request(f"{BASE}/equity/metadata/instruments",
                                 headers={"Authorization": f"Basic {tok}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    CACHE.write_text(json.dumps(data))
    return data

# --- categorisation (keyword, name-based; fuzzy but navigable) ---
LEVERAGED = ("leverage", "3x", "2x", "-1x", "-2x", "-3x", "-5x", " short ", "ultra",
             "daily lev", "inverse")
def is_leveraged(n: str) -> bool:
    s = f" {n.lower()} "
    return any(k in s for k in LEVERAGED)

CATS = [
    ("crypto",    ("bitcoin", "ethereum", "crypto", "coinshares", " coin", "blockchain")),
    ("bond",      ("bond", "treasury", "gilt", "govt", "government", "corporate",
                   "aggregate", "tips", "inflation-link", "duration", "high yield",
                   "fixed income", "maturity", "money market", "ultrashort")),
    ("commodity", ("gold", "silver", "commodity", "commodities", "platinum",
                   "crude", "oil", "natural gas", "metals", "carbon", "agriculture")),
    ("factor",    ("momentum", "value factor", "quality factor", "min vol",
                   "minimum volatility", "multifactor", "multi-factor", "size factor",
                   "small cap", "small-cap", "enhanced value", "dividend", "high yield equity",
                   "quality screened", "buyback")),
    ("sector",    ("energy sector", "financials", "health care", "healthcare",
                   "information technology", "industrials", "materials sector",
                   "utilities", "real estate", "consumer discretionary",
                   "consumer staples", "communication", "semiconductor", "banks",
                   "biotech", "insurance", " reit")),
    ("thematic",  ("clean energy", "robotics", "artificial intelligence", " ai ",
                   "cyber", "battery", "water", "ageing", "genomics", "automation",
                   "cloud", "ecommerce", "digital", "infrastructure", "uranium",
                   "defence", "defense", "space", "hydrogen", "lithium", "metaverse")),
    ("region",    ("s&p 500", "msci world", "msci usa", "msci emerging", "emerging markets",
                   "msci europe", "msci japan", "msci china", "msci india", "msci uk",
                   "ftse", "nasdaq", "all country", "all-world", "acwi", "russell",
                   "stoxx", "dax", "msci ", "pacific", "asia")),
]
def categorise(n: str) -> str:
    s = n.lower()
    for cat, keys in CATS:
        if any(k in s for k in keys):
            return cat
    return "other"

def yf_ticker(listing: dict) -> str | None:
    """Derive a yfinance ticker from a T212 listing. London -> short.L,
    Xetra -> short.DE, US -> short. None if unmappable."""
    t, short = listing["ticker"], listing["shortName"]
    if t.endswith("l_EQ"):
        return f"{short}.L"
    if t.endswith("d_EQ"):
        return f"{short}.DE"
    if t.endswith("_EQ") and "_US_EQ" not in t:  # plain US-listed
        return short
    return None

# Preference: London USD > London GBX > Xetra EUR > US > anything (Tilt ranks in
# USD, currency-neutral, so the USD London line matches the existing universe).
def listing_rank(l: dict) -> tuple:
    t, ccy = l["ticker"], l["currencyCode"]
    london = t.endswith("l_EQ"); xetra = t.endswith("d_EQ")
    return (
        0 if (london and ccy == "USD") else 1 if london else
        2 if xetra else 3,
        0 if ccy == "USD" else 1,
    )

def main() -> None:
    data = fetch_instruments()
    etfs = [x for x in data if x["type"] == "ETF"]
    by_isin: dict[str, list[dict]] = {}
    for x in etfs:
        by_isin.setdefault(x["isin"], []).append(x)

    rows = []
    for isin, listings in by_isin.items():
        best = sorted(listings, key=listing_rank)[0]
        yf = yf_ticker(best)
        name = best["name"]
        rows.append({
            "isin": isin,
            "yf_ticker": yf or "",
            "t212_ticker": best["ticker"],
            "short": best["shortName"],
            "currency": best["currencyCode"],
            "category": categorise(name),
            "leveraged": int(is_leveraged(name)),
            "n_listings": len(listings),
            "name": name,
        })
    rows.sort(key=lambda r: (r["category"], r["name"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # report
    from collections import Counter
    print(f"ETF listings: {len(etfs)}  ->  unique ISINs (funds): {len(rows)}")
    mappable = sum(1 for r in rows if r["yf_ticker"])
    lev = sum(r["leveraged"] for r in rows)
    print(f"yfinance-mappable: {mappable}  ({mappable*100//len(rows)}%)   leveraged/inverse: {lev}")
    print("\nBy category (core = non-leveraged):")
    core = Counter(r["category"] for r in rows if not r["leveraged"])
    for cat, n in core.most_common():
        print(f"  {cat:10s} {n:5d}")
    print(f"\nWrote {OUT.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
