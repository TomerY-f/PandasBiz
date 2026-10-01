"""Stores parsed product files: resolves the account and owner, then upserts
transactions / holdings / loans / policies / snapshots, and keeps the original file."""
import hashlib
import json
import os
import re
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db.database import DATA_DIR
from ..db.models import (
    PRODUCTS, Account, AssetSnapshot, Document, FamilyMember, Holding, InsurancePolicy, Loan, PensionProduct,
    PensionReport, Transaction,
)
from ..ingest import etrade
from ..ingest.detect import detect_kind
from ..ingest.pension_report import PdfPasswordError, is_pension_report, parse_pension_report, pdf_text, report_as_of
from ..ingest.products import parse_file
from .categorize import Categorizer
from .market import USD_ILS_KEY, _set_setting, get_usd_ils

UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

# Products whose files carry no account reference: one account per product (+ owner).
SINGLE_ACCOUNT_PRODUCTS = {"fx", "bank_loan", "insurance", "trading", "bank_securities"}


# ---------- members ----------

def match_member(db: Session, holder: str) -> FamilyMember | None:
    """Finds a member whose name or alias appears in the holder string (e.g. 'על שם ...')."""
    holder = (holder or "").strip()
    if not holder:
        return None
    for m in db.scalars(select(FamilyMember)):
        names = [m.name] + [a.strip() for a in (m.aliases or "").split(",") if a.strip()]
        if any(n and (n == holder or n in holder.split() or n in holder) for n in names):
            return m
    return None


def member_for_holder(db: Session, holder: str) -> FamilyMember | None:
    """Matches a holder to a member, creating one (named by first name) if it's a new person."""
    if not holder:
        return None
    member = match_member(db, holder)
    if member:
        return member
    first = holder.split()[0]
    member = FamilyMember(name=first, aliases=holder)
    db.add(member)
    db.flush()
    return member


def member_for_id_number(db: Session, id_number: str) -> FamilyMember | None:
    if not id_number:
        return None
    return db.scalar(select(FamilyMember).where(FamilyMember.id_number == id_number))


# ---------- accounts ----------

def account_label(product: str, ref: str = "", meta: dict | None = None) -> str:
    label = PRODUCTS[product][0]
    if product == "credit_card":
        name = (meta or {}).get("card_name") or "כרטיס"
        return f"{name} {ref}".strip() if ref else label
    return f"{label} {ref}".strip() if ref else label


def get_or_create_account(
    db: Session, product: str, ref: str = "", owner_id: int | None = None, meta: dict | None = None,
    account_id: int | None = None,
) -> Account:
    if account_id:
        account = db.get(Account, account_id)
        if account:
            return account
    q = select(Account).where(Account.product == product)
    if ref:
        account = db.scalar(q.where(Account.external_ref == ref).limit(1))
        if not account and product in SINGLE_ACCOUNT_PRODUCTS:
            # adopt an account created earlier from a file that had no reference (e.g. a summary page)
            account = db.scalar(q.where(Account.external_ref == "").limit(1))
            if account:
                account.external_ref = ref
    elif product in SINGLE_ACCOUNT_PRODUCTS:
        candidates = list(db.scalars(q))
        account = next((a for a in candidates if a.owner_id == owner_id), candidates[0] if candidates else None)
    else:
        account = db.scalar(q.where(Account.external_ref == "").limit(1))
    if account:
        return account
    _, acc_type, bucket = PRODUCTS[product]
    name = account_label(product, ref, meta)
    base, n = name, 2
    while db.scalar(select(Account).where(Account.name == name)):
        name = f"{base} ({n})"
        n += 1
    account = Account(
        name=name, type=acc_type, currency="ILS", product=product, nw_bucket=bucket, external_ref=ref, owner_id=owner_id,
    )
    db.add(account)
    db.flush()
    return account


# ---------- writers ----------

def upsert_snapshot(db: Session, account: Account, d: date, value: float, note: str = "") -> None:
    snap = db.scalar(select(AssetSnapshot).where(AssetSnapshot.account_id == account.id, AssetSnapshot.date == d))
    if snap:
        snap.value = value
        snap.note = note or snap.note
    else:
        db.add(AssetSnapshot(account_id=account.id, date=d, value=value, note=note))


def write_transactions(db: Session, account: Account, records: list[dict]) -> dict:
    existing = {h for (h,) in db.execute(select(Transaction.dedup_hash).where(Transaction.account_id == account.id))}
    cat = Categorizer(db)
    inserted = duplicates = 0
    for rec in records:
        if rec["dedup_hash"] in existing:
            duplicates += 1
            continue
        existing.add(rec["dedup_hash"])
        tx = Transaction(account_id=account.id, **rec)
        tx.category = ""
        cat.apply(tx)
        db.add(tx)
        inserted += 1
    return {"inserted": inserted, "duplicates": duplicates}


def write_holdings(db: Session, account: Account, records: list[dict]) -> dict:
    """A positions file is the full picture of the account: holdings missing from it are removed."""
    keep = set()
    created = updated = 0
    now = datetime.utcnow()
    for rec in records:
        keep.add(rec["symbol"])
        h = db.scalar(select(Holding).where(Holding.account_id == account.id, Holding.symbol == rec["symbol"]))
        if h:
            for k, v in rec.items():
                if k == "asset_class" and h.asset_class:
                    continue  # keep a manual override
                setattr(h, k, v)
            updated += 1
        else:
            h = Holding(account_id=account.id, **rec)
            db.add(h)
            created += 1
        h.price_updated_at = now
    removed = 0
    for h in list(account.holdings):
        if h.symbol not in keep:
            db.delete(h)
            removed += 1
    return {"created": created, "updated": updated, "removed": removed}


def holdings_value_ils(db: Session, records: list[dict]) -> float:
    usd_ils = get_usd_ils(db)
    total = 0.0
    for r in records:
        value = r["quantity"] * (r["last_price"] or 0.0)
        total += value * usd_ils if r["currency"] == "USD" else value
    return round(total, 2)


def write_loans(db: Session, account: Account, records: list[dict]) -> dict:
    db.execute(delete(Loan).where(Loan.account_id == account.id))
    for rec in records:
        db.add(
            Loan(
                account_id=account.id,
                **{k: rec.get(k) for k in (
                    "name", "original_amount", "balance", "rate_text", "monthly_payment", "payments_left", "end_date", "as_of",
                )},
            )
        )
    return {"loans": len(records)}


def write_policies(db: Session, records: list[dict], member_id: int | None) -> dict:
    """Har HaBituach export = full picture per insured ID: replace that ID's policies."""
    ids = {r["id_number"] for r in records if r["id_number"]}
    for id_number in ids:
        db.execute(delete(InsurancePolicy).where(InsurancePolicy.id_number == id_number))
    for rec in records:
        member = member_for_id_number(db, rec["id_number"])
        db.add(InsurancePolicy(member_id=member.id if member else member_id, **rec))
    return {"policies": len(records)}


# ---------- documents ----------

def store_document(
    db: Session, product: str, filename: str, data: bytes, member_id: int | None = None,
    account_id: int | None = None, parsed: bool = False, summary: str = "",
) -> Document:
    sha1 = hashlib.sha1(data).hexdigest()
    doc = db.scalar(select(Document).where(Document.sha1 == sha1, Document.product == product))
    folder = os.path.join(UPLOAD_DIR, product)
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r"[\\/:*?\"<>|]", "_", os.path.basename(filename))
    path = os.path.join(folder, f"{sha1[:10]}_{safe}")
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
    if doc:
        doc.parsed = int(parsed) or doc.parsed
        doc.summary = summary or doc.summary
        doc.member_id = member_id or doc.member_id
        doc.account_id = account_id or doc.account_id
        doc.uploaded_at = datetime.utcnow()
        return doc
    doc = Document(
        product=product, member_id=member_id, account_id=account_id, filename=filename, stored_path=path,
        sha1=sha1, size=len(data), parsed=int(parsed), summary=summary,
    )
    db.add(doc)
    return doc


# ---------- broker logo (embedded image in a trading export) ----------

def logo_path(account_id: int) -> str | None:
    for ext in ("png", "jpg"):
        path = os.path.join(UPLOAD_DIR, "trading", f"logo_{account_id}.{ext}")
        if os.path.exists(path):
            return path
    return None


def save_embedded_logo(account: Account, filename: str, data: bytes) -> None:
    """Brokerage exports carry the broker's logo as an image inside the xlsx; keep it to show on the page."""
    if not filename.lower().endswith(".xlsx"):
        return
    import io
    import zipfile

    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        media = [n for n in z.namelist() if n.startswith("xl/media/") and not n.endswith("/")]
        if not media:
            return
        raw = z.read(media[0])
    except Exception:
        return
    ext = "png" if raw[:4] == b"\x89PNG" else "jpg"
    folder = os.path.join(UPLOAD_DIR, "trading")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"logo_{account.id}.{ext}"), "wb") as f:
        f.write(raw)


# ---------- entry point ----------

# קופת גמל לתגמולים is locked until retirement age → pension savings; only קופת גמל להשקעה is liquid
PENSION_BUCKETS = {"pension": "pension", "study_fund": "study_fund", "gemel": "pension"}


def mask(ref: str) -> str:
    return f"…{ref[-4:]}" if len(ref) > 4 else ref


def display_ref(account: Account) -> str:
    """Account reference for display: pension policy numbers are often the member's ID number, so mask them."""
    if account.product == "pension" and account.external_ref:
        return mask(account.external_ref.split(":")[0])
    return account.external_ref


def write_pension_report(db: Session, parsed: dict, member_id: int | None) -> dict:
    """Creates / updates one account + PensionProduct per product line, a snapshot at the report date,
    and the member's report summary."""
    member = db.get(FamilyMember, member_id) if member_id else None
    if not member and parsed["client"]:
        member = member_for_holder(db, parsed["client"])
    owner_id = member.id if member else None
    as_of = report_as_of(parsed)
    for p in parsed["products"]:
        ref = f"{p['policy_number']}:{p['type_name']}"
        account = db.scalar(select(Account).where(Account.product == "pension", Account.external_ref == ref))
        if not account:
            name = f"{p['type_name']} · {p['provider']} {mask(p['policy_number'])}"
            base, n = name, 2
            while db.scalar(select(Account).where(Account.name == name)):
                name, n = f"{base} ({n})", n + 1
            account = Account(
                name=name, type="pension", currency="ILS", institution=p["provider"], product="pension",
                nw_bucket="liquid_gemel" if "להשקעה" in p["type_name"] else PENSION_BUCKETS[p["product_type"]], external_ref=ref, owner_id=owner_id,
            )
            db.add(account)
            db.flush()
        elif owner_id:
            account.owner_id = owner_id
        prod = db.scalar(select(PensionProduct).where(PensionProduct.account_id == account.id))
        if not prod:
            prod = PensionProduct(account_id=account.id)
            db.add(prod)
        prod.provider = p["provider"]
        prod.product_type = p["product_type"]
        prod.track = p["type_name"]
        prod.fee_deposit_pct = p["fee_deposit_pct"]
        prod.fee_accrual_pct = p["fee_accrual_pct"]
        prod.policy_number = p["policy_number"]
        prod.employer = p["employer"]
        prod.status = p["status"]
        prod.salary = p["salary"]
        prod.projected_pension = p["projected_pension"]
        prod.last_deposit = p["last_deposit"]
        db.flush()
        upsert_snapshot(db, account, as_of, p["balance"], note="מדוח מסלקה")
        db.flush()
    report = db.scalar(
        select(PensionReport).where(PensionReport.member_id == owner_id) if owner_id
        else select(PensionReport).where(PensionReport.client_name == parsed["client"])
    )
    if not report:
        report = PensionReport(member_id=owner_id)
        db.add(report)
    if report.report_date and parsed["report_date"] and report.report_date > parsed["report_date"]:
        return {"products": len(parsed["products"]), "snapshot": parsed["total"]}  # an older report: keep the newer summary
    report.client_name = parsed["client"]
    report.report_date = parsed["report_date"]
    report.total_savings = parsed["total"]
    report.ytd_return_pct = parsed["ytd_return"]
    report.monthly_premium = parsed["monthly_premium"]
    report.data = json.dumps(
        {k: parsed[k] for k in ("deposits", "pension", "coverages", "mix")}, ensure_ascii=False
    )
    return {"products": len(parsed["products"]), "snapshot": parsed["total"], "owner_id": owner_id}


def ingest_file(
    db: Session, filename: str, data: bytes, product_hint: str | None = None,
    member_id: int | None = None, account_id: int | None = None, password: str | None = None,
) -> dict:
    """Parses and stores one uploaded file. Caller commits. `password` opens protected PDFs and is never stored."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        try:
            text = pdf_text(data, password)
        except PdfPasswordError:
            if product_hint == "pension":
                raise
            text = ""
        except Exception:
            text = ""
        if is_pension_report(text):
            stats = write_pension_report(db, parse_pension_report(text), member_id)
            owner_id = stats.pop("owner_id", None) or member_id
            summary = f"דוח מסלקה: {stats['products']} מוצרים, צבירה ₪{stats['snapshot']:,.0f}"
            doc = store_document(db, "pension", filename, data, owner_id, None, parsed=True, summary=summary)
            db.flush()
            owner = db.get(FamilyMember, owner_id) if owner_id else None
            return {"file": filename, "product": "pension", "product_label": PRODUCTS["pension"][0],
                    "owner": owner.name if owner else None, "document_id": doc.id, **stats}
    if lower.endswith((".pdf", ".png", ".jpg", ".jpeg")):
        product = product_hint or "manual"
        doc = store_document(db, product, filename, data, member_id, account_id, parsed=False, summary="מסמך שמור (ללא פענוח)")
        db.flush()
        return {"file": filename, "product": product, "document_id": doc.id, "stored_only": True}

    try:
        result = parse_file(filename, data, product_hint)
    except ValueError:
        if detect_kind(filename, data) == "etrade":
            recs = etrade.parse(filename, data)
            result = {"product": "trading", "meta": {"account_ref": "E-Trade"}, "transactions": [], "holdings": [
                {**r, "asset_class": "stocks"} for r in recs
            ], "loans": [], "policies": [], "snapshot": None}
        else:
            raise
    product = result["product"]
    meta = result["meta"]

    owner = db.get(FamilyMember, member_id) if member_id else None
    if not owner and meta.get("holder"):
        owner = member_for_holder(db, meta["holder"])
    owner_id = owner.id if owner else None

    stats: dict = {}
    account = None
    if product == "insurance":
        stats.update(write_policies(db, result["policies"], owner_id))
    else:
        ref = meta.get("last4") or meta.get("account_ref") or ""
        account = get_or_create_account(db, product, ref, owner_id, meta, account_id)
        if owner_id and not account.owner_id:
            account.owner_id = owner_id
        if result["transactions"]:
            stats.update(write_transactions(db, account, result["transactions"]))
            if product == "bank_current":
                # month-end balances → net-worth history for the current account
                month_end: dict[str, tuple[date, float]] = {}
                for t in result["transactions"]:
                    if t["balance"] is not None:
                        month_end[t["month_year"]] = (t["date"], t["balance"])
                for d, bal in month_end.values():
                    upsert_snapshot(db, account, d, bal, note="יתרה מתנועות")
                db.flush()
        if product == "fx":
            usd = next((h for h in result["holdings"] if h["symbol"] == "USD"), None)
            if usd and usd["last_price"]:
                _set_setting(db, USD_ILS_KEY, f"{usd['last_price']:.4f}")  # bank's representative rate
        if product == "trading":
            save_embedded_logo(account, filename, data)
        if result["holdings"]:
            stats.update(write_holdings(db, account, result["holdings"]))
            if not result["snapshot"]:
                as_of = meta.get("as_of") or date.today()
                result["snapshot"] = {"date": as_of, "value": holdings_value_ils(db, result["holdings"])}
        if result["loans"]:
            stats.update(write_loans(db, account, result["loans"]))
        snap = result["snapshot"]
        if snap and snap.get("value") is not None:
            upsert_snapshot(db, account, snap["date"], snap["value"], note=f"מקובץ {filename}")
            stats["snapshot"] = snap["value"]

    summary = ", ".join(f"{k}: {v}" for k, v in stats.items())
    doc = store_document(
        db, product, filename, data, owner_id or (account.owner_id if account else None),
        account.id if account else None, parsed=True, summary=summary,
    )
    db.flush()
    return {
        "file": filename,
        "product": product,
        "product_label": PRODUCTS[product][0],
        "account": account.name if account else None,
        "account_id": account.id if account else None,
        "owner": (db.get(FamilyMember, account.owner_id).name if account and account.owner_id else (owner.name if owner else None)),
        "document_id": doc.id,
        **stats,
    }
