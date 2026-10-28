"""Round-3 regression matrix (RE-AUDIT §05). Each test name carries its matrix ID.
All fixtures are synthetic. Provider-shaped ones come from tests/fixtures/contracts/synth.py (invented values, provider shapes; R5-02)."""
import copy, json, sys, tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib"))
from grok_the_block.markets import detectors as X, feed as F, lifecycle as LC, timebase as T, events as EV, entities as EN, sources as S

NOW = 1_800_000_000
sys.path.insert(0, str(R / "tests/fixtures/contracts"))
import synth as SY  # noqa: E402
FX = json.loads((R / "tests/fixtures/signals-fixtures.json").read_text())


def ob(now=NOW, st="HEALTHY"):
    return {"ingestTs": now, "status": st, "coverage": {"universe": "fixture", "observed": 1}, "limitations": []}


def sig(key, src="equities", sev="HIGH", members=None):
    s = {"key": key, "source": src, "family": EN.family_of(src, None), "type": "T", "severity": sev, "basis": "observed", "title": key, "what": "",
         "when": NOW, "subject": {"name": key, "id": key, "url": "https://example.org"}, "evidence": [], "limits": [], "metrics": {}, "entities": []}
    if members:
        s["metrics"]["memberKeys"] = members
    return s


def fake(src, ent, when, inst=None, sev="MEDIUM", gran="intraday", title=None, status="HEALTHY", temporal="OK", cal=(), change=None, outcome="Yes"):
    s = {"key": f"{src}:{inst or title or ent}:{when}", "source": src, "family": EN.family_of(src, inst), "instrument": inst, "relations": {},
         "type": "T", "severity": sev, "basis": "observed", "title": title or f"{src} {inst or ent}", "what": "", "when": when,
         "subject": {"name": ent, "id": ent, "url": "https://example.org"}, "evidence": [{"label": "e", "url": "https://example.org"}],
         "limits": [], "metrics": {"change": change, "outcome": outcome}, "entities": [ent], "calendar": list(cal),
         "observation": {"eventTs": when - 600, "granularity": gran, "temporalStatus": temporal, "sourceStatus": status,
                         "fastEligible": gran in ("intraday", "delayed") and temporal == "OK"}}
    return s


def roundtrip(st):  # restart: the state goes through the JSON file between runs
    return json.loads(json.dumps(st))


# ---------------- OBS: observation validity drives resolution (P0.01) ----------------

def test_OBS_01_degraded_source_updates_spy_but_holds_failed_nvda():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    LC.step(st, [sig("equities:SPY:T"), sig("equities:NVDA:T")], {"equities:SPY:T": 1.2, "equities:NVDA:T": 1.2}, {"equities": "HEALTHY"}, NOW)
    for i in range(1, 4):  # NVDA fetch fails; equities is DEGRADED but SPY is validly observed below exit
        st = roundtrip(st)
        r = LC.step(st, [], {"equities:SPY:T": {"ratio": 0.2, "valid": True}}, {"equities": "DEGRADED"}, NOW + i * 600)
    assert st["incidents"]["equities:SPY:T"]["state"] == "RESOLVED"
    nv = st["incidents"]["equities:NVDA:T"]
    assert nv["state"] != "RESOLVED" and nv["lastConfirmedAt"] == NOW
    assert r["telemetry"]["heldUnobserved"] == 1 and nv["history"][-1]["event"] == "HELD_UNOBSERVED"
    # NVDA recovers: two valid probes at 0.5x → COOLING then RESOLVED
    LC.step(st, [], {"equities:NVDA:T": {"ratio": 0.5, "valid": True}}, {"equities": "HEALTHY"}, NOW + 5000)
    assert st["incidents"]["equities:NVDA:T"]["state"] == "COOLING"
    LC.step(st, [], {"equities:NVDA:T": {"ratio": 0.5, "valid": True}}, {"equities": "HEALTHY"}, NOW + 5600)
    assert st["incidents"]["equities:NVDA:T"]["state"] == "RESOLVED"


def test_OBS_02_two_valid_below_exit_readings_resolve_one_does_not_and_absent_is_not_zero():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    LC.step(st, [sig("equities:SPY:T")], {"equities:SPY:T": 1.3}, {"equities": "HEALTHY"}, NOW)
    LC.step(st, [], {"equities:SPY:T": {"ratio": 0.4, "valid": True}}, {"equities": "HEALTHY"}, NOW + 600)
    assert st["incidents"]["equities:SPY:T"]["state"] == "COOLING", "one valid reading does not resolve"
    LC.step(st, [], {}, {"equities": "HEALTHY"}, NOW + 1200)  # a gap in between is not a reading
    assert st["incidents"]["equities:SPY:T"]["state"] == "COOLING"
    LC.step(st, [], {"equities:SPY:T": {"ratio": 0.4, "valid": True}}, {"equities": "HEALTHY"}, NOW + 1800)
    assert st["incidents"]["equities:SPY:T"]["state"] == "RESOLVED"
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    LC.step(st, [sig("treasury:2Y:T", "treasury")], {"treasury:2Y:T": 1.3}, {"treasury": "HEALTHY"}, NOW)
    for i in range(1, 5):
        probes = {} if i % 2 else {"treasury:2Y:T": {"ratio": None, "valid": False, "reason": "short history"}}
        LC.step(st, [], probes, {"treasury": "HEALTHY"}, NOW + i * 600)
    assert st["incidents"]["treasury:2Y:T"]["state"] == "NEW" and st["incidents"]["treasury:2Y:T"]["belowCount"] == 0
    # detector side: short history writes an invalid probe, not a zero
    X.reset()
    rows = [(NOW - 86400 * (30 - i), 100.0, 1e6) for i in range(30)]
    X.daily_anomaly("equities", "NVDA", rows, "https://finance.yahoo.com/quote/NVDA", ob())
    assert all(not p["valid"] for p in X.PROBES.values()) and X.PROBES


def test_OBS_03_cross_incident_held_until_every_member_validly_below_exit():
    m = ["polymarket:a:T", "treasury:2Y:T"]
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    LC.step(st, [sig("cross:fed-policy:CONVERGENCE", "cross", members=m)], {}, {"cross": "HEALTHY"}, NOW)
    for i in range(1, 4):  # treasury unavailable: only one member observed
        st = roundtrip(st)
        LC.step(st, [], {m[0]: {"ratio": 0.1, "valid": True}}, {"polymarket": "HEALTHY", "treasury": "UNAVAILABLE"}, NOW + i * 600)
    inc = st["incidents"]["cross:fed-policy:CONVERGENCE"]
    assert inc["state"] != "RESOLVED" and inc["members"] == m and "treasury:2Y:T" in inc["history"][-1]["note"], "coverage note names the missing member"
    both = {m[0]: {"ratio": 0.1, "valid": True}, m[1]: {"ratio": 0.5, "valid": True}}
    LC.step(st, [], both, {}, NOW + 5000); LC.step(st, [], both, {}, NOW + 5600)
    assert inc["state"] == "RESOLVED" or st["incidents"]["cross:fed-policy:CONVERGENCE"]["state"] == "RESOLVED"


# ---------------- TIME: honest times (P0.02) ----------------

def test_TIME_01_daily_bar_at_1000_1559_1601_and_post_close():
    d = date(2026, 10, 28)
    bar = T.ny_ts(d, 0)
    for hh, mm, done in ((10, 0, False), (15, 59, False), (16, 1, False), (16, 20, True)):
        st = T.daily_bar_status("equities", "NVDA", bar, T.ny_ts(d, hh, mm))
        assert st["complete"] is done, (hh, mm)
        assert st["availableTs"] == T.ny_ts(d, 16, 15) and st["estimated"], "availability = close + publish lag, estimated"
    sat = T.daily_bar_status("equities", "NVDA", T.ny_ts(date(2026, 10, 30), 0), T.ny_ts(date(2026, 10, 31), 12))
    assert sat["complete"], "Friday bar complete on Saturday"
    rows = [(T.ny_ts(d, 0) - 86400 * (80 - i), 100 * (1 + 0.004 * ((-1) ** i)), 1e6 * (1 + 0.05 * (i % 5))) for i in range(81)]
    rows[-1] = (T.ny_ts(d, 0), 140.0, 9e7)
    for hh, mm in ((10, 0), (15, 59), (16, 1)):
        X.reset()
        out = X.daily_anomaly("equities", "NVDA", rows, "https://finance.yahoo.com/quote/NVDA", ob(T.ny_ts(d, hh, mm)))
        assert not any(s["basis"] != "unverified" and s["severity"] != "INFO" for s in out), (hh, mm)
        assert all((s["observation"].get("eventTs") or 0) <= T.ny_ts(d, hh, mm) + 120 for s in out), "no future event time"
    X.reset()
    late = X.daily_anomaly("equities", "NVDA", rows, "https://finance.yahoo.com/quote/NVDA", ob(T.ny_ts(d, 16, 20)))
    assert any(s["type"] == "VOLUME_ROBUST_Z" for s in late), "the completed bar is scored after the close"


def test_TIME_01b_incomplete_daily_bar_dropped_and_session_rules():
    now = T.ny_ts(date(2026, 10, 28), 11)  # 11:00 ET, today's bar still forming
    rows = [(T.ny_ts(date(2026, 10, 28), 0) - 86400 * (80 - i), 100 * (1 + 0.004 * ((-1) ** i)), 1e6) for i in range(81)]
    rows[-1] = (T.ny_ts(date(2026, 10, 28), 0), 140.0, 9e7)  # absurd partial bar
    X.reset()
    out = X.daily_anomaly("equities", "NVDA", rows, "https://finance.yahoo.com/quote/NVDA", ob(now))
    assert not any(s["basis"] != "unverified" and s["severity"] != "INFO" for s in out), "partial bar must not fire"
    ec = T.daily_bar_status("equities", "SPY", T.ny_ts(date(2026, 11, 27), 0), T.ny_ts(date(2026, 11, 27), 13, 30))
    assert datetime.fromtimestamp(ec["eventTs"], T.NY).hour == 13 and ec["complete"] and "early" in ec["basis"]
    assert datetime.fromtimestamp(T.daily_bar_status("macro", "^VIX", T.ny_ts(date(2026, 3, 9), 0), NOW)["eventTs"], T.NY).strftime("%H:%M") == "16:15"
    fx = T.daily_bar_status("macro", "EURUSD=X", T.ny_ts(date(2026, 3, 9), 0), T.ny_ts(date(2026, 3, 9), 16))
    assert not fx["complete"] and datetime.fromtimestamp(fx["eventTs"], T.NY).hour == 17
    c = T.daily_bar_status("crypto", "BTC", 1793145600, 1793145600 + 3600)
    assert not c["complete"] and c["eventTs"] == 1793145600 + 86400
    # DST: the close is 16:00 New York both sides of the November switch (20:00Z → 21:00Z)
    a = T.daily_bar_status("equities", "SPY", T.ny_ts(date(2026, 10, 30), 0), NOW)["eventTs"]
    b = T.daily_bar_status("equities", "SPY", T.ny_ts(date(2026, 11, 2), 0), NOW)["eventTs"]
    assert datetime.fromtimestamp(a, timezone.utc).hour == 20 and datetime.fromtimestamp(b, timezone.utc).hour == 21


def test_TIME_02_future_or_missing_option_snapshot_is_degraded_and_not_fast():
    j = SY.cboe_chain()
    now = 1793202974 - 3600
    p = S.parse_cboe(j, now)  # snapshot is an hour after "now": a future time, never clamped
    assert p["snapshotIssue"] and "future" in p["snapshotIssue"] and p["snapshotTs"] == 1793202974
    j2 = dict(j, timestamp="")
    assert S.parse_cboe(j2, now)["snapshotIssue"] == "missing snapshot time"
    assert S.parse_cboe(dict(j, timestamp="28/10/2026 3pm"), now)["snapshotIssue"] == "missing snapshot time", "malformed = missing"
    assert T.freshness("options", 1793202974 - 6 * 3600, 1793202974)[0] != "HEALTHY", "a 6h-old delayed snapshot is not HEALTHY"
    chain = {"rows": [{"contract": "X", "expiry": "20261120", "type": "call", "strike": 1, "volume": 9000, "oi": 10, "price": 50.0}], "rejected": 0, "snapshotTs": None}
    X.reset(); out = X.options_activity("TLT", chain, "https://www.cboe.com/x", ob())
    assert out and all(s["observation"]["sourceStatus"] == "DEGRADED" and not s["observation"]["fastEligible"] for s in out)
    # env never clamps a non-final future estimate
    o = X.env(ob(), NOW - 60, NOW + 900, NOW, final=False, granularity="daily")
    assert o["temporalStatus"] == "INCOMPLETE" and o["availableTs"] == NOW + 900 and not o["fastEligible"]
    o = X.env(ob(), NOW - 60, None, NOW)
    assert o["availableTs"] == NOW and o["timeBasis"]["available"] == "ingest-lower-bound"
    # feed: a source whose snapshot is in the future is DEGRADED
    orig = S.options_chain
    try:
        S.options_chain = lambda sym: dict(S.parse_cboe(j, now), via="cboe delayed", url="https://www.cboe.com/delayed_quotes/tlt/quote_table")
        rep = F.run(["options"], option_tickers=["TLT"], now=now, calendar={"events": []})
    finally:
        S.options_chain = orig
    assert rep["sourceStatus"]["options"]["state"] == "DEGRADED" and "future" in rep["sourceStatus"]["options"]["detail"]


def test_TIME_03_divergence_needs_comparable_windows():
    X.reset()
    X.observe("equities:TLT", 0.2, "https://finance.yahoo.com/quote/TLT", NOW - 86400, "daily", (NOW - 2 * 86400, NOW - 86400))
    mover = fake("polymarket", "fed-policy", NOW, sev="HIGH", gran="intraday", title="Fed cut December 2026")
    assert X.divergence([mover], NOW) == [], "yesterday's daily bar can't show a live move was ignored"
    X.observe("equities:TLT", 0.2, "https://finance.yahoo.com/quote/TLT", NOW, "intraday", (NOW - 3600, NOW))
    assert len(X.divergence([mover], NOW)) == 1
    y = fake("equities", "fed-policy", NOW - 20 * 3600, inst="treasury:2Y", gran="daily")
    y["source"] = "treasury"; y["family"] = "rates"
    cv = [c for c in X.convergence([mover, y], NOW) if c["type"] == "CONVERGENCE"]
    assert not cv or cv[0]["metrics"]["mode"] != "fast", "yesterday's daily bar can't make fast mode"


# ---------------- CAL: calendar phases (P0.03) ----------------
CAL = {"events": [{"type": "FOMC", "label": "FOMC decision", "ts": NOW + 3 * 3600, "source": "federalreserve.gov"},
                  {"type": "CPI", "label": "CPI", "ts": NOW - 1800, "source": "bls.gov"},
                  {"type": "AUCTION", "label": "10-Year Note auction", "ts": T.ny_ts(T.datetime.fromtimestamp(NOW, T.NY).date(), 0), "timeExact": False}]}


def test_CAL_01_three_hours_before_fomc_is_pre_event_not_capped():
    e = EV.events_near(NOW, {"prediction"}, {"events": CAL["events"][:1]})
    assert [x["phase"] for x in e] == ["PRE_EVENT_POSITIONING"] and e[0]["eventId"] and "BEFORE" in e[0]["rationale"]
    a = fake("polymarket", "fed-policy", NOW - 900, title="Fed cut in December 2026", cal=e, change=0.2)
    b = fake("treasury", "fed-policy", NOW - 600, inst="treasury:2Y", cal=e)
    cv = [c for c in X.convergence([a, b], NOW) if c["type"] == "CONVERGENCE"]
    assert cv and cv[0]["severity"] != "LOW" and not cv[0]["metrics"]["calendarExplained"]
    assert any(c.startswith("before ") for c in cv[0]["metrics"]["calendarContext"])
    ex = json.loads((R / "examples/signals-EXAMPLE.json").read_text())  # the Oct 28 pre-FOMC example
    for c in [s for s in ex["signals"] if s["type"] == "CONVERGENCE"]:
        assert not c["metrics"]["calendarExplained"] or all(e.split("-")[0] != "FOMC" for e in c["metrics"]["explainedBy"]), "not explained by a future decision"
    for s in ex["signals"]:
        for e in s.get("calendar") or []:
            if e["type"] == "FOMC" and e["time"] > T.iso(s["when"]):
                assert e["phase"] == "PRE_EVENT_POSITIONING"


def test_CAL_03_wrong_tenor_auction_is_no_blanket_rates_explanation():
    ten = EV.events_near(NOW, {"rates"}, CAL, instrument="treasury:10Y")
    two = EV.events_near(NOW, {"rates"}, CAL, instrument="treasury:2Y")
    auc = [x for x in ten if x["type"] == "AUCTION"]
    assert auc and auc[0]["phase"] == "POST_EVENT_CONTEXT" and auc[0]["timeExact"] is False
    assert not [x for x in two if x["type"] == "AUCTION"], "a 10Y auction doesn't explain a 2Y move"
    rr = EV.events_near(NOW, {"rates"}, CAL, instrument="treasury:2Y", window_start=NOW - 1200)
    assert any(x["type"] == "CPI" and x["phase"] == "RELEASE_REACTION" for x in rr)
    daily = EV.events_near(NOW, {"rates"}, CAL, instrument="treasury:2Y", granularity="daily")
    assert all(x["phase"] != "RELEASE_REACTION" for x in daily), "daily data can't prove a 0-60 min reaction"


def test_CAL_02_post_cpi_reaction_only_the_same_event_explains_the_cluster():
    ra = {"eventId": "CPI-1", "label": "CPI", "phase": "RELEASE_REACTION", "availableAtObservation": True}
    rb = {"eventId": "NFP-1", "label": "NFP", "phase": "RELEASE_REACTION", "availableAtObservation": True}
    a = fake("polymarket", "fed-policy", NOW - 900, title="Fed cut in December 2026", cal=[ra], change=0.2)
    b = fake("treasury", "fed-policy", NOW - 600, inst="treasury:2Y", cal=[rb])
    c = [x for x in X.convergence([a, b], NOW) if x["type"] == "CONVERGENCE"][0]
    assert c["severity"] != "LOW" and not c["metrics"]["calendarExplained"]
    b["calendar"] = [ra]
    c = [x for x in X.convergence([a, b], NOW) if x["type"] == "CONVERGENCE"][0]
    assert c["severity"] == "LOW" and c["metrics"]["explainedBy"] == ["CPI-1"]
    cal = json.loads((R / "data/event-calendar.json").read_text())
    assert cal["contact"]["configured"] is False and cal["contact"]["envVar"] == "GTB_CONTACT" and "@" not in json.dumps(cal["contact"])


# ---------------- CONV: typed relations and dependency groups (P1.04) ----------------

def test_CONV_01_mechanically_linked_instruments_count_once():
    oil = [fake("macro", "oil", NOW - 900, inst="macro:CL=F"), fake("equities", "oil", NOW - 800, inst="equities:USO")]
    assert not [c for c in X.convergence(oil, NOW) if c["type"] == "CONVERGENCE"], "oil + USO is one group"
    btc = [fake("crypto", "bitcoin", NOW - 900, inst="crypto:BTC"), fake("equities", "bitcoin", NOW - 800, inst="equities:MSTR", title="MSTR earnings move")]
    out = X.convergence(btc, NOW)
    assert not [c for c in out if c["type"] == "CONVERGENCE"] and [c for c in out if c["type"] == "RELATED_ACTIVITY"]
    k8 = fake("sec", "nvidia", NOW - 900, title="NVIDIA 8-K item 2.02")
    stock = fake("equities", "nvidia", NOW - 600, inst="equities:NVDA")
    assert not [c for c in X.convergence([k8, stock], NOW) if c["type"] == "CONVERGENCE"], "filing + its stock = one disclosure chain"
    coin = [fake("equities", "bitcoin", NOW - 900, inst="equities:COIN", title="COIN news"), fake("crypto", "bitcoin", NOW - 800, inst="crypto:BTC")]
    assert not [c for c in X.convergence(coin, NOW) if c["type"] == "CONVERGENCE"], "COIN news is exposure to BTC, not the same event"
    tsy = [fake("treasury", "fed-policy", NOW - 900, inst="treasury:10Y"), fake("polymarket", "fed-policy", NOW - 800, title="Fed cut in December 2026", change=0.2)]
    assert not [c for c in X.convergence(tsy, NOW) if c["type"] == "CONVERGENCE"], "10Y is macro exposure to the Fed, not the same event"


def test_CONV_02_prediction_markets_with_different_settlement_or_outcome_do_not_corroborate():
    a = fake("polymarket", "fed-policy", NOW - 900, title="Fed cut in December 2026?", change=0.2)
    b = fake("kalshi", "fed-policy", NOW - 800, title="Fed cut by March 2027?", change=0.2)
    t = fake("treasury", "fed-policy", NOW - 600, inst="treasury:2Y")
    out = X.convergence([a, b, t], NOW)
    assert not [c for c in out if c["type"] == "CONVERGENCE"]
    rel = X.same_family_repricing([a, b], NOW)
    assert rel[0]["type"] == "RELATED_ACTIVITY" and "not the same event" in rel[0]["what"]
    c = fake("kalshi", "fed-policy", NOW - 800, title="Fed cut in December 2026?", change=0.2, outcome="No")  # opposite outcome moved up
    assert not [x for x in X.convergence([a, c, t], NOW) if x["type"] == "CONVERGENCE"]
    same = fake("kalshi", "fed-policy", NOW - 800, title="Fed cut in December 2026?", change=0.15)
    assert X.same_family_repricing([a, same], NOW)[0]["type"] == "RELATED_REPRICING"


def test_CONV_03_positive_control_and_stale_member_excluded():
    a = fake("polymarket", "fed-policy", NOW - 900, title="Fed cut in December 2026?", change=0.2)
    t = fake("treasury", "fed-policy", NOW - 600, inst="treasury:2Y")
    cv = [c for c in X.convergence([a, t], NOW) if c["type"] == "CONVERGENCE"]
    assert len(cv) == 1 and cv[0]["metrics"]["mode"] == "fast" and len(cv[0]["metrics"]["contributing"]) == 2
    assert set(cv[0]["metrics"]["memberKeys"]) == {a["key"], t["key"]} and "Related observations" in cv[0]["title"]
    stale = fake("equities", "us-treasuries", NOW - 700, inst="equities:TLT", status="STALE")
    live = fake("polymarket", "us-treasuries", NOW - 600, title="10Y above 5% in December?", change=0.2)
    out = X.convergence([stale, live], NOW)
    assert not [c for c in out if c["type"] == "CONVERGENCE"]
    d = fake("treasury", "fed-policy", NOW - 600, inst="treasury:2Y", gran="daily")
    cv = [c for c in X.convergence([a, d], NOW) if c["type"] == "CONVERGENCE"]
    assert cv and cv[0]["metrics"]["mode"] != "fast", "a daily member can't make fast mode"
    ex = [c for c in X.convergence([a, t, fake("equities", "fed-policy", NOW - 500, inst="equities:TLT")], NOW) if c["type"] == "CONVERGENCE"][0]
    assert any("MACRO_EXPOSURE" in e["reason"] for e in ex["metrics"]["excluded"])


# ---------------- PROV: provider-shaped fixtures (P1.06) ----------------

def test_PROV_01_options_providers_happy_and_failure_paths():
    c = S.parse_cboe(SY.cboe_chain(), 1793202974)
    assert len(c["rows"]) == 12 and all(r["expiry"] and r["priceBasis"] in ("mid", "last", None) for r in c["rows"])
    n = S.parse_nasdaq(SY.nasdaq_chain(), "IWM", 1793202974)
    assert n["rows"] and n["snapshotTs"] == 1793202960 and n["rejected"] > 0, "missing OI rows rejected and counted"
    for bad in (None, {}, {"data": None}, {"data": {"options": [{"option": "garbage"}]}}, "<html>"):
        assert S.parse_cboe(bad, NOW) is None
        assert S.parse_nasdaq(bad, "IWM", NOW) is None
    miss = {"timestamp": "2026-10-28 15:56:14", "data": {"options": [{"option": "TLT261120C00090000", "volume": None, "open_interest": 5}]}}
    assert S.parse_cboe(miss, NOW) is None, "missing volume is rejected, not zero"


def test_PROV_02_okx_funding_normalized_per_settlement_period():
    o = S.parse_okx_perps(*SY.okx_perps())
    assert o["oi"] and all(len(r) == 3 for r in o["oi"]) and all(len(r) == 3 for r in o["funding"])
    assert S.parse_okx_perps(None, None, None) is None and S.parse_okx_perps({"data": [["x"]]}, {"data": [{}]}, {}) is None
    t0 = NOW - 60 * 8 * 3600
    hist = [(t0 + i * 8 * 3600, 0.0001, 8.0) for i in range(40)] + [(t0 + 40 * 8 * 3600 + i * 4 * 3600, 0.0001, 4.0) for i in range(1, 6)]
    hist[-1] = (hist[-1][0], 0.0004, 4.0)  # 0.04% per 4h = 0.08% per 8h
    X.reset(); out = X.crypto_perp_shock("BTC", [], hist, "https://www.okx.com/x", ob())
    f = [s for s in out if s["type"] == "FUNDING_EXTREME"]
    assert f and abs(f[0]["metrics"]["funding8h"] - 0.0008) < 1e-9
    X.reset(); X.crypto_perp_shock("BTC", [], hist[:20], "https://www.okx.com/x", ob())
    assert X.PROBES["crypto:BTC-PERP:FUNDING_EXTREME"]["valid"] is False, "<30 settlements: no percentile"


FORM4 = """<ownershipDocument><documentType>{doc}</documentType><issuer><issuerCik>0001045810</issuerCik><issuerTradingSymbol>NVDA</issuerTradingSymbol></issuer>
{owners}<nonDerivativeTable>{tx}</nonDerivativeTable></ownershipDocument>"""
OWN = "<reportingOwner><reportingOwnerId><rptOwnerCik>{}</rptOwnerCik></reportingOwnerId></reportingOwner>"
TX = """<nonDerivativeTransaction><transactionCoding><transactionCode>{c}</transactionCode></transactionCoding><transactionAmounts>
<transactionShares><value>{n}</value></transactionShares>{p}<transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode></transactionAmounts></nonDerivativeTransaction>"""


def f4(doc="4", owners=("111",), tx=(("P", 1000, 50.0, "A"),)):
    return FORM4.format(doc=doc, owners="".join(OWN.format(o) for o in owners),
                        tx="".join(TX.format(c=c, n=n, ad=ad, p=f"<transactionPricePerShare><value>{p}</value></transactionPricePerShare>" if p is not None else "") for c, n, p, ad in tx))


def test_PROV_03_form4_kalshi_polymarket_edge_cases():
    d = S.parse_form4(f4(owners=("111", "222")))
    assert d["owners"] == ["111", "222"] and d["issuerTicker"] == "NVDA" and d["transactions"][0]["code"] == "P"
    assert S.parse_form4(f4(doc="4/A"))["amendment"] and S.parse_form4("<html/>") is None
    assert S.parse_form4(f4(tx=(("P", 100, None, "A"),)))["transactions"][0]["price"] is None
    fl = [{"role": "Issuer", "cik": "1045810", "name": "NVIDIA CORP", "url": f"https://www.sec.gov/f{i}", "ts": NOW - 600} for i in range(4)]
    tx = {fl[0]["url"]: S.parse_form4(f4(owners=("111",), tx=(("P", 30000, 50.0, "A"),))),
          fl[1]["url"]: S.parse_form4(f4(doc="4/A", owners=("111",), tx=(("P", 30000, 50.0, "A"),))),  # amendment of the same owner: not double counted
          fl[2]["url"]: S.parse_form4(f4(owners=("222",), tx=(("P", 500, None, "A"), ("S", 10, 51.0, "D")))),
          fl[3]["url"]: S.parse_form4(f4(owners=("333",), tx=(("A", 9999, 0.0, "A"),)))}
    X.reset(); out = X.edgar_events(fl, [], ob(), tx)
    p = [s for s in out if s["type"] == "REPORTED_OPEN_MARKET_PURCHASES"][0]
    assert p["metrics"]["purchases"] == 2 and p["metrics"]["reportingPersons"] == 2 and p["metrics"]["unpriced"] == 1 and p["metrics"]["purchaseUsd"] == 1_500_000
    assert "reporting person" in p["title"] and "insider" not in (p["title"] + p["what"]).lower() and p["instrument"] == "sec:NVDA"
    old = F.adapt({"kind": "signals", "version": 2, "signals": [{"key": "sec:1:INSIDER_SALES_CLUSTER", "type": "INSIDER_SALES_CLUSTER"}]})
    assert old["signals"][0]["type"] == "REPORTED_SALES_CLUSTER" and "INSIDER" not in old["signals"][0]["key"]
    k = dict(FX["kalshi"]["shock"], yesBid=None, yesAsk=None, openTs=None)
    X.reset(); ks = [s for s in X.kalshi_shock(k, ob()) if s["type"] == "ODDS_REPRICING"]
    assert ks and ks[0]["severity"] == "LOW" and ks[0]["basis"] == "heuristic" and ks[0]["observation"]["granularity"] == "daily"
    pm = FX["polymarket"]["jump"]
    hist = [(NOW - 900 * i - (1000 if i % 4 == 0 else 0), 0.40) for i in range(40, 0, -1)] + [(NOW, 0.62)]
    X.reset(); s = X.pm_odds_jump(pm, ob(), hist)
    assert s and any("irregular" in x for x in s["limits"])


# ---------------- WATCH: quiet hours, restart, digest, delivery (P1.08) ----------------

def test_WATCH_01_dst_quiet_hours_restart_idempotent_digest_and_webhook_retry():
    tz = "America/New_York"
    prefs = {"quietHours": (22, 7), "quietTz": tz, "minSeverity": "MEDIUM", "mute": ["kalshi"]}
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "w.json"
        st = {"incidents": {}, "lastSuccessAt": NOW - 600}
        # Sat 31 Oct → Mon 2 Nov 2026 spans the DST change (1 Nov). 23:30 local is quiet on both sides.
        days = [datetime(2026, 10, 31, 23, 30, tzinfo=ZoneInfo(tz)), datetime(2026, 11, 1, 23, 30, tzinfo=ZoneInfo(tz))]
        for i, dt in enumerate(days):
            at = int(dt.timestamp())
            r = LC.step(st, [sig(f"equities:X{i}:T")], {f"equities:X{i}:T": 1.2}, {"equities": "HEALTHY"}, at, prefs)
            assert r["telemetry"]["deferred"] == 1 and not r["alerts"], dt
            p.write_text(json.dumps(st)); st = json.loads(p.read_text())  # restart between runs
        assert not LC._quiet(int(datetime(2026, 11, 2, 7, 30, tzinfo=ZoneInfo(tz)).timestamp()), (22, 7), 0, tz)
        assert LC._quiet(int(datetime(2026, 11, 2, 6, 30, tzinfo=ZoneInfo(tz)).timestamp()), (22, 7), 0, tz)
        morning = int(datetime(2026, 11, 2, 8, 0, tzinfo=ZoneInfo(tz)).timestamp())
        calls = []
        def flaky(a):
            calls.append(a["alertId"]); return len(calls) > 2  # first two attempts fail
        r = LC.step(st, [sig("kalshi:k:T", "kalshi"), sig("equities:L:T", sev="LOW")], {}, {"equities": "HEALTHY", "kalshi": "HEALTHY"}, morning, prefs)
        assert len(r["alerts"]) == 2 and r["telemetry"]["muted"] == 1 and r["telemetry"]["belowFloor"] == 1
        LC.deliver(st, r["alerts"], flaky, r["telemetry"])
        assert r["telemetry"].get("delivered", 0) == 0 and r["telemetry"]["pendingDelivery"] == 2, "failure never counted as delivered"
        p.write_text(json.dumps(st)); st = json.loads(p.read_text())
        r2 = LC.step(st, [], {}, {"equities": "HEALTHY"}, morning + 600, prefs)
        assert not r2["alerts"], "digest released once (idempotent)"
        LC.deliver(st, r2["alerts"], flaky, r2["telemetry"])
        assert r2["telemetry"]["delivered"] == 2 and st["outbox"] == [], "retried from the outbox after restart"
        LC.deliver(st, r["alerts"], flaky, {})  # replaying the same alerts after a crash
        assert st["outbox"] == [] and len(set(st["sentIds"])) == 2
        tel = r["telemetry"]
        assert {"muted", "belowFloor", "deferred", "suppressedUnchanged", "skippedUnavailable", "heldUnobserved", "resolved", "delivered"} <= set(tel) | {"delivered"}


# ---------------- REPLAY: point-in-time inputs only (§04) ----------------

def test_REPLAY_01_current_volume_rejected_as_historical_evidence():
    pm = dict(FX["polymarket"]["jump"], vol24AsOf=NOW + 30 * 86400)  # volume fetched a month later
    X.reset(); s = X.pm_odds_jump(pm, ob())
    assert s["basis"] == "unverified" and s["severity"] == "INFO" and s["metrics"]["vol24"] is None
    from grok_the_block.markets import replay as RP
    assert all(r["ticks"] > 0 for r in RP.run_all())
    import importlib.util
    spec = importlib.util.spec_from_file_location("rr", R / "skills/signals/scripts/replay_real.py")
    src = (R / "skills/signals/scripts/replay_real.py").read_text()
    assert "vol24AsOf" in src and "eval-config.json" in src, "real replay uses point-in-time volume and the frozen config"


# ---------------- wording (P1.07) ----------------

def test_WORDING_approved_proposition_and_no_identity_claims():
    prop = "Unusual-activity analysis across selected public markets, with the evidence behind every flag."
    for f in ("README.md", "skills/signals/SKILL.md"):
        t = (R / f).read_text()
        assert prop in t, f
        claims = "\n".join(l for l in t.splitlines() if "never say" not in l.lower())  # the banned-word list itself is allowed
        for bad in ("insider trading detect", "catch insiders", "smart money", "before the news", "predicts", "early warning system"):
            assert bad not in claims.lower(), (f, bad)
    sk = (R / "skills/signals/SKILL.md").read_text()
    assert "available historical or rule-based baseline" in sk and "related observations" in sk.lower()
    assert "Not financial advice" in sk or "not financial advice" in sk.lower()
    pr = (R / "docs/PROVIDER-RIGHTS.md").read_text()
    assert 'A row marked "unverified" is not permission.' in pr and "no contact configured" in pr
    assert "no public distribution path" in sk.lower().replace("there is no public distribution path", "no public distribution path")


if __name__ == "__main__":
    n = 0
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v(); n += 1; print("ok", k)
    print(f"round3 matrix: all {n} tests passed")
