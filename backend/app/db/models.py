from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# Account types
ACCOUNT_TYPES = [
    "checking",      # עו"ש
    "credit_card",   # כרטיס אשראי
    "brokerage",     # חשבון השקעות (אקסלנס, E-Trade)
    "money_market",  # קרן כספית
    "pension",       # פנסיה / השתלמות / גמל
    "insurance",     # ביטוח
    "property",      # נדל"ן
    "loan",          # הלוואה / משכנתא (שווי שלילי)
    "other",
]

# Account types whose value comes from snapshots (not transactions/holdings)
SNAPSHOT_VALUED_TYPES = {"money_market", "pension", "insurance", "property", "loan", "other"}


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    type: Mapped[str] = mapped_column(String)  # one of ACCOUNT_TYPES
    currency: Mapped[str] = mapped_column(String, default="ILS")
    institution: Mapped[str] = mapped_column(String, default="")
    # Family-app fields
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("family_members.id"), nullable=True)
    product: Mapped[str] = mapped_column(String, default="")      # one of PRODUCTS keys
    nw_bucket: Mapped[str] = mapped_column(String, default="")    # one of NW_BUCKETS keys
    external_ref: Mapped[str] = mapped_column(String, default="")  # card last-4 / account number, for matching uploads

    owner: Mapped["FamilyMember | None"] = relationship()
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")
    holdings: Mapped[list["Holding"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    snapshots: Mapped[list["AssetSnapshot"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("dedup_hash", name="uq_tx_dedup"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String, default="")
    # Signed amount: negative = expense/debit, positive = income/credit
    amount: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String, default="General / Uncategorized", index=True)
    source: Mapped[str] = mapped_column(String)  # "credit" | "bank"
    month_year: Mapped[str] = mapped_column(String, index=True)      # "2026-03"
    billing_cycle: Mapped[str] = mapped_column(String, index=True)   # "2026-02 → 2026-03" (10th to 10th)
    dedup_hash: Mapped[str] = mapped_column(String, index=True)
    category_locked: Mapped[int] = mapped_column(Integer, default=0)  # 1 = manually set, rules won't override
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)  # bank running balance if present
    sector: Mapped[str] = mapped_column(String, default="")  # raw merchant sector (ענף) from the card export

    account: Mapped["Account"] = relationship(back_populates="transactions")


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uq_holding_account_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    symbol: Mapped[str] = mapped_column(String)          # yfinance symbol, e.g. AAPL / TEVA.TA
    name: Mapped[str] = mapped_column(String, default="")
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    cost_basis: Mapped[float] = mapped_column(Float, default=0.0)  # total cost, in holding currency
    currency: Mapped[str] = mapped_column(String, default="USD")
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    asset_class: Mapped[str] = mapped_column(String, default="")  # NW bucket override (deposits / stocks / bonds / cash)

    account: Mapped["Account"] = relationship(back_populates="holdings")


class AssetSnapshot(Base):
    __tablename__ = "asset_snapshots"
    __table_args__ = (UniqueConstraint("account_id", "date", name="uq_snapshot_account_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[float] = mapped_column(Float)  # in account currency; negative for loans
    note: Mapped[str] = mapped_column(Text, default="")

    account: Mapped["Account"] = relationship(back_populates="snapshots")


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern: Mapped[str] = mapped_column(String)   # substring matched against description
    category: Mapped[str] = mapped_column(String)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # higher wins
    direction: Mapped[str] = mapped_column(String, default="")  # "" = any | "in" = credits only | "out" = debits only


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String, unique=True)
    monthly_limit: Mapped[float] = mapped_column(Float)


class PensionProduct(Base):
    __tablename__ = "pension_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    provider: Mapped[str] = mapped_column(String, default="")        # חברה מנהלת
    product_type: Mapped[str] = mapped_column(String, default="pension")  # pension | study_fund | gemel | insurance
    track: Mapped[str] = mapped_column(String, default="")           # מסלול השקעה
    fee_deposit_pct: Mapped[float] = mapped_column(Float, default=0.0)   # דמי ניהול מהפקדה
    fee_accrual_pct: Mapped[float] = mapped_column(Float, default=0.0)   # דמי ניהול מצבירה
    notes: Mapped[str] = mapped_column(Text, default="")
    # from a pension clearing-house report (PDF)
    policy_number: Mapped[str] = mapped_column(String, default="")
    employer: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="")          # פעיל | לא פעיל
    salary: Mapped[float] = mapped_column(Float, default=0.0)         # שכר למוצר
    projected_pension: Mapped[float] = mapped_column(Float, default=0.0)  # קצבה חזויה
    last_deposit: Mapped[str] = mapped_column(String, default="")

    account: Mapped["Account"] = relationship()


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    name: Mapped[str] = mapped_column(String)
    address: Mapped[str] = mapped_column(String, default="")
    purchase_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    monthly_rent: Mapped[float] = mapped_column(Float, default=0.0)
    kind: Mapped[str] = mapped_column(String, default="residence")  # residence | investment
    income_category: Mapped[str] = mapped_column(String, default="הכנסה משכירות - נטו")
    expense_category: Mapped[str] = mapped_column(String, default="משכנתא / דמי שכירות")
    details: Mapped[str] = mapped_column(Text, default="")  # JSON: area, rooms, parcel, appraisal, valuation...

    account: Mapped["Account"] = relationship()


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------- Family finance app ----------

# Product pages. key -> (Hebrew label, default account type, default net-worth bucket)
PRODUCTS = {
    "bank_current": ('עו"ש', "checking", "cash"),
    "credit_card": ("כרטיסי אשראי", "credit_card", "credit_cards"),
    "bank_securities": ('תיק ני"ע בבנק', "brokerage", "deposits"),
    "fx": ('מט"ח', "checking", "cash"),
    "bank_loan": ("הלוואות בנק", "loan", "personal_loans"),
    "mortgage": ("משכנתא", "loan", "mortgage"),
    "trading": ("מסחר עצמאי", "brokerage", "stocks"),
    "pension": ("פנסיה וקרנות השתלמות", "pension", "pension"),
    "insurance": ("ביטוחים", "insurance", "life_insurance"),
    "real_estate": ('נדל"ן', "property", "residence"),
    "manual": ("נכס / התחייבות ידני", "other", "other_illiquid"),
}

# Net-worth buckets, mirroring the columns of the "מעקב שווי נקי" sheet.
# key -> (Hebrew label, group) ; group: liquid | illiquid | liability
NW_BUCKETS = {
    "cash": ('מזומן (כולל עו"ש ומט"ח)', "liquid"),
    "deposits": ('פקדונות, תכניות חיסכון, מק"מ וקרנות כספיות', "liquid"),
    "bonds": ("אגרות חוב", "liquid"),
    "stocks": ("מניות", "liquid"),
    "study_fund": ("קרן השתלמות", "liquid"),
    "liquid_gemel": ("קופת גמל נזילה", "liquid"),
    "investment_re": ('שווי נדל"ן להשקעה', "liquid"),
    "business": ("שווי עסק בבעלותכם", "liquid"),
    "metals": ("מתכות יקרות", "liquid"),
    "other_productive": ("נכס מניב אחר", "liquid"),
    "pension": ("חסכונות פנסיוניים (גמל, ביטוח מנהלים, פנסיה)", "illiquid"),
    "residence": ("שווי דירת מגורים", "illiquid"),
    "car": ("שווי רכב", "illiquid"),
    "life_insurance": ("ערך פדיון ביטוח חיים", "illiquid"),
    "other_illiquid": ("נכס בלתי נזיל אחר", "illiquid"),
    "credit_cards": ("כרטיסי אשראי", "liability"),
    "overdraft": ("אוברדראפט", "liability"),
    "car_loan": ("יתרת הלוואת רכב", "liability"),
    "personal_loans": ("הלוואות אישיות", "liability"),
    "installments": ("עסקאות בתשלומים", "liability"),
    "cgt": ("מס רווח הון שנותר לשלם", "liability"),
    "other_taxes": ("מיסים אחרים שנותר לשלם", "liability"),
    "mortgage": ("יתרת משכנתא", "liability"),
    "mortgage2": ("יתרת משכנתא שניה", "liability"),
    "margin_loan": ("הלוואה בחשבון מסחר ממונף", "liability"),
    "business_loan": ("הלוואה עסקית", "liability"),
    "other_liability": ("התחייבויות אחרות", "liability"),
}

# Budget-line groups, mirroring the "מעקב הכנסות והוצאות" sheet sections.
LINE_GROUPS = {
    "income": "הכנסות נטו אחרי מס",
    "need_fixed": "הוצאות חיוניות קבועות",
    "need_variable": "הוצאות חיוניות משתנות",
    "want_fixed": "מותרויות קבועות",
    "want_variable": "מותרויות משתנות",
    "saving_gross": "הפקדות מהברוטו",
    "saving_net": "הפקדות מהנטו",
    "uncategorized": "לא מסווג",
    "excluded": "לא נספר (העברות פנימיות)",
}

UNCATEGORIZED = "לא מסווג"
INTERNAL_TRANSFER = "העברה פנימית"


class FamilyMember(Base):
    __tablename__ = "family_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    role: Mapped[str] = mapped_column(String, default="adult")  # adult | child
    id_number: Mapped[str] = mapped_column(String, default="")  # ת"ז, only for matching uploads (local DB only)
    aliases: Mapped[str] = mapped_column(String, default="")    # comma-separated names as they appear in exports
    color: Mapped[str] = mapped_column(String, default="#6C5CE7")


class BudgetLine(Base):
    __tablename__ = "budget_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    group: Mapped[str] = mapped_column(String)  # one of LINE_GROUPS
    sort: Mapped[int] = mapped_column(Integer, default=0)
    cpi_group: Mapped[str] = mapped_column(String, default="")  # personal-inflation group


class SectorMap(Base):
    """Maps a merchant sector (ענף) from card exports onto a budget line."""
    __tablename__ = "sector_map"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sector: Mapped[str] = mapped_column(String, unique=True)
    line: Mapped[str] = mapped_column(String)


class MonthlyEntry(Base):
    """Manual amount for a budget line in a month (salary slip deposits, cash, corrections)."""
    __tablename__ = "monthly_entries"
    __table_args__ = (UniqueConstraint("line", "month", "member_id", name="uq_entry_line_month_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line: Mapped[str] = mapped_column(String, index=True)
    month: Mapped[str] = mapped_column(String, index=True)  # "2026-03"
    member_id: Mapped[int | None] = mapped_column(ForeignKey("family_members.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(Text, default="")


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    name: Mapped[str] = mapped_column(String)
    original_amount: Mapped[float] = mapped_column(Float, default=0.0)
    balance: Mapped[float] = mapped_column(Float, default=0.0)  # positive number
    rate_text: Mapped[str] = mapped_column(String, default="")
    monthly_payment: Mapped[float] = mapped_column(Float, default=0.0)
    payments_left: Mapped[str] = mapped_column(String, default="")  # e.g. "44/300"
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)

    account: Mapped["Account"] = relationship()


class InsurancePolicy(Base):
    __tablename__ = "insurance_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("family_members.id"), nullable=True)
    id_number: Mapped[str] = mapped_column(String, default="", index=True)  # insured ID as in the export
    domain: Mapped[str] = mapped_column(String, default="")      # תחום
    main_branch: Mapped[str] = mapped_column(String, default="")  # ענף ראשי
    sub_branch: Mapped[str] = mapped_column(String, default="")   # ענף משני
    product_type: Mapped[str] = mapped_column(String, default="")
    company: Mapped[str] = mapped_column(String, default="")
    period: Mapped[str] = mapped_column(String, default="")
    details: Mapped[str] = mapped_column(Text, default="")
    premium: Mapped[float] = mapped_column(Float, default=0.0)
    premium_type: Mapped[str] = mapped_column(String, default="")  # שנתית | חודשית
    policy_number: Mapped[str] = mapped_column(String, default="")
    plan_class: Mapped[str] = mapped_column(String, default="")

    member: Mapped["FamilyMember | None"] = relationship()


class Document(Base):
    """An uploaded file kept on disk (PDFs, or the original of a parsed export)."""
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product: Mapped[str] = mapped_column(String, index=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("family_members.id"), nullable=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String)
    stored_path: Mapped[str] = mapped_column(String)
    sha1: Mapped[str] = mapped_column(String, index=True)
    size: Mapped[int] = mapped_column(Integer, default=0)
    parsed: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PensionReport(Base):
    """Summary page of a pension clearing-house report (one per member, latest wins)."""
    __tablename__ = "pension_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("family_members.id"), nullable=True)
    client_name: Mapped[str] = mapped_column(String, default="")
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_savings: Mapped[float] = mapped_column(Float, default=0.0)
    ytd_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    monthly_premium: Mapped[float] = mapped_column(Float, default=0.0)
    data: Mapped[str] = mapped_column(Text, default="")  # JSON: deposits, pensions, coverages, mix
