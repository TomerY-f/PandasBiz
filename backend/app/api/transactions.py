"""Transactions: listing, periods, summaries, category edits, cashflow."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Account, Transaction

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def period_column(period_type: str):
    return Transaction.billing_cycle if period_type == "cycle" else Transaction.month_year


@router.get("/periods")
def list_periods(source: str | None = None, period_type: str = "month", db: Session = Depends(get_db)):
    col = period_column(period_type)
    q = select(col).distinct()
    if source:
        q = q.where(Transaction.source == source)
    periods = sorted([p for (p,) in db.execute(q)], reverse=True)
    return {"periods": periods}


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    cats = sorted([c for (c,) in db.execute(select(Transaction.category).distinct())])
    return {"categories": cats}


@router.get("")
def list_transactions(
    source: str | None = None,
    period: str | None = None,
    period_type: str = "month",
    category: str | None = None,
    member: str | None = None,
    limit: int = 2000,
    db: Session = Depends(get_db),
):
    q = select(Transaction).join(Account, Account.id == Transaction.account_id).order_by(Transaction.date.desc()).limit(limit)
    if member == "joint":
        q = q.where(Account.owner_id.is_(None))
    elif member and member != "all":
        q = q.where(Account.owner_id == int(member))
    if source:
        q = q.where(Transaction.source == source)
    if period:
        q = q.where(period_column(period_type) == period)
    if category:
        q = q.where(Transaction.category == category)
    txs = db.scalars(q).all()
    return {
        "transactions": [
            {
                "id": t.id,
                "date": t.date.isoformat(),
                "description": t.description,
                "amount": t.amount,
                "category": t.category,
                "sector": t.sector,
                "account_id": t.account_id,
                "source": t.source,
                "month_year": t.month_year,
                "billing_cycle": t.billing_cycle,
                "balance": t.balance,
                "category_locked": bool(t.category_locked),
            }
            for t in txs
        ]
    }


@router.get("/summary")
def summary_by_category(
    source: str = "credit",
    period_type: str = "month",
    periods: str | None = None,  # comma-separated
    db: Session = Depends(get_db),
):
    col = period_column(period_type)
    q = (
        select(col.label("period"), Transaction.category, func.sum(Transaction.amount).label("total"))
        .where(Transaction.source == source)
        .group_by(col, Transaction.category)
    )
    if periods:
        q = q.where(col.in_(periods.split(",")))
    rows = db.execute(q).all()
    return {
        "rows": [
            {"period": r.period, "category": r.category, "total": round(abs(r.total), 2), "signed_total": round(r.total, 2)}
            for r in rows
        ]
    }


@router.get("/cashflow")
def monthly_cashflow(source: str = "bank", db: Session = Depends(get_db)):
    income = func.sum(func.max(Transaction.amount, 0)).label("income")
    expenses = func.sum(func.min(Transaction.amount, 0)).label("expenses")
    q = (
        select(Transaction.month_year, income, expenses)
        .where(Transaction.source == source)
        .group_by(Transaction.month_year)
        .order_by(Transaction.month_year)
    )
    rows = db.execute(q).all()
    return {
        "months": [
            {
                "month": r.month_year,
                "income": round(r.income or 0, 2),
                "expenses": round(abs(r.expenses or 0), 2),
                "net": round((r.income or 0) + (r.expenses or 0), 2),
            }
            for r in rows
        ]
    }


class CategoryUpdate(BaseModel):
    category: str
    unlock: bool = False


@router.patch("/{tx_id}")
def update_category(tx_id: int, body: CategoryUpdate, db: Session = Depends(get_db)):
    tx = db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(404, "Transaction not found")
    if body.unlock:
        from ..services.categorize import Categorizer

        tx.category_locked = 0
        Categorizer(db).apply(tx)
    else:
        tx.category = body.category
        tx.category_locked = 1
    db.commit()
    return {"ok": True, "category": tx.category}
