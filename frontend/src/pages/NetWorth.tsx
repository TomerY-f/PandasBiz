import { useCallback, useEffect, useState } from 'react'
import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { apiGet, apiSend, fmtILS, fmtNum, fmtPct, memberQuery, monthLabel, withQuery } from '../api'
import { useMember } from '../components/MemberContext'

interface Bucket { key: string; label: string; group: 'liquid' | 'illiquid' | 'liability' }
interface Totals {
  buckets: Record<string, number>
  liquid: number
  illiquid: number
  liabilities: number
  net_worth_retirement: number
  net_worth_total: number
}
interface HistoryRow extends Totals { month: string; change: number | null; change_pct: number | null }
interface BreakdownRow { account_id: number; name: string; product_label: string; owner_id: number | null; value_ils: number; parts: Record<string, number> }
interface NetWorthData {
  current: Totals & { breakdown: BreakdownRow[]; usd_ils: number }
  history: HistoryRow[]
  monthly_need: number | null
  years_of_living: number | null
  withdraw_4pct_monthly: number
  withdraw_3pct_monthly: number
  buckets: Bucket[]
}

const GROUP_LABELS = {
  liquid: 'נכסים מניבים נזילים (למימון פרישה מוקדמת)',
  illiquid: 'נכסים שאינם מניבים או שאינם נזילים',
  liability: 'התחייבויות',
}

export default function NetWorth() {
  const { member, memberName, members } = useMember()
  const [data, setData] = useState<NetWorthData | null>(null)
  const [need, setNeed] = useState<string>('')
  const [item, setItem] = useState({ name: '', nw_bucket: 'car', value: '', owner_id: '' })
  const [msg, setMsg] = useState('')

  const load = useCallback(() => {
    apiGet<NetWorthData>(withQuery('/sheets/networth', memberQuery(member), need ? `monthly_need=${need}` : '')).then(setData)
  }, [member, need])

  useEffect(load, [load])

  useEffect(() => {
    apiGet<{ value: string | null }>('/settings/monthly_need').then((r) => r.value && setNeed(r.value))
  }, [])

  if (!data) return <div className="empty">טוען...</div>
  const c = data.current

  const saveNeed = async (v: string) => {
    setNeed(v)
    await apiSend('PUT', '/settings/monthly_need', { value: v })
  }

  const addItem = async () => {
    if (!item.name || !item.value) return
    try {
      await apiSend('POST', '/sheets/manual-items', {
        name: item.name,
        nw_bucket: item.nw_bucket,
        value: Number(item.value),
        owner_id: item.owner_id ? Number(item.owner_id) : null,
      })
      setItem({ name: '', nw_bucket: 'car', value: '', owner_id: '' })
      setMsg('')
      load()
    } catch (e) {
      setMsg(String(e))
    }
  }

  const record = async () => {
    const r = await apiSend<{ recorded: number }>('POST', '/sheets/networth/record')
    setMsg(`נשמר צילום מצב ל-${r.recorded} חשבונות`)
    load()
  }

  const chart = data.history.map((h) => ({
    month: monthLabel(h.month),
    'שווי נקי לפרישה': h.net_worth_retirement,
    'שווי נקי כולל': h.net_worth_total,
  }))

  const groups = (['liquid', 'illiquid', 'liability'] as const).map((g) => ({
    key: g,
    buckets: data.buckets.filter((b) => b.group === g),
  }))

  return (
    <div>
      <div className="row spread">
        <h1>מעקב שווי נקי</h1>
        <button className="ghost" onClick={record}>📸 שמור צילום מצב חודשי</button>
      </div>
      {msg && <div className="alert warn">{msg}</div>}

      <div className="kpi-grid">
        <div className="card stat"><div className="label">שווי נקי לפרישה מוקדמת</div>
          <div className={`value ${c.net_worth_retirement >= 0 ? '' : 'neg'}`}>{fmtILS(c.net_worth_retirement)}</div>
          <div className="sub">נכסים נזילים + התחייבויות</div></div>
        <div className="card stat"><div className="label">שווי נקי כולל</div>
          <div className={`value ${c.net_worth_total >= 0 ? '' : 'neg'}`}>{fmtILS(c.net_worth_total)}</div></div>
        <div className="card stat"><div className="label">שנות מחיה צבורות</div>
          <div className="value">{data.years_of_living == null || data.years_of_living <= 0 ? '—' : fmtNum(data.years_of_living, 1)}</div>
          <div className="sub">לפי הוצאה של {fmtILS(data.monthly_need)} בחודש</div></div>
        <div className="card stat"><div className="label">משיכה חודשית בטוחה</div>
          <div className="value" style={{ fontSize: 19 }}>{fmtILS(Math.max(0, data.withdraw_4pct_monthly))} <span className="muted">(4%)</span></div>
          <div className="sub">{fmtILS(Math.max(0, data.withdraw_3pct_monthly))} בשיעור 3%</div></div>
      </div>

      <div className="card explain">
        <h2>איך מחושב "שווי נקי לפרישה מוקדמת"?</h2>
        <p>
          זה הכסף שיכול לממן אתכם לפני גיל 60: <b>נכסים מניבים ונזילים</b> פחות <b>כל ההתחייבויות</b>.
          {' '}{fmtILS(c.liquid)} − {fmtILS(Math.abs(c.liabilities))} = <b>{fmtILS(c.net_worth_retirement)}</b>.
        </p>
        <p className="muted">
          נכסים נזילים: מזומן ועו"ש, מט"ח, פקדונות וקרנות כספיות, אג"ח ומניות, קרן השתלמות, קופת גמל להשקעה ונדל"ן להשקעה.
          לא נכללים: דירת המגורים, הרכב, קרנות פנסיה וקופות גמל לתגמולים (נעולות עד הפרישה) וערך פדיון ביטוח.
          התחייבויות: משכנתא, הלוואות וחיובי אשראי שטרם ירדו. כך זה מחושב גם בגיליון של הסולידית
          ("שווי נקי לפרישה מוקדמת" = סה"כ נכסים לפרישה מוקדמת + סה"כ התחייבויות).
        </p>
      </div>

      <div className="card row">
        <span>כמה כסף אתם <b>באמת</b> צריכים כדי לחיות בחודש?</span>
        <input type="number" value={need} placeholder={data.monthly_need ? String(Math.round(data.monthly_need)) : ''}
          onChange={(e) => saveNeed(e.target.value)} style={{ width: 130 }} />
        <span className="muted">ריק = ממוצע ההוצאות בפועל מגיליון ההכנסות וההוצאות</span>
      </div>

      <div className="grid grid-3">
        {groups.map((g) => {
          const total = g.buckets.reduce((s, b) => s + (c.buckets[b.key] ?? 0), 0)
          return (
            <div className="card" key={g.key}>
              <h2>{GROUP_LABELS[g.key]}</h2>
              <table>
                <tbody>
                  {g.buckets.map((b) => (
                    <tr key={b.key}>
                      <td>{b.label}</td>
                      <td className={(c.buckets[b.key] ?? 0) < 0 ? 'neg' : ''}>{c.buckets[b.key] ? fmtILS(c.buckets[b.key]) : <span className="muted">—</span>}</td>
                    </tr>
                  ))}
                  <tr className="total"><td><b>סה"כ</b></td><td><b>{fmtILS(total)}</b></td></tr>
                </tbody>
              </table>
            </div>
          )
        })}
      </div>

      {chart.length > 0 && (
        <div className="card">
          <h2>שווי נקי לאורך זמן</h2>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={chart}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} width={90} />
              <Tooltip formatter={(v) => fmtILS(Number(v))} />
              <Legend />
              <Area type="monotone" dataKey="שווי נקי לפרישה" stroke="#6C5CE7" fill="#6C5CE7" fillOpacity={0.15} />
              <Area type="monotone" dataKey="שווי נקי כולל" stroke="#00B894" fill="#00B894" fillOpacity={0.08} />
            </AreaChart>
          </ResponsiveContainer>
          <div className="sheet-wrap">
            <table className="sheet">
              <thead>
                <tr><th>חודש</th><th>נכסים נזילים</th><th>לא נזילים</th><th>התחייבויות</th><th>שווי נקי לפרישה</th><th>שינוי חודשי</th><th>שינוי %</th><th>שווי נקי כולל</th></tr>
              </thead>
              <tbody>
                {[...data.history].reverse().map((h) => (
                  <tr key={h.month}>
                    <td>{monthLabel(h.month)}</td>
                    <td className="num">{fmtILS(h.liquid)}</td>
                    <td className="num">{fmtILS(h.illiquid)}</td>
                    <td className="num neg">{fmtILS(h.liabilities)}</td>
                    <td className="num"><b>{fmtILS(h.net_worth_retirement)}</b></td>
                    <td className={`num ${h.change == null ? '' : h.change >= 0 ? 'pos' : 'neg'}`}>{h.change == null ? '' : fmtILS(h.change)}</td>
                    <td className="num">{fmtPct(h.change_pct)}</td>
                    <td className="num">{fmtILS(h.net_worth_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted">ההיסטוריה נבנית מעדכוני השווי של כל חשבון (כל קובץ שמועלה ו"צילום מצב חודשי").</p>
        </div>
      )}

      <div className="card">
        <h2>פירוט לפי חשבון</h2>
        <table>
          <thead><tr><th>חשבון</th><th>מוצר</th><th>בעלים</th><th>שווי ₪</th></tr></thead>
          <tbody>
            {c.breakdown.map((b) => (
              <tr key={b.account_id}>
                <td>{b.name}</td>
                <td>{b.product_label}</td>
                <td>{memberName(b.owner_id)}</td>
                <td className={b.value_ils < 0 ? 'neg' : ''}>{fmtILS(b.value_ils)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>הוספת נכס / התחייבות ידנית</h2>
        <p className="muted">לנכסים שאין להם קובץ: רכב, מתכות יקרות, שווי עסק, הלוואת רכב, מס רווח הון שנותר לשלם...</p>
        <div className="row">
          <input placeholder="שם (למשל: רכב משפחתי)" value={item.name} onChange={(e) => setItem({ ...item, name: e.target.value })} />
          <select value={item.nw_bucket} onChange={(e) => setItem({ ...item, nw_bucket: e.target.value })}>
            {groups.map((g) => (
              <optgroup key={g.key} label={GROUP_LABELS[g.key]}>
                {g.buckets.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
              </optgroup>
            ))}
          </select>
          <input type="number" placeholder="שווי ₪" value={item.value} onChange={(e) => setItem({ ...item, value: e.target.value })} style={{ width: 130 }} />
          <select value={item.owner_id} onChange={(e) => setItem({ ...item, owner_id: e.target.value })}>
            <option value="">משותף</option>
            {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
          <button onClick={addItem}>הוסף</button>
        </div>
      </div>
    </div>
  )
}
