"""R6-04: build docs/assets-manifest.json, classifying every tracked public asset (images, archives, JSON, JSONL, CSV,
TXT outside lib/ and skills/) with SHA-256, source and status. Unknown files make this script FAIL rather than guess.
Statuses: synthetic · project-generated (our own test/eval output or docs; no raw provider values) · public-official
(US government schedules) · license-text (third-party licence files shipped with fonts/icons).
Run after any asset change: python tools/build_asset_manifest.py"""
import fnmatch, hashlib, json, subprocess, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".zip", ".json", ".jsonl", ".csv", ".txt"}
SYN_EX = sorted(f for f in subprocess.run(["git", "ls-files", "examples"], cwd=R, capture_output=True, text=True).stdout.split()
                if f.endswith(".json") and f != "examples/provenance-sample.json")
RULES = [  # (glob, status, source, renderedFrom)
    ("docs/signals-*.png", "synthetic", "Chromium-emulation screenshot of the Signals tab rendering only the synthetic signals example", ["examples/signals-EXAMPLE.json"]),
    ("docs/ui-*.png", "synthetic", "Chromium-emulation screenshot rendering only the synthetic on-chain examples (R6-04)", SYN_EX),
    ("docs/graph-*.png", "synthetic", "Chromium-emulation screenshot of a graph node panel rendering only the synthetic on-chain examples (R6-04)", SYN_EX),
    ("examples/signals-EXAMPLE.json", "synthetic", "tests/fixtures/contracts/make_example.py (synthetic generators through the production parsers)", None),
    ("examples/provenance-sample.json", "project-generated", "promo-provenance analysis of a generated test clip (C2PA test fixture); no chain, X or market data", None),
    ("examples/*.json", "synthetic", "tools/synthesize_onchain.py: transformed public on-chain scan; identifiers, names, links invented; amounts scaled; times shifted", None),
    ("tests/fixtures/onchain-denylist.json", "project-generated", "SHA-256 hashes of real identifiers (no identifiers themselves), for the R6-04 test", None),
    ("tests/fixtures/replay/*.json", "synthetic", "hand-written replay fixtures (invented values)", None),
    ("tests/fixtures/adjudication-vignettes-r7.json", "synthetic", "R7-01 written vignettes for the decision table (invented descriptions, no labels of real events)", None),
    ("tests/fixtures/adjudication-vignettes-r8.json", "synthetic", "R8-05 written vignettes (invented descriptions, no labels of real events)", None),
    ("tests/fixtures/signals-fixtures.json", "synthetic", "hand-written detector fixtures (invented values; file _note says SYNTHETIC)", None),
    ("data/event-calendar.json", "public-official", "official US release schedules (Federal Reserve FOMC calendar, BLS, Treasury auctions); rights row in PROVIDER-RIGHTS.md", None),
    ("docs/review/replay-real-*.json", "project-generated", "aggregate counts from a local replay over treasury.gov history and one Polymarket market (title and link only; no raw series)", None),
    ("docs/review/replay-fixtures.jsonl", "project-generated", "output of the synthetic replay harness", None),
    ("docs/review/eval-treasury/release-calendar.json", "public-official", "release DATES (FOMC, CPI, NFP) from federalreserve.gov and bls.gov archive indexes; no data values (tools/build_release_calendar.py)", None),
    ("docs/review/eval-treasury/release-calendar-r8.json", "public-official", "R8 release announcements (FOMC statement dates/times from federalreserve.gov statement pages; BLS dates per blsStatus); no data values", None),
    ("docs/review/eval-treasury/release-calendar-r9.json", "public-official", "R9 release announcements with verification state (FOMC VERIFIED from statement pages; BLS per blsStatus); no data values", None),
    ("docs/review/eval-treasury/*.json", "project-generated", "R6-06 evaluation dataset manifest/roster/label sheet: dates, tenors and checksums of treasury.gov series; no raw values", None),
    ("docs/review/*.json", "project-generated", "evaluation config/results written by this project", None),
    ("docs/review/*.txt", "project-generated", "test logs written by this project (paths sanitized)", None),
    ("docs/screenshots-provenance.json", "project-generated", "round-5 screenshot provenance (superseded by this manifest; kept for the R5 test)", None),
    ("ui/licenses/*.txt", "license-text", "font/icon licence texts (OFL, MIT) shipped with the UI", None),
]


def main():
    tracked = subprocess.run(["git", "ls-files"], cwd=R, capture_output=True, text=True).stdout.split()
    new = [f for f in subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=R, capture_output=True, text=True).stdout.split()]
    files = sorted({f for f in tracked + new if Path(f).suffix.lower() in EXT and not f.startswith(("lib/", "skills/")) and f not in ("requirements.txt", "docs/assets-manifest.json") and (R / f).exists()})
    out, unknown = {}, []
    for f in files:
        for g, st, src, rf in RULES:
            if fnmatch.fnmatch(f, g):
                out[f] = {"status": st, "source": src, "sha256": hashlib.sha256((R / f).read_bytes()).hexdigest()}
                if rf:
                    out[f]["renderedFrom"] = rf
                break
        else:
            unknown.append(f)
    if unknown:
        print("UNCLASSIFIED:", unknown); sys.exit(1)
    (R / "docs/assets-manifest.json").write_text(json.dumps({
        "_note": "R6-04 inventory of every public asset in the tree. tests/test_round6.py checks that every tracked asset is listed, the sha256 matches, the status is allowed, every image is synthetic and rendered only from synthetic inputs. Regenerate with tools/build_asset_manifest.py.",
        "assets": out}, indent=1) + "\n")
    print(f"assets-manifest: {len(out)} assets; " + ", ".join(f"{s}={sum(1 for v in out.values() if v['status'] == s)}" for s in sorted({v['status'] for v in out.values()})))


if __name__ == "__main__":
    main()
