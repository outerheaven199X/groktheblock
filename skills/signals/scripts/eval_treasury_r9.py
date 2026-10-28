#!/usr/bin/env python3
"""R9: r9 Treasury evaluation version (r6/r7/r8 artifacts kept unchanged as history). Differences from r8:
- R9-01: calendar strata are RELEASE_VERIFIED (a VERIFIED announcement maps to the session) / RELEASE_PROVISIONAL (only
  PROVISIONAL or FETCHED announcements, or a VERIFIED one whose session assignment is UNCERTAIN, map to it, incl. the
  alternative session) / NO_VERIFIED_RELEASE; a provisional date can never populate the verified stratum.
- R9-03: eval-results.json holds one current, hash-linked record; older versions are named historical sections.
Below: the r8 design notes, unchanged.

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
Run: python skills/signals/scripts/eval_treasury_r9.py"""
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
SEED = 20261028 + 9
FRACTION, MIN_PER_STRATUM = 0.05, 3
BOUNDARY, BOUNDARY_PER_STRATUM = (0.75, 1.25), 4
VERSION = "r9-2026-10-28"


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


def calendar_status(cal: dict) -> dict:
    """session date → RELEASE_VERIFIED / RELEASE_PROVISIONAL (absent = NO_VERIFIED_RELEASE)."""
    out = {}
    for e in cal["events"]:
        sure = e.get("verification") == "VERIFIED" and e.get("sessionAssignment", "CLEAR") == "CLEAR"
        for d in (e["firstObservationSession"], e.get("alternativeSession")):
            if not d:
                continue
            if sure and d == e["firstObservationSession"]:
                out[d] = "RELEASE_VERIFIED"
            elif out.get(d) != "RELEASE_VERIFIED":
                out[d] = "RELEASE_PROVISIONAL"
    return out


def build_frame(rows):
    cal = json.loads((OUT / "release-calendar-r9.json").read_text())
    cstat = calendar_status(cal)
    build_frame.cstat = cstat
    cand, inel = [], []
    for i, (d, _) in enumerate(rows):
        if d < FRAME_FROM:
            continue
        for t in TENORS:
            ser = _series(rows, t)
            ref = RF.tail_flag(ser, i)
            w = {"date": d, "tenor": t, "i": i, "split": "holdout" if d >= HOLDOUT_FROM else "development",
                 "calendar": cstat.get(d, "NO_VERIFIED_RELEASE"), "priorValidChanges": ref.get("priorValidChanges", 0)}
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
    build_frame.coverage = {"verifiedSessions": sum(1 for v in cstat.values() if v == "RELEASE_VERIFIED"),
                            "provisionalSessions": sum(1 for v in cstat.values() if v == "RELEASE_PROVISIONAL"),
                            "windowsByCalendar": {c: sum(1 for w in cand if w["calendar"] == c) for c in ("RELEASE_VERIFIED", "RELEASE_PROVISIONAL", "NO_VERIFIED_RELEASE")},
                            "note": "BLS CPI/NFP dates are PROVISIONAL (GTB_CONTACT not configured): their sessions form a separate stratum and can't act as verified releases or verified non-release days; verified-release analysis covers FOMC only"}
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


def write_results(counts, n_items):
    """R9-03: one current record, hash-linked to the frozen r9 inputs; older content kept under named historical sections."""
    from datetime import datetime, timezone
    p = ROOT / "docs/review/eval-results.json"
    old = json.loads(p.read_text())
    hist = old.get("historical") or {}
    if "configVersion" in old:  # first migration from the mixed r4/r6/r7/r8 file
        hist["r4"] = {k: old[k] for k in ("configVersion", "generatedAt", "noHitRateOrLeadTime", "synthetic", "unlabelledHistorical", "objective", "baselinesNotRun", "labelled") if k in old}
        a = old.get("objectiveA", {})
        hist["r6"] = {k: a[k] for k in ("status", "adjudicatedEvents", "minimumForAPrecisionFigure", "precision", "recall", "agreement", "wilson95",
                                         "rosterEpisodes", "matchedNegatives", "dataset", "configVersion", "baselines") if k in a}
        hist["r7"] = {k: a[k] for k in ("rubricVersion", "vignetteReviewerCheck", "rosterR7") if k in a}
        hist["r7"]["rubricVersion"] = "r7-2026-10-28"
        hist["r8"] = {k: a[k] for k in ("labelingGate", "pooledEstimateAllowed", "neverFrom", "rosterR8", "why") if k in a}
        hist["r8"]["rubricVersion"] = "r8-2026-10-28"

    def ref(f):
        return {"file": f, "sha256": sha(ROOT / f)}
    cur = {"evaluationVersion": VERSION, "computedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "INSUFFICIENT_EVIDENCE",
           "objective": "A (descriptive accuracy of emitted Treasury anomalies; see EVALUATION.md)",
           "datasetManifest": ref("docs/review/eval-treasury/manifest-r9.json"), "rubric": ref("docs/review/adjudication-r8.json"), "rubricVersion": "r8-2026-10-28",
           "roster": ref("docs/review/eval-treasury/roster-r9.json"), "sampleDesign": ref("docs/review/eval-treasury/sample-design-r9.json"),
           "releaseCalendar": ref("docs/review/eval-treasury/release-calendar-r9.json"),
           "labelingGate": "BLOCKED", "humanReviewedLabels": 0, "adjudicatedEvents": 0, "minimumForAPrecisionFigure": 100,
           "precision": None, "recall": None, "agreement": None, "intervals": None,
           "pooledEstimateAllowed": False, "neverFrom": {"QUIET_CONTROL": ["recall", "specificity"], "BOUNDARY_CHALLENGE": ["population estimates"]},
           "vignetteReviewerCheck": {"status": "NOT_RUN", "set": "tests/fixtures/adjudication-vignettes-r8.json", "vignettes": 12},
           "rosterCounts": counts, "rosterItems": n_items,
           "why": "No reviewer assigned; gate BLOCKED; no labels. Performance fields stay null until the gate passes and ≥100 assessable episodes are adjudicated."}
    p.write_text(json.dumps({"_note": "Current evaluation result = objectiveA (r9). 'historical' keeps earlier versions verbatim by name; nothing in it is current.",
                             "current": "objectiveA", "objectiveA": cur, "historical": hist}, indent=1, default=str))


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
        iid = f"R9-{n + 1:04d}"
        m = mem[(d, t)]
        pv = prior_valid_changes(rows, d, t)
        items.append({"itemId": iid, "date": d, "series": f"treasury:{t}", "window": "the session and the 5 sessions before it",
                      "split": "holdout" if d >= HOLDOUT_FROM else "development"})
        sealed[iid] = {"components": sorted(m["components"]), "stratumKey": m.get("stratumKey"), "inclusionProbability": m.get("inclusionProbability"),
                       "boundaryStratumKey": m.get("boundaryStratumKey"), "selectionProbability": m.get("selectionProbability"),
                       "detectorRatio": ratios.get((d, t)), "priorValidChanges": pv, "referenceEligible": pv >= RF.N_PRIOR}
        for c in m["components"]:
            el[c]["eligible" if pv >= RF.N_PRIOR else "ineligible"] += 1
    (RAW / "sealed-key-r9.json").write_text(json.dumps(sealed, indent=0))
    counts = {c: sum(1 for m in mem.values() if c in m["components"]) for c in el}
    roster = {"version": VERSION, "_note": "Blind roster r9: reviewers see itemId, date, series, window and split only; they judge integrity and context. Anomaly is computed by reference.py. Track membership, design weights and detector status are in the sealed key (local; SHA-256 below). Items appear once even if in several tracks; deduplication doesn't change any inclusion probability.",
              "seed": SEED, "counts": counts, "items": items, "sealedKeySha256": hashlib.sha256(json.dumps(sealed, sort_keys=True).encode()).hexdigest()}
    (OUT / "roster-r9.json").write_text(json.dumps(roster, indent=1) + "\n")
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
              "calendarSource": "docs/review/eval-treasury/release-calendar-r9.json", "calendarKey": "firstObservationSession",
              "volRegimeCuts_bp": {t: [round(c, 3) for c in v] for t, v in build_frame.cuts.items()},
              "coverageLoss": build_frame.coverage,
              "strata": table, "sampleSize": len(pop), "distributionTable": dist, "detectorStatusInSample": agg,
              "eligibility": {"byYearTenor": byyt, "byComponent": el},
              "tracks": {"population": {"component": "PROBABILITY_SAMPLE", "designWeights": True, "estimator": "Hájek, weights 1/inclusionProbability; stratified bootstrap interval (estimators.py)", "size": len(pop)},
                         "emittedEpisodes": {"component": "EPISODE", "controls": "QUIET_CONTROL (deliberately quiet; never used for recall or specificity)", "designWeights": False, "size": counts["EPISODE"]},
                         "boundaryChallenge": {"component": "BOUNDARY_CHALLENGE", "diagnosticOnly": True, "populationWeight": None, "ratioRange": list(BOUNDARY),
                                               "perStratum": BOUNDARY_PER_STRATUM, "strata": btable, "size": len(bset),
                                               "note": "selection uses detector output; selection probabilities are recorded but the set is never folded into population estimates under this design"}}}
    (OUT / "sample-design-r9.json").write_text(json.dumps(design, indent=1) + "\n")
    (OUT / "labels-r9.json").write_text(json.dumps({"_note": "EMPTY until reviewer-gate-r8.json passes. Reviewers record integrity and context only; anomaly is computed.", "rubric": "docs/review/adjudication-r8.json",
                                                    "reviewers": [], "labels": [], "fields": ["itemId", "reviewer", "integrity", "context", "note"]}, indent=1) + "\n")
    gp = OUT / "reviewer-gate-r8.json"  # R9-05: the existing gate is kept and pointed at the current roster, never replaced
    g = json.loads(gp.read_text())
    g["pilot"]["draw"] = "25 items from roster-r9 by seeded random order, all tracks"
    g["appliesTo"] = "roster-r9.json (r9 is the current frozen version)"
    g["validator"] = "skills/signals/scripts/reviewer_gate.py"
    g["vignetteCheck"]["vignettes"] = 12
    gp.write_text(json.dumps(g, indent=1) + "\n")
    man = {"version": VERSION, "_note": "R9 frozen evaluation manifest (current). Prior versions are kept unchanged; their hashes are listed.",
           "series": [{"year": y, "url": S.TSY_URL.format(y=y), "sha256": sha(RAW / f"{y}.csv")} for y in YEARS],
           "priorVersions": {f: sha(OUT / f) for f in ("roster.json", "manifest.json", "labels.json", "roster-r7.json", "sample-design-r7.json", "labels-r7.json", "manifest-r7.json", "release-calendar.json",
                                                     "roster-r8.json", "sample-design-r8.json", "labels-r8.json", "manifest-r8.json", "release-calendar-r8.json")},
           "roster": {"file": "roster-r9.json", "sha256": sha(OUT / "roster-r9.json")}, "sampleDesign": {"file": "sample-design-r9.json", "sha256": sha(OUT / "sample-design-r9.json")},
           "releaseCalendar": {"file": "release-calendar-r9.json", "sha256": sha(OUT / "release-calendar-r9.json")},
           "rubric": {"file": "docs/review/adjudication-r8.json", "sha256": sha(ROOT / "docs/review/adjudication-r8.json")},
           "reviewerGate": "reviewer-gate-r8.json", "labels": "labels-r9.json",
           "labelMapping": "no labels existed in any prior version; nothing carried forward",
           "calendarCoverage": build_frame.coverage}
    (OUT / "manifest-r9.json").write_text(json.dumps(man, indent=1) + "\n")
    write_results(counts, len(items))
    print(json.dumps({"frame": len(frame), "ineligible": len(build_frame.ineligible), "strata": len(table), "sample": len(pop), "boundary": len(bset),
                      "counts": counts, "items": len(items), "agg": agg, "el": el}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
