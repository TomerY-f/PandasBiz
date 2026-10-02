import { Fragment, useCallback, useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { apiGet, apiSend, fmtILS, fmtPct, memberQuery, monthLabel, withQuery } from '../api'
import { useMember } from '../components/MemberContext'

interface Line {
  name: string
  values: Record<string, number>
  manual: Record<string, number>
  total: number
  avg: number
  need_4pct: number
  need_3pct: number
}
interface Group {
  key: string
  label: string
  lines: Line[]
  totals: Record<string, number>
  total: number
  avg: number
  need_4pct: number
  need_3pct: number
}
interface Summary {
  month: string
  income: number
  needs: number
  wants: number
  expenses: number
  balance: number
  savings_rate: number | null
  savings: number
}
interface Sheet {
  months: string[]
  active_months: number
  groups: Group[]
  summary: Summary[]
  retirement_need_4pct: number
  retirement_need_3pct: number
}

const n0 = (v: number | undefined) => (v ? Math.round(v).toLocaleString('he-IL') : '')

export default function IncomeExpense() {
  const { member } = useMember()
  const [sheet, setSheet] = useState<Sheet | null>(null)
  const [end, setEnd] = useState('')
  const [editing, setEditing] = useState<{ line: string; month: string; value: string } | null>(null)
  const [hideEmpty, setHideEmpty] = useState(true)
  const [search, setSearch] = useState('')
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const [groupFilter, setGroupFilter] = useState('')
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    apiGet<Sheet>(withQuery('/sheets/income-expense', end ? `end=${end}` : '', memberQuery(member)))
      .then(setSheet)
      .catch((e) => setError(String(e)))
  }, [end, member])

  useEffect(load, [load])

  if (error) return <div className="alert">{error}</div>
  if (!sheet) return <div className="empty">טוען...</div>
  if (!sheet.months.length)
    return (
      <div>
        <h1>מעקב הכנסות והוצאות</h1>
        <div className="card empty">אין עדיין תנועות. העלו קבצי עו"ש וכרטיסי אשראי בעמודי המוצרים.</div>
      </div>
    )

  const saveManual = async () => {
    if (!editing) return
    const memberId = member !== 'all' && member !== 'joint' ? Number(member) : null
    await apiSend('PUT', '/entries', {
      line: editing.line,
      month: editing.month,
      amount: Number(editing.value) || 0,
      member_id: memberId,
    })
    setEditing(null)
    load()
  }

  const avg = sheet.summary.find((s) => s.month === 'avg')
  const chartData = sheet.summary
    .filter((s) => s.month !== 'avg' && (s.income || s.expenses))
    .map((s) => ({ month: monthLabel(s.month), הכנסות: s.income, 'צרכים': s.needs, 'רצונות': s.wants }))

  const shownGroups = sheet.groups.filter((g) => g.key !== 'excluded' || g.lines.some((l) => l.total))

  return (
    <div>
      <div className="row spread">
        <h1>מעקב הכנסות והוצאות</h1>
        <div className="row">
          <label className="muted">
            <input type="checkbox" checked={hideEmpty} onChange={(e) => setHideEmpty(e.target.checked)} /> הסתר שורות ריקות
          </label>
          <span className="muted">חודש אחרון:</span>
          <input type="month" value={end || sheet.months[sheet.months.length - 1]} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </div>

      {avg && (
        <div className="kpi-grid">
          <div className="card stat"><div className="label">הכנסה חודשית ממוצעת</div><div className="value pos">{fmtILS(avg.income)}</div></div>
          <div className="card stat"><div className="label">הוצאות בגין צרכים</div><div className="value">{fmtILS(avg.needs)}</div></div>
          <div className="card stat"><div className="label">הוצאות בגין רצונות</div><div className="value">{fmtILS(avg.wants)}</div></div>
          <div className="card stat">
            <div className="label">האם אני בפלוס / מינוס</div>
            <div className={`value ${avg.balance >= 0 ? 'pos' : 'neg'}`}>{fmtILS(avg.balance)}</div>
          </div>
          <div className="card stat"><div className="label">שיעור חיסכון</div><div className="value">{fmtPct(avg.savings_rate)}</div>
            <div className="sub">לא כולל הפרשות לפנסיה וקרנות</div></div>
          <div className="card stat"><div className="label">סכום דרוש לפרישה (4% / 3%)</div>
            <div className="value" style={{ fontSize: 19 }}>{fmtILS(sheet.retirement_need_4pct)}</div>
            <div className="sub">{fmtILS(sheet.retirement_need_3pct)} במשיכת 3%</div></div>
        </div>
      )}

      <div className="card">
        <h2>הכנסות מול הוצאות</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData}>
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

      <div className="card">
        <p className="muted" style={{ marginTop: 0 }}>
          הנתונים מחושבים מתנועות העו"ש והאשראי לפי שורות הגיליון. לחיצה על תא מוסיפה סכום ידני לחודש (למשל הפקדות מהתלוש או מזומן).
          ממוצע מחושב על {sheet.active_months} חודשים עם נתונים. סיווג תנועות משנים בעמוד "הגדרות".
        </p>
        <div className="filters">
          <label>חיפוש שורה<input placeholder="למשל: מזון" value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 160 }} /></label>
          <label>קבוצה
            <select value={groupFilter} onChange={(e) => setGroupFilter(e.target.value)}>
              <option value="">כל הקבוצות</option>
              {shownGroups.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}
            </select>
          </label>
          <button className="ghost small" onClick={() => setCollapsed(Object.fromEntries(shownGroups.map((g) => [g.key, true])))}>כווץ הכל</button>
          <button className="ghost small" onClick={() => setCollapsed({})}>פתח הכל</button>
          {sort && <button className="ghost small" onClick={() => setSort(null)}>סדר מקורי</button>}
          <span className="muted">לחיצה על כותרת עמודה ממיינת את השורות בכל קבוצה</span>
        </div>
        <div className="sheet-wrap sticky">
          <table className="sheet">
            <thead>
              <tr>
                {[{ key: 'name', label: 'פירוט' }, { key: 'avg', label: 'ממוצע' }, ...sheet.months.map((m) => ({ key: m, label: monthLabel(m) }))].map((c) => (
                  <th key={c.key} className="sortable"
                    onClick={() => setSort({ key: c.key, dir: sort?.key === c.key ? (sort.dir === 1 ? -1 : 1) : c.key === 'name' ? 1 : -1 })}>
                    {c.label}{sort?.key === c.key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
                  </th>
                ))}
                <th title="כמה עליכם לחסוך כדי לממן את ההוצאה לכל החיים (משיכה של 4% בשנה)">4%</th>
                <th title="כמה עליכם לחסוך כדי לממן את ההוצאה לכל החיים (משיכה של 3% בשנה)">3%</th>
              </tr>
            </thead>
            <tbody>
              {shownGroups.filter((g) => !groupFilter || g.key === groupFilter).map((g) => {
                const lineValue = (l: Line) => (sort?.key === 'name' ? l.name : sort?.key === 'avg' ? l.avg : l.values[sort?.key ?? ''] ?? 0)
                const lines = (hideEmpty ? g.lines.filter((l) => l.total || Object.keys(l.manual).length) : g.lines)
                  .filter((l) => !search || l.name.includes(search))
                  .sort((a, b) => {
                    if (!sort) return 0
                    const va = lineValue(a), vb = lineValue(b)
                    return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir
                  })
                if (search && !lines.length) return null
                const isCollapsed = collapsed[g.key] && !search
                const isExpense = !['income', 'saving_gross', 'saving_net', 'excluded'].includes(g.key)
                return (
                  <Fragment key={g.key}>
                    <tr className="group" onClick={() => setCollapsed({ ...collapsed, [g.key]: !collapsed[g.key] })}>
                      <td colSpan={sheet.months.length + 4}>{isCollapsed ? '◂' : '▾'} {g.label} <span className="muted">({lines.length})</span></td>
                    </tr>
                    {!isCollapsed && lines.map((l) => (
                      <tr key={l.name}>
                        <td>{l.name}</td>
                        <td className="num avg">{n0(l.avg)}</td>
                        {sheet.months.map((m) => {
                          const isEditing = editing?.line === l.name && editing.month === m
                          return (
                            <td
                              key={m}
                              className={`num editable ${l.manual[m] ? 'manual' : ''}`}
                              title={l.manual[m] ? `כולל ${l.manual[m]} ידני` : 'לחצו להוספת סכום ידני'}
                              onClick={() => !isEditing && setEditing({ line: l.name, month: m, value: String(l.manual[m] ?? '') })}
                            >
                              {isEditing ? (
                                <input
                                  autoFocus
                                  type="number"
                                  value={editing.value}
                                  onChange={(e) => setEditing({ ...editing, value: e.target.value })}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') saveManual()
                                    if (e.key === 'Escape') setEditing(null)
                                  }}
                                  onBlur={saveManual}
                                />
                              ) : (
                                n0(l.values[m])
                              )}
                            </td>
                          )
                        })}
                        <td className="num">{isExpense ? n0(l.need_4pct) : ''}</td>
                        <td className="num">{isExpense ? n0(l.need_3pct) : ''}</td>
                      </tr>
                    ))}
                    <tr className="total">
                      <td>סה"כ {g.label}</td>
                      <td className="num avg">{n0(g.avg)}</td>
                      {sheet.months.map((m) => <td key={m} className="num">{n0(g.totals[m])}</td>)}
                      <td className="num">{isExpense ? n0(g.need_4pct) : ''}</td>
                      <td className="num">{isExpense ? n0(g.need_3pct) : ''}</td>
                    </tr>
                  </Fragment>
                )
              })}
              <tr className="group"><td colSpan={sheet.months.length + 4}>תמונת מצב</td></tr>
              {([
                ['income', 'סה"כ הכנסות נטו'],
                ['needs', 'הוצאות בגין צרכים'],
                ['wants', 'הוצאות בגין רצונות'],
                ['expenses', 'סה"כ הוצאות'],
                ['balance', 'האם אני בפלוס / מינוס'],
                ['savings_rate', 'שיעור חיסכון'],
              ] as const).map(([k, label]) => (
                <tr key={k} className={k === 'balance' ? 'total' : ''}>
                  <td>{label}</td>
                  {[...sheet.summary.filter((s) => s.month === 'avg'), ...sheet.summary.filter((s) => s.month !== 'avg')].map((s) => {
                    const v = s[k]
                    const text = k === 'savings_rate' ? (v == null ? '' : fmtPct(v as number)) : n0(v as number)
                    const cls = k === 'balance' && v ? ((v as number) >= 0 ? 'pos' : 'neg') : ''
                    return <td key={s.month} className={`num ${cls} ${s.month === 'avg' ? 'avg' : ''}`}>{text}</td>
                  })}
                  <td /><td />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
