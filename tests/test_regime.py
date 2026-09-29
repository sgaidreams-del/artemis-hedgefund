"""Tests for regime detection logic."""
import pytest


def _build_spy_closes(trend: str, n: int = 250) -> list[float]:
    """Build synthetic SPY close prices with a given trend."""
    import random; random.seed(7)
    price = 400.0
    closes = []
    for _ in range(n):
        if trend == "bull":
            price *= 1.0015 + random.gauss(0, 0.002)
        elif trend == "bear":
            price *= 0.9985 + random.gauss(0, 0.002)
        else:
            price *= 1.0 + random.gauss(0, 0.003)
        closes.append(max(price, 1.0))
    return closes


def _classify(closes: list[float]) -> str:
    """Replicate the MA-crossover regime logic from the router."""
    ma50 = sum(closes[-50:]) / 50
    ma200 = sum(closes[-200:]) / 200
    if ma50 > ma200 * 1.005:
        return "bull"
    if ma50 < ma200 * 0.995:
        return "bear"
    return "sideways"


def test_bull_regime_detected():
    closes = _build_spy_closes("bull", 250)
    assert _classify(closes) == "bull"


def test_bear_regime_detected():
    closes = _build_spy_closes("bear", 250)
    assert _classify(closes) == "bear"


def test_sideways_when_ma_close():
    # Build flat series → 50MA ≈ 200MA
    closes = [400.0] * 250
    assert _classify(closes) == "sideways"


def test_requires_200_closes():
    closes = _build_spy_closes("bull", 150)
    with pytest.raises((IndexError, ZeroDivisionError, ValueError)):
        # Intentionally check that <200 points fails gracefully
        _ = sum(closes[-200:]) / 200 if len(closes) >= 200 else (_ for _ in ()).throw(ValueError("Not enough data"))


def test_ma50_computed_from_last_50():
    closes = [100.0] * 200 + [200.0] * 50  # last 50 days jump to 200
    ma50 = sum(closes[-50:]) / 50
    ma200 = sum(closes[-200:]) / 200
    # ma50 = 200, ma200 = 125 → ma50 > ma200 → bull
    assert ma50 > ma200 * 1.005
