import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Learning } from '../types'
import { formatPct } from '../components/StatPill'

const LABEL_STYLE: Record<string, { bg: string; border: string; color: string }> = {
  Missed:         { bg: 'rgba(251,191,36,0.15)', border: 'rgba(251,191,36,0.5)', color: '#fbbf24' },
  'Universe Miss':{ bg: 'rgba(239,68,68,0.12)',  border: 'rgba(239,68,68,0.4)',  color: '#f87171' },
  Test:           { bg: 'rgba(99,102,241,0.15)',  border: 'rgba(99,102,241,0.4)',  color: '#818cf8' },
}

const ACTION_LABEL: Record<string, string> = {
  missed_buy:    'MISSED BUY',
  missed_exit:   'MISSED EXIT',
  universe_miss: 'UNIVERSE MISS',
  buy:           'BUY',
  sell:          'SELL',
}

function LabelBadge({ label }: { label: string }) {
  const s = LABEL_STYLE[label] ?? { bg: 'rgba(148,163,184,0.15)', border: 'rgba(148,163,184,0.4)', color: '#94a3b8' }
  return (
    <span className="text-xs px-1.5 py-0.5 rounded font-medium"
      style={{ backgroundColor: s.bg, border: `1px solid ${s.border}`, color: s.color }}>
      {label}
    </span>
  )
}

export default function Learnings() {
  const [learnings, setLearnings] = useState<Learning[]>([])
  const [emptyReason, setEmptyReason] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.learnings()
      .then((r) => {
        setLearnings(r.learnings)
        setEmptyReason(r.empty_reason)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-6 text-sm" style={{ color: 'var(--color-text-secondary)' }}>Loading learnings…</div>

  const isMissed = (l: Learning) => l.label === 'Missed' || l.label === 'Universe Miss'

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h2 className="text-xl font-semibold mb-1">Learnings</h2>
      <p className="text-sm mb-4" style={{ color: 'var(--color-text-secondary)' }}>
        Executed trades and missed opportunities — feeds directly into AutoResearch's next hypothesis cycle.
      </p>
      {learnings.length === 0 ? (
        <div className="text-sm py-12 text-center rounded-lg" style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text-secondary)' }}>
          {emptyReason}
        </div>
      ) : (
        <div className="space-y-2">
          {learnings.map((l) => (
            <div key={l.id} className="rounded-lg p-4"
              style={{
                backgroundColor: 'var(--color-surface)',
                border: isMissed(l)
                  ? '1px solid rgba(251,191,36,0.25)'
                  : '1px solid var(--color-border)',
              }}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{l.ticker}</span>
                  <span className="text-xs uppercase" style={{ color: 'var(--color-text-secondary)' }}>
                    {ACTION_LABEL[l.action] ?? l.action.toUpperCase()}
                  </span>
                  <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{l.trade_date}</span>
                  {l.label && <LabelBadge label={l.label} />}
                </div>
                {l.status === 'resolved' ? (
                  <span className="text-sm font-medium"
                    style={{ color: (l.actual_return_5d ?? 0) >= 0 ? 'var(--color-up)' : 'var(--color-down)' }}>
                    {isMissed(l) ? 'moved ' : ''}{formatPct(l.actual_return_5d)}
                    {l.alpha_vs_spy_5d != null && ` (alpha ${formatPct(l.alpha_vs_spy_5d)})`}
                  </span>
                ) : (
                  <span className="text-xs px-2 py-0.5 rounded"
                    style={{ backgroundColor: 'var(--color-surface-hover)', color: 'var(--color-text-secondary)' }}>
                    pending
                  </span>
                )}
              </div>
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                {l.reflection ?? 'Reflection will be generated 5 trading days after entry.'}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
