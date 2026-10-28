---
name: solana-data
description: Shared read-only Solana data layer for every CryptOSINT skill: public Solana RPC with failover, DexScreener, RugCheck, an optional HELIUS_API_KEY, and a local JSON cache. Use it when another CryptOSINT skill needs setup or when Solana RPC calls fail.
---
# Solana data layer

Every CryptOSINT script imports the shared library at `lib/cryptosint/` (repo root; `data.py` is the data layer). You do not call it directly. This skill covers setup and troubleshooting.

## Setup (once per machine)
1. `cd` to the repo root and run `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
2. Optional: `export HELIUS_API_KEY=...` for higher rate limits. Never ask the user to paste a key into chat. If they want one, have them set it in their own environment.
3. Optional: `export SOLANA_RPC_URL=https://a,https://b` to use your own RPC list.

## How it works
- RPC calls go to `api.mainnet-beta.solana.com` first and fail over to `solana-rpc.publicnode.com` on 403, 413 ("data allowance"), 429, or 5xx errors.
- Finalized transactions are cached forever under `cache/tx/`. Signature lists are cached for 2 minutes, and DexScreener and RugCheck responses for 5 to 10 minutes.
- `get_token_transactions(mint)` walks signatures back from newest to find the launch window. Public RPC only pages backwards, so for tokens with more than about `sig-pages × 1000` transactions it cannot reach the launch, and it reports `reachedLaunch: false`.
- `cache/wallet_history.jsonl` replaces the original Cloudflare KV. Token and wallet scans write to it, and the leaderboard and reputation read from it.

## Troubleshooting
- Repeated "data allowance" or 429 errors: wait a minute, lower `--max-tx`, or set `HELIUS_API_KEY`.
- To clear stale market data, delete `cache/dexscreener` and `cache/rugcheck`.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
