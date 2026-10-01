const BASE = '/api'

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status}: ${body}`)
  }
  return res.json() as Promise<T>
}

export function apiGet<T>(path: string): Promise<T> {
  return fetch(`${BASE}${path}`).then((r) => handle<T>(r))
}

export function apiSend<T>(method: string, path: string, body?: unknown): Promise<T> {
  return fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  }).then((r) => handle<T>(r))
}

export function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  return fetch(`${BASE}${path}`, { method: 'POST', body: formData }).then((r) => handle<T>(r))
}

export const fmtILS = (v: number | null | undefined, digits = 0) =>
  v == null ? '—' : `₪${v.toLocaleString('he-IL', { maximumFractionDigits: digits })}`

export const fmtNum = (v: number | null | undefined, digits = 2) =>
  v == null ? '—' : v.toLocaleString('he-IL', { maximumFractionDigits: digits })

export const CHART_COLORS = [
  '#6C5CE7', '#00B894', '#0984E3', '#E17055', '#FDCB6E',
  '#E84393', '#00CEC9', '#636E72', '#A29BFE', '#55EFC4',
  '#FAB1A0', '#74B9FF', '#FF7675', '#81ECEC', '#DFE6E9',
]

// ---------- Types ----------

export interface Transaction {
  id: number
  date: string
  description: string
  amount: number
  category: string
  source: string
  month_year: string
  billing_cycle: string
  balance: number | null
  category_locked: boolean
}

export interface Account {
  id: number
  name: string
  type: string
  currency: string
  institution: string
}

export interface Holding {
  id: number
  account_id: number
  account_name: string
  symbol: string
  name: string
  quantity: number
  cost_basis: number
  currency: string
  last_price: number | null
  price_updated_at: string | null
  value_native: number | null
  value_ils: number
  gain_native: number | null
}

export interface PensionProduct {
  id: number
  account_id: number
  name: string
  provider: string
  product_type: string
  track: string
  fee_deposit_pct: number
  fee_accrual_pct: number
  notes: string
  latest_value: number | null
}

export interface Property {
  id: number
  account_id: number
  name: string
  address: string
  purchase_price: number | null
  purchase_date: string | null
  monthly_rent: number
  income_category: string
  expense_category: string
  current_value: number | null
  gross_yield_pct: number | null
  kind?: string
  details?: PropertyDetails | null
}

export interface PropertyDetails {
  address?: string
  gush?: number
  helka?: number
  sub_parcel?: string
  rooms?: number
  floor?: number
  area_sqm?: number
  gross_area_sqm?: number
  tax_area_sqm?: number
  built_year?: number
  extras?: string[]
  appraisal?: { date: string; value: number; appraiser: string; ppsqm?: number; quick_sale?: number }
  estimate?: { value: number; low: number; high: number; date: string; method: string }
  market?: { year: number; deals: number; median_ppsqm: number }[]
  comps?: { date: string; sub_parcel: string; area: number; rooms: number | null; amount: number; ppsqm: number; own?: boolean }[]
  source_url?: string
}

export interface Snapshot {
  id: number
  account_id: number
  date: string
  value: number
  note: string
}

export interface DashboardData {
  usd_ils: number
  assets_total: number
  liabilities_total: number
  net_worth: number
  asset_map: { type: string; label: string; value_ils: number }[]
  breakdown: { account_id: number; name: string; type: string; type_label: string; value_ils: number }[]
  history: { month: string; value_ils: number }[]
  cashflow: { month: string; income: number; expenses: number }[]
  budget_alerts: { category: string; spent: number; limit: number; over: boolean }[]
  latest_cycle: string | null
}

// ---------- Family app ----------

export interface Member {
  id: number
  name: string
  role: string
  id_number: string
  aliases: string
  color: string
}

export interface Meta {
  products: { key: string; label: string; type: string; bucket: string }[]
  buckets: { key: string; label: string; group: 'liquid' | 'illiquid' | 'liability' }[]
  line_groups: { key: string; label: string }[]
}

export interface UploadResult {
  file: string
  product?: string
  product_label?: string
  account?: string | null
  owner?: string | null
  inserted?: number
  duplicates?: number
  created?: number
  updated?: number
  removed?: number
  loans?: number
  policies?: number
  snapshot?: number
  stored_only?: boolean
  note?: string
  error?: string
}

/** member filter value: 'all' | 'joint' | member id as string */
export const memberQuery = (member: string) => (member && member !== 'all' ? `member=${member}` : '')

export const withQuery = (path: string, ...parts: string[]) => {
  const q = parts.filter(Boolean).join('&')
  return q ? `${path}${path.includes('?') ? '&' : '?'}${q}` : path
}

export const fmtPct = (v: number | null | undefined, digits = 1) =>
  v == null ? '—' : `${v.toLocaleString('he-IL', { maximumFractionDigits: digits })}%`

export const monthLabel = (m: string) => {
  if (m === 'avg') return 'ממוצע'
  const [y, mm] = m.split('-').map(Number)
  const names = ['ינו׳', 'פבר׳', 'מרץ', 'אפר׳', 'מאי', 'יוני', 'יולי', 'אוג׳', 'ספט׳', 'אוק׳', 'נוב׳', 'דצמ׳']
  return `${names[mm - 1]} ${String(y).slice(2)}`
}
