"""Per-source fetchers. Each returns normalized rows, or None when every provider failed (= unknown)."""
from __future__ import annotations

import csv
import io
import json
import time
from datetime import datetime, timezone

from .http import first, get

GAMMA = "https://gamma-api.polymarket.com"
PMDATA = "https://data-api.polymarket.com"
KALSHI_HOSTS = ["https://api.elections.kalshi.com/trade-api/v2", "https://trading-api.kalshi.com/trade-api/v2"]


def _f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _iso(s):
    try:
        return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return None


# ---------------- Polymarket ----------------

SPORTS_RX = __import__("re").compile(r"\bvs\.?\b|win on \d{4}-|\bO/U\b|Spread:|\bMap \d|\bBO\d|\bGame \d|\bSet \d|Over/Under|\bWorld Series\b|\bSuper Bowl\b|\bNBA\b|\bNFL\b|\bNHL\b|\bMLB\b|Premier League|Champions League|\bUFC\b|Grand Prix", 2)


def _pm_norm(m: dict) -> dict | None:
    try:
        prices = json.loads(m.get("outcomePrices") or "[]")
        outcomes = json.loads(m.get("outcomes") or "[]")
    except ValueError:
        return None
    if not prices:
        return None
    ev = (m.get("events") or [{}])[0]
    slug = ev.get("slug") or m.get("slug")
    return {"source": "polymarket", "id": m.get("conditionId"), "title": m.get("question"), "event": ev.get("title"),
            "url": f"https://polymarket.com/event/{slug}", "api": f"{GAMMA}/markets?slug={m.get('slug')}",
            "outcome": (outcomes or ["Yes"])[0], "price": _f(prices[0]), "change1h": _f(m.get("oneHourPriceChange"), 0.0),
            "change1d": _f(m.get("oneDayPriceChange"), 0.0), "change1w": _f(m.get("oneWeekPriceChange"), 0.0),
            "vol24": _f(m.get("volume24hr"), 0.0), "vol1wk": _f(m.get("volume1wk"), 0.0), "volume": _f(m.get("volumeNum") or m.get("volume"), 0.0),
            "liquidity": _f(m.get("liquidityNum") or m.get("liquidity"), 0.0), "endDate": m.get("endDate"),
            "startTs": _iso(m.get("startDate") or m.get("createdAt")), "endTs": _iso(m.get("endDate")),
            "category": "sports" if SPORTS_RX.search(f"{m.get('question')} {ev.get('title') or ''}") else None}


def polymarket_markets(limit: int = 200) -> list[dict] | None:
    def gamma_markets():
        rows = []
        for off in range(0, limit, 100):
            j = get(f"{GAMMA}/markets?active=true&closed=false&order=volume24hr&ascending=false&limit=100&offset={off}", "gamma")
            if not isinstance(j, list):
                return None if not rows else rows
            rows += j
        return rows

    def gamma_events():  # failover: same data, nested under events
        j = get(f"{GAMMA}/events?active=true&closed=false&order=volume24hr&ascending=false&limit=50", "gamma-events")
        return [m for e in (j or []) for m in (e.get("markets") or []) if not m.get("closed")] or None

    raw, _ = first("polymarket", [("gamma /markets", gamma_markets), ("gamma /events", gamma_events)])
    if raw is None:
        return None
    return [n for n in (_pm_norm(m) for m in raw) if n and n["price"] is not None]


def polymarket_trades(condition_id: str, min_usd: float = 2000, limit: int = 200) -> list[dict] | None:
    """Large recent trades in one market. Polymarket settles on Polygon, so each has an on-chain tx hash."""
    url = f"{PMDATA}/trades?market={condition_id}&limit={limit}&filterType=CASH&filterAmount={int(min_usd)}"
    raw, _ = first("polymarket-trades", [("data-api /trades", lambda: get(url, "pmdata", max_age=60))])
    if raw is None:
        return None
    out = []
    for t in raw:  # names / pseudonyms / profile images are deliberately dropped
        size, price = _f(t.get("size"), 0.0), _f(t.get("price"), 0.0)
        out.append({"wallet": t.get("proxyWallet"), "side": t.get("side"), "outcome": t.get("outcome"), "price": price,
                    "usd": round(size * price, 2), "ts": int(t.get("timestamp") or 0), "tx": t.get("transactionHash")})
    return out


def polymarket_first_seen(wallet: str) -> int | None:
    """Timestamp of a wallet's first Polymarket activity (data-api, sorted ascending)."""
    j = get(f"{PMDATA}/activity?user={wallet}&limit=1&sortBy=TIMESTAMP&sortDirection=ASC", "pmdata-activity", max_age=3600)
    if isinstance(j, list) and j:
        return int(j[0].get("timestamp") or 0) or None
    return None


# ---------------- Kalshi ----------------

SKIP_KALSHI_CATEGORIES = {"Sports"}


def _kalshi_norm(m: dict, cat: str | None) -> dict:
    series = (m.get("event_ticker") or m.get("ticker") or "").split("-")[0]
    return {"source": "kalshi", "id": m.get("ticker"), "title": " ".join(x for x in [m.get("title"), m.get("yes_sub_title")] if x).replace("**", ""),
            "event": m.get("event_ticker"), "category": cat, "url": f"https://kalshi.com/markets/{series.lower()}",
            "api": f"{KALSHI_HOSTS[0]}/markets/{m.get('ticker')}", "price": _f(m.get("last_price_dollars")),
            "prev": _f(m.get("previous_price_dollars")), "vol24": _f(m.get("volume_24h_fp"), 0.0),
            "volume": _f(m.get("volume_fp"), 0.0), "oi": _f(m.get("open_interest_fp"), 0.0),
            "openTs": _iso(m.get("open_time")), "closeTs": _iso(m.get("close_time"))}


def kalshi_markets(pages: int = 10) -> list[dict] | None:
    """Open Kalshi markets via /events (nested markets, with category); sports in-play props are skipped."""
    def events(host):
        def go():
            rows, cur = [], ""
            for _ in range(pages):
                j = get(f"{host}/events?status=open&limit=200&with_nested_markets=true" + (f"&cursor={cur}" if cur else ""), "kalshi")
                if not isinstance(j, dict):
                    return rows or None
                for e in j.get("events") or []:
                    if e.get("category") in SKIP_KALSHI_CATEGORIES:
                        continue
                    rows += [_kalshi_norm(m, e.get("category")) for m in e.get("markets") or []]
                cur = j.get("cursor")
                if not cur:
                    break
            return rows or None
        return go

    def markets(host):  # failover: flat market list (no category)
        def go():
            j = get(f"{host}/markets?status=open&limit=1000&mve_filter=exclude", "kalshi-m")
            return [_kalshi_norm(m, None) for m in (j or {}).get("markets") or []] or None
        return go

    h0, h1 = KALSHI_HOSTS
    raw, _ = first("kalshi", [("events", events(h0)), ("events (alt host)", events(h1)), ("markets", markets(h0))])
    return raw


# ---------------- US equities & options ----------------

def equity_daily(symbol: str) -> dict | None:
    def yahoo(host):
        def go():
            j = get(f"https://{host}/v8/finance/chart/{symbol}?range=3mo&interval=1d", "yahoo", headers={"User-Agent": "Mozilla/5.0"})
            r = (((j or {}).get("chart") or {}).get("result") or [None])[0]
            if not r:
                return None
            q = r["indicators"]["quote"][0]
            rows = [(t, c, v) for t, c, v in zip(r["timestamp"], q["close"], q["volume"]) if c is not None and v is not None]
            return rows or None
        return go

    def nasdaq():
        asset = "etf" if symbol in ETFS else "stocks"
        frm = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 120 * 86400))
        j = get(f"https://api.nasdaq.com/api/quote/{symbol}/historical?assetclass={asset}&fromdate={frm}&limit=90", "nasdaq")
        rows = ((((j or {}).get("data") or {}).get("tradesTable") or {}).get("rows")) or []
        out = []
        for x in reversed(rows):
            try:
                t = int(datetime.strptime(x["date"], "%m/%d/%Y").replace(tzinfo=timezone.utc).timestamp())
                out.append((t, float(x["close"].strip("$").replace(",", "")), float(x["volume"].replace(",", ""))))
            except (KeyError, ValueError):
                continue
        return out or None

    rows, via = first(f"equities:{symbol}", [("yahoo q1", yahoo("query1.finance.yahoo.com")), ("yahoo q2", yahoo("query2.finance.yahoo.com")),
                                             ("nasdaq", nasdaq)])
    if rows is None:
        return None
    return {"symbol": symbol, "rows": rows, "via": via, "url": f"https://finance.yahoo.com/quote/{symbol}"}


ETFS = {"SPY", "QQQ", "IWM", "TLT", "HYG", "GLD", "USO", "UUP", "XLE", "IEF", "SHY", "SLV", "XLF", "SMH"}


def options_chain(symbol: str) -> dict | None:
    """Per-contract volume and open interest (delayed). Cboe first, Nasdaq second."""
    def cboe():
        j = get(f"https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json", "cboe", max_age=600, timeout=60)
        opts = ((j or {}).get("data") or {}).get("options") or []
        rows = [{"contract": o["option"], "volume": _f(o.get("volume"), 0.0), "oi": _f(o.get("open_interest"), 0.0),
                 "type": "call" if o["option"][-9] == "C" else "put", "expiry": "20" + o["option"][-15:-9]} for o in opts if o.get("option")]
        return rows or None

    def nasdaq():
        asset = "etf" if symbol in ETFS else "stocks"
        j = get(f"https://api.nasdaq.com/api/quote/{symbol}/option-chain?assetclass={asset}&limit=2000&fromdate=all&todate=undefined&excode=oprac&callput=callput&money=all&type=all", "nasdaq-opt", max_age=600)
        rows = ((((j or {}).get("data") or {}).get("table") or {}).get("rows")) or []
        out = []
        for r in rows:
            if not r.get("strike"):
                continue
            for side, pre in (("call", "c_"), ("put", "p_")):
                v = _f(str(r.get(pre + "Volume") or "").replace(",", ""), None)
                oi = _f(str(r.get(pre + "Openinterest") or "").replace(",", ""), None)
                if v is not None and oi is not None:
                    out.append({"contract": f"{symbol} {r.get('expiryDate') or r.get('expirygroup') or ''} {r['strike']} {side}", "volume": v, "oi": oi, "type": side, "expiry": None})
        return out or None

    rows, via = first(f"options:{symbol}", [("cboe delayed", cboe), ("nasdaq", nasdaq)])
    if rows is None:
        return None
    return {"symbol": symbol, "rows": rows, "via": via, "url": f"https://www.cboe.com/delayed_quotes/{symbol.lower()}/quote_table"}


# ---------------- US Treasuries ----------------

TSY_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv"
TSY_PAGE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve"


def treasury_curve() -> dict | None:
    """Daily par yields: {"rows": [(date, {"2Y": 4.7, "10Y": 4.99, ...}), ...] oldest first}."""
    def treasury():
        y = datetime.now(timezone.utc).year
        rows = []
        for yr in (y - 1, y):
            txt = get(TSY_URL.format(y=yr), "treasury", as_text=True, max_age=3600)
            if not txt:
                continue
            for r in csv.DictReader(io.StringIO(txt)):
                try:
                    d = datetime.strptime(r["Date"], "%m/%d/%Y").strftime("%Y-%m-%d")
                except (KeyError, ValueError):
                    continue
                pick = {"3M": r.get("3 Mo"), "2Y": r.get("2 Yr"), "5Y": r.get("5 Yr"), "10Y": r.get("10 Yr"), "30Y": r.get("30 Yr")}
                rows.append((d, {k: _f(v) for k, v in pick.items() if _f(v) is not None}))
        rows.sort()
        return rows if len(rows) >= 10 else None

    def fred():
        series = {"3M": "DGS3MO", "2Y": "DGS2", "5Y": "DGS5", "10Y": "DGS10", "30Y": "DGS30"}
        byd: dict[str, dict] = {}
        for k, sid in series.items():
            txt = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", "fred", as_text=True, max_age=3600, timeout=45)
            if not txt:
                return None
            for r in list(csv.reader(io.StringIO(txt)))[1:][-300:]:
                if len(r) == 2 and _f(r[1]) is not None:
                    byd.setdefault(r[0], {})[k] = _f(r[1])
        return sorted(byd.items()) or None

    rows, via = first("treasury", [("treasury.gov", treasury), ("FRED", fred)])
    if rows is None:
        return None
    return {"rows": rows, "via": via, "url": TSY_PAGE if via == "treasury.gov" else "https://fred.stlouisfed.org/series/DGS10"}


# ---------------- Crypto beyond Solana (CEX spot / perps) ----------------
OKX = "https://www.okx.com/api/v5"
CB = "https://api.exchange.coinbase.com"


def crypto_daily(ccy: str) -> dict | None:
    """Daily spot candles (OKX first, Coinbase second) as (ts, close, quote-volume) oldest first."""
    def okx():
        j = get(f"{OKX}/market/history-candles?instId={ccy}-USDT&bar=1Dutc&limit=60", "okx")
        rows = [(int(r[0]) // 1000, float(r[4]), float(r[7])) for r in (j or {}).get("data") or []]
        return sorted(rows) or None

    def coinbase():
        j = get(f"{CB}/products/{ccy}-USD/candles?granularity=86400", "coinbase")
        rows = [(int(r[0]), float(r[4]), float(r[5]) * float(r[4])) for r in (j or [])[:60]] if isinstance(j, list) else []
        return sorted(rows) or None

    rows, via = first(f"crypto:{ccy}", [("okx spot", okx), ("coinbase spot", coinbase)])
    if rows is None:
        return None
    return {"symbol": ccy, "rows": rows, "via": via, "url": f"https://www.okx.com/trade-spot/{ccy.lower()}-usdt" if via == "okx spot" else f"https://www.coinbase.com/price/{ccy.lower()}"}


def crypto_perps(ccy: str) -> dict | None:
    """OKX perpetual: daily open interest (USD) history and recent funding rates."""
    def okx():
        oi = get(f"{OKX}/rubik/stat/contracts/open-interest-volume?ccy={ccy}&period=1D", "okx-oi")
        fr = get(f"{OKX}/public/funding-rate-history?instId={ccy}-USDT-SWAP&limit=30", "okx-funding")
        o = sorted((int(r[0]) // 1000, float(r[1])) for r in (oi or {}).get("data") or [])
        f = sorted((int(r["fundingTime"]) // 1000, float(r["fundingRate"])) for r in (fr or {}).get("data") or [])
        return {"oi": o, "funding": f} if o and f else None

    res, _ = first(f"perps:{ccy}", [("okx swap", okx)])
    if res:
        res.update(symbol=ccy, url=f"https://www.okx.com/trade-swap/{ccy.lower()}-usdt-swap")
    return res


def stablecoins() -> list[dict] | None:
    """Circulating supply now vs a day and a week ago (DefiLlama aggregate of on-chain supply)."""
    def llama():
        j = get("https://stablecoins.llama.fi/stablecoins?includePrices=false", "llama", max_age=1800)
        out = []
        for a in (j or {}).get("peggedAssets") or []:
            c = lambda k: _f(((a.get(k) or {}).get("peggedUSD")))  # noqa: E731
            if (c("circulating") or 0) >= 1e9:
                out.append({"symbol": a["symbol"], "name": a["name"], "id": a["id"], "now": c("circulating"), "d1": c("circulatingPrevDay"), "w1": c("circulatingPrevWeek"),
                            "url": f"https://defillama.com/stablecoin/{a.get('gecko_id') or a['symbol'].lower()}"})
        return out or None

    rows, _ = first("stablecoins", [("defillama", llama)])
    return rows


# ---------------- FX, commodities, volatility (daily) ----------------
MACRO = {"^VIX": "VIX volatility index", "DX-Y.NYB": "US dollar index (DXY)", "GC=F": "Gold futures", "CL=F": "WTI crude futures",
         "EURUSD=X": "EUR/USD", "USDJPY=X": "USD/JPY"}


def macro_daily(sym: str) -> dict | None:
    def yahoo(host):
        def go():
            j = get(f"https://{host}/v8/finance/chart/{sym}?range=3mo&interval=1d", "yahoo", headers={"User-Agent": "Mozilla/5.0"})
            r = (((j or {}).get("chart") or {}).get("result") or [None])[0]
            if not r:
                return None
            q = r["indicators"]["quote"][0]
            return [(t, c, v or 0) for t, c, v in zip(r["timestamp"], q["close"], q.get("volume") or [0] * len(q["close"])) if c is not None] or None
        return go

    rows, via = first(f"macro:{sym}", [("yahoo q1", yahoo("query1.finance.yahoo.com")), ("yahoo q2", yahoo("query2.finance.yahoo.com"))])
    if rows is None:
        return None
    return {"symbol": sym, "name": MACRO.get(sym, sym), "rows": rows, "via": via, "url": f"https://finance.yahoo.com/quote/{sym}"}


# ---------------- SEC EDGAR (event triggers) ----------------

def edgar_current(form: str, count: int = 100) -> list[dict] | None:
    """Latest filings of one form type from EDGAR's public atom feed.

    SEC fair-access rules require a declared User-Agent with a contact email. Set GTB_SEC_USER_AGENT
    ("Your Name you@example.org"). Without it the source is skipped (reported, never faked)."""
    import os
    import re
    from html import unescape
    ua = os.environ.get("GTB_SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        return None

    def atom():
        txt = get(f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={form}&company=&dateb=&owner=include&count={count}&output=atom",
                  "edgar", as_text=True, max_age=600, headers={"User-Agent": ua})
        if not txt or "<feed" not in txt[:500]:
            return None
        out = []
        for e in re.findall(r"<entry>(.*?)</entry>", txt, re.S):
            title = unescape((re.search(r"<title>(.*?)</title>", e, re.S) or [None, ""])[1]).strip()
            link = (re.search(r'href="([^"]+)"', e) or [None, ""])[1]
            summ = unescape((re.search(r"<summary[^>]*>(.*?)</summary>", e, re.S) or [None, ""])[1])
            upd = (re.search(r"<updated>(.*?)</updated>", e) or [None, ""])[1]
            m = re.match(r"(\S+) - (.*?) \((\d+)\) \((\w[\w ]*)\)", title)
            if not m:
                continue
            out.append({"form": m.group(1), "name": m.group(2), "cik": m.group(3), "role": m.group(4), "url": link,
                        "items": re.findall(r"Item (\d+\.\d+)", summ), "ts": _iso(upd)})
        return out or None

    rows, _ = first(f"edgar:{form}", [("edgar atom", atom)])
    return rows
