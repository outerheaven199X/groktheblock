# Adjudication rules for objective A (round 7 table supersedes the round-6 amendment; frozen before any label)

## Round 7 (R7-01): three orthogonal axes, one frozen decision table
Machine-readable and frozen: `adjudication-r7.json` (version r7-2026-10-28, SHA-256 `f3b072c93c6b48bd7f1855352af2cad67ca62c9be0e7767ab673e4ce40961254`); applied in code by `skills/signals/scripts/adjudication.py`.
The round-6 amendment below made an episode FALSE when no documented public cause was found. **That rule is withdrawn**: the product measures anomaly, not the existence of a news story.

| Axis | Values | Question |
|---|---|---|
| Anomaly | YES / NO / UNASSESSABLE | |change| ≥ 97.5th percentile of the 250 prior sessions' |daily change| in the same official series (not the detector's rule; reviewers don't see detector output) |
| Integrity | OK / VALUE_ERROR / TIMESTAMP_ERROR / AVAILABILITY_ERROR / UNASSESSABLE | do values, session date and availability match the official record |
| Context | SCHEDULED / DOCUMENTED_UNSCHEDULED / UNEXPLAINED / UNAVAILABLE | explanation, recorded separately |

Primary label: any integrity error → **FALSE**; integrity or anomaly UNASSESSABLE → **UNASSESSABLE**; OK + YES → **ANOMALY_CONFIRMED**; OK + NO → **NOT_ANOMALOUS**. The context label is reported beside it and never changes it, so an unexplained valid anomaly is not FALSE.
Vignettes: `tests/fixtures/adjudication-vignettes-r7.json` (genuine anomaly with no cause; scheduled CPI move; ordinary move around a public story; wrong timestamp around a real event). The code returns the intended labels. **Two independent reviewers returning them has not been done (NOT_RUN)**, and real labelling must not start before it. No precision is reported on the round-6 rubric.

## (superseded) Round 5/6 text


## Round 6 amendments (R6-06), preregistered
- **Dataset first:** Treasury.gov daily par yields 2019-2026, 2Y/10Y/30Y + 2s10s (`eval-treasury/manifest.json`, CSV SHA-256s). Blind roster `eval-treasury/roster.json`: 196 detector episodes + 196 matched non-alert windows (same series, ≥10 sessions away, no flag within ±3 sessions), shuffled with seed 20261028; membership is sealed.
- **Independent criteria (not circular):** reviewers do NOT apply a "large versus recent history" cutoff (that is the detector's own rule). For each item they answer three questions from the public record: (1) *Relevance*: is there a documented public cause or market-wide event within the window (official release, central-bank communication, auction result, market-wide stress reported in contemporaneous sources)? (2) *Evidence correct*: would the tool's evidence links and values match the official series for that date? (3) *Timestamp correct*: is the session date/availability right (publication ~18:00 ET, holidays)? A label follows mechanically: MEANINGFUL = relevance yes and evidence + timestamp correct; CONTEXTUAL = scheduled release explains it, evidence correct; FALSE = evidence or timestamp wrong, or no relevance on an episode item; UNASSESSABLE = can't tell.
- **Agreement:** Cohen's kappa between the two reviewers on the four labels, before adjudication; disagreements go to a third reviewer with the reason recorded.
- **Intervals:** Wilson 95% interval for each of MEANINGFUL, CONTEXTUAL and FALSE among assessable episode items, development and holdout (from 2025-01-01) separately; the same for matched negatives (how often a non-alert window also has a documented cause).
- **Comparison:** alert burden and, once labelled, the same metrics for the 10bp and volatility-normalized single-rule baselines on their own flagged sessions. No lead-time or prediction claim.
- Fewer than 100 assessable episodes → INSUFFICIENT_EVIDENCE.


Objective A asks: did a flag describe a move that a careful reader would agree was unusual, with correct evidence? These rules must be fixed **before** any labels are read.

## Unit
One flagged incident episode (incident id + episode), not one alert. Repeats inside an episode are not counted again.

## Sample
All episodes in the frozen universe over the evaluation window, or a uniform random sample drawn with a recorded seed. No cherry-picking; drop nothing after looking.

## Blind review
- Two reviewers per item; they see the instrument, the time window and the raw series, **not** the detector's severity, rank or wording.
- Each assigns one label independently. Disagreements go to a third reviewer; the reason is recorded.
- Reviewers may not be the people who set thresholds.

## Labels
| Label | Meaning |
|---|---|
| MEANINGFUL | The move is unusual against the instrument's own recent history and the evidence links/timestamps are correct. |
| CONTEXTUAL | Real move, but fully explained by a scheduled public release or a mechanical link already shown (still counted as correct for A, reported separately). |
| FALSE | Not unusual (data error, stale/partial data, unit or clock error, threshold artefact) or evidence is wrong. |
| UNASSESSABLE | Reviewer can't tell from the evidence available; excluded from the denominator and reported as a count. |

Never label intent, identity or "informed trading". A label is about the move and the evidence only.

## Reporting
- Fewer than 100 adjudicated episodes (excluding UNASSESSABLE): report **INSUFFICIENT_EVIDENCE** with counts per label, no percentage.
- At or above 100: report precision = (MEANINGFUL + CONTEXTUAL) / (adjudicated − UNASSESSABLE) with a Wilson 95% interval, per source and overall, development and holdout separately. Recall is not reported (no complete ground truth of unusual moves).
- Any threshold change after labels are seen invalidates the comparison; start a new config version.
