"""Parsers for the family-app product pages.

Each parser takes (filename, bytes) and returns a ParseResult dict:
    {
      "product": str,                 # key of PRODUCTS
      "meta": {...},                  # holder name, card last-4, account ref, as-of date
      "transactions": [...],          # normalized transaction dicts (amount < 0 = expense)
      "holdings": [...],              # holding dicts
      "loans": [...],                 # loan dicts
      "policies": [...],              # insurance policy dicts
      "snapshot": {"date", "value"},  # account value in ILS (negative for liabilities), optional
    }
"""
import re
from collections import Counter
from datetime import date

from .common import (
    assign_billing_cycle, dedup_hash, find_header_in_grid, grid_text, grid_with_header, read_grid, to_date, to_number,
)


def _result(product: str, **kwargs) -> dict:
    base = {"product": product, "meta": {}, "transactions": [], "holdings": [], "loans": [], "policies": [], "snapshot": None}
    base.update(kwargs)
    return base


def _col(df, *keywords, exclude: tuple = ()):
    """First column (by keyword priority) whose name contains the keyword."""
    for k in keywords:
        for c in df.columns:
            if k in c and not any(e in c for e in exclude):
                return c
    return None


def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s == "nan" else s.replace("‫", "").replace("‬", "")


def _tx(source: str, ref: str, d: date, description: str, amount: float, occurrence: int, **extra) -> dict:
    return {
        "date": d,
        "description": description,
        "amount": amount,
        "category": extra.pop("category", ""),
        "sector": extra.pop("sector", ""),
        "source": source,
        "month_year": d.strftime("%Y-%m"),
        "billing_cycle": assign_billing_cycle(d),
        "dedup_hash": dedup_hash(f"{source}:{ref}:{occurrence}", d, description, amount),
        "balance": extra.pop("balance", None),
    }


# ---------- Bank current account (עו"ש) ----------

BANK_KEYS = ["זכות", "חובה", "יתרה", "תאריך", "אסמכתא"]


def parse_bank_current(filename: str, data: bytes) -> dict:
    grid = read_grid(filename, data)
    text = grid_text(grid, 8)
    ref_match = re.search(r"חשבון:?\s*([\d-]{5,})", text)
    ref = ref_match.group(1) if ref_match else ""

    df = grid_with_header(grid, find_header_in_grid(grid, BANK_KEYS))
    date_col = "תאריך" if "תאריך" in df.columns else _col(df, "תאריך", exclude=("ערך",))
    desc_col = _col(df, "תאור", "תיאור", "פרטים", "פעולה", exclude=("סוג", "תאריך"))
    credit_col = _col(df, "זכות")
    debit_col = _col(df, "חובה")
    balance_col = _col(df, "יתרה")
    if not date_col or not (credit_col or debit_col):
        return _result("bank_current")

    seen: Counter = Counter()
    txs, last_balance, last_date = [], None, None
    for _, row in df.iterrows():
        d = to_date(row[date_col])
        if not d:
            continue
        amount = (to_number(row[credit_col]) or 0.0 if credit_col else 0.0) - (
            to_number(row[debit_col]) or 0.0 if debit_col else 0.0
        )
        balance = to_number(row[balance_col]) if balance_col else None
        if balance is not None:
            last_balance, last_date = balance, d
        if amount == 0:
            continue
        description = _clean(row[desc_col]) if desc_col else ""
        key = (d, description, round(amount, 2))
        seen[key] += 1
        txs.append(_tx("bank", ref, d, description, round(amount, 2), seen[key], balance=balance))

    snapshot = {"date": last_date, "value": last_balance} if last_balance is not None else None
    return _result("bank_current", meta={"account_ref": ref}, transactions=txs, snapshot=snapshot)


# ---------- Credit cards ----------

CARD_KEYS = ["תאריך", "בית עסק", "סכום", "חיוב", "ענף"]


def parse_credit_card(filename: str, data: bytes) -> dict:
    grid = read_grid(filename, data)
    top = grid_text(grid, 8)

    last4 = ""
    m = re.search(r"(?:המסתיים ב-?|-\s*)(\d{4})\b", top) or re.search(r"(\d{4})", filename)
    if m:
        last4 = m.group(1)
    holder = ""
    m = re.search(r"על שם\s+([^\d₪]+?)(?:\s{2,}|לחיוב|$)", top)
    if m:
        holder = m.group(1).strip()
    card_name = ""
    m = re.search(r"(?:לכרטיס|^)\s*([^\d]{3,40}?)\s*(?:המסתיים|-\s*\d{4})", top)
    if m:
        card_name = m.group(1).strip()

    df = grid_with_header(grid, find_header_in_grid(grid, CARD_KEYS))
    date_col = _col(df, "תאריך עסקה", "תאריך רכישה", "תאריך")
    desc_col = _col(df, "בית עסק", "תיאור")
    charge_col = _col(df, "סכום חיוב") or _col(df, "חיוב", exclude=("מטבע", "מועד", "תאריך")) or _col(df, "סכום")
    sector_col = _col(df, "ענף", "קטגוריה")
    voucher_col = _col(df, "שובר")
    if not date_col or not charge_col:
        return _result("credit_card", meta={"last4": last4, "holder": holder})

    seen: Counter = Counter()
    txs = []
    for _, row in df.iterrows():
        d = to_date(row[date_col])
        amount = to_number(row[charge_col])
        if not d or amount is None or amount == 0:
            continue
        description = _clean(row[desc_col]) if desc_col else ""
        voucher = _clean(row[voucher_col]) if voucher_col else ""
        key = (d, description, round(amount, 2), voucher)
        seen[key] += 1
        txs.append(
            _tx(
                "credit", f"{last4}:{voucher}", d, description, -round(amount, 2), seen[key],
                sector=_clean(row[sector_col]) if sector_col else "",
            )
        )

    # upcoming charge = liability until paid
    total = None
    m = re.search(r'סה"כ לחיוב[^\d]*([\d,]+\.?\d*)', grid_text(grid, len(grid)))
    if m:
        total = to_number(m.group(1))
    m2 = re.search(r"לחיוב ב-?\s*(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", top)
    charge_date = None
    if m2:
        day, month = int(m2.group(1)), int(m2.group(2))
        year = int(m2.group(3)) if m2.group(3) else (max(t["date"] for t in txs).year if txs else date.today().year)
        year = year + 2000 if year < 100 else year
        try:
            charge_date = date(year, month, day)
        except ValueError:
            charge_date = None
        if total is None:
            m3 = re.search(r"לחיוב ב-?[\d/.]+:?\s*([\d,]+\.?\d*)", top)
            total = to_number(m3.group(1)) if m3 else None
    if total is None and txs:
        total = -sum(t["amount"] for t in txs)
    snapshot = {"date": charge_date or (max(t["date"] for t in txs) if txs else date.today()), "value": -(total or 0.0)}

    return _result(
        "credit_card",
        meta={"last4": last4, "holder": holder, "card_name": card_name, "charge_date": charge_date},
        transactions=txs,
        snapshot=snapshot,
    )


# ---------- Bank securities portfolio (תיק ני"ע) ----------

def parse_bank_securities(filename: str, data: bytes) -> dict:
    grid = read_grid(filename, data)
    text = grid_text(grid, 6)
    ref = ""
    m = re.search(r"חשבון:?\s*([\d-]{4,})", text)
    if m:
        ref = m.group(1)
    as_of = None
    m = re.search(r"תאריך ייצוא:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", text)
    if m:
        as_of = to_date(m.group(1))

    header_idx = find_header_in_grid(grid, ["נייר", "כמות", "שער אחרון", "מטבע", "ISIN"])
    df = grid_with_header(grid, header_idx)
    name_col = _col(df, "נייר", exclude=("מספר",))
    num_col = _col(df, "מספר נייר")
    sym_col = _col(df, "סימבול")
    qty_col = _col(df, "כמות")
    price_col = _col(df, "שער אחרון")
    cur_col = _col(df, "מטבע")
    cost_col = _col(df, "שער עלות מותאם", "שער עלות")
    value_col = _col(df, "שווי", exclude=("שינוי",))

    holdings = []
    for _, row in df.iterrows():
        name = _clean(row[name_col]) if name_col else ""
        qty = to_number(row[qty_col]) if qty_col else None
        if not name or qty is None or qty == 0 or name.startswith(":") or 'סה"כ' in name:
            continue
        price = to_number(row[price_col]) if price_col else None
        currency_sign = _clean(row[cur_col]) if cur_col else ""
        is_ils = currency_sign in ("₪", "ILS", 'ש"ח', "")
        value = to_number(row[value_col]) if value_col else None
        # TASE quotes are in agorot: value ≈ qty * price / 100
        if price is not None and is_ils:
            if value is None or abs(qty * price / 100 - value) <= abs(qty * price - value):
                price = price / 100
        elif price is None and value is not None:
            price = value / qty
        cost = to_number(row[cost_col]) if cost_col else None
        if cost is not None and is_ils and price is not None and cost > price * 20:
            cost = cost / 100
        symbol = _clean(row[sym_col]) if sym_col else ""
        symbol = symbol or (_clean(row[num_col]) if num_col else "") or name
        asset_class = "deposits" if ("כספ" in name or "כספית" in name or 'מק"מ' in name) else "stocks"
        holdings.append(
            {
                "symbol": symbol,
                "name": name,
                "quantity": qty,
                "cost_basis": round((cost or 0.0) * qty, 2),
                "currency": "ILS" if is_ils else "USD",
                "last_price": price,
                "asset_class": asset_class,
            }
        )

    total = None
    m = re.search(r'שווי תיק בש"ח:?\s*([\d,]+\.?\d*)', grid_text(grid, 8))
    if m:
        total = to_number(m.group(1))
    snapshot = {"date": as_of or date.today(), "value": total} if total is not None else None
    return _result("bank_securities", meta={"account_ref": ref, "as_of": as_of}, holdings=holdings, snapshot=snapshot)


def parse_bank_assets_summary(filename: str, data: bytes) -> dict:
    """'טבלת סוגי מוצר' HTML — total of the bank investment portfolio by product type (snapshot only)."""
    grid = read_grid(filename, data)
    total = None
    for i in range(len(grid)):
        cells = [_clean(v) for v in grid.iloc[i].tolist()]
        if cells and cells[0].startswith('סה"כ'):
            total = next((to_number(c) for c in cells[1:] if to_number(c) is not None), None)
            break
    snapshot = {"date": date.today(), "value": total} if total is not None else None
    return _result("bank_securities", snapshot=snapshot)


# ---------- Foreign currency (מט"ח) ----------

def parse_fx(filename: str, data: bytes) -> dict:
    grid = read_grid(filename, data)
    holdings, total_ils = [], 0.0
    currency = ""
    currency_codes = {"דולר": "USD", "אירו": "EUR", "לירה": "GBP", "פרנק": "CHF", "ין": "JPY"}
    for i in range(len(grid)):
        cells = [_clean(v) for v in grid.iloc[i].tolist()]
        first = cells[0] if cells else ""
        if first.startswith("פרוט למטבע"):
            currency = next((code for word, code in currency_codes.items() if word in first), first.replace("פרוט למטבע", "").strip())
            continue
        nums = [to_number(c) for c in cells]
        # data row: action, account type, rate, balance, value ILS, cash, value ILS
        if len(cells) >= 5 and nums[2] is not None and nums[3] is not None and nums[4] is not None and currency:
            holdings.append(
                {
                    "symbol": currency,
                    "name": f'מט"ח {currency}',
                    "quantity": nums[3],
                    "cost_basis": 0.0,
                    "currency": "ILS",
                    "last_price": nums[2],
                    "asset_class": "cash",
                }
            )
            total_ils += nums[4]
    snapshot = {"date": date.today(), "value": round(total_ils, 2)} if holdings else None
    return _result("fx", holdings=holdings, snapshot=snapshot)


# ---------- Bank loans ----------

def parse_bank_loans(filename: str, data: bytes) -> dict:
    grid = read_grid(filename, data)
    df = grid_with_header(grid, find_header_in_grid(grid, ["שם ההלוואה", "יתרת", "ריבית", "פירעון"]))
    name_col = _col(df, "שם ההלוואה")
    orig_col = _col(df, "סכום הלוואה מקורי", "סכום ההלוואה")
    start_col = _col(df, "יום מתן")
    rate_col = _col(df, "ריבית")
    bal_col = _col(df, "יתרת ההלוואה", "יתרת")
    end_col = _col(df, "פירעון סופי")
    pay_col = _col(df, "סכום תשלום", "תשלום")
    loans = []
    for _, row in df.iterrows():
        name = _clean(row[name_col]) if name_col else ""
        if not name or name.startswith('סה"כ') or name.startswith("-"):
            continue
        balance = to_number(row[bal_col]) if bal_col else None
        if balance is None:
            continue
        loans.append(
            {
                "name": re.sub(r"\s{2,}", " ", name),
                "original_amount": to_number(row[orig_col]) or 0.0 if orig_col else 0.0,
                "balance": balance,
                "rate_text": _clean(row[rate_col]) if rate_col else "",
                "monthly_payment": to_number(row[pay_col]) or 0.0 if pay_col else 0.0,
                "payments_left": "",
                "end_date": to_date(row[end_col]) if end_col else None,
                "as_of": date.today(),
                "start_date": to_date(row[start_col]) if start_col else None,
            }
        )
    snapshot = {"date": date.today(), "value": -round(sum(l["balance"] for l in loans), 2)} if loans else None
    return _result("bank_loan", loans=loans, snapshot=snapshot)


# ---------- Mortgage ----------

def parse_mortgage(filename: str, data: bytes) -> dict:
    grid = read_grid(filename, data)
    text = grid_text(grid, 12)
    ref = ""
    m = re.search(r"חשבון:?\s*(\d{5,})", text)
    if m:
        ref = m.group(1)
    df = grid_with_header(grid, find_header_in_grid(grid, ["שם ההלוואה", "יתרת חוב", "ריבית", "תשלום"]))
    name_col = _col(df, "שם ההלוואה")
    orig_col = _col(df, "סכום ההלוואה")
    left_col = _col(df, "יתרת תשלומים")
    bal_col = _col(df, "יתרת חוב")
    rate_col = _col(df, "ריבית")
    pay_col = _col(df, "סכום תשלום")
    date_col = _col(df, "תאריך תשלום")
    loans = []
    for _, row in df.iterrows():
        balance = to_number(row[bal_col]) if bal_col else None
        name = _clean(row[name_col]) if name_col else ""
        if balance is None or not name:
            continue
        loans.append(
            {
                "name": name,
                "original_amount": to_number(row[orig_col]) or 0.0 if orig_col else 0.0,
                "balance": balance,
                "rate_text": _clean(row[rate_col]) if rate_col else "",
                "monthly_payment": to_number(row[pay_col]) or 0.0 if pay_col else 0.0,
                "payments_left": _clean(row[left_col]) if left_col else "",
                "end_date": None,
                "as_of": date.today(),
                "next_payment": to_date(row[date_col]) if date_col else None,
            }
        )
    snapshot = {"date": date.today(), "value": -round(sum(l["balance"] for l in loans), 2)} if loans else None
    return _result("mortgage", meta={"account_ref": ref}, loans=loans, snapshot=snapshot)


# ---------- Self-directed trading account (תיק סוף יום) ----------

def _ticker(name: str) -> str:
    m = re.search(r"\(([A-Z.]{1,8})\)", name)
    if m:
        return m.group(1)
    m = re.match(r"^([A-Z.]{1,8})\s+US", name)
    if m:
        return m.group(1)
    return ""


def parse_trading(filename: str, data: bytes) -> dict:
    grid = read_grid(filename, data)
    text = grid_text(grid, 9)
    ref = ""
    m = re.search(r"חשבון:?\s*([\d-]{5,})", text)
    if m:
        ref = m.group(1)
    as_of = None
    m = re.search(r"תאריך נכונות הנתונים:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", text)
    if m:
        as_of = to_date(m.group(1))

    df = grid_with_header(grid, find_header_in_grid(grid, ["שם נייר", "כמות", "מחיר ממוצע", "ערך"]))
    name_col = _col(df, "שם נייר", "נייר")
    num_col = _col(df, "מספר נייר")
    qty_col = _col(df, "כמות בתיק", "כמות", exclude=("מושאלת",))
    avg_col = _col(df, "מחיר ממוצע")
    value_col = _col(df, "ערך")
    holdings = []
    for _, row in df.iterrows():
        name = _clean(row[name_col]) if name_col else ""
        qty = to_number(row[qty_col]) if qty_col else None
        value = to_number(row[value_col]) if value_col else None
        if not name or not qty or value is None:
            continue
        ticker = _ticker(name)
        is_usd = bool(ticker) or "דולר" in name or bool(re.search(r"[A-Za-z]", name) and "שקל" not in name)
        is_cash = "מזומן" in name or "דולר" in name or "פחק" in name
        avg = to_number(row[avg_col]) if avg_col else None
        number = _clean(row[num_col]) if num_col else ""
        holdings.append(
            {
                "symbol": ticker or (number if number not in ("", "-") and not is_cash else name),
                "name": name,
                "quantity": qty,
                "cost_basis": round((avg or 0.0) * qty, 2) if not is_cash else 0.0,
                "currency": "USD" if is_usd else "ILS",
                "last_price": value / qty,
                "asset_class": "cash" if is_cash else ("bonds" if ticker in ("BND", "AGG", "BNDX", "TLT", "IEF") else "stocks"),
            }
        )
    return _result("trading", meta={"account_ref": ref, "as_of": as_of}, holdings=holdings)


# ---------- Insurance (הר הביטוח) ----------

def parse_insurance(filename: str, data: bytes) -> dict:
    grid = read_grid(filename, data)
    df = grid_with_header(grid, find_header_in_grid(grid, ["תעודת זהות", "ענף ראשי", "חברה", "פרמיה"]))
    id_col = _col(df, "תעודת זהות")
    main_col = _col(df, "ענף ראשי")
    sub_col = _col(df, "ענף (משני)", "משני")
    type_col = _col(df, "סוג מוצר")
    comp_col = _col(df, "חברה")
    period_col = _col(df, "תקופת ביטוח")
    details_col = _col(df, "פרטים נוספים")
    prem_col = _col(df, "פרמיה")
    prem_type_col = _col(df, "סוג פרמיה")
    policy_col = _col(df, "מספר פוליסה")
    class_col = _col(df, "סיווג")
    policies, domain = [], ""
    for _, row in df.iterrows():
        main = _clean(row[main_col]) if main_col else ""
        if main.startswith("תחום"):
            domain = main.replace("תחום -", "").strip()
            continue
        if not main:
            continue
        id_number = _clean(row[id_col]) if id_col else ""
        id_number = id_number.split(".")[0]
        policies.append(
            {
                "id_number": id_number,
                "domain": domain,
                "main_branch": main,
                "sub_branch": _clean(row[sub_col]) if sub_col else "",
                "product_type": _clean(row[type_col]) if type_col else "",
                "company": _clean(row[comp_col]) if comp_col else "",
                "period": _clean(row[period_col]) if period_col else "",
                "details": _clean(row[details_col]) if details_col else "",
                "premium": to_number(row[prem_col]) or 0.0 if prem_col else 0.0,
                "premium_type": _clean(row[prem_type_col]) if prem_type_col else "",
                "policy_number": _clean(row[policy_col]).split(".")[0] if policy_col else "",
                "plan_class": _clean(row[class_col]) if class_col else "",
            }
        )
    return _result("insurance", policies=policies)


# ---------- Detection ----------

SIGNATURES = [
    # (product, parser, keywords that must mostly appear in the first rows)
    ("insurance", parse_insurance, ["תעודת זהות", "ענף ראשי", "פרמיה", "מספר פוליסה"]),
    ("mortgage", parse_mortgage, ["משכנתאות", "יתרת חוב", "יתרת תשלומים", "שם ההלוואה"]),
    ("bank_loan", parse_bank_loans, ["פירוט הלוואות", "יתרת ההלוואה", "פירעון סופי", "שם ההלוואה"]),
    ("trading", parse_trading, ["תיק סוף יום", "שם נייר", "מחיר ממוצע", "כמות בתיק"]),
    ("bank_securities", parse_bank_securities, ['תיק ני"ע', "שער אחרון", "ISIN", "סימבול"]),
    ("bank_securities_summary", parse_bank_assets_summary, ["טבלת סוגי מוצר", "אחוז מהתיק", "קרנות נאמנות"]),
    ("fx", parse_fx, ['תיק מט"ח', "פרוט למטבע", "יתרה עדכנית", 'שווי בש"ח']),
    ("credit_card", parse_credit_card, ["בית עסק", "סכום חיוב", "ענף", "עסקה", "לחיוב"]),
    ("bank_current", parse_bank_current, ["זכות", "חובה", "יתרה", "אסמכתא", "תנועות בחשבון"]),
]

PARSERS = {product: parser for product, parser, _ in SIGNATURES}


def detect_product(filename: str, data: bytes) -> str | None:
    try:
        text = grid_text(read_grid(filename, data), 15)
    except Exception:
        return None
    best, best_score = None, 0.0
    for product, _, keys in SIGNATURES:
        score = sum(1 for k in keys if k in text) / len(keys)
        if score > best_score:
            best, best_score = product, score
    return best if best_score >= 0.5 else None


def parse_file(filename: str, data: bytes, product_hint: str | None = None) -> dict:
    """Parses a file for a product page. `product_hint` is the page it was dropped on;
    the file's own signature wins when it clearly belongs elsewhere."""
    detected = detect_product(filename, data)
    product = detected or product_hint
    if product == "bank_securities" and product_hint == "bank_securities" and detected == "bank_securities_summary":
        product = "bank_securities_summary"
    if not product or product not in PARSERS:
        raise ValueError("לא זוהה סוג הקובץ")
    result = PARSERS[product](filename, data)
    result["detected"] = detected
    return result
