# PandasBiz

A local FastAPI + SQLite + React app that turns the Hasolidit tracking sheet
("מעקב הכנסות והוצאות", "מעקב שווי נקי" and the calculators) into live pages fed by
bank, card, mortgage, insurance and brokerage exports.

## Run

```bash
cd backend && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload       # http://localhost:8000
cd frontend && npm install && npm run dev                # http://localhost:5173
```

Data lives in `backend/data/` (gitignored): `familybiz.db` plus the originals of every uploaded
file under `uploads/<product>/`. Set `FAMILYBIZ_DATA` / `FINDASH_DB` to move them.
The old `backend/findash.db` is not used or modified.

Bulk import of an exports folder (sub-folder names are used as hints, file content decides):

```bash
cd backend && .venv/bin/python import_folders.py /path/to/PandasBiz
```

## Pages

- **Sheets:** dashboard, income & expenses (12-month grid by the sheet's lines, averages,
  4%/3% columns, snapshot rows, manual cells), net worth (liquid / illiquid / liabilities
  buckets, monthly history, years of living, safe withdrawal), calculators (time to FI,
  aggressive saving, car cost, personal inflation), budget.
- **Products**, one tab per input folder, each with its own drag-and-drop upload and stored files:
  Bank (tabs: current account, securities & money-market funds, FX, loans), credit cards,
  self-directed trading, pension & study funds, insurance (Har HaBituach), mortgage, real estate.
- **Settings:** family members (auto-created from the card holder line), card-sector → line
  mapping, description rules (optionally only for credits / debits), uncategorized review.

Every page can be filtered by family member (or "joint" = accounts without an owner).

## Supported files

| Product | File |
|---|---|
| Current account | bank "תנועות בחשבון" xls/csv |
| Credit cards | monthly charge detail xlsx (both the "על שם" and the bank-issued layouts) |
| Bank securities | "תיק ני\"ע" xlsx (malformed exports handled), product-type summary html |
| FX | "תיק מט\"ח" html (also sets the USD/ILS rate) |
| Bank loans | "פירוט הלוואות" xls |
| Mortgage | "משכנתאות" xlsx |
| Trading | "תיק סוף יום" xlsx, E-Trade positions csv |
| Insurance | Har HaBituach xlsx |
| Pension & study funds | clearing-house "דוח מצב טרום טיפול" PDF (password-protected supported) |
| Trading | the broker logo embedded in the export is shown on the page |
| Any other PDF / image | stored as a document |

Password-protected PDFs: type the password next to the drop zone (used once, never stored), or set
`PDF_PASSWORDS="pw1,pw2"` when running `import_folders.py`.
