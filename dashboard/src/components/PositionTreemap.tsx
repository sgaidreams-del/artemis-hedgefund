import type { Position } from '../types'

interface Props {
  positions: Position[]
  totalEquity: number
}

interface Cell {
  ticker: string
  weight: number
  pl_pct: number
  x: number
  y: number
  w: number
  h: number
}

// Squarified treemap — builds rectangles for the given sorted area array.
function squarify(items: { ticker: string; weight: number; pl_pct: number }[], x: number, y: number, w: number, h: number): Cell[] {
  if (items.length === 0) return []

  const total = items.reduce((s, i) => s + i.weight, 0)
  if (total === 0) return []

  const cells: Cell[] = []
  let remaining = [...items]
  let rx = x, ry = y, rw = w, rh = h

  while (remaining.length > 0) {
    const horizontal = rw >= rh
    const size = horizontal ? rw : rh

    let row: typeof remaining = []
    let rowTotal = 0
    let bestWorst = Infinity

    for (let i = 0; i < remaining.length; i++) {
      const candidate = remaining[i]
      const newRowTotal = rowTotal + candidate.weight
      const newWorst = worstAspect(row.concat(candidate), newRowTotal, (rowTotal === 0 ? remaining[i].weight / total : newRowTotal / total), size, rw, rh)
      if (i > 0 && newWorst > bestWorst) break
      row.push(candidate)
      rowTotal = newRowTotal
      bestWorst = newWorst
    }

    const rowFraction = rowTotal / total
    const rowSize = horizontal ? rh * rowFraction : rw * rowFraction

    let cursor = horizontal ? rx : ry
    for (const item of row) {
      cells.push({
        ...item,
        x: horizontal ? rx : cursor,
        y: horizontal ? cursor : ry,
        w: horizontal ? rw * rowFraction : rowSize,
        h: horizontal ? rowSize : rh * rowFraction,
      })

      // Simpler rectangle placement
      if (horizontal) {
        cells[cells.length - 1].x = rx
        cells[cells.length - 1].y = cursor
        cells[cells.length - 1].w = rw * rowFraction
        cells[cells.length - 1].h = rh * (item.weight / rowTotal)
        cursor += rh * (item.weight / rowTotal)
      } else {
        cells[cells.length - 1].x = cursor
        cells[cells.length - 1].y = ry
        cells[cells.length - 1].w = rw * (item.weight / rowTotal)
        cells[cells.length - 1].h = rh * rowFraction
        cursor += rw * (item.weight / rowTotal)
      }
    }

    if (horizontal) {
      rx += rw * rowFraction
      rw -= rw * rowFraction
    } else {
      ry += rh * rowFraction
      rh -= rh * rowFraction
    }

    remaining = remaining.slice(row.length)
    total // re-use outer total — remaining items scale the new space
  }

  return cells
}

function worstAspect(row: { weight: number }[], rowTotal: number, rowFraction: number, size: number, _w: number, _h: number): number {
  if (row.length === 0) return Infinity
  const stripSize = size * rowFraction
  let worst = 0
  for (const item of row) {
    const frac = item.weight / rowTotal
    const cellSize = (size === _w ? _h : _w) * frac
    const ar = Math.max(stripSize / cellSize, cellSize / stripSize)
    if (ar > worst) worst = ar
  }
  return worst
}

function plColor(pct: number): string {
  if (pct > 0.03) return '#006b02'
  if (pct > 0.01) return '#004a01'
  if (pct > 0) return '#002d01'
  if (pct < -0.03) return '#882a00'
  if (pct < -0.01) return '#5a1c00'
  return '#2d0e00'
}

export default function PositionTreemap({ positions, totalEquity }: Props) {
  if (positions.length === 0) return null

  const items = positions
    .map((p) => ({
      ticker: p.ticker,
      weight: p.market_value / totalEquity,
      pl_pct: p.unrealized_plpc,
    }))
    .sort((a, b) => b.weight - a.weight)

  const W = 560, H = 160
  const cells = squarify(items, 0, 0, W, H)

  return (
    <div className="mb-6">
      <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>HOLDINGS MAP</div>
      <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--color-border)' }}>
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 160 }}>
          {cells.map((cell) => (
            <g key={cell.ticker}>
              <rect
                x={cell.x + 1}
                y={cell.y + 1}
                width={Math.max(cell.w - 2, 0)}
                height={Math.max(cell.h - 2, 0)}
                rx={4}
                fill={plColor(cell.pl_pct)}
              >
                <title>{cell.ticker}: {(cell.weight * 100).toFixed(1)}% of portfolio, P&L {(cell.pl_pct * 100).toFixed(2)}%</title>
              </rect>
              {cell.w > 40 && cell.h > 24 && (
                <text
                  x={cell.x + cell.w / 2}
                  y={cell.y + cell.h / 2}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize={Math.min(14, cell.w / 4, cell.h / 2)}
                  fill="#f5f5f5"
                  style={{ userSelect: 'none' }}
                >
                  {cell.ticker}
                </text>
              )}
              {cell.w > 50 && cell.h > 36 && (
                <text
                  x={cell.x + cell.w / 2}
                  y={cell.y + cell.h / 2 + Math.min(12, cell.h / 3)}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize={Math.min(10, cell.w / 6)}
                  fill="#8e8e93"
                  style={{ userSelect: 'none' }}
                >
                  {(cell.pl_pct * 100 >= 0 ? '+' : '')}{(cell.pl_pct * 100).toFixed(1)}%
                </text>
              )}
            </g>
          ))}
        </svg>
      </div>
    </div>
  )
}
