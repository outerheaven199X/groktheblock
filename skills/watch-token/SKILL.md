---
name: watch-token
description: Grok The Block (understand what actually happened on-chain, in plain English). Watch Solana tokens for whale buys and sells, moves by flagged insider wallets, and LP removals. This is a polling replacement for webhooks, built to run from a Grok Bot routine. Use when someone says watch this coin or alert me if insiders dump.
---
# Whale Watch (routine-ready)

## Steps
1. Add a token: `.venv/bin/python skills/watch-token/scripts/watch_token.py add <mint|$TICKER> --min-sol 10`. This sets a baseline and does not alert on history.
2. Run token-scan on it once, so insider and agent wallets are known and moves by them get flagged.
3. Create a routine (read your `routines` skill first) that runs every 5 to 15 minutes:
   - Prompt: "cd <repo> && .venv/bin/python skills/watch-token/scripts/watch_token.py check. If no token has new alerts, send nothing. Otherwise send me what changed since the last successful scan, grouped by token, with the evidence links. Never resend an alert whose key was already sent."
   - Alerts arrive minutes late, not in real time.
4. Fast mode, webhook-free: `watch_token.py check --loop 600 --every 10` polls every 10s for 10 minutes (Helius recommended).
5. `list` shows watched tokens, and `remove <mint>` stops watching one.

## Changes since the last successful scan
- Each `check` also takes a snapshot scan (verdict, bundle, liquidity, mint/freeze authority, LP lock, RugCheck risks) and diffs it against the previous *successful* snapshot. A provider failure keeps the old snapshot and is reported as a status, never as a change.
- Every alert has `key` (dedupe key), `timestamp`, `evidence` (Solscan, RugCheck or DexScreener links), and for snapshot changes `before`, `after`, `previousScanAt`. A key already alerted is suppressed and counted in `suppressedDuplicates`.
- Results go to `out/watch-<SYMBOL>-<mint6>.json` (`kind: "watch"`), which the dashboard's Watch & alerts tab renders.
- Snapshot change types: LIQUIDITY_DROP / LIQUIDITY_RISE (30% or more), AUTHORITY_CHANGE, LP_UNLOCK (10 points or more), VERDICT_CHANGE, NEW_RISK.

## Transaction alerts
- LARGE_BUY / WHALE_SELL: the SOL flow is at or above the threshold.
- INSIDER_MOVE: a flagged wallet sold.
- LP_CHANGE / RUG: a big SOL withdrawal from an AMM.

## Present the result as a Page
End every run by rendering the report as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the Grok The Block dashboard (`ui/index.html`), with kit blocks only.
Page structure (requirement: a Page must reach the same conclusions, evidence and next steps as the dashboard). Use `palette={["#00e87b", "#ff3b5c", "#ffb020"]}` on `Page` (the UI's `--org`, `--ins`, `--snip`); class colors are ORGANIC green, INSIDER red, SNIPER amber, AGENT violet, COPY cyan. Typography comes from the kit; never hardcode fonts. Build it from the result's `assessment` block when present (token scan, wallet scan, rug replay), in this order:
1. Title `Grok The Block: <subject>`; `summary` = `assessment.lead.text`. If the data is a bundled example, say "Example data, recorded <date>, not live" in the summary.
2. A `Callout` with the lead finding (tone `danger` for CRITICAL/HIGH, `warning` for MEDIUM) and `lead.why` when present. Name the basis: observed, heuristic or inferred.
3. Section "Coverage & limits", before any numbers: `Rows` with one row per `coverage.limits` item (kind as `meta`) and one per failed provider (`status` danger). An unreached launch, sampled X data, local-only reputation and approximate SOL figures must appear here. Missing provider data is "unknown", never "clean".
4. `Metrics` for the key numbers, then the main visual.
5. Section "Findings & evidence": a `Table` with Finding, Severity, Basis and Evidence columns, plus `LinkCards` for the Solscan or provider links in `evidence`.
6. Section "Next steps": `Steps`, one per `assessment.nextActions` item (title = `label`, detail = `why`, then "Ask Grok Bot: “<ask>”"). Never say a step ran unless you ran it in this turn.
Shorten addresses as `9zd5…QzhD`.
- When there are new alerts, update one "Grok The Block watch: $SYMBOL" Page per token with `EditCanvas`: lead with what changed since the previous successful scan (and when), then `Rows` of new alerts, newest first (severity as `status`, before → after in `meta`, evidence links). Mention how many repeats were suppressed. If the last check had a provider failure, say so in a `Callout`.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
