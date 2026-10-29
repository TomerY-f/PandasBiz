"""iCloud Drive inbox: files saved from the phone into a folder are imported automatically.

Uses file-system events (macOS FSEvents through `watchfiles`), not polling, so it costs nothing
while idle; it wakes only when something in the folder changes.

Layout (all inside the inbox folder):
    <inbox>/               drop files here (or in a member sub-folder, e.g. <inbox>/מור/)
    <inbox>/לבדיקה/        files that could not be imported
    <inbox>/סיכום.txt      one line per processed file (readable from the phone)
Imported files are moved into the archive folder (the PandasBiz input folder), by product.
"""
import configparser
import logging
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime

from ..db.database import SessionLocal
from ..db.models import FamilyMember, PRODUCTS
from .ingest import ingest_file

log = logging.getLogger("pandasbiz.inbox")

ICLOUD_ROOT = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs")
DEFAULT_INBOX = os.path.join(ICLOUD_ROOT, "PandasBiz Inbox")
REVIEW_DIR = "לבדיקה"
SUMMARY_FILE = "סיכום.txt"
SUPPORTED = (".xls", ".xlsx", ".csv", ".html", ".htm", ".pdf")
KEYCHAIN_SERVICE = "PandasBiz PDF"  # add with: security add-generic-password -s "PandasBiz PDF" -a pension -w

# product → sub-folder of the archive (same layout as the original input folder)
ARCHIVE_FOLDERS = {
    "bank_current": "Bank/CurrentAccount",
    "bank_securities": "Bank/BankStocksAccount",
    "fx": "Bank/ForeignCurrency",
    "bank_loan": "Bank/BankLoans",
    "credit_card": "CreditCards",
    "trading": "IndependentStocksTrading",
    "pension": "Pensions_and_Study_Funds",
    "insurance": "Insurences",
    "mortgage": "Mortgage",
    "real_estate": "RealEstate",
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "config.ini")


def settings() -> tuple[str, str | None]:
    """(inbox folder, archive folder) from config.ini [inbox], with defaults."""
    cfg = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        cfg.read(CONFIG_PATH)
    inbox = os.environ.get("PANDASBIZ_INBOX_DIR") or os.path.expanduser(cfg.get("inbox", "folder", fallback=DEFAULT_INBOX))
    archive = os.environ.get("PANDASBIZ_ARCHIVE_DIR") or cfg.get("inbox", "archive", fallback=None) or cfg.get("paths", "pandasbiz", fallback=None)
    return inbox, os.path.expanduser(archive) if archive else None


def keychain_passwords() -> list[str]:
    """PDF passwords kept in the macOS Keychain (never in code or files)."""
    out = []
    for account in ("pension", "pdf", "pdf2"):
        try:
            pw = subprocess.run(
                ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if pw:
                out.append(pw)
        except Exception:
            pass
    return out


def notify(title: str, text: str) -> None:
    try:
        subprocess.run(["osascript", "-e", f'display notification "{text}" with title "{title}"'], timeout=5)
    except Exception:
        pass


def _materialize(path: str) -> str | None:
    """iCloud may keep a not-yet-downloaded file as '.name.ext.icloud'; ask for it and return the real path."""
    name = os.path.basename(path)
    if name.startswith(".") and name.endswith(".icloud"):
        real = os.path.join(os.path.dirname(path), name[1:-len(".icloud")])
        subprocess.run(["brctl", "download", path], capture_output=True, timeout=30)
        for _ in range(60):
            if os.path.exists(real):
                return real
            time.sleep(1)
        return None
    return path


def _stable(path: str) -> bool:
    """Waits until the file stops growing (still syncing)."""
    last = -1
    for _ in range(30):
        try:
            size = os.path.getsize(path)
        except OSError:
            return False
        if size == last and size > 0:
            return True
        last = size
        time.sleep(1)
    return False


def _summary(inbox: str, line: str) -> None:
    with open(os.path.join(inbox, SUMMARY_FILE), "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%d/%m %H:%M} · {line}\n")


def process_file(path: str, inbox: str, archive: str | None) -> None:
    path = _materialize(path)
    if not path or not path.lower().endswith(SUPPORTED) or not _stable(path):
        return
    name = os.path.basename(path)
    parent = os.path.basename(os.path.dirname(path))
    with open(path, "rb") as f:
        data = f.read()

    db = SessionLocal()
    try:
        member = None
        if os.path.dirname(path) != inbox:  # dropped in a member sub-folder, e.g. <inbox>/מור/
            member = next((m for m in db.query(FamilyMember).all() if m.name == parent), None)
        res, error = None, None
        for pw in keychain_passwords() or [None]:
            try:
                res = ingest_file(db, name, data, member_id=member.id if member else None, password=pw)
                db.commit()
                break
            except Exception as e:  # wrong password / unknown file: try the next password, then give up
                db.rollback()
                error = str(e)
        if res is None and name.lower().endswith(".pdf") and not keychain_passwords():
            try:
                res = ingest_file(db, name, data, member_id=member.id if member else None)
                db.commit()
            except Exception as e:
                db.rollback()
                error = str(e)
    finally:
        db.close()

    if res is None or res.get("stored_only"):
        os.makedirs(os.path.join(inbox, REVIEW_DIR), exist_ok=True)
        shutil.move(path, os.path.join(inbox, REVIEW_DIR, name))
        msg = error or "נשמר כמסמך בלבד (לא זוהה כקובץ נתונים)"
        _summary(inbox, f"{name} · לבדיקה · {msg}")
        notify("PandasBiz", f"{name}: לבדיקה")
        log.warning("inbox: %s → review (%s)", name, msg)
        return

    product = res.get("product", "")
    parts = [PRODUCTS.get(product, (product,))[0]]
    if res.get("account"):
        parts.append(res["account"] + (f" ({res['owner']})" if res.get("owner") else ""))
    if res.get("inserted") is not None:
        parts.append(f"{res['inserted']} עסקאות חדשות" + (f", {res['duplicates']} כבר היו" if res.get("duplicates") else ""))
    if res.get("products") is not None:
        parts.append(f"{res['products']} מוצרים")
    if res.get("snapshot") is not None:
        parts.append(f"₪{abs(res['snapshot']):,.0f}")
    _summary(inbox, f"{name} · " + " · ".join(parts))
    notify("PandasBiz", f"{name}: נקלט")

    dest_dir = os.path.join(archive, ARCHIVE_FOLDERS.get(product, "Other")) if archive else os.path.join(inbox, "נקלטו")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)
    if os.path.exists(dest):
        stem, ext = os.path.splitext(name)
        dest = os.path.join(dest_dir, f"{stem}_{datetime.now():%Y%m%d_%H%M%S}{ext}")
    shutil.move(path, dest)
    log.info("inbox: %s → %s", name, dest)


def _candidates(inbox: str) -> list[str]:
    out = []
    for dirpath, dirnames, files in os.walk(inbox):
        dirnames[:] = [d for d in dirnames if d not in (REVIEW_DIR, "נקלטו")]
        for f in files:
            if f == SUMMARY_FILE or (f.startswith(".") and not f.endswith(".icloud")):
                continue
            out.append(os.path.join(dirpath, f))
    return out


def run(stop: threading.Event) -> None:
    inbox, archive = settings()
    if not os.path.isdir(os.path.dirname(inbox.rstrip("/"))):
        log.warning("inbox: iCloud Drive not found (%s); inbox disabled", os.path.dirname(inbox))
        return
    os.makedirs(inbox, exist_ok=True)
    log.info("inbox: watching %s", inbox)
    for path in _candidates(inbox):  # files that arrived while the app was off
        _safe(process_file, path, inbox, archive)

    from watchfiles import watch

    for changes in watch(inbox, stop_event=stop, debounce=2000, recursive=True):
        for _, path in changes:
            if os.path.isfile(path) and path in _candidates(inbox):
                _safe(process_file, path, inbox, archive)


def _safe(fn, *args):
    try:
        fn(*args)
    except Exception:
        log.exception("inbox: failed on %s", args[0])


_stop = threading.Event()


def start() -> None:
    if os.environ.get("PANDASBIZ_INBOX", "1") == "0":
        return
    threading.Thread(target=run, args=(_stop,), daemon=True, name="pandasbiz-inbox").start()


def stop() -> None:
    _stop.set()
