import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { CorrelationData } from '../types'

function corrColor(v: number): string {
  // -1 = red, 0 = neutral, +1 = green
  if (v > 0.7) return 'rgba(255,80,0,0.7)'
  if (v > 0.4) return 'rgba(255,80,0,0.35)'
  if (v > 0.1) return 'rgba(255,80,0,0.12)'
  if (v < -0.7) return 'rgba(0,200,5,0.7)'
  if (v < -0.4) return 'rgba(0,200,5,0.35)'
  if (v < -0.1) return 'rgba(0,200,5,0.12)'
  return 'var(--color-surface-hover)'
}

export default function CorrelationMatrix() {
  const [data, setData] = useState<CorrelationData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.correlation().then(setData).catch(() => null).finally(() => setLoading(false))
  }, [])

  if (loading || !data) return null

  if (data.tickers.length < 2) {
    return (
      <div className="rounded-lg p-4 mb-6 text-xs text-center"
        style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}>
        {data.empty_reason ?? 'Need at least 2 positions for correlation matrix.'}
      </div>
    )
  }

  const n = data.tickers.length
  const CELL = Math.max(36, Math.min(60, 320 / n))

  return (
    <div className="mb-6">
      <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>
        POSITION CORRELATION (60d)
      </div>
      <div className="rounded-lg p-4 overflow-x-auto" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        <table className="border-separate" style={{ borderSpacing: 2 }}>
          <thead>
            <tr>
              <th style={{ width: CELL }} />
              {data.tickers.map((t) => (
                <th key={t} style={{ width: CELL, fontSize: 10, color: 'var(--color-text-secondary)', fontWeight: 500, textAlign: 'center' }}>{t}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.matrix.map((row, ri) => (
              <tr key={data.tickers[ri]}>
                <td style={{ fontSize: 10, color: 'var(--color-text-secondary)', fontWeight: 500, paddingRight: 4, textAlign: 'right' }}>
                  {data.tickers[ri]}
                </td>
                {row.map((v, ci) => (
                  <td
                    key={ci}
                    title={`${data.tickers[ri]} × ${data.tickers[ci]}: ${v.toFixed(2)}`}
                    style={{
                      width: CELL,
                      height: CELL,
                      backgroundColor: corrColor(v),
                      borderRadius: 4,
                      textAlign: 'center',
                      fontSize: 10,
                      color: ri === ci ? 'var(--color-text-secondary)' : Math.abs(v) > 0.4 ? '#f5f5f5' : 'var(--color-text-secondary)',
                    }}
                  >
                    {ri === ci ? '—' : v.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex items-center gap-2 mt-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          <span className="w-3 h-3 rounded-sm inline-block" style={{ backgroundColor: 'rgba(0,200,5,0.7)' }} /> Negative corr (diversifies)
          <span className="w-3 h-3 rounded-sm inline-block ml-3" style={{ backgroundColor: 'rgba(255,80,0,0.7)' }} /> High corr (concentrated risk)
        </div>
      </div>
    </div>
  )
}
