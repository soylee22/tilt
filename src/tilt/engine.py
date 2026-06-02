"""Rotation engine — picks today's two leaders + runs the backtest.

Algorithm per Antonacci / MarketFighter:
  1. RELATIVE momentum: each month-end, for each basket compute every member's
     12-month total return and pick the single highest (the leader).
  2. ABSOLUTE momentum (the per-leg drawdown filter, ON by default): a leg is
     only held if its leader's OWN trend is intact, i.e. its price is not below
     its own 10-month SMA for `drawdown_confirm_months` consecutive month-ends.
     If the leader's trend has broken, that leg holds CASH instead. The two legs
     decide independently, so the book holds 0, 1, or 2 ETFs.
  3. Hold the resulting picks 50/50 (let-it-ride) for the next month.
  4. (Optional, off by default) market overlay: a single SPY 10-month SMA gate
     that takes the WHOLE book to cash. Coarser than the per-leg filter; left
     off because the per-leg filter is the better-behaved seatbelt.

Why two momentum tests? Relative momentum says "which is strongest"; absolute
momentum says "is the strongest actually worth holding, or is everything
falling?". Relative alone always stays invested in the least-bad option, which
is what rides a broad bear market down. The absolute leg is the brake.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .universe import (
    FACTOR_BASKET, SECTOR_BASKET, OVERLAY_TICKER, BENCHMARK_TICKER,
    factor_tickers, sector_tickers,
)


@dataclass
class TiltConfig:
    lookback_months: int = 12
    skip_recent_months: int = 1  # Jegadeesh-Titman 12-minus-1 momentum: skip the most recent month (LIVE default since 2026-06-02, evidence-based). 0 = plain trailing (the old published spec).
    # Per-leg drawdown filter (absolute momentum). ON by default. Each leg's
    # chosen ETF is moved to cash if it closes below its own SMA this many months.
    drawdown_sma_months: int | None = 10      # None disables the per-leg filter
    drawdown_confirm_months: int = 2          # consecutive months below SMA before exiting (anti-whipsaw)
    # Market-wide overlay (a single SPY SMA gate for the whole book). OFF; the
    # per-leg filter above is preferred.
    overlay_sma_months: int | None = None
    # Defensive sleeve (GEM-style out-asset). If a leg's equity pick is filtered
    # to cash, rotate into the best of these by skip-month momentum, gated by its
    # own trend (won't hold a falling bond), instead of sitting in cash. ()=off
    # (live default; an experiment, see outputs/2026-06-02-marketfighter-replication).
    defensive_tickers: tuple[str, ...] = ()
    transaction_cost_bps: float = 5.0
    starting_capital: float = 100_000.0
    start: dt.date = dt.date(2019, 4, 1)  # gated by WSML.L inception + 12mo lookback
    end: dt.date | None = None
    rebalance: str = "none"  # "none" (let legs drift), "monthly", or "annual" (each Jan)


@dataclass
class TiltResult:
    asof: dt.date
    factor_pick: str | None
    sector_pick: str | None
    factor_return_12m: float | None
    sector_return_12m: float | None
    overlay_in_market: bool
    factor_rankings: list[tuple[str, float]]
    sector_rankings: list[tuple[str, float]]


def long_to_wide(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()


def last_trading_days_of_month(dates: pd.DatetimeIndex) -> list[pd.Timestamp]:
    s = pd.Series(dates, index=dates)
    return sorted(s.groupby([dates.year, dates.month]).last().tolist())


def trailing_return(prices_wide: pd.DataFrame, asof: pd.Timestamp, months: int,
                    skip_recent_months: int = 0) -> pd.Series:
    valid = prices_wide.index[prices_wide.index <= asof]
    if len(valid) == 0:
        return pd.Series(dtype=float)
    today = valid[-1]
    # End of the measurement window. skip_recent_months>0 gives Jegadeesh-Titman
    # "12-minus-N" momentum: the numerator is the close N months ago, so the most
    # recent N months (which carry a short-term reversal effect) are excluded.
    # skip=0 reproduces plain trailing momentum and the published behaviour exactly.
    end_target = today - pd.DateOffset(months=skip_recent_months)
    end_slice = prices_wide.index[prices_wide.index <= end_target]
    if len(end_slice) == 0:
        return pd.Series(dtype=float)
    end_date = end_slice[-1]
    target = today - pd.DateOffset(months=months)
    earlier = prices_wide.index[prices_wide.index <= target]
    if len(earlier) == 0:
        return pd.Series(dtype=float)
    earlier_date = earlier[-1]
    return prices_wide.loc[end_date] / prices_wide.loc[earlier_date] - 1.0


def overlay_in_market(spy: pd.Series, asof: pd.Timestamp, sma_months: int) -> bool:
    valid = spy.loc[:asof].dropna()
    if len(valid) < 21 * sma_months:
        return True
    today = float(valid.iloc[-1])
    sma = float(valid.iloc[-21 * sma_months:].mean())
    return today > sma


def leg_drawdown_to_cash(
    prices_wide: pd.DataFrame,
    ticker: str,
    asof: pd.Timestamp,
    sma_months: int,
    confirm_months: int,
) -> bool:
    """Per-leg absolute-momentum gate. Returns True if this leg should hold CASH.

    The chosen ETF is forced to cash only when its OWN month-end close has been
    below its OWN `sma_months`-month moving average for `confirm_months`
    consecutive months. The confirmation window is the anti-whipsaw: one month
    poking below the line does nothing; the trend has to genuinely break and stay
    broken before we step aside. Fail-open: if there is not enough history to
    judge, stay invested.
    """
    s = prices_wide[ticker].loc[:asof].dropna()
    if s.empty:
        return False
    monthly = s.resample("ME").last()
    if len(monthly) < sma_months + confirm_months:
        return False  # not enough history -> stay invested
    sma = monthly.rolling(sma_months).mean()
    below_last = (monthly < sma).iloc[-confirm_months:]
    return bool(below_last.all())


def compute_pick(
    prices_wide: pd.DataFrame,
    asof: pd.Timestamp,
    *,
    lookback_months: int = 12,
    skip_recent_months: int = 0,
    drawdown_sma_months: int | None = 10,
    drawdown_confirm_months: int = 2,
    overlay_sma_months: int | None = None,
    defensive_tickers: tuple[str, ...] = (),
) -> TiltResult:
    """Compute the strategy's pick at a specific month-end."""
    # Optional market-wide overlay (whole book to cash). Off by default.
    in_market = True
    if overlay_sma_months and OVERLAY_TICKER in prices_wide.columns:
        in_market = overlay_in_market(prices_wide[OVERLAY_TICKER], asof, overlay_sma_months)

    def _rank(basket_tickers: list[str]) -> list[tuple[str, float]]:
        cols = [t for t in basket_tickers if t in prices_wide.columns]
        if not cols:
            return []
        rets = trailing_return(prices_wide[cols], asof, lookback_months, skip_recent_months).dropna()
        rets = rets.sort_values(ascending=False)
        return [(str(t), float(r)) for t, r in rets.items()]

    factor_rk = _rank(factor_tickers())
    sector_rk = _rank(sector_tickers())

    # Step 1: relative momentum picks each leg's leader.
    factor_pick = factor_rk[0][0] if (in_market and factor_rk) else None
    factor_ret = factor_rk[0][1] if (in_market and factor_rk) else None
    sector_pick = sector_rk[0][0] if (in_market and sector_rk) else None
    sector_ret = sector_rk[0][1] if (in_market and sector_rk) else None

    # Step 2: per-leg absolute-momentum filter. If a leg's leader's own trend
    # has broken (below its SMA for `confirm` consecutive months), that leg
    # holds cash. Legs are judged independently, so one can be in while the
    # other is out (e.g. Energy held while factors went to cash in 2022).
    if drawdown_sma_months:
        if factor_pick is not None and leg_drawdown_to_cash(
            prices_wide, factor_pick, asof, drawdown_sma_months, drawdown_confirm_months
        ):
            factor_pick, factor_ret = None, None
        if sector_pick is not None and leg_drawdown_to_cash(
            prices_wide, sector_pick, asof, drawdown_sma_months, drawdown_confirm_months
        ):
            sector_pick, sector_ret = None, None

    # Defensive sleeve: a leg filtered to cash rotates into the best defensive
    # asset whose OWN trend is up (skip-month momentum rank, gated by its own SMA),
    # instead of holding cash. GEM-style out-asset. Off unless defensive_tickers set.
    if defensive_tickers and in_market:
        def _best_defensive() -> tuple[str | None, float | None]:
            cols = [t for t in defensive_tickers if t in prices_wide.columns]
            if not cols:
                return None, None
            rr = trailing_return(prices_wide[cols], asof, lookback_months,
                                 skip_recent_months).dropna().sort_values(ascending=False)
            for t, r in rr.items():
                if drawdown_sma_months and leg_drawdown_to_cash(
                    prices_wide, str(t), asof, drawdown_sma_months, drawdown_confirm_months
                ):
                    continue  # skip a defensive that is itself in a downtrend
                return str(t), float(r)
            return None, None
        if factor_pick is None:
            factor_pick, factor_ret = _best_defensive()
        if sector_pick is None:
            sector_pick, sector_ret = _best_defensive()

    return TiltResult(
        asof=asof.date(),
        factor_pick=factor_pick,
        sector_pick=sector_pick,
        factor_return_12m=factor_ret,
        sector_return_12m=sector_ret,
        overlay_in_market=in_market,
        factor_rankings=factor_rk,
        sector_rankings=sector_rk,
    )


def backtest(
    prices: pd.DataFrame,
    config: TiltConfig,
) -> dict:
    """Run the full historical backtest. Returns equity_curve + history."""
    prices_wide = long_to_wide(prices)
    # Restrict to the LSE trading calendar. The raw union index includes
    # US-listed SPY, which prints on UK bank holidays (e.g. 31 Aug 2020) when
    # every .L ETF is shut. Such rows are all-NaN for the tradable universe and
    # poison both the month-end pick (ranker sees no prices) and any 12m lookback
    # that lands on them (e.g. 31 Aug 2021), spuriously forcing the book to cash.
    # Dropping them makes month-end fall on the last real LSE session instead.
    lse_cols = [c for c in prices_wide.columns if c.endswith(".L")]
    if lse_cols:
        prices_wide = prices_wide.loc[prices_wide[lse_cols].notna().any(axis=1)]
    end = config.end or prices_wide.index.max().date()
    rebal_dates = [d for d in last_trading_days_of_month(prices_wide.index)
                   if config.start <= d.date() <= end]

    cost = config.transaction_cost_bps / 10_000.0
    leg_nav = {"factor": config.starting_capital / 2,
               "sector": config.starting_capital / 2}
    leg_holding = {"factor": None, "sector": None}
    leg_shares = {"factor": 0.0, "sector": 0.0}

    equity_rows = []
    history = []
    rebal_set = set(rebal_dates)
    all_days = prices_wide.index[(prices_wide.index.date >= config.start) & (prices_wide.index.date <= end)]

    for d in all_days:
        # mark-to-market
        for leg in ("factor", "sector"):
            tk = leg_holding[leg]
            if tk is None:
                continue
            p = prices_wide.loc[d, tk] if tk in prices_wide.columns else np.nan
            if np.isnan(p):
                col = prices_wide[tk].loc[:d].dropna()
                if not col.empty:
                    p = col.iloc[-1]
            if not np.isnan(p):
                leg_nav[leg] = leg_shares[leg] * float(p)

        if d in rebal_set:
            picks = compute_pick(prices_wide, d,
                                 lookback_months=config.lookback_months,
                                 skip_recent_months=config.skip_recent_months,
                                 drawdown_sma_months=config.drawdown_sma_months,
                                 drawdown_confirm_months=config.drawdown_confirm_months,
                                 overlay_sma_months=config.overlay_sma_months,
                                 defensive_tickers=config.defensive_tickers)
            for leg, target in (("factor", picks.factor_pick), ("sector", picks.sector_pick)):
                current = leg_holding[leg]
                if target == current:
                    continue
                # sell current
                if current is not None:
                    p = prices_wide.loc[d, current]
                    if not np.isnan(p):
                        leg_nav[leg] = leg_shares[leg] * float(p) * (1 - cost)
                    leg_shares[leg] = 0.0
                    leg_holding[leg] = None
                # buy target
                if target is not None:
                    p = prices_wide.loc[d, target]
                    if not np.isnan(p) and p > 0:
                        spend = leg_nav[leg] * (1 - cost)
                        leg_shares[leg] = spend / float(p)
                        leg_holding[leg] = target

            # Optional rebalance of the two legs back to 50/50. Default "none"
            # leaves the loop above untouched (legs drift, published behaviour).
            do_rebal = config.rebalance == "monthly" or (config.rebalance == "annual" and d.month == 1)
            if config.rebalance != "none" and do_rebal:
                def _mtm(leg: str) -> float:
                    tk = leg_holding[leg]
                    if tk is None:
                        return leg_nav[leg]
                    p = prices_wide.loc[d, tk]
                    if np.isnan(p):
                        col = prices_wide[tk].loc[:d].dropna()
                        p = col.iloc[-1] if not col.empty else np.nan
                    return leg_shares[leg] * float(p) if not np.isnan(p) else leg_nav[leg]
                total = _mtm("factor") + _mtm("sector")
                for leg in ("factor", "sector"):
                    target_val = total / 2
                    new_val = target_val - cost * abs(target_val - _mtm(leg))  # cost on moved delta
                    leg_nav[leg] = new_val
                    tk = leg_holding[leg]
                    if tk is not None:
                        p = prices_wide.loc[d, tk]
                        if np.isnan(p):
                            col = prices_wide[tk].loc[:d].dropna()
                            p = col.iloc[-1] if not col.empty else np.nan
                        if not np.isnan(p) and p > 0:
                            leg_shares[leg] = new_val / float(p)

            total_nav = leg_nav["factor"] + leg_nav["sector"]
            # Benchmark close as-of this month-end (last valid <= d). None before
            # VWRP inception (2019-07) so the dashboard shows "—" for those months.
            bench_close = None
            if BENCHMARK_TICKER in prices_wide.columns:
                bcol = prices_wide[BENCHMARK_TICKER].loc[:d].dropna()
                if not bcol.empty:
                    bench_close = float(bcol.iloc[-1])
            history.append({
                "asof": d.date().isoformat(),
                "factor_pick": picks.factor_pick,
                "sector_pick": picks.sector_pick,
                "factor_return_12m": picks.factor_return_12m,
                "sector_return_12m": picks.sector_return_12m,
                "overlay_in_market": picks.overlay_in_market,
                "factor_rankings": picks.factor_rankings,
                "sector_rankings": picks.sector_rankings,
                "portfolio_value": total_nav,
                "factor_leg_value": leg_nav["factor"],
                "sector_leg_value": leg_nav["sector"],
                "benchmark_close": bench_close,
            })

        total_nav = leg_nav["factor"] + leg_nav["sector"]
        equity_rows.append({"date": d.date().isoformat(), "portfolio_value": total_nav})

    equity = pd.DataFrame(equity_rows)
    return {
        "equity": equity,
        "history": history,
        "metrics": _compute_metrics(equity),
    }


def _compute_metrics(equity: pd.DataFrame) -> dict:
    s = pd.to_numeric(equity["portfolio_value"], errors="coerce").dropna()
    s = s[s > 0]
    if len(s) < 2:
        return {}
    rets = s.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    dates = pd.to_datetime(equity["date"]).iloc[s.index]
    yrs = (dates.iloc[-1] - dates.iloc[0]).days / 365.25
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else np.nan
    vol = rets.std() * np.sqrt(252)
    sharpe = (rets.mean() * 252) / vol if vol > 0 else np.nan
    cummax = s.cummax()
    dd = (s / cummax - 1).min()
    return {
        "start_value": float(s.iloc[0]),
        "end_value": float(s.iloc[-1]),
        "years": float(yrs),
        "cagr": float(cagr) if not np.isnan(cagr) else None,
        "vol_ann": float(vol),
        "sharpe": float(sharpe) if not np.isnan(sharpe) else None,
        "max_drawdown": float(dd),
    }
