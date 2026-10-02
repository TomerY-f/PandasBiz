import { useCallback, useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { type Property, type PropertyDetails, apiGet, apiSend, fmtILS, fmtNum } from '../api'

interface PropertyStats {
  series: { month: string; income: number; expenses: number }[]
  total_income: number
  total_expenses: number
  net: number
}

const emptyForm = {
  name: '', address: '', purchase_price: '', purchase_date: '', monthly_rent: '',
  income_category: 'הכנסה משכירות - נטו', expense_category: 'משכנתא / דמי שכירות', kind: 'residence',
}

export default function RealEstate() {
  const [properties, setProperties] = useState<Property[]>([])
  const [stats, setStats] = useState<Record<number, PropertyStats>>({})
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')
  const [valueForm, setValueForm] = useState({ propertyId: 0, date: new Date().toISOString().slice(0, 10), value: '' })

  const reload = useCallback(() => {
    apiGet<{ properties: Property[] }>('/properties').then((r) => {
      setProperties(r.properties)
      r.properties.forEach((p) => {
        apiGet<PropertyStats>(`/properties/${p.id}/stats`).then((s) =>
          setStats((cur) => ({ ...cur, [p.id]: s })),
        )
      })
    })
  }, [])

  useEffect(reload, [reload])

  const addProperty = async () => {
    if (!form.name) return
    await apiSend('POST', '/properties', {
      name: form.name,
      address: form.address,
      purchase_price: form.purchase_price ? +form.purchase_price : null,
      purchase_date: form.purchase_date || null,
      monthly_rent: +form.monthly_rent || 0,
      income_category: form.income_category,
      expense_category: form.expense_category,
      kind: form.kind,
    })
    setForm(emptyForm)
    setShowForm(false)
    reload()
  }

  const saveValue = async () => {
    const prop = properties.find((p) => p.id === valueForm.propertyId)
    if (!prop || !valueForm.value) return
    await apiSend('POST', '/snapshots', {
      account_id: prop.account_id,
      date: valueForm.date,
      value: +valueForm.value,
      note: 'שערוך ידני',
    })
    setValueForm({ ...valueForm, propertyId: 0, value: '' })
    setSavedMsg(`השווי של ${prop.name} עודכן ל-${fmtILS(+valueForm.value)}`)
    reload()
    window.dispatchEvent(new Event('pandasbiz:refresh'))
  }

  return (
    <div>
      <div className="row spread">
        <h2 style={{ margin: 0 }}>הנכסים שלי</h2>
        <button onClick={() => setShowForm(!showForm)}>{showForm ? 'ביטול' : '+ הוסף נכס'}</button>
      </div>

      {showForm && (
        <div className="card">
          <h2>נכס חדש</h2>
          <div className="grid" style={{ gap: 10 }}>
            <div className="row">
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                <option value="residence">דירת מגורים</option>
                <option value="investment">נדל"ן להשקעה</option>
              </select>
              <input placeholder='שם (למשל "דירה בחיפה")' value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <input placeholder="כתובת" value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })} />
            </div>
            <div className="row">
              <input type="number" placeholder="מחיר רכישה ₪" value={form.purchase_price}
                onChange={(e) => setForm({ ...form, purchase_price: e.target.value })} style={{ width: 150 }} />
              <input type="date" value={form.purchase_date}
                onChange={(e) => setForm({ ...form, purchase_date: e.target.value })} />
              <input type="number" placeholder="שכ״ד חודשי ₪" value={form.monthly_rent}
                onChange={(e) => setForm({ ...form, monthly_rent: e.target.value })} style={{ width: 140 }} />
              <button onClick={addProperty}>שמור</button>
            </div>
            <p className="muted">
              הכנסות והוצאות הנכס מזוהות מתנועות הבנק לפי קטגוריה. הגדר בעמוד "תקציב וקטגוריות" חוק שממפה
              את העברת השכירות לקטגוריה "{form.income_category}" ואת הוצאות הדירה ל-"{form.expense_category}".
            </p>
          </div>
        </div>
      )}

      {properties.length === 0 && !showForm && (
        <div className="card"><div className="empty">אין נכסים עדיין — הוסף את הדירה שלך</div></div>
      )}

      {properties.map((p) => {
        const s = stats[p.id]
        return (
          <div className="card" key={p.id}>
            <div className="row spread">
              <h2>🏠 {p.name} {p.address && <span className="muted">— {p.address}</span>}</h2>
              <button className="small" onClick={() => { setSavedMsg(''); setValueForm({ ...valueForm, propertyId: p.id, value: String(p.current_value ?? '') }) }}>
                עדכן שווי
              </button>
            </div>

            {savedMsg && <div className="alert warn" onClick={() => setSavedMsg('')}>✓ {savedMsg}</div>}

            {valueForm.propertyId === p.id && (
              <div className="value-form">
                <b>עדכון שווי הנכס</b>
                <label>נכון לתאריך<input type="date" value={valueForm.date}
                  onChange={(e) => setValueForm({ ...valueForm, date: e.target.value })} /></label>
                <label>שווי חדש ₪<input type="number" autoFocus value={valueForm.value}
                  onChange={(e) => setValueForm({ ...valueForm, value: e.target.value })}
                  onKeyDown={(e) => e.key === 'Enter' && saveValue()} style={{ width: 160 }} /></label>
                <button onClick={saveValue}>שמור</button>
                <button className="ghost" onClick={() => setValueForm({ ...valueForm, propertyId: 0 })}>ביטול</button>
              </div>
            )}

            <div className="grid grid-4" style={{ marginBottom: 14 }}>
              <div className="stat">
                <div className="label">שווי נוכחי</div>
                <div className="value">{fmtILS(p.current_value)}</div>
                {p.purchase_price != null && p.current_value != null && (
                  <div className={`sub ${p.current_value >= p.purchase_price ? 'pos' : 'neg'}`}>
                    {fmtILS(p.current_value - p.purchase_price)} מהרכישה
                  </div>
                )}
              </div>
              <div className="stat">
                <div className="label">שכ"ד חודשי</div>
                <div className="value">{fmtILS(p.monthly_rent)}</div>
              </div>
              <div className="stat">
                <div className="label">תשואה ברוטו שנתית</div>
                <div className="value">{p.gross_yield_pct != null ? `${p.gross_yield_pct}%` : '—'}</div>
              </div>
              <div className="stat">
                <div className="label">נטו מצטבר (הכנסות − הוצאות)</div>
                <div className={`value ${s && s.net >= 0 ? 'pos' : 'neg'}`}>{fmtILS(s?.net)}</div>
              </div>
            </div>

            {p.details && <Valuation d={p.details} purchase={p.purchase_price} current={p.current_value} />}

            {s && s.series.length > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={s.series}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => fmtILS(Number(v))} />
                  <Legend />
                  <Bar dataKey="income" name="שכ״ד שהתקבל" fill="#2ECC71" />
                  <Bar dataKey="expenses" name="הוצאות הנכס" fill="#E74C3C" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="muted">
                אין עדיין תנועות מסווגות לנכס. הגדר חוק קטגוריה "{p.income_category}" על שם השוכר בהעברת הבנק.
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

function Valuation({ d, purchase, current }: { d: PropertyDetails; purchase: number | null; current: number | null }) {
  const e = d.estimate
  return (
    <div className="valuation">
      <div className="grid grid-3">
        <div>
          <h3>פרטי הנכס</h3>
          <table><tbody>
            {d.address && <tr><td>כתובת</td><td>{d.address}</td></tr>}
            {d.gush && <tr><td>גוש / חלקה / תת-חלקה</td><td>{d.gush} / {d.helka} / {d.sub_parcel}</td></tr>}
            {d.rooms && <tr><td>חדרים · קומה</td><td>{d.rooms} · {d.floor}</td></tr>}
            {d.area_sqm && <tr><td>שטח רשום</td><td>{d.area_sqm} מ"ר{d.gross_area_sqm ? ` (ברוטו כ-${d.gross_area_sqm})` : ''}</td></tr>}
            {d.built_year && <tr><td>שנת בנייה</td><td>{d.built_year}</td></tr>}
            {d.extras && <tr><td>הצמדות</td><td>{d.extras.join(' · ')}</td></tr>}
          </tbody></table>
        </div>
        {d.appraisal && (
          <div>
            <h3>שמאות בנק ({d.appraisal.date})</h3>
            <table><tbody>
              <tr><td>שווי שוק</td><td><b>{fmtILS(d.appraisal.value)}</b></td></tr>
              {d.appraisal.ppsqm && <tr><td>למ"ר אקוויוולנטי</td><td>{fmtILS(d.appraisal.ppsqm)}</td></tr>}
              {d.appraisal.quick_sale && <tr><td>שווי למימוש מהיר</td><td>{fmtILS(d.appraisal.quick_sale)}</td></tr>}
              <tr><td>שמאי</td><td>{d.appraisal.appraiser}</td></tr>
            </tbody></table>
          </div>
        )}
        {e && (
          <div className="estimate">
            <h3>השווי בשימוש (שווי נקי ודשבורד)</h3>
            <div className="big">{fmtILS(current ?? e.value)}</div>
            {purchase != null && current != null && (
              <div className={current >= purchase ? 'pos' : 'neg'}>
                {fmtILS(current - purchase)} ({fmtNum(((current - purchase) / purchase) * 100, 1)}%) מאז הרכישה
              </div>
            )}
            <p style={{ marginBottom: 4 }}>
              הערכת שוק לפי עסקאות: <b>{fmtILS(e.value)}</b> <span className="muted">(טווח {fmtILS(e.low)} – {fmtILS(e.high)}, {e.date})</span>
            </p>
            <p className="muted">{e.method}</p>
          </div>
        )}
      </div>
      {d.market && d.market.length > 0 && (
        <div className="grid grid-2" style={{ marginTop: 12 }}>
          <div>
            <h3>מחיר חציוני למ"ר ביהוד (דירות 3.5–4 חד׳)</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={d.market}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} width={60} />
                <Tooltip formatter={(v, n) => (n === 'median_ppsqm' ? fmtILS(Number(v)) : v)} labelFormatter={(l) => `שנת ${l}`} />
                <Bar dataKey="median_ppsqm" name='חציון למ"ר' fill="#6C5CE7" />
              </BarChart>
            </ResponsiveContainer>
            <p className="muted">מספר העסקאות לשנה: {d.market.map((m) => `${m.year}: ${m.deals}`).join(' · ')}</p>
          </div>
          {d.comps && (
            <div>
              <h3>עסקאות באותו מתחם (גוש {d.gush} חלקה {d.helka})</h3>
              <table>
                <thead><tr><th>תאריך</th><th>תת-חלקה</th><th>שטח</th><th>חד׳</th><th>מחיר</th><th>למ"ר</th></tr></thead>
                <tbody>
                  {d.comps.map((c) => (
                    <tr key={c.date + c.sub_parcel} style={c.own ? { fontWeight: 700 } : undefined}>
                      <td>{c.date}</td><td>{c.sub_parcel}{c.own ? ' (שלכם)' : ''}</td><td>{c.area}</td><td>{c.rooms ?? '—'}</td>
                      <td>{fmtILS(c.amount)}</td><td>{fmtILS(c.ppsqm)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
      {d.source_url && <p className="muted">מקור העסקאות: רשות המסים דרך <a href={d.source_url} target="_blank" rel="noreferrer">over.org.il</a> (נתונים מדווחים, לא מעובדים). השטח בטבלה הוא שטח הנכס במאגר.</p>}
    </div>
  )
}
