# The per-leg drawdown filter

This is the "seatbelt" added to the rotation in `engine.py`. It is ON by default
(`drawdown_sma_months=10`, `drawdown_confirm_months=2`). This note explains
exactly what it is, how it works, and why it works.

## What it is, in one sentence

Each leg (factor and sector) is only held if its chosen ETF's own price is in an
uptrend; if that ETF's trend has broken, the leg sits in cash instead of riding
it down.

## The two kinds of momentum

The strategy uses momentum twice, for two different jobs:

1. **Relative momentum (the picker).** Among the basket, which ETF has the
   highest 12-month return? That is the leader. This decides *what* to hold.
   Relative momentum is always "in", it just rotates to the least-bad option.

2. **Absolute momentum (the filter).** Is that leader actually trending up on its
   own, or is it merely the best of a falling bunch? This decides *whether* to
   hold at all. If even the leader is in a downtrend, hold cash.

Relative momentum alone is what rides a broad bear market down: in 2008 it just
kept rotating into whichever sector was falling slowest. Absolute momentum is the
brake that says "everything here is falling, step aside".

## How the filter works (precise mechanics)

At each month-end, for each leg's chosen ETF:

1. Take that ETF's own month-end closing prices.
2. Compute its own 10-month simple moving average (SMA).
3. Check the last **2** month-ends. If the close was **below** the SMA on **both**
   of them, the leg goes to **cash** next month. Otherwise it holds the ETF.

The legs are judged **independently**, so the book can hold 2, 1, or 0 ETFs.
(Example: in 2022 Energy stayed above its trend while the factor leg's leader
broke down, so the book held Energy + cash.)

Fail-open: if an ETF has too little history to compute the SMA, the leg stays
invested. The filter only ever removes risk, never adds leverage.

## Why the 2-month confirmation matters

A naive "below the 10-month SMA -> cash immediately" rule whipsaws badly: price
pokes below the line for one month, you sell, it bounces, you rebuy higher, you
bleed on costs and bad timing. Requiring the close to be below the SMA for **two
consecutive months** filters out single-month noise and only acts when a trend
has genuinely broken. In testing this one change lifted the sector-leg Sharpe
from 0.58 to 0.68 and cut the 2008 loss from −14% to −6%, while keeping the 2022
energy win. Confirmation is the difference between a useful filter and a costly one.

## Why it works (the evidence)

Trend-following / absolute-momentum filters are one of the most robust findings
in market history. On the S&P 500 back to 1928, a 10-month-SMA timing rule lifts
the Sharpe from 0.43 (buy and hold) to 0.63 and cuts the worst drawdown from
−86% to −50%, by sitting out the deflationary crashes (1930s, 1970s, 2000-02,
2008). Applied per-leg here, over 2000-26 on the sector rotation it turned the
2008 loss from −32% (no filter) into −6%, lifted Sharpe 0.61 -> 0.68, and kept
the +38% energy run in 2022. (Lineage: Faber's "Quantitative Approach to
Tactical Asset Allocation", 2007; Antonacci's *Dual Momentum*, 2014.)

## What it does NOT do (honest limits)

- **It does not dodge fast crashes.** A monthly filter cannot react inside a
  one-month crash (e.g. Covid, March 2020). The brake is for slow, grinding
  bears, not flash crashes.
- **It does not fix the dot-com type bear well.** When a few defensive sectors
  keep trending up while the index falls, the rotation stays invested in those,
  so per-leg protection is partial (~−33% in 2000-02). Only a whole-book market
  gate dodges that, and that gate also kills rotation winners like 2022, so it is
  left off.
- **In a long bull it is close to free, not better.** Over 2019-26 it returned
  the same as no filter (it stayed ~95% invested). Its value is reserved for the
  structural bear the live record has not yet seen.

## Config

```python
TiltConfig(
    drawdown_sma_months=10,    # SMA window per leg; set None to disable the filter
    drawdown_confirm_months=2, # consecutive months below SMA before going to cash
    overlay_sma_months=None,   # the coarser whole-book SPY gate; left off
)
```
