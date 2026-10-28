# Evaluation

**No historical hit rate or lead time has been measured.** Nothing here shows that any signal anticipates anything. The fixtures test plumbing and noise control. The real-history replay measures alert volume on public data without outcome labels. The review's §08 evidence (a ≥90-day adversarial replay with labelled events, measured precision and lead time against a news/availability timeline) is still outstanding.

## 1. Deterministic fixture replay

Reproduce: `PYTHONPATH=lib python3 -m grok_the_block.markets.replay` (output saved in `replay-fixtures.jsonl`); assertions in `tests/test_replay.py`.
The fixtures (`tests/fixtures/replay/*.json`) are synthetic and point-in-time: a tick may only use observations with availability time ≤ the tick. The harness runs the real entity resolution, calendar tagging, convergence, related-repricing and incident-lifecycle code. "v1" is a simulation of the f1a1819 behaviour: date-stamped keys, alert on a new key or higher severity, and keyword/topic convergence between any two sources.

| Fixture | Ticks | Alerts (v2) | Alerts (v1 sim) | Δ | Convergences (max sev) | Related repricing | False convergence prevented (ticks) | Calendar-tagged signals | Suppressed unchanged | Skipped unavailable | Resolved during outage |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 01-arbitrage-pair | 12 | 2 | 3 | +1 | 0 (–) | 12 | 12 | 0 | 22 | 0 | 0 |
| 02-keyword-false-match | 4 | 4 | 5 | +1 | 0 (–) | 0 | 4 | 0 | 12 | 0 | 0 |
| 03-outage | 12 | 1 | 1 | +0 | 0 (–) | 0 | 0 | 0 | 2 | 6 | 0 |
| 04-quiet-session | 13 | 0 | 0 | +0 | 0 (–) | 0 | 0 | 0 | 0 | 0 | 0 |
| 05-midnight-boundary | 9 | 1 | 2 | +1 | 0 (–) | 0 | 0 | 0 | 8 | 0 | 0 |
| 06-scheduled-cpi | 4 | 4 | 4 | +0 | 4 (LOW) | 0 | 0 | 12 | 12 | 0 | 0 |
| 07-cross-family-control | 6 | 5 | 4 | -1 | 6 (MEDIUM) | 0 | 0 | 0 | 17 | 0 | 0 |

How to read it:
- **Arbitrage pair:** the same Fed contract on Polymarket and Kalshi is one causal family, so it never converges. It's reported as RELATED_REPRICING (INFO). v1 would have alerted on a cross-market "convergence".
- **Keyword-only false match:** "Elon Musk tweets" doesn't map to Tesla, and "economy" doesn't map to the S&P 500, so there are 0 convergences. v1's topic matching would have linked them.
- **Outage:** the treasury incident stays ACTIVE through 6 unavailable ticks (skippedUnavailable = 6) and resolves only after 2 valid observations below 75% of entry.
- **Quiet session:** 0 alerts; the empty-feed text says what was observed, not that markets were quiet.
- **Midnight boundary:** one continuous condition from 23:00 to 01:00 UTC is one alert (v1: two).
- **Scheduled CPI:** three families move after a CPI release. Every signal is calendar-tagged and the convergence is capped at LOW.
- **Cross-family control:** an unscheduled Fed-market + 2Y move converges (MEDIUM, fast mode) and re-alerts once on a ≥25% magnitude rise. A low-severity BTC funding signal doesn't join, because it isn't the same entity.

## 2. Small real-history replay (labelled)

Reproduce: `python3 skills/signals/scripts/replay_real.py` (output saved in `replay-real-20261028.json`, run 2026-10-28). Public data, no outcome labels.

**Treasury par curve (treasury.gov), 395 sessions from 2025-03-31 to 2026-10-27, rolled forward one session at a time:**
- 38 signals on 30 sessions (7.6% of sessions). By type: {'YIELD_MOVE': 29, 'CURVE_SHIFT': 9}; by severity: {'MEDIUM': 6, 'LOW': 32}.
- 28 of 38 signals fell within the calendar window of a scheduled rates event (FOMC, CPI, NFP, or a note/bond auction). Auctions are frequent, so the tag is broad. It is context, not an explanation.
- Lifecycle: 35 alerts across 4 incident keys and 35 episodes ({'NEW': 4, 'NEW_EPISODE': 31}). Daily data means most moves are one-session episodes.

**Polymarket CLOB 15-minute history**: “Will Benjamin Netanyahu be the next Prime Minister of Israel?”, 2744 points from 2026-09-28T14:30:18Z to 2026-10-28T14:24:23Z:
- 2 observations crossed the ODDS_REPRICING rule; 2 lifecycle alerts ({'NEW': 1, 'NEW_EPISODE': 1}).
- Caveat: 24h volume is not point-in-time in Gamma, so the current value is used as a floor (look-ahead on volume only).

## 3. What this does not show
- Whether any alert preceded public information. No availability-time news timeline was built.
- Precision or recall against labelled events, or any lead time.
- Calibration of the convergence ranking. It stays labelled "uncalibrated".
- Behaviour on options, equities intraday, Kalshi intraday or SEC data over history. The free sources don't provide point-in-time history for those.
