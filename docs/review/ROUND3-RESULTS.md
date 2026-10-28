# Round 3 results (RE-AUDIT of 5a431ea)

Implementation commit: **`77707ea`** on `main` (this file is added in the commit after it). Accounting: `FINDINGS.md` → "Round 3" (R3-01…R3-25). Evaluation: `EVALUATION.md`, `METHODOLOGY.md`, `eval-config.json`, `eval-results.json`.

## Changes by item
- **P0.01:** probes are `{ratio, valid, reason}`; a missing or invalid probe holds the incident (`HELD_UNOBSERVED`, `heldUnobserved` telemetry, `lastConfirmedAt`). Only two valid below-exit readings resolve. Cross-market incidents store `members` and resolve only when every member was validly observed. Coverage names failed instruments.
- **P0.02:** `timebase.daily_bar_status` (NYSE close with early closes, VIX 16:15, FX/futures 17:00 ET, crypto UTC); forming bars are dropped. `env()` never clamps a future estimate: unknown → ingest lower bound, non-final future → INCOMPLETE. Option snapshot missing/malformed/future → DEGRADED, granularity unknown, not fast-eligible. Fast mode needs every group timely; divergence needs comparable windows.
- **P0.03:** calendar links carry eventId, phase, rationale and availability; pre-event is annotated, never capped; auctions match tenor and are date-only; the cap applies only when every group is a release reaction to the same event. Contact via `GTB_CONTACT`, recorded `configured:false`.
- **P1.04:** typed relations, dependency groups, RELATED_ACTIVITY, settlement/outcome-aware prediction grouping, contributing and excluded observations stored.
- **P1.05:** first-screen summary (what happened / how fresh / what was observed / why), short wrapped hero, no hero rank, one-sentence empty state, merged timestamps with their basis, keyboard/tap/click graph selection that persists, faded overlapping labels, raised panel on mobile, stacked matrix on phones and a scroll hint on tablets.
- **P1.06:** saved Cboe, Nasdaq and OKX responses as fixtures; parsers split out; per-settlement funding; Form 4 owners/amendments/missing price; Kalshi fallback capped; Polymarket irregular spacing.
- **P1.07:** approved proposition, "available historical or rule-based baseline", "related observations", REPORTED_* SEC names (with an adapter for old reports), Page template updated, no public distribution path, rights register says unverified ≠ permission.
- **P1.08:** `--quiet-tz` (IANA, DST-aware; `--tz-offset` kept), idempotent alert ids, restart-safe webhook outbox with retries; delivered counted on 2xx only.
- **§04:** point-in-time replay, frozen config, methodology, three separate tracks, current volume rejected.

## Regression results (all on 77707ea's tree)
| Suite | Result |
|---|---|
| tests/test_signals.py | 122/122 checks |
| tests/test_round3.py (OBS-01/02/03, TIME-01/01b/02/03, CAL-01/02/03, CONV-01/02/03, PROV-01/02/03, WATCH-01, REPLAY-01, WORDING) | 19/19 |
| tests/test_replay.py | 7/7 fixtures |
| tests/test_classify.py, tests/test_watch_diff.py | pass |
| tests/test_no_leaks.py | pass (154 tracked files) |
| UI-01 `tests/ui/ui_r3.py` (375/390/768/desktop/200% zoom/reduced motion) | 111/111 |
| e2e capture (8 device configs, 191 screens) | 155/155 |
| signals_ui, graph_ui, smoke-sig, watch_ui | all pass, 0 console errors |
| anim (desktop / android / iphone / reduced / storage-fail) | 32/31/31/32/32, 0 fail |

All browser runs are **Chrome/Chromium emulation**. Nothing was tested on a physical phone or in Safari.

## Live provider checks actually performed (2026-10-28)
- Full `signals.py scan` and four `watch` runs against live public data: 9/10 sources answered; SEC NOT_CONFIGURED (no contact). A watch run reported `heldUnobserved: 3`.
- `GTB_SIMULATE_FAIL=polymarket,treasury` and `=kalshi` scans: the failed sources show UNAVAILABLE, "unknown, not quiet".
- Webhook: watch runs against a local endpoint returning 500, then 200. 2 failed and queued, then 2 delivered on retry; the URL was not written to reports or state.
- Saved real responses: Cboe TLT chain, Nasdaq IWM chain, OKX BTC OI, funding history and current funding.
- `replay_real.py`: treasury.gov (395 sessions) and one Polymarket CLOB history (2,744 points).

## Failures and unknowns
- **SEC Form 4**: not live-tested. Parsing is tested on XML built to the EDGAR structure, not a saved real filing (R3-18 partial).
- **Provider fixtures**: Yahoo, treasury.gov, Gamma/CLOB, Kalshi, DefiLlama and EDGAR have no saved-payload fixtures yet (R3-20 partial).
- **Calendar contact**: none configured. BLS rows came from a placeholder test contact and need a rebuild with a real `GTB_CONTACT`.
- **OKX funding history**: the live endpoint returned 20 settlements, under the 30 needed, so FUNDING_EXTREME reports an invalid probe instead of a percentile.
- **Kalshi**: "previous day" timing gives a 0 h span against ingest-time lower bounds. Related observations including Kalshi are never fast mode, but their span is only a lower bound.
- **Independence**: rests on a hand-written link table (R3-12 partial).
- **Evaluation**: no adjudicated labels, no news-availability timeline, no hit rate or lead time (R3-24 outstanding). On the scheduled-release labels the detector does not beat a fixed 10bp rule.
- **Devices**: no real-device or Safari testing.
- `ui/index.html.sha256` is stale (it already was before this round) and was left as is.

## Release decisions
- **User-run research preview: CONDITIONAL GO.**
  - Met: the P0 items are fixed and tested, convergence no longer overstates independence, rights and limits are disclosed, the core mobile content is readable in emulation, and no performance or advisory claims are made.
  - Conditions: label it experimental; each user supplies their own contacts; confirm on a real phone and in Safari before calling mobile done.
- **Public hosted alert service: NO GO.** It needs documented data-use and redistribution rights, licensed feeds at the right latency, monitored delivery, load testing, and labelled real-history validation. None of these exist.

Not financial advice.
