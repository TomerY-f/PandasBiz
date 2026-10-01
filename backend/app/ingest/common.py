"""Shared helpers for file ingestion (ported from the original Streamlit app.py)."""
import hashlib
import io
from datetime import date

import pandas as pd

EXCEL_EXTENSIONS = (".xls", ".xlsx")
HTML_EXTENSIONS = (".html", ".htm")


def is_excel(filename: str) -> bool:
    return filename.lower().endswith(EXCEL_EXTENSIONS)


def is_html(filename: str, data: bytes) -> bool:
    head = data[:600].lstrip().lower()
    return filename.lower().endswith(HTML_EXTENSIONS) or head.startswith(b"<!doctype html") or head.startswith(b"<html")


def _read_xlsx_raw(data: bytes) -> pd.DataFrame:
    """Fallback for malformed .xlsx exports (e.g. bank portals writing ' ' into numeric cells
    and omitting cell references). Reads the first sheet's XML directly, row by row."""
    import html as html_lib
    import re
    import zipfile

    z = zipfile.ZipFile(io.BytesIO(data))
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        ss = z.read("xl/sharedStrings.xml").decode("utf-8")
        for si in re.findall(r"<(?:\w+:)?si>(.*?)</(?:\w+:)?si>", ss, re.S):
            shared.append("".join(re.findall(r"<(?:\w+:)?t[^>]*>(.*?)</(?:\w+:)?t>", si, re.S)))
    sheet_name = next(n for n in z.namelist() if n.startswith("xl/worksheets/") and n.endswith(".xml"))
    xml = z.read(sheet_name).decode("utf-8")
    rows = []
    for row_xml in re.findall(r"<(?:\w+:)?row\b[^>]*>(.*?)</(?:\w+:)?row>", xml, re.S):
        values = []
        for attrs, inner in re.findall(r"<(?:\w+:)?c\b([^>]*?)(?:/>|>(.*?)</(?:\w+:)?c>)", row_xml, re.S):
            texts = re.findall(r"<(?:\w+:)?(?:v|t)\b[^>]*>(.*?)</(?:\w+:)?(?:v|t)>", inner or "", re.S)
            raw = html_lib.unescape(texts[0]) if texts else ""
            if 't="s"' in attrs and raw.strip().isdigit():
                raw = shared[int(raw)]
            raw = raw.strip()
            values.append(raw if raw else None)
        rows.append(values)
    width = max((len(r) for r in rows), default=0)
    return pd.DataFrame([r + [None] * (width - len(r)) for r in rows])


def _read_html_grid(data: bytes) -> pd.DataFrame:
    """Flattens every leaf <tr> of an HTML export (bank portals) into a grid of cell texts."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data.decode("utf-8", errors="replace"), "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        if tr.find("tr"):  # skip container rows of nested tables
            continue
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]
        if any(cells):
            rows.append(cells)
    width = max((len(r) for r in rows), default=0)
    return pd.DataFrame([r + [None] * (width - len(r)) for r in rows])


def read_grid(filename: str, data: bytes) -> pd.DataFrame:
    """Reads any supported export (csv / xls / xlsx / html) as a raw grid with no header row."""
    buf = io.BytesIO(data)
    if is_html(filename, data):
        return _read_html_grid(data)
    if filename.lower().endswith(".xlsx"):
        try:
            return pd.read_excel(buf, header=None)
        except Exception:
            return _read_xlsx_raw(data)
    if filename.lower().endswith(".xls"):
        return pd.read_excel(buf, header=None)
    return read_peek(filename, data, nrows=100000)


def grid_with_header(grid: pd.DataFrame, header_idx: int) -> pd.DataFrame:
    """Turns row `header_idx` of a raw grid into the column names and returns the rows below it."""
    header = [str(c).replace("\n", " ").strip() if c is not None and str(c) != "nan" else f"_{i}"
              for i, c in enumerate(grid.iloc[header_idx].tolist())]
    df = grid.iloc[header_idx + 1:].copy()
    df.columns = header
    df = df.loc[:, ~df.columns.duplicated()]
    return df.reset_index(drop=True)


def find_header_in_grid(grid: pd.DataFrame, keywords: list[str], max_rows: int = 40) -> int:
    best, idx = 0, 0
    for i in range(min(len(grid), max_rows)):
        row_str = " ".join(str(v) for v in grid.iloc[i].tolist() if v is not None)
        hits = sum(1 for k in keywords if k in row_str)
        if hits > best:
            best, idx = hits, i
    return idx


def grid_text(grid: pd.DataFrame, max_rows: int = 40) -> str:
    return " ".join(
        " ".join(str(v) for v in grid.iloc[i].tolist() if v is not None and str(v) != "nan")
        for i in range(min(len(grid), max_rows))
    )


def to_number(value) -> float | None:
    """Parses '1,234.5', '₪ 12', '(4.35%)', '-' etc. Returns None when not a number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if pd.isna(value) else float(value)
    s = str(value).replace(",", "").replace("₪", "").replace("$", "").replace("%", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def to_date(value, dayfirst: bool = True) -> date | None:
    """Parses Excel serials, datetime objects and dd/mm/yy(yy) / dd.mm.yy strings."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        if 20000 < value < 80000:  # Excel serial date
            return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(value))).date()
        return None
    if hasattr(value, "date") and not isinstance(value, str):
        try:
            return value.date()
        except Exception:
            return None
    s = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d.%m.%y", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return pd.to_datetime(s, format=fmt).date()
        except Exception:
            continue
    return None


def read_peek(filename: str, data: bytes, nrows: int = 20) -> pd.DataFrame:
    """Reads the first rows of a file without assuming a header row.

    Uses a fixed wide column set so files with junk/title rows before the real
    header (typical for Israeli bank exports) don't break the CSV tokenizer.
    UTF-8 is tried first: cp1255 bytes fail UTF-8 strictly, but not vice versa.
    """
    buf = io.BytesIO(data)
    if is_excel(filename):
        return pd.read_excel(buf, nrows=nrows, header=None)
    last_error: Exception | None = None
    for encoding in ("utf-8", "windows-1255"):
        try:
            buf.seek(0)
            return pd.read_csv(
                buf, nrows=nrows, header=None, encoding=encoding,
                names=range(40), engine="python", dtype=str,
            )
        except Exception as e:
            last_error = e
    raise ValueError(f"Could not read CSV preview: {last_error}")


def find_header_row(filename: str, data: bytes, keywords: list[str]) -> int:
    """Scans the first 20 rows to find the row containing most of the expected headers."""
    df_peek = read_peek(filename, data)
    max_hits = 0
    header_idx = 0
    for i, row in df_peek.iterrows():
        row_str = " ".join(row.astype(str).values)
        hits = sum(1 for key in keywords if key in row_str)
        if hits > max_hits:
            max_hits = hits
            header_idx = i
    return header_idx


def read_table(filename: str, data: bytes, skiprows: int) -> pd.DataFrame:
    buf = io.BytesIO(data)
    if is_excel(filename):
        return pd.read_excel(buf, skiprows=skiprows)
    last_error: Exception | None = None
    for encoding in ("utf-8", "windows-1255"):
        try:
            buf.seek(0)
            return pd.read_csv(buf, skiprows=skiprows, encoding=encoding, engine="python")
        except Exception as e:
            last_error = e
    raise ValueError(f"Could not read CSV: {last_error}")


def assign_billing_cycle(d: date) -> str:
    """10th-to-10th billing cycle label, e.g. '2026-02 → 2026-03' for 10/Feb–9/Mar."""
    if d.day >= 10:
        start_month, start_year = d.month, d.year
    else:
        start_month = d.month - 1
        start_year = d.year
        if start_month < 1:
            start_month = 12
            start_year -= 1
    end_month = start_month + 1
    end_year = start_year
    if end_month > 12:
        end_month = 1
        end_year += 1
    return f"{start_year}-{start_month:02d} → {end_year}-{end_month:02d}"


def dedup_hash(source: str, d: date, description: str, amount: float) -> str:
    raw = f"{source}|{d.isoformat()}|{description}|{amount:.2f}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def clean_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "").str.replace("₪", "").str.replace("$", "").str.strip(),
        errors="coerce",
    )
