"""Universal Israeli bank activity parser (ported from app.py)."""
import pandas as pd

from .common import assign_billing_cycle, clean_number, dedup_hash, find_header_row, read_table

BANK_KEYS = ["זכות", "חובה", "פעולה", "יתרה"]


def parse(filename: str, data: bytes) -> list[dict]:
    """Returns normalized transaction dicts (credit positive, debit negative)."""
    header_idx = find_header_row(filename, data, BANK_KEYS)
    df = read_table(filename, data, skiprows=header_idx)

    df.columns = [str(col).strip() for col in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]

    date_col = next((c for c in df.columns if "תאריך" in c), None)
    if not date_col:
        return []

    df = df.dropna(subset=[date_col], how="all")

    if pd.api.types.is_numeric_dtype(df[date_col]):
        df["_date"] = pd.to_datetime(df[date_col], unit="D", origin="1899-12-30")
    else:
        df["_date"] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["_date"])

    for col in ["זכות", "חובה"]:
        if col in df.columns:
            df[col] = clean_number(df[col]).fillna(0)
        else:
            df[col] = 0.0

    desc_col = next(
        (c for c in df.columns if any(k in c for k in ["תיאור", "פעולה", "פרטים", "אסמכתא"]) and "תאריך" not in c),
        None,
    )
    balance_col = next((c for c in df.columns if "יתרה" in c), None)
    if balance_col:
        df[balance_col] = clean_number(df[balance_col])

    records = []
    for _, row in df.iterrows():
        d = row["_date"].date()
        description = str(row[desc_col]) if desc_col else ""
        amount = float(row["זכות"]) - float(row["חובה"])
        if amount == 0:
            continue
        balance = float(row[balance_col]) if balance_col and pd.notna(row[balance_col]) else None
        records.append(
            {
                "date": d,
                "description": description,
                "amount": amount,
                "category": "General / Uncategorized",
                "source": "bank",
                "month_year": d.strftime("%Y-%m"),
                "billing_cycle": assign_billing_cycle(d),
                "dedup_hash": dedup_hash("bank", d, description, amount),
                "balance": balance,
            }
        )
    return records
