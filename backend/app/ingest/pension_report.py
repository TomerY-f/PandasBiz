"""Parser for pension clearing-house "pre-treatment" reports (דוח מצב טרום טיפול) in PDF.

The PDF may be password protected; the password is passed in by the caller and never stored.
"""
import io
import re
from datetime import date

from .common import to_date, to_number

PRODUCT_TYPES = [
    ("קרן פנסיה חדשה מקיפה", "pension"),
    ("קרן פנסיה חדשה כללית", "pension"),
    ("קרן פנסיה", "pension"),
    ("קרן השתלמות", "study_fund"),
    ("קופת גמל להשקעה", "gemel"),
    ("קופת גמל", "gemel"),
    ("ביטוח מנהלים", "pension"),
    ("פוליסת חיסכון", "gemel"),
]


class PdfPasswordError(ValueError):
    pass


def pdf_text(data: bytes, password: str | None = None) -> str:
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        if not password or not reader.decrypt(password):
            raise PdfPasswordError("הקובץ מוגן בסיסמה. הזינו את הסיסמה ליד אזור ההעלאה ונסו שוב.")
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def is_pension_report(text: str) -> bool:
    return "סך החיסכון שצברת" in text and ("קרן" in text or "קופת גמל" in text)


def _money(s: str | None) -> float:
    return to_number((s or "").replace(" ", "")) or 0.0


def _after(text: str, label: str, pattern: str = r"₪\s*([\d,]+)") -> float:
    m = re.search(re.escape(label) + r"\s*\n?\s*" + pattern, text)
    return _money(m.group(1)) if m else 0.0


def parse_pension_report(text: str) -> dict:
    client = ""
    m = re.search(r"עבור הלקוח\s*\n\s*([^\n]+)", text)
    if m:
        client = m.group(1).strip()
    report_date = None
    m = re.search(r"דוח (?:מיום|נכון ליום)\s*\n\s*(\d{2}/\d{2}/\d{4})", text)
    if m:
        report_date = to_date(m.group(1))

    total = 0.0
    m = re.search(r"₪\s*([\d,]+)\s+סך החיסכון שצברת", text)
    if m:
        total = _money(m.group(1))
    ytd = None
    m = re.search(r"([\d.]+)%\s+תשואה מתחילת שנה", text)
    if m:
        ytd = float(m.group(1))
    premium = 0.0
    m = re.search(r"₪\s*([\d,]+)\s+סך פרמיה חודשית", text)
    if m:
        premium = _money(m.group(1))

    deposits = {}
    m = re.search(r"סך הפקדות חודשי\s*\n\s*₪\s*([\d,]+)(.*?)במוצרים", text, re.S)
    if m:
        deposits["total"] = _money(m.group(1))
        for label, key in (("פנסיה", "pension"), ("מנהלים", "managers"), ("השתלמות", "study_fund"), ("גמל להשקעה", "gemel_invest")):
            mm = re.search(r"^" + label + r"₪\s*([\d,]+)", m.group(2), re.M)
            if mm:
                deposits[key] = _money(mm.group(1))

    pension = {}
    m = re.search(r"סך קצבה צפויה לגיל פרישה\s*\n\s*₪\s*([\d,]+)", text)
    if m:
        pension["without_deposits"] = _money(m.group(1))
    m = re.search(r"\nפנסיה₪\s*([\d,]+)₪\s*([\d,]+)", text)
    if m:
        pension["without_deposits"] = _money(m.group(1))
        pension["with_deposits"] = _money(m.group(2))

    coverages = {}
    for label, key in (
        ("כיסויים לאובדן כושר עבודה", "disability"),
        ("סך קצבה לשאירים", "survivors"),
        ("סך כיסוי למוות", "death"),
        ("ביטוח חיים משכנתא", "mortgage_life"),
    ):
        m = re.search(re.escape(label) + r"\s*\n\s*([\d,]+)", text)
        if m:
            coverages[key] = _money(m.group(1))

    mix = {}
    m = re.search(r"חשיפה למניות\s*(\d+)%", text)
    if m:
        mix["stocks_exposure"] = int(m.group(1))
    m = re.search(r'חשיפה לחו"ל\s*(\d+)%', text)
    if m:
        mix["abroad_exposure"] = int(m.group(1))

    return {
        "client": client,
        "report_date": report_date,
        "total": total,
        "ytd_return": ytd,
        "monthly_premium": premium,
        "deposits": deposits,
        "pension": pension,
        "coverages": coverages,
        "mix": mix,
        # "דוח מצב טרום טיפול" is a snapshot before the agent moved funds; "דוח שוטף" is the current state
        "pre_treatment": "טרום טיפול" in text,
        "products": parse_products(text),
        "yields": parse_yields(text),
    }


def parse_products(text: str) -> list[dict]:
    start = text.find("קצבה\nחזויה")
    end = text.find("כיסויים לאובדן כושר עבודה", start)
    section = text[start:end] if start >= 0 else text
    type_names = "|".join(re.escape(t) for t, _ in PRODUCT_TYPES)
    block = re.compile(
        r"\.?\d+(" + type_names + r")[^\n]*\n\s*([^\n]+)\n\s*([\d-]+)\n"   # type, provider, policy number
        r"₪\s*(\d{1,3}(?:,\d{3})*)((?:\d+\.\d{2}%){1,2})₪\s*(\d{1,3}(?:,\d{3})*)"  # balance, fees, salary
        r"(.*?)(לא פעיל|פעיל)(\d{2}/\d{2}/\d{4})?₪\s*(\d{1,3}(?:,\d{3})*)",            # employer, status, last deposit, pension
        re.S,
    )
    products = []
    for m in block.finditer(section):
        type_name = m.group(1)
        fees = [float(x) for x in re.findall(r"([\d.]+)%", m.group(5))]
        fee_deposit, fee_accrual = (fees[0], fees[1]) if len(fees) == 2 else (0.0, fees[0])
        products.append(
            {
                "type_name": type_name,
                "product_type": next(k for t, k in PRODUCT_TYPES if type_name.startswith(t)),
                "provider": m.group(2).strip(),
                "policy_number": m.group(3),
                "balance": _money(m.group(4)),
                "fee_deposit_pct": fee_deposit,
                "fee_accrual_pct": fee_accrual,
                "salary": _money(m.group(6)),
                "employer": re.sub(r"\s+", " ", m.group(7)).strip(),
                "status": m.group(8),
                "last_deposit": m.group(9) or "",
                "projected_pension": _money(m.group(10)),
            }
        )
    return products


# Ministry of Finance returns per investment track, one table per product:
# columns = last month, year to date, 12 months, 3 years, 5 years, 3-year average, 5-year average.
YIELD_TABLE = "נתוני תשואה על פי דיווח משרד האוצר"
YIELD_ROW = re.compile(r"₪\s*(\d{1,3}(?:,\d{3})*)(\d{1,3})%((?:-?\d+\.\d{2}%){1,7})")
PRODUCT_HEAD = re.compile(r"\n\.?\d+(קרן[^\n]*|קופת גמל[^\n]*|ביטוח מנהלים[^\n]*)\n([^\n]+)\n([\d-]+)מספר פוליסה")


def _yield_columns(values: list[float]) -> dict:
    keys7 = ["last_month", "ytd", "y1", "y3", "y5", "y3_avg", "y5_avg"]
    keys5 = ["last_month", "ytd", "y1", "y3", "y3_avg"]  # tracks younger than 5 years
    keys3 = ["last_month", "ytd", "y1"]
    keys = keys7 if len(values) == 7 else keys5 if len(values) == 5 else keys3[: len(values)]
    return dict(zip(keys, values))


def parse_yields(text: str) -> list[dict]:
    out = []
    starts = [m.start() for m in re.finditer(re.escape(YIELD_TABLE), text)]
    for i, start in enumerate(starts):
        end_candidates = [text.find(marker, start + 10) for marker in ("סוג כיסוי", "עמודהופק", YIELD_TABLE)]
        end = min([e for e in end_candidates if e > 0] or [len(text)])
        segment = text[start:end]
        heads = list(PRODUCT_HEAD.finditer(text, 0, start))
        if not heads:
            continue
        head = heads[-1]
        as_of = None
        m = re.search(r"(\d{2}/\d{2}/\d{4})נכון ל", text[head.end():start])
        if m:
            as_of = to_date(m.group(1))
        body = segment.split("שנים\n")[-1] if "שנים\n" in segment else segment
        tracks, prev = [], 0
        for row in YIELD_ROW.finditer(body):
            name = re.sub(r"\s+", " ", body[prev:row.start()]).strip(" -")
            prev = row.end()
            values = [float(v) for v in re.findall(r"(-?\d+\.\d{2})%", row.group(3))]
            tracks.append({
                "name": name or "מסלול",
                "balance": _money(row.group(1)),
                "share_pct": int(row.group(2)),
                **_yield_columns(values),
            })
        if tracks:
            out.append({
                "type_name": head.group(1).strip(),
                "provider": head.group(2).strip(),
                "policy_number": head.group(3),
                "as_of": as_of.isoformat() if as_of else None,
                "tracks": tracks,
            })
    return out


def report_as_of(parsed: dict) -> date:
    return parsed.get("report_date") or date.today()
