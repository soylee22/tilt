"""Three-way rebalance comparison: let-it-ride vs monthly-50/50 vs annual-50/50.

Drives the real engine.backtest with config.rebalance set, so the 'none' row
reproduces the published backtest exactly. VWRP buy-and-hold added as reference.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tilt.engine import TiltConfig, backtest, long_to_wide, _compute_metrics  # noqa: E402
from tilt.fetch import load_prices  # noqa: E402
from tilt.universe import BENCHMARK_TICKER  # noqa: E402


def summarise(mode: str, prices: pd.DataFrame, prices_wide: pd.DataFrame) -> dict:
    res = backtest(prices, TiltConfig(start=dt.date(2019, 4, 1), rebalance=mode))
    h = res["history"]
    m = res["metrics"]
    last = h[-1]
    sect = last["sector_leg_value"] / last["portfolio_value"] * 100
    fac = last["factor_leg_value"] / last["portfolio_value"] * 100
    bench = prices_wide[BENCHMARK_TICKER]
    wins = tot = 0
    excess = []
    for i in range(1, len(h)):
        pv0, pv1 = h[i - 1]["portfolio_value"], h[i]["portfolio_value"]
        b0 = bench.loc[:pd.to_datetime(h[i - 1]["asof"])].dropna()
        b1 = bench.loc[:pd.to_datetime(h[i]["asof"])].dropna()
        if not b0.empty and not b1.empty and pv0 > 0:
            tr, vr = pv1 / pv0 - 1, b1.iloc[-1] / b0.iloc[-1] - 1
            tot += 1; wins += 1 if tr >= vr else 0; excess.append(tr - vr)
    return {"mode": mode, "cagr": m.get("cagr"), "sharpe": m.get("sharpe"),
            "maxdd": m.get("max_drawdown"), "end": m.get("end_value"),
            "conc": max(sect, fac), "beat": (wins / tot) if tot else None,
            "exc": float(np.mean(excess)) if excess else None}


def vwrp_ref(prices_wide: pd.DataFrame) -> dict:
    b = prices_wide[BENCHMARK_TICKER].dropna()
    eq = pd.DataFrame({"date": [d.date().isoformat() for d in b.index],
                       "portfolio_value": (b / b.iloc[0] * 100_000).values})
    m = _compute_metrics(eq)
    return {"mode": "vwrp", "cagr": m.get("cagr"), "sharpe": m.get("sharpe"),
            "maxdd": m.get("max_drawdown"), "end": m.get("end_value"),
            "conc": 100.0, "beat": None, "exc": None, "since": b.index[0].date().isoformat()}


def main() -> None:
    prices = load_prices()
    pw = long_to_wide(prices)
    rows = [summarise(m, prices, pw) for m in ("none", "monthly", "annual")]
    ref = vwrp_ref(pw)
    rows.append(ref)
    names = {"none": "Let-it-ride", "monthly": "Monthly 50/50",
             "annual": "Annual 50/50", "vwrp": "VWRP B&H"}

    def pc(x, s="%", sign=False):
        if x is None:
            return "—"
        return (f"{x*100:+.1f}" if sign else f"{x*100:.1f}") + s

    print(f"{'Variant':<15}{'CAGR':>7}{'Sharpe':>8}{'MaxDD':>9}{'End NAV':>11}"
          f"{'EndConc':>9}{'BeatVWRP':>10}{'AvgExc':>9}")
    print("-" * 78)
    for r in rows:
        print(f"{names[r['mode']]:<15}{pc(r['cagr']):>7}{r['sharpe']:>8.3f}"
              f"{(format(r['maxdd']*100,'.2f')+'%'):>9}{'£'+format(r['end']/1000,'.1f')+'k':>11}"
              f"{(format(r['conc'],'.1f')+'%'):>9}{(pc(r['beat']) if r['beat'] is not None else '—'):>10}"
              f"{(pc(r['exc'],'pp',sign=True) if r['exc'] is not None else '—'):>9}")
    print(f"\n'none' must reproduce the published £481k / 24.5%. "
          f"Annual rebalances each January. VWRP B&H from {ref['since']}.")


if __name__ == "__main__":
    main()
