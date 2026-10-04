import { useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtILS, monthLabel } from '../api'

export interface NetWorthPoint {
  month: string
  liquid: number
  illiquid: number
  liabilities: number
  net_worth_retirement: number
  net_worth_total: number
}

type Range = 'YTD' | '1Y' | '3Y' | '5Y'
const RANGES: { key: Range; label: string }[] = [
  { key: 'YTD', label: 'מתחילת השנה' },
  { key: '1Y', label: 'שנה' },
  { key: '3Y', label: '3 שנים' },
  { key: '5Y', label: '5 שנים' },
]

const SERIES = [
  { key: 'net_worth_total', label: 'שווי נקי כולל', color: '#00B894', width: 3 },
  { key: 'net_worth_retirement', label: 'שווי נקי לפרישה מוקדמת', color: '#6C5CE7', width: 3 },
  { key: 'liquid', label: 'הון נזיל', color: '#0984E3', width: 2 },
  { key: 'illiquid', label: 'הון לא נזיל', color: '#E17055', width: 2 },
] as const

/** Net worth over time with stock-chart style range tabs (YTD by default) and liquid / illiquid capital curves. */
export default function NetWorthChart({ history, height = 300 }: { history: NetWorthPoint[]; height?: number }) {
  const [range, setRange] = useState<Range>('YTD')
  if (!history.length) return null
  const last = history[history.length - 1].month
  const [y, m] = last.split('-').map(Number)
  const startMonth =
    range === 'YTD'
      ? `${y - 1}-12`
      : (() => {
          const back = { '1Y': 12, '3Y': 36, '5Y': 60 }[range]
          const idx = y * 12 + (m - 1) - back
          return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, '0')}`
        })()
  const rows = history.filter((h) => h.month >= startMonth)
  const first = rows[0]
  const change = first ? rows[rows.length - 1].net_worth_total - first.net_worth_total : 0
  const data = rows.map((h) => ({
    month: monthLabel(h.month),
    ...Object.fromEntries(SERIES.map((s) => [s.label, h[s.key]])),
  }))

  return (
    <div>
      <div className="row spread" style={{ marginBottom: 6 }}>
        <span className="muted">
          שינוי בשווי הנקי הכולל בטווח: <b className={change >= 0 ? 'pos' : 'neg'}>{change >= 0 ? '+' : '−'}{fmtILS(Math.abs(change))}</b>
          {history[0].month > startMonth && <> · יש נתונים רק מ-{monthLabel(history[0].month)}</>}
        </span>
        <div className="range-tabs">
          {RANGES.map((r) => (
            <button key={r.key} className={range === r.key ? 'active' : ''} onClick={() => setRange(r.key)}>{r.label}</button>
          ))}
        </div>
      </div>
      <ResponsiveContainer debounce={200} width="100%" height={height}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="month" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} width={90} tickFormatter={(v) => `₪${(Number(v) / 1e6).toFixed(1)}M`} />
          <Tooltip formatter={(v) => fmtILS(Number(v))} />
          <Legend />
          {SERIES.map((s) => (
            <Line key={s.key} type="monotone" dataKey={s.label} stroke={s.color} strokeWidth={s.width} dot={data.length < 16 ? { r: 3 } : false} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
