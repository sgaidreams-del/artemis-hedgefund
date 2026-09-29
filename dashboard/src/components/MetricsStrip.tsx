import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PortfolioMetrics } from '../types'

function fmt(v: number | null, decimals = 2): string {
  if (v == null) return '—'
  return v.toFixed(decimals)
}

function fmtPct(v: number | null): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

interface MetricProps {
  label: string
  value: string
  color?: string
  hint?: string
}

function Metric({ label, value, color, hint }: MetricProps) {
  return (
    <div
      className="flex flex-col gap-0.5 px-4 py-3 rounded-lg"
      title={hint}
      style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
    >
      <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{label}</div>
      <div className="text-lg font-semibold tabular-nums" style={{ color: color ?? 'var(--color-text-primary)' }}>
        {value}
      </div>
    </div>
  )
}

export default function MetricsStrip() {
  const [metrics, setMetrics] = useState<PortfolioMetrics | null>(null)

  useEffect(() => {
    api.portfolioMetrics().then(setMetrics).catch(() => null)
  }, [])

  if (!metrics || metrics.data_source === 'none') {
    return (
      <div className="text-xs py-2 text-center rounded-lg mb-6"
        style={{ color: 'var(--color-text-secondary)', backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        Performance metrics will appear once the portfolio has trade history (Phase 5+).
      </div>
    )
  }

  const ddColor = metrics.max_drawdown != null && metrics.max_drawdown < -0.10
    ? 'var(--color-down)'
    : metrics.max_drawdown != null && metrics.max_drawdown < -0.05
    ? '#facc15'
    : undefined

  return (
    <div className="grid grid-cols-5 gap-3 mb-6">
      <Metric
        label="Sharpe (ann.)"
        value={fmt(metrics.sharpe)}
        color={metrics.sharpe != null && metrics.sharpe > 1 ? 'var(--color-up)' : metrics.sharpe != null && metrics.sharpe < 0 ? 'var(--color-down)' : undefined}
        hint="Annualized Sharpe ratio. >1 is good."
      />
      <Metric
        label="Sortino (ann.)"
        value={fmt(metrics.sortino)}
        color={metrics.sortino != null && metrics.sortino > 1.5 ? 'var(--color-up)' : undefined}
        hint="Like Sharpe but only penalizes downside volatility."
      />
      <Metric
        label="Max Drawdown"
        value={fmtPct(metrics.max_drawdown)}
        color={ddColor}
        hint="Largest peak-to-trough decline."
      />
      <Metric
        label="Win Rate"
        value={fmtPct(metrics.win_rate)}
        hint={`${metrics.trades_count} trades`}
      />
      <Metric
        label="Profit Factor"
        value={fmt(metrics.profit_factor)}
        color={metrics.profit_factor != null && metrics.profit_factor > 1.5 ? 'var(--color-up)' : metrics.profit_factor != null && metrics.profit_factor < 1 ? 'var(--color-down)' : undefined}
        hint="Sum of wins / sum of losses. >1.5 is healthy."
      />
    </div>
  )
}
