import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ConnectionStatus } from '../types'

function Dot({ connected }: { connected: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${connected ? 'bg-up' : 'bg-down'}`}
      style={{ backgroundColor: connected ? 'var(--color-up)' : 'var(--color-down)' }}
    />
  )
}

function Item({ label, check }: { label: string; check: { connected: boolean; reason: string | null; latency_ms: number | null } }) {
  return (
    <div
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs"
      title={check.reason ?? (check.latency_ms != null ? `${check.latency_ms}ms` : 'connected')}
    >
      <Dot connected={check.connected} />
      <span style={{ color: 'var(--color-text-secondary)' }}>{label}</span>
    </div>
  )
}

export default function ConnectionBar() {
  const [status, setStatus] = useState<ConnectionStatus | null>(null)

  useEffect(() => {
    const load = () => api.connectionStatus().then(setStatus).catch(() => setStatus(null))
    load()
    const interval = setInterval(load, 15000)
    return () => clearInterval(interval)
  }, [])

  if (!status) {
    return <div className="px-4 py-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>Checking connections…</div>
  }

  return (
    <div className="flex items-center gap-1 px-3 py-1.5 border-b" style={{ borderColor: 'var(--color-border)' }}>
      <Item label="Alpaca" check={status.alpaca} />
      <Item label="Postgres" check={status.postgres} />
      <Item label="Redis" check={status.redis} />
      <Item label="DeepSeek" check={status.deepseek} />
    </div>
  )
}
