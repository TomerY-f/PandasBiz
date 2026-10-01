import { useRef, useState } from 'react'
import { type UploadResult, apiUpload } from '../api'
import { useMember } from './MemberContext'

interface Props {
  /** product key; omit for auto-detect */
  product?: string
  hint?: string
  accept?: string
  onDone?: (results: UploadResult[]) => void
}

const describe = (r: UploadResult) => {
  if (r.error) return r.error
  if (r.stored_only) return 'נשמר כמסמך'
  const parts: string[] = []
  if (r.inserted != null) parts.push(`${r.inserted} תנועות חדשות`)
  if (r.duplicates) parts.push(`${r.duplicates} כפולות דולגו`)
  if (r.created != null || r.updated != null) parts.push(`${(r.created ?? 0) + (r.updated ?? 0)} אחזקות`)
  if (r.loans != null) parts.push(`${r.loans} הלוואות`)
  if (r.policies != null) parts.push(`${r.policies} פוליסות`)
  if (r.snapshot != null) parts.push(`שווי ₪${Math.round(r.snapshot).toLocaleString('he-IL')}`)
  return parts.join(' · ')
}

export default function DropZone({ product, hint, accept = '.xls,.xlsx,.csv,.html,.htm,.pdf', onDone }: Props) {
  const { member, members } = useMember()
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [owner, setOwner] = useState<string>('auto')
  const [password, setPassword] = useState('')
  const [results, setResults] = useState<UploadResult[]>([])
  const input = useRef<HTMLInputElement>(null)

  const upload = async (files: FileList | File[]) => {
    const list = Array.from(files)
    if (!list.length) return
    setBusy(true)
    try {
      const fd = new FormData()
      list.forEach((f) => fd.append('files', f))
      const ownerId = owner === 'auto' ? (member !== 'all' && member !== 'joint' ? member : '') : owner
      if (ownerId) fd.append('member_id', ownerId)
      if (password) fd.append('password', password) // used once to open protected PDFs, never stored
      const res = await apiUpload<{ results: UploadResult[] }>(product ? `/products/${product}/upload` : '/upload', fd)
      setResults(res.results)
      onDone?.(res.results)
    } catch (e) {
      setResults([{ file: list.map((f) => f.name).join(', '), error: String(e) }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card">
      <div
        className={`dropzone ${over ? 'over' : ''} ${busy ? 'busy' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          upload(e.dataTransfer.files)
        }}
        onClick={() => input.current?.click()}
      >
        <div className="dz-icon">⬇</div>
        <div className="dz-title">{busy ? 'מעבד קבצים...' : 'גררו לכאן קבצים, או לחצו לבחירה'}</div>
        {hint && <div className="muted">{hint}</div>}
        <input
          ref={input}
          type="file"
          multiple
          accept={accept}
          style={{ display: 'none' }}
          onChange={(e) => {
            if (e.target.files) upload(e.target.files)
            e.target.value = ''
          }}
        />
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <span className="muted">שיוך לבן משפחה:</span>
        <select value={owner} onChange={(e) => setOwner(e.target.value)}>
          <option value="auto">אוטומטי (לפי הקובץ / הבחירה למעלה)</option>
          {members.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </select>
        <span className="muted">סיסמה לקובץ PDF מוגן:</span>
        <input type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="לא חובה" style={{ width: 130 }} />
      </div>
      {results.length > 0 && (
        <table style={{ marginTop: 12 }}>
          <tbody>
            {results.map((r, i) => (
              <tr key={i}>
                <td>{r.error ? '⚠' : '✓'}</td>
                <td>{r.file}</td>
                <td>{r.account ?? r.product_label ?? ''}{r.owner ? ` · ${r.owner}` : ''}</td>
                <td className={r.error ? 'neg' : 'muted'}>{describe(r)}{r.note ? ` · ${r.note}` : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
