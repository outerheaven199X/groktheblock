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


def _tok(x):
    try:
        return json.loads(x) if isinstance(x, str) else (x or [])
    except ValueError:
        return []


def polymarket_history(token_id: str, interval: str = "1w", fidelity: int = 15) -> list[tuple[int, float]] | None:
    """CLOB price history for one outcome token: [(ts, price)] at `fidelity`-minute spacing."""
    j = get(f"https://clob.polymarket.com/prices-history?market={token_id}&interval={interval}&fidelity={fidelity}", "clob", max_age=300)
    h = (j or {}).get("history") if isinstance(j, dict) else None
    return [(int(p["t"]), float(p["p"])) for p in h] if h else None


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
            "tokenIds": _tok(m.get("clobTokenIds")), "bestBid": _f(m.get("bestBid")), "bestAsk": _f(m.get("bestAsk")),
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
            "prev": _f(m.get("previous_price_dollars")), "yesBid": _f(m.get("yes_bid_dollars")), "yesAsk": _f(m.get("yes_ask_dollars")),
            "prevBid": _f(m.get("previous_yes_bid_dollars")), "prevAsk": _f(m.get("previous_yes_ask_dollars")), "vol24": _f(m.get("volume_24h_fp"), 0.0),
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
            j = get(f"https://{host}/v8/finance/chart/{symbol}?range=6mo&interval=1d", "yahoo", headers={"User-Agent": "Mozilla/5.0"})
            r = (((j or {}).get("chart") or {}).get("result") or [None])[0]
            if not r:
                return None
            q = r["indicators"]["quote"][0]
            rows = [(t, c, v) for t, c, v in zip(r["timestamp"], q["close"], q["volume"]) if c is not None and v is not None]
            return rows or None
        return go

    def nasdaq():
        asset = "etf" if symbol in ETFS else "stocks"
        frm = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 200 * 86400))
        j = get(f"https://api.nasdaq.com/api/quote/{symbol}/historical?assetclass={asset}&fromdate={frm}&limit=150", "nasdaq")
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


def _occ_expiry(code: str) -> str | None:
    """YYYYMMDD from an OCC-style contract code (…YYMMDD[C|P]strike), else None."""
    import re
    m = re.search(r"(\d{6})[CPcp]\d{8}$", code or "")
    return "20" + m.group(1) if m else None


def _snap_ok(ts, now):
    """(ts, issue): a snapshot time that is missing or more than 2 min in the future is an issue (never clamped)."""
    if ts is None:
        return None, "missing snapshot time"
    if ts > now + 120:
        return ts, f"snapshot time is {(ts - now) / 60:.0f} min in the future"
    return ts, None


def parse_cboe(j, now=None) -> dict | None:
    """Cboe delayed chain. Rows without a parseable expiry or with missing volume/OI are rejected and counted.
    priceBasis per row: mid (bid+ask) or last."""
    now = now or int(time.time())
    d = (j or {}).get("data") if isinstance(j, dict) else None
    d = d or {}
    rows, bad = [], 0
    for o in d.get("options") or []:
        exp = _occ_expiry(o.get("option"))
        v, oi = _f(o.get("volume")), _f(o.get("open_interest"))
        if not exp or v is None or oi is None:
            bad += 1; continue
        bid, ask, last = _f(o.get("bid"), 0.0), _f(o.get("ask"), 0.0), _f(o.get("last_trade_price"), 0.0)
        mid = bid > 0 and ask > 0
        rows.append({"contract": o["option"], "volume": v, "oi": oi, "type": "call" if o["option"][-9] in "Cc" else "put", "expiry": exp,
                     "strike": int(o["option"][-8:]) / 1000, "price": (bid + ask) / 2 if mid else last or None,
                     "priceBasis": "mid" if mid else "last" if last else None})
    ts = None
    try:  # Cboe's snapshot timestamp is UTC (checked against wall clock on 2026-10-28)
        ts = int(datetime.strptime((j or {}).get("timestamp", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
    except (ValueError, TypeError, AttributeError):
        ts = None
    ts, issue = _snap_ok(ts, now)
    return {"rows": rows, "rejected": bad, "snapshotTs": ts, "snapshotIssue": issue, "underlying": _f(d.get("current_price"))} if rows else None


def parse_nasdaq(j, symbol, now=None) -> dict | None:
    """Nasdaq option chain (fallback; no underlying price). Expiry from the drill-down OCC code or the group header."""
    import re
    now = now or int(time.time())
    d = ((j or {}).get("data") if isinstance(j, dict) else None) or {}
    rows, bad, group = [], 0, None
    for r in ((d.get("table") or {}).get("rows")) or []:
        if r.get("expirygroup"):
            group = None
            for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
                try:
                    group = datetime.strptime(r["expirygroup"].strip(), fmt).strftime("%Y%m%d"); break
                except ValueError:
                    continue
        if not r.get("strike"):
            continue
        url = r.get("drillDownURL") or ""
        exp = (_occ_expiry(url.split("--")[-1].upper()) if "--" in url else None) or group
        for side, pre in (("call", "c_"), ("put", "p_")):
            rv = str(r.get(pre + "Volume") or "").replace(",", "")
            v = 0.0 if rv == "--" else _f(rv, None)  # Nasdaq prints "--" for no trades today; missing OI is still rejected
            oi = _f(str(r.get(pre + "Openinterest") or "").replace(",", ""), None)
            if v is None or oi is None or not exp:
                bad += 1; continue
            bid, ask, last = (_f(str(r.get(pre + k) or "").replace(",", ""), 0.0) for k in ("Bid", "Ask", "Last"))
            mid = bid > 0 and ask > 0
            rows.append({"contract": f"{symbol} {exp} {r['strike']} {side}", "volume": v, "oi": oi, "type": side, "expiry": exp,
                         "strike": _f(r["strike"]), "price": (bid + ask) / 2 if mid else last or None, "priceBasis": "mid" if mid else "last" if last else None})
    ts = None
    m = re.search(r"AS OF (\w+ \d+, \d{4} \d+:\d+ [AP]M)", (d.get("lastTrade") or "").upper())
    if m:
        from zoneinfo import ZoneInfo
        ts = int(datetime.strptime(m.group(1).title().replace(" Am", " AM").replace(" Pm", " PM"), "%b %d, %Y %I:%M %p").replace(tzinfo=ZoneInfo("America/New_York")).timestamp())
    ts, issue = _snap_ok(ts, now)
    return {"rows": rows, "rejected": bad, "snapshotTs": ts, "snapshotIssue": issue, "underlying": None} if rows else None


def options_chain(symbol: str) -> dict | None:
    """Per-contract volume, open interest and an estimated price (delayed). Cboe first, Nasdaq second."""
    def cboe():
        return parse_cboe(get(f"https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json", "cboe", max_age=600, timeout=60))

    def nasdaq():
        asset = "etf" if symbol in ETFS else "stocks"
        return parse_nasdaq(get(f"https://api.nasdaq.com/api/quote/{symbol}/option-chain?assetclass={asset}&limit=2000&fromdate=all&todate=undefined&excode=oprac&callput=callput&money=all&type=all", "nasdaq-opt", max_age=600), symbol)

    res, via = first(f"options:{symbol}", [("cboe delayed", cboe), ("nasdaq", nasdaq)])
    if res is None:
        return None
    return dict(res, symbol=symbol, via=via, url=f"https://www.cboe.com/delayed_quotes/{symbol.lower()}/quote_table")


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
        j = get(f"{OKX}/market/history-candles?instId={ccy}-USDT&bar=1Dutc&limit=100", "okx")
        rows = [(int(r[0]) // 1000, float(r[4]), float(r[7])) for r in (j or {}).get("data") or []]
        return sorted(rows) or None

    def coinbase():
        j = get(f"{CB}/products/{ccy}-USD/candles?granularity=86400", "coinbase")
        rows = [(int(r[0]), float(r[4]), float(r[5]) * float(r[4])) for r in (j or [])[:100]] if isinstance(j, list) else []
        return sorted(rows) or None

    rows, via = first(f"crypto:{ccy}", [("okx spot", okx), ("coinbase spot", coinbase)])
    if rows is None:
        return None
    return {"symbol": ccy, "rows": rows, "via": via, "url": f"https://www.okx.com/trade-spot/{ccy.lower()}-usdt" if via == "okx spot" else f"https://www.coinbase.com/price/{ccy.lower()}"}


def crypto_perps(ccy: str) -> dict | None:
    """OKX perpetual: daily open interest in contracts AND USD, funding history, and the settlement interval."""
    inst = f"{ccy}-USDT-SWAP"

    def okx():
        return parse_okx_perps(get(f"{OKX}/rubik/stat/contracts/open-interest-history?instId={inst}&period=1D&limit=60", "okx-oi"),
                               get(f"{OKX}/public/funding-rate-history?instId={inst}&limit=100", "okx-funding"),
                               get(f"{OKX}/public/funding-rate?instId={inst}", "okx-funding-now", max_age=60))

    res, _ = first(f"perps:{ccy}", [("okx swap", okx)])
    if res:
        res.update(symbol=ccy, url=f"https://www.okx.com/trade-swap/{ccy.lower()}-usdt-swap")
    return res


def parse_okx_perps(oi, fr, cur) -> dict | None:
    """OKX rubik OI history rows are [ts, oi (contracts), oiCcy (coin), oiUsd] (checked against a saved 2026-10-28
    response). Funding history: each settlement keeps its own interval (time since the previous settlement), so
    a history that switched from 8h to 4h is normalized per period, not with today's interval."""
    def rows(x):
        return (x or {}).get("data") if isinstance(x, dict) and isinstance((x or {}).get("data"), list) else []
    o = []
    for r in rows(oi):
        try:
            o.append((int(r[0]) // 1000, float(r[1]), float(r[3])))
        except (TypeError, ValueError, IndexError):
            continue
    f = []
    for r in rows(fr):
        try:
            f.append((int(r["fundingTime"]) // 1000, float(r.get("realizedRate") or r["fundingRate"])))
        except (TypeError, ValueError, KeyError):
            continue
    o.sort(); f.sort()
    c = (rows(cur) or [{}])[0]
    interval_h = None
    try:
        if c.get("fundingTime") and c.get("prevFundingTime"):
            interval_h = (int(c["fundingTime"]) - int(c["prevFundingTime"])) / 3_600_000
    except (TypeError, ValueError):
        interval_h = None
    # per-settlement interval: gap to the previous settlement; the first one uses the next gap if it exists
    fi = []
    for i, (t, r) in enumerate(f):
        gap = (t - f[i - 1][0]) / 3600 if i else ((f[1][0] - t) / 3600 if len(f) > 1 else interval_h)
        fi.append((t, r, gap if gap and 0 < gap <= 24 else None))
    if not o or not f:
        return None
    return {"oi": o, "funding": fi, "intervalH": interval_h, "next": _f(c.get("fundingRate"))}


def stablecoins() -> list[dict] | None:
    """Circulating supply now vs a day and a week ago (DefiLlama aggregate of on-chain supply)."""
    def llama():
        j = get("https://stablecoins.llama.fi/stablecoins?includePrices=false", "llama", max_age=1800)
        out = []
        for a in (j or {}).get("peggedAssets") or []:
            c = lambda k: _f(((a.get(k) or {}).get("peggedUSD")))  # noqa: E731
            if (c("circulating") or 0) >= 1e9:
                chains = []
                for ch, v in (a.get("chainCirculating") or {}).items():
                    cur_, prev_ = _f(((v.get("current") or {}).get("peggedUSD"))), _f(((v.get("circulatingPrevDay") or {}).get("peggedUSD")))
                    if cur_ is not None and prev_ is not None:
                        chains.append((ch, round(cur_ - prev_)))
                chains.sort(key=lambda x: -abs(x[1]))
                out.append({"symbol": a["symbol"], "name": a["name"], "id": a["id"], "now": c("circulating"), "d1": c("circulatingPrevDay"), "w1": c("circulatingPrevWeek"),
                            "chains": chains[:4],
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
            j = get(f"https://{host}/v8/finance/chart/{sym}?range=6mo&interval=1d", "yahoo", headers={"User-Agent": "Mozilla/5.0"})
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


def edgar_form4_transactions(index_url: str) -> list[dict] | None:
    """Parse non-derivative transactions from one Form 4 (code, shares, price, acquired/disposed)."""
    import os
    import re
    ua = os.environ.get("GTB_SEC_USER_AGENT", "").strip()
    if "@" not in ua:
        return None
    idx = get(index_url, "edgar", as_text=True, max_age=86400, headers={"User-Agent": ua})
    m = re.search(r'href="(/Archives/edgar/data/[^"]+\.xml)"', idx or "")
    if not m:
        return None
    xml = get("https://www.sec.gov" + m.group(1), "edgar", as_text=True, max_age=86400, headers={"User-Agent": ua})
    if not xml:
        return None
    return parse_form4(xml)


def parse_form4(xml: str) -> dict | None:
    """Parse an EDGAR ownershipDocument (Form 4 / 4/A). Returns issuer, reporting owners (by CIK), amendment flag,
    and non-derivative transactions with code, shares, price (None when absent), acquired/disposed."""
    import re
    if not xml or "<ownershipDocument" not in xml:
        return None
    one = lambda tag, t=xml: ((re.search(rf"<{tag}>\s*(?:<value>)?\s*([^<]+?)\s*(?:</value>)?\s*</{tag}>", t, re.S) or [None, None])[1])  # noqa: E731
    owners = []
    for ro in re.findall(r"<reportingOwner>(.*?)</reportingOwner>", xml, re.S):
        cik = one("rptOwnerCik", ro)
        if cik and cik not in owners:
            owners.append(cik)
    tx = []
    for t in re.findall(r"<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>", xml, re.S):
        tx.append({"code": one("transactionCode", t), "shares": _f(one("transactionShares", t)), "price": _f(one("transactionPricePerShare", t)),
                   "ad": one("transactionAcquiredDisposedCode", t)})
    doc = one("documentType") or ""
    return {"documentType": doc, "amendment": doc.endswith("/A"), "issuerCik": one("issuerCik"), "issuerTicker": one("issuerTradingSymbol"),
            "owners": owners, "transactions": tx}
