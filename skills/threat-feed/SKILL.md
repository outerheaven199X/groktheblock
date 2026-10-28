---
name: threat-feed
description: Build a threat digest across recently scanned and watched Solana tokens: LP pulls, coordinated insider dumps, RugCheck 'rugged' flags, and enabled mint or freeze authority. Routine-ready, and silent when there is nothing new. Use when someone wants a daily or hourly rug and honeypot digest.
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
End every run by rendering the report as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the CryptOSINT dashboard (`ui/index.html`), with kit blocks only:
Page style (matches `ui/index.html`): set `palette={["#00e87b", "#ff3b5c", "#ffb020"]}` on `Page` (organic green, insider/sell red, sniper/warn amber; the same tokens as the UI's `--ok`, `--bad`, `--warn`). Class colors are fixed everywhere: ORGANIC green, INSIDER red, SNIPER amber, AGENT blue-violet, COPY cyan. Typography comes from the kit (serif-style headline title, mono for addresses and figures by writing them in backticks); never hardcode fonts or paint your own background. Order sections like the UI tab for this view: a one-line kicker `Text` (data source, tx count, scan time), headline `Metrics` (the UI's gauge cards), the main visual, then tables, then an "Evidence" `LinkCards` section and the disclaimer line. Shorten addresses as `9zd5…QzhD`. Status pills: `danger` for CRITICAL/HIGH, `warning` for MEDIUM, no tone for LOW.
- One "Threat feed" Page, updated in place: `Rows` with severity `status`, type, token, and detail, plus a `Bars` count by type.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
