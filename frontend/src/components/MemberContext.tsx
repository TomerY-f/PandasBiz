import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { type Member, type Meta, apiGet } from '../api'

interface Ctx {
  member: string // 'all' | 'joint' | id
  setMember: (m: string) => void
  members: Member[]
  meta: Meta | null
  reloadMembers: () => void
  memberName: (id: number | null | undefined) => string
}

const MemberCtx = createContext<Ctx | null>(null)

const readStored = () => {
  try {
    return localStorage.getItem('familybiz.member') || 'all'
  } catch {
    return 'all'
  }
}

export function MemberProvider({ children }: { children: ReactNode }) {
  const [member, setMemberState] = useState<string>(() => (readStored() === 'joint' ? 'all' : readStored()))
  const [members, setMembers] = useState<Member[]>([])
  const [meta, setMeta] = useState<Meta | null>(null)

  const reloadMembers = useCallback(() => {
    apiGet<{ members: Member[] }>('/members').then((r) => setMembers(r.members)).catch(() => {})
  }, [])

  useEffect(() => {
    reloadMembers()
    apiGet<Meta>('/meta').then(setMeta).catch(() => {})
  }, [reloadMembers])

  const setMember = (m: string) => {
    setMemberState(m)
    try {
      localStorage.setItem('familybiz.member', m)
    } catch {
      /* ignore */
    }
  }

  const memberName = (id: number | null | undefined) =>
    id == null ? 'משותף' : members.find((m) => m.id === id)?.name ?? '—'

  return (
    <MemberCtx.Provider value={{ member, setMember, members, meta, reloadMembers, memberName }}>
      {children}
    </MemberCtx.Provider>
  )
}

export function useMember() {
  const ctx = useContext(MemberCtx)
  if (!ctx) throw new Error('useMember outside MemberProvider')
  return ctx
}

export function MemberSelect() {
  const { member, setMember, members } = useMember()
  return (
    <div className="member-select">
      <div className="label">מציג עבור</div>
      <div className="member-chips">
        <button className={member === 'all' ? 'active' : ''} onClick={() => setMember('all')}>כל המשפחה</button>
        {members.map((m) => (
          <button key={m.id} className={member === String(m.id) ? 'active' : ''} onClick={() => setMember(String(m.id))}>
            <span className="dot" style={{ background: m.color }} />
            {m.name}
          </button>
        ))}
      </div>
    </div>
  )
}
