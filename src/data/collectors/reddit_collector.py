"""Reddit collector — PRAW. SPEC §4.1.

STATUS: STUB. Implement when Reddit credentials are provided in .env.
"""
from __future__ import annotations

from ...core.logging import get_logger, log_activity

log = get_logger("reddit_collector")


def collect() -> dict:
    log.info("not_implemented", reason="awaiting REDDIT_* env vars")
    log_activity("reddit_collector", "collect", "skipped", reason="not_implemented")
    return {"status": "stub", "inserted": 0}

# TODO when implementing:
# - praw.Reddit(...)
# - subreddits: wallstreetbets, stocks, investing, options
# - last 15min of submissions + top comments
# - extract tickers (same regex as news_collector)
# - upsert into social_posts on (source, post_id)
