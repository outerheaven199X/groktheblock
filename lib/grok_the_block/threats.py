"""Port of CryptOSINT src/lib/threats.ts (LP removal + coordinated dump detection)."""
from datetime import datetime, timezone
from .data import LAMPORTS_PER_SOL, short

AMM_PROGRAMS = {
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium AMM v4
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",  # Raydium CLMM
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",  # Orca Whirlpool
    # additions (not in original): where pump.fun tokens trade after graduation
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",  # PumpSwap AMM
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",  # Raydium CPMM
}
MIN_LP_REMOVAL_SOL, CRITICAL_LP_PCT, HIGH_LP_PCT = 5, 80, 50


def iso(ts): return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def is_lp_tx(tx): return any(a["account"] in AMM_PROGRAMS for a in tx["accountData"])


def fee_payer_sol_gain(tx):
    fp = next((a for a in tx["accountData"] if a["account"] == tx["feePayer"]), None)
    return fp["nativeBalanceChange"] / LAMPORTS_PER_SOL if fp else 0


def estimate_lp_pct(sol):
    return 95 if sol > 100 else 80 if sol > 50 else 60 if sol > 20 else 40 if sol > 10 else 20


def detect_lp_removals(txs, mint, symbol):
    out = []
    for tx in txs:
        if not is_lp_tx(tx): continue
        gain = fee_payer_sol_gain(tx)
        if gain <= 0: continue
        # liquidity withdrawal returns BOTH sides to the remover; a plain sell only gains SOL
        if not any(t["mint"] == mint and t.get("toUserAccount") == tx["feePayer"] for t in tx["tokenTransfers"]): continue
        if gain < MIN_LP_REMOVAL_SOL: continue
        pct = estimate_lp_pct(gain)
        sev = "CRITICAL" if pct >= CRITICAL_LP_PCT else "HIGH" if pct >= HIGH_LP_PCT else "MEDIUM"
        detail = (f"LP pulled — {gain:.1f} SOL (~{pct}%) removed by {short(tx['feePayer'])}. Likely rug." if pct >= CRITICAL_LP_PCT else
                  f"Major LP withdrawal — {gain:.1f} SOL (~{pct}%) removed by {short(tx['feePayer'])}. Significant liquidity reduction for ${symbol}." if pct >= HIGH_LP_PCT else
                  f"LP withdrawal — {gain:.1f} SOL (~{pct}%) removed by {short(tx['feePayer'])}.")
        out.append({"id": f"lp-{tx['signature']}", "timestamp": iso(tx["timestamp"]), "type": "RUG" if pct >= CRITICAL_LP_PCT else "LP_CHANGE",
                    "severity": sev, "tokenSymbol": symbol, "tokenMint": mint, "detail": detail,
                    "lpRemovedSol": gain, "lpRemovedPct": pct, "removerAddress": tx["feePayer"], "signature": tx["signature"],
                    "caveat": "SOL gain of the fee payer in an AMM tx touching this mint. A large sell looks the same; check the signature."})
    return out


def detect_coordinated_dumps(txs, mint, symbol, insiders, window=300, min_dumpers=2):
    if not insiders: return []
    sells = sorted(({"address": t["fromUserAccount"], "timestamp": tx["timestamp"], "signature": tx["signature"]}
                    for tx in txs for t in tx["tokenTransfers"] if t["mint"] == mint and t.get("fromUserAccount") in insiders),
                   key=lambda s: s["timestamp"])
    if len(sells) < min_dumpers: return []
    out, seen = [], set()
    for s in sells:
        cl = [x for x in sells if s["timestamp"] <= x["timestamp"] <= s["timestamp"] + window]
        u = {x["address"] for x in cl}
        if len(u) >= min_dumpers:
            k = ",".join(sorted(x["signature"] for x in cl))
            if k in seen: continue
            seen.add(k)
            out.append({"id": f"dump-{cl[0]['signature']}", "timestamp": iso(s["timestamp"]), "type": "BUNDLE",
                        "severity": "CRITICAL" if len(u) >= 4 else "HIGH", "tokenSymbol": symbol, "tokenMint": mint,
                        "detail": f"{len(u)} insider wallets sold ${symbol} within {window // 60}min window. Coordinated dump pattern detected."})
    return out
