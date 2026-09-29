#!/usr/bin/env python3
"""5-year walk-forward backtest — technical + quant signals only.

Scope (see research_journal/manual/ for the full writeup): the live ensemble's
LLM/sentiment/options-flow/insider signals have no historical archive to
backtest against, so this tests the technical_composite signal (point-in-time
safe by construction) and the qlib/LightGBM alpha model (retrained walk-forward
at each fold so it never sees future data), against the 12-ticker seed universe
over the last 5 years of real OHLCV history. SPY (in the universe and the
default scorecard benchmark) is used both as a tradable candidate and as the
buy-and-hold comparator.

Produces three results, printed as JSON to stdout and returned for the report
generator:
  A. Static 5-year scorecard (technical-only) — src.validation.scorecard.run_full_validation
  B. Cost-aware pass (technical-only, 5bps) — src.validation.backtest.simulator.simulate
  C. True walk-forward (technical + qlib alpha combined) — src.validation.walk_forward.WalkForwardRunner

Usage:
    python scripts/run_walkforward_backtest.py [--years 5] [--out results.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.core.config import universe as universe_cfg  # noqa: E402
from src.core.db import conn  # noqa: E402
from src.core.logging import get_logger  # noqa: E402
from src.validation.backtest.metrics import compute_metrics  # noqa: E402
from src.validation.backtest.simulator import simulate  # noqa: E402
from src.validation.baseline import buy_and_hold_returns  # noqa: E402
from src.validation.historical_signals import build_historical_technical_signals  # noqa: E402
from src.validation.scorecard import run_full_validation  # noqa: E402
from src.validation.walk_forward import WalkForwardRunner  # noqa: E402

log = get_logger("walkforward_backtest")

BENCHMARK_TICKER = "SPY"
# Renormalized from src.strategy.ensemble.weights.DEFAULT_WEIGHTS
# (technical_composite=0.20, qlib_alpha=0.15) so the combined signal sums to 1.0.
TECHNICAL_WEIGHT = 0.20 / 0.35
ALPHA_WEIGHT = 0.15 / 0.35


def _build_prices_df(tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT ticker, date, adj_close FROM ohlcv_daily
            WHERE ticker = ANY(%s) AND date BETWEEN %s AND %s
            ORDER BY date
            """,
            (tickers, start_date, end_date),
        )
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["ticker", "date", "adj_close"])
    df["date"] = pd.to_datetime(df["date"])
    df["adj_close"] = pd.to_numeric(df["adj_close"], errors="coerce")
    return df.pivot(index="date", columns="ticker", values="adj_close")


def run_technical_alpha_walkforward(
    technical_df: pd.DataFrame, prices_df: pd.DataFrame, tickers: list[str],
    train_days: int = 504, test_days: int = 126, step_days: int = 126,
) -> list[dict]:
    from src.strategy.alpha.qlib_model import predict_alpha
    from src.strategy.alpha.training import train_model

    # Dedicated path — never touch the live pipeline's models/qlib/model.pkl.
    backtest_model_path = ROOT / "models" / "qlib_backtest" / "model.pkl"

    runner = WalkForwardRunner(train_days=train_days, test_days=test_days, step_days=step_days)
    common_idx = technical_df.index.intersection(prices_df.index)
    technical = technical_df.loc[common_idx]
    prices = prices_df.loc[common_idx]
    windows = runner.generate_windows(len(common_idx))

    results: list[dict] = []
    for i, (train_range, test_range) in enumerate(windows):
        t0_train, t1_train = train_range
        t0_test, t1_test = test_range
        train_prices = prices.iloc[t0_train:t1_train]
        test_prices = prices.iloc[t0_test:t1_test]
        test_technical = technical.iloc[t0_test:t1_test]

        as_of = train_prices.index.max().date().isoformat()
        alpha_test = pd.DataFrame(index=test_technical.index, columns=tickers, dtype=float)
        try:
            train_model(
                lookback_days=min(756, t1_train - t0_train),
                as_of_date=as_of,
                model_path=backtest_model_path,
            )
            for d in test_technical.index:
                scores = predict_alpha(tickers, d.date().isoformat(), model_path=backtest_model_path)
                for t in tickers:
                    alpha_test.loc[d, t] = scores.get(t, np.nan)
        except Exception as exc:
            log.warning("walkforward.window_alpha_failed", window=i, error=str(exc))

        combined_test = (
            TECHNICAL_WEIGHT * test_technical.fillna(0.0)
            + ALPHA_WEIGHT * alpha_test.fillna(0.0)
        )

        from src.validation.backtest.engine import run_backtest
        is_result = run_backtest(technical.iloc[t0_train:t1_train].fillna(0.0), train_prices)
        oos_result = run_backtest(combined_test, test_prices)

        results.append({
            "window_idx": i,
            "train_range": train_range,
            "test_range": test_range,
            "train_end_date": str(train_prices.index.max().date()),
            "test_start_date": str(test_prices.index.min().date()),
            "test_end_date": str(test_prices.index.max().date()),
            "is_sharpe": is_result["metrics"]["sharpe"],
            "oos_sharpe": oos_result["metrics"]["sharpe"],
            "oos_metrics": oos_result["metrics"],
        })
        log.info("walkforward.window_done", window=i, as_of=as_of,
                  is_sharpe=round(is_result["metrics"]["sharpe"], 3),
                  oos_sharpe=round(oos_result["metrics"]["sharpe"], 3))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--out", type=str, default="walkforward_results.json")
    args = parser.parse_args()

    tickers = universe_cfg()["seed_tickers"]
    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=365 * args.years)).isoformat()

    log.info("backtest.start", tickers=tickers, start=start_date, end=end_date)

    prices_df = _build_prices_df(tickers, start_date, end_date)
    technical_df = build_historical_technical_signals(tickers, start_date, end_date)
    technical_df = technical_df.reindex(columns=prices_df.columns)

    log.info("backtest.data_ready", prices_rows=len(prices_df), signal_rows=len(technical_df))

    # ── Result A: static 5-year scorecard (technical-only) ──────────────────
    scorecard = run_full_validation(
        strategy_fn=None,
        signals_df=technical_df.fillna(0.0),
        prices_df=prices_df,
        benchmark_ticker=BENCHMARK_TICKER,
    )

    # ── Result B: cost-aware pass (technical-only, 5bps) ────────────────────
    cost_aware = simulate(technical_df.fillna(0.0), prices_df, transaction_cost_bps=5.0)

    # ── Result C: true walk-forward (technical + alpha combined) ────────────
    wf_results = run_technical_alpha_walkforward(technical_df, prices_df, tickers)

    # ── Benchmark: SPY buy-and-hold ──────────────────────────────────────────
    spy_returns = buy_and_hold_returns(prices_df, ticker=BENCHMARK_TICKER)
    spy_equity = (1 + spy_returns).cumprod()
    spy_metrics = compute_metrics(spy_equity)

    output = {
        "scope": {
            "tickers": tickers,
            "start_date": start_date,
            "end_date": end_date,
            "n_trading_days": len(prices_df),
        },
        "result_a_scorecard": scorecard,
        "result_b_cost_aware_metrics": cost_aware["metrics"],
        "result_c_walkforward": wf_results,
        "spy_benchmark_metrics": spy_metrics,
    }

    out_path = ROOT / args.out
    out_path.write_text(json.dumps(output, indent=2, default=str))
    log.info("backtest.complete", out=str(out_path))
    print(json.dumps(output, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
