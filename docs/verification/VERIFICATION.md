# Verification: UX and usefulness mandate

> **R6-04 (2026-10-28):** this is a historical record of an earlier round. Its evidence files (live scan JSON, CLI logs and 15 screenshots of real tokens) were **removed from the public tree** because they carry real on-chain identifiers and provider-derived values without recorded rights. They remain only in the maintainer's local private fixtures and in git history (see `docs/review/HISTORY-EXPOSURE.md`). The file names below refer to those removed files. The current public examples are synthetic (`examples/`, `tools/synthesize_onchain.py`).

Run on 2026-10-28 against bundled examples and live public data (Helius used, key never printed). UI checks run in headless Chrome (puppeteer-core): **20/20 pass** (`ui-journeys-results.txt`). Unit tests: `tests/test_classify.py` and `tests/test_watch_diff.py` pass.

## Journeys
| # | Journey | Result | Evidence |
|---|---|---|---|
| J1 | $OpenBot: bundle vs organic. The lead finding is that launch-slot wallets held 76.6% of supply. Severity is CRITICAL, raised from LOW, with the reason shown. | Pass | `screens/j1-01-openbot-lead.png`, `j1-02-openbot-full.png` |
| J2 | A flagged wallet opens its evidence (class rule, launch slot, txs), then the copy network for the same subject (clicking a node opens its evidence), then the replay with that wallet highlighted, then a timeline event with its transaction link. A wallet that hasn't been scanned hands off as copy text and says nothing ran. | Pass | `screens/j2-01` … `j2-06` |
| J3 | Watch: a live $Something check produced 21 new alerts. The back-to-back re-check suppressed 14 duplicates by key. A material change (liquidity drop, LP unlock, new risk) shows before → after, when, and evidence. | Pass (the material change uses a labelled fixture, because no live change happened) | `journey3-watch-cli.txt`, `watch-Something-dedupe.json`, `watch-FIXTURE-snapshot-diff.json`, `screens/j3-01`, `j3-02` |

## Failure cases
| Case | Behaviour | Evidence |
|---|---|---|
| Incomplete data | When the launch isn't reached, that becomes the lead finding, and coverage says early labels are unreliable. | `fail-incomplete-launch.txt`, `scan-Fartcoin-incomplete.json`, `screens/f1` |
| Ambiguous ticker | `$TRUMP` has 7 exact-symbol mints, so the scan exits with code 3, lists the candidates and needs a mint or `--pick N`. `$AI` resolves because only one mint matches exactly. | `fail-ambiguous-TRUMP.txt`, `fail-ambiguous-AI.txt`, `ambiguous-TRUMP.json`, `screens/f2`, `f2b` |
| Empty network | With no X posts or copy edges, the page says that absence is not evidence of organic activity, and offers a hand-off. | `shill-NOPOSTS.json`, `screens/f3`, `f3b` |
| Provider failure | `GTB_SIMULATE_FAIL=dexscreener,rugcheck`: the scan still completes. LP and authority values show as unknown, not clean, and the failed providers are listed under coverage. With `rpc`, the scan exits with code 2 and writes no report. In watch, a failure keeps the previous snapshot and is never counted as a change. | `fail-provider-degraded.txt`, `scan-OpenBot-degraded.json`, `fail-provider-rpc.txt`, `watch-Something-provider-failure.json`, `screens/f4`, `f4b` |

Also captured: the command bar separates "Search loaded reports" from "Start a new analysis" (`screens/in-01`), and mobile shows the lead first (`screens/m-01`).

## Known limits
- The material-change demo is a fixture, labelled TEST FIXTURE in the UI.
- Skill slugs (`token-scan` and others) are not renamed, so existing installs keep working. Only the descriptions were rebranded.
- X examples are anonymized. Reputation and the leaderboard only reflect local scans.

## Example data sanitization
- `tools/sanitize_examples.py` was run on `examples/*.json` and `docs/verification/*.json`. The provenance sample is a C2PA test fixture with no X data, so it was left unchanged.
- Each X post is replaced by a short pattern summary such as "Multiplier brag: early market cap versus current (includes contract address)". Links are dropped, and handles and `@` prefixes are removed.
- Follower and following counts are bucketed (`<100`, `100-500`, `500-1k`, `1k-5k`, `5k-10k`, `10k-50k`, `50k+`). Account creation dates become age buckets.
- Cluster structure is unchanged: accounts, edges, bursts and counts. The UI no longer adds `@` to account names.
- `tests/test_no_leaks.py` fails on t.co links, x.com or twitter.com status URLs, `api-key=` values, and absolute local home or workspace paths in any tracked file. A negative check with a planted t.co line failed as expected.
- After sanitizing, all 20/20 UI journeys pass, and the README and verification screenshots were retaken.
