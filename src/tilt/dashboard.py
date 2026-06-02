"""Static-HTML dashboard renderer (Palantir aesthetic).

Reads:
  data/history.jsonl   — chronological list of monthly picks + equity NAV
Writes:
  docs/index.html
  docs/history.json    — the same data exposed for client-side filtering
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .palantir import PL
from .universe import FACTOR_BASKET, SECTOR_BASKET, name_for

ROOT = Path(__file__).resolve().parent.parent.parent
HISTORY = ROOT / "data" / "history.jsonl"
DOCS = ROOT / "docs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    return [json.loads(line) for line in HISTORY.read_text().splitlines() if line.strip()]


def _pct(x, signed: bool = False) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    val = x * 100
    fmt = f"{val:+.1f}%" if signed else f"{val:.1f}%"
    return fmt


def _monthly_vs_benchmark(history: list[dict]) -> tuple[dict, dict]:
    """For each month, the 50/50 portfolio's own return vs VWRP's return.

    Tilt month return = pct change in portfolio_value between consecutive rows.
    VWRP month return = pct change in benchmark_close. Both are None for the
    first row and for any month where the benchmark has no price yet (pre-2019-07).
    Returns (per-asof map, summary). 'beat' is True when Tilt >= VWRP that month.

    Caveat: portfolio_value is built from USD-priced ETFs while VWRP is GBP, so a
    small monthly FX term is baked into the spread. This is a texture/honesty
    view, not an FX-clean attribution.
    """
    out: dict[str, dict] = {}
    wins = total = 0
    excess_sum = 0.0
    for i, h in enumerate(history):
        tilt = vwrp = None
        if i > 0:
            pv0, pv1 = history[i - 1].get("portfolio_value"), h.get("portfolio_value")
            if pv0 and pv1 and pv0 > 0:
                tilt = pv1 / pv0 - 1.0
            b0, b1 = history[i - 1].get("benchmark_close"), h.get("benchmark_close")
            if b0 and b1 and b0 > 0:
                vwrp = b1 / b0 - 1.0
        beat = None
        if tilt is not None and vwrp is not None:
            beat = tilt >= vwrp
            total += 1
            wins += 1 if beat else 0
            excess_sum += tilt - vwrp
        out[h["asof"]] = {"tilt": tilt, "vwrp": vwrp, "beat": beat}
    summary = {
        "wins": wins,
        "total": total,
        "rate": (wins / total) if total else None,
        "avg_excess": (excess_sum / total) if total else None,
    }
    return out, summary


def _equity_chart_svg(history: list[dict], width: int = 1000, height: int = 320) -> str:
    if len(history) < 2:
        return '<div class="empty">Equity curve will appear once 2+ months are tracked.</div>'
    dates = [pd.to_datetime(h["asof"]) for h in history]
    vals = [h["portfolio_value"] for h in history]

    # VWRP buy-and-hold, indexed to the strategy NAV at the first month VWRP has
    # a price (2019-07, its inception). Both lines therefore share that point and
    # the gap after it is pure relative performance. None before the anchor.
    anchor_i = next((i for i, h in enumerate(history) if h.get("benchmark_close")), None)
    bench_vals: list[float | None] = [None] * len(history)
    if anchor_i is not None:
        a_close = history[anchor_i]["benchmark_close"]
        a_nav = history[anchor_i]["portfolio_value"]
        for i, h in enumerate(history):
            bc = h.get("benchmark_close")
            if bc and i >= anchor_i:
                bench_vals[i] = a_nav * (bc / a_close)

    pad_l, pad_r, pad_t, pad_b = 70, 24, 28, 44
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(vals)
    present = vals + [b for b in bench_vals if b is not None]
    vmin = min(present)
    vmax = max(present)
    span = (vmax - vmin) or 1

    def _xy(i: int, v: float) -> tuple[float, float]:
        x = pad_l + i * (plot_w / (n - 1))
        y = pad_t + plot_h - ((v - vmin) / span) * plot_h
        return x, y

    pts = [_xy(i, v) for i, v in enumerate(vals)]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    bench_pts = [_xy(i, b) for i, b in enumerate(bench_vals) if b is not None]
    bench_polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in bench_pts)

    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="currentColor"/>'
        for x, y in pts[-1:]  # only last point highlighted
    )
    y_grid = []
    for frac in (0.0, 0.5, 1.0):
        val = vmin + span * frac
        y = pad_t + plot_h - frac * plot_h
        y_grid.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" '
            f'stroke="currentColor" stroke-opacity="0.08"/>'
            f'<text x="{pad_l - 10}" y="{y + 3:.1f}" text-anchor="end" font-size="10" '
            f'fill="currentColor" opacity="0.55">£{val/1000:.0f}k</text>'
        )
    step = max(1, n // 8)
    x_labels = "".join(
        f'<text x="{pts[i][0]:.1f}" y="{height - 16}" text-anchor="middle" '
        f'font-size="10" fill="currentColor" opacity="0.55">{dates[i].strftime("%Y-%m")}</text>'
        for i in range(0, n, step)
    )

    # End-of-line labels + legend
    bench_label = ""
    if bench_pts:
        bx, by = bench_pts[-1]
        bench_label = (
            f'<polyline fill="none" stroke="currentColor" stroke-opacity="0.45" '
            f'stroke-width="1.3" stroke-dasharray="4 3" points="{bench_polyline}"/>'
            f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="2.5" fill="currentColor" fill-opacity="0.45"/>'
            f'<text x="{bx-6:.1f}" y="{by-7:.1f}" text-anchor="end" font-size="10" '
            f'fill="currentColor" opacity="0.55">VWRP £{bench_vals[-1]/1000:.0f}k</text>'
        )
    tx, ty = pts[-1]
    tilt_label = (
        f'<text x="{tx-6:.1f}" y="{ty+13:.1f}" text-anchor="end" font-size="10" '
        f'fill="currentColor" opacity="0.85" font-weight="600">Tilt £{vals[-1]/1000:.0f}k</text>'
    )
    legend = (
        f'<g transform="translate({pad_l},{pad_t-14})" font-size="10" fill="currentColor">'
        f'<line x1="0" y1="0" x2="18" y2="0" stroke="currentColor" stroke-width="1.6"/>'
        f'<text x="23" y="3" opacity="0.85">Tilt 50/50</text>'
        f'<line x1="92" y1="0" x2="110" y2="0" stroke="currentColor" stroke-opacity="0.45" stroke-width="1.3" stroke-dasharray="4 3"/>'
        f'<text x="115" y="3" opacity="0.55">VWRP (indexed from {dates[anchor_i].strftime("%Y-%m") if anchor_i is not None else "start"})</text>'
        f'</g>'
    )

    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" style="max-width:100%;height:auto;">'
        f'{"".join(y_grid)}'
        f'{bench_label}'
        f'<polyline fill="none" stroke="currentColor" stroke-width="1.6" points="{polyline}"/>'
        f'{dots}{tilt_label}{legend}{x_labels}'
        f'</svg>'
    )


def _pick_card(label: str, pick: str | None, ret_12m: float | None,
               rankings: list[list], top_n: int | None = None) -> str:
    """Full league table for the bucket this month: every ETF ranked by 12-1
    momentum, the pick highlighted. top_n=None shows the whole basket."""
    if pick is None:
        body = '<div class="ticker cash">CASH</div><div class="meta muted">drawdown filter: trend broken</div>'
    else:
        body = (
            f'<div class="ticker">{pick}</div>'
            f'<div class="name">{name_for(pick)}</div>'
            f'<div class="meta">12-1 month return: '
            f'<strong class="accent">{_pct(ret_12m, signed=True)}</strong></div>'
        )
    rows = rankings if top_n is None else rankings[:top_n]
    runners = "".join(
        f'<tr style="{"background:rgba(212,160,23,0.12);" if tk == pick else ""}">'
        f'<td class="rank">{i+1}</td>'
        f'<td><span class="tk">{tk}</span> '
        f'<span class="muted" style="font-size:11px;">{name_for(tk)}</span></td>'
        f'<td class="num {"accent" if r>=0 else "neg"}">{_pct(r, signed=True)}</td></tr>'
        for i, (tk, r) in enumerate(rows)
    )
    return f"""
    <div class="pick-card">
      <div class="leg-label">{label}</div>
      {body}
      <table class="runners">
        <thead><tr><th>#</th><th>ETF (this month's league)</th><th class="right">12-1 mo</th></tr></thead>
        <tbody>{runners}</tbody>
      </table>
    </div>
    """


def _delta_pill(tilt, vwrp, beat) -> str:
    """Coloured ▲/▼ pill showing this month's excess over VWRP, in pp."""
    if tilt is None or vwrp is None or beat is None:
        return '<span class="muted">—</span>'
    pp = (tilt - vwrp) * 100
    arrow = "▲" if beat else "▼"
    cls = "win" if beat else "loss"
    return f'<span class="pill {cls}">{arrow} {pp:+.1f}pp</span>'


def _history_table(history: list[dict]) -> str:
    if not history:
        return '<div class="empty">History will accumulate after the first monthly run.</div>'
    rmap, summary = _monthly_vs_benchmark(history)

    if summary["total"]:
        rate = summary["rate"] * 100
        avg = summary["avg_excess"] * 100
        rate_cls = "accent" if rate >= 50 else "neg"
        avg_cls = "accent" if avg >= 0 else "neg"
        caption = (
            f'<div class="bm-summary">'
            f'Beat VWRP in <strong class="{rate_cls}">{summary["wins"]} of {summary["total"]}</strong> '
            f'months (<strong class="{rate_cls}">{rate:.0f}%</strong>). '
            f'Average monthly excess: <strong class="{avg_cls}">{avg:+.2f}pp</strong>. '
            f'<span class="muted">Green = the 50/50 beat a passive all-world hold that month; red = it lagged.</span>'
            f'</div>'
        )
    else:
        caption = ""

    rows = []
    # Reverse chronological — most recent first
    for h in reversed(history):
        f_tk = h.get("factor_pick") or "CASH"
        s_tk = h.get("sector_pick") or "CASH"
        f_ret = h.get("factor_return_12m")
        s_ret = h.get("sector_return_12m")
        nav = h.get("portfolio_value", 0)
        mr = rmap.get(h["asof"], {})
        tilt, vwrp, beat = mr.get("tilt"), mr.get("vwrp"), mr.get("beat")
        tilt_cls = "num " + ("win-num" if beat else "loss-num") if beat is not None else "num muted"
        rows.append(
            f"<tr>"
            f'<td class="muted">{h["asof"]}</td>'
            f'<td><span class="tk">{f_tk}</span><span class="tkname">{name_for(f_tk) if f_tk != "CASH" else ""}</span></td>'
            f'<td class="num">{_pct(f_ret, signed=True)}</td>'
            f'<td><span class="tk">{s_tk}</span><span class="tkname">{name_for(s_tk) if s_tk != "CASH" else ""}</span></td>'
            f'<td class="num">{_pct(s_ret, signed=True)}</td>'
            f'<td class="num">£{nav/1000:.1f}k</td>'
            f'<td class="{tilt_cls}">{_pct(tilt, signed=True)}</td>'
            f'<td class="num muted">{_pct(vwrp, signed=True)}</td>'
            f'<td class="num">{_delta_pill(tilt, vwrp, beat)}</td>'
            f"</tr>"
        )
    return f"""
    {caption}
    <table class="history-table">
      <thead><tr>
        <th>MONTH</th>
        <th>FACTOR LEG</th><th class="right">12M</th>
        <th>SECTOR LEG</th><th class="right">12M</th>
        <th class="right">NAV</th>
        <th class="right">TILT 1M</th>
        <th class="right">VWRP 1M</th>
        <th class="right">vs VWRP</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    """


def _universe_table() -> str:
    rows_f = "".join(
        f'<tr><td><span class="tk">{tk}</span></td><td>{name}</td></tr>'
        for tk, name in FACTOR_BASKET
    )
    rows_s = "".join(
        f'<tr><td><span class="tk">{tk}</span></td><td>{name}</td></tr>'
        for tk, name in SECTOR_BASKET
    )
    return f"""
    <div class="universe-grid">
      <div>
        <div class="leg-label">FACTOR BASKET · 8 ETFs</div>
        <table class="universe-table"><tbody>{rows_f}</tbody></table>
      </div>
      <div>
        <div class="leg-label">SECTOR BASKET · 12 ETFs</div>
        <table class="universe-table"><tbody>{rows_s}</tbody></table>
      </div>
    </div>
    """


def _holdings_persistence(history: list[dict]) -> str:
    """How many months did each ETF spend as the pick?"""
    if not history:
        return ""
    f_counter = {}
    s_counter = {}
    for h in history:
        f = h.get("factor_pick")
        s = h.get("sector_pick")
        if f:
            f_counter[f] = f_counter.get(f, 0) + 1
        if s:
            s_counter[s] = s_counter.get(s, 0) + 1
    total = len(history)

    def _rows(counter):
        items = sorted(counter.items(), key=lambda x: -x[1])
        out = []
        for tk, n in items:
            pct = n / total * 100
            bar_w = pct * 2  # px multiplier
            out.append(
                f"<tr><td><span class='tk'>{tk}</span></td>"
                f"<td class='small muted'>{name_for(tk)}</td>"
                f"<td class='num'><strong>{n}</strong></td>"
                f"<td><div class='barwrap'><div class='bar' style='width:{bar_w:.0f}px'></div></div></td>"
                f"<td class='num muted'>{pct:.0f}%</td></tr>"
            )
        return "".join(out)

    return f"""
    <div class="universe-grid">
      <div>
        <div class="leg-label">FACTOR LEG · TIME-IN-BASKET</div>
        <table class="persistence-table"><tbody>{_rows(f_counter)}</tbody></table>
      </div>
      <div>
        <div class="leg-label">SECTOR LEG · TIME-IN-BASKET</div>
        <table class="persistence-table"><tbody>{_rows(s_counter)}</tbody></table>
      </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------


def render() -> Path:
    history = _load_history()
    DOCS.mkdir(parents=True, exist_ok=True)
    # Expose history.json for any future client-side tooling
    (DOCS / "history.json").write_text(json.dumps(history, indent=2, default=str))

    latest = history[-1] if history else None
    metrics = {}
    if history:
        # Compute backtest metrics from full history
        s = pd.Series([h["portfolio_value"] for h in history])
        if (s > 0).all() and len(s) >= 2:
            dates = pd.to_datetime([h["asof"] for h in history])
            yrs = (dates[-1] - dates[0]).days / 365.25
            cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else float("nan")
            cummax = s.cummax()
            dd = (s / cummax - 1).min()
            rets = s.pct_change().dropna()
            sharpe = (rets.mean() * 12) / (rets.std() * np.sqrt(12)) if rets.std() > 0 else float("nan")
            metrics = {
                "cagr": cagr, "sharpe": sharpe, "max_dd": dd,
                "end_value": float(s.iloc[-1]),
                "months_tracked": len(history),
                "first_asof": history[0]["asof"],
                "last_asof": history[-1]["asof"],
            }

    factor_card = _pick_card(
        "FACTOR LEG",
        latest.get("factor_pick") if latest else None,
        latest.get("factor_return_12m") if latest else None,
        latest.get("factor_rankings", []) if latest else [],
    ) if latest else "<div class='empty'>No picks yet.</div>"
    sector_card = _pick_card(
        "SECTOR LEG",
        latest.get("sector_pick") if latest else None,
        latest.get("sector_return_12m") if latest else None,
        latest.get("sector_rankings", []) if latest else [],
    ) if latest else "<div class='empty'>No picks yet.</div>"

    equity_svg = _equity_chart_svg(history)
    history_html = _history_table(history)
    universe_html = _universe_table()
    persistence_html = _holdings_persistence(history)

    months_tracked = metrics.get("months_tracked", 0)
    cagr_pct = _pct(metrics.get("cagr"), signed=True) if metrics else "—"
    sharpe_str = f"{metrics['sharpe']:.2f}" if metrics.get("sharpe") is not None else "—"
    dd_pct = _pct(metrics.get("max_dd"), signed=True) if metrics else "—"
    end_value_str = f"£{metrics.get('end_value', 0)/1000:.1f}k" if metrics else "—"

    # VWRP buy-and-hold end value, indexed to strategy NAV at VWRP inception.
    bench_end_str = "—"
    bench_multiple_str = ""
    if history:
        ai = next((i for i, h in enumerate(history) if h.get("benchmark_close")), None)
        if ai is not None:
            a_close = history[ai]["benchmark_close"]
            a_nav = history[ai]["portfolio_value"]
            b_end = a_nav * (history[-1]["benchmark_close"] / a_close)
            bench_end_str = f"£{b_end/1000:.1f}k"
            if b_end > 0:
                bench_multiple_str = f" Tilt ended <strong>{history[-1]['portfolio_value']/b_end:.2f}×</strong> the VWRP hold over the same window."

    asof = latest["asof"] if latest else "—"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Tilt · ETF rotation by 12-minus-1-month momentum</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --ink: {PL.ink};
      --stage: {PL.stage};
      --bone: {PL.bone};
      --mute: {PL.mute};
      --graphite: {PL.graphite};
      --hairline-dk: {PL.hairline_dk};
      --hairline-lt: {PL.hairline_lt};
      --green: {PL.accent_green};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--stage);
      color: var(--graphite);
      font-family: "Inter", system-ui, -apple-system, sans-serif;
      font-size: 15px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }}
    .page {{ max-width: 1080px; margin: 0 auto; padding: 64px 40px 80px; }}
    .chip {{
      display: inline-block;
      padding: 8px 16px;
      border: 1px solid var(--graphite);
      border-radius: 999px;
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.14em;
      color: var(--graphite);
    }}
    h1 {{
      font-size: 64px;
      font-weight: 400;
      letter-spacing: -0.022em;
      line-height: 1.02;
      margin: 28px 0 16px;
    }}
    h2 {{ font-size: 22px; font-weight: 500; margin: 56px 0 16px; letter-spacing: -0.005em; }}
    .lede {{ max-width: 720px; color: #4A4A47; font-size: 16px; line-height: 1.6; }}
    hr {{ border: 0; border-top: 1px solid var(--hairline-lt); margin: 48px 0 28px; }}

    .stats {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 24px;
      margin: 24px 0 8px;
    }}
    .stat .num {{
      font-size: 42px;
      font-weight: 600;
      letter-spacing: -0.025em;
      line-height: 1;
    }}
    .stat .num.small {{ font-size: 28px; }}
    .stat .lbl {{
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--mute);
      margin-top: 8px;
    }}
    .stat .num.accent {{ color: var(--green); }}
    .accent {{ color: var(--green); }}
    .neg {{ color: #B23D3D; }}
    .muted {{ color: var(--mute); }}
    .small {{ font-size: 12px; }}

    .picks {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-top: 20px;
    }}
    .pick-card {{
      background: var(--ink);
      color: var(--bone);
      border-radius: 24px;
      padding: 32px 28px;
    }}
    .pick-card .leg-label {{
      font-size: 10px;
      letter-spacing: 0.18em;
      color: rgba(245,243,238,0.55);
      margin-bottom: 18px;
    }}
    .pick-card .ticker {{
      font-size: 52px;
      font-weight: 600;
      letter-spacing: -0.025em;
      line-height: 1;
    }}
    .pick-card .ticker.cash {{ color: var(--mute); }}
    .pick-card .name {{
      margin-top: 8px;
      color: rgba(245,243,238,0.75);
      font-size: 13px;
    }}
    .pick-card .meta {{ margin-top: 14px; font-size: 13px; }}
    .pick-card .accent {{ color: #7ED2A6; }}
    .pick-card table.runners {{
      width: 100%;
      margin-top: 24px;
      border-collapse: collapse;
      font-variant-numeric: tabular-nums;
    }}
    .pick-card .runners th {{
      text-align: left;
      font-size: 9px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: rgba(245,243,238,0.45);
      font-weight: 500;
      padding-bottom: 8px;
      border-bottom: 1px solid rgba(245,243,238,0.10);
    }}
    .pick-card .runners th.right, .pick-card .runners td.num {{ text-align: right; }}
    .pick-card .runners td {{
      padding: 8px 4px;
      font-size: 12px;
      border-bottom: 1px solid rgba(245,243,238,0.06);
    }}
    .pick-card .runners td.rank {{ color: rgba(245,243,238,0.4); width: 24px; }}
    .pick-card .runners .tk {{ font-weight: 600; }}
    .pick-card .runners .accent {{ color: #7ED2A6; }}
    .pick-card .runners .neg {{ color: #E08F8F; }}

    .lightcard {{
      background: var(--bone);
      border: 1px solid var(--hairline-lt);
      border-radius: 24px;
      padding: 32px 28px;
      margin-top: 20px;
      color: var(--ink);
      overflow-x: auto;
    }}

    table.history-table, table.universe-table, table.persistence-table {{
      width: 100%;
      border-collapse: collapse;
      font-variant-numeric: tabular-nums;
    }}
    table.history-table thead th, table.persistence-table thead th {{
      text-align: left;
      font-size: 9px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--mute);
      font-weight: 500;
      padding: 8px 6px;
      border-bottom: 1px solid var(--hairline-lt);
    }}
    table.history-table th.right, table.history-table td.num {{ text-align: right; }}
    table.history-table tbody td, table.universe-table td, table.persistence-table td {{
      padding: 10px 6px;
      font-size: 13px;
      border-bottom: 1px solid var(--hairline-lt);
    }}
    .tk {{ font-weight: 600; font-size: 13px; }}
    .tkname {{ display: block; font-size: 11px; color: var(--mute); margin-top: 2px; }}
    .universe-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }}
    .universe-table td:first-child {{ width: 80px; }}
    .leg-label {{
      font-size: 10px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--mute);
      margin-bottom: 12px;
    }}
    .barwrap {{ width: 200px; }}
    .bar {{ height: 4px; background: var(--ink); border-radius: 2px; }}
    .empty {{ text-align: center; color: var(--mute); padding: 20px; font-size: 13px; }}

    .bm-summary {{
      font-size: 14px;
      margin-bottom: 18px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--hairline-lt);
      line-height: 1.6;
    }}
    .win-num {{ color: var(--green); font-weight: 600; }}
    .loss-num {{ color: #B23D3D; font-weight: 600; }}
    .pill {{
      display: inline-block;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 9px;
      border-radius: 999px;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }}
    .pill.win {{ color: var(--green); background: rgba(30,110,64,0.10); }}
    .pill.loss {{ color: #B23D3D; background: rgba(178,61,61,0.10); }}

    .equity-card {{
      background: var(--ink);
      color: var(--bone);
      border-radius: 24px;
      padding: 28px;
      margin-top: 20px;
    }}

    .foot {{
      margin-top: 64px;
      font-size: 11px;
      color: var(--mute);
      letter-spacing: 0.04em;
      line-height: 1.7;
    }}
    .foot a {{ color: var(--graphite); }}

    .method ol {{ font-size: 14px; line-height: 1.65; padding-left: 22px; max-width: 720px; }}
    .method li {{ margin-bottom: 10px; }}
    .method code {{ font-family: ui-monospace, "SFMono-Regular", Menlo, monospace; font-size: 12px; background: rgba(0,0,0,0.04); padding: 1px 6px; border-radius: 3px; }}

    @media (max-width: 720px) {{
      h1 {{ font-size: 40px; }}
      .stats {{ grid-template-columns: 1fr 1fr; }}
      .picks, .universe-grid {{ grid-template-columns: 1fr; }}
      .page {{ padding: 40px 20px 60px; }}
      .pick-card .ticker {{ font-size: 40px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <span class="chip">TILT · ETF ROTATION</span>
    <h1>Two ETFs. One signal.<br/>Every month.</h1>
    <p class="lede">
      Monthly rotation between a factor basket (8 ETFs) and a sector basket (12 ETFs).
      Each month-end, the strategy picks the single ETF in each basket with the highest
      <strong>12-minus-1-month</strong> total return (the 12 months ending one month ago,
      skipping the latest month). Hold both 50/50. Repeat. All ETFs are LSE-listed UCITS,
      Trading 212 accessible.
    </p>

    <hr/>

    <div class="stats">
      <div class="stat">
        <div class="num small">{asof}</div>
        <div class="lbl">Latest pick</div>
      </div>
      <div class="stat">
        <div class="num">{months_tracked}</div>
        <div class="lbl">Months tracked</div>
      </div>
      <div class="stat">
        <div class="num accent">{cagr_pct}</div>
        <div class="lbl">CAGR (since {history[0]["asof"][:7] if history else "—"})</div>
      </div>
      <div class="stat">
        <div class="num">{sharpe_str}</div>
        <div class="lbl">Sharpe</div>
      </div>
    </div>

    <h2>This month's picks &amp; full league table</h2>
    <p class="muted small" style="margin-top:-6px;margin-bottom:14px;max-width:720px;">
      Every ETF in each basket ranked by 12-1 momentum for {asof}. The highlighted row is the pick (top of the basket, unless its trend has broken, in which case the leg holds CASH).
    </p>
    <div class="picks">
      {factor_card}
      {sector_card}
    </div>

    <h2>Equity curve · Tilt vs VWRP · £100k start</h2>
    <div class="equity-card">
      {equity_svg}
      <div style="margin-top:18px;font-size:12px;color:rgba(245,243,238,0.55);">
        Monthly NAV from <strong>{history[0]["asof"] if history else "—"}</strong>
        to <strong>{history[-1]["asof"] if history else "—"}</strong>.
        Realised drawdown: <strong>{dd_pct}</strong>. Tilt end value:
        <strong>{end_value_str}</strong> · VWRP (indexed from its 2019-07 inception):
        <strong>{bench_end_str}</strong>.{bench_multiple_str}
      </div>
    </div>

    <h2>History · monthly picks vs VWRP</h2>
    <div class="lightcard">
      {history_html}
    </div>

    <h2>Time-in-basket · which ETFs the strategy has held</h2>
    <div class="lightcard">
      {persistence_html}
    </div>

    <h2>The universe · 20 ETFs</h2>
    <div class="lightcard">
      {universe_html}
    </div>

    <h2>How it works</h2>
    <div class="lightcard method">
      <ol>
        <li>At each month-end close, compute every ETF's <strong>12-minus-1-month total return</strong> (the 12 months ending one month ago; the most recent month is skipped to avoid short-term reversal, the Jegadeesh-Titman convention).</li>
        <li>From the <strong>factor basket</strong>, pick the single ETF with the highest 12-1 return.</li>
        <li>From the <strong>sector basket</strong>, pick the single ETF with the highest 12-1 return.</li>
        <li><strong>Drawdown filter (per leg).</strong> Hold a pick only while its own price is above its 10-month SMA (confirmed 2 months). If the trend breaks, that leg goes to <strong>CASH</strong> instead of riding it down. That is why a <span class="tk">CASH</span> row appears in the history. Legs are judged independently, so the book can hold 2, 1, or 0 ETFs.</li>
        <li>Hold the surviving picks <strong>50/50</strong> for the next month. If a pick is unchanged, no trade.</li>
        <li>Repeat. No Stage 2 gates, no composite ranker.</li>
      </ol>
      <p class="muted small" style="margin-top:14px;max-width:720px;">
        <strong>Two kinds of momentum.</strong> <em>Relative</em> momentum picks <em>what</em> to hold (the strongest in each basket). <em>Absolute</em> momentum (step 4) decides <em>whether</em> to hold it at all, sitting out the slow grinding bears that ride relative momentum down.
      </p>
      <p class="muted small" style="margin-top:10px;max-width:720px;">
        <strong>The filter is honest insurance, not free alpha.</strong> In a bull market it is a dead heat (stays ~96&#37; invested, changes returns by a whisker). It earns its keep in one regime only, a slow correlated bear: on a 2000-26 reconstruction it cut the 2008 loss from &minus;32&#37; to &minus;6&#37; while keeping the +38&#37; 2022 energy run. It does <em>not</em> fully dodge a dispersed bear (dot-com) or a one-month crash (Covid). We run it anyway because the cover is near-free in normal years.
      </p>
      <p class="muted small" style="margin-top:10px;max-width:720px;">
        Lineage: Antonacci Dual Momentum + Faber Tactical Asset Allocation + MarketFighter Substack.
        Backtested 2019-04 to 2026-06 over the 20-ETF universe above, as run (12-1 momentum, filter ON): <strong>24.4&#37; CAGR, Sharpe 1.04, max DD &minus;31.4&#37;</strong>.
        Forward returns will be lower. Survivorship bias: zero (this is index-tracking ETFs not individual stocks).
      </p>
    </div>

    <div class="foot">
      <p>
        <strong>Disclaimers.</strong> Educational only. Past performance does not predict future returns. The backtest assumes a Euro/GBP-denominated investor and ignores UK CGT. Slippage modelled at 5 bps round-trip. <strong>vs VWRP:</strong> the monthly comparison scores the 50/50 NAV (built from USD-priced ETFs) against VWRP.L (GBP), so a small monthly FX term sits in the spread. It is a like-for-like texture view, not an FX-clean attribution. VWRP price history starts 2019-07, so the first three months show a dash.
      </p>
      <p>
        Updated monthly via GitHub Actions. <a href="history.json">history.json</a> · <a href="https://github.com/soylee22/tilt">Source repo</a>
      </p>
    </div>
  </div>
</body>
</html>
"""
    out = DOCS / "index.html"
    out.write_text(html)
    return out


def main() -> None:
    out = render()
    print(f"dashboard -> {out}")


if __name__ == "__main__":
    main()
