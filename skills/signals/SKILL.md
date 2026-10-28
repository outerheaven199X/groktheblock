---
name: signals
description: Grok The Block (understand what actually happened, in plain English). Cross-market early-warning feed — unusual activity anywhere, with evidence, from Polymarket (incl. on-chain wallet tracing), Kalshi, US stocks and options, Treasuries, crypto CEX spot/perps, stablecoin supply, FX/commodities/VIX, SEC EDGAR filings and Solana watch alerts, ranked by anomaly convergence. Use when someone asks what's moving, "alert me when something is about to happen", or to watch markets on a schedule. Not financial advice.
---
# Signals: the everything feed (routine-ready)

**Not financial advice.** Every signal is unusual activity in public data with the evidence behind it. It is never a prediction, a buy/sell call, or an accusation. Say "unusual activity", "signal", "flagged wallet". Never tell the user to buy, sell, bet or hedge, and never trade, sign, connect a wallet or place a bet.

## Run it
- One-shot feed: `.venv/bin/python skills/signals/scripts/signals.py scan` → `out/signals-<UTCstamp>.json` and `out/signals-latest.json` (`kind: "signals"`), which the dashboard's **Signals** tab renders. Takes ~20–40 s.
- Narrow it: `--sources polymarket,kalshi,equities,options,treasury,crypto,stablecoins,macro,sec,solana`, `--tickers SPY,NVDA`, `--options SPY,TSLA`, `--trace 6` (Polymarket markets to trace wallets on).
- All data is keyless and public. SEC EDGAR is opt-in: the SEC requires a declared contact, so set `GTB_SEC_USER_AGENT="Your Name you@example.org"` in the user's own environment. Without it the `sec` source is reported as **skipped**, never faked.
- Testing outages: `GTB_SIMULATE_FAIL=polymarket,treasury` marks those providers down; they must show as UNKNOWN.

## What each signal carries
`key` (dedupe), `source`, `type`, `severity` (INFO…CRITICAL), `basis` (**observed** read from the source / **heuristic** threshold rule / **inferred** link between facts), `title` (plain English), `what`, `when`, `subject`, `metrics`, `evidence` (links: Polymarket, Polygonscan tx, Kalshi, Cboe, Yahoo/Nasdaq, Treasury, OKX, DefiLlama, SEC, Solscan), `limits`.
Detectors: Polymarket ODDS_JUMP / VOLUME_SPIKE / FRESH_WALLET_BETS (on-chain, wallets new to Polymarket betting ≥$5k while odds moved), Kalshi PRICE_SHOCK / VOLUME_SPIKE, equities VOLUME_Z / PRICE_Z, UNUSUAL_OPTIONS (volume ≥2× open interest, 0DTE/1DTE excluded), Treasury YIELD_MOVE / CURVE_INVERSION / CURVE_SHIFT, crypto OI_SHOCK / FUNDING_EXTREME / spot z-scores, stablecoin SUPPLY_MINT / SUPPLY_BURN, MACRO_MOVE (VIX, DXY, gold, oil, EUR/USD, USD/JPY), SEC INSIDER_FILING_CLUSTER / 8K_EVENT, Solana watch alerts, and **CROSS_MARKET convergence** (0–100; independent sources, severity × basis, count, timing; broad themes discounted).
Sports/esports in-play markets are skipped; moves at or near resolution are downgraded one level and say so.

## Present the result as a Page
End every run by rendering the feed as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the dashboard's Signals tab, with kit blocks only. Use `palette={["#00e87b", "#ff3b5c", "#ffb020"]}` on `Page`. Typography comes from the kit; never hardcode fonts. Build it from the report's `assessment`, in this order:
1. Title `Grok The Block: signals <date>`; `summary` = `assessment.lead.text`. For a bundled example say "Example data, recorded <date>, not live".
2. A `Callout` with the lead finding (tone `danger` for CRITICAL/HIGH, `warning` for MEDIUM) and `lead.why`. Name the basis.
3. Section "Coverage & limits", before any numbers: `Rows`, one per `sourceStatus` entry (state as `status`: ok success, partial/skipped warning, unknown danger) and one per `coverage.limits` and `coverage.notIncluded` item. An unreachable source is "unknown", never "quiet".
4. Section "Anomaly convergence": one card or `Rows` item per `source == "cross"` signal, highest `metrics.convergence` first, listing `metrics.chain` (source, title, time, link) as the evidence chain.
5. `Metrics` for counts by severity and source, then section "Signals": a `Table` with Signal, Source, Severity, Basis, When and Evidence columns (newest high-severity first), plus `LinkCards` for the top evidence links.
6. Section "Next steps": `Rows`, one per `assessment.nextActions` item (title = `label`, meta = `why` followed by "Ask Grok Bot: “<ask>”"). Never say a step ran unless you ran it in this turn.
7. Close with the disclaimer line: "Not financial advice. Unusual activity in public data, with evidence; not a prediction or a recommendation."
- If a signals Page already exists, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself; draft text for the user if they want to post.

## Alerts on a schedule (routine recipe)
Each user runs this on **their own** Grok Bot. Nothing uses the author's accounts or keys.
1. Baseline once: `.venv/bin/python skills/signals/scripts/signals.py watch --quiet`. The first run records what is already happening and sends nothing.
2. Create a routine (read your `routines` skill first), e.g. every 30 minutes during market hours, hourly otherwise:
   - Prompt: "cd <repo> && .venv/bin/python skills/signals/scripts/signals.py watch --min-severity MEDIUM. Read out/signals-latest.json. If `watch.alerts` is empty, send nothing. Otherwise DM me only those alerts, convergence first: one line each with severity, basis, title, when, and its first evidence link, then update my Grok The Block signals Page. Mention how many repeats were suppressed and any source that was unknown. End with: Not financial advice. Never resend a key already sent."
3. How dedupe works: state lives in `cache/signals-watch.json`. An alert fires only for a signal key never seen before, or when the same key's severity rises (`alertType: ESCALATED`, with `previousSeverity` and `previousSuccessfulScanAt`). A run where every source failed sends nothing and keeps the previous baseline; an unknown source never creates or clears alerts.
4. Optional webhook (Discord/Slack-compatible relays, n8n, your server): `--webhook https://…` or env `GTB_SIGNALS_WEBHOOK`. Only new alerts are POSTed as JSON `{tool, kind: "signals-alerts", generatedAt, disclaimer, previousSuccessfulScanAt, alerts: [...]}`. The URL is never printed or written to reports. Only set it when the user gives you their own URL.

## Rules
- Read-only. Public data only. Respect rate limits (built-in per-host throttles and caching; don't loop faster than every 10 minutes).
- Polymarket wallet tracing stores shortened wallet addresses and transaction links only — never names, pseudonyms or profile images.
- The tool never whitelists or skips any market, token or ticker, including any tied to the author.
