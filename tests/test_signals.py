"""Fixture and regression tests for the v2 signal detectors, lifecycle and adapter (synthetic data, clearly not live)."""
import copy, json, sys, tempfile
from datetime import date
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib"))
from grok_the_block.markets import detectors as X, feed as F, lifecycle as LC, timebase as T, events as EV, entities as EN, sources as S

NOW = 1_800_000_000
FX = json.loads((R / "tests/fixtures/signals-fixtures.json").read_text())
ok = 0
def check(c, msg):
    global ok
    assert c, msg
    ok += 1
def ob(now=NOW, st="HEALTHY"):
    return {"ingestTs": now, "status": st, "coverage": {"universe": "fixture", "observed": 1}, "limitations": []}
def shape(s):
    for k in ("key", "source", "family", "type", "severity", "basis", "title", "what", "when", "subject", "evidence", "limits", "observation", "trigger", "entities"):
        check(k in s, f"signal missing {k}")
    for k in ("eventTime", "availableTime", "ingestTime", "validAsOf", "sourceStatus", "coverage", "limitations"):
        check(k in s["observation"], f"observation missing {k}")
    o = s["observation"]
    check(o.get("availableTs") is None or o["availableTs"] <= o["ingestTs"], "available never after ingest")
    check(s["observation"]["sourceStatus"] in ("HEALTHY", "DEGRADED", "STALE", "UNAVAILABLE", "NOT_CONFIGURED"), "status enum")
    check(s["basis"] in X.BASES, "basis")
    check(s["evidence"] and all(e["url"].startswith("https://") for e in s["evidence"] if e.get("url")), "evidence links")
    t = (s["title"] + s["what"]).lower()
    check(not any(w in t for w in ("buy now", "sell now", "you should", "insider trading", "probability of", "% likely")), "no advice / accusation / probability language")
    check(not any(p.isdigit() and len(p) == 8 for p in s["key"].split(":")), f"no date in key {s['key']}")

pm = FX["polymarket"]
# --- Polymarket repricing, settling downgrade, sports
X.reset(); s = X.pm_odds_jump(pm["jump"], ob()); shape(s)
check(s["type"] == "ODDS_REPRICING" and s["basis"] == "observed" and s["trigger"]["threshold"] == 0.12, s["trigger"])
check(s["severity"] == "MEDIUM" and "No CLOB" in " ".join(s["limits"]), "no history → capped MEDIUM, limited")
hist = [(NOW - 900 * i, 0.40 + 0.001 * (i % 3)) for i in range(40, 0, -1)] + [(NOW, 0.62)]
s = X.pm_odds_jump(pm["jump"], ob(), hist); check(s["severity"] == "HIGH" and s["trigger"]["window"] == "15m", s["trigger"])
check(X.pm_odds_jump(dict(pm["jump"], price=0.985), ob())["severity"] == "LOW", "settlement extreme downgraded")
check(X.pm_odds_jump(dict(pm["jump"], category="sports"), ob()) is None, "sports skipped")
check(X.pm_odds_jump(pm["quiet"], ob()) is None, "quiet market: no signal")

# --- P0 zero baseline → insufficient baseline (UNVERIFIED), never infinite
z = X.pm_volume_spike(dict(pm["spike"], vol1wk=pm["spike"]["vol24"]), ob()); shape(z)
check(z["basis"] == "unverified" and z["severity"] == "INFO" and z["metrics"]["ratio"] is None and "Insufficient" in z["title"], z["metrics"])
z = X.pm_volume_spike(dict(pm["spike"], startTs=NOW - 3600), ob()); check(z["basis"] == "unverified", "new market → insufficient baseline")
s = X.pm_volume_spike(pm["spike"], ob()); check(s["basis"] == "heuristic" and s["metrics"]["ratio"] == 20.0, s["metrics"])
k = X.kalshi_shock(dict(FX["kalshi"]["shock"], volume=FX["kalshi"]["shock"]["vol24"], openTs=NOW - 30 * 86400), ob())
check(any(x["basis"] == "unverified" and x["metrics"]["ratio"] is None for x in k), "kalshi zero baseline")
check(all(x["metrics"].get("ratio") != float("inf") for x in k), "never infinite")

# --- Newly observed address wording
fs = {kk: NOW - v for kk, v in FX["firstSeenAgo"].items()}
s = X.pm_fresh_activity(pm["jump"], FX["trades"], fs, ob(), moved=True)
check(s["type"] == "NEWLY_OBSERVED_ADDRESS_ACTIVITY" and "newly observed on Polymarket" in (s["title"] + s["what"]) and "wallet" not in s["title"].lower(), s["title"])
check(len(s["metrics"]["distinctTx"]) >= 1, "distinct tx tracked")

# --- P0 options expiry: parse or reject; 0/1DTE routed to separate conservative detector
check(S._occ_expiry("NVDA261030C00180000") == "20261030" and S._occ_expiry("garbage") is None, "OCC parse")
snap = T.ny_ts(date(2026, 10, 28), 12)
def c(exp, vol, oi, price, typ="call"): return {"contract": f"X{exp}", "expiry": exp, "type": typ, "strike": 100, "volume": vol, "oi": oi, "price": price}
chain = {"rows": [c("20261028", 9000, 100, 2.0), c("20261029", 8000, 200, 2.0), c("20261120", 3000, 100, 5.0), c(None, 99999, 1, 50.0)],
         "rejected": 2, "snapshotTs": snap, "underlying": 100}
X.reset(); oa = {x["type"]: x for x in X.options_activity("NVDA", chain, "https://www.cboe.com/x", ob(snap + 1200))}
check(set(oa) == {"UNUSUAL_OPTIONS_VOLUME", "SHORT_DATED_OPTIONS"}, oa.keys())
check(oa["SHORT_DATED_OPTIONS"]["severity"] == "LOW" and oa["SHORT_DATED_OPTIONS"]["metrics"]["contracts"] == 2, "0/1DTE separate, capped LOW")
check(oa["UNUSUAL_OPTIONS_VOLUME"]["metrics"]["contracts"] == 1 and oa["UNUSUAL_OPTIONS_VOLUME"]["metrics"]["rejectedContracts"] == 3, "unparsed expiry rejected, counted")
check(all(t["expiry"] for x in oa.values() for t in x["metrics"]["top"]), "no contract without expiry")

# --- Equity robust z / realized-vol return, insufficient history
import math
rows = [(NOW - 86400 * (70 - i), 100 * (1 + 0.004 * ((-1) ** i)), 1e6 * (1 + 0.05 * (i % 5))) for i in range(70)]
rows[-1] = (rows[-1][0], rows[-2][1] * 1.06, 6e6)
X.reset(); ea = {x["type"]: x for x in X.daily_anomaly("equities", "NVDA", rows, "https://finance.yahoo.com/quote/NVDA", ob())}
check("RETURN_VS_REALIZED_VOL" in ea and "VOLUME_ROBUST_Z" in ea and ea["VOLUME_ROBUST_Z"]["basis"] == "observed", ea.keys())
check(ea["RETURN_VS_REALIZED_VOL"]["entities"] == ["nvidia"], ea["RETURN_VS_REALIZED_VOL"]["entities"])
short = X.daily_anomaly("equities", "NVDA", rows[-30:], "https://finance.yahoo.com/quote/NVDA", ob())
check(any(x["basis"] == "unverified" for x in short), "<40 sessions → unverified")

# --- Treasury: regime classification
def tr(d, y2, y10): return (d, {"2Y": y2, "10Y": y10, "30Y": y10 + 0.3})
trows = [tr(f"2026-07-{i:02d}" if i < 32 else f"2026-08-{i - 31:02d}", 4.0 + 0.002 * (i % 2), 4.3 + 0.002 * (i % 3)) for i in range(1, 70)]
trows.append(("2026-10-27", {"2Y": 3.85, "10Y": 4.31, "30Y": 4.6}))
ts = {x["type"]: x for x in X.treasury_signals(trows, "https://home.treasury.gov/x", ob())}
check("YIELD_MOVE" in ts and "CURVE_SHIFT" in ts and ts["CURVE_SHIFT"]["metrics"]["regime"] == "bull steepening", {k: v["metrics"].get("regime") for k, v in ts.items()})

# --- Stablecoins: SUPPLY_CHANGE floors
U = "https://defillama.com/stablecoin/x"
sc = X.stablecoin_supply([{"symbol": "USDT", "name": "Tether", "now": 150e9, "d1": 148.8e9, "w1": 148e9, "chains": [], "url": U},
                          {"symbol": "SMALL", "name": "Small", "now": 100.2e9, "d1": 100e9, "w1": 100e9, "chains": [], "url": U},
                          {"symbol": "TINY", "name": "Tiny", "now": 2.1e9, "d1": 2e9, "w1": 2e9, "chains": [], "url": U}], ob())
check([x["type"] for x in sc] == ["SUPPLY_CHANGE"] and sc[0]["severity"] == "HIGH" and "bridg" in " ".join(sc[0]["limits"]).lower(), [(x["subject"]["id"], x["severity"]) for x in sc])

# --- Convergence: entity-only, family-deduped, generic tags never converge, ranking not probability
INST = {"treasury": "treasury:2Y", "equities": "equities:TLT"}
def fake(src, ent, when, sev="MEDIUM", typ="T", cal=(), inst=None, gran="intraday", title=None):
    return {"key": f"{src}:{ent}{when}:{typ}", "source": src, "family": EN.family_of(src, inst or INST.get(src)), "type": typ, "severity": sev, "basis": "observed",
            "instrument": inst or INST.get(src), "relations": {},
            "title": title or f"{src} {ent}", "what": "", "when": when, "subject": {"name": ent, "id": ent, "url": "https://example.org"},
            "evidence": [{"label": "e", "url": "https://example.org"}], "limits": [], "metrics": {}, "entities": [ent] if ent else [],
            "calendar": list(cal), "observation": {"eventTs": when, "granularity": gran, "temporalStatus": "OK", "fastEligible": gran in ("intraday", "delayed"), "sourceStatus": "HEALTHY"}}
cv = X.convergence([fake("polymarket", "fed-policy", NOW - 3600), fake("kalshi", "fed-policy", NOW - 3000)], NOW)
check(cv == [], "prediction + prediction = one family → no convergence (arbitrage pair)")
check(X.same_family_repricing([fake("polymarket", "fed-policy", NOW - 3600), fake("kalshi", "fed-policy", NOW - 3000)], NOW)[0]["severity"] == "INFO", "related repricing")
cv = X.convergence([fake("polymarket", "fed-policy", NOW - 3600), fake("kalshi", "fed-policy", NOW - 3000), fake("treasury", "fed-policy", NOW - 1800)], NOW)
check(len(cv) == 1 and cv[0]["metrics"]["effectiveObservations"] == 2 and cv[0]["metrics"]["mode"] == "fast", cv and cv[0]["metrics"])
check("uncalibrated" in cv[0]["metrics"]["rankNote"] and "%" not in cv[0]["title"], "ranking wording")
cv2 = X.convergence([fake("polymarket", "fed-policy", NOW - 40 * 3600), fake("treasury", "fed-policy", NOW - 1800)], NOW)
check(cv2[0]["metrics"]["mode"] == "forensic" and cv2[0]["severity"] == "LOW" and "early warning" not in cv2[0]["what"].lower().replace("not an early warning", ""), "forensic")
cal = [{"type": "FOMC", "label": "FOMC", "eventId": "FOMC-x", "phase": "RELEASE_REACTION", "availableAtObservation": True}]
cv3 = X.convergence([fake("polymarket", "fed-policy", NOW - 3600, cal=cal), fake("treasury", "fed-policy", NOW - 1800, cal=cal)], NOW)
check(cv3[0]["severity"] == "LOW" and cv3[0]["metrics"]["calendarExplained"], "calendar-explained capped")
check(EN.resolve("polymarket", None, "Will the economy beat expectations?") == [] and "nvidia" in EN.resolve("polymarket", None, "Will NVIDIA close above $200?"),
      "keyword-only generic text never maps")
check("tesla" in EN.resolve("polymarket", None, "Tesla deliveries") and EN.resolve("polymarket", None, "Will Musk tweet 500 times?") == [], "musk ≠ tesla")

# --- Calendar
cal = {"events": [{"type": "CPI", "label": "CPI Oct", "ts": NOW + 3600}, {"type": "AUCTION", "label": "10Y auction", "ts": NOW + 3600}]}
tags = EV.events_near(NOW, {"equity"}, cal)
check([t["type"] for t in tags] == ["CPI"], tags)
check(EV.third_friday(2026, 11) == date(2026, 11, 20), "opex")

# --- Freshness: weekend/holiday aware
sat = T.ny_ts(date(2026, 10, 31), 12)
check(T.freshness("equities", T.ny_ts(date(2026, 10, 30), 16), sat)[0] == "HEALTHY", "Friday bar fresh on Saturday")
check(T.freshness("equities", T.ny_ts(date(2026, 10, 28), 16), sat)[0] == "STALE", "Wednesday bar stale on Saturday")
check(T.freshness("treasury", T.ny_ts(date(2026, 11, 10), 15), T.ny_ts(date(2026, 11, 11), 20))[0] == "HEALTHY", "Veterans Day: no bond session")
check(T.freshness("polymarket", None, NOW)[0] == "UNAVAILABLE", "no timestamp → unavailable")

# --- P0 stable identity across UTC midnight
X.reset(); a = X.pm_odds_jump(pm["jump"], ob(T.ny_ts(date(2026, 10, 28), 19, 55)))
b = X.pm_odds_jump(pm["jump"], ob(T.ny_ts(date(2026, 10, 28), 20, 5)))
check(a["key"] == b["key"] == "polymarket:0xfixture1:ODDS_REPRICING", (a["key"], b["key"]))

# --- P0 lifecycle: NEW → ACTIVE → COOLING → RESOLVED; hysteresis; re-alerts; reminders; outage retention; telemetry
def sig(sev="HIGH", tx=(), src="polymarket"):
    s = copy.deepcopy(a); s["severity"] = sev; s["source"] = src; s["metrics"] = dict(s["metrics"], distinctTx=list(tx)); return s
K = a["key"]; HEALTH = {"polymarket": "HEALTHY"}
st = {"incidents": {}, "lastSuccessAt": None}
r = LC.step(st, [sig()], {K: 1.2}, HEALTH, NOW)
check(r["baseline"] and r["alerts"] == [] and st["incidents"][K]["state"] == "NEW", "baseline run")
st = {"incidents": {}, "lastSuccessAt": NOW - 600}
r = LC.step(st, [sig()], {K: 1.2}, HEALTH, NOW); check(r["alerts"][0]["alertReason"] == "NEW" and r["alerts"][0]["incidentId"] == K + "#e1", r["alerts"])
r = LC.step(st, [sig()], {K: 1.3}, HEALTH, NOW + 600); check(r["alerts"] == [] and r["telemetry"]["suppressedUnchanged"] == 1 and st["incidents"][K]["state"] == "ACTIVE", "unchanged suppressed")
r = LC.step(st, [sig()], {K: 1.6}, HEALTH, NOW + 1200); check(r["alerts"][0]["alertReason"] == "MAGNITUDE_RISE", "≥25% rise re-alerts")
r = LC.step(st, [sig(tx=["0xabc"])], {K: 1.6}, HEALTH, NOW + 1800); check(r["alerts"][0]["alertReason"] == "NEW_TRANSACTION", "new distinct tx")
r = LC.step(st, [sig("CRITICAL", ["0xabc"])], {K: 1.6}, HEALTH, NOW + 2400); check(r["alerts"][0]["alertReason"] == "ESCALATED", "escalation")
r = LC.step(st, [sig("CRITICAL", ["0xabc"])], {K: 1.6}, HEALTH, NOW + 6 * 3600 + 1); check(r["alerts"][0]["alertReason"] == "REMINDER", "6h reminder")
r = LC.step(st, [sig("CRITICAL", ["0xabc"])], {K: 1.6}, HEALTH, NOW + 12 * 3600); check(r["alerts"] == [], "no second reminder within a day")
r = LC.step(st, [sig("CRITICAL", ["0xabc"])], {K: 1.6}, HEALTH, NOW + 30 * 3600 + 2); check(r["alerts"][0]["alertReason"] == "REMINDER", "daily reminder")
# outage: never resolves
for i in range(3):
    r = LC.step(st, [], {}, {"polymarket": "UNAVAILABLE"}, NOW + 31 * 3600 + i)
check(st["incidents"][K]["state"] == "ACTIVE" and r["telemetry"]["skippedUnavailable"] == 1, "outage keeps last confirmed state")
r = LC.step(st, [], {}, {}, NOW + 32 * 3600); check(st["incidents"][K]["state"] == "ACTIVE", "source not run → retained")
# hysteresis: 0.8 holds, below 0.75 twice resolves
LC.step(st, [], {K: 0.8}, HEALTH, NOW + 33 * 3600); check(st["incidents"][K]["state"] == "ACTIVE", "inside band holds")
LC.step(st, [], {K: 0.5}, HEALTH, NOW + 34 * 3600); check(st["incidents"][K]["state"] == "COOLING", "cooling")
LC.step(st, [], {K: 0.9}, HEALTH, NOW + 35 * 3600); LC.step(st, [], {K: 0.5}, HEALTH, NOW + 36 * 3600)
check(st["incidents"][K]["state"] == "COOLING", "count resets when it recovers")
r = LC.step(st, [], {K: 0.4}, HEALTH, NOW + 37 * 3600); check(st["incidents"][K]["state"] == "RESOLVED" and r["telemetry"]["resolved"] == 1, "resolved after 2")
r = LC.step(st, [sig()], {K: 1.1}, HEALTH, NOW + 38 * 3600)
check(r["alerts"][0]["alertReason"] == "NEW_EPISODE" and r["alerts"][0]["incidentId"] == K + "#e2", "new episode")
# telemetry: floor, mute, quiet hours
st2 = {"incidents": {}, "lastSuccessAt": NOW - 600}
r = LC.step(st2, [sig("LOW")], {K: 1.0}, HEALTH, NOW, {"minSeverity": "MEDIUM"}); check(r["telemetry"]["belowFloor"] == 1 and not r["alerts"], "below floor counted")
st2 = {"incidents": {}, "lastSuccessAt": NOW - 600}
r = LC.step(st2, [sig()], {K: 1.0}, HEALTH, NOW, {"mute": ["polymarket"]}); check(r["telemetry"]["muted"] == 1, "muted counted")
st2 = {"incidents": {}, "lastSuccessAt": NOW - 600}; h = T.datetime.fromtimestamp(NOW, T.timezone.utc).hour
r = LC.step(st2, [sig()], {K: 1.0}, HEALTH, NOW, {"quietHours": (h, (h + 2) % 24)}); check(r["telemetry"]["deferred"] == 1 and not r["alerts"], "quiet hours defer")
r = LC.step(st2, [], {K: 1.0}, HEALTH, NOW + 3 * 3600, {"quietHours": (h, (h + 2) % 24)}); check(len(r["alerts"]) == 1, "digest released after quiet hours")

# --- feed.watch: failed run never resolves; adapter for v1 state + v1 report
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "w.json"; p.write_text(json.dumps({"seen": {"x:y:20261027": "HIGH"}, "lastSuccessAt": NOW - 600}))
    rep = {"generatedAt": NOW, "status": "ok", "sourceStatus": {"polymarket": {"state": "HEALTHY"}}, "signals": [sig()], "probes": {K: 1.2}}
    out = F.watch(rep, p); check(len(out["watch"]["alerts"]) == 1 and out["signals"][0]["incident"]["state"] == "NEW", "v1 state adapted")
    rep2 = {"generatedAt": NOW + 600, "status": "failed", "sourceStatus": {"polymarket": {"state": "UNAVAILABLE"}}, "signals": [], "probes": {}}
    out = F.watch(rep2, p); check(out["watch"]["activeIncidents"][0]["state"] == "NEW" and out["watch"]["telemetry"]["skippedUnavailable"] == 1, "failed run retains")
v1 = {"kind": "signals", "generatedAt": NOW, "sourceStatus": {"kalshi": {"state": "ok"}, "sec": {"state": "skipped"}},
      "signals": [{"key": "stablecoins:USDT:SUPPLY_MINT:20261027", "source": "stablecoins", "type": "SUPPLY_MINT", "severity": "MEDIUM", "basis": "observed",
                   "title": "t", "what": "w", "when": NOW, "subject": {"name": "USDT"}, "evidence": [], "limits": []},
                  {"key": "cross:fed:CONVERGENCE:20261027", "source": "cross", "type": "CONVERGENCE", "severity": "HIGH", "basis": "inferred",
                   "title": "Convergence 80", "what": "", "when": NOW, "subject": {"name": "fed"}, "evidence": [], "limits": [], "metrics": {"convergence": 80}}]}
ad = F.adapt(v1)
check(ad["version"] == 2 and ad["signals"][0]["type"] == "SUPPLY_CHANGE" and ad["signals"][0]["key"] == "stablecoins:USDT:SUPPLY_MINT", ad["signals"][0]["key"])
check(ad["sourceStatus"]["kalshi"]["state"] == "HEALTHY" and ad["sourceStatus"]["sec"]["state"] == "NOT_CONFIGURED", "status adapted")
check(ad["signals"][1]["metrics"]["rank"] == 80 and "uncalibrated" in ad["signals"][1]["metrics"]["rankNote"], "legacy score → uncalibrated rank")
check(ad["signals"][0]["observation"]["timesApproximate"], "legacy times flagged approximate")

# --- empty feed says what was observed, not "quiet market"
a0 = F._assess([], {"kalshi": {"state": "HEALTHY", "coverage": {"observed": 1200}}, "options": {"state": "UNAVAILABLE", "coverage": {"observed": 0}}})
check("not that markets were quiet" in a0["lead"]["text"] and "1200" in a0["lead"]["text"] and "unknown, not quiet" in a0["lead"]["text"], a0["lead"]["text"])

# --- example file is v2, sanitized
ex = json.loads((R / "examples/signals-EXAMPLE.json").read_text())
check(ex.get("example") is True and ex["kind"] == "signals" and ex["version"] == 2, "example file v2")
print(f"signals: all {ok} checks passed")
