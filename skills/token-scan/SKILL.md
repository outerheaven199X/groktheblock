---
name: token-scan
description: Scan a Solana token (mint or $TICKER) and classify every wallet in its launch window as INSIDER, AGENT, SNIPER, COPY, or ORGANIC, with an organic score, verdict, LP monitor, bundle signal, copy network, and JSON export. Use when someone asks whether a coin is organic, bundled, sniped, or safe-looking.
---
# Token Scan (port of CryptOSINT's scanner)

## Steps
1. Get the mint. If the user gives a $TICKER, the script resolves it through DexScreener to the highest-liquidity Solana pair and prints the mint it picked. Confirm that mint with the user, because tickers are not unique.
2. Run `.venv/bin/python skills/token-scan/scripts/token_scan.py <mint> [--max-tx 200] [--sig-pages 20] [--origins 10]`. This takes 1 to 3 minutes on public RPC.
3. Read `out/scan-<SYMBOL>-<mint6>.json`. The fields are `organicScore`, `counts`, `verdict`, `wallets` (top 50, each with class, entry block, tx count, supply %, `solFlowEstimate`, tag, reputation, and wallet age/funder for flagged wallets), `lpMonitor` (pools, liquidity, RugCheck authorities, LP locked %, risks, top holders), `bundleSignal`, `copyNetwork`, and `scanWindow`.
4. Check `scanWindow.reachedLaunch`. If it is false, say plainly that the launch was out of reach on free RPC and that the early-block labels are unreliable. Suggest a Helius key or a higher `--sig-pages`.
5. For a graph, run `skills/copy-network/scripts/copy_network.py <scan.json>`.

## Classifier (faithful to classify.ts)
- INSIDER: block 0 or 1, and either funded by the deployer or holding more than 1% of supply.
- AGENT: cadence stddev under 2s with more than 10 txs, or Jito/MEV with more than 5 txs, or more than 20 txs with stddev under 5s.
- SNIPER: block 3 or earlier with 2 or fewer txs.
- COPY: blocks 2 to 5 with 3 to 15 txs.
- ORGANIC: everything else. Organic score = share of ORGANIC wallets. Verdict bands are under 20, 40, and 65.

Documented deviations (pass `--faithful` to turn them off):
- Pool and bonding-curve accounts are excluded.
- Supply % uses the real on-chain supply.
- `bundleSignal` is added, because launch-slot bundlers that dump within seconds end up labeled ORGANIC under the original rules.

## Present the result as a Page
End every run by rendering the report as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the CryptOSINT dashboard (`ui/index.html`), with kit blocks only:
- A `Metrics` row: organic score, verdict severity, market cap, wallets in window.
- Wallet classes as `StackedBars` or `Bars` (INSIDER, AGENT, SNIPER, COPY, ORGANIC), with the verdict summary in a `Callout`.
- LP status as `Properties`: liquidity, pools, mint/freeze authority, LP locked %, and RugCheck risks.
- The bundle signal as `Rows`.
- A `Table` of flagged wallets (class, wallet, block, txs, supply %, SOL flow, tag), with Solscan links in `LinkCards`.
- A "launch not reached" `Callout tone="warning"` when that applies.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
