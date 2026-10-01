"""Snapshots, pension products and properties (manual-entry assets)."""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Account, AssetSnapshot, PensionProduct, Property, Transaction

router = APIRouter(prefix="/api", tags=["assets"])


# ---------- Snapshots ----------

class SnapshotIn(BaseModel):
    account_id: int
    date: date
    value: float
    note: str = ""


@router.get("/snapshots")
def list_snapshots(account_id: int | None = None, db: Session = Depends(get_db)):
    q = select(AssetSnapshot).order_by(AssetSnapshot.date.desc())
    if account_id:
        q = q.where(AssetSnapshot.account_id == account_id)
    snaps = db.scalars(q).all()
    return {
        "snapshots": [
            {"id": s.id, "account_id": s.account_id, "date": s.date.isoformat(), "value": s.value, "note": s.note}
            for s in snaps
        ]
    }


@router.post("/snapshots")
def upsert_snapshot(body: SnapshotIn, db: Session = Depends(get_db)):
    existing = db.scalar(
        select(AssetSnapshot).where(AssetSnapshot.account_id == body.account_id, AssetSnapshot.date == body.date)
    )
    if existing:
        existing.value = body.value
        existing.note = body.note
    else:
        db.add(AssetSnapshot(**body.model_dump()))
    db.commit()
    return {"ok": True}


@router.delete("/snapshots/{snapshot_id}")
def delete_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    s = db.get(AssetSnapshot, snapshot_id)
    if not s:
        raise HTTPException(404, "Snapshot not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


# ---------- Pension & insurance products ----------

PENSION_BUCKETS = {"pension": "pension", "study_fund": "study_fund", "gemel": "liquid_gemel", "insurance": "life_insurance"}


class PensionIn(BaseModel):
    name: str
    owner_id: int | None = None
    provider: str = ""
    product_type: str = "pension"  # pension | study_fund | gemel | insurance
    track: str = ""
    fee_deposit_pct: float = 0.0
    fee_accrual_pct: float = 0.0
    notes: str = ""


def pension_out(p: PensionProduct, latest_value: float | None) -> dict:
    return {
        "id": p.id,
        "account_id": p.account_id,
        "name": p.account.name if p.account else "",
        "provider": p.provider,
        "product_type": p.product_type,
        "track": p.track,
        "fee_deposit_pct": p.fee_deposit_pct,
        "fee_accrual_pct": p.fee_accrual_pct,
        "notes": p.notes,
        "owner_id": p.account.owner_id if p.account else None,
        "latest_value": latest_value,
    }


def latest_value(db: Session, account_id: int) -> float | None:
    snap = db.scalar(
        select(AssetSnapshot)
        .where(AssetSnapshot.account_id == account_id)
        .order_by(AssetSnapshot.date.desc())
        .limit(1)
    )
    return snap.value if snap else None


@router.get("/pension")
def list_pension(db: Session = Depends(get_db)):
    products = db.scalars(select(PensionProduct)).all()
    return {"products": [pension_out(p, latest_value(db, p.account_id)) for p in products]}


@router.post("/pension")
def create_pension(body: PensionIn, db: Session = Depends(get_db)):
    acc_type = "insurance" if body.product_type == "insurance" else "pension"
    account = Account(
        name=body.name, type=acc_type, currency="ILS", institution=body.provider, product="pension",
        nw_bucket=PENSION_BUCKETS.get(body.product_type, "pension"), owner_id=body.owner_id,
    )
    db.add(account)
    db.flush()
    product = PensionProduct(account_id=account.id, **body.model_dump(exclude={"name", "owner_id"}))
    db.add(product)
    db.commit()
    return {"id": product.id, "account_id": account.id}


@router.patch("/pension/{product_id}")
def update_pension(product_id: int, body: PensionIn, db: Session = Depends(get_db)):
    p = db.get(PensionProduct, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    for key, value in body.model_dump(exclude={"name", "owner_id"}).items():
        setattr(p, key, value)
    if p.account and body.name:
        p.account.name = body.name
        p.account.institution = body.provider
        p.account.owner_id = body.owner_id
        p.account.nw_bucket = PENSION_BUCKETS.get(body.product_type, "pension")
    db.commit()
    return {"ok": True}


@router.delete("/pension/{product_id}")
def delete_pension(product_id: int, db: Session = Depends(get_db)):
    p = db.get(PensionProduct, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    account = p.account
    db.delete(p)
    if account:
        db.delete(account)
    db.commit()
    return {"ok": True}


# ---------- Properties ----------

class PropertyIn(BaseModel):
    name: str
    details: dict | None = None
    kind: str = "residence"  # residence | investment
    owner_id: int | None = None
    address: str = ""
    purchase_price: float | None = None
    purchase_date: date | None = None
    monthly_rent: float = 0.0
    income_category: str = "הכנסה משכירות - נטו"
    expense_category: str = "משכנתא / דמי שכירות"


def property_out(p: Property, current_value: float | None) -> dict:
    gross_yield = None
    if current_value and p.monthly_rent:
        gross_yield = round(12 * p.monthly_rent / current_value * 100, 2)
    return {
        "id": p.id,
        "account_id": p.account_id,
        "name": p.name,
        "address": p.address,
        "purchase_price": p.purchase_price,
        "purchase_date": p.purchase_date.isoformat() if p.purchase_date else None,
        "monthly_rent": p.monthly_rent,
        "income_category": p.income_category,
        "expense_category": p.expense_category,
        "kind": p.kind,
        "details": json.loads(p.details) if p.details else None,
        "owner_id": p.account.owner_id if p.account else None,
        "current_value": current_value,
        "gross_yield_pct": gross_yield,
    }


@router.get("/properties")
def list_properties(db: Session = Depends(get_db)):
    props = db.scalars(select(Property)).all()
    return {"properties": [property_out(p, latest_value(db, p.account_id)) for p in props]}


@router.post("/properties")
def create_property(body: PropertyIn, db: Session = Depends(get_db)):
    account = Account(
        name=body.name, type="property", currency="ILS", product="real_estate",
        nw_bucket="investment_re" if body.kind == "investment" else "residence", owner_id=body.owner_id,
    )
    db.add(account)
    db.flush()
    prop = Property(account_id=account.id, **body.model_dump(exclude={"owner_id", "details"}))
    prop.details = json.dumps(body.details, ensure_ascii=False) if body.details else ""
    db.add(prop)
    db.commit()
    return {"id": prop.id, "account_id": account.id}


@router.patch("/properties/{property_id}")
def update_property(property_id: int, body: PropertyIn, db: Session = Depends(get_db)):
    p = db.get(Property, property_id)
    if not p:
        raise HTTPException(404, "Property not found")
    for key, value in body.model_dump(exclude={"owner_id", "details"}).items():
        setattr(p, key, value)
    if body.details is not None:
        p.details = json.dumps(body.details, ensure_ascii=False)
    if p.account:
        p.account.name = body.name
        p.account.owner_id = body.owner_id
        p.account.nw_bucket = "investment_re" if body.kind == "investment" else "residence"
    db.commit()
    return {"ok": True}


@router.delete("/properties/{property_id}")
def delete_property(property_id: int, db: Session = Depends(get_db)):
    p = db.get(Property, property_id)
    if not p:
        raise HTTPException(404, "Property not found")
    account = p.account
    db.delete(p)
    if account:
        db.delete(account)
    db.commit()
    return {"ok": True}


@router.get("/properties/{property_id}/stats")
def property_stats(property_id: int, db: Session = Depends(get_db)):
    p = db.get(Property, property_id)
    if not p:
        raise HTTPException(404, "Property not found")

    def monthly(category: str):
        rows = db.execute(
            select(Transaction.month_year, func.sum(Transaction.amount))
            .where(Transaction.category == category)
            .group_by(Transaction.month_year)
            .order_by(Transaction.month_year)
        ).all()
        return {m: round(total, 2) for m, total in rows}

    income = monthly(p.income_category)
    expenses = monthly(p.expense_category)
    months = sorted(set(income) | set(expenses))
    series = [
        {"month": m, "income": income.get(m, 0.0), "expenses": abs(expenses.get(m, 0.0))}
        for m in months
    ]
    total_income = round(sum(income.values()), 2)
    total_expenses = round(abs(sum(expenses.values())), 2)
    return {
        "series": series,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net": round(total_income - total_expenses, 2),
    }
