"""Net worth by the buckets of the Hasolidit "מעקב שווי נקי" sheet, in ILS, optionally per family member."""
from calendar import monthrange
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import INTERNAL_TRANSFER, NW_BUCKETS, PRODUCTS, Account, AssetSnapshot, Holding, Transaction
from ..db.seed import SECURITIES_LINE
from .market import get_usd_ils

TYPE_LABELS = {
    "checking": "בנק ועו\"ש",
    "credit_card": "אשראי",
    "brokerage": "שוק ההון",
    "money_market": "קרן כספית",
    "pension": "קופות ופנסיות",
    "insurance": "ביטוחים",
    "property": "נדל\"ן",
    "loan": "הלוואות ומשכנתא",
    "other": "אחר",
}

LIABILITY_TYPES = {"loan", "credit_card"}


def member_accounts(db: Session, member: str | None) -> list[Account]:
    """member: None/'all' = everyone, 'joint' = accounts without an owner, or a member id."""
    q = select(Account)
    if member == "joint":
        q = q.where(Account.owner_id.is_(None))
    elif member and member != "all":
        q = q.where(Account.owner_id == int(member))
    return list(db.scalars(q))


def holding_value_ils(h: Holding, usd_ils: float) -> float:
    if h.last_price is None:
        return 0.0
    value = h.quantity * h.last_price
    if (h.currency or "ILS").upper() == "USD":
        value *= usd_ils
    return value


def account_bucket(account: Account, value: float) -> str:
    bucket = account.nw_bucket or (PRODUCTS.get(account.product, ("", "", "other_illiquid"))[2])
    if account.product == "bank_current" and value < 0:
        return "overdraft"
    return bucket


def snapshot_value(snap: AssetSnapshot, account: Account, usd_ils: float) -> float:
    return snap.value * usd_ils if (account.currency or "ILS").upper() == "USD" else snap.value


def card_value_at(snaps: list[AssetSnapshot], at: date) -> float:
    """A card statement is a liability from its purchases until its charge date (the snapshot date)."""
    upcoming = [s for s in snaps if s.date >= at and (s.date - at).days <= 45]
    return min(upcoming, key=lambda s: s.date).value if upcoming else 0.0


def bank_flows(db: Session) -> dict[str, list[Transaction]]:
    """Bank transactions that move money into an asset account, per product (negative amount = money in)."""
    txs = list(db.scalars(select(Transaction).where(Transaction.source == "bank")))
    return {
        "bank_securities": [t for t in txs if t.category == SECURITIES_LINE],
        "fx": [t for t in txs if t.category == INTERNAL_TRANSFER and "מטח" in (t.description or "")],
    }


def account_values(db: Session, accounts: list[Account], at: date | None = None) -> list[dict]:
    """Per-account value split by bucket. `at` = None means now (live holdings valuation)."""
    usd_ils = get_usd_ils(db)
    today = date.today()
    at_date = at or today
    snaps_by_account: dict[int, list[AssetSnapshot]] = defaultdict(list)
    ids = [a.id for a in accounts]
    for s in db.scalars(select(AssetSnapshot).where(AssetSnapshot.account_id.in_(ids)).order_by(AssetSnapshot.date)):
        snaps_by_account[s.account_id].append(s)

    flows = bank_flows(db) if at is not None else {}

    rows = []
    for a in accounts:
        snaps = snaps_by_account.get(a.id, [])
        parts: dict[str, float] = defaultdict(float)
        if a.product == "credit_card" or (not a.product and a.type == "credit_card"):
            value = card_value_at(snaps, at_date)
            if value:
                parts["credit_cards"] += value
        elif at is None and a.holdings:
            for h in a.holdings:
                v = holding_value_ils(h, usd_ils)
                parts[h.asset_class or account_bucket(a, v)] += v
        else:
            past = [s for s in snaps if s.date <= at_date]
            if past:
                v = snapshot_value(past[-1], a, usd_ils)
                parts[account_bucket(a, v)] += v
            elif at is not None and snaps:
                # before the first known value: start from it and undo the money that moved in since then
                # (securities bought / FX purchased from the bank account), otherwise carry it back as is
                v = snapshot_value(snaps[0], a, usd_ils)
                moved_in = sum(-t.amount for t in flows.get(a.product, []) if at_date < t.date <= snaps[0].date)
                v = max(v - moved_in, 0.0) if a.product in flows else v
                parts[account_bucket(a, v)] += v
        total = sum(parts.values())
        if not parts:
            continue
        rows.append(
            {
                "account_id": a.id,
                "name": a.name,
                "type": a.type,
                "type_label": TYPE_LABELS.get(a.type, a.type),
                "product": a.product,
                "product_label": PRODUCTS.get(a.product, (a.product,))[0],
                "owner_id": a.owner_id,
                "institution": a.institution,
                "value_ils": round(total, 2),
                "parts": {k: round(v, 2) for k, v in parts.items()},
            }
        )
    return rows


def summarize(rows: list[dict]) -> dict:
    buckets: dict[str, float] = defaultdict(float)
    for r in rows:
        for k, v in r["parts"].items():
            buckets[k] += v
    groups = {"liquid": 0.0, "illiquid": 0.0, "liability": 0.0}
    for k, v in buckets.items():
        groups[NW_BUCKETS.get(k, ("", "illiquid"))[1]] += v
    return {
        "buckets": {k: round(v, 2) for k, v in buckets.items()},
        "liquid": round(groups["liquid"], 2),
        "illiquid": round(groups["illiquid"], 2),
        "liabilities": round(groups["liability"], 2),
        "net_worth_retirement": round(groups["liquid"] + groups["liability"], 2),
        "net_worth_total": round(groups["liquid"] + groups["illiquid"] + groups["liability"], 2),
    }


RETURN_KINDS = {
    "ytd": "תשואה מתחילת השנה (דיווח משרד האוצר)",
    "since_purchase": "תשואה מאז הקנייה (אין בקובץ נתון מתחילת השנה)",
    "value_change": "שינוי בשווי מתחילת השנה (לפי עדכוני השווי)",
}


def _weighted(acc: dict, key: str, pct: float, weight: float, kind: str) -> None:
    cur = acc.setdefault(key, {"sum": 0.0, "w": 0.0, "kinds": set()})
    cur["sum"] += pct * weight
    cur["w"] += weight
    cur["kinds"].add(kind)


def _finish(acc: dict) -> dict:
    out = {}
    for k, v in acc.items():
        if v["w"] > 0:
            kinds = v["kinds"]
            kind = "ytd" if kinds == {"ytd"} else "value_change" if kinds == {"value_change"} else "since_purchase"
            out[k] = {"pct": round(v["sum"] / v["w"], 2), "kind": kind}
    return out


def asset_returns(db: Session, rows: list[dict]) -> tuple[dict, dict]:
    """Return per net-worth bucket and per product label, weighted by value:
    pension products use the report's year-to-date track returns, holdings their gain since purchase,
    real estate its value change since the end of last year."""
    from ..db.models import PensionProduct  # local import: avoid widening the module's import list
    import json

    usd_ils = get_usd_ils(db)
    by_bucket: dict = {}
    by_product: dict = {}
    year_start = date(date.today().year - 1, 12, 31)
    for r in rows:
        a = db.get(Account, r["account_id"])
        label = r["product_label"] or r["type_label"]
        if a.product == "pension":
            p = db.scalar(select(PensionProduct).where(PensionProduct.account_id == a.id))
            tracks = json.loads(p.yields)["tracks"] if p and p.yields else []
            w = sum(t["balance"] for t in tracks if t.get("ytd") is not None)
            if w:
                ytd = sum(t["ytd"] * t["balance"] for t in tracks if t.get("ytd") is not None) / w
                for bucket, value in r["parts"].items():
                    _weighted(by_bucket, bucket, ytd, value, "ytd")
                _weighted(by_product, label, ytd, r["value_ils"], "ytd")
        elif a.holdings:
            for h in a.holdings:
                if not h.cost_basis or h.last_price is None or h.asset_class == "cash":
                    continue
                native = h.quantity * h.last_price
                pct = (native / h.cost_basis - 1) * 100
                value = holding_value_ils(h, usd_ils)
                _weighted(by_bucket, h.asset_class or account_bucket(a, value), pct, value, "since_purchase")
                _weighted(by_product, label, pct, value, "since_purchase")
        elif a.product == "real_estate":
            snaps = list(db.scalars(select(AssetSnapshot).where(AssetSnapshot.account_id == a.id).order_by(AssetSnapshot.date)))
            if len(snaps) >= 1:
                before = [x for x in snaps if x.date <= year_start] or snaps[:1]
                start, now = before[-1].value, snaps[-1].value
                if start and snaps[-1].date > year_start:
                    pct = (now / start - 1) * 100
                    for bucket, value in r["parts"].items():
                        _weighted(by_bucket, bucket, pct, value, "value_change")
                    _weighted(by_product, label, pct, r["value_ils"], "value_change")
    return _finish(by_bucket), _finish(by_product)


def compute_net_worth(db: Session, member: str | None = None) -> dict:
    rows = account_values(db, member_accounts(db, member))
    s = summarize(rows)
    bucket_ret, product_ret = asset_returns(db, rows)
    by_product: dict[str, float] = defaultdict(float)
    for r in rows:
        by_product[r["product_label"] or r["type_label"]] += r["value_ils"]
    return {
        "usd_ils": get_usd_ils(db),
        "assets_total": round(s["liquid"] + s["illiquid"], 2),
        "liabilities_total": s["liabilities"],
        "net_worth": s["net_worth_total"],
        **s,
        "asset_map": [
            {"type": k, "label": NW_BUCKETS.get(k, (k,))[0], "value_ils": v}
            for k, v in sorted(s["buckets"].items(), key=lambda kv: -kv[1])
            if v > 0
        ],
        "by_product": [
            {"label": k, "value_ils": round(v, 2), "return": product_ret.get(k)}
            for k, v in sorted(by_product.items(), key=lambda kv: -kv[1])
        ],
        "bucket_returns": bucket_ret,
        "return_kinds": RETURN_KINDS,
        "breakdown": sorted(rows, key=lambda b: -b["value_ils"]),
    }


def month_ends(start: date, end: date) -> list[date]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(date(y, m, monthrange(y, m)[1]))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def net_worth_history(db: Session, member: str | None = None) -> list[dict]:
    """Month-end series of every bucket, built from snapshots (forward-filled per account)."""
    accounts = member_accounts(db, member)
    ids = [a.id for a in accounts]
    first = db.scalar(select(AssetSnapshot.date).where(AssetSnapshot.account_id.in_(ids)).order_by(AssetSnapshot.date).limit(1))
    if not first:
        return []
    today = date.today()
    series = []
    for end in month_ends(first, today):
        at = min(end, today)
        s = summarize(account_values(db, accounts, at=at))
        series.append({"month": end.strftime("%Y-%m"), **s})
    for i, row in enumerate(series):
        prev = series[i - 1]["net_worth_retirement"] if i else None
        row["change"] = round(row["net_worth_retirement"] - prev, 2) if prev is not None else None
        row["change_pct"] = (
            round((1 - prev / row["net_worth_retirement"]) * 100, 2)
            if prev is not None and row["net_worth_retirement"] else None
        )
    return series


def record_current_snapshots(db: Session) -> int:
    """Stores today's live value of holdings-valued accounts so history keeps a monthly point."""
    usd_ils = get_usd_ils(db)
    count = 0
    today = date.today()
    for a in db.scalars(select(Account)):
        if not a.holdings:
            continue
        value = round(sum(holding_value_ils(h, usd_ils) for h in a.holdings), 2)
        snap = db.scalar(select(AssetSnapshot).where(AssetSnapshot.account_id == a.id, AssetSnapshot.date == today))
        if snap:
            snap.value = value
        else:
            db.add(AssetSnapshot(account_id=a.id, date=today, value=value, note="צילום מצב"))
        count += 1
    db.commit()
    return count
