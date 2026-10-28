# Round 8 results (ROUND8-REVIEW of fa56b4e)

Not financial advice. Read-only. Normal pushes only, no history rewrite. The UI was not changed, so there are no screenshots. Detector thresholds are frozen. Labels are empty and no adjudications were made.
Regressions: `tests/test_round8.py` (17). Before the fix, on fa56b4e: **1/17** (`round8-tests-before-fix.txt`). The one test that already passed (missed option session / holiday reopening / slow provider) is a guard on behaviour round 7 already implemented. After the fix: **17/17**.

| Item | Status | Change |
|---|---|---|
| R8-01 (P0) calendar | **PASS (FOMC); PARTIAL (BLS)** | `release-calendar-r8.json` is rebuilt from the Fed's own statement pages: 64 FOMC statements, each with its own release date and time (EST/EDT), class (62 SCHEDULED, 2 UNSCHEDULED: 2020-03-03 10:00 and Sunday 2020-03-15 17:00), weekday, and first Treasury observation session (curve ≈15:30 ET, so 2020-03-15 → 2020-03-16, which is not a release). Audit: 64 checked, **0 mismatches** (page date vs URL date, zone label vs New York DST). Corrected r7 error: 2020-03-02 → 2020-03-03. Bond calendar: for 2018-01-01 … 2026-10-27, weekdays without a treasury.gov curve are taken from the official CSVs. This fixes Good Friday 2021/2023/2026 and 2025-01-09, where the curve was published while the NYSE was shut. NYSE holidays for 2018-2024 were added. **BLS: NOT_CONFIGURED.** GTB_CONTACT is unset, so no request was sent. The 93 CPI and 95 NFP dates are r7 archive-file dates, marked `timeVerified: false` (UNAUDITED). |
| R8-02 (P0) 250-session frame | **PASS** | Added treasury.gov 2018 (249 rows; CSV sha256 in manifest-r8). The frame keeps windows with ≥250 valid prior changes: 7,816 eligible, 8 ineligible (the first days of January 2019, listed as UNASSESSABLE and outside every denominator). Every sampled item in every track is eligible. Eligibility is reported by year×tenor and by track. |
| R8-03 estimators | **PASS** | The sealed key stores each item's tracks, `stratumKey`, `inclusionProbability` (population only), boundary selection probability, detector ratio and prior-change count. `estimators.py` gives a Hájek weighted share with a stratified bootstrap interval and refuses a pooled share. Tests recompute every weight from the frozen frame and check that adding EPISODE, QUIET_CONTROL or BOUNDARY items doesn't change the estimate. |
| R8-04 reference | **PASS** | `reference.py` computes the cutoff in code: type-7 interpolation, ≥ cutoff = YES, nulls skipped, <250 changes = UNASSESSABLE. Tests cover each edge case. `adjudication-r8.json` says the anomaly flag measures a statistical tail, not market relevance; reviewers judge only integrity and context; 95% and 99% sensitivity runs are preregistered; "hit rate", "predictive accuracy" and similar are not to be claimed. |
| R8-05 reviewer gate | **PASS (gate in place); human work OUTSTANDING** | `reviewer-gate-r8.json` is BLOCKED: no reviewers or adjudicator assigned (owner decision), vignette check NOT_RUN, 25-item pilot NOT_RUN (marked calibration, not validation). There are now 12 vignettes, covering holiday, false availability, unexplained volatility, borderline and mixed cases. `labels-r8.json` is empty. |
| R8-06 tracks | **PASS** | The tracks are kept separate: population (422 probability-sampled), emitted episodes (196, plus 196 quiet controls never used for recall), and a boundary challenge set (94 windows, detector ratio 0.75-1.25, diagnostic only, no population weight). r6 and r7 artifacts are unchanged; their hashes are in manifest-r8. |
| R8-07 clocks / contact | **PASS** | Every clock is now labelled "provisional (not an SLA)". An unknown source gets "unknown cadence", polled aging, and never a finding or a resolution. The placeholder contact is removed: the calendar tool uses `GTB_CONTACT`, or else NOT_CONFIGURED with no BLS request. *Disclosure:* the r7 BLS index pages were fetched with that placeholder contact. |
| R8-08 CI / devices | **OUTSTANDING** | **CI: not active** (the token lacks `workflow` scope; staged `docs/ci/tests.yml` now includes round 8). The UI is **not tested on a physical device**. No purge was redone and no backups were deleted. |

## New r8 counts and hashes
- Roster r8: 865 items. Track memberships: EPISODE 196, QUIET_CONTROL 196, PROBABILITY_SAMPLE 422, BOUNDARY_CHALLENGE 94.
- Strata: 48. Detector status in the population sample: 19 flagged, 18 near-threshold, 385 below.
- `roster-r8.json` fedf1848…cedf; `sample-design-r8.json` b019cdb9…9d72; `release-calendar-r8.json` 6701aadd…7954; `adjudication-r8.json` 59f36579…2720; sealed key d4fc5b3e…212f (key kept locally).

## Commands and results (2026-10-28 ET)
- `python tests/run_all.py`: **250/250** counted (round8 17, round7 14, round6 14, round5 30, round4 27, round3 19, replay 7, signals 122).
- `python tools/verify_history.py`: 0 findings.
- `python tools/build_release_calendar.py`: FOMC 64, 0 mismatches, BLS NOT_CONFIGURED.
- `python skills/signals/scripts/eval_treasury_r8.py`.
- `python tools/build_asset_manifest.py`.
- **Earlier tests amended:** the `test_round7` R7-01 rubric-version check now accepts r8.

## Release decision
- **Evaluation labelling: STOP** until the reviewer gate passes.
- **Local research preview: CONDITIONAL GO.**
- **Hosted alert service: NO GO.**
