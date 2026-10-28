"""R6-04: turn the real on-chain example reports (kept only in the gitignored tests/fixtures/private/onchain/) into
SYNTHETIC examples for the public repo. Deterministic. Every Solana address/signature/mint (full and shortened forms),
every token name and symbol, and every link is replaced with an invented value; decimal amounts are scaled by a fixed
factor and all times are shifted by a fixed offset, so no value can be matched back to the chain. Structure and the
relationships inside a file are kept, so the UI and the tests still exercise real report shapes.

Also writes tests/fixtures/onchain-denylist.json: SHA-256 of every real identifier, so a test can prove none remains.
Run: python tools/synthesize_onchain.py"""
import hashlib, json, re
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SRC = R / "tests/fixtures/private/onchain/examples"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
FULL = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,88}(?![1-9A-HJ-NP-Za-km-z])")
ABBR = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])([1-9A-HJ-NP-Za-km-z]{4})(\.\.\.|…)([1-9A-HJ-NP-Za-km-z]{4})(?![1-9A-HJ-NP-Za-km-z])")
URL = re.compile(r"https?://([^/\s\"']+)([^\s\"']*)")
SHIFT_S = 30 * 86400 + 3 * 3600 + 17 * 60   # all times move 30d 3h17m earlier
SCALE = 0.87                                 # all decimal amounts ×0.87
KEEP_NAMES = {"?", "dexscreener", "rugcheck", "solana-rpc", "helius", "jupiter", "SOL", "USDC", "USDT", "Wrapped SOL"}
NAMES = {"OpenBot": "SYNBOT", "Something": "SYNTHING", "Believe in Something": "Synthetic Thing", "Fartcoin": "SYNFART", "TRUMP": "SYNTRUMP"}


def fake(s: str, n: int | None = None) -> str:
    h = hashlib.sha256(("gtb-synth:" + s).encode()).digest()
    out = "Syn"
    i = 0
    while len(out) < (n or len(s)):
        out += B58[h[i % len(h)] % 58]; i += 1
        if i % len(h) == 0:
            h = hashlib.sha256(h).digest()
    return out[: (n or len(s))]


def collect_names(o, acc):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("symbol", "name", "tokenSymbol", "tokenName") and isinstance(v, str) and v not in KEEP_NAMES and len(v) > 1:
                acc.add(v)
            collect_names(v, acc)
    elif isinstance(o, list):
        for v in o:
            collect_names(v, acc)


def main():
    files = sorted(SRC.glob("*.json"))
    if not files:
        print("SKIPPED: no private on-chain originals"); return
    texts = {f: f.read_text() for f in files}
    full = set()
    names = set(NAMES)
    for t in texts.values():
        full |= set(FULL.findall(t))
        collect_names(json.loads(t), names)
    full -= {n for n in full if n.startswith("Syn")}
    fmap = {a: fake(a) for a in full}
    amap = {}
    for a, b in fmap.items():
        for sep in ("...", "…"):
            amap[a[:4] + sep + a[-4:]] = b[:4] + sep + b[-4:]
    nmap = dict(NAMES)
    for i, n in enumerate(sorted(names - set(NAMES))):
        nmap[n] = "SYN" + fake(n, 7)[3:].upper()
    (R / "tests/fixtures/onchain-denylist.json").write_text(json.dumps({
        "_note": "SHA-256 of every real Solana identifier in the original on-chain examples (R6-04). Hashes only; used by tests/test_round6.py to prove none remains in the public tree.",
        "sha256OfRealIdentifiers": sorted(hashlib.sha256(a.encode()).hexdigest() for a in full)}, indent=0) + "\n")

    def sub_str(s: str) -> str:
        s = FULL.sub(lambda m: fmap.get(m.group(0), m.group(0) if m.group(0).startswith("Syn") else fake(m.group(0))), s)
        s = ABBR.sub(lambda m: amap.get(m.group(0)) or (fake(m.group(1) + m.group(3), 8)[3:7] + m.group(2) + fake(m.group(0), 8)[4:8]), s)
        s = URL.sub(lambda m: f"https://example.invalid/synthetic/{m.group(1)}{m.group(2)}", s)
        for a in sorted(nmap, key=len, reverse=True):
            s = re.sub(rf"(?<![A-Za-z0-9]){re.escape(a)}(?![A-Za-z0-9])", nmap[a], s)
        s = re.sub(r"\b(20\d\d-\d\d-\d\d)[T ](\d\d:\d\d(?::\d\d)?)", lambda m: _shift_iso(m.group(1), m.group(2), m.group(0)[10]), s)
        s = re.sub(r"(?<![\d.])(\d+\.\d+)(?=\s*(?:SOL|USD|%|\$|k|K|M|x|×))", lambda m: _fmt(float(m.group(1)) * SCALE, m.group(1)), s)
        return s

    def walk(o, k=None):
        if isinstance(o, dict):
            return {sub_str(kk) if FULL.search(kk) else kk: walk(v, kk) for kk, v in o.items()}
        if isinstance(o, list):
            return [walk(v, k) for v in o]
        if isinstance(o, str):
            return sub_str(o)
        if isinstance(o, bool) or o is None:
            return o
        if isinstance(o, int):
            if 1_500_000_000 <= o <= 2_100_000_000:
                return o - SHIFT_S
            if 1_500_000_000_000 <= o <= 2_100_000_000_000:
                return o - SHIFT_S * 1000
            return o
        if isinstance(o, float):
            return round(o * SCALE, 6)
        return o

    out_dir = R / "examples"
    for old in out_dir.glob("*.json"):
        if old.name != "signals-EXAMPLE.json":
            old.unlink()
    for f, t in texts.items():
        j = json.loads(t)
        if f.name == "provenance-sample.json":  # media analysis of a generated test clip; no chain data, no vendor data
            (out_dir / f.name).write_text(t); continue
        s = walk(j)
        note = ("SYNTHETIC EXAMPLE (R6-04): transformed from a public on-chain scan by tools/synthesize_onchain.py. Every address, "
                "signature, mint, token name/symbol and link is invented; amounts are scaled and times shifted by fixed amounts. "
                "It describes no real token or wallet. Not financial advice.")
        if isinstance(s, list):
            s = [dict(x, _provenance="synthetic") if isinstance(x, dict) else x for x in s]
        else:
            s = dict(s, synthetic=True, _provenance="synthetic", _syntheticNote=note)
            if "example" in j:
                s["example"] = True
        name = sub_str(f.stem)
        for a in sorted(full, key=len, reverse=True):
            for n in (6, 8):
                name = name.replace(a[:n], fmap[a][:n])
        (out_dir / (name + ".json")).write_text(json.dumps(s, indent=1, ensure_ascii=False) + "\n")
        print(f"{f.name} -> {name}.json")
    json.dump({"names": nmap}, open(R / "tests/fixtures/private/onchain/name-map.json", "w"), indent=1)


def _fmt(x, like):
    d = len(like.split(".")[1])
    return f"{x:.{d}f}"


def _shift_iso(d, t, sep):
    from datetime import datetime, timedelta
    fmt = "%Y-%m-%d %H:%M:%S" if t.count(":") == 2 else "%Y-%m-%d %H:%M"
    v = datetime.strptime(f"{d} {t}", fmt) - timedelta(seconds=SHIFT_S)
    return v.strftime(fmt).replace(" ", sep)


if __name__ == "__main__":
    main()
