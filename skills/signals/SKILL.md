---
name: signals
description: Grok The Block (understand what actually happened, in plain English). Unusual-activity analysis across selected markets in multiple asset classes, with evidence, at the next observation or scan (subject to provider latency), from Polymarket (incl. on-chain trade links), Kalshi, US stocks and options, Treasuries, crypto CEX spot/perps, stablecoin supply, FX/commodities/VIX, SEC EDGAR filings and Solana watch alerts, with an uncalibrated anomaly-convergence ranking. Use when someone asks what's moving in the markets it covers, to be alerted on new unusual activity, or to watch markets on a schedule. Not financial advice.
---
# Signals: selected-market unusual-activity feed (routine-ready)

**Not financial advice.** Every signal is unusual activity in public data with the evidence behind it. It is never a prediction, a buy/sell call, or an accusation. Say "unusual activity", "signal", "address newly observed on Polymarket". Never say "insider", "whale knew", "smart money", "about to happen", "anywhere", "as soon as it happens", a probability, or a confidence percentage. Rankings are uncalibrated; no hit rate or lead time has been measured. Never tell the user to buy, sell, bet or hedge, and never trade, sign, connect a wallet or place a bet.

## Run it
- One-shot feed: `.venv/bin/python skills/signals/scripts/signals.py scan` → `out/signals-<UTCstamp>.json` and `out/signals-latest.json` (`kind: "signals"`), which the dashboard's **Signals** tab renders. Takes ~20–40 s.
- Narrow it: `--sources polymarket,kalshi,equities,options,treasury,crypto,stablecoins,macro,sec,solana`, `--tickers SPY,NVDA`, `--options SPY,TSLA`, `--trace 6` (Polymarket markets to trace wallets on).
- All data is keyless and public. SEC EDGAR is opt-in: the SEC requires a declared contact, so set `GTB_SEC_USER_AGENT="Your Name you@example.org"` in the user's own environment. Without it the `sec` source is reported as **NOT_CONFIGURED**, never faked.
- Testing outages: `GTB_SIMULATE_FAIL=polymarket,treasury` marks those providers down; they must show as UNAVAILABLE (unknown, not quiet).

## What each signal carries
`key` (provider:entity:detector, no date), `source`, `family` (prediction / equity / rates / crypto / disclosure), `entities` (canonical), `type`, `severity` (INFO…CRITICAL), `basis` (**observed** / **heuristic** / **inferred** / **unverified** = insufficient baseline or unparsed data), `title`, `what`, `when` (availability time), `observation` (eventTime, availableTime, ingestTime, validAsOf, timesApproximate, sourceStatus, coverage, limitations), `trigger` (observed, baseline, threshold, window, unit, dataAge), `calendar` (scheduled events nearby), `metrics`, `evidence`, `limits`, and in watch mode `incident` (state, episode, history).
Detectors use the review's shadow-mode defaults; see README. Detectors marked `limited` can't apply the full rule on free data, and their limits say why.
Sports/esports in-play markets are skipped; settlement-extreme moves are downgraded one level and say so.

## Present the result as a Page
End every run by rendering the feed as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the dashboard's Signals tab, with kit blocks only. Use `palette={["#00e87b", "#ff3b5c", "#ffb020"]}` on `Page`. Typography comes from the kit; never hardcode fonts. Build it from the report's `assessment`, in this order:
1. Title `Grok The Block: signals <date>`; `summary` = `assessment.lead.text`. For a bundled example say "Example data, recorded <date>, not live".
2. A `Callout` with the lead finding (tone `danger` for CRITICAL/HIGH, `warning` for MEDIUM) and `lead.why`. Name the basis.
3. Section "Coverage & limits", before any numbers: a `Table` from `coverage.matrix` (source, family, status, last valid, universe, observed, sample fraction, exclusions; HEALTHY success, DEGRADED/NOT_CONFIGURED warning, STALE/UNAVAILABLE danger), then `Rows` for `coverage.limits` and `coverage.notIncluded`. An unreachable source is "unknown", never "quiet". If there are no signals, say what was observed (from `assessment.lead.text`), never "markets were quiet".
4. Section "Uncalibrated anomaly-convergence ranking": one item per `CONVERGENCE` signal, highest `metrics.rank` first, with mode, families and `metrics.chain` (source, title, availability time, link) as the timeline. Never present the rank as a probability or percentage. Forensic mode is never called an early warning. Then `DIVERGENCE` and `RELATED_REPRICING` items as hypotheses.
5. `Metrics` for counts by severity and source, then section "Signals": a `Table` with Signal, Source, Severity, Basis, Available (time), Trigger (observed vs threshold), Calendar and Evidence columns (newest high-severity first), plus `LinkCards` for the top evidence links.
6. Section "Next steps": `Rows`, one per `assessment.nextActions` item (title = `label`, meta = `why` followed by "Ask Grok Bot: “<ask>”"). Never say a step ran unless you ran it in this turn.
7. Close with the disclaimer line: "Not financial advice. Unusual activity in selected public data, with evidence, at the next scan subject to provider latency; not a prediction or a recommendation. Rankings are uncalibrated."
- If a signals Page already exists, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself; draft text for the user if they want to post.

## Alerts on a schedule (routine recipe)
Each user runs this on **their own** Grok Bot. Nothing uses the author's accounts or keys.
1. Baseline once: `.venv/bin/python skills/signals/scripts/signals.py watch --quiet`. The first run records what is already happening and sends nothing.
2. Create a routine (read your `routines` skill first), e.g. every 30 minutes during market hours, hourly otherwise:
   - Prompt: "cd <repo> && .venv/bin/python skills/signals/scripts/signals.py watch --min-severity MEDIUM [--mute <sources>] [--quiet-hours 22-7 --tz-offset <h>]. Read out/signals-latest.json. If `watch.alerts` is empty, send nothing. Otherwise DM me only those alerts, convergence first: one line each with severity, basis, alertReason, title, availability time, and its first evidence link, then update my Grok The Block signals Page. Mention `watch.telemetry` (suppressed, below floor, muted, deferred, skipped-unavailable) and any source that was UNAVAILABLE or STALE. End with: Not financial advice."
   - Digest instead: run with `--digest` on the schedule, and once a day with `--release-digest`.
3. How the lifecycle works: state lives in `cache/signals-watch.json` (a v1 state file is adapted automatically). Incidents are keyed by provider + entity + detector + episode, never by date. Alerts fire on NEW / NEW_EPISODE / NEW_TRANSACTION / MAGNITUDE_RISE (≥25%) / ESCALATED, and REMINDER for unresolved HIGH at 6h then at most daily. An incident goes COOLING then RESOLVED only after 2 valid observations below 75% of its entry threshold. An UNAVAILABLE, STALE or NOT_CONFIGURED source keeps its incidents' last confirmed state and never resolves them. The first run sets the baseline and sends nothing.
4. Optional webhook (Discord/Slack-compatible relays, n8n, your server): `--webhook https://…` or env `GTB_SIGNALS_WEBHOOK`. Only alerts that pass the lifecycle and your controls are POSTed as JSON `{tool, kind: "signals-alerts", generatedAt, disclaimer, previousSuccessfulScanAt, alerts: [{key, incidentId, alertReason, severity, basis, source, title, what, when, evidence, limits}]}`. The URL is never printed or written to reports. Only set it when the user gives you their own URL.

## Rules
- Read-only. Public data only, for the user's own local analysis. Don't republish provider data as a public feed: rights are unverified (docs/PROVIDER-RIGHTS.md). Respect rate limits (built-in per-host throttles and caching; don't loop faster than every 10 minutes).
- Polymarket wallet tracing stores shortened wallet addresses and transaction links only — never names, pseudonyms or profile images.
- The tool never whitelists or skips any market, token or ticker, including any tied to the author.
