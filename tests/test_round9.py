"""Round-9 regressions (ROUND9-REVIEW.html, reviewed 75ae493). Test ids follow the review's R9-* table.
Written first and run against the 75ae493 code (docs/review/round9-tests-before-fix.txt), then against the fix.
Labels here are SYNTHETIC estimator inputs only; real label sheets stay empty and no reviewer is invented."""
import hashlib, json, sys
from datetime import date
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib")); sys.path.insert(0, str(R / "skills/signals/scripts")); sys.path.insert(0, str(R / "tools"))
from grok_the_block.markets import timebase as T

EV = R / "docs/review/eval-treasury"
PRIV = R / "tests/fixtures/private/treasury"


def _j(p):
    return json.loads(Path(p).read_text())


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ny(y, m, d, hh=0, mm=0):
    return T.ny_ts(date(y, m, d), hh, mm)


# ---------------- R9-CAL-01: fetched ≠ verified; provisional never fills a verified stratum ----------------

def test_R9_CAL_01_calendar_distinguishes_provisional_fetched_verified():
    c = _j(EV / "release-calendar-r9.json")
    assert c["verificationStates"] == ["VERIFIED", "FETCHED", "PROVISIONAL"]
    for e in c["events"]:
        assert e["verification"] in c["verificationStates"]
        if e["verification"] == "VERIFIED":
            assert e["evidence"]["url"] and e["evidence"]["text"], e
        if e["type"] == "FOMC":
            assert e["verification"] == "VERIFIED"
    if c["blsStatus"] == "NOT_CONFIGURED":
        assert all(e["verification"] == "PROVISIONAL" for e in c["events"] if e["type"] in ("CPI", "NFP"))


def test_R9_CAL_01_bls_fetch_without_parsed_release_time_is_fetched_not_verified():
    import build_release_calendar as B

    class Resp:
        def __init__(self, b): self.b = b
        def read(self): return self.b
    pages = {
        "https://www.bls.gov/bls/news-release/cpi.htm": b'<a href="/news.release/archives/cpi_01152019.htm">x</a><a href="/news.release/archives/cpi_02132019.htm">y</a>',
        "https://www.bls.gov/bls/news-release/empsit.htm": b"",
        "https://www.bls.gov/news.release/archives/cpi_01152019.htm": b"Transmission of material in this release is embargoed until 8:30 a.m. (ET) Friday, January 11, 2019",
        "https://www.bls.gov/news.release/archives/cpi_02132019.htm": b"<html>no embargo line</html>",
    }

    def opener(req, timeout=60):
        return Resp(pages.get(req.full_url, b""))
    out = B.build("ops@test.invalid", opener, log=lambda *a: None)
    cpi = {e["announcementDate"]: e for e in out["events"] if e["type"] == "CPI"}
    # the archive file says 01-15 but the release itself says Jan 11: the release record wins, the mismatch is audited
    assert cpi["2019-01-11"]["verification"] == "VERIFIED" and "embargoed until 8:30" in cpi["2019-01-11"]["evidence"]["text"]
    assert any("2019-01-15" in m["problem"] for m in out["audit"]["mismatches"])
    assert cpi["2019-02-13"]["verification"] == "FETCHED"


def test_R9_CAL_01_provisional_event_never_populates_a_verified_stratum():
    import eval_treasury_r9 as E
    cal = {"events": [
        {"type": "CPI", "verification": "PROVISIONAL", "firstObservationSession": "2024-01-11", "alternativeSession": None},
        {"type": "FOMC", "verification": "VERIFIED", "firstObservationSession": "2024-01-31", "alternativeSession": None},
        {"type": "NFP", "verification": "FETCHED", "firstObservationSession": "2024-02-02", "alternativeSession": None},
        {"type": "CPI", "verification": "PROVISIONAL", "firstObservationSession": "2024-01-31", "alternativeSession": None}]}
    m = E.calendar_status(cal)
    assert m["2024-01-11"] == "RELEASE_PROVISIONAL" and m["2024-02-02"] == "RELEASE_PROVISIONAL"
    assert m["2024-01-31"] == "RELEASE_VERIFIED"
    assert E.calendar_status(cal).get("2024-03-01", "NO_VERIFIED_RELEASE") == "NO_VERIFIED_RELEASE"
    d = _j(EV / "sample-design-r9.json")
    assert {s["calendar"] for s in d["strata"]} <= {"RELEASE_VERIFIED", "RELEASE_PROVISIONAL", "NO_VERIFIED_RELEASE"}
    assert "RELEASE_VERIFIED" in {s["calendar"] for s in d["strata"]} and "RELEASE_PROVISIONAL" in {s["calendar"] for s in d["strata"]}
    assert d["calendarSource"].endswith("release-calendar-r9.json") and d["version"].startswith("r9")
    assert d["coverageLoss"]["provisionalSessions"] > 0


# ---------------- R9-EST-01 / 02: finite-population design variance, stratum coverage ----------------

def _key(pi):
    return {"components": ["PROBABILITY_SAMPLE"], "stratumKey": None, "inclusionProbability": pi}


def test_R9_EST_01_census_stratum_has_zero_design_variance_and_tracks_dont_move_the_estimate():
    import estimators as ES
    design = {"strata": [{"stratumKey": "C", "N": 3, "n": 3, "inclusionProbability": 1.0},
                         {"stratumKey": "S", "N": 100, "n": 4, "inclusionProbability": 0.04}]}
    key, lab = {}, {}
    for i, y in enumerate(["ANOMALY_CONFIRMED", "NOT_ANOMALOUS", "NOT_ANOMALOUS"]):
        key[f"c{i}"] = dict(_key(1.0), stratumKey="C"); lab[f"c{i}"] = y
    for i, y in enumerate(["ANOMALY_CONFIRMED", "NOT_ANOMALOUS", "ANOMALY_CONFIRMED", "NOT_ANOMALOUS"]):
        key[f"s{i}"] = dict(_key(0.04), stratumKey="S"); lab[f"s{i}"] = y
    est = ES.population_share(lab, key, design, "ANOMALY_CONFIRMED")
    assert est["byStratum"]["C"]["varianceContribution"] == 0.0 and est["byStratum"]["C"]["fpc"] == 0.0
    assert est["byStratum"]["S"]["varianceContribution"] > 0
    assert abs(est["estimate"] - (1 + 50) / 103) < 1e-12
    assert est["interval"]["method"].startswith("stratified SRSWOR")
    only_c = {"strata": [design["strata"][0]]}
    e2 = ES.population_share({k: v for k, v in lab.items() if k.startswith("c")}, key, only_c, "ANOMALY_CONFIRMED")
    assert e2["standardError"] == 0.0 and e2["interval"]["low"] == e2["interval"]["high"] == e2["estimate"]
    key["e1"] = {"components": ["EPISODE"], "stratumKey": None, "inclusionProbability": None}; lab["e1"] = "ANOMALY_CONFIRMED"
    key["b1"] = {"components": ["BOUNDARY_CHALLENGE"], "stratumKey": None, "inclusionProbability": None}; lab["b1"] = "ANOMALY_CONFIRMED"
    assert ES.population_share(lab, key, design, "ANOMALY_CONFIRMED")["estimate"] == est["estimate"]


def test_R9_EST_02_unassessable_stratum_is_reported_not_silently_dropped():
    import estimators as ES
    design = {"strata": [{"stratumKey": "A", "N": 50, "n": 2, "inclusionProbability": 0.04},
                         {"stratumKey": "B", "N": 950, "n": 2, "inclusionProbability": 2 / 950}]}
    key = {"a1": dict(_key(0.04), stratumKey="A"), "a2": dict(_key(0.04), stratumKey="A"),
           "b1": dict(_key(2 / 950), stratumKey="B"), "b2": dict(_key(2 / 950), stratumKey="B")}
    lab = {"a1": "ANOMALY_CONFIRMED", "a2": "NOT_ANOMALOUS", "b1": "UNASSESSABLE", "b2": "UNASSESSABLE"}
    est = ES.population_share(lab, key, design, "ANOMALY_CONFIRMED")
    assert est["coverage"]["missingStrata"] == ["B"] and est["coverage"]["fullPopulation"] is False
    assert abs(est["coverage"]["populationCoveredShare"] - 0.05) < 1e-12
    assert est["byStratum"]["B"] == {"N": 950, "n": 2, "labelled": 2, "assessable": 0, "share": None, "fpc": est["byStratum"]["B"]["fpc"], "varianceContribution": None}
    assert est["publishable"] is False and "B" in est["warning"]
    lab["b1"] = "NOT_ANOMALOUS"; lab.pop("b2")
    e2 = ES.population_share(lab, key, design, "ANOMALY_CONFIRMED")
    assert e2["coverage"]["complete"] is False and e2["byStratum"]["B"]["labelled"] == 1   # partial response is visible


# ---------------- R9-VERS-01: one current, hash-linked result record ----------------

def test_R9_VERS_01_current_result_links_r9_hashes_and_history_is_named():
    res = _j(R / "docs/review/eval-results.json")
    assert set(res) == {"_note", "current", "objectiveA", "historical"} and res["current"] == "objectiveA"
    a = res["objectiveA"]
    assert a["evaluationVersion"].startswith("r9") and a["computedAt"]
    for k in ("datasetManifest", "rubric", "roster", "sampleDesign", "releaseCalendar"):
        assert _sha(R / a[k]["file"]) == a[k]["sha256"], k
    assert a["datasetManifest"]["file"].endswith("manifest-r9.json")
    for f in ("precision", "recall", "agreement", "intervals"):
        assert a[f] is None
    assert a["humanReviewedLabels"] == 0 and a["status"] == "INSUFFICIENT_EVIDENCE" and a["labelingGate"] == "BLOCKED"
    assert a["vignetteReviewerCheck"]["set"].endswith("adjudication-vignettes-r8.json") and a["vignetteReviewerCheck"]["vignettes"] == 12
    assert "configVersion" not in a and "rosterR7" not in a
    assert {"r4", "r6", "r7", "r8"} <= set(res["historical"])
    assert res["historical"]["r4"]["configVersion"].startswith("r4")
    m = _j(EV / "manifest-r9.json")
    for f, h in m["priorVersions"].items():
        assert _sha(EV / f) == h, f


# ---------------- R9-TIME-01: observation vs publication, uncertainty near 15:30 ----------------

def test_R9_TIME_01_observation_and_publication_fields_and_boundary_uncertainty():
    import build_release_calendar as B
    a = B.assign_session(ny(2020, 3, 3, 10))
    assert a["firstObservationSession"] == "2020-03-03" and a["sessionAssignment"] == "CLEAR" and a["alternativeSession"] is None
    assert B.assign_session(ny(2020, 3, 15, 17))["firstObservationSession"] == "2020-03-16"
    assert B.assign_session(ny(2024, 9, 18, 14))["firstObservationSession"] == "2024-09-18"
    for hh, mm in ((15, 20), (15, 40)):
        u = B.assign_session(ny(2024, 9, 18, hh, mm))
        assert u["sessionAssignment"] == "UNCERTAIN" and u["firstObservationSession"] == "2024-09-19" and u["alternativeSession"] == "2024-09-18", u
    c = _j(EV / "release-calendar-r9.json")
    assert "approximate" in c["marketObservationApproxAt"] and c["publicationExpectedBy"].startswith("18:00")
    e = next(x for x in c["events"] if x["announcementDate"] == "2020-03-03")
    assert e["marketObservationApproxAt"].startswith("2020-03-03T15:30") and e["publicationExpectedBy"].startswith("2020-03-03T18:00")
    assert "leadTime" not in json.dumps(c)


# ---------------- R9-GATE-01: the existing gate can't PASS without records ----------------

def test_R9_GATE_01_gate_cannot_pass_with_missing_records_or_adjudicator():
    import reviewer_gate as G
    g = _j(EV / "reviewer-gate-r8.json")
    assert g["status"] == "BLOCKED" and G.validate(g) == []
    fake = dict(g, status="PASS")
    errs = G.validate(fake)
    assert any("reviewer" in e for e in errs) and any("adjudicator" in e for e in errs) and any("pilot" in e for e in errs)
    two = dict(fake, reviewersAssigned=True, adjudicatorAssigned=False,
               records={"reviewers": [{"ref": "R-A", "vignettes": 12, "independent": True}, {"ref": "R-B", "vignettes": 11, "independent": True}],
                        "pilot": {"items": 25, "completedBy": ["R-A", "R-B"]}})
    errs = G.validate(two)
    assert any("adjudicator" in e for e in errs) and any("12 vignettes" in e for e in errs)
    assert not list(EV.glob("reviewer-gate-r9*.json")), "the existing gate is completed, not replaced"
    assert _j(EV / "labels-r9.json")["labels"] == []


def test_R9_reporting_files():
    res = (R / "docs/review/ROUND9-RESULTS.md").read_text()
    for s in ("NOT_RUN", "CI: not active", "not tested on a physical device", "Human-reviewed labels: 0"):
        assert s in res, s
    assert "test_round9.py" in (R / "tests/run_all.py").read_text() and "test_round9.py" in (R / "docs/ci/tests.yml").read_text()


if __name__ == "__main__":
    n = fails = 0
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            n += 1
            try:
                v(); print("ok  ", k)
            except Exception as e:  # noqa: BLE001
                fails += 1; print("FAIL", k, "--", type(e).__name__, str(e)[:200])
    print(f"round9: {n - fails}/{n} passed")
    sys.exit(1 if fails else 0)
