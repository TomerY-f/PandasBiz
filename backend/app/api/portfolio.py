"""Accounts, holdings and market data endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import ACCOUNT_TYPES, Account, Holding
from ..services.market import get_usd_ils, refresh_prices
from ..services.networth import holding_value_ils

router = APIRouter(prefix="/api", tags=["portfolio"])


# ---------- Accounts ----------

class AccountIn(BaseModel):
    name: str
    type: str
    currency: str = "ILS"
    institution: str = ""


def account_out(a: Account) -> dict:
    return {"id": a.id, "name": a.name, "type": a.type, "currency": a.currency, "institution": a.institution}


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db)):
    return {"accounts": [account_out(a) for a in db.scalars(select(Account).order_by(Account.type, Account.name))]}


@router.post("/accounts")
def create_account(body: AccountIn, db: Session = Depends(get_db)):
    if body.type not in ACCOUNT_TYPES:
        raise HTTPException(400, f"Invalid type. Use one of: {ACCOUNT_TYPES}")
    account = Account(**body.model_dump())
    db.add(account)
    db.commit()
    return account_out(account)


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    if account.transactions:
        raise HTTPException(400, "לא ניתן למחוק חשבון עם תנועות")
    db.delete(account)
    db.commit()
    return {"ok": True}


# ---------- Holdings ----------

class HoldingIn(BaseModel):
    account_id: int
    symbol: str
    name: str = ""
    quantity: float
    cost_basis: float = 0.0
    currency: str = "USD"
    last_price: float | None = None


@router.get("/holdings")
def list_holdings(db: Session = Depends(get_db)):
    usd_ils = get_usd_ils(db)
    accounts = {a.id: a for a in db.scalars(select(Account))}
    holdings = db.scalars(select(Holding).order_by(Holding.account_id, Holding.symbol)).all()
    result = []
    for h in holdings:
        value_native = (h.quantity * h.last_price) if h.last_price is not None else None
        value_ils = holding_value_ils(h, usd_ils)
        gain = (value_native - h.cost_basis) if (value_native is not None and h.cost_basis) else None
        result.append(
            {
                "id": h.id,
                "account_id": h.account_id,
                "account_name": accounts[h.account_id].name if h.account_id in accounts else "",
                "symbol": h.symbol,
                "name": h.name,
                "quantity": h.quantity,
                "cost_basis": h.cost_basis,
                "currency": h.currency,
                "last_price": h.last_price,
                "price_updated_at": h.price_updated_at.isoformat() if h.price_updated_at else None,
                "value_native": round(value_native, 2) if value_native is not None else None,
                "value_ils": round(value_ils, 2),
                "gain_native": round(gain, 2) if gain is not None else None,
            }
        )
    total_ils = round(sum(r["value_ils"] for r in result), 2)
    return {"holdings": result, "total_ils": total_ils, "usd_ils": usd_ils}


@router.post("/holdings")
def create_holding(body: HoldingIn, db: Session = Depends(get_db)):
    h = Holding(**body.model_dump())
    db.add(h)
    db.commit()
    return {"id": h.id}


@router.patch("/holdings/{holding_id}")
def update_holding(holding_id: int, body: HoldingIn, db: Session = Depends(get_db)):
    h = db.get(Holding, holding_id)
    if not h:
        raise HTTPException(404, "Holding not found")
    for key, value in body.model_dump().items():
        setattr(h, key, value)
    db.commit()
    return {"ok": True}


@router.delete("/holdings/{holding_id}")
def delete_holding(holding_id: int, db: Session = Depends(get_db)):
    h = db.get(Holding, holding_id)
    if not h:
        raise HTTPException(404, "Holding not found")
    db.delete(h)
    db.commit()
    return {"ok": True}


# ---------- Market ----------

@router.post("/market/refresh")
def market_refresh(db: Session = Depends(get_db)):
    try:
        return refresh_prices(db)
    except Exception as e:
        raise HTTPException(502, f"שגיאה במשיכת נתוני שוק: {e}")
