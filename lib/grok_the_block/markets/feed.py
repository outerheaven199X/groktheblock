"""Run selected sources, apply detectors, and build one signals report (kind: "signals", version 2)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .. import data as D
from . import detectors as X
from . import entities as EN
from . import events as EV
from . import lifecycle as LC
from . import sources as S
from . import timebase as T

DEFAULT_TICKERS = ["SPY", "QQQ", "IWM", "TLT", "HYG", "GLD", "USO", "UUP", "XLE", "NVDA", "TSLA", "AAPL", "MSFT", "COIN", "MSTR"]
DEFAULT_OPTIONS = ["SPY", "QQQ", "NVDA", "TSLA", "COIN", "TLT"]
SOURCES = ["polymarket", "kalshi", "equities", "options", "treasury", "crypto", "stablecoins", "macro", "sec", "solana"]
CRYPTO = ["BTC", "ETH", "SOL"]
NOT_INCLUDED = [
    {"source": "Binance / Bybit public APIs", "why": "geo-blocked (HTTP 451/403) from the build machine, so they could not be verified; OKX and Coinbase are used instead"},
    {"source": "Transaction-level stablecoin mint/burn", "why": "keyless Etherscan V1 is retired; aggregate supply changes (DefiLlama) are reported as SUPPLY_CHANGE instead"},
    {"source": "Stooq", "why": "serves a JavaScript challenge, so it is not machine-readable"},
    {"source": "Options aggressor / trade-level prints, intraday equity bars", "why": "not available from the free delayed sources; those detectors are marked limited"},
    {"source": "Earnings calendar", "why": "no free official schedule; listed tickers are not tagged for earnings"},
]
DISCLAIMER = ("Not financial advice. Grok The Block flags unusual activity in selected public market data, with the evidence behind it, "
              "at the next observation or scan, subject to each provider's latency. A signal is not a prediction, a recommendation to "
              "buy or sell, or an accusation against anyone. Rankings are uncalibrated; no historical hit rate or lead time has been measured.")

NEXT = {
    "polymarket": ("Open the market and its recent trades", "check whether a public event explains the repricing", "Show the Polymarket trades behind “{t}” with Grok The Block"),
    "kalshi": ("Check the Kalshi order book and trades", "the previous-day comparison can hide intraday timing", "Pull recent Kalshi trades for {id} with Grok The Block"),
    "equities": ("Look for the news or filing behind the move", "daily outliers usually have a public catalyst", "What news or filings hit {id} on this session?"),
    "options": ("Inspect the flagged contracts", "volume over open interest doesn't show direction or intent", "Show the flagged {id} option contracts from the Grok The Block signals feed"),
    "treasury": ("Compare against the rates calendar", "check auctions, data releases and Fed communication", "Which scheduled rates events fall around this Treasury move?"),
    "cross": ("Open the evidence dossier", "check the availability-time order and whether a public event explains it", "Show the dossier and timeline for {t} in Grok The Block"),
    "crypto": ("Check spot vs perp positioning", "OI and funding show leverage, not direction", "Show the Grok The Block crypto signals for {id}"),
    "stablecoins": ("Look at the per-chain supply view", "aggregate changes can be bridging or revisions", "Which chains did {id} supply change on today?"),
    "macro": ("Line it up against the macro calendar", "macro moves reprice related markets", "What moved {t} today, and which related markets didn't?"),
    "sec": ("Read the filing", "filings are the primary source", "Summarize the latest SEC filing for {t}"),
    "solana": ("Open the token's watch report", "on-chain alert from your watchlist", "Show the Grok The Block watch report for {t}"),
}


def _src_status(fetch_ok: bool, partial: bool, degraded_note: str | None, fresh: tuple[str, str] | None) -> tuple[str, str]:
    if not fetch_ok:
        return "UNAVAILABLE", "request failed or returned unusable data"
    if fresh and fresh[0] == "STALE":
        return "STALE", fresh[1]
    if partial or degraded_note:
        return "DEGRADED", degraded_note or "partial universe"
    return "HEALTHY", fresh[1] if fresh else "fresh"


def run(sources: list[str] | None = None, tickers: list[str] | None = None, option_tickers: list[str] | None = None,
        pm_limit: int = 200, trace_markets: int = 6, history_markets: int = 20, local_reports: list[dict] | None = None,
        now: int | None = None, calendar: dict | None = None) -> dict:
    sources = sources or SOURCES
    now = now or int(time.time())
    X.reset()
    cal = calendar if calendar is not None else EV.load()
    sigs: list[dict] = []
    status: dict[str, dict] = {}
    limits = [{"kind": "latency", "text": "Signals appear at the next observation or scan, subject to each provider's latency (options ~15 min delayed; equities, FX and Treasuries are daily)."},
              {"kind": "heuristic", "text": "Thresholds are the review's proposed shadow-mode starting settings, not optimized or validated cutoffs."},
              {"kind": "inferred", "text": "Convergence links observations through canonical entities and counts one observation per causal family; it shows co-occurrence, not a shared actor or causality."},
              {"kind": "unvalidated", "text": "No historical hit rate or lead time has been measured on real history. Rankings are uncalibrated."}]

    def base(src, st, cov, lim=()):
        return {"ingestTs": now, "status": st, "coverage": cov, "limitations": list(lim)}

    def put(src, state, detail, cov, last_valid=None, **kw):
        status[src] = {"state": state, "detail": detail, "coverage": cov, "lastValidAt": T.iso(last_valid), "lastValidTs": last_valid, **kw}

    if "polymarket" in sources:
        pm = S.polymarket_markets(pm_limit)
        if pm is None:
            put("polymarket", "UNAVAILABLE", D.PROVIDERS.get("polymarket", {}).get("detail"), {"universe": "open markets by 24h volume", "observed": 0})
        else:
            sports = sum(1 for m in pm if m.get("category") == "sports")
            cov = {"universe": f"top {pm_limit} open markets by 24h volume", "observed": len(pm) - sports, "sampleFraction": None,
                   "exclusions": [f"{sports} live sports/esports markets skipped"]}
            ob = base("polymarket", "HEALTHY", cov)
            cand = sorted([m for m in pm if m.get("category") != "sports" and (m.get("vol24") or 0) >= 25_000],
                          key=lambda m: -abs(m.get("change1h") or 0) * (m.get("vol24") or 0))[:history_markets]
            hist_ok = 0
            hists = {}
            for m in cand:
                if m.get("tokenIds"):
                    h = S.polymarket_history(m["tokenIds"][0], "1w", 15)
                    if h:
                        hists[m["id"]] = h; hist_ok += 1
            moved = {}
            for m in pm:
                s = X.pm_odds_jump(m, ob, hists.get(m["id"]))
                if s:
                    s["_event"] = m.get("event"); sigs.append(s); moved[m["id"]] = True
                s = X.pm_volume_spike(m, ob)
                if s:
                    s["_event"] = m.get("event"); sigs.append(s); moved.setdefault(m["id"], False)
            tr_cand = [m for m in pm if m["id"] in moved][:trace_markets]
            traced = failed = 0
            for m in tr_cand:
                trades = S.polymarket_trades(m["id"], min_usd=25_000)
                if trades is None:
                    failed += 1; continue
                traced += 1
                fs = {w: S.polymarket_first_seen(w) for w in list(dict.fromkeys(t["wallet"] for t in sorted(trades, key=lambda t: -t["usd"])))[:8]}
                s = X.pm_fresh_activity(m, trades, fs, ob, moved=moved.get(m["id"], False))
                if s:
                    sigs.append(s)
            cov.update(priceHistory=f"{hist_ok}/{len(cand)} most-active markets had CLOB 15-minute history", addressTracing=f"{traced} market(s), ≤8 addresses each")
            st, note = ("DEGRADED", f"address tracing failed on {failed} market(s)") if failed else ("HEALTHY", D.PROVIDERS["polymarket"]["detail"])
            put("polymarket", st, note, cov, now)

    if "kalshi" in sources:
        km = S.kalshi_markets()
        if km is None:
            put("kalshi", "UNAVAILABLE", D.PROVIDERS.get("kalshi", {}).get("detail"), {"universe": "open events (non-sports)", "observed": 0})
        else:
            cov = {"universe": "first 2,000 open events, Sports category and parlays excluded", "observed": len(km), "active24h": sum(1 for m in km if m["vol24"] > 0),
                   "sampleFraction": None, "exclusions": ["Sports category", "multivariate parlays"]}
            ob = base("kalshi", "HEALTHY", cov)
            for m in km:
                for s in X.kalshi_shock(m, ob):
                    s["_event"] = m.get("event"); sigs.append(s)
            put("kalshi", "HEALTHY", D.PROVIDERS["kalshi"]["detail"], cov, now)

    def daily_source(src, items, fetch, name_of=lambda s: None):
        bad, latest, fb = [], [], []
        pend = []
        for sym in items:
            d = fetch(sym)
            if d is None:
                bad.append(sym); continue
            if d.get("via", "").startswith("nasdaq") or d.get("via", "").startswith("coinbase"):
                fb.append(sym)
            latest.append(d["rows"][-1][0]); pend.append((sym, d))
        last = max(latest) if latest else None
        evt = (X._close_ts(last) if src in ("equities", "macro") else last + 86400) if last else None
        fresh = T.freshness(src, evt, now) if evt else None
        cov = {"universe": f"{len(items)} configured: {', '.join(items)}", "observed": len(pend), "sampleFraction": round(len(pend) / len(items), 3) if items else 0,
               "exclusions": [f"unavailable: {', '.join(bad)}"] if bad else []}
        st, note = _src_status(bool(pend), bool(bad), f"fallback provider for {', '.join(fb)}" if fb else None, fresh)
        ob = base(src, st, cov)
        return pend, ob, st, note, cov, evt

    if "equities" in sources:
        tick = tickers or DEFAULT_TICKERS
        pend, ob, st, note, cov, evt = daily_source("equities", tick, S.equity_daily)
        for sym, d in pend:
            sigs += X.daily_anomaly("equities", sym, d["rows"], d["url"], ob)
        put("equities", st, note, cov, evt)

    if "options" in sources:
        tick = option_tickers or DEFAULT_OPTIONS
        bad, rej, snaps, fb = [], 0, [], []
        chains = []
        for sym in tick:
            o = S.options_chain(sym)
            if o is None:
                bad.append(sym); continue
            rej += o.get("rejected", 0); snaps.append(o.get("snapshotTs") or 0); chains.append((sym, o))
            if o["via"] == "nasdaq":
                fb.append(sym)
        snap = max(snaps) if snaps else None
        cov = {"universe": f"{len(tick)} underlyings: {', '.join(tick)}", "observed": len(chains), "sampleFraction": round(len(chains) / len(tick), 3),
               "exclusions": ([f"unavailable: {', '.join(bad)}"] if bad else []) + ([f"{rej} contracts rejected (unparsed expiry)"] if rej else []),
               "routing": "expiry ≤ next session → SHORT_DATED_OPTIONS (conservative); later expiries → UNUSUAL_OPTIONS_VOLUME"}
        st, note = _src_status(bool(chains), bool(bad), f"Nasdaq fallback (no underlying price) for {', '.join(fb)}" if fb else None,
                               T.freshness("options", snap, now) if snap else ("STALE", "no snapshot time"))
        ob = base("options", st, cov)
        for sym, o in chains:
            sigs += X.options_activity(sym, o, o["url"], ob)
        put("options", st, note, cov, snap)

    if "treasury" in sources:
        c = S.treasury_curve()
        if c is None:
            put("treasury", "UNAVAILABLE", D.PROVIDERS.get("treasury", {}).get("detail"), {"universe": "daily par curve", "observed": 0})
        else:
            d, y = c["rows"][-1]
            evt = T.ny_ts(T.date.fromisoformat(d), 15, 30)
            cov = {"universe": "2Y, 10Y, 30Y, 2s10s", "observed": 4, "sampleFraction": 1.0, "exclusions": []}
            st, note = _src_status(True, False, "FRED fallback" if c["via"] == "FRED" else None, T.freshness("treasury", evt, now))
            sigs += X.treasury_signals(c["rows"], c["url"], base("treasury", st, cov))
            put("treasury", st, note, cov, evt, asOf=d, curve=y)

    if "crypto" in sources:
        bad, pend, perps = [], [], []
        for ccy in CRYPTO:
            dd, pp = S.crypto_daily(ccy), S.crypto_perps(ccy)
            if dd is None and pp is None:
                bad.append(ccy); continue
            if dd: pend.append((ccy, dd))
            if pp: perps.append((ccy, pp))
        last = max((d["rows"][-1][0] for _, d in pend), default=None)
        cov = {"universe": "BTC, ETH, SOL (OKX spot + perps; Coinbase spot fallback)", "observed": len(CRYPTO) - len(bad), "sampleFraction": round((len(CRYPTO) - len(bad)) / len(CRYPTO), 3),
               "exclusions": ["single venue (OKX) for perps", "intraday OI (1h/4h) not used"] + ([f"unavailable: {', '.join(bad)}"] if bad else [])}
        st, note = _src_status(bool(pend or perps), bool(bad), None, T.freshness("crypto", min(last + 86400, now) if last else None, now) if last else None)
        ob = base("crypto", st, cov)
        for ccy, d in pend:
            sigs += X.daily_anomaly("crypto", ccy, d["rows"], d["url"], ob, name=f"{ccy} spot")
        for ccy, p in perps:
            sigs += X.crypto_perp_shock(ccy, p["oi"], p["funding"], p["url"], ob, p.get("intervalH"))
        put("crypto", st, note, cov, min(last + 86400, now) if last else None)

    if "stablecoins" in sources:
        rows = S.stablecoins()
        if rows is None:
            put("stablecoins", "UNAVAILABLE", D.PROVIDERS.get("stablecoins", {}).get("detail"), {"universe": "stablecoins > $1B", "observed": 0})
        else:
            cov = {"universe": "stablecoins with > $1B circulating (DefiLlama aggregate)", "observed": len(rows), "sampleFraction": None,
                   "exclusions": ["transaction-level mints/burns not read"]}
            sigs += X.stablecoin_supply(rows, base("stablecoins", "HEALTHY", cov))
            put("stablecoins", "HEALTHY", "DefiLlama aggregate supply", cov, now)

    if "macro" in sources:
        items = list(S.MACRO)
        pend, ob, st, note, cov, evt = daily_source("macro", items, S.macro_daily)
        for sym, d in pend:
            sigs += X.daily_anomaly("macro", sym, d["rows"], d["url"], ob, name=S.MACRO[sym])
        put("macro", st, note, cov, evt)

    if "sec" in sources:
        if "@" not in os.environ.get("GTB_SEC_USER_AGENT", ""):
            put("sec", "NOT_CONFIGURED", 'set GTB_SEC_USER_AGENT="Your Name you@example.org" (SEC fair-access rule) to include EDGAR Form 4 / 8-K', {"universe": "EDGAR latest filings", "observed": 0})
        else:
            f4, f8 = S.edgar_current("4"), S.edgar_current("8-K")
            if f4 is None and f8 is None:
                put("sec", "UNAVAILABLE", "EDGAR unreachable", {"universe": "EDGAR latest filings", "observed": 0})
            else:
                tx = {}
                clusters = {}
                for f in f4 or []:
                    if f["role"] == "Issuer":
                        clusters.setdefault(f["cik"], []).append(f)
                for fs in [v for v in clusters.values() if len(v) >= 3][:8]:
                    for f in fs[:6]:
                        tx[f["url"]] = S.edgar_form4_transactions(f["url"]) or []
                cov = {"universe": "latest 100 Form 4 + 100 8-K", "observed": len(f4 or []) + len(f8 or []), "sampleFraction": None,
                       "exclusions": ["grants/exercises/gifts excluded from Form 4 findings"]}
                st = "HEALTHY" if f4 is not None and f8 is not None else "DEGRADED"
                last = max((f["ts"] or 0 for f in (f4 or []) + (f8 or [])), default=None)
                sigs += X.edgar_events(f4, f8, base("sec", st, cov), tx)
                put("sec", st, f"{len(f4 or [])} Form 4 + {len(f8 or [])} 8-K entries", cov, last)

    if "solana" in sources:
        reps = local_reports if local_reports is not None else _local_watch_reports()
        cov = {"universe": "your local watch-token reports", "observed": len(reps), "sampleFraction": None, "exclusions": ["only tokens you watch"]}
        if reps:
            last = max(int(r.get("checkedAt") or 0) for r in reps)
            fresh = T.freshness("solana", last, now)
            ob = base("solana", fresh[0], cov)
            for s in X.solana_from_reports(reps, ob):
                s["_event"] = s["subject"]["name"]; sigs.append(s)
            put("solana", fresh[0], f"{len(reps)} local watch report(s); {fresh[1]}", cov, last)
        else:
            put("solana", "NOT_CONFIGURED", "no watch-token reports in out/; run watch-token to include on-chain alerts", cov)

    sigs = group_events(sigs)
    for s in sigs:  # calendar context: tag expected-volatility moments
        s["calendar"] = EV.events_near(s["observation"].get("eventTs") or s["when"], {s["family"]}, cal)
        if s["calendar"]:
            s["limits"].append("Coincides with a scheduled event (" + ", ".join(e["label"] for e in s["calendar"][:2]) + "); expected volatility may explain it.")
    cross = X.convergence(sigs, now) + X.same_family_repricing(sigs, now) + X.divergence(sigs, now)
    sigs += cross
    sigs = list({s["key"]: s for s in sigs}.values())
    sigs.sort(key=lambda s: (0 if s["type"] == "CONVERGENCE" else 1 if s["source"] == "cross" else 2,
                             -((s["metrics"] or {}).get("rank") or 0), -X.SEV.index(s["severity"]), -s["when"]))
    for k, v in status.items():
        if v["state"] in ("UNAVAILABLE", "STALE", "NOT_CONFIGURED"):
            limits.insert(0, {"kind": v["state"].lower(), "text": f"{k}: {v['state']} — {v.get('detail') or ''}. Its markets are unknown this run, not quiet."})
    bad = [k for k, v in status.items() if v["state"] in ("UNAVAILABLE", "STALE")]
    run_status = "failed" if status and all(v["state"] in ("UNAVAILABLE", "NOT_CONFIGURED") for v in status.values()) else \
        "partial" if any(v["state"] != "HEALTHY" for v in status.values()) else "ok"
    cal_meta = {"builtAt": cal.get("builtAt"), "types": sorted({e["type"] for e in cal.get("events", [])}), "notIncluded": cal.get("notIncluded", []),
                "upcoming": [dict(e, time=T.iso(e["ts"])) for e in cal.get("events", []) if now <= e["ts"] <= now + 7 * 86400][:12]}
    return {"kind": "signals", "version": 2, "generatedAt": now, "sources": sources, "status": run_status,
            "sourceStatus": status, "signals": sigs, "counts": _counts(sigs), "assessment": _assess(sigs, status),
            "coverage": {"limits": limits, "providers": D.provider_report(), "notIncluded": NOT_INCLUDED, "matrix": _matrix(status)},
            "calendar": cal_meta, "probes": dict(X.PROBES), "disclaimer": DISCLAIMER}


def _matrix(status):
    return [{"source": k, "family": EN.FAMILY.get(k), "status": v["state"], "lastValidAt": v.get("lastValidAt"),
             "universe": (v.get("coverage") or {}).get("universe"), "observed": (v.get("coverage") or {}).get("observed"),
             "sampleFraction": (v.get("coverage") or {}).get("sampleFraction"), "exclusions": (v.get("coverage") or {}).get("exclusions") or [],
             "detail": v.get("detail")} for k, v in status.items()]


def group_events(sigs: list[dict]) -> list[dict]:
    """One event with many sub-markets keeps its strongest signal per type; siblings become evidence."""
    groups: dict[tuple, list[dict]] = {}
    rest = []
    for s in sigs:
        ev = s.pop("_event", None)
        (groups.setdefault((s["source"], ev, s["type"]), []) if ev else rest).append(s)
    for (src, ev, _), g in groups.items():
        g.sort(key=lambda s: (-X.SEV.index(s["severity"]), -abs((s["metrics"].get("change") or 0)), -(s["metrics"].get("vol24") or 0)))
        top = g[0]
        if len(g) > 1:
            noun = "alert" if src == "solana" else "sibling market"
            top["metrics"]["relatedMarkets"] = len(g) - 1
            top["what"] = top["what"].rstrip(".") + f". {len(g) - 1} more {noun}{'s' if len(g) > 2 else ''} in “{ev}” showed the same pattern."
            top["evidence"] += [{"label": f"Sibling: {s['subject']['name'][:70]}", "url": s["subject"]["url"]} for s in g[1:4]]
            tx = set(top["metrics"].get("distinctTx") or [])
            for s in g[1:]:
                tx |= set(s["metrics"].get("distinctTx") or [])
            if tx:
                top["metrics"]["distinctTx"] = sorted(tx)
        rest.append(top)
    return rest


def _counts(sigs):
    c = {"total": len(sigs), "bySource": {}, "bySeverity": {}, "byBasis": {}}
    for s in sigs:
        c["bySource"][s["source"]] = c["bySource"].get(s["source"], 0) + 1
        c["bySeverity"][s["severity"]] = c["bySeverity"].get(s["severity"], 0) + 1
        c["byBasis"][s["basis"]] = c["byBasis"].get(s["basis"], 0) + 1
    return c


def _assess(sigs, status):
    unk = [k for k, v in status.items() if v["state"] in ("UNAVAILABLE", "STALE")]
    nc = [k for k, v in status.items() if v["state"] == "NOT_CONFIGURED"]
    observed = sum(((v.get("coverage") or {}).get("observed") or 0) for v in status.values())
    tail = (f" {', '.join(unk)} {'was' if len(unk) == 1 else 'were'} unavailable or stale, so {'its' if len(unk) == 1 else 'their'} markets are unknown, not quiet." if unk else "") + \
           (f" Not configured: {', '.join(nc)}." if nc else "")
    real = [s for s in sigs if s["basis"] != "unverified" and s["severity"] != "INFO"]
    if not real:
        ok = [k for k, v in status.items() if v["state"] in ("HEALTHY", "DEGRADED")]
        return {"severity": "INFO", "lead": {"text": f"No detector crossed its threshold in what was observed: {len(ok)} source(s) answered, covering {observed} configured markets/instruments/filings. "
                                                     "This is a statement about this sample at this scan, not that markets were quiet." + tail, "basis": "observed"},
                "nextActions": [{"label": "Check the coverage matrix", "why": "what was and wasn't observed", "ask": "Show the Grok The Block signals coverage matrix"}]}
    conv = [s for s in real if s["type"] == "CONVERGENCE"]
    top = conv[0] if conv else max(real, key=lambda s: (X.SEV.index(s["severity"]), s["when"]))
    na, seen = [], set()
    for s in [top] + real:
        if s["source"] in seen or len(na) >= 5:
            continue
        seen.add(s["source"])
        lab, why, ask = NEXT.get(s["source"], NEXT["cross"])
        na.append({"label": lab, "why": f"{why} ({s['title'][:80]})", "ask": ask.format(t=s["subject"]["name"][:60], id=s["subject"]["id"]), "signal": s["key"]})
    why = (f"Top uncalibrated anomaly-convergence ranking ({top['metrics']['rank']}): {top['metrics']['effectiveObservations']} causal families, {top['metrics']['mode']} mode."
           if top in conv else f"Highest-severity of {len(real)} signals; basis {top['basis']}.")
    return {"severity": top["severity"], "lead": {"text": top["title"] + ". " + top["what"] + tail, "basis": top["basis"], "signal": top["key"], "why": why}, "nextActions": na}


def _local_watch_reports() -> list[dict]:
    out = []
    for p in sorted((D.REPO_ROOT / "out").glob("watch-*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    return out


# ---------------- backwards-compatible adapter ----------------
_STATE_MAP = {"ok": "HEALTHY", "partial": "DEGRADED", "unknown": "UNAVAILABLE", "skipped": "NOT_CONFIGURED", "none": "NOT_CONFIGURED"}


def adapt(rep: dict) -> dict:
    """Upgrade a v1 signals report (no observation envelope, date-stamped keys) to the v2 shape in place."""
    if rep.get("kind") != "signals" or (rep.get("version") or 1) >= 2:
        return rep
    for k, v in (rep.get("sourceStatus") or {}).items():
        v["state"] = _STATE_MAP.get(v.get("state"), v.get("state", "UNAVAILABLE"))
    for s in rep.get("signals") or []:
        parts = s["key"].split(":")
        if parts and parts[-1].isdigit() and len(parts[-1]) == 8:
            s["key"] = ":".join(parts[:-1])
        s.setdefault("family", EN.FAMILY.get(s["source"], "cross"))
        s.setdefault("entities", [])
        s.setdefault("trigger", None)
        s.setdefault("calendar", [])
        s.setdefault("observation", T.obs(None, s.get("when"), s.get("when") or rep.get("generatedAt"), s.get("when"), "UNKNOWN_LEGACY", {},
                                          ["Legacy v1 report: event and availability times were not recorded; `when` is the scan time."], True))
        if s["type"] in ("SUPPLY_MINT", "SUPPLY_BURN"):
            s["type"] = "SUPPLY_CHANGE"; s["limits"] = s.get("limits", []) + ["Aggregate supply change; not a mint/burn transaction."]
        if s["type"] == "FRESH_WALLET_BETS":
            s["type"] = "NEWLY_OBSERVED_ADDRESS_ACTIVITY"
        if s["source"] == "cross":
            m = s.get("metrics") or {}
            if "convergence" in m:
                m["rank"] = m.pop("convergence"); m["rankNote"] = "uncalibrated anomaly-convergence ranking (legacy score)"
            s["title"] = s["title"].replace("Convergence ", "Ranking ")
    rep["version"] = 2
    rep["adaptedFrom"] = 1
    rep.setdefault("coverage", {}).setdefault("matrix", _matrix(rep.get("sourceStatus") or {}))
    return rep


# ---------------- watch mode ----------------

def watch(rep: dict, state_path: Path, prefs: dict | None = None) -> dict:
    st = LC.load(state_path)
    prev_ok = st.get("lastSuccessAt")
    src_state = {k: v["state"] for k, v in rep["sourceStatus"].items()}
    if rep["status"] == "failed":
        res = {"alerts": [], "telemetry": {"alerts": 0, "skippedUnavailable": sum(1 for i in st["incidents"].values() if i["state"] != "RESOLVED")}, "baseline": False}
        for inc in st["incidents"].values():
            if inc["state"] != "RESOLVED":
                inc["history"].append({"at": rep["generatedAt"], "event": "SOURCE_UNAVAILABLE", "state": inc["state"], "severity": inc["severity"], "note": "every source failed"})
    else:
        res = LC.step(st, rep["signals"], rep.get("probes") or {}, src_state, rep["generatedAt"], prefs)
    D.write_json(state_path, st)
    active = [{k: i[k] for k in ("id", "key", "state", "severity", "openedAt", "lastSeenAt", "episode", "title")} | {"history": i["history"][-8:]}
              for i in st["incidents"].values() if i["state"] != "RESOLVED"]
    resolved = sorted([i for i in st["incidents"].values() if i["state"] == "RESOLVED"], key=lambda i: -(i.get("resolvedAt") or 0))[:20]
    by_key = {i["key"]: i for i in st["incidents"].values()}
    for s in rep["signals"]:
        i = by_key.get(s["key"])
        if i:
            s["incident"] = {"id": i["id"], "state": i["state"], "episode": i["episode"], "openedAt": T.iso(i["openedAt"]), "history": i["history"][-8:]}
    rep["watch"] = {"previousSuccessfulScanAt": prev_ok, "baseline": res["baseline"], "alerts": res["alerts"], "telemetry": res["telemetry"],
                    "suppressedDuplicates": res["telemetry"].get("suppressedUnchanged", 0), "activeIncidents": active,
                    "recentlyResolved": [{k: i.get(k) for k in ("id", "title", "resolvedAt", "severity")} for i in resolved],
                    "prefs": prefs or {}, "sourceLastValid": st.get("sourceLastValid", {}),
                    "notes": ["First run sets the baseline and sends nothing." if res["baseline"] else
                              "Alerts: new episode, new distinct transaction, ≥25% magnitude rise, escalation, or a reminder for unresolved HIGH (6h, then daily).",
                              "Incidents resolve only after 2 valid observations below 75% of the entry threshold. An unavailable source never resolves anything."]}
    return rep
