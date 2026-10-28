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
import re
import statistics

from . import entities as EN
from . import timebase as T

SEV = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
BASES = ("observed", "heuristic", "inferred", "unverified")
# key -> {"ratio": magnitude/entry threshold | None, "valid": bool, "reason": str | None}. A key that is ABSENT was not
# observed this run (failed fetch, skipped detector); the lifecycle must hold, never resolve, such incidents.
PROBES: dict[str, dict] = {}
OBSERVED: dict[str, dict] = {}     # instrument id -> latest standardized move + its time window, for divergence


def reset():
    PROBES.clear(); OBSERVED.clear()


def sev_max(a: str, b: str) -> str:
    return a if SEV.index(a) >= SEV.index(b) else b


def cap(sev: str, top: str) -> str:
    return SEV[min(SEV.index(sev), SEV.index(top))]


def key(source: str, entity: str, typ: str) -> str:
    return f"{source}:{entity}:{typ}"


def probe(source: str, entity: str, typ: str, ratio: float | None, reason: str | None = None):
    """Record a VALID measurement (ratio) or an explicitly invalid one (ratio None + reason, e.g. incomplete history)."""
    k = key(source, entity, typ)
    if ratio is None or (isinstance(ratio, float) and math.isnan(ratio)):
        if k not in PROBES:
            PROBES[k] = {"ratio": None, "valid": False, "reason": reason or "insufficient history"}
        return
    old = PROBES.get(k)
    r = round(float(ratio), 4)
    if not old or not old["valid"] or r > old["ratio"]:
        PROBES[k] = {"ratio": r, "valid": True, "reason": None}


def invalid(source: str, entity: str, typ: str, reason: str):
    PROBES[key(source, entity, typ)] = {"ratio": None, "valid": False, "reason": reason}


def observe(instrument: str, z: float | None, url: str, ts: int | None, granularity: str = "daily", window: tuple | None = None):
    if z is not None:
        OBSERVED[instrument] = {"z": round(z, 2), "url": url, "ts": ts, "granularity": granularity, "window": window}


def _sig(source, typ, severity, basis, title, what, subject, metrics, evidence, limits, observation, trigger,
         text="", instrument=None, limited=False):
    assert basis in BASES
    ents = EN.resolve(source, instrument, f"{subject.get('name', '')} {text}")
    inst = f"{source}:{instrument}" if instrument else None
    when = observation.get("availableTs") or observation.get("ingestTs")
    return {"key": key(source, subject.get("id") or subject["name"], typ), "source": source, "family": EN.family_of(source, inst),
            "relations": {e: EN.relation(inst, e, source, text) for e in ents},
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


def env(obs_base: dict, event=None, available=None, valid=None, approx=False, extra_limits=(), *, granularity="intraday",
        event_basis="provider", avail_basis="provider", final=True, status=None) -> dict:
    """Per-signal observation envelope. Times keep their basis:
    event_basis / avail_basis ∈ provider | estimated | ingest-lower-bound | window-start.
    An availability estimate later than the ingest time is NEVER silently clamped: for data already final in hand
    (final=True) the first-observed ingest time is used and labelled so; otherwise the observation is marked
    INCOMPLETE and excluded from time-sensitive (fast) analysis."""
    ing = obs_base["ingestTs"]
    temporal = "OK"
    if available is None:
        available, avail_basis = ing, "ingest-lower-bound"
    elif available > ing:
        if final:
            available, avail_basis = ing, "ingest-lower-bound"
        else:
            temporal = "INCOMPLETE"
    if event is not None and event > ing + 120:
        temporal = "FUTURE_EVENT_TIME"
    o = T.obs(event, available, ing, valid if valid is not None else event, status or obs_base["status"], obs_base["coverage"],
              list(obs_base.get("limitations") or []) + list(extra_limits), approx)
    o.update(granularity=granularity, timeBasis={"event": event_basis, "available": avail_basis, "ingest": "local clock"},
             temporalStatus=temporal,
             fastEligible=temporal == "OK" and granularity in ("intraday", "delayed"))
    return o


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
    irregular = False
    if hist and len(hist) >= 20:
        # never assume adjacent CLOB samples are 15 min apart: only use pairs 10–20 min apart
        pairs = [(b[1] - a[1]) for a, b in zip(hist[:-1], hist[1:]) if 600 <= b[0] - a[0] <= 1200]
        last_gap = hist[-1][0] - hist[-2][0]
        c15 = (hist[-1][1] - hist[-2][1]) if 600 <= last_gap <= 1200 else None
        irregular = c15 is None or len(pairs) < len(hist) - 1
        diffs = pairs[:-1] if c15 is not None else pairs
        vol15 = statistics.pstdev(diffs) if len(diffs) >= 10 else None
    r1h = abs(h1) / 0.12
    r15 = abs(c15) / 0.08 if c15 is not None else 0.0
    rvol = abs(c15) / (3 * vol15) if (c15 is not None and vol15) else None
    ratio = max(r1h, r15 if (rvol is None or rvol >= 1) else 0.0)
    probe("polymarket", ent, "ODDS_REPRICING", ratio)
    # volume must be point-in-time: a current Gamma 24h volume is not evidence about a historical observation
    vol_pit = m.get("vol24AsOf") is None or abs(m["vol24AsOf"] - now) <= 3600
    if ratio < 1 or (vol_pit and (m.get("vol24") or 0) < 25_000):
        return None
    if not vol_pit:
        p = m["price"]
        return _sig("polymarket", "ODDS_REPRICING", "INFO", "unverified", f"Price moved {pts(abs(h1))} in 1h, volume not known at that time: “{m['title']}”",
                    "The volume eligibility floor can't be checked: the only volume available is from a later time, which would be look-ahead.",
                    {"name": m["title"], "id": ent, "url": m["url"]}, {"price": p, "change": h1, "window": "1h", "vol24": None},
                    [{"label": "Polymarket market", "url": m["url"]}], ["Volume not point-in-time; not eligible as a finding (REPLAY-01)."],
                    env(ob, now - 3600, now, now, True, granularity="intraday", event_basis="window-start"),
                    trig(round(abs(h1), 4), None, 0.12, "1h", "probability points"), text=f"{m['title']} {m.get('event') or ''}")
    win, ch, thr = ("15m", c15, 0.08) if r15 >= r1h and c15 is not None else ("1h", h1, 0.12)
    phase, settling = _phase(m, now)
    sev = "HIGH" if ratio >= 2 and (m.get("vol24") or 0) >= 250_000 else "MEDIUM" if ratio >= 1.4 else "LOW"
    limited = hist is None
    lim = ["Real traded notional in the same window isn't available from Gamma; 24h volume is used as a floor."]
    if irregular and not limited:
        lim.append("CLOB history has irregular sample spacing; only 10–20 minute pairs were used.")
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
                {"price": p, "change": ch, "outcome": m.get("outcome"), "window": win, "vol24": m.get("vol24"), "liquidity": m.get("liquidity"), "spread": spread,
                 "eventPhase": phase, "eventVol15m": vol15},
                [{"label": "Polymarket market", "url": m["url"]}, {"label": "Gamma API record", "url": m.get("api")}],
                lim, env(ob, now - (900 if win == "15m" else 3600), now, now, approx=True,
                         extra_limits=["Event time is the start of the measurement window; the exact moment of repricing isn't known."],
                         granularity="intraday", event_basis="window-start", avail_basis="ingest-lower-bound"),
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
                    ["Insufficient historical baseline. This is not a maximal anomaly."], env(ob, now - 86400, now, now, True, granularity="daily", event_basis="window-start", avail_basis="ingest-lower-bound"),
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
                lim, env(ob, now - 86400, now, now, True, granularity="daily", event_basis="window-start", avail_basis="ingest-lower-bound"), trig(vol, round(base, 2), round(4 * base, 2), "24h vs prior 6d", "USD"),
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
            out.append(_sig("kalshi", "ODDS_REPRICING", cap(sev, "LOW") if lim else sev, "heuristic" if lim else "observed",
                            f"Yes {'midpoint' if not lim else 'price'} {'up' if ch > 0 else 'down'} {pts(abs(ch))} vs previous day: “{m['title']}”",
                            f"{pct(p)} vs {pct(prev)} on {v24:,.0f} contracts.", subj, {"price": p, "prev": prev, "change": round(ch, 4), "vol24": v24}, ev,
                            lim + ["Previous-day comparison only (no intraday history); 15m/1h windows not available."],
                            env(ob, now - 86400, now, now, True, granularity="daily", event_basis="window-start", avail_basis="ingest-lower-bound"), trig(round(abs(ch), 4), prev, 0.12, "1d", "probability points"),
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
                                env(ob, now - 86400, now, now, True, granularity="daily", event_basis="window-start", avail_basis="ingest-lower-bound"), trig(v24, round(base, 1), round(5 * base, 1), "24h vs lifetime/day", "contracts"),
                                text=f"{m['title']} {m.get('event') or ''}"))
        elif age < 7 or base <= 0:
            out.append(_sig("kalshi", "VOLUME_SPIKE", "INFO", "unverified", f"Insufficient baseline: {v24:,.0f} contracts in 24h on “{m['title']}”",
                            "Market too new or no prior volume, so no ratio is computed.", subj, {"vol24": v24, "ratio": None, "ageDays": round(age, 1)}, ev,
                            ["Insufficient historical baseline. This is not a maximal anomaly."], env(ob, now - 86400, now, now, True, granularity="daily", event_basis="window-start", avail_basis="ingest-lower-bound"),
                            trig(v24, None, "5× baseline", "24h vs lifetime/day", "contracts"), text=m["title"]))
    return out


# ---------------- equities / options / macro / crypto spot (daily bars) ----------------

def _close_ts(t: int) -> int:
    d = T.datetime.fromtimestamp(t, T.NY).date()
    return T.ny_ts(d, 16)


def daily_anomaly(source: str, sym: str, rows: list[tuple[int, float, float]], url: str, ob: dict, name: str | None = None,
                  vol_window: int = 60, ret_window: int = 20, close_hm=(16, 0), tz: str | None = None) -> list[dict]:
    """Volume: robust z (median + 1.4826·MAD of 60 sessions of log volume) ≥3 AND ≥1.8× median volume.
    Return: daily log return / prior 20-day realized vol, |z| ≥3. Intraday variants are not supported (daily bars only)."""
    name = name or sym
    out, subj = [], {"name": name, "id": sym, "url": url}
    now = ob["ingestTs"]
    dropped = None
    if rows:
        st = T.daily_bar_status(source, sym, rows[-1][0], now, tz=tz)
        if not st["complete"]:  # never score an in-progress session as a completed daily bar (TIME-01)
            dropped = rows[-1]
            rows = rows[:-1]
    if len(rows) < ret_window + 2:
        for typ in ("RETURN_VS_REALIZED_VOL", "VOLUME_ROBUST_Z"):
            invalid(source, sym, typ, "insufficient completed history")
        return []
    t, c, v = rows[-1]
    prev_c = rows[-2][1]
    st = T.daily_bar_status(source, sym, t, now, tz=tz)
    ev_ts, avail = st["eventTs"], st["availableTs"]
    extra = ["Daily bars only; the time of day the move happened is unknown. Intraday detectors are not available on this data.",
             f"Bar close: {st['basis']}; availability is an estimate (close + {T.PUBLISH_LAG_S // 60} min)."]
    if dropped:
        extra.append("Today's bar is still forming and was excluded; this is the last completed session.")
    if st.get("clockNote"):
        extra.append("Provider clock: " + st["clockNote"] + ".")
    o = env(ob, ev_ts, avail, ev_ts, approx=True, extra_limits=extra, granularity="daily", event_basis="estimated", avail_basis="estimated", final=False)
    o.update(sessionDate=st["sessionDate"], providerClock=st["providerClock"], clockNote=st.get("clockNote"))
    evid = [{"label": f"{name} quote & history", "url": url}]
    rets = [math.log(b[1] / a[1]) for a, b in zip(rows[-ret_window - 2:-2], rows[-ret_window - 1:-1]) if a[1] and b[1]]
    r = math.log(c / prev_c) if prev_c and c else 0.0
    rv = statistics.pstdev(rets) if len(rets) >= 10 else 0.0
    rz = r / rv if rv else None
    observe(f"{source}:{sym}", rz, url, avail, "daily", (ev_ts - 86400, ev_ts))
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
    issue = ch.get("snapshotIssue") or (None if snap else "missing snapshot time")
    if snap:
        o = env(ob, snap, snap, snap, extra_limits=["Delayed snapshot (~15 min); retrospective anomaly report, not an immediate flow alert.",
                                                   "Event time is the provider's snapshot time; availability is the same snapshot time (already delayed)."],
                granularity="delayed", event_basis="provider", avail_basis="provider")
    else:  # TIME-02: no invented precision; downgraded and excluded from fast convergence
        o = env(ob, None, None, None, approx=True, extra_limits=[f"Option snapshot time unavailable ({issue}); timing unknown, so this can't take part in fast-mode analysis."],
                granularity="unknown", status="DEGRADED")
        o["fastEligible"] = False
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
    avail = T.ny_ts(obs_day, 18, 0)
    o = env(ob, ev_ts, avail, ev_ts, approx=True,
            extra_limits=["Daily indicative par yields; availability is an estimate (same business day, late afternoon ET) or the first time this scan saw the row, whichever is earlier."],
            granularity="daily", event_basis="estimated", avail_basis="estimated", final=True)
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
        observe(f"treasury:{k}", bp / (scale or 8), url, avail, "daily", (ev_ts - 86400, ev_ts))
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
            o = env(ob, t1 + 86400, t1 + 86400 + 300, t1 + 86400, True, ["OKX only; other venues' open interest can differ."], granularity="daily",
                    event_basis="provider", avail_basis="estimated", final=True)
            out.append(_sig("crypto", "OI_SHOCK", "HIGH" if abs(ch) >= 0.30 else "MEDIUM", "observed",
                            f"Unusual observed open interest: {ccy} perp OI {ch * 100:+.0f}% in contracts over 24h (robust z {z:.1f})",
                            f"Contracts {c0:,.0f} → {c1:,.0f}; USD value {usd_ch * 100:+.0f}%." if usd_ch is not None else f"Contracts {c0:,.0f} → {c1:,.0f}.", subj,
                            {"oiContracts": c1, "oiUsd": u1, "change1dContracts": round(ch, 4), "change1dUsd": None if usd_ch is None else round(usd_ch, 4), "z": round(z, 2)},
                            evid, ["Daily fallback (intraday 1h/4h OI history not used). USD OI can rise with price without contract growth; both are shown."], o,
                            trig(round(ch, 4), None, 0.15, "24h, z vs prior 30 daily changes", "fraction (contracts)"), text=text, instrument=ccy))
    # per-settlement normalization (PROV-02): each settlement uses its own interval; unknown intervals are skipped
    f8 = []
    for row in funding:
        t_, r_, gap = (row + (interval_h,))[:3] if len(row) == 2 else row
        if gap:
            f8.append((t_, r_ * 8 / gap))
    ih = (funding[-1][2] if len(funding[-1]) > 2 else None) or interval_h or 8.0
    if len(f8) < 30:
        invalid("crypto", f"{ccy}-PERP", "FUNDING_EXTREME", f"only {len(f8)} settlements with a known interval; no percentile computed")
    else:
        t, r = f8[-1]
        hist = sorted(abs(x) for _, x in f8[:-1][-90:])
        p95 = hist[int(0.95 * (len(hist) - 1))]; p99 = hist[int(0.99 * (len(hist) - 1))]
        probe("crypto", f"{ccy}-PERP", "FUNDING_EXTREME", min(abs(r) / 0.0005, abs(r) / p95 if p95 else 99))
        if abs(r) >= 0.0005 and abs(r) > p95:
            severe = abs(r) >= 0.001 and abs(r) > p99
            o = env(ob, t, t + 60, t, False, [], granularity="intraday", event_basis="provider", avail_basis="estimated", final=True)
            out.append(_sig("crypto", "FUNDING_EXTREME", "HIGH" if severe else "MEDIUM", "observed",
                            f"{ccy} perp funding {r * 100:+.3f}% per 8h-equivalent ({'longs' if r > 0 else 'shorts'} paying), above the 30-day {'99th' if severe else '95th'} percentile",
                            f"Settlement interval {ih:g}h; realized rate normalized to 8h.", subj,
                            {"funding8h": r, "intervalH": ih, "p95": p95, "p99": p99, "sample": len(f8) - 1}, evid,
                            ["Funding is positioning context, not a directional forecast. Basis and predicted-next funding not yet combined."], o,
                            trig(round(abs(r), 6), round(p95, 6), max(0.0005, p95), f"latest settlement vs {len(f8) - 1} prior", "funding per 8h"), text=text, instrument=ccy))
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
                            env(ob, now - 86400, now, now, True, granularity="daily", event_basis="window-start", avail_basis="ingest-lower-bound"), trig(round(abs(d1)), None, 250e6, "1d", "USD"),
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
        docs = [d for d in ((tx or {}).get(f["url"]) for f in fs) if isinstance(d, dict)]
        # amendments: a 4/A from an owner who also has an original filing here is not counted twice
        orig_owners = {o for d in docs if not d["amendment"] for o in d["owners"]}
        use = [d for d in docs if not d["amendment"] or not set(d["owners"]) & orig_owners]
        parsed = [dict(t, owners=d["owners"]) for d in use for t in d["transactions"]]
        ticker = next((d["issuerTicker"] for d in docs if d.get("issuerTicker")), None)
        n = fs[0]["name"]
        subj = {"name": n, "id": cik, "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4"}
        ev = [{"label": f"Form 4 · {n}", "url": f["url"]} for f in fs[:4]]
        eids = [{"id": accession(f["url"]), "eventTs": f["ts"], "url": f["url"]} for f in fs if accession(f["url"])]
        o = env(ob, min(f["ts"] or now for f in fs), max(f["ts"] or now for f in fs), max(f["ts"] or now for f in fs),
                extra_limits=["Event time = earliest EDGAR acceptance time in the cluster; trades occurred up to two business days earlier."],
                granularity="intraday", event_basis="provider", avail_basis="provider")
        if not parsed:
            out.append(_sig("sec", "FORM4_FILING_CLUSTER", "INFO", "unverified", f"{len(fs)} Form 4 filings for {n} (transactions not parsed)",
                            "Counts alone are mostly noise: routine grants and planned sales dominate.", subj, {"filings": len(fs)}, ev,
                            ["Transactions could not be parsed; no finding is made."], o, trig(len(fs), None, 3, "latest EDGAR feed", "filings"), text=n, instrument=ticker))
            continue
        buys = [t for t in parsed if t["code"] == "P"]
        sells = [t for t in parsed if t["code"] == "S"]
        owners = lambda ts: len({o for t in ts for o in t["owners"]})  # noqa: E731
        priced = lambda ts: [t for t in ts if t["price"] is not None and t["shares"] is not None]  # noqa: E731
        usd = lambda ts: sum(t["shares"] * t["price"] for t in priced(ts))  # noqa: E731
        nop = lambda ts: len(ts) - len(priced(ts))  # noqa: E731
        lim0 = ["Reported by the filers on Form 4; this says nothing about what anyone knew or intended."]
        if buys:
            out.append(_sig("sec", "REPORTED_OPEN_MARKET_PURCHASES", "MEDIUM" if usd(buys) >= 1e6 else "LOW", "observed",
                            f"{n}: {len(buys)} reported open-market purchase(s) by {owners(buys)} reporting person(s) (≈${usd(buys):,.0f}{' + ' + str(nop(buys)) + ' without a reported price' if nop(buys) else ''})",
                            "Transaction code P parsed from the filings. Grants, exercises and gifts excluded; amendments not double-counted.", subj,
                            {"eventIds": eids, "filings": len(fs), "purchases": len(buys), "purchaseUsd": round(usd(buys)), "unpriced": nop(buys), "reportingPersons": owners(buys), "sales": len(sells)}, ev,
                            lim0 + ["Filings arrive up to two business days after the trade."], o, trig(len(buys), None, 1, "latest EDGAR feed", "purchases"), text=n, instrument=ticker))
        elif sells:
            out.append(_sig("sec", "REPORTED_SALES_CLUSTER", "LOW", "observed", f"{n}: {len(sells)} reported sale(s) by {owners(sells)} reporting person(s) (≈${usd(sells):,.0f})",
                            "Code S parsed. Sales are frequently scheduled (10b5-1); context only.", subj,
                            {"eventIds": eids, "filings": len(fs), "sales": len(sells), "salesUsd": round(usd(sells)), "unpriced": nop(sells), "reportingPersons": owners(sells)}, ev,
                            lim0 + ["10b5-1 plan status isn't parsed."], o, trig(len(sells), None, 1, "latest EDGAR feed", "sales"), text=n, instrument=ticker))
    # R5-01: every 8-K accession is its own event; several filings by one issuer stay separately inspectable
    by8: dict[str, list[dict]] = {}
    for f in eightk or []:
        if [i for i in f["items"] if i in MATERIAL_8K] and accession(f.get("url")):
            by8.setdefault(f["cik"], []).append(f)
    for cik, fs in by8.items():
        fs = sorted(fs, key=lambda f: (f["ts"] or 0, accession(f["url"])))
        items = sorted({i for f in fs for i in f["items"] if i in MATERIAL_8K})
        severe = [i for i in items if i in SEVERE_8K]
        n = fs[-1]["name"]
        s = _sig("sec", "8K_EVENT", "HIGH" if severe else "LOW" if items == ["5.02"] else "MEDIUM", "observed",
                 f"{n} 8-K: " + ", ".join(MATERIAL_8K[i] for i in items) + (f" ({len(fs)} filings)" if len(fs) > 1 else ""),
                 "Items " + ", ".join(items) + " filed with the SEC" + (f" across {len(fs)} separate filings" if len(fs) > 1 else "") + ".",
                 {"name": n, "id": cik, "url": fs[-1]["url"]}, {"items": items, "filings": len(fs),
                  "eventIds": [{"id": accession(f["url"]), "eventTs": f["ts"], "url": f["url"], "items": [i for i in f["items"] if i in MATERIAL_8K]} for f in fs]},
                 [{"label": f"8-K {accession(f['url'])}", "url": f["url"]} for f in fs],
                 ["Item codes only, not the full text. Latest ~100 filings.", "A filing is a disclosure; it says nothing about what anyone knew or intended."],
                 env(ob, fs[0]["ts"], fs[-1]["ts"], fs[-1]["ts"]), trig(len(items), None, 1, "latest EDGAR feed", "material items"), text=n)
        out.append(s)
    return out


def accession(url: str | None) -> str | None:
    """SEC accession number (immutable filing id) from an EDGAR URL: 0000000042-26-000001."""
    m = re.search(r"(\d{10}-\d{2}-\d{6})", url or "")
    if m:
        return m.group(1)
    m = re.search(r"/(\d{18})(?:/|$)", url or "")
    return f"{m.group(1)[:10]}-{m.group(1)[10:12]}-{m.group(1)[12:]}" if m else None


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
            # R5-01: immutable event id = transaction signature + event type + token mint, with its own time and link
            s["metrics"]["eventIds"] = [{"id": f"{a['signature']}:{a.get('type')}:{tok.get('mint')}", "eventTs": ts, "url": a.get("url") or (ev[0]["url"] if ev else None),
                                         "observedAt": int(r.get("checkedAt") or 0)}] if a.get("signature") else []
            out.append(s)
    return out


# ---------------- convergence & divergence (typed relations, dependency-aware) ----------------
MODES = [("fast", 6 * 3600, "Close in time on timely data"), ("cross-session", 24 * 3600, "Slower event context"),
         ("forensic", 48 * 3600, "Retrospective co-occurrence (not an early warning)")]
_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
_SETTLE = re.compile(rf"\b(?:{_MONTHS})(?:\s+\d{{1,2}})?(?:,?\s+\d{{4}})?|\b20\d\d\b|\bq[1-4]\b|end of (?:the )?(?:year|month|\d{{4}})", re.I)


def settlement_terms(text: str) -> frozenset:
    """Settlement date tokens of a prediction question ('December', 'end of 2026', 'Q4'); empty if none found."""
    return frozenset(m.group(0).lower().replace(",", "") for m in _SETTLE.finditer(text or ""))


def _direction(s) -> int:
    ch = (s.get("metrics") or {}).get("change")
    if not ch:
        return 0
    yes = (s.get("metrics") or {}).get("outcome", "Yes") != "No"
    return (1 if ch > 0 else -1) * (1 if yes else -1)


def _eligible(s, now, window_s):
    o = s.get("observation") or {}
    if s["source"] == "cross" or s["basis"] == "unverified" or SEV.index(s["severity"]) < 1:
        return "not a counted finding (cross/unverified/INFO)"
    if now - s["when"] > window_s:
        return "outside the 48h window"
    if o.get("sourceStatus") in ("STALE", "UNAVAILABLE", "NOT_CONFIGURED"):
        return f"source {o.get('sourceStatus')}"
    if o.get("temporalStatus", "OK") != "OK":
        return f"time not valid ({o.get('temporalStatus')})"
    return None


_ACT = {"cut": "cut", "cuts": "cut", "lower": "cut", "hike": "hike", "hikes": "hike", "raise": "hike", "increase": "hike",
        "hold": "hold", "pause": "hold", "unchanged": "hold", "above": "above", "over": "above", "below": "below", "under": "below"}


def outcome_terms(text: str) -> frozenset:
    """R4-05: the outcome a prediction question settles on (cut / hike / hold / above / below)."""
    return frozenset(_ACT[w] for w in re.findall(r"[a-z]+", (text or "").lower()) if w in _ACT)


def certainty(s) -> str:
    """R4-03: temporal certainty of one contributor's availability time: exact | estimated | lower-bound | daily."""
    o = s.get("observation") or {}
    basis = (o.get("timeBasis") or {}).get("available")
    if o.get("temporalStatus", "OK") != "OK":
        return "invalid"
    if basis == "ingest-lower-bound":
        return "lower-bound"
    if basis in ("estimated", "window-start") or o.get("granularity") == "daily":
        return "estimated" if o.get("granularity") != "daily" else "daily"
    return "exact" if o.get("granularity") in ("intraday", "delayed", None) else "estimated"


def _dep(s, ent, rel=None):
    if rel == "SETTLES_ON_UNDERLYING":
        i = EN.settlement_instrument(ent, s.get("title", ""))
        if i:
            return EN.dependency_group(i, i.split(":")[0])
    if s["family"] == "prediction":
        return f"prediction:{ent}"
    if s["source"] == "sec":
        eq = [i for i in EN.ENTITIES.get(ent, {}).get("instruments", []) if i.startswith("equities:")]
        if eq:
            return f"issuer:{eq[0].split(':')[1]}"
    return EN.dependency_group(s.get("instrument"), s["source"], s["subject"].get("id"))


def _ref(s, rel):
    if rel == "SETTLES_ON_UNDERLYING":
        return EN.settlement_instrument(None, s.get("title", ""))
    return s.get("instrument")


def _dep_reason(x, r, s0, g):
    """R5-04: say WHY two observations count once: the same reference price/rate, a correlated proxy, or a shared issuer chain."""
    a, b = _ref(x, r), _ref(s0[0], s0[1])
    if a and a == b:
        return f"same reference ({a}) as {s0[0]['key']}: settles on / is the same price, not independent evidence; counted once"
    if g.startswith("dep") and a and b:
        return f"correlated proxy: {a} vs {b} (same dependency group {g}) are related exposures but not identical instruments; not counted separately"
    return f"same dependency group ({g}) as {s0[0]['key']}: mechanically linked, counted once"


def convergence(sigs: list[dict], now: int, window_s: int = 48 * 3600) -> list[dict]:
    """CONVERGENCE needs ≥2 distinct counted evidence groups in different causal families, each with a counting typed
    relation to the entity (SAME_UNDERLYING / SAME_EVENT / DIRECT_PROXY / DISCLOSURE_REACTION), time-compatible
    observations, and non-conflicting prediction questions. Mechanically linked instruments (oil + USO, BTC + MSTR,
    a filing + its stock) are one group. Otherwise a plausible link is reported as RELATED_ACTIVITY (hypothesis).
    The rank is an uncalibrated sorting aid; contributing and excluded observations are stored."""
    by: dict[str, list[dict]] = {}
    for s in sigs:
        for e in s.get("entities") or []:
            by.setdefault(e, []).append(s)
    out = []
    for ent, ss in sorted(by.items()):
        excluded, units = [], {}
        for s in ss:
            why = _eligible(s, now, window_s)
            rel = (s.get("relations") or {}).get(ent) or EN.relation(s.get("instrument"), ent, s["source"], s.get("title", ""))
            if why is None and rel not in EN.COUNTING and rel != "DISCLOSURE_REACTION":
                why = ("relation RELATED_ACTIVITY: prediction question without a normalized event, settlement or outcome; related activity only, not counted"
                       if rel == "RELATED_ACTIVITY" else f"relation {rel}: exposure, not the same underlying or event")
            if why:
                if s["source"] != "cross":
                    excluded.append({"key": s["key"], "reason": why, "relation": rel})
                continue
            units.setdefault(_dep(s, ent, rel), []).append((s, rel))
        # prediction questions must agree on settlement and direction to count as one SAME_EVENT observation
        pk = f"prediction:{ent}"
        inst = None
        if pk in units:
            ps = [x for x, _ in units[pk]]
            specs = [EN.settlement_spec(x["title"]) for x in ps]
            insts = {(sp or {}).get("eventInstance") or (f"{sp['settlementMetric']}:{sp.get('polarity')}{sp.get('threshold')}:{sp.get('date')}" if sp else None) for sp in specs}
            if len(insts) > 1:  # R6-05: two different normalized event instances (meeting dates, outcomes) are never one event
                for x in ps:
                    excluded.append({"key": x["key"], "reason": "prediction questions settle on different outcomes or meetings (normalized instances " + " vs ".join(sorted(str(i) for i in insts)) + "); not one event", "relation": "UNRESOLVED"})
                del units[pk]
                ps = []
            elif insts and None not in insts:
                inst = f"{ent}:{next(iter(insts))}"
        if pk in units:
            terms = {settlement_terms(x["title"]) for x in ps}
            outs = {outcome_terms(x["title"]) for x in ps}
            dirs = {_direction(x) for x in ps} - {0}
            if len(outs) > 1:
                for x in ps:
                    excluded.append({"key": x["key"], "reason": "prediction questions settle on different outcomes (" + " vs ".join(sorted("/".join(sorted(o)) or "unstated" for o in outs)) + "); not one event instance", "relation": "UNRESOLVED"})
                del units[pk]
            elif len(terms) > 1 or len(dirs) > 1:
                for x in ps:
                    excluded.append({"key": x["key"], "reason": "prediction questions differ in settlement or direction; not one event", "relation": "UNRESOLVED"})
                del units[pk]
        reps = {}
        for g, lst in units.items():
            s0 = min(lst, key=lambda x: x[0]["when"])
            for x, r in lst:
                if x is not s0[0]:
                    excluded.append({"key": x["key"], "reason": _dep_reason(x, r, s0, g), "relation": r})
            fam = s0[0]["family"]
            if fam not in reps or s0[0]["when"] < reps[fam]["s"]["when"]:
                if fam in reps:
                    excluded.append({"key": reps[fam]["s"]["key"], "reason": f"second group in family {fam}; one per family", "relation": reps[fam]["rel"]})
                reps[fam] = {"s": s0[0], "rel": s0[1], "group": g, "dependents": [x["key"] for x, _ in lst if x is not s0[0]]}
            else:
                excluded.append({"key": s0[0]["key"], "reason": f"second group in family {fam}; one per family", "relation": s0[1]})
        others = {x["family"] for x in ss if x["source"] != "cross" and _eligible(x, now, window_s) is None}
        if len(reps) < 2:
            if len(others) >= 2 and ss:
                out.append(_related(ent, ss, excluded, now))
            continue
        R = list(reps.values())
        times = sorted(r["s"]["when"] for r in R)
        span = times[-1] - times[0]
        cert = {r["s"]["key"]: certainty(r["s"]) for r in R}
        comparable = all(c == "exact" for c in cert.values())
        fast_ok = all((r["s"].get("observation") or {}).get("fastEligible") for r in R)
        if comparable:
            mode = next((m for m in MODES if span <= m[1] and (m[0] != "fast" or fast_ok)), None)
        else:  # R4-03: lower-bound / estimated / daily times can't give a co-occurrence interval or a timing bonus
            mode = ("timing-approximate", window_s, "Within the same 48h window; timing comparison approximate (some availability times are estimates or ingest-time lower bounds)")
        if not mode:
            continue
        w = {"observed": 1.0, "heuristic": 0.7, "inferred": 0.5}
        sev_mean = sum(SEV.index(r["s"]["severity"]) * w.get(r["s"]["basis"], 0.5) for r in R) / len(R)
        rank = min(100, round(30 * (len(R) - 1) + 12 * sev_mean + {"fast": 15, "cross-session": 8}.get(mode[0], 0)))
        sev = "HIGH" if mode[0] == "fast" and len(R) >= 3 else "MEDIUM" if mode[0] == "cross-session" or mode[0] == "fast" else "LOW"
        # calendar (P0.03): only the SAME specific event, already released, as a RELEASE_REACTION for EVERY member explains it
        rr = [{c["eventId"] for c in (r["s"].get("calendar") or []) if c.get("phase") == "RELEASE_REACTION" and c.get("availableAtObservation")} for r in R]
        common = set.intersection(*rr) if rr else set()
        explained = bool(common)
        PW = {"PRE_EVENT_POSITIONING": "before", "RELEASE_REACTION": "release reaction to", "POST_EVENT_CONTEXT": "after"}
        ctx = sorted({f"{PW.get(c['phase'], c['phase'])} {c['label']}" for r in R for c in (r["s"].get("calendar") or []) if c.get("phase") != "UNRELATED"})
        if explained:
            sev = cap(sev, "LOW")
        chain = sorted([r["s"] for r in R], key=lambda s: s["when"])
        label = mode[0].replace("-", " ")
        tlabel = f"{label}, {span / 3600:.1f}h" if comparable else "timing comparison approximate"
        s = _sig("cross", "CONVERGENCE", sev, "inferred",
                 f"Related observations on {ent}: {len(R)} distinct counted evidence groups ({tlabel})",
                 f"{mode[2]}. Earliest available per group: " + "; ".join(f"{EN.FAMILY_LABEL.get(r['s']['family'], r['s']['family'])} [{r['rel']}]: {r['s']['title']}"
                                                                    for r in sorted(R, key=lambda r: r['s']['when'])) + ".",
                 {"name": ent, "id": ent, "url": chain[0]["subject"]["url"]},
                 {"rank": rank, "rankNote": "uncalibrated anomaly-convergence ranking (a sorting aid, not a probability or confidence)",
                  "families": sorted(reps), "effectiveObservations": len(R), "mode": mode[0], "spanHours": round(span / 3600, 2) if comparable else None,
                  "timingComparable": comparable, "timingNote": None if comparable else "Availability times include estimates or ingest-time lower bounds ("
                  + ", ".join(sorted(set(cert.values()) - {"exact"})) + "); no co-occurrence interval is computed and no timing bonus is applied.",
                  "calendarExplained": explained, "explainedBy": sorted(common), "calendarContext": ctx,
                  "contributing": [{"key": r["s"]["key"], "family": f, "relation": r["rel"], "dependencyGroup": r["group"], "dependentsCountedOnce": r["dependents"],
                                    "granularity": (r["s"].get("observation") or {}).get("granularity"), "fastEligible": (r["s"].get("observation") or {}).get("fastEligible"),
                                    "temporalCertainty": cert[r["s"]["key"]], "availableBasis": ((r["s"].get("observation") or {}).get("timeBasis") or {}).get("available")}
                                   for f, r in reps.items()],
                  "excluded": excluded, "memberKeys": [r["s"]["key"] for r in R], "eventInstance": inst,
                  "chain": [{"key": c["key"], "source": c["source"], "family": c["family"], "severity": c["severity"], "basis": c["basis"],
                             "title": c["title"], "availableTime": T.iso(c["when"]), "when": c["when"],
                             "url": (c["evidence"] or [{"url": c["subject"]["url"]}])[0]["url"]} for c in chain[:10]]},
                 [e for r in R for e in r["s"]["evidence"][:1]],
                 ["Linked through a canonical entity and typed relations, not a shared actor. Mechanically linked instruments and same-family venues count once.",
                  "Distinct counted groups come from a conservative manual relation table, not a proof that the information is independent; this is co-occurrence.",
                  "Ranking is uncalibrated; no hit rate or lead time has been measured."]
                 + (["Every group's move was a release reaction to the same event (" + ", ".join(sorted(common)) + "); capped at LOW."] if explained else [])
                 + (["Calendar context (not an explanation): " + "; ".join(ctx[:4])] if ctx and not explained else []),
                 T.obs(times[0], times[-1], now, times[-1], "HEALTHY", {}, [], False),
                 trig(len(R), None, 2, f"{mode[0]} ≤{mode[1] // 3600}h", "distinct counted evidence groups"))
        s["key"] = f"cross:{ent}:CONVERGENCE"
        s["entities"] = [ent]
        out.append(s)
    return out


def _related(ent, ss, excluded, now):
    ss = sorted([x for x in ss if x["source"] != "cross"], key=lambda x: x["when"])
    s = _sig("cross", "RELATED_ACTIVITY", "INFO", "inferred", f"Related activity on {ent} (not counted as convergence)",
             "Several observations mention or are exposed to this entity, but they are mechanically linked, exposure-only, conflicting or not time-compatible. A hypothesis to check, not corroboration.",
             {"name": ent, "id": ent, "url": ss[0]["subject"]["url"]}, {"excluded": excluded, "chain": [{"key": x["key"], "title": x["title"], "when": x["when"], "family": x["family"]} for x in ss[:8]]},
             [x["evidence"][0] for x in ss if x["evidence"]][:4], ["See `excluded` for why each observation wasn't counted."],
             T.obs(ss[0]["when"], ss[-1]["when"], now, ss[-1]["when"], "HEALTHY", {}, []), trig(len(ss), None, None, "related", "observations"))
    s["key"] = f"cross:{ent}:RELATED_ACTIVITY"; s["entities"] = [ent]
    return s


def same_family_repricing(sigs: list[dict], now: int) -> list[dict]:
    """Prediction venues on one entity. Same settlement terms → RELATED_REPRICING (one observation, not corroboration).
    Different settlement/outcome → RELATED_ACTIVITY wording: different questions, not the same event."""
    by: dict[str, list[dict]] = {}
    for s in sigs:
        if s["source"] in ("polymarket", "kalshi") and s["basis"] != "unverified":
            for e in s.get("entities") or []:
                by.setdefault(e, []).append(s)
    out = []
    for ent, ss in by.items():
        if len({s["source"] for s in ss}) < 2:
            continue
        ss.sort(key=lambda s: s["when"])
        same = len({settlement_terms(x["title"]) for x in ss}) == 1 and len({_direction(x) for x in ss} - {0}) <= 1
        typ = "RELATED_REPRICING" if same else "RELATED_ACTIVITY"
        s = _sig("cross", typ, "INFO", "inferred",
                 f"Related contracts on {ent} repriced on {', '.join(sorted({x['source'] for x in ss}))}" if same else f"Different prediction questions about {ent} moved",
                 ("Same question terms on two venues: cross-venue arbitrage or a shared public event can explain both. Counted as one observation, not corroboration."
                  if same else "The questions differ in settlement date or direction, so they are not the same event and don't corroborate each other."),
                 {"name": ent, "id": ent, "url": ss[0]["subject"]["url"]}, {"chain": [{"key": x["key"], "title": x["title"], "when": x["when"]} for x in ss], "sameTerms": same},
                 [x["evidence"][0] for x in ss if x["evidence"]][:4], ["Which venue led is unknown without independent event availability timestamps."],
                 T.obs(ss[0]["when"], ss[-1]["when"], now, ss[-1]["when"], "HEALTHY", {}, []), trig(len(ss), None, None, "same family", "signals"))
        s["key"] = f"cross:{ent}:{typ}"; s["entities"] = [ent]
        out.append(s)
    return out


def divergence(sigs: list[dict], now: int, quiet_z: float = 1.0) -> list[dict]:
    """A related instrument in another family that was observed over a COMPARABLE window and stayed within ±quiet_z.
    A prior-session daily bar can't show that something was quiet during an intraday move (TIME-03)."""
    out = []
    seen = set()
    for s in sigs:
        if s["source"] == "cross" or SEV.index(s["severity"]) < 2 or s["basis"] == "unverified":
            continue
        so = s.get("observation") or {}
        g = so.get("granularity")
        for ent in s.get("entities") or []:
            if (ent, s["family"]) in seen:
                continue
            rel = []
            for i in EN.ENTITIES.get(ent, {}).get("related", []):
                o = OBSERVED.get(i)
                if not o or EN.family_of(i.split(":")[0], i) == s["family"] or abs(o["z"]) >= quiet_z:
                    continue
                if g in ("intraday", "delayed") and o.get("granularity") != g:
                    continue  # not comparable: e.g. yesterday's daily bar vs a live move
                if g == "daily" and o.get("window") and so.get("eventTs") and not (o["window"][0] <= so["eventTs"] <= o["window"][1] + 86400):
                    continue
                if g not in ("intraday", "delayed", "daily"):
                    continue
                rel.append((i, o))
            if not rel:
                continue
            seen.add((ent, s["family"]))
            d = _sig("cross", "DIVERGENCE", "LOW", "inferred", f"Divergence on {ent}: {s['title'][:90]} — but {', '.join(i.split(':')[1] for i, _ in rel)} barely moved",
                     "A hypothesis to investigate, not a finding: the related market may not have caught up, may disagree, or the link may be weak.",
                     {"name": ent, "id": ent, "url": s["subject"]["url"]},
                     {"moved": s["key"], "granularity": g, "quiet": [{"instrument": i, "z": o["z"], "url": o["url"], "availableTime": T.iso(o["ts"]), "granularity": o.get("granularity")} for i, o in rel]},
                     s["evidence"][:1] + [{"label": f"{i} (quiet, z {o['z']:+.1f})", "url": o["url"]} for i, o in rel],
                     [f"Compared on {g} observations over overlapping windows only."],
                     T.obs(so.get("eventTs"), s["when"], now, s["when"], "HEALTHY", {}, []),
                     trig(quiet_z, None, quiet_z, "comparable window", "|z| of related instruments"))
            d["key"] = f"cross:{ent}:DIVERGENCE:{s['family']}"; d["entities"] = [ent]
            out.append(d)
    return out
