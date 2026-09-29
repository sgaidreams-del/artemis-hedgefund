"""Shared pytest fixtures."""
import src.core.logging as logging_mod


def pytest_configure(config):
    """Redirect activity logging to a throwaway file for the whole test session.

    Without this, log_activity() calls triggered by code under test (daily_trader,
    regime.detector, etc.) append to the SAME logs/activity.jsonl the dashboard's
    activity feed reads, making test runs look like real trading activity.
    """
    import tempfile
    from pathlib import Path

    tmp_dir = Path(tempfile.mkdtemp(prefix="artemis_test_logs_"))
    logging_mod.ACTIVITY_LOG = tmp_dir / "activity.jsonl"
