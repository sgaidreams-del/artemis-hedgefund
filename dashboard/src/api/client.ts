import type {
  ActivityResponse,
  AlertsResponse,
  BenchmarkData,
  CalendarEvent,
  ConnectionStatus,
  CorrelationData,
  DrawdownPoint,
  EarningsSignal,
  HedgeReview,
  KillSwitchState,
  LearningsResponse,
  NewsResponse,
  OptionsFlowSignal,
  OptionsPosition,
  OptionsStatus,
  PlanOfAction,
  PortfolioHistory,
  PortfolioMetrics,
  PortfolioOverview,
  PriceAlert,
  RebalanceResult,
  RegimeData,
  ReturnsHeatmapPoint,
  SimPosition,
  SimSnapshot,
  SimStatus,
  SimTrade,
  SimWeeklyReport,
  StraddleExecutionResult,
  TradesResponse,
} from '../types'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

// The API rejects state-changing requests without this header (CSRF guard,
// see dashboard_api/main.py).
const WRITE_HEADERS = { 'X-Artemis-Client': 'dashboard' }

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: body ? { ...WRITE_HEADERS, 'Content-Type': 'application/json' } : WRITE_HEADERS,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`, { method: 'DELETE', headers: WRITE_HEADERS })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  // existing
  portfolioOverview: () => get<PortfolioOverview>('/portfolio/overview'),
  portfolioHistory: (period = '1M') => get<PortfolioHistory>(`/portfolio/history?period=${period}`),
  connectionStatus: () => get<ConnectionStatus>('/connections/status'),
  trades: () => get<TradesResponse>('/trades'),
  learnings: () => get<LearningsResponse>('/learnings'),
  calendarEvents: (daysAhead = 60) => get<{ events: CalendarEvent[] }>(`/calendar/events?days_ahead=${daysAhead}`),
  calendarSync: () => post<{ synced: number }>('/calendar/sync'),
  eventPlan: (id: number) => get<PlanOfAction>(`/calendar/events/${id}/plan`),

  // kill switch
  killSwitchStatus: () => get<KillSwitchState>('/kill-switch'),
  killSwitchPause: (reason?: string) => post<KillSwitchState>('/kill-switch/pause', { reason: reason ?? null }),
  killSwitchResume: () => post<KillSwitchState>('/kill-switch/resume'),

  // analytics
  portfolioMetrics: () => get<PortfolioMetrics>('/analytics/metrics'),
  returnsHeatmap: (years = 2) => get<{ returns: ReturnsHeatmapPoint[] }>(`/analytics/returns-heatmap?years=${years}`),
  benchmark: (period = '1M') => get<BenchmarkData>(`/analytics/benchmark?period=${period}`),
  correlation: () => get<CorrelationData>('/analytics/correlation'),
  drawdown: () => get<{ points: DrawdownPoint[] }>('/analytics/drawdown'),

  // regime
  regime: () => get<RegimeData>('/regime/current'),

  // alerts
  alerts: () => get<AlertsResponse>('/alerts'),
  createAlert: (ticker: string, threshold: number, direction: 'above' | 'below') =>
    post<PriceAlert>('/alerts', { ticker, threshold, direction }),
  deleteAlert: (id: number) => del<{ deleted: boolean }>(`/alerts/${id}`),
  checkAlerts: () => post<{ checked: number; triggered: unknown[] }>('/alerts/check'),

  // news
  news: (limit = 20) => get<NewsResponse>(`/news?limit=${limit}`),

  // options
  optionsStatus: () => get<OptionsStatus>('/options/status'),
  optionsFlow: (days = 14) => get<{ signals: OptionsFlowSignal[] }>(`/options/flow?days=${days}`),
  optionsPositions: () => get<{ positions: OptionsPosition[] }>('/options/positions'),
  hedgeReview: () => get<HedgeReview>('/options/hedge-review'),
  earningsScan: () => get<{ signals: EarningsSignal[] }>('/options/earnings-scan'),
  executeStraddle: (ticker: string, earningsDate: string) =>
    post<StraddleExecutionResult>('/options/earnings-scan/execute', { ticker, earnings_date: earningsDate }),

  // trading
  previewRebalance: () => post<RebalanceResult>('/trading/rebalance/preview'),
  executeRebalance: () => post<RebalanceResult>('/trading/rebalance/execute'),

  // activity
  activity: (limit = 50) => get<ActivityResponse>(`/activity?limit=${limit}`),

  // simulator
  simStatus: () => get<SimStatus>('/sim/status'),
  simPositions: () => get<{ positions: SimPosition[] }>('/sim/positions'),
  simTrades: (limit = 100) => get<{ trades: SimTrade[] }>(`/sim/trades?limit=${limit}`),
  simSnapshots: (days = 90) => get<{ snapshots: SimSnapshot[] }>(`/sim/snapshots?days=${days}`),
  simReports: () => get<{ reports: SimWeeklyReport[] }>('/sim/reports'),
  simToggle: (enabled: boolean) => post<{ enabled: boolean; status: string }>('/sim/toggle', { enabled }),
  simReset: () => post<{ status: string }>('/sim/reset'),
  simRun: () => post<{ status: string; bought?: number; sold?: number; total_value?: number }>('/sim/run'),
  simGenerateReport: () => post<SimWeeklyReport>('/sim/generate-report'),
}
