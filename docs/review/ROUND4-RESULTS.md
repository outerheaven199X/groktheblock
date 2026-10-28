# Round 4 results (ROUND4-REVIEW of e29040e)

Implementation commit: **`5db4c29`** on `main`. This file is added in the commit after it. Status table: `FINDINGS.md` → "Round 4". Evaluation: `EVALUATION.md` (§0 objective, §3 baselines).

**Changed files (60):** `lib/grok_the_block/markets/{lifecycle,feed,detectors,entities,timebase,sources,replay}.py`; `skills/signals/scripts/{signals,replay_real}.py`; `skills/signals/SKILL.md`; `README.md`; `ui/index.html` and `ui/index.html.sha256`; `examples/signals-EXAMPLE.json` (regenerated from a real scan, 2026-10-28 13:04 ET); `docs/review/{FINDINGS,EVALUATION,METHODOLOGY}.md`, `eval-config.json` (r4), `eval-results.json`, `round4-tests-before-fix.txt`; `docs/ci/tests.yml`; `tests/test_round4.py`, `tests/ui/ui_r4.py`, `tests/ui/ui_r3.py` (wording); `tests/fixtures/providers/` (MANIFEST plus 25 new saved responses); refreshed `docs/*.png`.

## Per item

| Item | Code correction | Regression (failed on e29040e → passes now) | Remaining limitation |
|---|---|---|---|
| R4-01 | `lifecycle.step` uses the **hottest** member (`max`), not `min`. `_members` keeps still-active members on recomposition and records `memberHistory` | mixed A=0.20/B=1.40 ×3 → ACTIVE (was COOLING, RESOLVED); 0.20/0.50 ×2 → COOLING, RESOLVED; missing B → HELD_UNOBSERVED; JSON round-trip | Exit thresholds are shadow-mode settings, not validated |
| R4-02 | `lifecycle.admit`: needs a current source (not STALE/UNAVAILABLE/NOT_CONFIGURED), a valid time and a valid probe. Otherwise HELD_STALE/HELD_INVALID (lastConfirmedAt kept) or `notAdmitted`. `feed.analyze_daily` stamps each instrument's own freshness | unit ×3, plus integration through `feed.run → feed.watch → lifecycle` with Yahoo-shaped rows ×3. Before the fix, a stale scan produced a REMINDER | Event detectors (SEC, Solana) have no ratio probe; they are admitted on source and time validity only |
| R4-03 | `detectors.certainty` per contributor; `timingComparable`; mode `timing-approximate` with `spanHours: null`, no timing bonus; UI says "timing comparison approximate" and shows the time basis per group | `test_R4_03_*` ×2; `ui_r4.py` span/wording checks (desktop, 390, 375, 200%) | Event-time ordering is still not used (no documented release times) |
| R4-04 | `daily_bar_status(tz=)` reads the session date in the provider clock: Yahoo exchange tz; date-only rows keep their UTC date; FX London-day bars complete at London midnight and get a `clockNote`. Per-instrument completion and freshness; coverage has `fetchedInstruments` vs `analyzedInstruments` and `instrumentStatus` | `test_R4_04_*` ×6 on saved Yahoo (6 months, the Nov-2025 early close, the Mar-2026 DST change), Nasdaq, OKX payloads | `PUBLISH_LAG_S` is still an estimate. treasury.gov/Kalshi/Gamma/DefiLlama/Coinbase payloads are saved but not parsed in tests. No real Form 4 |
| R4-05 | "distinct counted evidence groups" everywhere; outcome matching (cut/hike/hold/above/below); a price-level contract → SETTLES_ON_UNDERLYING in its instrument's dependency group; same-group members listed as excluded with the reason | `test_R4_05_*` ×5, including the live round-3 lead's "10Y" wording | Still a hand-written relation table; no empirical independence test (R3-12) |
| R4-06 | `deliver` → bounded `deadLetter` (200) with lastError. `retry_dead_letter` / `--retry-dead-letter`. `Idempotency-Key` header. At-least-once wording in README/SKILL | `test_R4_06_*` ×3 (exhaustion, crash between POST and persist duplicates the same alertId, CLI/docs) | Not monitored; no alerting on dead letters beyond the report |
| R4-07 | `.calchip` is one inline-flex chip with the phase inside it; sidecar refreshed from the bytes | `ui_r4.py` overlap at 375/390/200%; tap ≥44 px; focus visible; `test_R4_07_index_html_sha256_…` | **CI not active**: the push token lacks GitHub `workflow` scope, so the workflow is at `docs/ci/tests.yml` for the owner to move. Emulation only |
| Claim | README now opens with the suggested first-release claim | `test_R4_07_readme_first_release_claim` | — |
| Evaluation | Objective stated first; vol-normalized single and calendar-only baselines; per-session burden; config r4; **thresholds unchanged** | `eval-results.json` | No adjudicated labels, no news timeline, no hit rate or lead time |

## Exact commands and results (2026-10-28)

Python (`/tmp/gtbvenv` = a venv with `requirements.txt`):

| Command | Result |
|---|---|
| `python tests/test_round4.py` | **27/27** (on e29040e code: 4/27; see `round4-tests-before-fix.txt`) |
| `python tests/test_round3.py` | 19/19 |
| `python tests/test_signals.py` | 122/122 checks |
| `python tests/test_replay.py` | 7/7 fixtures |
| `python tests/test_classify.py` · `python tests/test_watch_diff.py` | pass · pass |
| `python tests/test_no_leaks.py` | pass, 185 tracked files clean |
| `cd ui && sha256sum -c index.html.sha256` | OK |
| `python skills/signals/scripts/replay_real.py` | exit 0; results in EVALUATION.md |

UI (Playwright, Chromium **emulation**, served copies of `ui/` + `examples/`):

| Command | Result |
|---|---|
| `python tests/ui/ui_r4.py http://localhost:8796/ui/ before …` (e29040e UI) | 12/27; the overlap, span and wording checks fail as expected |
| `python tests/ui/ui_r4.py http://localhost:8768/ui/ after …` | **27/27** |
| `ui_r3.py` (UI-01) | 111/111 |
| end-to-end capture (`e2e_r3.py`, output redirected) | 155/155 checks, 191 screens |
| `signals_ui.py` · `graph_ui.py` · `smoke-sig.py` · `watch_ui.py` | 54/54 · 12/12 · 9/9 · 1/1 |
| `anim.py` desktop / android / iphone / reduced / badls | 32/32 · 31/31 · 31/31 · 32/32 · 32/32 |

## Live checks actually performed
- `signals.py watch --min-severity LOW` against live public sources, twice: 9/10 sources answered (polymarket DEGRADED: address tracing failed on 1 market); SEC NOT_CONFIGURED. Equities analyzed 15/15. Macro coverage carries the Yahoo FX London-clock notes. The round-3 lead (TLT options + the "10Y yield above 3.49%" contract) is now **RELATED_ACTIVITY**, not CONVERGENCE.
- Webhook through `feed.watch` to a local HTTP server: 5 runs at HTTP 500 → 2 alerts dead-lettered (attempts 5, "non-2xx response"); `retry_dead_letter` run at HTTP 200 → 2 delivered. 12 POSTs in total, all with `Idempotency-Key` = alertId. The URL was not written to the state file.
- Saved responses fetched from free endpoints on 2026-10-28: Yahoo chart v8, Nasdaq historical, OKX candles, Coinbase candles, treasury.gov CSV, Kalshi, Gamma, DefiLlama.

## Not verified / remaining
- Physical iOS/Android and Safari: **not tested**. Touch tab navigation on real hardware: not tested.
- SEC Form 4 live or saved: none (no contact). Calendar contact: not configured; BLS rows still need a rebuild with a real `GTB_CONTACT`.
- Licensed redistribution: every provider is still "unverified".
- Predictive accuracy, hit rate, lead time: not measured. Labelled evaluation standard (≥90 days, ≥100 adjudicated events and matched windows, ≥100 unfiltered alerts): not met.
- CI: workflow staged, not active (needs a token with `workflow` scope).

## Release decisions
- **Local user-run research preview: CONDITIONAL GO.** R4-01 and R4-02 are fixed with integration tests. Precise timing claims from unknown timestamps are removed (R4-03). Descriptions are observational and ranking is secondary. Conditions: label it experimental, local/user-run and subject to provider terms; don't claim mobile or Safari verified until tested on devices.
- **Public hosted alert service: NO GO.** It needs vendor permissions (access, caching, derived signals, distribution), appropriate-latency licensed feeds, labelled historical evaluation, monitored delivery, load tests and real client-device tests. None are waived.

Not financial advice.
