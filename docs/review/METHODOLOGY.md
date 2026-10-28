# Evaluation methodology (rounds 3–4)

Config: `docs/review/eval-config.json` (frozen, version `r4-2026-10-28`; r3 differed only in baselines). Output: `docs/review/eval-results.json` (machine-readable).
Reproduce: `PYTHONPATH=lib python3 skills/signals/scripts/replay_real.py` (needs network for treasury.gov and Polymarket; numbers change as new sessions are published).

**No hit rate, precision or lead time is claimed or computed.** The three tracks below are kept separate and must not be combined.

## Tracks

| Track | Data | What it measures | What it can't show |
|---|---|---|---|
| Synthetic | `tests/fixtures/replay/*.json` (7 hand-built point-in-time fixtures) | plumbing and noise control: dependency grouping, calendar caps, outage holding, midnight identity | anything about real markets |
| Unlabelled historical | treasury.gov par curve; one Polymarket CLOB price history | alert volume and lifecycle behaviour on real public data | whether a flag was meaningful |
| Labelled | the same Treasury sessions, labelled by scheduled official release days (FOMC, CPI, NFP) | whether flags cluster on days with known public news, against a fixed 10bp baseline, with a development/holdout split | informed or unusual trading; lead time; precision for any "insider" notion |

## Point-in-time rules
- Treasury: session *i* uses rows 0…*i* only. Availability is estimated at 18:00 ET (treasury.gov publishes the curve in the afternoon); the estimate is labelled `estimated`.
- Polymarket: the price history is sliced to each point. Gamma 24h volume exists only as a current value, so it is passed as `vol24=None` with `vol24AsOf` = fetch time. `pm_odds_jump` then returns an `unverified` INFO observation and no finding (REPLAY-01). The round-2 replay used the current volume as a floor; that was look-ahead and is superseded (`replay-real-20261028.json` is kept only as the round-2 record).
- Calendar labels come from `data/event-calendar.json`. Its BLS rows were fetched with a placeholder test contact and must be rebuilt with a real `GTB_CONTACT` before the labels count as verified (see the calendar's `provenance`).

## Baseline and split
- Baseline: `|Δ| ≥ 10bp` on 2Y, 10Y or 30Y for the session.
- Development = first half of sessions, holdout = second half. Thresholds were not tuned on either half; both are reported.

## Not available on free data (left unknown, not estimated)
Point-in-time Polymarket/Kalshi volume; historical option chains and snapshot times; intraday equity bars; a news availability timeline; adjudicated event labels; SEC Form 4 history (needs a declared SEC contact, not configured here).

## Minimum standard still unmet (RE-AUDIT §04)
≥90 consecutive days per market-specific claim, ≥100 adjudicated events with 100 matched non-event windows, ≥100 consecutive unfiltered alerts, provider availability clocks, best-single-detector and news-availability baselines, robustness with and without calendar/alias/independence rules. None of these are met, so no performance claim is authorized.


## Round 4 changes (config r4-2026-10-28)
- Detector thresholds unchanged (not tuned). Added two fixed baselines (volatility-normalized single detector, calendar-only) and per-session alert burden. The news/first-publication baseline is recorded as not run.
- The objective question (large moves vs scheduled-day volatility vs information outside the public calendar) is stated in EVALUATION.md §0 before the results.
- Daily bars are dated in the provider's own clock (Yahoo exchangeTimezoneName; date-only rows keep their UTC date). This affects live scans, not the Treasury replay (treasury.gov rows are date strings).
