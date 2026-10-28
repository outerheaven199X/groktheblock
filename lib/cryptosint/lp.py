"""LP Monitor: pool, liquidity, LP burned/locked, authorities (DexScreener + RugCheck)."""
from .data import dexscreener_pairs, rugcheck_report


def lp_status(mint: str) -> dict:
    pairs = dexscreener_pairs(mint)
    pools = []
    for p in sorted(pairs, key=lambda p: -((p.get("liquidity") or {}).get("usd") or 0)):
        pools.append({"dex": p.get("dexId"), "pair": p.get("pairAddress"), "url": p.get("url"),
                      "liquidityUsd": (p.get("liquidity") or {}).get("usd"),
                      "priceUsd": p.get("priceUsd"), "fdv": p.get("fdv"), "marketCap": p.get("marketCap"),
                      "volume24h": (p.get("volume") or {}).get("h24"),
                      "pairCreatedAt": p.get("pairCreatedAt")})
    rc = rugcheck_report(mint) or {}
    markets = []
    for m in rc.get("markets") or []:
        lp = m.get("lp") or {}
        markets.append({"type": m.get("marketType"), "pubkey": m.get("pubkey"),
                        "lpLockedPct": lp.get("lpLockedPct"), "lpLockedUsd": lp.get("lpLockedUSD"),
                        "baseUsd": lp.get("baseUSD"), "quoteUsd": lp.get("quoteUSD")})
    return {
        "pools": pools,
        "totalLiquidityUsd": sum((p["liquidityUsd"] or 0) for p in pools),
        "rugcheck": {
            "available": bool(rc),
            "score": rc.get("score"), "scoreNormalised": rc.get("score_normalised"),
            "rugged": rc.get("rugged"),
            "mintAuthority": rc.get("mintAuthority"), "freezeAuthority": rc.get("freezeAuthority"),
            "totalMarketLiquidityUsd": rc.get("totalMarketLiquidity"),
            "creator": rc.get("creator"), "totalHolders": rc.get("totalHolders"),
            "risks": [{"name": r.get("name"), "level": r.get("level"), "description": r.get("description")} for r in rc.get("risks") or []],
            "markets": markets,
            "topHolders": [{"owner": h.get("owner"), "pct": h.get("pct"), "insider": h.get("insider")} for h in (rc.get("topHolders") or [])[:10]],
        },
    }
