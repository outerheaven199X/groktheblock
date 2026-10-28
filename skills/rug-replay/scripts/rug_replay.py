#!/usr/bin/env python3
"""Rug Replay: reconstruct a token's lifecycle as a timeline (creation, insider /
bot / sniper entries, organic buy waves, large sells, LP removals, mass dumps),
then optionally overlay X posts the bot saved (raw search_posts_all JSON).
Port of CryptOSINT /api/replay + new X chatter overlay.

usage: rug_replay.py <mint|$TICKER> [--x-posts DIR_OR_FILE ...] [--max-tx 500] [--sig-pages 20] [--out path]
"""
import argparse, json, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from cryptosint import classify as C, data as D
from cryptosint.cli import OUT, resolve_mint
from cryptosint.threats import is_lp_tx, fee_payer_sol_gain
from cryptosint.timefmt import rel, lifespan

LARGE_SELL_PCT, DUMP_WINDOW, DUMP_MIN = 5, 60, 3
BUY_TYPE = {"INSIDER": "INSIDER_BUY", "AGENT": "BOT_ENTRY", "SNIPER": "SNIPER_ENTRY", "ORGANIC": "ORGANIC_BUY", "COPY": "ORGANIC_BUY"}


def load_x(paths):
    posts, users = {}, {}
    for p in map(Path, paths):
        for f in (sorted(p.glob("*")) if p.is_dir() else [p]):
            raw = f.read_text(); i = raw.find("{")
            if i < 0: continue
            try: obj, _ = json.JSONDecoder().raw_decode(raw[i:])
            except Exception: continue
            for d in obj.get("data") or []: posts[d["id"]] = d
            for u in (obj.get("includes") or {}).get("users") or []: users[u["id"]] = u
    return posts, users


def replay(mint, max_tx=500, sig_pages=20, x_paths=None):
    meta = D.token_metadata(mint)
    t = D.get_token_transactions(mint, max_tx=max_tx, max_sig_pages=sig_pages)
    txs = sorted(t["transactions"], key=lambda x: x["slot"])
    if not txs: raise SystemExit("No transactions found for this token")
    created, deployer = txs[0]["timestamp"], txs[0]["feePayer"]
    profiles = C.build_wallet_profiles(txs, mint, deployer)
    cand = {p.address for p in sorted(profiles, key=lambda p: -p.txCount)[:15]} | {p.address for p in sorted(profiles, key=lambda p: -p.totalBought)[:15]} | {p.address for p in profiles if p.firstBlock <= 3 or p.isFundedByDeployer}
    pools = [a for a in cand if D.is_program_account(a)]
    profiles = [p for p in profiles if p.address not in pools]
    supply = meta.get("supply") or sum(max(0, p.currentHolding) for p in profiles)  # on-chain supply (deviation: original estimated from observed transfers)
    wallets = C.classify_all_wallets(profiles, supply)
    flows = D.sol_flows(txs, mint)
    wtype = {w["address"]: w["type"] for w in wallets}
    ev = [{"timestamp": created, "relativeTime": "+0s", "type": "CREATION", "wallet": deployer, "walletType": "INSIDER", "detail": "Token created / first observed tx" + ("" if t["reached_genesis"] else " (NOT the real launch: history beyond scan window)")}]
    seen, buckets = set(), {}
    for tx in txs:
        if is_lp_tx(tx) and any(tr["mint"] == mint for tr in tx["tokenTransfers"]):
            g = fee_payer_sol_gain(tx)
            # original flags any positive SOL gain; we keep it but require >= 1 SOL to skip normal sells
            gets_tokens = any(tr["mint"] == mint and tr.get("toUserAccount") == tx["feePayer"] for tr in tx["tokenTransfers"])
            if g >= 1 and gets_tokens and tx["feePayer"] in (deployer,) + tuple(a for a, k in wtype.items() if k == "INSIDER"):
                ev.append({"timestamp": tx["timestamp"], "relativeTime": rel(tx["timestamp"], created), "type": "LP_REMOVE", "wallet": tx["feePayer"],
                           "walletType": wtype.get(tx["feePayer"], "ORGANIC"), "detail": f"LP removed — {g:.1f} SOL withdrawn by {D.short(tx['feePayer'])}", "amountSol": g, "signature": tx["signature"]})
        for tr in tx["tokenTransfers"]:
            if tr["mint"] != mint: continue
            b, s = tr.get("toUserAccount"), tr.get("fromUserAccount")
            pct = tr["tokenAmount"] / supply * 100 if supply else 0
            if b and b not in pools and b not in seen:
                seen.add(b); k = wtype.get(b, "ORGANIC"); et = BUY_TYPE[k]
                if et == "ORGANIC_BUY":
                    m = max(created, tx["timestamp"] // 60 * 60); buckets[m] = buckets.get(m, 0) + 1
                else:
                    ev.append({"timestamp": tx["timestamp"], "relativeTime": rel(tx["timestamp"], created), "type": et, "wallet": b, "walletType": k,
                               "detail": f"{D.short(b)} bought ({k}) — {pct:.1f}% supply", "supplyPercent": pct})
            if s and s not in pools and pct >= LARGE_SELL_PCT:
                ev.append({"timestamp": tx["timestamp"], "relativeTime": rel(tx["timestamp"], created), "type": "LARGE_SELL", "wallet": s, "walletType": wtype.get(s, "ORGANIC"),
                           "detail": f"{D.short(s)} sold {pct:.1f}% of supply", "supplyPercent": pct})
    for m, n in buckets.items():
        ev.append({"timestamp": m, "relativeTime": rel(m, created), "type": "ORGANIC_BUY", "wallet": "", "walletType": "ORGANIC", "detail": f"{n} organic buyer{'s' if n > 1 else ''} entered"})
    sells = sorted([e for e in ev if e["type"] == "LARGE_SELL"], key=lambda e: e["timestamp"])
    covered_until = -1
    for e in sells:
        cl = {x["wallet"] for x in sells if e["timestamp"] <= x["timestamp"] <= e["timestamp"] + DUMP_WINDOW}
        if len(cl) >= DUMP_MIN and e["timestamp"] > covered_until:  # one event per dump window (original emitted one per sell)
            covered_until = e["timestamp"] + DUMP_WINDOW
            ev.append({"timestamp": e["timestamp"], "relativeTime": rel(e["timestamp"], created), "type": "MASS_DUMP", "wallet": "", "walletType": "INSIDER", "detail": f"{len(cl)} wallets dumped within {DUMP_WINDOW}s"})
    xcount = 0
    if x_paths:
        posts, users = load_x(x_paths)
        for p in posts.values():
            ts = int(datetime.fromisoformat(p["created_at"].replace("Z", "+00:00")).timestamp())
            u = users.get(p.get("author_id"), {})
            ev.append({"timestamp": ts, "relativeTime": rel(ts, created), "type": "X_POST", "wallet": "", "walletType": "ORGANIC",
                       "detail": f"@{u.get('username', p.get('author_id'))} ({(u.get('public_metrics') or {}).get('followers_count', '?')} followers): {p.get('text', '')[:120]}",
                       "url": p.get("url"), "impressions": (p.get("public_metrics") or {}).get("impression_count")})
            xcount += 1
    ev.sort(key=lambda e: e["timestamp"])
    org_loss = abs(sum(min(0, flows.get(w["address"], 0)) for w in wallets if w["type"] == "ORGANIC"))
    ins_profit = sum(max(0, flows.get(w["address"], 0)) for w in wallets if w["type"] in ("INSIDER", "AGENT"))
    method = "LP_PULL" if any(e["type"] == "LP_REMOVE" for e in ev) else "MASS_DUMP" if any(e["type"] == "MASS_DUMP" for e in ev) else "UNKNOWN"
    return {"token": {"name": meta["name"], "symbol": meta["symbol"], "mint": mint, "createdAt": created},
            "timeline": ev,
            "summary": {"lifespan": lifespan(txs[-1]["timestamp"] - created) + (" (of analyzed window)" if True else ""), "peakHolders": len(wallets),
                        "organicLossEstimateSol": round(org_loss, 3), "insiderProfitEstimateSol": round(ins_profit, 3), "rugMethod": method,
                        "xPostsMerged": xcount},
            "walletBreakdown": C.count_types(wallets),
            "window": {"transactionsAnalyzed": len(txs), "reachedLaunch": t["reached_genesis"], "excludedProgramAccounts": pools},
            "notes": ["Loss/profit are realized SOL flows in the analyzed window (the original summed token-unit 'pnl', which is always ~0).",
                      "LP_REMOVE = deployer/insider gains >= 1 SOL AND receives the token in the same AMM tx (both sides of the pool returned); heuristic.", "organicLossEstimateSol = net SOL spent by ORGANIC wallets in the window, including positions still open.", "Signals, not accusations."]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("token"); ap.add_argument("--x-posts", nargs="*")
    ap.add_argument("--max-tx", type=int, default=500); ap.add_argument("--sig-pages", type=int, default=20); ap.add_argument("--out")
    a = ap.parse_args()
    mint = resolve_mint(a.token)
    r = replay(mint, a.max_tx, a.sig_pages, a.x_posts)
    out = Path(a.out) if a.out else OUT / f"replay-{r['token']['symbol']}-{mint[:6]}.json"
    D.write_json(out, r)
    s = r["summary"]
    print(f"${r['token']['symbol']} replay: lifespan {s['lifespan']}, wallets {s['peakHolders']}, method {s['rugMethod']}, "
          f"organic loss ~{s['organicLossEstimateSol']} SOL, insider/agent profit ~{s['insiderProfitEstimateSol']} SOL, X posts merged {s['xPostsMerged']}")
    print("Breakdown:", r["walletBreakdown"], "| reachedLaunch:", r["window"]["reachedLaunch"])
    shown = [e for e in r["timeline"] if e["type"] != "ORGANIC_BUY"][:25]
    for e in shown:
        print(f"  {e['relativeTime']:>9}  {e['type']:13} {e['detail'][:110]}")
    print(f"JSON: {out}")


if __name__ == "__main__":
    main()
