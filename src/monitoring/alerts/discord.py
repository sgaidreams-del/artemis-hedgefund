"""Discord posting for #hedgefund channel.

Uses the Discord bot REST API directly (no PyCord dependency for one-shot posts).
"""
from __future__ import annotations

import httpx

from ...core.config import env
from ...core.logging import get_logger, log_activity

log = get_logger("discord")

API = "https://discord.com/api/v10"


def post(content: str, *, channel_id: str | None = None) -> bool:
    """Post a message to the #hedgefund channel. Returns True on success."""
    token = env("DISCORD_ARTEMIS_TOKEN")
    cid = channel_id or env("DISCORD_HEDGEFUND_CHANNEL_ID")
    if not token or not cid:
        log.warning("discord_skipped", reason="missing token or channel id")
        log_activity("discord", "post", "skipped", reason="missing_credentials")
        return False
    try:
        r = httpx.post(
            f"{API}/channels/{cid}/messages",
            headers={"Authorization": f"Bot {token}"},
            json={"content": content[:1990]},  # Discord 2000 char limit
            timeout=15.0,
        )
        ok = r.status_code in (200, 201)
        if not ok:
            log.warning("discord_post_failed", status=r.status_code, body=r.text[:200])
        log_activity("discord", "post", "ok" if ok else "fail",
                     status=r.status_code, length=len(content))
        return ok
    except Exception as e:
        log.error("discord_post_exception", err=str(e))
        log_activity("discord", "post", "error", err=str(e))
        return False
