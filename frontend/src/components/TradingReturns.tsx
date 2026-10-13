import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { apiGet, memberQuery, monthLabel, withQuery } from '../api'

interface Returns {
  months: string[]
  holdings: { symbol: string; name: string; value_ils: number; ytd: number | null; monthly: Record<string, number> }[]
  portfolio: { ytd: number | null; monthly: Record<string, number | null>; weights: Record<string, number> } | null
}

const pct = (v: number | null | undefined) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`)
const cls = (v: number | null | undefined) => (v == null ? 'muted' : v >= 0 ? 'pos' : 'neg')

/** Year-to-date and monthly price returns of the current trading holdings (from market data). */
export default function TradingReturns({ member }: { member: string }) {
  const [data, setData] = useState<Returns | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    apiGet<Returns>(withQuery('/products/trading/returns', memberQuery(member))).then(setData).catch((e) => setError(String(e)))
  }, [member])

  if (error) return <div className="card muted">לא ניתן לחשב תשואות כרגע (נדרש חיבור לאינטרנט לנתוני שוק).</div>
  if (!data || !data.portfolio) return null
  const p = data.portfolio
  const chart = data.months.map((m) => ({ month: monthLabel(m), value: p.monthly[m] ?? 0 }))

  return (
    <div className="card">
      <div className="row spread">
        <h2>תשואה מתחילת השנה ולפי חודש</h2>
        <span>תשואת התיק מתחילת השנה: <b className={cls(p.ytd)}>{pct(p.ytd)}</b></span>
      </div>
      <ResponsiveContainer debounce={200} width="100%" height={220}>
        <BarChart data={chart}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="month" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} width={50} unit="%" />
          <ReferenceLine y={0} stroke="#999" />
          <Tooltip formatter={(v) => pct(Number(v))} />
          <Bar dataKey="value" name="תשואה חודשית" isAnimationActive={false}>
            {chart.map((c) => <Cell key={c.month} fill={c.value >= 0 ? '#00B894' : '#E17055'} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="table-scroll">
        <table>
          <thead>
            <tr><th>נייר</th><th>משקל</th><th>מתחילת השנה</th>{data.months.map((m) => <th key={m}>{monthLabel(m)}</th>)}</tr>
          </thead>
          <tbody>
            {data.holdings.map((h) => (
              <tr key={h.symbol}>
                <td><b>{h.symbol}</b></td>
                <td className="muted">{p.weights[h.symbol]}%</td>
                <td className={cls(h.ytd)}><b>{pct(h.ytd)}</b></td>
                {data.months.map((m) => <td key={m} className={cls(h.monthly[m])}>{pct(h.monthly[m])}</td>)}
              </tr>
            ))}
            <tr className="total">
              <td><b>התיק</b></td><td>100%</td><td className={cls(p.ytd)}><b>{pct(p.ytd)}</b></td>
              {data.months.map((m) => <td key={m} className={cls(p.monthly[m])}><b>{pct(p.monthly[m])}</b></td>)}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="muted">
        תשואת מחיר במונחי דולר לפי מחירי סגירה חודשיים (כולל דיבידנדים מושקעים), של האחזקות הנוכחיות במשקלן היום.
        החודש האחרון חלקי. זה לא מביא בחשבון קניות ומכירות במהלך השנה או שינויי שער הדולר.
      </p>
    </div>
  )
}
