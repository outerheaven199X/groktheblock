#!/usr/bin/env python3
"""Small real-history replay (labelled honestly): Treasury par curve (treasury.gov, daily) and one Polymarket market's
CLOB 15-minute price history. Rolls the detectors forward one observation at a time using only data available at
that point, runs the incident lifecycle, and reports alert volume and calendar overlap. It measures noise and
plumbing, NOT predictive value: there are no labelled outcomes, so no hit rate or lead time is computed."""
import json, sys
from collections import Counter
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from grok_the_block.markets import sources as S, detectors as X, lifecycle as LC, events as EV, timebase as T

cal = EV.load()
out = {"label": "REAL-HISTORY REPLAY (public data, no outcome labels; not a hit-rate or lead-time measurement)"}
c = S.treasury_curve()
rows = c["rows"]
st = {"incidents": {}, "lastSuccessAt": 1}
types, sev, tagged, alerts, reasons, days_with = Counter(), Counter(), 0, 0, Counter(), 0
for i in range(61, len(rows) + 1):
    X.reset()
    d = rows[i - 1][0]
    at = T.ny_ts(date.fromisoformat(d), 18)
    ob = {"ingestTs": at, "status": "HEALTHY", "coverage": {}, "limitations": []}
    sigs = X.treasury_signals(rows[:i], c["url"], ob)
    for s in sigs:
        types[s["type"]] += 1; sev[s["severity"]] += 1
        if EV.events_near(s["observation"].get("eventTs") or at, {"rates"}, cal):
            tagged += 1
    days_with += bool(sigs)
    r = LC.step(st, sigs, dict(X.PROBES), {"treasury": "HEALTHY"}, at)
    alerts += len(r["alerts"]); reasons.update(a["alertReason"] for a in r["alerts"])
out["treasury"] = {"source": c["via"], "sessions": len(rows) - 60, "from": rows[60][0], "to": rows[-1][0], "signals": sum(types.values()),
                   "sessionsWithSignal": days_with, "byType": dict(types), "bySeverity": dict(sev), "calendarTagged": tagged,
                   "lifecycleAlerts": alerts, "alertsByReason": dict(reasons),
                   "incidents": len(st["incidents"]), "episodes": sum(i["episode"] for i in st["incidents"].values())}
# Polymarket: the highest-volume open non-sports market with CLOB history
pm = S.polymarket_markets(60) or []
m = next((m for m in pm if m.get("category") != "sports" and m.get("tokenIds")), None)
if m:
    h = S.polymarket_history(m["tokenIds"][0], "1m", 15) or []
    st = {"incidents": {}, "lastSuccessAt": 1}
    n_sig, alerts, reasons = 0, 0, Counter()
    for j in range(24, len(h)):
        X.reset()
        at = h[j][0]
        hist = h[: j + 1]
        mm = dict(m, price=hist[-1][1], change1h=hist[-1][1] - hist[-5][1], vol24=max(m.get("vol24") or 0, 25_000))
        ob = {"ingestTs": at, "status": "HEALTHY", "coverage": {}, "limitations": []}
        s = X.pm_odds_jump(mm, ob, hist[-96:])
        sigs = [s] if s else []
        n_sig += len(sigs)
        r = LC.step(st, sigs, dict(X.PROBES), {"polymarket": "HEALTHY"}, at)
        alerts += len(r["alerts"]); reasons.update(a["alertReason"] for a in r["alerts"])
    out["polymarket"] = {"market": m["title"], "url": m["url"], "points": len(h), "from": T.iso(h[0][0]) if h else None, "to": T.iso(h[-1][0]) if h else None,
                         "observationsWithSignal": n_sig, "lifecycleAlerts": alerts, "alertsByReason": dict(reasons),
                         "note": "24h volume is not point-in-time in Gamma, so the current value is used as a floor (look-ahead on volume only)."}
print(json.dumps(out, indent=1))
