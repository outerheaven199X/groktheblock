"""Small helpers shared by skill scripts."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out"


def resolve_mint(q: str) -> str:
    """Accept a mint address or a $TICKER/name; tickers resolve via DexScreener
    to the highest-liquidity Solana pair (print the choice so the user can verify)."""
    from .data import dexscreener_search
    q = q.strip().lstrip("$")
    if len(q) >= 32:
        return q
    pairs = dexscreener_search(q)
    pairs = [p for p in pairs if (p.get("baseToken") or {}).get("symbol", "").lower() == q.lower()] or pairs
    if not pairs:
        sys.exit(f"Could not resolve '{q}' on DexScreener; pass the mint address.")
    best = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
    bt = best["baseToken"]
    print(f"Resolved ${q} -> {bt['symbol']} {bt['address']} (liq ${((best.get('liquidity') or {}).get('usd') or 0):,.0f}). "
          "Tickers are not unique; verify the mint.", file=sys.stderr)
    return bt["address"]
