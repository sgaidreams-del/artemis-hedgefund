"""News collector — RSS feeds with naïve ticker extraction. SPEC §4.1."""
from __future__ import annotations

import re
from datetime import datetime, timezone

import feedparser

from ...core.config import universe
from ...core.db import conn
from ...core.logging import get_logger, log_activity

log = get_logger("news_collector")

# Free, no-key RSS feeds
FEEDS = [
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
    ("CNBC Top News", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("MarketWatch Top", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("Seeking Alpha Editor's Picks", "https://seekingalpha.com/feed.xml"),
]

TICKER_RX = re.compile(r"\b([A-Z]{1,5})\b")


def _extract_tickers(text: str, known: set[str]) -> list[str]:
    """Cheap extractor — match all-caps tokens against the known universe set."""
    found = set()
    for m in TICKER_RX.findall(text):
        if m in known and len(m) >= 2:
            found.add(m)
    return sorted(found)


def collect() -> dict:
    known = set(universe()["seed_tickers"])  # will expand to full universe later
    inserted = 0
    skipped = 0
    sources_seen = 0
    with conn() as c, c.cursor() as cur:
        for source, url in FEEDS:
            try:
                parsed = feedparser.parse(url)
                sources_seen += 1
                for entry in parsed.entries[:50]:  # most-recent 50 per feed per pull
                    headline = (entry.get("title") or "").strip()
                    link = entry.get("link") or None
                    summary = (entry.get("summary") or "")
                    text = f"{headline} {summary}"
                    tickers = _extract_tickers(text, known)
                    if not headline or not link:
                        continue
                    ts = entry.get("published_parsed") or entry.get("updated_parsed")
                    if ts:
                        ts_dt = datetime(*ts[:6], tzinfo=timezone.utc)
                    else:
                        ts_dt = datetime.now(timezone.utc)
                    try:
                        cur.execute(
                            """
                            INSERT INTO news_headlines (timestamp, source, headline, url, tickers)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (url) DO NOTHING
                            RETURNING id
                            """,
                            (ts_dt, source, headline, link, tickers),
                        )
                        if cur.fetchone():
                            inserted += 1
                        else:
                            skipped += 1
                    except Exception as e:
                        log.warning("insert_failed", source=source, err=str(e))
                        skipped += 1
            except Exception as e:
                log.warning("feed_failed", source=source, err=str(e))
        c.commit()
    log_activity("news_collector", "collect", "ok",
                 sources=sources_seen, inserted=inserted, skipped=skipped)
    return {"sources": sources_seen, "inserted": inserted, "skipped": skipped}
