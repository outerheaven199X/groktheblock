"""Signal detectors (v2). Pure functions over normalized rows from sources.py, so they test on fixtures.

Signal fields: key (stable identity: provider + canonical entity + detector; NO calendar date — episodes are
added by the incident lifecycle), source, family, type, severity, basis (observed | heuristic | inferred |
unverified), title, what, when (= availability time), subject, entities, metrics, trigger (observed value,
baseline, threshold, window, unit), observation (event/available/ingest/validAsOf times, source status,
coverage, limitations), evidence, limits, limited (detector can't apply its full method on this data).

Thresholds are the review's proposed shadow-mode starting settings (MARKET-REVIEW §02), not validated cutoffs.
Severity describes how far past the threshold, never predictive accuracy. Nothing here is trading advice.
"""
from __future__ import annotations

import math
import statistics

from . import entities as EN
from . import timebase as T

SEV = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
BASES = ("observed", "heuristic", "inferred", "unverified")
PROBES: dict[str, float] = {}      # key -> magnitude / entry threshold, for every evaluated subject (lifecycle exit)
OBSERVED: dict[str, dict] = {}     # instrument id -> latest standardized move, for divergence


def reset():
    PROBES.clear(); OBSERVED.clear()


def sev_max(a: str, b: str) -> str:
    return a if SEV.index(a) >= SEV.index(b) else b


def cap(sev: str, top: str) -> str:
    return SEV[min(SEV.index(sev), SEV.index(top))]


def key(source: str, entity: str, typ: str) -> str:
    return f"{source}:{entity}:{typ}"


def probe(source: str, entity: str, typ: str, ratio: float | None):
    if ratio is not None and not math.isnan(ratio):
        PROBES[key(source, entity, typ)] = max(PROBES.get(key(source, entity, typ), 0.0), round(ratio, 4))


def observe(instrument: str, z: float | None, url: str, ts: int | None):
    if z is not None:
        OBSERVED[instrument] = {"z": round(z, 2), "url": url, "ts": ts}


def _sig(source, typ, severity, basis, title, what, subject, metrics, evidence, limits, observation, trigger,
         text="", instrument=None, limited=False):
    assert basis in BASES
    ents = EN.resolve(source, instrument, f"{subject.get('name', '')} {text}")
    when = observation.get("availableTs") or observation.get("ingestTs")
    return {"key": key(source, subject.get("id") or subject["name"], typ), "source": source, "family": EN.FAMILY.get(source),
            "type": typ, "severity": severity, "basis": basis, "title": title, "what": what, "when": int(when or 0),
            "subject": subject, "entities": ents, "instrument": f"{source}:{instrument}" if instrument else None,
            "metrics": metrics, "trigger": trigger, "observation": observation, "evidence": [e for e in evidence if e.get("url")],
            "limits": list(limits) + list(observation.get("limitations") or []), "limited": limited, "calendar": []}


def trig(observed, baseline, threshold, window, unit, data_age_s=None):
    return {"observed": observed, "baseline": baseline, "threshold": threshold, "window": window, "unit": unit,
            "dataAgeSeconds": data_age_s}


def pts(x):
    return f"{x * 100:.0f} pts"


def pct(x):
    return f"{x * 100:.0f}%"


def robust(series: list[float], x: float) -> tuple[float | None, float, float]:
    """(robust z, median, scaled MAD) with MAD scaled by 1.4826; z is None if the scale is zero or n < 20."""
    if len(series) < 20:
        return None, float("nan"), float("nan")
    med = statistics.median(series)
    mad = 1.4826 * statistics.median(abs(v - med) for v in series)
    return (None if mad == 0 else (x - med) / mad), med, mad


def env(obs_base: dict, event=None, available=None, valid=None, approx=False, extra_limits=()) -> dict:
    """Per-signal observation envelope from the run's per-source base (status, coverage, ingest time)."""
    ing = obs_base["ingestTs"]
    avail = min(available, ing) if available is not None else ing  # never later than we actually read it
    return T.obs(event, avail, ing,
                 valid if valid is not None else event, obs_base["status"], obs_base["coverage"],
                 list(obs_base.get("limitations") or []) + list(extra_limits), approx)


# ---------------- prediction markets ----------------

def _phase(m, now):
    end, p = m.get("endTs"), m.get("price")
    if p is not None and (p >= 0.97 or p <= 0.03):
        return "settling", True   # settlement mechanics/public outcome explain moves
    if end and end <= now:
        return "past end date (awaiting resolution)", False
    if end and end - now < 24 * 3600:
        return "final 24h before end date", False
    return "open", False


def pm_odds_jump(m: dict, ob: dict, hist: list[tuple[int, float]] | None = None) -> dict | None:
    """≥8 pts in 15m (needs CLOB history) or ≥12 pts in 1h, with ≥$25K volume; ≥3× event-specific volatility when history exists."""
    now = ob["ingestTs"]
    if m.get("category") == "sports":
        return None
    ent = m["id"]
    h1 = m.get("change1h") or 0.0
    c15, vol15 = None, None
    if hist and len(hist) >= 20:
        ps = [p for _, p in hist]
        c15 = ps[-1] - ps[-2]
        diffs = [b - a for a, b in zip(ps[:-1], ps[1:])][:-1]
        vol15 = statistics.pstdev(diffs) if len(diffs) >= 10 else None
    r1h = abs(h1) / 0.12
    r15 = abs(c15) / 0.08 if c15 is not None else 0.0
    rvol = abs(c15) / (3 * vol15) if (c15 is not None and vol15) else None
    ratio = max(r1h, r15 if (rvol is None or rvol >= 1) else 0.0)
    probe("polymarket", ent, "ODDS_REPRICING", ratio)
    if (m.get("vol24") or 0) < 25_000 or ratio < 1:
        return None
    win, ch, thr = ("15m", c15, 0.08) if r15 >= r1h and c15 is not None else ("1h", h1, 0.12)
    phase, settling = _phase(m, now)
    sev = "HIGH" if ratio >= 2 and (m.get("vol24") or 0) >= 250_000 else "MEDIUM" if ratio >= 1.4 else "LOW"
    limited = hist is None
    lim = ["Real traded notional in the same window isn't available from Gamma; 24h volume is used as a floor."]
    if limited:
        lim.append("No CLOB price history: the 15-minute and event-volatility checks were not applied; 1h change only.")
        sev = cap(sev, "MEDIUM")
    if settling:
        sev = SEV[max(SEV.index(sev) - 1, 0)]
        lim.append("Price is at a settlement extreme (≥97% or ≤3%), so a public outcome likely explains the move. Downgraded one level.")
    spread = (m["bestAsk"] - m["bestBid"]) if m.get("bestAsk") and m.get("bestBid") else None
    p = m["price"]
    return _sig("polymarket", "ODDS_REPRICING", sev, "observed",
                f"{m['outcome']} repriced {'up' if ch > 0 else 'down'} {pts(abs(ch))} in {win}: “{m['title']}”",
                f"Now {pct(p)} (≈{pct(p - ch)} {win} earlier). 24h volume ${m.get('vol24') or 0:,.0f}. Event phase: {phase}.",
                {"name": m["title"], "id": ent, "url": m["url"]},
                {"price": p, "change": ch, "window": win, "vol24": m.get("vol24"), "liquidity": m.get("liquidity"), "spread": spread,
                 "eventPhase": phase, "eventVol15m": vol15},
                [{"label": "Polymarket market", "url": m["url"]}, {"label": "Gamma API record", "url": m.get("api")}],
                lim, env(ob, now - (900 if win == "15m" else 3600), now, now, approx=True,
                         extra_limits=["Event time is the start of the measurement window; the exact moment of repricing isn't known."]),
                trig(round(abs(ch), 4), round(vol15 * 3, 4) if vol15 else None, thr, win, "probability points"),
                text=f"{m['title']} {m.get('event') or ''}", limited=limited)


def pm_volume_spike(m: dict, ob: dict) -> dict | None:
    """24h volume ≥4× its prior-6-day daily average (≥$100K). A zero baseline is 'insufficient baseline', never infinite."""
    now = ob["ingestTs"]
    vol, wk = m.get("vol24") or 0, m.get("vol1wk") or 0
    if vol < 100_000 or m.get("category") == "sports":
        return None
    age_days = (now - m["startTs"]) / 86400 if m.get("startTs") else 99
    base = (wk - vol) / 6 if wk > vol else 0.0
    subj = {"name": m["title"], "id": m["id"], "url": m["url"]}
    ev = [{"label": "Polymarket market", "url": m["url"]}, {"label": "Gamma API record", "url": m.get("api")}]
    if base <= 0 or age_days < 7:
        probe("polymarket", m["id"], "VOLUME_SPIKE", None)
        return _sig("polymarket", "VOLUME_SPIKE", "INFO", "unverified", f"Insufficient baseline: ${vol:,.0f} traded in 24h on “{m['title']}”",
                    f"No usable prior-6-day volume (market age {age_days:.0f} days), so no ratio is computed.", subj,
                    {"vol24": vol, "baselinePerDay": base, "ratio": None, "ageDays": round(age_days, 1)}, ev,
                    ["Insufficient historical baseline. This is not a maximal anomaly."], env(ob, now - 86400, now, now, True),
                    trig(vol, None, "4× baseline", "24h vs prior 6d", "USD"), text=f"{m['title']} {m.get('event') or ''}")
    ratio = vol / base
    probe("polymarket", m["id"], "VOLUME_SPIKE", ratio / 4)
    if ratio < 4:
        return None
    sev = "HIGH" if ratio >= 10 and vol >= 1_000_000 else "MEDIUM" if ratio >= 6 else "LOW"
    phase, settling = _phase(m, now)
    lim = ["Baseline is the 7-day total minus the last 24h, averaged over 6 days."]
    if settling:
        sev = SEV[max(SEV.index(sev) - 1, 0)]; lim.append("Settlement-extreme price: downgraded one level.")
    return _sig("polymarket", "VOLUME_SPIKE", sev, "heuristic", f"24h volume {ratio:.0f}× its prior-6-day average: “{m['title']}”",
                f"${vol:,.0f} in 24h vs ~${base:,.0f}/day before. Event phase: {phase}.", subj,
                {"vol24": vol, "baselinePerDay": round(base, 2), "ratio": round(ratio, 1), "price": m["price"], "eventPhase": phase}, ev,
                lim, env(ob, now - 86400, now, now, True), trig(vol, round(base, 2), round(4 * base, 2), "24h vs prior 6d", "USD"),
                text=f"{m['title']} {m.get('event') or ''}")


def pm_fresh_activity(m: dict, trades: list[dict], first_seen: dict[str, int | None], ob: dict, moved: bool = False,
                      min_usd: float = 25_000, lookback_days: float = 30) -> dict | None:
    """Single-address bets ≥$25K from addresses newly observed on Polymarket within available history (≤30 days)."""
    now = ob["ingestTs"]
    hits, unknown = [], 0
    for t in trades:
        if t["usd"] < min_usd:
            continue
        fs = first_seen.get(t["wallet"])
        if fs is None:
            unknown += 1; continue
        if t["ts"] - fs <= lookback_days * 86400:
            hits.append(dict(t, ageDays=round((t["ts"] - fs) / 86400, 1)))
    top = max((h["usd"] for h in hits), default=0)
    probe("polymarket", m["id"], "NEWLY_OBSERVED_ADDRESS_ACTIVITY", top / min_usd if hits else 0.0)
    if not hits:
        return None
    total = sum(h["usd"] for h in hits)
    addrs = {h["wallet"] for h in hits}
    sev = "HIGH" if top >= 100_000 and moved else "MEDIUM" if top >= 50_000 or moved else "LOW"
    hits.sort(key=lambda h: -h["usd"])
    ev = [{"label": f"Polygon tx · ${h['usd']:,.0f} {h['side']} {h['outcome']} @ {h['price']:.2f} · address first seen {h['ageDays']}d before",
           "url": f"https://polygonscan.com/tx/{h['tx']}"} for h in hits[:6] if h.get("tx")]
    first_tx = min(h["ts"] for h in hits)
    return _sig("polymarket", "NEWLY_OBSERVED_ADDRESS_ACTIVITY", sev, "inferred" if moved else "heuristic",
                f"{len(addrs)} address{'es' if len(addrs) > 1 else ''} newly observed on Polymarket placed ${total:,.0f}: “{m['title']}”",
                f"Each placed ≥${min_usd:,.0f} within {lookback_days:g} days of its first Polymarket activity in available history"
                + (", while the market was repricing." if moved else ".") + " Causality and beneficial ownership unverified.",
                {"name": m["title"], "id": m["id"], "url": m["url"]},
                {"addresses": len(addrs), "usd": round(total, 2), "trades": len(hits), "unknownHistory": unknown,
                 "largest": [{"address": h["wallet"][:6] + "…" + h["wallet"][-4:], "usd": h["usd"], "firstSeenDaysBefore": h["ageDays"], "ts": h["ts"]} for h in hits[:5]],
                 "distinctTx": sorted({h["tx"] for h in hits if h.get("tx")})},
                ev + [{"label": "Polymarket market", "url": m["url"]}],
                ["Only the most recent large trades are sampled (data-api, ≤200 per market).",
                 "“Newly observed” means first Polymarket activity within available history, not a new on-chain wallet, a new trader or an insider.",
                 "Related-address grouping (≥$100K validated groups) is not implemented."] + ([f"{unknown} large trade(s) had no retrievable history."] if unknown else []),
                env(ob, first_tx, max(h["ts"] for h in hits), max(h["ts"] for h in hits)),
                trig(top, None, min_usd, f"{lookback_days:g}d first-seen lookback", "USD per address"),
                text=f"{m['title']} {m.get('event') or ''}")


def kalshi_shock(m: dict, ob: dict) -> list[dict]:
    now = ob["ingestTs"]
    out = []
    if m.get("category") == "Sports":
        return out
    subj = {"name": m["title"], "id": m["id"], "url": m["url"]}
    ev = [{"label": "Kalshi market", "url": m["url"]}, {"label": "Kalshi API record", "url": m.get("api")}]
    mid = (m["yesBid"] + m["yesAsk"]) / 2 if m.get("yesBid") and m.get("yesAsk") else None
    pmid = (m["prevBid"] + m["prevAsk"]) / 2 if m.get("prevBid") and m.get("prevAsk") else None
    p, prev, lim = (mid, pmid, []) if mid is not None and pmid is not None else (m.get("price"), m.get("prev"),
                                                                                ["Using last trade (no executable midpoint), which a single thin trade can move."])
    v24 = m.get("vol24") or 0
    if p is not None and prev and 0.02 < prev < 0.98:
        ch = p - prev
        probe("kalshi", m["id"], "ODDS_REPRICING", abs(ch) / 0.12)
        if v24 >= 2000 and abs(ch) >= 0.12:
            sev = "HIGH" if abs(ch) >= 0.25 and v24 >= 20_000 else "MEDIUM" if abs(ch) >= 0.18 else "LOW"
            out.append(_sig("kalshi", "ODDS_REPRICING", cap(sev, "MEDIUM") if lim else sev, "observed",
                            f"Yes {'midpoint' if not lim else 'price'} {'up' if ch > 0 else 'down'} {pts(abs(ch))} vs previous day: “{m['title']}”",
                            f"{pct(p)} vs {pct(prev)} on {v24:,.0f} contracts.", subj, {"price": p, "prev": prev, "change": round(ch, 4), "vol24": v24}, ev,
                            lim + ["Previous-day comparison only (no intraday history); 15m/1h windows not available."],
                            env(ob, now - 86400, now, now, True), trig(round(abs(ch), 4), prev, 0.12, "1d", "probability points"),
                            text=f"{m['title']} {m.get('event') or ''}", limited=True))
    if m.get("openTs") and v24 >= 10_000:
        age = max((now - m["openTs"]) / 86400, 0)
        base = max(m.get("volume", 0) - v24, 0) / max(age - 1, 1)
        if age >= 7 and base > 0:
            ratio = v24 / base
            probe("kalshi", m["id"], "VOLUME_SPIKE", ratio / 5)
            if ratio >= 5:
                out.append(_sig("kalshi", "VOLUME_SPIKE", "LOW", "heuristic", f"Volume {ratio:.0f}× its lifetime daily average: “{m['title']}”",
                                f"{v24:,.0f} contracts in 24h vs ~{base:,.0f}/day since it opened {age:.0f} days ago.", subj,
                                {"vol24": v24, "baselinePerDay": round(base, 1), "ratio": round(ratio, 1)}, ev,
                                ["Context only: lifetime-average volume spikes are confounded by event proximity (review §03). Capped at LOW."],
                                env(ob, now - 86400, now, now, True), trig(v24, round(base, 1), round(5 * base, 1), "24h vs lifetime/day", "contracts"),
                                text=f"{m['title']} {m.get('event') or ''}"))
        elif age < 7 or base <= 0:
            out.append(_sig("kalshi", "VOLUME_SPIKE", "INFO", "unverified", f"Insufficient baseline: {v24:,.0f} contracts in 24h on “{m['title']}”",
                            "Market too new or no prior volume, so no ratio is computed.", subj, {"vol24": v24, "ratio": None, "ageDays": round(age, 1)}, ev,
                            ["Insufficient historical baseline. This is not a maximal anomaly."], env(ob, now - 86400, now, now, True),
                            trig(v24, None, "5× baseline", "24h vs lifetime/day", "contracts"), text=m["title"]))
    return out


# ---------------- equities / options / macro / crypto spot (daily bars) ----------------

def _close_ts(t: int) -> int:
    d = T.datetime.fromtimestamp(t, T.NY).date()
    return T.ny_ts(d, 16)


def daily_anomaly(source: str, sym: str, rows: list[tuple[int, float, float]], url: str, ob: dict, name: str | None = None,
                  vol_window: int = 60, ret_window: int = 20, close_hm=(16, 0)) -> list[dict]:
    """Volume: robust z (median + 1.4826·MAD of 60 sessions of log volume) ≥3 AND ≥1.8× median volume.
    Return: daily log return / prior 20-day realized vol, |z| ≥3. Intraday variants are not supported (daily bars only)."""
    name = name or sym
    out, subj = [], {"name": name, "id": sym, "url": url}
    if len(rows) < ret_window + 2:
        return []
    t, c, v = rows[-1]
    prev_c = rows[-2][1]
    ev_ts = _close_ts(t) if source in ("equities", "macro") else t + 86400
    avail = ev_ts + (15 * 60 if source in ("equities", "macro") else 60)
    o = env(ob, ev_ts, min(avail, ob["ingestTs"]), ev_ts, approx=True,
            extra_limits=["Daily bars only; the time of day the move happened is unknown. Intraday detectors are not available on this data."])
    evid = [{"label": f"{name} quote & history", "url": url}]
    rets = [math.log(b[1] / a[1]) for a, b in zip(rows[-ret_window - 2:-2], rows[-ret_window - 1:-1]) if a[1] and b[1]]
    r = math.log(c / prev_c) if prev_c and c else 0.0
    rv = statistics.pstdev(rets) if len(rets) >= 10 else 0.0
    rz = r / rv if rv else None
    observe(f"{source}:{sym}", rz, url, avail)
    probe(source, sym, "RETURN_VS_REALIZED_VOL", abs(rz) / 3 if rz is not None else None)
    if rz is not None and abs(rz) >= 3:
        sev = "HIGH" if abs(rz) >= 5 else "MEDIUM" if abs(rz) >= 4 else "LOW"
        out.append(_sig(source, "RETURN_VS_REALIZED_VOL", sev, "observed", f"{name} {'rose' if r > 0 else 'fell'} {abs(math.expm1(r)) * 100:.1f}%, {abs(rz):.1f}× its 20-day realized volatility",
                        f"Close {c:,.4g} vs {prev_c:,.4g}. Daily realized vol ≈{rv * 100:.2f}%.", subj,
                        {"close": c, "return": round(r, 5), "z": round(rz, 2), "realizedVol20": round(rv, 5)}, evid, [], o,
                        trig(round(abs(r), 5), round(rv, 5), round(3 * rv, 5), "1 session vs 20-session realized vol", "log return"),
                        text=name, instrument=sym))
    vols = [x[2] for x in rows[-vol_window - 1:-1] if x[2] and x[2] > 0]
    if v and v > 0 and len(vols) >= 40:
        lv = [math.log(x) for x in vols]
        z, med, mad = robust(lv, math.log(v))
        rel = v / math.exp(med)
        probe(source, sym, "VOLUME_ROBUST_Z", min(z / 3, rel / 1.8) if z is not None else None)
        if z is not None and z >= 3 and rel >= 1.8:
            sev = "HIGH" if z >= 6 else "MEDIUM" if z >= 4 else "LOW"
            out.append(_sig(source, "VOLUME_ROBUST_Z", sev, "observed", f"{name} volume {rel:.1f}× its {len(vols)}-session median (robust z {z:.1f})",
                            f"{v:,.0f} vs median {math.exp(med):,.0f}. Volume exceeds its comparable historical baseline.", subj,
                            {"volume": v, "medianVolume": round(math.exp(med)), "robustZ": round(z, 2), "relative": round(rel, 2), "sessions": len(vols)}, evid,
                            ["Raw daily volume outliers often lag public news (review §03)."], o,
                            trig(v, round(math.exp(med)), round(max(math.exp(med + 3 * mad), 1.8 * math.exp(med))), f"1 session vs {len(vols)}-session median/MAD", "volume"),
                            text=name, instrument=sym))
    elif v:
        out.append(_sig(source, "VOLUME_ROBUST_Z", "INFO", "unverified", f"{name}: insufficient volume history ({len(vols)} sessions)",
                        "Fewer than 40 sessions with volume, so no robust baseline.", subj, {"sessions": len(vols)}, evid,
                        ["Insufficient historical baseline."], o, trig(v, None, "robust z ≥3", "60 sessions", "volume"), text=name, instrument=sym))
    return out


def options_activity(sym: str, ch: dict, url: str, ob: dict) -> list[dict]:
    """Two detectors. Every contract must have a parsed expiry (rejects are counted).
    UNUSUAL_OPTIONS_VOLUME (expiry ≥2 sessions out): volume ≥500, est. premium ≥$250K, volume/OI ≥3 as context.
    SHORT_DATED_OPTIONS (0DTE/1DTE, separate and conservative): volume ≥5,000, premium ≥$1M, volume/OI ≥5, capped LOW.
    No aggressor or direction is asserted: trade-level prints and contemporaneous quotes aren't available."""
    now = ob["ingestTs"]
    rows = ch["rows"]
    snap = ch.get("snapshotTs")
    t0 = T.datetime.fromtimestamp(snap or now, T.NY).date()
    nxt = t0 + T.timedelta(days=1)
    while not T.is_session(nxt):
        nxt += T.timedelta(days=1)
    short_cut = nxt.strftime("%Y%m%d")
    rejected = ch.get("rejected", 0) + sum(1 for r in rows if not r.get("expiry"))
    good = [r for r in rows if r.get("expiry")]
    prem = lambda r: (r["volume"] * (r.get("price") or 0) * 100)  # noqa: E731
    o = env(ob, snap, (snap + 15 * 60) if snap else None, snap, approx=snap is None,
            extra_limits=["Delayed snapshot (~15 min); retrospective anomaly report, not an immediate flow alert."])
    if rejected:
        o["limitations"].append(f"{rejected} contract(s) rejected: expiry could not be parsed.")
    evid = [{"label": f"{sym} delayed option chain", "url": url}]
    out = []
    for typ, sel, vmin, pmin, ratio_min, top in (("UNUSUAL_OPTIONS_VOLUME", lambda r: r["expiry"] > short_cut, 500, 250_000, 3, "MEDIUM"),
                                                 ("SHORT_DATED_OPTIONS", lambda r: r["expiry"] <= short_cut, 5000, 1_000_000, 5, "LOW")):
        pool = [r for r in good if sel(r)]
        hot = [r for r in pool if r["volume"] >= vmin and prem(r) >= pmin and r["volume"] >= ratio_min * max(r["oi"], 1)]
        best = max((min(r["volume"] / vmin, prem(r) / pmin, r["volume"] / (ratio_min * max(r["oi"], 1))) for r in pool if r.get("price")), default=0)
        probe("options", sym, typ, best)
        if not hot:
            continue
        hot.sort(key=lambda r: -prem(r))
        p_tot = sum(prem(r) for r in hot)
        call_share = sum(prem(r) for r in hot if r["type"] == "call") / p_tot if p_tot else 0
        sev = cap("HIGH" if p_tot >= 25e6 and len(hot) >= 5 else "MEDIUM" if p_tot >= 5e6 else "LOW", top)
        lbl = "short-dated (0DTE/1DTE) " if typ == "SHORT_DATED_OPTIONS" else ""
        out.append(_sig("options", typ, sev, "heuristic",
                        f"{sym}: {len(hot)} {lbl}contract{'s' if len(hot) > 1 else ''} with unusual observed volume vs open interest (≈${p_tot / 1e6:,.1f}M premium)",
                        f"Call share of flagged premium {call_share * 100:.0f}%. Aggressor and direction unknown; spreads, closes, rolls and hedges look the same.",
                        {"name": sym, "id": sym, "url": url},
                        {"contracts": len(hot), "estPremium": round(p_tot), "callShare": round(call_share, 3), "rejectedContracts": rejected,
                         "top": [{"contract": r["contract"], "expiry": r["expiry"], "strike": r.get("strike"), "volume": r["volume"], "oi": r["oi"],
                                  "estPremium": round(prem(r)), "underlying": ch.get("underlying")} for r in hot[:5]]},
                        evid, ["Open interest is a prior-session snapshot; volume above it doesn't prove new positioning.",
                               "Historical matched-contract relative volume (≥3× 20–60 sessions) is not available: limited detector."], o,
                        trig(round(p_tot), None, pmin, "session to snapshot", "est. premium USD (vol × mid × 100)",
                             (now - snap) if snap else None), text=sym, instrument=sym, limited=True))
    return out


# ---------------- Treasuries ----------------

def treasury_signals(rows: list[tuple[str, dict]], url: str, ob: dict) -> list[dict]:
    """2Y/10Y/30Y: daily |Δ| ≥ max(8 bp, 2.5× robust scale of 60 sessions of bp changes).
    2s10s: shift ≥10 bp in a day or ≥15 bp over 5 sessions, classified bull/bear steepening/flattening.
    Inversion: zero crossing that persists (≥3 bp beyond zero or two consecutive observations)."""
    if len(rows) < 22:
        return []
    out = []
    d1, y1 = rows[-1]
    d0, y0 = rows[-2]
    obs_day = T.date.fromisoformat(d1)
    ev_ts = T.ny_ts(obs_day, 15, 30)
    avail = min(T.ny_ts(obs_day, 18, 0), ob["ingestTs"])
    o = env(ob, ev_ts, avail, ev_ts, approx=True,
            extra_limits=["Daily indicative par yields; availability time is an estimate (published the same business day, late afternoon ET)."])
    evid = [{"label": "US Treasury daily par yield curve", "url": url}]
    subj = lambda n, i: {"name": n, "id": i, "url": url}  # noqa: E731
    for k in ("2Y", "10Y", "30Y"):
        ser = [y.get(k) for _, y in rows[-62:]]
        if any(v is None for v in ser[-2:]):
            continue
        ch = [(b - a) * 100 for a, b in zip(ser[:-1], ser[1:]) if a is not None and b is not None]
        bp = ch[-1]
        hist = ch[:-1][-60:]
        _, med, scale = robust(hist, bp) if len(hist) >= 20 else (None, 0, 0)
        scale = scale if scale == scale else 0
        thr = max(8.0, 2.5 * scale)
        observe(f"treasury:{k}", bp / (scale or 8), url, avail)
        probe("treasury", k, "YIELD_MOVE", abs(bp) / thr)
        if abs(bp) >= thr:
            out.append(_sig("treasury", "YIELD_MOVE", "MEDIUM" if abs(bp) >= 1.5 * thr else "LOW", "observed",
                            f"{k} Treasury yield {bp:+.0f} bp on {d1} ({abs(bp) / (scale or 1):.1f}× its robust daily scale)",
                            f"{k} {y1[k]:.2f}% vs {y0.get(k, float('nan')):.2f}% on {d0}. Context for rates-sensitive markets.", subj(f"{k} yield", k),
                            {"yield": y1[k], "bp1d": round(bp, 1), "robustScaleBp": round(scale, 2), "thresholdBp": round(thr, 2)}, evid,
                            ["Daily publication seldom qualifies as early warning (review §03)."], o,
                            trig(round(bp, 1), round(scale, 2), round(thr, 2), "1 session vs 60-session robust scale", "bp"),
                            text=f"treasury {k} yield", instrument=k))
    if all(k in y for _, y in rows[-6:] for k in ("2Y", "10Y")):
        sp = [(y["10Y"] - y["2Y"]) * 100 for _, y in rows[-6:]]
        s1, s0, s5 = sp[-1], sp[-2], sp[0]
        d2, d10 = (y1["2Y"] - y0["2Y"]) * 100, (y1["10Y"] - y0["10Y"]) * 100
        steep = s1 > s0
        regime = ("bull " if (d2 + d10) / 2 < 0 else "bear ") + ("steepening" if steep else "flattening")
        shift1, shift5 = s1 - s0, s1 - s5
        probe("treasury", "2s10s", "CURVE_SHIFT", max(abs(shift1) / 10, abs(shift5) / 15))
        if abs(shift1) >= 10 or abs(shift5) >= 15:
            out.append(_sig("treasury", "CURVE_SHIFT", "MEDIUM" if abs(shift1) >= 15 or abs(shift5) >= 25 else "LOW", "observed",
                            f"2s10s {regime}: {shift1:+.0f} bp in a day, {shift5:+.0f} bp over 5 sessions (now {s1:+.0f} bp)",
                            f"2Y {d2:+.0f} bp, 10Y {d10:+.0f} bp on {d1}.", subj("2s10s spread", "2s10s"),
                            {"spreadBp": round(s1, 1), "shift1dBp": round(shift1, 1), "shift5dBp": round(shift5, 1), "regime": regime,
                             "d2Bp": round(d2, 1), "d10Bp": round(d10, 1)}, evid, ["A curve regime is context, not an anomaly by itself."], o,
                            trig(round(shift1, 1), None, "10 bp/1d or 15 bp/5d", "1 and 5 sessions", "bp"), text="treasury yield 2s10s", instrument="2s10s"))
        crossed_recent = any((a < 0) != (b < 0) for a, b in zip(sp[-3:-1], sp[-2:]))
        persist = (abs(s1) >= 3 and (s1 < 0) != (s5 < 0)) or (len(sp) >= 3 and (sp[-1] < 0) == (sp[-2] < 0) != (sp[-3] < 0))
        if crossed_recent and persist:
            out.append(_sig("treasury", "CURVE_INVERSION" if s1 < 0 else "CURVE_UNINVERSION", "MEDIUM", "observed",
                            f"2s10s {'inverted' if s1 < 0 else 'un-inverted'} and held ({s1:+.0f} bp, {regime})",
                            "Zero crossing confirmed by ≥3 bp beyond zero or two consecutive observations.", subj("2s10s spread", "2s10s"),
                            {"spreadBp": round(s1, 1), "series": [round(x, 1) for x in sp], "regime": regime}, evid,
                            ["A regime/state transition, not automatically a high-conviction anomaly (review §02)."], o,
                            trig(round(s1, 1), 0, "±3 bp or 2 observations", "last 3 sessions", "bp"), text="treasury yield 2s10s", instrument="2s10s"))
    return out


# ---------------- crypto perps / stablecoins ----------------

def crypto_perp_shock(ccy: str, oi: list[tuple], funding: list[tuple], url: str, ob: dict, interval_h: float | None = None) -> list[dict]:
    """OI (daily fallback): ≥15% over 24h AND z ≥3 vs prior daily changes; reported in contracts and USD.
    Funding normalized to 8h from the actual settlement interval: |f8| ≥0.05% and >95th pct of ~30d (severe ≥0.10% and >99th)."""
    out, subj = [], {"name": f"{ccy} perpetual", "id": f"{ccy}-PERP", "url": url}
    evid = [{"label": f"OKX {ccy}-USDT perpetual", "url": url}]
    text = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}.get(ccy, ccy)
    if len(oi) >= 12:
        rows = [(r[0], r[1], r[2] if len(r) > 2 else None) for r in oi]
        t1, c1, u1 = rows[-1]
        _, c0, u0 = rows[-2]
        chg = [(b[1] - a[1]) / a[1] for a, b in zip(rows[:-1], rows[1:]) if a[1]]
        ch = chg[-1]
        z, _, _ = robust(chg[:-1][-30:], ch) if len(chg) > 21 else (None, 0, 0)
        usd_ch = (u1 - u0) / u0 if u0 else None
        probe("crypto", f"{ccy}-PERP", "OI_SHOCK", min(abs(ch) / 0.15, abs(z) / 3) if z is not None else None)
        if abs(ch) >= 0.15 and z is not None and abs(z) >= 3:
            o = env(ob, t1 + 86400, min(t1 + 86400 + 300, ob["ingestTs"]), t1 + 86400, True, ["OKX only; other venues' open interest can differ."])
            out.append(_sig("crypto", "OI_SHOCK", "HIGH" if abs(ch) >= 0.30 else "MEDIUM", "observed",
                            f"Unusual observed open interest: {ccy} perp OI {ch * 100:+.0f}% in contracts over 24h (robust z {z:.1f})",
                            f"Contracts {c0:,.0f} → {c1:,.0f}; USD value {usd_ch * 100:+.0f}%." if usd_ch is not None else f"Contracts {c0:,.0f} → {c1:,.0f}.", subj,
                            {"oiContracts": c1, "oiUsd": u1, "change1dContracts": round(ch, 4), "change1dUsd": None if usd_ch is None else round(usd_ch, 4), "z": round(z, 2)},
                            evid, ["Daily fallback (intraday 1h/4h OI history not used). USD OI can rise with price without contract growth; both are shown."], o,
                            trig(round(ch, 4), None, 0.15, "24h, z vs prior 30 daily changes", "fraction (contracts)"), text=text, instrument=ccy))
    if len(funding) >= 30:
        ih = interval_h or 8.0
        f8 = [(t, r * 8 / ih) for t, r in funding]
        t, r = f8[-1]
        hist = sorted(abs(x) for _, x in f8[:-1][-90:])
        p95 = hist[int(0.95 * (len(hist) - 1))]; p99 = hist[int(0.99 * (len(hist) - 1))]
        probe("crypto", f"{ccy}-PERP", "FUNDING_EXTREME", min(abs(r) / 0.0005, abs(r) / p95 if p95 else 99))
        if abs(r) >= 0.0005 and abs(r) > p95:
            severe = abs(r) >= 0.001 and abs(r) > p99
            o = env(ob, t, min(t + 60, ob["ingestTs"]), t, False, [])
            out.append(_sig("crypto", "FUNDING_EXTREME", "HIGH" if severe else "MEDIUM", "observed",
                            f"{ccy} perp funding {r * 100:+.3f}% per 8h-equivalent ({'longs' if r > 0 else 'shorts'} paying), above the 30-day {'99th' if severe else '95th'} percentile",
                            f"Settlement interval {ih:g}h; realized rate normalized to 8h.", subj,
                            {"funding8h": r, "intervalH": ih, "p95": p95, "p99": p99}, evid,
                            ["Funding is positioning context, not a directional forecast. Basis and predicted-next funding not yet combined."], o,
                            trig(round(abs(r), 6), round(p95, 6), max(0.0005, p95), "latest settlement vs ~30d", "funding per 8h"), text=text, instrument=ccy))
    return out


def stablecoin_supply(rows: list[dict], ob: dict) -> list[dict]:
    """SUPPLY_CHANGE (aggregate circulating supply, DefiLlama): |Δ1d| ≥$250M AND ≥0.5%; HIGH ≥$1B.
    Not a mint/burn: MINT/BURN/REDEMPTION require transaction or issuer evidence, which this source doesn't provide."""
    now = ob["ingestTs"]
    out = []
    for a in rows:
        if not a.get("d1"):
            continue
        d1 = a["now"] - a["d1"]; w1 = a["now"] - (a.get("w1") or a["now"])
        p1 = d1 / a["d1"]
        probe("stablecoins", a["symbol"], "SUPPLY_CHANGE", min(abs(d1) / 250e6, abs(p1) / 0.005))
        if abs(d1) >= 250e6 and abs(p1) >= 0.005:
            chains = ", ".join(f"{c} {v / 1e6:+,.0f}M" for c, v in (a.get("chains") or [])[:3])
            out.append(_sig("stablecoins", "SUPPLY_CHANGE", "HIGH" if abs(d1) >= 1e9 else "MEDIUM", "observed",
                            f"{a['symbol']} aggregate circulating supply {d1 / 1e6:+,.0f}M ({p1 * 100:+.2f}%) in a day",
                            f"Now ${a['now'] / 1e9:,.2f}B; 7-day {w1 / 1e6:+,.0f}M." + (f" Largest chain changes: {chains}." if chains else ""),
                            {"name": a["symbol"], "id": a["symbol"], "url": a["url"]},
                            {"change1d": round(d1), "pct1d": round(p1, 5), "change7d": round(w1), "chains": a.get("chains")},
                            [{"label": f"{a['name']} supply by chain (DefiLlama)", "url": a["url"]}],
                            ["Aggregate supply changes can reflect issuance, redemptions, cross-chain bridging, peg/price effects, tracking changes or data revisions. Not evidence of a mint or burn transaction."],
                            env(ob, now - 86400, now, now, True), trig(round(abs(d1)), None, 250e6, "1d", "USD"),
                            text=a["name"], instrument=a["symbol"]))
    return out


# ---------------- SEC EDGAR ----------------
MATERIAL_8K = {"1.01": "material agreement", "1.02": "agreement terminated", "1.03": "bankruptcy", "2.01": "acquisition or disposal",
               "2.04": "triggering event on debt", "2.05": "exit/restructuring costs", "2.06": "material impairment", "3.01": "delisting notice",
               "4.02": "prior financials can't be relied on", "5.01": "change in control", "5.02": "officer/director change"}
SEVERE_8K = {"1.03", "2.04", "3.01", "4.02", "5.01"}


def edgar_events(form4: list[dict] | None, eightk: list[dict] | None, ob: dict, tx: dict[str, list[dict]] | None = None) -> list[dict]:
    """Form 4: clusters (≥3 filings for one issuer) are only reported when transactions are parsed; open-market
    purchases (code P) lead, sales (S) are context, grants/exercises (A, M, F, G) are excluded.
    8-K: material item codes, observed."""
    now = ob["ingestTs"]
    out, by = [], {}
    for f in form4 or []:
        if f["role"] == "Issuer":
            by.setdefault(f["cik"], []).append(f)
    for cik, fs in by.items():
        if len(fs) < 3:
            continue
        parsed = [t for f in fs for t in ((tx or {}).get(f["url"]) or [])]
        n = fs[0]["name"]
        subj = {"name": n, "id": cik, "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4"}
        ev = [{"label": f"Form 4 · {n}", "url": f["url"]} for f in fs[:4]]
        o = env(ob, min(f["ts"] or now for f in fs), max(f["ts"] or now for f in fs), max(f["ts"] or now for f in fs))
        if not parsed:
            out.append(_sig("sec", "INSIDER_FILING_CLUSTER", "INFO", "unverified", f"{len(fs)} Form 4 filings for {n} (transactions not parsed)",
                            "Counts alone are mostly noise: routine grants and planned sales dominate.", subj, {"filings": len(fs)}, ev,
                            ["Transactions could not be parsed; no finding is made."], o, trig(len(fs), None, 3, "latest EDGAR feed", "filings"), text=n))
            continue
        buys = [t for t in parsed if t["code"] == "P"]
        sells = [t for t in parsed if t["code"] == "S"]
        usd = lambda ts: sum((t["shares"] or 0) * (t["price"] or 0) for t in ts)  # noqa: E731
        if buys:
            out.append(_sig("sec", "INSIDER_OPEN_MARKET_PURCHASES", "MEDIUM" if usd(buys) >= 1e6 else "LOW", "observed",
                            f"{n}: {len(buys)} open-market insider purchase(s) across {len(fs)} Form 4 filings (≈${usd(buys):,.0f})",
                            "Transaction code P parsed from the filings. Grants, exercises and gifts excluded.", subj,
                            {"filings": len(fs), "purchases": len(buys), "purchaseUsd": round(usd(buys)), "sales": len(sells)}, ev,
                            ["Filings arrive up to two business days after the trade."], o, trig(len(buys), None, 1, "latest EDGAR feed", "purchases"), text=n))
        elif sells:
            out.append(_sig("sec", "INSIDER_SALES_CLUSTER", "LOW", "observed", f"{n}: {len(sells)} insider sale(s) across {len(fs)} Form 4 filings (≈${usd(sells):,.0f})",
                            "Code S parsed. Sales are frequently scheduled (10b5-1); context only.", subj,
                            {"filings": len(fs), "sales": len(sells), "salesUsd": round(usd(sells))}, ev,
                            ["10b5-1 plan status isn't parsed."], o, trig(len(sells), None, 1, "latest EDGAR feed", "sales"), text=n))
    seen = set()
    for f in eightk or []:
        items = [i for i in f["items"] if i in MATERIAL_8K]
        if not items or f["cik"] in seen:
            continue
        seen.add(f["cik"])
        severe = [i for i in items if i in SEVERE_8K]
        out.append(_sig("sec", "8K_EVENT", "HIGH" if severe else "LOW" if items == ["5.02"] else "MEDIUM", "observed",
                        f"{f['name']} 8-K: " + ", ".join(MATERIAL_8K[i] for i in items), "Items " + ", ".join(items) + " filed with the SEC.",
                        {"name": f["name"], "id": f["cik"], "url": f["url"]}, {"items": items}, [{"label": "8-K filing index", "url": f["url"]}],
                        ["Item codes only, not the full text. Latest ~100 filings."], env(ob, f["ts"], f["ts"], f["ts"]),
                        trig(len(items), None, 1, "latest EDGAR feed", "material items"), text=f["name"]))
    return out


def solana_from_reports(reports: list[dict], ob: dict, window_h: float = 72) -> list[dict]:
    now = ob["ingestTs"]
    out = []
    for r in reports:
        if r.get("kind") != "watch":
            continue
        tok = r.get("token") or {}
        for a in (r.get("recentAlerts") or []):
            ts = int(a.get("timestamp") or 0)
            if now - ts > window_h * 3600:
                continue
            ev = [e if isinstance(e, dict) else {"label": "evidence", "url": e} for e in (a.get("evidence") or ([{"label": "transaction", "url": a["url"]}] if a.get("url") else []))]
            name = f"${tok.get('symbol')}"
            w = str(a.get("wallet") or "")
            what = a.get("detail") or (f"{a.get('amountSol')} SOL" + (f" by wallet {w[:4]}…{w[-4:]}" if w else "") if a.get("amountSol") is not None else "")
            s = _sig("solana", a.get("type", "ALERT"), a.get("severity") or "MEDIUM", "observed", f"{name}: {str(a.get('type', 'alert')).replace('_', ' ').lower()}",
                     what, {"name": name, "id": tok.get("mint") or name, "url": f"https://solscan.io/token/{tok.get('mint')}"},
                     {k: a[k] for k in ("before", "after", "amountSol") if k in a}, ev, ["From your local watch-token runs; only watched tokens are covered."],
                     env(ob, ts, int(r.get("checkedAt") or ts), ts), trig(a.get("amountSol"), None, None, "watch-token rule", "SOL"), text=name)
            s["key"] = f"solana:{tok.get('mint')}:{a.get('type')}"
            s["metrics"]["distinctTx"] = [a.get("signature")] if a.get("signature") else []
            out.append(s)
    return out


# ---------------- convergence & divergence (dependency-aware) ----------------
MODES = [("fast", 6 * 3600, "Potential timely signal"), ("cross-session", 24 * 3600, "Slower event context"),
         ("forensic", 48 * 3600, "Retrospective reconstruction; not an early warning")]


def convergence(sigs: list[dict], now: int, window_s: int = 48 * 3600) -> list[dict]:
    """Group by canonical entity. Each causal family contributes ONE effective observation (its earliest-available
    signal). ≥2 families required. Generic tags never link. The ranking is uncalibrated: an attention index, not a probability."""
    by: dict[str, list[dict]] = {}
    for s in sigs:
        if s["source"] == "cross" or s["basis"] == "unverified" or SEV.index(s["severity"]) < 1 or now - s["when"] > window_s:
            continue
        for e in s.get("entities") or []:
            by.setdefault(e, []).append(s)
    out = []
    for ent, ss in sorted(by.items()):
        fam: dict[str, list[dict]] = {}
        for s in ss:
            fam.setdefault(s["family"], []).append(s)
        if len(fam) < 2:
            continue
        reps = {f: min(v, key=lambda s: s["when"]) for f, v in fam.items()}
        times = sorted(r["when"] for r in reps.values())
        span = times[-1] - times[0]
        mode = next((m for m in MODES if span <= m[1]), None)
        if not mode:
            continue
        w = {"observed": 1.0, "heuristic": 0.7, "inferred": 0.5}
        sev_mean = sum(SEV.index(r["severity"]) * w.get(r["basis"], 0.5) for r in reps.values()) / len(reps)
        rank = min(100, round(30 * (len(reps) - 1) + 12 * sev_mean + {"fast": 15, "cross-session": 8, "forensic": 0}[mode[0]]))
        sev = "HIGH" if mode[0] == "fast" and len(reps) >= 3 else "MEDIUM" if mode[0] != "forensic" else "LOW"
        tagged = all(r.get("calendar") for r in reps.values())
        if tagged:
            sev = cap(sev, "LOW")
        chain = sorted(ss, key=lambda s: s["when"])
        within = {f: len(v) for f, v in fam.items()}
        label = mode[0].replace("-", " ")
        s = _sig("cross", "CONVERGENCE", sev, "inferred",
                 f"{len(reps)} causal families moved on {ent} ({label}, {span / 3600:.1f}h)",
                 f"{mode[2]}. Distinct data sources; independence of the underlying evidence is not established. Earliest available: "
                 + "; ".join(f"{EN.FAMILY_LABEL[f]}: {r['title']}" for f, r in sorted(reps.items(), key=lambda kv: kv[1]['when'])) + ".",
                 {"name": ent, "id": ent, "url": chain[0]["subject"]["url"]},
                 {"rank": rank, "rankNote": "uncalibrated anomaly-convergence ranking (not a probability)", "families": sorted(reps),
                  "effectiveObservations": len(reps), "signalsPerFamily": within, "mode": mode[0], "spanHours": round(span / 3600, 2),
                  "calendarExplained": tagged,
                  "chain": [{"key": c["key"], "source": c["source"], "family": c["family"], "severity": c["severity"], "basis": c["basis"],
                             "title": c["title"], "availableTime": T.iso(c["when"]), "when": c["when"],
                             "url": (c["evidence"] or [{"url": c["subject"]["url"]}])[0]["url"]} for c in chain[:10]]},
                 [e for r in reps.values() for e in r["evidence"][:1]],
                 ["Matched on a canonical entity, not a shared actor. Same-family signals (e.g. two prediction venues, a stock and its options) count once.",
                  "Ranking is uncalibrated; no hit rate or lead time has been measured on real history."]
                 + (["Every family's move coincided with a scheduled event; likely explained, capped at LOW."] if tagged else []),
                 T.obs(times[0], times[-1], now, times[-1], "HEALTHY", {}, [], False),
                 trig(len(reps), None, 2, f"{mode[0]} ≤{mode[1] // 3600}h", "effective observations (families)"))
        s["key"] = f"cross:{ent}:CONVERGENCE"
        s["entities"] = [ent]
        out.append(s)
    return out


def same_family_repricing(sigs: list[dict], now: int) -> list[dict]:
    """Two venues in ONE family on the same entity (e.g. Polymarket + Kalshi): reported once, never as independent proof."""
    by: dict[tuple, list[dict]] = {}
    for s in sigs:
        if s["source"] in ("polymarket", "kalshi") and s["basis"] != "unverified":
            for e in s.get("entities") or []:
                by.setdefault((s["family"], e), []).append(s)
    out = []
    for (fam, ent), ss in by.items():
        if len({s["source"] for s in ss}) < 2:
            continue
        ss.sort(key=lambda s: s["when"])
        s = _sig("cross", "RELATED_REPRICING", "INFO", "inferred", f"Related contracts on {ent} repriced on {', '.join(sorted({x['source'] for x in ss}))}",
                 "Same causal family: cross-venue arbitrage or a shared public event can explain both. Counted as one observation, not corroboration.",
                 {"name": ent, "id": ent, "url": ss[0]["subject"]["url"]}, {"chain": [{"key": x["key"], "title": x["title"], "when": x["when"]} for x in ss]},
                 [x["evidence"][0] for x in ss if x["evidence"]][:4], ["Which venue led is unknown without independent event availability timestamps."],
                 T.obs(ss[0]["when"], ss[-1]["when"], now, ss[-1]["when"], "HEALTHY", {}, []), trig(len(ss), None, None, "same family", "signals"))
        s["key"] = f"cross:{ent}:RELATED_REPRICING"; s["entities"] = [ent]
        out.append(s)
    return out


def divergence(sigs: list[dict], now: int, quiet_z: float = 1.0) -> list[dict]:
    """Which related market failed to move? For an entity with a ≥MEDIUM signal in one family, list related
    instruments in OTHER families that were observed this run and stayed within ±quiet_z of normal."""
    out = []
    seen = set()
    for s in sigs:
        if s["source"] == "cross" or SEV.index(s["severity"]) < 2 or s["basis"] == "unverified":
            continue
        for ent in s.get("entities") or []:
            if (ent, s["family"]) in seen:
                continue
            rel = [(i, OBSERVED[i]) for i in EN.ENTITIES.get(ent, {}).get("related", []) if i in OBSERVED
                   and EN.FAMILY.get(i.split(":")[0]) != s["family"] and abs(OBSERVED[i]["z"]) < quiet_z]
            if not rel:
                continue
            seen.add((ent, s["family"]))
            d = _sig("cross", "DIVERGENCE", "LOW", "inferred", f"Divergence on {ent}: {s['title'][:90]} — but {', '.join(i.split(':')[1] for i, _ in rel)} barely moved",
                     "A hypothesis to investigate, not a finding: the related market may not have caught up, may disagree, or the link may be weak. Validate with event studies.",
                     {"name": ent, "id": ent, "url": s["subject"]["url"]},
                     {"moved": s["key"], "quiet": [{"instrument": i, "z": o["z"], "url": o["url"], "availableTime": T.iso(o["ts"])} for i, o in rel]},
                     s["evidence"][:1] + [{"label": f"{i} (quiet, z {o['z']:+.1f})", "url": o["url"]} for i, o in rel],
                     ["Quiet is |standardized move| < 1 on the latest daily observation; timing granularity differs across instruments."],
                     T.obs(s["observation"].get("eventTs"), s["when"], now, s["when"], "HEALTHY", {}, []),
                     trig(quiet_z, None, quiet_z, "latest observation", "|z| of related instruments"))
            d["key"] = f"cross:{ent}:DIVERGENCE:{s['family']}"; d["entities"] = [ent]
            out.append(d)
    return out
