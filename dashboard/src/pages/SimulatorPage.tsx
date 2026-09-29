import { useEffect, useState } from 'react'
import {
  AreaChart, Area, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine,
} from 'recharts'
import { api } from '../api/client'
import type { SimPosition, SimSnapshot, SimStatus, SimTrade, SimWeeklyReport } from '../types'
import { formatUsd } from '../components/StatPill'

function pctColor(v: number | null | undefined) {
  if (v == null) return 'var(--color-text-secondary)'
  return v >= 0 ? 'var(--color-up)' : 'var(--color-down)'
}

function fmt2(v: number | null | undefined) {
  if (v == null) return '—'
  return v.toFixed(2)
}

function Toggle({ enabled, onChange }: { enabled: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!enabled)}
      className="relative inline-flex items-center rounded-full transition-colors focus:outline-none"
      style={{
        width: 44,
        height: 24,
        backgroundColor: enabled ? 'var(--color-up)' : 'var(--color-border)',
      }}
      aria-label={enabled ? 'Disable simulator' : 'Enable simulator'}
    >
      <span
        className="inline-block rounded-full transition-transform"
        style={{
          width: 18,
          height: 18,
          backgroundColor: '#fff',
          transform: enabled ? 'translateX(22px)' : 'translateX(3px)',
        }}
      />
    </button>
  )
}

function MetricCard({ label, value, sub, valueColor }: {
  label: string; value: string; sub?: string; valueColor?: string
}) {
  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-1"
      style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
    >
      <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{label}</div>
      <div className="text-xl font-semibold" style={{ color: valueColor ?? 'var(--color-text-primary)' }}>{value}</div>
      {sub && <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{sub}</div>}
    </div>
  )
}

export default function SimulatorPage() {
  const [status, setStatus] = useState<SimStatus | null>(null)
  const [positions, setPositions] = useState<SimPosition[]>([])
  const [trades, setTrades] = useState<SimTrade[]>([])
  const [snapshots, setSnapshots] = useState<SimSnapshot[]>([])
  const [reports, setReports] = useState<SimWeeklyReport[]>([])
  const [loading, setLoading] = useState(true)
  const [toggling, setToggling] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [running, setRunning] = useState(false)

  function reload() {
    setLoading(true)
    Promise.all([
      api.simStatus(),
      api.simPositions(),
      api.simTrades(100),
      api.simSnapshots(90),
      api.simReports(),
    ]).then(([s, p, t, ss, r]) => {
      setStatus(s)
      setPositions(p.positions)
      setTrades(t.trades)
      setSnapshots(ss.snapshots)
      setReports(r.reports)
    }).catch(() => null).finally(() => setLoading(false))
  }

  useEffect(() => { reload() }, [])

  async function handleToggle(enabled: boolean) {
    setToggling(true)
    try {
      await api.simToggle(enabled)
      setStatus((s) => s ? { ...s, enabled } : s)
    } finally {
      setToggling(false)
    }
  }

  async function handleRunNow() {
    setRunning(true)
    try {
      await api.simRun()
      reload()
    } finally {
      setRunning(false)
    }
  }

  async function handleReset() {
    if (!window.confirm('Reset simulator? This will clear all positions, trades, and history and restore $100,000.')) return
    setResetting(true)
    try {
      await api.simReset()
      reload()
    } finally {
      setResetting(false)
    }
  }

  async function handleGenerateReport() {
    await api.simGenerateReport()
    const r = await api.simReports()
    setReports(r.reports)
  }

  if (loading) {
    return <div className="p-6 text-sm" style={{ color: 'var(--color-text-secondary)' }}>Loading simulator…</div>
  }

  const enabled = status?.enabled ?? false
  const startingCapital = status?.starting_capital ?? 100_000
  const totalValue = status?.total_value ?? startingCapital
  const totalPnl = status?.total_pnl ?? 0
  const totalReturnPct = status?.total_return_pct ?? 0

  const chartData = snapshots.map((s) => ({
    date: s.date,
    value: s.total_value,
    drawdown: s.drawdown != null ? s.drawdown * 100 : null,
  }))

  const maxDD = snapshots.length > 0
    ? Math.min(...snapshots.map((s) => s.drawdown ?? 0)) * 100
    : 0

  const openCount = positions.length
  const buyCount = trades.filter((t) => t.side === 'buy').length
  const sellCount = trades.filter((t) => t.side === 'sell').length

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Trade Simulator</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
            Paper-trades ensemble recommendations against a virtual $100K portfolio — no broker calls.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-sm" style={{ color: toggling ? 'var(--color-text-secondary)' : 'var(--color-text-primary)' }}>
              {enabled ? 'Running' : 'Paused'}
            </span>
            <Toggle enabled={enabled} onChange={handleToggle} />
          </div>
          <button
            onClick={handleRunNow}
            disabled={running}
            className="px-3 py-1.5 rounded-lg text-xs transition-colors"
            style={{
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              color: running ? 'var(--color-text-secondary)' : 'var(--color-up)',
              cursor: running ? 'not-allowed' : 'pointer',
            }}
          >
            {running ? 'Running…' : 'Run Now'}
          </button>
          <button
            onClick={handleReset}
            disabled={resetting}
            className="px-3 py-1.5 rounded-lg text-xs transition-colors"
            style={{
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              color: resetting ? 'var(--color-text-secondary)' : 'var(--color-down)',
              cursor: resetting ? 'not-allowed' : 'pointer',
            }}
          >
            {resetting ? 'Resetting…' : 'Reset'}
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <MetricCard
          label="Total Value"
          value={formatUsd(totalValue)}
          sub={`Started ${formatUsd(startingCapital)}`}
        />
        <MetricCard
          label="Total P/L"
          value={`${totalPnl >= 0 ? '+' : ''}${formatUsd(totalPnl)}`}
          sub={`${totalReturnPct >= 0 ? '+' : ''}${totalReturnPct.toFixed(2)}%`}
          valueColor={pctColor(totalPnl)}
        />
        <MetricCard
          label="Cash"
          value={formatUsd(status?.cash ?? 0)}
          sub={`${formatUsd(status?.positions_value ?? 0)} in positions`}
        />
        <MetricCard
          label="Max Drawdown"
          value={`${maxDD.toFixed(2)}%`}
          sub={`${openCount} open · ${buyCount}B / ${sellCount}S`}
          valueColor={maxDD < -5 ? 'var(--color-down)' : 'var(--color-text-primary)'}
        />
      </div>

      {/* Equity curve */}
      {chartData.length > 0 && (
        <div
          className="rounded-xl p-4 mb-6"
          style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        >
          <div className="text-sm font-medium mb-3">Equity Curve</div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="simGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--color-up)" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="var(--color-up)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} axisLine={false}
                tickFormatter={(d: string) => d.slice(5)} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false}
                tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} width={48} />
              <Tooltip
                formatter={(v) => [formatUsd(Number(v)), 'Value']}
                labelStyle={{ color: 'var(--color-text-secondary)', fontSize: 11 }}
                contentStyle={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', fontSize: 12 }}
              />
              <ReferenceLine y={startingCapital} stroke="var(--color-border)" strokeDasharray="3 3" />
              <Area type="monotone" dataKey="value" stroke="var(--color-up)" fill="url(#simGrad)" strokeWidth={1.5} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Open positions */}
        <div
          className="rounded-xl p-4"
          style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        >
          <div className="text-sm font-medium mb-3">Open Positions ({positions.length})</div>
          {positions.length === 0 ? (
            <div className="text-sm py-4 text-center" style={{ color: 'var(--color-text-secondary)' }}>
              No open positions — {enabled ? 'waiting for next pipeline run' : 'enable simulator to start trading'}
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: 'var(--color-text-secondary)', borderBottom: '1px solid var(--color-border)' }}>
                  <th className="text-left py-1.5">Ticker</th>
                  <th className="text-right py-1.5">Qty</th>
                  <th className="text-right py-1.5">Avg Cost</th>
                  <th className="text-right py-1.5">Price</th>
                  <th className="text-right py-1.5">Unreal. P/L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.ticker} style={{ borderBottom: '1px solid var(--color-border)' }}>
                    <td className="py-1.5 font-medium">{p.ticker}</td>
                    <td className="text-right py-1.5">{p.qty}</td>
                    <td className="text-right py-1.5">${fmt2(p.avg_cost)}</td>
                    <td className="text-right py-1.5">${fmt2(p.current_price)}</td>
                    <td className="text-right py-1.5" style={{ color: pctColor(p.unrealized_pnl) }}>
                      {p.unrealized_pnl >= 0 ? '+' : ''}{formatUsd(p.unrealized_pnl)}
                      <span className="ml-1 text-xs" style={{ color: pctColor(p.unrealized_pct) }}>
                        ({p.unrealized_pct >= 0 ? '+' : ''}{p.unrealized_pct.toFixed(1)}%)
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Recent trades */}
        <div
          className="rounded-xl p-4"
          style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        >
          <div className="text-sm font-medium mb-3">Recent Trades</div>
          {trades.length === 0 ? (
            <div className="text-sm py-4 text-center" style={{ color: 'var(--color-text-secondary)' }}>
              No trades yet
            </div>
          ) : (
            <div className="overflow-y-auto" style={{ maxHeight: 260 }}>
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ color: 'var(--color-text-secondary)', borderBottom: '1px solid var(--color-border)' }}>
                    <th className="text-left py-1.5">Date</th>
                    <th className="text-left py-1.5">Ticker</th>
                    <th className="text-left py-1.5">Side</th>
                    <th className="text-right py-1.5">Qty</th>
                    <th className="text-right py-1.5">Price</th>
                    <th className="text-right py-1.5">P/L</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--color-border)' }}>
                      <td className="py-1.5" style={{ color: 'var(--color-text-secondary)' }}>{t.date}</td>
                      <td className="py-1.5 font-medium">{t.ticker}</td>
                      <td className="py-1.5" style={{ color: t.side === 'buy' ? 'var(--color-up)' : 'var(--color-down)' }}>
                        {t.side.toUpperCase()}
                      </td>
                      <td className="text-right py-1.5">{t.qty}</td>
                      <td className="text-right py-1.5">${fmt2(t.price)}</td>
                      <td className="text-right py-1.5" style={{ color: t.realized_pnl != null ? pctColor(t.realized_pnl) : 'var(--color-text-secondary)' }}>
                        {t.realized_pnl != null
                          ? `${t.realized_pnl >= 0 ? '+' : ''}${formatUsd(t.realized_pnl)}`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Weekly reports */}
      <div
        className="rounded-xl p-4"
        style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-medium">Weekly Performance Reports</div>
          <button
            onClick={handleGenerateReport}
            className="text-xs px-2 py-1 rounded"
            style={{
              backgroundColor: 'var(--color-surface-hover)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-secondary)',
              cursor: 'pointer',
            }}
          >
            Regenerate
          </button>
        </div>
        {reports.length === 0 ? (
          <div className="text-sm py-4 text-center" style={{ color: 'var(--color-text-secondary)' }}>
            No weekly reports yet — reports are generated every Friday automatically.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: 'var(--color-text-secondary)', borderBottom: '1px solid var(--color-border)' }}>
                  <th className="text-left py-1.5 pr-4">Week</th>
                  <th className="text-right py-1.5 pr-3">Weekly Ret.</th>
                  <th className="text-right py-1.5 pr-3">Total Ret.</th>
                  <th className="text-right py-1.5 pr-3">Max DD</th>
                  <th className="text-right py-1.5 pr-3">Sharpe</th>
                  <th className="text-right py-1.5 pr-3">Trades</th>
                  <th className="text-right py-1.5 pr-3">Win %</th>
                  <th className="text-right py-1.5 pr-3">Profit Factor</th>
                  <th className="text-right py-1.5">Ending Value</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <tr key={r.week_ending} style={{ borderBottom: '1px solid var(--color-border)' }}>
                    <td className="py-1.5 pr-4" style={{ color: 'var(--color-text-secondary)' }}>{r.week_ending}</td>
                    <td className="text-right py-1.5 pr-3" style={{ color: pctColor(r.weekly_return_pct) }}>
                      {r.weekly_return_pct != null ? `${r.weekly_return_pct >= 0 ? '+' : ''}${r.weekly_return_pct.toFixed(2)}%` : '—'}
                    </td>
                    <td className="text-right py-1.5 pr-3" style={{ color: pctColor(r.total_return_pct) }}>
                      {r.total_return_pct != null ? `${r.total_return_pct >= 0 ? '+' : ''}${r.total_return_pct.toFixed(2)}%` : '—'}
                    </td>
                    <td className="text-right py-1.5 pr-3" style={{ color: (r.max_drawdown_pct ?? 0) < -5 ? 'var(--color-down)' : 'var(--color-text-primary)' }}>
                      {r.max_drawdown_pct != null ? `${r.max_drawdown_pct.toFixed(2)}%` : '—'}
                    </td>
                    <td className="text-right py-1.5 pr-3">
                      {r.sharpe_weekly != null ? r.sharpe_weekly.toFixed(2) : '—'}
                    </td>
                    <td className="text-right py-1.5 pr-3">{r.total_trades}</td>
                    <td className="text-right py-1.5 pr-3">
                      {r.win_rate_pct != null ? `${r.win_rate_pct.toFixed(0)}%` : '—'}
                    </td>
                    <td className="text-right py-1.5 pr-3">
                      {r.profit_factor != null ? r.profit_factor.toFixed(2) : '—'}
                    </td>
                    <td className="text-right py-1.5">{formatUsd(r.ending_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
