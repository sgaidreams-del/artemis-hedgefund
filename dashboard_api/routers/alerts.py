"""Price-alert CRUD + check runner — SPEC §11.1 Alerts panel."""
from __future__ import annotations

import logging
import subprocess
from typing import Literal, Optional

import yfinance as yf
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.db import conn
from .. import alpaca_client

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
log = logging.getLogger(__name__)


def _row_to_dict(r) -> dict:
    return {
        "id": r[0],
        "ticker": r[1],
        "threshold": float(r[2]),
        "direction": r[3],
        "triggered_at": r[4].isoformat() if r[4] else None,
        "created_at": r[5].isoformat() if r[5] else None,
    }


@router.get("")
def list_alerts():
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT id, ticker, threshold, direction, triggered_at, created_at "
                "FROM price_alerts ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
        return {"alerts": [_row_to_dict(r) for r in rows]}
    except Exception as exc:
        log.exception("list_alerts failed")
        return {"error": str(exc), "alerts": []}


class AlertBody(BaseModel):
    ticker: str
    threshold: float
    direction: Literal["above", "below"]


@router.post("")
def create_alert(body: AlertBody):
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO price_alerts (ticker, threshold, direction) "
                "VALUES (%s, %s, %s) "
                "RETURNING id, ticker, threshold, direction, triggered_at, created_at",
                (body.ticker.upper(), body.threshold, body.direction),
            )
            row = cur.fetchone()
        return _row_to_dict(row)
    except Exception as exc:
        log.exception("create_alert failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{alert_id}")
def delete_alert(alert_id: int):
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute("DELETE FROM price_alerts WHERE id = %s", (alert_id,))
        return {"deleted": True}
    except Exception as exc:
        log.exception("delete_alert failed")
        raise HTTPException(status_code=500, detail=str(exc))


def _get_current_prices(tickers: list[str]) -> dict[str, float]:
    """Build ticker→price map from Alpaca positions first, then yfinance for the rest."""
    prices: dict[str, float] = {}
    held = {p["ticker"]: p["current_price"] for p in alpaca_client.get_positions()}
    for t in tickers:
        if t in held:
            prices[t] = held[t]

    missing = [t for t in tickers if t not in prices]
    if missing:
        try:
            data = yf.download(
                missing, period="1d", auto_adjust=True, progress=False
            )
            close = data["Close"] if len(missing) > 1 else data["Close"]
            last = close.iloc[-1]
            if len(missing) == 1:
                prices[missing[0]] = float(last)
            else:
                for t in missing:
                    if t in last.index and not __import__("math").isnan(last[t]):
                        prices[t] = float(last[t])
        except Exception:
            pass
    return prices


def _fire_notification(ticker: str, threshold: float, direction: str, price: float):
    msg = f"{ticker} is {direction} {threshold:.2f} — current: {price:.2f}"
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{msg}" with title "Artemis Alert"'],
            timeout=5,
            check=False,
        )
    except Exception:
        log.info("osascript unavailable; alert would have been: %s", msg)


@router.post("/check")
def check_alerts():
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT id, ticker, threshold, direction "
                "FROM price_alerts WHERE triggered_at IS NULL"
            )
            pending = cur.fetchall()

        if not pending:
            return {"checked": 0, "triggered": []}

        tickers = list({r[1] for r in pending})
        prices = _get_current_prices(tickers)

        triggered = []
        with conn() as c, c.cursor() as cur:
            for alert_id, ticker, threshold, direction in pending:
                price = prices.get(ticker)
                if price is None:
                    continue
                fired = (direction == "above" and price > threshold) or (
                    direction == "below" and price < threshold
                )
                if fired:
                    cur.execute(
                        "UPDATE price_alerts SET triggered_at = NOW() WHERE id = %s",
                        (alert_id,),
                    )
                    _fire_notification(ticker, threshold, direction, price)
                    triggered.append({
                        "ticker": ticker,
                        "threshold": threshold,
                        "direction": direction,
                        "current_price": price,
                    })

        return {"checked": len(pending), "triggered": triggered}
    except Exception as exc:
        log.exception("check_alerts failed")
        return {"error": str(exc), "checked": 0, "triggered": []}
