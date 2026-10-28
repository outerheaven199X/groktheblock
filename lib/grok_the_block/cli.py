"""Small helpers shared by skill scripts."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out"


class Ambiguous(SystemExit):
    pass


def ticker_candidates(q: str) -> list[dict]:
    """Distinct Solana mints whose symbol matches q exactly, best liquidity first."""
    from .data import dexscreener_search
    q = q.strip().lstrip("$")
    pairs = [p for p in dexscreener_search(q) if (p.get("baseToken") or {}).get("symbol", "").lower() == q.lower()]
    best: dict[str, dict] = {}
    for p in pairs:
        bt = p["baseToken"]; liq = (p.get("liquidity") or {}).get("usd") or 0
        c = best.setdefault(bt["address"], {"mint": bt["address"], "symbol": bt.get("symbol"), "name": bt.get("name"),
                                             "liquidityUsd": 0, "marketCap": p.get("marketCap") or p.get("fdv"),
                                             "pairCreatedAt": p.get("pairCreatedAt"), "url": p.get("url")})
        c["liquidityUsd"] += liq
    return sorted(best.values(), key=lambda c: -c["liquidityUsd"])


def resolve_mint(q: str, pick: int | None = None) -> str:
    """Accept a mint address or a $TICKER. Tickers are not unique: if more than one
    mint carries the symbol, stop and list candidates (exit 3) unless the caller
    picked one (pick=N, 1-based). Liquidity is shown to help choose, never to choose silently."""
    import json, os
    q = q.strip().lstrip("$")
    if len(q) >= 32:
        return q
    cands = ticker_candidates(q)
    if not cands:
        sys.exit(f"Could not resolve '${q}' on DexScreener (no exact symbol match, or DexScreener unavailable); pass the mint address.")
    pick = pick or (int(os.environ.get("GTB_PICK") or os.environ["CRYPTOSINT_PICK"]) if (os.environ.get("GTB_PICK") or os.environ.get("CRYPTOSINT_PICK")) else None)
    total = sum(c["liquidityUsd"] for c in cands) or 1
    if pick is None and len(cands) > 1:
        OUT.mkdir(parents=True, exist_ok=True)
        rep = {"kind": "ambiguous-ticker", "ticker": "$" + q, "candidates": cands[:10],
               "message": f"${q} matches {len(cands)} different Solana mints. Pick one by mint address (or --pick N)."}
        (OUT / f"ambiguous-{q}.json").write_text(json.dumps(rep, indent=2))
        lines = [f"  {i+1}. {c['symbol']} {c['mint']}  liq ${c['liquidityUsd']:,.0f}  {c.get('name') or ''}" for i, c in enumerate(cands[:10])]
        print(f"Ambiguous ticker ${q}: {len(cands)} mints share this symbol. Re-run with the mint address or --pick N:\n" + "\n".join(lines), file=sys.stderr)
        raise Ambiguous(3)
    c = cands[(pick or 1) - 1]
    print(f"Resolved ${q} -> {c['symbol']} {c['mint']} (liq ${c['liquidityUsd']:,.0f}; {len(cands)} candidate mint(s)). "
          "Tickers are not unique; verify the mint.", file=sys.stderr)
    return c["mint"]
