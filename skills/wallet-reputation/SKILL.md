---
name: wallet-reputation
description: Score one or more Solana wallets 0-100 for suspicion from their scan history, using the original CryptOSINT weights (INSIDER 25, AGENT 10, SNIPER 8, COPY 3, with multipliers for early entry, young wallets, and funding many wallets). Use when someone asks how sketchy a wallet is.
---
# Wallet Reputation

## Steps
1. Run `.venv/bin/python skills/wallet-reputation/scripts/reputation.py <wallet> [<wallet> ...] [--live]`. `--live` also fetches wallet age.
2. Grades: 0 to 10 CLEAN, 11 to 30 LOW, 31 to 55 MODERATE, 56 to 80 HIGH, 81 and up EXTREME.
3. With no history, run wallet-scan on it first. The score is only as good as what this machine has scanned.

## Present the result as a Page
End every run by rendering the report as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the CryptOSINT dashboard (`ui/index.html`), with kit blocks only:
- `Properties` per wallet: score, grade, and factors as a `BulletList`.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
