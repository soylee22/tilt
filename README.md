# Tilt

Monthly ETF rotation by 12-minus-1-month momentum (skip the most recent month). Two picks, one signal.

**Live dashboard:** [soylee22.github.io/tilt](https://soylee22.github.io/tilt/)

## Strategy

At each month-end close:

1. Compute every ETF's 12-minus-1-month total return (the 12 months ending one month ago; the most recent month is skipped to avoid short-term reversal, the Jegadeesh-Titman convention).
2. From the **factor basket** (8 ETFs), pick the one with the highest 12m return.
3. From the **sector basket** (12 ETFs), pick the one with the highest 12m return.
4. **Drawdown filter (per leg).** Hold the pick only if its own price is above its 10-month SMA (confirmed 2 months). If its trend has broken, that leg sits in **cash** instead of riding it down. Legs are judged independently, so the book holds 2, 1, or 0 ETFs.
5. Hold the surviving picks 50/50 for the next month. If a pick is unchanged, no trade.
6. Repeat. No Stage 2 filter, no composite ranker.

Two kinds of momentum: **relative** momentum picks *what* to hold (always the strongest in the basket); **absolute** momentum (step 4) decides *whether* to hold it at all. Full mechanics and evidence in [`FILTER.md`](FILTER.md).

## Universe

All LSE-listed UCITS ETFs, available on Trading 212.

**Factor basket (8):** IUMO, IUQA, IUVL, CUS1, IEMO, IEQU, IEVL, WSML.

**Sector basket (12):** IUIT, IHCU, IUES, IUCD, IUCS, IUIS, IUMS, IUFS, IUCM, IUUS, IUSP, SMH.

Full names and inception dates documented in `src/tilt/universe.py`.

## Backtest (2019-04 to 2026-05)

As run (per-leg filter ON), daily resolution:

| Metric | Value |
|---|---|
| CAGR | 23.6% |
| Sharpe | 1.02 |
| Max drawdown | -31% |
| End on £100k | £457k |

vs SPY: 16% CAGR, vs VWRP: 12% CAGR, same window.

### The drawdown filter is honest insurance, not free alpha

- **In a bull market it is a dead heat.** Over this 2019-26 window the filter sits ~96% invested and changes CAGR/Sharpe by a whisker. It is not an improvement on the headline numbers, and we are not pretending it is.
- **It earns its keep in one regime only: a slow, correlated bear.** Reconstructed on US proxies back to 2000 (the .L ETFs lack the history), the sector leg goes from 12.0% CAGR / 0.61 Sharpe to **13.4% / 0.68**, and the **2008 loss drops from -32% to -6%** while the +38% 2022 energy run is kept. That 2008-shaped event is exactly what this five-year live record has never contained.
- **It does not save you from everything.** A *dispersed* bear like dot-com (defensives keep rising, so rotation stays invested, ~-33%) or a *fast* one like Covid (a monthly filter can't react inside a one-month crash) are only partially helped. See [`FILTER.md`](FILTER.md) for the mechanism. We run it anyway because the cover is close to free in normal years.

## Lineage

Antonacci's Dual Momentum + Faber's Tactical Asset Allocation + the MarketFighter
Substack strategy, all reduced to a 50/50 two-pick basket rotation.

## Updating

Monthly GitHub Actions cron on the 1st at 06:23 UTC. Manual dispatch supported.

```bash
gh workflow run "Monthly Tilt run" -R soylee22/tilt
```
