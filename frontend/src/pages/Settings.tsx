import { useCallback, useEffect, useState } from 'react'
import { type Member, apiGet, apiSend, fmtILS } from '../api'
import { useMember } from '../components/MemberContext'

interface Rule { id: number; pattern: string; category: string; priority: number; direction: string }
interface SectorRow { sector: string; line: string; count: number }
interface Uncat { description: string; category: string; count: number; total: number }
interface LineRow { id: number; name: string; group: string }

const DIRECTIONS: Record<string, string> = { '': 'כל תנועה', in: 'זיכוי (הכנסה)', out: 'חיוב (הוצאה)' }
const emptyMember = { name: '', role: 'adult', id_number: '', aliases: '', color: '#6C5CE7' }

export default function Settings() {
  const { members, reloadMembers, meta } = useMember()
  const [form, setForm] = useState(emptyMember)
  const [editId, setEditId] = useState<number | null>(null)
  const [rules, setRules] = useState<Rule[]>([])
  const [sectors, setSectors] = useState<SectorRow[]>([])
  const [uncat, setUncat] = useState<Uncat[]>([])
  const [lines, setLines] = useState<LineRow[]>([])
  const [ruleForm, setRuleForm] = useState({ pattern: '', category: '', direction: '' })
  const [lineForm, setLineForm] = useState({ name: '', group: 'want_variable' })
  const [msg, setMsg] = useState('')

  const load = useCallback(() => {
    apiGet<{ rules: Rule[] }>('/rules').then((r) => setRules(r.rules))
    apiGet<{ sectors: SectorRow[] }>('/sectors').then((r) => setSectors(r.sectors))
    apiGet<{ items: Uncat[] }>('/uncategorized').then((r) => setUncat(r.items))
    apiGet<{ lines: LineRow[] }>('/lines').then((r) => setLines(r.lines))
  }, [])
  useEffect(load, [load])

  const saveMember = async () => {
    if (!form.name) return
    try {
      if (editId) await apiSend('PATCH', `/members/${editId}`, form)
      else await apiSend('POST', '/members', form)
      setForm(emptyMember)
      setEditId(null)
      reloadMembers()
    } catch (e) {
      setMsg(String(e))
    }
  }

  const editMember = (m: Member) => {
    setEditId(m.id)
    setForm({ name: m.name, role: m.role, id_number: m.id_number, aliases: m.aliases, color: m.color })
  }

  const deleteMember = async (m: Member) => {
    if (!confirm(`להסיר את ${m.name}? החשבונות שלו יהפכו למשותפים.`)) return
    await apiSend('DELETE', `/members/${m.id}`)
    reloadMembers()
  }

  const addRule = async (pattern = ruleForm.pattern, category = ruleForm.category, direction = ruleForm.direction) => {
    if (!pattern || !category) return
    const r = await apiSend<{ changed: number }>('POST', '/rules', { pattern, category, direction, priority: 60 })
    setMsg(`הכלל נשמר — ${r.changed} תנועות סווגו מחדש`)
    setRuleForm({ pattern: '', category: '', direction: '' })
    load()
  }

  const deleteRule = async (id: number) => {
    await apiSend('DELETE', `/rules/${id}`)
    await apiSend('POST', '/rules/apply')
    load()
  }

  const setSector = async (sector: string, line: string) => {
    const r = await apiSend<{ changed: number }>('PUT', '/sectors', { sector, line })
    setMsg(`${r.changed} תנועות סווגו מחדש`)
    load()
  }

  const addLine = async () => {
    if (!lineForm.name) return
    await apiSend('POST', '/lines', lineForm)
    setLineForm({ ...lineForm, name: '' })
    load()
  }

  const groupLabel = (k: string) => meta?.line_groups.find((g) => g.key === k)?.label ?? k
  const lineOptions = (
    <>
      <option value="">בחרו שורה...</option>
      {meta?.line_groups.map((g) => (
        <optgroup key={g.key} label={g.label}>
          {lines.filter((l) => l.group === g.key).map((l) => <option key={l.id} value={l.name}>{l.name}</option>)}
        </optgroup>
      ))}
    </>
  )

  return (
    <div>
      <h1>הגדרות</h1>
      {msg && <div className="alert warn" onClick={() => setMsg('')}>{msg}</div>}

      <div className="card">
        <h2>בני המשפחה</h2>
        <p className="muted">
          בני משפחה נוצרים אוטומטית לפי "על שם" בקבצי האשראי. כינויים = שמות נוספים כפי שהם מופיעים בקבצים (מופרדים בפסיק).
          ת"ז משמשת רק לשיוך פוליסות מהר הביטוח ונשמרת במסד הנתונים המקומי בלבד.
        </p>
        <table>
          <thead><tr><th>שם</th><th>כינויים בקבצים</th><th>ת"ז</th><th>צבע</th><th></th></tr></thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id}>
                <td><b>{m.name}</b></td>
                <td className="muted">{m.aliases}</td>
                <td className="muted">{m.id_number ? '••••' + m.id_number.slice(-3) : '—'}</td>
                <td><span className="dot" style={{ display: 'inline-block', width: 14, height: 14, borderRadius: 7, background: m.color }} /></td>
                <td className="row">
                  <button className="ghost small" onClick={() => editMember(m)}>עריכה</button>
                  <button className="danger small" onClick={() => deleteMember(m)}>הסר</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row" style={{ marginTop: 12 }}>
          <input placeholder="שם" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={{ width: 120 }} />
          <input placeholder="כינויים (שם מלא כפי שמופיע בקובץ)" value={form.aliases} onChange={(e) => setForm({ ...form, aliases: e.target.value })} />
          <input placeholder='ת"ז (לא חובה)' value={form.id_number} onChange={(e) => setForm({ ...form, id_number: e.target.value })} style={{ width: 130 }} />
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option value="adult">מבוגר</option>
            <option value="child">ילד</option>
          </select>
          <input type="color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} style={{ width: 44, padding: 2 }} />
          <button onClick={saveMember}>{editId ? 'שמירה' : 'הוספה'}</button>
          {editId && <button className="ghost" onClick={() => { setEditId(null); setForm(emptyMember) }}>ביטול</button>}
        </div>
      </div>

      <div className="card">
        <h2>תנועות שעדיין לא סווגו</h2>
        <p className="muted">התיאורים השכיחים ביותר שנפלו ל"לא מסווג" או ל"הכנסה אחרת". בחירת שורה יוצרת כלל ומסווגת מחדש את כל התנועות התואמות.</p>
        <table>
          <thead><tr><th>תיאור</th><th>פעמים</th><th>סה"כ</th><th>סווג כעת</th><th>שייך לשורה</th></tr></thead>
          <tbody>
            {uncat.map((u) => (
              <tr key={u.description + u.category}>
                <td>{u.description}</td>
                <td>{u.count}</td>
                <td className={u.total < 0 ? 'neg' : 'pos'}>{fmtILS(u.total)}</td>
                <td className="muted">{u.category}</td>
                <td>
                  <select value="" onChange={(e) => e.target.value && addRule(u.description, e.target.value, u.total >= 0 ? 'in' : 'out')}>
                    {lineOptions}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>מיפוי ענפי אשראי לשורות הגיליון</h2>
        <table>
          <thead><tr><th>ענף (מהקובץ)</th><th>תנועות</th><th>שורה בגיליון</th></tr></thead>
          <tbody>
            {sectors.map((s) => (
              <tr key={s.sector}>
                <td>{s.sector}</td>
                <td>{s.count}</td>
                <td><select value={s.line} onChange={(e) => setSector(s.sector, e.target.value)}>{lineOptions}</select></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>כללי סיווג לפי תיאור</h2>
        <p className="muted">כלל גובר על מיפוי הענף. כלל עם כיוון חל רק על זיכויים או רק על חיובים.</p>
        <div className="row" style={{ marginBottom: 10 }}>
          <input placeholder="טקסט בתיאור (למשל: שם המעסיק)" value={ruleForm.pattern} onChange={(e) => setRuleForm({ ...ruleForm, pattern: e.target.value })} />
          <select value={ruleForm.direction} onChange={(e) => setRuleForm({ ...ruleForm, direction: e.target.value })}>
            {Object.entries(DIRECTIONS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <select value={ruleForm.category} onChange={(e) => setRuleForm({ ...ruleForm, category: e.target.value })}>{lineOptions}</select>
          <button onClick={() => addRule()}>הוספת כלל</button>
        </div>
        <div style={{ maxHeight: 360, overflowY: 'auto' }}>
          <table>
            <thead><tr><th>טקסט</th><th>כיוון</th><th>שורה</th><th>עדיפות</th><th></th></tr></thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id}>
                  <td>{r.pattern}</td>
                  <td className="muted">{DIRECTIONS[r.direction] ?? r.direction}</td>
                  <td>{r.category}</td>
                  <td className="muted">{r.priority}</td>
                  <td><button className="danger small" onClick={() => deleteRule(r.id)}>מחק</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>שורות הגיליון</h2>
        <p className="muted">השורות מבוססות על גיליון מעקב ההוצאות של הסולידית. אפשר להוסיף שורות משלכם.</p>
        <div className="row">
          <input placeholder="שם שורה חדשה" value={lineForm.name} onChange={(e) => setLineForm({ ...lineForm, name: e.target.value })} />
          <select value={lineForm.group} onChange={(e) => setLineForm({ ...lineForm, group: e.target.value })}>
            {meta?.line_groups.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}
          </select>
          <button onClick={addLine}>הוספה</button>
        </div>
        <p className="muted">{lines.length} שורות, ב-{new Set(lines.map((l) => groupLabel(l.group))).size} קבוצות.</p>
      </div>
    </div>
  )
}
