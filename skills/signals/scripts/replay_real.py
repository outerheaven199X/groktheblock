#!/usr/bin/env python3
"""Point-in-time evaluation (RE-AUDIT §04) driven by the frozen config docs/review/eval-config.json.

Three tracks, kept separate in docs/review/eval-results.json:
- synthetic: the deterministic fixtures in tests/fixtures/replay (plumbing and noise control only)
- unlabelledHistorical: real public history (treasury.gov curve, one Polymarket CLOB history) rolled forward one
  observation at a time; alert volume and lifecycle behaviour only
- labelled: Treasury sessions labelled by scheduled official release days (FOMC/CPI/NFP). This measures whether
  flags cluster on days with known public news, against a fixed 10bp baseline, with a development/holdout split.
  It is NOT a hit rate for informed trading and no lead time is computed.
Polymarket 24h volume is not available point-in-time, so it is passed as vol24=None with vol24AsOf=fetch time;
the detector then refuses volume-gated findings (REPLAY-01)."""
import json, sys, time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
from grok_the_block.markets import sources as S, detectors as X, lifecycle as LC, events as EV, timebase as T, replay as RP

CFG = json.loads((ROOT / "docs/review/eval-config.json").read_text())
cal = EV.load()
fetched = int(time.time())
out = {"configVersion": CFG["version"], "generatedAt": T.iso(fetched), "noHitRateOrLeadTime": True}

# ---- synthetic
out["synthetic"] = {"label": "SYNTHETIC fixtures; not market data", "fixtures": RP.run_all()}

# ---- unlabelled historical: Treasury
c = S.treasury_curve()
L = CFG["history"]["treasuryLookbackSessions"]
rows = c["rows"] if c else []
label_days = {datetime.fromtimestamp(e["ts"], T.NY).date().isoformat() for e in cal.get("events", []) if e["type"] in ("FOMC", "CPI", "NFP")}
st = {"incidents": {}, "lastSuccessAt": 1}
types, sev, phases, alerts, reasons = Counter(), Counter(), Counter(), 0, Counter()
per_day = []
for i in range(L + 1, len(rows) + 1):
    X.reset()
    d = rows[i - 1][0]
    at = T.ny_ts(date.fromisoformat(d), 18)
    ob = {"ingestTs": at, "status": "HEALTHY", "coverage": {}, "limitations": []}
    sigs = [s for s in X.treasury_signals(rows[:i], c["url"], ob) if s["basis"] != "unverified"]
    for s in sigs:
        types[s["type"]] += 1; sev[s["severity"]] += 1
        for e in EV.events_near(s["when"], {"rates"}, cal, granularity="daily", instrument=s.get("instrument")):
            phases[e["phase"]] += 1
    prev = rows[i - 2][1]
    base = any(abs((rows[i - 1][1].get(t) or 0) - (prev.get(t) or 0)) >= 0.10 for t in ("2Y", "10Y", "30Y") if rows[i - 1][1].get(t) and prev.get(t))
    per_day.append({"date": d, "flag": bool(sigs), "baseline": base, "label": d in label_days})
    r = LC.step(st, sigs, dict(X.PROBES), {"treasury": "HEALTHY"}, at)
    alerts += len(r["alerts"]); reasons.update(a["alertReason"] for a in r["alerts"])
uh = {"treasury": {"source": c["via"] if c else None, "url": c["url"] if c else None, "sessions": len(per_day),
                   "from": per_day[0]["date"] if per_day else None, "to": per_day[-1]["date"] if per_day else None,
                   "signals": sum(types.values()), "sessionsWithSignal": sum(p["flag"] for p in per_day), "byType": dict(types), "bySeverity": dict(sev),
                   "calendarPhases": dict(phases), "lifecycleAlerts": alerts, "alertsByReason": dict(reasons), "incidents": len(st["incidents"])}}

# ---- unlabelled historical: Polymarket (no point-in-time volume)
pm = S.polymarket_markets(60) or []
m = next((m for m in pm if m.get("category") != "sports" and m.get("tokenIds")), None)
if m:
    h = S.polymarket_history(m["tokenIds"][0], CFG["history"]["polymarketInterval"], CFG["history"]["polymarketFidelityMin"]) or []
    st = {"incidents": {}, "lastSuccessAt": 1}
    moved, findings, alerts = 0, 0, 0
    for j in range(24, len(h)):
        X.reset()
        at, hist = h[j][0], h[: j + 1]
        mm = dict(m, price=hist[-1][1], change1h=hist[-1][1] - hist[-5][1], vol24=None, vol24AsOf=fetched)
        s = X.pm_odds_jump(mm, {"ingestTs": at, "status": "HEALTHY", "coverage": {}, "limitations": []}, hist[-CFG["history"]["polymarketWindowPoints"]:])
        if s:
            moved += 1; findings += s["basis"] != "unverified"
        r = LC.step(st, [s] if s else [], dict(X.PROBES), {"polymarket": "HEALTHY"}, at)
        alerts += len(r["alerts"])
    uh["polymarket"] = {"market": m["title"], "url": m["url"], "points": len(h), "from": T.iso(h[0][0]) if h else None, "to": T.iso(h[-1][0]) if h else None,
                        "priceMovesPastThreshold": moved, "eligibleFindings": findings, "lifecycleAlerts": alerts,
                        "note": "Volume is not point-in-time, so every price move is reported as UNVERIFIED and none is eligible as a finding. This is the intended REPLAY-01 behaviour, not a quiet market."}
out["unlabelledHistorical"] = dict(uh, label="REAL public history, no outcome labels: alert volume and lifecycle behaviour only")


# ---- labelled (scheduled-release days)
def rates(ps, key):
    lab = [p for p in ps if p["label"]]; un = [p for p in ps if not p["label"]]
    f = lambda xs: (sum(p[key] for p in xs), len(xs))  # noqa: E731
    (a, n1), (b, n0) = f(lab), f(un)
    return {"flaggedOnLabelDays": a, "labelDays": n1, "flaggedOnOtherDays": b, "otherDays": n0,
            "shareOfLabelDaysFlagged": round(a / n1, 3) if n1 else None, "shareOfOtherDaysFlagged": round(b / n0, 3) if n0 else None}


half = len(per_day) // 2
out["labelled"] = {"label": "Treasury sessions labelled by scheduled official release days. Association with known public news only; not informed-trading ground truth; no hit rate or lead time.",
                   "labelSource": "data/event-calendar.json (FOMC, CPI, NFP)", "labelCaveat": "BLS entries were fetched with a placeholder contact and should be rebuilt (see the calendar provenance).",
                   "development": {"detector": rates(per_day[:half], "flag"), "baseline10bp": rates(per_day[:half], "baseline")},
                   "holdout": {"detector": rates(per_day[half:], "flag"), "baseline10bp": rates(per_day[half:], "baseline")}}
(ROOT / "docs/review/eval-results.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps({k: v for k, v in out.items() if k != "synthetic"}, indent=1, default=str))
