import { useEffect, useState } from 'react'
import { formatDistanceToNow, parseISO } from 'date-fns'
import { api } from '../api/client'
import type { NewsArticle } from '../types'

const SENTIMENT_COLOR: Record<string, string> = {
  positive: 'var(--color-up)',
  negative: 'var(--color-down)',
  neutral: 'var(--color-text-secondary)',
}

function timeAgo(ts: string): string {
  try {
    const d = ts.includes('T') ? parseISO(ts) : new Date(Number(ts) * 1000)
    return formatDistanceToNow(d, { addSuffix: true })
  } catch {
    return ts
  }
}

export default function NewsFeed() {
  const [articles, setArticles] = useState<NewsArticle[]>([])
  const [source, setSource] = useState<string>('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.news(15).then((r) => {
      setArticles(r.articles)
      setSource(r.source)
    }).catch(() => null).finally(() => setLoading(false))
  }, [])

  if (loading) return null

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
          NEWS — HELD POSITIONS
        </div>
        {source === 'yfinance_fallback' && (
          <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>via yfinance</div>
        )}
      </div>
      {articles.length === 0 ? (
        <div className="rounded-lg p-4 text-xs text-center" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}>
          No recent news found for current positions.
        </div>
      ) : (
        <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--color-border)' }}>
          {articles.slice(0, 8).map((a, i) => (
            <div
              key={a.id ?? i}
              className="px-4 py-3 flex flex-col gap-1"
              style={{
                backgroundColor: 'var(--color-surface)',
                borderBottom: i < articles.length - 1 ? '1px solid var(--color-border)' : 'none',
              }}
            >
              <div className="flex items-start justify-between gap-3">
                <a
                  href={a.url ?? '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium leading-snug hover:underline"
                  style={{ color: 'var(--color-text-primary)' }}
                >
                  {a.headline}
                </a>
                {a.sentiment_label && (
                  <span
                    className="text-xs shrink-0 px-1.5 py-0.5 rounded"
                    style={{
                      color: SENTIMENT_COLOR[a.sentiment_label] ?? 'var(--color-text-secondary)',
                      backgroundColor: 'var(--color-surface-hover)',
                    }}
                  >
                    {a.sentiment_label}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                {a.source && <span>{a.source}</span>}
                <span>{timeAgo(a.timestamp)}</span>
                {a.tickers.length > 0 && (
                  <div className="flex gap-1">
                    {a.tickers.slice(0, 4).map((t) => (
                      <span key={t} className="px-1.5 py-0 rounded" style={{ backgroundColor: 'var(--color-surface-hover)', color: 'var(--color-accent)' }}>
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
