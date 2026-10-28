#!/usr/bin/env python3
"""R7-02: a detector-independent probability sample of Treasury session×tenor windows, plus a new frozen, blind roster.

Keeps the r6 records untouched (roster.json, manifest.json, labels.json: their SHA-256s are recorded as prior rosters). The
r6 episodes stay the EPISODE stratum, and the r6 matched negatives become the named QUIET_CONTROL stratum (never used to
infer recall). New: a stratified random sample of ALL eligible windows (frame = every session×tenor with ≥60 prior sessions),
chosen WITHOUT using detector output, stratified by tenor × split (development/holdout) × calendar (release day or not, from
release-calendar.json) × volatility regime (tercile of the trailing 20-session s.d. of daily changes, cut points from the
development split per tenor). Inclusion probability per stratum = n_h / N_h. Detector status is computed AFTER sampling and
kept only as aggregate counts and in the sealed key. Labels stay empty.
Inputs: tests/fixtures/private/treasury/<year>.csv and sealed-key.json (local, gitignored). Run: python skills/signals/scripts/eval_treasury_r7.py"""
import hashlib, json, random, statistics, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
from grok_the_block.markets import sources as S, detectors as X, timebase as T  # noqa: E402

RAW = ROOT / "tests/fixtures/private/treasury"
OUT = ROOT / "docs/review/eval-treasury"
SEED = 20261028 + 7
LOOKBACK = 60
HOLDOUT_FROM = "2025-01-01"
TENORS = ("2Y", "10Y", "30Y", "2s10s")
FRACTION = 0.05      # target sampling fraction per stratum (frozen before sampling)
MIN_PER_STRATUM = 3  # so every non-empty stratum is represented
NEAR = 0.75          # aggregate reporting only: detector ratio in [0.75, 1) = near-threshold


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    files = [RAW / f"{y}.csv" for y in range(2019, 2027)]
    if not all(f.exists() for f in files) or not (RAW / "sealed-key.json").exists():
        print("SKIPPED: private Treasury CSVs / r6 sealed key missing (run eval_treasury.py --fetch first)"); return 0
    rows = {}
    for f in files:
        rows.update(dict(S.parse_treasury_csv(f.read_text()) or []))
    rows = sorted(rows.items())
    cal = json.loads((OUT / "release-calendar.json").read_text())
    release = {e["date"] for e in cal["events"]}

    def val(r, t):
        if t == "2s10s":
            return (r["10Y"] - r["2Y"]) if r.get("10Y") is not None and r.get("2Y") is not None else None
        return r.get(t)

    frame = []
    for i in range(LOOKBACK, len(rows)):
        d = rows[i][0]
        for t in TENORS:
            ser = [val(r, t) for _, r in rows[i - 20:i + 1]]
            ch = [(b - a) * 100 for a, b in zip(ser, ser[1:]) if a is not None and b is not None]
            vol = statistics.pstdev(ch[:-1]) if len(ch) >= 10 else None
            frame.append({"date": d, "tenor": t, "i": i, "split": "holdout" if d >= HOLDOUT_FROM else "development",
                          "calendar": "RELEASE" if d in release else "NO_RELEASE", "vol": vol})
    cuts = {}
    for t in TENORS:
        v = sorted(w["vol"] for w in frame if w["tenor"] == t and w["split"] == "development" and w["vol"] is not None)
        cuts[t] = (v[len(v) // 3], v[2 * len(v) // 3])
    for w in frame:
        lo, hi = cuts[w["tenor"]]
        w["volRegime"] = "LOW" if (w["vol"] or 0) < lo else "MID" if w["vol"] < hi else "HIGH"
    strata = {}
    for w in frame:
        strata.setdefault((w["tenor"], w["split"], w["calendar"], w["volRegime"]), []).append(w)
    rng = random.Random(SEED)
    sample, table = [], []
    for k in sorted(strata):
        pop = strata[k]
        n = min(len(pop), max(MIN_PER_STRATUM, round(len(pop) * FRACTION)))
        pick = rng.sample(pop, n)
        sample += pick
        table.append({"tenor": k[0], "split": k[1], "calendar": k[2], "volRegime": k[3], "N": len(pop), "n": n, "inclusionProbability": n / len(pop)})
    # detector status AFTER sampling (point-in-time, same frozen detector), aggregate only
    status = {}
    for w in sorted(sample, key=lambda w: w["i"]):
        X.reset()
        ob = {"ingestTs": T.ny_ts(date.fromisoformat(w["date"]), 18), "status": "HEALTHY", "coverage": {}, "limitations": []}
        X.treasury_signals(rows[:w["i"] + 1], "https://home.treasury.gov/", ob)
        typ = "CURVE_SHIFT" if w["tenor"] == "2s10s" else "YIELD_MOVE"
        r = (X.PROBES.get(f"treasury:{w['tenor']}:{typ}") or {}).get("ratio")
        status[(w["date"], w["tenor"])] = "UNMEASURED" if r is None else "FLAGGED" if r >= 1 else "NEAR" if r >= NEAR else "BELOW"
    agg = {"flagged": 0, "nearThreshold": 0, "belowThreshold": 0, "unmeasured": 0}
    for v in status.values():
        agg[{"FLAGGED": "flagged", "NEAR": "nearThreshold", "BELOW": "belowThreshold", "UNMEASURED": "unmeasured"}[v]] += 1
    # roster: r6 episodes + quiet controls (from the r6 sealed key) + probability sample, deduplicated, shuffled, blind
    r6 = json.loads((OUT / "roster.json").read_text())
    key6 = json.loads((RAW / "sealed-key.json").read_text())
    member = {}
    for it in r6["items"]:
        member.setdefault((it["date"], it["series"]), set()).add("EPISODE" if key6[it["itemId"]] == "episode" else "QUIET_CONTROL")
    for w in sample:
        member.setdefault((w["date"], f"treasury:{w['tenor']}"), set()).add("PROBABILITY_SAMPLE")
    keys = sorted(member)
    rng.shuffle(keys)
    items, sealed = [], {}
    for n, (d, s) in enumerate(keys):
        iid = f"R7-{n + 1:04d}"
        items.append({"itemId": iid, "date": d, "series": s, "window": "the session and the 5 sessions before it",
                      "split": "holdout" if d >= HOLDOUT_FROM else "development"})
        t = s.split(":", 1)[1]
        sealed[iid] = {"strata": sorted(member[(d, s)]), "detectorStatus": status.get((d, t))}
    (RAW / "sealed-key-r7.json").write_text(json.dumps(sealed, indent=0))
    counts = {c: sum(1 for m in member.values() if c in m) for c in ("EPISODE", "QUIET_CONTROL", "PROBABILITY_SAMPLE")}
    roster = {"version": "r7-2026-10-28", "_note": "Blind roster r7: reviewers see itemId, date, series, window and split only. Stratum membership and detector status are in the sealed key (kept locally; SHA-256 below). An item may belong to several strata; it is listed once.",
              "seed": SEED, "counts": counts, "items": items, "sealedKeySha256": hashlib.sha256(json.dumps(sealed, sort_keys=True).encode()).hexdigest()}
    (OUT / "roster-r7.json").write_text(json.dumps(roster, indent=1) + "\n")
    dist = {}
    for s in table:
        k = f"{s['calendar']}/{s['volRegime']}"
        dist.setdefault(k, {"N": 0, "n": 0}); dist[k]["N"] += s["N"]; dist[k]["n"] += s["n"]
    design = {"version": "r7-2026-10-28", "selectionUsesDetectorOutput": False, "seed": SEED, "fraction": FRACTION, "minPerStratum": MIN_PER_STRATUM,
              "frame": {"windows": len(frame), "rule": f"every session×tenor with ≥{LOOKBACK} prior sessions, {frame[0]['date']} → {frame[-1]['date']}", "tenors": list(TENORS)},
              "calendarSource": "docs/review/eval-treasury/release-calendar.json", "volRegimeCuts_bp": {t: [round(c, 3) for c in v] for t, v in cuts.items()},
              "strata": table, "sampleSize": len(sample), "distributionTable": dist, "detectorStatusInSample": agg,
              "estimation": "Horvitz-Thompson weights 1/inclusionProbability for population shares; QUIET_CONTROL items are never used for recall or specificity."}
    (OUT / "sample-design-r7.json").write_text(json.dumps(design, indent=1) + "\n")
    (OUT / "labels-r7.json").write_text(json.dumps({"_note": "EMPTY. r7 label sheet (adjudication-r7.json axes). No reviewer has labelled anything; nothing is invented.",
                                                    "rubric": "docs/review/adjudication-r7.json", "reviewers": [], "labels": [],
                                                    "fields": ["itemId", "reviewer", "anomaly", "integrity", "context", "primary", "note"]}, indent=1) + "\n")
    man = {"version": "r7-2026-10-28", "_note": "R7-02 frozen roster manifest. r6 records are kept unchanged as history.",
           "priorRosters": {n: {"sha256": sha(OUT / n), "role": r} for n, r in (
               ("roster.json", "historical record (r6); its negatives are the QUIET_CONTROL stratum, never used for recall"),
               ("manifest.json", "r6 dataset manifest (CSV SHA-256s still apply)"), ("labels.json", "r6 label sheet (empty, superseded by labels-r7.json)"))},
           "roster": {"file": "roster-r7.json", "sha256": sha(OUT / "roster-r7.json")}, "sampleDesign": {"file": "sample-design-r7.json", "sha256": sha(OUT / "sample-design-r7.json")},
           "releaseCalendar": {"file": "release-calendar.json", "sha256": sha(OUT / "release-calendar.json")},
           "rubric": {"file": "docs/review/adjudication-r7.json", "sha256": sha(ROOT / "docs/review/adjudication-r7.json")}, "labels": "labels-r7.json"}
    (OUT / "manifest-r7.json").write_text(json.dumps(man, indent=1) + "\n")
    res = json.loads((ROOT / "docs/review/eval-results.json").read_text())
    a = res["objectiveA"]
    a.update({"rubricVersion": "r7-2026-10-28", "precision": None, "adjudicatedEvents": 0,
              "vignetteReviewerCheck": {"status": "NOT_RUN", "why": "two independent reviewers have not returned the four vignette labels"},
              "rosterR7": {"file": "docs/review/eval-treasury/roster-r7.json", "counts": counts, "items": len(items)},
              "why": "r7 rubric, blind r7 roster and probability sample exist; no reviewer has labelled anything. INSUFFICIENT_EVIDENCE; no precision on the r6 rubric; no lead time."})
    (ROOT / "docs/review/eval-results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({"frame": len(frame), "strata": len(table), "sample": len(sample), "counts": counts, "items": len(items), "detectorStatusInSample": agg, "dist": dist}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
