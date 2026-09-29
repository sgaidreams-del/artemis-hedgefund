import { useState } from 'react'
import { api } from '../api/client'
import type { RebalanceResult } from '../types'

const STATUS_LABEL: Record<string, string> = {
  paused: 'Kill switch is paused — no orders generated.',
  no_account: 'Broker not connected.',
  drawdown_halt: 'Drawdown halt active — rebalance skipped.',
  no_scores: 'No ensemble scores for today yet — run the pipeline first.',
  error: 'Rebalance failed.',
}

export default function RebalanceButton() {
  const [result, setResult] = useState<RebalanceResult | null>(null)
  const [loading, setLoading] = useState<'preview' | 'execute' | null>(null)

  const preview = async () => {
    setLoading('preview')
    try {
      setResult(await api.previewRebalance())
    } catch {
      setResult({ status: 'error', orders: [], error: 'Request failed' })
    } finally {
      setLoading(null)
    }
  }

  const execute = async () => {
    if (!result || result.orders.length === 0) return
    const lines = result.orders.map((o) => `${o.side.toUpperCase()} ${o.qty} ${o.ticker}`).join('\n')
    const confirmed = window.confirm(
      `This submits REAL orders to your paper account:\n\n${lines}\n\nProceed?`
    )
    if (!confirmed) return
    setLoading('execute')
    try {
      setResult(await api.executeRebalance())
    } catch {
      setResult({ status: 'error', orders: [], error: 'Request failed' })
    } finally {
      setLoading(null)
    }
  }

  const previewedNotYetExecuted =
    result?.status === 'ok' && result.dry_run === true && result.orders.length > 0

  return (
    <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
          MANUAL REBALANCE
        </h3>
        <div className="flex gap-2">
          <button
            onClick={preview}
            disabled={loading !== null}
            className="text-xs px-3 py-1.5 rounded-full font-medium transition-opacity"
            style={{
              backgroundColor: 'var(--color-surface-hover)',
              color: 'var(--color-text-primary)',
              opacity: loading !== null ? 0.5 : 1,
            }}
          >
            {loading === 'preview' ? 'Computing…' : 'Preview'}
          </button>
          <button
            onClick={execute}
            disabled={loading !== null || !previewedNotYetExecuted}
            title={!previewedNotYetExecuted ? 'Preview first to see what would be submitted' : undefined}
            className="text-xs px-3 py-1.5 rounded-full font-medium transition-opacity"
            style={{
              backgroundColor: previewedNotYetExecuted ? 'rgba(255,80,0,0.15)' : 'var(--color-surface-hover)',
              border: previewedNotYetExecuted ? '1px solid #ff5000' : '1px solid var(--color-border)',
              color: previewedNotYetExecuted ? '#ff5000' : 'var(--color-text-secondary)',
              opacity: loading !== null ? 0.5 : 1,
            }}
          >
            {loading === 'execute' ? 'Submitting…' : 'Submit Orders'}
          </button>
        </div>
      </div>

      {result === null && (
        <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          Preview computes today's risk-sized orders without submitting anything. Submit sends them to your paper account.
        </p>
      )}

      {result !== null && result.status !== 'ok' && (
        <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {result.error ? `Error: ${result.error}` : STATUS_LABEL[result.status] ?? result.status}
        </p>
      )}

      {result !== null && result.status === 'ok' && result.orders.length === 0 && (
        <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          No drift above threshold — nothing to rebalance today.
        </p>
      )}

      {result !== null && result.orders.length > 0 && (
        <div className="space-y-1.5">
          {result.orders.map((o) => (
            <div key={`${o.ticker}-${o.decision_id}`} className="flex items-center justify-between text-sm px-2 py-1.5 rounded" style={{ backgroundColor: 'var(--color-surface-hover)' }}>
              <span className="font-medium">
                <span style={{ color: o.side === 'buy' ? 'var(--color-up)' : 'var(--color-down)' }}>{o.side.toUpperCase()}</span>{' '}
                {o.qty} {o.ticker}
              </span>
              <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                {o.submitted
                  ? o.filled === false
                    ? 'unfilled'
                    : `filled @ ${o.fill_price?.toFixed(2)}`
                  : 'preview only'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
