from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import assets, budget, dashboard, family, portfolio, products, sheets, transactions
from .db import models  # noqa: F401 — register models with Base
from .db.database import Base, SessionLocal, engine, migrate_add_columns
from .db.seed import seed

Base.metadata.create_all(bind=engine)
migrate_add_columns()
with SessionLocal() as _db:
    seed(_db)

app = FastAPI(title="Family Finance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(family.router)
app.include_router(sheets.router)
app.include_router(transactions.router)
app.include_router(portfolio.router)
app.include_router(assets.router)
app.include_router(budget.router)
app.include_router(dashboard.router)


@app.get("/api/health")
def health():
    return {"ok": True}
