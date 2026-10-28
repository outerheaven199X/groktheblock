# Round 9 results (ROUND9-REVIEW of 75ae493)

Not financial advice. Read-only. Normal pushes only. No UI change, so no screenshots. Thresholds, source universe and UI design are unchanged. **Human-reviewed labels: 0.** No reviewer, adjudicator or contact was invented.
Regressions: `tests/test_round9.py` (9, named after the review's R9-* table). Before the fix, on 75ae493: **0/9** (`round9-tests-before-fix.txt`). After the fix: **9/9**.

| Item | Status | Change |
|---|---|---|
| 1 (P0) BLS dates as strata | **PASS** (BLS dates themselves still PROVISIONAL) | `release-calendar-r9.json` gives each event a verification state: VERIFIED (the release's own record was read; evidence URL and text stored), FETCHED (page fetched but no release time parsed), or PROVISIONAL (not fetched). FOMC: 64 VERIFIED. CPI/NFP: 188 PROVISIONAL, because GTB_CONTACT is unset; that BLS check is **NOT_RUN**. With a contact, each archived release page is read for its "embargoed until h:mm (ET) …" line; if the release date disagrees with the file name, the release record wins and the mismatch is audited. Strata are now RELEASE_VERIFIED / RELEASE_PROVISIONAL / NO_VERIFIED_RELEASE, so a provisional date can't fill the verified stratum or act as a verified non-release day. Coverage loss is recorded: 64 verified vs 185 provisional sessions; windows 252 / 732 / 6,832. New frozen version r9 (roster, sample, sealed key); r8 files are unchanged and their hashes are in manifest-r9. |
| 2 (P1) interval method | **PASS** | `estimators.py` now uses a stratified SRS-without-replacement design variance with finite-population correction: a census stratum (n = N) contributes 0. It reports per-stratum N / n / labelled / assessable. A stratum with no assessable item goes in `missingStrata`, with `fullPopulation: false`, `publishable: false` and a warning. The bootstrap is removed. No interval is published (there are no labels). |
| 3 (P1) result provenance | **PASS** | `eval-results.json` has one current record, `objectiveA` r9. It carries the evaluation version, computedAt, and file+SHA-256 for the manifest, rubric, roster, sample design and calendar, all verified by test. Status is INSUFFICIENT_EVIDENCE, gate BLOCKED, 0 human labels, all performance fields null, and the vignette set is the 12 r8 vignettes. The r4, r6, r7 and r8 content sits under `historical.*`. `replay_real.py` now writes only to `historical.r4`. |
| 4 (P1) observation vs publication | **PASS** | Each event has `marketObservationApproxAt` (≈15:30 ET, approximate) and `publicationExpectedBy` (18:00 ET). Announcements between 15:00 and 16:00 ET on a bond session are UNCERTAIN: assigned to the next session, with `alternativeSession` for a one-session sensitivity case. March 3, 2020 maps to the same day; Sunday March 15 maps to March 16. No current event is uncertain. No lead time is inferred. |
| 5 (P2) reviewer gate | **PASS (validator); human work NOT_RUN** | The existing `reviewer-gate-r8.json` is kept and pointed at roster-r9 (no new gate). `reviewer_gate.py` refuses PASS without two independent 12-vignette records, a filled adjudicator slot, the 25-item pilot done by both reviewers, and a disagreement record. Reviewers are not assigned; the vignette check and pilot are NOT_RUN. |
| CI / devices | **OUTSTANDING** | **CI: not active** (token lacks `workflow` scope; staged `docs/ci/tests.yml` includes round 9). The UI is **not tested on a physical device**. |

## Counts and hashes (r9)
- Frame: 7,816 eligible windows, 8 ineligible. Strata: 71 (non-empty).
- Population sample: 482. Boundary set: 113. Episodes: 196. Quiet controls: 196. Roster: 920 items.
- Detector status in the sample: 25 flagged, 26 near-threshold, 431 below.
- `release-calendar-r9.json` e25039b7…0b42; `roster-r9.json` a912a91d…dc9; `sample-design-r9.json` 0c009eb8…76f; `manifest-r9.json` 6f44690a…f2e; sealed key 8aaf7110…cbcd (local).
- Fed calendar page hashes: fomccalendars 7224c5a3…1568, 2019 d0ee4198…3423, 2020 f266a3bd…6a08.

## Commands (2026-10-28 ET)
- `python tests/run_all.py`: **259/259** counted (round9 9, round8 17, round7 14, round6 14, round5 30, round4 27, round3 19, replay 7, signals 122).
- `python tools/build_release_calendar.py`: BLS NOT_CONFIGURED.
- `python skills/signals/scripts/eval_treasury_r9.py`.
- `python tools/verify_history.py`: 0.
- **Earlier tests amended:** `test_round8` R8-03 now expects the SRSWOR interval method; `test_round6` R6-06 reads `historical.r6`.

## NOT_RUN
BLS release-time audit (needs GTB_CONTACT); reviewer vignette check; 25-item pilot; CI; physical devices; any performance metric.

## Release decision
- Local research preview: **CONDITIONAL GO**.
- Human evaluation: **STOP / BLOCKED**.
- Hosted alerts: **NO GO**.
