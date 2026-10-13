import { fmtILS, monthLabel } from '../api'

interface Row { month: string; income: number; needs: number; wants: number; balance: number }

const n = (v: number) => Math.round(v).toLocaleString('he-IL')

/** Monthly cash flow in words: income − needs − wants = surplus / deficit. */
export default function CashflowSummary({ rows }: { rows: Row[] }) {
  const months = rows.filter((r) => r.month !== 'avg' && (r.income || r.needs || r.wants))
  if (!months.length) return null
  return (
    <div className="cashflow-summary">
      <div className="muted" style={{ marginBottom: 4 }}>תזרים חודשי: הכנסות − צרכים − רצונות</div>
      {[...months].reverse().map((r) => (
        <div key={r.month} className="cf-row">
          <span className="cf-month">{monthLabel(r.month)}</span>
          <span className="cf-calc">
            <span className="pos">{n(r.income)}</span> − {n(r.needs)} − {n(r.wants)} =
          </span>
          <b className={r.balance >= 0 ? 'pos' : 'neg'}>{r.balance >= 0 ? '+' : '−'}{fmtILS(Math.abs(r.balance))}</b>
        </div>
      ))}
    </div>
  )
}
