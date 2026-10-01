"""Main dashboard aggregate: net worth, asset map, history, cashflow, budget alerts."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Budget, Transaction
from ..services.networth import compute_net_worth, net_worth_history

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(member: str | None = None, db: Session = Depends(get_db)):
    net = compute_net_worth(db, member)
    history = [
        {"month": h["month"], "value_ils": h["net_worth_total"], "retirement": h["net_worth_retirement"]}
        for h in net_worth_history(db, member)
    ]

    # last 12 months bank cashflow
    cashflow_rows = db.execute(
        select(
            Transaction.month_year,
            func.sum(func.max(Transaction.amount, 0)),
            func.sum(func.min(Transaction.amount, 0)),
        )
        .where(Transaction.source == "bank", Transaction.category != "העברה פנימית")
        .group_by(Transaction.month_year)
        .order_by(Transaction.month_year.desc())
        .limit(12)
    ).all()
    cashflow = [
        {"month": m, "income": round(inc or 0, 2), "expenses": round(abs(exp or 0), 2)}
        for m, inc, exp in reversed(cashflow_rows)
    ]

    # budget alerts for the latest billing cycle
    latest_cycle = db.scalar(
        select(Transaction.billing_cycle).order_by(Transaction.date.desc()).limit(1)
    )
    alerts = []
    if latest_cycle:
        spent_rows = db.execute(
            select(Transaction.category, func.sum(Transaction.amount))
            .where(Transaction.billing_cycle == latest_cycle, Transaction.amount < 0)
            .group_by(Transaction.category)
        ).all()
        spent = {cat: abs(total) for cat, total in spent_rows}
        for b in db.scalars(select(Budget)):
            used = spent.get(b.category, 0.0)
            if b.monthly_limit and used / b.monthly_limit >= 0.85:
                alerts.append(
                    {
                        "category": b.category,
                        "spent": round(used, 2),
                        "limit": b.monthly_limit,
                        "over": used > b.monthly_limit,
                    }
                )

    return {
        **net,
        "history": history,
        "cashflow": cashflow,
        "budget_alerts": alerts,
        "latest_cycle": latest_cycle,
    }
