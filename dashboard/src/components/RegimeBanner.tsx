import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { RegimeData } from '../types'

const REGIME_CONFIG = {
  bull: { label: 'Bull Market', bg: 'rgba(0,200,5,0.08)', border: '#00c805', color: '#00c805', emoji: '↑' },
  bear: { label: 'Bear Market', bg: 'rgba(255,80,0,0.08)', border: '#ff5000', color: '#ff5000', emoji: '↓' },
  sideways: { label: 'Sideways / Choppy', bg: 'rgba(250,204,21,0.08)', border: '#facc15', color: '#facc15', emoji: '→' },
  unknown: { label: 'Regime Unknown', bg: 'rgba(142,142,147,0.08)', border: '#8e8e93', color: '#8e8e93', emoji: '?' },
}

export default function RegimeBanner() {
  const [data, setData] = useState<RegimeData | null>(null)

  useEffect(() => {
    api.regime().then(setData).catch(() => null)
    const t = setInterval(() => api.regime().then(setData).catch(() => null), 5 * 60 * 1000)
    return () => clearInterval(t)
  }, [])

  if (!data) return null

  const cfg = REGIME_CONFIG[data.regime] ?? REGIME_CONFIG.unknown

  return (
    <div
      className="flex items-center justify-between rounded-lg px-4 py-2.5 mb-6 text-sm"
      style={{ backgroundColor: cfg.bg, border: `1px solid ${cfg.border}` }}
    >
      <div className="flex items-center gap-2">
        <span style={{ color: cfg.color }} className="font-semibold">
          {cfg.emoji} {cfg.label}
        </span>
        {data.source === 'ma_rules' && (
          <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            (50d MA rules — upgrades to HMM in Phase 2)
          </span>
        )}
        {data.source === 'hmm' && data.confidence != null && (
          <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            {(data.confidence * 100).toFixed(0)}% confidence
          </span>
        )}
      </div>
      <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
        {data.spy_price != null && (
          <span>SPY ${data.spy_price.toFixed(2)}</span>
        )}
        {data.realized_vol_20d != null && (
          <span>20d vol {(data.realized_vol_20d * 100).toFixed(1)}%</span>
        )}
        {data.ma50 != null && data.ma200 != null && (
          <span>50MA {data.ma50.toFixed(0)} / 200MA {data.ma200.toFixed(0)}</span>
        )}
      </div>
    </div>
  )
}
