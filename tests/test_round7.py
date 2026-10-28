"""Round-7 regressions (ROUND7-REVIEW.html, reviewed 5fabd64). Test names carry the R7 item.
Written first and run against the 5fabd64 code (docs/review/round7-tests-before-fix.txt), then against the fix.
All market inputs are SYNTHETIC; no label is produced or invented by any test."""
import hashlib, json, subprocess, sys
from datetime import date, datetime
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib")); sys.path.insert(0, str(R / "tests")); sys.path.insert(0, str(R / "skills/signals/scripts"))
from grok_the_block.markets import lifecycle as LC, timebase as T
from test_round3 import sig

H = 3600
EV = R / "docs/review/eval-treasury"


def _j(p):
    return json.loads(Path(p).read_text())


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ======================= R7-01 (P0): orthogonal adjudication axes =======================

def test_R7_01_frozen_decision_table_is_versioned_and_hash_recorded():
    t = _j(R / "docs/review/adjudication-r7.json")
    assert t["version"].startswith("r7") and t["frozenBeforeLabels"] is True
    assert set(t["axes"]) == {"anomaly", "integrity", "context"}
    assert set(t["axes"]["context"]["values"]) == {"SCHEDULED", "DOCUMENTED_UNSCHEDULED", "UNEXPLAINED", "UNAVAILABLE"}
    assert "detector" in t["axes"]["anomaly"]["notTheDetectorRule"].lower()
    md = (R / "docs/review/ADJUDICATION.md").read_text()
    assert _sha(R / "docs/review/adjudication-r7.json") in md, "the table's hash is recorded in the rubric"
    assert any("precision" in x for x in t["doNotReport"])


def test_R7_01_four_vignettes_get_the_intended_labels_and_cause_is_not_validity():
    import adjudication as A
    v = _j(R / "tests/fixtures/adjudication-vignettes-r7.json")["vignettes"]
    assert len(v) == 4
    for x in v:
        got = A.decide(x["axes"])
        assert (got["primary"], got["context"]) == (x["intended"]["primary"], x["intended"]["context"]), (x["id"], got)
    by = {x["id"]: A.decide(x["axes"]) for x in v}
    assert by["genuine-anomaly-no-cause"]["primary"] != "FALSE", "an unexplained valid anomaly is not FALSE"
    assert by["wrong-timestamp-real-event"]["primary"] == "FALSE", "an availability/timestamp error is FALSE regardless of news"
    # the context axis never changes the primary label
    for ctx in ("SCHEDULED", "DOCUMENTED_UNSCHEDULED", "UNEXPLAINED", "UNAVAILABLE"):
        assert A.decide({"anomaly": "YES", "integrity": "OK", "context": ctx})["primary"] == "ANOMALY_CONFIRMED"


def test_R7_01_objective_a_uses_r7_rubric_and_reports_no_precision():
    a = _j(R / "docs/review/eval-results.json")["objectiveA"]
    assert a["rubricVersion"][:2] in ("r7", "r8") and a["precision"] is None and a["adjudicatedEvents"] == 0
    assert a["vignetteReviewerCheck"]["status"] == "NOT_RUN"   # R8 amendment: rubricVersion may now be r8 (supersedes r7)   # two independent reviewers have not done it
    assert _j(EV / "labels.json")["labels"] == [] and _j(EV / "labels-r7.json")["labels"] == []


# ======================= R7-02: detector-independent probability sample =======================

def test_R7_02_r6_roster_kept_unchanged_as_quiet_control_record():
    m = _j(EV / "manifest-r7.json")
    prior = m["priorRosters"]["roster.json"]
    assert prior["sha256"] == "5e54bf1010260e5e0d43cf6c79241ea48161ef056bf2f081374c2b0cb350f22a" == _sha(EV / "roster.json")
    assert prior["role"] == "historical record (r6); its negatives are the QUIET_CONTROL stratum, never used for recall"


def test_R7_02_probability_sample_has_denominators_inclusion_probabilities_and_strata():
    d = _j(EV / "sample-design-r7.json")
    assert d["selectionUsesDetectorOutput"] is False and d["seed"]
    assert d["frame"]["windows"] > 5000
    st = d["strata"]
    assert all({"tenor", "split", "calendar", "volRegime", "N", "n", "inclusionProbability"} <= set(s) for s in st)
    for s in st:
        assert abs(s["inclusionProbability"] - s["n"] / s["N"]) < 1e-9 and 0 < s["n"] <= s["N"]
    assert {s["calendar"] for s in st} == {"RELEASE", "NO_RELEASE"} and {s["volRegime"] for s in st} == {"LOW", "MID", "HIGH"}
    assert {s["tenor"] for s in st} == {"2Y", "10Y", "30Y", "2s10s"} and {s["split"] for s in st} == {"development", "holdout"}
    assert sum(s["n"] for s in st) == d["sampleSize"]
    dt = d["detectorStatusInSample"]  # aggregate only; per-item status stays sealed
    assert dt["belowThreshold"] > 0 and dt["nearThreshold"] > 0
    assert "distributionTable" in d and d["calendarSource"].endswith("release-calendar.json")


def test_R7_02_new_roster_is_blind_frozen_and_hashed():
    r = _j(EV / "roster-r7.json")
    assert r["version"].startswith("r7") and r["sealedKeySha256"]
    for e in r["items"]:
        assert set(e) == {"itemId", "date", "series", "window", "split"}
    assert {"EPISODE", "QUIET_CONTROL", "PROBABILITY_SAMPLE"} == set(r["counts"])
    m = _j(EV / "manifest-r7.json")
    assert m["roster"]["sha256"] == _sha(EV / "roster-r7.json")
    assert _j(EV / "release-calendar.json")["counts"]["FOMC"] > 40


# ======================= R7-03: source-specific cadence =======================

def ny(y, m, d, hh=0, mm=0):
    return T.ny_ts(date(y, m, d), hh, mm)


def test_R7_03_equities_early_close_and_treasury_thanksgiving():
    assert T.expected_update("equities", "SPY", ny(2026, 11, 25, 16, 30), 1) == ny(2026, 11, 27, 13, 15)   # Thanksgiving Thu shut, Fri closes 13:00 (+15m)
    assert T.expected_update("equities", "SPY", ny(2026, 11, 24, 16, 30), 1) == ny(2026, 11, 25, 16, 15)
    last = ny(2026, 11, 25, 18)
    assert T.expected_update("treasury", "2Y", last, 1) == ny(2026, 11, 27, 18)
    unc, arc = LC.deadlines("treasury", last)
    assert unc >= last + 96 * H and arc >= last + 168 * H     # fail-safe floors kept for Treasury


def test_R7_03_options_open_session_vs_long_weekend():
    wed = ny(2027, 1, 20, 11)
    unc, arc = LC.deadlines("options", wed, "SPY")
    assert unc <= ny(2027, 1, 20, 16, 15), "missing intraday snapshots during an open session become UNCONFIRMED the same session"
    fri = ny(2027, 1, 15, 15)  # Mon 2027-01-18 MLK: exchange closed
    unc, arc = LC.deadlines("options", fri, "SPY")
    assert unc >= ny(2027, 1, 19, 10), "a closed exchange over a long weekend is not a missed snapshot"
    assert arc > unc


def test_R7_03_stablecoins_run_on_a_7_day_calendar():
    fri = ny(2027, 1, 15, 12)
    unc, arc = LC.deadlines("stablecoins", fri)
    assert unc <= ny(2027, 1, 17, 12), "Sunday delay counts: stablecoin aggregates are not NYSE-bound"
    assert T.expected_update("stablecoins", None, fri, 1) == fri + 24 * H


def test_R7_03_fx_uses_london_day_end_across_dst_mismatch_and_vix_futures_clocks():
    assert T.expected_update("macro", "EURUSD=X", ny(2027, 1, 11, 12), 1) == ny(2027, 1, 11, 19)    # GMT/EST: London midnight = 19:00 ET
    assert T.expected_update("macro", "EURUSD=X", ny(2027, 3, 15, 12), 1) == ny(2027, 3, 15, 20)    # US DST, UK not yet: 20:00 ET
    assert T.expected_update("macro", "EURUSD=X", ny(2027, 4, 5, 12), 1) == ny(2027, 4, 5, 19)      # both DST: 19:00 ET
    assert T.expected_update("macro", "^VIX", ny(2027, 1, 11, 12), 1) == ny(2027, 1, 11, 16, 15)
    assert T.expected_update("macro", "CL=F", ny(2027, 1, 11, 12), 1) == ny(2027, 1, 11, 17)


def test_R7_03_cross_mixing_hourly_options_and_daily_treasury_ages_on_the_missing_member():
    KC = "cross:rates:CONVERGENCE"
    wed = ny(2027, 1, 20, 11)
    for missing, hot, expect in (("options", "treasury:2Y:YIELD_MOVE", "UNCONFIRMED"), ("treasury", "options:SPY:IV_MOVE", "ACTIVE")):
        st = {"incidents": {}, "lastSuccessAt": wed - 600}
        LC.step(st, [sig(KC, "cross", members=["options:SPY:IV_MOVE", "treasury:2Y:YIELD_MOVE"])], {}, {"options": "HEALTHY", "treasury": "HEALTHY"}, wed)
        tel = {"options": "HEALTHY", "treasury": "HEALTHY"}; tel[missing] = "UNAVAILABLE"
        for h in (1, 2, 3, 4, 5):
            LC.step(st, [], {hot: {"ratio": 1.5, "valid": True}}, tel, wed + h * H)
        inc = st["incidents"][KC]
        assert (inc["state"] == "UNCONFIRMED") == (expect == "UNCONFIRMED") and inc["state"] in ("NEW", "ACTIVE", "UNCONFIRMED"), (missing, inc["state"])
        assert inc["state"] != "RESOLVED"
        if expect == "UNCONFIRMED":
            u = [h for h in inc["history"] if h["event"] == "UNCONFIRMED"][-1]
            assert "expected update" in u["note"] and "hourly while the exchange is open" in u["note"], u


# ======================= R7-04: final purge receipt distinct from the rehearsal =======================

def test_R7_04_rehearsal_and_final_receipts_are_distinct():
    reh = _j(R / "docs/review/history-purge-rehearsal.json")
    assert reh["phase"] == "REHEARSAL" and reh["disposableClone"] is True and reh["pushed"] is False
    assert not (R / "docs/review/history-purge-verification.json").exists()
    fin = _j(R / "docs/review/history-purge-final.json")
    assert fin["phase"] == "FINAL_FORCE_PUSH" and fin["pushed"] is True and fin["ownerApproved"] is True
    refs = {r["ref"]: r for r in fin["refs"]}
    assert set(refs) == {"refs/heads/main", "refs/heads/ui/investigation-workbench-20261028", "refs/heads/ui/reference-dark-preserved-20261028"}
    assert refs["refs/heads/main"]["old"].startswith("fd858c0") and refs["refs/heads/main"]["new"].startswith("aa4de42")
    assert all(len(r["old"]) == 40 and len(r["new"]) == 40 for r in fin["refs"])
    assert fin["scan"]["before"]["findings"] == 177 and fin["scan"]["after"]["findings"] == 0
    assert fin["mainTreeEqual"] is True and fin["freshClone"]["findings"] == 0 and fin["prHead"]["new"].startswith("b9ec827")
    lim = " ".join(fin["limitations"]).lower()
    assert "fork" in lim and "clone" in lim and "cache" in lim and "rotate" in lim
    ok = subprocess.run(["git", "-C", str(R), "merge-base", "--is-ancestor", refs["refs/heads/main"]["new"], "HEAD"]).returncode == 0
    assert ok, "the recorded new main is in this history"


def test_R7_04_docs_separate_historical_phases():
    doc = (R / "docs/review/HISTORY-EXPOSURE.md").read_text()
    assert "Phase 1: rehearsal" in doc and "Phase 2: final force-push" in doc and "history-purge-final.json" in doc
    r6 = (R / "docs/review/ROUND6-RESULTS.md").read_text()
    assert "superseded" in r6.lower() and "history-purge-final.json" in r6


# ======================= R7-05 / R7-06: CI and devices stated honestly =======================

def test_R7_05_ci_staged_with_round7_and_results_say_not_active():
    ci = (R / "docs/ci/tests.yml").read_text()
    assert "test_round7.py" in ci and "STAGED, NOT ACTIVE" in ci
    res = (R / "docs/review/ROUND7-RESULTS.md").read_text()
    assert "CI: not active" in res and "workflow" in res and "not tested on a physical device" in res
    run = (R / "tests/run_all.py").read_text()
    assert "test_round7.py" in run


if __name__ == "__main__":
    n = fails = 0
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            n += 1
            try:
                v(); print("ok  ", k)
            except Exception as e:  # noqa: BLE001
                fails += 1; print("FAIL", k, "--", type(e).__name__, str(e)[:200])
    print(f"round7: {n - fails}/{n} passed")
    sys.exit(1 if fails else 0)
