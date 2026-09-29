"""Weekly performance report. SPEC §11.4.

STATUS: STUB. Implement once daily report is validated.
"""
from __future__ import annotations

from ...core.logging import log_activity


def generate_and_post() -> dict:
    log_activity("weekly_report", "generate_and_post", "skipped", reason="not_implemented")
    return {"status": "stub"}
