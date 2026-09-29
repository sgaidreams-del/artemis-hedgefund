export interface Account {
  equity: number
  cash: number
  buying_power: number
  last_equity: number
  day_pl: number
  day_pl_pct: number
  status: string
  pattern_day_trader: boolean
}

export interface Position {
  ticker: string
  qty: number
  avg_entry_price: number
  current_price: number
  market_value: number
  unrealized_pl: number
  unrealized_plpc: number
  side: string
}

export interface PortfolioOverview {
  connected: boolean
  message?: string
  account: Account | null
  positions: Position[]
}

export interface HistoryPoint {
  date?: string
  timestamp?: number
  total_value?: number | null
  equity?: number
  daily_return?: number | null
  cumulative_return?: number | null
  drawdown?: number | null
  regime?: string | null
}

export interface PortfolioHistory {
  source: 'internal_snapshots' | 'alpaca_ledger' | 'none'
  points: HistoryPoint[]
}

export interface ConnectionCheck {
  connected: boolean
  reason: string | null
  latency_ms: number | null
}

export interface ConnectionStatus {
  alpaca: ConnectionCheck
  postgres: ConnectionCheck
  redis: ConnectionCheck
  deepseek: ConnectionCheck
}

export interface Trade {
  trade_id: string
  timestamp: string
  ticker: string
  side: string
  quantity: number
  order_type: string
  limit_price: number | null
  fill_price: number | null
  slippage_bps: number | null
  signals: Record<string, unknown> | null
  risk_snapshot: Record<string, unknown> | null
  rationale: string | null
}

export interface TradesResponse {
  trades: Trade[]
  empty_reason: string | null
}

export interface Learning {
  id: number
  ticker: string
  trade_date: string
  action: string
  entry_price: number | null
  regime: string | null
  status: string
  actual_return_5d: number | null
  alpha_vs_spy_5d: number | null
  reflection: string | null
  resolved_date: string | null
  label: string | null
}

export interface LearningsResponse {
  learnings: Learning[]
  empty_reason: string | null
}

export interface CalendarEvent {
  id: number
  event_date: string
  event_type: 'fomc' | 'cpi' | 'jobs_report' | 'earnings' | 'other'
  ticker: string | null
  title: string
  description: string
  days_out: number
  plan_available: boolean
  plan_eligible: boolean
  plan_generated_at: string | null
}

export interface PlanOfAction {
  available: boolean
  reason?: string
  cached?: boolean
  plan?: {
    quant_stats: {
      n: number
      note?: string
      avg_move_pct?: number
      std_move_pct?: number
      max_move_pct?: number
    }
    narrative: string
    reaction_ticker: string
  }
}

// ── Kill switch ───────────────────────────────────────────────────────────────
export interface KillSwitchState {
  paused: boolean
  set_at: string | null
  reason: string | null
}

// ── Portfolio analytics ───────────────────────────────────────────────────────
export interface PortfolioMetrics {
  sharpe: number | null
  sortino: number | null
  max_drawdown: number | null
  win_rate: number | null
  profit_factor: number | null
  obs_count: number
  trades_count: number
  data_source: 'snapshots' | 'none'
  empty_reason?: string
}

export interface ReturnsHeatmapPoint {
  date: string
  return_pct: number
}

export interface BenchmarkPoint {
  date: string
  portfolio: number | null
  spy: number | null
}

export interface BenchmarkData {
  points: BenchmarkPoint[]
}

export interface CorrelationData {
  tickers: string[]
  matrix: number[][]
  empty_reason?: string
}

export interface DrawdownPoint {
  date: string
  drawdown: number
}

// ── Regime ───────────────────────────────────────────────────────────────────
export interface RegimeData {
  regime: 'bull' | 'bear' | 'sideways' | 'unknown'
  confidence: number | null
  source: 'hmm' | 'ma_rules' | 'none'
  ma50: number | null
  ma200: number | null
  realized_vol_20d: number | null
  spy_price: number | null
}

// ── Price alerts ─────────────────────────────────────────────────────────────
export interface PriceAlert {
  id: number
  ticker: string
  threshold: number
  direction: 'above' | 'below'
  triggered_at: string | null
  created_at: string
}

export interface AlertsResponse {
  alerts: PriceAlert[]
}

// ── Activity feed ────────────────────────────────────────────────────────────
export interface ActivityEntry {
  timestamp: string
  component: string
  action: string
  status: string
  [key: string]: unknown
}

export interface ActivityResponse {
  entries: ActivityEntry[]
  empty_reason: string | null
}

// ── News ─────────────────────────────────────────────────────────────────────
export interface NewsArticle {
  id: number | string
  timestamp: string
  source: string | null
  headline: string
  url: string | null
  tickers: string[]
  sentiment_score: number | null
  sentiment_label: string | null
}

export interface NewsResponse {
  articles: NewsArticle[]
  source: 'db' | 'yfinance_fallback'
  empty_reason: string | null
}

// ── Options ──────────────────────────────────────────────────────────────────
export interface OptionsStatus {
  phase_a_flow: boolean
  phase_b_execution: boolean
  phase_c_earnings: boolean
  phase_d_hedge: boolean
}

export interface OptionsFlowSignal {
  ticker: string
  date: string
  iv_rank: number | null
  put_call_ratio: number | null
  unusual_volume: boolean
  signal: 'bullish_flow' | 'bearish_flow' | 'neutral' | 'insufficient_data'
}

export interface OptionsPosition {
  id: number
  symbol: string
  underlying: string
  option_type: 'call' | 'put'
  strike: number
  expiry: string
  qty: number
  entry_premium: number | null
  current_premium: number | null
  delta_snapshot: number | null
  strategy_type: string | null
  opened_at: string
}

export interface TailHedgeSignal {
  action: 'hedge' | 'no_hedge'
  score: number
  recommended_size_pct: number
  reason: string
}

export interface CollarSuggestion {
  ticker: string
  weight_pct: number
  suggested_strike: number | null
  rationale: string
}

export interface OptionContract {
  symbol: string
  underlying: string
  option_type: 'call' | 'put'
  strike: number
  expiry: string
  lastPrice: number | null
  impliedVolatility: number | null
  openInterest: number | null
  approx_delta: number
}

export interface HedgeReview {
  tail_hedge: TailHedgeSignal | null
  spy_put_contract: OptionContract | null
  collar_suggestions: CollarSuggestion[]
  portfolio_value: number
  positions_reviewed: number
  error?: string
}

export interface EarningsStraddleSignal {
  action: 'straddle' | 'skip'
  reason: string
  iv_rank: number | null
  days_to_earnings: number
}

export interface EarningsSignal {
  ticker: string
  earnings_date: string
  signal: EarningsStraddleSignal
}

export interface StraddleExecutionResult {
  call_order: Record<string, unknown> | null
  put_order: Record<string, unknown> | null
  total_premium: number
  error?: string
}

// ── Trade Simulator ──────────────────────────────────────────────────────────
export interface SimStatus {
  enabled: boolean
  starting_capital: number
  cash: number
  positions_value: number
  total_value: number
  total_pnl: number
  total_return_pct: number
  error?: string
}

export interface SimPosition {
  ticker: string
  qty: number
  avg_cost: number
  cost_basis: number
  current_price: number
  market_value: number
  unrealized_pnl: number
  unrealized_pct: number
  first_entry: string
  last_updated: string
}

export interface SimTrade {
  date: string
  ticker: string
  side: 'buy' | 'sell'
  qty: number
  price: number
  notional: number
  realized_pnl: number | null
  target_weight: number | null
  created_at: string
}

export interface SimSnapshot {
  date: string
  cash: number
  positions_value: number
  total_value: number
  daily_return: number | null
  cumulative_return: number | null
  drawdown: number | null
  open_positions: number
}

export interface SimWeeklyReport {
  week_ending: string
  starting_value: number
  ending_value: number
  weekly_return_pct: number | null
  total_return_pct: number | null
  max_drawdown_pct: number | null
  sharpe_weekly: number | null
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate_pct: number | null
  avg_win: number | null
  avg_loss: number | null
  profit_factor: number | null
  gross_profit: number | null
  gross_loss: number | null
}

// ── Trading / rebalance ──────────────────────────────────────────────────────
export interface RebalanceOrder {
  ticker: string
  side: 'buy' | 'sell'
  qty: number
  reason: string
  decision_id: number
  submitted: boolean
  filled?: boolean
  trade_id?: string
  fill_price?: number
}

export interface RebalanceResult {
  status: 'ok' | 'paused' | 'no_account' | 'drawdown_halt' | 'no_scores' | 'error'
  orders: RebalanceOrder[]
  dry_run?: boolean
  error?: string
}
