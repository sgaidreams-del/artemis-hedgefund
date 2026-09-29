import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ActivityEntry } from '../types'

const ALERT_STATUSES = new Set(['alert', 'halt'])

function timeAgo(ts: string): string {
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  const secs = Math.max(0, (Date.now() - d.getTime()) / 1000)
  if (secs < 60) return 'just now'
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}

function detail(entry: ActivityEntry): string | null {
  const { timestamp, component, action, status, ...rest } = entry
  const keys = Object.keys(rest)
  if (keys.length === 0) return null
  return keys.map((k) => `${k}=${JSON.stringify(rest[k])}`).join(' ')
}

export default function ActivityPanel() {
  const [entries, setEntries] = useState<ActivityEntry[]>([])
  const [emptyReason, setEmptyReason] = useState<string | null>(null)
  const [open, setOpen] = useState(false)

  const load = () =>
    api.activity(50).then((r) => {
      setEntries(r.entries)
      setEmptyReason(r.empty_reason)
    }).catch(() => null)

  useEffect(() => {
    load()
    const t = setInterval(load, 30 * 1000)
    return () => clearInterval(t)
  }, [])

  const hasAlert = entries.some((e) => ALERT_STATUSES.has(e.status))

  return (
    <div className="mb-6">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 w-full text-left mb-2"
      >
        <span className="text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
          ACTIVITY / ALERTS
        </span>
        {hasAlert && (
          <span className="text-xs px-1.5 py-0.5 rounded font-medium"
            style={{ backgroundColor: 'rgba(255,80,0,0.15)', color: '#ff5000' }}>
            alert
          </span>
        )}
        <span className="text-xs ml-auto" style={{ color: 'var(--color-text-secondary)' }}>
          {open ? '▲' : '▼'}
        </span>
      </button>

      {open && (
        <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--color-border)' }}>
          {entries.length === 0 ? (
            <div className="p-4 text-xs text-center" style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text-secondary)' }}>
              {emptyReason ?? 'No activity logged yet.'}
            </div>
          ) : (
            entries.slice(0, 30).map((e, i) => {
              const isAlert = ALERT_STATUSES.has(e.status)
              return (
                <div
                  key={i}
                  className="flex items-center justify-between gap-3 px-4 py-2 text-xs"
                  style={{
                    backgroundColor: isAlert ? 'rgba(255,80,0,0.08)' : 'var(--color-surface)',
                    borderBottom: i < Math.min(entries.length, 30) - 1 ? '1px solid var(--color-border)' : 'none',
                  }}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className="px-1.5 py-0.5 rounded shrink-0 font-medium"
                      style={{
                        backgroundColor: isAlert ? 'rgba(255,80,0,0.15)' : 'var(--color-surface-hover)',
                        color: isAlert ? '#ff5000' : 'var(--color-text-secondary)',
                      }}
                    >
                      {e.status}
                    </span>
                    <span style={{ color: 'var(--color-text-primary)' }}>{e.component}.{e.action}</span>
                    <span className="truncate" style={{ color: 'var(--color-text-secondary)' }}>{detail(e)}</span>
                  </div>
                  <span className="shrink-0" style={{ color: 'var(--color-text-secondary)' }}>{timeAgo(e.timestamp)}</span>
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
