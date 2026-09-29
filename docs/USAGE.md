# Artemis operations guide

This guide covers running Artemis day to day. For installation, see the
[README](../README.md#quick-start).

All commands assume you're in the repo root. `py` means `.venv/bin/python`.

---

## Contents
1. [The daily pipeline](#1-the-daily-pipeline)
2. [Trading: preview, submit, stop](#2-trading-preview-submit-stop)
3. [Risk halts](#3-risk-halts)
4. [The dashboard](#4-the-dashboard)
5. [The simulator](#5-the-simulator)
6. [Learning loop](#6-learning-loop)
7. [Choosing what to trade](#7-choosing-what-to-trade)
8. [Scheduling](#8-scheduling)
9. [Backtesting](#9-backtesting)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. The daily pipeline

```bash
py scripts/run_pipeline.py
```

This runs each job below in order. A failing job is reported and skipped, so the rest still run.
A lock file stops two pipeline runs from overlapping. Run it after the US market closes.

| Job | What it does | Needs |
|---|---|---|
| `universe.refresh` | Refreshes the tradable universe from the filters | — |
| `price.eod`, `price.eod_extended` | Daily bars for trading and watch-only tickers | Alpaca |
| `news.rss` | News headlines | — |
| `macro.fred` | Macro indicators | FRED key |
| `fundamentals.daily` | Fundamentals snapshot | — |
| `insider.finnhub` | Insider transactions | Finnhub key |
| `options_flow.collect` | Put/call volume, IV rank, unusual activity | Alpaca |
| `features.daily` | Feature store (volatility, returns, …) | — |
| `signals.*` | Sentiment, technical, regime, LLM, insider, short interest, options flow, volume anomaly, alpha | DeepSeek for LLM |
| `strategy.ensemble` | Blends signals into scores and target weights | — |
| `strategy.reflections` | Post-mortems on trades at least 5 trading days old | DeepSeek |
| `strategy.eod_movers` | Missed-mover and Universe Miss analysis | DeepSeek |
| `quality.watchdog` | Data freshness and health score | — |
| `portfolio.snapshot` | Records equity, return and drawdown (the halts depend on this) | Alpaca |
| `sim.step` | Advances the virtual portfolio | — |
| `report.daily` | Daily report | — |

The pipeline **never places orders**.

## 2. Trading: preview, submit, stop

```bash
py scripts/run_daily_trade.py          # dry run — prints the orders, submits nothing
py scripts/run_daily_trade.py --live   # asks you to type 'yes', then submits limit orders
```

The dashboard has matching **Preview** and **Execute** buttons.

Each order goes through `src/risk/pretrade.py` before reaching the broker. The gate rejects the
order if any of these is true:
- the kill switch is on;
- the market is closed;
- quantity or dollar size is over the cap (`execution.max_order_qty` / `max_order_notional`);
- the limit price is more than `price_collar_pct` away from a fresh quote;
- the quote is older than `max_quote_age_seconds`;
- more than `max_orders_per_minute` orders have been sent in the last minute;
- the same order ID has already been sent.

If a check can't run (for example, the broker is unreachable), the order is **rejected**, not
allowed through.

**Kill switch.** Use the dashboard button, or send a request to the API:

```bash
curl -X POST localhost:8000/api/kill-switch/pause \
     -H 'X-Artemis-Client: dashboard' -H 'Content-Type: application/json' \
     -d '{"reason":"manual"}'
```

Turning it on blocks all new orders and **cancels every open order**. Resume from the dashboard,
or send the same request to `/resume`.

**Flatten everything (manual only).** `py scripts/flatten_all.py` liquidates every position.
It requires typing `yes`, and no halt or safeguard ever calls it automatically.

## 3. Risk halts

On every rebalance, `daily_trader.py` checks the following. Any breach **freezes** trading
through the kill switch; positions are kept, not sold.

| Check | Default | Setting in `config/settings.yaml` |
|---|---|---|
| Daily loss | −3% | `risk.daily_drawdown_halt` |
| Drawdown from peak | −15% | `risk.max_drawdown_liquidate` (freezes; the name is historical) |
| Consecutive losing days | 3 | `risk.consecutive_loss_days_halt` |
| Cash floor | 10% | `portfolio.min_cash_pct` |
| Gross leverage | 1.0× | `portfolio.max_gross_leverage` |
| Options DB ↔ broker mismatch | any quantity mismatch | — (reconciliation) |

Halts are logged to the dashboard's **Activity / Alerts** panel. Investigate before you resume.

## 4. The dashboard

`./start.sh` serves the API on `127.0.0.1:8000` and the UI on `127.0.0.1:5173`.

| Tab | Shows |
|---|---|
| **Overview** | Portfolio value, day P&L, equity curve, Sharpe/Sortino/drawdown, vs-SPY chart, regime banner, activity feed |
| **Trade History** | Every fill |
| **Learnings** | Reflections, labeled by type: **Missed** (mover in your universe), **Universe Miss** (mover outside it), **Test** (development entries) |
| **Options** | Engine status, open options positions, hedge review, earnings straddle scan, flow signals |
| **Calendar** | FOMC/CPI/jobs/earnings events. Click an event 7+ days out for an LLM plan of action |
| **Simulator** | The virtual $100k portfolio |

The strip at the top shows live connection status for Alpaca, Postgres, Redis and DeepSeek. A red
dot usually means a key is missing or wrong, or a service isn't running. Redis is optional.

## 5. The simulator

The Simulator tab paper-trades every ensemble recommendation against a **virtual** $100k
portfolio. It uses the same sizing and rebalancer logic as live trading but makes **no broker
calls**. Use it to judge the strategy with zero risk.
- **Running** toggle: steps once per pipeline run.
- **Run Now**: steps it immediately.
- **Reset**: restores $100k and clears its history.
- Weekly reports summarize performance.

## 6. Learning loop

- **Reflections**: 5 trading days after a trade, DeepSeek compares the entry signals with what
  actually happened and writes a short post-mortem.
- **End-of-day movers**: the day's biggest moves of at least 2% in your universe that you did
  *not* trade get an analysis of which signals were informative, which misled, and what weight or
  threshold change would have caught them. The 3 biggest watch-only movers each day are logged as
  **Universe Miss**, with a recommendation on whether to add them.
- **AutoResearch** (`src/autoresearch/`) reads these entries, generates hypotheses, runs
  experiments, and promotes a change only after a shadow period and a paper burn-in
  (`autoresearch.*` in `settings.yaml`), rolling back if Sharpe degrades.

All of these entries are in the `trade_memory` table and on the Learnings tab.

## 7. Choosing what to trade

Edit `config/universe.yaml`:

```yaml
seed_tickers:        # full signals + eligible for orders
  - AAPL
  - MRNA
  ...
extended_watchlist:  # prices only; scanned for big moves ("Universe Miss")
  - AVGO
  ...
```

After adding tickers, backfill their history:

```bash
py scripts/seed_historical.py --years 2 --tickers NEW1 NEW2
```

Use Alpaca's symbol format, which uses a dot for share classes: `BRK.B`, not `BRK-B`.

## 8. Scheduling

**macOS**

```bash
scripts/launchagent_setup.sh                # data pipeline Mon–Fri 17:00 (never trades)
scripts/launchagent_setup.sh --with-trader  # ALSO unattended rebalance 06:35 — opt-in, paper only
scripts/launchagent_setup.sh --uninstall
```

Logs go to `~/Library/Logs/artemis_*.log`. The trader schedule assumes the machine clock is on
US Pacific time (06:35 PT is 09:35 ET), so edit the template if you're elsewhere.

**Linux**

```cron
0 17 * * 1-5  cd /path/to/artemis && .venv/bin/python scripts/run_pipeline.py >> logs/pipeline.log 2>&1
```

## 9. Backtesting

```bash
py scripts/run_walkforward_backtest.py
```

This rebuilds the historically reconstructable signals (technical composite and LightGBM alpha)
point-in-time over 5 years. It then runs the 8-gate validation scorecard, a cost-aware simulation
and a rolling walk-forward (2-year train, 6-month test), and compares the results with SPY.
Results go to `walkforward_results.json`.

LLM, insider, options-flow and news signals have no historical archive, so they **aren't**
included.

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `Required env var 'POSTGRES_PASSWORD' is not set` | Run `./install.sh --keys`. It generates one. |
| Dashboard says **Broker not connected** | Check your Alpaca keys with `./install.sh --keys`. It also appears briefly while the API restarts. |
| LLM columns empty / reflections stuck at "pending" | Your DeepSeek key is missing or out of credit. Top up, then re-run the pipeline. |
| `403 missing 'x-artemis-client: dashboard' header` | Scripts calling the API must send that header on POST and DELETE requests (CSRF protection). |
| `400 Invalid host header` | Open the dashboard at `localhost` or `127.0.0.1`. To use another hostname, add it to `ARTEMIS_ALLOWED_HOSTS` (and its origin to `ARTEMIS_ALLOWED_ORIGINS`) in `.env`, and understand the risk first. |
| `pip install` fails on numba / llvmlite | Use Python 3.11–3.13. Python 3.14 isn't supported yet. |
| Port 5432/8000/5173 already in use | Docker Postgres uses 5433. Stop the other process or change `POSTGRES_PORT` in `.env`. |
| `invalid symbol: BRK-B` | Use the dot form, `BRK.B`. |
| No trades today | Check the Activity panel for halts or the kill switch. Otherwise, target weights may be within `rebalance_threshold_pct` of the current ones. |
