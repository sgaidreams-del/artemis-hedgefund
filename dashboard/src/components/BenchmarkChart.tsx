import { useEffect, useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { api } from '../api/client'
import type { BenchmarkPoint } from '../types'

interface Props {
  period?: string
}

export default function BenchmarkChart({ period = '1M' }: Props) {
  const [points, setPoints] = useState<BenchmarkPoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.benchmark(period).then((r) => setPoints(r.points)).catch(() => null).finally(() => setLoading(false))
  }, [period])

  if (loading) return <div className="h-48 rounded-lg mb-6" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }} />

  if (points.length < 2) {
    return (
      <div className="h-24 rounded-lg mb-6 flex items-center justify-center text-xs"
        style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}>
        Benchmark comparison available once portfolio history exists.
      </div>
    )
  }

  const hasPortfolio = points.some((p) => p.portfolio != null)

  return (
    <div className="mb-6">
      <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>
        PORTFOLIO VS SPY (indexed to 100)
      </div>
      <div className="h-48 rounded-lg p-3" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points}>
            <defs>
              <linearGradient id="bm-portfolio" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#00c805" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#00c805" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="bm-spy" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#5b9dff" stopOpacity={0.15} />
                <stop offset="100%" stopColor="#5b9dff" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" hide />
            <YAxis hide domain={['auto', 'auto']} />
            <Tooltip
              contentStyle={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 8 }}
              labelStyle={{ color: 'var(--color-text-secondary)', fontSize: 11 }}
              formatter={(v, name) => [v != null ? Number(v).toFixed(2) : '—', String(name ?? '')]}
            />
            <Legend
              wrapperStyle={{ fontSize: 11, color: 'var(--color-text-secondary)', paddingTop: 4 }}
            />
            {hasPortfolio && (
              <Area type="monotone" dataKey="portfolio" name="Artemis" stroke="#00c805" fill="url(#bm-portfolio)" strokeWidth={2} dot={false} connectNulls />
            )}
            <Area type="monotone" dataKey="spy" name="SPY" stroke="#5b9dff" fill="url(#bm-spy)" strokeWidth={1.5} dot={false} connectNulls />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
