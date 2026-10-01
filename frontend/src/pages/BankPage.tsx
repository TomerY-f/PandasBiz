import { useState } from 'react'
import DropZone from '../components/DropZone'
import ProductPage from './ProductPage'

const TABS = [
  { key: 'bank_current', label: 'עו"ש' },
  { key: 'bank_securities', label: 'תיק ני"ע וקרנות כספיות' },
  { key: 'fx', label: 'מט"ח' },
  { key: 'bank_loan', label: 'הלוואות' },
]

export default function BankPage() {
  const [tab, setTab] = useState(TABS[0].key)
  const [reloadKey, setReloadKey] = useState(0)
  return (
    <div>
      <h1>בנק</h1>
      <DropZone
        product="bank"
        hint='כל ייצוא מאתר הבנק: תנועות עו"ש, תיק ני"ע, מט"ח, הלוואות. כל קובץ מזוהה לפי התוכן שלו'
        onDone={() => setReloadKey((k) => k + 1)}
      />
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? 'active' : ''} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      <ProductPage key={tab} product={tab} title={TABS.find((t) => t.key === tab)!.label} hint="" upload={false} reloadKey={reloadKey} />
    </div>
  )
}
