"""Universal Israeli credit-card statement parser (ported from app.py)."""
import pandas as pd

from .common import assign_billing_cycle, clean_number, dedup_hash, find_header_row, read_table

CREDIT_KEYS = ["תאריך", "עסקה", "בית עסק", "סכום"]

TARGETS = {
    "תאריך עסקה": ["תאריך", "עסקה"],
    "שם בית עסק": ["בית עסק", "תיאור", "פעולה"],
    "סכום חיוב": ["סכום", "חיוב", 'בש"ח', 'בש""ח'],
    "ענף": ["ענף", "קטגוריה"],
}


def smart_rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Maps varying bank/card export headers onto canonical names, avoiding duplicates."""
    df.columns = [str(col).replace("\n", " ").strip() for col in df.columns]
    new_mapping = {}
    used_targets = {t for t in TARGETS if t in df.columns}

    for col in df.columns:
        if col in TARGETS:
            continue
        for target, keywords in TARGETS.items():
            if target in used_targets:
                continue
            if target == "תאריך עסקה" and any(k in col for k in keywords) and not any(
                k in col for k in ["סכום", "חיוב"]
            ):
                new_mapping[col] = target
                used_targets.add(target)
                break
            elif target != "תאריך עסקה" and any(k in col for k in keywords):
                new_mapping[col] = target
                used_targets.add(target)
                break
    return df.rename(columns=new_mapping)


def parse(filename: str, data: bytes) -> list[dict]:
    """Returns normalized transaction dicts (amount negative = expense)."""
    header_idx = find_header_row(filename, data, CREDIT_KEYS)
    df = read_table(filename, data, skiprows=header_idx)
    df = smart_rename_columns(df)
    df = df.loc[:, ~df.columns.duplicated()]

    if "תאריך עסקה" not in df.columns or "סכום חיוב" not in df.columns:
        return []

    df = df.dropna(subset=["תאריך עסקה", "סכום חיוב"], how="all")
    df["תאריך עסקה"] = pd.to_datetime(df["תאריך עסקה"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["תאריך עסקה"])
    df["סכום חיוב"] = clean_number(df["סכום חיוב"]).fillna(0)

    if "ענף" not in df.columns:
        df["ענף"] = "General / Uncategorized"
    df["ענף"] = df["ענף"].fillna("General / Uncategorized")

    records = []
    for _, row in df.iterrows():
        d = row["תאריך עסקה"].date()
        description = str(row.get("שם בית עסק", "Unknown"))
        amount = -abs(float(row["סכום חיוב"]))  # credit-card charge = expense
        records.append(
            {
                "date": d,
                "description": description,
                "amount": amount,
                "category": str(row["ענף"]),
                "source": "credit",
                "month_year": d.strftime("%Y-%m"),
                "billing_cycle": assign_billing_cycle(d),
                "dedup_hash": dedup_hash("credit", d, description, amount),
                "balance": None,
            }
        )
    return records
