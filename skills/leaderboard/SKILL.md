---
name: leaderboard
description: Rank wallets that keep showing up as SNIPER, INSIDER, AGENT, or COPY across every token scanned on this machine (appearances, average entry block, win rate, estimated PnL). Use when someone asks for the top snipers or repeat insiders.
---
# Sniper Leaderboard

## Steps
1. Run `.venv/bin/python skills/leaderboard/scripts/leaderboard.py --type SNIPER` (or INSIDER, AGENT, or COPY) with `--top 25`.
2. Read `out/leaderboard-<TYPE>.json`.
3. It only knows about tokens and wallets scanned on this machine (`cache/wallet_history.jsonl`). It gets better the more token-scan and wallet-scan runs there are. Say how many tokens it covers.

## Present the result as a Page
End every run by rendering the report as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the CryptOSINT dashboard (`ui/index.html`), with kit blocks only:
Page style (matches `ui/index.html`): set `palette={["#00e87b", "#ff3b5c", "#ffb020"]}` on `Page` (organic green, insider/sell red, sniper/warn amber; the same tokens as the UI's `--org`, `--ins`, `--snip`). Class colors are fixed everywhere: ORGANIC green, INSIDER red, SNIPER amber, AGENT blue-violet, COPY cyan. Typography comes from the kit (serif-style headline title, mono for addresses and figures by writing them in backticks); never hardcode fonts or paint your own background. Order sections like the UI tab for this view: a one-line kicker `Text` (data source, tx count, scan time), headline `Metrics` (the UI's gauge cards), the main visual, then tables, then an "Evidence" `LinkCards` section and the disclaimer line. Shorten addresses as `9zd5…QzhD`. Status pills: `danger` for CRITICAL/HIGH, `warning` for MEDIUM, no tone for LOW.
- A `Table`: rank, wallet, appearances, average block, win rate, PnL, tokens. Add a `Segmented` control to switch type if you embed several types.
- One line on the data span and token count.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
