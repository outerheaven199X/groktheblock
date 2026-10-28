"""Round-4 regressions (ROUND4-REVIEW.html, reviewed e29040e). Each test name carries its R4 item.
Written to FAIL on e29040e and pass after the fix (see docs/review/ROUND4-RESULTS.md for the before/after run).
All synthetic. Tests named "provider" use provider-SHAPED synthetic payloads from tests/fixtures/contracts/synth.py
(R5-02 replaced the saved real responses used in round 4; real ones may be kept locally in tests/fixtures/private/)."""
import copy, hashlib, json, math, sys, tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib")); sys.path.insert(0, str(R / "tests"))
from grok_the_block.markets import detectors as X, feed as F, lifecycle as LC, timebase as T, entities as EN, sources as S
from test_round3 import fake, sig, roundtrip, NOW

NY = ZoneInfo("America/New_York")
sys.path.insert(0, str(R / "tests/fixtures/contracts"))
import synth as SY  # noqa: E402


def at(d, hh=18, mm=0):
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).timestamp())


# ======================= R4-01: cross-market incidents need EVERY member below exit =======================

def _cross_state():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    c = sig("cross:fed-policy:CONVERGENCE", "cross", members=["treasury:2Y:A", "kalshi:FED:B"])
    LC.step(st, [c], {}, {"treasury": "HEALTHY", "kalshi": "HEALTHY"}, NOW)
    return st


def test_R4_01_mixed_members_one_hot_one_cool_stays_active_then_both_cool_resolves():
    st = _cross_state()
    K = "cross:fed-policy:CONVERGENCE"
    states = []
    for i in range(1, 4):  # A cooled to 0.20, B still anomalous at 1.40, three valid scans
        st = roundtrip(st)
        LC.step(st, [], {"treasury:2Y:A": {"ratio": 0.20, "valid": True}, "kalshi:FED:B": {"ratio": 1.40, "valid": True}},
                {"treasury": "HEALTHY", "kalshi": "HEALTHY"}, NOW + i * 600)
        states.append(st["incidents"][K]["state"])
    assert all(s == "ACTIVE" for s in states), states
    inc = st["incidents"][K]
    assert inc["belowCount"] == 0 and inc["lastMagnitude"] == 1.40, "the hottest member is the incident's magnitude"
    for i, want in ((4, "COOLING"), (5, "RESOLVED")):
        st = roundtrip(st)
        r = LC.step(st, [], {"treasury:2Y:A": {"ratio": 0.20, "valid": True}, "kalshi:FED:B": {"ratio": 0.50, "valid": True}},
                    {"treasury": "HEALTHY", "kalshi": "HEALTHY"}, NOW + i * 600)
        assert st["incidents"][K]["state"] == want, (i, st["incidents"][K]["state"])
    assert r["telemetry"]["resolved"] == 1
    ev = [h["event"] for h in st["incidents"][K]["history"]]
    assert ev[-2:] == ["COOLING", "RESOLVED"] and "COOLING" not in ev[:-2]


def test_R4_01_missing_member_holds_at_either_cooling_step():
    for miss_at in (1, 2):
        st = _cross_state()
        K = "cross:fed-policy:CONVERGENCE"
        for i in (1, 2):
            p = {"treasury:2Y:A": {"ratio": 0.2, "valid": True}, "kalshi:FED:B": {"ratio": 0.5, "valid": True}}
            if i == miss_at:
                del p["kalshi:FED:B"]
            st = roundtrip(st)
            r = LC.step(st, [], p, {"treasury": "HEALTHY", "kalshi": "HEALTHY"}, NOW + i * 600)
            if i == miss_at:
                assert r["telemetry"]["heldUnobserved"] == 1 and st["incidents"][K]["history"][-1]["event"] == "HELD_UNOBSERVED"
        assert st["incidents"][K]["state"] != "RESOLVED", miss_at


def test_R4_01_composition_change_keeps_still_active_members():
    st = _cross_state()
    K = "cross:fed-policy:CONVERGENCE"
    # next scan the convergence is recomputed with members A and C; B is still hot (1.4) and must not be silently dropped
    c2 = sig(K, "cross", members=["treasury:2Y:A", "polymarket:FED:C"])
    LC.step(st, [c2], {"kalshi:FED:B": {"ratio": 1.4, "valid": True}, "treasury:2Y:A": {"ratio": 1.1, "valid": True}},
            {"treasury": "HEALTHY", "kalshi": "HEALTHY", "polymarket": "HEALTHY"}, NOW + 600)
    inc = st["incidents"][K]
    assert set(inc["members"]) == {"treasury:2Y:A", "kalshi:FED:B", "polymarket:FED:C"}, inc["members"]
    assert any(h.get("event") == "MEMBERS_CHANGED" for h in inc.get("memberHistory", [])), inc.get("memberHistory")


# ======================= R4-02: stale / invalid present signals can't open, refresh or re-alert =======================

def _osig(key, status="HEALTHY", sev="HIGH", temporal="OK"):
    s = sig(key, key.split(":")[0], sev)
    s["observation"] = {"sourceStatus": status, "temporalStatus": temporal, "granularity": "daily"}
    return s


def test_R4_02_stale_present_signal_does_not_realert_or_reconfirm():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    K = "equities:NVDA:RETURN_VS_REALIZED_VOL"
    r = LC.step(st, [_osig(K)], {K: {"ratio": 1.8, "valid": True}}, {"equities": "HEALTHY"}, NOW)
    assert len(r["alerts"]) == 1
    later = NOW + 7 * 3600  # a REMINDER would be due for an unresolved HIGH incident
    st = roundtrip(st)
    r = LC.step(st, [_osig(K, "STALE")], {K: {"ratio": 1.8, "valid": True}}, {"equities": "STALE"}, later)
    inc = st["incidents"][K]
    assert r["alerts"] == [], [a["alertReason"] for a in r["alerts"]]
    assert inc["lastConfirmedAt"] == NOW and inc["lastSeenAt"] == NOW
    assert r["telemetry"]["heldStale"] == 1 and inc["history"][-1]["event"] == "HELD_STALE"


def test_R4_02_new_high_signal_from_stale_provider_opens_nothing():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    K = "equities:TSLA:RETURN_VS_REALIZED_VOL"
    r = LC.step(st, [_osig(K, "STALE")], {K: {"ratio": 2.0, "valid": True}}, {"equities": "STALE"}, NOW)
    assert r["alerts"] == [] and K not in st["incidents"]
    assert r["telemetry"]["notAdmitted"] == 1 and r["telemetry"]["notAdmittedDetail"][0]["reason"].startswith("source STALE")


def test_R4_02_invalid_probe_or_incomplete_time_is_not_a_measurement():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    a, b = "options:SPY:UNUSUAL_OPTIONS_VOLUME", "options:QQQ:UNUSUAL_OPTIONS_VOLUME"
    r = LC.step(st, [_osig(a), _osig(b, temporal="INCOMPLETE")], {a: {"ratio": None, "valid": False, "reason": "no OI"}, b: {"ratio": 2, "valid": True}},
                {"options": "DEGRADED"}, NOW)
    assert r["alerts"] == [] and not st["incidents"]
    reasons = sorted(d["reason"] for d in r["telemetry"]["notAdmittedDetail"])
    assert reasons[0].startswith("detector produced no valid measurement") and reasons[1].startswith("time not valid"), reasons


# ---- integration: feed.run → feed.watch → lifecycle with real observation envelopes (provider-shaped Yahoo rows) ----

def _sessions(end: date, n: int):
    out, d = [], end
    while len(out) < n:
        if T.is_session(d):
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def _rows(end: date, spike=False, n=80, seed=1):
    rows, c = [], 100.0
    for i, d in enumerate(_sessions(end, n)):
        c *= 1 + 0.002 * math.sin(i * 1.7 + seed)
        v = 1e6 * (1 + 0.05 * math.sin(i * 2.3 + seed))
        rows.append((T.ny_ts(d, 9, 30), c, v))  # Yahoo stamps US equity daily bars at the 09:30 ET open
    if spike:
        t, c0, v0 = rows[-1]
        rows[-1] = (t, rows[-2][1] * 1.12, v0)
    return rows


def _scan(now, books, state):
    def fetch(sym):
        b = books.get(sym)
        if b is None:
            return None
        return {"symbol": sym, "rows": b, "via": "yahoo q1", "url": f"https://finance.yahoo.com/quote/{sym}", "tz": "America/New_York"}
    old = S.equity_daily
    S.equity_daily = fetch
    try:
        rep = F.run(sources=["equities"], tickers=list(books), now=now, calendar={"events": []})
    finally:
        S.equity_daily = old
    return F.watch(rep, state, {"minSeverity": "LOW"})


def test_R4_02_integration_stale_scan_does_not_remind_or_refresh():
    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "state.json"
        _scan(at(date(2026, 10, 22)), {"NVDA": _rows(date(2026, 10, 22))}, sp)                 # baseline, calm
        r1 = _scan(at(date(2026, 10, 23)), {"NVDA": _rows(date(2026, 10, 23), True)}, sp)       # fresh spike → NEW
        K = "equities:NVDA:RETURN_VS_REALIZED_VOL"
        assert [a["key"] for a in r1["watch"]["alerts"]] == [K] and r1["signals"][0]["observation"]["sourceStatus"] == "HEALTHY"
        st1 = json.loads(sp.read_text())["incidents"][K]
        # five days later the provider still serves the 10-23 bar: the same HIGH signal arrives with sourceStatus STALE
        r2 = _scan(at(date(2026, 10, 28)), {"NVDA": _rows(date(2026, 10, 23), True)}, sp)
        s2 = next(s for s in r2["signals"] if s["key"] == K)
        assert s2["observation"]["sourceStatus"] == "STALE" and s2["severity"] == "HIGH"
        assert r2["watch"]["alerts"] == [], "stale data must not produce a REMINDER"
        st2 = json.loads(sp.read_text())["incidents"][K]
        # R6-01 amendment: the hold now also ages it (5 days, past Tue's publication + grace) → UNCONFIRMED after HELD_STALE
        assert st2["lastConfirmedAt"] == st1["lastConfirmedAt"] and [h["event"] for h in st2["history"][-2:]] == ["HELD_STALE", "UNCONFIRMED"]
        assert r2["watch"]["telemetry"]["heldStale"] >= 1


def test_R4_02_integration_new_signal_from_stale_provider_opens_no_incident():
    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "state.json"
        _scan(at(date(2026, 10, 22)), {"TSLA": _rows(date(2026, 10, 22))}, sp)
        r = _scan(at(date(2026, 10, 28)), {"TSLA": _rows(date(2026, 10, 23), True)}, sp)
        assert any(s["severity"] == "HIGH" for s in r["signals"])
        assert r["watch"]["alerts"] == [] and not json.loads(sp.read_text())["incidents"]


def test_R4_02_integration_degraded_provider_spy_advances_nvda_holds():
    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "state.json"
        _scan(at(date(2026, 10, 22)), {"SPY": _rows(date(2026, 10, 22)), "NVDA": _rows(date(2026, 10, 22), seed=3)}, sp)
        _scan(at(date(2026, 10, 23)), {"SPY": _rows(date(2026, 10, 23), True), "NVDA": _rows(date(2026, 10, 23), True, seed=3)}, sp)
        # next session: SPY calm and complete; NVDA returns only a short history (invalid probe); AAPL fetch fails → DEGRADED
        r = _scan(at(date(2026, 10, 26)), {"SPY": _rows(date(2026, 10, 26)) [:-1] + [_rows(date(2026, 10, 26))[-1]],
                                           "NVDA": _rows(date(2026, 10, 26), n=10, seed=3), "AAPL": None}, sp)
        assert r["sourceStatus"]["equities"]["state"] == "DEGRADED"
        inc = json.loads(sp.read_text())["incidents"]
        assert inc["equities:SPY:RETURN_VS_REALIZED_VOL"]["state"] == "COOLING"
        nv = inc["equities:NVDA:RETURN_VS_REALIZED_VOL"]
        assert nv["state"] in ("NEW", "ACTIVE") and nv["history"][-1]["event"] == "HELD_UNOBSERVED"
        cov = r["sourceStatus"]["equities"]["coverage"]
        assert cov["fetchedInstruments"] == ["SPY", "NVDA"] and cov["analyzedInstruments"] == ["SPY"], cov


# ======================= R4-03: no precise co-occurrence span from unknown availability =======================

def _tb(s, avail):
    s["observation"]["timeBasis"] = {"available": avail}
    return s


def test_R4_03_mixed_clocks_never_show_exact_span():
    now = NOW
    tsy = _tb(fake("treasury", "fed-policy", now, "treasury:2Y", gran="daily"), "estimated")
    ks = _tb(fake("kalshi", "fed-policy", now, None, title="Fed rate cut in December 2026?"), "ingest-lower-bound")
    opt = _tb(fake("options", "fed-policy", now, "options:SPY", gran="delayed"), "ingest-lower-bound")
    for s in (tsy, ks, opt):
        s["relations"] = {"fed-policy": "SAME_EVENT"}
    out = [c for c in X.convergence([tsy, ks, opt], now + 60) if c["type"] == "CONVERGENCE"]
    assert out, "the groups still count; only the timing claim changes"
    c = out[0]; m = c["metrics"]
    assert m["timingComparable"] is False and m["spanHours"] is None
    assert "0.0h" not in c["title"] and "simultaneous" not in json.dumps(c).lower()
    assert "timing comparison approximate" in c["title"]
    assert m["mode"] == "timing-approximate" and all(x["temporalCertainty"] != "exact" for x in m["contributing"])
    # no time-sensitive rank bonus from unknown timestamps
    sev_bonus_free = m["rank"]
    for s in (tsy, ks, opt):
        s["observation"]["timeBasis"] = {"available": "provider"}; s["observation"]["granularity"] = "intraday"; s["observation"]["fastEligible"] = True
    exact = [c for c in X.convergence([tsy, ks, opt], now + 60) if c["type"] == "CONVERGENCE"][0]
    assert exact["metrics"]["timingComparable"] is True and exact["metrics"]["rank"] > sev_bonus_free


def test_R4_03_example_report_and_ui_do_not_render_exact_span_for_lower_bounds():
    rep = json.loads((R / "examples/signals-EXAMPLE.json").read_text())
    for s in rep["signals"]:
        if s["type"] == "CONVERGENCE":
            m = s["metrics"]
            if any(x.get("temporalCertainty") != "exact" for x in m.get("contributing", [])):
                assert m["spanHours"] is None and "0.0h" not in s["title"], s["title"]
    ui = (R / "ui/index.html").read_text()
    assert "timing comparison approximate" in ui and 'm.spanHours??"?"}h apart' not in ui
    assert "m.timingComparable===false||m.spanHours==null" in ui


# ======================= R4-04: provider clocks, per-instrument completion, fetched vs analyzed =======================

def _yahoo(j):
    p = S.parse_yahoo_chart(j)
    return p["rows"], p["tz"]


def test_R4_04_provider_yahoo_fx_bar_stamped_london_midnight_is_not_complete_on_its_session_evening():
    rows, tz = _yahoo(SY.yahoo_chart("EURUSD=X", tz="Europe/London", stamp=(0, 0)))
    assert tz == "Europe/London"
    last = rows[-1][0]  # the 2026-10-28 London-day bar, stamped 2026-10-27 20:00 New York
    assert datetime.fromtimestamp(last, NY).date() == date(2026, 10, 27)
    st = T.daily_bar_status("macro", "EURUSD=X", last, at(date(2026, 10, 27), 21), tz=tz)
    assert st["sessionDate"] == "2026-10-28" and not st["complete"], st
    assert st["clockNote"], "provider clock differs from the 17:00 ET convention and must be flagged"


def test_R4_04_provider_nasdaq_date_only_rows_keep_their_calendar_date():
    j = SY.nasdaq_hist()
    d0 = j["data"]["tradesTable"]["rows"][0]["date"]  # e.g. 10/27/2026
    ts = int(datetime.strptime(d0, "%m/%d/%Y").replace(tzinfo=timezone.utc).timestamp())
    st = T.daily_bar_status("equities", "SPY", ts, at(date(2026, 10, 28), 12))
    assert st["sessionDate"] == datetime.strptime(d0, "%m/%d/%Y").date().isoformat(), st


def test_R4_04_provider_early_close_dst_and_equity_clock():
    rows, tz = _yahoo(SY.yahoo_chart("SPY", days=SY.weekdays(date(2025, 12, 2), 10)))
    nov28 = [t for t, _, _ in rows if datetime.fromtimestamp(t, NY).date() == date(2025, 11, 28)][0]
    st = T.daily_bar_status("equities", "SPY", nov28, at(date(2025, 11, 28), 13, 20), tz=tz)
    assert st["complete"] and "early close" in st["basis"] and not st["clockNote"]
    rows, tz = _yahoo(SY.yahoo_chart("SPY", days=SY.weekdays(date(2026, 3, 13), 10)))
    for t, _, _ in rows:  # 09:30 ET both sides of the 2026-03-08 DST change
        assert datetime.fromtimestamp(t, NY).strftime("%H:%M") == "09:30"
    rows, tz = _yahoo(SY.yahoo_chart("GC=F", days=SY.weekdays(date(2026, 3, 13), 10), stamp=(0, 0)))
    st = T.daily_bar_status("macro", "GC=F", rows[-1][0], rows[-1][0] + 3600, tz=tz)
    assert st["sessionDate"] == datetime.fromtimestamp(rows[-1][0], NY).date().isoformat() and not st["complete"]


def test_R4_04_provider_crypto_utc_candles_cross_new_york_date_boundary():
    j = SY.okx_candles()
    ts = int(j["data"][0][0]) // 1000
    assert ts % 86400 == 0
    st = T.daily_bar_status("crypto", "BTC", ts, ts + 3600)
    assert not st["complete"] and st["sessionDate"] == datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def test_R4_04_per_symbol_staleness_is_not_masked_by_a_fresh_symbol():
    with tempfile.TemporaryDirectory() as d:
        r = _scan(at(date(2026, 10, 28)), {"SPY": _rows(date(2026, 10, 28)), "NVDA": _rows(date(2026, 10, 20), True)}, Path(d) / "s.json")
        st = r["sourceStatus"]["equities"]
        assert st["state"] == "DEGRADED" and "NVDA" in st["detail"], st
        bars = st["coverage"]["instrumentStatus"]
        assert bars["NVDA"]["freshness"] == "STALE" and bars["SPY"]["freshness"] == "HEALTHY"
        nv = [s for s in r["signals"] if s.get("instrument") == "equities:NVDA"]
        assert nv and all(s["observation"]["sourceStatus"] == "STALE" for s in nv)


def test_R4_04_provider_fixtures_are_synthetic_contracts():
    # R5-02 replaced this round-4 test (it required saved real payloads in the public repo). Now: the shapes used above
    # are synthetic and labelled; real responses may only live in the gitignored tests/fixtures/private/.
    assert SY.PROVENANCE == "synthetic" and SY.yahoo_chart()["_provenance"] == "synthetic"
    assert not (R / "tests/fixtures/providers").exists() or not any((R / "tests/fixtures/providers").iterdir())


# ======================= R4-05: honest independence language and event matching =======================

def test_R4_05_exact_outcome_matching_cut_vs_hike_do_not_merge():
    a = fake("polymarket", "fed-policy", NOW, None, title="Fed rate cut in December 2026?", change=0.1)
    b = fake("kalshi", "fed-policy", NOW, None, title="Fed rate hike in December 2026?", change=0.1)
    t = fake("treasury", "fed-policy", NOW, "treasury:2Y", gran="daily")
    out = X.convergence([a, b, t], NOW + 60)
    assert not [c for c in out if c["type"] == "CONVERGENCE"]
    rel = [c for c in out if c["type"] == "RELATED_ACTIVITY"][0]
    assert any("outcome" in e["reason"] for e in rel["metrics"]["excluded"])


def test_R4_05_company_crypto_exposure_is_related_activity_only():
    coin = fake("equities", "bitcoin", NOW, "equities:COIN"); coin["relations"] = {"bitcoin": EN.relation("equities:COIN", "bitcoin", "equities")}
    btc = fake("crypto", "bitcoin", NOW, "crypto:BTC"); btc["relations"] = {"bitcoin": "SAME_UNDERLYING"}
    out = X.convergence([coin, btc], NOW + 60)
    assert [c["type"] for c in out] == ["RELATED_ACTIVITY"]


def test_R4_05_common_mechanism_tlt_options_and_yield_contract_count_once():
    o = fake("options", "us-treasuries", NOW, "options:TLT"); o["relations"] = {"us-treasuries": "DIRECT_PROXY"}
    k = fake("kalshi", "us-treasuries", NOW, None, title="10-year Treasury yield above 4.50% on Dec 31, 2026?")
    k["relations"] = {"us-treasuries": EN.relation(None, "us-treasuries", "kalshi", k["title"])}
    assert k["relations"]["us-treasuries"] == "SETTLES_ON_UNDERLYING"
    out = X.convergence([o, k], NOW + 60)
    assert not [c for c in out if c["type"] == "CONVERGENCE"], [c["title"] for c in out]
    rel = [c for c in out if c["type"] == "RELATED_ACTIVITY"][0]
    assert "us-treasuries" in rel["title"]
    assert any("same dependency group" in e["reason"] for e in rel["metrics"]["excluded"])
    # the live 2026-10-28 lead used this wording ("10Y"), which the first version of the fix missed
    live = "Will the 10Y U.S. Treasury yield be above 3.49% on Dec 31, 2027? 3.5% or above"
    assert EN.relation(None, "us-treasuries", "polymarket", live) == "SETTLES_ON_UNDERLYING"
    assert EN.dependency_group(EN.settlement_instrument("us-treasuries", live), "treasury") == EN.dependency_group("options:TLT", "options")


def test_R4_05_alias_negatives():
    for text in ("Golden State Warriors win the title?", "Will Elon Musk tweet 100 times?", "apple pie contest", "Fedex earnings", "goldman sachs layoffs"):
        assert EN.resolve("polymarket", None, text) == [], text


def test_R4_05_wording_distinct_counted_groups_not_independent_evidence():
    out = X.convergence([fake("treasury", "fed-policy", NOW, "treasury:2Y", gran="daily"),
                         fake("kalshi", "fed-policy", NOW, None, title="Fed rate cut in December 2026?")], NOW + 60)
    c = [x for x in out if x["type"] == "CONVERGENCE"][0]
    assert "distinct counted evidence groups" in c["title"]
    for f in ("ui/index.html", "README.md", "skills/signals/SKILL.md", "lib/grok_the_block/markets/detectors.py", "lib/grok_the_block/markets/feed.py"):
        t = (R / f).read_text().lower()
        assert "independent evidence group" not in t and "independent corroboration" not in t.replace("not independent corroboration", ""), f


# ======================= R4-06: webhook dead letters, retry, at-least-once =======================

def _alert(i):
    return {"alertId": f"x#e1|NEW|{i}", "key": f"k{i}", "title": "t"}


def test_R4_06_retry_exhaustion_goes_to_dead_letter_and_explicit_retry_redelivers():
    st = {}
    for _ in range(5):
        LC.deliver(st, [_alert(1)], lambda a: False)
    assert st["outbox"] == [] and [d["alert"]["alertId"] for d in st["deadLetter"]] == ["x#e1|NEW|1"]
    assert st["deadLetter"][0]["attempts"] == 5 and st["deadLetter"][0]["lastError"]
    st = roundtrip(st)
    n = LC.retry_dead_letter(st)
    assert n == 1 and not st["deadLetter"]
    got = []
    tel = LC.deliver(st, [], lambda a: got.append(a["alertId"]) or True)
    assert got == ["x#e1|NEW|1"] and tel["delivered"] == 1 and tel["deadLetter"] == 0
    for i in range(300):
        st.setdefault("deadLetter", []).append({"alert": _alert(i), "attempts": 5})
    LC.deliver(st, [], lambda a: True)
    assert len(st["deadLetter"]) <= LC.DEAD_LETTER_MAX


def test_R4_06_crash_after_post_before_persist_redelivers_same_alert_id():
    st = {}
    received = []
    persisted = roundtrip(st)
    LC.deliver(st, [_alert(7)], lambda a: received.append(a["alertId"]) or True)  # POST succeeded …
    st = roundtrip(persisted)                                                       # … but the process died before saving
    LC.deliver(st, [_alert(7)], lambda a: received.append(a["alertId"]) or True)
    assert received == ["x#e1|NEW|7", "x#e1|NEW|7"], "at-least-once: a duplicate is possible"
    assert len(set(received)) == 1, "receivers dedupe by alertId"


def test_R4_06_signals_cli_and_docs_state_at_least_once():
    cli = (R / "skills/signals/scripts/signals.py").read_text()
    assert "--retry-dead-letter" in cli and "Idempotency-Key" in cli
    for f in ("README.md", "skills/signals/SKILL.md"):
        t = (R / f).read_text()
        assert "at-least-once" in t and "alertId" in t and "exactly-once" not in t.replace("not exactly-once", ""), f


# ======================= R4-07: integrity sidecar =======================

def test_R4_07_index_html_sha256_sidecar_matches_file_bytes():
    want = (R / "ui/index.html.sha256").read_text().split()[0]
    assert want == hashlib.sha256((R / "ui/index.html").read_bytes()).hexdigest()


def test_R4_07_readme_first_release_claim():
    claim = ("Experimental, user-run market-forensics research tool; rule-based observations with linked evidence and explicit "
             "coverage limits. No measured predictive accuracy.")
    assert claim in (R / "README.md").read_text()


if __name__ == "__main__":
    n = fails = 0
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            n += 1
            try:
                v(); print("ok  ", k)
            except Exception as e:  # noqa: BLE001
                fails += 1; print("FAIL", k, "--", type(e).__name__, str(e)[:160])
    print(f"round4: {n - fails}/{n} passed")
    sys.exit(1 if fails else 0)
