"""Round-5 regressions (ROUND5-REVIEW.html, reviewed f100071 / code 5db4c29). Test names carry the R5 item.
Written first and run against the 5db4c29 code (docs/review/round5-tests-before-fix.txt), then against the fix.
All fixtures are SYNTHETIC: provider shapes from tests/fixtures/contracts/synth.py, invented values."""
import json, re, subprocess, sys, tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib")); sys.path.insert(0, str(R / "tests")); sys.path.insert(0, str(R / "tests/fixtures/contracts"))
from grok_the_block.markets import detectors as X, feed as F, lifecycle as LC, timebase as T, entities as EN, sources as S
from test_round3 import fake, sig, roundtrip, NOW
import synth as SY

H = 3600
OB = lambda now=NOW, st="HEALTHY": {"ingestTs": now, "status": st, "coverage": {"universe": "synthetic", "observed": 1}, "limitations": []}  # noqa: E731
MINT = "SyntheticMint1111111111111111111111111111111"


def _report(alerts, checked):
    return {"kind": "watch", "checkedAt": checked, "token": {"symbol": "SYN", "mint": MINT}, "recentAlerts": alerts}


def _alert(sigid, ts, typ="WHALE_SELL"):
    return {"type": typ, "severity": "HIGH", "amountSol": 12.5, "timestamp": ts, "signature": sigid, "url": f"https://solscan.io/tx/{sigid}",
            "wallet": "SyntheticWallet111111111111111111111111111"}


def _sol_scan(st, reports, now):
    X.reset()
    rep = F.run(sources=["solana"], local_reports=reports, now=now, calendar={"events": []})
    res = LC.step(st, rep["signals"], rep.get("probes") or {}, {k: v["state"] for k, v in rep["sourceStatus"].items()}, now)
    return rep, res


# ======================= R5-01: discrete events get event-episode semantics =======================

def test_R5_01_same_solana_tx_in_five_scans_is_one_event_no_refresh_no_reminder():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    t_ev = NOW - 1800
    alerts, times = [], [NOW, NOW + 3 * H, NOW + 7 * H, NOW + 30 * H, NOW + 50 * H]
    first_conf = None
    for at in times:
        st = roundtrip(st)
        rep, res = _sol_scan(st, [_report([_alert("sigA", t_ev)], at - 60)], at)
        alerts += res["alerts"]
        inc = st["incidents"][f"solana:{MINT}:WHALE_SELL"]
        first_conf = first_conf or inc["lastConfirmedAt"]
        assert inc["lastConfirmedAt"] == first_conf == t_ev, "evidence time is the event's own time and is never refreshed by a repeat"
    assert [a["alertReason"] for a in alerts] == ["NEW"], [a["alertReason"] for a in alerts]
    assert inc["kind"] == "event" and inc["state"] == "OBSERVED" and list(inc["events"]) == [f"sigA:WHALE_SELL:{MINT}"]


def test_R5_01_second_distinct_tx_is_a_new_event_with_its_own_id():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    _sol_scan(st, [_report([_alert("sigA", NOW - 1800)], NOW - 60)], NOW)
    rep, res = _sol_scan(st, [_report([_alert("sigA", NOW - 1800), _alert("sigB", NOW + 1200)], NOW + 1700)], NOW + 1800)
    assert [a["alertReason"] for a in res["alerts"]] == ["NEW_EVENT"]
    assert res["alerts"][0]["newEventIds"] == [f"sigB:WHALE_SELL:{MINT}"]
    inc = st["incidents"][f"solana:{MINT}:WHALE_SELL"]
    assert sorted(inc["events"]) == [f"sigA:WHALE_SELL:{MINT}", f"sigB:WHALE_SELL:{MINT}"] and inc["lastConfirmedAt"] == NOW + 1200


def test_R5_01_stale_watched_token_cannot_be_admitted_as_fresh():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    fresh = _report([], NOW - 60)
    stale = dict(_report([_alert("sigOld", NOW - 60 * H)], NOW - 80 * H), token={"symbol": "OLD", "mint": "OldMint"})
    rep, res = _sol_scan(st, [fresh, stale], NOW)
    s = [x for x in rep["signals"] if x["source"] == "solana"]
    assert s and all(x["observation"]["sourceStatus"] == "STALE" for x in s)
    assert rep["sourceStatus"]["solana"]["state"] == "DEGRADED" and "OLD" in rep["sourceStatus"]["solana"]["detail"]
    assert res["alerts"] == [] and not st["incidents"] and res["telemetry"]["notAdmitted"] == 1


def test_R5_01_two_8k_accessions_same_issuer_both_preserved_no_intent_wording():
    ob = OB()
    f1 = {"form": "8-K", "name": "Synthetic Corp", "cik": "0000000042", "role": "Filer", "items": ["5.02"], "ts": NOW - 7200,
          "url": "https://www.sec.gov/Archives/edgar/data/42/000000004226000001/0000000042-26-000001-index.htm"}
    f2 = dict(f1, items=["1.01"], ts=NOW - 600, url="https://www.sec.gov/Archives/edgar/data/42/000000004226000002/0000000042-26-000002-index.htm")
    out = [s for s in X.edgar_events([], [f1, f2], ob) if s["type"] == "8K_EVENT"]
    assert len(out) == 1
    ids = [e["id"] for e in out[0]["metrics"]["eventIds"]]
    assert ids == ["0000000042-26-000001", "0000000042-26-000002"], ids
    assert len(out[0]["evidence"]) == 2
    txt = json.dumps(out).lower()
    assert not re.search(r"insider|intent|knew|wrongdo|illegal", txt.replace("says nothing about what anyone knew or intended", ""))
    # lifecycle: the second accession arriving later is a NEW_EVENT, the first is kept
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    a = X.edgar_events([], [f1], ob); LC.step(st, a, {}, {"sec": "HEALTHY"}, NOW)
    b = X.edgar_events([], [f1, f2], OB(NOW + 600)); r = LC.step(st, b, {}, {"sec": "HEALTHY"}, NOW + 600)
    inc = st["incidents"]["sec:0000000042:8K_EVENT"]
    assert sorted(inc["events"]) == ids and [x["alertReason"] for x in r["alerts"]] == ["NEW_EVENT"]


def test_R5_01_transient_failure_neither_completes_nor_clears_an_event_and_archive_is_not_resolve():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    _sol_scan(st, [_report([_alert("sigA", NOW - 1800)], NOW - 60)], NOW)
    K = f"solana:{MINT}:WHALE_SELL"
    for h in (24, 60, 100):  # watch reports unavailable for 100h
        LC.step(st, [], {}, {"solana": "UNAVAILABLE"}, NOW + h * H)
        assert st["incidents"][K]["state"] == "OBSERVED" and list(st["incidents"][K]["events"]) == [f"sigA:WHALE_SELL:{MINT}"]
    r = LC.step(st, [], {}, {"solana": "HEALTHY"}, NOW + 101 * H)
    inc = st["incidents"][K]
    assert inc["state"] == "ARCHIVED" and inc["state"] != "RESOLVED" and r["telemetry"]["archived"] == 1
    assert "not a resolution" in inc["history"][-1]["note"] and inc["events"]
    # the same old transaction reappearing later does not open a new episode
    rep, res = _sol_scan(st, [_report([_alert("sigA", NOW - 1800)], NOW + 102 * H - 60)], NOW + 102 * H)
    assert res["alerts"] == [] and st["incidents"][K]["state"] == "ARCHIVED"


def test_R5_01_event_without_immutable_id_is_not_admitted():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    a = _alert("x", NOW - 60); a.pop("signature"); a.pop("url")
    rep, res = _sol_scan(st, [_report([a], NOW - 30)], NOW)
    assert not st["incidents"] and res["telemetry"]["notAdmitted"] >= 1
    assert "immutable" in res["telemetry"]["notAdmittedDetail"][0]["reason"]


def test_R5_01_continuous_lifecycle_unchanged():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    LC.step(st, [sig("equities:SPY:T")], {"equities:SPY:T": 1.3}, {"equities": "HEALTHY"}, NOW)
    for i, want in ((1, "COOLING"), (2, "RESOLVED")):
        LC.step(st, [], {"equities:SPY:T": {"ratio": 0.4, "valid": True}}, {"equities": "HEALTHY"}, NOW + i * 600)
        assert st["incidents"]["equities:SPY:T"]["state"] == want


# ======================= R5-02: no raw vendor payloads in the public repo =======================

VENDOR_MARKERS = {
    "Yahoo chart": r'"exchangeTimezoneName"', "Nasdaq": r'"tradesTable"\s*:|"lastTrade": "LAST TRADE', "DefiLlama": r'"peggedAssets"',
    "treasury.gov CSV": r'"1 Mo","1\.5 Month"', "Gamma": r'"clobTokenIds"', "Kalshi": r'"yes_sub_title"|"previous_yes_bid_dollars"',
    "Cboe": r'"iv30_change_percent"|"seqno"', "OKX": r'"realizedRate"|"interestRate"|"instType": "SWAP"', "SEC Form 4": r"<ownershipDocument>.*<rptOwnerName>",
}


def _tracked():
    return subprocess.run(["git", "ls-files"], cwd=R, capture_output=True, text=True).stdout.split()


def test_R5_02_static_scan_no_unapproved_raw_vendor_payloads_tracked():
    bad = []
    allowed = {"tests/fixtures/contracts/synth.py", "tests/test_round5.py"}  # the synthetic generator and this scanner name the shapes
    for f in _tracked():
        p = R / f
        if f in allowed or (f.startswith("lib/") and p.suffix == ".py") or p.suffix in (".png", ".jpg", ".mp4", ".zip", ".gif", ".webp") or not p.is_file():
            continue
        try:
            t = p.read_text(errors="ignore")
        except OSError:
            continue
        for vendor, rx in VENDOR_MARKERS.items():
            if re.search(rx, t, re.S) and '"_provenance": "synthetic"' not in t:
                bad.append(f"{f}: {vendor}")
    assert not bad, bad
    assert not [f for f in _tracked() if f.startswith("tests/fixtures/providers/") or f.startswith("tests/fixtures/private/")]
    assert "tests/fixtures/private/" in (R / ".gitignore").read_text()


def test_R5_02_public_example_and_screenshots_are_synthetic():
    ex = json.loads((R / "examples/signals-EXAMPLE.json").read_text())
    assert ex.get("synthetic") is True and "SYNTHETIC" in ex["_note"]
    man = json.loads((R / "docs/screenshots-provenance.json").read_text())
    import hashlib
    for f, v in man["files"].items():
        assert v["source"].startswith("synthetic"), f
        assert hashlib.sha256((R / f).read_bytes()).hexdigest() == v["sha256"], f"{f} changed without a provenance update"
    shots = [f for f in _tracked() if f.startswith("docs/signals-") and f.endswith(".png")]
    assert shots and all(f in man["files"] for f in shots), shots


def test_R5_02_rights_register_names_the_basis_for_public_samples():
    pr = (R / "docs/PROVIDER-RIGHTS.md").read_text()
    assert "Public samples" in pr and "synthetic" in pr and "tests/fixtures/private/" in pr


# ======================= R5-03: cross-market episodes can't become immortal =======================

def _cross(st, members, at, k="cross:fed-policy:CONVERGENCE"):
    c = sig(k, "cross", members=members)
    return LC.step(st, [c], {}, {"treasury": "HEALTHY", "kalshi": "HEALTHY", "polymarket": "HEALTHY"}, at)


def test_R5_03_member_vanishes_72h_is_not_resolved_nor_fresh_active():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    _cross(st, ["treasury:2Y:A", "kalshi:FED:B"], NOW)
    K = "cross:fed-policy:CONVERGENCE"
    seen = []
    for h in range(6, 79, 6):  # A validly cool, B never observed again
        LC.step(st, [], {"treasury:2Y:A": {"ratio": 0.2, "valid": True}}, {"treasury": "HEALTHY", "kalshi": "HEALTHY"}, NOW + h * H)
        seen.append(st["incidents"][K]["state"])
    assert "RESOLVED" not in seen
    assert seen[-1] == "ARCHIVED_UNRESOLVED", seen
    assert "UNCONFIRMED" in seen and seen.index("UNCONFIRMED") < seen.index("ARCHIVED_UNRESOLVED")
    inc = st["incidents"][K]
    assert inc["lastConfirmedAt"] == NOW and inc["memberLastValid"].get("kalshi:FED:B") is None


def test_R5_03_disjoint_member_set_starts_a_new_episode_old_one_inspectable():
    st = {"incidents": {}, "lastSuccessAt": NOW - 600}
    _cross(st, ["treasury:2Y:A", "kalshi:FED:B"], NOW)
    r = _cross(st, ["equities:SPY:C", "polymarket:FED:D"], NOW + 600)
    inc = st["incidents"]["cross:fed-policy:CONVERGENCE"]
    assert inc["episode"] == 2 and inc["id"].endswith("#e2") and set(inc["members"]) == {"equities:SPY:C", "polymarket:FED:D"}
    prev = inc["previousEpisodes"][-1]
    assert prev["id"].endswith("#e1") and prev["members"] == ["treasury:2Y:A", "kalshi:FED:B"] and prev["endedAs"] == "SUPERSEDED"
    assert [a["alertReason"] for a in r["alerts"]] == ["NEW_EPISODE"]


def test_R5_03_round4_mixed_member_rules_still_hold():
    import test_round4 as R4
    R4.test_R4_01_mixed_members_one_hot_one_cool_stays_active_then_both_cool_resolves()
    R4.test_R4_01_composition_change_keeps_still_active_members()


# ======================= R5-04: SETTLES_ON_UNDERLYING needs an explicit settlement spec =======================

def test_R5_04_fed_funds_level_is_not_the_2y_yield():
    t = "Will the Fed funds rate be above 4% after the December 2026 meeting?"
    sp = EN.settlement_spec(t)
    assert sp and sp["settlementMetric"] == "FED_FUNDS_TARGET" and sp["referenceInstrument"] is None
    assert EN.relation(None, "fed-policy", "kalshi", t) == "SAME_EVENT"
    assert EN.settlement_instrument("fed-policy", t) is None


def test_R5_04_10y_yield_contract_maps_to_the_10y_metric_and_is_not_identical_to_tlt_options():
    t = "10Y Treasury yield above 4.5% on Dec 31, 2026?"
    sp = EN.settlement_spec(t)
    assert sp["settlementMetric"] == "UST_10Y_YIELD" and sp["referenceInstrument"] == "treasury:10Y" and sp["unit"] == "percent"
    assert sp["threshold"] == 4.5 and sp["polarity"] == "above" and sp["date"]
    o = fake("options", "us-treasuries", NOW, "options:TLT"); o["relations"] = {"us-treasuries": "DIRECT_PROXY"}
    k = fake("kalshi", "us-treasuries", NOW, None, title=t); k["relations"] = {"us-treasuries": EN.relation(None, "us-treasuries", "kalshi", t)}
    out = X.convergence([o, k], NOW + 60)
    assert not [c for c in out if c["type"] == "CONVERGENCE"]
    ex = [c for c in out if c["type"] == "RELATED_ACTIVITY"][0]["metrics"]["excluded"]
    why = " ".join(e["reason"] for e in ex)
    assert "correlated" in why and "mechanically linked" not in why and "identical" in why


def test_R5_04_btc_price_level_and_btc_spot_share_a_reference_no_independent_evidence():
    t = "Will Bitcoin be above $150,000 on December 31, 2026?"
    sp = EN.settlement_spec(t)
    assert sp["settlementMetric"] == "BTC_USD_PRICE" and sp["referenceInstrument"] == "crypto:BTC" and sp["threshold"] == 150000
    b = fake("crypto", "bitcoin", NOW, "crypto:BTC"); b["relations"] = {"bitcoin": "SAME_UNDERLYING"}
    p = fake("polymarket", "bitcoin", NOW, None, title=t); p["relations"] = {"bitcoin": EN.relation(None, "bitcoin", "polymarket", t)}
    out = X.convergence([b, p], NOW + 60)
    assert not [c for c in out if c["type"] == "CONVERGENCE"]
    assert any("same reference" in e["reason"] for c in out for e in c["metrics"].get("excluded", []))


def test_R5_04_ambiguous_company_forecast_is_unresolved():
    t = "Will Nvidia report quarterly revenue above $50B?"
    assert EN.settlement_spec(t) is None
    assert EN.relation(None, "nvidia", "polymarket", t) == "UNRESOLVED"
    t2 = "Will Tesla deliver above 500,000 cars in Q4?"
    assert EN.relation(None, "tesla", "kalshi", t2) == "UNRESOLVED"


# ======================= R5-05: provider contract tests (synthetic, offline) =======================

def test_R5_05_yahoo_contract():
    p = S.parse_yahoo_chart(SY.yahoo_chart("SPY"), need_volume=True)
    assert p["tz"] == "America/New_York" and len(p["rows"]) == 30
    j = SY.yahoo_chart(); del j["chart"]["result"][0]["meta"]["exchangeTimezoneName"]
    assert S.parse_yahoo_chart(j) is None, "no provider timezone metadata → rejected, not guessed"
    j = SY.yahoo_chart(); j["chart"]["result"][0]["timestamp"].pop()
    assert S.parse_yahoo_chart(j) is None, "array length mismatch = schema failure"
    j = SY.yahoo_chart(); q = j["chart"]["result"][0]["indicators"]["quote"][0]; q["close"][3] = None; q["close"][4] = "1.2"
    assert len(S.parse_yahoo_chart(j)["rows"]) == 28, "null/garbled closes skipped individually"
    assert S.parse_yahoo_chart({"chart": {"result": [], "error": {"code": "Not Found"}}}) is None and S.parse_yahoo_chart("<html>") is None


def test_R5_05_nasdaq_history_contract():
    rows = S.parse_nasdaq_hist(SY.nasdaq_hist())
    assert len(rows) == 30 and rows[0][0] < rows[-1][0] and rows[-1][0] % 86400 == 0
    j = SY.nasdaq_hist(); j["data"]["tradesTable"]["rows"][0]["close"] = "N/A"; j["data"]["tradesTable"]["rows"][1].pop("volume")
    assert len(S.parse_nasdaq_hist(j)) == 28
    assert S.parse_nasdaq_hist({"data": None}) is None and S.parse_nasdaq_hist({"data": {"tradesTable": {"rows": []}}}) is None
    assert S.parse_nasdaq_hist([1, 2]) is None


def test_R5_05_okx_candles_contract_uses_the_confirm_flag():
    rows = S.parse_okx_candles(SY.okx_candles())
    assert len(rows) == 29, "the forming candle (confirm=0) is dropped by the provider's own flag"
    assert S.parse_okx_candles(SY.okx_candles(forming=False)) and len(S.parse_okx_candles(SY.okx_candles(forming=False))) == 30
    j = SY.okx_candles(); j["data"][3][4] = "abc"; j["data"][4][0] = str(int(j["data"][4][0]) + 3_600_000)
    assert len(S.parse_okx_candles(j)) == 27, "garbled close and non-midnight (wrong bar) rows rejected"
    assert S.parse_okx_candles({"code": "51001", "msg": "Instrument ID does not exist", "data": []}) is None
    assert S.parse_okx_candles({"code": "0", "data": []}) is None and S.parse_okx_candles(None) is None


def test_R5_05_coinbase_contract():
    rows = S.parse_coinbase_candles(SY.coinbase_candles())
    assert len(rows) == 30 and rows[-1][2] > 0
    j = SY.coinbase_candles(); j[0][4] = None; j[1] = [1]; j[2][5] = -1
    assert len(S.parse_coinbase_candles(j)) == 27
    assert S.parse_coinbase_candles({"message": "NotFound"}) is None and S.parse_coinbase_candles([]) is None


def test_R5_05_treasury_csv_contract():
    rows = S.parse_treasury_csv(SY.treasury_csv())
    assert len(rows) == 30 and set(rows[0][1]) == {"3M", "2Y", "5Y", "10Y", "30Y"} and rows[0][0] < rows[-1][0]
    t = SY.treasury_csv().splitlines(); t[1] = t[1].split(",", 1)[0] + "," + ",".join(["N/A"] * 14); t[2] = "13/45/2026," + t[2].split(",", 1)[1]
    assert len(S.parse_treasury_csv("\n".join(t))) == 28
    assert S.parse_treasury_csv("Date,Foo\n10/27/2026,1\n") is None, "unknown header = schema failure"
    assert S.parse_treasury_csv("") is None and S.parse_treasury_csv(None) is None
    t = SY.treasury_csv().splitlines(); c = t[3].split(","); c[4] = "415.00"; t[3] = ",".join(c)  # 3 Mo column, percent typed as bps
    assert "3M" not in dict(S.parse_treasury_csv("\n".join(t)))[datetime.strptime(t[3].split(",")[0], "%m/%d/%Y").strftime("%Y-%m-%d")], "unit error (450%) dropped"


def test_R5_05_kalshi_contract():
    rows = S.parse_kalshi_events(SY.kalshi_events([SY.kalshi_market(), SY.kalshi_market("SYNTH-2", price="0.1000")]))
    assert len(rows) == 2 and rows[0]["price"] == 0.42 and rows[0]["prev"] == 0.30 and rows[0]["closeTs"]
    bad = [SY.kalshi_market("B1", price="abc"), SY.kalshi_market("B2", price="42"), SY.kalshi_market(None), SY.kalshi_market("OK")]
    assert [r["id"] for r in S.parse_kalshi_events(SY.kalshi_events(bad))] == ["OK"], "garbled, out-of-unit and id-less markets dropped individually"
    assert S.parse_kalshi_events(SY.kalshi_events(category="Sports")) is None
    assert S.parse_kalshi_events({"error": "x"}) is None and S.parse_kalshi_markets({"markets": "nope"}) is None
    assert S.parse_kalshi_markets({"markets": [SY.kalshi_market()]})[0]["id"]


def test_R5_05_gamma_contract():
    rows = S.parse_gamma([SY.gamma_market(0), SY.gamma_market(1)])
    assert len(rows) == 2 and rows[0]["price"] == 0.42 and rows[0]["tokenIds"] == ["111", "222"]
    bad = [SY.gamma_market(2, outcomePrices="not json"), SY.gamma_market(3, outcomePrices="[]"), SY.gamma_market(4, outcomePrices='"0.4"'), "x", SY.gamma_market(5)]
    assert [r["title"] for r in S.parse_gamma(bad)] == ["Synthetic question 5?"]
    assert S.parse_gamma({"error": "rate limited"}) is None and S.parse_gamma([]) is None


def test_R5_05_defillama_contract():
    rows = S.parse_llama(SY.llama())
    assert [r["symbol"] for r in rows] == ["SUSD"] and rows[0]["chains"], "< $1B excluded; per-chain deltas parsed"
    j = SY.llama(); j["peggedAssets"][0]["circulating"] = {"peggedUSD": "lots"}; j["peggedAssets"].append({"name": "no symbol"})
    assert S.parse_llama(j) is None
    j = SY.llama(); j["peggedAssets"][0]["chainCirculating"] = {"Ethereum": "bad"}
    assert S.parse_llama(j)[0]["chains"] == []
    assert S.parse_llama({"peggedAssets": None}) is None and S.parse_llama([]) is None


def test_R5_05_options_and_perps_contracts():
    c = S.parse_cboe(SY.cboe_chain(), 1793202974)
    assert len(c["rows"]) == 12 and c["snapshotTs"] == 1793202974 and c["underlying"] == 90.0
    j = SY.cboe_chain(); j["data"]["options"][0]["volume"] = None; j["data"]["options"][1]["option"] = "bad"
    assert S.parse_cboe(j, 1793202974)["rejected"] == 2
    assert S.parse_cboe(SY.cboe_chain(timestamp=""), 1793202974)["snapshotIssue"] == "missing snapshot time"
    n = S.parse_nasdaq(SY.nasdaq_chain(), "SYNT", 1793202974)
    assert n["snapshotTs"] == 1793202960 and n["rejected"] == 1 and any(r["volume"] == 0.0 for r in n["rows"])
    assert S.parse_nasdaq(SY.nasdaq_chain(last_trade="LAST TRADE: n/a"), "SYNT", 1793202974)["snapshotIssue"] == "missing snapshot time"
    o = S.parse_okx_perps(*SY.okx_perps())
    assert len(o["oi"]) == 40 and o["intervalH"] == 8.0 and all(g == 8.0 for _, _, g in o["funding"])
    oi, fr, cur = SY.okx_perps(); fr["data"][0]["fundingRate"] = "x"; fr["data"][0]["realizedRate"] = None
    assert len(S.parse_okx_perps(oi, fr, cur)["funding"]) == 39
    assert S.parse_okx_perps({"code": "50011"}, fr, cur) is None


def test_R5_05_one_malformed_instrument_cannot_mask_a_sibling_or_clear_an_incident():
    import test_round4 as R4
    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "s.json"
        R4._scan(R4.at(date(2026, 10, 22)), {"SPY": R4._rows(date(2026, 10, 22)), "QQQ": R4._rows(date(2026, 10, 22), seed=2)}, sp)
        R4._scan(R4.at(date(2026, 10, 23)), {"SPY": R4._rows(date(2026, 10, 23)), "QQQ": R4._rows(date(2026, 10, 23), True, seed=2)}, sp)
        bad = SY.yahoo_chart("QQQ"); bad["chart"]["result"][0]["timestamp"].pop()  # malformed payload for QQQ only
        assert S.parse_yahoo_chart(bad) is None
        r = R4._scan(R4.at(date(2026, 10, 26)), {"SPY": R4._rows(date(2026, 10, 26)), "QQQ": None}, sp)
        assert r["sourceStatus"]["equities"]["state"] == "DEGRADED"
        assert r["sourceStatus"]["equities"]["coverage"]["analyzedInstruments"] == ["SPY"]
        inc = json.loads(sp.read_text())["incidents"]["equities:QQQ:RETURN_VS_REALIZED_VOL"]
        assert inc["state"] not in ("RESOLVED", "ARCHIVED_UNRESOLVED") and inc["history"][-1]["event"] in ("HELD_UNOBSERVED", "SOURCE_UNAVAILABLE")


def test_R5_05_private_fixture_runner_skips_cleanly_offline():
    out = subprocess.run([sys.executable, str(R / "tests/test_private_fixtures.py")], capture_output=True, text=True, cwd=R)
    assert out.returncode == 0 and ("SKIPPED" in out.stdout or "private fixtures:" in out.stdout), out.stdout + out.stderr


# ======================= R5-06: evaluation objective =======================

def test_R5_06_evaluation_commits_to_objective_a_and_reports_insufficient_evidence():
    ev = (R / "docs/review/EVALUATION.md").read_text()
    assert "Release objective: A" in ev and "C is future research" in ev and "B is excluded" in ev
    cfg = json.loads((R / "docs/review/eval-config.json").read_text())
    assert cfg["objective"]["release"] == "A" and cfg["objective"]["excluded"] == ["B"] and cfg["objective"]["research"] == ["C"]
    assert cfg["frozen"]["thresholdsFrom"] and cfg["frozen"]["universe"]
    res = json.loads((R / "docs/review/eval-results.json").read_text())
    st = res["objectiveA"]
    assert st["status"] == "INSUFFICIENT_EVIDENCE" and st["adjudicatedEvents"] < 100 and st["precision"] is None
    assert (R / "docs/review/ADJUDICATION.md").exists()


# ======================= R5-07: CI honesty + suite runner =======================

def test_R5_07_ci_status_is_stated_honestly_and_runner_lists_totals():
    gh = R / ".github/workflows/tests.yml"
    rs = (R / "docs/review/ROUND5-RESULTS.md")
    assert gh.exists() or ("staged" in (R / "docs/ci/tests.yml").read_text().lower())
    run = (R / "tests/run_all.py").read_text()
    assert "SKIPPED" in run and "TOTAL" in run
    ci = (R / "docs/ci/tests.yml").read_text()
    for t in ("test_round5.py", "test_private_fixtures.py", "test_no_leaks.py", "sha256sum -c", "run_all.py"):
        assert t in ci, t


if __name__ == "__main__":
    n = fails = 0
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            n += 1
            try:
                v(); print("ok  ", k)
            except Exception as e:  # noqa: BLE001
                fails += 1; print("FAIL", k, "--", type(e).__name__, str(e)[:160])
    print(f"round5: {n - fails}/{n} passed")
    sys.exit(1 if fails else 0)
