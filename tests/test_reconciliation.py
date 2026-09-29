"""reconcile_options() — deliberately desync DB vs broker and confirm it's caught."""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


def _mock_db_conn(rows):
    class MockCursor:
        def execute(self, *a, **k): pass
        def fetchall(self): return rows
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class MockConn:
        def cursor(self): return MockCursor()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    @contextmanager
    def mock_conn():
        yield MockConn()
    return mock_conn


def _alpaca_position(symbol, qty):
    from alpaca.trading.enums import AssetClass
    p = MagicMock()
    p.symbol = symbol
    p.qty = qty
    p.asset_class = AssetClass.US_OPTION
    return p


def test_reconcile_options_clean_match_no_findings():
    db_rows = [("AAPL250117C00150000", 2)]
    mock_client = MagicMock()
    mock_client.get_all_positions.return_value = [_alpaca_position("AAPL250117C00150000", 2)]
    with patch("src.risk.reconciliation.conn", _mock_db_conn(db_rows)), \
         patch("src.execution.options._options_client", return_value=mock_client), \
         patch("src.core.logging.log_activity"):
        from src.risk.reconciliation import reconcile_options
        findings = reconcile_options()
    assert findings == []


def test_reconcile_options_orphaned_db_row():
    db_rows = [("AAPL250117C00150000", 2)]
    mock_client = MagicMock()
    mock_client.get_all_positions.return_value = []
    with patch("src.risk.reconciliation.conn", _mock_db_conn(db_rows)), \
         patch("src.execution.options._options_client", return_value=mock_client), \
         patch("src.core.logging.log_activity"), \
         patch("dashboard_api.routers.kill_switch.engage") as mock_engage:
        from src.risk.reconciliation import reconcile_options
        findings = reconcile_options()
    assert len(findings) == 1
    assert "orphaned_db" in findings[0]
    mock_engage.assert_not_called()  # existence mismatch, not a qty mismatch


def test_reconcile_options_untracked_alpaca_position():
    db_rows = []
    mock_client = MagicMock()
    mock_client.get_all_positions.return_value = [_alpaca_position("AAPL250117C00150000", 1)]
    with patch("src.risk.reconciliation.conn", _mock_db_conn(db_rows)), \
         patch("src.execution.options._options_client", return_value=mock_client), \
         patch("src.core.logging.log_activity"), \
         patch("dashboard_api.routers.kill_switch.engage") as mock_engage:
        from src.risk.reconciliation import reconcile_options
        findings = reconcile_options()
    assert len(findings) == 1
    assert "untracked_alpaca" in findings[0]
    mock_engage.assert_not_called()


def test_reconcile_options_qty_mismatch_engages_kill_switch():
    db_rows = [("AAPL250117C00150000", 5)]
    mock_client = MagicMock()
    mock_client.get_all_positions.return_value = [_alpaca_position("AAPL250117C00150000", 1)]
    with patch("src.risk.reconciliation.conn", _mock_db_conn(db_rows)), \
         patch("src.execution.options._options_client", return_value=mock_client), \
         patch("src.core.logging.log_activity"), \
         patch("dashboard_api.routers.kill_switch.engage") as mock_engage:
        from src.risk.reconciliation import reconcile_options
        findings = reconcile_options()
    assert len(findings) == 1
    assert "qty_mismatch" in findings[0]
    mock_engage.assert_called_once()
