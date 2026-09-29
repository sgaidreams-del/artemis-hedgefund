import { useEffect, useState } from 'react'
import { format, parseISO, getYear, getMonth } from 'date-fns'
import { api } from '../api/client'
import type { ReturnsHeatmapPoint } from '../types'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function returnColor(r: number): string {
  if (r > 0.02) return '#00c805'
  if (r > 0.01) return '#00a004'
  if (r > 0.003) return '#006b02'
  if (r > 0) return '#003d01'
  if (r < -0.02) return '#ff5000'
  if (r < -0.01) return '#cc4000'
  if (r < -0.003) return '#882a00'
  if (r < 0) return '#441500'
  return 'var(--color-surface)'
}

export default function ReturnsHeatmap() {
  const [data, setData] = useState<ReturnsHeatmapPoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.returnsHeatmap(2).then((r) => setData(r.returns)).catch(() => null).finally(() => setLoading(false))
  }, [])

  if (loading) return null

  if (data.length === 0) {
    return (
      <div className="rounded-lg p-4 mb-6 text-xs text-center"
        style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}>
        Daily returns heatmap will appear once portfolio history is recorded.
      </div>
    )
  }

  // group by year
  const byYear: Record<number, Record<string, number>> = {}
  for (const pt of data) {
    const d = parseISO(pt.date)
    const yr = getYear(d)
    if (!byYear[yr]) byYear[yr] = {}
    byYear[yr][pt.date] = pt.return_pct
  }

  const years = Object.keys(byYear).map(Number).sort((a, b) => b - a)

  return (
    <div className="mb-6">
      <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>
        DAILY RETURNS
      </div>
      <div className="rounded-lg p-4 overflow-x-auto" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        {years.map((yr) => (
          <YearGrid key={yr} year={yr} returns={byYear[yr]} />
        ))}
        <div className="flex items-center gap-2 mt-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          <span>Less</span>
          {[-0.03, -0.015, -0.003, 0, 0.003, 0.015, 0.03].map((r) => (
            <span key={r} className="w-3 h-3 rounded-sm inline-block" style={{ backgroundColor: r === 0 ? 'var(--color-border)' : returnColor(r) }} />
          ))}
          <span>More</span>
        </div>
      </div>
    </div>
  )
}

function YearGrid({ year, returns }: { year: number; returns: Record<string, number> }) {
  // build 53×7 grid: columns = weeks, rows = days of week
  const startDate = new Date(year, 0, 1)
  const startDow = startDate.getDay() // 0=Sun

  const cells: Array<{ date: string | null; val: number | null }> = []
  // pad start
  for (let i = 0; i < startDow; i++) cells.push({ date: null, val: null })

  for (let d = 0; d < 365 + (year % 4 === 0 ? 1 : 0); d++) {
    const dt = new Date(year, 0, 1 + d)
    if (getYear(dt) !== year) break
    const key = format(dt, 'yyyy-MM-dd')
    cells.push({ date: key, val: returns[key] ?? null })
  }

  // pad end to fill last week
  while (cells.length % 7 !== 0) cells.push({ date: null, val: null })

  const weeks: Array<typeof cells> = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))

  return (
    <div className="mb-4">
      <div className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>{year}</div>
      <div className="flex gap-px">
        <div className="flex flex-col gap-px mr-1">
          {DAYS.map((d) => (
            <div key={d} className="h-3 w-5 text-[8px] flex items-center" style={{ color: 'var(--color-text-secondary)' }}>{d[0]}</div>
          ))}
        </div>
        {weeks.map((week, wi) => (
          <div key={wi} className="flex flex-col gap-px">
            {week.map((cell, di) => (
              <div
                key={di}
                className="w-3 h-3 rounded-sm"
                title={cell.date ? `${cell.date}: ${cell.val != null ? (cell.val * 100).toFixed(2) + '%' : 'no data'}` : ''}
                style={{ backgroundColor: cell.val != null ? returnColor(cell.val) : cell.date ? 'var(--color-border)' : 'transparent' }}
              />
            ))}
          </div>
        ))}
      </div>
      <div className="flex gap-px ml-6 mt-0.5">
        {weeks.map((week, wi) => {
          const firstDate = week.find((c) => c.date)?.date
          const mon = firstDate ? getMonth(parseISO(firstDate)) : null
          const showLabel = wi === 0 || (firstDate && parseISO(firstDate).getDate() <= 7)
          return (
            <div key={wi} className="w-3 text-[8px] text-center overflow-hidden" style={{ color: 'var(--color-text-secondary)' }}>
              {showLabel && mon != null ? MONTHS[mon][0] : ''}
            </div>
          )
        })}
      </div>
    </div>
  )
}
