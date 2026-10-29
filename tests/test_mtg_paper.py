"""MTG paper-printing price attribution regression suite (offline, SYNTHETIC fixtures in tests/fixtures/mtg).
Covers Power Nine and original-dual pins, paper/digital variants, same-name reprints, foil/nonfoil, language, absent paper
prices, unresolvable printings (unknown with a reason), and the committed data: no MTG observation references a
digital/MTGO printing, and every observation carries the exact printing it was computed from.  Run: python3 tests/test_mtg_paper.py"""
import json, os, sys, tempfile, time
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib")); sys.path.insert(0, str(R / "tools"))
from grok_the_block.everything import sources as SRC  # noqa: E402
import build_everything as B  # noqa: E402
import sync_tcg_art as SY  # noqa: E402

FX = json.loads((R / "tests/fixtures/mtg/paper-printings-synthetic.json").read_text())["routes"]
SEEN = []


def fake_get(url, *a, **k):
    SEEN.append(url)
    path = url.split("api.scryfall.com", 1)[-1]
    for r, v in FX.items():
        if path == r or path.startswith(r + "&"):
            return json.loads(json.dumps(v))
    return None


class patched:
    def __enter__(self):
        self.g, self.s = SRC.H.get, SRC.time.sleep
        SRC.H.get = fake_get; SRC.time.sleep = lambda *_: None; SEEN.clear(); return self

    def __exit__(self, *e):
        SRC.H.get, SRC.time.sleep = self.g, self.s


def test_power_nine_pin_ignores_mtgo_default_and_tix():
    with patched():
        c, why = SRC.scryfall_resolve("Black Lotus")
    assert why is None and (c["set"], c["cn"], c["paper"], c["lang"], c["finish"]) == ("2ed", "233", True, "en", "nonfoil")
    assert not any("named" in u for u in SEEN), "a pinned card must not consult the (digital) default printing"
    assert c["usd"] is None and c["eur"] == 20000.0  # tix 9.99 on the MTGO printing never becomes a USD paper price


def test_original_dual_pin_has_both_paper_venues():
    with patched():
        c, why = SRC.scryfall_resolve("Underground Sea")
    assert why is None and (c["set"], c["cn"], c["usd"], c["eur"]) == ("2ed", "286", 1500.0, 1000.0)


def test_pin_answered_with_other_edition_is_unknown_not_substituted():
    with patched():
        c, why = SRC.scryfall_resolve("Volcanic Island")
    assert c is None and "pinned paper printing 2ED #287 unavailable" in why


def test_pin_answered_digital_is_unknown():
    with patched():
        c, why = SRC.scryfall_resolve("Ancestral Recall")
    assert c is None and "digital-only" in why


def test_paper_digital_variants_fall_back_to_paper_printing():
    with patched():
        c, why = SRC.scryfall_resolve("Grim Monolith")
    assert why is None and (c["set"], c["cn"], c["paper"]) == ("ulg", "126", True)
    assert any("game%3Apaper" in u and "lang%3Aen" in u for u in SEEN)


def test_foil_only_never_uses_foil_price():
    with patched():
        c, why = SRC.scryfall_resolve("Foil Only")
    assert c is None and "no English nonfoil paper printing" in why and "foil-only" in why


def test_other_language_rejected_english_paper_selected():
    with patched():
        c, why = SRC.scryfall_resolve("German Card")
    assert why is None and (c["set"], c["lang"]) == ("gen", "en")
    de = SRC.parse_scryfall_card(FX["/cards/named?exact=German%20Card"])
    assert "language" in SRC.paper_reject(de, "German Card")


def test_name_mismatch_rejected():
    c = SRC.parse_scryfall_card(FX["/cards/2ed/286"])
    assert "different card" in SRC.paper_reject(c, "Volcanic Island")


def _sandbox():
    d = Path(tempfile.mkdtemp()); B.DD = d / "data"; B.SNAP = d / "snap"; B.DD.mkdir(); return d


def _mod(names, prev_rows=None, rate=1.1):
    real = SRC.scryfall_snapshot; dd, snap = B.DD, B.SNAP
    _sandbox()
    if prev_rows:
        (B.SNAP / "scryfall").mkdir(parents=True)
        (B.SNAP / "scryfall" / "2026-10-28.json").write_text(json.dumps(prev_rows))
    try:
        with patched():
            SRC.scryfall_snapshot = lambda: [(lambda r: r[0] if r[0] else {"name": n, "unresolved": r[1]})(SRC.scryfall_resolve(n)) for n in names]
            ctx = {"now": 1793300000, "prev": {}, "fx": {"USD": [(1793200000, rate)]}}
            return B.mod_mtg(ctx)
    finally:
        SRC.scryfall_snapshot = real; B.DD, B.SNAP = dd, snap


def test_unresolvable_printings_become_unknown_with_reason_and_module_degraded():
    S, P, A, cov = _mod(["Black Lotus", "Underground Sea", "Volcanic Island", "Ancestral Recall", "Foil Only"])
    names = {a["name"] for a in A}
    assert names == {"Black Lotus", "Underground Sea"}
    for n in ("Volcanic Island", "Ancestral Recall", "Foil Only"):
        ps = [p for p in P if p["asset"] == n]
        assert len(ps) == 2 and all(p["state"] == "unknown" and p["reason"].startswith("no paper printing identified") for p in ps), ps
    assert cov[0]["status"] == "DEGRADED" and {u["name"] for u in cov[0]["unresolved"]} == {"Volcanic Island", "Ancestral Recall", "Foil Only"}


def test_absent_paper_price_is_unknown_and_never_enters_history():
    S, P, A, cov = _mod(["Black Lotus", "No Prices"])
    for n in ("Black Lotus", "No Prices"):
        sp = next(p for p in P if p["asset"] == n and p["type"] == "CROSS_VENUE_SPREAD")
        assert sp["state"] == "unknown"
    assert cov[0]["snapshotDays"] == 0 and not S


def test_signals_carry_exact_printing_and_detector_threshold_unchanged():
    S, P, A, cov = _mod(["Underground Sea"])  # 1500 USD vs 1000 EUR * 1.1 = 1100 -> +30.8% < 40% flag
    sp = next(p for p in P if p["type"] == "CROSS_VENUE_SPREAD")
    assert sp["state"] == "measured" and abs(sp["ratio"] - round(abs((1500 - 1100) / 1300 * 100) / 40, 3)) < 1e-9 and not S
    S, P, A, cov = _mod(["Underground Sea"], rate=0.5)  # EUR 1000 * 0.5 = 500 -> +100% -> flagged
    assert len(S) == 1 and S[0]["printing"] == A[0]["printing"] and S[0]["printing"]["set"] == "2ed" and S[0]["printing"]["paper"]


def test_same_name_reprint_and_digital_rows_never_join_history():
    other = {"id": "00000000-0000-4000-8000-000000000299", "name": "Force of Will", "set": "all", "cn": "28", "lang": "en", "finish": "nonfoil", "paper": True, "usd": 5.0}
    digital = {"id": "x", "name": "Force of Will", "set": "dmr", "cn": "50", "lang": "en", "finish": "nonfoil", "paper": False, "usd": 1.0}
    S, P, A, cov = _mod(["Force of Will"], prev_rows=[other, digital])
    g = next(p for p in P if p["type"] == "GUIDE_MOVE_VS_30D_MEDIAN")
    assert "day 1 of 14" in g["reason"]  # only today's exact DMR #50 row; the ALL reprint and the digital row never join


def test_card_explorer_binding_requires_exact_id_and_finish():
    mk = lambda id_, set_, cn, fins=("nonfoil",), lang="en": {"object": "card", "id": id_, "name": "Force of Will", "set": set_, "set_name": set_, "collector_number": cn, "lang": lang,
                                                              "games": ["paper"], "digital": False, "finishes": list(fins), "rarity": "rare", "image_uris": {}, "scryfall_uri": f"https://scryfall.com/card/{set_}/{cn}/x"}
    cards = [mk("00000000-0000-4000-8000-000000000201", "dmr", "50"), mk("00000000-0000-4000-8000-000000000202", "dmr", "50", lang="ja"),
             mk("00000000-0000-4000-8000-000000000299", "all", "28")]
    t = [{"name": "Force of Will", "set": "dmr", "cn": "50", "lang": "en", "finish": "nonfoil", "id": "00000000-0000-4000-8000-000000000201"}]
    bound = [p for g in SY.build(cards, t, now=1)["groups"] for p in g["printings"] if p.get("tracked")]
    assert [p["id"] for p in bound] == ["00000000-0000-4000-8000-000000000201"]
    t2 = [dict(t[0], id="00000000-0000-4000-8000-00000000dead")]  # id disagrees -> no binding at all
    assert not [p for g in SY.build(cards, t2, now=1)["groups"] for p in g["printings"] if p.get("tracked")]
    foil = [mk("00000000-0000-4000-8000-000000000201", "dmr", "50", fins=("foil",))]
    assert not [p for g in SY.build(foil, t, now=1)["groups"] for p in g["printings"] if p.get("tracked")]


def test_committed_data_no_mtgo_binding_anywhere():
    j = json.loads((R / "data/everything/live-derived.json").read_text())
    assets = {a["name"]: a for a in j["assets"] if a.get("universe") == "mtg"}
    assert len(assets) >= 20
    for a in assets.values():
        pr = a["printing"]
        assert pr["paper"] is True and pr["finish"] == "nonfoil" and pr["lang"] == "en" and pr["id"] and pr["cn"], a["name"]
        assert f"/card/{pr['set']}/{pr['cn']}/" in a["url"] and pr["set"] not in ("vma", "tpr", "me1", "me2", "me3", "me4", "pz1", "pz2"), a["name"]
    for n, (st, cn) in SRC.PAPER_PIN.items():
        assert (assets[n]["printing"]["set"], assets[n]["printing"]["cn"]) == (st, cn), n
    for s in (x for x in j["signals"] if x["source"] == "mtg"):
        assert s.get("printing") == assets[s["asset"]]["printing"], s["asset"]
        assert all("/vma/" not in e["url"] and "/tpr/" not in e["url"] for e in s["evidence"])
    blob = (R / "ui/data/everything.js").read_text()
    assert "scryfall.com/card/vma/" not in blob and "scryfall.com/card/tpr/" not in blob


if __name__ == "__main__":
    ts = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    ok = 0
    for n, f in ts:
        try:
            f(); ok += 1; print("ok  ", n)
        except Exception as e:  # noqa: BLE001
            import traceback; traceback.print_exc(); print("FAIL", n, repr(e)[:300])
    print(f"{ok}/{len(ts)} passed")
    sys.exit(0 if ok == len(ts) else 1)
