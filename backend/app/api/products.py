"""Product pages: per-product upload (drag & drop), summary data and stored documents."""
import base64
import json
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import (
    PRODUCTS, Account, AssetSnapshot, Document, FamilyMember, Holding, InsurancePolicy, Loan, PensionProduct,
    PensionReport, Transaction,
)
from ..services.ingest import display_ref, ingest_file, logo_path, mask
from ..services.market import get_usd_ils
from ..services.networth import account_values, holding_value_ils

router = APIRouter(prefix="/api", tags=["products"])

# Upload pages that group several products (the Bank page takes every bank export)
PRODUCT_GROUPS = {"bank": ("bank_current", {"bank_current", "bank_securities", "fx", "bank_loan"})}


def _member_ok(owner_id: int | None, member: str | None) -> bool:
    if not member or member == "all":
        return True
    if member == "joint":
        return owner_id is None
    return owner_id == int(member)


async def _ingest_uploads(
    db: Session, files: list[UploadFile], product: str | None, member_id: int | None, password: str | None = None,
) -> list[dict]:
    expected = {product} if product else set()
    if product in PRODUCT_GROUPS:
        product, expected = PRODUCT_GROUPS[product]
    results = []
    for f in files:
        data = await f.read()
        name = f.filename or "upload"
        try:
            res = ingest_file(db, name, data, product_hint=product, member_id=member_id, password=password or None)
            db.commit()
            if product and res["product"] not in expected and not res.get("stored_only"):
                res["note"] = f"הקובץ זוהה כ{res.get('product_label', res['product'])} ונקלט שם"
            results.append(res)
        except Exception as e:
            db.rollback()
            results.append({"file": name, "error": str(e)})
    return results


@router.post("/products/{product}/upload")
async def upload_to_product(
    product: str,
    files: list[UploadFile] = File(...),
    member_id: int | None = Form(None),
    password: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if product not in PRODUCTS and product not in PRODUCT_GROUPS:
        raise HTTPException(404, "Unknown product")
    return {"results": await _ingest_uploads(db, files, product, member_id, password)}


@router.post("/upload")
async def upload_auto(
    files: list[UploadFile] = File(...),
    member_id: int | None = Form(None),
    password: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Global upload: product is detected from each file's content."""
    return {"results": await _ingest_uploads(db, files, None, member_id, password)}


@router.get("/products/{product}")
def product_summary(product: str, member: str | None = None, db: Session = Depends(get_db)):
    if product not in PRODUCTS:
        raise HTTPException(404, "Unknown product")
    usd_ils = get_usd_ils(db)
    accounts = [a for a in db.scalars(select(Account).where(Account.product == product)) if _member_ok(a.owner_id, member)]
    ids = [a.id for a in accounts]
    values = {r["account_id"]: r for r in account_values(db, accounts)}
    members = {m.id: m.name for m in db.scalars(select(FamilyMember))}

    out: dict = {
        "product": product,
        "label": PRODUCTS[product][0],
        "usd_ils": usd_ils,
        "accounts": [
            {
                "id": a.id, "name": a.name, "owner_id": a.owner_id, "owner": members.get(a.owner_id),
                "external_ref": display_ref(a), "nw_bucket": a.nw_bucket,
                "value_ils": values.get(a.id, {}).get("value_ils", 0.0),
            }
            for a in accounts
        ],
    }
    out["total_ils"] = round(sum(a["value_ils"] for a in out["accounts"]), 2)

    if product in ("bank_current", "credit_card"):
        txs = db.scalars(
            select(Transaction).where(Transaction.account_id.in_(ids)).order_by(Transaction.date.desc()).limit(3000)
        ).all()
        names = {a.id: a.name for a in accounts}
        out["transactions"] = [
            {
                "id": t.id, "date": t.date.isoformat(), "description": t.description, "amount": t.amount,
                "category": t.category, "sector": t.sector, "account": names.get(t.account_id, ""),
                "account_id": t.account_id, "month_year": t.month_year, "billing_cycle": t.billing_cycle,
                "balance": t.balance, "category_locked": bool(t.category_locked),
            }
            for t in txs
        ]

    if product == "trading":
        for a in out["accounts"]:
            path = logo_path(a["id"])
            if path:
                mime = "image/png" if path.endswith(".png") else "image/jpeg"
                with open(path, "rb") as f:
                    a["logo"] = f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"

    if product == "pension":
        out["pension_members"] = pension_by_member(db, accounts, members, member)

    if product in ("bank_securities", "trading", "fx"):
        holds = db.scalars(select(Holding).where(Holding.account_id.in_(ids)).order_by(Holding.account_id, Holding.symbol)).all()
        names = {a.id: a.name for a in accounts}
        rows = []
        for h in holds:
            value_native = h.quantity * h.last_price if h.last_price is not None else None
            rows.append(
                {
                    "id": h.id, "account": names.get(h.account_id, ""), "symbol": h.symbol, "name": h.name,
                    "quantity": h.quantity, "last_price": h.last_price, "currency": h.currency,
                    "cost_basis": h.cost_basis, "value_native": round(value_native, 2) if value_native is not None else None,
                    "value_ils": round(holding_value_ils(h, usd_ils), 2),
                    "gain_native": round(value_native - h.cost_basis, 2) if value_native is not None and h.cost_basis else None,
                    "asset_class": h.asset_class,
                    "price_updated_at": h.price_updated_at.isoformat() if h.price_updated_at else None,
                }
            )
        out["holdings"] = rows

    if product in ("bank_loan", "mortgage"):
        loans = db.scalars(select(Loan).where(Loan.account_id.in_(ids))).all()
        out["loans"] = [
            {
                "id": l.id, "name": l.name, "original_amount": l.original_amount, "balance": l.balance,
                "rate_text": l.rate_text, "monthly_payment": l.monthly_payment, "payments_left": l.payments_left,
                "end_date": l.end_date.isoformat() if l.end_date else None, "as_of": l.as_of.isoformat() if l.as_of else None,
            }
            for l in loans
        ]
        out["monthly_payment_total"] = round(sum(l.monthly_payment for l in loans), 2)

    if product == "insurance":
        policies = [p for p in db.scalars(select(InsurancePolicy)) if _member_ok(p.member_id, member)]
        out["policies"] = [
            {
                "id": p.id, "member_id": p.member_id, "member": members.get(p.member_id), "domain": p.domain,
                "main_branch": p.main_branch, "sub_branch": p.sub_branch, "product_type": p.product_type,
                "company": p.company, "period": p.period, "details": p.details, "premium": p.premium,
                "premium_type": p.premium_type, "policy_number": p.policy_number,
                "monthly_premium": round(p.premium / 12 if p.premium_type == "שנתית" else p.premium, 2),
                "has_id": bool(p.id_number),
                "manual": p.domain == "ידני",
            }
            for p in policies
        ]
        out["monthly_premium_total"] = round(sum(p["monthly_premium"] for p in out["policies"]), 2)

    snaps = db.scalars(
        select(AssetSnapshot).where(AssetSnapshot.account_id.in_(ids)).order_by(AssetSnapshot.date)
    ).all()
    out["snapshots"] = [
        {"id": s.id, "account_id": s.account_id, "date": s.date.isoformat(), "value": s.value, "note": s.note} for s in snaps
    ]

    docs = db.scalars(select(Document).where(Document.product == product).order_by(Document.uploaded_at.desc())).all()
    out["documents"] = [
        {
            "id": d.id, "filename": d.filename, "size": d.size, "parsed": bool(d.parsed), "summary": d.summary,
            "member": members.get(d.member_id), "uploaded_at": d.uploaded_at.isoformat(),
        }
        for d in docs
        if _member_ok(d.member_id, member)
    ]
    return out


def pension_by_member(db: Session, accounts: list[Account], members: dict[int, str], member: str | None) -> list[dict]:
    """Report summary + product lines, grouped by family member (one block per member)."""
    latest = {}
    for s in db.scalars(select(AssetSnapshot).where(AssetSnapshot.account_id.in_([a.id for a in accounts])).order_by(AssetSnapshot.date)):
        latest[s.account_id] = s
    by_owner: dict[int | None, list[dict]] = {}
    for a in accounts:
        p = db.scalar(select(PensionProduct).where(PensionProduct.account_id == a.id))
        snap = latest.get(a.id)
        by_owner.setdefault(a.owner_id, []).append(
            {
                "account_id": a.id,
                "name": p.track if p and p.track else a.name,
                "provider": p.provider if p else a.institution,
                "product_type": p.product_type if p else "",
                "policy": mask(p.policy_number) if p and p.policy_number else "",
                "balance": snap.value if snap else 0.0,
                "as_of": snap.date.isoformat() if snap else None,
                "fee_deposit_pct": p.fee_deposit_pct if p else 0.0,
                "fee_accrual_pct": p.fee_accrual_pct if p else 0.0,
                "employer": p.employer if p else "",
                "status": p.status if p else "",
                "salary": p.salary if p else 0.0,
                "projected_pension": p.projected_pension if p else 0.0,
                "last_deposit": p.last_deposit if p else "",
            }
        )
    reports = {r.member_id: r for r in db.scalars(select(PensionReport))}
    out = []
    for owner_id in sorted(by_owner, key=lambda o: (o is None, o or 0)):
        r = reports.get(owner_id)
        products = sorted(by_owner[owner_id], key=lambda x: -x["balance"])
        out.append(
            {
                "member_id": owner_id,
                "member": members.get(owner_id, "משותף") if owner_id else "משותף",
                "total": round(sum(x["balance"] for x in products), 2),
                "report": {
                    "report_date": r.report_date.isoformat() if r.report_date else None,
                    "total_savings": r.total_savings,
                    "ytd_return_pct": r.ytd_return_pct,
                    "monthly_premium": r.monthly_premium,
                    **json.loads(r.data or "{}"),
                } if r else None,
                "products": products,
            }
        )
    return out


class PolicyIn(BaseModel):
    member_id: int | None = None
    main_branch: str
    sub_branch: str = ""
    product_type: str = "פוליסת ביטוח"
    company: str = ""
    period: str = ""
    details: str = ""
    premium: float = 0.0
    premium_type: str = "חודשית"
    policy_number: str = ""


@router.post("/insurance-policies")
def add_policy(body: PolicyIn, db: Session = Depends(get_db)):
    p = InsurancePolicy(**body.model_dump(), domain="ידני", plan_class="ידני")
    db.add(p)
    db.commit()
    return {"id": p.id}


@router.delete("/insurance-policies/{policy_id}")
def delete_policy(policy_id: int, db: Session = Depends(get_db)):
    p = db.get(InsurancePolicy, policy_id)
    if not p:
        raise HTTPException(404, "Policy not found")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.get("/documents/{doc_id}/file")
def document_file(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(Document, doc_id)
    if not d or not os.path.exists(d.stored_path):
        raise HTTPException(404, "Document not found")
    return FileResponse(d.stored_path, filename=d.filename)


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    """Removes the stored file and its record (data already parsed from it stays)."""
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404, "Document not found")
    if os.path.exists(d.stored_path):
        os.remove(d.stored_path)
    db.delete(d)
    db.commit()
    return {"ok": True}


@router.patch("/holdings/{holding_id}/class")
def set_holding_class(holding_id: int, body: dict, db: Session = Depends(get_db)):
    h = db.get(Holding, holding_id)
    if not h:
        raise HTTPException(404, "Holding not found")
    h.asset_class = body.get("asset_class", "")
    db.commit()
    return {"ok": True}
