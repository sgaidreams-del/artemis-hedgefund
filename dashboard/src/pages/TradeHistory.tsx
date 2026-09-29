import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Trade } from '../types'
import { formatUsd } from '../components/StatPill'

export default function TradeHistory() {
  const [trades, setTrades] = useState<Trade[]>([])
  const [emptyReason, setEmptyReason] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.trades()
      .then((r) => {
        setTrades(r.trades)
        setEmptyReason(r.empty_reason)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-6 text-sm" style={{ color: 'var(--color-text-secondary)' }}>Loading trade history…</div>

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h2 className="text-xl font-semibold mb-4">Trade History</h2>
      {trades.length === 0 ? (
        <div className="text-sm py-12 text-center rounded-lg" style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text-secondary)' }}>
          {emptyReason}
        </div>
      ) : (
        <div className="space-y-2">
          {trades.map((t) => (
            <div
              key={t.trade_id}
              className="rounded-lg p-4 cursor-pointer"
              style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
              onClick={() => setExpanded(expanded === t.trade_id ? null : t.trade_id)}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span
                    className="text-xs font-semibold px-2 py-0.5 rounded"
                    style={{
                      backgroundColor: t.side === 'buy' ? 'rgba(0,200,5,0.15)' : 'rgba(255,80,0,0.15)',
                      color: t.side === 'buy' ? 'var(--color-up)' : 'var(--color-down)',
                    }}
                  >
                    {t.side.toUpperCase()}
                  </span>
                  <span className="font-medium">{t.ticker}</span>
                  <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>{t.quantity} sh</span>
                </div>
                <div className="text-right">
                  <div>{formatUsd(t.fill_price ?? t.limit_price)}</div>
                  <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                    {new Date(t.timestamp).toLocaleString()}
                  </div>
                </div>
              </div>
              {expanded === t.trade_id && (
                <div className="mt-3 pt-3 text-sm" style={{ borderTop: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}>
                  <div className="mb-2">
                    <span className="font-medium" style={{ color: 'var(--color-text-primary)' }}>Rationale: </span>
                    {t.rationale ?? 'No rationale recorded.'}
                  </div>
                  {t.slippage_bps != null && <div>Slippage: {t.slippage_bps} bps</div>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
