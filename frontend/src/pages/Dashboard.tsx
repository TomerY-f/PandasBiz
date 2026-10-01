import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { CHART_COLORS, apiGet, fmtILS, fmtPct, memberQuery, monthLabel, withQuery } from '../api'
import { useMember } from '../components/MemberContext'

interface NW {
  current: {
    net_worth_retirement: number
    net_worth_total: number
    liquid: number
    illiquid: number
    liabilities: number
    asset_map: { type: string; label: string; value_ils: number }[]
    by_product: { label: string; value_ils: number }[]
  }
  history: { month: string; net_worth_retirement: number; net_worth_total: number }[]
  years_of_living: number | null
}
interface Summary { month: string; income: number; needs: number; wants: number; expenses: number; balance: number; savings_rate: number | null }

export default function Dashboard() {
  const { member } = useMember()
  const [nw, setNw] = useState<NW | null>(null)
  const [summary, setSummary] = useState<Summary[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet<NW>(withQuery('/sheets/networth', memberQuery(member))).then(setNw).catch((e) => setError(String(e)))
    apiGet<{ summary: Summary[] }>(withQuery('/sheets/income-expense', memberQuery(member)))
      .then((r) => setSummary(r.summary))
      .catch(() => {})
  }, [member])

  if (error) return <div className="alert">שגיאה בטעינת הדשבורד: {error}</div>
  if (!nw) return <div className="empty">טוען...</div>
  const c = nw.current
  const avg = summary.find((s) => s.month === 'avg')
  const months = summary.filter((s) => s.month !== 'avg' && (s.income || s.expenses))
  const empty = !c.asset_map.length && !months.length

  return (
    <div>
      <h1>דשבורד משפחתי</h1>
      {empty && (
        <div className="card empty">
          ברוכים הבאים 👋 עדיין אין נתונים. גררו קבצים לעמוד של כל מוצר (בנק, כרטיסי אשראי, משכנתא...).
        </div>
      )}
      <div className="kpi-grid">
        <Link to="/networth" className="card stat" style={{ textDecoration: 'none', color: 'inherit' }}>
          <div className="label">שווי נקי כולל</div>
          <div className={`value ${c.net_worth_total < 0 ? 'neg' : ''}`}>{fmtILS(c.net_worth_total)}</div>
          <div className="sub">לפרישה מוקדמת: {fmtILS(c.net_worth_retirement)}</div>
        </Link>
        <div className="card stat"><div className="label">נכסים</div><div className="value pos">{fmtILS(c.liquid + c.illiquid)}</div>
          <div className="sub">נזילים: {fmtILS(c.liquid)}</div></div>
        <div className="card stat"><div className="label">התחייבויות</div><div className="value neg">{fmtILS(c.liabilities)}</div></div>
        <Link to="/income-expense" className="card stat" style={{ textDecoration: 'none', color: 'inherit' }}>
          <div className="label">תזרים חודשי ממוצע</div>
          <div className={`value ${(avg?.balance ?? 0) >= 0 ? 'pos' : 'neg'}`}>{fmtILS(avg?.balance)}</div>
          <div className="sub">הכנסות {fmtILS(avg?.income)} · הוצאות {fmtILS(avg?.expenses)}</div>
        </Link>
        <div className="card stat"><div className="label">שיעור חיסכון</div><div className="value">{fmtPct(avg?.savings_rate)}</div>
          <div className="sub">שנות מחיה צבורות: {nw.years_of_living != null && nw.years_of_living > 0 ? nw.years_of_living : '—'}</div></div>
      </div>

      <div className="grid grid-2">
        {months.length > 0 && (
          <div className="card">
            <h2>הכנסות מול הוצאות</h2>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={months.map((s) => ({ month: monthLabel(s.month), הכנסות: s.income, צרכים: s.needs, רצונות: s.wants }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} width={70} />
                <Tooltip formatter={(v) => fmtILS(Number(v))} />
                <Legend />
                <Bar dataKey="הכנסות" fill="#00B894" />
                <Bar dataKey="צרכים" stackId="e" fill="#E17055" />
                <Bar dataKey="רצונות" stackId="e" fill="#FDCB6E" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        {c.asset_map.length > 0 && (
          <div className="card">
            <h2>מפת הנכסים</h2>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={c.asset_map} dataKey="value_ils" nameKey="label" innerRadius={60} outerRadius={100} paddingAngle={2}>
                  {c.asset_map.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v) => fmtILS(Number(v))} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="grid grid-2">
        {nw.history.length > 1 && (
          <div className="card">
            <h2>שווי נקי לאורך זמן</h2>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={nw.history.map((h) => ({ month: monthLabel(h.month), 'כולל': h.net_worth_total, 'לפרישה': h.net_worth_retirement }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} width={90} />
                <Tooltip formatter={(v) => fmtILS(Number(v))} />
                <Legend />
                <Area type="monotone" dataKey="כולל" stroke="#00B894" fill="#00B894" fillOpacity={0.1} />
                <Area type="monotone" dataKey="לפרישה" stroke="#6C5CE7" fill="#6C5CE7" fillOpacity={0.15} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
        {c.by_product.length > 0 && (
          <div className="card">
            <h2>לפי מוצר</h2>
            <table>
              <tbody>
                {c.by_product.map((p) => (
                  <tr key={p.label}><td>{p.label}</td><td className={p.value_ils < 0 ? 'neg' : ''}>{fmtILS(p.value_ils)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
