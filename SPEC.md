# Artemis: AI-Powered Autonomous Hedge Fund

## System Specification Document

**Version:** 4.0
**Date:** 2026-06-17
**Status:** Phase 1 Complete
**Phase 1 completion date:** 2026-06-17
**Revision Notes:**
- v2.0 — peer review pass: removed local LLM dependency, added tax-aware trading, corporate actions handler, dual-engine backtesting, feature store, HITL Git gate, concept drift monitoring, execution safety fixes.
- v2.x — absorbed [TradingAgents](https://github.com/tauricresearch/tradingagents) ideas: Bull/Bear adversarial debate gate (6.4), trade decision memory with deferred reflection (6.5), data vendor failover (6.6), two-tier LLM routing (DeepSeek v4 Pro for argumentation, DeepSeek R1 for adjudication), DeepSeek v4 Pro cost model replacing Claude.
- v3.0 — absorbed [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) ideas: philosophy-grounded debate scoring (6.4.1 — deterministic quality/contrarian checklists, not a 13-persona zoo), constrain-then-delegate position sizing (8.1 — vol-tier cap × correlation multiplier computed before any LLM/RL call), forced-HOLD cost optimization (8.1.1), event-study pre-screen Gate 0 (7.0) with seeded PEAD strategy.
- v4.0 — Phase 1 complete: macOS LaunchAgent pipeline scheduler (Unit 14), Options Engine design (Phases A–D), expanded Dashboard Features documentation.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Goals & Constraints](#2-system-goals--constraints)
3. [Architecture Overview](#3-architecture-overview)
4. [Layer 1: Data Ingestion](#4-layer-1-data-ingestion)
5. [Layer 2: Intelligence & Signal Generation](#5-layer-2-intelligence--signal-generation)
6. [Layer 3: Strategy & ML Engine](#6-layer-3-strategy--ml-engine)
7. [Layer 4: Backtesting & Validation Engine](#7-layer-4-backtesting--validation-engine)
8. [Layer 5: Portfolio & Risk Management](#8-layer-5-portfolio--risk-management)
9. [Layer 6: Execution Engine](#9-layer-6-execution-engine)
10. [Layer 7: AutoResearch Engine](#10-layer-7-autoresearch-engine)
11. [Layer 8: Monitoring & Dashboard](#11-layer-8-monitoring--dashboard)
12. [Tech Stack](#12-tech-stack)
13. [Data Schema](#13-data-schema)
14. [Directory Structure](#14-directory-structure)
15. [Implementation Plan](#15-implementation-plan)
16. [Cost Estimates](#16-cost-estimates)
17. [Risk Register](#17-risk-register)
18. [Options Engine](#18-options-engine-v40)
19. [Dashboard Features](#19-dashboard-features-v40)
20. [Appendix](#20-appendix)

---

## 1. Executive Summary

Artemis is a fully automated, AI-powered trading system that analyzes US equities and executes trades autonomously to grow a personal portfolio. The system combines traditional quantitative finance (technical indicators, factor models) with modern AI (reinforcement learning, LLM-powered analysis, sentiment models) and a self-improving research loop inspired by Karpathy-style autoresearch.

The system is designed for minimal user input: once configured and deployed, it operates autonomously — collecting data, generating signals, validating strategies against overfitting, executing trades, managing risk, and continuously researching improvements to its own strategies.

### Key Differentiators

- **Self-improving:** An autonomous research loop continuously generates, tests, and deploys new indicators and strategy improvements.
- **Overfitting-resistant:** A fast event-study pre-screen plus a 6-gate statistical validation pipeline ensures no strategy reaches live trading without rigorous out-of-sample proof.
- **Regime-aware:** Hidden Markov Model detects market regimes and adjusts strategy weights, position sizing, and risk limits dynamically.
- **Cloud-native inference:** All LLM work uses cloud APIs (DeepSeek v4 Pro + R1) — no local model hosting required, runs on any machine with sufficient RAM for data processing. Total LLM cost: ~$4.50/mo.
- **Tax-aware:** Wash sale detection and tax-lot management prevent unexpected tax liabilities from high-frequency rebalancing.
- **Constrain-then-delegate risk:** Position size ceilings are computed deterministically (volatility tier × correlation multiplier) before any LLM or RL call — decision layers can choose conviction within the legal range but cannot structurally violate risk limits.
- **Debate-gated, evidence-grounded decisions:** Significant trades pass through an adversarial Bull/Bear debate anchored to deterministic quality and tail-risk checklists, adjudicated by a reasoning model — not a single opaque score.

---

## 2. System Goals & Constraints

### Goals

| Goal | Target | Measurement |
|---|---|---|
| Annual return | 15-25% (net of costs) | Realized P&L vs benchmark (SPY) |
| Sharpe ratio | > 1.0 | Rolling 252-day Sharpe |
| Max drawdown | < 15% | Peak-to-trough portfolio value |
| Automation level | > 95% hands-off | Human interventions per month |
| Strategy improvement | Measurable quarterly | AutoResearch journal metrics |

### Constraints

| Constraint | Detail |
|---|---|
| Asset universe | US equities (NYSE, NASDAQ) — no crypto, forex, or options at launch |
| Broker | Alpaca (commission-free, excellent API) |
| Capital | Personal capital only — no outside investors (avoids SEC registration) |
| Leverage | 1.0x maximum (no margin trading at launch) |
| Trading hours | Regular market hours only (9:30 AM - 4:00 PM ET) |
| Rebalancing frequency | Daily (intraday signals aggregated to EOD decisions) |
| Minimum position hold | 1 trading day (no HFT) |

### Non-Goals (Explicitly Out of Scope)

- High-frequency trading (sub-second execution)
- Options or derivatives strategies
- Cryptocurrency trading
- Multi-asset portfolio (bonds, commodities) — potential future expansion
- Managing external capital
- Market making

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              LAYER 1: DATA INGESTION                     │  │
│  │  Market Data · News · SEC Filings · Social · Macro       │  │
│  │  ┌─────────────────────────────────────────────────┐     │  │
│  │  │         Data Quality Watchdog (continuous)       │     │  │
│  │  └─────────────────────────────────────────────────┘     │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │           LAYER 2: INTELLIGENCE & SIGNALS                │  │
│  │  FinBERT Sentiment · FinGPT Analysis · Technical Ind.    │  │
│  │  Regime Detection (HMM) · Alternative Data Signals       │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │            LAYER 3: STRATEGY & ML ENGINE                 │  │
│  │  QLib Alpha Model · FinRL RL Agent · Ensemble Weighting  │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │         LAYER 4: BACKTESTING & VALIDATION                │  │
│  │  Walk-Forward Analysis · CPCV · DSR · PBO · SPA          │  │
│  │  Parameter Stability · Regime Robustness                  │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │          LAYER 5: PORTFOLIO & RISK MANAGEMENT            │  │
│  │  Position Sizing · Drawdown Halts · Correlation Monitor  │  │
│  │  Volatility Targeting · Sector Limits                     │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │             LAYER 6: EXECUTION ENGINE                    │  │
│  │  Alpaca API · Smart Order Routing · Cost Tracking        │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │          LAYER 8: MONITORING & DASHBOARD                 │  │
│  │  React+FastAPI Dashboard · Telegram Alerts · Daily Reports│ │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           LAYER 7: AUTORESEARCH ENGINE                   │  │
│  │  Hypothesize → Implement → Backtest → Analyze → Learn    │  │
│  │  ┌────────────────────────────────────────────────┐      │  │
│  │  │           Research Journal (persistent)         │      │  │
│  │  └────────────────────────────────────────────────┘      │  │
│  │  Feeds validated improvements back into Layers 2-5       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Layer 1** collects raw market data, news, filings, social sentiment, and macro indicators on schedule.
2. **Layer 2** transforms raw data into actionable signals: sentiment scores, technical indicators, LLM analysis, regime labels.
3. **Layer 3** consumes signals and produces trade decisions via ML models (QLib, FinRL) combined through an ensemble.
4. **Layer 4** validates every strategy and model change through walk-forward analysis and a 6-gate overfitting detection suite before anything reaches production.
5. **Layer 5** applies risk constraints: position limits, drawdown halts, sector caps, volatility targeting.
6. **Layer 6** converts risk-adjusted trade decisions into broker orders via Alpaca.
7. **Layer 7** (AutoResearch) runs continuously in the background, generating hypotheses, running experiments, and feeding validated improvements back into Layers 2-5.
8. **Layer 8** provides real-time monitoring, alerting, and performance reporting.

---

## 4. Layer 1: Data Ingestion

### 4.1 Data Sources

| Data Type | Source | Library/API | Update Frequency | Storage |
|---|---|---|---|---|
| Price/Volume (OHLCV) | Alpaca Market Data | `alpaca-trade-api` | Real-time / 1-min bars | TimescaleDB |
| Historical price data | Polygon.io | `polygon-io` | End of day | TimescaleDB |
| Company fundamentals | Yahoo Finance | `yfinance` | Daily | PostgreSQL |
| SEC filings (10-K, 10-Q, 8-K) | SEC EDGAR | `sec-edgar-downloader` | As filed | File system + PostgreSQL |
| Insider transactions (Form 4) | SEC EDGAR | `sec-edgar-downloader` | As filed | PostgreSQL |
| News headlines | RSS feeds (Reuters, MarketWatch, CNBC) | `feedparser` | Every 15 minutes | PostgreSQL |
| Social sentiment | Reddit (r/wallstreetbets, r/stocks) | `praw` | Every 15 minutes | PostgreSQL |
| Macro indicators | FRED (Federal Reserve) | `fredapi` | Daily/Monthly | PostgreSQL |
| Earnings calendar | Yahoo Finance | `yfinance` | Daily | PostgreSQL |
| Options flow | Unusual Whales / CBOE | TBD | Daily | PostgreSQL |
| Short interest | FINRA | `finra-api` | Bi-weekly | PostgreSQL |

### 4.2 Data Pipeline Architecture

```
Scheduler (Celery + Redis)
    │
    ├── every 1 min ──→ Price Collector ──→ TimescaleDB (ohlcv_1m)
    ├── every 15 min ─→ News Collector ──→ PostgreSQL (news_headlines)
    ├── every 15 min ─→ Reddit Scraper ──→ PostgreSQL (social_posts)
    ├── daily 6:00 PM → EOD Collector ───→ TimescaleDB (ohlcv_daily)
    ├── daily 6:00 PM → Fundamentals ───→ PostgreSQL (fundamentals)
    ├── daily 7:00 PM → FRED Macro ─────→ PostgreSQL (macro_indicators)
    ├── on filing ────→ SEC Collector ──→ File System + PostgreSQL
    └── bi-weekly ────→ Short Interest ─→ PostgreSQL (short_interest)
```

### 4.3 Data Quality Watchdog

An automated monitoring system that runs after every data collection job.

**Checks performed:**

| Check | Action on Failure |
|---|---|
| Missing data points (gaps in time series) | Attempt re-fetch; if persistent, flag and interpolate |
| Stale data (no update in expected window) | Alert via Telegram; pause affected signals |
| Obvious errors (price = 0, negative volume) | Quarantine record; alert |
| Survivorship bias (delisted tickers disappearing) | Maintain delisted ticker archive |
| Point-in-time violation (future data leaking into historical) | Hard block; alert immediately |
| Source availability (API responding) | Failover to backup source if available |

**Implementation:** Each collector returns a `DataQualityReport` object. Reports are logged and aggregated into a daily health score (0-100). If health score drops below 80, trading is paused until manual review.

### 4.4 Corporate Actions Handler

**Problem this solves:** Stock splits, reverse splits, dividends, ticker changes, and mergers happen daily. If a 4-to-1 split is recorded as a -75% price drop, the ML models and technical indicators will generate catastrophic false signals.

**Runs:** Daily at 5:00 AM ET (before any other pipeline stage)

**Actions handled:**

| Event | Detection | Response |
|---|---|---|
| Forward split | Polygon corporate actions API / yfinance | Back-adjust all historical OHLCV and volume; recalculate all technical indicators |
| Reverse split | Same | Same — adjust historical data upward |
| Cash dividend | Ex-date tracking | Adjust historical prices by dividend amount for continuity |
| Stock dividend | Corporate actions feed | Adjust share counts and historical prices |
| Ticker change | Symbol change feed | Update all references; maintain ticker alias history |
| Merger/acquisition (target delisted) | Delisting notification | Move to delisted archive; close any open position at final price |
| Spinoff | Corporate actions feed | Add new ticker to universe; adjust parent historical price |

**Implementation:**
```
Daily 5:00 AM ET:
    1. Fetch corporate actions for all universe tickers (last 24h)
    2. For each action:
        a. Apply retroactive adjustment to ohlcv_daily (back to IPO)
        b. Invalidate and recompute affected signals in feature store
        c. Update position records (adjust share counts for splits)
        d. Log action to corporate_actions table
    3. If any action affects current holdings, send Telegram alert
    4. Run data quality check on adjusted data
```

**Data source:** Polygon.io includes corporate actions in their API. Supplemented by `yfinance` as a cross-check.

### 4.5 Feature Store

**Problem this solves:** Computing FinBERT, technical indicators, and all derived features on-the-fly during CPCV validation runs (which iterate over many train/test folds) causes massive redundant computation. A feature store computes once and serves many times.

**Design:** A dedicated set of TimescaleDB tables that store pre-computed features with point-in-time semantics.

```
feature_store/
├── features_daily (TimescaleDB hypertable)
│   ├── ticker, date, feature_name, value
│   └── Indexed by (ticker, date) for fast slice queries
├── feature_metadata
│   ├── feature_name, category, computation_version, last_updated
│   └── Tracks which version of each feature's code produced the value
└── feature_lineage
    └── Tracks dependencies (e.g., RSI depends on ohlcv_daily.close)
```

**Rules:**
- Features are computed once per day after data ingestion completes
- Validation engine reads features directly — never recomputes
- If a feature's computation code changes (via AutoResearch), the feature store marks old values as stale and recomputes historically
- Point-in-time correctness: features are never updated retroactively without explicit recomputation (prevents lookahead)

**Performance impact:** CPCV with 252 combinatorial paths goes from ~4 hours (recomputing) to ~20 minutes (reading pre-computed features).

### 4.6 Polygon.io Tier Reality Check

**Known limitations of the $29/mo Starter tier:**
- Rate limits: 5 API calls/min (free), unlimited with paid
- Historical data: Daily bars are available for 5+ years; 1-min bars limited to 2 years
- No real-time streaming (15-min delayed quotes)
- Corporate actions data IS included
- No historical options flow data

**Mitigation strategy:**
- Use Alpaca's included real-time data for live price feeds (free with funded account)
- Use Polygon for historical backfill only (batch overnight, respecting rate limits)
- For 5-year 1-min bar backfill: use Alpaca's historical data API (included free)
- Accept that options flow data requires a separate provider or manual tracking initially
- Upgrade Polygon tier only if AutoResearch experiments demand deeper tick data

### 4.7 Universe Selection

The tradeable universe is filtered daily:

```
Full US Equity Universe (~8,000 stocks)
    │
    ├── Filter: Market cap > $500M ──→ ~2,500 stocks
    ├── Filter: Avg daily volume > $5M ──→ ~1,800 stocks  
    ├── Filter: Price > $5 ──→ ~1,700 stocks
    ├── Filter: Not ADR, SPAC, or BDC ──→ ~1,500 stocks
    └── Filter: Sufficient historical data (>252 days) ──→ ~1,400 stocks
```

This ensures adequate liquidity and reduces noise from micro-caps and thinly traded securities.

---

## 5. Layer 2: Intelligence & Signal Generation

### 5.1 Signal Categories

All signals are normalized to a [-1, +1] scale where:
- **+1** = strongest bullish signal
- **0** = neutral
- **-1** = strongest bearish signal

Each signal also carries a **confidence score** (0-1) and a **decay rate** (how quickly the signal loses predictive power).

### 5.2 Sentiment Analysis — FinBERT

**Repository:** [ProsusAI/finBERT](https://github.com/ProsusAI/finBERT)

**Purpose:** Classify news headlines and social media posts as positive, negative, or neutral for each ticker.

**Pipeline:**

```
Raw text (headline / reddit post / filing excerpt)
    │
    ▼
Preprocessing (ticker extraction, deduplication)
    │
    ▼
FinBERT inference (batch, GPU-accelerated)
    │
    ▼
Per-ticker sentiment aggregation
    │
    ▼
Rolling sentiment scores:
    - sent_1h:  last 1 hour
    - sent_24h: last 24 hours
    - sent_7d:  last 7 days
    - sent_delta: 24h change in sentiment (momentum of sentiment)
```

**Output schema:**

```python
{
    "ticker": "AAPL",
    "timestamp": "2026-05-16T14:30:00Z",
    "sent_1h": 0.42,
    "sent_24h": 0.31,
    "sent_7d": 0.18,
    "sent_delta": 0.13,
    "confidence": 0.87,
    "article_count": 24,
    "source_breakdown": {"news": 15, "reddit": 9}
}
```

### 5.3 LLM Analysis — DeepSeek v4 Pro (Cloud)

**Provider:** DeepSeek v4 Pro API ($0.435/M input tokens)

**Purpose:** Deep qualitative analysis that sentiment scores alone cannot capture — understanding earnings narratives, management tone shifts, macro implications.

**Runs via cloud API** — no local GPU required. System memory constraints preclude local LLM hosting.

**Critical scoping rule:** LLM analysis is expensive and slow at scale. It is restricted to:
- **Current portfolio holdings** (typically 15-30 stocks)
- **Top 20 watchlist candidates** (highest alpha scores not yet in portfolio)
- **NOT the entire 1,400-stock universe** — cross-sectional filtering is handled by LightGBM (fast, cheap)

This limits LLM calls to ~50 per day maximum, keeping costs under control (~$2/mo total) and ensuring the pipeline completes well before market open.

**Use cases:**

| Task | Input | Output | Frequency |
|---|---|---|---|
| Earnings analysis | Earnings transcript excerpt | Bull/bear thesis + conviction score | Quarterly per holding |
| SEC filing summary | 10-K/10-Q sections | Risk factor changes, guidance shifts | On filing (holdings only) |
| Macro regime commentary | Fed minutes, CPI data | Regime outlook + sector implications | Monthly |
| Trade rationale | Combined signals | Human-readable trade thesis | Per trade |

**Output schema:**

```python
{
    "ticker": "AAPL",
    "analysis_type": "earnings",
    "timestamp": "2026-05-16T18:00:00Z",
    "thesis": "Revenue beat driven by Services, but hardware guidance soft...",
    "conviction": 0.65,       # 0-1 scale
    "direction": "bullish",   # bullish / bearish / neutral
    "catalysts": ["services_growth", "buyback_increase"],
    "risks": ["china_exposure", "hardware_cycle"],
    "time_horizon": "90d"
}
```

### 5.4 Technical Indicators

**Library:** `pandas-ta`

Computed daily for every ticker in the universe. Grouped by category:

**Trend indicators:**
- SMA(20, 50, 200) — simple moving averages
- EMA(12, 26) — exponential moving averages
- MACD(12, 26, 9) — signal line crossover
- ADX(14) — trend strength

**Momentum indicators:**
- RSI(14) — overbought/oversold
- Stochastic RSI(14, 14, 3, 3) — refined RSI
- Williams %R(14) — momentum reversal

**Volatility indicators:**
- Bollinger Bands(20, 2) — volatility envelope
- ATR(14) — average true range
- Keltner Channels(20, 2) — ATR-based envelope

**Volume indicators:**
- OBV — on-balance volume
- VWAP — volume-weighted average price
- Volume SMA ratio — current volume vs 20-day average

**Composite technical signal:** A meta-score computed from all indicators, normalized to [-1, +1]. The individual indicator weights are managed by the AutoResearch engine (Layer 7).

### 5.5 Regime Detection

**Library:** `hmmlearn` (Hidden Markov Model)

**Purpose:** Detect the current market regime so that strategy weights and risk limits can adapt.

**Regime definitions:**

| Regime | Characteristics | Strategy Adaptation |
|---|---|---|
| 1: Bull / Low Vol | SPY trending up, VIX < 18 | Momentum-heavy, wider stops, higher allocation |
| 2: Bull / High Vol | SPY up but VIX > 25 | Reduce size, tighter stops, quality bias |
| 3: Bear / Low Vol | SPY trending down, VIX < 22 | Defensive sectors, value bias, raise cash |
| 4: Bear / High Vol | SPY down, VIX > 30 | Maximum cash, hedging via inverse ETFs, minimal new positions |
| 5: Mean-Reverting | Sideways SPY, normal VIX | Contrarian signals weighted higher, range-bound strategies |

**Input features for HMM:**
- SPY 20-day return
- VIX level and 5-day change
- Market breadth (% stocks above 50-day MA)
- Yield curve slope (10Y - 2Y)
- Credit spread (HY OAS)
- Put/call ratio

**Output:** Regime label + transition probability matrix (probability of switching to each other regime). Updated daily.

### 5.6 Alternative Data Signals

| Signal | Source | Logic | Output |
|---|---|---|---|
| Insider buying/selling | SEC Form 4 | Net insider purchases, cluster buys | Per-ticker insider score [-1, +1] |
| Short interest change | FINRA | 2-week change in SI% of float | Short squeeze potential score |
| Options flow | Unusual Whales | Large unusual call/put activity | Smart money direction indicator |
| Earnings surprise momentum | Historical earnings | Post-earnings drift persistence | Drift score for recent reporters |

---

## 6. Layer 3: Strategy & ML Engine

### 6.1 QLib Alpha Model

**Repository:** [microsoft/qlib](https://github.com/microsoft/qlib)

**Purpose:** Predict relative stock returns (alpha) using the full feature set from Layer 2.

**Model architecture:** LightGBM ensemble (fast, handles mixed features well, interpretable via SHAP).

**Feature set (per ticker, daily):**
- All technical indicators from 5.4
- Sentiment scores from 5.2
- LLM conviction scores from 5.3
- Regime label and transition probabilities from 5.5
- Alternative data signals from 5.6
- Sector one-hot encoding
- Market cap quintile
- 20-day realized volatility
- 60-day momentum rank

**Target:** 5-day forward return relative to SPY (cross-sectional alpha).

**Training:**
- Rolling 252-day training window
- QLib's built-in data handler for point-in-time correctness
- Feature importance tracked and fed to AutoResearch journal
- Model retrained weekly (Saturday)

**Output:** Alpha score per ticker, ranked. Top decile = buy candidates, bottom decile = avoid/sell.

### 6.2 FinRL Reinforcement Learning Agent

**Repository:** [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL)

**Purpose:** Learn optimal trading policies — not just what to buy, but when, how much, and when to exit.

**Algorithm:** PPO (Proximal Policy Optimization) — stable, sample-efficient.

**State space:**
- Portfolio holdings (current positions and weights)
- Cash balance
- Alpha scores from QLib (top 20 only)
- Regime label
- Current risk metrics (portfolio beta, sector exposures)
- Days since last rebalance

**Action space (SIMPLIFIED):** Discrete/low-dimensional — NOT continuous weights for 50 stocks.

The original design of 50 continuous target weights is known to be unstable with financial data's low signal-to-noise ratio. Instead, the RL agent makes **portfolio-level allocation decisions**:

```
Simplified Action Space (5 dimensions):
  - equity_allocation: [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]  (% in stocks vs cash)
  - concentration: [10, 15, 20, 25, 30]                   (number of positions)
  - momentum_tilt: [-0.2, -0.1, 0, +0.1, +0.2]           (tilt toward momentum vs value)
  - size_tilt: [-0.2, -0.1, 0, +0.1, +0.2]               (tilt toward small vs large)
  - rebalance_urgency: [skip, partial, full]               (how aggressively to rebalance today)
```

This reduces the action space from 50 continuous dimensions to 5 discrete/low-cardinality dimensions — dramatically more stable and trainable. The RL agent decides "how much" and "what style" while QLib decides "which stocks." This division of labor plays to each model's strengths.

**Fallback:** If the RL agent underperforms a simple risk-parity benchmark after 6 months of paper trading, replace it entirely with Black-Litterman optimization (which is deterministic and well-understood). The ensemble can function without RL.

**Reward function:**

```
reward = portfolio_return 
         - 0.5 * max_drawdown_penalty
         - transaction_cost_penalty
         + diversification_bonus
         - 2.0 * max(0, sector_concentration - 0.25)  # penalize sector overweight
```

**Training environment:** Custom Gym environment built with FinRL, using historical data with realistic:
- Transaction costs (0.1% round trip)
- Slippage (0.05% per trade, volume-dependent)
- Partial fills (orders > 1% of daily volume get partial)
- T+1 settlement

**Retraining:** Monthly, using walk-forward methodology.

### 6.3 Ensemble Decision System

The final trade decision combines all signal sources through a weighted ensemble:

```
Final_Score(ticker) = w_alpha   * QLib_alpha_rank
                    + w_rl      * FinRL_target_weight
                    + w_sent    * sentiment_composite
                    + w_tech    * technical_composite
                    + w_llm     * llm_conviction
                    + w_alt     * alternative_data_composite
```

**Weight constraints:**
- All weights >= 0 (no signal can have negative influence)
- Sum of weights = 1
- No single weight > 0.40 (prevent over-reliance on one signal)

**Weight optimization:** Bayesian optimization via Optuna, run weekly by AutoResearch engine. Objective function is out-of-sample Sharpe ratio with overfitting penalty.

**Regime-conditional weights:** Separate weight vectors for each of the 5 regimes. Example:

| Signal | Bull/Low Vol | Bear/High Vol | Mean-Reverting |
|---|---|---|---|
| QLib Alpha | 0.30 | 0.20 | 0.25 |
| FinRL | 0.25 | 0.15 | 0.20 |
| Sentiment | 0.15 | 0.10 | 0.10 |
| Technical | 0.10 | 0.15 | 0.25 |
| LLM | 0.10 | 0.15 | 0.10 |
| Alt Data | 0.10 | 0.25 | 0.10 |

(These are initial estimates; the AutoResearch engine optimizes them continuously.)

### 6.4 Bull/Bear Adversarial Debate (LLM Decision Gate)

**Inspired by:** [TradingAgents](https://github.com/tauricresearch/tradingagents) — multi-agent debate architecture.

**Purpose:** Before any significant trade executes, force an adversarial debate that surfaces risks a pure numeric score might miss. This mirrors how real trading desks operate: an analyst pitches, a devil's advocate challenges, a PM decides.

**When it triggers:** Only for trades exceeding a significance threshold:
- New positions (any size)
- Position increases > 1% of portfolio
- NOT triggered for: stop-loss exits, routine rebalancing, position trims

**Debate flow:**

```
Ensemble produces: BUY AAPL (score: 0.72, conviction: high)
    │
    ▼
Bull Agent (DeepSeek v4 Pro):
    Input: All signals, fundamentals, sentiment, regime context
    Task: Argue the strongest case FOR this trade
    Output: Bull thesis with catalysts and upside targets
    │
    ▼
Bear Agent (DeepSeek v4 Pro):
    Input: Same data + Bull's thesis
    Task: Argue the strongest case AGAINST this trade
    Output: Bear thesis with risks, red flags, and downside scenarios
    │
    ▼
Judge (DeepSeek R1 — reasoning model):
    Input: Bull thesis + Bear thesis + ensemble score + regime + trade memory
    Task: Adjudicate. Output structured decision:
        - PROCEED (execute as planned)
        - REDUCE (execute at 50% planned size)
        - DEFER (wait 1 day, re-evaluate)
        - REJECT (do not execute)
    Output: Decision + reasoning + key risk to monitor
```

**Two-tier LLM pattern:** The Bull/Bear agents use the cheap fast model (DeepSeek v4 Pro) to argue. The Judge uses a reasoning model (DeepSeek R1) to decide. This mirrors the TradingAgents insight: cheap models argue, expensive models judge.

**Cost impact:** ~3-5 debate triggers per day × ~$0.005/debate = ~$0.50/mo. Negligible.

**What this adds over pure ensemble scoring:**
- Forces explicit articulation of WHY a trade is good/bad (not just a number)
- Surfaces qualitative risks (e.g., "CEO just resigned" or "earnings in 2 days") that numeric signals may not capture
- Creates an auditable decision trail with reasoning
- The Judge can override the ensemble if the Bear case is compelling enough

**Configurable aggressiveness:**
```yaml
debate:
  enabled: true
  trigger_threshold: 0.01  # 1% of portfolio
  max_override_rate: 0.30  # Judge can reject max 30% of trades per week (prevents over-caution)
  judge_model: "deepseek-r1"
  debater_model: "deepseek-v4-pro"
```

### 6.4.1 Philosophy-Grounded Debate Scoring

**Inspired by:** [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) — persona-based investor agents (Buffett, Munger, Burry, Taleb, etc.).

**What we deliberately did NOT adopt:** ai-hedge-fund runs 13 separate LLM personas (Buffett, Munger, Cathie Wood, Burry, Taleb, Druckenmiller, etc.) as fully independent agents, each making its own LLM call per ticker. We rejected this wholesale — it triples-to-13x's LLM cost for diversification benefit we already get more rigorously from QLib's cross-sectional factor model, FinBERT sentiment, and the technical composite. Running 13 LLM personas to approximate what a quantitative factor model already does well is expensive theater.

**What we DID extract:** Their most valuable technique is grounding each persona's LLM reasoning in **deterministic Python sub-scores** computed BEFORE the LLM call, so the model reasons over concrete numbers instead of free-associating from raw data. This measurably reduces hallucination. We apply this single technique to sharpen our existing Bull/Bear debate (6.4) rather than building a persona zoo.

**Implementation:** The Bull and Bear agents each receive a pre-computed checklist score instead of raw fundamentals, computed in pure Python (no LLM, near-zero cost):

```python
# Bull checklist (quality + growth lens — Buffett/Lynch-inspired)
bull_checklist = {
    "roe_score":            2 if roe > 0.15 else 0,
    "debt_to_equity_score": 2 if debt_to_equity < 0.5 else 0,
    "margin_stability_score": score_margin_consistency(gross_margins_5y),
    "moat_score":            score_roe_consistency(roe_5y),  # consistent high ROE = durable moat
    "earnings_growth_score": 2 if eps_growth_3y > 0.10 else 0,
    "insider_buying_score":  2 if net_insider_buys_90d > 0 else 0,
}
bull_total = sum(bull_checklist.values())  # out of 12

# Bear checklist (contrarian + tail-risk lens — Burry/Taleb-inspired)
bear_checklist = {
    "fcf_yield_score":       score_fcf_yield_bucket(fcf_yield),       # cheap on FCF = risk already priced in? or value trap?
    "ev_ebit_score":         score_ev_ebit_bucket(ev_ebit),
    "insider_selling_score": 2 if net_insider_buys_90d < 0 else 0,
    "negative_news_score":   score_recent_negative_news(news_30d),
    "tail_risk_score":       score_kurtosis_and_max_drawdown(returns_252d),  # fat tails / large historical DD
    "vol_regime_score":      2 if realized_vol_60d > historical_vol_pct_80 else 0,  # "turkey problem" — calm before storm
}
bear_total = sum(bear_checklist.values())  # out of 12
```

These checklist totals (not raw data) are injected into the Bull/Bear prompts:

```
Bull Agent prompt: "Quality/growth checklist score: 9/12 (strong ROE consistency,
low leverage, positive insider buying). Build the strongest bull case using
these facts plus the signals provided. Cite the checklist explicitly."

Bear Agent prompt: "Contrarian/tail-risk checklist score: 7/12 (elevated realized
vol vs 80th percentile, EV/EBIT in expensive bucket). Build the strongest bear
case using these facts plus the signals provided. Cite the checklist explicitly."
```

**Why this matters:** The Judge (DeepSeek R1) now adjudicates between two arguments that are each anchored to specific, auditable numbers — not vibes. If the Bull claims "strong fundamentals" but the checklist score is 3/12, the Judge can catch the inconsistency. This is the single highest-leverage idea from ai-hedge-fund, extracted without importing its cost structure.

**Cost impact:** The checklist scoring is pure Python — $0. No change to debate LLM costs (same Bull/Bear/Judge calls as 6.4, just better-grounded prompts).

### 6.5 Trade Decision Memory

**Inspired by:** TradingAgents' deferred reflection with outcome tracking.

**Purpose:** Build per-ticker institutional memory that prevents the system from repeating mistakes and reinforces patterns that work.

**Two-phase lifecycle:**

```
Phase A — At trade time:
    Record: {ticker, date, action, signals_snapshot, debate_summary, regime}
    Status: PENDING

Phase B — 5 trading days later (automated):
    Fetch: actual 5-day return, alpha vs SPY
    Generate: 2-3 sentence reflection (DeepSeek v4 Pro)
        "Bought AAPL at $198 based on earnings beat + sentiment surge.
         Result: +3.2% (alpha: +1.8%). Thesis held — services revenue 
         was the catalyst as predicted. Lesson: post-earnings sentiment
         momentum is reliable for AAPL in bull regimes."
    Status: RESOLVED
```

**Memory injection into future decisions:**

When the system is about to trade a ticker, it retrieves:
- Last 5 resolved decisions for this specific ticker
- Last 3 cross-ticker lessons from similar setups (same regime + similar signal profile)

This context is injected into the Bull/Bear debate Judge's prompt, giving it institutional knowledge like:
- "Last time you bought AAPL before earnings, it gapped down 4%"
- "Sentiment-driven buys in high-vol regime have 35% win rate historically"

**Storage:** PostgreSQL table `trade_memory`:

```sql
CREATE TABLE trade_memory (
    id              SERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    trade_date      DATE NOT NULL,
    action          TEXT NOT NULL,       -- buy/sell
    entry_price     NUMERIC(12, 4),
    signals         JSONB,              -- snapshot at decision time
    debate_summary  TEXT,               -- condensed bull/bear/judge reasoning
    regime          TEXT,
    status          TEXT DEFAULT 'pending',  -- pending / resolved
    actual_return_5d NUMERIC(8, 6),
    alpha_vs_spy_5d NUMERIC(8, 6),
    reflection      TEXT,               -- LLM-generated lesson
    resolved_date   DATE
);
CREATE INDEX idx_trade_memory_ticker ON trade_memory(ticker, trade_date DESC);
```

**Cost impact:** ~20 reflections/month × ~$0.001/reflection = ~$0.02/mo. Essentially free.

### 6.6 Data Vendor Failover

**Inspired by:** TradingAgents' vendor routing with automatic fallback.

**Purpose:** If a primary data source fails (rate limit, outage, timeout), seamlessly fall back to an alternative without halting the pipeline.

**Implementation:**

```python
VENDOR_PRIORITY = {
    "price_daily": ["alpaca", "polygon", "yfinance"],
    "price_realtime": ["alpaca"],  # no fallback for real-time
    "fundamentals": ["yfinance", "polygon"],
    "news": ["rss_feeds", "yfinance_news"],
    "macro": ["fredapi"],
    "sec_filings": ["sec_edgar"],
}

def fetch_with_failover(category: str, ticker: str, **kwargs):
    for vendor in VENDOR_PRIORITY[category]:
        try:
            result = VENDOR_REGISTRY[vendor].fetch(ticker, **kwargs)
            if result.is_valid():
                return result
        except (RateLimitError, TimeoutError, APIError) as e:
            log.warning(f"{vendor} failed for {ticker}: {e}, trying next")
            continue
    raise AllVendorsFailedError(category, ticker)
```

**Added to data quality watchdog:** Track per-vendor failure rates. If a vendor fails >20% of calls in a day, temporarily deprioritize it.

---

## 7. Layer 4: Backtesting & Validation Engine

This layer is the quality gate. No strategy, model change, or AutoResearch improvement reaches production without passing through this pipeline.

### 7.0 Event-Study Pre-Screen (Gate 0)

**Inspired by:** [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) `v2/event_study/` — a classical event-study framework (market-model OLS, abnormal returns, CAR, t-test, bootstrap CI) used to validate their Post-Earnings-Announcement-Drift (PEAD) strategy. Notably, this module is one of the few genuinely complete, well-tested pieces in their `v2/` rewrite, while their CPCV/PBO/risk-manager/optimizer modules are still empty stubs.

**Purpose:** Before AutoResearch spends compute running a hypothesis through the full 6-gate validation pipeline (which can take 20+ minutes per experiment), run a 30-second statistical pre-screen specifically for **catalyst-driven hypotheses** (earnings surprises, insider buying clusters, analyst rating changes, M&A announcements). If the catalyst shows no statistically significant abnormal return historically, reject the hypothesis immediately — don't waste a full validation run on it.

**When it applies:** Only to hypotheses with a discrete, dateable catalyst (not continuous signals like RSI or sentiment momentum, which go straight to the existing 6-gate pipeline).

**Method:**

```
1. Market-model fit (OLS):
   r_i,t = alpha_i + beta_i * r_market,t + epsilon_i,t
   Fit over a clean estimation window (e.g., [-252, -30] days before catalyst)

2. Abnormal return per event:
   AR_i,t = r_i,t - (alpha_i + beta_i * r_market,t)
   Computed for the event window (e.g., [-1, +5] days around catalyst date)

3. Cumulative Abnormal Return (CAR):
   CAR_i = sum(AR_i,t for t in event_window)

4. Statistical significance:
   One-sample t-test: is mean(CAR) across all historical events != 0?
   Percentile bootstrap CI (10,000 resamples) on mean CAR

5. Pass condition:
   - t-test p-value < 0.05
   - Bootstrap 95% CI excludes zero
   - Effect size (mean CAR) is economically meaningful (> transaction cost * 2)
```

**Pass → proceed to full Section 7.1-7.3 pipeline (walk-forward + 6 gates).**
**Fail → reject immediately, log to research journal as "failed event-study pre-screen," do not consume a full validation run.**

**Cost/time savings:** This pre-screen runs in seconds (pure `statsmodels`/`scipy` computation, no LLM, no full backtest engine) versus 20+ minutes for the complete walk-forward + CPCV pipeline. For AutoResearch's ~20 experiments/week, catching obviously-insignificant catalyst hypotheses here saves significant compute and keeps the 6-gate pipeline focused on hypotheses that already show basic statistical merit.

**Seeded starter strategy — Post-Earnings-Announcement-Drift (PEAD):**

ai-hedge-fund's v2 ships a concrete, well-documented implementation of PEAD (long post-beat, short post-miss, with careful filing-date/report-period deduplication to avoid double-counting the same earnings event). PEAD is a well-established academic anomaly (returns drift in the direction of an earnings surprise for ~60 days post-announcement). We seed this as experiment `exp_0001` in the AutoResearch journal at launch — pre-validated via the event-study pre-screen, then run through the full 6-gate pipeline before deployment. This gives AutoResearch a credible, well-understood starting point rather than beginning from zero.

### 7.1 Dual-Engine Backtesting Framework

Two backtesting engines serve different purposes:

**Engine 1: vectorbt (Fast Screening)**
- Vectorized, 100x faster than event-driven
- Used for: rapid alpha feature screening, initial hypothesis testing, CPCV combinatorial runs
- Limitation: assumes execution at bar close/OHLC — cannot simulate limit-order escalation logic
- Role: Phase 1 of validation (does the signal even have edge?)

**Engine 2: Custom Event-Driven Backtester (Execution Fidelity)**
- Lightweight event loop simulating the actual order router logic
- Used for: final validation of strategies that pass vectorbt screening
- Simulates: limit → adjust → aggressive limit escalation, partial fills, queue position
- Role: Phase 2 of validation (does the edge survive realistic execution?)

A strategy must pass BOTH engines. vectorbt gates access to the more expensive event-driven engine.

**Realistic simulation requirements (both engines):**

| Simulation Parameter | Setting |
|---|---|
| Transaction costs | 0.1% round trip (spread + slippage) |
| Market impact | Square-root model: impact = k * sqrt(trade_size / daily_volume) |
| Partial fills | Orders > 1% daily volume filled proportionally |
| Execution latency | 1-second delay simulated |
| Data | Survivorship-bias-free (includes delisted stocks) |
| Point-in-time | Strict — no lookahead on any data source |
| Benchmark | SPY total return (dividends reinvested) |
| Corporate actions | All splits/dividends back-adjusted (see Layer 1 Corp Actions Handler) |

### 7.2 Walk-Forward Analysis

The primary validation methodology. Prevents "great backtest, terrible live" outcomes.

```
Time ──────────────────────────────────────────────────────────►

Window 1:  [======= Train (252d) =======][== Test (63d) ==]
Window 2:       [======= Train (252d) =======][== Test (63d) ==]
Window 3:            [======= Train (252d) =======][== Test (63d) ==]
Window 4:                 [======= Train (252d) =======][== Test (63d) ==]
...
Window N:                                    [======= Train =======][= Test =]
                                                                      ↓
                                              Concatenate ALL test periods
                                              → This is the "true" performance
```

**Parameters:**

| Parameter | Value | Rationale |
|---|---|---|
| Training window | 252 trading days (1 year) | Captures seasonality and at least 4 earnings cycles |
| Test window | 63 trading days (1 quarter) | Long enough for statistical significance |
| Step size | 21 trading days (1 month) | Provides sufficient overlapping windows |
| Minimum windows | 12 | Requires 3+ years of history |
| Anchored variant | Also tested | Expanding-window version for comparison |

**Pass criteria:**
- Concatenated out-of-sample Sharpe > 0.5
- Positive returns in > 60% of test windows
- No single test window with drawdown > 20%

### 7.3 Overfitting Detection Suite

Six statistical gates. ALL must pass before any strategy reaches production.

#### Gate 1: Combinatorial Purged Cross-Validation (CPCV)

**Reference:** De Prado, "Advances in Financial Machine Learning" (2018)

**Method:**
1. Partition the dataset into N groups (N=10)
2. Generate all C(N, k) combinations of train/test splits
3. Apply purging: remove training observations that immediately precede test observations (embargo period = 5 trading days)
4. Run strategy on each combination
5. Measure win rate across all paths

**Pass condition:** Strategy profitable in >= 60% of combinatorial paths.

**Why purging matters:** Without it, autocorrelation in financial returns causes train/test leakage, inflating apparent performance.

#### Gate 2: Deflated Sharpe Ratio (DSR)

**Reference:** Bailey & Lopez de Prado (2014)

**Method:**
1. Track all strategies ever tested (including by AutoResearch)
2. The more strategies tested, the higher the bar for statistical significance
3. DSR adjusts the Sharpe ratio for: number of strategies tried, skewness, kurtosis of returns

**Formula:**

```
DSR = Φ^(-1)(1 - e * Φ(-IS_expected))

Where:
  IS_expected = expected max Sharpe given number of trials
  e = number of independent strategies tested
  Φ = standard normal CDF
```

**Pass condition:** DSR p-value < 0.05 (the strategy's Sharpe is unlikely to be a product of multiple testing).

#### Gate 3: Probability of Backtest Overfitting (PBO)

**Reference:** Bailey et al. (2015)

**Method:**
1. Partition backtest period into S equal sub-periods (S=16)
2. Form all C(S, S/2) combinations of in-sample (IS) and out-of-sample (OOS) halves
3. For each combination: find the optimal strategy IS, measure its rank OOS
4. PBO = fraction of combinations where the IS-optimal strategy underperforms the median OOS

**Pass condition:** PBO < 0.30 (less than 30% probability of overfitting).

#### Gate 4: White's Reality Check / SPA Test

**Reference:** Hansen (2005) — Superior Predictive Ability test

**Method:**
1. Define null hypothesis: best strategy has no predictive ability beyond random
2. Bootstrap (10,000 iterations) the distribution of maximum performance under the null
3. Compare actual best performance to this null distribution

**Pass condition:** SPA p-value < 0.05 (the best strategy significantly outperforms random).

#### Gate 5: Parameter Stability

**Method:**
1. Define a grid of strategy parameters (e.g., lookback windows, thresholds, weight ranges)
2. Compute Sharpe ratio for every grid point
3. Generate a heatmap of performance across parameter space
4. Compute stability score: fraction of grid points within 20% of center that have Sharpe > 0.5

**Pass condition:** Stability score >= 0.70 (performance is robust to small parameter changes — no sharp cliffs).

#### Gate 6: Regime Robustness

**Method:**
1. Label each historical day with its regime (from HMM in 5.5)
2. Compute strategy Sharpe ratio within each regime independently
3. Count regimes where Sharpe > 0 (strategy is at least not destructive)

**Regimes tested:** Bull/Low Vol, Bull/High Vol, Bear/Low Vol, Bear/High Vol, Mean-Reverting

**Pass condition:** Sharpe > 0 in at least 3 of 5 regimes. A strategy that only works in bull markets is just leveraged beta.

### 7.4 Validation Scorecard

Every strategy/change produces a scorecard:

```json
{
    "strategy_id": "exp_0042_credit_spread",
    "timestamp": "2026-05-16T20:00:00Z",
    "walk_forward": {
        "oos_sharpe": 0.82,
        "win_rate_windows": 0.75,
        "max_window_drawdown": -0.08,
        "passed": true
    },
    "cpcv": {
        "win_rate": 0.67,
        "n_paths": 252,
        "passed": true
    },
    "deflated_sharpe": {
        "raw_sharpe": 1.12,
        "deflated_sharpe": 0.78,
        "p_value": 0.023,
        "strategies_tested": 87,
        "passed": true
    },
    "pbo": {
        "probability": 0.18,
        "n_partitions": 16,
        "passed": true
    },
    "spa_test": {
        "p_value": 0.012,
        "bootstrap_iterations": 10000,
        "passed": true
    },
    "parameter_stability": {
        "stability_score": 0.83,
        "grid_dimensions": [20, 20],
        "passed": true
    },
    "regime_robustness": {
        "regime_sharpes": {
            "bull_low_vol": 1.2,
            "bull_high_vol": 0.4,
            "bear_low_vol": 0.3,
            "bear_high_vol": -0.1,
            "mean_reverting": 0.6
        },
        "positive_regimes": 4,
        "passed": true
    },
    "overall_passed": true
}
```

---

## 8. Layer 5: Portfolio & Risk Management

### 8.1 Position Sizing — Constrain-Then-Delegate Pattern

**Inspired by:** [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) — risk_manager → portfolio_manager pipeline.

**Core idea:** Compute the legal position ceiling in pure Python BEFORE the ensemble, RL agent, or debate gate ever runs. The downstream decision-making layers (ensemble, FinRL, Bull/Bear debate) can only choose a size WITHIN this pre-computed legal range — they are structurally incapable of violating risk limits, rather than being checked/clipped after the fact. This is more robust than "decide then clip," because no decision path (including future AutoResearch-introduced ones) can bypass it.

**Step 1: Volatility-tiered base cap**

```python
def volatility_tier_cap(realized_vol_60d_annualized: float) -> float:
    if realized_vol_60d_annualized < 0.15:
        return 0.05   # max_position_pct ceiling (5%)
    elif realized_vol_60d_annualized < 0.25:
        return 0.04
    elif realized_vol_60d_annualized < 0.35:
        return 0.03
    elif realized_vol_60d_annualized < 0.50:
        return 0.02
    else:
        return 0.01   # high-vol names get a much smaller max allocation
```

**Step 2: Correlation multiplier (dampens or boosts the base cap)**

```python
def correlation_multiplier(avg_corr_with_holdings: float) -> float:
    if avg_corr_with_holdings >= 0.80:
        return 0.70   # shrink cap up to 30% — too similar to existing exposure
    elif avg_corr_with_holdings <= 0.20:
        return 1.10   # grow cap up to 10% — genuine diversification benefit
    else:
        # linear interpolation between the two anchors
        return 1.10 - (avg_corr_with_holdings - 0.20) / (0.80 - 0.20) * (1.10 - 0.70)
```

**Step 3: Legal ceiling (computed once per ticker, per day, before any LLM/RL call)**

```python
position_limit_pct = volatility_tier_cap(ticker_vol_60d) * correlation_multiplier(avg_corr)
max_dollar_position = position_limit_pct * portfolio_value
max_shares = floor(min(max_dollar_position, available_cash) / current_price)
```

**Step 4: Downstream decision happens within [0, max_shares]**

```
Ensemble score, FinRL target weight, and Bull/Bear debate Judge ALL operate
on the pre-clipped legal range. The final size is:

    target_shares = round(ensemble_final_score(ticker) * max_shares)

The ensemble/RL/debate layers choose CONVICTION (how much of the legal
room to use), never the ceiling itself. Tickers where max_shares == 0
(cap already filled, correlation too high, or insufficient cash) skip
the debate gate entirely — see 8.1.1 cost optimization below.
```

**Volatility targeting (portfolio-level, applied after per-ticker caps):**

```python
target_annual_vol = 0.15  # 15% portfolio volatility target
portfolio_scalar = target_annual_vol / portfolio_realized_vol_60d
final_weight = ticker_weight_from_step_4 * portfolio_scalar  # still respects max_shares ceiling
```

### 8.1.1 Cost Optimization — Skip Forced-HOLD Tickers

**Inspired by:** ai-hedge-fund's pattern of pre-filling decisions where the only legal action is "hold," skipping the LLM call entirely.

If `max_shares == 0` for a ticker (already at position cap, correlation too high, or insufficient cash), there is no legal action other than hold. The system skips:
- The Bull/Bear debate gate (6.4) — no decision to debate
- LLM holdings analysis (5.3) for that ticker that day — re-use the prior day's analysis

This directly reduces the ~50 LLM calls/day estimate in Section 5.3 by filtering out tickers with no legal trading room, with zero loss of decision quality (there's nothing to decide).

### 8.2 Risk Limits (Hard Rules)

| Rule | Limit | Action on Breach |
|---|---|---|
| Max single position | 5% of portfolio | Trim excess immediately |
| Max sector weight | 25% of portfolio | Reject new same-sector positions |
| Daily portfolio drawdown | -3% | Halt all new trades for the day |
| Weekly portfolio drawdown | -5% | Reduce all positions by 50%, enter review mode |
| Max total drawdown | -15% | Liquidate to cash, halt system, require manual restart |
| Max correlated positions | No pair with correlation > 0.80 | Reject the less-alpha position |
| Max portfolio beta | 1.3 | Reduce highest-beta positions |
| Min cash reserve | 10% of portfolio | Reject new positions if cash too low |

### 8.3 Portfolio Optimization

**Library:** `PyPortfolioOpt`

After the ensemble produces target weights, the optimizer adjusts them to minimize risk for the given return target.

**Methods available:**
- Mean-variance optimization (Markowitz)
- Black-Litterman (using ensemble scores as "views")
- Risk parity (equal risk contribution per position)
- Hierarchical Risk Parity (HRP) — robust to estimation error

**Default:** Black-Litterman, as it naturally incorporates the ensemble's alpha predictions as views while maintaining a market-cap-weighted prior.

### 8.4 Correlation & Crowding Monitor

- Compute portfolio correlation to standard factor indices (Momentum, Value, Quality, Low Vol, Size)
- If portfolio correlation to any single factor > 0.70, flag for review and reduce exposure
- Track factor crowding metrics to avoid being caught in unwind events

### 8.5 Tax-Aware Trading (Wash Sale Prevention)

**Problem this solves:** The IRS Wash Sale Rule disallows tax deductions on losses if you buy a "substantially identical" security within 30 days before or after the sale. With daily rebalancing across 1,400 stocks, the system can easily trigger wash sales accidentally — resulting in taxable gains without offsetting losses, even if the portfolio lost money overall.

**Wash Sale Detection Logic:**

```
Before executing any SELL at a loss:
    1. Check: was this ticker (or substantially identical ETF) bought in last 30 days?
    2. Check: is there a pending BUY signal for this ticker in the next 30 days?
       (based on current alpha score trajectory)
    3. If wash sale would be triggered:
        a. Calculate: tax_penalty = disallowed_loss * marginal_tax_rate
        b. Calculate: alpha_benefit = expected_return_from_trade * position_size
        c. If alpha_benefit > tax_penalty * 1.5:
            → Execute trade anyway (alpha strongly overrides tax cost)
            → Log as "intentional wash sale — alpha justified"
        d. Else:
            → BLOCK the sell, defer to day 31
            → Or: sell and do NOT repurchase within 30 days (one-way exit)
```

**Tax-Lot Tracking:**
- Every purchase creates a new tax lot with: date, cost basis, quantity
- FIFO (First-In-First-Out) is the default accounting method
- System tracks holding period: <1 year = short-term gains (taxed as income), >1 year = long-term gains (lower rate)
- When possible, prefer selling long-term lots over short-term lots (tax efficiency)

**Substantially Identical Securities:**
- Maintain a mapping of tickers to their "substantially identical" counterparts (e.g., SPY ↔ IVV ↔ VOO)
- Wash sale check applies across the entire equivalence group, not just the same ticker

**Annual Tax Optimization:**
- In December, run tax-loss harvesting scan: identify positions with unrealized losses that could offset realized gains
- Suggest swaps (e.g., sell AAPL at a loss, buy MSFT as a non-identical substitute) to harvest losses while maintaining market exposure
- Never sacrifice significant alpha purely for tax optimization — alpha always has priority

### 8.6 Cost-Aware Rebalancing

Not every signal change warrants a trade. Rebalancing only occurs when:

```
|target_weight - current_weight| > rebalance_threshold

Where:
    rebalance_threshold = max(0.5%, estimated_round_trip_cost * 3)
```

This prevents excessive turnover from small signal fluctuations.

---

## 9. Layer 6: Execution Engine

### 9.1 Broker Integration — Alpaca

**API:** [alpaca.markets](https://alpaca.markets)
**SDK:** `alpaca-trade-api` (Python)

**Account types:**
- Paper trading account (Phase 5 validation)
- Live trading account (Phase 8 onward)

**Supported order types:**
- Limit orders (default — placed at mid-price)
- Aggressive limit orders (marketable limit at ask + buffer)
- IOC (Immediate-or-Cancel) limit orders
- Stop orders (for stop-loss implementation)
- Trailing stop orders (for trailing stop-loss)
- **NEVER pure market orders** — even urgent liquidations use aggressive limits

### 9.2 Smart Order Routing

**Critical design decision:** No market orders for automated rebalancing. A market order on a $500M market-cap stock during volatility can sweep a thin order book and destroy alpha. Instead, we use an **aggressive limit escalation** pattern.

```
1. Calculate target position change
2. Check if change exceeds rebalance threshold (from 8.5)
3. If yes:
    a. Place limit order at mid-price
    b. Wait 30 seconds
    c. If not filled, cancel and place aggressive limit at ask + 0.05%
    d. Wait 60 seconds
    e. If still not filled, place IOC limit at ask + 0.10%
    f. If IOC partially fills or misses entirely:
       - Log the shortfall
       - If remaining qty < 20% of original, accept partial fill
       - If remaining qty >= 20%, retry next bar (do NOT chase)
    g. Log fill quality (slippage vs expected)
4. If no:
    Skip trade, log decision
5. Emergency liquidation (drawdown halt):
    Aggressive limit at ask + 0.15%, IOC — accept whatever fills
    STILL no pure market orders
```

**Why no market orders:** For a $100K portfolio, a 5% position is $5,000. On a stock near the $500M market cap floor during volatility, a market order can experience 0.5-1.0% slippage — wiping out weeks of alpha on a single fill.

### 9.3 Execution Monitoring

| Metric | Logged | Alert Threshold |
|---|---|---|
| Fill price vs expected | Every trade | Slippage > 0.2% |
| Partial fill rate | Every trade | > 30% partial |
| Order rejection rate | Every trade | Any rejection |
| Execution latency | Every trade | > 5 seconds |
| Daily turnover | Daily | > 30% portfolio |

### 9.4 Trade Journal

Every executed trade is logged with full context:

```json
{
    "trade_id": "t_20260516_001",
    "timestamp": "2026-05-16T14:32:15Z",
    "ticker": "AAPL",
    "side": "buy",
    "quantity": 15,
    "order_type": "limit",
    "limit_price": 198.50,
    "fill_price": 198.52,
    "slippage_bps": 1.0,
    "signals_at_time": {
        "qlib_alpha": 0.72,
        "finrl_weight": 0.035,
        "sentiment": 0.42,
        "technical": 0.31,
        "llm_conviction": 0.65,
        "regime": "bull_low_vol"
    },
    "risk_at_time": {
        "portfolio_drawdown": -0.8,
        "position_weight_after": 3.2,
        "sector_weight_after": 18.5
    },
    "rationale": "Strong alpha rank (top decile), positive sentiment momentum, LLM bullish on services growth..."
}
```

---

## 10. Layer 7: AutoResearch Engine

The self-improving brain of the system. Runs autonomously, continuously seeking improvements to strategy, signals, and weights.

### 10.1 Core Loop

```
┌─────────────────────────────────────────────────────────────┐
│                    AUTORESEARCH CYCLE                        │
│                                                             │
│  1. OBSERVE                                                 │
│     │  Read research journal (what's been tried)            │
│     │  Analyze recent portfolio performance                  │
│     │  Identify weaknesses (drawdown periods, regime gaps)   │
│     │  Scan for new academic papers / ideas                  │
│     ▼                                                       │
│  2. HYPOTHESIZE                                             │
│     │  LLM generates 3-5 testable hypotheses                │
│     │  Each hypothesis is specific and measurable            │
│     ▼                                                       │
│  3. IMPLEMENT                                               │
│     │  LLM writes code for new indicator/feature/model mod  │
│     │  Code is sandboxed and linted                         │
│     ▼                                                       │
│  4. BACKTEST & VALIDATE                                     │
│     │  Full Layer 4 pipeline (walk-forward + 6 gates)       │
│     │  Compare vs current baseline                          │
│     ▼                                                       │
│  5. ANALYZE                                                 │
│     │  LLM reviews results, writes analysis                 │
│     │  Determine: deploy / iterate / abandon                │
│     ▼                                                       │
│  6. LEARN & JOURNAL                                         │
│     │  Record everything in research journal                │
│     │  Update experiment graph (which ideas led where)       │
│     │  Feed successful changes into production (with burn-in)│
│     └──→ Back to step 1                                     │
└─────────────────────────────────────────────────────────────┘
```

### 10.2 Hypothesis Generation

The LLM (DeepSeek v4 Pro — at $0.435/M input tokens, AutoResearch costs ~$1/mo) generates hypotheses by synthesizing:

**Inputs:**
- Research journal: all past experiments, their outcomes, and learnings
- Performance attribution: which signals contributed most/least to recent returns
- Regime analysis: where is the system underperforming?
- Feature importance: SHAP values from QLib model — which features are losing power?
- Academic literature: new papers from arXiv quantitative finance

**Hypothesis categories:**

| Category | Example | Typical Frequency |
|---|---|---|
| New indicator | "Intraday volume profile skewness may predict next-day returns" | 3-4 per week |
| Feature engineering | "Interaction term: RSI * sentiment_delta may capture momentum confirmation" | 2-3 per week |
| Model architecture | "Replacing LightGBM with TabNet for non-linear feature selection" | 1-2 per month |
| Weight optimization | "Regime 4 (bear/high vol) should weight alt_data higher based on recent analysis" | Weekly |
| Signal decay | "RSI signal should use 10-period instead of 14 based on autocorrelation analysis" | 1-2 per month |
| Data source | "Adding congressional trading data (STOCK Act disclosures) as new signal" | Monthly |

**Hypothesis format:**

```yaml
hypothesis_id: hyp_0042
date: 2026-05-16
category: new_indicator
description: >
  Credit spread (HY OAS - IG OAS) as a risk-off regime detector.
  Hypothesis: widening credit spreads precede equity drawdowns by 3-5 days.
  Adding this as a feature to the QLib model should improve bear-market detection.
testable_prediction: >
  QLib model with credit spread feature will have:
  - Higher Sharpe in Bear/High Vol regime (currently -0.1, target > 0.2)
  - No degradation in other regimes (Sharpe change > -0.05)
  - Overall portfolio Sharpe improvement > +0.05
data_requirements:
  - ICE BofA HY OAS (available via FRED)
  - ICE BofA IG OAS (available via FRED)
estimated_complexity: low
related_experiments: [exp_0031, exp_0033]
```

### 10.3 Experiment Runner

For each approved hypothesis:

1. **Code generation:** The LLM writes a self-contained Python module implementing the indicator/feature/change. Code is:
   - Linted (`ruff`)
   - Type-checked (`mypy`)
   - Unit tested (the LLM also generates tests)
   - Sandboxed (runs in isolated environment, cannot affect production)

2. **Gate 0 pre-screen (catalyst hypotheses only):** If the hypothesis involves a discrete catalyst (earnings, insider clusters, rating changes), run the event-study pre-screen (Section 7.0) first. Takes seconds. If it fails (no statistically significant abnormal return), reject immediately — skip step 3 entirely and save the compute.

3. **Backtest execution:** The full Layer 4 validation pipeline runs:
   - Walk-forward analysis
   - All 6 overfitting gates
   - Comparison vs current production baseline

4. **Result recording:** Everything is saved to the experiment directory.

**Seeded starter experiment:** `exp_0001` is pre-populated at launch with Post-Earnings-Announcement-Drift (PEAD), validated via Gate 0 + the full pipeline (see 7.0). This gives AutoResearch a credible, academically-documented starting point in the research journal rather than beginning from an empty history.

**Experiment directory structure:**

```
experiments/
├── exp_0001_pead/                  # Seeded starter strategy (7.0)
│   ├── hypothesis.yaml
│   ├── event_study_results.json    # Gate 0 pre-screen output
│   ├── feature_code.py
│   ├── backtest_results.json
│   ├── validation_scorecard.json
│   └── verdict.yaml
├── exp_0042_credit_spread/
│   ├── hypothesis.yaml          # The original hypothesis
│   ├── feature_code.py          # Implementation
│   ├── test_feature.py          # Unit tests
│   ├── backtest_config.yaml     # Backtest parameters
│   ├── backtest_results.json    # Full performance metrics
│   ├── validation_scorecard.json # 6-gate results
│   ├── comparison.json          # vs baseline comparison
│   ├── analysis.md              # LLM-written analysis
│   └── verdict.yaml             # DEPLOY / ITERATE / ABANDON
```

### 10.4 Promotion Pipeline (HITL Git Gate)

Successful experiments don't go straight to live trading. A **Human-in-the-Loop Git Gate** ensures no AI-generated code reaches production without human review.

```
Experiment passes all 6 gates
    │
    ▼
Stage 0: GitHub Pull Request (HUMAN REVIEW)
    System auto-creates a PR with:
      - Validation scorecard (all 6 gates)
      - Code diff (the new indicator/feature/model change)
      - Backtest comparison vs baseline
      - LLM-written analysis summary
    Human reviews on phone/laptop, clicks "Merge" to approve.
    NO deployment happens without merge.
    │
    ▼
Stage 1: Shadow mode (30 days)
    Signal is computed but NOT used in trading decisions.
    Track what WOULD have happened if included.
    │
    ▼
Stage 2: Low-weight paper trade (30 days)
    Added to ensemble with 50% of target weight.
    Paper trading only.
    │
    ▼
Stage 3: Full-weight paper trade (30 days)
    Added at full target weight.
    Paper trading.
    │
    ▼
Stage 4: Live deployment
    Promoted to live with monitoring.
    Auto-rollback if Sharpe drops > 0.3 within 2 weeks.
```

**Why the Git Gate matters:** Full autonomy for AI to generate code and deploy to live money is high-risk. The PR gate preserves 99% of automation (hypothesis → experiment → validation is fully autonomous) while preventing catastrophic code hallucinations from reaching production. Reviewing a PR takes <5 minutes — a negligible human cost for significant safety improvement.

### 10.5 Weight Optimization Cycle

Runs weekly (Saturday/Sunday when markets are closed):

```
1. Collect 90-day signal attribution data
   - For each signal: standalone Sharpe, marginal contribution, decay curve

2. For each regime:
   - Compute regime-conditional signal performance
   - Identify signals that are helping vs hurting in that regime

3. Run Bayesian optimization (Optuna, 500 trials):
   - Objective: out-of-sample Sharpe (walk-forward validated)
   - Constraints: weight bounds, no single weight > 0.40
   - Separate optimization per regime

4. Validate new weights:
   - Walk-forward analysis with new weights
   - Overfitting gates must still pass
   - Sharpe improvement must be > 0.05 (meaningful, not noise)

5. If validated:
   - Deploy new weights to paper trading
   - After 2-week burn-in with positive results, promote to live
   
6. If not validated:
   - Log the attempt and learnings
   - Keep current weights
```

### 10.6 Research Journal

A persistent, structured knowledge base that prevents the system from:
- Repeating failed experiments
- Losing institutional knowledge about what works and why
- Drifting into strategies it has already proven don't work

**Journal entry format:**

```yaml
id: exp_0042
date: 2026-05-16
hypothesis_id: hyp_0042
category: new_indicator
description: "Credit spread (HY-IG) as risk-off regime detector"
result: SUCCESS  # SUCCESS / PARTIAL / FAILURE / ABANDONED

performance:
  sharpe_baseline: 0.95
  sharpe_with_change: 1.07
  sharpe_delta: +0.12
  max_drawdown_delta: -0.8%  # negative = improvement
  turnover_impact: +2.1%     # additional annual turnover

validation:
  walk_forward_passed: true
  cpcv_win_rate: 0.67
  deflated_sharpe_pval: 0.023
  pbo: 0.18
  spa_pval: 0.012
  param_stability: 0.83
  regime_robustness: 4  # out of 5

deployment:
  deployed: true
  deployed_date: 2026-06-20
  current_weight: 0.08
  promotion_stage: live

learnings: >
  Credit spread is a strong leading indicator for risk-off moves.
  Works best 3-5 days before equity drawdowns.
  Signal is noisy during low-vol bull markets but doesn't hurt.
  HY OAS alone is nearly as good as HY-IG spread — simpler is better.

related_experiments:
  - exp_0031: "VIX term structure as regime detector — partial success"
  - exp_0033: "Treasury yield curve — failed, too slow"
  
tags: [macro, regime, risk_off, credit]
```

### 10.7 AutoResearch Guardrails

| Guardrail | Rule | Rationale |
|---|---|---|
| Max experiments per week | 20 | Prevent compute waste and thrashing |
| Max concurrent live changes | 1 | Isolate impact of each change (A/B testing) |
| Mandatory shadow period | 30 days | Verify signal in real-time before any weight |
| Mandatory paper burn-in | 60 days | Full paper trade before live |
| Auto-rollback trigger | Live Sharpe drops > 0.3 after change | Automatic revert within 24 hours |
| Human review gate | Any change shifting > 20% of portfolio weight | Requires manual approval |
| Complexity budget | Max 50 total features in QLib model | Prevents feature bloat and overfitting |
| Experiment diversity | Max 5 experiments per category per week | Forces exploration over exploitation |
| Journal review before hypothesis | Mandatory | LLM must read relevant past experiments first |

### 10.8 Weekly Strategic Review (Sunday — Premium Model)

A stronger, more expensive model (e.g., Claude Opus, GPT-4o, or DeepSeek R1) acts as a **second pair of eyes** — reviewing the entire week's activity every Sunday and providing strategic corrections that the day-to-day DeepSeek v4 Pro may miss.

**Schedule:** Every Sunday 8:00 AM ET (before Monday open)

**Input context (assembled automatically):**

```
Weekly Review Package:
├── Portfolio performance (daily P&L, Sharpe, drawdown for the week)
├── All trades executed (with signals and rationale at time of trade)
├── Signal attribution (which signals contributed to/detracted from P&L)
├── Regime transitions (if any)
├── AutoResearch activity (experiments run, results, deployments)
├── SHAP drift report (feature importance changes)
├── Risk limit proximity (how close did we get to any limit?)
├── Market context (SPY performance, VIX movement, sector rotation)
└── Research journal entries from the week
```

**The review model answers 5 questions:**

| # | Question | Purpose |
|---|---|---|
| 1 | **What went wrong this week?** Identify trades that lost money and diagnose whether the loss was: (a) bad signal, (b) bad timing, (c) regime mismatch, or (d) acceptable variance | Fault diagnosis |
| 2 | **What patterns is the system missing?** Look at market moves the system didn't capture — was there a signal it should have acted on? | Blind spot detection |
| 3 | **Are the ensemble weights still appropriate for the current regime?** Given this week's regime behavior and signal performance, should weights be adjusted? | Weight sanity check |
| 4 | **Is the AutoResearch pursuing the right priorities?** Given current weaknesses, are the hypotheses being generated addressing the actual problems? | Research direction |
| 5 | **Any position-level concerns for next week?** Earnings coming up on holdings, macro events (FOMC, CPI), sector rotation signals that need attention | Forward-looking risk |

**Output format:**

```yaml
weekly_review:
  date: 2026-05-18
  model: claude-opus-4  # or deepseek-r1, gpt-4o
  
  diagnosis:
    worst_trade: {ticker: "XOM", loss: -$145, cause: "regime_mismatch", detail: "..."}
    best_trade: {ticker: "NVDA", gain: +$312, signal_source: "qlib_alpha + sentiment"}
    overall_assessment: "System performed in-line with expectations for bull/low-vol regime..."
  
  blind_spots:
    - "Missed the semiconductor rotation — SHAP shows sector_momentum decaying"
    - "Reddit sentiment spike on PLTR was ignored because position was full"
  
  weight_recommendations:
    - {signal: "technical_composite", current: 0.10, suggested: 0.15, reason: "..."}
    - {signal: "sentiment", current: 0.15, suggested: 0.12, reason: "..."}
    action: "SUGGEST"  # never AUTO — human reviews these
  
  research_priorities:
    - "Investigate sector rotation signal — current sector exposure is pure market-cap weighting"
    - "Test shorter lookback for RSI — current 14-period is lagging this fast market"
  
  next_week_alerts:
    - {ticker: "AAPL", event: "earnings", date: "2026-05-22", action: "reduce position 24h before"}
    - {event: "FOMC minutes", date: "2026-05-21", action: "expect vol spike"}
  
  confidence: 0.72  # model's self-assessed confidence in this review
```

**Actions triggered by the review:**

| Recommendation Type | System Response |
|---|---|
| Weight adjustment suggestions | Queued for human review (Telegram notification with summary) |
| Research priorities | Fed directly into hypothesis generator as top-priority inputs for the coming week |
| Next-week alerts | Added to risk system as temporary position-size overrides (e.g., reduce before earnings) |
| Blind spot identification | Logged to research journal; generates hypothesis if novel |

**What the review does NOT do:**
- Does NOT auto-execute trades
- Does NOT auto-change weights (only suggests)
- Does NOT override risk limits
- Does NOT deploy any code

It is purely advisory — a strategic counselor that informs the system and the human, not an autonomous actor.

**Cost estimate:**

| Model | Input (~15K tokens) | Output (~3K tokens) | Weekly Cost | Monthly Cost |
|---|---|---|---|---|
| DeepSeek R1 (reasoning) | ~$0.01 | ~$0.01 | ~$0.02 | ~$0.08 |
| Claude Opus | ~$0.23 | ~$0.23 | ~$0.46 | ~$1.84 |
| GPT-4o | ~$0.04 | ~$0.06 | ~$0.10 | ~$0.40 |

Even using the most expensive option (Claude Opus), this adds less than **$2/mo** — negligible. Using DeepSeek R1 (reasoning model) keeps it under $0.10/mo.

**Recommended:** Use the best available reasoning model for this task — it only runs 4x/month and quality matters more than cost here. Start with DeepSeek R1; switch to Claude Opus if review quality is insufficient.

---

## 11. Layer 8: Monitoring & Dashboard

### 11.1 Real-Time Dashboard (React + FastAPI)

**Revision (implemented):** The dashboard was built as a custom React + FastAPI web app rather
than Streamlit, and a Discord-bot reporting design (used briefly during early Phase 1 scaffolding)
was dropped entirely in favor of it. Rationale: Streamlit's widget model and Discord's message-feed
model both fall short of the "glance at portfolio, drill into detail" Robinhood-style interaction
the system needs — particularly the calendar's click-to-drill-down plan-of-action panel, which
needs a real interactive UI, not a chat feed or a server-rendered widget tree.

**Stack:** FastAPI backend (`dashboard_api/`) serving JSON, React + Vite + TypeScript + Tailwind
CSS v4 frontend (`dashboard/`), Recharts for the equity sparkline, a custom month-grid calendar
component (no heavy calendar library — kept full control over the dark theme). Vite's dev server
proxies `/api/*` to FastAPI on port 8000; both run as local processes, no container needed.

**Always-visible connection status strip** (top of every page): Alpaca, Postgres, Redis, DeepSeek —
each a colored dot with latency/error reason on hover, polled every 15s. This replaces the
originally-specced separate "Data Health" / "System Status" pages — for a single-operator system,
a persistent strip is faster to scan than a page you have to navigate to.

**Tabs:**

| Tab | Content | Data source | Status (as of dashboard build) |
|---|---|---|---|
| Overview | Equity, day P&L, equity curve, open positions | Alpaca account/positions API (live) + `portfolio_snapshots` (once Phase 5+ populates it) | Live — shows real Alpaca data once keys are set |
| Trade History | Every trade with full signals + rationale, click to expand | `trades` table | Wired, empty until Phase 5 execution ships |
| Learnings | Per-trade reflection — what went wrong/right, resolved 5 trading days later | `trade_memory` table (§6.5) | Wired, empty until Phase 3+ debate/memory ships |
| Calendar | Month grid: FOMC/CPI/jobs reports (fixed/computed schedule) + earnings (yfinance), click any event ≥7 days out for a plan of action | `calendar_events` table + on-demand generation | Live — fully functional today, independent of later phases |

**Why Calendar works today but Trade History/Learnings don't:** the calendar's event data (macro
calendar, earnings dates) and its plan-of-action generator (historical price-reaction stats +
DeepSeek narrative) only depend on Layer 1 data and a DeepSeek API key — no strategy/execution code
required. Trade History and Learnings are intentionally schema-ready but functionally empty until
the layers that produce that data (Phase 5 execution, Phase 3+ debate/memory) ship — this is
correct behavior, not a bug, and the API returns an explicit `empty_reason` string so the UI can
say so instead of showing a blank table.

**Calendar plan-of-action generation (§7.0/§6.4.1 in practice):**

```
Click event (≥7 days out)
    │
    ▼
Quantitative pass (pure Python, no LLM):
    Look up past occurrences of this event type (FOMC/CPI/NFP fixed schedule,
    or prior earnings dates for this ticker)
    Pull ohlcv_daily around each occurrence, compute next-day return distribution
    If N < 3 historical observations: report "insufficient data" honestly —
        never fabricate a stat from too few points
    │
    ▼
DeepSeek narrative pass:
    System prompt: concise markets analyst, never assert precise numbers beyond
    what the quant stats support, fall back to qualitative positioning advice
    when data is sparse
    User prompt: event details + quant stats (including N=0 case)
    │
    ▼
Cache to calendar_events.plan_of_action (JSONB) — regenerate only on force_refresh
```

This mirrors the philosophy-grounded debate pattern from §6.4.1: deterministic numbers first,
LLM narrates/contextualizes them, never the reverse. Cost: ~$0.0005/event, generated once and
cached — a few hundred events/month is negligible against the ~$36/mo total budget (§16).

### 11.2 Alerting (Telegram Bot — planned, not yet built)

A Discord-bot variant of this was scaffolded early in Phase 1 (`src/monitoring/alerts/discord.py`)
but dropped in favor of the dashboard's connection strip for routine status. Telegram push alerts
remain on the roadmap for genuinely urgent events (drawdown breaches, system halts) where a glance
at the dashboard isn't fast enough — not yet built as of the dashboard implementation.

**Alert levels:**

| Level | Trigger | Delivery |
|---|---|---|
| INFO | Trade executed, daily summary | Telegram (silent) |
| WARNING | Drawdown approaching limit, data quality degraded, model performance drop | Telegram (normal) |
| CRITICAL | Drawdown limit hit, system error, data pipeline failure | Telegram (urgent) + sound |
| EMERGENCY | Max drawdown breached, system halted | Telegram (urgent) + repeated until acknowledged |

### 11.3 Daily Report (Automated)

Generated at 5:00 PM ET every trading day:

```
=== ARTEMIS DAILY REPORT — 2026-05-16 ===

Portfolio Value:  $127,450.32  (+$312.18 / +0.25%)
SPY Today:        +0.18%
Alpha Today:      +0.07%

Regime:           Bull / Low Vol (75% confidence)
Regime Shift:     None (stable 14 days)

Trades Executed:  3
  BUY   50 MSFT @ $442.10  (alpha: 0.72, sentiment: +0.31)
  SELL  30 XOM  @ $108.22  (alpha: -0.45, regime shift signal)
  BUY   25 AMZN @ $198.55  (alpha: 0.68, earnings beat drift)

Risk Status:      GREEN
  Daily Drawdown:      -0.12% (limit: -3.0%)
  Max Position:        4.2% AAPL (limit: 5.0%)
  Max Sector:          22.1% Tech (limit: 25.0%)

Top Contributors:   NVDA (+$145), AAPL (+$89), GOOGL (+$67)
Top Detractors:     JPM (-$34), UNH (-$28)

AutoResearch:     2 experiments completed
  exp_0043: RSI divergence exit signal — FAILED (PBO too high)
  exp_0044: Volume profile feature — PASSED (deploying to shadow)

Data Health:      98/100
System Health:    All processes running
```

### 11.4 Weekly Performance Report

More detailed, generated Saturday morning:

- Full equity curve for the week
- Trade attribution (which signals drove P&L)
- Factor exposure analysis
- Turnover and cost analysis
- AutoResearch summary
- Regime transition analysis
- Comparison vs SPY, QQQ, and relevant sector ETFs

### 11.5 Concept Drift & SHAP Monitor

**Problem this solves:** Financial markets change structurally (regime shifts, regulatory changes, new market participants). Features that were predictive 6 months ago may be worthless today. Without monitoring, the model silently degrades.

**Implementation:**

```
Weekly (Saturday, after model retraining):

1. Compute SHAP values for all features in QLib model
2. Compare rolling 30-day SHAP importance vs 90-day baseline:
   - For each of top 10 features:
     - shap_current = mean |SHAP| over last 30 days
     - shap_baseline = mean |SHAP| over last 90 days
     - drift_score = (shap_baseline - shap_current) / shap_baseline

3. Alert triggers:
   - WARNING: Any top-5 feature drift_score > 0.30 (30% drop in importance)
   - CRITICAL: Top-5 feature drift_score > 0.50 (50% drop — feature may be dead)
   - INFO: Any bottom-quartile feature suddenly enters top 10 (new regime?)

4. Automated response:
   - WARNING → Log and notify; AutoResearch prioritizes experiments in that signal category
   - CRITICAL → Reduce weight of affected signal by 50% immediately; schedule urgent re-evaluation
   - INFO → Flag for AutoResearch exploration (potential new alpha source)
```

**SHAP Dashboard Page:**
- Time series of SHAP importance per feature (rolling 30-day)
- Feature importance ranking changes over time
- Drift score heatmap (features × time)
- Correlation of SHAP drift with regime changes

**Why this matters:** This turns the system from reactive (notice bad P&L → investigate) to proactive (detect feature decay → adapt before it costs money). Combined with AutoResearch, it creates a closed loop: SHAP monitor detects decay → AutoResearch generates hypotheses to replace the dying signal → validation pipeline approves → new signal deployed.

---

## 12. Tech Stack

### Core

| Component | Technology | Rationale |
|---|---|---|
| Language | Python 3.11-3.13 | Ecosystem dominance in quant finance and ML. **Not 3.14** — numba (pulled in by shap/vectorbt) doesn't support it yet as of this build |
| Database | PostgreSQL 16, native Homebrew install | TimescaleDB hypertables dropped — the `timescale/tap` Homebrew formula's build is currently broken against modern macOS/Postgres (github.com/timescale/homebrew-tap issues #55, #57). Plain tables + btree indexes are fine at current data volume; revisit if/when intraday tick data at scale justifies the operational complexity |
| Cache | Redis 7, native Homebrew install | Signal state, task queue, pub/sub for real-time |
| Task Queue | Celery 5 + Redis | Distributed task scheduling and execution |
| Local infra | Homebrew (not Docker) | Docker isn't installed on this dev machine; native services are also lighter on RAM, which fits the system memory constraint better than Docker Desktop's VM overhead |
| Dashboard backend | FastAPI + Uvicorn | JSON API for the dashboard frontend; async-friendly, fast to iterate |
| Dashboard frontend | React + Vite + TypeScript + Tailwind CSS v4 | Replaces the originally-specced Streamlit — needed real interactivity (calendar click-to-drill-down) and Robinhood-level visual polish that Streamlit's widget model doesn't support well |
| Charting | Recharts | Equity sparkline on the Overview tab |

### ML & AI

| Component | Technology | Rationale |
|---|---|---|
| Quant ML | QLib (Microsoft) | Production-grade alpha research platform |
| Reinforcement Learning | FinRL (simplified action space) | Purpose-built for trading RL — see note on action space |
| Sentiment NLP | FinBERT (ProsusAI) | Financial domain BERT, pre-trained (CPU inference OK for headlines) |
| LLM Analysis | DeepSeek v4 Pro | Cloud inference — scoped to holdings + top 20 watchlist (~$2/mo) |
| LLM Research | DeepSeek v4 Pro | Hypothesis generation, experiment analysis, weight opt (~$1/mo) |
| Regime Detection | hmmlearn | Standard HMM library, well-tested |
| Portfolio Optimization | PyPortfolioOpt | Black-Litterman, HRP, mean-variance |
| Technical Analysis | pandas-ta | Comprehensive, pandas-native |
| Backtesting (screening) | vectorbt | Vectorized — 100x faster than event-driven |
| Backtesting (validation) | Custom event-driven | Simulates actual order routing logic |
| Hyperparameter Opt | Optuna | Bayesian optimization with pruning |
| Feature Store | TimescaleDB (dedicated tables) | Precompute features once, serve many validation runs |
| Explainability | SHAP | Feature importance tracking and concept drift detection |
| Event Study | statsmodels + scipy | Market-model OLS, CAR, t-test, bootstrap CI for Gate 0 pre-screen |

### Broker & Data

| Component | Technology | Rationale |
|---|---|---|
| Broker | Alpaca | Commission-free, excellent API, paper + live |
| Historical Data | Polygon.io | Clean, survivorship-bias-free |
| Fundamentals | yfinance | Free, sufficient for daily updates |
| SEC Filings | sec-edgar-downloader | Direct SEC access |
| Macro Data | fredapi | Free, authoritative (Federal Reserve) |
| News | feedparser (RSS) | Free, covers major outlets |
| Social | praw (Reddit API) | Free, covers retail sentiment |

### Infrastructure & Monitoring

| Component | Technology | Rationale |
|---|---|---|
| Dashboard | React + FastAPI (see §12 Core) | See §11.1 for the rationale on dropping Streamlit |
| Alerts | python-telegram-bot (planned) | Free, reliable, mobile push — not yet built; see §11.2 |
| Logging | structlog + Loki (optional) | Structured JSON logs |
| Metrics | Prometheus + Grafana (optional) | Time-series metrics |
| CI/CD | GitHub Actions | Automated testing and model validation |
| Storage | Local SSD + S3 (backup) | Fast local, durable backup |

---

## 13. Data Schema

**Revision note:** TimescaleDB hypertables (`SELECT create_hypertable(...)`) were dropped from the
actual implementation — see §12 Core for why. The tables below are plain Postgres tables with
btree indexes, matching `scripts/init.sql` exactly. Two tables were added beyond the original
design to back the dashboard: `trade_memory` (§6.5) and `calendar_events` (§11.1).

### 13.1 Core Tables

```sql
-- Price data
CREATE TABLE ohlcv_daily (
    ticker      TEXT NOT NULL,
    date        DATE NOT NULL,
    open        NUMERIC(12, 4),
    high        NUMERIC(12, 4),
    low         NUMERIC(12, 4),
    close       NUMERIC(12, 4),
    volume      BIGINT,
    adj_close   NUMERIC(12, 4),
    PRIMARY KEY (ticker, date)
);

-- Signals (computed daily)
CREATE TABLE signals (
    ticker          TEXT NOT NULL,
    date            DATE NOT NULL,
    signal_name     TEXT NOT NULL,
    value           NUMERIC(8, 4),   -- normalized [-1, +1]
    confidence      NUMERIC(4, 3),   -- [0, 1]
    metadata        JSONB,
    PRIMARY KEY (ticker, date, signal_name)
);

-- Ensemble scores
CREATE TABLE ensemble_scores (
    ticker          TEXT NOT NULL,
    date            DATE NOT NULL,
    final_score     NUMERIC(8, 4),
    target_weight   NUMERIC(6, 4),
    regime          TEXT,
    component_scores JSONB,          -- breakdown by signal source
    PRIMARY KEY (ticker, date)
);

-- Trade journal
CREATE TABLE trades (
    trade_id        TEXT PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL,
    ticker          TEXT NOT NULL,
    side            TEXT NOT NULL,    -- buy / sell
    quantity        INTEGER NOT NULL,
    order_type      TEXT NOT NULL,
    limit_price     NUMERIC(12, 4),
    fill_price      NUMERIC(12, 4),
    slippage_bps    NUMERIC(6, 2),
    signals         JSONB,           -- snapshot of all signals at trade time
    risk_snapshot   JSONB,           -- portfolio risk state at trade time
    rationale       TEXT
);

-- Portfolio snapshots (daily)
CREATE TABLE portfolio_snapshots (
    date            DATE PRIMARY KEY,
    total_value     NUMERIC(14, 2),
    cash            NUMERIC(14, 2),
    positions       JSONB,           -- {ticker: {shares, weight, unrealized_pnl}}
    daily_return    NUMERIC(8, 6),
    cumulative_return NUMERIC(8, 6),
    drawdown        NUMERIC(8, 6),
    sharpe_60d      NUMERIC(6, 3),
    regime          TEXT,
    risk_metrics    JSONB
);

-- News and sentiment
CREATE TABLE news_headlines (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL,
    source          TEXT,
    headline        TEXT NOT NULL,
    url             TEXT,
    tickers         TEXT[],
    sentiment_score NUMERIC(4, 3),
    sentiment_label TEXT
);

-- Research journal
CREATE TABLE research_journal (
    experiment_id   TEXT PRIMARY KEY,
    date            DATE NOT NULL,
    hypothesis_id   TEXT,
    category        TEXT,
    description     TEXT,
    result          TEXT,            -- SUCCESS / PARTIAL / FAILURE / ABANDONED
    performance     JSONB,
    validation      JSONB,
    deployment      JSONB,
    learnings       TEXT,
    related         TEXT[],
    tags            TEXT[]
);

-- Regime history
CREATE TABLE regime_history (
    date            DATE PRIMARY KEY,
    regime          TEXT NOT NULL,
    confidence      NUMERIC(4, 3),
    transition_probs JSONB          -- probability of switching to each regime
);

-- Trade decision memory (§6.5) — feeds the dashboard Learnings tab
CREATE TABLE trade_memory (
    id                BIGSERIAL PRIMARY KEY,
    ticker            TEXT NOT NULL,
    trade_date        DATE NOT NULL,
    action            TEXT NOT NULL,
    entry_price       NUMERIC(12, 4),
    signals           JSONB,
    debate_summary    TEXT,
    regime            TEXT,
    status            TEXT DEFAULT 'pending',  -- pending | resolved
    actual_return_5d  NUMERIC(8, 6),
    alpha_vs_spy_5d   NUMERIC(8, 6),
    reflection        TEXT,
    resolved_date     DATE
);

-- Calendar events (§11.1) — feeds the dashboard Calendar tab
CREATE TABLE calendar_events (
    id                 BIGSERIAL PRIMARY KEY,
    event_date         DATE NOT NULL,
    event_type         TEXT NOT NULL,    -- earnings | fomc | cpi | jobs_report | other
    ticker             TEXT,             -- NULL for macro-wide events (FOMC, CPI, NFP)
    title              TEXT NOT NULL,
    description        TEXT,
    plan_of_action     JSONB,            -- cached {quant_stats, narrative}, generated on-demand
    plan_generated_at  TIMESTAMPTZ
);
-- NULL tickers aren't equal under a plain UNIQUE constraint — use an expression
-- index on COALESCE(ticker, '') so macro events dedupe correctly on re-sync.
CREATE UNIQUE INDEX ux_calendar_events
    ON calendar_events (event_date, event_type, (COALESCE(ticker, '')));
```

---

## 14. Directory Structure

```
hedgefund/
├── SPEC.md                          # This document
├── README.md                        # Quick start guide
├── HANDOFF.md                       # Historical bootstrap notes (superseded, see README.md)
├── pyproject.toml                   # Dependencies and project config
├── .env.example                     # Environment variable template
│
├── config/
│   ├── settings.yaml                # Main configuration
│   ├── universe.yaml                # Stock universe filters
│   ├── risk_limits.yaml             # Risk management parameters
│   ├── signals.yaml                 # Signal definitions and weights
│   └── schedules.yaml               # Data collection schedules
│
├── dashboard_api/                   # FastAPI backend for the dashboard (§11.1)
│   ├── main.py                      # App + CORS + router registration
│   ├── alpaca_client.py             # Account/positions wrapper, never raises if unconfigured
│   ├── llm.py                       # DeepSeek client (OpenAI-compatible API)
│   ├── event_sources.py             # FOMC/CPI/NFP/earnings + plan-of-action generator
│   └── routers/
│       ├── portfolio.py             # /api/portfolio/overview, /history
│       ├── connections.py           # /api/connections/status
│       ├── trades.py                # /api/trades
│       ├── learnings.py             # /api/learnings
│       └── calendar.py              # /api/calendar/events, /sync, /{id}/plan
│
├── dashboard/                       # React + Vite + TypeScript + Tailwind frontend
│   ├── src/
│   │   ├── App.tsx                  # Router + nav tabs + layout shell
│   │   ├── types.ts                 # Shared types matching dashboard_api response shapes
│   │   ├── api/client.ts            # Typed fetch helpers
│   │   ├── components/              # ConnectionBar, StatPill
│   │   └── pages/                   # Overview, TradeHistory, Learnings, CalendarPage
│   └── vite.config.ts               # Tailwind v4 plugin + /api dev proxy to :8000
│
├── src/
│   ├── __init__.py
│   │
│   ├── data/                        # Layer 1: Data Ingestion
│   │   ├── __init__.py
│   │   ├── collectors/
│   │   │   ├── price_collector.py   # OHLCV from Alpaca/Polygon
│   │   │   ├── news_collector.py    # RSS feeds
│   │   │   ├── reddit_collector.py  # Reddit via PRAW
│   │   │   ├── sec_collector.py     # SEC EDGAR filings
│   │   │   ├── macro_collector.py   # FRED macro indicators
│   │   │   └── fundamentals_collector.py
│   │   ├── quality/
│   │   │   ├── watchdog.py          # Data quality monitoring
│   │   │   └── validators.py        # Per-source validation rules
│   │   ├── corporate_actions/
│   │   │   ├── handler.py           # Split/dividend/merger processing
│   │   │   └── adjustments.py       # Historical price back-adjustment
│   │   ├── feature_store/
│   │   │   ├── store.py             # Feature computation and caching
│   │   │   ├── lineage.py           # Feature dependency tracking
│   │   │   └── invalidation.py      # Stale feature detection
│   │   ├── universe.py              # Universe selection logic
│   │   └── storage.py               # Database write utilities
│   │
│   ├── signals/                     # Layer 2: Intelligence
│   │   ├── __init__.py
│   │   ├── sentiment/
│   │   │   ├── finbert.py           # FinBERT sentiment scoring
│   │   │   └── aggregator.py        # Per-ticker sentiment aggregation
│   │   ├── llm/
│   │   │   ├── deepseek_analyzer.py # DeepSeek v4 Pro API analysis
│   │   │   └── prompts.py           # Prompt templates
│   │   ├── technical/
│   │   │   ├── indicators.py        # Technical indicator computation
│   │   │   └── composite.py         # Technical composite score
│   │   ├── regime/
│   │   │   ├── detector.py          # HMM regime detection
│   │   │   └── features.py          # Regime input features
│   │   ├── alternative/
│   │   │   ├── insider.py           # Insider trading signals
│   │   │   ├── short_interest.py    # Short interest changes
│   │   │   └── options_flow.py      # Options activity
│   │   └── registry.py              # Signal registration and normalization
│   │
│   ├── strategy/                    # Layer 3: Strategy Engine
│   │   ├── __init__.py
│   │   ├── alpha/
│   │   │   ├── qlib_model.py        # QLib alpha model wrapper
│   │   │   ├── features.py          # Feature engineering for QLib
│   │   │   └── training.py          # Model training pipeline
│   │   ├── rl/
│   │   │   ├── finrl_agent.py       # FinRL PPO agent wrapper
│   │   │   ├── environment.py       # Custom trading environment
│   │   │   └── reward.py            # Reward function definition
│   │   ├── ensemble/
│   │   │   ├── combiner.py          # Signal combination logic
│   │   │   ├── weights.py           # Weight management
│   │   │   └── regime_weights.py    # Regime-conditional weights
│   │   ├── universe_scorer.py       # Final scoring for universe
│   │   ├── debate/
│   │   │   ├── bull_agent.py        # Bull case argumentation
│   │   │   ├── bear_agent.py        # Bear case argumentation
│   │   │   ├── judge.py             # Adjudicator (reasoning model)
│   │   │   ├── checklist_scorer.py  # Deterministic quality/contrarian sub-scores (6.4.1)
│   │   │   └── prompts.py           # Debate prompt templates
│   │   └── memory/
│   │       ├── trade_memory.py      # Per-ticker decision memory
│   │       └── reflector.py         # Deferred outcome reflection generator
│   │
│   ├── validation/                  # Layer 4: Backtesting & Validation
│   │   ├── __init__.py
│   │   ├── event_study/
│   │   │   ├── market_model.py      # OLS market-model fit, abnormal returns
│   │   │   ├── car.py               # Cumulative abnormal return computation
│   │   │   └── significance.py      # t-test + bootstrap CI (Gate 0 pre-screen)
│   │   ├── backtest/
│   │   │   ├── engine.py            # vectorbt-based backtest runner
│   │   │   ├── simulator.py         # Realistic market simulation
│   │   │   └── metrics.py           # Performance metric computation
│   │   ├── walk_forward.py          # Walk-forward analysis
│   │   ├── overfitting/
│   │   │   ├── cpcv.py              # Combinatorial purged CV
│   │   │   ├── deflated_sharpe.py   # Deflated Sharpe ratio
│   │   │   ├── pbo.py               # Probability of backtest overfitting
│   │   │   ├── spa_test.py          # Superior predictive ability
│   │   │   ├── param_stability.py   # Parameter stability analysis
│   │   │   └── regime_robustness.py # Per-regime performance
│   │   ├── scorecard.py             # Unified validation scorecard
│   │   └── baseline.py              # Current production baseline tracking
│   │
│   ├── risk/                        # Layer 5: Risk Management
│   │   ├── __init__.py
│   │   ├── position_sizer.py        # Constrain-then-delegate: vol-tier cap × correlation multiplier
│   │   ├── legal_action_space.py    # Pre-computes max_shares ceiling before any LLM/RL call
│   │   ├── limits.py                # Hard risk limits enforcement
│   │   ├── optimizer.py             # Portfolio optimization (PyPortfolioOpt)
│   │   ├── correlation.py           # Correlation & crowding monitor
│   │   ├── tax_lots.py              # Tax-lot tracking (FIFO)
│   │   ├── wash_sale.py             # Wash sale rule detection and prevention
│   │   └── rebalancer.py            # Cost-aware rebalancing logic
│   │
│   ├── execution/                   # Layer 6: Execution Engine
│   │   ├── __init__.py
│   │   ├── broker.py                # Alpaca API wrapper
│   │   ├── order_router.py          # Smart order routing
│   │   ├── monitor.py               # Execution quality monitoring
│   │   └── journal.py               # Trade journaling
│   │
│   ├── autoresearch/                # Layer 7: AutoResearch Engine
│   │   ├── __init__.py
│   │   ├── hypothesis/
│   │   │   ├── generator.py         # LLM hypothesis generation
│   │   │   ├── templates.py         # Hypothesis prompt templates
│   │   │   └── prioritizer.py       # Hypothesis ranking
│   │   ├── experiment/
│   │   │   ├── runner.py            # Experiment execution pipeline
│   │   │   ├── sandbox.py           # Isolated experiment environment
│   │   │   └── analyzer.py          # LLM result analysis
│   │   ├── promotion/
│   │   │   ├── pipeline.py          # Shadow → paper → live promotion
│   │   │   ├── rollback.py          # Automatic rollback logic
│   │   │   └── weight_optimizer.py  # Bayesian weight optimization
│   │   ├── journal/
│   │   │   ├── manager.py           # Research journal CRUD
│   │   │   └── search.py            # Journal search and retrieval
│   │   ├── weekly_review.py          # Sunday premium-model strategic review
│   │   ├── git_gate.py              # GitHub PR creation for HITL approval
│   │   └── guardrails.py            # AutoResearch safety limits
│   │
│   ├── monitoring/                  # Layer 8: Monitoring
│   │   ├── __init__.py
│   │   │                            # Dashboard lives at top-level dashboard/ + dashboard_api/
│   │   │                            # (React+FastAPI), not here — see §14 top of tree
│   │   ├── alerts/
│   │   │   ├── discord.py           # Discord posting — built, then superseded by dashboard
│   │   │   ├── telegram_bot.py      # Telegram alert delivery (planned, not yet built)
│   │   │   └── rules.py             # Alert trigger rules
│   │   ├── concept_drift/
│   │   │   ├── shap_monitor.py      # Rolling SHAP importance tracking
│   │   │   └── drift_alerts.py      # Feature degradation alerting
│   │   └── reports/
│   │       ├── daily.py             # Daily report generator
│   │       └── weekly.py            # Weekly performance report
│   │
│   └── core/                        # Shared utilities
│       ├── __init__.py
│       ├── db.py                    # Database connection management
│       ├── config.py                # Configuration loading
│       ├── logging.py               # Structured logging setup
│       ├── types.py                 # Shared type definitions
│       ├── checkpoint.py            # Pipeline checkpoint/resume (crash recovery)
│       ├── vendor_failover.py       # Data vendor routing with automatic fallback
│       └── scheduling.py            # Celery task definitions
│
├── models/                          # Trained model artifacts
│   ├── qlib/
│   ├── finrl/
│   ├── finbert/
│   └── regime_hmm/
│
├── experiments/                     # AutoResearch experiment storage
│   └── exp_NNNN_description/
│
├── research_journal/                # Persistent research journal
│   └── entries/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── backtest/
│
├── scripts/
│   ├── setup_db.py                  # Database initialization
│   ├── seed_historical.py           # Backfill historical data
│   ├── train_models.py              # Full model training pipeline
│   └── run_backtest.py              # Manual backtest runner
│
└── notebooks/                       # Exploratory analysis (Jupyter)
    ├── signal_exploration.ipynb
    ├── regime_analysis.ipynb
    └── performance_attribution.ipynb
```

---

## 15. Implementation Plan

### Phase 1: Foundation & Data Pipeline (Weeks 1-3)

**Goal:** Project scaffolding, database, reliable data collection, corporate actions handling, and feature store.

| Task | Details | Deliverable |
|---|---|---|
| 1.1 Project setup | pyproject.toml, native Homebrew Postgres 16 + Redis (Docker unavailable on dev machine; TimescaleDB tap build broken — see §12), directory structure | Working dev environment |
| 1.2 Configuration system | YAML-based config loading with defaults and overrides | `config/` directory |
| 1.3 Database schema | All tables from Section 13 + feature store tables, migrations | `scripts/setup_db.py` |
| 1.3.1 Dashboard (built ahead of schedule) | React+FastAPI dashboard — Overview/Trade History/Learnings/Calendar tabs, connection monitor | `dashboard/`, `dashboard_api/` — see §11.1 |
| 1.4 Price data collector | Alpaca + Polygon.io OHLCV collection, daily + minute bars | `src/data/collectors/price_collector.py` |
| 1.5 News collector | RSS feed parsing, ticker extraction, deduplication | `src/data/collectors/news_collector.py` |
| 1.6 Reddit collector | PRAW integration for r/wallstreetbets, r/stocks | `src/data/collectors/reddit_collector.py` |
| 1.7 Fundamentals collector | yfinance integration for company data | `src/data/collectors/fundamentals_collector.py` |
| 1.8 Macro collector | FRED API for macro indicators | `src/data/collectors/macro_collector.py` |
| 1.9 SEC collector | EDGAR downloader for filings and Form 4 | `src/data/collectors/sec_collector.py` |
| 1.10 Data quality watchdog | Validation checks, health scoring, alerting | `src/data/quality/` |
| 1.11 Universe selection | Daily filtered universe based on liquidity/cap filters | `src/data/universe.py` |
| 1.12 Corporate actions handler | Split/dividend/merger detection, historical back-adjustment | `src/data/corporate_actions/` |
| 1.13 Feature store infrastructure | Pre-computed feature tables, lineage tracking, invalidation logic | `src/data/feature_store/` |
| 1.14 Historical backfill | Seed database with 5+ years of historical data (corporate-action-adjusted) | `scripts/seed_historical.py` |
| 1.15 Celery scheduler | All collection jobs running on schedule | `src/core/scheduling.py` |

**Exit criteria:** All data sources collecting reliably. 5 years of corporate-action-adjusted historical data loaded. Data quality score > 90 for 3 consecutive days. Feature store computing and caching daily features. Corporate actions handler correctly adjusts a test split.

---

### Phase 2: Signal Engine (Weeks 4-6)

**Goal:** Transform raw data into normalized, tradeable signals.

| Task | Details | Deliverable |
|---|---|---|
| 2.1 FinBERT setup | Download model, **CPU batch inference** on headlines (short text = fast enough) | `src/signals/sentiment/finbert.py` |
| 2.2 Sentiment aggregation | Per-ticker rolling sentiment (1h, 24h, 7d), delta computation | `src/signals/sentiment/aggregator.py` |
| 2.3 Technical indicators | Full indicator suite via pandas-ta, composite scoring, stored in feature store | `src/signals/technical/` |
| 2.4 DeepSeek LLM analysis | DeepSeek v4 Pro API for holdings + top 20 watchlist; prompt templates | `src/signals/llm/deepseek_analyzer.py` |
| 2.5 Regime detector | HMM training on historical data, daily regime labeling | `src/signals/regime/` |
| 2.6 Alternative data signals | Insider trading, short interest processing | `src/signals/alternative/` |
| 2.7 Signal registry | Unified signal interface, normalization to [-1, +1], metadata | `src/signals/registry.py` |
| 2.8 Feature store integration | All signals write to feature store; validation engine reads from it | `src/data/feature_store/store.py` |
| 2.9 Signal validation | Backtest each signal independently — does it have predictive power? | Test results |

**Exit criteria:** All signals computing daily and stored in feature store. Each signal individually backtested with documented predictive power (or explicitly marked as experimental). Regime detector accurately labels historical regimes. DeepSeek API scoped to max 50 calls/day, completing within 15 minutes, costing < $3/mo.

---

### Phase 3: ML Models & Strategy (Weeks 7-10)

**Goal:** Build the decision-making core — alpha model, RL agent (simplified action space), and ensemble.

| Task | Details | Deliverable |
|---|---|---|
| 3.1 QLib integration | Install, configure data handler, connect to feature store | `src/strategy/alpha/` |
| 3.2 Feature engineering | Build QLib-compatible features from feature store (no recomputation) | `src/strategy/alpha/features.py` |
| 3.3 Alpha model training | LightGBM model, cross-sectional alpha prediction, SHAP tracking | `src/strategy/alpha/training.py` |
| 3.4 FinRL environment | Custom Gym environment — **simplified 5-dimensional action space** (see 6.2) | `src/strategy/rl/environment.py` |
| 3.5 FinRL agent training | PPO agent with discrete portfolio-level actions, not per-stock weights | `src/strategy/rl/` |
| 3.6 Black-Litterman fallback | Deterministic optimizer as RL fallback/baseline | `src/risk/optimizer.py` |
| 3.7 Ensemble system | Signal combination, regime-conditional weights | `src/strategy/ensemble/` |
| 3.8 Initial weight calibration | Optimize weights on historical data (pre walk-forward) | `src/strategy/ensemble/weights.py` |
| 3.9 Bull/Bear debate system | Adversarial LLM debate gate: Bull agent, Bear agent, Judge (reasoning model) | `src/strategy/debate/` |
| 3.9.1 Philosophy checklist scorer | Deterministic quality (Bull) and contrarian/tail-risk (Bear) sub-scores grounding the debate prompts | `src/strategy/debate/checklist_scorer.py` |
| 3.10 Trade decision memory | Per-ticker memory with deferred 5-day reflection, memory injection into Judge | `src/strategy/memory/` |
| 3.11 Two-tier LLM routing | DeepSeek v4 Pro for analysts/debaters, DeepSeek R1 for Judge + Sunday review | Config + routing logic |
| 3.12 Data vendor failover | Automatic fallback between data sources on failure | `src/core/vendor_failover.py` |
| 3.13 Pipeline checkpoint/resume | SQLite-based checkpoint so crashed pipelines resume from last successful stage | `src/core/checkpoint.py` |
| 3.14 End-to-end backtest | Full pipeline from data → signals → strategy → debate → simulated trades | Backtest report |

**Exit criteria:** QLib alpha model shows positive out-of-sample alpha. FinRL agent outperforms simple risk-parity baseline OR Black-Litterman fallback is adopted. Ensemble outperforms any single signal source. Bull/Bear debate correctly identifies at least 1 trade per week worth rejecting/deferring in historical simulation. Trade memory correctly retrieves relevant past decisions. End-to-end backtest Sharpe > 0.5.

---

### Phase 4: Validation Engine (Weeks 11-13)

**Goal:** Build the dual-engine backtesting system and full overfitting detection pipeline.

| Task | Details | Deliverable |
|---|---|---|
| 4.0 Event-study pre-screen (Gate 0) | Market-model OLS, CAR, t-test, bootstrap CI for catalyst-driven hypotheses | `src/validation/event_study/` |
| 4.0.1 Seed PEAD strategy | Implement Post-Earnings-Announcement-Drift as `exp_0001`, validate via Gate 0 + full pipeline | `experiments/exp_0001_pead/` |
| 4.1 vectorbt backtest engine | Fast screening engine, reads from feature store (no recomputation) | `src/validation/backtest/engine.py` |
| 4.2 Event-driven backtest engine | Custom event loop simulating actual order router logic (limit escalation, partial fills) | `src/validation/backtest/event_engine.py` |
| 4.3 Walk-forward analysis | Rolling window implementation, concatenated OOS metrics | `src/validation/walk_forward.py` |
| 4.4 CPCV | Combinatorial purged cross-validation with embargo (uses feature store) | `src/validation/overfitting/cpcv.py` |
| 4.5 Deflated Sharpe Ratio | DSR computation, strategy trial counter | `src/validation/overfitting/deflated_sharpe.py` |
| 4.6 PBO | Probability of backtest overfitting implementation | `src/validation/overfitting/pbo.py` |
| 4.7 SPA Test | Bootstrap-based superior predictive ability test | `src/validation/overfitting/spa_test.py` |
| 4.8 Parameter stability | Grid sweep and stability scoring | `src/validation/overfitting/param_stability.py` |
| 4.9 Regime robustness | Per-regime Sharpe computation | `src/validation/overfitting/regime_robustness.py` |
| 4.10 Unified scorecard | Combined pass/fail report for all 6 gates | `src/validation/scorecard.py` |
| 4.11 Validate current strategy | Run full pipeline (both engines) on current ensemble | Validation report |

**Exit criteria:** Event-study pre-screen (Gate 0) correctly rejects a known-insignificant synthetic catalyst and passes PEAD with statistically significant CAR. Both backtest engines working. Feature store eliminates redundant computation in CPCV runs (target: <30 min for full CPCV). All 6 overfitting gates implemented and tested. Current strategy passes all gates. Walk-forward OOS Sharpe > 0.5. Event-driven engine confirms vectorbt results within 10% tolerance.

---

### Phase 5: Risk & Execution (Weeks 14-16)

**Goal:** Risk management layer (including tax-awareness) and broker integration (with safe execution).

| Task | Details | Deliverable |
|---|---|---|
| 5.1 Position sizer | Constrain-then-delegate: vol-tier cap × correlation multiplier, computed pre-decision | `src/risk/position_sizer.py` |
| 5.1.1 Legal action space | Pre-compute max_shares ceiling per ticker before ensemble/RL/debate runs; skip forced-HOLD tickers (8.1.1) | `src/risk/legal_action_space.py` |
| 5.2 Risk limits | All hard limits from Section 8.2, enforcement logic | `src/risk/limits.py` |
| 5.3 Portfolio optimizer | PyPortfolioOpt integration, Black-Litterman | `src/risk/optimizer.py` |
| 5.4 Correlation monitor | Factor correlation tracking, crowding detection | `src/risk/correlation.py` |
| 5.5 Tax-lot tracker | FIFO lot tracking, holding period calculation, cost basis | `src/risk/tax_lots.py` |
| 5.6 Wash sale prevention | 30-day window detection, alpha-override threshold, blocking logic | `src/risk/wash_sale.py` |
| 5.7 Cost-aware rebalancer | Threshold-based rebalancing with cost + tax estimation | `src/risk/rebalancer.py` |
| 5.8 Alpaca integration | API wrapper, authentication, account management | `src/execution/broker.py` |
| 5.9 Smart order router | Limit → aggressive limit → IOC escalation (**NO market orders**) | `src/execution/order_router.py` |
| 5.10 Execution monitor | Fill quality tracking, slippage logging | `src/execution/monitor.py` |
| 5.11 Trade journal | Full-context trade logging | `src/execution/journal.py` |

**Exit criteria:** Risk system correctly blocks trades that violate limits. Wash sale detector correctly identifies and blocks/defers triggering trades in test scenarios. Alpaca paper trading API connected. Order router uses only limit-based orders (no market orders). Execution monitor confirms slippage < 0.15% on average.

---

### Phase 6: Paper Trading (Weeks 17-30 / Months 4-7)

**Goal:** Run the full system in paper trading mode. Validate real-world performance.

| Task | Details | Deliverable |
|---|---|---|
| 6.1 Full system integration | Wire all layers together, end-to-end daily cycle | Working system |
| 6.2 Monitoring dashboard | Already built (§11.1) — extend Trade History/Learnings tabs with real data as Phases 3-5 ship | `dashboard/`, `dashboard_api/` |
| 6.3 Telegram alerts | Alert bot with all levels from Section 11.2 | `src/monitoring/alerts/` |
| 6.4 SHAP / concept drift monitor | Weekly SHAP tracking, drift scoring, degradation alerts | `src/monitoring/concept_drift/` |
| 6.5 Daily/weekly reports | Automated report generation | `src/monitoring/reports/` |
| 6.6 Paper trading | Run on Alpaca paper account with realistic capital | Daily performance logs |
| 6.7 Performance tracking | Track Sharpe, drawdown, alpha vs SPY daily | Performance database |
| 6.8 Weekly strategic review | Sunday premium-model review pipeline (10.8) — assembles context, calls model, parses output, routes recommendations | `src/autoresearch/weekly_review.py` |
| 6.9 Bug fixing & tuning | Address issues discovered in live operation | Bug fixes, parameter adjustments |

**Minimum paper trading duration: 3 months (13 weeks).**

**Paper trading success criteria (must meet ALL):**
- Annualized Sharpe > 0.8
- Max drawdown < 15%
- Positive alpha vs SPY in at least 2 of 3 months
- No data pipeline failures lasting > 1 hour
- No risk limit breaches (system correctly prevents them)
- Execution slippage within modeled expectations (< 0.15%)

---

### Phase 7: AutoResearch Engine (Weeks 20-24, overlaps with Paper Trading)

**Goal:** Build the self-improving research loop with human-in-the-loop Git gate.

| Task | Details | Deliverable |
|---|---|---|
| 7.1 Hypothesis generator | DeepSeek v4 Pro API integration, prompt engineering, journal reading | `src/autoresearch/hypothesis/` |
| 7.2 Experiment runner | Sandboxed execution, full validation pipeline per experiment | `src/autoresearch/experiment/` |
| 7.3 Result analyzer | LLM analysis of experiment results, verdict generation | `src/autoresearch/experiment/analyzer.py` |
| 7.4 Research journal | CRUD operations, search, relationship tracking | `src/autoresearch/journal/` |
| 7.5 Git gate (HITL) | Auto-create GitHub PR with scorecard + diff on experiment success; block deployment until merged | `src/autoresearch/git_gate.py` |
| 7.6 Promotion pipeline | PR merge → shadow → paper → live staged deployment | `src/autoresearch/promotion/` |
| 7.7 Weight optimizer | Bayesian optimization of ensemble weights, regime-conditional | `src/autoresearch/promotion/weight_optimizer.py` |
| 7.8 Rollback system | Automatic revert on performance degradation | `src/autoresearch/promotion/rollback.py` |
| 7.9 Guardrails | All limits from Section 10.7 | `src/autoresearch/guardrails.py` |
| 7.10 SHAP → AutoResearch feedback loop | SHAP drift alerts auto-generate research priorities for hypothesis generator | Integration |
| 7.11 Initial research cycle | Run 10+ experiments, validate the loop works end-to-end | Experiment results |

**Exit criteria:** AutoResearch loop running autonomously. Git gate creates well-formatted PRs with validation scorecards. At least 2 successful experiments deployed to shadow mode after human PR approval. SHAP drift alerts correctly trigger hypothesis generation for degrading features. Research journal accumulating useful learnings. Guardrails preventing runaway experimentation.

---

### Phase 8: Risk Hardening (Weeks 25-26)

**Goal:** Stress test everything before live money.

| Task | Details | Deliverable |
|---|---|---|
| 8.1 Historical stress tests | Run system through 2008, 2020 March, 2022 rate hikes | Stress test reports |
| 8.2 Extreme scenario simulation | What if: flash crash, market halt, broker outage, data loss | Scenario reports |
| 8.3 Kill switch testing | Verify all emergency stops work correctly | Test results |
| 8.4 Recovery procedures | Document and test: system restart, data recovery, rollback | Runbook |
| 8.5 Wash sale stress test | Simulate rapid buy/sell cycles; verify wash sale blocker engages | Tax compliance report |
| 8.5 Security audit | API key management, database access, network security | Security report |

**Exit criteria:** System survives all historical stress scenarios within drawdown limits. Kill switches tested and working. Recovery procedures documented and tested.

---

### Phase 9: Live Trading (Week 31+)

**Goal:** Deploy with real capital, gradual scale-up.

| Stage | Capital Allocation | Duration | Success Criteria |
|---|---|---|---|
| 9.1 Minimum viable | $5,000 | 4 weeks | Positive return, no system issues |
| 9.2 Scale to 25% | 25% of target capital | 8 weeks | Sharpe > 0.5, drawdown < 10% |
| 9.3 Scale to 50% | 50% of target capital | 8 weeks | Sharpe > 0.7, drawdown < 12% |
| 9.4 Full allocation | 100% of target capital | Ongoing | Sharpe > 0.8, drawdown < 15% |

**Scaling rules:**
- Only scale up after the duration AND criteria are met
- Any drawdown > 10% during scale-up triggers a pause and review
- Scale DOWN (not up) if AutoResearch deploys a major change during scale-up

---

### Phase 10: Continuous Operation (Ongoing)

| Activity | Frequency | Owner |
|---|---|---|
| Monitor daily reports | Daily | Human (5 min review) |
| Review AutoResearch journal | Weekly | Human (30 min) |
| Model retraining (QLib) | Weekly (automated) | System |
| Model retraining (FinRL) | Monthly (automated) | System |
| Weight optimization | Weekly (automated) | System |
| Regime model update | Monthly (automated) | System |
| Quarterly strategy review | Quarterly | Human (deep review) |
| Tax-lot reporting | Annually | Human + system data export |

---

## 16. Cost Estimates

### Design Principle

All features enabled from day 1. By using DeepSeek v4 Pro ($0.435/M input tokens, ~$1.74/M output tokens) for all LLM tasks, the entire system — including AutoResearch, LLM analysis, dashboard, and SHAP monitoring — runs at ~$34/mo.

**Scale-up rule:** Only increase spend when monthly profits consistently exceed 3x the running cost for 2 consecutive months.

```
Scale-Up Formula:
    avg_monthly_profit (last 60 days) >= 3 × next_tier_monthly_cost
    
Example:
    Tier 2 costs $80/mo → only unlock when avg profit >= $240/mo for 2 months
```

This ensures the system is self-funding with comfortable margin at every stage.

---

### Tier 1: Full System ($34/mo) — ALL FEATURES ENABLED

**When:** Day 1. Everything is on from the start. DeepSeek v4 Pro pricing makes LLM features nearly free (~$3/mo total), so there is no reason to gate any feature.

| Component | Cost | Notes |
|---|---|---|
| Alpaca (broker + real-time data) | $0 | Real-time quotes, execution, paper trading |
| Alpaca historical data API | $0 | Free 5+ years of daily/min bars with funded account |
| Free data (FRED, SEC EDGAR, Reddit, RSS) | $0 | Macro, filings, social, news headlines |
| PostgreSQL (local, native Homebrew install) | $0 | TimescaleDB extension dropped — see §12 |
| Redis (local, native Homebrew install) | $0 | |
| FinBERT sentiment (CPU inference) | $0 | Runs locally on headlines — lightweight |
| pandas-ta technical indicators | $0 | |
| QLib alpha model (LightGBM, CPU) | $0 | Trains in minutes on CPU |
| Regime detector (HMM) | $0 | |
| React + FastAPI dashboard (local) | $0 | Full monitoring UI on localhost — see §11.1 |
| Telegram Bot (alerts, planned) | $0 | Not yet built — see §11.2 |
| SHAP concept drift monitor | $0 | Weekly CPU computation |
| GitHub (private repo + Actions) | $0 | Free tier — hosts HITL Git Gate PRs |
| Polygon.io (Starter) | $29 | Historical data + corporate actions feed |
| DeepSeek v4 Pro — LLM analysis | ~$2 | Holdings + watchlist (~50 calls/day) |
| DeepSeek v4 Pro — AutoResearch | ~$1 | Hypothesis gen, experiment analysis, weight opt |
| DeepSeek v4 Pro — Bull/Bear debate agents | ~$0.50 | ~100 debates/mo (Bull + Bear arguments) |
| DeepSeek R1 — Judge (debate adjudication) | ~$0.50 | ~100 judge calls/mo (reasoning model) |
| DeepSeek v4 Pro — Trade reflections | ~$0.02 | ~20 deferred reflections/mo |
| DeepSeek v4 Pro — SHAP reasoning | ~$0.20 | Drift interpretation |
| DeepSeek R1 — Weekly Strategic Review | ~$0.50 | Sunday review, 4 calls/mo |
| S3 backup (50GB) | ~$1 | Research journal + model artifacts |
| Local compute (electricity) | ~$1 | No GPU — CPU workloads only |
| **Total** | **~$36/mo** | |

**Everything is ON from day 1:**

| Category | Features Enabled |
|---|---|
| Data Pipeline | Price (real-time), fundamentals, news (RSS), social (Reddit), macro (FRED), SEC filings, corporate actions handler |
| Intelligence | FinBERT sentiment, technical indicators, regime detection (HMM), DeepSeek LLM analysis (holdings + top 20 watchlist) |
| Strategy | QLib alpha model (LightGBM), RL agent (simplified), ensemble with regime-conditional weights, Bull/Bear adversarial debate gate, trade decision memory with deferred reflection |
| Validation | Feature store, walk-forward analysis, all 6 overfitting gates, dual-engine backtesting |
| Risk | Position limits, drawdown halts, correlation monitor, wash sale prevention, tax-lot tracking, volatility targeting |
| Execution | Alpaca (aggressive limit orders only — no market orders), smart order routing |
| AutoResearch | Full loop: hypothesize > implement > backtest > analyze > learn, HITL Git Gate, weight optimization, SHAP feedback |
| Weekly Review | Sunday premium-model strategic review — fault diagnosis, blind spots, weight suggestions, forward risk alerts |
| Monitoring | React+FastAPI dashboard (built), Telegram alerts (planned), daily/weekly reports, concept drift monitoring |

**DeepSeek v4 Pro Token Usage Breakdown:**

| LLM Task | Calls/Month | Input Tokens | Output Tokens | Monthly Cost |
|---|---|---|---|---|
| Holdings + watchlist analysis | ~1,500 | ~3.1M | ~0.55M | ~$2.30 |
| Bull/Bear debate (DeepSeek v4 Pro) | ~200 | ~1.0M | ~0.4M | ~$0.50 |
| Judge adjudication (DeepSeek R1) | ~100 | ~0.5M | ~0.1M | ~$0.50 |
| Trade reflections (5-day deferred) | ~20 | ~0.06M | ~0.02M | ~$0.02 |
| AutoResearch (hypothesis + analysis + weight opt) | ~214 | ~1.1M | ~0.28M | ~$1.00 |
| SHAP drift reasoning | ~8 | ~0.1M | ~0.03M | ~$0.10 |
| Weekly strategic review (DeepSeek R1) | ~4 | ~0.06M | ~0.01M | ~$0.05 |
| **Total LLM** | **~2,046** | **~5.9M** | **~1.4M** | **~$4.47** |

Pricing: $0.435/M input tokens, ~$1.74/M output tokens (estimated).

---

### Tier 2: Scale ($80/mo)

**Unlock when:** Avg monthly profit >= $240/mo for 2 consecutive months.

This tier is optional — Tier 1 is the complete system. Tier 2 adds resolution and reliability.

| Component | Cost | Change from Tier 1 |
|---|---|---|
| Everything in Tier 1 | $34 | |
| Polygon.io upgrade (higher tier) | +$20-50 | Tick data, faster rate limits for deeper backtests |
| Increased DeepSeek budget | +$5 | More aggressive AutoResearch (30+ experiments/week) |
| Cloud VM for 24/7 uptime (optional) | +$0-50 | Only if local machine reliability becomes an issue |
| **Total** | **~$60-140/mo** | |

**What this adds:**
- Higher data resolution (tick-level for intraday pattern detection)
- More aggressive AutoResearch experimentation (30+ experiments/week vs 20)
- Optional cloud migration for always-on reliability

---

### Tier Transition Logic (Automated)

```python
def should_scale_up(current_tier, monthly_profits_60d):
    tier_costs = {1: 34, 2: 80}
    next_tier = current_tier + 1
    
    if next_tier not in tier_costs:
        return False
    
    next_cost = tier_costs[next_tier]
    min_profit = next_cost * 3  # 3x rule
    
    # Need 2 consecutive months above threshold
    month_1_profit = sum(monthly_profits_60d[:30])
    month_2_profit = sum(monthly_profits_60d[30:])
    
    if month_1_profit >= min_profit and month_2_profit >= min_profit:
        return True  # Send Telegram alert recommending scale-up
    
    return False
```

The system sends a **Telegram alert** when scale-up conditions are met. Actual tier change requires human confirmation (config flag flip).

---

### One-Time Setup Costs

| Item | Cost | Notes |
|---|---|---|
| Historical data backfill | $0-50 | Polygon + Alpaca free tiers cover most needs |
| Domain name (optional) | ~$12/year | For remote dashboard access |

### Break-Even Analysis

| Tier | Annual Cost | Min Portfolio to Break Even (15% return) | Min Portfolio for 3x Rule |
|---|---|---|---|
| Tier 1 ($34/mo) | $408 | ~$2,700 | ~$8,200 |
| Tier 2 ($80/mo) | $960 | ~$6,400 | ~$19,200 |

### LLM Quality Monitoring

DeepSeek is dramatically cheaper but quality must be monitored. The system tracks:

| Metric | Alert Threshold | Action |
|---|---|---|
| Hypothesis to experiment success rate | < 5% after 50 experiments | Review prompts; consider model switch for AutoResearch |
| LLM analysis signal correlation with outcomes | < 0.1 over 60 days | Reduce LLM signal weight in ensemble |
| Code generation lint/type-check failure rate | > 40% of experiments | Adjust code generation prompts |
| Hallucination rate (claims vs verified data) | Any detected | Cross-validate all LLM outputs against data |

The validation pipeline protects regardless of LLM quality — a weaker model means more failed experiments (costing fractions of a cent each), not bad trades reaching production.


## 17. Risk Register

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Data pipeline failure | Medium | High | Watchdog + alerts; halt trading on bad data |
| Model degradation (alpha decay) | High | Medium | AutoResearch continuously discovers new signals; rolling retraining |
| Broker API outage | Low | High | Queue orders for retry; daily reconciliation; consider backup broker |
| Overfitting despite gates | Low | High | Conservative position sizing; 6-gate pipeline is thorough |
| AutoResearch deploys bad change | Low | Medium | Mandatory burn-in; auto-rollback on performance drop |
| DeepSeek API outage | Low | Medium | Cache last LLM signals; system can trade for 24h on cached analysis; degrade gracefully |

### Market Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Prolonged drawdown | Medium | High | Hard drawdown limits; regime-aware cash allocation |
| Black swan event | Low | Very High | Max drawdown kill switch; cash reserve minimum |
| Regime model misclassification | Medium | Medium | Ensemble doesn't rely solely on regime; conservative defaults |
| Crowded factor unwind | Low | High | Correlation monitor; factor exposure limits |
| Changed market microstructure | Low | Medium | AutoResearch detects signal decay; continuous adaptation |

### Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| API key compromise | Low | Very High | Env variables only; no keys in code; API key rotation |
| Tax complexity from high turnover | Medium | Medium | Cost-aware rebalancing; track tax lots; annual review |
| Regulatory changes | Low | Medium | Personal capital only; monitor SEC/FINRA updates |
| Dependency version conflicts | Medium | Low | Docker containerization; pinned dependencies |

---

## 18. Options Engine (v4.0)

The Options Engine extends Artemis into listed options — initially as an additional signal source, then progressing to execution and hedging.  All phases follow the same 6-gate validation pipeline as equity strategies (§7.3) before live deployment.

### Phase A: Options-as-Signal

Use options market data as a confirming/contrarian signal layer for equity decisions — no options execution required at this phase.

| Signal | Source | Logic |
|---|---|---|
| IV Rank (IVR) | Options chain (Alpaca / CBOE) | IVR = (current IV − 52w low) / (52w high − 52w low). High IVR (>80) signals elevated market anxiety; low IVR (<20) signals complacency. Combined with regime label as a secondary risk filter |
| Put/Call Ratio | CBOE / broker chain data | Rolling 5-day PCR by ticker and market-wide. Extreme put skew (PCR > 1.5) = bearish institutional hedging signal; extreme call skew (PCR < 0.5) = speculative froth |
| Unusual Flow Detection | Unusual Whales API / CBOE flow data | Identify unusually large single-print option trades (block sweeps). Cross-reference with stock direction and expiry to classify as hedging vs directional bet. Feed as alt-data signal into ensemble (§6.3) |

**Deliverable:** `src/signals/alternative/options_flow.py` extended with IV rank, PCR aggregation, and unusual flow classifier. All three signals normalized to [-1, +1] and added to the signal registry.

### Phase B: Options Execution

Add ability to execute simple options strategies via Alpaca options API.

| Strategy | Trigger | Mechanics |
|---|---|---|
| Pre-earnings straddle | Earnings ≥ 5 days out, IVR < 40 (cheap vol), strong ensemble signal | Buy ATM call + ATM put ~5 DTE before earnings; close both legs 1 day before announcement to avoid binary event; profit from IV expansion |
| Directional call / put | High-conviction ensemble score (>0.80) in low-IVR environment | Buy OTM call (bullish) or put (bearish) as levered expression of existing equity signal; max loss = premium paid; sized at ≤0.5% of portfolio per position |

**Deliverable:** `src/execution/options_router.py`, options-aware position sizer in `src/risk/position_sizer.py` (premium-capped sizing), and integration with the Bull/Bear debate gate (options plays require debate approval same as equity trades >1% of portfolio).

### Phase C: Earnings Events (PEAD Momentum)

Extend the seeded PEAD strategy (§7.0 / `exp_0001`) with an options layer for amplified post-earnings drift capture.

| Component | Detail |
|---|---|
| PEAD equity leg | Long/short equity position entered at market open after earnings announcement (existing `exp_0001` logic) |
| PEAD options overlay | If IVR collapses post-earnings (typical IV crush), sell short-dated covered calls against long equity (call overwrite) to generate income while holding the drift position |
| Earnings event calendar | `calendar_events` table feeds the dashboard Calendar tab; plan-of-action generator (§11.1) provides historical drift statistics and positioning guidance for upcoming earnings |

**Deliverable:** Updated `experiments/exp_0001_pead/` with options overlay variant; calendar integration for earnings-driven options suggestions.

### Phase D: Hedging

Portfolio-level protection using options, activated only in Bear/High Vol regime (Regime 4, §5.5) or when drawdown exceeds the warning threshold.

| Hedge Type | Trigger | Implementation |
|---|---|---|
| Tail hedge | Portfolio beta > 1.1 AND regime = Bear/High Vol | Buy SPY put spreads (buy ATM put, sell 10% OTM put) — defined-cost downside protection; sized at 1–2% of portfolio in premium |
| Collar suggestions | Single position >4% of portfolio with unrealized gain >20% | Suggest (not auto-execute) a collar: sell OTM call to finance OTM put, locking in gains while capping upside. Surfaces as a dashboard alert requiring human action |

**Deliverable:** `src/risk/hedge_suggester.py` generating collar suggestions posted to dashboard alerts; tail hedge logic in `src/risk/limits.py` as a portfolio-level drawdown guard.

---

## 19. Dashboard Features (v4.0)

The Artemis dashboard (React + FastAPI, §11.1) provides the following panels and features as of v4.0:

| Feature | Tab / Location | Description |
|---|---|---|
| **Portfolio Overview** | Overview | Total equity, day P&L, open positions with weights, equity curve sparkline |
| **Trade History** | Trade History | Full trade log with signals, rationale, and slippage; click to expand per-trade detail |
| **Learnings** | Learnings | Per-trade reflection (§6.5) — deferred 5-day outcome, alpha vs SPY, LLM-written lesson |
| **Options** | Options | IV rank by holding, PCR heatmap, unusual flow alerts, active options positions and P&L |
| **Calendar** | Calendar | Month grid: FOMC/CPI/NFP/earnings; click event ≥7 days out for plan-of-action panel with quant stats and DeepSeek narrative |
| **Kill Switch** | Persistent (top nav) | One-click emergency halt: cancels all open orders, sets system to cash-only mode; requires manual restart |
| **Regime Banner** | Persistent (top strip) | Current market regime label + confidence + days stable; color-coded (green = bull/low vol, red = bear/high vol) |
| **News Feed** | Overview sidebar | Last 24h headlines for current holdings, with FinBERT sentiment label and score |
| **Price Alerts** | Overview | User-configurable price alerts for watchlist tickers; triggers Telegram notification |
| **Benchmark Chart** | Overview | Portfolio equity curve vs SPY total return (rolling 3-month and YTD); rendered with Recharts |
| **Drawdown Chart** | Overview | Peak-to-trough drawdown chart overlaid on equity curve; highlights daily/weekly/max drawdown limit thresholds |
| **Correlation Matrix** | Risk (sub-tab) | Pairwise correlation heatmap of current holdings; cells turn red if correlation > 0.80 (hard limit, §8.2) |
| **AutoResearch Status** | Research | Active experiments, recent verdicts (DEPLOY / ITERATE / ABANDON), SHAP drift scores, next hypothesis queue |

**Connection Status Strip** (top of every page): colored dots for Alpaca, Postgres, Redis, DeepSeek — polled every 15s with latency and last-error on hover.

---

## 20. Appendix

### A. Key Academic References

| Paper | Author(s) | Relevance |
|---|---|---|
| "Advances in Financial Machine Learning" | Marcos Lopez de Prado (2018) | CPCV, meta-labeling, feature importance |
| "The Deflated Sharpe Ratio" | Bailey & Lopez de Prado (2014) | Overfitting gate #2 |
| "Probability of Backtest Overfitting" | Bailey et al. (2015) | Overfitting gate #3 |
| "A Test for Superior Predictive Ability" | Hansen (2005) | Overfitting gate #4 |
| "FinRL: Deep RL for Automated Stock Trading" | Liu et al. (2020) | RL agent architecture |
| "QLib: An AI-Oriented Quantitative Investment Platform" | Yang et al. (2020) | Alpha model pipeline |
| "FinBERT: Financial Sentiment Analysis with Pre-Trained LMs" | Araci (2019) | Sentiment model |
| "FinGPT: Open-Source Financial LLMs" | Yang et al. (2023) | LLM financial analysis |
| "Portfolio Selection" | Markowitz (1952) | Portfolio optimization foundations |
| "Black-Litterman Model" | Black & Litterman (1992) | Incorporating alpha views into optimization |

### B. Glossary

| Term | Definition |
|---|---|
| Alpha | Excess return relative to benchmark (SPY) |
| Sharpe Ratio | Risk-adjusted return: (return - risk_free) / volatility |
| Drawdown | Peak-to-trough decline in portfolio value |
| CPCV | Combinatorial Purged Cross-Validation — a method for detecting overfitting |
| DSR | Deflated Sharpe Ratio — Sharpe adjusted for multiple testing |
| PBO | Probability of Backtest Overfitting |
| HMM | Hidden Markov Model — for regime detection |
| PPO | Proximal Policy Optimization — RL algorithm |
| OOS | Out-of-sample — data not used in training |
| Walk-forward | Rolling train/test validation methodology |
| ATR | Average True Range — volatility measure |
| VIX | CBOE Volatility Index — market fear gauge |
| OAS | Option-Adjusted Spread — credit risk measure |

### C. Configuration Defaults

```yaml
# config/settings.yaml (reference defaults)
portfolio:
  initial_capital: 100000
  target_volatility: 0.15
  max_position_pct: 0.05
  max_sector_pct: 0.25
  min_cash_pct: 0.10
  rebalance_threshold_pct: 0.005

risk:
  daily_drawdown_halt: -0.03
  weekly_drawdown_reduce: -0.05
  max_drawdown_liquidate: -0.15
  max_portfolio_beta: 1.3
  max_correlation: 0.80

models:
  qlib_retrain_day: "Saturday"
  finrl_retrain_day: 1  # 1st of month
  regime_retrain_day: 1
  walk_forward_train_days: 252
  walk_forward_test_days: 63

autoresearch:
  max_experiments_per_week: 20
  max_concurrent_live_changes: 1
  shadow_period_days: 30
  paper_burnin_days: 60
  rollback_sharpe_threshold: -0.30
  max_features: 50
  weight_optimization_day: "Saturday"

execution:
  order_timeout_seconds: 90
  limit_price_adjustment_pct: 0.0025
  max_daily_turnover_pct: 0.30

data:
  min_market_cap: 500000000
  min_daily_volume: 5000000
  min_price: 5.0
  min_history_days: 252
```
