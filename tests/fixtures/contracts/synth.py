"""SYNTHETIC provider-contract fixtures (R5-02). Every value here is invented. The SHAPE (field names, nesting, string vs
number encodings, timestamp conventions) follows each provider's public response format, so the production parsers in
`lib/grok_the_block/markets/sources.py` are exercised without redistributing any vendor's data.

Developers who want to check the parsers against real responses can save them under tests/fixtures/private/ (gitignored,
never committed); tests/test_private_fixtures.py runs on them when present and reports SKIPPED otherwise."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PROVENANCE = "synthetic"
NY, LDN, CHI = ZoneInfo("America/New_York"), ZoneInfo("Europe/London"), ZoneInfo("America/Chicago")


def _wave(i, base=100.0, amp=0.01):
    return round(base * (1 + amp * math.sin(i * 0.7)), 4)


def weekdays(end: date, n: int):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def yahoo_chart(symbol="SYNTH", days=None, tz="America/New_York", stamp=(9, 30), base=100.0, volume=True):
    """Yahoo chart v8 shape: one daily bar per date, stamped at `stamp` local time in the exchange timezone."""
    days = days or weekdays(date(2026, 10, 28), 30)
    z = ZoneInfo(tz)
    ts = [int(datetime(d.year, d.month, d.day, *stamp, tzinfo=z).timestamp()) for d in days]
    q = {"close": [_wave(i, base) for i in range(len(days))], "open": [_wave(i, base) for i in range(len(days))]}
    if volume:
        q["volume"] = [1_000_000 + 1000 * i for i in range(len(days))]
    return {"chart": {"result": [{"meta": {"symbol": symbol, "currency": "USD", "exchangeTimezoneName": tz, "gmtoffset": -14400},
                                  "timestamp": ts, "indicators": {"quote": [q]}}], "error": None}, "_provenance": PROVENANCE}


def nasdaq_hist(days=None, base=500.0):
    days = days or weekdays(date(2026, 10, 27), 30)
    rows = [{"date": d.strftime("%m/%d/%Y"), "close": f"${_wave(i, base):,.2f}", "volume": f"{20_000_000 + i * 1000:,}",
             "open": f"${base:,.2f}", "high": f"${base * 1.01:,.2f}", "low": f"${base * 0.99:,.2f}"} for i, d in enumerate(reversed(days))]
    return {"data": {"symbol": "SYNTH", "totalRecords": len(rows), "tradesTable": {"asOf": None, "rows": rows}}, "_provenance": PROVENANCE}


def okx_candles(end=date(2026, 10, 28), n=30, base=50_000.0, forming=True):
    """OKX /market/history-candles 1Dutc: newest first, [ts_ms, o, h, l, c, vol, volCcy, volCcyQuote, confirm]."""
    out = []
    for i in range(n):
        d = end - timedelta(days=i)
        t = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()) * 1000
        c = _wave(i, base)
        out.append([str(t), str(c), str(c * 1.01), str(c * 0.99), str(c), "100.5", "5000000", "5000000", "0" if (i == 0 and forming) else "1"])
    return {"code": "0", "msg": "", "data": out, "_provenance": PROVENANCE}


def coinbase_candles(end=date(2026, 10, 28), n=30, base=50_000.0):
    """Coinbase Exchange /candles: newest first, [time_s, low, high, open, close, volume(base)]."""
    out = []
    for i in range(n):
        d = end - timedelta(days=i)
        t = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
        c = _wave(i, base)
        out.append([t, c * 0.99, c * 1.01, c, c, 120.25])
    return out


def treasury_csv(days=None):
    days = days or weekdays(date(2026, 10, 27), 30)
    head = 'Date,"1 Mo","1.5 Month","2 Mo","3 Mo","4 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr","7 Yr","10 Yr","20 Yr","30 Yr"'
    lines = [head]
    for i, d in enumerate(reversed(days)):
        y = 4.0 + 0.01 * math.sin(i)
        lines.append(f"{d.strftime('%m/%d/%Y')}," + ",".join(f"{y + k * 0.05:.2f}" for k in range(14)))
    return "\n".join(lines) + "\n"


def kalshi_market(ticker="SYNTH-26DEC31-T4.50", price="0.4200", prev="0.3000", **kw):
    m = {"ticker": ticker, "event_ticker": (ticker or "SYNTH-X").rsplit("-", 1)[0], "title": "Synthetic question above 4.50?", "yes_sub_title": "Above 4.50",
         "last_price_dollars": price, "previous_price_dollars": prev, "yes_bid_dollars": "0.4100", "yes_ask_dollars": "0.4300",
         "previous_yes_bid_dollars": "0.2900", "previous_yes_ask_dollars": "0.3100", "volume_24h_fp": "1500.00", "volume_fp": "90000.00",
         "open_interest_fp": "12000.00", "open_time": "2026-01-01T15:00:00Z", "close_time": "2026-12-31T21:00:00Z", "status": "active"}
    m.update(kw)
    return m


def kalshi_events(markets=None, category="Economics"):
    return {"events": [{"event_ticker": "SYNTH-26DEC31", "category": category, "markets": markets or [kalshi_market()]}], "cursor": "", "_provenance": PROVENANCE}


def gamma_market(i=0, **kw):
    m = {"id": str(1000 + i), "question": f"Synthetic question {i}?", "conditionId": f"0x{i:064x}", "slug": f"synthetic-question-{i}",
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.42", "0.58"]', "volume24hr": 125000.5, "volume1wk": 500000.0, "volumeNum": 2_000_000.0,
         "liquidityNum": 80000.0, "oneHourPriceChange": 0.01, "oneDayPriceChange": 0.05, "oneWeekPriceChange": 0.1,
         "startDate": "2026-01-01T00:00:00Z", "endDate": "2026-12-31T00:00:00Z", "clobTokenIds": f'["{111 + i}", "{222 + i}"]',
         "bestBid": 0.41, "bestAsk": 0.43, "events": [{"slug": f"synthetic-event-{i}", "title": f"Synthetic event {i}"}]}
    m.update(kw)
    return m


def llama(assets=None):
    def a(sym, now, d1, w1, i):
        return {"id": str(i), "name": f"Synthetic {sym}", "symbol": sym, "gecko_id": f"synthetic-{sym.lower()}", "pegType": "peggedUSD",
                "circulating": {"peggedUSD": now}, "circulatingPrevDay": {"peggedUSD": d1}, "circulatingPrevWeek": {"peggedUSD": w1},
                "chainCirculating": {"Ethereum": {"current": {"peggedUSD": now * 0.6}, "circulatingPrevDay": {"peggedUSD": d1 * 0.6}},
                                     "Tron": {"current": {"peggedUSD": now * 0.4}, "circulatingPrevDay": {"peggedUSD": d1 * 0.4}}}}
    return {"peggedAssets": assets if assets is not None else [a("SUSD", 5e10, 4.9e10, 4.8e10, 1), a("TINY", 5e8, 5e8, 5e8, 2)], "_provenance": PROVENANCE}


def cboe_chain(n=12, timestamp="2026-10-28 15:56:14", underlying=90.0):
    opts = []
    for i in range(n):
        side = "C" if i % 2 else "P"
        opts.append({"option": f"SYNT261231{side}{(80 + i) * 1000:08d}", "bid": 0.5 + i / 10, "ask": 0.6 + i / 10, "open_interest": 1000.0 + i,
                     "volume": 50.0 * (i + 1), "last_trade_price": 0.55 + i / 10, "iv": 0.2, "delta": 0.1})
    return {"timestamp": timestamp, "data": {"symbol": "SYNT", "current_price": underlying, "options": opts}, "_provenance": PROVENANCE}


def nasdaq_chain(last_trade="LAST TRADE: $100.0 (AS OF OCT 28, 2026 11:56 AM ET)"):
    rows = [{"expirygroup": "December 31, 2026", "strike": None}]
    for i in range(4):
        rows.append({"expirygroup": "", "strike": f"{90 + i}.00", "c_Last": "1.10", "c_Bid": "1.00", "c_Ask": "1.20", "c_Volume": "--" if i == 0 else f"{100 * i:,}",
                     "c_Openinterest": f"{1000 + i:,}", "p_Last": "0.90", "p_Bid": "0.80", "p_Ask": "1.00", "p_Volume": f"{50 * i}",
                     "p_Openinterest": "" if i == 3 else "500", "drillDownURL": f"/market-activity/options/synt/synt--261231c{(90 + i) * 1000:08d}"})
    return {"data": {"totalRecord": len(rows), "lastTrade": last_trade, "table": {"rows": rows}}, "_provenance": PROVENANCE}


def okx_perps(n_oi=40, n_f=40, now_ms=1_793_203_200_000):
    oi = {"code": "0", "data": [[str(now_ms - i * 86_400_000), str(3e6 + i), str(3e4 + i), str(2.5e9 + i)] for i in range(n_oi)]}
    fr = {"code": "0", "data": [{"fundingRate": "0.0001", "realizedRate": "0.0001", "fundingTime": str(now_ms - (i + 1) * 28_800_000), "instId": "SYNT-USDT-SWAP"} for i in range(n_f)]}
    cur = {"code": "0", "data": [{"fundingRate": "0.00006", "fundingTime": str(now_ms), "prevFundingTime": str(now_ms - 28_800_000), "instId": "SYNT-USDT-SWAP"}]}
    return oi, fr, cur
