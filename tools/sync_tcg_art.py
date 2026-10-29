"""Opt-in Card Explorer sync: Scryfall printing metadata + card artwork into ui/cache/tcg (gitignored; bulk files in ./cache/tcg). Never runs implicitly.

  python3 tools/sync_tcg_art.py                 # tracked MTG cards: all paper printings + small thumbnails (tracked printings first)
  python3 tools/sync_tcg_art.py --large         # also the 'normal' (488x680) image for each TRACKED printing only
  python3 tools/sync_tcg_art.py --bulk          # substantial imports: Scryfall bulk 'default_cards' file instead of per-card search
  python3 tools/sync_tcg_art.py --dry-run       # print the plan, no network
  python3 tools/sync_tcg_art.py --from-dir DIR  # offline: build the cache from saved Scryfall card JSON (tests, fixtures)

Rules kept here (Scryfall API docs): <=10 requests/s (we leave >=120 ms between api.scryfall.com calls and 100 ms between
image downloads), a descriptive User-Agent and an Accept header on every request, bulk data for large imports, images unaltered
(no crop/overlay; artist and copyright stay visible), attribution shown in the UI. Images and their metadata stay in
ui/cache/tcg until redistribution rights are verified; the UI only loads them same-origin. No API key is used or needed.
Output: ui/cache/tcg/mtg/explorer.js (window.GTB_TCG_CACHE), printings.json, img/*.jpg.
"""
from __future__ import annotations

import argparse, json, sys, time
from pathlib import Path
from urllib.parse import quote, urlparse

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib"))
from grok_the_block.tcg.adapters import ScryfallAdapter, ADAPTERS, group_printings, parse_scryfall_uri  # noqa: E402

OUT = R / "ui/cache/tcg/mtg"  # same-origin for the UI; gitignored by the cache/ rule
BULK = R / "cache/tcg/bulk"
API = "https://api.scryfall.com"
IMG_HOSTS = {"cards.scryfall.io"}
HEADERS = {"User-Agent": "GrokTheBlock/0.6 (local research preview; card-explorer sync)", "Accept": "application/json;q=0.9,*/*;q=0.8"}
IMG_HEADERS = {"User-Agent": HEADERS["User-Agent"], "Accept": "image/jpeg,image/*;q=0.8"}
API_GAP, IMG_GAP = 0.12, 0.10
# Browse-only additions (no price tracking): cover layouts the tracked list lacks (double-faced, modal DFC, adventure).
EXPLORER_EXTRA = ["Delver of Secrets", "Valki, God of Lies", "Brazen Borrower"]
_last = {"api": 0.0, "img": 0.0}


def _wait(kind: str, gap: float) -> None:
    dt = time.time() - _last[kind]
    if dt < gap:
        time.sleep(gap - dt)
    _last[kind] = time.time()


def api_get(url: str):
    import requests
    for attempt in range(3):
        _wait("api", API_GAP)
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 429:
            time.sleep(2 ** attempt * 2); continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    return None


def tracked_printings() -> list[dict]:
    """Tracked MTG instruments from the committed derived data, bound to their exact printing (set + collector number)."""
    j = json.loads((R / "data/everything/live-derived.json").read_text())
    out = []
    for a in j.get("assets", []):
        if a.get("universe") != "mtg":
            continue
        sc = parse_scryfall_uri(a.get("url", ""))
        out.append({"name": a["name"], "set": sc[0] if sc else None, "cn": sc[1] if sc else None, "lang": "en", "finish": "nonfoil"})
    return out


def search_prints(name: str, max_pages: int = 3) -> list[dict]:
    q = quote('!"' + name + '"')
    url = f"{API}/cards/search?q={q}&unique=prints&order=released&dir=asc"
    cards = []
    for _ in range(max_pages):
        j = api_get(url)
        if not j:
            break
        cards += j.get("data", [])
        if not j.get("has_more"):
            break
        url = j["next_page"]
    return cards


def bulk_cards(names: set[str]) -> list[dict]:
    import requests
    meta = api_get(f"{API}/bulk-data/default-cards")
    dest = BULK / "default-cards.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.stat().st_mtime < time.time() - 86400 * 7:
        with requests.get(meta["download_uri"], headers=HEADERS, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
    return [c for c in json.loads(dest.read_text()) if c.get("name") in names or (c.get("card_faces") and c["card_faces"][0].get("name") in names)]


def fetch_image(url: str, dest: Path) -> bool:
    import requests
    if dest.exists() and dest.stat().st_size > 0:
        return True
    if urlparse(url).netloc not in IMG_HOSTS:
        return False
    _wait("img", IMG_GAP)
    try:
        r = requests.get(url, headers=IMG_HEADERS, timeout=30)
    except requests.RequestException:
        return False
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return True


def build(cards: list[dict], tracked: list[dict], *, download=None, large=False, max_thumbs=400, now=None) -> dict:
    """Pure-ish assembly (download is injectable for tests). Returns the explorer cache document."""
    ad = ScryfallAdapter()
    seen, ps = set(), []
    tset = {(t["set"], t["cn"], t["lang"]) for t in tracked}
    for c in cards:
        p = ad.printing(c)
        # paper printings only, except a digital printing the tracked market data is actually bound to (shown as digital)
        if p and (not p["digital"] or (p["set"], p["cn"], p["lang"]) in tset) and p["key"] not in seen:
            seen.add(p["key"]); ps.append(p)
    tmap = {(t["set"], t["cn"], t["lang"]): t for t in tracked}
    tracked_ids = set()
    for p in ps:
        t = tmap.get((p["set"], p["cn"], p["lang"]))
        if t and t["name"] == p["name"]:
            p["tracked"] = {"asset": t["name"], "finish": t["finish"]}  # observations bind to this printing + finish only
            tracked_ids.add(p["id"])
    groups = group_printings(ps, tracked_ids)
    order = sorted(ps, key=lambda p: p["id"] not in tracked_ids)
    n = 0
    for p in order:
        for f in p["faces"]:
            f["img"] = {}
            if p["image_status"] in ("missing",) or not f["uris"]:
                f["state"] = "provider-missing"; continue
            want = ["small"] + (["normal"] if large and p["id"] in tracked_ids else [])
            for size in want:
                if size == "small" and n >= max_thumbs:
                    continue
                rel = f"img/{p['id']}-f{f['face']}-{size}.jpg"
                ok = bool(download and f["uris"].get(size) and download(f["uris"][size], OUT / rel))
                if ok:
                    f["img"][size] = "cache/tcg/mtg/" + rel
                    n += size == "small"
            f["state"] = "cached" if f["img"] else "not-cached"
            f.pop("uris", None)  # remote URLs never reach the browser bundle
    manifest = [{"printing": p["id"], "set": p["set"], "cn": p["cn"], "lang": p["lang"], "face": f["face"], "role": role, "file": path,
                 "source": "Scryfall", "uri": p["uri"]} for p in ps for f in p["faces"] for role, path in f["img"].items()]
    return {"syncedAt": int(now or time.time()), "manifest": manifest,
            "artworkRights": "BLOCKED", "artworkRightsNote": "Redistribution of card images is not verified (images © Wizards of the Coast, served by Scryfall). Local research cache only; a hosted build must ship the text fallback.", "provider": "Scryfall", "game": "mtg",
            "attribution": "Card data and images: Scryfall (scryfall.com). Card images © Wizards of the Coast; artist credited per printing.",
            "imagePolicy": "Unaltered Scryfall images cached locally for research use; not redistributed. Rights for hosted redistribution unverified.",
            "adapters": [a.describe() for a in ADAPTERS], "tracked": tracked, "extra": EXPLORER_EXTRA,
            "groups": groups, "counts": {"printings": len(ps), "cards": len(groups), "thumbs": n}}


def write(doc: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "printings.json").write_text(json.dumps(doc, indent=1))
    (OUT / "explorer.js").write_text("/* generated by tools/sync_tcg_art.py; local cache, gitignored, not for redistribution */\nwindow.GTB_TCG_CACHE = "
                                     + json.dumps(doc, separators=(",", ":")).replace("</", "<\\/") + ";\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--large", action="store_true"); ap.add_argument("--bulk", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-dir"); ap.add_argument("--max-thumbs", type=int, default=400); ap.add_argument("--no-images", action="store_true")
    a = ap.parse_args(argv)
    tracked = tracked_printings()
    names = [t["name"] for t in tracked] + EXPLORER_EXTRA
    if a.dry_run:
        print(f"would sync {len(names)} cards ({len(tracked)} tracked) via {'bulk default_cards' if a.bulk else '/cards/search unique=prints'};"
              f" thumbnails <= {a.max_thumbs}; large={a.large}; out={OUT}")
        return 0
    if a.from_dir:
        cards = [c for f in sorted(Path(a.from_dir).glob("*.json")) for c in (lambda j: j.get("data", [j]) if isinstance(j, dict) else j)(json.loads(f.read_text()))]
    elif a.bulk:
        cards = bulk_cards(set(names))
    else:
        cards = [c for n in names for c in search_prints(n)]
    doc = build(cards, tracked, download=None if (a.no_images or a.from_dir) else fetch_image, large=a.large, max_thumbs=a.max_thumbs)
    write(doc)
    print(f"synced {doc['counts']['cards']} cards, {doc['counts']['printings']} printings, {doc['counts']['thumbs']} thumbnails -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
