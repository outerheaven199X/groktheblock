---
name: shill-network
description: Grok The Block (understand what actually happened on-chain, in plain English). Detect coordinated promotion of a crypto ticker on X: clusters of accounts posting near-identical text, in posting bursts, with accounts created around the same time or with skewed follower ratios. Outputs a coordination index, clusters, and a network graph PNG. Use when someone asks who is shilling a coin or whether its hype is organic.
---
# Shill-network detector (X)

Python cannot call your X tools, so you fetch the posts and the script analyzes the saved JSON.

## Steps
1. Load the `x-api-mcp-guide` skill.
2. Search with the built-in public read `search_posts_all`. The `$` cashtag character is stripped by the API, so search the contract address (best: shill posts nearly always paste the CA), then the bare ticker word plus a qualifier, for example `SOMETHING (solana OR pump OR CA) -is:retweet`.
   - Params: `max_results: 25` (the per-call max), `sort_order: recency`, `start_time` from 1 to 3 days back, `post.fields=created_at,public_metrics,author_id,lang,conversation_id`, `user.fields=created_at,description,public_metrics,verified,location`, `expansions=author_id`.
   - Pass `write_to_file: true` and copy each result file to `out/x-<TICKER>/pN.txt`.
   - Page with `next_token` until it is missing or you have about 200 posts (8 calls).
   - Stay under 30 X calls per minute and keep an eye on the daily budget that each result reports.
3. Run `.venv/bin/python skills/shill-network/scripts/shill_network.py '$TICKER' out/x-<TICKER>`.
4. Read `out/shill-<TICKER>.json`, `.md`, and `.png`.
   - The coordination index is the % of sampled posts that came from accounts in a cluster of 3 or more linked accounts.
   - Clusters list accounts, sample texts, and example post pairs.
   - `exactDuplicateTexts` shows the same normalized text posted by several accounts.
5. Open 2 or 3 example links before you describe anything. Template giveaways and memes can look coordinated.

## Signals
- Text: word-3-shingle Jaccard of 0.6 or higher, after stripping links, @mentions, numbers, and contract addresses. Retweets are skipped.
- Bursts: 4 or more accounts posting within 5 minutes.
- Account creation clustered within 72 hours. Accounts younger than 30 days.
- Under 25 followers, or a following/followers ratio of 10 or more.
- Edges: text similarity, or a shared burst plus a shared creation window.

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
- A `Metrics` row: coordination index, posts, accounts, clusters.
- The network graph PNG as an `Image` (upload or embed it the way the canvas skill allows; otherwise use a `Diagram` of the top clusters).
- One `Section` per cluster: an `AvatarStack` or account list, 2 sample posts as `Quote`s with the handle as `cite`, and the example pairs in `LinkCards`.
- A `Table` of identical texts with account counts.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
