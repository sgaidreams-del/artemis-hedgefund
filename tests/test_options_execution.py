"""submit_option_order — Phase 5 Greeks/concentration gates, on top of the
Phase 1 pre-trade gate already covered in test_pretrade.py."""
from unittest.mock import MagicMock, patch

from src.risk.pretrade import PreTradeDecision

_GATE_ALLOW = PreTradeDecision(allow=True, reason="ok")
_SYMBOL = "AAPL  250117C00150000"


def _patched(**overrides):
    defaults = dict(
        _options_client=MagicMock(),
        check_option_order=_GATE_ALLOW,
        get_account={"equity": 100_000.0},
        get_options_positions=[],
        check_greeks_limits=False,
        check_underlying_concentration=False,
    )
    defaults.update(overrides)
    return defaults


def _run_submit(**overrides):
    from src.execution import options as options_mod
    p = _patched(**overrides)
    with patch.object(options_mod, "_options_client", return_value=p["_options_client"]), \
         patch("src.risk.pretrade.check_option_order", return_value=p["check_option_order"]), \
         patch("src.execution.broker.get_account", return_value=p["get_account"]), \
         patch.object(options_mod, "get_options_positions", return_value=p["get_options_positions"]), \
         patch("src.risk.limits.check_greeks_limits", return_value=p["check_greeks_limits"]), \
         patch("src.risk.limits.check_underlying_concentration", return_value=p["check_underlying_concentration"]):
        return options_mod.submit_option_order(_SYMBOL, 1, "buy", 5.0)


def test_submit_rejected_on_greeks_breach():
    result = _run_submit(check_greeks_limits=True)
    assert result is None


def test_submit_rejected_on_underlying_concentration_breach():
    result = _run_submit(check_underlying_concentration=True)
    assert result is None


def test_submit_proceeds_when_both_within_caps():
    from src.execution import options as options_mod
    p = _patched()
    mock_order = MagicMock()
    mock_order.model_dump.return_value = {"id": "abc", "status": "accepted"}
    p["_options_client"].submit_order.return_value = mock_order

    with patch.object(options_mod, "_options_client", return_value=p["_options_client"]), \
         patch("src.risk.pretrade.check_option_order", return_value=p["check_option_order"]), \
         patch("src.execution.broker.get_account", return_value=p["get_account"]), \
         patch.object(options_mod, "get_options_positions", return_value=p["get_options_positions"]), \
         patch("src.risk.limits.check_greeks_limits", return_value=False), \
         patch("src.risk.limits.check_underlying_concentration", return_value=False), \
         patch.object(options_mod, "conn") as mock_conn:
        mock_cursor = MagicMock()
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        result = options_mod.submit_option_order(_SYMBOL, 1, "buy", 5.0)

    assert result is not None
    p["_options_client"].submit_order.assert_called_once()
