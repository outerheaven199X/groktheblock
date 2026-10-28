"""Run every source, apply the detectors, and build one signals report (kind: "signals")."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .. import data as D
from . import detectors as X
from . import sources as S

DEFAULT_TICKERS = ["SPY", "QQQ", "IWM", "TLT", "HYG", "GLD", "USO", "UUP", "XLE", "NVDA", "TSLA", "AAPL", "MSFT", "COIN", "MSTR"]
DEFAULT_OPTIONS = ["SPY", "QQQ", "NVDA", "TSLA", "COIN", "TLT"]
SOURCES = ["polymarket", "kalshi", "equities", "options", "treasury", "crypto", "stablecoins", "macro", "sec", "solana"]
CRYPTO = ["BTC", "ETH", "SOL"]
NOT_INCLUDED = [
    {"source": "Binance / Bybit public APIs", "why": "geo-blocked (HTTP 451/403) from the build machine, so they could not be verified; OKX and Coinbase are used instead"},
    {"source": "Per-transaction stablecoin mint/burn", "why": "keyless Etherscan V1 is retired; supply changes come from DefiLlama aggregates instead"},
    {"source": "Stooq", "why": "now serves a JavaScript challenge, so it is not machine-readable"},
]
DISCLAIMER = ("Not financial advice. Grok The Block flags unusual activity in public market data with the evidence behind it. "
              "A signal is not a prediction, a recommendation to buy or sell, or an accusation against anyone.")

NEXT = {
    "polymarket": ("Trace the wallets behind the biggest bets", "the top Polymarket signal", "Trace the large Polymarket bets on “{t}” with Grok The Block"),
    "kalshi": ("Check the Kalshi order flow", "price shocks can come from a single thin trade", "Pull recent Kalshi trades for {id} with Grok The Block"),
    "equities": ("Look for the news or filing behind the move", "price/volume outliers usually have a public catalyst", "What news hit {id} today? Check filings and headlines"),
    "options": ("Check which strikes and expiries are hot", "volume over open interest is new positioning, direction unknown", "Show the unusual {id} option contracts from the Grok The Block signals feed"),
    "treasury": ("Compare against the rates calendar", "yield moves often lead rates-sensitive prediction markets", "Which Fed or data releases are this week, and which Polymarket/Kalshi rate markets moved?"),
    "cross": ("Open the linked signals side by side", "inferred link; confirm the timing order", "Show the timeline of the “{t}” signals across markets"),
    "crypto": ("Check spot vs perp positioning", "OI and funding shocks show leverage building or unwinding", "Show the Grok The Block crypto signals for {id}"),
    "stablecoins": ("Look at which chain the supply moved on", "large mints often precede inflows; burns redemptions", "Which chains did {id} supply change on today?"),
    "macro": ("Line it up against the rates and data calendar", "macro moves reprice everything downstream", "What moved {t} today, and which prediction markets reacted?"),
    "sec": ("Read the filing", "filings are the primary source", "Summarize the latest SEC filing for {t}"),
    "solana": ("Open the token's watch report", "on-chain alert from your watchlist", "Show the Grok The Block watch report for {t}"),
}


def _ok(name: str) -> bool | None:
    p = D.PROVIDERS.get(name)
    return None if p is None else p["ok"]


def run(sources: list[str] | None = None, tickers: list[str] | None = None, option_tickers: list[str] | None = None,
        pm_limit: int = 200, trace_markets: int = 6, local_reports: list[dict] | None = None, now: int | None = None) -> dict:
    sources = sources or SOURCES
    now = now or int(time.time())
    sigs: list[dict] = []
    status: dict[str, dict] = {}
    limits = [{"kind": "approximate", "text": "Market data is public and delayed (options ~15 min, equities and Treasuries end-of-day). Signals are snapshots at scan time."},
              {"kind": "heuristic", "text": "Thresholds (σ, ×baseline, bp) are fixed heuristics, not fitted models. Expect false positives near resolutions, earnings and data releases."},
              {"kind": "inferred", "text": "Cross-market links match topic keywords and tickers; they show co-movement, not a shared actor."}]

    if "polymarket" in sources:
        pm = S.polymarket_markets(pm_limit)
        if pm is None:
            status["polymarket"] = {"state": "unknown", "detail": D.PROVIDERS.get("polymarket", {}).get("detail")}
        else:
            moved = {}
            for m in pm:
                for f in (X.pm_odds_jump, X.pm_volume_spike):
                    s = f(m, now)
                    if s:
                        s["_event"] = m.get("event"); sigs.append(s); moved[m["id"]] = moved.get(m["id"]) or s["type"] == "ODDS_JUMP"
            # On-chain wallet tracing for the most-moved markets (rate-limited: few markets, ≤8 wallets each).
            cand = sorted([m for m in pm if m["id"] in moved], key=lambda m: -(abs(m["change1d"]) * m["vol24"]))[:trace_markets]
            traced, failed = 0, 0
            for m in cand:
                trades = S.polymarket_trades(m["id"], min_usd=5000)
                if trades is None:
                    failed += 1; continue
                traced += 1
                fs = {}
                for w in list(dict.fromkeys(t["wallet"] for t in sorted(trades, key=lambda t: -t["usd"])))[:8]:
                    fs[w] = S.polymarket_first_seen(w)
                s = X.pm_fresh_wallet_bets(m, trades, fs, now, moved=moved.get(m["id"], False))
                if s:
                    sigs.append(s)
            status["polymarket"] = {"state": "ok" if not failed else "partial", "markets": len(pm), "traced": traced,
                                    "detail": D.PROVIDERS["polymarket"]["detail"] + (f"; wallet tracing failed on {failed} market(s)" if failed else "")}
            limits.append({"kind": "sampled", "text": f"Polymarket: top {len(pm)} open markets by 24h volume, live sports/esports skipped; wallet tracing on the {len(cand)} most-moved markets, ≤8 wallets each."})

    if "kalshi" in sources:
        km = S.kalshi_markets()
        if km is None:
            status["kalshi"] = {"state": "unknown", "detail": D.PROVIDERS.get("kalshi", {}).get("detail")}
        else:
            for m in km:
                for s in X.kalshi_shock(m, now):
                    s["_event"] = m.get("event"); sigs.append(s)
            status["kalshi"] = {"state": "ok", "markets": len(km), "active": sum(1 for m in km if m["vol24"] > 0), "detail": D.PROVIDERS["kalshi"]["detail"]}
            limits.append({"kind": "sampled", "text": f"Kalshi: {len(km)} open markets from the first 2,000 events from the public API (Sports category and multivariate parlays excluded)."})

    if "equities" in sources:
        tick = tickers or DEFAULT_TICKERS
        bad = []
        for t in tick:
            e = S.equity_daily(t)
            if e is None:
                bad.append(t); continue
            sigs += X.equity_anomaly(t, e["rows"], e["url"])
        status["equities"] = {"state": "unknown" if len(bad) == len(tick) else "partial" if bad else "ok", "tickers": len(tick) - len(bad),
                              "unknown": bad, "detail": f"{len(tick) - len(bad)}/{len(tick)} tickers"}
        limits.append({"kind": "sampled", "text": f"Equities: a fixed watchlist of {len(tick)} tickers ({', '.join(tick)}), daily bars, 20-session baseline."})

    if "options" in sources:
        tick = option_tickers or DEFAULT_OPTIONS
        bad = []
        for t in tick:
            o = S.options_chain(t)
            if o is None:
                bad.append(t); continue
            s = X.options_unusual(t, o["rows"], o["url"], now)
            if s:
                sigs.append(s)
        status["options"] = {"state": "unknown" if len(bad) == len(tick) else "partial" if bad else "ok", "tickers": len(tick) - len(bad),
                             "unknown": bad, "detail": f"{len(tick) - len(bad)}/{len(tick)} chains"}
        limits.append({"kind": "sampled", "text": f"Options: delayed chains for {', '.join(tick)}; same-day volume vs prior open interest."})

    if "treasury" in sources:
        c = S.treasury_curve()
        if c is None:
            status["treasury"] = {"state": "unknown", "detail": D.PROVIDERS.get("treasury", {}).get("detail")}
        else:
            sigs += X.treasury_signals(c["rows"], c["url"])
            d, y = c["rows"][-1]
            status["treasury"] = {"state": "ok", "asOf": d, "curve": y, "detail": D.PROVIDERS["treasury"]["detail"]}

    if "crypto" in sources:
        bad = []
        for c in CRYPTO:
            d = S.crypto_daily(c)
            p = S.crypto_perps(c)
            if d is None and p is None:
                bad.append(c); continue
            if d:
                sigs += X.crypto_spot(c, d["rows"], d["url"])
            if p:
                sigs += X.crypto_perp_shock(c, p["oi"], p["funding"], p["url"])
        status["crypto"] = {"state": "unknown" if len(bad) == len(CRYPTO) else "partial" if bad else "ok", "unknown": bad,
                            "detail": f"{len(CRYPTO) - len(bad)}/{len(CRYPTO)} assets (spot volume/return, OKX perp OI and funding)"}
        limits.append({"kind": "sampled", "text": "Crypto CEX: BTC, ETH, SOL only; spot from OKX (Coinbase fallback), perps from OKX alone."})

    if "stablecoins" in sources:
        st = S.stablecoins()
        if st is None:
            status["stablecoins"] = {"state": "unknown", "detail": D.PROVIDERS.get("stablecoins", {}).get("detail")}
        else:
            sigs += X.stablecoin_flows(st, now)
            status["stablecoins"] = {"state": "ok", "assets": len(st), "detail": f"{len(st)} stablecoins over $1B (DefiLlama)"}

    if "macro" in sources:
        bad = []
        for sym, name in S.MACRO.items():
            m = S.macro_daily(sym)
            if m is None:
                bad.append(sym); continue
            sigs += X.macro_move(sym, name, m["rows"], m["url"])
        status["macro"] = {"state": "unknown" if len(bad) == len(S.MACRO) else "partial" if bad else "ok", "unknown": bad,
                           "detail": f"{len(S.MACRO) - len(bad)}/{len(S.MACRO)} series (VIX, DXY, gold, oil, EUR/USD, USD/JPY)"}

    if "sec" in sources:
        import os
        if "@" not in os.environ.get("GTB_SEC_USER_AGENT", ""):
            status["sec"] = {"state": "skipped", "detail": "set GTB_SEC_USER_AGENT=\"Your Name you@example.org\" (SEC fair-access rule) to include EDGAR Form 4 / 8-K"}
        else:
            f4, f8 = S.edgar_current("4"), S.edgar_current("8-K")
            if f4 is None and f8 is None:
                status["sec"] = {"state": "unknown", "detail": "EDGAR unreachable"}
            else:
                sigs += X.edgar_events(f4, f8, now)
                status["sec"] = {"state": "ok" if f4 is not None and f8 is not None else "partial", "detail": f"{len(f4 or [])} Form 4 + {len(f8 or [])} 8-K entries"}

    if "solana" in sources:
        reps = local_reports if local_reports is not None else _local_watch_reports()
        for s in X.solana_from_reports(reps, now):
            s["_event"] = s["subject"]["name"]; sigs.append(s)
        status["solana"] = {"state": "ok" if reps else "none", "watched": len(reps),
                            "detail": f"{len(reps)} local watch report(s)" if reps else "no watch-token reports in out/; run watch-token to include on-chain alerts"}

    sigs = group_events(sigs)
    cross = X.cross_market(sigs, now)
    X.convergence(cross, sigs)
    sigs += cross
    sigs = list({s["key"]: s for s in sigs}.values())
    # Convergence clusters lead the feed (by score); everything else by severity, newest first.
    sigs.sort(key=lambda s: (0 if s["source"] == "cross" else 1, -(s["metrics"].get("convergence") or 0), -X.SEV.index(s["severity"]), -s["when"]))
    for s in sigs:
        if any(st.get("state") in ("unknown", "partial") for k, st in status.items() if k == s["source"]):
            s["limits"] = s["limits"] + ["This source was only partly reachable in this run."]
    unknown = [k for k, v in status.items() if v["state"] == "unknown"]
    for k, v in status.items():
        if v["state"] == "skipped":
            limits.insert(0, {"kind": "skipped", "text": f"{k}: not run — {v['detail']}"})
    for k in unknown:
        limits.insert(0, {"kind": "failed", "text": f"{k}: provider unreachable — status UNKNOWN, not quiet. {status[k].get('detail') or ''}".strip()})
    return {"kind": "signals", "version": 1, "generatedAt": now, "sources": sources, "status": "failed" if status and all(v["state"] in ("unknown", "none") for v in status.values()) else "partial" if unknown or any(v["state"] == "partial" for v in status.values()) else "ok",
            "sourceStatus": status, "signals": sigs, "counts": _counts(sigs), "assessment": _assess(sigs, status),
            "coverage": {"limits": limits, "providers": D.provider_report(), "notIncluded": NOT_INCLUDED}, "disclaimer": DISCLAIMER}


def group_events(sigs: list[dict]) -> list[dict]:
    """One event (e.g. an election with 20 sub-markets) shouldn't flood the feed: keep the strongest signal per
    event and type, and note how many sibling markets did the same."""
    groups: dict[tuple, list[dict]] = {}
    rest = []
    for s in sigs:
        ev = s.get("_event")
        (groups.setdefault((s["source"], ev, s["type"]), []) if ev else rest).append(s)
    for g in groups.values():
        g.sort(key=lambda s: (-X.SEV.index(s["severity"]), -abs((s["metrics"].get("change") or 0)), -(s["metrics"].get("vol24") or 0)))
        top = g[0]
        if len(g) > 1:
            top["metrics"]["relatedMarkets"] = len(g) - 1
            noun = "alert" if top["source"] == "solana" else "sibling market"
            top["what"] = top["what"].rstrip(".") + f". {len(g) - 1} more {noun}{'s' if len(g) > 2 else ''} in “{top['_event']}” showed the same pattern."
            top["evidence"] += [{"label": f"Sibling: {s['subject']['name'][:70]}", "url": s["subject"]["url"]} for s in g[1:4]]
        rest.append(top)
    for s in rest:
        s.pop("_event", None)
    return rest


def _counts(sigs):
    c = {"total": len(sigs), "bySource": {}, "bySeverity": {}}
    for s in sigs:
        c["bySource"][s["source"]] = c["bySource"].get(s["source"], 0) + 1
        c["bySeverity"][s["severity"]] = c["bySeverity"].get(s["severity"], 0) + 1
    return c


def _assess(sigs, status):
    unknown = [k for k, v in status.items() if v["state"] == "unknown"]
    tail = f" {', '.join(unknown)} could not be reached, so {'it is' if len(unknown) == 1 else 'they are'} unknown, not quiet." if unknown else ""
    if not sigs:
        return {"severity": "INFO", "lead": {"text": "No unusual activity crossed the thresholds in the sources that answered." + tail, "basis": "observed"},
                "nextActions": [{"label": "Run the feed again later", "why": "signals are snapshots", "ask": "Run the Grok The Block signals feed again"}]}
    conv = [s for s in sigs if s["source"] == "cross" and (s["metrics"].get("convergence") or 0) >= 45]
    top = conv[0] if conv else max(sigs, key=lambda s: (X.SEV.index(s["severity"]), s["when"]))
    na, seen = [], set()
    for s in [top] + sigs:
        if s["source"] in seen or len(na) >= 5:
            continue
        seen.add(s["source"])
        lab, why, ask = NEXT.get(s["source"], NEXT["cross"])
        na.append({"label": lab, "why": f"{why} ({s['title'][:80]})", "ask": ask.format(t=s["subject"]["name"][:60], id=s["subject"]["id"]), "signal": s["key"]})
    return {"severity": top["severity"], "lead": {"text": top["title"] + ". " + top["what"] + tail, "basis": top["basis"], "signal": top["key"],
            "why": (f"Strongest anomaly convergence of {len(sigs)} signals: {top['metrics']['independentSources']} independent sources within {top['metrics']['spanHours']:g}h." if top in conv else f"Highest-severity of {len(sigs)} signals; basis {top['basis']}.")}, "nextActions": na}


def _local_watch_reports() -> list[dict]:
    out = []
    for p in sorted((D.REPO_ROOT / "out").glob("watch-*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    return out


# ---------------- watch mode: diff against the last successful run ----------------

def watch(rep: dict, state_path: Path) -> dict:
    """Same rules as watch-token: dedupe keys, never alert on a failed source, keep the last success."""
    try:
        st = json.loads(state_path.read_text())
    except (OSError, ValueError):
        st = {}
    seen: dict[str, str] = st.get("seen") or {}
    prev_ok = st.get("lastSuccessAt")
    fresh, dup = [], 0
    for s in rep["signals"]:
        prev = seen.get(s["key"])
        if prev and X.SEV.index(prev) >= X.SEV.index(s["severity"]):
            dup += 1; continue
        a = dict(s, alertType="ESCALATED" if prev else "NEW", previousSeverity=prev,
                 previousSuccessfulScanAt=prev_ok)
        fresh.append(a); seen[s["key"]] = s["severity"]
    first_run = not prev_ok
    st["seen"] = dict(list(seen.items())[-2000:])
    if rep["status"] == "failed":
        fresh, dup = [], 0  # nothing reachable: no alerts, keep the previous success as the baseline
    if rep["status"] in ("ok", "partial"):
        st["lastSuccessAt"] = rep["generatedAt"]
    hist = (st.get("alertHistory") or []) + ([] if first_run else fresh)
    st["alertHistory"] = hist[-100:]
    D.write_json(state_path, st)
    rep["watch"] = {"previousSuccessfulScanAt": prev_ok,
                    "baseline": first_run, "alerts": [] if first_run else fresh, "suppressedDuplicates": dup,
                    "recentAlerts": st["alertHistory"][-30:],
                    "notes": ["First run sets the baseline and sends nothing." if first_run else "Alerts are signals not seen in a previous run, or ones whose severity rose.",
                              "Unknown sources never generate alerts or clear old ones."]}
    return rep
