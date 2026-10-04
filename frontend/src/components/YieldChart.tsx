import { useMemo, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CHART_COLORS } from '../api'

export interface YieldTrack {
  name: string
  balance: number
  share_pct: number
  last_month?: number
  ytd?: number
  y1?: number
  y3?: number
  y5?: number
  y3_avg?: number
  y5_avg?: number
}
export interface ProductYields {
  product: string
  as_of: string | null
  tracks: YieldTrack[]
}

type Range = '1M' | 'YTD' | '1Y' | '3Y' | '5Y'
const RANGES: { key: Range; label: string }[] = [
  { key: '1M', label: 'חודש' },
  { key: 'YTD', label: 'מתחילת השנה' },
  { key: '1Y', label: 'שנה' },
  { key: '3Y', label: '3 שנים' },
  { key: '5Y', label: '5 שנים' },
]
const RANGE_MONTHS: Record<Range, number> = { '1M': 1, YTD: 0, '1Y': 12, '3Y': 36, '5Y': 60 }

const pct = (v: number | undefined) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`)
const cls = (v: number | undefined) => (v == null ? 'muted' : v >= 0 ? 'pos' : 'neg')

const monthsBack = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth() - n, d.getDate())
const iso = (d: Date) => d.toISOString().slice(0, 10)

/** Growth index at each reported anchor (as-of date = 1.0); a track's line connects these anchors. */
function anchors(t: YieldTrack, asOf: Date): { date: Date; index: number }[] {
  const out: { date: Date; index: number }[] = [{ date: asOf, index: 1 }]
  const add = (date: Date, ret: number | undefined) => {
    if (ret != null) out.push({ date, index: 1 / (1 + ret / 100) })
  }
  add(monthsBack(asOf, 1), t.last_month)
  add(new Date(asOf.getFullYear() - 1, 11, 31), t.ytd)
  add(monthsBack(asOf, 12), t.y1)
  add(monthsBack(asOf, 36), t.y3)
  add(monthsBack(asOf, 60), t.y5)
  return out.sort((a, b) => a.date.getTime() - b.date.getTime())
}

export default function YieldChart({ products }: { products: ProductYields[] }) {
  const [range, setRange] = useState<Range>('YTD')
  const [picked, setPicked] = useState<string[] | null>(null)  // null = default (largest 3 tracks)

  // the same track often appears in several funds (e.g. "1200 מניות"); show it once
  const tracks = useMemo(() => {
    const seen = new Map<string, YieldTrack & { products: string[]; as_of: string | null }>()
    products.forEach((p) =>
      p.tracks.forEach((t) => {
        const key = `${t.name}|${t.ytd}|${t.y1}`
        const cur = seen.get(key)
        if (cur) {
          cur.balance += t.balance
          cur.products.push(p.product)
        } else seen.set(key, { ...t, products: [p.product], as_of: p.as_of })
      }),
    )
    return Array.from(seen.values()).sort((a, b) => b.balance - a.balance)
  }, [products])

  const label = (t: { name: string; products: string[] }) => `${t.name} · ${t.products[0]}`
  const active = picked ?? tracks.slice(0, 3).map(label)
  const toggle = (l: string) => setPicked(active.includes(l) ? active.filter((x) => x !== l) : [...active, l])

  const data = useMemo(() => {
    const asOfStr = tracks.find((t) => t.as_of)?.as_of
    if (!asOfStr) return []
    const asOf = new Date(asOfStr)
    const start = range === 'YTD' ? new Date(asOf.getFullYear() - 1, 11, 31) : monthsBack(asOf, RANGE_MONTHS[range])
    const rows = new Map<string, Record<string, number | string>>()
    tracks.forEach((t) => {
      const pts = anchors(t, asOf).filter((a) => a.date.getTime() >= start.getTime() - 86400000)
      if (!active.includes(label(t))) return
      if (pts.length < 2 || pts[0].date.getTime() > start.getTime() + 86400000) return // no data back to the range start
      const base = pts[0].index
      pts.forEach((a) => {
        const k = iso(a.date)
        const row = rows.get(k) ?? { date: k, ts: a.date.getTime() }
        row[label(t)] = Math.round((a.index / base - 1) * 10000) / 100
        rows.set(k, row)
      })
    })
    return Array.from(rows.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)))
  }, [tracks, range, active])

  const shown = tracks.filter((t) => data.some((r) => label(t) in r))

  return (
    <div className="yield-chart">
      <div className="row spread">
        <h3 style={{ margin: 0 }}>תשואות לפי מסלול השקעה (דיווח משרד האוצר{tracks[0]?.as_of ? `, נכון ל-${tracks[0].as_of}` : ''})</h3>
        <div className="range-tabs">
          {RANGES.map((r) => (
            <button key={r.key} className={range === r.key ? 'active' : ''} onClick={() => setRange(r.key)}>{r.label}</button>
          ))}
        </div>
      </div>
      <div className="row" style={{ margin: '6px 0' }}>
        {tracks.map((t) => (
          <span key={label(t)} className={`chip ${active.includes(label(t)) ? '' : 'off'}`} onClick={() => toggle(label(t))}>{label(t)}</span>
        ))}
      </div>
      {data.length > 1 ? (
        <ResponsiveContainer debounce={200} width="100%" height={260}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="ts" type="number" scale="time" domain={['dataMin', 'dataMax']} tick={{ fontSize: 10 }}
              tickFormatter={(v) => new Date(Number(v)).toLocaleDateString('he-IL', { month: 'short', year: '2-digit' })} />
            <YAxis tick={{ fontSize: 11 }} width={50} unit="%" />
            <ReferenceLine y={0} stroke="#999" />
            <Tooltip formatter={(v) => `${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(2)}%`}
              labelFormatter={(v) => new Date(Number(v)).toLocaleDateString('he-IL')} />
            <Legend />
            {shown.map((t, i) => (
              <Line key={label(t)} type="monotone" dataKey={label(t)} stroke={CHART_COLORS[i % CHART_COLORS.length]} strokeWidth={2.5} dot={{ r: 3 }} connectNulls isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p className="muted">אין נתוני תשואה לטווח הזה.</p>
      )}
      <p className="muted" style={{ marginTop: 0 }}>
        תשואה מצטברת מתחילת הטווח. הקו מחבר בין נקודות הדיווח בדוח (חודש, תחילת השנה, שנה, 3 ו-5 שנים) ואינו נתון יומי.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr><th>מסלול</th><th>צבירה</th><th>חודש</th><th>מתחילת השנה</th><th>12 חודשים</th><th>3 שנים</th><th>5 שנים</th><th>ממוצע שנתי 3 ש׳</th><th>ממוצע שנתי 5 ש׳</th></tr>
          </thead>
          <tbody>
            {tracks.map((t) => (
              <tr key={label(t)}>
                <td><b>{t.name}</b> <span className="muted">{t.products.join(', ')}</span></td>
                <td>₪{Math.round(t.balance).toLocaleString('he-IL')}</td>
                {(['last_month', 'ytd', 'y1', 'y3', 'y5', 'y3_avg', 'y5_avg'] as const).map((k) => (
                  <td key={k} className={cls(t[k])}>{pct(t[k])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
