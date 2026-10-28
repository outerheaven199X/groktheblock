"""Local replacement for the original Cloudflare KV wallet history.

cache/wallet_history.jsonl: one line per (wallet, token) classification, written
by token-scan. leaderboard and wallet-reputation read it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .data import CACHE_DIR

HIST = CACHE_DIR / "wallet_history.jsonl"


def record_scan(mint: str, symbol: str, wallets: list[dict]) -> int:
    existing = {(r["wallet"], r["tokenMint"]) for r in load_all()}
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with HIST.open("a") as f:
        for w in wallets:
            if w["type"] == "ORGANIC" or (w["address"], mint) in existing:
                continue  # original only persists flagged wallets
            f.write(json.dumps({"wallet": w["address"], "tokenMint": mint, "tokenSymbol": symbol,
                                "classification": w["type"], "entryBlock": w["entryBlock"],
                                "pnl": w.get("pnlSol", 0), "solFlow": w.get("solFlowEstimate", 0), "timestamp": now}) + "\n")
            n += 1
    return n


def load_all() -> list[dict]:
    if not HIST.exists():
        return []
    return [json.loads(l) for l in HIST.read_text().splitlines() if l.strip()]


def history_for(wallet: str) -> list[dict]:
    return [r for r in load_all() if r["wallet"] == wallet]
