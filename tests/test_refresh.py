"""RC2 refresh runner: per-module isolation, last-good-cache preservation, stale/unknown marking, cadence, single-run
lock, atomic writes, HTTP backoff/failure simulation, derived-only markets cache, MTG paper pinning.
Offline: every provider call is replaced by an in-process fake. Run: python3 tests/test_refresh.py"""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib")); sys.path.insert(0, str(R / "tools"))
import build_everything as B  # noqa: E402
from grok_the_block.markets import http as HT  # noqa: E402
from grok_the_block.everything import sources as SRC  # noqa: E402

ORIG = dict(B.MODULES)


def sandbox():
    d = Path(tempfile.mkdtemp()); B.DD = d / "data"; B.SNAP = d / "snap"; B.DD.mkdir(); return d


def fake(sig_key="k1", fail=False):
    def fn(ctx):
        if fail:
            raise TimeoutError("simulated")
        return ([{"key": sig_key, "source": "fx", "type": "T", "severity": "LOW"}], [{"asset": "A", "type": "T", "state": "measured", "ratio": 0.5}],
                [{"id": "A", "universe": "fx-majors", "name": "A"}], [{"module": "fx", "status": "HEALTHY", "via": "fake", "observed": 1}])
    return fn


def only_fx(fn):
    B.MODULES = {"fx": fn}; B.CADENCE.setdefault("fx", 86400)


def test_two_runs_no_duplicate_ids_and_metadata():
    sandbox(); only_fx(fake())
    a = B.fetch(); time.sleep(1.1); b = B.fetch()
    assert [s["key"] for s in b["signals"]] == ["k1"]
    h = b["health"][0]
    assert h["status"] == "HEALTHY" and h["lastSuccessAt"] == b["generatedAt"] and h["lastAttemptAt"] == b["generatedAt"] and h["nextExpectedRun"] == h["lastSuccessAt"] + 86400
    assert b["generatedAt"] > a["generatedAt"] and b["lastRun"]["ok"]


def test_failure_keeps_last_good_cache_and_marks_stale():
    sandbox(); only_fx(fake()); good = B.fetch(); time.sleep(1.1)
    only_fx(fake(fail=True)); bad = B.fetch()
    assert [s["key"] for s in bad["signals"]] == ["k1"] and bad["assets"] == good["assets"]
    c = [c for c in bad["coverage"] if c["module"] == "fx"][0]
    h = bad["health"][0]
    assert c["status"] == "STALE" and h["status"] == "STALE" and h["errorCategory"] == "timeout"
    assert h["lastSuccessAt"] == good["generatedAt"] and h["lastAttemptAt"] == bad["generatedAt"] and not bad["lastRun"]["ok"]
    json.loads((B.DD / "live-derived.json").read_text())


def test_never_succeeded_failure_is_unavailable_not_quiet():
    sandbox(); only_fx(fake(fail=True)); o = B.fetch()
    assert o["signals"] == [] and [c["status"] for c in o["coverage"]] == ["UNAVAILABLE"]


def test_scheduled_skips_modules_not_due():
    sandbox(); calls = []
    def fn(ctx):
        calls.append(1); return fake()(ctx)
    only_fx(fn); B.fetch(); B.fetch(scheduled=True)
    assert len(calls) == 1


def test_lock_blocks_live_run_and_reclaims_dead_pid():
    d = sandbox(); lp = d / "lock"
    lp.write_text(json.dumps({"pid": os.getpid(), "at": int(time.time())}))
    try:
        with B.Lock(lp):
            raise AssertionError("should not acquire")
    except SystemExit as e:
        assert "already running" in str(e)
    p = subprocess.Popen([sys.executable, "-c", "pass"]); p.wait()
    lp.write_text(json.dumps({"pid": p.pid, "at": int(time.time())}))
    with B.Lock(lp):
        assert json.loads(lp.read_text())["pid"] == os.getpid()
    assert not lp.exists()


def test_atomic_write_never_leaves_partial_file():
    d = sandbox(); f = d / "x.json"; B.atomic_write(f, '{"a": 1}')
    real = os.replace
    def boom(*a):
        raise KeyboardInterrupt("interrupted")
    os.replace = boom
    try:
        B.atomic_write(f, '{"a": 2, "partial"')
    except KeyboardInterrupt:
        pass
    finally:
        os.replace = real
    assert json.loads(f.read_text()) == {"a": 1}


def test_http_simulated_429_and_timeout_back_off_then_fail():
    os.environ["GTB_HTTP_BACKOFF_BASE"] = "0.01"
    try:
        for mode, cat in (("429", "rate_limited"), ("timeout", "timeout"), ("5xx", "http_5xx"), ("schema", "schema")):
            os.environ["GTB_HTTP_SIMULATE"] = f"{mode}:simprov"
            t = time.time()
            assert HT.get("http://127.0.0.1:9/x", "simprov", max_age=0) is None
            assert HT.LAST_ERR["simprov"] == cat, (mode, HT.LAST_ERR)
            if mode in ("429", "timeout", "5xx"):
                assert time.time() - t >= 0.07  # 3 attempts with 0.01, 0.02, 0.04 s backoff
    finally:
        os.environ.pop("GTB_HTTP_SIMULATE", None); os.environ.pop("GTB_HTTP_BACKOFF_BASE", None)


def test_derived_markets_cache_drops_vendor_values():
    s = {"key": "options:NVDA:X", "source": "options", "type": "UNUSUAL", "severity": "LOW", "title": "NVDA: 8 contracts with unusual observed volume vs open interest (≈$46.2M premium)",
         "what": "$715,267 in 24h", "metrics": {"premiumUsd": 46200000, "ratio": 3.1, "contracts": [{"x": 1}]}, "evidence": [{"label": "Cboe", "url": "https://cboe", "raw": 1}]}
    d = B.derive_signal(s)
    assert "$" not in d["title"] and "$" not in d["what"] and d["metrics"] == {"ratio": 3.1} and d["derivedOnly"] and d["evidence"] == [{"label": "Cboe", "url": "https://cboe"}]
    t = B.derive_signal({"key": "treasury:10Y", "source": "treasury", "title": "10Y +12bp", "what": "10Y moved 12bp", "metrics": {"changeBp": 12}})
    assert t["what"] == "10Y moved 12bp" and t["metrics"] == {"changeBp": 12} and not t.get("derivedOnly")
    assert "volume traded" in B._scrub("Insufficient baseline: $169,184 traded in 24h on “Will BTC be above $72,000?”") and "$72,000" in B._scrub("“Will BTC be above $72,000?”")


def test_markets_failed_source_carries_previous_signals_as_stale():
    from grok_the_block.markets import feed as F
    real = F.run
    prev = {"markets": {"signals": [{"key": "kalshi:A", "source": "kalshi", "title": "t"}], "sourceStatus": {"kalshi": {"lastSuccessAt": 111, "lastValidAt": "x"}}}}
    F.run = lambda *a, **k: {"generatedAt": 5, "status": "partial", "signals": [], "sourceStatus": {"kalshi": {"state": "UNAVAILABLE", "detail": "403", "coverage": {}}, "treasury": {"state": "HEALTHY", "coverage": {"observed": 4}}},
                             "assessment": {"severity": "INFO", "lead": {}}, "coverage": {"limits": [], "matrix": []}}
    try:
        m = B.mod_markets({"now": 10, "prev": prev})
    finally:
        F.run = real
    k, t = m["sourceStatus"]["kalshi"], m["sourceStatus"]["treasury"]
    assert k["outcome"] == "BLOCKED_EXTERNAL" and k["assessment"] == "unknown" and k["lastSuccessAt"] == 111
    assert t["outcome"] == "FETCHED" and t["assessment"] == "quiet" and t["lastSuccessAt"] == 10
    assert m["signals"][0]["key"] == "kalshi:A" and m["signals"][0]["carried"]


def test_paper_pin_never_returns_digital_printing():
    real = SRC.H.get
    seen = []
    def g(url, *a, **k):
        seen.append(url)
        if "/cards/2ed/233" in url:
            return {"object": "card", "id": "p", "name": "Black Lotus", "set": "2ed", "collector_number": "233", "games": ["paper"], "digital": False, "prices": {"eur": "1"}, "scryfall_uri": "https://scryfall.com/card/2ed/233/black-lotus"}
        if "named" in url:
            return {"object": "card", "id": "d", "name": "Grim Monolith", "set": "vma", "collector_number": "9", "games": ["mtgo"], "digital": True, "prices": {}, "scryfall_uri": "u"}
        if "search" in url:
            return {"data": [{"object": "card", "id": "q", "name": "Grim Monolith", "set": "ulg", "collector_number": "126", "games": ["paper", "mtgo"], "digital": False, "prices": {"usd": "5"}, "scryfall_uri": "u2"}]}
    SRC.H.get = g
    try:
        a = SRC.scryfall_card("Black Lotus"); b = SRC.scryfall_card("Grim Monolith")
    finally:
        SRC.H.get = real
    assert (a["set"], a["cn"], a["paper"]) == ("2ed", "233", True) and "/cards/2ed/233" in seen[0]
    assert (b["set"], b["cn"], b["paper"]) == ("ulg", "126", True)
    assert set(SRC.PAPER_PIN) >= {"Black Lotus", "Mox Sapphire", "Ancestral Recall", "Time Walk", "Timetwister", "Underground Sea", "Volcanic Island", "Mox Diamond"}


def test_mtg_snapshot_daily_idempotent_and_keyed_by_printing():
    sandbox(); real = SRC.scryfall_snapshot
    (B.SNAP / "scryfall").mkdir(parents=True)
    (B.SNAP / "scryfall" / "2026-10-28.json").write_text(json.dumps([{"name": "Black Lotus", "set": "vma", "usd": 9000.0}]))  # old digital row, no cn
    SRC.scryfall_snapshot = lambda: [{"id": "p", "name": "Black Lotus", "set": "2ed", "cn": "233", "lang": "en", "finish": "nonfoil", "paper": True, "usd": 10.0, "eur": 9.0, "url": "u"}]
    try:
        r1 = B.mod_mtg({"now": 1793260800, "prev": {}}); r2 = B.mod_mtg({"now": 1793260900, "prev": {}})
    finally:
        SRC.scryfall_snapshot = real
    assert len(list((B.SNAP / "scryfall").glob("*.json"))) == 2  # same day twice -> one file for that day
    assert r2[3][0]["snapshotDays"] == 1 and "day 1 of 14" in r2[1][0]["reason"]  # the VMA row never joins the 2ED history
    assert r1[2][0]["printing"] == {"provider": "scryfall", "id": "p", "set": "2ed", "cn": "233", "lang": "en", "finish": "nonfoil", "paper": True}


def test_committed_data_has_no_digital_mtg_binding_and_no_secrets():
    j = json.loads((R / "data/everything/live-derived.json").read_text())
    mtg = [a for a in j["assets"] if a.get("universe") == "mtg"]
    assert mtg and all(a.get("printing", {}).get("paper") for a in mtg) and not any("/vma/" in a["url"] or "/tpr/" in a["url"] for a in mtg)
    blob = (R / "ui/data/everything.js").read_text()
    for k in ("Authorization", "api_key", "apikey", "Bearer ") + tuple(v for n, v in os.environ.items() if n.startswith("GTB_") and len(v) > 8):
        assert k not in blob, "secret-like value in everything.js"
    m = (R / "data/everything/markets-derived.json")
    if m.exists():
        mk = json.loads(m.read_text())
        assert all(v["outcome"] in ("FETCHED", "DEGRADED", "BLOCKED_EXTERNAL", "NOT_CONFIGURED") for v in mk["sourceStatus"].values())
        assert all("$" not in s["what"] for s in mk["signals"] if s.get("derivedOnly"))


if __name__ == "__main__":
    ts = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    ok = 0
    for n, f in ts:
        DD, SNAP = B.DD, B.SNAP
        try:
            f(); ok += 1
        except Exception as e:  # noqa: BLE001
            print("FAIL", n, repr(e)[:300])
        finally:
            B.DD, B.SNAP, B.MODULES = DD, SNAP, dict(ORIG)
    print(f"{ok}/{len(ts)} passed")
    sys.exit(0 if ok == len(ts) else 1)
