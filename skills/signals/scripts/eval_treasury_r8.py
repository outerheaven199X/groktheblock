#!/usr/bin/env python3
"""R8-01..06: r8 Treasury evaluation version (r6/r7 artifacts kept unchanged as history).

- History: treasury.gov daily par-yield CSVs 2018-2026 (2018 added so 2019 windows can have 250 prior changes).
- Population frame: every session×tenor (2Y, 10Y, 30Y, 2s10s) from 2019-01-02 whose item change is observable AND that has
  ≥250 valid prior daily changes (reference.py). Windows without that history are listed as ineligible (UNASSESSABLE) and
  are not in the frame or any denominator.
- Strata: tenor × split (development < 2025-01-01 ≤ holdout) × calendar (RELEASE if the session is the first Treasury
  observation session after an FOMC/CPI/NFP announcement in release-calendar-r8.json) × volatility regime (terciles of the
  trailing 20-session s.d. of daily changes, cut points from the development split per tenor).
- Three tracks, never pooled: POPULATION (stratified random sample, 5%, min 3 per stratum, design weights 1/π); EMITTED
  EPISODES (the r6 detector episodes) with QUIET_CONTROL (r6 matched negatives, never used for recall); BOUNDARY_CHALLENGE
  (detector ratio 0.75-1.25, up to 4 per tenor×calendar×vol stratum; diagnostic only, no population weight).
- Detector status is computed point-in-time with the frozen detector and is kept only in the sealed key and as aggregates.
Inputs (local, gitignored): tests/fixtures/private/treasury/{2018..2026}.csv, sealed-key.json (r6).
Run: python skills/signals/scripts/eval_treasury_r8.py"""
import bisect, hashlib, json, random, statistics, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib")); sys.path.insert(0, str(Path(__file__).resolve().parent))
from grok_the_block.markets import sources as S, detectors as X, timebase as T  # noqa: E402
import reference as RF  # noqa: E402

RAW = ROOT / "tests/fixtures/private/treasury"
OUT = ROOT / "docs/review/eval-treasury"
YEARS = range(2018, 2027)
FRAME_FROM = "2019-01-02"
HOLDOUT_FROM = "2025-01-01"
TENORS = ("2Y", "10Y", "30Y", "2s10s")
SEED = 20261028 + 8
FRACTION, MIN_PER_STRATUM = 0.05, 3
BOUNDARY, BOUNDARY_PER_STRATUM = (0.75, 1.25), 4
VERSION = "r8-2026-10-28"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_rows():
    rows = {}
    for y in YEARS:
        rows.update(dict(S.parse_treasury_csv((RAW / f"{y}.csv").read_text()) or []))
    return sorted(rows.items())


def val(r, t):
    if t == "2s10s":
        return (r["10Y"] - r["2Y"]) if r.get("10Y") is not None and r.get("2Y") is not None else None
    return r.get(t)


_CACHE = {}


def _series(rows, t):
    k = (id(rows), t)
    if k not in _CACHE:
        _CACHE[k] = [val(r, t) for _, r in rows]
    return _CACHE[k]


def prior_valid_changes(rows, d, t):
    i = bisect.bisect_left([x[0] for x in rows], d)
    return RF.tail_flag(_series(rows, t), i).get("priorValidChanges", 0) if rows[i][0] == d else 0


def build_frame(rows):
    cal = json.loads((OUT / "release-calendar-r8.json").read_text())
    release = {e["firstObservationSession"] for e in cal["events"]}
    cand, inel = [], []
    for i, (d, _) in enumerate(rows):
        if d < FRAME_FROM:
            continue
        for t in TENORS:
            ser = _series(rows, t)
            ref = RF.tail_flag(ser, i)
            w = {"date": d, "tenor": t, "i": i, "split": "holdout" if d >= HOLDOUT_FROM else "development",
                 "calendar": "RELEASE" if d in release else "NO_RELEASE", "priorValidChanges": ref.get("priorValidChanges", 0)}
            if ref["status"] == "UNASSESSABLE":
                inel.append(w); continue
            ch = [(b - a) * 100 for a, b in zip(ser[i - 20:i], ser[i - 19:i + 1]) if a is not None and b is not None]
            w["vol"] = statistics.pstdev(ch[:-1]) if len(ch) >= 10 else 0.0
            cand.append(w)
    cuts = {}
    for t in TENORS:
        v = sorted(w["vol"] for w in cand if w["tenor"] == t and w["split"] == "development")
        cuts[t] = (v[len(v) // 3], v[2 * len(v) // 3])
    strata = {}
    for w in cand:
        lo, hi = cuts[w["tenor"]]
        w["volRegime"] = "LOW" if w["vol"] < lo else "MID" if w["vol"] < hi else "HIGH"
        w["stratumKey"] = "|".join((w["tenor"], w["split"], w["calendar"], w["volRegime"]))
        strata.setdefault(w["stratumKey"], []).append(w)
    build_frame.ineligible, build_frame.cuts = inel, cuts
    return cand, strata


def detector_ratios(rows):
    out = {}
    start = next(i for i, (d, _) in enumerate(rows) if d >= FRAME_FROM)
    for i in range(start, len(rows)):
        X.reset()
        ob = {"ingestTs": T.ny_ts(date.fromisoformat(rows[i][0]), 18), "status": "HEALTHY", "coverage": {}, "limitations": []}
        X.treasury_signals(rows[:i + 1], "https://home.treasury.gov/", ob)
        for t in TENORS:
            p = X.PROBES.get(f"treasury:{t}:{'CURVE_SHIFT' if t == '2s10s' else 'YIELD_MOVE'}") or {}
            out[(rows[i][0], t)] = p.get("ratio")
    return out


def main():
    if not all((RAW / f"{y}.csv").exists() for y in YEARS) or not (RAW / "sealed-key.json").exists():
        print("SKIPPED: private Treasury CSVs (2018-2026) / r6 sealed key missing"); return 0
    rows = load_rows()
    frame, strata = build_frame(rows)
    ratios = detector_ratios(rows)
    rng = random.Random(SEED)
    table, pop = [], []
    for k in sorted(strata):
        p = strata[k]
        n = min(len(p), max(MIN_PER_STRATUM, round(len(p) * FRACTION)))
        pop += rng.sample(p, n)
        t, sp, c, v = k.split("|")
        table.append({"stratumKey": k, "tenor": t, "split": sp, "calendar": c, "volRegime": v, "N": len(p), "n": n, "inclusionProbability": n / len(p)})
    bstr = {}
    for w in frame:
        r = ratios.get((w["date"], w["tenor"]))
        if r is not None and BOUNDARY[0] <= r <= BOUNDARY[1]:
            bstr.setdefault("|".join((w["tenor"], w["calendar"], w["volRegime"])), []).append(w)
    btable, bset = [], []
    for k in sorted(bstr):
        p = bstr[k]
        n = min(len(p), BOUNDARY_PER_STRATUM)
        bset += [(k, w) for w in rng.sample(p, n)]
        btable.append({"stratumKey": k, "N": len(p), "n": n, "selectionProbability": n / len(p)})
    bprob = {b["stratumKey"]: b["selectionProbability"] for b in btable}
    pi = {s["stratumKey"]: s["inclusionProbability"] for s in table}
    # memberships
    r6 = json.loads((OUT / "roster.json").read_text())
    key6 = json.loads((RAW / "sealed-key.json").read_text())
    mem = {}

    def add(d, t, comp, **kw):
        m = mem.setdefault((d, t), {"components": set()})
        m["components"].add(comp); m.update(kw)
    for it in r6["items"]:
        add(it["date"], it["series"].split(":")[1], "EPISODE" if key6[it["itemId"]] == "episode" else "QUIET_CONTROL")
    for w in pop:
        add(w["date"], w["tenor"], "PROBABILITY_SAMPLE", stratumKey=w["stratumKey"], inclusionProbability=pi[w["stratumKey"]])
    for k, w in bset:
        add(w["date"], w["tenor"], "BOUNDARY_CHALLENGE", boundaryStratumKey=k, selectionProbability=bprob[k])
    keys = sorted(mem)
    rng.shuffle(keys)
    items, sealed = [], {}
    el = {c: {"eligible": 0, "ineligible": 0} for c in ("EPISODE", "QUIET_CONTROL", "PROBABILITY_SAMPLE", "BOUNDARY_CHALLENGE")}
    for n, (d, t) in enumerate(keys):
        iid = f"R8-{n + 1:04d}"
        m = mem[(d, t)]
        pv = prior_valid_changes(rows, d, t)
        items.append({"itemId": iid, "date": d, "series": f"treasury:{t}", "window": "the session and the 5 sessions before it",
                      "split": "holdout" if d >= HOLDOUT_FROM else "development"})
        sealed[iid] = {"components": sorted(m["components"]), "stratumKey": m.get("stratumKey"), "inclusionProbability": m.get("inclusionProbability"),
                       "boundaryStratumKey": m.get("boundaryStratumKey"), "selectionProbability": m.get("selectionProbability"),
                       "detectorRatio": ratios.get((d, t)), "priorValidChanges": pv, "referenceEligible": pv >= RF.N_PRIOR}
        for c in m["components"]:
            el[c]["eligible" if pv >= RF.N_PRIOR else "ineligible"] += 1
    (RAW / "sealed-key-r8.json").write_text(json.dumps(sealed, indent=0))
    counts = {c: sum(1 for m in mem.values() if c in m["components"]) for c in el}
    roster = {"version": VERSION, "_note": "Blind roster r8: reviewers see itemId, date, series, window and split only; they judge integrity and context. Anomaly is computed by reference.py. Track membership, design weights and detector status are in the sealed key (local; SHA-256 below). Items appear once even if in several tracks; deduplication doesn't change any inclusion probability.",
              "seed": SEED, "counts": counts, "items": items, "sealedKeySha256": hashlib.sha256(json.dumps(sealed, sort_keys=True).encode()).hexdigest()}
    (OUT / "roster-r8.json").write_text(json.dumps(roster, indent=1) + "\n")
    byyt = {}
    for w in frame + build_frame.ineligible:
        k = f"{w['date'][:4]}|{w['tenor']}"
        byyt.setdefault(k, {"eligible": 0, "ineligible": 0})
        byyt[k]["eligible" if "stratumKey" in w else "ineligible"] += 1
    agg = {"flagged": 0, "nearThreshold": 0, "belowThreshold": 0, "unmeasured": 0}
    for w in pop:
        r = ratios.get((w["date"], w["tenor"]))
        agg["unmeasured" if r is None else "flagged" if r >= 1 else "nearThreshold" if r >= 0.75 else "belowThreshold"] += 1
    dist = {}
    for s in table:
        k = f"{s['calendar']}/{s['volRegime']}"
        dist.setdefault(k, {"N": 0, "n": 0}); dist[k]["N"] += s["N"]; dist[k]["n"] += s["n"]
    design = {"version": VERSION, "selectionUsesDetectorOutput": False, "seed": SEED,
              "frame": {"windows": len(frame), "ineligibleWindows": len(build_frame.ineligible), "minPriorValidChanges": RF.N_PRIOR,
                        "from": FRAME_FROM, "to": rows[-1][0], "tenors": list(TENORS), "history": "treasury.gov CSVs 2018-2026"},
              "calendarSource": "docs/review/eval-treasury/release-calendar-r8.json", "calendarKey": "firstObservationSession",
              "volRegimeCuts_bp": {t: [round(c, 3) for c in v] for t, v in build_frame.cuts.items()},
              "strata": table, "sampleSize": len(pop), "distributionTable": dist, "detectorStatusInSample": agg,
              "eligibility": {"byYearTenor": byyt, "byComponent": el},
              "tracks": {"population": {"component": "PROBABILITY_SAMPLE", "designWeights": True, "estimator": "Hájek, weights 1/inclusionProbability; stratified bootstrap interval (estimators.py)", "size": len(pop)},
                         "emittedEpisodes": {"component": "EPISODE", "controls": "QUIET_CONTROL (deliberately quiet; never used for recall or specificity)", "designWeights": False, "size": counts["EPISODE"]},
                         "boundaryChallenge": {"component": "BOUNDARY_CHALLENGE", "diagnosticOnly": True, "populationWeight": None, "ratioRange": list(BOUNDARY),
                                               "perStratum": BOUNDARY_PER_STRATUM, "strata": btable, "size": len(bset),
                                               "note": "selection uses detector output; selection probabilities are recorded but the set is never folded into population estimates under this design"}}}
    (OUT / "sample-design-r8.json").write_text(json.dumps(design, indent=1) + "\n")
    (OUT / "labels-r8.json").write_text(json.dumps({"_note": "EMPTY until reviewer-gate-r8.json passes. Reviewers record integrity and context only; anomaly is computed.", "rubric": "docs/review/adjudication-r8.json",
                                                    "reviewers": [], "labels": [], "fields": ["itemId", "reviewer", "integrity", "context", "note"]}, indent=1) + "\n")
    (OUT / "reviewer-gate-r8.json").write_text(json.dumps({
        "status": "BLOCKED", "reviewersAssigned": False, "adjudicatorAssigned": False,
        "requirement": "two independent human reviewers familiar with fixed-income data, not involved in setting thresholds, plus a third adjudicator; chosen by the owner and identified privately (not in this repository)",
        "vignetteCheck": {"status": "NOT_RUN", "set": "tests/fixtures/adjudication-vignettes-r8.json", "rule": "each reviewer labels integrity and context independently, blind to the intended answers; disagreements recorded with reasons"},
        "pilot": {"status": "NOT_RUN", "size": 25, "purpose": "calibration, not validation", "draw": "25 items from roster-r8 by seeded random order, all tracks", "rule": "rubric changes after seeing pilot labels are versioned and affected items relabelled"},
        "gatePasses": "vignette disagreements resolvable by the rubric itself, and pilot complete; only then may labels-r8.json receive labels"}, indent=1) + "\n")
    man = {"version": VERSION, "_note": "R8 frozen evaluation manifest. Prior versions are kept unchanged.",
           "series": [{"year": y, "url": S.TSY_URL.format(y=y), "sha256": sha(RAW / f"{y}.csv")} for y in YEARS],
           "priorVersions": {f: sha(OUT / f) for f in ("roster.json", "manifest.json", "labels.json", "roster-r7.json", "sample-design-r7.json", "labels-r7.json", "manifest-r7.json", "release-calendar.json")},
           "roster": {"file": "roster-r8.json", "sha256": sha(OUT / "roster-r8.json")}, "sampleDesign": {"file": "sample-design-r8.json", "sha256": sha(OUT / "sample-design-r8.json")},
           "releaseCalendar": {"file": "release-calendar-r8.json", "sha256": sha(OUT / "release-calendar-r8.json")},
           "rubric": {"file": "docs/review/adjudication-r8.json", "sha256": sha(ROOT / "docs/review/adjudication-r8.json")},
           "reviewerGate": "reviewer-gate-r8.json", "labels": "labels-r8.json",
           "labelMapping": "no labels existed in any prior version; nothing carried forward"}
    (OUT / "manifest-r8.json").write_text(json.dumps(man, indent=1) + "\n")
    res = json.loads((ROOT / "docs/review/eval-results.json").read_text())
    a = res["objectiveA"]
    a.update({"status": "INSUFFICIENT_EVIDENCE", "rubricVersion": "r8-2026-10-28", "labelingGate": "BLOCKED", "precision": None, "adjudicatedEvents": 0,
              "pooledEstimateAllowed": False, "neverFrom": {"QUIET_CONTROL": ["recall", "specificity"], "BOUNDARY_CHALLENGE": ["population estimates"]},
              "rosterR8": {"file": "docs/review/eval-treasury/roster-r8.json", "counts": counts, "items": len(items)},
              "why": "r8 calendar, frame (250-session eligibility), tracks and estimators exist; reviewers not assigned; label gate BLOCKED; no labels."})
    (ROOT / "docs/review/eval-results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({"frame": len(frame), "ineligible": len(build_frame.ineligible), "strata": len(table), "sample": len(pop), "boundary": len(bset),
                      "counts": counts, "items": len(items), "agg": agg, "el": el}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
