---
name: threat-feed
description: Grok The Block (understand what actually happened on-chain, in plain English). Build a threat digest across recently scanned and watched Solana tokens: LP pulls, coordinated insider dumps, RugCheck 'rugged' flags, and enabled mint or freeze authority. Routine-ready, and silent when there is nothing new. Use when someone wants a daily or hourly rug and honeypot digest.
---
# Threat Feed (routine-ready)

## Steps
1. Run `.venv/bin/python skills/threat-feed/scripts/threat_feed.py [--max-tokens 10]`. It re-checks the newest 100 txs of each recently scanned or watched token and prints only threats it hasn't reported before (state is kept in `cache/threat_state.json`).
2. As a routine (read your `routines` skill): hourly or daily, run it and message the user only if it prints threats.
3. Threat types:
   - RUG / LP_CHANGE: LP removal.
   - BUNDLE: 2 or more insiders selling within 5 minutes.
   - HONEYPOT: mint or freeze authority is enabled.
   - RUG: RugCheck marks the token rugged.
4. The original's mock feed is gone. Every item here comes from real data.

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
- One "Threat feed" Page, updated in place: `Rows` with severity `status`, type, token, and detail, plus a `Bars` count by type.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
