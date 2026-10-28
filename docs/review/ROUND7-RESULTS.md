# Round 7 results (ROUND7-REVIEW of 5fabd64)

Not financial advice. Read-only. Normal pushes only, no history rewrite. Regressions: `tests/test_round7.py` (14). Before the fix, on 5fabd64: **0/14** (`round7-tests-before-fix.txt`). After the fix: **14/14**. No detector threshold, market coverage, UI design, identity model or alerting architecture changed. No labels were produced.

| Item | Status | What changed | Tests |
|---|---|---|---|
| R7-01 (P0) labeling rule | **PARTIAL** (table done; reviewer vignette check NOT_RUN) | The frozen decision table `adjudication-r7.json` (hash recorded in ADJUDICATION.md) has three orthogonal axes. **Anomaly** is checked against an independent reference: the 97.5th percentile of the 250 prior sessions' \|Δ\|, not the detector's rule. **Integrity** covers value, timestamp and availability. **Context** (scheduled / documented / unexplained / unavailable) is reported separately and never changes the primary label. An integrity error is FALSE; an unexplained valid anomaly is ANOMALY_CONFIRMED. The round-6 public-cause rule is withdrawn. `adjudication.py` returns the intended labels for the 4 vignettes. Two independent reviewers have **not** done the vignette check, so labelling must not start yet. | `test_R7_01_*` (3) |
| R7-02 study validity | **PASS** (design); labels empty | The r6 roster, manifest and labels are unchanged (hashes recorded), and the r6 negatives become the named QUIET_CONTROL stratum. New: a detector-independent stratified probability sample. Frame: 7,584 session×tenor windows, 2019-03-29 → 2026-10-27. Strata: 48 (tenor × split × release-day × volatility tercile). Sample: 411 windows, with inclusion probabilities n/N. Release dates come from official FOMC/BLS pages (`release-calendar.json`: 64 FOMC, 93 CPI, 95 NFP). Detector status in the sample (aggregate only; per-item status is sealed): 25 flagged, 25 near-threshold, 361 below. New blind roster `roster-r7.json` (778 items: 196 EPISODE, 196 QUIET_CONTROL, 411 PROBABILITY_SAMPLE, deduplicated) with its hash in `manifest-r7.json`. `labels-r7.json` is empty. | `test_R7_02_*` (3) |
| R7-03 source cadence | **PASS** | `timebase.expected_update` / `cadence` gives each source and instrument its own clock. Treasury: bond sessions 18:00 ET (the R6 logic is kept). Equities: session close (13:00 on early-close days) + 15 min. Options: hourly snapshots while the exchange is open (UNCONFIRMED on the 4th missed snapshot, archived on the 14th). Stablecoins: 7-day, 24h cadence. Macro: VIX 16:15, futures 17:00, FX at the end of the London day (DST-aware). Cross incidents use each missing member's clock. History notes name the clock. Daily-bar floors of 96h/168h stay as fail-safes (not provider SLAs). Nothing is ever RESOLVED by a missed publication. | `test_R7_03_*` (5) |
| R7-04 post-purge receipt | **PASS** | The round-6 receipt is renamed `history-purge-rehearsal.json` (phase REHEARSAL). New `history-purge-final.json` (phase FINAL_FORCE_PUSH) records: old→new SHAs for all 3 branches, the scan going from 177 to 0 findings, the main tree being equal, the fresh-clone check (0 findings, leak test clean, 219/219), PR head b9ec827, and the limits on clones, forks, caches and credential rotation. HISTORY-EXPOSURE.md separates Phase 1 and Phase 2. ROUND6-RESULTS.md is marked superseded on history. The `test_round6` R6-04 test now reads the rehearsal receipt. | `test_R7_04_*` (2) |
| R7-05 CI | **OUTSTANDING** | **CI: not active.** The push token has scopes `repo, gist, read:org` but not `workflow`, so `.github/workflows/tests.yml` can't be pushed. The staged `docs/ci/tests.yml` now includes round 7. There is no green run URL. | `test_R7_05_*` |
| R7-06 devices | **OUTSTANDING** | The UI is **not tested on a physical device** (no iOS Safari or Android Chrome results). The UI was not changed this round. Regression runs below are Chromium emulation only. Draft PR #1 is untouched. | none |

## Commands and actual results (2026-10-28, ET)
- `python tests/run_all.py`: **233/233** counted tests (round7 14, round6 14, round5 30, round4 27, round3 19, replay 7, signals 122); leak/classify/watch-diff/private-fixtures pass.
- `python tests/test_round7.py`: 14/14. `python tests/test_round6.py`: 14/14.
- `python tools/verify_history.py`: 0 findings, 29 commits, 570 blobs.
- `python tools/build_asset_manifest.py`: 65 assets (synthetic 39, project-generated 21, public-official 2, license-text 3).
- `python tools/build_release_calendar.py` and `python skills/signals/scripts/eval_treasury_r7.py`: outputs as above.
- UI (Playwright, **Chromium emulation**): ui_r3 111/111; ui_r4 27/27; signals_ui and smoke-sig ALL PASS; animation desktop 32/32, android 31/31, iphone 31/31, reduced-motion 32/32, bad-landscape 32/32; e2e 155/155 (191 screens). No UI file changed (`git diff 5fabd64 -- ui/` is empty), so there are no before/after pairs. Captures are in `ui-screens-r7.zip` (outside the repo).

## Synthetic vs real
- **Real public-official inputs:** treasury.gov CSVs (local, by hash) and release dates. Derived and committed: the frame, strata, roster and aggregate counts (no raw values).
- **Synthetic:** test inputs, vignettes and the UI examples.
- **Labels:** none.

## Remaining blockers
Reviewer vignette check and labelling (≥100 assessable episodes); CI activation (needs `workflow` scope); physical-device QA; provider rights for hosting.

## Release decision
- **A, user-run research preview: CONDITIONAL GO.** Read-only, local, experimental. No accuracy, prediction or early-warning claim, and the disclaimer stays.
- **B, hosted public alert service: NO GO.**
