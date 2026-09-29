"""Pure calculation utilities — no FastAPI, no DB. All functions accept plain Python
lists and return floats or structured dicts.
"""
from __future__ import annotations

import math

import numpy as np


def sharpe_ratio(
    daily_returns: list[float], risk_free_daily: float = 0.0
) -> float | None:
    if len(daily_returns) < 30:
        return None
    excess = [r - risk_free_daily for r in daily_returns]
    mu = sum(excess) / len(excess)
    variance = sum((x - mu) ** 2 for x in excess) / (len(excess) - 1)
    std = math.sqrt(variance)
    if std == 0.0:
        return None
    return (mu / std) * math.sqrt(252)


def sortino_ratio(
    daily_returns: list[float], risk_free_daily: float = 0.0
) -> float | None:
    if len(daily_returns) < 30:
        return None
    excess = [r - risk_free_daily for r in daily_returns]
    mu = sum(excess) / len(excess)
    negatives = [x for x in excess if x < 0]
    if not negatives:
        return None
    downside_variance = sum(x ** 2 for x in negatives) / len(negatives)
    downside_std = math.sqrt(downside_variance)
    if downside_std == 0.0:
        return None
    return (mu / downside_std) * math.sqrt(252)


def max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    worst = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak
            if dd < worst:
                worst = dd
    return worst


def running_drawdown(equity_curve: list[float]) -> list[float]:
    if not equity_curve:
        return []
    result: list[float] = []
    peak = equity_curve[0]
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak > 0 else 0.0
        result.append(dd)
    return result


def win_rate(pnls: list[float]) -> float | None:
    if not pnls:
        return None
    wins = sum(1 for p in pnls if p > 0)
    return wins / len(pnls)


def profit_factor(pnls: list[float]) -> float | None:
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    if gross_loss == 0.0:
        return None
    return gross_win / gross_loss


def correlation_matrix(returns_by_ticker: dict[str, list[float]]) -> dict:
    tickers = list(returns_by_ticker.keys())
    if len(tickers) < 2:
        return {"tickers": [], "matrix": []}
    min_len = min(len(v) for v in returns_by_ticker.values())
    if min_len < 2:
        return {"tickers": [], "matrix": []}
    arr = np.array([returns_by_ticker[t][:min_len] for t in tickers], dtype=float)
    matrix = np.corrcoef(arr)
    # Replace NaN (constant series) with 0.0 to keep JSON serialisable
    matrix = np.nan_to_num(matrix, nan=0.0)
    return {
        "tickers": tickers,
        "matrix": matrix.tolist(),
    }
