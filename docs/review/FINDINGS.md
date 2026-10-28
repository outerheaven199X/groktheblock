# Market review — findings reconciled against main

Source: `MARKET-REVIEW.html` (review pinned to commit `f1a1819`). Each finding is marked **fixed** (with the code and test that cover it) or **outstanding** (with why).
"Fixed" means the code behaviour changed and a regression test passes. It does not mean the detector is validated: no historical hit rate or lead time has been measured (see `EVALUATION.md`).

| ID | Review § | Finding | Status | Where / regression test |
|---|---|---|---|---|
| F01 | 01 (confirmed defect) | Nasdaq options rows had no expiry → 0/1DTE routing silently failed | **fixed** | `sources.options_chain` parses the OCC code or the expiry group, and rejects and counts unparsed contracts. `options_activity` routes expiry ≤ next session to `SHORT_DATED_OPTIONS` (vol ≥5,000, premium ≥$1M, ≥5× OI, capped LOW). Test: "unparsed expiry rejected, counted", "0/1DTE separate". Live check: Nasdaq NVDA 920 rows, 0 rejected |
| F02 | 01 (confirmed defect) | Signal key carried the UTC date → duplicate alerts across midnight | **fixed** | `detectors.key()` is provider + entity + detector with no date. Episodes live in `lifecycle.py`. Test: "stable identity across UTC midnight" |
| F03 | 03 | Equal-severity repeats suppressed forever; no material-update re-alert | **fixed** | `lifecycle.step` re-alerts on a new episode, a new distinct tx, a ≥25% magnitude rise or an escalation. Tests: MAGNITUDE_RISE, NEW_TRANSACTION, ESCALATED, NEW_EPISODE |
| F04 | 03 | Zero baseline produced an infinite/maximal ratio | **fixed** | Polymarket, Kalshi and equity volume give INFO `unverified` "insufficient baseline", ratio `null`. Tests: "zero baseline", "never infinite", "<40 sessions → unverified" |
| F05 | 04 | One `when` timestamp; event vs availability vs ingest not distinguished | **fixed** | Every signal carries `observation{eventTime, availableTime, ingestTime, validAsOf, timesApproximate}` (`timebase.obs`). Timelines/convergence use availability time |
| F06 | 04 | Source health was ok/partial/unknown only | **fixed** | HEALTHY / DEGRADED / STALE / UNAVAILABLE / NOT_CONFIGURED per source and per observation. Test: "status enum" |
| F07 | 04 | Freshness not calendar/weekend aware | **fixed** | `timebase.freshness` uses NYSE 2025–27 holidays plus SIFMA bond holidays. Tests: Friday-bar-on-Saturday, Veterans Day |
| F08 | 04 | No coverage (universe, sample fraction) or limitations per observation | **fixed** | `coverage{universe, observed, sampleFraction, exclusions}` per source and observation, plus a coverage matrix in the report |
| F09 | 02 | Options thresholds (vol/OI only) | **fixed (limited)** | UNUSUAL_OPTIONS_VOLUME: vol ≥500, premium ≥$250K, vol/OI ≥3, capped MEDIUM. Matched-contract historical relative volume is not available, so the detector is marked `limited` |
| F10 | 02 | Equity "z" on raw volume / mean | **fixed** | Robust z over 60-session log-volume MAD (≥3 and ≥1.8× median). Returns over 20-day realized vol (|z| ≥3). Daily bars only: intraday variants are not available, so they're marked limited in the limitations |
| F11 | 02 | Treasury fixed bp threshold, no regime | **fixed** | max(8 bp, 2.5× robust scale); 2s10s bull/bear steepening/flattening; inversion needs persistence. Test: "bull steepening" |
| F12 | 02 | Prediction-market thresholds | **fixed** | 15m ≥8 pts (CLOB history), 1h ≥12 pts, ≥3× event volatility, settlement-extreme downgrade, event phase. Without history: limited, capped MEDIUM |
| F13 | 05 | "New wallet" overclaims | **fixed** | `NEWLY_OBSERVED_ADDRESS_ACTIVITY`: "address newly observed on Polymarket within available history" |
| F14 | 03 | Convergence counted dependent sources; keyword/topic matching | **fixed** | Canonical alias table (`entities.py`), five causal families with one effective observation each, generic tags never link. Tests: arbitrage pair → no convergence, keyword-only false match, musk ≠ tesla |
| F15 | 03/05 | Convergence "score" reads as a probability | **fixed** | "uncalibrated anomaly-convergence ranking" (`metrics.rank`, `rankNote`). No percentages |
| F16 | 03 | Convergence timing modes | **fixed** | fast (15m–6h), cross-session (≤24h), forensic (≤48h, labelled "not an early warning", capped LOW) |
| F17 | 03 | Divergence not modelled | **fixed** | `DIVERGENCE` (LOW, inferred): related instruments observed this run that stayed within ±1 z |
| F18 | 05 | Stablecoin "mint/burn" labels | **fixed** | `SUPPLY_CHANGE` (≥$250M and ≥0.5%; HIGH ≥$1B), with bridge/revision/peg caveats and per-chain deltas |
| F19 | 02 | OKX OI units and funding interval | **fixed** | OI in contracts and USD (rubik history); funding normalized to 8h from the live settlement interval; p95/p99 tails |
| F20 | 05 | No UNVERIFIED basis | **fixed** | `basis` ∈ observed / heuristic / inferred / unverified |
| F21 | 06 | No provider rights register | **fixed (register only)** | `docs/PROVIDER-RIGHTS.md`. Every row is "unverified, needs review/permission"; no legal conclusions |
| F22 | 03 | No incident lifecycle | **fixed** | NEW→ACTIVE→COOLING→RESOLVED, exit below 75% of entry for 2 valid observations. Tests: hysteresis band, cooling reset, resolved after 2 |
| F23 | 03 | Reminders for unresolved HIGH | **fixed** | 6h, then at most daily. Tests: "6h reminder", "daily reminder" |
| F24 | 04 | Outage could auto-resolve / read as quiet | **fixed** | An UNAVAILABLE/STALE/NOT_CONFIGURED/not-run source keeps the last confirmed state. Tests: "outage keeps last confirmed state", "failed run retains" |
| F25 | 03 | Telemetry conflated suppressed / below-floor / unavailable | **fixed** | `telemetry{suppressedUnchanged, belowFloor, muted, deferred, skippedUnavailable, resolved, reminders}` |
| F26 | 09 | Over-broad wording ("anywhere", "as soon as it happens", "everything") | **fixed** | README, SKILL.md, UI, brief and disclaimer reworded per §09/§05 |
| F27 | 05 | Empty feed reads as "quiet market" | **fixed** | The assessment states what was observed and "not that markets were quiet". Test: "empty feed" |
| F28 | 02 | Form 4 counted filings, not transactions | **fixed** | `edgar_form4_transactions` parses code P/S; open-market purchases vs sales clusters; grants/exercises excluded; unparsed → unverified |
| F29 | 03 | VIX/Kalshi lifetime-volume noise | **fixed** | Kalshi lifetime-volume spikes capped LOW (context only); Kalshi uses executable midpoint when available |
| F30 | 03 | No scheduled-event awareness | **fixed** | `events.py` + `data/event-calendar.json` (FOMC, CPI, NFP, Treasury auctions, monthly opex). Earnings **not included**. Calendar-explained convergence is capped LOW |
| F31 | 07 | Evidence dossier / coverage matrix / node-click evidence / mobile settings | see UI rows in `EVALUATION.md`; status updated at the UX milestone | |
| F32 | 07/08 | Alert quality controls | **fixed** | `--min-severity`, `--mute`, `--quiet-hours` with `--tz-offset`, `--digest`/`--release-digest` (CLI + routine recipe) |
| F33 | 07 | Adversarial historical evaluation (≥90-day replay) | **outstanding** | Only a deterministic fixture replay exists (`EVALUATION.md`). No real-history hit rate or lead time has been measured |
| F34 | 07 | Licensed real-time tier | **outstanding** | Out of scope by instruction (no paid integrations). Free sources are delayed/daily |
| F35 | 06 | Rights confirmed for display/redistribution | **outstanding** | The register exists; every provider still needs review/permission. The default is user-run local analysis, not a central broadcast feed |
| F36 | 05 | Identity / intent claims | **fixed (posture)** | No actor identity or intent is asserted. Tests forbid accusation and probability language |
