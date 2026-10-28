---
name: copy-network
description: Draw the copy-trade network from a token scan: follower wallets that buy 3 to 30 seconds after INSIDER or AGENT leaders. Use after token-scan when someone asks who is copy-trading or following the insiders.
---
# Copy Trade Network

## Steps
1. Run token-scan first.
2. Run `.venv/bin/python skills/copy-network/scripts/copy_network.py out/scan-<...>.json`. It prints the leaders and their followers and writes `out/copy-network-<SYMBOL>.png`.
3. The relationships come from the faithful `detectCopyRelationships` port:
   - Followers sit in blocks 2 to 10 and buy 3 to 30 seconds after a leader.
   - With 2 or more matches, the delay stddev must be under 5s.
   - A single match in the window still counts.
4. If there are no INSIDER or AGENT leaders, there is no network. Say that. Don't invent one.

## Present the result as a Page
End every run by rendering the report as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the CryptOSINT dashboard (`ui/index.html`), with kit blocks only:
Page style (matches `ui/index.html`): set `palette={["#00e87b", "#ff3b5c", "#ffb020"]}` on `Page` (organic green, insider/sell red, sniper/warn amber; the same tokens as the UI's `--ok`, `--bad`, `--warn`). Class colors are fixed everywhere: ORGANIC green, INSIDER red, SNIPER amber, AGENT blue-violet, COPY cyan. Typography comes from the kit (serif-style headline title, mono for addresses and figures by writing them in backticks); never hardcode fonts or paint your own background. Order sections like the UI tab for this view: a one-line kicker `Text` (data source, tx count, scan time), headline `Metrics` (the UI's gauge cards), the main visual, then tables, then an "Evidence" `LinkCards` section and the disclaimer line. Shorten addresses as `9zd5…QzhD`. Status pills: `danger` for CRITICAL/HIGH, `warning` for MEDIUM, no tone for LOW.
- A `Diagram` with leaders as boxes, followers as nodes, and edge labels showing the delay in seconds, or the PNG as an `Image`.
- A `Table` of leader, follower, average delay, and matches.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
