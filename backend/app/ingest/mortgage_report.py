"""Mortgage payoff report PDF ("פרטי משכנתא כולל יתרה לסילוק", Discount bank's mortgages_world_*.pdf).

One block per loan (track) with a "general details" column and a "payoff details" column. pypdf's
layout mode keeps the two columns apart but returns Hebrew in visual order (reversed, mirrored
parentheses), so labels are matched in reversed form and Hebrew values are flipped back.
"""
import io
import re
from datetime import date

from .common import to_date, to_number

TITLE = "פרטי משכנתא כולל יתרה לסילוק"


def _rev(s: str) -> str:
    return s[::-1].translate(str.maketrans("()", ")("))


LABELS = [  # normal order; matched against the reversed layout text
    # payoff column
    "מדד בסיס", "מדד נוכחי ידוע", "ריבית ממוצעת", "יתרת תקופה בחודשים", "חיוב אחרון בהלוואה", "יתרת קרן",
    "יתרת הצמדת קרן", "ריבית צבורה", "הצמדת ריבית", "יתרת פיגור", "ריבית פיגורים", 'סה"כ יתרה', 'סה"כ יתרה לסילוק',
    "עמלה תפעולית", "עמלת מדד ממוצע", "עמלת פערי ריבית", "עמלת העדר הודעה מוקדמת", 'סה"כ עמלת פרעון מוקדם',
    # general column
    "סוג הלוואה", "סוג ריבית", "שיטת פרעון", "תאריך מתן הלוואה", "סכום מקורי", "מועד תשלום ראשון",
    "מועד תשלום אחרון", "שיעור ריבית שנתית", "בסיס לקביעת ריבית", "ריבית בסיס(עוגן)מקורית",
    "ריבית בסיס(עוגן)עדכנית", "שיעור תוספת/הפחתה", "ריבית מתואמת מקורית", "ריבית מתואמת עדכנית",
    "תדירות שינוי ריבית", "תאריך שינוי קרוב", "מטרת הלוואה",
]
_REV_LABELS = sorted(((_rev(l), l) for l in LABELS), key=lambda p: -len(p[0]))
_HEB = re.compile(r"[֐-׿]")
_LOAN_NO = re.compile(r"(\d-\d{3}-(\d{4})-\d{2}-(\d{6}))\s*:")


def is_mortgage_report(text: str) -> bool:
    return TITLE in text or _rev(TITLE) in text


def layout_text(data: bytes, password: str | None = None) -> str:
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        reader.decrypt(password or "")
    return "\n".join((p.extract_text(extraction_mode="layout") or "") for p in reader.pages)


def _fields(block: str) -> dict:
    out = {}
    for line in block.splitlines():
        for seg in line.split("|"):
            seg = re.sub(r"^\s*-{3,}|-{3,}\s*$", "", seg).strip(" *")
            for rlabel, label in _REV_LABELS:
                if seg.endswith(rlabel) and (len(seg) == len(rlabel) or seg[-len(rlabel) - 1] == " "):
                    value = seg[: -len(rlabel)].strip(" *")
                    if _HEB.search(value) and not re.search(r"\d", value):
                        value = _rev(value)
                    out.setdefault(label, value)
                    break
    return out


def _num(v: str | None) -> float | None:
    return None if not v or set(v) <= {"-"} else to_number(v)


def _date(v: str | None) -> date | None:
    m = re.search(r"\d{2}/\d{2}/\d{2,4}", v or "")
    return to_date(m.group(0)) if m else None


def _months(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def _track(f: dict) -> tuple[str, str]:
    """(track type, rate text) in the bank's own terms."""
    kind = f.get("סוג ריבית", "")
    rate = _num(f.get("שיעור ריבית שנתית")) or 0.0
    linked = "לא צמוד" not in kind
    if "פריים" in f.get("בסיס לקביעת ריבית", ""):
        spread = _num(f.get("שיעור תוספת/הפחתה")) or 0.0
        return "פריים", f"P{spread:+g}% {rate:g}%"
    if "משתנה" in kind:
        months = _num(f.get("תדירות שינוי ריבית"))
        every = f" כל {months / 12:g} שנים" if months else ""
        return f"משתנה{every}, {'צמודה' if linked else 'לא צמודה'}", f"{rate:g}%"
    return f"קבועה, {'צמודה' if linked else 'לא צמודה'}", f"{rate:g}%"


def parse_mortgage_report(data: bytes, password: str | None = None) -> dict:
    text = layout_text(data, password)
    head = text[:3000]
    m = re.search(r"(\d{6,})\s*:" + re.escape(_rev("מס' חשבון")), head)
    ref = m.group(1) if m else ""
    m = re.search(r"\d{2}/\d{2}/\d{4}", head)
    as_of = to_date(m.group(0)) if m else date.today()

    loans = []
    marks = list(_LOAN_NO.finditer(text))
    for i, mark in enumerate(marks):
        block = text[mark.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        f = _fields(block)
        balance = _num(f.get('סה"כ יתרה'))
        if not balance:  # paid-off track
            continue
        first, last = _date(f.get("מועד תשלום ראשון")), _date(f.get("מועד תשלום אחרון"))
        left = int(_num(f.get("יתרת תקופה בחודשים")) or 0)
        total = _months(first, last) + 1 if first and last else 0
        track, rate_text = _track(f)
        loans.append(
            {
                "name": f"{track} ({mark.group(2)}-{mark.group(3)})",
                "loan_ref": mark.group(1),
                "track_type": track,
                "original_amount": _num(f.get("סכום מקורי")) or 0.0,
                "balance": balance,
                "rate_text": rate_text,
                "monthly_payment": _num(f.get("חיוב אחרון בהלוואה")) or 0.0,
                "payments_left": f"{total - left}/{total}" if total else str(left),
                "start_date": _date(f.get("תאריך מתן הלוואה")),
                "end_date": last,
                "prepay_fee": _num(f.get('סה"כ עמלת פרעון מוקדם')) or 0.0,
                "as_of": as_of,
            }
        )
    snapshot = {"date": as_of, "value": -round(sum(l["balance"] for l in loans), 2)} if loans else None
    return {
        "product": "mortgage", "meta": {"account_ref": ref, "as_of": as_of}, "transactions": [], "holdings": [],
        "loans": loans, "policies": [], "snapshot": snapshot,
    }
