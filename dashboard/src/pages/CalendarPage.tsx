import { useEffect, useMemo, useState } from 'react'
import {
  startOfMonth,
  endOfMonth,
  startOfWeek,
  endOfWeek,
  addDays,
  addMonths,
  format,
  isSameMonth,
  isSameDay,
  isToday,
} from 'date-fns'
import { api } from '../api/client'
import type { CalendarEvent, PlanOfAction } from '../types'

const EVENT_COLORS: Record<string, string> = {
  fomc: '#5b9dff',
  cpi: '#c084fc',
  jobs_report: '#facc15',
  earnings: '#00c805',
  other: '#8e8e93',
}

export default function CalendarPage() {
  const [month, setMonth] = useState(new Date())
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [selected, setSelected] = useState<CalendarEvent | null>(null)
  const [plan, setPlan] = useState<PlanOfAction | null>(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)

  const loadEvents = () => {
    api.calendarEvents(90).then((r) => setEvents(r.events))
  }

  useEffect(() => {
    loadEvents()
  }, [])

  const handleSync = async () => {
    setSyncing(true)
    await api.calendarSync()
    await loadEvents()
    setSyncing(false)
  }

  const days = useMemo(() => {
    const start = startOfWeek(startOfMonth(month))
    const end = endOfWeek(endOfMonth(month))
    const result: Date[] = []
    let d = start
    while (d <= end) {
      result.push(d)
      d = addDays(d, 1)
    }
    return result
  }, [month])

  const eventsByDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>()
    for (const e of events) {
      const key = e.event_date
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(e)
    }
    return map
  }, [events])

  const selectEvent = async (e: CalendarEvent) => {
    setSelected(e)
    setPlan(null)
    if (e.plan_eligible) {
      setPlanLoading(true)
      try {
        const p = await api.eventPlan(e.id)
        setPlan(p)
      } finally {
        setPlanLoading(false)
      }
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto flex gap-6">
      <div className="flex-1">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={() => setMonth((m) => addMonths(m, -1))} className="px-2 py-1 rounded" style={{ color: 'var(--color-text-secondary)' }}>‹</button>
            <h2 className="text-lg font-semibold w-40 text-center">{format(month, 'MMMM yyyy')}</h2>
            <button onClick={() => setMonth((m) => addMonths(m, 1))} className="px-2 py-1 rounded" style={{ color: 'var(--color-text-secondary)' }}>›</button>
          </div>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="text-xs px-3 py-1.5 rounded-full"
            style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            {syncing ? 'Syncing…' : 'Refresh events'}
          </button>
        </div>

        <div className="grid grid-cols-7 text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>
          {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
            <div key={d} className="text-center py-1">{d}</div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {days.map((d) => {
            const key = format(d, 'yyyy-MM-dd')
            const dayEvents = eventsByDay.get(key) ?? []
            const inMonth = isSameMonth(d, month)
            return (
              <div
                key={key}
                className="rounded-lg p-1.5 min-h-20"
                style={{
                  backgroundColor: 'var(--color-surface)',
                  opacity: inMonth ? 1 : 0.35,
                  border: isToday(d) ? '1px solid var(--color-accent)' : '1px solid var(--color-border)',
                }}
              >
                <div className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>{format(d, 'd')}</div>
                <div className="flex flex-col gap-0.5">
                  {dayEvents.slice(0, 3).map((e) => (
                    <button
                      key={e.id}
                      data-testid={`event-${e.id}`}
                      onClick={() => selectEvent(e)}
                      className="text-[10px] text-left px-1 py-0.5 rounded truncate"
                      style={{
                        backgroundColor: selected && isSameDay(new Date(selected.event_date), d) && selected.id === e.id
                          ? EVENT_COLORS[e.event_type]
                          : `${EVENT_COLORS[e.event_type]}26`,
                        color: selected?.id === e.id ? '#0a0a0a' : EVENT_COLORS[e.event_type],
                      }}
                      title={e.title}
                    >
                      {e.ticker ?? e.title}
                    </button>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="w-80 shrink-0">
        {!selected ? (
          <div
            className="rounded-lg p-4 text-sm h-full flex items-center justify-center text-center"
            style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            Click an event to see details and (for events 7+ days out) its plan of action.
          </div>
        ) : (
          <div className="rounded-lg p-4 sticky top-4" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
            <div className="text-xs mb-1" style={{ color: EVENT_COLORS[selected.event_type] }}>
              {selected.event_type.toUpperCase().replace('_', ' ')}
            </div>
            <h3 className="font-semibold mb-1">{selected.title}</h3>
            <div className="text-xs mb-3" style={{ color: 'var(--color-text-secondary)' }}>
              {selected.event_date} · {selected.days_out} day(s) out
            </div>
            <p className="text-sm mb-4" style={{ color: 'var(--color-text-secondary)' }}>{selected.description}</p>

            <div className="pt-3" style={{ borderTop: '1px solid var(--color-border)' }}>
              <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>PLAN OF ACTION</div>
              {!selected.plan_eligible ? (
                <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  Available once this event is 7+ days out.
                </p>
              ) : planLoading ? (
                <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>Generating…</p>
              ) : plan?.plan ? (
                <div className="text-sm space-y-2">
                  <p>{plan.plan.narrative}</p>
                  <div className="text-xs pt-2" style={{ color: 'var(--color-text-secondary)', borderTop: '1px solid var(--color-border)' }}>
                    Historical reaction (N={plan.plan.quant_stats.n}){' '}
                    {plan.plan.quant_stats.n >= 3
                      ? `· avg ${plan.plan.quant_stats.avg_move_pct}% · std ${plan.plan.quant_stats.std_move_pct}%`
                      : '· ' + (plan.plan.quant_stats.note ?? '')}
                  </div>
                </div>
              ) : (
                <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>No plan available.</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
