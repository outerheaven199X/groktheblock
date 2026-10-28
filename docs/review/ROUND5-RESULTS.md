# Round 5 results (ROUND5-REVIEW of f100071)

Date: 2026-10-28 (ET). Base: `f100071`. Commit with these changes: see `git log` (the SHA is reported in the evaluation handoff outside the repo). Not financial advice.

**Honest scope:** browser checks are Chromium **emulation** only; no physical iOS/Android, no Safari. No hit rate, precision or lead time has been measured. Thresholds were **not** tuned. CI is **staged, not active**. Git history was **not** rewritten.

## Per item (priority order)

Every regression in `tests/test_round5.py` was run against f100071 code first (tests and synthetic fixtures copied in): **3/30 passed**, 27 failed (`docs/review/round5-tests-before-fix.txt`). After: **30/30**.

| Item | What was wrong | Fix | Regression | Result | Limits |
|---|---|---|---|---|---|
| R5-01 (P0) event episodes | SEC/Solana bypassed admission; each repeat refreshed `lastConfirmedAt` and could re-remind; one stale watch report shared the freshest report's verdict; second 8-K per issuer dropped | Immutable ids (SEC accession; Solana `signature:type:mint`) with `eventTs` + `url` per event, else `notAdmitted`; `kind: event`, OBSERVED → ARCHIVED 72h after the last new event ("not a resolution"); repeats: no refresh, no reminder; new ids → NEW_EVENT with `newEventIds`; archived ids never re-alert; BAD/NOT_RUN source pauses the archive clock; per-report Solana freshness (DEGRADED/STALE naming tokens); all 8-K accessions kept with one evidence link each; continuous lifecycle unchanged | `test_R5_01_*` (7) | fixed | Form 4 accessions also carried; no live SEC run (no contact configured) |
| R5-02 (P0) vendor payloads | 31 raw provider responses committed in `tests/fixtures/providers/`; the signals example and 6 screenshots showed real scan content | Synthetic contract generators (`tests/fixtures/contracts/synth.py`, `_provenance: synthetic`); real files moved to gitignored `tests/fixtures/private/` (local only) with `tests/test_private_fixtures.py` (SKIPPED when absent); synthetic `examples/signals-EXAMPLE.json` (`synthetic: true`, every title `[SYNTHETIC]`, links `example.invalid`) from `make_example.py`; `docs/signals-*.png` regenerated from it with sha256 in `docs/screenshots-provenance.json`; PROVIDER-RIGHTS "Public samples"; README wording | `test_R5_02_*` (3, incl. static scan of every tracked file) | **partial** | On-chain token examples (`examples/scan-*`, `wallet-*`, `replay-*`, `watch-*`, `shill-*`, `leaderboard-*`, `threats-sample.json`) and 34 images (`docs/ui-*.png`, `docs/graph-*.png`, `docs/verification/`, `examples/copy-network-OpenBot.png`) are listed as `notSynthetic` and not converted. History still contains the payloads (below). |
| R5-03 composition/expiry | Dropped or unobserved members kept forever | `memberLastValid`; UNCONFIRMED at 24h without a valid observation, ARCHIVED_UNRESOLVED at 72h (daily sources 96h/168h so weekends can't archive), never RESOLVED; disjoint member set → new episode `#eN`, old one in `previousEpisodes` (`endedAs: SUPERSEDED`), NEW_EPISODE | `test_R5_03_*` (3) + R4 tests 27/27 | fixed | "Materially different" = disjoint member set; partial overlap keeps the episode (memberHistory) |
| R5-04 settlement spec | Settlement guessed from the entity's first instrument; proxies called "mechanically linked" | `entities.settlement_spec` → `settlementMetric`, `referenceInstrument`, `unit`, `threshold`, `date`, `polarity`, or None; Fed funds = FED_FUNDS_TARGET (no instrument, SAME_EVENT, not 2Y); 10Y contract vs TLT options = "correlated proxy … not identical"; BTC level vs spot = "same reference … not independent evidence"; ambiguous company forecasts UNRESOLVED | `test_R5_04_*` (4) | fixed | Regex spec over question text; a manual table, not a resolver of contract rules |
| R5-05 parser contracts | Parsers inline, no invalid-case tests | `sources.parse_*` per provider, fetchers call them; valid + ≥3 invalid cases each offline; OKX `confirm` flag; treasury unit guard; Kalshi per-market drop; malformed sibling can't mask or clear | `test_R5_05_*` (11) | fixed | Optional real-payload check is local only: 26 parsed, 0 failed, 5 unmapped (of 31) |
| R5-06 evaluation | Objective not chosen | **Release objective A**; C future research; B excluded; universe + thresholds frozen (`eval-config.json` r5); `ADJUDICATION.md`; `eval-results.json` `objectiveA` = INSUFFICIENT_EVIDENCE (0 adjudicated, precision null) | `test_R5_06_*` | fixed (method) | No adjudication done; `objectiveA` written by hand from that fact, no replay re-run this round |
| R5-07 CI | "Staged" was in docs only | `docs/ci/tests.yml` header: STAGED, NOT ACTIVE; adds round5, private fixtures, run_all; `tests/run_all.py` prints per-suite totals, SKIPPED and TOTAL | `test_R5_07_*` | partial | Not active: token lacks `workflow` scope (see CI section) |

## Commands and counts (repo root, project venv python)

| Command | Result |
|---|---|
| `python tests/test_round5.py` | **30/30** (f100071: 3/30) |
| `python tests/test_round4.py` | 27/27 (R4-04 payload test replaced by the synthetic-contract test) |
| `python tests/test_round3.py` | 19/19 |
| `python tests/test_signals.py` | 122/122 checks |
| `python tests/test_replay.py` | 7/7 fixtures |
| `python tests/test_classify.py` · `python tests/test_watch_diff.py` | pass · pass |
| `python tests/test_no_leaks.py` | pass, 164 tracked files clean |
| `python tests/test_private_fixtures.py` | local: 26 parsed, 0 failed, 5 unmapped of 31; without the private dir: SKIPPED, exit 0 |
| `python tests/run_all.py` | TOTAL 205/205 counted tests, 0 suites failed; 0 SKIPPED with local private fixtures, 1 SKIPPED (private fixtures) without them, as in CI |
| `cd ui && sha256sum -c index.html.sha256` | OK |
| `python tests/fixtures/contracts/make_example.py` | regenerates the synthetic example (9 signals) |

UI (Playwright, **Chromium emulation**, served copies of `ui/` + `examples/`):

| Command | Result |
|---|---|
| `tests/ui/ui_r3.py` | 111/111 |
| `tests/ui/ui_r4.py http://localhost:8768/ui/ after-r5 …` | 27/27 |
| `e2e_r3.py` (output redirected to `ui-screens-r5/e2e/`) | 155/155 checks, 191 screens |
| `signals_ui.py` · `graph_ui.py` (outputs redirected away from docs/) · `smoke-sig.py` · `watch_ui.py` | all pass |
| `anim.py` desktop / android / iphone / reduced / badls | 32/32 · 31/31 · 31/31 · 32/32 · 32/32 |
| before/after Signals screens (`shots_r5.py`) | 6 before (f100071, real example) + 6 after (synthetic) |

## History exposure (no rewrite done; for Nikki to decide)

Raw provider payloads and real-content examples remain reachable in git history even though they are gone from the tree:
- `tests/fixtures/providers/*` (31 files: Yahoo, Nasdaq, OKX, Coinbase, treasury.gov, Kalshi, Gamma, DefiLlama, Cboe): added in **77707ea** (Cboe/Nasdaq options/OKX perps) and **5db4c29** (Yahoo, Nasdaq hist, OKX candles, Coinbase, treasury, Kalshi, Gamma, DefiLlama); present in every commit up to f100071.
- `examples/signals-EXAMPLE.json` with real scan content: **607c32d**, **e396a91**, **5a431ea**, **77707ea**, **5db4c29**.
- `docs/signals-*.png` showing real content: **607c32d**, **f1a1819**, **5a431ea**, **77707ea**, **5db4c29**.

Removing them needs a history rewrite and force-push (like the separate pending gtb-purge force-push). Neither was done. That decision is Nikki's.

## CI guidance

- Status: **staged, not active.** The workflow is at `docs/ci/tests.yml`; GitHub runs nothing.
- Why: the push token has `gist, read:org, repo`, not `workflow`, so pushes touching `.github/workflows/` are rejected.
- To activate: someone with a `workflow`-scoped token copies `docs/ci/tests.yml` to `.github/workflows/tests.yml` and pushes. In CI, `test_private_fixtures.py` prints SKIPPED (no private payloads), which is expected.
- Until then, run `python tests/run_all.py` locally; it prints each suite, any SKIPPED line and a TOTAL.

## Remaining
- R5-02: convert on-chain token examples and the 34 non-synthetic images; history decision.
- Adjudicated events for objective A (≥100), then a precision figure with an interval.
- Rights: every provider "unverified". SEC contact not configured. Physical device and Safari tests.
- Settlement spec and relations are still a hand-written table.

## Release decisions
- **Local user-run research preview: CONDITIONAL GO.** R5-01 is closed. R5-02 is closed for the public tree's provider payloads, signals example and signals screenshots, but **partial** for on-chain examples/images and history; the reviewer should decide whether that meets the gate. Conditions as round 4 (experimental, local, provider terms, no mobile/Safari claims).
- **Hosted service: NO GO** (rights, monitored delivery, licensed latency, device tests).
