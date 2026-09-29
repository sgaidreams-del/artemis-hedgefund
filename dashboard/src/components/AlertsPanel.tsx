import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PriceAlert } from '../types'

export default function AlertsPanel() {
  const [alerts, setAlerts] = useState<PriceAlert[]>([])
  const [ticker, setTicker] = useState('')
  const [threshold, setThreshold] = useState('')
  const [direction, setDirection] = useState<'above' | 'below'>('above')
  const [saving, setSaving] = useState(false)

  const load = () => api.alerts().then((r) => setAlerts(r.alerts)).catch(() => null)

  useEffect(() => {
    load()
  }, [])

  const add = async () => {
    if (!ticker.trim() || !threshold) return
    const val = parseFloat(threshold)
    if (isNaN(val) || val <= 0) return
    setSaving(true)
    try {
      await api.createAlert(ticker.toUpperCase().trim(), val, direction)
      setTicker('')
      setThreshold('')
      await load()
    } finally {
      setSaving(false)
    }
  }

  const remove = async (id: number) => {
    await api.deleteAlert(id)
    await load()
  }

  const active = alerts.filter((a) => !a.triggered_at)
  const triggered = alerts.filter((a) => !!a.triggered_at)

  return (
    <div className="mb-6">
      <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>PRICE ALERTS</div>
      <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        {/* Add form */}
        <div className="flex gap-2 mb-4">
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="Ticker"
            maxLength={6}
            className="flex-1 min-w-0 rounded px-3 py-1.5 text-sm"
            style={{ backgroundColor: 'var(--color-surface-hover)', border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', outline: 'none' }}
          />
          <select
            value={direction}
            onChange={(e) => setDirection(e.target.value as 'above' | 'below')}
            className="rounded px-2 py-1.5 text-sm"
            style={{ backgroundColor: 'var(--color-surface-hover)', border: '1px solid var(--color-border)', color: 'var(--color-text-primary)' }}
          >
            <option value="above">above</option>
            <option value="below">below</option>
          </select>
          <input
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            placeholder="Price"
            type="number"
            min="0"
            step="0.01"
            className="w-24 rounded px-3 py-1.5 text-sm"
            style={{ backgroundColor: 'var(--color-surface-hover)', border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', outline: 'none' }}
          />
          <button
            onClick={add}
            disabled={saving || !ticker || !threshold}
            className="rounded px-3 py-1.5 text-sm font-medium"
            style={{ backgroundColor: 'var(--color-accent)', color: '#0a0a0a', opacity: saving || !ticker || !threshold ? 0.5 : 1 }}
          >
            {saving ? '…' : 'Add'}
          </button>
        </div>

        {/* Active alerts */}
        {active.length > 0 && (
          <div className="space-y-1 mb-3">
            {active.map((a) => (
              <div key={a.id} className="flex items-center justify-between text-sm py-1.5 px-2 rounded" style={{ backgroundColor: 'var(--color-surface-hover)' }}>
                <span className="font-medium" style={{ color: 'var(--color-accent)' }}>{a.ticker}</span>
                <span style={{ color: 'var(--color-text-secondary)' }}>{a.direction} ${a.threshold.toFixed(2)}</span>
                <button onClick={() => remove(a.id)} className="text-xs px-2 py-0.5 rounded" style={{ color: 'var(--color-text-secondary)' }}>✕</button>
              </div>
            ))}
          </div>
        )}

        {/* Triggered */}
        {triggered.length > 0 && (
          <div>
            <div className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>TRIGGERED</div>
            {triggered.slice(0, 5).map((a) => (
              <div key={a.id} className="flex items-center justify-between text-xs py-1 px-2 rounded mb-1"
                style={{ backgroundColor: 'rgba(255,80,0,0.08)', border: '1px solid rgba(255,80,0,0.2)' }}>
                <span style={{ color: '#ff5000' }}>{a.ticker} {a.direction} ${a.threshold.toFixed(2)}</span>
                <span style={{ color: 'var(--color-text-secondary)' }}>{a.triggered_at?.slice(0, 10)}</span>
                <button onClick={() => remove(a.id)} className="text-xs px-1" style={{ color: 'var(--color-text-secondary)' }}>✕</button>
              </div>
            ))}
          </div>
        )}

        {active.length === 0 && triggered.length === 0 && (
          <div className="text-xs text-center" style={{ color: 'var(--color-text-secondary)' }}>
            No alerts set. Add ticker + price threshold above.
          </div>
        )}
      </div>
    </div>
  )
}
