"""Card Explorer: adapter identity, exact-printing artwork selection, opt-in sync rules, cache isolation, rights gating.
Offline; uses SYNTHETIC Scryfall-shaped fixtures (tests/fixtures/tcg). Run: python3 tests/test_tcg.py"""
import json, re, subprocess, sys, tempfile
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib")); sys.path.insert(0, str(R / "tools"))
from grok_the_block.tcg.adapters import ScryfallAdapter, ADAPTERS, group_printings, printing_key, parse_scryfall_uri  # noqa: E402
import sync_tcg_art as SY  # noqa: E402

CARDS = json.loads((R / "tests/fixtures/tcg/scryfall-synthetic.json").read_text())["data"]
A = ScryfallAdapter()
TR = [{"name": "Synthetic Lotus", "set": "aaa", "cn": "1", "lang": "en", "finish": "nonfoil"}]


def doc(download=None, tracked=TR, **kw):
    return SY.build(CARDS, tracked, download=download, now=1_800_000_000, **kw)


def allp(d):
    return [p for g in d["groups"] for p in g["printings"]]


def test_identity_key_includes_id_set_cn_lang():
    p = A.printing(CARDS[0])
    assert p["key"] == printing_key("scryfall", CARDS[0]["id"], "aaa", "1", "en") == "scryfall:00000000-0000-4000-8000-000000000001:aaa:1:en"


def test_same_set_cn_other_language_is_a_different_printing():
    en, de = A.printing(CARDS[0]), A.printing(CARDS[4])
    assert en["key"] != de["key"] and en["lang"] == "en" and de["lang"] == "de"


def test_image_is_the_exact_printing_not_first_name_match():
    for c in CARDS[:5]:
        p = A.printing(c)
        assert all(c["id"] in u for f in p["faces"] for u in f["uris"].values()), c["id"]


def test_double_faced_uses_card_faces_image_uris():
    p = A.printing(CARDS[6])
    assert len(p["faces"]) == 2 and "/front/" in p["faces"][0]["uris"]["small"] and "/back/" in p["faces"][1]["uris"]["small"]
    assert p["faces"][0]["name"] == "Synthetic Delver" and p["faces"][1]["name"] == "Synthetic Aberration"


def test_adventure_with_card_faces_but_top_level_image_uses_single_image():
    p = A.printing(CARDS[7])
    assert len(p["faces"]) == 1 and "/front/" in p["faces"][0]["uris"]["small"]


def test_duplicate_names_with_different_oracle_ids_stay_separate():
    d = doc()
    lotus = [g for g in d["groups"] if g["name"] == "Synthetic Lotus"]
    assert len(lotus) == 2 and {g["oracle_id"] for g in lotus} == {"o-lotus", "o-other"}


def test_alternate_art_reprint_and_print_variant_separated():
    d = doc(); g = next(g for g in d["groups"] if g["oracle_id"] == "o-lotus")
    kind = {p["id"][-1]: p["kind"] for p in g["printings"]}
    assert kind["1"] == "tracked" and kind["2"] == "reprint" and kind["3"] == "alternate art" and kind["4"] == "print variant"


def test_market_binding_only_on_exact_tracked_printing_and_finish():
    d = doc(); bound = [p for p in allp(d) if p.get("tracked")]
    assert len(bound) == 1 and bound[0]["id"].endswith("1") and bound[0]["lang"] == "en" and bound[0]["tracked"]["finish"] == "nonfoil"
    # same name in another set, same set/cn in German, and the other oracle card with the same name get nothing
    assert all(not p.get("tracked") for p in allp(d) if p["name"] == "Synthetic Lotus" and p is not bound[0])


def test_tracked_binding_requires_name_match_too():
    d = doc(tracked=[{"name": "Another Card", "set": "aaa", "cn": "1", "lang": "en", "finish": "nonfoil"}])
    assert not any(p.get("tracked") for p in allp(d))


def test_no_prices_in_browser_cache_document():
    s = json.dumps(doc())
    assert "99.00" not in s and '"usd"' not in s and '"prices"' not in s


def test_missing_and_placeholder_imagery():
    d = doc(download=lambda u, dest: True)
    miss = next(p for p in allp(d) if p["name"] == "Synthetic Missing")
    ph = next(p for p in allp(d) if p["name"] == "Synthetic Placeholder")
    assert miss["faces"][0]["state"] == "provider-missing" and not miss["faces"][0]["img"]
    assert ph["image_status"] == "placeholder"  # the UI renders the text fallback for placeholders


def test_digital_printings_excluded_unless_tracked():
    assert not any(p["name"] == "Synthetic Digital" for p in allp(doc()))
    d = doc(tracked=TR + [{"name": "Synthetic Digital", "set": "mmo", "cn": "4", "lang": "en", "finish": "nonfoil"}])
    assert any(p["name"] == "Synthetic Digital" and p["digital"] for p in allp(d))


def test_thumbnails_tracked_first_and_capped_large_only_for_tracked():
    got = []
    d = doc(download=lambda u, dest: got.append((u, dest.name)) or True, large=True, max_thumbs=1)
    assert got[0][0].endswith("/small/front/00000000-0000-4000-8000-000000000001.jpg")
    assert [n for _, n in got if n.endswith("-normal.jpg")] == ["00000000-0000-4000-8000-000000000001-f0-normal.jpg"]
    assert sum(1 for _, n in got if n.endswith("-small.jpg")) == 1
    assert any(f["state"] == "not-cached" for p in allp(d) for f in p["faces"])


def test_failed_download_is_not_marked_cached():
    d = doc(download=lambda u, dest: False)
    assert all(f["state"] in ("not-cached", "provider-missing") for p in allp(d) for f in p["faces"])


def test_browser_paths_are_same_origin_cache_files_only():
    d = doc(download=lambda u, dest: True)
    s = json.dumps(d["groups"])
    assert "cards.scryfall.io" not in s
    assert all(v.startswith("cache/tcg/mtg/img/") for p in allp(d) for f in p["faces"] for v in f["img"].values())


def test_manifest_keyed_by_printing_set_cn_face_role():
    d = doc(download=lambda u, dest: True, large=True)
    m = d["manifest"]; assert m
    assert all({"printing", "set", "cn", "lang", "face", "role", "file"} <= set(x) for x in m)
    assert {x["role"] for x in m} == {"small", "normal"}
    assert len({(x["printing"], x["face"], x["role"]) for x in m}) == len(m)


def test_artwork_rights_marked_blocked():
    d = doc(); assert d["artworkRights"] == "BLOCKED" and "not verified" in d["artworkRightsNote"]


def test_only_scryfall_adapter_active_others_documented_inactive():
    act = [a.describe() for a in ADAPTERS if a.ACTIVE]
    assert [a["provider"] for a in act] == ["Scryfall"]
    ina = [a.describe() for a in ADAPTERS if not a.ACTIVE]
    assert {a["provider"] for a in ina} >= {"TCGdex", "Scrydex"} and all(a["reason"].startswith("Inactive") and a["terms"].startswith("https://") for a in ina)
    doc_ = (R / "docs/everything/TCG-PROVIDERS.md").read_text()
    assert "TCGdex" in doc_ and "Scrydex" in doc_ and "inactive" in doc_.lower()


def test_rate_limit_and_headers():
    assert SY.API_GAP >= 0.1 and SY.IMG_GAP >= 0.1  # <= 10 requests/second
    assert SY.HEADERS["User-Agent"].startswith("GrokTheBlock/") and "application/json" in SY.HEADERS["Accept"]
    assert SY.IMG_HEADERS["User-Agent"] and SY.IMG_HEADERS["Accept"].startswith("image/")
    assert SY.IMG_HOSTS == {"cards.scryfall.io"}


def test_fetch_image_refuses_other_hosts(tmp=None):
    assert SY.fetch_image("https://example.com/x.jpg", Path(tempfile.mkdtemp()) / "x.jpg") is False


def test_bulk_mode_uses_bulk_data_endpoint():
    calls = []
    orig = SY.api_get
    SY.api_get = lambda u: calls.append(u) or None
    try:
        try:
            SY.bulk_cards({"x"})
        except Exception:
            pass
    finally:
        SY.api_get = orig
    assert calls == ["https://api.scryfall.com/bulk-data/default-cards"]


def test_dry_run_and_sync_is_opt_in():
    out = subprocess.run([sys.executable, str(R / "tools/sync_tcg_art.py"), "--dry-run"], capture_output=True, text=True, cwd=R)
    assert out.returncode == 0 and "would sync" in out.stdout
    assert "sync_tcg_art" not in (R / "tools/build_everything.py").read_text()  # never runs implicitly


def test_tracked_printings_parse_from_committed_data():
    t = SY.tracked_printings()
    assert t and all(x["set"] and x["cn"] for x in t)
    assert parse_scryfall_uri("https://scryfall.com/card/vma/4/black-lotus") == ("vma", "4")


def test_explorer_js_escapes_script_close():
    with tempfile.TemporaryDirectory() as td:
        old = SY.OUT; SY.OUT = Path(td)
        try:
            d = doc(); d["groups"][0]["name"] = "</script><b>"; SY.write(d)
            js = (Path(td) / "explorer.js").read_text()
        finally:
            SY.OUT = old
    assert "</script>" not in js and js.startswith("/*") and "window.GTB_TCG_CACHE = " in js


def test_cache_is_gitignored_and_untracked():
    assert "cache/" in (R / ".gitignore").read_text().split()
    out = subprocess.run(["git", "ls-files", "cache", "ui/cache"], capture_output=True, text=True, cwd=R).stdout
    assert out.strip() == ""
    chk = subprocess.run(["git", "check-ignore", "-q", "ui/cache/tcg/mtg/explorer.js"], cwd=R)
    assert chk.returncode == 0


def test_csp_unchanged_and_scripts_same_origin():
    h = (R / "ui/index.html").read_text()
    # Migration (Investigations): connect-src 'none' -> 'self' (same-origin launcher /api only).
    assert "img-src 'self' data: blob:;" in h and "connect-src 'self'" in h
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', h)
    assert all(not s.startswith(("http:", "https:", "//")) for s in srcs) and "cache/tcg/mtg/explorer.js" in srcs


def test_ui_has_no_remote_image_hosts_secrets_or_sync_button():
    js = (R / "ui/tcg.js").read_text()
    assert "scryfall.io" not in js and "api.scryfall.com" not in js
    assert not re.search(r"(api[_-]?key|secret|token)\s*[:=]", js, re.I)
    assert not re.search(r">\s*(Sync|Refresh) (artwork|images)", js, re.I)  # no sync button: sync is CLI-only


def test_registry_tcg_menu_items():
    reg = (R / "ui/registry.js").read_text()
    for name in ("Card Explorer", "Market Signals", "Price History", "Cross-Venue Spreads"):
        assert f'cat: "tcg", name: "{name}"' in reg, name
    assert 'id: "tcg.explorer", cat: "tcg", name: "Card Explorer", route: { view: "tcg" }' in reg


def test_every_ui_href_goes_through_the_single_url_validator():
    """Regression for RC2-final F-1: Card Explorer source links bypassed safeExternalUrl. Every interpolated href in the UI must
    be the output of safeExternalUrl (extLink in app.js, tcgLink in tcg.js); nothing else may build an href from data."""
    for f in ("ui/app.js", "ui/tcg.js", "ui/registry.js", "ui/stage.js"):
        src = (R / f).read_text()
        hits = re.findall(r'href="\$\{([^}]*)\}', src)
        assert all(h.strip() == "esc(h)" for h in hits), (f, hits)
        for line in src.splitlines():
            if 'href="${esc(h)}"' in line:
                assert "safeExternalUrl" in line or "GTB_safeExternalUrl" in line, (f, line[:120])


if __name__ == "__main__":
    ts = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    ok = 0
    for n, f in ts:
        try:
            f(); ok += 1
        except Exception as e:  # noqa: BLE001
            print("FAIL", n, repr(e)[:300])
    print(f"{ok}/{len(ts)} passed")
    sys.exit(0 if ok == len(ts) else 1)
