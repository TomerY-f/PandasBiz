"""Family members, account ownership, budget lines, sector mapping, manual monthly entries, settings."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import (
    LINE_GROUPS, NW_BUCKETS, PRODUCTS, UNCATEGORIZED, Account, BudgetLine, FamilyMember, InsurancePolicy,
    MonthlyEntry, SectorMap, Setting, Transaction,
)
from ..services.categorize import reapply_all
from ..services.ingest import display_ref

router = APIRouter(prefix="/api", tags=["family"])


# ---------- metadata ----------

@router.get("/meta")
def meta():
    return {
        "products": [{"key": k, "label": v[0], "type": v[1], "bucket": v[2]} for k, v in PRODUCTS.items()],
        "buckets": [{"key": k, "label": v[0], "group": v[1]} for k, v in NW_BUCKETS.items()],
        "line_groups": [{"key": k, "label": v} for k, v in LINE_GROUPS.items()],
    }


# ---------- members ----------

class MemberIn(BaseModel):
    name: str
    role: str = "adult"
    id_number: str = ""
    aliases: str = ""
    color: str = "#6C5CE7"


def member_out(m: FamilyMember) -> dict:
    return {"id": m.id, "name": m.name, "role": m.role, "id_number": m.id_number, "aliases": m.aliases, "color": m.color}


def relink_policies(db: Session) -> None:
    """Assigns insurance policies to members by ID number."""
    by_id = {m.id_number: m.id for m in db.scalars(select(FamilyMember)) if m.id_number}
    for p in db.scalars(select(InsurancePolicy)):
        if p.id_number in by_id:
            p.member_id = by_id[p.id_number]


@router.get("/members")
def list_members(db: Session = Depends(get_db)):
    return {"members": [member_out(m) for m in db.scalars(select(FamilyMember).order_by(FamilyMember.id))]}


@router.post("/members")
def create_member(body: MemberIn, db: Session = Depends(get_db)):
    if db.scalar(select(FamilyMember).where(FamilyMember.name == body.name)):
        raise HTTPException(400, "כבר קיים בן משפחה בשם הזה")
    m = FamilyMember(**body.model_dump())
    db.add(m)
    db.flush()
    relink_policies(db)
    db.commit()
    return member_out(m)


@router.patch("/members/{member_id}")
def update_member(member_id: int, body: MemberIn, db: Session = Depends(get_db)):
    m = db.get(FamilyMember, member_id)
    if not m:
        raise HTTPException(404, "Member not found")
    for k, v in body.model_dump().items():
        setattr(m, k, v)
    relink_policies(db)
    db.commit()
    return member_out(m)


@router.delete("/members/{member_id}")
def delete_member(member_id: int, db: Session = Depends(get_db)):
    m = db.get(FamilyMember, member_id)
    if not m:
        raise HTTPException(404, "Member not found")
    for a in db.scalars(select(Account).where(Account.owner_id == member_id)):
        a.owner_id = None
    for p in db.scalars(select(InsurancePolicy).where(InsurancePolicy.member_id == member_id)):
        p.member_id = None
    db.delete(m)
    db.commit()
    return {"ok": True}


# ---------- accounts (ownership / bucket) ----------

class AccountPatch(BaseModel):
    name: str | None = None
    owner_id: int | None = None
    nw_bucket: str | None = None
    clear_owner: bool = False


@router.get("/family-accounts")
def family_accounts(db: Session = Depends(get_db)):
    rows = []
    for a in db.scalars(select(Account).order_by(Account.product, Account.name)):
        rows.append(
            {
                "id": a.id, "name": a.name, "type": a.type, "product": a.product,
                "product_label": PRODUCTS.get(a.product, (a.product,))[0], "nw_bucket": a.nw_bucket,
                "owner_id": a.owner_id, "external_ref": display_ref(a),
            }
        )
    return {"accounts": rows}


@router.patch("/family-accounts/{account_id}")
def patch_account(account_id: int, body: AccountPatch, db: Session = Depends(get_db)):
    a = db.get(Account, account_id)
    if not a:
        raise HTTPException(404, "Account not found")
    if body.name:
        a.name = body.name
    if body.clear_owner:
        a.owner_id = None
    elif body.owner_id is not None:
        a.owner_id = body.owner_id
    if body.nw_bucket:
        if body.nw_bucket not in NW_BUCKETS:
            raise HTTPException(400, "Unknown bucket")
        a.nw_bucket = body.nw_bucket
    db.commit()
    return {"ok": True}


# ---------- budget lines & sector map ----------

class LineIn(BaseModel):
    name: str
    group: str


@router.get("/lines")
def list_lines(db: Session = Depends(get_db)):
    lines = db.scalars(select(BudgetLine).order_by(BudgetLine.sort, BudgetLine.id)).all()
    return {"lines": [{"id": l.id, "name": l.name, "group": l.group, "cpi_group": l.cpi_group} for l in lines]}


@router.post("/lines")
def create_line(body: LineIn, db: Session = Depends(get_db)):
    if body.group not in LINE_GROUPS:
        raise HTTPException(400, "Unknown group")
    if db.scalar(select(BudgetLine).where(BudgetLine.name == body.name)):
        raise HTTPException(400, "שורה בשם הזה כבר קיימת")
    max_sort = db.scalar(select(func.max(BudgetLine.sort))) or 0
    line = BudgetLine(name=body.name, group=body.group, sort=max_sort + 1)
    db.add(line)
    db.commit()
    return {"id": line.id}


class SectorIn(BaseModel):
    sector: str
    line: str


@router.get("/sectors")
def list_sectors(db: Session = Depends(get_db)):
    mapped = {m.sector: m.line for m in db.scalars(select(SectorMap))}
    counts = dict(
        db.execute(select(Transaction.sector, func.count()).where(Transaction.sector != "").group_by(Transaction.sector)).all()
    )
    sectors = sorted(set(mapped) | set(counts), key=lambda s: -counts.get(s, 0))
    return {"sectors": [{"sector": s, "line": mapped.get(s, ""), "count": counts.get(s, 0)} for s in sectors]}


@router.put("/sectors")
def upsert_sector(body: SectorIn, db: Session = Depends(get_db)):
    m = db.scalar(select(SectorMap).where(SectorMap.sector == body.sector))
    if m:
        m.line = body.line
    else:
        db.add(SectorMap(sector=body.sector, line=body.line))
    db.commit()
    changed = reapply_all(db)
    return {"ok": True, "changed": changed}


@router.get("/uncategorized")
def top_uncategorized(limit: int = 40, db: Session = Depends(get_db)):
    """Most frequent descriptions still on the 'unclassified' / default-income lines — candidates for rules."""
    rows = db.execute(
        select(Transaction.description, Transaction.category, func.count(), func.sum(Transaction.amount))
        .where(Transaction.category.in_([UNCATEGORIZED, "הכנסה אחרת / חד פעמית"]), Transaction.category_locked == 0)
        .group_by(Transaction.description, Transaction.category)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return {
        "items": [
            {"description": d, "category": c, "count": n, "total": round(t or 0, 2)} for d, c, n, t in rows
        ]
    }


# ---------- manual monthly entries ----------

class EntryIn(BaseModel):
    line: str
    month: str
    amount: float
    member_id: int | None = None
    note: str = ""


@router.put("/entries")
def upsert_entry(body: EntryIn, db: Session = Depends(get_db)):
    q = select(MonthlyEntry).where(MonthlyEntry.line == body.line, MonthlyEntry.month == body.month)
    q = q.where(MonthlyEntry.member_id == body.member_id) if body.member_id else q.where(MonthlyEntry.member_id.is_(None))
    e = db.scalar(q)
    if body.amount == 0:
        if e:
            db.delete(e)
        db.commit()
        return {"ok": True}
    if e:
        e.amount = body.amount
        e.note = body.note
    else:
        db.add(MonthlyEntry(**body.model_dump()))
    db.commit()
    return {"ok": True}


# ---------- key/value settings (calculator inputs etc.) ----------

@router.get("/settings/{key}")
def get_setting(key: str, db: Session = Depends(get_db)):
    s = db.get(Setting, f"ui:{key}")
    return {"value": json.loads(s.value) if s else None}


@router.put("/settings/{key}")
def put_setting(key: str, body: dict, db: Session = Depends(get_db)):
    from datetime import datetime

    s = db.get(Setting, f"ui:{key}")
    raw = json.dumps(body.get("value"), ensure_ascii=False)
    if s:
        s.value = raw
        s.updated_at = datetime.utcnow()
    else:
        db.add(Setting(key=f"ui:{key}", value=raw, updated_at=datetime.utcnow()))
    db.commit()
    return {"ok": True}
