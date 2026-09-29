export function formatPct(v: number | null | undefined, digits = 2): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
}

export function formatUsd(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

export default function StatPill({ value, suffix = '' }: { value: number | null | undefined; suffix?: string }) {
  const positive = (value ?? 0) >= 0
  return (
    <span style={{ color: positive ? 'var(--color-up)' : 'var(--color-down)' }} className="font-medium">
      {formatPct(value)}
      {suffix}
    </span>
  )
}
