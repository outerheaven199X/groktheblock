#!/usr/bin/env python3
"""Wallet Scan: tokens a wallet touched, per-token classification, approximate
SOL PnL, win rate, funding sources and funded wallets, reputation.
Port of CryptOSINT /api/wallet.

usage: wallet_scan.py <wallet> [--max-tx 200] [--out path.json]
PnL is APPROXIMATE: realized SOL in/out within the fetched window only
(public RPC = most recent N txs), unsold bags valued at 0.
"""
import argparse, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from grok_the_block import classify as C, data as D, history
from grok_the_block.cli import OUT
from grok_the_block.timefmt import age

MIN_FUND_SOL = 0.01


def iso(ts): return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else ""


def scan_wallet(w: str, max_tx=200) -> dict:
    txs = D.get_wallet_transactions(w, max_tx)
    if not txs:
        raise SystemExit("No transactions found for this wallet")
    counts = Counter()
    for tx in txs:
        for t in tx["tokenTransfers"]:
            if w in (t.get("fromUserAccount"), t.get("toUserAccount")) and t["mint"] != D.SOL_MINT:
                counts[t["mint"]] += 1
    mints = [m for m, _ in counts.most_common(20)]
    tokens = []
    for m in mints:
        r = C.classify_wallet_for_token(txs, w, m)
        flow = D.sol_flows([t for t in txs if any(tr["mint"] == m for tr in t["tokenTransfers"])], m).get(w, 0.0)
        pairs = D.dexscreener_pairs(m)
        bt = next(((p.get("baseToken") or {}) for p in pairs if (p.get("baseToken") or {}).get("address") == m), {})
        first = min((t["timestamp"] for t in txs if any(tr["mint"] == m and w in (tr.get("fromUserAccount"), tr.get("toUserAccount")) for tr in t["tokenTransfers"])), default=0)
        tokens.append({"mint": m, "symbol": bt.get("symbol", "?"), "name": bt.get("name", "?"),
                       "classification": r["classification"], "entryBlock": r["entryBlock"],
                       "pnlSol": round(flow, 4), "buyAmount": r["buyAmount"], "sellAmount": r["sellAmount"],
                       "holdingAmount": r["holdingAmount"], "firstTx": iso(first), "tag": r["tag"]})
    # funding graph from native transfers
    src, dst = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for tx in txs:
        for nt in tx["nativeTransfers"]:
            sol = nt["amount"] / D.LAMPORTS_PER_SOL
            if sol < MIN_FUND_SOL: continue
            if nt["toUserAccount"] == w and nt["fromUserAccount"] != w:
                e = src[nt["fromUserAccount"]]; e[0] += sol; e[1] = max(e[1], tx["timestamp"])
            if nt["fromUserAccount"] == w and nt["toUserAccount"] != w:
                e = dst[nt["toUserAccount"]]; e[0] += sol; e[1] = max(e[1], tx["timestamp"])
    # drop program-owned destinations (pools, bonding curves, fee vaults)
    funded = [{"address": a, "amountSol": round(v[0], 4), "timestamp": iso(v[1])} for a, v in sorted(dst.items(), key=lambda x: -x[1][0])[:40] if not D.is_program_account(a)][:20]
    sources = [{"address": a, "amountSol": round(v[0], 4), "timestamp": iso(v[1])} for a, v in sorted(src.items(), key=lambda x: -x[1][0])[:40] if not D.is_program_account(a)][:20]
    total = sum(t["pnlSol"] for t in tokens)
    wins = sum(1 for t in tokens if t["pnlSol"] > 0)
    first, genesis = D.wallet_first_tx(w)
    wallet_age = age(int(time.time()) - first["timestamp"]) if first else None
    prior = history.history_for(w)
    rep_hist = [{"classification": r["classification"], "entryBlock": 0} for r in prior] + \
               [{"classification": t["classification"], "entryBlock": t["entryBlock"]} for t in tokens]
    sol_usd = D.sol_price_usd()
    # record per-token classes so leaderboard/reputation learn from wallet scans too
    for t in tokens:
        history.record_scan(t["mint"], t["symbol"], [{"address": w, "type": t["classification"], "entryBlock": t["entryBlock"], "pnlSol": t["pnlSol"], "solFlowEstimate": t["pnlSol"]}])
    return {
        "wallet": {"address": w, "totalPnlSol": round(total, 4), "totalPnlUsdApprox": round(total * sol_usd, 2) if sol_usd else None,
                   "totalTokensTouched": len(counts), "winRate": round(100 * wins / len(tokens)) if tokens else 0,
                   "firstActivity": iso(txs[0]["timestamp"]), "walletAge": wallet_age, "historyComplete": genesis,
                   "fundedBy": [s["address"] for s in sources], "fundedAddresses": [f["address"] for f in funded],
                   "priorHistory": [{"tokenSymbol": r["tokenSymbol"], "classification": r["classification"], "timestamp": r["timestamp"]} for r in prior],
                   "reputation": C.compute_reputation(rep_hist, wallet_age, len(funded))},
        "tokens": sorted(tokens, key=lambda t: -t["pnlSol"]),
        "associations": {"fundingSources": sources, "fundedWallets": funded},
        "verdict": C.generate_wallet_verdict([t["classification"] for t in tokens]),
        "window": {"transactionsAnalyzed": len(txs), "from": iso(txs[0]["timestamp"]), "to": iso(txs[-1]["timestamp"])},
        "notes": ["PnL is approximate: realized SOL flow in the analyzed window only; open positions count as 0.",
                  "Per-token classification uses timing/cadence only (entry block is relative to this wallet's first tx on that token, as in the original).",
                  "Signals, not accusations."],
    }


def main():
    ap = argparse.ArgumentParser(description='Grok The Block · wallet scan: explain what a wallet did across the launches it touched.', epilog="An evolution of CryptOSINT by @varien. Read-only."); ap.add_argument("wallet"); ap.add_argument("--max-tx", type=int, default=200); ap.add_argument("--out")
    a = ap.parse_args()
    r = scan_wallet(a.wallet, a.max_tx)
    from grok_the_block.assess import assess_wallet
    r["assessment"] = assess_wallet(r)
    out = Path(a.out) if a.out else OUT / f"wallet-{a.wallet[:8]}.json"
    D.write_json(out, r)
    wl = r["wallet"]
    print(f"Wallet {a.wallet}  age {wl['walletAge']}  window {r['window']['transactionsAnalyzed']} txs ({r['window']['from'][:16]} → {r['window']['to'][:16]})")
    print(f"Tokens touched {wl['totalTokensTouched']}  approx PnL {wl['totalPnlSol']:+.3f} SOL (~${wl['totalPnlUsdApprox']})  win rate {wl['winRate']}%")
    print(f"Reputation {wl['reputation']}  Verdict [{r['verdict']['severity']}] {r['verdict']['summary']}")
    for t in r["tokens"][:10]:
        print(f"  {t['symbol'][:12]:12} {t['classification']:8} pnl {t['pnlSol']:+9.3f} SOL  {t['tag'] or ''}")
    print(f"Funding sources {len(r['associations']['fundingSources'])}, funded wallets {len(r['associations']['fundedWallets'])}\nJSON: {out}")


if __name__ == "__main__":
    main()
