"""Everything-markets: parsers, detectors, data files and product rules. Offline; fixtures are tiny and synthetic
(provider-shaped, invented numbers), so no vendor data is committed."""
import json, math, re, subprocess, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib"))
from grok_the_block.everything import detectors as X, sources as S  # noqa: E402

D0 = 1767225600  # 2026-01-01
PROVENANCE = '"_provenance": "synthetic"'  # R5-02 marker: every provider-shaped fixture in this file is invented


def series(n, start=1.10, step=0.0005, jump=None):
    rows, v = [], start
    for i in range(n):
        v *= 1 + (step if i % 2 else -step * 0.9)
        rows.append((D0 + i * 86400, v))
    if jump:
        rows[-1] = (rows[-1][0], rows[-2][1] * (1 + jump))
    return rows


# ---------------- parsers ----------------
def test_parse_ecb_csv():
    t = "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\nEXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-10-27,1.0812\nEXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-10-26,1.0790\nEXR.D.JPY.EUR.SP00.A,D,JPY,EUR,SP00,A,2026-10-27,165.2\n"
    s = S.parse_ecb_csv(t)
    assert list(s) == ["USD", "JPY"] and s["USD"][0][1] == 1.079 and s["USD"][0][0] < s["USD"][1][0]
    assert S.parse_ecb_csv("<html>") is None and S.parse_ecb_csv("") is None

def test_parse_frankfurter():
    s = S.parse_frankfurter({"base": "EUR", "rates": {"2026-10-27": {"USD": 1.08, "JPY": 165.0}, "2026-10-26": {"USD": 1.07}}})
    assert s["USD"] == [(S._day("2026-10-26"), 1.07), (S._day("2026-10-27"), 1.08)]
    assert S.parse_frankfurter({"base": "USD", "rates": {}}) is None and S.parse_frankfurter(None) is None

def test_parse_fred_csv_skips_missing():
    s = S.parse_fred_csv("observation_date,DCOILWTICO\n2026-10-26,61.2\n2026-10-27,.\n2026-10-28,62.0\n")
    assert [v for _, v in s] == [61.2, 62.0]
    assert S.parse_fred_csv("") is None

def test_parse_nasdaq_reexport():
    j = {"data": {"tradesTable": {"rows": [{"date": "10/28/2026", "close": "$373.51", "volume": "9,013,109"}, {"date": "10/27/2026", "close": "370.00", "volume": "8,000,000"}]}}}
    r = S.parse_nasdaq_hist(j)
    assert r[0][1] == 370.0 and r[1][2] == 9013109.0

def test_parse_cot():
    rows = [{"market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.", "report_date_as_yyyy_mm_dd": f"2026-0{m}-01T00:00:00.000", "noncomm_positions_long_all": "300000", "noncomm_positions_short_all": "50000", "open_interest_all": "500000"} for m in (3, 1, 2)]
    c = S.parse_cot(rows + [{"bad": 1}])
    g = c["GOLD - COMMODITY EXCHANGE INC."]
    assert len(g) == 3 and g[0]["ts"] < g[1]["ts"] < g[2]["ts"] and g[0]["long"] == 300000.0
    assert S.parse_cot("x") is None

def test_parse_scryfall_keeps_only_identity_and_venue_prices():
    c = S.parse_scryfall_card({"object": "card", "id": "x", "name": "Card", "set": "abc", "set_name": "Set", "prices": {"usd": "10.50", "eur": "8.00", "usd_foil": None, "tix": "0.1"}, "scryfall_uri": "https://scryfall.com/card/abc/1/card?utm_source=api", "image_uris": {"png": "https://..."}})
    assert c["usd"] == 10.5 and c["eur"] == 8.0 and c["usd_foil"] is None and "image_uris" not in c and "?" not in c["url"]
    assert S.parse_scryfall_card({"object": "error"}) is None

def test_parse_steam_overview():
    o = S.parse_steam_overview({"success": True, "lowest_price": "$1,032.00", "volume": "1,247", "median_price": "$1,000.50"})
    assert o == {"lowest": 1032.0, "median": 1000.5, "volume24h": 1247}
    assert S.parse_steam_overview({"success": True, "lowest_price": "$2"})["volume24h"] == 0
    assert S.parse_steam_overview({"success": False}) is None


# ---------------- liquid detectors ----------------
def test_daily_move_flags_jump_and_not_calm():
    s, p = X.daily_move("fx", "fx", "EUR/TRY", "EUR/TRY", series(60, jump=0.03), "https://x")
    assert len(s) == 1 and s[0]["type"] == "MOVE_VS_REALIZED_VOL" and s[0]["severity"] in ("MEDIUM", "HIGH") and p[0]["state"] == "measured"
    s, p = X.daily_move("fx", "fx", "EUR/USD", "EUR/USD", series(60), "https://x")
    assert s == [] and p[0]["ratio"] < 1

def test_daily_move_insufficient_history_is_unknown():
    s, p = X.daily_move("fx", "fx", "EUR/X", "EUR/X", series(10), "https://x")
    assert s == [] and p[0]["state"] == "unknown" and "insufficient" in p[0]["reason"]

def test_daily_move_volume_spike_and_derived_only_hides_prices():
    rows = [(t, v, 1e6 * (1 + 0.05 * (i % 3))) for i, (t, v) in enumerate(series(80))]
    rows[-1] = (rows[-1][0], rows[-1][1], 6e6)
    s, _ = X.daily_move("metals", "metals", "GLD", "Gold ETF", rows, "https://x", derived_only=True)
    v = [x for x in s if x["type"] == "VOLUME_ROBUST_Z"]
    assert v and v[0]["derivedOnly"] and "last" not in v[0]["metrics"]
    s, _ = X.daily_move("metals", "metals", "GLD", "Gold ETF", [(t, c, 1e6) for t, c in series(60, jump=0.05)], "https://x", derived_only=True)
    assert s and "last" not in s[0]["metrics"] and "prev" not in s[0]["metrics"]

def test_fx_crosscheck_flags_only_outsized_gap():
    a = series(80); b = [(t, v * 1.0005) for t, v in a]
    s, p = X.fx_crosscheck("EUR/USD", a, b, "u1", "u2")
    assert s == [] and p[0]["state"] in ("measured", "unknown")
    b2 = [(t, v * (1.0005 + (0.00002 * (i % 3)))) for i, (t, v) in enumerate(a)]; b2[-1] = (b2[-1][0], a[-1][1] * 1.01)
    s, _ = X.fx_crosscheck("EUR/USD", a, b2, "u1", "u2")
    assert s and s[0]["type"] == "FIX_CROSSCHECK" and s[0]["severity"] == "LOW" and abs(s[0]["metrics"]["gapBp"]) > 50
    s, p = X.fx_crosscheck("EUR/USD", a[:10], b[:10], "u1", "u2")
    assert p[0]["state"] == "unknown"

def test_pair_divergence():
    a = [(t, v, 1e6) for t, v in series(90)]
    b = [(t, v * 0.054 * (1 + 0.0001 * ((i * 7) % 5 - 2)), 1e6) for i, (t, v) in enumerate(series(90))]
    b[-1] = (b[-1][0], b[-2][1] * 0.98, 1e6)
    s, p = X.pair_divergence("metals", "GLD~IAU", "Gold trackers", a, b, "u1", "u2")
    assert s and s[0]["severity"] in ("LOW", "MEDIUM") and s[0]["derivedOnly"]
    s, p = X.pair_divergence("metals", "GLD~IAU", "Gold trackers", a[:20], b[:20], "u1", "u2")
    assert s == [] and p[0]["state"] == "unknown"

def test_cross_venue_spread_evidence_only_and_capped():
    items = [{"name": "A", "usd": 100.0, "eur": 40.0, "url": "https://scryfall.com/a"}, {"name": "B", "usd": 10.0, "eur": 9.0, "url": "u"}, {"name": "C", "usd": 2.0, "eur": None, "url": "u"}]
    s, p = X.cross_venue_spread("cards", items, 1.08, "2026-10-27")
    assert len(s) == 1 and s[0]["asset"] == "A" and s[0]["severity"] in ("LOW", "MEDIUM") and X.NOT_ARB in s[0]["limits"]
    assert [x["state"] for x in p] == ["measured", "measured", "unknown"]

def test_steam_gap_thin_market_unknown_and_low_cap():
    s, p = X.steam_ask_gap([{"name": "x", "lowest": 200, "median": 100, "volume24h": 50, "url": "u"}, {"name": "y", "lowest": 3, "median": 1, "volume24h": 2, "url": "u"}])
    assert len(s) == 1 and s[0]["severity"] == "LOW" and s[0]["derivedOnly"] and p[1]["state"] == "unknown" and "thin" in p[1]["reason"]

def test_cot_shift():
    rows = [{"ts": D0 + i * 7 * 86400, "long": 200000 + (i % 3) * 1000, "short": 100000, "oi": 500000} for i in range(60)]
    rows[-1] = {**rows[-1], "long": 260000}
    s, p = X.cot_shift("GOLD", "Gold futures", rows, "u")
    assert s and s[0]["type"] == "COT_POSITIONING_SHIFT" and "individual" in s[0]["limits"][0]
    s, p = X.cot_shift("GOLD", "Gold futures", rows[:10], "u")
    assert p[0]["state"] == "unknown"


# ---------------- thin-market detectors ----------------
def sales(prices, grade="CIB", start=D0):
    return [{"ts": start + i * 86400, "price": p, "grade": grade} for i, p in enumerate(prices)]

def test_sparse_gate():
    assert X.sparse_gate("x", sales([1, 2]), 5)["state"] == "unknown"
    assert "no sales" in X.sparse_gate("x", [], 5)["reason"]
    assert X.sparse_gate("x", sales([1] * 5), 5) is None

def test_snapshot_move_needs_history_then_flags():
    s, p = X.snapshot_move("cards", "mtg", "c", "c", [(D0, 10.0)], "u")
    assert s == [] and "day 1 of 14" in p[0]["reason"]
    snaps = [(D0 + i * 86400, 10.0) for i in range(20)] + [(D0 + 20 * 86400, 16.0)]
    s, p = X.snapshot_move("cards", "mtg", "c", "c", snaps, "u")
    assert s and s[0]["metrics"]["movePct"] == 60.0 and s[0]["severity"] == "MEDIUM"

def test_outlier_sale_single_low_repeat_medium():
    base = [100, 104, 98, 101, 99, 103, 97, 102]
    s, _ = X.outlier_sale("games", "t", "a", "a", sales(base + [300]), "u")
    assert len(s) == 1 and s[0]["severity"] == "LOW"
    s, _ = X.outlier_sale("games", "t", "a", "a", sales(base + [300, 310]), "u")
    assert s[0]["severity"] == "MEDIUM" and s[0]["metrics"]["repeats7d"] == 2
    s, p = X.outlier_sale("games", "t", "a", "a", sales([100, 300]), "u")
    assert s == [] and p[0]["state"] == "unknown"

def test_outlier_is_per_grade():
    mixed = sales([100, 101, 99, 100, 102, 98]) + sales([400, 404, 396, 401, 399, 403], grade="PSA 10")
    s, _ = X.outlier_sale("cards", "t", "a", "a", mixed, "u")
    assert s == []  # a PSA 10 sale is not an outlier against raw sales

def test_grade_mix_reports_mix_not_move():
    prev = sales([40, 41, 39, 40, 400, 40], grade="raw"); prev[4]["grade"] = "PSA 10"; prev.append({"ts": D0, "price": 401, "grade": "PSA 10"})
    cur = [{"ts": D0 + 40 * 86400 + i, "price": p, "grade": g} for i, (p, g) in enumerate([(41, "raw"), (402, "PSA 10"), (40, "raw"), (399, "PSA 10"), (403, "PSA 10"), (41, "raw")])]
    s, _ = X.grade_mix("cards", "t", "a", "a", prev, cur, "u")
    assert s and s[0]["type"] == "GRADE_MIX_SHIFT" and s[0]["severity"] == "INFO" and abs(s[0]["metrics"]["withinGradePct"]) < 8

def test_wash_pattern_capped_with_limit_text():
    s, _ = X.wash_pattern("cards", "t", "a", "a", sales([250, 310, 250, 310, 250, 310, 250]), "u")
    assert s and s[0]["severity"] in ("LOW", "MEDIUM") and X.PATTERN_LIMIT in s[0]["limits"] and s[0]["basis"] == "heuristic"
    s, _ = X.wash_pattern("cards", "t", "a", "a", sales([100, 120, 110, 130, 115]), "u")
    assert s == []

def test_supply_shock_and_guide_divergence():
    c = [(D0 + i * 86400, 100) for i in range(30)] + [(D0 + 30 * 86400, 330)]
    s, _ = X.supply_shock("cards", "t", "a", "a", c, "u")
    assert s and s[0]["metrics"]["ratio"] == 3.3
    s, _ = X.guide_divergence("collectibles", "t", "a", "a", 60.0, sales([95] * 6), "u")
    assert s and s[0]["metrics"]["gapPct"] > 50 and "Not an appraisal." in s[0]["limits"]

def test_no_advice_or_identity_words_in_any_detector_text():
    import inspect
    src = inspect.getsource(X)
    titles = " ".join(re.findall(r'title=f?"([^"]*)"', src) + re.findall(r'what=f?"([^"]*)"', src)).lower()
    assert not re.search(r"\b(buy|sell|hold|should|moon|scam|insider|seller \w+ is)\b", titles), titles


# ---------------- data files ----------------
def test_universe_has_50_plus_with_required_fields():
    u = json.loads((R / "data/everything/universe.json").read_text())
    a = u["assets"]
    assert len(a) >= 50 and len({x["id"] for x in a}) == len(a)
    for x in a:
        assert x["access"] in ("free-redistributable", "derived-signals-only", "paid", "partner-only", "blocked"), x
        assert x["status"] in ("shipped", "feasible-next", "blocked-licence"), x
        assert x["sourceUrl"].startswith("https://") and x["venues"] and x["arbitrage"] and x["category"] in u["categories"], x
    ids = {x["id"]: x for x in a}
    for need in ("fx-majors", "gold", "mtg", "cs2-skins", "pokemon", "retro-games", "sneakers", "carbon", "freight", "gift-cards"):
        assert need in ids, need
    assert ids["cs2-skins"]["status"] != "shipped" and ids["pokemon"]["status"] == "blocked-licence"

def test_generated_files_in_sync():
    r = subprocess.run([sys.executable, str(R / "tools/build_everything.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

def test_synthetic_is_flagged_and_live_is_not():
    syn = json.loads((R / "data/everything/synthetic.json").read_text())
    assert syn["synthetic"] and syn["signals"] and all(s["synthetic"] and s["title"].startswith("[SYNTHETIC]") for s in syn["signals"])
    types = {s["type"] for s in syn["signals"]}
    assert {"OUTLIER_SALE", "GRADE_MIX_SHIFT", "ROUND_TRIP_PATTERN", "SUPPLY_SHOCK", "GUIDE_VS_SALES", "CROSS_VENUE_SPREAD"} <= types, types
    live = json.loads((R / "data/everything/live-derived.json").read_text())
    assert not live["synthetic"] and all(not s["synthetic"] for s in live["signals"])

def test_live_file_has_no_vendor_price_tables():
    live = json.loads((R / "data/everything/live-derived.json").read_text())
    for a in live["assets"]:
        if not a["redistributable"]:
            assert "spark" not in a and "last" not in a, a
    for s in live["signals"]:
        if s["derivedOnly"]:
            assert not {"last", "prev", "usd", "eur", "lowest", "median"} & set(s["metrics"]), s
    txt = (R / "data/everything/live-derived.json").read_text()
    assert "api_key" not in txt and "GTB_" not in txt


if __name__ == "__main__":
    n = fails = 0
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            n += 1
            try:
                v(); print("ok  ", k)
            except Exception as e:  # noqa: BLE001
                fails += 1; print("FAIL", k, "--", type(e).__name__, str(e)[:300])
    print(f"everything: {n - fails}/{n} passed")
    sys.exit(1 if fails else 0)
