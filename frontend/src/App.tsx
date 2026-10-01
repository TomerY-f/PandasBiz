import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { MemberProvider, MemberSelect } from './components/MemberContext'
import BankPage from './pages/BankPage'
import Budget from './pages/Budget'
import Calculators from './pages/Calculators'
import Dashboard from './pages/Dashboard'
import IncomeExpense from './pages/IncomeExpense'
import NetWorth from './pages/NetWorth'
import ProductPage from './pages/ProductPage'
import RealEstate from './pages/RealEstate'
import Settings from './pages/Settings'

const SHEETS = [
  { to: '/', label: 'דשבורד', end: true },
  { to: '/income-expense', label: 'מעקב הכנסות והוצאות' },
  { to: '/networth', label: 'מעקב שווי נקי' },
  { to: '/calculators', label: 'מחשבונים' },
  { to: '/budget', label: 'תקציב' },
]

// Product tabs follow the input folders: Bank, CreditCards, IndependentStocksTrading,
// Pensions_and_Study_Funds, Insurences, Mortgage, RealEstate
const PRODUCTS: { key: string; path: string; label: string; hint: string }[] = [
  { key: 'bank', path: '/p/bank', label: 'בנק', hint: '' },
  { key: 'credit_card', path: '/p/credit', label: 'כרטיסי אשראי', hint: 'פירוט חיובים חודשי לכל כרטיס (xlsx). הבעלים מזוהה לפי "על שם"' },
  { key: 'trading', path: '/p/trading', label: 'מסחר עצמאי', hint: 'תיק סוף יום מבית ההשקעות (xlsx)' },
  { key: 'pension', path: '/p/pension', label: 'פנסיה והשתלמות', hint: 'דוח מסלקה פנסיונית (PDF, גם מוגן בסיסמה) לכל בן משפחה' },
  { key: 'insurance', path: '/p/insurance', label: 'ביטוחים', hint: 'ייצוא מהר הביטוח (xlsx). פוליסות PDF נשמרות כמסמך' },
  { key: 'mortgage', path: '/p/mortgage', label: 'משכנתא', hint: 'פירוט המשכנתאות (xlsx). דוחות PDF נשמרים כמסמך' },
  { key: 'real_estate', path: '/p/realestate', label: 'נדל"ן', hint: 'נסחי טאבו / שמאות (PDF) נשמרים כמסמך; שווי מעדכנים ידנית' },
]

export default function App() {
  return (
    <MemberProvider>
      <div className="layout">
        <nav className="sidebar">
          <div className="brand">🐼 PandasBiz</div>
          <MemberSelect />
          <div className="section">גיליונות</div>
          {SHEETS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => (isActive ? 'active' : '')}>
              {item.label}
            </NavLink>
          ))}
          <div className="section">מוצרים</div>
          {PRODUCTS.map((p) => (
            <NavLink key={p.key} to={p.path} className={({ isActive }) => (isActive ? 'active' : '')}>
              {p.label}
            </NavLink>
          ))}
          <div className="section">ניהול</div>
          <NavLink to="/settings" className={({ isActive }) => (isActive ? 'active' : '')}>הגדרות</NavLink>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/income-expense" element={<IncomeExpense />} />
            <Route path="/networth" element={<NetWorth />} />
            <Route path="/calculators" element={<Calculators />} />
            <Route path="/budget" element={<Budget />} />
            <Route path="/p/bank" element={<BankPage />} />
            {PRODUCTS.filter((p) => p.key !== 'bank').map((p) => (
              <Route
                key={p.key}
                path={p.path}
                element={
                  <ProductPage key={p.key} product={p.key} title={p.label} hint={p.hint}>
                    {p.key === 'real_estate' && <RealEstate />}
                  </ProductPage>
                }
              />
            ))}
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </MemberProvider>
  )
}
