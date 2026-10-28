---
name: wallet-reputation
description: Grok The Block (understand what actually happened on-chain, in plain English). Score one or more Solana wallets 0-100 for suspicion from their scan history, using the original CryptOSINT weights (INSIDER 25, AGENT 10, SNIPER 8, COPY 3, with multipliers for early entry, young wallets, and funding many wallets). Use when someone asks how sketchy a wallet is.
---
# Wallet Reputation

## Steps
1. Run `.venv/bin/python skills/wallet-reputation/scripts/reputation.py <wallet> [<wallet> ...] [--live]`. `--live` also fetches wallet age.
2. Grades: 0 to 10 CLEAN, 11 to 30 LOW, 31 to 55 MODERATE, 56 to 80 HIGH, 81 and up EXTREME.
3. With no history, run wallet-scan on it first. The score is only as good as what this machine has scanned.

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
- `Properties` per wallet: score, grade, and factors as a `BulletList`.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
