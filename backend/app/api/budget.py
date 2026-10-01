"""Budgets and category rules."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Budget, CategoryRule, Transaction
from ..services.categorize import reapply_all

router = APIRouter(prefix="/api", tags=["budget"])


# ---------- Budgets ----------

class BudgetIn(BaseModel):
    category: str
    monthly_limit: float


@router.get("/budgets")
def list_budgets(db: Session = Depends(get_db)):
    budgets = db.scalars(select(Budget).order_by(Budget.category)).all()
    return {"budgets": [{"id": b.id, "category": b.category, "monthly_limit": b.monthly_limit} for b in budgets]}


@router.post("/budgets")
def upsert_budget(body: BudgetIn, db: Session = Depends(get_db)):
    b = db.scalar(select(Budget).where(Budget.category == body.category))
    if b:
        b.monthly_limit = body.monthly_limit
    else:
        b = Budget(**body.model_dump())
        db.add(b)
    db.commit()
    return {"id": b.id}


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: int, db: Session = Depends(get_db)):
    b = db.get(Budget, budget_id)
    if not b:
        raise HTTPException(404, "Budget not found")
    db.delete(b)
    db.commit()
    return {"ok": True}


@router.get("/budgets/status")
def budget_status(period: str, period_type: str = "cycle", db: Session = Depends(get_db)):
    """Spend (expenses only) per budgeted category in a given period."""
    col = Transaction.billing_cycle if period_type == "cycle" else Transaction.month_year
    spent_rows = db.execute(
        select(Transaction.category, func.sum(Transaction.amount))
        .where(col == period, Transaction.amount < 0)
        .group_by(Transaction.category)
    ).all()
    spent = {cat: abs(total) for cat, total in spent_rows}

    budgets = db.scalars(select(Budget)).all()
    status = []
    for b in budgets:
        used = round(spent.get(b.category, 0.0), 2)
        status.append(
            {
                "category": b.category,
                "limit": b.monthly_limit,
                "spent": used,
                "pct": round(used / b.monthly_limit * 100, 1) if b.monthly_limit else 0,
                "over": used > b.monthly_limit,
            }
        )
    return {"period": period, "status": sorted(status, key=lambda s: -s["pct"])}


# ---------- Category rules ----------

class RuleIn(BaseModel):
    pattern: str
    category: str
    priority: int = 0
    direction: str = ""  # "" | "in" | "out"


@router.get("/rules")
def list_rules(db: Session = Depends(get_db)):
    rules = db.scalars(select(CategoryRule).order_by(CategoryRule.priority.desc(), CategoryRule.id)).all()
    return {
        "rules": [
            {"id": r.id, "pattern": r.pattern, "category": r.category, "priority": r.priority, "direction": r.direction}
            for r in rules
        ]
    }


@router.post("/rules")
def create_rule(body: RuleIn, db: Session = Depends(get_db)):
    r = CategoryRule(**body.model_dump())
    db.add(r)
    db.commit()
    changed = reapply_all(db)
    return {"id": r.id, "changed": changed}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    r = db.get(CategoryRule, rule_id)
    if not r:
        raise HTTPException(404, "Rule not found")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.post("/rules/apply")
def apply_rules(db: Session = Depends(get_db)):
    changed = reapply_all(db)
    return {"changed": changed}
