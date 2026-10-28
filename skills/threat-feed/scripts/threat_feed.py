#!/usr/bin/env python3
"""Threat Feed: re-check recently scanned tokens (from local history) and any
watched tokens for LP removals, coordinated insider dumps, and RugCheck risk
changes (mint/freeze authority, 'rugged' flag). Port of /api/threats; the
original's mock feed is replaced by real checks.

usage: threat_feed.py [--max-tokens 10] [--json] [--out path.json]
Prints nothing when there are no threats (routine-friendly)."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from grok_the_block import data as D, history
from grok_the_block.lp import lp_status
from grok_the_block.threats import detect_lp_removals, detect_coordinated_dumps

STATE = D.CACHE_DIR / "threat_state.json"


def main():
    ap = argparse.ArgumentParser(description='Grok The Block · threat feed: sweep scanned tokens for LP pulls, dumps and risky authorities.', epilog="An evolution of CryptOSINT by @varien. Read-only."); ap.add_argument("--max-tokens", type=int, default=10); ap.add_argument("--json", action="store_true"); ap.add_argument("--out")
    a = ap.parse_args()
    rows = history.load_all()
    tokens = {}
    for r in sorted(rows, key=lambda r: r["timestamp"], reverse=True):
        tokens.setdefault(r["tokenMint"], {"symbol": r["tokenSymbol"], "insiders": set()})
        if r["classification"] == "INSIDER": tokens[r["tokenMint"]]["insiders"].add(r["wallet"])
    wl = D.CACHE_DIR / "watchlist.json"
    if wl.exists():
        for m, e in json.loads(wl.read_text()).items(): tokens.setdefault(m, {"symbol": e["symbol"], "insiders": set()})
    state = json.loads(STATE.read_text()) if STATE.exists() else {"seen": []}
    seen = set(state["seen"]); threats = []
    for m, t in list(tokens.items())[: a.max_tokens]:
        sigs, _ = D.get_signatures(m, max_pages=1, page_size=100, newest_only=True)
        txs = D.fetch_transactions(sigs, 100, progress=False)
        found = detect_lp_removals(txs, m, t["symbol"]) + detect_coordinated_dumps(txs, m, t["symbol"], t["insiders"])
        rc = lp_status(m)["rugcheck"]
        if rc.get("rugged"): found.append({"id": f"rugged-{m}", "type": "RUG", "severity": "CRITICAL", "tokenSymbol": t["symbol"], "tokenMint": m, "detail": "RugCheck marks this token as rugged."})
        if rc.get("mintAuthority"): found.append({"id": f"mintauth-{m}", "type": "HONEYPOT", "severity": "HIGH", "tokenSymbol": t["symbol"], "tokenMint": m, "detail": "Mint authority is still enabled (supply can be inflated)."})
        if rc.get("freezeAuthority"): found.append({"id": f"freeze-{m}", "type": "HONEYPOT", "severity": "HIGH", "tokenSymbol": t["symbol"], "tokenMint": m, "detail": "Freeze authority is enabled (holders can be frozen)."})
        threats += [f for f in found if f["id"] not in seen]
    state["seen"] = list(seen | {f["id"] for f in threats})[-5000:]
    D.CACHE_DIR.mkdir(parents=True, exist_ok=True); STATE.write_text(json.dumps(state))
    D.write_json(Path(a.out) if a.out else Path(__file__).resolve().parents[3] / "out" / "threats.json", threats)
    if a.json: print(json.dumps(threats, indent=2))
    else:
        for f in threats: print(f"[{f['severity']}] {f['type']} ${f['tokenSymbol']}: {f['detail']}")
    print(f"(checked {min(len(tokens), a.max_tokens)} tokens, {len(threats)} new threats)", file=sys.stderr)


if __name__ == "__main__":
    main()
