"""Daily report — posts to #hedgefund. SPEC §11.3."""
from __future__ import annotations

from datetime import date, datetime, timezone

from ...core.db import conn
from ...core.logging import log_activity
from ..alerts.discord import post


def _query_portfolio_today():
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT total_value, daily_return, cumulative_return, drawdown, regime "
            "FROM portfolio_snapshots WHERE date = %s",
            (date.today(),),
        )
        return cur.fetchone()


def _query_quality():
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT health_score FROM data_quality_reports "
            "ORDER BY timestamp DESC LIMIT 1"
        )
        r = cur.fetchone()
        return r[0] if r else None


def _query_trades_today():
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT ticker, side, quantity, fill_price, rationale "
            "FROM trades WHERE date(timestamp) = %s ORDER BY timestamp DESC",
            (date.today(),),
        )
        return cur.fetchall()


def generate_and_post() -> dict:
    snap = _query_portfolio_today()
    qhealth = _query_quality()
    trades = _query_trades_today()
    today_str = date.today().isoformat()

    lines = [
        f"**🏹 Artemis Daily Report — {today_str}**",
        "",
    ]
    if snap:
        total, ret, cret, dd, regime = snap
        lines.append(f"Portfolio: **${total:,.2f}** (today {float(ret or 0)*100:+.2f}%, "
                     f"cum {float(cret or 0)*100:+.2f}%, drawdown {float(dd or 0)*100:+.2f}%)")
        lines.append(f"Regime: `{regime or 'unknown'}`")
    else:
        lines.append("Portfolio: _no snapshot recorded today (bootstrap phase)_")
    lines.append("")

    if trades:
        lines.append(f"**Trades ({len(trades)}):**")
        for t in trades[:10]:
            ticker, side, qty, fill, rationale = t
            lines.append(f"  • {side.upper()} {qty} {ticker} @ ${float(fill or 0):.2f} — "
                         f"_{(rationale or '')[:80]}_")
    else:
        lines.append("**Trades:** (none today)")

    lines.append("")
    lines.append(f"Data quality health: **{qhealth if qhealth is not None else 'n/a'}/100**")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")

    body = "\n".join(lines)
    ok = post(body)
    log_activity("daily_report", "generate_and_post", "ok" if ok else "skipped",
                 trades=len(trades), has_snapshot=snap is not None)
    return {"posted": ok, "trades": len(trades)}
