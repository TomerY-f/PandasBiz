import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Local data folder (gitignored): the SQLite DB and the originals of uploaded files.
DATA_DIR = os.environ.get("FAMILYBIZ_DATA", os.path.join(BACKEND_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.environ.get("FINDASH_DB", os.path.join(DATA_DIR, "familybiz.db"))

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_add_columns():
    """Additive migration: adds model columns missing from existing tables (never drops or alters)."""
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                col_type = col.type.compile(dialect=engine.dialect)
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                default_sql = ""
                if isinstance(default, str):
                    default_sql = " DEFAULT '" + default.replace("'", "''") + "'"
                elif isinstance(default, (int, float)):
                    default_sql = f" DEFAULT {default}"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}{default_sql}'))
