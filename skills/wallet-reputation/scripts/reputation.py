#!/usr/bin/env python3
"""Wallet Reputation 0-100 (higher = more suspicious) from local scan history,
using the original computeReputation weights (INSIDER 25, AGENT 10, SNIPER 8, COPY 3;
x1.5 avg entry block < 2; x1.5 wallet younger than a day; x1.2 funds > 3 wallets).
usage: reputation.py <wallet> [<wallet> ...] [--live]   (--live also fetches wallet age)"""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from grok_the_block import classify as C, history, data as D
from grok_the_block.timefmt import age


def main():
    ap = argparse.ArgumentParser(description='Grok The Block · wallet reputation: score wallets from local scan history.', epilog="An evolution of CryptOSINT by @varien. Read-only."); ap.add_argument("wallets", nargs="+"); ap.add_argument("--live", action="store_true")
    a = ap.parse_args()
    out = []
    for w in a.wallets:
        h = history.history_for(w)
        wa = None
        if a.live:
            first, _ = D.wallet_first_tx(w)
            wa = age(int(time.time()) - first["timestamp"]) if first else None
        rep = C.compute_reputation(h, wa)
        out.append({"wallet": w, **rep, "walletAge": wa, "history": h})
        print(f"{w}: {rep['score']}/100 {rep['grade']}  {'; '.join(rep['factors']) or 'no flagged history on this machine'}")
    D.write_json(Path(__file__).resolve().parents[3] / "out" / "reputation.json", out)


if __name__ == "__main__":
    main()
