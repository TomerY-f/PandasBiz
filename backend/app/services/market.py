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


def monthly_returns(db: Session, holdings: list) -> dict:
    """Year-to-date and month-by-month price returns of the current holdings (USD tickers),
    from monthly closes; the portfolio figure weights each holding by its current value.
    Cached per day in the settings table."""
    import json
    from datetime import date

    tickers = sorted({h.symbol for h in holdings if (h.currency or "").upper() == "USD" and h.symbol.isascii() and h.symbol.isalpha()})
    if not tickers:
        return {"months": [], "holdings": [], "portfolio": None}
    key = f"returns:{date.today().isoformat()}:{','.join(tickers)}"
    cached = db.get(Setting, key)
    if cached:
        closes = json.loads(cached.value)
    else:
        import yfinance as yf

        start = date(date.today().year - 1, 12, 1).isoformat()
        data = yf.download(" ".join(tickers), start=start, interval="1mo", progress=False, auto_adjust=True)
        close = data["Close"] if len(tickers) > 1 else data[["Close"]].rename(columns={"Close": tickers[0]})
        closes = {
            t: {idx.strftime("%Y-%m"): round(float(v), 4) for idx, v in close[t].dropna().items()}
            for t in tickers if t in close
        }
        _set_setting(db, key, json.dumps(closes))
        db.commit()
    year = date.today().year
    months = sorted({m for c in closes.values() for m in c if m.startswith(str(year))})
    usd_ils = get_usd_ils(db)
    rows, weights = [], {}
    for h in holdings:
        c = closes.get(h.symbol)
        if not c:
            continue
        base = c.get(f"{year - 1}-12")
        monthly = {}
        prev = base
        for m in months:
            if m in c and prev:
                monthly[m] = round((c[m] / prev - 1) * 100, 2)
            prev = c.get(m, prev)
        last = c.get(months[-1]) if months else None
        ytd = round((last / base - 1) * 100, 2) if base and last else None
        value = h.quantity * (h.last_price or 0) * usd_ils
        weights[h.symbol] = value
        rows.append({"symbol": h.symbol, "name": h.name, "value_ils": round(value, 2), "ytd": ytd, "monthly": monthly})
    total = sum(weights.values()) or 1

    def wavg(get):
        vals = [(get(r), weights[r["symbol"]]) for r in rows if get(r) is not None]
        w = sum(x[1] for x in vals)
        return round(sum(v * x for v, x in vals) / w, 2) if w else None

    portfolio = {
        "ytd": wavg(lambda r: r["ytd"]),
        "monthly": {m: wavg(lambda r, m=m: r["monthly"].get(m)) for m in months},
        "weights": {r["symbol"]: round(weights[r["symbol"]] / total * 100, 1) for r in rows},
    }
    return {"months": months, "holdings": rows, "portfolio": portfolio}
