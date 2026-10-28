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
- A `Table`: rank, wallet, appearances, average block, win rate, PnL, tokens. Add a `Segmented` control to switch type if you embed several types.
- One line on the data span and token count.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
