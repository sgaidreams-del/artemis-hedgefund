"""engage() must both flip the paused flag and cancel resting orders — the
kill switch should stop the bleeding, not just block new submissions."""
from contextlib import contextmanager
from unittest.mock import patch, MagicMock


def _mock_conn():
    class MockCursor:
        def execute(self, *a, **k): pass
        def fetchone(self): return None
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class MockConn:
        def cursor(self): return MockCursor()
        def commit(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

    @contextmanager
    def mock_conn():
        yield MockConn()
    return mock_conn


def test_engage_cancels_resting_orders():
    with patch("dashboard_api.routers.kill_switch.conn", _mock_conn()), \
         patch("src.execution.broker.cancel_all_orders", return_value=3) as mock_cancel:
        from dashboard_api.routers.kill_switch import engage
        engage("test breach")
    mock_cancel.assert_called_once()


def test_engage_cancels_even_if_db_update_fails():
    @contextmanager
    def broken_conn():
        raise Exception("DB is down")
        yield  # unreachable

    with patch("dashboard_api.routers.kill_switch.conn", broken_conn), \
         patch("src.execution.broker.cancel_all_orders", return_value=0) as mock_cancel:
        from dashboard_api.routers.kill_switch import engage
        engage("test breach")  # must not raise
    mock_cancel.assert_called_once()


def test_pause_endpoint_calls_engage():
    with patch("dashboard_api.routers.kill_switch.engage") as mock_engage, \
         patch("dashboard_api.routers.kill_switch._read_row", return_value={"paused": True}):
        from dashboard_api.routers.kill_switch import pause, PauseBody
        pause(PauseBody(reason="manual"))
    mock_engage.assert_called_once_with("manual")
