---
name: token-scan
description: Grok The Block (understand what actually happened on-chain, in plain English). Scan a Solana token (mint or $TICKER) and classify every wallet in its launch window as INSIDER, AGENT, SNIPER, COPY, or ORGANIC, with an organic score, verdict, LP monitor, bundle signal, copy network, and JSON export. Use when someone asks whether a coin is organic, bundled, sniped, or safe-looking.
---
# Token Scan (Grok The Block; evolved from CryptOSINT's scanner)

## Steps
0. Export in the original CryptOSINT envelope format: `skills/token-scan/scripts/export.py <result.json>` writes `grok-the-block-<type>-<id>-<ts>.json`.
1. Get the mint. Tickers are not unique: given a $TICKER, the script looks up every Solana mint with that exact symbol. If there is more than one, it scans nothing, exits with code 3, prints the candidates (mint, name, liquidity) and writes `out/ambiguous-<TICKER>.json`. Show the candidates and ask which mint the user means, then re-run with the mint (or `--pick N`). Never pick for them.
2. Run `.venv/bin/python skills/token-scan/scripts/token_scan.py <mint> [--max-tx 200] [--sig-pages 20] [--origins 10]`. This takes 1 to 3 minutes on public RPC.
3. Read `out/scan-<SYMBOL>-<mint6>.json`. The fields are `organicScore`, `counts`, `verdict`, `wallets` (top 50, each with class, entry block, tx count, supply %, `solFlowEstimate`, tag, reputation, and wallet age/funder for flagged wallets), `lpMonitor` (pools, liquidity, RugCheck authorities, LP locked %, risks, top holders), `bundleSignal`, `copyNetwork`, and `scanWindow`. When `verdict.escalatedBy` is `bundleSignal`, the verdict was raised from `verdict.originalSeverity` because launch-slot wallets held 25% or more of supply; say so, and give both. `--faithful` keeps the original verdict.
4. Lead with `assessment.lead` (the most consequential supported finding) and its `why`; then `assessment.coverage` (limits and provider status), then `assessment.findings` with their `basis` and `evidence`, then `assessment.nextActions`. If a provider failed (`coverage.providers[].ok` false, or exit code 2 with no report), say which and that dependent values are unknown, not clean.
5. Check `scanWindow.reachedLaunch`. If it is false, say plainly that the launch was out of reach on free RPC and that the early-block labels are unreliable. Suggest a Helius key or a higher `--sig-pages`.
6. For a graph, run `skills/copy-network/scripts/copy_network.py <scan.json>`.

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
End every run by rendering the report as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the Grok The Block dashboard (`ui/index.html`), with kit blocks only.
Page structure (requirement: a Page must reach the same conclusions, evidence and next steps as the dashboard). Use `palette={["#00e87b", "#ff3b5c", "#ffb020"]}` on `Page` (the UI's `--org`, `--ins`, `--snip`); class colors are ORGANIC green, INSIDER red, SNIPER amber, AGENT violet, COPY cyan. Typography comes from the kit; never hardcode fonts. Build it from the result's `assessment` block when present (token scan, wallet scan, rug replay), in this order:
1. Title `Grok The Block: <subject>`; `summary` = `assessment.lead.text`. If the data is a bundled example, say "Example data, recorded <date>, not live" in the summary.
2. A `Callout` with the lead finding (tone `danger` for CRITICAL/HIGH, `warning` for MEDIUM) and `lead.why` when present. Name the basis: observed, heuristic or inferred.
3. Section "Coverage & limits", before any numbers: `Rows` with one row per `coverage.limits` item (kind as `meta`) and one per failed provider (`status` danger). An unreached launch, sampled X data, local-only reputation and approximate SOL figures must appear here. Missing provider data is "unknown", never "clean".
4. `Metrics` for the key numbers, then the main visual.
5. Section "Findings & evidence": a `Table` with Finding, Severity, Basis and Evidence columns, plus `LinkCards` for the Solscan or provider links in `evidence`.
6. Section "Next steps": `Rows`, one per `assessment.nextActions` item (title = `label`, meta = `why` followed by "Ask Grok Bot: “<ask>”"). Never say a step ran unless you ran it in this turn.
Shorten addresses as `9zd5…QzhD`.
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
