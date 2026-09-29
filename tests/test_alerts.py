"""Tests for price alert comparison logic (direction + threshold)."""
import pytest


def _should_trigger(current_price: float, threshold: float, direction: str) -> bool:
    """Replicate the trigger check from dashboard_api/routers/alerts.py."""
    if direction == "above":
        return current_price >= threshold
    if direction == "below":
        return current_price <= threshold
    return False


def test_above_triggered():
    assert _should_trigger(155.0, 150.0, "above") is True


def test_above_not_triggered():
    assert _should_trigger(145.0, 150.0, "above") is False


def test_below_triggered():
    assert _should_trigger(145.0, 150.0, "below") is True


def test_below_not_triggered():
    assert _should_trigger(155.0, 150.0, "below") is False


def test_above_at_threshold():
    # At exactly the threshold → should trigger (≥)
    assert _should_trigger(150.0, 150.0, "above") is True


def test_below_at_threshold():
    # At exactly the threshold → should trigger (≤)
    assert _should_trigger(150.0, 150.0, "below") is True


def test_invalid_direction():
    assert _should_trigger(100.0, 90.0, "sideways") is False


@pytest.mark.parametrize("price,threshold,direction,expected", [
    (200.0, 190.0, "above", True),
    (180.0, 190.0, "above", False),
    (80.0,  90.0,  "below", True),
    (100.0, 90.0,  "below", False),
    (0.01,  0.01,  "above", True),
    (0.01,  0.01,  "below", True),
])
def test_parametrized(price, threshold, direction, expected):
    assert _should_trigger(price, threshold, direction) == expected
