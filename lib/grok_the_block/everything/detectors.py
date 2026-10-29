"""Everything-markets detectors. Pure functions over normalized rows; each returns (signals, probes).

A signal describes activity with its evidence. It never says buy, sell or hold, never names a person, and a thin or
failed input yields an explicit "unknown" probe, never "nothing unusual". Thresholds are starting settings, not
validated cutoffs; severity says how far past the threshold, not how likely anything is.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict

SEV = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
PATTERN_LIMIT = "Statistical pattern in public price data, not an accusation. It says nothing about who traded or why."
NOT_ARB = "Not an executable arbitrage: condition, printing, fees, shipping, FX timing and liquidity are not modelled."


def cap(sev: str, top: str) -> str:
    return SEV[min(SEV.index(sev), SEV.index(top))]


def sev_for(x: float, lo: float, mid: float, hi: float) -> str:
    return "HIGH" if x >= hi else "MEDIUM" if x >= mid else "LOW" if x >= lo else "INFO"


def probe(asset: str, typ: str, ratio: float | None, reason: str | None = None) -> dict:
    """ratio = magnitude / entry threshold when measured; None + reason = unknown (never reads as quiet)."""
    return {"asset": asset, "type": typ, "state": "measured" if ratio is not None else "unknown",
            "ratio": None if ratio is None else round(ratio, 3), "reason": reason}


def sig(*, source, category, asset, typ, severity, title, what, when, metrics, trigger, evidence, limits=(), basis="observed",
        derived_only=False, synthetic=False, name=None) -> dict:
    assert severity in SEV and basis in ("observed", "heuristic", "inferred", "unverified")
    return {"key": f"{source}:{asset}:{typ}", "source": source, "category": category, "asset": asset, "name": name or asset,
            "type": typ, "severity": severity, "basis": basis, "title": ("[SYNTHETIC] " if synthetic else "") + title, "what": what,
            "when": int(when or 0), "metrics": metrics, "trigger": trigger, "evidence": [e for e in evidence if e.get("url")],
            "limits": list(limits), "derivedOnly": derived_only, "synthetic": synthetic}


def robust(series: list[float], x: float, min_n: int = 20) -> tuple[float | None, float, float]:
    if len(series) < min_n:
        return None, float("nan"), float("nan")
    med = statistics.median(series)
    mad = 1.4826 * statistics.median(abs(v - med) for v in series)
    return (None if mad == 0 else (x - med) / mad), med, mad


def _date(ts: int) -> str:
    import datetime as _d
    return _d.datetime.fromtimestamp(ts, _d.timezone.utc).strftime("%Y-%m-%d")


# ---------------- liquid daily series (FX fixes, metal ETFs, energy spot) ----------------
def daily_move(source, category, asset, name, rows, url, *, window=20, label="daily", derived_only=False, extra_limits=()):
    """rows: [(ts, value) | (ts, value, volume)] oldest first. Move = last log return / prior `window`-day realised vol."""
    rows = [r for r in rows if r[1] and r[1] > 0]
    if len(rows) < window + 2:
        return [], [probe(asset, "MOVE_VS_REALIZED_VOL", None, f"insufficient history ({len(rows)} of {window + 2} observations)")]
    rets = [math.log(b[1] / a[1]) for a, b in zip(rows[-window - 2:-2], rows[-window - 1:-1])]
    r = math.log(rows[-1][1] / rows[-2][1])
    rv = statistics.pstdev(rets)
    if not rv:
        return [], [probe(asset, "MOVE_VS_REALIZED_VOL", None, "zero realised volatility in window")]
    z = r / rv
    out, prb = [], [probe(asset, "MOVE_VS_REALIZED_VOL", abs(z) / 3)]
    lim = [f"Uses {label} observations only; intraday timing is unknown."] + list(extra_limits)
    if abs(z) >= 3:
        out.append(sig(source=source, category=category, asset=asset, name=name, typ="MOVE_VS_REALIZED_VOL", severity=sev_for(abs(z), 3, 4, 5),
                       title=f"{name} {'rose' if r > 0 else 'fell'} {abs(math.expm1(r)) * 100:.2f}% on {_date(rows[-1][0])}, {abs(z):.1f}× its {window}-day realised volatility",
                       what=f"Log return {r * 100:+.2f}% vs a {window}-day realised volatility of {rv * 100:.2f}% per observation.",
                       when=rows[-1][0], metrics={"returnPct": round(math.expm1(r) * 100, 3), "z": round(z, 2), "realizedVolPct": round(rv * 100, 3),
                                                  **({} if derived_only else {"last": rows[-1][1], "prev": rows[-2][1]})},
                       trigger={"observed": round(abs(z), 2), "threshold": 3, "window": f"{window} observations", "unit": "× realised vol"},
                       evidence=[{"label": f"{name} source page", "url": url}], limits=lim, derived_only=derived_only))
    if len(rows[-1]) > 2:
        vols = [math.log(x[2]) for x in rows[-61:-1] if len(x) > 2 and x[2] > 0]
        v = rows[-1][2]
        vz, med, _ = robust(vols, math.log(v)) if v and v > 0 else (None, 0, 0)
        if vz is None:
            prb.append(probe(asset, "VOLUME_ROBUST_Z", None, "insufficient volume history"))
        else:
            ratio = v / math.exp(med)
            prb.append(probe(asset, "VOLUME_ROBUST_Z", vz / 3))
            if vz >= 3 and ratio >= 1.8:
                out.append(sig(source=source, category=category, asset=asset, name=name, typ="VOLUME_ROBUST_Z", severity=sev_for(vz, 3, 4.5, 6),
                               title=f"{name} traded {ratio:.1f}× its 60-session median volume on {_date(rows[-1][0])}",
                               what=f"Robust z of log volume {vz:.1f} (median + 1.4826·MAD over 60 sessions).", when=rows[-1][0],
                               metrics={"volumeRatio": round(ratio, 2), "z": round(vz, 2)},
                               trigger={"observed": round(vz, 2), "threshold": 3, "window": "60 sessions", "unit": "robust z"},
                               evidence=[{"label": f"{name} source page", "url": url}], limits=lim, derived_only=derived_only))
    return out, prb


def fx_crosscheck(asset, ecb: list[tuple[int, float]], fred: list[tuple[int, float]], url_a, url_b, *, min_bp=20.0, k=5.0):
    """Two official fixes of the same pair at different times of day (ECB ≈14:15 CET, H.10 noon NY). Their gap is
    normal; a gap far outside its own history is a DATA-QUALITY flag (stale, mis-keyed or revised value), not a market signal."""
    fd = dict(fred)
    pairs = [(t, a, fd[t]) for t, a in ecb if t in fd and fd[t] > 0]
    if len(pairs) < 30:
        return [], [probe(asset, "FIX_CROSSCHECK", None, f"only {len(pairs)} matched dates between sources")]
    bps = [(b / a - 1) * 1e4 for _, a, b in pairs]
    z, med, mad = robust(bps[:-1], bps[-1])
    gap = abs(bps[-1] - med)
    prb = [probe(asset, "FIX_CROSSCHECK", None if z is None else abs(z) / k)]
    if z is not None and abs(z) >= k and gap >= min_bp:
        return [sig(source="fx", category="fx", asset=asset, name=asset + " fix cross-check", typ="FIX_CROSSCHECK", severity="LOW",
                    title=f"ECB and Fed H.10 fixes for {asset} disagree by {bps[-1]:+.0f} bp on {_date(pairs[-1][0])} (usual gap {med:+.0f} bp)",
                    what="Data-quality flag: the two official daily fixes diverged far more than usual. Check for a stale or revised value before reading anything into it.",
                    when=pairs[-1][0], metrics={"gapBp": round(bps[-1], 1), "medianGapBp": round(med, 1), "z": round(z, 2)},
                    trigger={"observed": round(abs(z), 2), "threshold": k, "window": f"{len(bps) - 1} matched dates", "unit": "robust z"},
                    evidence=[{"label": "ECB reference rate", "url": url_a}, {"label": "Fed H.10 via FRED", "url": url_b}],
                    limits=["Fixes are taken at different times of day, so some gap is expected."])], prb
    return [], prb


def pair_divergence(category, asset, name, a_rows, b_rows, url_a, url_b, *, k=4.0, window=60, derived_only=True):
    """Two trackers of the same underlying (e.g. GLD vs IAU). Flags a daily return gap far outside its history."""
    bd = {r[0]: r[1] for r in b_rows}
    m = [(t, c, bd[t]) for t, c, *_ in a_rows if t in bd]
    if len(m) < window + 2:
        return [], [probe(asset, "TRACKER_DIVERGENCE", None, f"only {len(m)} common sessions")]
    diffs = [math.log(m[i][1] / m[i - 1][1]) - math.log(m[i][2] / m[i - 1][2]) for i in range(1, len(m))]
    z, med, _ = robust(diffs[-window - 1:-1], diffs[-1])
    prb = [probe(asset, "TRACKER_DIVERGENCE", None if z is None else abs(z) / k)]
    if z is not None and abs(z) >= k:
        return [sig(source="metals", category="metals", asset=asset, name=name, typ="TRACKER_DIVERGENCE", severity=cap(sev_for(abs(z), k, 6, 9), "MEDIUM"),
                    title=f"{name}: the two trackers' daily returns diverged by {diffs[-1] * 1e4:+.0f} bp on {_date(m[-1][0])} ({abs(z):.1f} robust z)",
                    what="Two funds holding the same metal moved differently. Usual causes: creation/redemption timing, closing-auction prints, or a data error.",
                    when=m[-1][0], metrics={"gapBp": round(diffs[-1] * 1e4, 1), "z": round(z, 2)},
                    trigger={"observed": round(abs(z), 2), "threshold": k, "window": f"{window} sessions", "unit": "robust z"},
                    evidence=[{"label": "Tracker A history", "url": url_a}, {"label": "Tracker B history", "url": url_b}],
                    limits=["ETF closing prices, not spot metal.", NOT_ARB], derived_only=derived_only)], prb
    return [], prb


def cross_venue_spread(category, items, usd_per_eur, fx_date, *, min_usd=5.0, flag_pct=40.0, source="mtg"):
    """items: [{id,name,url,usd,eur}] where usd and eur are two venues' prices for the same item.
    Spread = (USD venue − EUR venue converted at the ECB fix) / midpoint. Evidence only; severity capped at MEDIUM."""
    out, prb = [], []
    for it in items:
        a, e = it.get("usd"), it.get("eur")
        if a is None or e is None or min(a, e * usd_per_eur) < min_usd:
            prb.append(probe(it["name"], "CROSS_VENUE_SPREAD", None, "one venue has no price, or price below the noise floor"))
            continue
        eu = e * usd_per_eur
        sp = (a - eu) / ((a + eu) / 2) * 100
        prb.append(probe(it["name"], "CROSS_VENUE_SPREAD", abs(sp) / flag_pct))
        if abs(sp) >= flag_pct:
            out.append(sig(source=source, category=category, asset=it["name"], name=it["name"], typ="CROSS_VENUE_SPREAD",
                           severity=cap(sev_for(abs(sp), flag_pct, 70, 100), "MEDIUM"), derived_only=True,
                           title=f"{it['name']}: US-venue price sits {abs(sp):.0f}% {'above' if sp > 0 else 'below'} the EU venue after FX",
                           what=f"Venue gap {sp:+.0f}% of midpoint, converting at the ECB EUR/USD reference rate of {fx_date}.",
                           when=it.get("ts") or 0, metrics={"spreadPct": round(sp, 1), "fxDate": fx_date},
                           trigger={"observed": round(abs(sp), 1), "threshold": flag_pct, "window": "single snapshot", "unit": "% of midpoint"},
                           evidence=[{"label": "Item page (venue prices and links)", "url": it.get("url")}],
                           limits=[NOT_ARB, "Vendor prices are shown only as a derived percentage; follow the link for the source."]))
    return out, prb


def steam_ask_gap(items, *, min_volume=5, flag_pct=15.0):
    """CS2 lowest ask vs 24h median sale. Undocumented endpoint -> derived only; severity capped at LOW."""
    out, prb = [], []
    for it in items:
        if not it.get("median") or not it.get("lowest") or it.get("volume24h", 0) < min_volume:
            prb.append(probe(it["name"], "ASK_VS_MEDIAN_SALE", None, f"thin market ({it.get('volume24h', 0)} sales in 24h, need {min_volume})"))
            continue
        g = (it["lowest"] / it["median"] - 1) * 100
        prb.append(probe(it["name"], "ASK_VS_MEDIAN_SALE", abs(g) / flag_pct))
        if abs(g) >= flag_pct:
            out.append(sig(source="cs2", category="skins", asset=it["name"], name=it["name"], typ="ASK_VS_MEDIAN_SALE", severity="LOW", derived_only=True,
                           title=f"{it['name']}: lowest ask is {abs(g):.0f}% {'above' if g > 0 else 'below'} the 24h median sale",
                           what=f"{it['volume24h']} sales in 24h. A wide ask-vs-sale gap means the order book moved away from recent prints.",
                           when=it.get("ts") or 0, metrics={"gapPct": round(g, 1), "volume24h": it["volume24h"]},
                           trigger={"observed": round(abs(g), 1), "threshold": flag_pct, "window": "24h", "unit": "%"},
                           evidence=[{"label": "Steam Community Market listing", "url": it.get("url")}],
                           limits=["Undocumented Steam endpoint, not covered by the Steam Web API terms: derived signal only, roadmap item."]))
    return out, prb


def cot_shift(market, name, rows, url, *, k=3.0):
    """Weekly change in speculators' net position (% of open interest) vs its own 52-week history."""
    if len(rows) < 30:
        return [], [probe(name, "COT_POSITIONING_SHIFT", None, f"only {len(rows)} weekly reports")]
    net = [(r["long"] - r["short"]) / r["oi"] * 100 for r in rows if r["oi"]]
    ch = [b - a for a, b in zip(net, net[1:])]
    z, med, _ = robust(ch[-53:-1], ch[-1])
    prb = [probe(name, "COT_POSITIONING_SHIFT", None if z is None else abs(z) / k)]
    if z is not None and abs(z) >= k:
        return [sig(source="cot", category="positioning", asset=name, name=name, typ="COT_POSITIONING_SHIFT", severity=sev_for(abs(z), k, 4, 5.5),
                    title=f"{name}: speculators' net position moved {ch[-1]:+.1f} pts of open interest in the week to {_date(rows[-1]['ts'])}",
                    what=f"Non-commercial net position now {net[-1]:+.1f}% of open interest; the weekly change is {abs(z):.1f} robust z vs 52 weeks.",
                    when=rows[-1]["ts"], metrics={"netPctOI": round(net[-1], 2), "weeklyChangePts": round(ch[-1], 2), "z": round(z, 2)},
                    trigger={"observed": round(abs(z), 2), "threshold": k, "window": "52 weekly reports", "unit": "robust z"},
                    evidence=[{"label": "CFTC Commitments of Traders", "url": url}],
                    limits=["Positions as of Tuesday, published Friday. Aggregate categories, no individual traders."])], prb
    return [], prb


# ---------------- thin markets: collectibles ----------------
def sparse_gate(asset, sales, min_n=5, typ="THIN_MARKET"):
    if len(sales) < min_n:
        last = max((s["ts"] for s in sales), default=None)
        why = f"insufficient sales ({len(sales)} of {min_n})" + (f"; last sale {_date(last)}" if last else "; no sales in window")
        return probe(asset, typ, None, why)
    return None


def snapshot_move(category, source, asset, name, snaps, url, *, need=14, flag_pct=25.0):
    """Daily snapshots of a vendor guide price we took ourselves. History starts on day 1 of snapshotting."""
    if len(snaps) < need:
        return [], [probe(asset, "GUIDE_MOVE_VS_30D_MEDIAN", None, f"insufficient snapshot history (day {len(snaps)} of {need})")]
    base = statistics.median(v for _, v in snaps[-31:-1])
    mv = (snaps[-1][1] / base - 1) * 100 if base else 0
    prb = [probe(asset, "GUIDE_MOVE_VS_30D_MEDIAN", abs(mv) / flag_pct)]
    if abs(mv) >= flag_pct:
        return [sig(source=source, category=category, asset=asset, name=name, typ="GUIDE_MOVE_VS_30D_MEDIAN", severity=cap(sev_for(abs(mv), flag_pct, 50, 100), "MEDIUM"),
                    title=f"{name}: guide price {'up' if mv > 0 else 'down'} {abs(mv):.0f}% vs its 30-day median", what="Derived from our own daily snapshots of the vendor guide.",
                    when=snaps[-1][0], metrics={"movePct": round(mv, 1), "snapshots": len(snaps)}, derived_only=True,
                    trigger={"observed": round(abs(mv), 1), "threshold": flag_pct, "window": "30 daily snapshots", "unit": "%"},
                    evidence=[{"label": "Item page", "url": url}], limits=["Guide prices lag sales; low-liquidity item."])], prb
    return [], prb


def _by_grade(sales):
    g = defaultdict(list)
    for s in sales:
        g[s.get("grade", "ungraded")].append(s)
    return g


def outlier_sale(category, source, asset, name, sales, url, *, k=3.5, min_n=6, synthetic=False):
    """Hampel filter per grade: newest sale vs median ± k·MAD of the others in its grade. One outlier stays LOW;
    two or more in the last 7 days in the same direction can reach MEDIUM."""
    out, prb = [], []
    for grade, ss in _by_grade(sales).items():
        ss = sorted(ss, key=lambda s: s["ts"])
        g = sparse_gate(f"{asset}/{grade}", ss, min_n, "OUTLIER_SALE")
        if g:
            prb.append(g); continue
        hist = [s["price"] for s in ss[:-1]]
        med = statistics.median(hist); mad = 1.4826 * statistics.median(abs(x - med) for x in hist) or med * 0.05
        z = (ss[-1]["price"] - med) / mad
        prb.append(probe(f"{asset}/{grade}", "OUTLIER_SALE", abs(z) / k))
        if abs(z) >= k:
            recent = [s for s in ss if s["ts"] >= ss[-1]["ts"] - 7 * 86400 and abs(s["price"] - med) / mad >= k and (s["price"] > med) == (z > 0)]
            out.append(sig(source=source, category=category, asset=asset, name=name, typ="OUTLIER_SALE", severity="MEDIUM" if len(recent) >= 2 else "LOW",
                           title=f"{name} ({grade}): latest sale {abs(ss[-1]['price'] / med - 1) * 100:.0f}% {'above' if z > 0 else 'below'} the grade median",
                           what=f"{len(recent)} outlier sale(s) in 7 days; Hampel z {z:.1f} against {len(hist)} prior sales in the same grade.",
                           when=ss[-1]["ts"], metrics={"z": round(z, 2), "repeats7d": len(recent), "grade": grade, "sales": len(ss)},
                           trigger={"observed": round(abs(z), 2), "threshold": k, "window": f"{len(hist)} sales, same grade", "unit": "Hampel z"},
                           evidence=[{"label": "Item page", "url": url}], limits=["Single sales are noisy in thin markets."], synthetic=synthetic, derived_only=True))
    return out, prb


def grade_mix(category, source, asset, name, prev, cur, url, *, move_pct=20.0, within_pct=8.0, synthetic=False):
    """Overall median moved but like-for-like grades did not: report a MIX SHIFT, not a price move."""
    def med(xs): return statistics.median(x["price"] for x in xs) if xs else None
    if len(prev) < 5 or len(cur) < 5:
        return [], [probe(asset, "GRADE_MIX_SHIFT", None, "insufficient sales in one of the windows")]
    om = (med(cur) / med(prev) - 1) * 100
    gp, gc = _by_grade(prev), _by_grade(cur)
    within = [(med(gc[g]) / med(gp[g]) - 1) * 100 for g in gc if g in gp and len(gp[g]) >= 2 and len(gc[g]) >= 2]
    if not within:
        return [], [probe(asset, "GRADE_MIX_SHIFT", None, "no grade has sales in both windows")]
    wm = statistics.median(within)
    prb = [probe(asset, "GRADE_MIX_SHIFT", abs(om) / move_pct)]
    if abs(om) >= move_pct and abs(wm) < within_pct:
        mix = {g: len(v) for g, v in gc.items()}
        return [sig(source=source, category=category, asset=asset, name=name, typ="GRADE_MIX_SHIFT", severity="INFO", synthetic=synthetic, derived_only=True,
                    title=f"{name}: median sale {'up' if om > 0 else 'down'} {abs(om):.0f}%, but within-grade prices moved only {wm:+.0f}%",
                    what="The headline move comes from which grades sold, not from prices changing. This is a mix shift.",
                    when=max(x["ts"] for x in cur), metrics={"overallPct": round(om, 1), "withinGradePct": round(wm, 1), "gradeCounts": mix},
                    trigger={"observed": round(abs(om), 1), "threshold": move_pct, "window": "two equal windows", "unit": "%"},
                    evidence=[{"label": "Item page", "url": url}])], prb
    return [], prb


def wash_pattern(category, source, asset, name, sales, url, *, window_days=14, repeats=3, synthetic=False):
    """Repeated identical prices or A-B-A-B round trips in a short window. Pattern only, capped at MEDIUM."""
    if not sales:
        return [], [probe(asset, "ROUND_TRIP_PATTERN", None, "no sales in window")]
    end = max(s["ts"] for s in sales)
    w = sorted([s for s in sales if s["ts"] >= end - window_days * 86400], key=lambda s: s["ts"])
    g = sparse_gate(asset, w, 4, "ROUND_TRIP_PATTERN")
    if g:
        return [], [g]
    cnt = defaultdict(int)
    for s in w:
        cnt[round(s["price"], 2)] += 1
    top_p, top_n = max(cnt.items(), key=lambda x: x[1])
    ps = [round(s["price"], 2) for s in w]
    abab = sum(1 for i in range(3, len(ps)) if ps[i] == ps[i - 2] and ps[i - 1] == ps[i - 3] and ps[i] != ps[i - 1])
    score = max(top_n / repeats, abab / 2)
    prb = [probe(asset, "ROUND_TRIP_PATTERN", score)]
    if top_n >= repeats or abab >= 2:
        return [sig(source=source, category=category, asset=asset, name=name, typ="ROUND_TRIP_PATTERN", basis="heuristic", synthetic=synthetic, derived_only=True,
                    severity=cap("MEDIUM" if (top_n >= repeats + 2 or abab >= 3) else "LOW", "MEDIUM"),
                    title=f"{name}: {top_n} sales at the identical price in {window_days} days" + (f", {abab} A-B-A-B round trips" if abab else ""),
                    what="Repeated identical or alternating prices are a known wash-trading signature, and also happen with fixed-price listings.",
                    when=end, metrics={"identicalPriceCount": top_n, "roundTrips": abab, "sales": len(w)},
                    trigger={"observed": round(score, 2), "threshold": 1, "window": f"{window_days} days", "unit": "pattern score"},
                    evidence=[{"label": "Item page", "url": url}], limits=[PATTERN_LIMIT])], prb
    return [], prb


def supply_shock(category, source, asset, name, counts, url, *, ratio=2.0, min_add=10, synthetic=False):
    """counts: [(ts, active listings or population count)] daily. Today vs the prior 30-day median."""
    if len(counts) < 8:
        return [], [probe(asset, "SUPPLY_SHOCK", None, f"insufficient count history ({len(counts)} days)")]
    base = statistics.median(c for _, c in counts[-31:-1]); now = counts[-1][1]
    r = now / base if base else float("inf")
    prb = [probe(asset, "SUPPLY_SHOCK", (r / ratio) if base else None, None if base else "zero baseline")]
    if base and r >= ratio and now - base >= min_add:
        return [sig(source=source, category=category, asset=asset, name=name, typ="SUPPLY_SHOCK", synthetic=synthetic, derived_only=True,
                    severity=cap(sev_for(r, ratio, 3, 5), "MEDIUM"), title=f"{name}: supply count {r:.1f}× its 30-day median ({int(base)} → {int(now)})",
                    what="A jump in listings or graded population usually precedes price pressure; it is not a price move itself.",
                    when=counts[-1][0], metrics={"ratio": round(r, 2), "baseline": base, "now": now},
                    trigger={"observed": round(r, 2), "threshold": ratio, "window": "30 days", "unit": "× median"},
                    evidence=[{"label": "Item page", "url": url}])], prb
    return [], prb


def guide_divergence(category, source, asset, name, guide, sales, url, *, flag_pct=25.0, min_n=5, synthetic=False):
    g = sparse_gate(asset, sales, min_n, "GUIDE_VS_SALES")
    if g:
        return [], [g]
    m = statistics.median(s["price"] for s in sales[-min_n * 2:])
    d = (m / guide - 1) * 100
    prb = [probe(asset, "GUIDE_VS_SALES", abs(d) / flag_pct)]
    if abs(d) >= flag_pct:
        return [sig(source=source, category=category, asset=asset, name=name, typ="GUIDE_VS_SALES", synthetic=synthetic, derived_only=True,
                    severity=cap(sev_for(abs(d), flag_pct, 50, 100), "MEDIUM"),
                    title=f"{name}: recent sales run {abs(d):.0f}% {'above' if d > 0 else 'below'} the price guide",
                    what="Price guides update slowly; a persistent gap means the guide is lagging actual sales.", when=sales[-1]["ts"],
                    metrics={"gapPct": round(d, 1), "salesUsed": min(len(sales), min_n * 2)},
                    trigger={"observed": round(abs(d), 1), "threshold": flag_pct, "window": f"last {min_n * 2} sales", "unit": "%"},
                    evidence=[{"label": "Item page", "url": url}], limits=["Not an appraisal."])], prb
    return [], prb
