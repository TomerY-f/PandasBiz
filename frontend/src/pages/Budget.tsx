import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiSend, fmtILS } from '../api'

interface BudgetItem { id: number; category: string; monthly_limit: number }
interface BudgetStatus { category: string; limit: number; spent: number; pct: number; over: boolean }
interface Rule { id: number; pattern: string; category: string; priority: number }

export default function Budget() {
  const [budgets, setBudgets] = useState<BudgetItem[]>([])
  const [status, setStatus] = useState<BudgetStatus[]>([])
  const [rules, setRules] = useState<Rule[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [periods, setPeriods] = useState<string[]>([])
  const [period, setPeriod] = useState('')
  const [periodType, setPeriodType] = useState<'cycle' | 'month'>('cycle')

  const [newBudget, setNewBudget] = useState({ category: '', monthly_limit: '' })
  const [newRule, setNewRule] = useState({ pattern: '', category: '' })
  const [applyMsg, setApplyMsg] = useState('')

  const reload = useCallback(() => {
    apiGet<{ budgets: BudgetItem[] }>('/budgets').then((r) => setBudgets(r.budgets))
    apiGet<{ rules: Rule[] }>('/rules').then((r) => setRules(r.rules))
    apiGet<{ categories: string[] }>('/transactions/categories').then((r) => setCategories(r.categories))
  }, [])

  useEffect(reload, [reload])

  useEffect(() => {
    apiGet<{ periods: string[] }>(`/transactions/periods?period_type=${periodType}`).then((r) => {
      setPeriods(r.periods)
      setPeriod((cur) => (r.periods.includes(cur) ? cur : r.periods[0] ?? ''))
    })
  }, [periodType])

  useEffect(() => {
    if (!period) { setStatus([]); return }
    apiGet<{ status: BudgetStatus[] }>(
      `/budgets/status?period=${encodeURIComponent(period)}&period_type=${periodType}`,
    ).then((r) => setStatus(r.status))
  }, [period, periodType, budgets])

  const addBudget = async () => {
    if (!newBudget.category || !newBudget.monthly_limit) return
    await apiSend('POST', '/budgets', { category: newBudget.category, monthly_limit: +newBudget.monthly_limit })
    setNewBudget({ category: '', monthly_limit: '' })
    reload()
  }

  const deleteBudget = async (id: number) => {
    await apiSend('DELETE', `/budgets/${id}`)
    reload()
  }

  const addRule = async () => {
    if (!newRule.pattern || !newRule.category) return
    await apiSend('POST', '/rules', { ...newRule, priority: 0 })
    setNewRule({ pattern: '', category: '' })
    reload()
  }

  const deleteRule = async (id: number) => {
    await apiSend('DELETE', `/rules/${id}`)
    reload()
  }

  const applyRules = async () => {
    const r = await apiSend<{ changed: number }>('POST', '/rules/apply')
    setApplyMsg(`עודכנו ${r.changed} תנועות`)
  }

  return (
    <div>
      <h1>תקציב וקטגוריות</h1>

      <div className="card">
        <div className="row spread">
          <h2>מצב התקציב</h2>
          <div className="row">
            <select value={periodType} onChange={(e) => setPeriodType(e.target.value as 'cycle' | 'month')}>
              <option value="cycle">מחזור חיוב (10 → 10)</option>
              <option value="month">חודש קלנדרי</option>
            </select>
            <select value={period} onChange={(e) => setPeriod(e.target.value)}>
              {periods.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
        </div>

        {status.length === 0 ? (
          <div className="empty">אין תקציבים מוגדרים — הוסף למטה</div>
        ) : (
          status.map((s) => (
            <div key={s.category} style={{ marginBottom: 14 }}>
              <div className="row spread" style={{ marginBottom: 4 }}>
                <span>{s.category} {s.over && <span className="neg">⚠ חריגה!</span>}</span>
                <span className="muted">{fmtILS(s.spent)} מתוך {fmtILS(s.limit)} ({s.pct}%)</span>
              </div>
              <div className="progress-track">
                <div
                  className={`progress-fill ${s.over ? 'over' : s.pct >= 85 ? 'warn' : ''}`}
                  style={{ width: `${Math.min(s.pct, 100)}%` }}
                />
              </div>
            </div>
          ))
        )}

        <div className="row" style={{ marginTop: 16 }}>
          <input
            list="categories-list"
            placeholder="קטגוריה"
            value={newBudget.category}
            onChange={(e) => setNewBudget({ ...newBudget, category: e.target.value })}
          />
          <datalist id="categories-list">
            {categories.map((c) => <option key={c} value={c} />)}
          </datalist>
          <input
            type="number"
            placeholder="תקרה חודשית ₪"
            value={newBudget.monthly_limit}
            onChange={(e) => setNewBudget({ ...newBudget, monthly_limit: e.target.value })}
            style={{ width: 140 }}
          />
          <button onClick={addBudget}>הוסף תקציב</button>
        </div>

        {budgets.length > 0 && (
          <table style={{ marginTop: 12 }}>
            <thead><tr><th>קטגוריה</th><th>תקרה</th><th></th></tr></thead>
            <tbody>
              {budgets.map((b) => (
                <tr key={b.id}>
                  <td>{b.category}</td>
                  <td>{fmtILS(b.monthly_limit)}</td>
                  <td><button className="danger small" onClick={() => deleteBudget(b.id)}>מחק</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="row spread">
          <h2>חוקי קטגוריות</h2>
          <div className="row">
            {applyMsg && <span className="muted">{applyMsg}</span>}
            <button className="ghost" onClick={applyRules}>הרץ חוקים על כל התנועות</button>
          </div>
        </div>
        <p className="muted">
          חוק = אם תיאור התנועה מכיל טקסט מסוים, הקטגוריה מתעדכנת אוטומטית. החוקים רצים על כל קובץ חדש שנקלט.
          קטגוריות ששונו ידנית (🔒) לא נדרסות.
        </p>
        <div className="row">
          <input
            placeholder='טקסט בתיאור (למשל "שופרסל")'
            value={newRule.pattern}
            onChange={(e) => setNewRule({ ...newRule, pattern: e.target.value })}
          />
          <input
            list="categories-list"
            placeholder="קטגוריה"
            value={newRule.category}
            onChange={(e) => setNewRule({ ...newRule, category: e.target.value })}
          />
          <button onClick={addRule}>הוסף חוק</button>
        </div>
        {rules.length > 0 && (
          <table style={{ marginTop: 12 }}>
            <thead><tr><th>אם התיאור מכיל</th><th>קטגוריה</th><th></th></tr></thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id}>
                  <td>{r.pattern}</td>
                  <td>{r.category}</td>
                  <td><button className="danger small" onClick={() => deleteRule(r.id)}>מחק</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
