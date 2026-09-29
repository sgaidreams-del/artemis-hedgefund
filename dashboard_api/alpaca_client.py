"""Thin Alpaca wrapper for the dashboard. Returns None/empty gracefully when
ALPACA_API_KEY isn't set yet, instead of raising — the dashboard should render
a "connect your broker" state, not crash.
"""
from __future__ import annotations

from functools import lru_cache

from alpaca.trading.client import TradingClient

from src.core.config import env


def configured() -> bool:
    return bool(env("ALPACA_API_KEY") and env("ALPACA_API_SECRET"))


@lru_cache(maxsize=1)
def _client() -> TradingClient | None:
    if not configured():
        return None
    return TradingClient(
        api_key=env("ALPACA_API_KEY"),
        secret_key=env("ALPACA_API_SECRET"),
        paper=True,
    )


def get_account() -> dict | None:
    client = _client()
    if client is None:
        return None
    a = client.get_account()
    return {
        "equity": float(a.equity),
        "cash": float(a.cash),
        "buying_power": float(a.buying_power),
        "last_equity": float(a.last_equity),
        "day_pl": float(a.equity) - float(a.last_equity),
        "day_pl_pct": (float(a.equity) - float(a.last_equity)) / float(a.last_equity)
        if float(a.last_equity) else 0.0,
        "status": str(a.status),
        "pattern_day_trader": a.pattern_day_trader,
    }


def get_positions() -> list[dict]:
    client = _client()
    if client is None:
        return []
    positions = client.get_all_positions()
    return [
        {
            "ticker": p.symbol,
            "qty": float(p.qty),
            "avg_entry_price": float(p.avg_entry_price),
            "current_price": float(p.current_price),
            "market_value": float(p.market_value),
            "unrealized_pl": float(p.unrealized_pl),
            "unrealized_plpc": float(p.unrealized_plpc),
            "side": str(p.side),
        }
        for p in positions
    ]


def get_clock() -> dict | None:
    client = _client()
    if client is None:
        return None
    c = client.get_clock()
    return {
        "is_open": c.is_open,
        "next_open": c.next_open.isoformat(),
        "next_close": c.next_close.isoformat(),
        "timestamp": c.timestamp.isoformat(),
    }


def ping() -> dict:
    """Connection-monitor check: latency + status, never raises."""
    import time

    if not configured():
        return {"connected": False, "reason": "ALPACA_API_KEY not set", "latency_ms": None}
    start = time.monotonic()
    try:
        client = _client()
        client.get_account()
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"connected": True, "reason": None, "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"connected": False, "reason": str(e), "latency_ms": latency_ms}


def get_portfolio_history(period: str = "1M", timeframe: str = "1D") -> list[dict]:
    """Real equity curve from Alpaca's own ledger — available even with zero trades."""
    client = _client()
    if client is None:
        return []
    import httpx

    base = env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    try:
        r = httpx.get(
            f"{base}/v2/account/portfolio/history",
            headers={
                "APCA-API-KEY-ID": env("ALPACA_API_KEY"),
                "APCA-API-SECRET-KEY": env("ALPACA_API_SECRET"),
            },
            params={"period": period, "timeframe": timeframe},
            timeout=10.0,
        )
        r.raise_for_status()
        data = r.json()
        timestamps = data.get("timestamp", [])
        equity = data.get("equity", [])
        return [
            {"timestamp": ts, "equity": eq}
            for ts, eq in zip(timestamps, equity)
            if eq is not None
        ]
    except Exception:
        return []
