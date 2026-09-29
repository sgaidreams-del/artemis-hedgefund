import { useEffect, useState } from 'react'
import { AreaChart, Area, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import type { HistoryPoint, PortfolioOverview } from '../types'
import { formatUsd, formatPct } from '../components/StatPill'
import RegimeBanner from '../components/RegimeBanner'
import MetricsStrip from '../components/MetricsStrip'
import BenchmarkChart from '../components/BenchmarkChart'
import DrawdownChart from '../components/DrawdownChart'
import PositionTreemap from '../components/PositionTreemap'
import CorrelationMatrix from '../components/CorrelationMatrix'
import NewsFeed from '../components/NewsFeed'
import AlertsPanel from '../components/AlertsPanel'
import ActivityPanel from '../components/ActivityPanel'
import ReturnsHeatmap from '../components/ReturnsHeatmap'
import AutoResearchStatus from '../components/AutoResearchStatus'
import RebalanceButton from '../components/RebalanceButton'

export default function Overview() {
  const [overview, setOverview] = useState<PortfolioOverview | null>(null)
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.portfolioOverview(), api.portfolioHistory()])
      .then(([o, h]) => {
        setOverview(o)
        setHistory(h.points)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="p-6 text-sm" style={{ color: 'var(--color-text-secondary)' }}>Loading portfolio…</div>
  }

  if (!overview?.connected) {
    return (
      <div className="p-6">
        <div
          className="rounded-xl p-6 max-w-md"
          style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        >
          <h2 className="text-lg font-semibold mb-2">Broker not connected</h2>
          <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            {overview?.message ?? 'Add ALPACA_API_KEY / ALPACA_API_SECRET to .env, then restart the API.'}
          </p>
        </div>
        <div className="mt-6 max-w-5xl">
          <AutoResearchStatus />
        </div>
      </div>
    )
  }

  const { account, positions } = overview
  const equity = account?.equity ?? 0

  const chartData = history.map((h) => ({
    x: h.date ?? (h.timestamp ? new Date(h.timestamp * 1000).toISOString().slice(0, 10) : ''),
    y: h.total_value ?? h.equity ?? null,
  })).filter((p) => p.y != null)

  const up = (account?.day_pl ?? 0) >= 0

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Regime banner — full width at top */}
      <RegimeBanner />

      {/* Activity / alerts — surfaces halts and reconciliation findings */}
      <ActivityPanel />

      {/* Hero equity + sparkline */}
      <div className="mb-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>Portfolio Value</div>
      <div className="text-5xl font-semibold tracking-tight mb-2">{formatUsd(equity)}</div>
      <div className="flex items-center gap-2 mb-6">
        <span style={{ color: up ? 'var(--color-up)' : 'var(--color-down)' }} className="text-base font-medium">
          {up ? '+' : ''}{formatUsd(account?.day_pl)} ({formatPct(account?.day_pl_pct)}) today
        </span>
      </div>

      {chartData.length > 1 ? (
        <div className="h-48 mb-8 -ml-2">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={up ? '#00c805' : '#ff5000'} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={up ? '#00c805' : '#ff5000'} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="x" hide />
              <YAxis hide domain={['auto', 'auto']} />
              <Tooltip
                contentStyle={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 8 }}
                labelStyle={{ color: 'var(--color-text-secondary)' }}
                formatter={(v) => [formatUsd(Number(v)), 'Value']}
              />
              <Area type="monotone" dataKey="y" stroke={up ? '#00c805' : '#ff5000'} fill="url(#grad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div
          className="h-24 mb-8 flex items-center justify-center rounded-lg text-xs"
          style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text-secondary)' }}
        >
          Equity history will appear here once the daily pipeline has run for a few days.
        </div>
      )}

      {/* Performance metrics */}
      <MetricsStrip />

      {/* Benchmark comparison */}
      <BenchmarkChart period="1M" />

      {/* Drawdown */}
      <DrawdownChart />

      {/* Returns heatmap */}
      <ReturnsHeatmap />

      {/* Account quick stats */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <Stat label="Cash" value={formatUsd(account?.cash)} />
        <Stat label="Equity" value={formatUsd(account?.equity)} />
        <Stat label="Account Status" value={account?.status ?? '—'} />
      </div>

      {/* Manual rebalance trigger */}
      <div className="mb-8">
        <RebalanceButton />
      </div>

      {/* Concentration warnings inline with positions header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
          HOLDINGS ({positions.length})
        </h3>
        {positions.filter((p) => p.market_value / equity > 0.10).map((p) => (
          <span
            key={p.ticker}
            className="text-xs px-2 py-0.5 rounded-full"
            style={{ backgroundColor: 'rgba(250,204,21,0.12)', border: '1px solid #facc15', color: '#facc15' }}
          >
            ⚠ {p.ticker} {((p.market_value / equity) * 100).toFixed(0)}%
          </span>
        ))}
      </div>

      {/* Position treemap */}
      <PositionTreemap positions={positions} totalEquity={equity} />

      {/* Positions list */}
      {positions.length === 0 ? (
        <div className="text-sm py-8 text-center rounded-lg mb-6" style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text-secondary)' }}>
          No open positions yet.
        </div>
      ) : (
        <div className="rounded-lg overflow-hidden mb-6" style={{ border: '1px solid var(--color-border)' }}>
          {positions.map((p) => (
            <div
              key={p.ticker}
              className="flex items-center justify-between px-4 py-3"
              style={{ borderBottom: '1px solid var(--color-border)', backgroundColor: 'var(--color-surface)' }}
            >
              <div className="font-medium">{p.ticker}</div>
              <div className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>{p.qty} sh @ {formatUsd(p.avg_entry_price)}</div>
              <div className="text-right">
                <div>{formatUsd(p.market_value)}</div>
                <div style={{ color: p.unrealized_pl >= 0 ? 'var(--color-up)' : 'var(--color-down)' }} className="text-sm">
                  {formatUsd(p.unrealized_pl)} ({formatPct(p.unrealized_plpc)})
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Correlation matrix */}
      <CorrelationMatrix />

      {/* Two-column bottom row */}
      <div className="grid grid-cols-2 gap-6">
        <div>
          <NewsFeed />
          <AlertsPanel />
        </div>
        <AutoResearchStatus />
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
      <div className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>{label}</div>
      <div className="text-lg font-medium">{value}</div>
    </div>
  )
}
