-- Artemis Database Schema (per SPEC §13)
-- Runs once at Postgres init.
--
-- NOTE: TimescaleDB hypertables were dropped from this schema. The Homebrew
-- timescaledb tap's build is currently broken against modern macOS/Postgres
-- (see https://github.com/timescale/homebrew-tap/issues/55,57). At the
-- current data volume (a dozen tickers, daily bars) plain Postgres tables
-- with btree indexes perform fine. Revisit hypertables if/when intraday
-- tick-level data at scale makes them worth the operational complexity.

-- ── Price data ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ohlcv_daily (
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
CREATE INDEX IF NOT EXISTS ix_ohlcv_daily_ticker ON ohlcv_daily(ticker, date DESC);

CREATE TABLE IF NOT EXISTS ohlcv_1m (
    ticker      TEXT NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    open        NUMERIC(12, 4),
    high        NUMERIC(12, 4),
    low         NUMERIC(12, 4),
    close       NUMERIC(12, 4),
    volume      BIGINT,
    PRIMARY KEY (ticker, ts)
);

-- ── Signals ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signals (
    ticker          TEXT NOT NULL,
    date            DATE NOT NULL,
    signal_name     TEXT NOT NULL,
    value           NUMERIC(8, 4),
    confidence      NUMERIC(4, 3),
    metadata        JSONB,
    PRIMARY KEY (ticker, date, signal_name)
);

CREATE TABLE IF NOT EXISTS ensemble_scores (
    ticker           TEXT NOT NULL,
    date             DATE NOT NULL,
    final_score      NUMERIC(8, 4),
    target_weight    NUMERIC(6, 4),
    regime           TEXT,
    component_scores JSONB,
    PRIMARY KEY (ticker, date)
);

-- ── Trades ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    trade_id        TEXT PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL,
    ticker          TEXT NOT NULL,
    side            TEXT NOT NULL,
    quantity        INTEGER NOT NULL,
    order_type      TEXT NOT NULL,
    limit_price     NUMERIC(12, 4),
    fill_price      NUMERIC(12, 4),
    slippage_bps    NUMERIC(6, 2),
    signals         JSONB,
    risk_snapshot   JSONB,
    rationale       TEXT
);
CREATE INDEX IF NOT EXISTS ix_trades_ts ON trades(timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_trades_ticker ON trades(ticker, timestamp DESC);

-- ── Portfolio snapshots ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    date              DATE PRIMARY KEY,
    total_value       NUMERIC(14, 2),
    cash              NUMERIC(14, 2),
    positions         JSONB,
    daily_return      NUMERIC(8, 6),
    cumulative_return NUMERIC(8, 6),
    drawdown          NUMERIC(8, 6),
    sharpe_60d        NUMERIC(6, 3),
    regime            TEXT,
    risk_metrics      JSONB
);

-- ── News / Sentiment ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS news_headlines (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL,
    source          TEXT,
    headline        TEXT NOT NULL,
    url             TEXT UNIQUE,
    tickers         TEXT[],
    sentiment_score NUMERIC(4, 3),
    sentiment_label TEXT
);
CREATE INDEX IF NOT EXISTS ix_news_ts ON news_headlines(timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_news_tickers ON news_headlines USING GIN(tickers);

CREATE TABLE IF NOT EXISTS social_posts (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL,
    source          TEXT NOT NULL,
    post_id         TEXT UNIQUE,
    author          TEXT,
    text            TEXT,
    tickers         TEXT[],
    sentiment_score NUMERIC(4, 3),
    metadata        JSONB
);
CREATE INDEX IF NOT EXISTS ix_social_ts ON social_posts(timestamp DESC);

-- ── Macro indicators ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS macro_indicators (
    series_id   TEXT NOT NULL,
    date        DATE NOT NULL,
    value       NUMERIC(14, 6),
    PRIMARY KEY (series_id, date)
);

-- ── Fundamentals ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fundamentals (
    ticker         TEXT NOT NULL,
    asof_date      DATE NOT NULL,
    market_cap     NUMERIC(18, 2),
    pe_ratio       NUMERIC(10, 4),
    eps            NUMERIC(10, 4),
    dividend_yield NUMERIC(8, 6),
    revenue_ttm    NUMERIC(18, 2),
    sector         TEXT,
    industry       TEXT,
    payload        JSONB,
    PRIMARY KEY (ticker, asof_date)
);

-- ── Universe ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS universe_daily (
    date     DATE NOT NULL,
    ticker   TEXT NOT NULL,
    eligible BOOLEAN,
    reason   TEXT,
    PRIMARY KEY (date, ticker)
);

-- ── Corporate actions ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS corporate_actions (
    id          BIGSERIAL PRIMARY KEY,
    ticker      TEXT NOT NULL,
    action_type TEXT NOT NULL,    -- split | dividend | merger | ticker_change | spinoff
    ex_date     DATE NOT NULL,
    payload     JSONB,
    applied_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_corp_actions ON corporate_actions(ticker, ex_date DESC);

-- ── Regime history ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS regime_history (
    date             DATE PRIMARY KEY,
    regime           TEXT NOT NULL,
    confidence       NUMERIC(4, 3),
    transition_probs JSONB
);

-- ── Feature store ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS features_daily (
    ticker        TEXT NOT NULL,
    date          DATE NOT NULL,
    feature_name  TEXT NOT NULL,
    value         NUMERIC(14, 6),
    PRIMARY KEY (ticker, date, feature_name)
);
CREATE INDEX IF NOT EXISTS ix_features_lookup ON features_daily(ticker, feature_name, date DESC);

CREATE TABLE IF NOT EXISTS feature_metadata (
    feature_name        TEXT PRIMARY KEY,
    category            TEXT,
    computation_version TEXT,
    last_updated        TIMESTAMPTZ,
    description         TEXT
);

-- ── Data quality reports ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS data_quality_reports (
    id            BIGSERIAL PRIMARY KEY,
    timestamp     TIMESTAMPTZ NOT NULL,
    source        TEXT NOT NULL,
    health_score  INTEGER,
    issues        JSONB
);

-- ── Research journal ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS research_journal (
    experiment_id TEXT PRIMARY KEY,
    date          DATE NOT NULL,
    hypothesis_id TEXT,
    category      TEXT,
    description   TEXT,
    result        TEXT,
    performance   JSONB,
    validation    JSONB,
    deployment    JSONB,
    learnings     TEXT,
    related       TEXT[],
    tags          TEXT[]
);

-- ── Trade decision memory (SPEC §6.5) — feeds the dashboard Learnings tab ──
CREATE TABLE IF NOT EXISTS trade_memory (
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
    resolved_date     DATE,
    label             VARCHAR(50)              -- NULL (real trade) | Missed | Universe Miss | Test
);
-- Upgrade path for databases created before the label column existed.
ALTER TABLE trade_memory ADD COLUMN IF NOT EXISTS label VARCHAR(50);
CREATE INDEX IF NOT EXISTS ix_trade_memory_ticker ON trade_memory(ticker, trade_date DESC);
CREATE INDEX IF NOT EXISTS ix_trade_memory_status ON trade_memory(status);

-- ── Order idempotency (pre-trade gate) ──────────────────────────────────────
-- Every order intent gets a deterministic client_order_id; the gate inserts
-- here once and rejects any resend of an id already present. Protects against
-- reconnect/retry loops and same-day double-submits of the same rebalance.
CREATE TABLE IF NOT EXISTS submitted_orders (
    client_order_id TEXT PRIMARY KEY,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    qty             INTEGER NOT NULL,
    limit_price     NUMERIC(12, 4),
    asset_class     TEXT NOT NULL DEFAULT 'equity',
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_submitted_orders_ts ON submitted_orders(submitted_at DESC);

-- ── Kill switch ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kill_switch (
    id      INTEGER PRIMARY KEY DEFAULT 1,
    paused  BOOLEAN NOT NULL DEFAULT FALSE,
    set_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason  TEXT,
    CONSTRAINT ks_single_row CHECK (id = 1)
);
INSERT INTO kill_switch (id, paused) VALUES (1, FALSE) ON CONFLICT (id) DO NOTHING;

-- ── Price alerts ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS price_alerts (
    id            BIGSERIAL PRIMARY KEY,
    ticker        TEXT NOT NULL,
    threshold     NUMERIC(12, 4) NOT NULL,
    direction     TEXT NOT NULL CHECK (direction IN ('above', 'below')),
    triggered_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_price_alerts_ticker ON price_alerts(ticker);

-- ── Options flow (SPEC Phase A — options-as-signal) ─────────────────────────
CREATE TABLE IF NOT EXISTS options_flow (
    ticker         TEXT NOT NULL,
    date           DATE NOT NULL,
    iv_rank        NUMERIC(6, 3),     -- 0–100, current IV vs 1yr range
    iv_percentile  NUMERIC(6, 3),     -- 0–100
    put_call_ratio NUMERIC(6, 3),
    unusual_volume BOOLEAN DEFAULT FALSE,
    signal         TEXT,              -- bullish_flow | bearish_flow | neutral | insufficient_data
    metadata       JSONB,
    PRIMARY KEY (ticker, date)
);

-- ── Options positions (SPEC Phase B+) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS options_positions (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL UNIQUE,   -- OCC symbol: AAPL250117C00150000
    underlying      TEXT NOT NULL,
    option_type     TEXT NOT NULL CHECK (option_type IN ('call', 'put')),
    strike          NUMERIC(12, 4) NOT NULL,
    expiry          DATE NOT NULL,
    qty             INTEGER NOT NULL,
    entry_premium   NUMERIC(10, 4),
    current_premium NUMERIC(10, 4),
    delta_snapshot  NUMERIC(8, 6),
    gamma_snapshot  NUMERIC(10, 8),
    theta_snapshot  NUMERIC(10, 8),
    vega_snapshot   NUMERIC(10, 8),
    strategy_type   TEXT,                   -- directional | straddle | collar | hedge
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_options_pos_underlying ON options_positions(underlying, expiry);

-- ── Calendar events — feeds the dashboard Calendar tab ─────────────────────
CREATE TABLE IF NOT EXISTS calendar_events (
    id            BIGSERIAL PRIMARY KEY,
    event_date    DATE NOT NULL,
    event_type    TEXT NOT NULL,    -- earnings | fomc | cpi | jobs_report | other
    ticker        TEXT,             -- NULL for macro-wide events (FOMC, CPI, NFP)
    title         TEXT NOT NULL,
    description   TEXT,
    plan_of_action JSONB,           -- cached analysis, generated on-demand
    plan_generated_at TIMESTAMPTZ
);
-- NULL tickers aren't equal to each other under a plain UNIQUE constraint, so
-- macro events (ticker IS NULL) would dedupe-fail on re-sync. Use an
-- expression index on COALESCE(ticker, '') instead.
CREATE UNIQUE INDEX IF NOT EXISTS ux_calendar_events
    ON calendar_events (event_date, event_type, (COALESCE(ticker, '')));
CREATE INDEX IF NOT EXISTS ix_calendar_events_date ON calendar_events(event_date);

-- ── Trade Simulator ─────────────────────────────────────────────────────────
-- Single-row config + cash balance
CREATE TABLE IF NOT EXISTS sim_config (
    id               INTEGER PRIMARY KEY DEFAULT 1,
    starting_capital NUMERIC(14,2) NOT NULL DEFAULT 100000.00,
    cash             NUMERIC(14,2) NOT NULL DEFAULT 100000.00,
    enabled          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT sim_single_row CHECK (id = 1)
);
INSERT INTO sim_config (id, starting_capital, cash, enabled)
    VALUES (1, 100000.00, 100000.00, FALSE) ON CONFLICT (id) DO NOTHING;

-- Open positions (one row per ticker, average-cost method)
CREATE TABLE IF NOT EXISTS sim_positions (
    ticker       TEXT PRIMARY KEY,
    qty          INTEGER NOT NULL,
    avg_cost     NUMERIC(12,4) NOT NULL,
    cost_basis   NUMERIC(14,4) NOT NULL,
    first_entry  DATE NOT NULL,
    last_updated DATE NOT NULL
);

-- Every simulated buy and sell
CREATE TABLE IF NOT EXISTS sim_trades (
    id            BIGSERIAL PRIMARY KEY,
    date          DATE NOT NULL,
    ticker        TEXT NOT NULL,
    side          TEXT NOT NULL CHECK (side IN ('buy','sell')),
    qty           INTEGER NOT NULL,
    price         NUMERIC(12,4) NOT NULL,
    notional      NUMERIC(14,4) NOT NULL,
    realized_pnl  NUMERIC(14,4),           -- NULL for buys, set on sells
    target_weight NUMERIC(6,4),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_sim_trades_date   ON sim_trades(date DESC);
CREATE INDEX IF NOT EXISTS ix_sim_trades_ticker ON sim_trades(ticker, date DESC);

-- Daily equity snapshots (mirrors portfolio_snapshots structure)
CREATE TABLE IF NOT EXISTS sim_snapshots (
    date              DATE PRIMARY KEY,
    cash              NUMERIC(14,2) NOT NULL,
    positions_value   NUMERIC(14,2) NOT NULL,
    total_value       NUMERIC(14,2) NOT NULL,
    daily_return      NUMERIC(8,6),
    cumulative_return NUMERIC(8,6),
    drawdown          NUMERIC(8,6),
    open_positions    INTEGER DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Weekly performance roll-ups
CREATE TABLE IF NOT EXISTS sim_weekly_reports (
    week_ending       DATE PRIMARY KEY,
    starting_value    NUMERIC(14,2),
    ending_value      NUMERIC(14,2),
    weekly_return_pct NUMERIC(8,4),
    total_return_pct  NUMERIC(8,4),
    max_drawdown_pct  NUMERIC(8,4),
    sharpe_weekly     NUMERIC(8,4),
    total_trades      INTEGER DEFAULT 0,
    winning_trades    INTEGER DEFAULT 0,
    losing_trades     INTEGER DEFAULT 0,
    win_rate_pct      NUMERIC(8,4),
    avg_win           NUMERIC(14,4),
    avg_loss          NUMERIC(14,4),
    profit_factor     NUMERIC(8,4),
    gross_profit      NUMERIC(14,4) DEFAULT 0,
    gross_loss        NUMERIC(14,4) DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
