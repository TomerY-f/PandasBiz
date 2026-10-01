import { useEffect, useRef, useState } from 'react'
import { apiGet, apiSend, fmtILS, fmtNum, fmtPct, memberQuery, withQuery } from '../api'
import { useMember } from '../components/MemberContext'

interface Defaults {
  avg_income: number
  avg_expenses: number
  net_worth_retirement: number
  car_value: number
  active_months: number
}
interface Inflation {
  current_period: string
  previous_period: string
  current_months_with_data: number
  previous_months_with_data: number
  groups: { group: string; previous: number; current: number }[]
}

type Values = Record<string, number>

const DEFAULTS: Values = {
  fi_income: 0, fi_expense: 0, fi_return: 5, fi_withdraw: 4,
  ag_before: 8500, ag_after: 6000, ag_rate: 3,
  car_buy: 36900, car_sell: 34000, car_km_total: 41220, car_km_year: 11206, car_kmpl: 12.7,
  car_fuel: 6.82, car_test: 1374, car_ins: 2000, car_service: 1960,
}

function Num({ label, k, v, set, step = 1, suffix }: { label: string; k: string; v: Values; set: (k: string, n: number) => void; step?: number; suffix?: string }) {
  return (
    <label>
      <span>{label}</span>
      <span className="row" style={{ gap: 4 }}>
        <input type="number" step={step} value={v[k] ?? ''} onChange={(e) => set(k, Number(e.target.value))} />
        {suffix && <span className="muted">{suffix}</span>}
      </span>
    </label>
  )
}

export default function Calculators() {
  const { member } = useMember()
  const [v, setV] = useState<Values>(DEFAULTS)
  const [defaults, setDefaults] = useState<Defaults | null>(null)
  const [infl, setInfl] = useState<Inflation | null>(null)
  const [inflEdit, setInflEdit] = useState<Record<string, { previous: number; current: number }>>({})
  const loaded = useRef(false)

  useEffect(() => {
    Promise.all([
      apiGet<Defaults>(withQuery('/sheets/calculator-defaults', memberQuery(member))),
      apiGet<{ value: Values | null }>('/settings/calculators'),
    ]).then(([d, saved]) => {
      setDefaults(d)
      setV({
        ...DEFAULTS,
        fi_income: Math.round(d.avg_income),
        fi_expense: Math.round(d.avg_expenses),
        ...(saved.value ?? {}),
      })
      loaded.current = true
    })
    apiGet<Inflation>(withQuery('/sheets/inflation', memberQuery(member))).then(setInfl)
    apiGet<{ value: Record<string, { previous: number; current: number }> | null }>('/settings/inflation').then(
      (r) => r.value && setInflEdit(r.value),
    )
  }, [member])

  const set = (k: string, n: number) => {
    const next = { ...v, [k]: n }
    setV(next)
    if (loaded.current) apiSend('PUT', '/settings/calculators', { value: next })
  }

  const resetFromData = () => {
    if (!defaults) return
    const next = { ...v, fi_income: Math.round(defaults.avg_income), fi_expense: Math.round(defaults.avg_expenses) }
    setV(next)
    apiSend('PUT', '/settings/calculators', { value: next })
  }

  // עד מתי — the Hasolidit formula: years = ln((expense/income)*(1/withdraw)*return/(saving/income) + 1) / ln(1+return)
  const income = v.fi_income || 0
  const expense = v.fi_expense || 0
  const saving = income - expense
  const r = (v.fi_return || 0) / 100
  const w = (v.fi_withdraw || 0) / 100
  const yearsToFi =
    income > 0 && saving > 0 && r > 0 && w > 0 ? Math.log(((expense / income) * (1 / w) * r) / (saving / income) + 1) / Math.log(1 + r) : null

  // חיסכון אגרסיבי
  const agRate = (v.ag_rate || 0) / 100
  const agBefore = agRate ? (v.ag_before * 12) / agRate : 0
  const agAfter = agRate ? (v.ag_after * 12) / agRate : 0

  // הרכב כמגרסה
  const carYears = v.car_km_year ? v.car_km_total / v.car_km_year : 0
  const carAnnual = carYears
    ? v.car_buy / carYears - v.car_sell / carYears + (v.car_km_year / (v.car_kmpl || 1)) * v.car_fuel + (v.car_test + v.car_ins + v.car_service)
    : 0

  // אינפלציה אישית
  const rows = (infl?.groups ?? []).map((g) => ({ ...g, ...(inflEdit[g.group] ?? {}) }))
  const totalCur = rows.reduce((s, g) => s + (g.current || 0), 0)
  const personal = rows.reduce((s, g) => {
    if (!g.previous || !totalCur) return s
    return s + ((g.current - g.previous) / g.previous) * (g.current / totalCur)
  }, 0)
  const setInflValue = (group: string, field: 'previous' | 'current', n: number) => {
    const base = rows.find((g) => g.group === group)!
    const next = { ...inflEdit, [group]: { previous: base.previous, current: base.current, [field]: n } }
    setInflEdit(next)
    apiSend('PUT', '/settings/inflation', { value: next })
  }

  return (
    <div>
      <h1>מחשבונים</h1>
      <p className="muted">הערכים נשמרים מקומית. הכנסות והוצאות מתמלאות מהממוצע בפועל ({defaults?.active_months ?? 0} חודשים עם נתונים).</p>
      <div className="grid grid-2">
        <div className="card calc">
          <div className="row spread"><h2>⏳ עד מתי! זמן עד לחופש</h2><button className="ghost small" onClick={resetFromData}>מלא מהנתונים</button></div>
          <Num label="מדי חודש אני מכניס/ה" k="fi_income" v={v} set={set} suffix="₪" />
          <Num label="מדי חודש אני מוציא/ה" k="fi_expense" v={v} set={set} suffix="₪" />
          <label><span>כך שבסך הכל אני חוסכ/ת</span><b>{fmtILS(saving)} ({fmtPct(income ? (saving / income) * 100 : null)})</b></label>
          <Num label="תשואה שנתית ממוצעת משוערת" k="fi_return" v={v} set={set} step={0.1} suffix="%" />
          <Num label="שיעור משיכה שנתי לאחר פרישה" k="fi_withdraw" v={v} set={set} step={0.1} suffix="%" />
          <div className="result">
            {yearsToFi == null ? 'כדי לחשב צריך שהחיסכון יהיה חיובי' : <>נותרו לי עוד <b>{fmtNum(yearsToFi, 1)}</b> שנים לעצמאות כלכלית!</>}
          </div>
          <p className="muted">לפי הנוסחה של הסולידית, מההתחלה (לא כולל החסכונות הקיימים — שווי נקי לפרישה כיום: {fmtILS(defaults?.net_worth_retirement)}).</p>
        </div>

        <div className="card calc">
          <h2>✂️ האפקט המדהים של חיסכון אגרסיבי</h2>
          <Num label="הוצאות חודשיות לפני ההתייעלות" k="ag_before" v={v} set={set} suffix="₪" />
          <Num label="הוצאות חודשיות לאחר ההתייעלות" k="ag_after" v={v} set={set} suffix="₪" />
          <Num label="שיעור משיכה מתוכנן מהתיק" k="ag_rate" v={v} set={set} step={0.1} suffix="%" />
          <table>
            <tbody>
              <tr><td>סכום לעצמאות כלכלית — לפני</td><td>{fmtILS(agBefore)}</td></tr>
              <tr><td>סכום לעצמאות כלכלית — אחרי</td><td>{fmtILS(agAfter)}</td></tr>
            </tbody>
          </table>
          <div className="result">ההפרש: צריך לחסוך <b>{fmtILS(agBefore - agAfter)}</b> פחות כדי להגיע לעצמאות כלכלית</div>
        </div>

        <div className="card calc">
          <h2>🚗 הרכב שלך כמגרסת מזומנים</h2>
          <Num label="קנינו את הרכב תמורת" k="car_buy" v={v} set={set} suffix="₪" />
          <Num label="נוכל למכור אותו היום תמורת" k="car_sell" v={v} set={set} suffix="₪" />
          <Num label='סה"כ ק"מ עד כה' k="car_km_total" v={v} set={set} />
          <Num label='ק"מ בשנה' k="car_km_year" v={v} set={set} />
          <Num label='צריכת דלק (ק"מ לליטר)' k="car_kmpl" v={v} set={set} step={0.1} />
          <Num label="מחיר ליטר דלק" k="car_fuel" v={v} set={set} step={0.01} suffix="₪" />
          <Num label="טסט שנתי" k="car_test" v={v} set={set} suffix="₪" />
          <Num label="ביטוח שנתי" k="car_ins" v={v} set={set} suffix="₪" />
          <Num label="טיפולים שנתיים" k="car_service" v={v} set={set} suffix="₪" />
          <div className="result">
            על בסיס {fmtNum(carYears, 1)} שנות בעלות, אחזקת הרכב עולה <b>{fmtILS(carAnnual)}</b> בשנה, או{' '}
            {fmtNum(v.car_km_year ? carAnnual / v.car_km_year : 0, 2)} ₪ לקילומטר.
          </div>
        </div>

        <div className="card calc">
          <h2>📈 מחשבון אינפלציה אישית</h2>
          <p className="muted">
            ממוצע חודשי לפי קבוצה: {infl?.previous_period} ({infl?.previous_months_with_data ?? 0} חודשים) מול {infl?.current_period} (
            {infl?.current_months_with_data ?? 0} חודשים). אפשר לתקן ידנית.
          </p>
          <table>
            <thead><tr><th>סעיף</th><th>קודם</th><th>נוכחי</th><th>משקל</th><th>שינוי</th></tr></thead>
            <tbody>
              {rows.map((g) => (
                <tr key={g.group}>
                  <td>{g.group}</td>
                  <td><input type="number" style={{ width: 90 }} value={Math.round(g.previous)} onChange={(e) => setInflValue(g.group, 'previous', Number(e.target.value))} /></td>
                  <td><input type="number" style={{ width: 90 }} value={Math.round(g.current)} onChange={(e) => setInflValue(g.group, 'current', Number(e.target.value))} /></td>
                  <td>{fmtPct(totalCur ? (g.current / totalCur) * 100 : null)}</td>
                  <td>{g.previous ? fmtPct(((g.current - g.previous) / g.previous) * 100) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="result">שיעור האינפלציה האישית: <b>{fmtPct(personal * 100, 2)}</b></div>
        </div>
      </div>
    </div>
  )
}
