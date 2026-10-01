"""Excellence Trade holdings export parser (Hebrew Excel/CSV).

Flexible column matching since export formats vary; expects a table with
security name/symbol, quantity, and optionally cost and current value.
"""
import pandas as pd

from .common import clean_number, find_header_row, read_table

EXCELLENCE_KEYS = ["נייר", "כמות", "שער", "שווי"]


def _find_col(df: pd.DataFrame, keywords: list[str], exclude: list[str] | None = None) -> str | None:
    """Keyword-priority match: first keyword that hits any column wins."""
    exclude = exclude or []
    for k in keywords:
        for col in df.columns:
            c = str(col)
            if k in c and not any(e in c for e in exclude):
                return col
    return None


def parse(filename: str, data: bytes) -> list[dict]:
    """Returns holding dicts: symbol, name, quantity, cost_basis, currency, last_price."""
    header_idx = find_header_row(filename, data, EXCELLENCE_KEYS)
    df = read_table(filename, data, skiprows=header_idx)
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]

    name_col = _find_col(df, ["שם נייר", "שם המכשיר", "נייר ערך", "שם"])
    symbol_col = _find_col(df, ["סימול", "סימבול", "מספר נייר", "Symbol"])
    qty_col = _find_col(df, ["כמות", "יתרה"])
    cost_col = _find_col(df, ["עלות", "מחיר קנייה", "שער קנייה"])
    value_col = _find_col(df, ["שווי"])
    price_col = _find_col(df, ["שער אחרון", "שער נוכחי", "שער"], exclude=["קנייה"])

    if not qty_col or not (name_col or symbol_col):
        return []

    df[qty_col] = clean_number(df[qty_col])
    df = df.dropna(subset=[qty_col])

    records = []
    for _, row in df.iterrows():
        name = str(row[name_col]).strip() if name_col and pd.notna(row.get(name_col)) else ""
        symbol = str(row[symbol_col]).strip() if symbol_col and pd.notna(row.get(symbol_col)) else name
        if not symbol or symbol.lower() in ("nan", 'סה"כ', "סהכ"):
            continue
        quantity = float(row[qty_col])
        cost = clean_number(pd.Series([row[cost_col]])).iloc[0] if cost_col else None
        price = clean_number(pd.Series([row[price_col]])).iloc[0] if price_col else None
        value = clean_number(pd.Series([row[value_col]])).iloc[0] if value_col else None
        # TASE quotes are in agorot; keep raw — valuation handled by market service or via value
        last_price = None
        if price is not None and pd.notna(price):
            last_price = float(price)
        elif value is not None and pd.notna(value) and quantity:
            last_price = float(value) / quantity
        records.append(
            {
                "symbol": symbol,
                "name": name or symbol,
                "quantity": quantity,
                "cost_basis": float(cost) if cost is not None and pd.notna(cost) else 0.0,
                "currency": "ILS",
                "last_price": last_price,
            }
        )
    return records
