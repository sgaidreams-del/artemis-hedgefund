import { useEffect, useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { api } from '../api/client'
import type { DrawdownPoint } from '../types'

export default function DrawdownChart() {
  const [points, setPoints] = useState<DrawdownPoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.drawdown().then((r) => setPoints(r.points)).catch(() => null).finally(() => setLoading(false))
  }, [])

  if (loading) return null

  if (points.length < 2) return null

  const minDD = Math.min(...points.map((p) => p.drawdown))

  return (
    <div className="mb-6">
      <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>
        DRAWDOWN
        <span className="ml-2 font-normal">
          max {(minDD * 100).toFixed(1)}%
        </span>
      </div>
      <div className="h-28 rounded-lg p-3" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points}>
            <defs>
              <linearGradient id="dd-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#ff5000" stopOpacity={0.05} />
                <stop offset="100%" stopColor="#ff5000" stopOpacity={0.3} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" hide />
            <YAxis hide domain={[minDD * 1.1, 0]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
            <ReferenceLine y={0} stroke="var(--color-border)" strokeDasharray="3 3" />
            <Tooltip
              contentStyle={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 8 }}
              labelStyle={{ color: 'var(--color-text-secondary)', fontSize: 11 }}
              formatter={(v) => [`${(Number(v) * 100).toFixed(2)}%`, 'Drawdown']}
            />
            <Area
              type="monotone"
              dataKey="drawdown"
              stroke="#ff5000"
              fill="url(#dd-grad)"
              strokeWidth={1.5}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
