# Tilt

Monthly ETF rotation by 12-month momentum. Two picks, one signal.

**Live dashboard:** [soylee22.github.io/tilt](https://soylee22.github.io/tilt/)

## Strategy

At each month-end close:

1. Compute every ETF's 12-month total return.
2. From the **factor basket** (8 ETFs), pick the one with the highest 12m return.
3. From the **sector basket** (12 ETFs), pick the one with the highest 12m return.
4. Hold both 50/50 for the next month.
5. Repeat. No Stage 2 filter, no composite ranker. Pure relative momentum.

## Universe

All LSE-listed UCITS ETFs, available on Trading 212.

**Factor basket (8):** IUMO, IUQA, IUVL, CUS1, IEMO, IEQU, IEVL, WSML.

**Sector basket (12):** IUIT, IHCU, IUES, IUCD, IUCS, IUIS, IUMS, IUFS, IUCM, IUUS, IUSP, SMH.

Full names and inception dates documented in `src/tilt/universe.py`.

## Backtest (2019-04 to 2026-05)

| Metric | Value |
|---|---|
| CAGR | 23.6% |
| Sharpe | 1.02 |
| Max drawdown | -31% |
| End on £100k | £452k |

vs SPY: 16% CAGR, vs VWRP: 12% CAGR, same window.

## Lineage

Antonacci's Dual Momentum + Faber's Tactical Asset Allocation + the MarketFighter
Substack strategy, all reduced to a 50/50 two-pick basket rotation.

## Updating

Monthly GitHub Actions cron on the 1st at 06:23 UTC. Manual dispatch supported.

```bash
gh workflow run "Monthly Tilt run" -R soylee22/tilt
```
