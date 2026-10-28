# Round 6 results (ROUND6-REVIEW of c894915)

Commit: see `git log` (the round-6 commits on top of `c894915`; normal pushes only, no history rewrite). Not financial advice. Read-only: nothing trades.
Regressions: `tests/test_round6.py` (14). Before the fix, on c894915: **0/14** (`round6-tests-before-fix.txt`). After the fix: **14/14**.

| Item | Status | What changed | Tests |
|---|---|---|---|
| R6-01 (P0) present-but-invalid observations age | **PASS** | A held stale/invalid present signal now runs the same aging as a missing one: UNCONFIRMED, then ARCHIVED_UNRESOLVED on the source's publication cadence. `lastConfirmedAt` is never refreshed and there are no alerts. Events go OBSERVED → UNCONFIRMED when their source is STALE, then ARCHIVED_UNRESOLVED at lastValidObs + 2× the freshness limit. An outage (UNAVAILABLE/NOT_RUN) still pauses the clock. A later valid observation opens NEW_EPISODE. (`lifecycle.py` `_age`, `deadlines`) | `test_R6_01_*` (2). `test_round4` R4-02 amended to expect `HELD_STALE→UNCONFIRMED` |
| R6-02 slowest-member clock | **PASS** | Cross incidents age on the slowest missing member's deadline. Daily sources are holiday-aware: UNCONFIRMED at max(last+96h, 1st next publication+24h), archive at max(last+168h, 3rd next publication+24h), using the bond calendar for Treasury. Friday Treasury+Kalshi with MLK Monday: not archived at 72h or 120h; archived at 174h | `test_R6_02_*` |
| R6-03 partial overlap | **PASS** | Uses `eventInstance` from the signal when present. A+B→A+C with the same instance continues as IDENTIFIED_EVENT, with memberHistory added/dropped/retained and alert MEMBERS_CHANGED. A different instance starts a new episode, and the old evidence is kept. Without an identity, the continuation is marked HYPOTHESIS and shown. A+B→C+D starts a new episode. No Jaccard | `test_R6_03_*` (3) |
| R6-04 public samples and history | **PARTIAL** | All examples and docs images are synthetic or project-generated, rendered from synthetic inputs. `docs/assets-manifest.json` covers 56 assets with sha256/source/status and is checked by test and CI step. The scanner checks real identifiers by hashed denylist. Real originals are kept only in a gitignored private dir. History: `tools/verify_history.py` finds 177 items over 21 commits. A purge rehearsal on a disposable mirror clone found **0** after the purge, with the HEAD tree unchanged and nothing pushed. **Published history is unchanged** (owner decision; options in `HISTORY-EXPOSURE.md`) | `test_R6_04_*` (4) |
| R6-05 no SAME_EVENT from alias | **PASS** | An unnormalized question falls back to RELATED_ACTIVITY (was SAME_EVENT). A conditional question gives RELATED_ACTIVITY. A Fed question normalizes to `FED_DECISION:<outcome>:<YYYY-MM>`, and different instances are excluded from convergence. The 5 adversarial pairs do not converge. The positive control (same normalized FOMC cut) still converges | `test_R6_05_*` (2) |
| R6-06 evaluation dataset | **PARTIAL (INSUFFICIENT_EVIDENCE)** | Treasury.gov 2019-2026 (1,896 sessions, 2Y/10Y/30Y + 2s10s, CSV sha256s). Blind shuffled roster: 196 episodes + 196 matched negatives. Holdout from 2025-01-01. Independent criteria, kappa and Wilson rules preregistered in ADJUDICATION.md. Baseline alert burden is reported. **Labels: none. Reviewers: none.** No precision or agreement figure is given | `test_R6_06_*` |
| R6-07 CI and devices | **PARTIAL** | run_all prints SKIP and "SKIPPED (not counted in TOTAL)". The workflow at `docs/ci/tests.yml` adds round 6 and the manifest check. **CI: not active**: the push token lacks the `workflow` scope. The UI is **not tested on a physical device**: all UI results are Chromium emulation | `test_R6_07_*` |

## Commands and counts (2026-10-28)
- `python tests/run_all.py`: 219/219 counted tests (round6 14, round5 30, round4 27, round3 19, replay 7, signals 122), plus no_leaks/classify/watch_diff/private_fixtures passing. With `tests/fixtures/private/` moved away, private_fixtures shows `SKIP … SKIPPED (not counted in TOTAL)`.
- `python tools/build_asset_manifest.py`: 56 assets (synthetic 38, project-generated 14, public-official 1, license-text 3).
- `python tools/verify_history.py`: 177 findings (real repo); 0 (disposable purged clone).
- `python skills/signals/scripts/eval_treasury.py --fetch`
- UI (Chromium emulation, Playwright): ui_r3 111/111, ui_r4 27/27, anim desktop 32/32 / android 31/31 / iphone 31/31 / reduced 32/32 / bad-landscape 32/32, e2e 155/155 (191 screens), signals_ui, graph_ui, smoke-sig and watch_ui ALL PASS.

## Release decision
- **Preview: CONDITIONAL GO.** Conditions: the "not financial advice" disclaimer stays; Objective A is reported as INSUFFICIENT_EVIDENCE; device support is not claimed; the history decision is recorded by the owner.
- **Hosted: NO GO.** Blockers: no labels or adjudication; CI not active; no physical-device testing; history exposure unresolved; provider-rights review.
