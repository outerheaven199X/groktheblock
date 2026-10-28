#!/usr/bin/env python3
"""Token Scan: classify every wallet in a token's launch window
(INSIDER / AGENT / SNIPER / COPY / ORGANIC), organic score, verdict, LP monitor,
copy network, and JSON export. Port of CryptOSINT /api/scan.

usage: token_scan.py <mint|$TICKER> [--max-tx 200] [--sig-pages 20] [--origins 10] [--out path.json] [--no-record]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from cryptosint import classify as C, data as D, history, lp
from cryptosint.cli import OUT, resolve_mint

ORDER = {"INSIDER": 0, "AGENT": 1, "SNIPER": 2, "COPY": 3, "ORGANIC": 4}


def age_str(sec: int) -> str:
    if sec < 3600: return f"{sec // 60}m"
    if sec < 86400: return f"{sec // 3600}h {(sec % 3600) // 60}m"
    return f"{sec // 86400}d"


def wallet_origin(addr: str) -> dict:
    """Wallet age + first funder (oldest tx reachable within 3 sig pages)."""
    sigs, genesis = D.get_signatures(addr, max_pages=3)
    if not sigs:
        return {}
    first = sigs[0]
    o = {"walletAge": age_str(int(time.time()) - (first.get("blockTime") or 0)) if genesis else None,
         "historyComplete": genesis}
    if genesis:
        tx = D.normalize_tx(D.get_transaction(first["signature"]), first["signature"])
        for nt in (tx or {}).get("nativeTransfers", []):
            if nt["toUserAccount"] == addr:
                o["firstFunder"], o["firstFundAmountSol"] = nt["fromUserAccount"], nt["amount"] / D.LAMPORTS_PER_SOL
                break
    return o


def scan(mint: str, max_tx=200, sig_pages=20, origins=10, record=True, faithful=False) -> dict:
    meta = D.token_metadata(mint)
    print(f"Scanning {meta['symbol']} ({mint})", file=sys.stderr)
    t = D.get_token_transactions(mint, max_tx=max_tx, max_sig_pages=sig_pages)
    txs = t["transactions"]
    if not txs:
        raise SystemExit("No transactions found for this token")
    txs.sort(key=lambda x: x["slot"])
    deployer = txs[0]["feePayer"]
    profiles = C.build_wallet_profiles(txs, mint, deployer)
    pools = []
    if not faithful:
        # Deviation from original (documented): drop program-owned accounts such as the
        # pump.fun bonding curve / AMM vault authorities. Otherwise the pool itself is
        # labelled INSIDER ("FUNDED BY DEPLOYER", 80%+ supply) on every pump.fun token.
        busiest = sorted(profiles, key=lambda p: -p.txCount)[:15]
        for p in busiest:
            if D.is_program_account(p.address):
                pools.append(p.address)
        profiles = [p for p in profiles if p.address not in pools]
    total_supply = sum(max(0, p.currentHolding) for p in profiles)  # original: estimated from observed transfers
    if not faithful and meta.get("supply"):
        total_supply = meta["supply"]  # deviation: real on-chain supply, since pool accounts are excluded
    wallets = C.classify_all_wallets(profiles, total_supply)
    flows = D.sol_flows(txs, mint)
    for w in wallets:
        w["solFlowEstimate"] = round(flows.get(w["address"], 0.0), 4)  # realized SOL in/out within scan window
    score = C.compute_organic_score(wallets)
    counts = C.count_types(wallets)
    verdict = C.generate_verdict(score, counts)
    # prior history + reputation (local cache replaces KV)
    for w in wallets:
        prior = [r for r in history.history_for(w["address"]) if r["tokenMint"] != mint]
        if prior:
            w["priorHistory"] = [{"tokenSymbol": r["tokenSymbol"], "classification": r["classification"], "timestamp": r["timestamp"]} for r in prior]
    flagged = sorted([w for w in wallets if w["type"] in ("INSIDER", "AGENT", "SNIPER")], key=lambda w: -w["supplyPercent"])[:origins]
    for w in flagged:
        try:
            w.update({k: v for k, v in wallet_origin(w["address"]).items() if v is not None})
        except Exception as e:
            print(f"  origin lookup failed for {w['address']}: {e}", file=sys.stderr)
    for w in wallets:
        hist = [r for r in history.history_for(w["address"]) if r["tokenMint"] != mint]
        if w["type"] != "ORGANIC":
            hist = hist + [{"classification": w["type"], "entryBlock": w["entryBlock"]}]
        if hist:
            w["reputation"] = C.compute_reputation(hist, w.get("walletAge"))
    copy_net = C.detect_copy_relationships(profiles, wallets)
    for w in wallets:
        if w["address"] == deployer:
            w["isDeployer"] = True  # extra flag: the original classifies the deployer by the same rules, often ORGANIC
            w["tag"] = ("DEPLOYER" + (f" · {w['tag']}" if w["tag"] else "")) if t["reached_genesis"] else w["tag"]
    # Extra signal (not in original classify.ts): same-slot-as-launch buyers. Bundled
    # launches buy in block 0 and dump within seconds, so the original rules end up
    # calling them ORGANIC once their holding is ~0.
    blk0 = [p for p in profiles if p.firstBlock == 0 and p.totalBought > 0 and p.address != deployer]
    bundle = {"block0Buyers": len(blk0),
              "block0SupplyBoughtPct": round(100 * sum(p.totalBought for p in blk0) / total_supply, 2) if total_supply else None,
              "block0BuyersAlreadySoldPct": round(100 * sum(1 for p in blk0 if p.totalSold >= 0.9 * p.totalBought) / len(blk0)) if blk0 else 0,
              "wallets": [p.address for p in sorted(blk0, key=lambda p: -p.totalBought)[:20]],
              "valid": bool(t["reached_genesis"]),
              "note": "Wallets that bought in the launch slot. Only meaningful when reachedLaunch is true."}
    wallets.sort(key=lambda w: (ORDER[w["type"]], w["entryBlock"]))
    lps = lp.lp_status(mint)
    best = lps["pools"][0] if lps["pools"] else {}
    first_ts = txs[0]["timestamp"]
    result = {
        "token": {"name": meta["name"], "symbol": meta["symbol"], "mint": mint,
                  "age": age_str(int(time.time()) - first_ts) if t["reached_genesis"] else "unknown (history beyond scan window)",
                  "mcap": best.get("marketCap") or best.get("fdv") or 0, "volume24h": best.get("volume24h") or 0,
                  "totalHolders": len(wallets), "deployerAddress": deployer, "onchainSupply": meta.get("supply")},
        "organicScore": score, "counts": counts, "wallets": wallets[:50], "allWalletCount": len(wallets),
        "copyNetwork": copy_net or None, "bundleSignal": bundle, "verdict": verdict, "lpMonitor": lps,
        "scanWindow": {"transactionsAnalyzed": len(txs), "signaturesSeen": t["signatures_seen"],
                       "reachedLaunch": t["reached_genesis"], "excludedProgramAccounts": pools,
                       "firstTx": first_ts, "lastTx": txs[-1]["timestamp"],
                       "note": "Launch window only. If reachedLaunch is false, 'block 0' is the oldest tx we could reach, not the real launch, and INSIDER/SNIPER labels are unreliable."},
        "disclaimer": "Heuristic signals from public on-chain data, not accusations. Labels describe on-chain patterns, not intent.",
        "generatedAt": int(time.time()),
    }
    if record and t["reached_genesis"]:
        result["historyRecorded"] = history.record_scan(mint, meta["symbol"], wallets)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("token"); ap.add_argument("--max-tx", type=int, default=200)
    ap.add_argument("--sig-pages", type=int, default=20); ap.add_argument("--origins", type=int, default=10)
    ap.add_argument("--out"); ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--faithful", action="store_true", help="keep pool/program accounts in the wallet set, exactly like the original")
    a = ap.parse_args()
    mint = resolve_mint(a.token)
    r = scan(mint, a.max_tx, a.sig_pages, a.origins, not a.no_record, a.faithful)
    out = Path(a.out) if a.out else OUT / f"scan-{r['token']['symbol']}-{mint[:6]}.json"
    D.write_json(out, r)
    tk, lpm = r["token"], r["lpMonitor"]
    print(f"\n${tk['symbol']} {tk['name']}  age {tk['age']}  mcap ${tk['mcap']:,.0f}  holders-in-window {tk['totalHolders']}")
    print(f"Organic score: {r['organicScore']}  [{r['verdict']['severity']}] {r['verdict']['summary']}")
    print("Counts:", r["counts"], f"| window: {r['scanWindow']['transactionsAnalyzed']} txs, reachedLaunch={r['scanWindow']['reachedLaunch']}")
    print(f"LP: ${lpm['totalLiquidityUsd']:,.0f} across {len(lpm['pools'])} pools; rugcheck mintAuth={lpm['rugcheck']['mintAuthority']} freezeAuth={lpm['rugcheck']['freezeAuthority']} "
          f"LP locked% {[m['lpLockedPct'] for m in lpm['rugcheck']['markets']][:3]}")
    for w in r["wallets"][:12]:
        print(f"  {w['type']:8} blk {w['entryBlock']:>4} tx {w['txCount']:>3} supply {w['supplyPercent']:5.1f}%  sol {w['solFlowEstimate']:+8.3f}  {D.short(w['address'])}  {w['tag'] or ''}")
    b = r["bundleSignal"]
    if b["valid"]:
        print(f"Bundle signal: {b['block0Buyers']} wallets bought in the launch slot = {b['block0SupplyBoughtPct']}% of supply; {b['block0BuyersAlreadySoldPct']}% of them already sold out")
    print(f"Copy relationships: {len(r['copyNetwork'] or [])}\nJSON: {out}")


if __name__ == "__main__":
    main()
