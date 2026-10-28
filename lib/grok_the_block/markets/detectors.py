"""Signal detectors. Pure functions over normalized rows from sources.py, so they test on fixtures.

Every signal: key (dedupe), source, type, severity, basis (observed | heuristic | inferred), title (plain
English), what, when (unix ts), subject {name, url}, metrics, evidence [{label, url}], limits, topics.
Signals describe unusual activity with evidence. They are not predictions and not trading advice.
"""
from __future__ import annotations

import math
import re
import statistics
import time

SEV = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


def sev_max(a: str, b: str) -> str:
    return a if SEV.index(a) >= SEV.index(b) else b


def _sig(source, typ, severity, basis, title, what, when, subject, metrics, evidence, limits, text="", key_extra=""):
    day = time.strftime("%Y%m%d", time.gmtime(when or 0))
    return {"key": f"{source}:{typ}:{subject.get('id') or subject['name']}:{key_extra or day}", "source": source, "type": typ,
            "severity": severity, "basis": basis, "title": title, "what": what, "when": int(when or 0), "subject": subject,
            "metrics": metrics, "evidence": [e for e in evidence if e.get("url")], "limits": limits,
            "topics": sorted(topics(text or subject["name"]))}


def pct(x):
    return f"{x * 100:.0f}%"


# ---------------- topic matching (for cross-market links) ----------------
TOPICS = {
    "fed-rates": ["fed", "fomc", "rate cut", "rate hike", "interest rate", "powell", "federal funds", "treasury", "yield", "bps", "TLT", "IEF", "SHY", "2Y", "10Y"],
    "inflation": ["inflation", "cpi", "pce", "ppi"],
    "jobs": ["jobs report", "nonfarm", "payroll", "unemployment"],
    "recession": ["recession", "gdp", "HYG"],
    "bitcoin": ["bitcoin", "btc", "COIN", "MSTR", "IBIT"],
    "ethereum": ["ethereum", "eth "],
    "solana": ["solana", "sol "],
    "crypto": ["crypto", "stablecoin", "memecoin", "token"],
    "oil": ["oil", "brent", "wti", "opec", "USO", "XLE"],
    "gold": ["gold", "GLD"],
    "nvidia": ["nvidia", "NVDA", "SMH"],
    "tesla": ["tesla", "elon", "musk", "TSLA"],
    "apple": ["apple", "AAPL"],
    "microsoft": ["microsoft", "MSFT"],
    "ai": ["openai", "anthropic", "gpt", " ai ", "grok", "xai"],
    "stocks": ["s&p", "sp500", "nasdaq", "dow", "SPY", "QQQ", "IWM"],
    "tariffs": ["tariff", "trade war", "trade deal"],
    "elections": ["election", "senate", "house", "governor", "mayor", "midterm", "president"],
    "shutdown": ["shutdown", "debt ceiling"],
    "dollar": ["dollar", "dxy", "UUP"],
}


STOP = {"will", "what", "which", "who", "when", "does", "the", "yes", "next", "before", "after", "above", "below", "between", "than",
        "more", "less", "most", "fewer", "win", "wins", "party", "election", "elections", "price", "reach", "hit", "end", "out", "by",
        "january", "february", "march", "april", "june", "july", "august", "september", "october", "november", "december",
        "democratic", "republican", "republicans", "democrats", "senate", "house", "governor", "president", "presidential", "prime",
        "minister", "legislative", "seats", "inc", "holdings", "report", "market", "markets", "open", "close", "daily", "weekly",
        "major", "average", "winner", "nominee", "nomination", "south", "north", "west", "east", "margin", "victory", "percentage", "points", "united", "states", "new", "first", "last", "game", "team", "world", "this", "that", "with", "from"}


def topics(text: str) -> set[str]:
    t = f" {text} "
    low = t.lower()
    # Named entities (capitalized words) let e.g. a Polymarket and a Kalshi market on the same person link up.
    out = {"name:" + w.lower() for w in re.findall(r"\b[A-Z][a-z]{3,}\b", t) if w.lower() not in STOP}
    for name, words in TOPICS.items():
        for w in words:
            if w.isupper() and re.search(rf"(?<![A-Za-z$]){re.escape(w)}(?![A-Za-z])", t):
                out.add(name); break
            if not w.isupper() and re.search(rf"(?<![a-z]){re.escape(w.lower().strip())}(?![a-z])", low):
                out.add(name); break
    return out


# ---------------- prediction markets ----------------

def pm_odds_jump(m: dict, now: int) -> dict | None:
    """Observed: the leading outcome's price moved sharply in 1h or 24h on real volume."""
    h, d, vol = abs(m.get("change1h") or 0), abs(m.get("change1d") or 0), m.get("vol24") or 0
    if vol < 25_000 or (h < 0.08 and d < 0.15) or m.get("category") == "sports":
        return None
    sev = "HIGH" if (h >= 0.20 or d >= 0.30) and vol >= 250_000 else "MEDIUM" if (h >= 0.10 or d >= 0.20) else "LOW"
    sev, late = _late(m, now, sev)
    win, ch = ("1h", m["change1h"]) if h >= 0.08 and h * 2 >= d else ("24h", m["change1d"])
    p = m["price"]
    return _sig("polymarket", "ODDS_JUMP", sev, "observed",
                f"{m['outcome']} odds {'up' if ch > 0 else 'down'} {abs(ch) * 100:.0f} pts in {win}: “{m['title']}”",
                f"Price now {pct(p)} (was ~{pct(p - ch)}) on ${vol:,.0f} 24h volume.", now,
                {"name": m["title"], "id": m["id"], "url": m["url"]},
                {"price": p, "change": ch, "window": win, "vol24": vol, "liquidity": m.get("liquidity")},
                [{"label": "Polymarket market", "url": m["url"]}, {"label": "Gamma API record", "url": m.get("api")}],
                ["Price change is Polymarket's own 1h/24h figure, sampled at scan time; intraday path not stored."] + late,
                text=f"{m['title']} {m.get('event') or ''}")


def _late(m: dict, now: int, sev: str) -> tuple[str, list[str]]:
    """A move after the event or at resolution is not early warning: downgrade one level and say why."""
    end, p = m.get("endTs"), m.get("price")
    if (end and end - now < 24 * 3600) or (p is not None and (p >= 0.97 or p <= 0.03)):
        return SEV[max(SEV.index(sev) - 1, 0)], ["Market is at or near resolution (end date within 24h or price ≥97%/≤3%), so this is likely the outcome being priced in, not an early warning. Downgraded one level."]
    return sev, []


def pm_volume_spike(m: dict, now: int) -> dict | None:
    """Heuristic: 24h volume far above its own 7-day daily average."""
    vol, wk = m.get("vol24") or 0, m.get("vol1wk") or 0
    base = (wk - vol) / 6 if wk > vol else 0
    if vol < 100_000 or m.get("category") == "sports":
        return None
    age_days = (now - m["startTs"]) / 86400 if m.get("startTs") else 99
    if age_days < 2:
        return None  # a brand-new market has no baseline
    ratio = vol / base if base > 0 else math.inf
    if ratio < 4:
        return None
    sev = "HIGH" if ratio >= 10 and vol >= 1_000_000 else "MEDIUM" if ratio >= 6 else "LOW"
    sev, late = _late(m, now, sev)
    return _sig("polymarket", "VOLUME_SPIKE", sev, "heuristic",
                f"Volume {'∞' if ratio == math.inf else f'{ratio:.0f}×'} its 6-day average: “{m['title']}”",
                f"${vol:,.0f} traded in 24h vs ~${base:,.0f}/day the prior 6 days.", now,
                {"name": m["title"], "id": m["id"], "url": m["url"]},
                {"vol24": vol, "baselinePerDay": round(base, 2), "ratio": None if ratio == math.inf else round(ratio, 1), "price": m["price"]},
                [{"label": "Polymarket market", "url": m["url"]}, {"label": "Gamma API record", "url": m.get("api")}],
                ["Baseline is the 7-day total minus the last 24h, averaged; markets near resolution spike naturally."] + late,
                text=f"{m['title']} {m.get('event') or ''}")


def pm_fresh_wallet_bets(m: dict, trades: list[dict], first_seen: dict[str, int | None], now: int,
                         min_usd: float = 5000, fresh_days: float = 7, moved: bool = False) -> dict | None:
    """Heuristic (inferred when the market also moved): large bets from wallets new to Polymarket."""
    hits = []
    for t in trades:
        fs = first_seen.get(t["wallet"])
        if t["usd"] >= min_usd and fs and t["ts"] - fs <= fresh_days * 86400:
            hits.append(dict(t, ageDays=round((t["ts"] - fs) / 86400, 1)))
    if not hits:
        return None
    total = sum(h["usd"] for h in hits)
    wallets = {h["wallet"] for h in hits}
    sev = "HIGH" if total >= 50_000 and moved else "MEDIUM" if total >= 20_000 or moved else "LOW"
    hits.sort(key=lambda h: -h["usd"])
    ev = [{"label": f"Polygon tx · ${h['usd']:,.0f} {h['side']} {h['outcome']} @ {h['price']:.2f} · wallet {h['ageDays']}d old",
           "url": f"https://polygonscan.com/tx/{h['tx']}"} for h in hits[:6] if h.get("tx")]
    return _sig("polymarket", "FRESH_WALLET_BETS", sev, "inferred" if moved else "heuristic",
                f"{len(wallets)} new wallet{'s' if len(wallets) > 1 else ''} bet ${total:,.0f}: “{m['title']}”",
                f"Wallets whose first Polymarket activity was ≤{fresh_days:g} days before the trade placed ≥${min_usd:,.0f} bets"
                + (" while the odds were moving." if moved else "."), max(h["ts"] for h in hits),
                {"name": m["title"], "id": m["id"], "url": m["url"]},
                {"wallets": len(wallets), "usd": round(total, 2), "trades": len(hits),
                 "largest": [{"wallet": h["wallet"][:6] + "…" + h["wallet"][-4:], "usd": h["usd"], "ageDays": h["ageDays"], "ts": h["ts"]} for h in hits[:5]]},
                ev + [{"label": "Polymarket market", "url": m["url"]}],
                ["Only the most recent large trades are sampled (data-api, ≤200 per market).",
                 "“New” means first Polymarket activity, not first on-chain activity; a fresh proxy wallet can belong to an old trader."],
                text=f"{m['title']} {m.get('event') or ''}")


def kalshi_shock(m: dict, now: int) -> list[dict]:
    out = []
    p, prev, v24 = m.get("price"), m.get("prev"), m.get("vol24") or 0
    subj = {"name": m["title"], "id": m["id"], "url": m["url"]}
    ev = [{"label": "Kalshi market", "url": m["url"]}, {"label": "Kalshi API record", "url": m.get("api")}]
    if m.get("category") == "Sports":
        return out
    if p is not None and prev and v24 >= 2000 and abs(p - prev) >= 0.12 and 0.02 < prev < 0.98:
        ch = p - prev
        sev = "HIGH" if abs(ch) >= 0.25 and v24 >= 20_000 else "MEDIUM" if abs(ch) >= 0.18 else "LOW"
        out.append(_sig("kalshi", "PRICE_SHOCK", sev, "observed", f"Yes price {'up' if ch > 0 else 'down'} {abs(ch) * 100:.0f} pts in a day: “{m['title']}”",
                        f"Last {pct(p)} vs previous-day {pct(prev)} on {v24:,.0f} contracts.", now, subj,
                        {"price": p, "prev": prev, "change": round(ch, 4), "vol24": v24}, ev,
                        ["Compares Kalshi's last trade with its previous-day price; one thin trade can move the last price."],
                        text=f"{m['title']} {m.get('event') or ''}"))
    if m.get("openTs") and v24 >= 10_000:
        age = max((now - m["openTs"]) / 86400, 0)
        if age >= 3:
            base = max(m.get("volume", 0) - v24, 0) / max(age - 1, 1)
            ratio = v24 / base if base > 0 else math.inf
            if ratio >= 5:
                sev = "HIGH" if ratio >= 15 and v24 >= 100_000 else "MEDIUM" if ratio >= 8 else "LOW"
                out.append(_sig("kalshi", "VOLUME_SPIKE", sev, "heuristic",
                                f"Volume {'∞' if ratio == math.inf else f'{ratio:.0f}×'} its lifetime daily average: “{m['title']}”",
                                f"{v24:,.0f} contracts in 24h vs ~{base:,.0f}/day since it opened {age:.0f} days ago.", now, subj,
                                {"vol24": v24, "baselinePerDay": round(base, 1), "ratio": None if ratio == math.inf else round(ratio, 1), "price": p}, ev,
                                ["Baseline is lifetime volume averaged per day; activity naturally rises near close."],
                                text=f"{m['title']} {m.get('event') or ''}"))
    return out


# ---------------- equities / options ----------------

def zscore(series: list[float], x: float) -> float | None:
    if len(series) < 10:
        return None
    sd = statistics.pstdev(series)
    return None if sd == 0 else (x - statistics.mean(series)) / sd


def equity_anomaly(sym: str, rows: list[tuple[int, float, float]], url: str, lookback: int = 20) -> list[dict]:
    """Observed: last session's volume or return far outside the prior `lookback` sessions."""
    if len(rows) < lookback + 2:
        return []
    hist, (t, c, v) = rows[-lookback - 1:-1], rows[-1]
    prev_c = rows[-2][1]
    rets = [math.log(b[1] / a[1]) for a, b in zip(rows[-lookback - 2:-2], rows[-lookback - 1:-1]) if a[1] and b[1]]
    r = math.log(c / prev_c) if prev_c else 0
    vz, rz = zscore([math.log(x[2]) for x in hist if x[2] > 0], math.log(v) if v > 0 else 0), zscore(rets, r)
    out, subj = [], {"name": sym, "id": sym, "url": url}
    ev = [{"label": f"{sym} quote & history", "url": url}]
    if vz is not None and vz >= 2.5:
        sev = "HIGH" if vz >= 4 else "MEDIUM" if vz >= 3 else "LOW"
        out.append(_sig("equities", "VOLUME_Z", sev, "observed", f"{sym} volume {vz:.1f}σ above its 20-day norm",
                        f"{v:,.0f} shares vs ~{statistics.mean(x[2] for x in hist):,.0f}/day; close {r * 100:+.1f}%.", t, subj,
                        {"volume": v, "z": round(vz, 2), "return": round(r, 4)}, ev, ["Daily bars only; intraday timing unknown."], text=sym))
    if rz is not None and abs(rz) >= 2.5:
        sev = "HIGH" if abs(rz) >= 4 else "MEDIUM" if abs(rz) >= 3 else "LOW"
        out.append(_sig("equities", "PRICE_Z", sev, "observed", f"{sym} {'jumped' if r > 0 else 'fell'} {abs(r) * 100:.1f}% ({abs(rz):.1f}σ day)",
                        f"Close {c:,.2f} vs {prev_c:,.2f}; a {abs(rz):.1f}σ move against the last 20 sessions.", t, subj,
                        {"close": c, "return": round(r, 4), "z": round(rz, 2)}, ev, ["Daily closes only."], text=sym))
    return out


def options_unusual(sym: str, rows: list[dict], url: str, now: int) -> dict | None:
    """Heuristic: contracts trading far more than their open interest (new positioning)."""
    soon = time.strftime("%Y%m%d", time.gmtime(now + 86400))
    hot = [r for r in rows if r["volume"] >= 1000 and r["volume"] >= 2 * max(r["oi"], 1) and not (r.get("expiry") and r["expiry"] <= soon)]
    if not hot:
        return None
    vol = sum(r["volume"] for r in hot)
    calls = sum(r["volume"] for r in hot if r["type"] == "call")
    tot_c = sum(r["volume"] for r in rows if r["type"] == "call") or 1
    tot_p = sum(r["volume"] for r in rows if r["type"] == "put")
    hot.sort(key=lambda r: -r["volume"] / max(r["oi"], 1))
    tilt = "calls" if calls >= vol * 0.65 else "puts" if calls <= vol * 0.35 else "mixed"
    big = sum(1 for r in hot if r["volume"] >= 5 * max(r["oi"], 1))
    sev = "HIGH" if vol >= 50_000 and big >= 5 else "MEDIUM" if vol >= 10_000 else "LOW"
    return _sig("options", "UNUSUAL_OPTIONS", sev, "heuristic",
                f"{sym}: {len(hot)} option contract{'s' if len(hot) > 1 else ''} traded ≥2× open interest ({tilt})",
                f"{vol:,.0f} contracts in contracts where volume exceeds open interest; total put/call {tot_p / tot_c:.2f}.", now,
                {"name": sym, "id": sym, "url": url},
                {"contracts": len(hot), "volume": vol, "tilt": tilt, "putCall": round(tot_p / tot_c, 2),
                 "top": [{"contract": r["contract"], "volume": r["volume"], "oi": r["oi"]} for r in hot[:5]]},
                [{"label": f"{sym} delayed option chain", "url": url}],
                ["Same-day and next-day expiries (0DTE/1DTE) are excluded. Delayed quotes (~15 min). Volume > open interest suggests new positions but cannot show direction, buyer or intent; hedges look the same."],
                text=sym)


# ---------------- Treasuries ----------------

def treasury_signals(rows: list[tuple[str, dict]], url: str) -> list[dict]:
    if len(rows) < 7:
        return []
    out = []
    (d0, y0), (d1, y1) = rows[-2], rows[-1]
    when = int(time.mktime(time.strptime(d1, "%Y-%m-%d")))
    ev = [{"label": "US Treasury daily par yield curve", "url": url}]
    subj = lambda n: {"name": n, "id": n, "url": url}  # noqa: E731
    for k in ("2Y", "10Y", "30Y"):
        if k in y0 and k in y1:
            bp = (y1[k] - y0[k]) * 100
            wk = next((y for d, y in rows[-6:-5]), {})
            bp5 = (y1[k] - wk[k]) * 100 if k in wk else 0
            if abs(bp) >= 10 or abs(bp5) >= 25:
                big = abs(bp) >= 15 or abs(bp5) >= 40
                out.append(_sig("treasury", "YIELD_MOVE", "HIGH" if big else "MEDIUM", "observed",
                                f"{k} Treasury yield {'+' if bp >= 0 else ''}{bp:.0f} bp in a day ({'+' if bp5 >= 0 else ''}{bp5:.0f} bp in 5)",
                                f"{k} at {y1[k]:.2f}% on {d1} vs {y0[k]:.2f}% on {d0}.", when, subj(f"{k} yield"),
                                {"yield": y1[k], "bp1d": round(bp, 1), "bp5d": round(bp5, 1)}, ev, ["End-of-day par yields; published the next business day."],
                                text=f"treasury {k} yield", key_extra=d1))
    if "2Y" in y1 and "10Y" in y1 and "2Y" in y0 and "10Y" in y0:
        s1, s0 = (y1["10Y"] - y1["2Y"]) * 100, (y0["10Y"] - y0["2Y"]) * 100
        week = rows[-6][1]
        s5 = (week["10Y"] - week["2Y"]) * 100 if "2Y" in week and "10Y" in week else s0
        crossed = (s1 < 0) != (s0 < 0) or (s1 < 0) != (s5 < 0)
        if crossed or abs(s1 - s5) >= 15:
            out.append(_sig("treasury", "CURVE_INVERSION" if s1 < 0 and crossed else "CURVE_SHIFT", "HIGH" if crossed else "MEDIUM", "observed",
                            f"2s10s curve {'inverted' if s1 < 0 and crossed else 'un-inverted' if crossed else ('steepened' if s1 > s5 else 'flattened')}: {s1:+.0f} bp",
                            f"10Y minus 2Y is {s1:+.0f} bp on {d1} (was {s0:+.0f} bp the day before, {s5:+.0f} bp five sessions ago).", when,
                            subj("2s10s spread"), {"spreadBp": round(s1, 1), "prevBp": round(s0, 1), "fiveDayAgoBp": round(s5, 1)}, ev,
                            ["End-of-day data. A curve shift is context for rates-sensitive markets, not a signal by itself."],
                            text="treasury yield 2Y 10Y", key_extra=d1))
    return out


# ---------------- cross-market ----------------

def cross_market(signals: list[dict], now: int, window_h: float = 48) -> list[dict]:
    """Inferred: signals from 2+ different sources share a topic within the window."""
    by: dict[str, list[dict]] = {}
    for s in signals:
        if s["source"] == "cross" or now - s["when"] > window_h * 3600 or SEV.index(s["severity"]) < 1:
            continue
        for t in s["topics"]:
            by.setdefault(t, []).append(s)
    out, taken = [], []
    for t, ss in sorted(by.items(), key=lambda kv: (not kv[0].startswith("name:"), -len(kv[1]))):
        srcs = sorted({s["source"] for s in ss})
        if len(srcs) < 2:
            continue
        keys = {s["key"] for s in ss}
        if len(keys & set().union(*taken)) >= 0.5 * len(keys):
            continue  # same cluster already reported under a broader topic
        taken.append(keys)
        ss = sorted(ss, key=lambda s: (-SEV.index(s["severity"]), -s["when"]))[:8]
        top = ss[0]["severity"]
        sev = SEV[min(SEV.index(top), 3)] if len(srcs) >= 3 else SEV[min(SEV.index(top), 2)]
        first_ts = min(s["when"] for s in ss)
        out.append(_sig("cross", "CROSS_MARKET", sev, "inferred",
                        f"{len(ss)} unusual moves on “{t.removeprefix('name:').title() if t.startswith('name:') else t}” across {', '.join(srcs)}",
                        "Separate markets moved on the same theme within " + f"{window_h:g}h: " + "; ".join(s["title"] for s in ss[:3]) + ".",
                        max(s["when"] for s in ss), {"name": t, "id": t, "url": ss[0]["subject"]["url"]},
                        {"sources": srcs, "signals": [s["key"] for s in ss], "firstAt": first_ts},
                        [e for s in ss[:4] for e in s["evidence"][:1]],
                        ["Matched by topic keywords and tickers, not by a shared actor. Co-movement on a theme is context, not proof of coordination."],
                        text=t, key_extra=f"{','.join(srcs)}:{time.strftime('%Y%m%d', time.gmtime(now))}"))
    return out


def solana_from_reports(reports: list[dict], now: int, window_h: float = 72) -> list[dict]:
    """Re-surface on-chain alerts from local Grok The Block watch reports (no network)."""
    out = []
    for r in reports:
        if r.get("kind") != "watch":
            continue
        tok = r.get("token") or {}
        for a in (r.get("recentAlerts") or []):
            ts = int(a.get("timestamp") or a.get("ts") or 0)
            if now - ts > window_h * 3600:
                continue
            ev = [e if isinstance(e, dict) else {"label": "evidence", "url": e} for e in (a.get("evidence") or ([{"label": "transaction", "url": a["url"]}] if a.get("url") else []))]
            sev = a.get("severity") or ("HIGH" if a.get("type") in ("RUG", "INSIDER_MOVE", "LP_UNLOCK", "LIQUIDITY_DROP") else "MEDIUM")
            name = f"${tok.get('symbol')}"
            out.append({"key": f"solana:{a.get('key')}", "source": "solana", "type": a.get("type", "ALERT"), "severity": sev,
                        "basis": "observed", "title": f"{name}: {a.get('type', 'alert').replace('_', ' ').lower()}",
                        "what": a.get("text") or a.get("detail") or (f"{a.get('amountSol')} SOL" + (f" by wallet {str(a.get('wallet'))[:4]}…{str(a.get('wallet'))[-4:]}" if a.get("wallet") else "") if a.get("amountSol") is not None else ""), "when": ts,
                        "subject": {"name": name, "id": tok.get("mint"), "url": f"https://solscan.io/token/{tok.get('mint')}"},
                        "metrics": {k: a[k] for k in ("before", "after", "sol") if k in a}, "evidence": [e for e in ev if e.get("url")],
                        "limits": ["From your local watch-token runs; only watched tokens are covered."],
                        "topics": sorted(topics(f"solana crypto token {name}"))})
    return out


# ---------------- crypto (CEX) ----------------

def crypto_spot(ccy: str, rows: list[tuple], url: str) -> list[dict]:
    out = equity_anomaly(ccy, rows, url)  # same z-score logic on daily quote volume and returns
    for s in out:
        s["source"] = "crypto"; s["key"] = "crypto:" + s["key"].split(":", 1)[1]
        s["topics"] = sorted(set(s["topics"]) | topics(f"crypto {CRYPTO_NAMES.get(ccy, ccy)}"))
        s["limits"] = ["Daily candles in UTC; the current day may be partial."]
    return out


CRYPTO_NAMES = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}


def crypto_perp_shock(ccy: str, oi: list[tuple], funding: list[tuple], url: str) -> list[dict]:
    out, subj = [], {"name": f"{ccy} perpetual", "id": f"{ccy}-PERP", "url": url}
    ev = [{"label": f"OKX {ccy}-USDT perpetual", "url": url}]
    text = f"crypto {CRYPTO_NAMES.get(ccy, ccy)}"
    if len(oi) >= 8:
        (t1, v1), v0 = oi[-1], oi[-2][1]
        wk = oi[-8][1]
        ch, chw = (v1 - v0) / v0 if v0 else 0, (v1 - wk) / wk if wk else 0
        if abs(ch) >= 0.10 or abs(chw) >= 0.25:
            sev = "HIGH" if abs(ch) >= 0.20 or abs(chw) >= 0.40 else "MEDIUM"
            out.append(_sig("crypto", "OI_SHOCK", sev, "observed", f"{ccy} perp open interest {ch * 100:+.0f}% in a day ({chw * 100:+.0f}% in 7)",
                            f"OKX open interest ${v1 / 1e9:.2f}B vs ${v0 / 1e9:.2f}B the day before.", t1, subj,
                            {"oiUsd": v1, "change1d": round(ch, 4), "change7d": round(chw, 4)}, ev,
                            ["One venue (OKX). Open interest across all exchanges can differ."], text=text))
    if len(funding) >= 6:
        t, r = funding[-1]
        base = [x[1] for x in funding[:-1]]
        z = zscore(base, r) if len(base) >= 10 else None
        if abs(r) >= 0.0005 or (z is not None and abs(z) >= 4 and abs(r) >= 0.0002):
            out.append(_sig("crypto", "FUNDING_EXTREME", "HIGH" if abs(r) >= 0.001 else "MEDIUM", "observed",
                            f"{ccy} perp funding {r * 100:+.3f}% per 8h ({'longs' if r > 0 else 'shorts'} paying)",
                            f"Latest OKX funding {r * 100:+.4f}% vs a recent average of {statistics.mean(base) * 100:+.4f}%.", t, subj,
                            {"funding": r, "z": None if z is None else round(z, 2)}, ev,
                            ["Funding shows crowded positioning, not direction of the next move."], text=text))
    return out


def stablecoin_flows(rows: list[dict], now: int) -> list[dict]:
    out = []
    for a in rows:
        d1 = a["now"] - (a["d1"] or a["now"]); w1 = a["now"] - (a["w1"] or a["now"])
        p1 = d1 / a["d1"] if a["d1"] else 0
        if abs(d1) >= 500e6 or abs(p1) >= 0.02:
            sev = "HIGH" if abs(d1) >= 2e9 or abs(p1) >= 0.05 else "MEDIUM"
            out.append(_sig("stablecoins", "SUPPLY_MINT" if d1 > 0 else "SUPPLY_BURN", sev, "observed",
                            f"{a['symbol']} supply {'+' if d1 > 0 else '−'}${abs(d1) / 1e6:,.0f}M in a day ({'minted' if d1 > 0 else 'burned/redeemed'})",
                            f"Circulating ${a['now'] / 1e9:,.2f}B; {w1 / 1e6:+,.0f}M over 7 days.", now,
                            {"name": a["symbol"], "id": a["symbol"], "url": a["url"]}, {"change1d": round(d1), "change7d": round(w1), "pct1d": round(p1, 4)},
                            [{"label": f"{a['name']} supply by chain (DefiLlama)", "url": a["url"]}],
                            ["Aggregate on-chain supply from DefiLlama, not individual mint/burn transactions; bridging can shift chains without a mint."],
                            text=f"crypto stablecoin {a['name']}"))
    return out


# ---------------- FX / commodities / volatility ----------------

def macro_move(sym: str, name: str, rows: list[tuple], url: str) -> list[dict]:
    if len(rows) < 22:
        return []
    (t, c, _), prev = rows[-1], rows[-2][1]
    rets = [math.log(b[1] / a[1]) for a, b in zip(rows[-22:-2], rows[-21:-1]) if a[1] and b[1]]
    r = math.log(c / prev) if prev else 0
    z = zscore(rets, r)
    vix = sym == "^VIX"
    if not ((z is not None and abs(z) >= 2.5) or (vix and (abs(c / prev - 1) >= 0.20 or c >= 30))):
        return []
    zz = abs(z or 0)
    sev = "HIGH" if zz >= 4 or (vix and (c / prev - 1 >= 0.30 or c >= 35)) else "MEDIUM" if zz >= 3 or vix else "LOW"
    words = {"^VIX": "volatility fear", "DX-Y.NYB": "dollar", "GC=F": "gold", "CL=F": "oil crude", "EURUSD=X": "dollar euro", "USDJPY=X": "dollar yen"}
    return [_sig("macro", "MACRO_MOVE", sev, "observed", f"{name} {'up' if r > 0 else 'down'} {abs(c / prev - 1) * 100:.1f}%" + (f" ({zz:.1f}σ day)" if z else ""),
                 f"Last {c:,.4g} vs {prev:,.4g} the prior session.", t, {"name": name, "id": sym, "url": url},
                 {"close": c, "return": round(r, 4), "z": None if z is None else round(z, 2)}, [{"label": f"{name} chart", "url": url}],
                 ["Daily closes (futures/FX via Yahoo); intraday path unknown."], text=f"{words.get(sym, '')} {name}")]


# ---------------- SEC EDGAR events ----------------
MATERIAL_8K = {"1.01": "material agreement", "1.02": "agreement terminated", "1.03": "bankruptcy", "2.01": "acquisition or disposal",
               "2.04": "triggering event on debt", "2.05": "exit/restructuring costs", "2.06": "material impairment", "3.01": "delisting notice",
               "4.02": "prior financials can't be relied on", "5.01": "change in control", "5.02": "officer/director change"}
SEVERE_8K = {"1.03", "2.04", "3.01", "4.02", "5.01"}


def edgar_events(form4: list[dict] | None, eightk: list[dict] | None, now: int) -> list[dict]:
    out = []
    by: dict[str, list[dict]] = {}
    for f in form4 or []:
        if f["role"] == "Issuer":
            by.setdefault(f["cik"], []).append(f)
    for cik, fs in by.items():
        if len(fs) >= 3:
            n = fs[0]["name"]
            out.append(_sig("sec", "INSIDER_FILING_CLUSTER", "MEDIUM" if len(fs) >= 5 else "LOW", "heuristic",
                            f"{len(fs)} insider Form 4 filings for {n} in the latest EDGAR feed",
                            "Several officers/directors reported trades at once. Open the filings for buy vs sell and size.", max(f["ts"] or now for f in fs),
                            {"name": n, "id": cik, "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4"},
                            {"filings": len(fs)}, [{"label": f"Form 4 · {n}", "url": f["url"]} for f in fs[:4]],
                            ["Counts filings only; transaction direction and size are in each filing. Clusters also follow routine grant dates."],
                            text=n))
    seen = set()
    for f in eightk or []:
        items = [i for i in f["items"] if i in MATERIAL_8K]
        if not items or f["cik"] in seen:
            continue
        seen.add(f["cik"])
        severe = [i for i in items if i in SEVERE_8K]
        out.append(_sig("sec", "8K_EVENT", "HIGH" if severe else "LOW" if items == ["5.02"] else "MEDIUM", "observed",
                        f"{f['name']} 8-K: " + ", ".join(MATERIAL_8K[i] for i in items),
                        "Items " + ", ".join(items) + " filed with the SEC.", f["ts"] or now,
                        {"name": f["name"], "id": f["cik"], "url": f["url"]}, {"items": items}, [{"label": "8-K filing index", "url": f["url"]}],
                        ["Filing feed is the latest ~100 filings; item codes only, not the full text."], text=f["name"]))
    return out


# ---------------- anomaly convergence ----------------

BROAD_TOPICS = {"crypto", "elections", "stocks", "ai", "recession"}


def convergence(cross: list[dict], sigs: list[dict]) -> None:
    """Score each cross-market cluster 0-100: independent sources, severity, basis and how tight the timing is."""
    by = {s["key"]: s for s in sigs}
    w = {"observed": 1.0, "heuristic": 0.7, "inferred": 0.5}
    for c in cross:
        mem = [by[k] for k in c["metrics"]["signals"] if k in by]
        srcs = {m["source"] for m in mem}
        span_h = (max(m["when"] for m in mem) - min(m["when"] for m in mem)) / 3600 if mem else 48
        sev = sum(SEV.index(m["severity"]) * w[m["basis"]] for m in mem) / max(len(mem), 1)
        broad = c["subject"]["id"] in BROAD_TOPICS
        score = min(100, round((0.6 if broad else 1.0) * (22 * (len(srcs) - 1) + 12 * sev + 10 * min(len(mem), 5) / 5 + 10 * max(0, 1 - span_h / 48))))
        c["metrics"].update(convergence=score, broadTopic=broad, independentSources=len(srcs), spanHours=round(span_h, 1),
                            chain=[{"key": m["key"], "source": m["source"], "severity": m["severity"], "basis": m["basis"], "title": m["title"],
                                    "when": m["when"], "url": (m["evidence"] or [{"url": m["subject"]["url"]}])[0]["url"]} for m in sorted(mem, key=lambda m: m["when"])])
        c["severity"] = "HIGH" if score >= 75 and len(srcs) >= 3 else "MEDIUM" if score >= 45 else "LOW"
        c["title"] = f"Convergence {score}: " + c["title"]
        if broad:
            c["limits"] = c["limits"] + ["Broad theme: the score is discounted 40% because many unrelated markets share this topic."]
