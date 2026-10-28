# Evaluation (round 3)

**No historical hit rate, precision or lead time has been measured, and none is claimed.** Method, point-in-time rules and the unmet minimum standard: `METHODOLOGY.md`. Frozen config: `eval-config.json` (`r3-2026-10-28`). Machine-readable output: `eval-results.json` (generated 2026-10-28T16:07:45Z). The three tracks are separate; don't add them up.

## 1. Synthetic regression (not market data)

Reproduce: `PYTHONPATH=lib python3 -m grok_the_block.markets.replay` → `replay-fixtures.jsonl`; assertions in `tests/test_replay.py`. The harness runs the real typed-relation convergence, calendar phases and incident lifecycle. "v1" simulates the f1a1819 behaviour.

| Fixture | Ticks | Alerts | v1 sim | Convergences (max sev) | Related repricing | False convergence prevented | Calendar-tagged | Skipped unavailable | Held unobserved | Resolved during outage |
|---|---|---|---|---|---|---|---|---|---|---|
| 01-arbitrage-pair | 12 | 2 | 3 | 0 (–) | 12 | 12 | 0 | 0 | 0 | 0 |
| 02-keyword-false-match | 4 | 4 | 5 | 0 (–) | 0 | 4 | 0 | 0 | 0 | 0 |
| 03-outage | 12 | 1 | 1 | 0 (–) | 0 | 0 | 0 | 6 | 0 | 0 |
| 04-quiet-session | 13 | 0 | 0 | 0 (–) | 0 | 0 | 0 | 0 | 0 | 0 |
| 05-midnight-boundary | 9 | 1 | 2 | 0 (–) | 0 | 0 | 0 | 0 | 0 | 0 |
| 06-scheduled-cpi | 4 | 4 | 4 | 4 (LOW) | 0 | 0 | 12 | 0 | 0 | 0 |
| 07-cross-family-control | 6 | 5 | 4 | 6 (MEDIUM) | 0 | 0 | 0 | 0 | 0 | 0 |

The adversarial cases the re-audit asked for (oil+USO, BTC+MSTR, 8-K+stock, Fed vs unrelated rates, different settlement dates, opposite outcomes, COIN vs BTC, stale TLT + live Fed market, positive control) are deterministic tests in `tests/test_round3.py` (CONV-01/02/03), not replay fixtures.

## 2. Unlabelled historical (real public data, frequency only)

**Treasury par curve** (treasury.gov), 395 sessions 2025-03-31 → 2026-10-27, rolled forward one session at a time:
- 38 signals on 30 sessions. By type {'YIELD_MOVE': 29, 'CURVE_SHIFT': 9}; by severity {'MEDIUM': 6, 'LOW': 32}.
- Calendar phases on those signals: {'PRE_EVENT_POSITIONING': 7, 'POST_EVENT_CONTEXT': 10}. Daily data can't prove a 0–60 min release reaction, so none is tagged RELEASE_REACTION; auctions only match their own tenor and are date-only.
- Lifecycle: 35 alerts across 4 incident keys ({'NEW': 4, 'NEW_EPISODE': 31}). Daily moves usually resolve after two quiet sessions, so most re-entries are new episodes. This is alert burden, not quality.

**Polymarket CLOB history**: “Will Benjamin Netanyahu be the next Prime Minister of Israel?”, 2744 points 2026-09-28T16:15:18Z → 2026-10-28T16:07:39Z:
- 1 price move(s) crossed the ODDS_REPRICING price rule; **0 eligible findings and 0 alerts**, because 24h volume isn't point-in-time and the detector now refuses to use current volume (REPLAY-01). Round 2 reported 2 alerts here using the current volume; that was look-ahead and is withdrawn.

## 3. Labelled (scheduled official release days)

Label = the session is an FOMC decision, CPI or Employment Situation release day (`data/event-calendar.json`). It means "a known public information day", **not** informed trading. Label caveat: BLS entries were fetched with a placeholder contact and should be rebuilt (see the calendar provenance).

| Split | Detector: flagged label days | Detector: flagged other days | 10bp baseline: label days | 10bp baseline: other days |
|---|---|---|---|---|
| Development | 3/24 | 7/173 | 6/24 | 13/173 |
| Holdout | 3/24 | 17/174 | 3/24 | 11/174 |

Reading: with 24 label days per half the samples are thin. In both halves the regime-aware detector flags fewer label days than the fixed 10bp rule and, in the holdout, flags other days at a higher rate than the baseline. Nothing here supports a claim that the detector separates news days better than a simple threshold. No interval estimates are given because the sample can't support them.

## 4. What this does not show
- Whether any alert preceded public information (no availability-time news timeline).
- Precision/recall against adjudicated events, or any lead time.
- Calibration of the related-observations ranking. It stays an uncalibrated sorting aid.
- Options, intraday equities, Kalshi intraday, SEC history: no free point-in-time history.
