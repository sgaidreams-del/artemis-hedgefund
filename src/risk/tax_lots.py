"""Tax lot tracking using features_daily as a persistent store."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime

from src.core.db import conn
from src.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class TaxLot:
    ticker: str
    qty: int
    cost_basis: float  # per-share price
    acquired_date: date


def add_lot(ticker: str, qty: int, price: float, acquired_date: date) -> None:
    """Insert a TaxLot into features_daily as feature_name='taxlot_{idx}'.

    Acquired_date is serialized as an ISO format string.
    Cost_basis is stored as the actual price (float).
    """
    existing = get_lots(ticker)
    idx = len(existing)  # next sequential index

    lot = TaxLot(ticker=ticker, qty=qty, cost_basis=price, acquired_date=acquired_date)
    lot_dict = asdict(lot)
    # Serialize date to isoformat string
    lot_dict["acquired_date"] = acquired_date.isoformat()

    feature_name = f"taxlot_{idx}"
    feature_value = json.dumps(lot_dict)

    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO features_daily (ticker, date, feature_name, feature_value)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (ticker, date, feature_name) DO UPDATE
                SET feature_value = EXCLUDED.feature_value
            """,
            (ticker, date.today().isoformat(), feature_name, feature_value),
        )

    log.info("add_lot", ticker=ticker, qty=qty, price=price, acquired_date=acquired_date.isoformat(), idx=idx)


def get_lots(ticker: str) -> list[TaxLot]:
    """Read all taxlot_ features for ticker from features_daily.

    Returns list of TaxLot sorted by acquired_date (oldest first).
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT feature_name, feature_value
            FROM features_daily
            WHERE ticker = %s AND feature_name LIKE 'taxlot_%'
            ORDER BY feature_name ASC
            """,
            (ticker,),
        )
        rows = cur.fetchall()

    lots = []
    for _name, value in rows:
        try:
            d = json.loads(value)
            acquired = date.fromisoformat(d["acquired_date"]) if isinstance(d["acquired_date"], str) else d["acquired_date"]
            lots.append(
                TaxLot(
                    ticker=d["ticker"],
                    qty=int(d["qty"]),
                    cost_basis=float(d["cost_basis"]),
                    acquired_date=acquired,
                )
            )
        except Exception as exc:
            log.warning("get_lots: failed to parse lot", error=str(exc), value=value)

    # Sort by acquired_date for FIFO
    lots.sort(key=lambda lot: lot.acquired_date)
    return lots


def compute_gain(ticker: str, sale_price: float, qty: int) -> dict:
    """FIFO gain computation across tax lots.

    Returns {short_term_gain, long_term_gain, remaining_qty}.
    Short-term: held <= 1 year; Long-term: held > 1 year.
    """
    lots = get_lots(ticker)
    today = date.today()

    short_term_gain = 0.0
    long_term_gain = 0.0
    remaining = qty

    for lot in lots:
        if remaining <= 0:
            break

        consume = min(lot.qty, remaining)
        gain_per_share = sale_price - lot.cost_basis
        total_gain = gain_per_share * consume

        # Determine short vs long term (>1 year = long)
        held_days = (today - lot.acquired_date).days
        if held_days > 365:
            long_term_gain += total_gain
        else:
            short_term_gain += total_gain

        remaining -= consume

    return {
        "short_term_gain": short_term_gain,
        "long_term_gain": long_term_gain,
        "remaining_qty": remaining,
    }
