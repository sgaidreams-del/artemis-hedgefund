# 5-Year Walk-Forward Backtest — Technical + Quant Signals — 2026-06-24

## Scope and methodology

This backtests the **technical_composite signal** and the **qlib/LightGBM alpha model** against 5 years of real historical OHLCV data (2021-06-25 → 2026-06-24) across the 12-ticker seed universe (`SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, JPM, XOM, UNH`), benchmarked against SPY buy-and-hold.

### What this does NOT test

The live ensemble strategy combines 8 signal types (`src/strategy/ensemble/weights.py`), but most have no historical archive to backtest against:
- `ensemble_scores` (the live strategy's actual daily decisions) has only 2 days of history — that pipeline was wired up this session.
- LLM sentiment, options-flow, and insider signals are either generated live (LLM calls happen "now," not retroactively informed by point-in-time news from years ago) or have no historical data feed (options flow / insider data collection only started recently).
- This run therefore covers **technical_composite (20% of the live ensemble's weight) and qlib_alpha (15%)** — renormalized to ~57%/43% for the combined signal — not the full live strategy. It also does not replay the live position-sizing/risk-limit logic (`src/risk/position_sizer.py`, `rebalancer.py`, the pre-trade gate) — it uses the validation engine's own simplified long/short cross-sectional weighting (signal value, sign preserved, gross-normalized per day), which is standard for signal-validation backtesting but is not how `daily_trader.py` actually sizes positions live.

### Point-in-time correctness

- `compute_technical_score(ticker, date)` was already point-in-time safe (queries `ohlcv_daily WHERE date <= date`). The bulk signal builder (`src/validation/historical_signals.py`, new) reuses its exact formula/weights, computed once per ticker across the full history instead of ~15,000 individual per-date DB calls — verified to match the live function within a few hundredths on spot-checked dates (the only documented divergence: OBV momentum uses a full-history basis instead of compute_technical_score's per-call fresh-window basis; immaterial given OBV is 15% of one sub-signal and the result is clipped to [-1, 1]).
- `train_model()` (`src/strategy/alpha/training.py`) had a **real latent lookahead-bias bug** for any non-live use: it hardcoded `end_date = date.today()`, so any historical retrain would have trained on data including dates after the test period. Fixed with a backward-compatible `as_of_date` parameter (defaults to today for the live pipeline; the backtest passes each walk-forward window's train-end date). Also added a `model_path` parameter so backtest retrains never overwrite the live pipeline's `models/qlib/model.pkl` — confirmed after the run that the live model file's mtime is untouched.

## Data coverage

| Table | Coverage used |
|---|---|
| `ohlcv_daily` | Full 5yr history, all 12 tickers, 1253 trading days |
| `fundamentals` | Sparse/likely empty over most of the window — qlib alpha's `pe_ratio_norm`/`market_cap_log` features degrade to 0 (neutral) where missing, by existing design in `training.py` |

## Result A — Static 5-year scorecard (technical-only, no training, no lookahead risk)

`run_full_validation()` ran all 8 gates over the full window. **1/8 gates passed.**

| Gate | Passed | Metric | Value |
|---|---|---|---|
| Event study | ❌ | CAR p-value | 0.410 (not significant) |
| Backtest | ❌ | Sharpe | **-0.074** (max drawdown -17%) |
| CPCV | ✅ | OOS win rate | 0.60 |
| Deflated Sharpe | ❌ | DSR | 0.00 |
| PBO (overfitting prob.) | ❌ | 0.625 (>0.5 — likely overfit if treated as a fitted strategy) |
| SPA test | ❌ | p=0.288 (not significant vs. SPY) |
| Param stability | ❌ | 0.267 (<0.30 threshold) |
| Regime robustness | ❌ | min regime Sharpe -19.97 (driven by a sharp bear-quantile day) |

**Reading:** the technical_composite signal, used alone as a cross-sectional long/short allocator, has **no measurable edge** over this 5-year window. A negative Sharpe and failing 7/8 gates is a clean, credible negative result — not a sign of a broken pipeline (CPCV's 60% OOS win rate is the one gate that passed, but the corresponding avg Sharpe and every other significance/overfitting check disagree).

## Result B — Cost-aware pass (technical-only, 5bps one-way transaction cost)

| Metric | Value |
|---|---|
| Sharpe | -0.154 |
| Sortino | -0.207 |
| Max drawdown | -29.2% |
| Win rate | 49.0% |
| Profit factor | 0.97 |

Realistic transaction costs make the already-negative result worse, as expected for a signal with no underlying edge (costs only erode, they don't fix a strategy that isn't predictive).

## Result C — True walk-forward (technical + qlib alpha combined, retrained per window)

`WalkForwardRunner(train_days=504, test_days=126, step_days=126)` — 2-year train / 6-month test, non-overlapping. 5 windows fit in the 5-year span; the first 2 years are consumed as the initial training set (expected).

| Window | Train ends | Test period | IS Sharpe | OOS Sharpe |
|---|---|---|---|---|
| 0 | 2023-06-27 | 2023-06-28 → 2023-12-26 | 0.201 | **-1.804** |
| 1 | 2023-12-26 | 2023-12-27 → 2024-06-27 | 0.010 | **+1.036** |
| 2 | 2024-06-27 | 2024-06-28 → 2024-12-26 | 0.166 | **-0.191** |
| 3 | 2024-12-26 | 2024-12-27 → 2025-07-01 | 0.297 | **-1.219** |
| 4 | 2025-07-01 | 2025-07-02 → 2025-12-30 | -0.463 | **+2.830** |

Average OOS Sharpe: **0.13**. Windows with positive OOS Sharpe: 2/5 (40%). In-sample Sharpe is consistently small and near zero, and does not predict the sign or magnitude of the out-of-sample result in any of the 5 windows — the hallmark of a signal combination without genuine, stable predictive power, rather than a strategy that "works but is volatile."

## SPY benchmark (buy-and-hold, same 5-year window)

| Metric | Value |
|---|---|
| Sharpe | **0.718** |
| Sortino | 0.993 |
| Max drawdown | -25.4% |
| Calmar | 0.453 |
| Win rate | 54.3% |

SPY's ~0.72 Sharpe over a window that includes the 2022 bear market and subsequent recovery is consistent with its known real performance — a useful sanity check that the data pipeline isn't silently broken.

## Interpretation

- **Simply holding SPY clearly outperformed every variant of the technical/quant signal tested here**, on a risk-adjusted basis, over the last 5 years.
- The technical_composite and qlib_alpha signals, alone or combined, show no statistically credible edge in this window — most overfitting/significance gates fail, and walk-forward OOS performance is high-variance with no IS→OOS predictive relationship.
- This is **not** a verdict on the live ensemble strategy as a whole — the components most likely to carry real informational edge (LLM-driven fundamental/news analysis, options flow, insider activity) are exactly the ones this backtest structurally cannot test, since they don't have a historical archive.
- The methodology itself (point-in-time signal construction, walk-forward retraining, an 8-gate overfitting scorecard, cost-aware simulation, benchmark comparison) is now in place and reusable — `scripts/run_walkforward_backtest.py` can be re-run on demand, and will become more informative as `ensemble_scores`/`signals` accumulate real history for the full live strategy.

## Recommended next steps

1. Let the live pipeline accumulate `ensemble_scores`/`portfolio_snapshots` history (now being written daily, per the Phase 3 risk-safeguards snapshot writer) so a future backtest can test the actual full-ensemble decisions, not just the technical/quant subset.
2. If technical/quant signals are to remain in the live ensemble at their current weights (20%/15%) despite this result, treat that as a deliberate choice to diversify against the un-backtestable signals' blind spots, not as a result of these signals having demonstrated edge.
3. Consider re-running this backtest periodically (e.g. quarterly) as more data accumulates, and once `fundamentals` history is deeper (qlib alpha's PE/market-cap features are currently mostly neutral-filled).

---
*Generated by `scripts/run_walkforward_backtest.py`. Raw output: `walkforward_results.json` (repo root, gitignored — regenerate by re-running the script).*
