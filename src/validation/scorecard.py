"""Validation scorecard — runs all 8 overfitting-detection gates."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from src.core.logging import get_logger
from src.validation.backtest.engine import run_backtest
from src.validation.backtest.metrics import compute_metrics
from src.validation.baseline import buy_and_hold_returns
from src.validation.event_study.car import compute_car
from src.validation.event_study.significance import t_test_car
from src.validation.overfitting.cpcv import run_cpcv
from src.validation.overfitting.deflated_sharpe import deflated_sharpe_ratio
from src.validation.overfitting.param_stability import stability_score
from src.validation.overfitting.pbo import prob_backtest_overfitting
from src.validation.overfitting.regime_robustness import regime_sharpes
from src.validation.overfitting.spa_test import spa_test
from src.validation.walk_forward import WalkForwardRunner

log = get_logger(__name__)

GATES = [
    "event_study",
    "backtest",
    "cpcv",
    "deflated_sharpe",
    "pbo",
    "spa",
    "param_stability",
    "regime_robustness",
]

# Gate thresholds
_THRESHOLDS = {
    "backtest_sharpe": 0.5,       # minimum acceptable Sharpe
    "backtest_max_dd": -0.25,     # max drawdown floor
    "cpcv_win_rate": 0.5,         # OOS win rate >= 50%
    "cpcv_sharpe": 0.0,           # OOS Sharpe > 0
    "dsr": 0.5,                   # DSR > 0.5 (likely real edge)
    "pbo": 0.5,                   # PBO < 0.5
    "spa_p": 0.10,                # SPA p-value < 0.10 (significant at 10%)
    "param_stability": 0.30,      # at least 30% of grid near peak
    "min_regime_sharpe": -0.5,    # no regime Sharpe below -0.5
}


def run_full_validation(
    strategy_fn: Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame] | None,
    signals_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    *,
    n_trials: int = 100,
    event_date: str | None = None,
    regime_labels: pd.Series | None = None,
    sharpe_grid: np.ndarray | None = None,
    benchmark_ticker: str = "SPY",
) -> dict:
    """Run all 8 validation gates and return a structured scorecard.

    Parameters
    ----------
    strategy_fn:
        Optional callable for walk-forward; if None, signals_df is used as-is.
    signals_df:
        Strategy signals (weights / directions) DataFrame.
    prices_df:
        Adjusted close prices DataFrame.
    n_trials:
        Number of parameter combinations tested (for DSR).
    event_date:
        Date string for event study (e.g. '2024-01-15'). If None, uses the
        midpoint of the available data.
    regime_labels:
        Optional regime labels Series aligned with prices index.
    sharpe_grid:
        Optional N-D array of Sharpe ratios over parameter grid (for stability).
    benchmark_ticker:
        Ticker in prices_df used as benchmark for SPA test.

    Returns
    -------
    dict with keys:
        passed (bool): True iff ALL gates passed.
        gates (dict): {gate_name: {passed, metric, value}}
    """
    gates: dict[str, dict] = {}

    # --- Gate 1: Event study ---
    try:
        common_tickers = signals_df.columns.intersection(prices_df.columns)
        first_ticker = common_tickers[0] if len(common_tickers) > 0 else prices_df.columns[0]
        stock_ret = prices_df[first_ticker].pct_change().dropna()

        bench_col = benchmark_ticker if benchmark_ticker in prices_df.columns else prices_df.columns[0]
        market_ret = prices_df[bench_col].pct_change().dropna()

        if event_date is None:
            mid_idx = len(stock_ret) // 2
            event_date_used = str(stock_ret.index[mid_idx].date())
        else:
            event_date_used = event_date

        car_result = compute_car(stock_ret, market_ret, event_date=event_date_used)
        t_result = t_test_car(
            car_result["car"],
            car_result["model_params"]["residual_std"],
            n_days=len(car_result["aar_series"]),
        )
        # Gate passes if CAR is significant OR if strategy has positive expected alpha
        gate_passed = t_result["significant"] or car_result["model_params"]["alpha"] > 0
        gates["event_study"] = {
            "passed": gate_passed,
            "metric": "car_significant",
            "value": t_result["p_value"],
            "car": car_result["car"],
            "t_stat": t_result["t_stat"],
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("scorecard.event_study_failed", error=str(exc))
        gates["event_study"] = {"passed": False, "metric": "error", "value": str(exc)}

    # --- Gate 2: Backtest ---
    try:
        bt = run_backtest(signals_df, prices_df)
        metrics = bt["metrics"]
        sharpe = metrics["sharpe"]
        max_dd = metrics["max_drawdown"]
        bt_passed = sharpe >= _THRESHOLDS["backtest_sharpe"] and max_dd >= _THRESHOLDS["backtest_max_dd"]
        gates["backtest"] = {
            "passed": bt_passed,
            "metric": "sharpe",
            "value": sharpe,
            "max_drawdown": max_dd,
            "all_metrics": metrics,
        }
        # Save equity curve and sharpe for downstream gates
        _equity_curve = bt["equity_curve"]
        _backtest_sharpe = sharpe
    except Exception as exc:  # noqa: BLE001
        log.warning("scorecard.backtest_failed", error=str(exc))
        gates["backtest"] = {"passed": False, "metric": "error", "value": str(exc)}
        _equity_curve = None
        _backtest_sharpe = 0.0

    # --- Gate 3: CPCV ---
    try:
        cpcv = run_cpcv(signals_df, prices_df)
        cpcv_passed = (
            cpcv["win_rate_oos"] >= _THRESHOLDS["cpcv_win_rate"]
            and cpcv["avg_sharpe_oos"] >= _THRESHOLDS["cpcv_sharpe"]
        )
        gates["cpcv"] = {
            "passed": cpcv_passed,
            "metric": "win_rate_oos",
            "value": cpcv["win_rate_oos"],
            "avg_sharpe_oos": cpcv["avg_sharpe_oos"],
            "n_paths": cpcv["n_paths"],
        }
        _cpcv_paths = cpcv.get("paths", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("scorecard.cpcv_failed", error=str(exc))
        gates["cpcv"] = {"passed": False, "metric": "error", "value": str(exc)}
        _cpcv_paths = []

    # --- Gate 4: Deflated Sharpe ---
    try:
        n_obs = len(signals_df)
        dsr = deflated_sharpe_ratio(_backtest_sharpe, n_trials=n_trials, n_obs=n_obs)
        dsr_passed = dsr >= _THRESHOLDS["dsr"]
        gates["deflated_sharpe"] = {
            "passed": dsr_passed,
            "metric": "dsr",
            "value": dsr,
            "raw_sharpe": _backtest_sharpe,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("scorecard.dsr_failed", error=str(exc))
        gates["deflated_sharpe"] = {"passed": False, "metric": "error", "value": str(exc)}

    # --- Gate 5: PBO ---
    try:
        if _cpcv_paths:
            is_sharpes = [p.get("is_sharpe", 0.0) for p in _cpcv_paths]
            oos_sharpes = [p.get("oos_sharpe", 0.0) for p in _cpcv_paths]
            pbo = prob_backtest_overfitting(is_sharpes, oos_sharpes)
            pbo_passed = pbo < _THRESHOLDS["pbo"]
            gates["pbo"] = {"passed": pbo_passed, "metric": "pbo", "value": pbo}
        else:
            gates["pbo"] = {"passed": False, "metric": "pbo", "value": 1.0, "note": "no cpcv paths"}
    except Exception as exc:  # noqa: BLE001
        log.warning("scorecard.pbo_failed", error=str(exc))
        gates["pbo"] = {"passed": False, "metric": "error", "value": str(exc)}

    # --- Gate 6: SPA test ---
    try:
        if _equity_curve is not None:
            bench_returns = buy_and_hold_returns(prices_df, ticker=benchmark_ticker)
            strat_daily = _equity_curve.pct_change().dropna()
            common_idx = strat_daily.index.intersection(bench_returns.index)
            strat_arr = strat_daily.loc[common_idx].values
            bench_arr = bench_returns.loc[common_idx].values
            spa_p = spa_test(strat_arr, bench_arr)
            spa_passed = spa_p < _THRESHOLDS["spa_p"]
            gates["spa"] = {"passed": spa_passed, "metric": "spa_p_value", "value": spa_p}
        else:
            gates["spa"] = {"passed": False, "metric": "spa_p_value", "value": 1.0, "note": "no equity curve"}
    except Exception as exc:  # noqa: BLE001
        log.warning("scorecard.spa_failed", error=str(exc))
        gates["spa"] = {"passed": False, "metric": "error", "value": str(exc)}

    # --- Gate 7: Parameter stability ---
    try:
        if sharpe_grid is not None:
            score = stability_score(sharpe_grid)
        else:
            # Approximate: use CPCV OOS Sharpes as a 1-D pseudo-grid
            if _cpcv_paths:
                pseudo_grid = np.array([p.get("oos_sharpe", 0.0) for p in _cpcv_paths])
            else:
                pseudo_grid = np.array([_backtest_sharpe])
            score = stability_score(pseudo_grid)
        stab_passed = score >= _THRESHOLDS["param_stability"]
        gates["param_stability"] = {"passed": stab_passed, "metric": "stability_score", "value": score}
    except Exception as exc:  # noqa: BLE001
        log.warning("scorecard.stability_failed", error=str(exc))
        gates["param_stability"] = {"passed": False, "metric": "error", "value": str(exc)}

    # --- Gate 8: Regime robustness ---
    try:
        if _equity_curve is not None:
            if regime_labels is not None:
                labels = regime_labels
            else:
                # Synthetic regimes: split into thirds (bull/sideways/bear by return)
                eq = _equity_curve.dropna()
                daily_ret = eq.pct_change().dropna()
                q33, q67 = daily_ret.quantile(0.33), daily_ret.quantile(0.67)
                labels = pd.Series("sideways", index=daily_ret.index)
                labels[daily_ret >= q67] = "bull"
                labels[daily_ret <= q33] = "bear"

            regime_sh = regime_sharpes(_equity_curve, labels)
            min_regime_sharpe = min(regime_sh.values()) if regime_sh else 0.0
            regime_passed = min_regime_sharpe >= _THRESHOLDS["min_regime_sharpe"]
            gates["regime_robustness"] = {
                "passed": regime_passed,
                "metric": "min_regime_sharpe",
                "value": min_regime_sharpe,
                "regime_sharpes": regime_sh,
            }
        else:
            gates["regime_robustness"] = {
                "passed": False,
                "metric": "min_regime_sharpe",
                "value": -999.0,
                "note": "no equity curve",
            }
    except Exception as exc:  # noqa: BLE001
        log.warning("scorecard.regime_failed", error=str(exc))
        gates["regime_robustness"] = {"passed": False, "metric": "error", "value": str(exc)}

    # --- Overall pass/fail ---
    all_passed = all(g.get("passed", False) for g in gates.values())

    scorecard = {
        "passed": all_passed,
        "gates": gates,
        "n_gates_passed": sum(g.get("passed", False) for g in gates.values()),
        "n_gates_total": len(GATES),
    }

    log.info(
        "scorecard.complete",
        passed=all_passed,
        n_passed=scorecard["n_gates_passed"],
        n_total=scorecard["n_gates_total"],
        gate_results={k: v.get("passed", False) for k, v in gates.items()},
    )

    return scorecard
