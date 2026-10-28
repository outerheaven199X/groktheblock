#!/usr/bin/env python3
"""Whale watch (polling replacement for the original Helius webhooks).
Each run fetches the newest txs for every watched mint since the last run and
reports large buys/sells, insider moves (wallets flagged by an earlier scan), and LP changes.

usage:
  watch_token.py add <mint|$TICKER> [--min-sol 10]
  watch_token.py remove <mint>
  watch_token.py list
  watch_token.py check [--json]      # run from a routine; prints nothing if no alerts
"""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from cryptosint import data as D, history
from cryptosint.cli import resolve_mint
from cryptosint.threats import detect_lp_removals

WATCH = D.CACHE_DIR / "watchlist.json"


def load(): return json.loads(WATCH.read_text()) if WATCH.exists() else {}
def save(w): D.CACHE_DIR.mkdir(parents=True, exist_ok=True); WATCH.write_text(json.dumps(w, indent=2))


def check(entry, mint):
    sigs, _ = D.get_signatures(mint, max_pages=1, page_size=100, newest_only=True)
    last = entry.get("lastSlot", 0)
    new = [s for s in sigs if s["slot"] > last]
    if not last:  # first run: set baseline, no alerts
        entry["lastSlot"] = max((s["slot"] for s in sigs), default=0); return []
    txs = D.fetch_transactions(new, 100, progress=False)
    entry["lastSlot"] = max([last] + [s["slot"] for s in new])
    flagged = {r["wallet"]: r["classification"] for r in history.load_all() if r["tokenMint"] == mint}
    flows = {}
    alerts = []
    for tx in txs:
        f = D.sol_flows([tx], mint)
        for w, sol in f.items():
            if D.is_program_account(w): continue
            kind = flagged.get(w)
            if abs(sol) >= entry["minSol"] or (kind in ("INSIDER", "AGENT") and sol > 0.5):
                t = "INSIDER_MOVE" if kind == "INSIDER" else ("WHALE_SELL" if sol > 0 else "LARGE_BUY")
                alerts.append({"type": t, "severity": "HIGH" if t != "LARGE_BUY" else "MEDIUM", "tokenSymbol": entry["symbol"], "tokenMint": mint,
                               "wallet": w, "walletType": kind, "amountSol": round(abs(sol), 3), "timestamp": tx["timestamp"],
                               "signature": tx["signature"], "url": f"https://solscan.io/tx/{tx['signature']}",
                               "detail": f"{D.short(w)}{' (' + kind + ')' if kind else ''} {'sold for' if sol > 0 else 'bought with'} {abs(sol):.2f} SOL"})
    alerts += detect_lp_removals(txs, mint, entry["symbol"])
    return alerts


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["add", "remove", "list", "check"]); ap.add_argument("token", nargs="?")
    ap.add_argument("--min-sol", type=float, default=10); ap.add_argument("--json", action="store_true")
    ap.add_argument("--loop", type=int, default=0, help="keep polling for N seconds (webhook-free fast mode)")
    ap.add_argument("--every", type=int, default=0, help="seconds between polls in --loop (default 10 with Helius, 30 without)")
    a = ap.parse_args(); w = load()
    if a.cmd == "add":
        m = resolve_mint(a.token); meta = D.token_metadata(m)
        w[m] = {"symbol": meta["symbol"], "minSol": a.min_sol, "addedAt": int(time.time()), "lastSlot": 0}
        check(w[m], m); save(w); print(f"Watching ${meta['symbol']} {m} (alerts >= {a.min_sol} SOL)")
    elif a.cmd == "remove":
        w.pop(a.token, None); save(w); print("removed")
    elif a.cmd == "list":
        for m, e in w.items(): print(f"${e['symbol']} {m} min {e['minSol']} SOL")
    else:
        end = time.time() + a.loop
        every = a.every or (10 if D.has_helius() else 30)
        while True:
            run_check(w, a)
            if time.time() + every > end:
                break
            time.sleep(every)


def run_check(w, a):
    if True:
        allx = []
        for m, e in w.items():
            try: allx += check(e, m)
            except Exception as ex: print(f"check failed for {e['symbol']}: {ex}", file=sys.stderr)
        save(w)
        if a.json: print(json.dumps(allx, indent=2))
        else:
            for x in allx: print(f"[{x['severity']}] {x['type']} ${x['tokenSymbol']}: {x['detail']} {x.get('url', '')}")


if __name__ == "__main__":
    main()
