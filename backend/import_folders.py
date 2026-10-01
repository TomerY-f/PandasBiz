"""Imports every supported file under a folder tree (e.g. the PandasBiz folder) into the local DB.

Usage:  .venv/bin/python import_folders.py [FOLDER]
FOLDER defaults to [paths] pandasbiz in config.ini. Sub-folder names are used as a product hint
(CreditCards, Bank/CurrentAccount, Mortgage, ...), but each file's own content decides.
Safe to run repeatedly — transactions are de-duplicated and position files replace their snapshot.
Password-protected PDFs: set PDF_PASSWORDS="pw1,pw2" in the environment (never stored).
"""
import configparser
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import models  # noqa: F401
from app.db.database import Base, SessionLocal, engine, migrate_add_columns
from app.db.seed import seed
from app.services.ingest import ingest_file

SUPPORTED = (".csv", ".xlsx", ".xls", ".html", ".htm", ".pdf")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.ini")

# folder-name fragment → product hint (lower-case match)
FOLDER_HINTS = [
    ("creditcard", "credit_card"),
    ("currentaccount", "bank_current"),
    ("bankstocks", "bank_securities"),
    ("bankassest", "bank_securities"),
    ("foreigncurrency", "fx"),
    ("bankloan", "bank_loan"),
    ("mortgage", "mortgage"),
    ("independentstocks", "trading"),
    ("pension", "pension"),
    ("insur", "insurance"),
    ("realestate", "real_estate"),
]
SKIP_FOLDERS = ("maindashboard",)


def hint_for(path: str) -> str | None:
    low = path.lower()
    return next((product for frag, product in FOLDER_HINTS if frag in low), None)


def collect(root: str) -> list[str]:
    out = []
    for dirpath, _, files in os.walk(root):
        if any(s in dirpath.lower() for s in SKIP_FOLDERS):
            continue
        for name in files:
            if name.startswith(("~$", ".")) or not name.lower().endswith(SUPPORTED):
                continue
            out.append(os.path.join(dirpath, name))
    return sorted(out)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else None
    if not root and os.path.exists(CONFIG_PATH):
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH)
        root = config.get("paths", "pandasbiz", fallback=None)
    if not root or not os.path.isdir(root):
        print("Usage: import_folders.py FOLDER  (or set [paths] pandasbiz in config.ini)")
        return

    Base.metadata.create_all(bind=engine)
    migrate_add_columns()
    db = SessionLocal()
    seed(db)
    try:
        for path in collect(root):
            name = os.path.basename(path)
            with open(path, "rb") as f:
                data = f.read()
            try:
                res = None
                passwords = [p for p in os.environ.get("PDF_PASSWORDS", "").split(",") if p] or [None]
                for i, pw in enumerate(passwords):
                    try:
                        res = ingest_file(db, name, data, product_hint=hint_for(path), password=pw)
                        break
                    except ValueError:
                        db.rollback()
                        if i == len(passwords) - 1:
                            raise
                db.commit()
                extras = {k: v for k, v in res.items() if k not in ("file", "document_id", "product_label", "account_id")}
                print(f"OK    {name}: {extras}")
            except Exception as e:
                db.rollback()
                print(f"ERROR {name}: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
