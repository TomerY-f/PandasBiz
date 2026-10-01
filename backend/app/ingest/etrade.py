"""E-Trade positions export parser (English CSV, USD)."""
import pandas as pd

from .common import clean_number, find_header_row, read_table

ETRADE_KEYS = ["Symbol", "Quantity", "Price", "Qty"]


def _find_col(df: pd.DataFrame, keywords: list[str], exclude_cols: tuple = ()) -> str | None:
    """Keyword-priority match: first keyword that hits any column wins."""
    for k in keywords:
        for col in df.columns:
            if col in exclude_cols:
                continue
            if k.lower() in str(col).lower():
                return col
    return None


def parse(filename: str, data: bytes) -> list[dict]:
    """Returns holding dicts in USD."""
    header_idx = find_header_row(filename, data, ETRADE_KEYS)
    df = read_table(filename, data, skiprows=header_idx)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]

    symbol_col = _find_col(df, ["symbol"])
    qty_col = _find_col(df, ["quantity", "qty"])
    price_paid_col = _find_col(df, ["price paid", "cost"])
    last_price_col = _find_col(
        df, ["last price", "market price", "price"],
        exclude_cols=(price_paid_col,) if price_paid_col else (),
    )
    name_col = _find_col(df, ["description", "security", "name"])

    if not symbol_col or not qty_col:
        return []

    df[qty_col] = clean_number(df[qty_col])
    df = df.dropna(subset=[qty_col])

    records = []
    for _, row in df.iterrows():
        symbol = str(row[symbol_col]).strip().upper()
        if not symbol or symbol in ("NAN", "TOTAL", "CASH"):
            continue
        quantity = float(row[qty_col])
        price_paid = clean_number(pd.Series([row[price_paid_col]])).iloc[0] if price_paid_col else None
        last_price = clean_number(pd.Series([row[last_price_col]])).iloc[0] if last_price_col else None
        cost_basis = float(price_paid) * quantity if price_paid is not None and pd.notna(price_paid) else 0.0
        records.append(
            {
                "symbol": symbol,
                "name": str(row[name_col]).strip() if name_col and pd.notna(row.get(name_col)) else symbol,
                "quantity": quantity,
                "cost_basis": cost_basis,
                "currency": "USD",
                "last_price": float(last_price) if last_price is not None and pd.notna(last_price) else None,
            }
        )
    return records
