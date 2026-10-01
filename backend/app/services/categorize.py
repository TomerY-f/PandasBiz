"""Transaction categorization onto budget lines.

Order: locked (manual) > description rule (with optional in/out direction) > card sector map > default.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import UNCATEGORIZED, CategoryRule, SectorMap, Transaction

DEFAULT_INCOME_LINE = "הכנסה אחרת / חד פעמית"


class Categorizer:
    def __init__(self, db: Session):
        self.rules = list(db.scalars(select(CategoryRule).order_by(CategoryRule.priority.desc(), CategoryRule.id)))
        self.sectors = {m.sector: m.line for m in db.scalars(select(SectorMap))}

    def line_for(self, description: str, amount: float, sector: str = "") -> str:
        for rule in self.rules:
            if not rule.pattern or rule.pattern not in (description or ""):
                continue
            if rule.direction == "in" and amount <= 0:
                continue
            if rule.direction == "out" and amount >= 0:
                continue
            return rule.category
        if sector and sector in self.sectors:
            return self.sectors[sector]
        if amount > 0 and not sector:
            return DEFAULT_INCOME_LINE
        return UNCATEGORIZED

    def apply(self, tx: Transaction) -> bool:
        """Returns True if the category changed."""
        if tx.category_locked:
            return False
        line = self.line_for(tx.description, tx.amount, tx.sector or "")
        if line != tx.category:
            tx.category = line
            return True
        return False


def get_rules(db: Session) -> list[CategoryRule]:
    return list(db.scalars(select(CategoryRule).order_by(CategoryRule.priority.desc(), CategoryRule.id)))


def reapply_all(db: Session) -> int:
    """Re-runs rules and sector map over all non-locked transactions. Returns count changed."""
    cat = Categorizer(db)
    changed = sum(1 for tx in db.scalars(select(Transaction)) if cat.apply(tx))
    db.commit()
    return changed
