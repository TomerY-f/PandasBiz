"""The "מעקב הכנסות והוצאות" sheet computed from transactions + manual monthly entries."""
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import LINE_GROUPS, Account, BudgetLine, MonthlyEntry, Transaction

EXPENSE_GROUPS = ["need_fixed", "need_variable", "want_fixed", "want_variable", "uncategorized"]
NEED_GROUPS = {"need_fixed", "need_variable"}
WANT_GROUPS = {"want_fixed", "want_variable", "uncategorized"}
SAVING_GROUPS = {"saving_gross", "saving_net"}


def shift_month(month: str, delta: int) -> str:
    y, m = map(int, month.split("-"))
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12}-{idx % 12 + 1:02d}"


def month_window(end: str, count: int = 12) -> list[str]:
    return [shift_month(end, -i) for i in range(count - 1, -1, -1)]


def _member_filter(q, member: str | None):
    if member == "joint":
        return q.where(Account.owner_id.is_(None))
    if member and member != "all":
        return q.where(Account.owner_id == int(member))
    return q


def latest_month(db: Session) -> str | None:
    return db.scalar(select(func.max(Transaction.month_year)))


def line_month_totals(db: Session, months: list[str], member: str | None) -> dict[tuple[str, str], float]:
    """Signed sum of transactions per (line, month)."""
    q = (
        select(Transaction.category, Transaction.month_year, func.sum(Transaction.amount))
        .join(Account, Account.id == Transaction.account_id)
        .where(Transaction.month_year.in_(months))
        .group_by(Transaction.category, Transaction.month_year)
    )
    return {(c, m): v for c, m, v in db.execute(_member_filter(q, member))}


def manual_totals(db: Session, months: list[str], member: str | None) -> dict[tuple[str, str], float]:
    q = select(MonthlyEntry).where(MonthlyEntry.month.in_(months))
    if member == "joint":
        q = q.where(MonthlyEntry.member_id.is_(None))
    elif member and member != "all":
        q = q.where(MonthlyEntry.member_id == int(member))
    out: dict[tuple[str, str], float] = defaultdict(float)
    for e in db.scalars(q):
        out[(e.line, e.month)] += e.amount
    return out


def income_expense_sheet(db: Session, end: str | None = None, member: str | None = None, count: int = 12) -> dict:
    end = end or latest_month(db)
    if not end:
        return {"months": [], "groups": [], "summary": [], "active_months": 0}
    months = month_window(end, count)
    tx = line_month_totals(db, months, member)
    manual = manual_totals(db, months, member)
    active = sorted({m for (_, m) in tx} | {m for (_, m) in manual})
    n_active = max(len(active), 1)

    lines = list(db.scalars(select(BudgetLine).order_by(BudgetLine.sort, BudgetLine.id)))
    known = {line.name for line in lines}
    # categories that exist on transactions but aren't lines (legacy / user-typed) → show under uncategorized
    extra = sorted({c for (c, _) in tx if c and c not in known})

    groups = []
    group_month_totals: dict[str, dict[str, float]] = {}
    for gkey, glabel in LINE_GROUPS.items():
        glines = [line.name for line in lines if line.group == gkey] + (extra if gkey == "uncategorized" else [])
        rows = []
        totals = defaultdict(float)
        for name in glines:
            values = {}
            for m in months:
                raw = tx.get((name, m), 0.0)
                v = raw if gkey in ("income",) else -raw
                if gkey == "excluded":
                    v = raw
                v += manual.get((name, m), 0.0)
                if v:
                    values[m] = round(v, 2)
                    totals[m] += v
            total = sum(values.values())
            avg = total / n_active
            rows.append(
                {
                    "name": name,
                    "values": values,
                    "manual": {m: manual[(name, m)] for m in months if (name, m) in manual},
                    "total": round(total, 2),
                    "avg": round(avg, 2),
                    "need_4pct": round(avg * 300, 0),
                    "need_3pct": round(avg * 400, 0),
                }
            )
        gtotal = sum(totals.values())
        groups.append(
            {
                "key": gkey,
                "label": glabel,
                "lines": rows,
                "totals": {m: round(v, 2) for m, v in totals.items()},
                "total": round(gtotal, 2),
                "avg": round(gtotal / n_active, 2),
                "need_4pct": round(sum(r["need_4pct"] for r in rows), 0),
                "need_3pct": round(sum(r["need_3pct"] for r in rows), 0),
            }
        )
        group_month_totals[gkey] = totals

    summary = []
    for m in months + ["avg"]:
        if m == "avg":
            income = sum(g["avg"] for g in groups if g["key"] == "income")
            needs = sum(g["avg"] for g in groups if g["key"] in NEED_GROUPS)
            wants = sum(g["avg"] for g in groups if g["key"] in WANT_GROUPS)
            savings = sum(g["avg"] for g in groups if g["key"] in SAVING_GROUPS)
        else:
            income = group_month_totals["income"].get(m, 0.0)
            needs = sum(group_month_totals[g].get(m, 0.0) for g in NEED_GROUPS)
            wants = sum(group_month_totals[g].get(m, 0.0) for g in WANT_GROUPS)
            savings = sum(group_month_totals[g].get(m, 0.0) for g in SAVING_GROUPS)
        expenses = needs + wants
        summary.append(
            {
                "month": m,
                "income": round(income, 2),
                "needs": round(needs, 2),
                "wants": round(wants, 2),
                "expenses": round(expenses, 2),
                "balance": round(income - expenses, 2),
                "savings_rate": round((1 - expenses / income) * 100, 1) if income else None,
                "savings": round(savings, 2),
            }
        )

    need_4 = sum(g["need_4pct"] for g in groups if g["key"] in NEED_GROUPS | WANT_GROUPS)
    need_3 = sum(g["need_3pct"] for g in groups if g["key"] in NEED_GROUPS | WANT_GROUPS)
    return {
        "months": months,
        "active_months": len(active),
        "groups": groups,
        "summary": summary,
        "retirement_need_4pct": need_4,
        "retirement_need_3pct": need_3,
    }


def personal_inflation(db: Session, end: str | None = None, member: str | None = None) -> dict:
    """Average monthly spend per CPI group: the last 12 months vs the 12 before."""
    end = end or latest_month(db)
    if not end:
        return {"groups": []}
    cur_months = month_window(end, 12)
    prev_months = month_window(shift_month(end, -12), 12)
    line_cpi = {line.name: line.cpi_group for line in db.scalars(select(BudgetLine)) if line.cpi_group}

    def averages(months: list[str]) -> tuple[dict[str, float], int]:
        tx = line_month_totals(db, months, member)
        manual = manual_totals(db, months, member)
        sums: dict[str, float] = defaultdict(float)
        active = {m for (_, m) in tx} | {m for (_, m) in manual}
        for (line, _), v in tx.items():
            if line in line_cpi:
                sums[line_cpi[line]] += -v
        for (line, _), v in manual.items():
            if line in line_cpi:
                sums[line_cpi[line]] += v
        n = max(len(active), 1)
        return {k: round(v / n, 0) for k, v in sums.items()}, len(active)

    cur, n_cur = averages(cur_months)
    prev, n_prev = averages(prev_months)
    from ..db.seed import CPI_GROUPS

    return {
        "current_period": f"{cur_months[0]} – {cur_months[-1]}",
        "previous_period": f"{prev_months[0]} – {prev_months[-1]}",
        "current_months_with_data": n_cur,
        "previous_months_with_data": n_prev,
        "groups": [{"group": g, "previous": prev.get(g, 0.0), "current": cur.get(g, 0.0)} for g in CPI_GROUPS],
    }
