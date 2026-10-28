---
name: wallet-scan
description: Profile a Solana wallet: tokens touched, per-token classification, approximate realized SOL PnL, win rate, funding sources and funded wallets, wallet age, and a 0-100 reputation score. Use when someone asks who a wallet is, whether it is a serial sniper or insider, or how much it made.
---
# Wallet Scan

## Steps
1. Run `.venv/bin/python skills/wallet-scan/scripts/wallet_scan.py <wallet> [--max-tx 200]`.
2. Read `out/wallet-<addr8>.json`. It has `wallet` (approximate PnL in SOL and USD, win rate, age, reputation), `tokens` (up to 20, most traded first), `associations` (funding sources and funded wallets, with program and pool accounts removed), and `verdict`.
3. Per-token classes are recorded in `cache/wallet_history.jsonl`, so the leaderboard and reputation learn from them.

## Caveats to state
- PnL is realized SOL flow within the fetched window (the most recent N txs). Open bags count as 0.
- As in the original, the per-token entry block is relative to this wallet's own first tx on that token. So any wallet with 2 or more txs on a token shows as "INSIDER, BLOCK 0 ENTRY" in wallet mode. Treat that as "trades the same token repeatedly", and cross-check it with a token-scan of that coin.

## Present the result as a Page
End every run by rendering the report as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the CryptOSINT dashboard (`ui/index.html`), with kit blocks only:
Page style (matches `ui/index.html`): set `palette={["#00e87b", "#ff3b5c", "#ffb020"]}` on `Page` (organic green, insider/sell red, sniper/warn amber; the same tokens as the UI's `--org`, `--ins`, `--snip`). Class colors are fixed everywhere: ORGANIC green, INSIDER red, SNIPER amber, AGENT blue-violet, COPY cyan. Typography comes from the kit (serif-style headline title, mono for addresses and figures by writing them in backticks); never hardcode fonts or paint your own background. Order sections like the UI tab for this view: a one-line kicker `Text` (data source, tx count, scan time), headline `Metrics` (the UI's gauge cards), the main visual, then tables, then an "Evidence" `LinkCards` section and the disclaimer line. Shorten addresses as `9zd5…QzhD`. Status pills: `danger` for CRITICAL/HIGH, `warning` for MEDIUM, no tone for LOW.
- A `Metrics` row: approximate PnL, win rate, tokens touched, reputation score and grade.
- The verdict in a `Callout`.
- A `Table` of tokens: symbol, class, PnL, first tx.
- Two `Rows` lists in a `Grid`: funded by, and funded.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
