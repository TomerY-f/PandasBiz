"""Market data via yfinance: holding prices and USD/ILS rate."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Holding, Setting

USD_ILS_KEY = "usd_ils"
DEFAULT_USD_ILS = 3.7


def get_usd_ils(db: Session) -> float:
    setting = db.get(Setting, USD_ILS_KEY)
    if setting:
        try:
            return float(setting.value)
        except ValueError:
            pass
    return DEFAULT_USD_ILS


def _set_setting(db: Session, key: str, value: str):
    setting = db.get(Setting, key)
    if setting:
        setting.value = value
        setting.updated_at = datetime.utcnow()
    else:
        db.add(Setting(key=key, value=value, updated_at=datetime.utcnow()))


def refresh_prices(db: Session) -> dict:
    """Fetches latest prices for all holdings + USD/ILS. Returns summary."""
    import yfinance as yf

    holdings = list(db.scalars(select(Holding)))
    symbols = sorted({h.symbol for h in holdings if h.symbol})
    tickers = symbols + ["USDILS=X"]

    updated, failed = [], []
    now = datetime.utcnow()

    data = yf.download(tickers=" ".join(tickers), period="5d", interval="1d", progress=False, group_by="ticker")

    def last_close(symbol: str) -> float | None:
        try:
            series = data[symbol]["Close"].dropna() if len(tickers) > 1 else data["Close"].dropna()
            if len(series):
                return float(series.iloc[-1])
        except Exception:
            pass
        return None

    usd_ils = last_close("USDILS=X")
    if usd_ils:
        _set_setting(db, USD_ILS_KEY, f"{usd_ils:.4f}")

    for h in holdings:
        price = last_close(h.symbol)
        if price is not None:
            # TASE symbols (.TA) are quoted in agorot → convert to ILS
            if h.symbol.upper().endswith(".TA"):
                price = price / 100.0
            h.last_price = price
            h.price_updated_at = now
            updated.append(h.symbol)
        else:
            failed.append(h.symbol)

    db.commit()
    return {"updated": sorted(set(updated)), "failed": sorted(set(failed)), "usd_ils": usd_ils or get_usd_ils(db)}
