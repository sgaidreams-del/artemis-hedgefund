"""Analytics endpoints — SPEC §11.1 Performance Analytics page."""
from __future__ import annotations

import datetime
import logging

import yfinance as yf
from fastapi import APIRouter

from src.core.db import conn
from .. import alpaca_client
from ..analytics import (
    correlation_matrix,
    max_drawdown,
    profit_factor,
    running_drawdown,
    sharpe_ratio,
    sortino_ratio,
    win_rate,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
log = logging.getLogger(__name__)

_YF_PERIOD_MAP = {
    "1D": "1d",
    "1W": "5d",
    "1M": "1mo",
    "3M": "3mo",
    "6M": "6mo",
    "1Y": "1y",
    "2Y": "2y",
    "5Y": "5y",
}


def _period_to_yf(period: str) -> str:
    return _YF_PERIOD_MAP.get(period, "1mo")


@router.get("/metrics")
def metrics():
    try:
        with conn() as c, c.cursor() as cur:
            # Last 252 snapshots, oldest first — drawdown depends on order.
            cur.execute(
                "SELECT daily_return FROM ("
                "  SELECT date, daily_return FROM portfolio_snapshots ORDER BY date DESC LIMIT 252"
                ") recent ORDER BY date ASC"
            )
            snapshot_rows = cur.fetchall()

            cur.execute(
                "SELECT fill_price, slippage_bps, side, quantity "
                "FROM trades ORDER BY timestamp ASC"
            )
            trade_rows = cur.fetchall()

        if not snapshot_rows:
            return {
                "sharpe": None,
                "sortino": None,
                "max_drawdown": None,
                "win_rate": None,
                "profit_factor": None,
                "obs_count": 0,
                "trades_count": len(trade_rows),
                "data_source": "none",
                "empty_reason": "No portfolio history yet — portfolio_snapshots is empty.",
            }

        daily_returns = [
            float(r[0]) for r in snapshot_rows if r[0] is not None
        ]
        # max_drawdown() takes an equity curve, not returns — compound them.
        equity_curve = [1.0]
        for r in daily_returns:
            equity_curve.append(equity_curve[-1] * (1 + r))

        # Approximate per-trade PnL as fill_price * quantity * (1 - slippage_bps/10000)
        # for buys and -fill_price * quantity * (1 + slippage_bps/10000) for sells.
        # This is only a proxy; actual P&L requires paired buy/sell matching.
        pnls: list[float] = []
        for row in trade_rows:
            fill, slip_bps, side, qty = row
            if fill is None or qty is None:
                continue
            fill = float(fill)
            qty = float(qty)
            slip = float(slip_bps) / 10_000 if slip_bps is not None else 0.0
            notional = fill * qty
            if side == "buy":
                pnls.append(-notional * (1 + slip))
            else:
                pnls.append(notional * (1 - slip))

        return {
            "sharpe": sharpe_ratio(daily_returns),
            "sortino": sortino_ratio(daily_returns),
            "max_drawdown": max_drawdown(equity_curve),
            "win_rate": win_rate(pnls) if pnls else None,
            "profit_factor": profit_factor(pnls) if pnls else None,
            "obs_count": len(daily_returns),
            "trades_count": len(trade_rows),
            "data_source": "snapshots",
        }
    except Exception as exc:
        log.exception("metrics failed")
        return {"error": str(exc)}


@router.get("/returns-heatmap")
def returns_heatmap(years: int = 2):
    try:
        cutoff = datetime.date.today() - datetime.timedelta(days=years * 365)
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT date, daily_return FROM portfolio_snapshots "
                "WHERE date >= %s ORDER BY date ASC",
                (cutoff,),
            )
            rows = cur.fetchall()

        return {
            "returns": [
                {
                    "date": r[0].isoformat(),
                    "return_pct": float(r[1]) if r[1] is not None else None,
                }
                for r in rows
            ]
        }
    except Exception as exc:
        log.exception("returns-heatmap failed")
        return {"error": str(exc), "returns": []}


@router.get("/benchmark")
def benchmark(period: str = "1M"):
    try:
        portfolio_points = alpaca_client.get_portfolio_history(period=period)

        # SPY: try DB first, fall back to yfinance
        spy_prices: dict[str, float] = {}
        try:
            with conn() as c, c.cursor() as cur:
                cur.execute(
                    "SELECT date, close FROM ohlcv_daily "
                    "WHERE ticker = 'SPY' ORDER BY date ASC"
                )
                spy_rows = cur.fetchall()
            if spy_rows:
                spy_prices = {r[0].isoformat(): float(r[1]) for r in spy_rows}
        except Exception:
            pass

        if not spy_prices:
            yf_period = _period_to_yf(period)
            try:
                df = yf.download("SPY", period=yf_period, auto_adjust=True, progress=False)
                if not df.empty:
                    spy_prices = {
                        str(idx.date()): float(row["Close"])
                        for idx, row in df.iterrows()
                    }
            except Exception:
                pass

        # Normalise portfolio equity
        port_by_date: dict[str, float] = {}
        for pt in portfolio_points:
            ts = pt.get("timestamp")
            eq = pt.get("equity")
            if ts is not None and eq is not None:
                # Alpaca returns Unix timestamps
                if isinstance(ts, (int, float)):
                    date_str = datetime.datetime.utcfromtimestamp(ts).date().isoformat()
                else:
                    date_str = str(ts)[:10]
                port_by_date[date_str] = float(eq)

        all_dates = sorted(set(list(port_by_date.keys()) + list(spy_prices.keys())))
        if not all_dates:
            return {"points": []}

        # Find common start for normalisation
        common_start = None
        for d in all_dates:
            if d in port_by_date and d in spy_prices:
                common_start = d
                break

        port_base = port_by_date.get(common_start) if common_start else None
        spy_base = spy_prices.get(common_start) if common_start else None

        points = []
        for d in all_dates:
            port_val = port_by_date.get(d)
            spy_val = spy_prices.get(d)
            points.append({
                "date": d,
                "portfolio": round(port_val / port_base * 100, 4)
                if port_val is not None and port_base else None,
                "spy": round(spy_val / spy_base * 100, 4)
                if spy_val is not None and spy_base else None,
            })

        return {"points": points}
    except Exception as exc:
        log.exception("benchmark failed")
        return {"error": str(exc), "points": []}


@router.get("/correlation")
def correlation():
    try:
        positions = alpaca_client.get_positions()
        tickers = [p["ticker"] for p in positions]

        if len(tickers) < 2:
            return {
                "tickers": [],
                "matrix": [],
                "empty_reason": "Need at least 2 positions for correlation",
            }

        returns_by_ticker: dict[str, list[float]] = {}
        with conn() as c, c.cursor() as cur:
            for ticker in tickers:
                cur.execute(
                    """
                    SELECT (close - lag(close) OVER (ORDER BY date)) / lag(close) OVER (ORDER BY date)
                    FROM (
                        SELECT date, close FROM ohlcv_daily
                        WHERE ticker = %s ORDER BY date DESC LIMIT 61
                    ) sub
                    ORDER BY date ASC
                    """,
                    (ticker,),
                )
                rows = cur.fetchall()
                vals = [float(r[0]) for r in rows if r[0] is not None]
                if vals:
                    returns_by_ticker[ticker] = vals[-60:]

        if len(returns_by_ticker) < 2:
            return {
                "tickers": [],
                "matrix": [],
                "empty_reason": "Insufficient price history in ohlcv_daily for correlation",
            }

        return correlation_matrix(returns_by_ticker)
    except Exception as exc:
        log.exception("correlation failed")
        return {"error": str(exc), "tickers": [], "matrix": []}


@router.get("/drawdown")
def drawdown():
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT date, total_value FROM portfolio_snapshots ORDER BY date ASC"
            )
            rows = cur.fetchall()

        if not rows:
            return {"points": []}

        dates = [r[0].isoformat() for r in rows]
        equity = [float(r[1]) for r in rows if r[1] is not None]

        if not equity:
            return {"points": []}

        dds = running_drawdown(equity)
        return {
            "points": [
                {"date": d, "drawdown": dd}
                for d, dd in zip(dates, dds)
            ]
        }
    except Exception as exc:
        log.exception("drawdown failed")
        return {"error": str(exc), "points": []}
