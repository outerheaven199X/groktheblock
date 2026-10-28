#!/usr/bin/env python3
"""Sniper Leaderboard from the local scan history (cache/wallet_history.jsonl).
usage: leaderboard.py [--type SNIPER|INSIDER|AGENT|COPY] [--top 25] [--out path.json]"""
import argparse, json, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from grok_the_block import history
from grok_the_block.cli import OUT
from grok_the_block.data import write_json, short, is_program_account


def build(kind="SNIPER", top=25):
    rows = history.load_all()
    agg = defaultdict(list)
    for r in rows:
        if r["classification"] == kind and not is_program_account(r["wallet"]):
            agg[r["wallet"]].append(r)
    entries = []
    for w, rs in agg.items():
        entries.append({"address": w, "appearances": len(rs), "tokens": sorted({r["tokenSymbol"] for r in rs}),
                        "winRate": round(100 * sum(1 for r in rs if r.get("solFlow", r.get("pnl", 0)) > 0) / len(rs)),
                        "avgEntryBlock": round(sum(r["entryBlock"] for r in rs) / len(rs), 2),
                        "totalEstimatedPnlSol": round(sum(r.get("solFlow", 0) for r in rs), 3),
                        "lastSeen": max(r["timestamp"] for r in rs)})
    entries.sort(key=lambda e: (-e["appearances"], e["avgEntryBlock"]))
    ts = sorted(r["timestamp"] for r in rows)
    return {"type": kind, "entries": entries[:top], "totalWalletsTracked": len({r["wallet"] for r in rows}),
            "tokensScanned": len({r["tokenMint"] for r in rows}),
            "dataSpan": f"{ts[0][:10]} to {ts[-1][:10]}" if ts else "no scans yet",
            "note": "Only covers tokens scanned on this machine. Grows as you run token-scan."}


def main():
    ap = argparse.ArgumentParser(description='Grok The Block · leaderboard: wallets that keep appearing early across scanned launches (local data only).', epilog="An evolution of CryptOSINT by @varien. Read-only."); ap.add_argument("--type", default="SNIPER"); ap.add_argument("--top", type=int, default=25); ap.add_argument("--out")
    a = ap.parse_args()
    r = build(a.type.upper(), a.top)
    out = Path(a.out) if a.out else OUT / f"leaderboard-{r['type']}.json"
    write_json(out, r)
    print(f"{r['type']} leaderboard: {r['totalWalletsTracked']} wallets tracked across {r['tokensScanned']} tokens ({r['dataSpan']})")
    for i, e in enumerate(r["entries"][:15], 1):
        print(f" {i:2}. {short(e['address'])}  x{e['appearances']}  avg blk {e['avgEntryBlock']}  win {e['winRate']}%  pnl {e['totalEstimatedPnlSol']:+.3f}  {','.join(e['tokens'])[:50]}")
    print(f"JSON: {out}")


if __name__ == "__main__":
    main()
