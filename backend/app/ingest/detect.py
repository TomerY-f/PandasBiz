"""File-kind detection by scoring header keywords in the first rows."""
from .common import read_peek

KIND_KEYWORDS = {
    "credit": ["בית עסק", "סכום חיוב", "תאריך עסקה", "ענף", "סוג עסקה"],
    "bank": ["זכות", "חובה", "יתרה", "אסמכתא", "תיאור פעולה"],
    "excellence": ["שם נייר", "סימול", "שווי שוק", "שער אחרון", "מספר נייר"],
    "etrade": ["Symbol", "Quantity", "Price Paid", "Last Price", "Qty #", "Market Value"],
}


def detect_kind(filename: str, data: bytes) -> str | None:
    """Returns 'credit' | 'bank' | 'excellence' | 'etrade' or None if unrecognized."""
    try:
        df_peek = read_peek(filename, data)
    except Exception:
        return None
    text = " ".join(" ".join(row.astype(str).values) for _, row in df_peek.iterrows())

    scores = {kind: sum(1 for k in keys if k in text) for kind, keys in KIND_KEYWORDS.items()}
    best_kind, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score == 0:
        return None
    return best_kind
