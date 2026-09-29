import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type {
  EarningsSignal,
  HedgeReview,
  OptionsFlowSignal,
  OptionsPosition,
  OptionsStatus,
  StraddleExecutionResult,
} from '../types'

const SIGNAL_CONFIG: Record<string, { color: string; label: string }> = {
  bullish_flow: { color: 'var(--color-up)', label: 'Bullish Flow' },
  bearish_flow: { color: 'var(--color-down)', label: 'Bearish Flow' },
  neutral: { color: 'var(--color-text-secondary)', label: 'Neutral' },
  insufficient_data: { color: 'var(--color-border)', label: 'Insufficient Data' },
}

function PhaseChip({ active, label }: { active: boolean; label: string }) {
  return (
    <div
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs"
      style={{
        backgroundColor: active ? 'rgba(0,200,5,0.1)' : 'var(--color-surface)',
        border: `1px solid ${active ? 'var(--color-up)' : 'var(--color-border)'}`,
        color: active ? 'var(--color-up)' : 'var(--color-text-secondary)',
      }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: active ? 'var(--color-up)' : 'var(--color-border)' }} />
      {label}
    </div>
  )
}

export default function OptionsPage() {
  const [status, setStatus] = useState<OptionsStatus | null>(null)
  const [signals, setSignals] = useState<OptionsFlowSignal[]>([])
  const [positions, setPositions] = useState<OptionsPosition[]>([])
  const [hedgeReview, setHedgeReview] = useState<HedgeReview | null>(null)
  const [earningsSignals, setEarningsSignals] = useState<EarningsSignal[]>([])
  const [loading, setLoading] = useState(true)
  const [executing, setExecuting] = useState<string | null>(null)
  const [executionResults, setExecutionResults] = useState<Record<string, StraddleExecutionResult>>({})

  useEffect(() => {
    Promise.all([
      api.optionsStatus(),
      api.optionsFlow(),
      api.optionsPositions(),
      api.hedgeReview(),
      api.earningsScan(),
    ]).then(([s, f, p, h, e]) => {
      setStatus(s)
      setSignals(f.signals)
      setPositions(p.positions)
      setHedgeReview(h)
      setEarningsSignals(e.signals)
    }).catch(() => null).finally(() => setLoading(false))
  }, [])

  async function handleExecuteStraddle(ticker: string, earningsDate: string) {
    if (!window.confirm(`Submit a real (paper) ATM straddle for ${ticker} ahead of its ${earningsDate} earnings?`)) {
      return
    }
    setExecuting(ticker)
    try {
      const result = await api.executeStraddle(ticker, earningsDate)
      setExecutionResults((prev) => ({ ...prev, [ticker]: result }))
    } catch (err) {
      setExecutionResults((prev) => ({
        ...prev,
        [ticker]: { call_order: null, put_order: null, total_premium: 0, error: String(err) },
      }))
    } finally {
      setExecuting(null)
    }
  }

  if (loading) {
    return <div className="p-6 text-sm" style={{ color: 'var(--color-text-secondary)' }}>Loading options data…</div>
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Phase status */}
      <div className="mb-6">
        <div className="text-xs font-semibold mb-3" style={{ color: 'var(--color-text-secondary)' }}>OPTIONS ENGINE STATUS</div>
        <div className="flex flex-wrap gap-2">
          <PhaseChip active={status?.phase_a_flow ?? false} label="Phase A: Flow Signal" />
          <PhaseChip active={status?.phase_b_execution ?? false} label="Phase B: Execution" />
          <PhaseChip active={status?.phase_c_earnings ?? false} label="Phase C: Earnings" />
          <PhaseChip active={status?.phase_d_hedge ?? false} label="Phase D: Hedging" />
        </div>
        {!status?.phase_b_execution && (
          <p className="mt-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            Enable execution: set <code className="px-1 rounded" style={{ backgroundColor: 'var(--color-surface-hover)' }}>OPTIONS_EXECUTION_ENABLED=true</code> in .env once Alpaca options approval is confirmed.
          </p>
        )}
      </div>

      {/* Open positions */}
      <div className="mb-6">
        <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>OPEN OPTIONS POSITIONS</div>
        {positions.length === 0 ? (
          <div className="rounded-lg p-6 text-sm text-center" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}>
            No open options positions.
            {!status?.phase_b_execution && ' Enable Phase B execution to start trading options.'}
          </div>
        ) : (
          <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--color-border)' }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-border)', backgroundColor: 'var(--color-surface-hover)' }}>
                  {['Symbol', 'Type', 'Strike', 'Expiry', 'Qty', 'Entry $', 'Current $', 'Δ', 'Strategy'].map((h) => (
                    <th key={h} className="px-4 py-2 text-left text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => {
                  const pnl = p.current_premium != null && p.entry_premium != null
                    ? (p.current_premium - p.entry_premium) * p.qty * 100
                    : null
                  return (
                    <tr key={p.id} style={{ borderBottom: '1px solid var(--color-border)', backgroundColor: 'var(--color-surface)' }}>
                      <td className="px-4 py-3 font-medium">{p.underlying}</td>
                      <td className="px-4 py-3" style={{ color: p.option_type === 'call' ? 'var(--color-up)' : 'var(--color-down)' }}>
                        {p.option_type.toUpperCase()}
                      </td>
                      <td className="px-4 py-3">${p.strike.toFixed(2)}</td>
                      <td className="px-4 py-3" style={{ color: 'var(--color-text-secondary)' }}>{p.expiry}</td>
                      <td className="px-4 py-3">{p.qty}</td>
                      <td className="px-4 py-3">{p.entry_premium != null ? `$${p.entry_premium.toFixed(2)}` : '—'}</td>
                      <td className="px-4 py-3">
                        {p.current_premium != null ? `$${p.current_premium.toFixed(2)}` : '—'}
                        {pnl != null && (
                          <span className="ml-2 text-xs" style={{ color: pnl >= 0 ? 'var(--color-up)' : 'var(--color-down)' }}>
                            {pnl >= 0 ? '+' : ''}{pnl.toFixed(0)}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3" style={{ color: 'var(--color-text-secondary)' }}>
                        {p.delta_snapshot != null ? p.delta_snapshot.toFixed(2) : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-xs px-2 py-0.5 rounded" style={{ backgroundColor: 'var(--color-surface-hover)', color: 'var(--color-text-secondary)' }}>
                          {p.strategy_type ?? 'directional'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Hedge review */}
      <div className="mb-6">
        <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>HEDGE REVIEW (advisory only)</div>
        <div className="rounded-lg p-4 mb-3" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
          {hedgeReview?.tail_hedge ? (
            <div className="text-sm">
              <span
                className="font-medium"
                style={{ color: hedgeReview.tail_hedge.action === 'hedge' ? 'var(--color-down)' : 'var(--color-text-secondary)' }}
              >
                {hedgeReview.tail_hedge.action === 'hedge' ? 'Tail hedge recommended' : 'No tail hedge needed'}
              </span>
              <p className="mt-1" style={{ color: 'var(--color-text-secondary)' }}>{hedgeReview.tail_hedge.reason}</p>
              {hedgeReview.spy_put_contract && (
                <p className="mt-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  Suggested: SPY {hedgeReview.spy_put_contract.strike.toFixed(2)}P exp {hedgeReview.spy_put_contract.expiry}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>No hedge data available.</p>
          )}
        </div>
        {hedgeReview && hedgeReview.collar_suggestions.length > 0 && (
          <div className="space-y-2">
            {hedgeReview.collar_suggestions.map((c) => (
              <div key={c.ticker} className="rounded-lg p-3 text-sm" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
                <span className="font-medium">{c.ticker}</span>
                <span className="ml-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{c.weight_pct}% of portfolio</span>
                <p className="mt-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{c.rationale}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Earnings straddle scan */}
      <div className="mb-6">
        <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>EARNINGS STRADDLE SCAN (14d)</div>
        {earningsSignals.length === 0 ? (
          <div className="rounded-lg p-6 text-sm text-center" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}>
            No upcoming earnings in the next 14 days.
          </div>
        ) : (
          <div className="space-y-2">
            {earningsSignals.map((e) => {
              const result = executionResults[e.ticker]
              return (
                <div key={e.ticker} className="rounded-lg p-3 text-sm" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-medium">{e.ticker}</span>
                      <span className="ml-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>earnings {e.earnings_date}</span>
                    </div>
                    {e.signal.action === 'straddle' && (
                      <button
                        onClick={() => handleExecuteStraddle(e.ticker, e.earnings_date)}
                        disabled={executing === e.ticker}
                        className="text-xs px-3 py-1.5 rounded font-medium"
                        style={{ backgroundColor: 'var(--color-up)', color: '#000' }}
                      >
                        {executing === e.ticker ? 'Submitting…' : 'Execute straddle'}
                      </button>
                    )}
                  </div>
                  <p className="mt-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{e.signal.reason}</p>
                  {result && (
                    <p className="mt-1 text-xs" style={{ color: result.error ? 'var(--color-down)' : 'var(--color-up)' }}>
                      {result.error
                        ? `Failed: ${result.error}`
                        : `Submitted — total premium $${result.total_premium.toFixed(2)}`}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Options flow signals */}
      <div>
        <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>OPTIONS FLOW SIGNALS (14d)</div>
        {signals.length === 0 ? (
          <div className="rounded-lg p-6 text-sm text-center" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}>
            No options flow data yet. Run the pipeline with Phase A enabled to collect flow signals.
          </div>
        ) : (
          <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--color-border)' }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-border)', backgroundColor: 'var(--color-surface-hover)' }}>
                  {['Ticker', 'Date', 'IV Rank', 'P/C Ratio', 'Unusual Vol', 'Signal'].map((h) => (
                    <th key={h} className="px-4 py-2 text-left text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {signals.map((s, i) => {
                  const cfg = SIGNAL_CONFIG[s.signal] ?? SIGNAL_CONFIG.neutral
                  return (
                    <tr key={i} style={{ borderBottom: '1px solid var(--color-border)', backgroundColor: 'var(--color-surface)' }}>
                      <td className="px-4 py-3 font-medium">{s.ticker}</td>
                      <td className="px-4 py-3" style={{ color: 'var(--color-text-secondary)' }}>{s.date}</td>
                      <td className="px-4 py-3">{s.iv_rank != null ? `${s.iv_rank.toFixed(1)}` : '—'}</td>
                      <td className="px-4 py-3">{s.put_call_ratio != null ? s.put_call_ratio.toFixed(2) : '—'}</td>
                      <td className="px-4 py-3">
                        {s.unusual_volume
                          ? <span style={{ color: '#facc15' }}>⚡ Yes</span>
                          : <span style={{ color: 'var(--color-text-secondary)' }}>No</span>}
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-medium" style={{ color: cfg.color }}>{cfg.label}</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
