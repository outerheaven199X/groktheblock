# Evaluation (round 5)

## Round 5 decision (R5-06)

**Release objective: A** — characterize unusual moves (what moved, how unusual against its own history, with evidence links and coverage limits). **C is future research** (information outside the public calendar; needs a point-in-time news timeline we don't have). **B is excluded** (forecasting scheduled-day volatility; a calendar already answers it).

- Frozen: universe and thresholds (`eval-config.json` → `frozen`, version `r5-2026-10-28`; thresholds as of f100071, not tuned on any result).
- Adjudication rules: `ADJUDICATION.md` (blind review; MEANINGFUL / CONTEXTUAL / FALSE / UNASSESSABLE).
- Result for objective A: **INSUFFICIENT_EVIDENCE**. 0 flagged moves have been adjudicated (minimum 100 before any precision figure). No precision, recall or lead-time number is reported (`eval-results.json` → `objectiveA`).

The round-4 text below is kept for the record.

# Evaluation (round 4)

**No historical hit rate, precision or lead time has been measured, and none is claimed.** Method, point-in-time rules and the unmet minimum standard: `METHODOLOGY.md`. Frozen config: `eval-config.json` (`r4-2026-10-28`; detector thresholds are **unchanged** from r3 and were not tuned on any result). Machine-readable output: `eval-results.json` (regenerated 2026-10-28, ~17:05 ET, by `python skills/signals/scripts/replay_real.py`). The three tracks are separate; don't add them up.

## 0. Objective (decided before reading results; R4 evaluation item)

The round-3 labelled test is **scheduled-release-day association**, not anomaly truth or early-warning precision. Three different objectives could be meant, and they need different labels and baselines:

| Objective | What would show it | Right baseline | Status here |
|---|---|---|---|
| A. Detect large moves | flags line up with large, adjudicated moves | absolute 10bp; volatility-normalized single detector | partially measurable (both baselines run below); no adjudicated moves |
| B. Forecast scheduled-day volatility | flags fall on scheduled days more than elsewhere | calendar-only | the calendar-only rule is, by construction, identical to the current label: a market detector can't beat it on this label |
| C. Identify information outside the public calendar | flags before a first-publication time on non-calendar events | first-publication / news timeline | **not measurable**: no adjudicated non-calendar events and no free point-in-time news archive |

The tool's stated purpose (observations with evidence and coverage limits) is closest to **A** as a description aid, and it claims none of A–C as validated. The scheduled-day result below is therefore not a reason to lower thresholds: lowering them would optimise for B, which a calendar already answers. **No thresholds were changed in round 4.**

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

**Polymarket CLOB history**: “Will Benjamin Netanyahu be the next Prime Minister of Israel?”, 2744 points 2026-09-28T17:15:29Z → 2026-10-28T17:03:36Z (UTC):
- 1 price move(s) crossed the ODDS_REPRICING price rule; **0 eligible findings and 0 alerts**, because 24h volume isn't point-in-time and the detector now refuses to use current volume (REPLAY-01). Round 2 reported 2 alerts here using the current volume; that was look-ahead and is withdrawn.

## 3. Labelled (scheduled official release days)

Label = the session is an FOMC decision, CPI or Employment Situation release day (`data/event-calendar.json`). It means "a known public information day", **not** informed trading. Label caveat: BLS entries were fetched with a placeholder contact and should be rebuilt (see the calendar provenance).

Baselines (fixed in `eval-config.json` before results; none tuned): **10bp** = |daily change| ≥ 10bp on 2Y/10Y/30Y; **vol-normalized single** = |daily change| / stdev(prior 20 daily changes) ≥ 3 on any one tenor; **calendar-only** = flag every scheduled release day with no market data. A first-publication/news-timeline baseline was **not run** (no free point-in-time archive); it is not substituted.

| Split | Rule | Flagged label days | Flagged other days | Flags per session |
|---|---|---|---|---|
| Development | Detector | 3/24 | 7/173 | 0.051 |
| Development | 10bp | 6/24 | 13/173 | 0.096 |
| Development | Vol-normalized single | 2/24 | 3/173 | 0.025 |
| Development | Calendar-only | 24/24 | 0/173 | 0.122 |
| Holdout | Detector | 3/24 | 17/174 | 0.101 |
| Holdout | 10bp | 3/24 | 11/174 | 0.071 |
| Holdout | Vol-normalized single | 1/24 | 8/174 | 0.045 |
| Holdout | Calendar-only | 24/24 | 0/174 | 0.121 |

Reading: the detector numbers are identical to round 3 (same thresholds, same data window). With 24 label days per half the samples are thin and no interval estimates are given. The detector does not separate release days better than the 10bp rule. The vol-normalized single rule flags the fewest sessions overall and does not separate them either. Calendar-only is perfect on this label by construction, which shows that this label measures objective B and can't evaluate A or C. Labelled evidence for the tool's purpose still needs ≥90 consecutive days, ≥100 independently adjudicated material events with ≥100 matched non-event windows, and ≥100 consecutive unfiltered emitted alerts (ROUND4-REVIEW). None of these exist; **no labels were invented.**

Quality metrics the review lists, and what exists: alert burden per day (flags per session above; lifecycle alerts in section 2); precision of adjudicated relevance, false corroboration rate and time to detect (**not measured**, no adjudicated set); duplicates (synthetic table, "v1 sim" vs alerts); failure/retry rates (webhook: tested in `tests/test_round4.py` R4-06 only, no field data).

## 4. What this does not show
- Whether any alert preceded public information (no availability-time news timeline).
- Precision/recall against adjudicated events, or any lead time.
- Calibration of the related-observations ranking. It stays an uncalibrated sorting aid.
- Whether a pair of distinct counted evidence groups carries independent information: the relation table is a conservative manual filter (R4-05).
- Options, intraday equities, Kalshi intraday, SEC history: no free point-in-time history.
