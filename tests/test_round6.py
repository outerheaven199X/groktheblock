"""Round-6 regressions (ROUND6-REVIEW.html, reviewed c894915). Test names carry the R6 item.
Written first and run against the c894915 code (docs/review/round6-tests-before-fix.txt), then against the fix.
All market inputs are SYNTHETIC. NOW = 1_800_000_000 = Fri 2027-01-15 03:00 ET; Mon 2027-01-18 is an NYSE/bond holiday (MLK)."""
import hashlib, json, subprocess, sys
from datetime import date
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib")); sys.path.insert(0, str(R / "tests")); sys.path.insert(0, str(R / "tests/fixtures/contracts"))
from grok_the_block.markets import detectors as X, entities as EN, lifecycle as LC, timebase as T
from test_round3 import fake, sig, NOW
import test_round5 as R5

H = 3600
K = "equities:SYNX:RETURN_VS_REALIZED_VOL"


def _eq(sev="HIGH", status="HEALTHY", temporal="OK"):
    s = sig(K, "equities", sev)
    s["observation"] = {"sourceStatus": status, "temporalStatus": temporal, "granularity": "daily"}
    return s


# ======================= R6-01 (P0): present-but-invalid observations must age =======================

def test_R6_01_repeated_stale_present_equity_signal_ages_on_daily_cadence_never_refreshes():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    LC.step(st, [_eq()], {K: {"ratio": 2.0, "valid": True}}, {"equities": "HEALTHY"}, NOW)
    LC.step(st, [_eq()], {K: {"ratio": 2.0, "valid": True}}, {"equities": "HEALTHY"}, NOW + 600)
    assert st["incidents"][K]["state"] == "ACTIVE"
    conf = st["incidents"][K]["lastConfirmedAt"]
    states, alerts = {}, []
    for h in (24, 72, 96, 168, 240):  # same STALE present signal; probe also flagged invalid (incomplete bar)
        r = LC.step(st, [_eq(status="STALE")], {K: {"ratio": None, "valid": False, "reason": "INCOMPLETE"}}, {"equities": "STALE"}, NOW + h * H)
        alerts += r["alerts"]
        states[h] = st["incidents"][K]["state"]
        assert st["incidents"][K]["lastConfirmedAt"] == conf, h
    assert alerts == []
    # daily cadence: Fri 03:00 last valid → Mon holiday → next expected publication Tue 18:00 ET, +24h grace → UNCONFIRMED from Wed 18:00 (+135h)
    assert states[24] == "ACTIVE" and states[72] == "ACTIVE" and states[96] == "ACTIVE", states
    assert states[168] == "UNCONFIRMED", states
    assert states[240] == "ARCHIVED_UNRESOLVED", states
    r = LC.step(st, [_eq()], {K: {"ratio": 2.0, "valid": True}}, {"equities": "HEALTHY"}, NOW + 250 * H)
    inc = st["incidents"][K]
    assert inc["episode"] == 2 and [a["alertReason"] for a in r["alerts"]] == ["NEW_EPISODE"]


def test_R6_01_repeated_stale_present_solana_event_leaves_observed():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    a = R5._alert("SigOld1", NOW - 72 * H)
    chk = NOW - 71 * H  # the watch report was checked 71h ago: still current (Solana limit 72h) when first scanned
    R5._sol_scan(st, [R5._report([a], chk)], NOW)
    k = next(iter(st["incidents"]))
    assert st["incidents"][k]["state"] == "OBSERVED"
    conf = st["incidents"][k]["lastConfirmedAt"]
    states, alerts = {}, []
    for h in (24, 72, 96, 168):  # the same report is never refreshed → a STALE present signal on every run
        _, res = R5._sol_scan(st, [R5._report([a], chk)], NOW + h * H)
        alerts += res["alerts"]; states[h] = st["incidents"][k]["state"]
        assert st["incidents"][k]["lastConfirmedAt"] == conf
    assert alerts == []
    # c894915: OBSERVED forever. Now: UNCONFIRMED at once; ARCHIVED_UNRESOLVED 2×72h after the report's check time (NOW+73h)
    assert states == {24: "UNCONFIRMED", 72: "UNCONFIRMED", 96: "ARCHIVED_UNRESOLVED", 168: "ARCHIVED_UNRESOLVED"}, states
    # a fresh report with only the old signature: no alert; with a NEW signature: a new episode
    _, res = R5._sol_scan(st, [R5._report([a], NOW + 170 * H)], NOW + 170 * H)
    assert res["alerts"] == []
    b = R5._alert("SigNew2", NOW + 170 * H - 600)
    _, res = R5._sol_scan(st, [R5._report([a, b], NOW + 171 * H)], NOW + 171 * H)
    assert st["incidents"][k]["episode"] == 2 and [x["alertReason"] for x in res["alerts"]] == ["NEW_EPISODE"]


# ======================= R6-02: cross incidents age on the slowest member's publication clock =======================

def test_R6_02_cross_with_daily_treasury_member_does_not_archive_over_a_holiday_weekend():
    fri = T.ny_ts(date(2027, 1, 15), 15, 0)
    st = {"incidents": {}, "lastSuccessAt": fri - 600}
    KC = "cross:fed-policy:CONVERGENCE"
    LC.step(st, [sig(KC, "cross", members=["treasury:2Y:YIELD_MOVE", "kalshi:FED:ODDS"])], {}, {"treasury": "HEALTHY", "kalshi": "HEALTHY"}, fri)
    seen = {}
    for h in range(6, 200, 6):  # Treasury unavailable through MLK Monday and beyond; Kalshi polled normally and still hot
        LC.step(st, [], {"kalshi:FED:ODDS": {"ratio": 1.5, "valid": True}}, {"treasury": "UNAVAILABLE", "kalshi": "HEALTHY"}, fri + h * H)
        seen[h] = st["incidents"][KC]["state"]
    assert seen[72] not in ("UNCONFIRMED", "ARCHIVED_UNRESOLVED", "RESOLVED"), seen[72]   # Mon 15:00: no archive from 72 wall-clock hours
    assert seen[120] not in ("UNCONFIRMED", "ARCHIVED_UNRESOLVED"), seen[120]          # Wed 15:00: still inside Tue publication + grace
    assert seen[126] == "UNCONFIRMED", seen[126]                                         # Wed 21:00 > Tue 18:00 + 24h
    assert seen[168] == "UNCONFIRMED" and seen[174] == "ARCHIVED_UNRESOLVED", (seen[168], seen[174])
    assert "RESOLVED" not in seen.values()


# ======================= R6-03: partial member overlap is not silently one event =======================

def _c(members, inst=None):
    s = sig("cross:fed-policy:CONVERGENCE", "cross", members=members)
    if inst:
        s["metrics"]["eventInstance"] = inst
    return s


def _run(st, s, at, probes=None):
    return LC.step(st, [s], probes or {}, {"treasury": "HEALTHY", "kalshi": "HEALTHY", "polymarket": "HEALTHY"}, at)


def test_R6_03_partial_overlap_same_identified_event_continues_and_keeps_active_b():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    E1 = "fed-policy:FED_DECISION:cut:2027-03"
    _run(st, _c(["treasury:2Y:A", "kalshi:FED:B"], E1), NOW)
    r = _run(st, _c(["treasury:2Y:A", "polymarket:FED:C"], E1), NOW + 600, {"kalshi:FED:B": {"ratio": 1.4, "valid": True}})
    inc = st["incidents"]["cross:fed-policy:CONVERGENCE"]
    assert inc["episode"] == 1 and inc["continuity"] == "IDENTIFIED_EVENT"
    assert "kalshi:FED:B" in inc["members"], "an active B is not lost"
    mh = inc["memberHistory"][-1]
    assert mh["added"] == ["polymarket:FED:C"] and mh["dropped"] == ["kalshi:FED:B"] and mh["retainedActive"] == ["kalshi:FED:B"]
    assert [a["alertReason"] for a in r["alerts"]] == ["MEMBERS_CHANGED"]


def test_R6_03_partial_overlap_different_event_instance_is_a_new_episode_old_evidence_kept():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    _run(st, _c(["treasury:2Y:A", "kalshi:FED:B"], "fed-policy:FED_DECISION:cut:2027-03"), NOW)
    r = _run(st, _c(["treasury:2Y:A", "polymarket:FED:C"], "fed-policy:FED_DECISION:cut:2027-06"), NOW + 600)
    inc = st["incidents"]["cross:fed-policy:CONVERGENCE"]
    assert inc["episode"] == 2 and [a["alertReason"] for a in r["alerts"]] == ["NEW_EPISODE"]
    prev = inc["previousEpisodes"][-1]
    assert prev["endedAs"] == "SUPERSEDED" and prev["members"] == ["treasury:2Y:A", "kalshi:FED:B"] and prev["eventInstance"].endswith("2027-03")
    assert prev["evidence"] is not None


def test_R6_03_partial_overlap_without_identity_is_a_visible_continuation_hypothesis():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    _run(st, _c(["treasury:2Y:A", "kalshi:FED:B"]), NOW)
    r = _run(st, _c(["treasury:2Y:A", "polymarket:FED:C"]), NOW + 600, {"kalshi:FED:B": {"ratio": 1.4, "valid": True}})
    inc = st["incidents"]["cross:fed-policy:CONVERGENCE"]
    assert inc["episode"] == 1 and inc["continuity"] == "HYPOTHESIS"
    assert inc["memberHistory"][-1]["continuity"] == "HYPOTHESIS" and "kalshi:FED:B" in inc["members"]
    assert [a["alertReason"] for a in r["alerts"]] == ["MEMBERS_CHANGED"], "a recomposition is shown, never silently confirmed"
    r = _run(st, _c(["equities:SPY:D", "polymarket:FED:E"]), NOW + 1200)  # C+D style: disjoint → new episode
    assert st["incidents"]["cross:fed-policy:CONVERGENCE"]["episode"] == 2


# ======================= R6-05: no SAME_EVENT from an alias alone =======================

ADV = [
    ("nvidia", "Will Nvidia be the largest company by market cap on June 30, 2027?", "Will Nvidia announce a stock split in 2027?"),
    ("fed-policy", "Will the Fed cut rates at the March 2027 meeting?", "Will the Fed cut rates at the June 2027 meeting?"),
    ("fed-policy", "Will the Fed cut rates at the March 2027 meeting?", "Will the Fed not cut rates at the March 2027 meeting?"),
    ("bitcoin", "Will a spot Bitcoin ETF see record inflows in March 2027?", "Will El Salvador buy more bitcoin in 2027?"),
    ("fed-policy", "Will the Fed cut rates at the March 2027 meeting?", "If CPI is above 3%, will the Fed cut rates at the March 2027 meeting?"),
]


def test_R6_05_adversarial_prediction_pairs_never_converge_by_alias():
    for i, (ent, a, b) in enumerate(ADV):
        o = fake("equities", ent, NOW, "equities:SPY"); o["relations"] = {ent: "DIRECT_PROXY"}
        pa = fake("polymarket", ent, NOW, None, title=a); pa["relations"] = {ent: EN.relation(None, ent, "polymarket", a)}
        pb = fake("kalshi", ent, NOW, None, title=b); pb["relations"] = {ent: EN.relation(None, ent, "kalshi", b)}
        out = X.convergence([o, pa, pb], NOW + 60)
        cv = [c for c in out if c["type"] == "CONVERGENCE"]
        for c in cv:  # b never contributes; a and b are never one counted event
            assert pb["key"] not in c["metrics"]["memberKeys"], (a, b)
        if i in (1, 2):  # two normalized but different instances (meeting dates; cut vs not cut): both excluded
            assert not cv, (a, b)
        if i in (0, 3):  # alias-only questions: neither counts
            assert not cv, (a, b)
        alone = X.convergence([o, pb], NOW + 60)
        assert not [c for c in alone if c["type"] == "CONVERGENCE"] or i in (1, 2), (b, pb["relations"])


def test_R6_05_unnormalized_question_is_related_activity_and_positive_control_still_counts():
    assert EN.relation(None, "nvidia", "polymarket", "Will Nvidia announce a stock split in 2027?") == "RELATED_ACTIVITY"
    assert EN.relation(None, "bitcoin", "kalshi", "Will El Salvador buy more bitcoin in 2027?") == "RELATED_ACTIVITY"
    assert EN.relation(None, "fed-policy", "kalshi", "If CPI is above 3%, will the Fed cut rates at the March 2027 meeting?") == "RELATED_ACTIVITY"
    sp = EN.settlement_spec("Will the Fed cut rates at the March 2027 meeting?")
    assert sp["settlementMetric"] == "FED_DECISION" and sp["outcome"] == "cut" and sp["date"] == "2027-03" and sp["eventInstance"] == "FED_DECISION:cut:2027-03"
    # positive control: the same normalized event on two venues + a rates observation still counts
    t = "Will the Fed cut rates at the March 2027 meeting?"
    o = fake("treasury", "fed-policy", NOW, "treasury:2Y"); o["relations"] = {"fed-policy": "SAME_UNDERLYING"}
    p = fake("polymarket", "fed-policy", NOW, None, title=t); p["relations"] = {"fed-policy": EN.relation(None, "fed-policy", "polymarket", t)}
    assert p["relations"]["fed-policy"] == "SAME_EVENT"
    out = X.convergence([o, p], NOW + 60)
    cv = [c for c in out if c["type"] == "CONVERGENCE"]
    assert cv and cv[0]["metrics"].get("eventInstance") == "fed-policy:FED_DECISION:cut:2027-03"


# ======================= R6-04: every public asset classified; images covered; history options =======================

ASSET_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".zip", ".json", ".jsonl", ".csv", ".txt"}
STATUSES = {"synthetic", "project-generated", "public-official", "license-text"}


def _assets():
    out = []
    for f in R5._tracked():
        p = Path(f)
        if p.suffix.lower() in ASSET_EXT and not f.startswith(("lib/", "skills/")) and f not in ("requirements.txt",):
            out.append(f)
    return out


def test_R6_04_every_tracked_public_asset_is_in_the_manifest_with_hash_source_and_status():
    man = json.loads((R / "docs/assets-manifest.json").read_text())["assets"]
    missing = [f for f in _assets() if f not in man and f != "docs/assets-manifest.json"]
    assert not missing, missing
    for f, v in man.items():
        assert (R / f).exists(), f"manifest lists a file not in the tree: {f}"
        assert v["status"] in STATUSES, (f, v["status"])
        assert v["source"] and hashlib.sha256((R / f).read_bytes()).hexdigest() == v["sha256"], f


def test_R6_04_images_and_examples_are_synthetic_or_project_generated_and_scanned():
    man = json.loads((R / "docs/assets-manifest.json").read_text())["assets"]
    for f, v in man.items():
        if Path(f).suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4"):
            assert v["status"] in ("synthetic", "project-generated"), f
            assert v.get("renderedFrom") or v["status"] == "project-generated", f
        if f.startswith("examples/") and f.endswith(".json"):
            j = json.loads((R / f).read_text())
            assert v["status"] in ("synthetic", "project-generated"), f
            if v["status"] == "synthetic":
                marks = j if isinstance(j, list) else [j]
                assert all(x.get("_provenance") == "synthetic" for x in marks) and (isinstance(j, list) or j.get("synthetic") is True), f
    # the image scan: every image's renderedFrom input must itself be synthetic
    for f, v in man.items():
        if v.get("renderedFrom"):
            for src in v["renderedFrom"]:
                assert man[src]["status"] == "synthetic", (f, src)


def test_R6_04_onchain_examples_carry_no_real_identifiers():
    import re
    real = json.loads((R / "tests/fixtures/onchain-denylist.json").read_text())["sha256OfRealIdentifiers"]
    for f in [x for x in R5._tracked() if x.startswith(("examples/", "docs/")) and x.endswith((".json", ".txt", ".md"))]:
        for tok in set(re.findall(r"[1-9A-HJ-NP-Za-km-z]{32,88}", (R / f).read_text(errors="ignore"))):
            assert hashlib.sha256(tok.encode()).hexdigest() not in real, f"{f} still holds a real on-chain identifier"


def test_R6_04_history_options_documented_and_purge_verified_on_a_disposable_clone():
    doc = (R / "docs/review/HISTORY-EXPOSURE.md").read_text()
    for t in ("coordinated purge", "clean-root", "risk acceptance", "already cloned", "forks", "not run on the real repository"):
        assert t in doc, t
    v = json.loads((R / "docs/review/history-purge-verification.json").read_text())
    assert v["disposableClone"] is True and v["pushed"] is False
    assert v["before"]["findings"] > 0 and v["after"]["findings"] == 0
    assert (R / "tools/verify_history.py").exists()


# ======================= R6-06: Treasury evaluation dataset, no invented labels =======================

def test_R6_06_treasury_dataset_manifest_roster_and_blind_label_sheet_without_labels():
    d = R / "docs/review/eval-treasury"
    man = json.loads((d / "manifest.json").read_text())
    assert man["series"] and all(s["sha256"] and s["url"].startswith("https://home.treasury.gov") for s in man["series"])
    assert man["configVersion"].startswith("r6") and man["holdout"]["from"]
    ros = json.loads((d / "roster.json").read_text())
    assert ros["counts"]["episodes"] >= 100 and ros["counts"]["negatives"] >= 100 and len(ros["items"]) == sum(ros["counts"].values())
    for e in ros["items"]:
        assert set(e) == {"itemId", "date", "series", "window", "split"}, "reviewers are blind to detector output and to episode/negative membership"
    lab = json.loads((d / "labels.json").read_text())
    assert lab["labels"] == [] and lab["reviewers"] == []
    res = json.loads((R / "docs/review/eval-results.json").read_text())["objectiveA"]
    assert res["status"] == "INSUFFICIENT_EVIDENCE" and res["adjudicatedEvents"] == 0 and res["precision"] is None
    assert res["rosterEpisodes"] == ros["counts"]["episodes"] and res["matchedNegatives"] == ros["counts"]["negatives"]
    assert "baselines" in res and res["agreement"] is None


# ======================= R6-07: CI and device claims =======================

def test_R6_07_runner_names_skipped_suites_and_does_not_count_them():
    run = (R / "tests/run_all.py").read_text()
    assert "test_round6.py" in run and "not counted" in run
    ci = (R / "docs/ci/tests.yml").read_text()
    assert "STAGED, NOT ACTIVE" in ci and "test_round6.py" in ci and "assets-manifest" in ci
    res = (R / "docs/review/ROUND6-RESULTS.md").read_text()
    assert "not tested on a physical device" in res and "CI: not active" in res


if __name__ == "__main__":
    n = fails = 0
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            n += 1
            try:
                v(); print("ok  ", k)
            except Exception as e:  # noqa: BLE001
                fails += 1; print("FAIL", k, "--", type(e).__name__, str(e)[:160])
    print(f"round6: {n - fails}/{n} passed")
    sys.exit(1 if fails else 0)
