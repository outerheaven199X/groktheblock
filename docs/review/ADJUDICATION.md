# Adjudication rules for objective A (round 5, frozen with eval-config r5-2026-10-28)

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
