---
name: watch-token
description: Watch Solana tokens for whale buys and sells, moves by flagged insider wallets, and LP removals. This is a polling replacement for webhooks, built to run from a Grok Bot routine. Use when someone says watch this coin or alert me if insiders dump.
---
# Whale Watch (routine-ready)

## Steps
1. Add a token: `.venv/bin/python skills/watch-token/scripts/watch_token.py add <mint|$TICKER> --min-sol 10`. This sets a baseline and does not alert on history.
2. Run token-scan on it once, so insider and agent wallets are known and moves by them get flagged.
3. Create a routine (read your `routines` skill first) that runs every 5 to 15 minutes:
   - Prompt: "cd <repo> && .venv/bin/python skills/watch-token/scripts/watch_token.py check. If it prints nothing, send nothing. Otherwise send me the alerts, grouped by token, with the Solscan links."
   - Alerts arrive minutes late, not in real time.
4. Fast mode, webhook-free: `watch_token.py check --loop 600 --every 10` polls every 10s for 10 minutes (Helius recommended).
5. `list` shows watched tokens, and `remove <mint>` stops watching one.

## Alerts
- LARGE_BUY / WHALE_SELL: the SOL flow is at or above the threshold.
- INSIDER_MOVE: a flagged wallet sold.
- LP_CHANGE / RUG: a big SOL withdrawal from an AMM.

## Present the result as a Page
End every run by rendering the report as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the CryptOSINT dashboard (`ui/index.html`), with kit blocks only:
Page style (matches `ui/index.html`): set `palette={["#00e87b", "#ff3b5c", "#ffb020"]}` on `Page` (organic green, insider/sell red, sniper/warn amber; the same tokens as the UI's `--org`, `--ins`, `--snip`). Class colors are fixed everywhere: ORGANIC green, INSIDER red, SNIPER amber, AGENT blue-violet, COPY cyan. Typography comes from the kit (serif-style headline title, mono for addresses and figures by writing them in backticks); never hardcode fonts or paint your own background. Order sections like the UI tab for this view: a one-line kicker `Text` (data source, tx count, scan time), headline `Metrics` (the UI's gauge cards), the main visual, then tables, then an "Evidence" `LinkCards` section and the disclaimer line. Shorten addresses as `9zd5…QzhD`. Status pills: `danger` for CRITICAL/HIGH, `warning` for MEDIUM, no tone for LOW.
- When there are alerts, update one "Whale watch" Page per token with `EditCanvas`: a `Rows` list of alerts, newest first, with severity as `status` and the Solscan link.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
