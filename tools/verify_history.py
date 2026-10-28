"""R6-04: scan EVERY blob reachable from any ref in a git repository (not only HEAD) for public-sample exposure:
recognisable raw vendor payload shapes (same markers as tests/test_round5.py) without the synthetic marker, real on-chain
identifiers from tests/fixtures/onchain-denylist.json (compared by SHA-256), and paths that were removed from the
public tree. Read-only. Prints a JSON summary.  Usage: python tools/verify_history.py [repo-path] [--blobs-out=FILE]"""
import hashlib, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
VENDOR = {
    "Yahoo chart": r'"exchangeTimezoneName"', "Nasdaq": r'"tradesTable"\s*:|"lastTrade": "LAST TRADE', "DefiLlama": r'"peggedAssets"',
    "treasury.gov CSV": r'"1 Mo","1\.5 Month"', "Gamma": r'"clobTokenIds"', "Kalshi": r'"yes_sub_title"|"previous_yes_bid_dollars"',
    "Cboe": r'"iv30_change_percent"|"seqno"', "OKX": r'"realizedRate"|"interestRate"|"instType": "SWAP"', "SEC Form 4": r"<ownershipDocument>.*<rptOwnerName>",
}
REMOVED = ["tests/fixtures/providers/", "docs/verification/screens/", "examples/copy-network-OpenBot.png", "examples/scan-OpenBot", "examples/scan-Something",
           "examples/scan-Fartcoin", "examples/replay-Something", "examples/watch-Something", "examples/shill-Something", "examples/wallet-5htGpHK2"]
B58 = re.compile(rb"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,88}(?![1-9A-HJ-NP-Za-km-z])")
SKIP_SELF = ("tools/verify_history.py", "tests/test_round5.py", "tests/fixtures/contracts/synth.py", "tools/synthesize_onchain.py")


def git(repo, *a, inp=None):
    return subprocess.run(["git", "-C", str(repo), *a], input=inp, capture_output=True, check=True).stdout


def main(repo, blobs_out=None):
    deny = set(json.loads((HERE / "tests/fixtures/onchain-denylist.json").read_text())["sha256OfRealIdentifiers"])
    objs = git(repo, "rev-list", "--all", "--objects").decode().splitlines()
    path_of = {}
    for line in objs:
        sha, _, p = line.partition(" ")
        if p:
            path_of.setdefault(sha, set()).add(p)
    shas = list(path_of)
    # blobs of public sample paths that are not the current (synthetic) version: earlier real examples and screenshots
    head = {l.split()[2] for l in git(repo, "ls-tree", "-r", "HEAD").decode().splitlines()}
    SAMPLE = re.compile(r"^(examples/|docs/[^/]+\.png$|docs/verification/)")
    batch = git(repo, "cat-file", "--batch", inp=("\n".join(shas) + "\n").encode())
    i, findings = 0, []
    for sha in shas:
        nl = batch.index(b"\n", i)
        hdr = batch[i:nl].split()
        size = int(hdr[2]) if len(hdr) > 2 else 0
        body = batch[nl + 1: nl + 1 + size]
        i = nl + 1 + size + 1
        if hdr[1] != b"blob":
            continue
        paths = sorted(path_of[sha])
        if all(p.endswith(SKIP_SELF) for p in paths):
            continue
        why = []
        for p in paths:
            if any(p.startswith(r) for r in REMOVED):
                why.append(f"removed path {p}")
        if sha not in head and any(SAMPLE.match(p) for p in paths):
            why.append(f"earlier non-synthetic sample version {paths[0]}")
        txt = body.decode("utf-8", "ignore")
        if '"_provenance": "synthetic"' not in txt and not any(p.endswith(".py") and p.startswith("lib/") for p in paths):
            for v, rx in VENDOR.items():
                if re.search(rx, txt, re.S):
                    why.append(f"vendor payload shape: {v}")
        hits = sum(1 for t in set(B58.findall(body)) if hashlib.sha256(t).hexdigest() in deny)
        if hits:
            why.append(f"{hits} real on-chain identifier(s)")
        if why:
            findings.append({"blob": sha, "paths": paths[:3], "why": sorted(set(why))[:4]})
    commits = git(repo, "rev-list", "--all").decode().split()
    out = {"repo": "<repo>", "commitsScanned": len(commits), "blobsScanned": sum(1 for _ in shas), "findings": len(findings),
           "byReason": {}, "sample": findings[:15]}
    for f in findings:
        for w in f["why"]:
            k = w.split(":")[0] if ":" in w else re.sub(r"^\d+ ", "", w.split(" ", 1)[0] + " " + w.split(" ", 2)[1] if w.startswith("removed") else w)
            k = "removed path" if w.startswith("removed path") else ("real on-chain identifiers" if "identifier" in w else "earlier sample version" if w.startswith("earlier") else k)
            out["byReason"][k] = out["byReason"].get(k, 0) + 1
    if blobs_out:
        Path(blobs_out).write_text("\n".join(f["blob"] for f in findings) + ("\n" if findings else ""))
    print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--blobs-out=")]
    bo = next((x.split("=", 1)[1] for x in sys.argv[1:] if x.startswith("--blobs-out=")), None)
    main(Path(a[0]) if a else HERE, bo)
