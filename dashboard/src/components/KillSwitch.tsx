import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { KillSwitchState } from '../types'

export default function KillSwitch() {
  const [state, setState] = useState<KillSwitchState | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.killSwitchStatus().then(setState).catch(() => null)
  }, [])

  const toggle = async () => {
    if (loading) return
    if (!state?.paused) {
      const confirmed = window.confirm('Pause all new trading orders from Artemis?')
      if (!confirmed) return
    }
    setLoading(true)
    try {
      const next = state?.paused
        ? await api.killSwitchResume()
        : await api.killSwitchPause('Manual pause via dashboard')
      setState(next)
    } finally {
      setLoading(false)
    }
  }

  const paused = state?.paused ?? false

  return (
    <button
      onClick={toggle}
      disabled={loading || state === null}
      title={paused ? `Paused since ${state?.set_at ?? ''}` : 'Trading active — click to pause'}
      className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all"
      style={{
        backgroundColor: paused ? 'rgba(255,80,0,0.15)' : 'rgba(0,200,5,0.12)',
        border: `1px solid ${paused ? '#ff5000' : '#00c805'}`,
        color: paused ? '#ff5000' : '#00c805',
        opacity: loading || state === null ? 0.5 : 1,
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: paused ? '#ff5000' : '#00c805' }}
      />
      {loading ? '…' : paused ? 'PAUSED' : 'LIVE'}
    </button>
  )
}
