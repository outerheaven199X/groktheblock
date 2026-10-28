---
name: rug-replay
description: Reconstruct a Solana token's lifecycle as a forensic timeline (creation, insider, bot, and sniper entries, organic buy waves, large sells, LP removals, mass dumps) and merge in X posts about it. Use for a post-mortem on a rug or crash.
---
# Rug Replay (with X chatter)

## Steps
1. Optional, to overlay X chatter: fetch posts the same way as shill-network step 2 (search the contract address over the token's life) and save them to `out/x-<TICKER>/`.
2. Run `.venv/bin/python skills/rug-replay/scripts/rug_replay.py <mint> [--x-posts out/x-<TICKER>] [--max-tx 500] [--sig-pages 20]`.
3. Read `out/replay-<SYMBOL>-<mint6>.json`. It has `timeline` (events with `relativeTime`; X posts are `X_POST` with a url and can be negative when they came before the analyzed window), `summary` (lifespan of the window, wallets, realized organic loss and insider/agent profit in SOL, rug method LP_PULL, MASS_DUMP, or UNKNOWN), and `walletBreakdown`.
4. If `reachedLaunch` is false, the timeline starts mid-life. Say so.

## Heuristics
- These are ported from replay.ts: LARGE_SELL is 5% or more of supply in one transfer, and MASS_DUMP is 3 or more large sellers within 60s.
- Changes from the original: a dump is reported once per window, not per sell; supply is on-chain; LP_REMOVE needs a SOL gain of 1 or more by the deployer or an insider in an AMM tx (Raydium, Orca, PumpSwap, or CPMM); loss and profit use real SOL flows (the original's token-unit PnL is always about 0).

## Present the result as a Page
End every run by rendering the report as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the CryptOSINT dashboard (`ui/index.html`), with kit blocks only:
- A `Metrics` row: rug method, lifespan, organic loss, insider profit.
- A custom SVG timeline or `Rows` (relativeTime as `lead`, event type as `status`, detail as `title`), with X posts interleaved and linked.
- The wallet breakdown as `Bars`.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
