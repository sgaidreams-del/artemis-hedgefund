"""Tests for the kill-switch API and the is_paused() guard."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def _make_mock_conn(paused: bool):
    """Return a mock conn() context manager that returns paused state.

    The is_paused() query is `SELECT paused FROM kill_switch WHERE id=1`
    so fetchone() returns a 1-element tuple: (paused_bool,).
    """
    # is_paused() calls execute() twice (INSERT, SELECT) but fetchone() only once.
    class MockCursor:
        def execute(self, *a, **k): pass
        def fetchone(self): return (paused,)
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class MockConn:
        def cursor(self): return MockCursor()
        def commit(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

    from contextlib import contextmanager
    @contextmanager
    def mock_conn():
        yield MockConn()
    return mock_conn


def test_is_paused_returns_false_when_not_paused():
    mock_conn = _make_mock_conn(paused=False)
    with patch("dashboard_api.routers.kill_switch.conn", mock_conn):
        from dashboard_api.routers.kill_switch import is_paused
        assert is_paused() is False


def test_is_paused_returns_true_when_paused():
    mock_conn = _make_mock_conn(paused=True)
    with patch("dashboard_api.routers.kill_switch.conn", mock_conn):
        from dashboard_api.routers.kill_switch import is_paused
        assert is_paused() is True


def test_is_paused_defaults_false_on_db_error():
    from contextlib import contextmanager
    @contextmanager
    def broken_conn():
        raise Exception("DB is down")
        yield  # unreachable

    with patch("dashboard_api.routers.kill_switch.conn", broken_conn):
        from dashboard_api.routers.kill_switch import is_paused
        # Should return False, not raise, so trading continues during outage
        assert is_paused() is False
