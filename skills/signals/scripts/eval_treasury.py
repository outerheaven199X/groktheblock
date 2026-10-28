#!/usr/bin/env python3
"""R6-06: build the Objective-A evaluation dataset on official Treasury daily par yields (2Y/10Y/30Y + 2s10s).

Inputs: the treasury.gov yearly CSVs saved locally in tests/fixtures/private/treasury/<year>.csv (gitignored; fetch them
with --fetch). Outputs (committed, no raw values): docs/review/eval-treasury/manifest.json (URLs, SHA-256, row counts,
frozen config, holdout span), roster.json (episodes and matched non-alert windows, shuffled with a recorded seed and
WITHOUT detector severity, magnitude or rank so reviewers are blind), labels.json (an empty label sheet). It also writes
objectiveA in docs/review/eval-results.json. No label is ever produced here: until two blind reviewers adjudicate
>= 100 assessable episodes, the status stays INSUFFICIENT_EVIDENCE. Thresholds are the frozen detector settings.
Run: python skills/signals/scripts/eval_treasury.py [--fetch]"""
import hashlib, json, random, statistics, sys, urllib.request
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
from grok_the_block.markets import sources as S, detectors as X, lifecycle as LC, timebase as T  # noqa: E402

YEARS = list(range(2019, 2027))
RAW = ROOT / "tests/fixtures/private/treasury"
OUT = ROOT / "docs/review/eval-treasury"
SEED = 20261028
LOOKBACK = 60
HOLDOUT_FROM = "2025-01-01"  # frozen before any label exists: 2019-2024 development, 2025-2026 held out


def fetch():
    RAW.mkdir(parents=True, exist_ok=True)
    for y in YEARS:
        req = urllib.request.Request(S.TSY_URL.format(y=y), headers={"User-Agent": "Mozilla/5.0"})
        (RAW / f"{y}.csv").write_bytes(urllib.request.urlopen(req, timeout=60).read())


def main():
    if "--fetch" in sys.argv:
        fetch()
    series, rows = [], {}
    for y in YEARS:
        p = RAW / f"{y}.csv"
        if not p.exists():
            print(f"SKIPPED: {p.name} missing (run with --fetch)"); return 0
        b = p.read_bytes()
        rr = S.parse_treasury_csv(b.decode()) or []
        series.append({"year": y, "url": S.TSY_URL.format(y=y), "sha256": hashlib.sha256(b).hexdigest(), "rows": len(rr),
                       "first": rr[0][0] if rr else None, "last": rr[-1][0] if rr else None})
        rows.update(dict(rr))
    rows = sorted(rows.items())
    st = {"incidents": {}, "lastSuccessAt": 1}
    episodes, flagged, per = [], set(), []
    for i in range(LOOKBACK + 1, len(rows) + 1):
        X.reset()
        d = rows[i - 1][0]
        at = T.ny_ts(date.fromisoformat(d), 18)
        ob = {"ingestTs": at, "status": "HEALTHY", "coverage": {}, "limitations": []}
        sigs = [s for s in X.treasury_signals(rows[:i], "https://home.treasury.gov/", ob) if s["basis"] != "unverified"]
        for s in sigs:
            flagged.add((d, s.get("instrument")))
        r = LC.step(st, sigs, dict(X.PROBES), {"treasury": "HEALTHY"}, at)
        for a in r["alerts"]:
            if a["alertReason"] in ("NEW", "NEW_EPISODE"):
                episodes.append({"date": d, "series": a.get("instrument") or a["key"].split(":")[1], "detector": a["type"], "incident": a["incidentId"]})
        prev = rows[i - 2][1]
        base = any(abs((rows[i - 1][1].get(t) or 0) - (prev.get(t) or 0)) >= 0.10 for t in ("2Y", "10Y", "30Y") if rows[i - 1][1].get(t) and prev.get(t))
        vn = False
        for t in ("2Y", "10Y", "30Y"):
            ys = [x[1].get(t) for x in rows[max(0, i - 22):i]]
            if None in ys or len(ys) < 22:
                continue
            dd = [b - a for a, b in zip(ys, ys[1:])]
            sd = statistics.pstdev(dd[:-1])
            vn = vn or bool(sd and abs(dd[-1]) / sd >= 3)
        per.append({"date": d, "flag": bool(sigs), "baseline10bp": base, "volNormalized": vn})
    dates = [p["date"] for p in per]
    flag_days = {p["date"] for p in per if p["flag"]}
    rng = random.Random(SEED)
    negatives, used = [], set()
    for e in episodes:  # matched non-alert window: same series, nearest session ≥10 sessions away with no flag within ±3 sessions
        k = dates.index(e["date"])
        cands = [j for j in range(len(dates)) if abs(j - k) >= 10 and (j, e["series"]) not in used and not any(dates[x] in flag_days for x in range(max(0, j - 3), min(len(dates), j + 4)))]
        if cands:
            j = min(cands, key=lambda j: (abs(j - k), rng.random())); used.add((j, e["series"]))
            negatives.append({"date": dates[j], "series": e["series"]})
    items = [dict(e, kind="episode") for e in episodes] + [dict(n, kind="negative") for n in negatives]
    rng.shuffle(items)
    blind = [{"itemId": f"T{n + 1:04d}", "date": it["date"], "series": it["series"], "window": "the session and the 5 sessions before it",
              "split": "holdout" if it["date"] >= HOLDOUT_FROM else "development"} for n, it in enumerate(items)]
    key = {b["itemId"]: it["kind"] for b, it in zip(blind, items)}
    OUT.mkdir(parents=True, exist_ok=True)
    n_ep = sum(1 for v in key.values() if v == "episode")
    roster = {"_note": "Blind roster: reviewers see itemId, date, series, window and split only, in reviewOrder. Whether an item is a detector episode or a matched non-alert window is in the sealed key (kept locally; its SHA-256 is below), not shown to reviewers.",
              "seed": SEED, "counts": {"episodes": n_ep, "negatives": len(key) - n_ep}, "items": blind,
              "sealedKeySha256": hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()}
    (RAW / "sealed-key.json").write_text(json.dumps(key, indent=0))
    man = {"_note": "R6-06 immutable dataset manifest (Objective A, Treasury first). Raw CSVs are kept locally (gitignored); verify them by SHA-256.",
           "configVersion": "r6-2026-10-28", "series": series, "seriesUsed": ["2Y", "10Y", "30Y", "2s10s"], "lookbackSessions": LOOKBACK,
           "thresholdsFrom": "lib/grok_the_block/markets/detectors.py treasury_signals at c894915 (unchanged; not tuned)",
           "sessions": len(per), "span": {"from": dates[0], "to": dates[-1]}, "holdout": {"from": HOLDOUT_FROM, "rule": "frozen before labels; never used to choose thresholds"},
           "roster": "roster.json", "labels": "labels.json", "adjudication": "docs/review/ADJUDICATION.md"}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1) + "\n")
    (OUT / "roster.json").write_text(json.dumps(roster, indent=1) + "\n")
    (OUT / "labels.json").write_text(json.dumps({"_note": "EMPTY. Labels are added only by two blind reviewers under ADJUDICATION.md; none have been collected. Nothing here is invented.",
                                                 "reviewers": [], "labels": [], "disagreements": [], "fields": ["itemId", "reviewer", "relevance", "evidenceCorrect", "timestampCorrect", "label", "note"]}, indent=1) + "\n")

    def burden(ps):
        return {k: sum(p[k] for p in ps) for k in ("flag", "baseline10bp", "volNormalized")} | {"sessions": len(ps)}
    dev = [p for p in per if p["date"] < HOLDOUT_FROM]; ho = [p for p in per if p["date"] >= HOLDOUT_FROM]
    res = json.loads((ROOT / "docs/review/eval-results.json").read_text())
    res["objectiveA"] = {"status": "INSUFFICIENT_EVIDENCE", "adjudicatedEvents": 0, "minimumForAPrecisionFigure": 100, "precision": None, "recall": None,
                         "agreement": None, "wilson95": None, "rosterEpisodes": roster["counts"]["episodes"], "matchedNegatives": roster["counts"]["negatives"],
                         "dataset": "docs/review/eval-treasury/manifest.json", "configVersion": "r6-2026-10-28",
                         "baselines": {"note": "alert burden only (flagged sessions); no accuracy without labels", "development": burden(dev), "holdout": burden(ho)},
                         "why": "The dataset, blind roster and empty label sheet exist; no reviewer has labelled anything. Reported as INSUFFICIENT_EVIDENCE, not a percentage. No lead time is claimed."}
    (ROOT / "docs/review/eval-results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({"sessions": len(per), "span": man["span"], "episodes": roster["counts"]["episodes"], "negatives": roster["counts"]["negatives"], "burden": res["objectiveA"]["baselines"]}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
