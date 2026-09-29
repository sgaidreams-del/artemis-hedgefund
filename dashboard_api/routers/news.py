"""News feed — SPEC §11.1 News / Sentiment panel."""
from __future__ import annotations

import datetime
import logging

import yfinance as yf
from fastapi import APIRouter

from src.core.db import conn
from .. import alpaca_client

router = APIRouter(prefix="/api/news", tags=["news"])
log = logging.getLogger(__name__)

_SEED_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "JPM", "XOM", "UNH", "SPY", "QQQ",
]


@router.get("")
def list_news(limit: int = 20):
    try:
        positions = alpaca_client.get_positions()
        tickers = [p["ticker"] for p in positions] or _SEED_UNIVERSE

        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT id, timestamp, source, headline, url, tickers, "
                "sentiment_score, sentiment_label "
                "FROM news_headlines "
                "WHERE tickers && %s::text[] "
                "ORDER BY timestamp DESC LIMIT %s",
                (tickers, limit),
            )
            rows = cur.fetchall()

        if rows:
            return {
                "articles": [
                    {
                        "id": r[0],
                        "timestamp": r[1].isoformat() if r[1] else None,
                        "source": r[2],
                        "headline": r[3],
                        "url": r[4],
                        "tickers": r[5],
                        "sentiment_score": float(r[6]) if r[6] is not None else None,
                        "sentiment_label": r[7],
                    }
                    for r in rows
                ],
                "source": "db",
                "empty_reason": None,
            }

        # yfinance fallback
        articles = []
        seen: set[str] = set()
        for ticker in tickers[:12]:
            try:
                items = yf.Ticker(ticker).get_news()[:3]
                for item in items:
                    title = item.get("title") or item.get("content", {}).get("title", "")
                    if not title or title in seen:
                        continue
                    seen.add(title)
                    content = item.get("content", {})
                    pub_time = item.get("providerPublishTime") or content.get("pubDate")
                    ts_str: str | None = None
                    if isinstance(pub_time, (int, float)):
                        ts_str = datetime.datetime.utcfromtimestamp(pub_time).isoformat()
                    elif isinstance(pub_time, str):
                        ts_str = pub_time

                    publisher = (
                        item.get("publisher")
                        or content.get("provider", {}).get("displayName")
                        or "yfinance"
                    )
                    link = (
                        item.get("link")
                        or content.get("canonicalUrl", {}).get("url")
                    )
                    articles.append({
                        "id": None,
                        "timestamp": ts_str,
                        "source": publisher,
                        "headline": title,
                        "url": link,
                        "tickers": [ticker],
                        "sentiment_score": None,
                        "sentiment_label": None,
                    })
            except Exception:
                pass

        articles = articles[:limit]
        return {
            "articles": articles,
            "source": "yfinance_fallback" if articles else "none",
            "empty_reason": None if articles else "No news available from DB or yfinance.",
        }
    except Exception as exc:
        log.exception("list_news failed")
        return {"error": str(exc), "articles": [], "source": "none", "empty_reason": str(exc)}
