"""The dashboard "sheets": income & expenses, net worth, and calculator inputs."""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import NW_BUCKETS, Account
from ..services.ingest import upsert_snapshot
from ..services.networth import compute_net_worth, net_worth_history, record_current_snapshots
from ..services.sheets import income_expense_sheet, personal_inflation

router = APIRouter(prefix="/api/sheets", tags=["sheets"])


@router.get("/income-expense")
def income_expense(end: str | None = None, member: str | None = None, months: int = 12, db: Session = Depends(get_db)):
    return income_expense_sheet(db, end, member, months)


@router.get("/networth")
def networth(member: str | None = None, monthly_need: float | None = None, db: Session = Depends(get_db)):
    current = compute_net_worth(db, member)
    history = net_worth_history(db, member)
    if monthly_need is None:
        sheet = income_expense_sheet(db, None, member)
        avg = next((s for s in sheet["summary"] if s["month"] == "avg"), None)
        monthly_need = avg["expenses"] if avg and avg["expenses"] > 0 else None
    nw = current["net_worth_retirement"]
    return {
        "current": current,
        "history": history,
        "monthly_need": monthly_need,
        "years_of_living": round(nw / (12 * monthly_need), 1) if monthly_need else None,
        "withdraw_4pct_monthly": round(0.04 * nw / 12, 0),
        "withdraw_3pct_monthly": round(0.03 * nw / 12, 0),
        "buckets": [{"key": k, "label": v[0], "group": v[1]} for k, v in NW_BUCKETS.items()],
    }


@router.post("/networth/record")
def networth_record(db: Session = Depends(get_db)):
    return {"recorded": record_current_snapshots(db)}


@router.get("/inflation")
def inflation(end: str | None = None, member: str | None = None, db: Session = Depends(get_db)):
    return personal_inflation(db, end, member)


@router.get("/calculator-defaults")
def calculator_defaults(member: str | None = None, db: Session = Depends(get_db)):
    """Real averages used to pre-fill the FIRE calculators."""
    sheet = income_expense_sheet(db, None, member)
    avg = next((s for s in sheet["summary"] if s["month"] == "avg"), None) or {}
    current = compute_net_worth(db, member)
    return {
        "avg_income": avg.get("income", 0.0),
        "avg_expenses": avg.get("expenses", 0.0),
        "avg_needs": avg.get("needs", 0.0),
        "avg_wants": avg.get("wants", 0.0),
        "net_worth_retirement": current["net_worth_retirement"],
        "car_value": current["buckets"].get("car", 0.0),
        "active_months": sheet.get("active_months", 0),
    }


# ---------- manual net-worth items (car, metals, other assets / liabilities) ----------

class ManualItemIn(BaseModel):
    name: str
    nw_bucket: str
    value: float
    date: dt.date | None = None
    owner_id: int | None = None


@router.post("/manual-items")
def create_manual_item(body: ManualItemIn, db: Session = Depends(get_db)):
    if body.nw_bucket not in NW_BUCKETS:
        raise HTTPException(400, "Unknown bucket")
    if db.query(Account).filter(Account.name == body.name).first():
        raise HTTPException(400, "כבר קיים פריט בשם הזה")
    is_liability = NW_BUCKETS[body.nw_bucket][1] == "liability"
    account = Account(
        name=body.name, type="loan" if is_liability else "other", product="manual", nw_bucket=body.nw_bucket,
        owner_id=body.owner_id,
    )
    db.add(account)
    db.flush()
    value = -abs(body.value) if is_liability else body.value
    upsert_snapshot(db, account, body.date or dt.date.today(), value, note="ידני")
    db.commit()
    return {"account_id": account.id}
