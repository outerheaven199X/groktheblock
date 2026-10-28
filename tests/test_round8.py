"""Round-8 regressions (ROUND8-REVIEW.html, reviewed fa56b4e). Test names carry the R8 item.
Written first and run against the fa56b4e code (docs/review/round8-tests-before-fix.txt), then against the fix.
Labels used here are SYNTHETIC test inputs for the estimator only; the real label sheets stay empty."""
import hashlib, json, os, sys
from datetime import date
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib")); sys.path.insert(0, str(R / "tests")); sys.path.insert(0, str(R / "skills/signals/scripts")); sys.path.insert(0, str(R / "tools"))
from grok_the_block.markets import lifecycle as LC, timebase as T
from test_round3 import sig

H = 3600
EV = R / "docs/review/eval-treasury"
PRIV = R / "tests/fixtures/private/treasury"


def _j(p):
    return json.loads(Path(p).read_text())


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ny(y, m, d, hh=0, mm=0):
    return T.ny_ts(date(y, m, d), hh, mm)


# ======================= R8-01 (P0): calendar from primary announcements =======================

def test_R8_01_emergency_fomc_dates_and_sunday_release():
    c = _j(EV / "release-calendar-r8.json")
    f = {e["announcementDate"]: e for e in c["events"] if e["type"] == "FOMC"}
    assert "2020-03-02" not in f, "March 2 was the meeting; the emergency statement was released March 3"
    assert f["2020-03-03"]["class"] == "UNSCHEDULED" and f["2020-03-03"]["announcementTimeET"] == "10:00"
    assert f["2020-03-03"]["firstObservationSession"] == "2020-03-03"
    m15 = f["2020-03-15"]
    assert m15["class"] == "UNSCHEDULED" and m15["weekday"] == "Sunday" and m15["firstObservationSession"] == "2020-03-16"
    assert not any(e["announcementDate"] == "2020-03-16" for e in c["events"]), "Mar 16 is the first observation, not a release"
    assert c["audit"]["mismatches"] == [] and c["audit"]["checked"] == c["counts"]["FOMC"] >= 60
    assert all(e["timeVerified"] for e in f.values())
    assert sum(1 for e in f.values() if e["class"] == "SCHEDULED") == c["counts"]["FOMC"] - 2
    if c["blsStatus"] != "FETCHED":
        assert all(not e["timeVerified"] for e in c["events"] if e["type"] != "FOMC")


def test_R8_01_first_observation_session_dst_weekend_holiday_and_curve_time():
    import build_release_calendar as B
    assert B.first_observation_session(ny(2024, 9, 18, 14)) == "2024-09-18"          # 14:00 EDT, before the 15:30 curve
    assert B.first_observation_session(ny(2024, 1, 31, 14)) == "2024-01-31"          # 14:00 EST
    assert B.first_observation_session(ny(2020, 3, 15, 17)) == "2020-03-16"          # Sunday
    assert B.first_observation_session(ny(2024, 3, 29, 8, 30)) == "2024-04-01"       # Good Friday: bond market closed
    assert B.first_observation_session(ny(2024, 9, 18, 15, 30)) == "2024-09-19"      # at/after the curve time → next session
    assert B.first_observation_session(ny(2026, 4, 3, 8, 30)) == "2026-04-03"        # Good Friday 2026: NYSE shut, Treasury curve published
    assert T.is_session(date(2025, 1, 9), "bond") and not T.is_session(date(2025, 1, 9), "equity")


def test_R8_01_sampling_uses_the_corrected_calendar():
    d = _j(EV / "sample-design-r8.json")
    assert d["calendarSource"].endswith("release-calendar-r8.json") and d["calendarKey"] == "firstObservationSession"
    assert d["version"].startswith("r8")


# ======================= R8-02 (P0): frame compatible with the 250-session reference =======================

def test_R8_02_frame_requires_250_prior_changes_and_reports_eligibility():
    d = _j(EV / "sample-design-r8.json")
    assert d["frame"]["minPriorValidChanges"] == 250
    el = d["eligibility"]
    assert {"byYearTenor", "byComponent"} <= set(el)
    for comp in ("EPISODE", "QUIET_CONTROL", "PROBABILITY_SAMPLE", "BOUNDARY_CHALLENGE"):
        assert {"eligible", "ineligible"} <= set(el["byComponent"][comp])
    assert el["byComponent"]["PROBABILITY_SAMPLE"]["ineligible"] == 0, "population items all meet the reference rule"
    m = _j(EV / "manifest-r8.json")
    assert any(s["year"] == 2018 and s["sha256"] for s in m["series"]), "earlier history fetched from treasury.gov"


def test_R8_02_every_sampled_item_has_250_valid_prior_changes_when_data_present():
    _j(EV / "sample-design-r8.json")
    if not (PRIV / "sealed-key-r8.json").exists():
        print("     (private data absent: structural checks only)"); return
    import eval_treasury_r8 as E
    rows = E.load_rows()
    key = _j(PRIV / "sealed-key-r8.json")
    roster = {i["itemId"]: i for i in _j(EV / "roster-r8.json")["items"]}
    for iid, k in key.items():
        n = E.prior_valid_changes(rows, roster[iid]["date"], roster[iid]["series"].split(":")[1])
        assert (n >= 250) == k["referenceEligible"], (iid, n)
        if "PROBABILITY_SAMPLE" in k["components"]:
            assert n >= 250


# ======================= R8-03: estimators kept separate =======================

def test_R8_03_weights_recomputed_from_frozen_frame_match_sealed_key():
    _j(EV / "sample-design-r8.json")
    if not (PRIV / "sealed-key-r8.json").exists():
        print("     (private data absent)"); return
    import eval_treasury_r8 as E
    frame, strata = E.build_frame(E.load_rows())
    pi = {s["stratumKey"]: s["inclusionProbability"] for s in _j(EV / "sample-design-r8.json")["strata"]}
    key = _j(PRIV / "sealed-key-r8.json")
    roster = {i["itemId"]: i for i in _j(EV / "roster-r8.json")["items"]}
    byw = {(w["date"], w["tenor"]): w for w in frame}
    n = 0
    for iid, k in key.items():
        if "PROBABILITY_SAMPLE" in k["components"]:
            w = byw[(roster[iid]["date"], roster[iid]["series"].split(":")[1])]
            assert k["stratumKey"] == w["stratumKey"] and abs(k["inclusionProbability"] - pi[w["stratumKey"]]) < 1e-12
            n += 1
        else:
            assert k.get("inclusionProbability") is None
    assert n == _j(EV / "sample-design-r8.json")["sampleSize"]


def test_R8_03_weighted_estimator_uses_only_the_probability_sample():
    import estimators as ES
    design = {"strata": [{"stratumKey": "A", "N": 100, "n": 2, "inclusionProbability": 0.02}, {"stratumKey": "B", "N": 900, "n": 2, "inclusionProbability": 2 / 900}]}
    key = {"i1": {"components": ["PROBABILITY_SAMPLE"], "stratumKey": "A", "inclusionProbability": 0.02},
           "i2": {"components": ["PROBABILITY_SAMPLE"], "stratumKey": "A", "inclusionProbability": 0.02},
           "i3": {"components": ["PROBABILITY_SAMPLE", "EPISODE"], "stratumKey": "B", "inclusionProbability": 2 / 900},
           "i4": {"components": ["PROBABILITY_SAMPLE"], "stratumKey": "B", "inclusionProbability": 2 / 900},
           "e1": {"components": ["EPISODE"], "stratumKey": None, "inclusionProbability": None},
           "q1": {"components": ["QUIET_CONTROL"], "stratumKey": None, "inclusionProbability": None},
           "b1": {"components": ["BOUNDARY_CHALLENGE"], "stratumKey": None, "inclusionProbability": None}}
    lab = {"i1": "ANOMALY_CONFIRMED", "i2": "ANOMALY_CONFIRMED", "i3": "NOT_ANOMALOUS", "i4": "NOT_ANOMALOUS",
           "e1": "ANOMALY_CONFIRMED", "q1": "ANOMALY_CONFIRMED", "b1": "ANOMALY_CONFIRMED"}
    est = ES.population_share(lab, key, design, "ANOMALY_CONFIRMED", reps=400, seed=1)
    assert abs(est["estimate"] - 0.1) < 1e-12, est         # (100·1 + 900·0) / 1000, not the unweighted 5/7
    assert est["itemsUsed"] == 4 and est["excluded"] == {"EPISODE": 1, "QUIET_CONTROL": 1, "BOUNDARY_CHALLENGE": 1}
    # R9-02 amendment: the bootstrap was replaced by a finite-population (SRSWOR) design variance
    assert est["interval"]["method"].startswith("stratified SRSWOR") and est["interval"]["low"] <= 0.1 <= est["interval"]["high"]
    lab2 = dict(lab, e1="NOT_ANOMALOUS", q1="NOT_ANOMALOUS", b1="NOT_ANOMALOUS")
    assert ES.population_share(lab2, key, design, "ANOMALY_CONFIRMED", reps=400, seed=1)["estimate"] == est["estimate"]
    assert ES.population_share(lab, key, design, "ANOMALY_CONFIRMED", reps=400, seed=1) == est   # deterministic
    try:
        ES.pooled_share(lab, "ANOMALY_CONFIRMED"); raise AssertionError("pooled estimate must be refused")
    except ES.EstimatorError:
        pass


# ======================= R8-04: the reference percentile, computed in code =======================

def test_R8_04_reference_edge_cases():
    import reference as RF
    base = [1.0 + 0.01 * (i % 7) for i in range(260)]   # synthetic series in percent
    assert RF.tail_flag(base[:200], 199)["status"] == "UNASSESSABLE"                 # <250 prior changes
    holes = list(base); holes[100] = None; holes[150] = None
    r = RF.tail_flag(holes, 253)   # 252 prior changes, 4 of them touch a null → 248 valid
    assert r["status"] == "UNASSESSABLE" and r["priorValidChanges"] < 250             # nulls don't count as changes
    assert RF.percentile([0, 10], 0.975) == 9.75 and RF.percentile([1, 2, 3, 4], 0.5) == 2.5   # linear interpolation
    s = [0.0] * 252
    for i in range(1, 252):
        s[i] = s[i - 1] + (0.01 if i % 2 else -0.01)                                # |change| = 1bp always
    s.append(s[-1] + 0.01)
    on = RF.tail_flag(s, 252)
    assert on["cutoffBp"] == 1.0 and on["changeBp"] == 1.0 and on["status"] == "YES"  # exactly on the cutoff counts
    s2 = s[:-1] + [s[-2] + 0.5]
    assert RF.tail_flag(s2, 252)["status"] == "YES" and RF.tail_flag(s2, 252)["changeBp"] == 50.0
    s3 = s[:-1] + [s[-2] + 0.001]
    assert RF.tail_flag(s3, 252)["status"] == "NO"


def test_R8_04_rubric_describes_a_statistical_tail_not_relevance():
    t = _j(R / "docs/review/adjudication-r8.json")
    a = t["axes"]["anomaly"]
    assert a["computedBy"].endswith("reference.py") and a["reviewersAssess"] is False
    assert "statistical tail" in a["measures"] and "not" in a["measures"]
    assert t["sensitivityAnalyses"]["quantiles"] == [0.95, 0.99] and t["sensitivityAnalyses"]["preregistered"] is True
    for c in ("market relevance", "hit rate", "predictive accuracy"):
        assert c in t["doNotClaim"]
    assert {"integrity", "context"} == set(t["reviewerAxes"])


# ======================= R8-05: reviewer calibration gate =======================

def test_R8_05_label_sheet_stays_empty_until_the_gate_passes():
    g = _j(EV / "reviewer-gate-r8.json")
    assert g["status"] == "BLOCKED" and g["reviewersAssigned"] is False and g["adjudicatorAssigned"] is False
    assert g["vignetteCheck"]["status"] == "NOT_RUN" and g["pilot"]["purpose"] == "calibration, not validation"
    assert 20 <= g["pilot"]["size"] <= 30
    assert _j(EV / "labels-r8.json")["labels"] == []
    assert _j(R / "docs/review/eval-results.json")["objectiveA"]["labelingGate"] == "BLOCKED"


def test_R8_05_more_vignettes_cover_the_confusing_cases():
    import adjudication as A
    v = _j(R / "tests/fixtures/adjudication-vignettes-r8.json")["vignettes"]
    cats = {x["category"] for x in v}
    assert {"holiday", "false-availability", "unexplained-volatility", "borderline", "mixed-integrity-context"} <= cats and len(v) >= 9
    for x in v:
        got = A.decide(x["axes"], table="r8")
        assert (got["primary"], got["context"]) == (x["intended"]["primary"], x["intended"]["context"]), x["id"]


# ======================= R8-06: three separate analysis tracks =======================

def test_R8_06_tracks_are_separate_and_boundary_set_is_diagnostic():
    d = _j(EV / "sample-design-r8.json")
    t = d["tracks"]
    assert set(t) == {"population", "emittedEpisodes", "boundaryChallenge"}
    assert t["population"]["component"] == "PROBABILITY_SAMPLE" and t["population"]["designWeights"] is True
    b = t["boundaryChallenge"]
    assert b["diagnosticOnly"] is True and b["populationWeight"] is None and b["ratioRange"] == [0.75, 1.25]
    assert b["size"] > 0 and all("selectionProbability" in s for s in b["strata"])
    r = _j(EV / "roster-r8.json")
    assert set(r["counts"]) == {"EPISODE", "QUIET_CONTROL", "PROBABILITY_SAMPLE", "BOUNDARY_CHALLENGE"}
    a = _j(R / "docs/review/eval-results.json")["objectiveA"]
    assert a["pooledEstimateAllowed"] is False and "recall" in a["neverFrom"]["QUIET_CONTROL"]


def test_R8_06_prior_versions_preserved():
    m = _j(EV / "manifest-r8.json")
    for f in ("roster.json", "roster-r7.json", "sample-design-r7.json", "release-calendar.json", "manifest-r7.json"):
        assert m["priorVersions"][f] == _sha(EV / f)
    assert m["roster"]["sha256"] == _sha(EV / "roster-r8.json") and m["sampleDesign"]["sha256"] == _sha(EV / "sample-design-r8.json")
    assert m["labelMapping"] == "no labels existed in any prior version; nothing carried forward"


# ======================= R8-07: provisional clocks, no placeholder contact =======================

def test_R8_07_calendar_fetch_without_contact_sends_no_placeholder_and_skips_bls(monkeypatch=None):
    import build_release_calendar as B
    sent = []

    class Resp:
        def __init__(self, b): self.b = b
        def read(self): return self.b

    def opener(req, timeout=60):
        sent.append((req.full_url, req.get_header("User-agent")))
        if "fomccalendars" in req.full_url or "fomchistorical" in req.full_url:
            return Resp(b"")
        return Resp(b"")
    out = B.build(None, opener, log=lambda *a: None)
    assert out["blsStatus"] == "NOT_CONFIGURED"
    assert not any("bls.gov" in u for u, _ in sent)
    assert not any("example.com" in (ua or "") or "nick@" in (ua or "") for _, ua in sent)
    src = (R / "tools/build_release_calendar.py").read_text()
    assert "nick@example.com" not in src and "GTB_CONTACT" in src
    sent.clear()
    B.build("ops@test.invalid", opener, log=lambda *a: None)
    assert any("bls.gov" in u and "ops@test.invalid" in ua for u, ua in sent)


def test_R8_07_clocks_are_labelled_provisional_and_unknown_cadence_is_unknown():
    for s, i in (("options", "SPY"), ("stablecoins", None), ("treasury", "2Y"), ("macro", "EURUSD=X")):
        assert T.cadence(s, i).startswith("provisional"), s
    assert "unknown" in T.cadence("newsource") and T.expected_update("newsource", None, ny(2027, 1, 20, 11), 1) is None


def test_R8_07_missed_option_session_holiday_reopening_slow_provider():
    K = "options:SPY:IV_MOVE"

    def run(last, checks, tel_status="UNAVAILABLE"):
        st = {"incidents": {}, "lastSuccessAt": last - 600}
        s = sig(K, "options", "HIGH"); s["observation"] = {"sourceStatus": "HEALTHY", "temporalStatus": "OK", "granularity": "intraday"}
        LC.step(st, [s], {K: {"ratio": 2.0, "valid": True}}, {"options": "HEALTHY"}, last)
        out = {}
        for t in checks:
            r = LC.step(st, [], {}, {"options": tel_status}, t)
            out[t] = (st["incidents"][K]["state"], r["alerts"])
        return out
    # a whole session of missed snapshots (Tue close → Wed): UNCONFIRMED on Wed's 4th expected snapshot (13:00)
    tue = ny(2027, 1, 19, 16, 5)
    o = run(tue, [ny(2027, 1, 20, 12, 30), ny(2027, 1, 20, 13, 5)])
    assert o[ny(2027, 1, 20, 12, 30)][0] != "UNCONFIRMED" and o[ny(2027, 1, 20, 13, 5)][0] == "UNCONFIRMED"
    # holiday reopening: Fri 15:00 before MLK; Mon closed; Tue reopening's 3rd slot (12:00) is the 4th expected snapshot
    fri = ny(2027, 1, 15, 15)
    o = run(fri, [ny(2027, 1, 18, 23), ny(2027, 1, 19, 11, 30), ny(2027, 1, 19, 12, 5)])
    assert o[ny(2027, 1, 18, 23)][0] != "UNCONFIRMED" and o[ny(2027, 1, 19, 11, 30)][0] != "UNCONFIRMED"
    assert o[ny(2027, 1, 19, 12, 5)][0] == "UNCONFIRMED"
    for v in list(o.values()):
        assert v[0] != "RESOLVED" and v[1] == []
    # a provider that updates less often than expected: STALE ages it (never RESOLVED, no new finding)
    o = run(tue, [ny(2027, 1, 20, 13, 5), ny(2027, 1, 22, 16)], tel_status="STALE")
    assert all(v[0] in ("UNCONFIRMED", "ARCHIVED_UNRESOLVED") and v[1] == [] for v in o.values()), o


# ======================= R8-08: operational checks stated =======================

def test_R8_08_ci_and_devices_stated():
    ci = (R / "docs/ci/tests.yml").read_text()
    assert "test_round8.py" in ci and "STAGED, NOT ACTIVE" in ci
    res = (R / "docs/review/ROUND8-RESULTS.md").read_text()
    assert "CI: not active" in res and "not tested on a physical device" in res
    assert "test_round8.py" in (R / "tests/run_all.py").read_text()


if __name__ == "__main__":
    n = fails = 0
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            n += 1
            try:
                v(); print("ok  ", k)
            except Exception as e:  # noqa: BLE001
                fails += 1; print("FAIL", k, "--", type(e).__name__, str(e)[:200])
    print(f"round8: {n - fails}/{n} passed")
    sys.exit(1 if fails else 0)
