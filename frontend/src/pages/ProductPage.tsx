import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { Bar, Cell, ComposedChart, Line, LineChart, CartesianGrid, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from 'recharts'
import { CHART_COLORS, apiGet, apiSend, fmtILS, fmtNum, memberQuery, withQuery } from '../api'
import DropZone from '../components/DropZone'
import { useMember } from '../components/MemberContext'

interface Tx {
  id: number
  date: string
  description: string
  amount: number
  category: string
  sector: string
  account: string
  account_id: number
  month_year: string
  billing_cycle: string
  balance: number | null
  category_locked: boolean
}
interface HoldingRow {
  id: number
  account: string
  symbol: string
  name: string
  quantity: number
  last_price: number | null
  currency: string
  cost_basis: number
  value_native: number | null
  value_ils: number
  gain_native: number | null
  asset_class: string
}
interface LoanRow {
  id: number
  name: string
  original_amount: number
  balance: number
  rate_text: string
  monthly_payment: number
  payments_left: string
  end_date: string | null
}
interface Policy {
  id: number
  member: string | null
  domain: string
  main_branch: string
  sub_branch: string
  product_type: string
  company: string
  period: string
  details: string
  premium: number
  premium_type: string
  monthly_premium: number
  manual?: boolean
}
interface PensionLine {
  account_id: number
  name: string
  provider: string
  product_type: string
  policy: string
  balance: number
  as_of: string | null
  fee_deposit_pct: number
  fee_accrual_pct: number
  employer: string
  status: string
  salary: number
  projected_pension: number
  last_deposit: string
}
interface PensionMember {
  member_id: number | null
  member: string
  total: number
  report: {
    report_date: string | null
    total_savings: number
    ytd_return_pct: number | null
    monthly_premium: number
    deposits?: Record<string, number>
    pension?: { without_deposits?: number; with_deposits?: number }
    coverages?: Record<string, number>
    mix?: { stocks_exposure?: number; abroad_exposure?: number }
  } | null
  products: PensionLine[]
}
interface Doc { id: number; filename: string; size: number; parsed: boolean; summary: string; member: string | null; uploaded_at: string }
interface AccountRow { id: number; name: string; owner_id: number | null; owner: string | null; external_ref: string; nw_bucket: string; value_ils: number; logo?: string }
interface ProductData {
  product: string
  label: string
  usd_ils: number
  total_ils: number
  accounts: AccountRow[]
  transactions?: Tx[]
  holdings?: HoldingRow[]
  loans?: LoanRow[]
  monthly_payment_total?: number
  policies?: Policy[]
  pension_members?: PensionMember[]
  monthly_premium_total?: number
  snapshots: { id: number; account_id: number; date: string; value: number }[]
  documents: Doc[]
}

interface Props {
  product: string
  title: string
  hint: string
  children?: ReactNode
  /** false when the page is a tab inside a group page that has its own upload zone */
  upload?: boolean
  reloadKey?: number
}

export default function ProductPage({ product, title, hint, children, upload = true, reloadKey = 0 }: Props) {
  const { member, members, meta } = useMember()
  const [data, setData] = useState<ProductData | null>(null)
  const [lines, setLines] = useState<string[]>([])
  const [error, setError] = useState('')

  const load = useCallback(() => {
    apiGet<ProductData>(withQuery(`/products/${product}`, memberQuery(member)))
      .then(setData)
      .catch((e) => setError(String(e)))
  }, [product, member, reloadKey])

  useEffect(load, [load])
  useEffect(() => {
    window.addEventListener('pandasbiz:refresh', load)
    return () => window.removeEventListener('pandasbiz:refresh', load)
  }, [load])
  useEffect(() => {
    apiGet<{ lines: { name: string }[] }>('/lines').then((r) => setLines(r.lines.map((l) => l.name)))
  }, [])

  const setOwner = async (accountId: number, value: string) => {
    await apiSend('PATCH', `/family-accounts/${accountId}`, value ? { owner_id: Number(value) } : { clear_owner: true })
    load()
  }

  const deleteDoc = async (id: number) => {
    if (!confirm('למחוק את הקובץ השמור? (נתונים שכבר נקלטו ממנו נשארים)')) return
    await apiSend('DELETE', `/documents/${id}`)
    load()
  }

  const refreshPrices = async () => {
    try {
      await apiSend('POST', '/market/refresh')
    } catch (e) {
      alert(String(e))
    }
    load()
  }

  if (error) return <div className="alert">{error}</div>

  return (
    <div>
      <div className="row spread">
        {upload ? <h1>{title}</h1> : <h2>{title}</h2>}
        {data && data.accounts.length > 0 && (
          <div className="card stat" style={{ margin: 0, padding: '10px 16px' }}>
            <div className="label">סה"כ</div>
            <div className={`value ${data.total_ils < 0 && product !== 'credit_card' ? 'neg' : ''}`} style={{ fontSize: 20 }}>
              {fmtILS(product === 'credit_card' ? -data.total_ils || 0 : data.total_ils)}
            </div>
          </div>
        )}
      </div>

      {upload && <DropZone product={product} hint={hint} onDone={load} />}

      {children}

      {data && data.accounts.length > 0 && product !== 'pension' && (
        <div className="card">
          <h2>חשבונות</h2>
          <table>
            <thead><tr><th>חשבון</th><th>מזהה</th><th>בעלים</th><th>סיווג שווי נקי</th>{product === 'credit_card' && <th>חיוב אחרון</th>}<th>שווי ₪</th></tr></thead>
            <tbody>
              {data.accounts.map((a) => (
                <tr key={a.id}>
                  <td>{a.logo && <img src={a.logo} alt="בית ההשקעות" className="broker-logo" />}<b>{a.name}</b></td>
                  <td className="muted">{a.external_ref}</td>
                  <td>
                    <select value={a.owner_id ?? ''} onChange={(e) => setOwner(a.id, e.target.value)}>
                      <option value="">משותף</option>
                      {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                    </select>
                  </td>
                  <td>
                    <select
                      value={a.nw_bucket}
                      onChange={async (e) => {
                        await apiSend('PATCH', `/family-accounts/${a.id}`, { nw_bucket: e.target.value })
                        load()
                      }}
                    >
                      {meta?.buckets.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
                    </select>
                  </td>
                  {product === 'credit_card' && (() => {
                    const last = data.snapshots.filter((x) => x.account_id === a.id).slice(-1)[0]
                    return <td>{last ? `${fmtILS(-last.value)} · ${last.date}` : '—'}</td>
                  })()}
                  <td className={a.value_ils < 0 && product !== 'credit_card' ? 'neg' : ''}>{fmtILS(product === 'credit_card' ? -a.value_ils || 0 : a.value_ils)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data?.transactions && <Transactions txs={data.transactions} lines={lines} product={product} onChange={load} />}
      {data?.holdings && data.holdings.length > 0 && (
        <Holdings rows={data.holdings} usdIls={data.usd_ils} onRefresh={product === 'fx' ? undefined : refreshPrices} onChange={load} />
      )}
      {data?.loans && data.loans.length > 0 && <Loans rows={data.loans} total={data.monthly_payment_total ?? 0} />}
      {data?.pension_members && data.pension_members.map((m) => <PensionMemberCard key={m.member} m={m} />)}
      {data?.policies && <Policies rows={data.policies} total={data.monthly_premium_total ?? 0} onChange={load} />}
      {data && data.snapshots.length > 1 && product !== 'pension' && <SnapshotChart data={data} />}

      {data && data.documents.length > 0 && (
        <div className="card">
          <h2>קבצים שהועלו</h2>
          <table>
            <thead><tr><th>קובץ</th><th>סטטוס</th><th>בן משפחה</th><th>הועלה</th><th></th></tr></thead>
            <tbody>
              {data.documents.map((d) => (
                <tr key={d.id}>
                  <td><a href={`/api/documents/${d.id}/file`} target="_blank" rel="noreferrer">{d.filename}</a></td>
                  <td>{d.parsed ? <span className="badge green">נקלט</span> : <span className="badge">מסמך</span>} <span className="muted">{d.summary}</span></td>
                  <td>{d.member ?? '—'}</td>
                  <td className="muted">{d.uploaded_at.slice(0, 10)}</td>
                  <td><button className="danger small" onClick={() => deleteDoc(d.id)}>מחק</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ---------- sections ----------

const AVG_KEY = 'ממוצע מתחילת השנה'

// long sheet-line names (e.g. "אוכל בחוץ (כולל מסעדות...)") are cut at the bracket so labels fit the card
const short = (n: string) => {
  const base = n.split(' (')[0]
  return base.length > 20 ? `${base.slice(0, 19)}…` : base
}

// pie slice label: line name, amount and share, sized to stay readable
const signedILS = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${fmtILS(Math.abs(v))}`

function PieLabel(props: {
  x?: number; y?: number; textAnchor?: 'inherit' | 'middle' | 'start' | 'end'; name?: string; value?: number; percent?: number
  fill?: string; payload?: { signed?: number; showSign?: boolean }
}) {
  const { x = 0, y = 0, textAnchor = 'middle', name, value, percent, fill, payload } = props
  if ((percent ?? 0) < 0.03) return null  // tiny slices: the label would overlap its neighbours; hover shows it
  // on bank pages, money in is "+" in green and money out is "−" in red, like the table below
  const signed = payload?.showSign ? payload.signed ?? 0 : null
  const amount = signed == null ? fmtILS(Number(value)) : signedILS(signed)
  const color = signed == null ? fill : signed >= 0 ? '#00a37a' : '#d63031'
  return (
    <text x={x} y={y} textAnchor={textAnchor} dominantBaseline="central" fontSize={14} fontWeight={600} fill={color}>
      {`${short(name ?? '')}: ${amount} (${Math.round((percent ?? 0) * 100)}%)`}
    </text>
  )
}

function Transactions({ txs, lines, product, onChange }: { txs: Tx[]; lines: string[]; product: string; onChange: () => void }) {
  // period: calendar month (1st–1st) or billing cycle (10th of the month – 9th of the next)
  const [periodType, setPeriodType] = useState<'month' | 'cycle'>(product === 'credit_card' ? 'cycle' : 'month')
  const periodOf = (t: Tx) => (periodType === 'cycle' ? t.billing_cycle : t.month_year)
  const months = useMemo(
    () => Array.from(new Set(txs.map((t) => (periodType === 'cycle' ? t.billing_cycle : t.month_year)))).sort().reverse(),
    [txs, periodType],
  )
  const accounts = useMemo(() => Array.from(new Set(txs.map((t) => t.account))), [txs])
  const [month, setMonth] = useState('')
  // credit cards open on the latest billing cycle only (the full history is heavy to render)
  const [periodInit, setPeriodInit] = useState(false)
  useEffect(() => {
    if (!periodInit && product === 'credit_card' && months.length) {
      setMonth(months[0])
      setPeriodInit(true)
    }
  }, [months, periodInit, product])
  // charges are shown as positive amounts and refunds as negative on card pages
  const sign = product === 'credit_card' ? -1 : 1
  const [saved, setSaved] = useState<number | null>(null)
  const [account, setAccount] = useState('')
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [minAmount, setMinAmount] = useState('')
  const [maxAmount, setMaxAmount] = useState('')
  const [sort, setSort] = useState<{ key: 'date' | 'amount' | 'description'; dir: 1 | -1 }>({ key: 'date', dir: -1 })

  const cycleLabel = (c: string) => {
    const [a, b] = c.split(' → ')
    if (!b) return c
    const [y1, m1] = a.split('-')
    const [y2, m2] = b.split('-')
    return `10.${m1}.${y1.slice(2)} – 9.${m2}.${y2.slice(2)}`
  }

  const filtered = txs
    .filter(
      (t) =>
        (!month || periodOf(t) === month) &&
        (!account || t.account === account) &&
        (!category || t.category === category) &&
        (!search || t.description.includes(search)) &&
        (!dateFrom || t.date >= dateFrom) &&
        (!dateTo || t.date <= dateTo) &&
        (!minAmount || Math.abs(t.amount) >= Number(minAmount)) &&
        (!maxAmount || Math.abs(t.amount) <= Number(maxAmount)),
    )
    .sort((a, b) => {
      const va = sort.key === 'amount' ? Math.abs(a.amount) : a[sort.key]
      const vb = sort.key === 'amount' ? Math.abs(b.amount) : b[sort.key]
      return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir
    })
  const sortBy = (key: 'date' | 'amount' | 'description') =>
    setSort((cur) => ({ key, dir: cur.key === key ? (cur.dir === 1 ? -1 : 1) : key === 'description' ? 1 : -1 }))
  const arrow = (key: string) => (sort.key === key ? (sort.dir === 1 ? ' ▲' : ' ▼') : '')
  const clearFilters = () => {
    setMonth(''); setAccount(''); setSearch(''); setCategory(''); setDateFrom(''); setDateTo(''); setMinAmount(''); setMaxAmount('')
  }
  const byCategory = useMemo(() => {
    const m = new Map<string, number>()
    filtered.forEach((t) => {
      if (t.category === 'העברה פנימית') return
      m.set(t.category, (m.get(t.category) ?? 0) + (product === 'credit_card' ? -t.amount : t.amount))
    })
    // slice size is the absolute amount; `signed` keeps the direction (+ income / − expense) for labels
    const items = Array.from(m.entries())
      .map(([name, v]) => ({ name, value: Math.round(Math.abs(v)), signed: Math.round(v), showSign: product !== 'credit_card' }))
      .sort((a, b) => b.value - a.value)
    const top = items.slice(0, 8)
    const rest = items.slice(8)
    for (const dir of [1, -1]) {
      const group = rest.filter((x) => (product === 'credit_card' ? dir === 1 : Math.sign(x.signed || 1) === dir))
      if (!group.length) continue
      const signed = group.reduce((acc, x) => acc + x.signed, 0)
      const label = product === 'credit_card' ? 'אחר' : dir === 1 ? 'אחר (הכנסות)' : 'אחר (הוצאות)'
      top.push({ name: label, value: Math.abs(signed), signed, showSign: product !== 'credit_card' })
    }
    return top
  }, [filtered, product])
  const pieIncome = byCategory.filter((x) => x.signed > 0).reduce((a, x) => a + x.signed, 0)
  const pieExpense = byCategory.filter((x) => x.signed < 0).reduce((a, x) => a + x.signed, 0)
  const total = filtered.reduce((s, t) => s + t.amount, 0) * sign
  // which slice of time the charts and the table show, in words
  const scopeText = [
    month ? (periodType === 'cycle' ? `מחזור חיוב ${cycleLabel(month)}` : `חודש ${month}`) : 'כל התקופה',
    dateFrom || dateTo ? `תאריכים ${dateFrom || '…'} – ${dateTo || '…'}` : '',
    account ? `חשבון ${account}` : '',
    category ? `שורה: ${category}` : '',
    minAmount || maxAmount ? `סכום ${minAmount || 0} – ${maxAmount || '∞'}` : '',
  ].filter(Boolean).join(' · ') + ` · ${filtered.length} תנועות`

  const setCat = async (t: Tx, value: string) => {
    t.category = value === '__auto' ? t.category : value  // show the choice at once; the reload confirms it
    t.category_locked = value !== '__auto'
    setSaved(t.id)
    await apiSend('PATCH', `/transactions/${t.id}`, value === '__auto' ? { category: '', unlock: true } : { category: value })
    onChange()
    setTimeout(() => setSaved((cur) => (cur === t.id ? null : cur)), 2500)
  }

  const balances = product === 'bank_current'
    ? [...txs].filter((t) => t.balance != null).reverse().map((t) => ({ date: t.date, balance: t.balance }))
    : []

  const monthly = useMemo(() => {
    if (product !== 'credit_card') return []
    const m = new Map<string, Record<string, number | string>>()
    txs.forEach((t) => {
      const row = m.get(t.month_year) ?? { month: t.month_year }
      row[t.account] = Math.round(((row[t.account] as number) ?? 0) - t.amount)
      m.set(t.month_year, row)
    })
    const rows = Array.from(m.values()).sort((a, b) => String(a.month).localeCompare(String(b.month)))
    // year-to-date average: for each month, the mean monthly charge from January of that year up to it
    let year = '', sum = 0, count = 0
    return rows.map((r) => {
      const y = String(r.month).slice(0, 4)
      if (y !== year) { year = y; sum = 0; count = 0 }
      sum += accounts.reduce((acc, a) => acc + ((r[a] as number) ?? 0), 0)
      count += 1
      return { ...r, [AVG_KEY]: Math.round(sum / count) }
    })
  }, [txs, product, accounts])

  return (
    <>
      <div className="grid grid-2">
        {byCategory.length > 0 && (
          <div className="card">
            <h2 style={{ marginBottom: 2 }}>התפלגות לפי שורת תקציב</h2>
            <p className="muted" style={{ margin: '0 0 6px' }}>{scopeText} · לפי הסינון בטבלת התנועות</p>
            {product !== 'credit_card' && (
              <p style={{ margin: '0 0 6px', fontSize: 13 }}>
                <span className="pos">הכנסות {signedILS(pieIncome)}</span> · <span className="neg">הוצאות {signedILS(pieExpense)}</span>
                <span className="muted"> (גודל הפרוסה לפי הסכום, הסימן לפי הכיוון; ללא העברות פנימיות)</span>
              </p>
            )}
            <ResponsiveContainer width="100%" height={400}>
              <PieChart>
                <Pie data={byCategory} dataKey="value" nameKey="name" innerRadius={55} outerRadius={115} paddingAngle={2}
                  label={PieLabel} labelLine>
                  {byCategory.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v, _n, item) => {
                  const p = (item as { payload?: { signed?: number; showSign?: boolean } }).payload
                  return p?.showSign ? signedILS(p.signed ?? 0) : fmtILS(Number(v))
                }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
        {monthly.length > 0 && (
          <div className="card">
            <h2>חיובים לפי חודש וכרטיס</h2>
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={monthly}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} width={60} />
                <Tooltip formatter={(v) => fmtILS(Number(v))} />
                <Legend />
                {accounts.map((a, i) => <Bar key={a} dataKey={a} stackId="c" fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                <Line type="monotone" dataKey={AVG_KEY} stroke="#d63031" strokeWidth={2.5} dot={{ r: 3 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
        {balances.length > 1 && (
          <div className="card">
            <h2>יתרה בעו"ש</h2>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={balances}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} width={70} />
                <Tooltip formatter={(v) => fmtILS(Number(v))} />
                <Line type="monotone" dataKey="balance" name="יתרה" stroke="#6C5CE7" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
      <div className="card">
        <div className="row spread">
          <h2>תנועות ({filtered.length})</h2>
          <span className="muted">{product === 'credit_card' ? 'סה"כ חיובים' : 'סה"כ'}: <b className={product === 'credit_card' ? '' : total < 0 ? 'neg' : 'pos'}>{fmtILS(total)}</b></span>
        </div>
        <div className="filters">
          <label>חיפוש<input placeholder="תיאור" value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 140 }} /></label>
          <label>תקופה
            <span className="row" style={{ gap: 4 }}>
              <select value={periodType} onChange={(e) => { setPeriodType(e.target.value as 'month' | 'cycle'); setMonth('') }}>
                <option value="month">חודש (1 עד 1)</option>
                <option value="cycle">מחזור חיוב (10 עד 10)</option>
              </select>
              <select value={month} onChange={(e) => setMonth(e.target.value)}>
                <option value="">הכל</option>
                {months.map((m) => <option key={m} value={m}>{periodType === 'cycle' ? cycleLabel(m) : m}</option>)}
              </select>
            </span>
          </label>
          <label>מתאריך<input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label>
          <label>עד תאריך<input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label>
          <label>סכום מ-<input type="number" min={0} value={minAmount} onChange={(e) => setMinAmount(e.target.value)} style={{ width: 90 }} /></label>
          <label>עד<input type="number" min={0} value={maxAmount} onChange={(e) => setMaxAmount(e.target.value)} style={{ width: 90 }} /></label>
          {accounts.length > 1 && (
            <label>חשבון
              <select value={account} onChange={(e) => setAccount(e.target.value)}>
                <option value="">כל החשבונות</option>
                {accounts.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </label>
          )}
          <label>שורה בגיליון
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">כל השורות</option>
              {Array.from(new Set(txs.map((t) => t.category))).sort().map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <button className="ghost small" onClick={clearFilters}>נקה סינון</button>
        </div>
        <div style={{ maxHeight: 520, overflowY: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th className="sortable" onClick={() => sortBy('date')}>תאריך{arrow('date')}</th>
                <th className="sortable" onClick={() => sortBy('description')}>תיאור{arrow('description')}</th>
                {accounts.length > 1 && <th>חשבון</th>}<th>ענף</th>
                <th className="sortable" onClick={() => sortBy('amount')}>סכום{arrow('amount')}</th>
                <th>שורה בגיליון</th>{product === 'bank_current' && <th>יתרה</th>}
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 600).map((t) => (
                <tr key={t.id}>
                  <td>{t.date}</td>
                  <td>{t.description}</td>
                  {accounts.length > 1 && <td className="muted">{t.account}</td>}
                  <td className="muted">{t.sector}</td>
                  <td className={product === 'credit_card' ? (t.amount > 0 ? 'pos' : '') : t.amount < 0 ? 'neg' : 'pos'}>{fmtNum(t.amount * sign)}</td>
                  <td>
                    <select value={t.category} onChange={(e) => setCat(t, e.target.value)} title={t.category_locked ? 'סווג ידנית' : 'סווג אוטומטית'}>
                      {!lines.includes(t.category) && <option value={t.category}>{t.category}</option>}
                      {lines.map((l) => <option key={l} value={l}>{l}</option>)}
                      {t.category_locked && <option value="__auto">↺ חזרה לסיווג אוטומטי</option>}
                    </select>
                    {saved === t.id ? <span className="badge green" style={{ marginRight: 4 }}>נשמר ✓</span>
                      : t.category_locked && <span className="badge" style={{ marginRight: 4 }}>ידני</span>}
                  </td>
                  {product === 'bank_current' && <td className="muted">{t.balance == null ? '' : fmtNum(t.balance)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length > 600 && <p className="muted">מוצגות 600 הראשונות — צמצמו בעזרת המסננים.</p>}
        </div>
      </div>
    </>
  )
}

const CLASS_LABELS: Record<string, string> = { cash: 'מזומן', deposits: 'קרן כספית / פיקדון', bonds: 'אג"ח', stocks: 'מניות', metals: 'מתכות' }

function Holdings({ rows, usdIls, onRefresh, onChange }: { rows: HoldingRow[]; usdIls: number; onRefresh?: () => void; onChange: () => void }) {
  const total = rows.reduce((s, h) => s + h.value_ils, 0)
  const setClass = async (id: number, value: string) => {
    await apiSend('PATCH', `/holdings/${id}/class`, { asset_class: value })
    onChange()
  }
  const pie = rows.filter((h) => h.value_ils > 0).map((h) => ({ name: h.symbol, value: Math.round(h.value_ils) }))
  return (
    <div className="card">
      <div className="row spread">
        <h2>אחזקות</h2>
        <div className="row">
          <span className="muted">שער דולר: {fmtNum(usdIls, 4)}</span>
          {onRefresh && <button className="ghost small" onClick={onRefresh}>עדכן שערים</button>}
        </div>
      </div>
      <div className="grid grid-2" style={{ gridTemplateColumns: '2fr 1fr' }}>
        <table>
          <thead><tr><th>נייר</th><th>כמות</th><th>מחיר</th><th>שווי</th><th>שווי ₪</th><th>רווח/הפסד</th><th>סוג נכס</th></tr></thead>
          <tbody>
            {rows.map((h) => (
              <tr key={h.id}>
                <td><b>{h.symbol}</b> <span className="muted">{h.name !== h.symbol ? h.name : ''}</span></td>
                <td>{fmtNum(h.quantity, 2)}</td>
                <td>{fmtNum(h.last_price, 4)} {h.currency === 'USD' ? '$' : '₪'}</td>
                <td>{fmtNum(h.value_native)}</td>
                <td>{fmtILS(h.value_ils)}</td>
                <td className={(h.gain_native ?? 0) >= 0 ? 'pos' : 'neg'}>{h.gain_native == null ? '—' : fmtNum(h.gain_native)}</td>
                <td>
                  <select value={h.asset_class} onChange={(e) => setClass(h.id, e.target.value)}>
                    <option value="">לפי החשבון</option>
                    {Object.entries(CLASS_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                </td>
              </tr>
            ))}
            <tr className="total"><td><b>סה"כ</b></td><td /><td /><td /><td><b>{fmtILS(total)}</b></td><td /><td /></tr>
          </tbody>
        </table>
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie data={pie} dataKey="value" nameKey="name" outerRadius={85}>
              {pie.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={(v) => fmtILS(Number(v))} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function Loans({ rows, total }: { rows: LoanRow[]; total: number }) {
  const balance = rows.reduce((s, l) => s + l.balance, 0)
  return (
    <div className="card">
      <h2>מסלולים / הלוואות</h2>
      <div className="kpi-grid">
        <div className="stat"><div className="label">יתרת חוב</div><div className="value neg">{fmtILS(balance)}</div></div>
        <div className="stat"><div className="label">החזר חודשי</div><div className="value">{fmtILS(total)}</div></div>
      </div>
      <table>
        <thead><tr><th>שם</th><th>סכום מקורי</th><th>יתרת חוב</th><th>% מהחוב</th><th>ריבית</th><th>תשלום חודשי</th><th>תשלומים</th><th>פירעון סופי</th></tr></thead>
        <tbody>
          {rows.map((l) => (
            <tr key={l.id}>
              <td>{l.name}</td>
              <td>{fmtILS(l.original_amount)}</td>
              <td className="neg">{fmtILS(l.balance)}</td>
              <td>{balance ? `${Math.round((l.balance / balance) * 100)}%` : ''}</td>
              <td>{l.rate_text}</td>
              <td>{fmtILS(l.monthly_payment, 2)}</td>
              <td>{l.payments_left}</td>
              <td>{l.end_date ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

type PolicyKey = 'member' | 'main_branch' | 'sub_branch' | 'company' | 'period' | 'premium' | 'monthly_premium'
const POLICY_COLS: { key: PolicyKey; label: string; num?: boolean }[] = [
  { key: 'member', label: 'מבוטח' },
  { key: 'main_branch', label: 'ענף' },
  { key: 'sub_branch', label: 'משני' },
  { key: 'company', label: 'חברה' },
  { key: 'period', label: 'תקופה' },
  { key: 'premium', label: 'פרמיה', num: true },
  { key: 'monthly_premium', label: 'לחודש', num: true },
]
const emptyPolicy = { member_id: '', main_branch: '', sub_branch: '', company: '', period: '', premium: '', premium_type: 'חודשית' }

function Policies({ rows, total, onChange }: { rows: Policy[]; total: number; onChange: () => void }) {
  const { members } = useMember()
  const [sort, setSort] = useState<{ key: PolicyKey; dir: 1 | -1 }>({ key: 'monthly_premium', dir: -1 })
  const [filters, setFilters] = useState<Partial<Record<PolicyKey, string>>>({})
  const [form, setForm] = useState(emptyPolicy)
  const [showForm, setShowForm] = useState(false)
  const [hideZero, setHideZero] = useState(false)

  const val = (p: Policy, k: PolicyKey) => (k === 'member' ? p.member ?? 'לא משויך' : p[k])
  const options = (k: PolicyKey) => Array.from(new Set(rows.map((p) => String(val(p, k))))).sort()
  const shown = rows
    .filter((p) => !hideZero || p.premium > 0)
    .filter((p) => POLICY_COLS.every((c) => !filters[c.key] || String(val(p, c.key)) === filters[c.key]))
    .sort((x, y) => {
      const a = val(x, sort.key), b = val(y, sort.key)
      return (a < b ? -1 : a > b ? 1 : 0) * sort.dir
    })
  const shownTotal = shown.reduce((s, p) => s + p.monthly_premium, 0)
  const byBranch = new Map<string, number>()
  shown.forEach((p) => byBranch.set(p.main_branch, (byBranch.get(p.main_branch) ?? 0) + p.monthly_premium))

  const add = async () => {
    if (!form.main_branch) return
    await apiSend('POST', '/insurance-policies', {
      ...form,
      member_id: form.member_id ? Number(form.member_id) : null,
      premium: Number(form.premium) || 0,
    })
    setForm(emptyPolicy)
    setShowForm(false)
    onChange()
  }
  const remove = async (id: number) => {
    await apiSend('DELETE', `/insurance-policies/${id}`)
    onChange()
  }

  return (
    <div className="card">
      <div className="row spread">
        <h2>פוליסות ({shown.length})</h2>
        <div className="row">
          <span>פרמיה חודשית: <b>{fmtILS(shownTotal, 2)}</b> · שנתית: <b>{fmtILS(shownTotal * 12)}</b></span>
          {shown.length !== rows.length && <span className="muted">(מתוך {fmtILS(total, 0)} בסה"כ)</span>}
          <button className="small" onClick={() => setShowForm(!showForm)}>{showForm ? 'ביטול' : '+ הוספת ביטוח ידנית'}</button>
        </div>
      </div>

      {showForm && (
        <div className="filters" style={{ background: 'var(--accent-soft)', padding: 10, borderRadius: 10 }}>
          <label>מבוטח
            <select value={form.member_id} onChange={(e) => setForm({ ...form, member_id: e.target.value })}>
              <option value="">משותף</option>
              {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </label>
          <label>ענף<input placeholder="למשל: ביטוח בריאות" value={form.main_branch} onChange={(e) => setForm({ ...form, main_branch: e.target.value })} /></label>
          <label>משני<input value={form.sub_branch} onChange={(e) => setForm({ ...form, sub_branch: e.target.value })} /></label>
          <label>חברה<input value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} /></label>
          <label>תקופה<input placeholder="01/01/2026 - 31/12/2026" value={form.period} onChange={(e) => setForm({ ...form, period: e.target.value })} /></label>
          <label>פרמיה<input type="number" value={form.premium} onChange={(e) => setForm({ ...form, premium: e.target.value })} style={{ width: 100 }} /></label>
          <label>סוג פרמיה
            <select value={form.premium_type} onChange={(e) => setForm({ ...form, premium_type: e.target.value })}>
              <option value="חודשית">חודשית</option>
              <option value="שנתית">שנתית</option>
            </select>
          </label>
          <button onClick={add}>שמירה</button>
        </div>
      )}

      <div className="row" style={{ margin: '8px 0' }}>
        {Array.from(byBranch.entries()).map(([k, v]) => (
          <span key={k} className={`chip ${filters.main_branch === k ? '' : 'off'}`}
            onClick={() => setFilters({ ...filters, main_branch: filters.main_branch === k ? '' : k })}>
            {k}: {fmtILS(v, 0)}/חודש
          </span>
        ))}
        <label className="muted"><input type="checkbox" checked={hideZero} onChange={(e) => setHideZero(e.target.checked)} /> הסתר כתבי שירות ללא פרמיה</label>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {POLICY_COLS.map((c) => (
                <th key={c.key} className="sortable" onClick={() => setSort({ key: c.key, dir: sort.key === c.key ? (sort.dir === 1 ? -1 : 1) : c.num ? -1 : 1 })}>
                  {c.label}{sort.key === c.key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
                </th>
              ))}
              <th />
            </tr>
            <tr className="filter-row">
              {POLICY_COLS.map((c) => (
                <th key={c.key}>
                  {!c.num && (
                    <select value={filters[c.key] ?? ''} onChange={(e) => setFilters({ ...filters, [c.key]: e.target.value })}>
                      <option value="">הכל</option>
                      {options(c.key).map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  )}
                </th>
              ))}
              <th><button className="ghost small" onClick={() => setFilters({})}>נקה</button></th>
            </tr>
          </thead>
          <tbody>
            {shown.map((p) => (
              <tr key={p.id}>
                <td>{p.member ?? <span className="muted">לא משויך</span>}</td>
                <td>{p.main_branch}</td>
                <td>{p.sub_branch} <span className="muted">{p.product_type !== 'פוליסת ביטוח' ? p.product_type : ''}</span></td>
                <td>{p.company}</td>
                <td className="muted">{p.period}</td>
                <td>{fmtILS(p.premium, 2)} <span className="muted">{p.premium_type}</span></td>
                <td>{fmtILS(p.monthly_premium, 2)}</td>
                <td>{p.manual && <button className="danger small" onClick={() => remove(p.id)}>מחק</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.some((p) => !p.member) && (
        <p className="muted">כדי לשייך פוליסות לבן משפחה, הזינו את מספר תעודת הזהות שלו בעמוד "הגדרות" (נשמר רק במחשב שלכם).</p>
      )}
    </div>
  )
}

const PENSION_TYPE: Record<string, string> = { pension: 'פנסיה', study_fund: 'השתלמות', gemel: 'גמל' }

function PensionMemberCard({ m }: { m: PensionMember }) {
  const r = m.report
  const byType = new Map<string, number>()
  m.products.forEach((p) => byType.set(PENSION_TYPE[p.product_type] ?? p.product_type, (byType.get(PENSION_TYPE[p.product_type] ?? p.product_type) ?? 0) + p.balance))
  return (
    <div className="card">
      <div className="row spread">
        <h2>{m.member}</h2>
        <span className="muted">{r?.report_date ? `דוח מסלקה מיום ${r.report_date}` : ''}</span>
      </div>
      <div className="kpi-grid">
        <div className="stat"><div className="label">סך החיסכון שנצבר</div><div className="value">{fmtILS(m.total)}</div>
          <div className="sub">{Array.from(byType.entries()).map(([k, v]) => `${k} ${fmtILS(v)}`).join(' · ')}</div></div>
        {r?.ytd_return_pct != null && <div className="stat"><div className="label">תשואה מתחילת השנה</div><div className="value pos">{r.ytd_return_pct}%</div></div>}
        {r?.deposits?.total != null && <div className="stat"><div className="label">הפקדות חודשיות</div><div className="value">{fmtILS(r.deposits.total)}</div>
          <div className="sub">פנסיה {fmtILS(r.deposits.pension)} · השתלמות {fmtILS(r.deposits.study_fund)}</div></div>}
        {r?.pension?.with_deposits != null && <div className="stat"><div className="label">קצבה צפויה בפרישה</div><div className="value">{fmtILS(r.pension.with_deposits)}</div>
          <div className="sub">{fmtILS(r.pension.without_deposits)} בלי הפקדות נוספות</div></div>}
        {r?.coverages && <div className="stat"><div className="label">כיסויים</div>
          <div className="sub">
            {r.coverages.death ? <>מוות: {fmtILS(r.coverages.death)}<br /></> : null}
            {r.coverages.disability ? <>אובדן כושר: {fmtILS(r.coverages.disability)}/חודש<br /></> : null}
            {r.coverages.mortgage_life ? <>ביטוח חיים למשכנתא: {fmtILS(r.coverages.mortgage_life)}</> : null}
          </div></div>}
      </div>
      <div className="table-scroll">
        <table>
          <thead><tr><th>מוצר</th><th>יצרן</th><th>מס' חשבון</th><th>צבירה</th><th>ד"נ הפקדה</th><th>ד"נ צבירה</th><th>מעסיק</th><th>סטטוס</th><th>הפקדה אחרונה</th><th>קצבה חזויה</th></tr></thead>
          <tbody>
            {m.products.map((p) => (
              <tr key={p.account_id}>
                <td><b>{p.name}</b></td>
                <td>{p.provider}</td>
                <td className="muted">{p.policy}</td>
                <td>{fmtILS(p.balance)}</td>
                <td>{p.fee_deposit_pct ? `${p.fee_deposit_pct}%` : '—'}</td>
                <td className={p.fee_accrual_pct > 0.5 && p.product_type === 'pension' ? 'neg' : ''}>{p.fee_accrual_pct}%</td>
                <td>{p.employer}</td>
                <td>{p.status ? <span className={`badge ${p.status === 'פעיל' ? 'green' : ''}`}>{p.status}</span> : ''}</td>
                <td className="muted">{p.last_deposit}</td>
                <td>{p.projected_pension ? fmtILS(p.projected_pension) : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function SnapshotChart({ data }: { data: ProductData }) {
  const byDate = new Map<string, Record<string, number | string>>()
  const names = new Map(data.accounts.map((a) => [a.id, a.name]))
  data.snapshots.forEach((s) => {
    const row = byDate.get(s.date) ?? { date: s.date }
    row[names.get(s.account_id) ?? String(s.account_id)] = data.product === 'credit_card' ? -s.value : s.value
    byDate.set(s.date, row)
  })
  const rows = Array.from(byDate.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)))
  return (
    <div className="card">
      <h2>היסטוריית שווי</h2>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 11 }} width={80} />
          <Tooltip formatter={(v) => fmtILS(Number(v))} />
          <Legend />
          {data.accounts.map((a, i) => (
            <Line key={a.id} type="monotone" dataKey={a.name} stroke={CHART_COLORS[i % CHART_COLORS.length]} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
