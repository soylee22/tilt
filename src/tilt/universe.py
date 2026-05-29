"""The Tilt universe — two fixed baskets of LSE-listed UCITS ETFs.

All available on Trading 212 (Lee's broker). GBP-tradable.
"""
from __future__ import annotations

import pandas as pd


# Factor basket (8) — factor-exposure ETFs. The strategy picks one per month
# by 12-month trailing total return. Substitutions vs author's original spec:
#  WSML.L replaces "MSCI Europe Small Cap" — UCITS for that index isn't on
#  yfinance, so we use the World Small Cap UCITS as proxy.
FACTOR_BASKET = [
    ("IUMO.L", "iShares Edge MSCI USA Momentum"),
    ("IUQA.L", "iShares Edge MSCI USA Quality"),
    ("IUVL.L", "iShares Edge MSCI USA Value"),
    ("CUS1.L", "iShares S&P 600 Small Cap (USA)"),
    ("IEMO.L", "iShares Edge MSCI Europe Momentum"),
    ("IEQU.L", "iShares Edge MSCI Europe Quality"),
    ("IEVL.L", "iShares Edge MSCI Europe Value"),
    ("WSML.L", "iShares MSCI World Small Cap"),
]

# Sector basket (12) — full 11 GICS sectors of the S&P 500 + pure semis thematic.
# Expanded from author's original 7 because in our 2019-2026 backtest the
# expanded basket delivered Sharpe 1.02 vs 0.74 (the rejected sectors carried
# their own rotations worth capturing).
SECTOR_BASKET = [
    ("IUIT.L", "iShares S&P 500 IT"),
    ("IHCU.L", "iShares S&P 500 Health Care"),
    ("IUES.L", "iShares S&P 500 Energy"),
    ("IUCD.L", "iShares S&P 500 Cons Discretionary"),
    ("IUCS.L", "iShares S&P 500 Cons Staples"),
    ("IUIS.L", "iShares S&P 500 Industrials"),
    ("IUMS.L", "iShares S&P 500 Materials"),
    ("IUFS.L", "iShares S&P 500 Financials"),
    ("IUCM.L", "iShares S&P 500 Communication Services"),
    ("IUUS.L", "iShares S&P 500 Utilities"),
    ("IUSP.L", "iShares S&P 500 Real Estate"),
    ("SMH.L",  "VanEck Semiconductor"),
]

# Overlay signal (Faber 10-month SMA on SPY). Used optionally — recent backtest
# showed overlay HURT in 2019-2026 (no sustained bears for it to protect
# against). Kept available; off by default.
OVERLAY_TICKER = "SPY"

# Benchmark: Vanguard FTSE All-World UCITS Acc (GBP line). Fetched and stored so
# the dashboard can score each month's 50/50 return against a passive all-world
# hold, but it is NEVER a pick candidate (excluded from both baskets). Note the
# benchmark is GBP-denominated whereas the sector/factor ETFs come off yfinance
# in USD, so a small monthly FX term sits in the comparison. Data starts 2019-07.
BENCHMARK_TICKER = "VWRP.L"


def factor_tickers() -> list[str]:
    return [tk for tk, _ in FACTOR_BASKET]


def sector_tickers() -> list[str]:
    return [tk for tk, _ in SECTOR_BASKET]


def all_tickers() -> list[str]:
    return factor_tickers() + sector_tickers() + [OVERLAY_TICKER, BENCHMARK_TICKER]


def name_for(ticker: str) -> str:
    for tk, name in FACTOR_BASKET + SECTOR_BASKET:
        if tk == ticker:
            return name
    if ticker == OVERLAY_TICKER:
        return "SPDR S&P 500 (overlay signal)"
    if ticker == BENCHMARK_TICKER:
        return "Vanguard FTSE All-World (benchmark)"
    return ticker


def universe_df() -> pd.DataFrame:
    rows = []
    for tk, name in FACTOR_BASKET:
        rows.append({"ticker": tk, "name": name, "basket": "Factor"})
    for tk, name in SECTOR_BASKET:
        rows.append({"ticker": tk, "name": name, "basket": "Sector"})
    return pd.DataFrame(rows)
