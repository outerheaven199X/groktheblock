# Grok The Block

**Unusual-activity analysis across selected public markets, with the evidence behind every flag.**

> **Experimental, user-run market-forensics research tool; rule-based observations with linked evidence and explicit coverage limits. No measured predictive accuracy.**

> **Research preview.** The example data is synthetic, there is no live feed, and it has not been tested on physical devices. Hosted alerts are **NO GO**. The evaluation is **unlabeled** (the human-review gate is blocked), so **no detection accuracy has been measured or is claimed.** Not financial advice. See the [Legal notice](#legal-notice).

## What it is
Grok The Block is the everything app for unusual market activity. Together with Grok Bot, it flags unusual activity across prediction markets, US stocks and options, Treasuries, macro and calendar events, and crypto, and it shows the evidence behind every flag. It never tells you to buy, sell or hold.

Its Python skills run locally or through Grok Bot and write JSON reports. The `ui/` dashboard (design v6) shows those reports with their evidence and states what the data can't show. It never trades, never connects a wallet, never says who traded and never claims wrongdoing.

## Markets covered
All markets below run through one cross-market engine (`skills/signals`, `lib/grok_the_block/markets/`) and appear together in the **Signals** view.

| Market | What is flagged | Public sources |
|---|---|---|
| Prediction markets | Polymarket odds jumps, volume spikes and large trades from new wallets; Kalshi price and volume shocks | Polymarket Gamma/CLOB, Kalshi public API |
| US stocks and options | Daily price/volume anomalies; unusual options volume and open interest | Yahoo/Nasdaq, Cboe delayed |
| Bonds | Treasury yield-curve moves | Treasury.gov / FRED |
| Macro and calendar | Macro series anomalies; activity linked to Fed decisions, BLS releases, Treasury auctions and options expiry (`data/event-calendar.json`) | Yahoo, federalreserve.gov, bls.gov, fiscaldata.treasury.gov |
| Filings | SEC Form 4 and 8-K events as context (opt-in) | SEC EDGAR |
| Crypto | Perp open-interest and funding shocks; stablecoin supply changes; daily anomalies | OKX/Coinbase, DefiLlama |
| Solana module | Token, wallet, rug-replay, copy-trade and leaderboard scans, plus X promo-account and media checks | Solana RPC, DexScreener, RugCheck, Helius (optional) |

Signals from different markets are linked when they line up (convergence, same-family repricing, divergence), and each link says how certain it is.

## What it does
**Views** (`ui/`, top navigation):

| View | Shows |
|---|---|
| Home | Search box, "Try" examples, and Grok Bot |
| Token | Kinetic result sequence: hazard wipe, RESULT, five stats counting up, then the verdict roll. Details tabs: Holders, Timeline, Why flagged |
| Wallet | The same result sequence for a wallet. Rows are the tokens it touched |
| Replay | A token's timeline with a scrubber and an optional X-post overlay |
| Signals | Summary, source filters, expandable evidence dossiers, related observations, coverage matrix, calendar, watch telemetry |
| Threats | Alert feed with a severity filter, expandable alerts, and a monitoring snapshot |
| Shill net | Graph of linked X accounts (anonymized): clusters, isolated accounts, evidence panel |
| Copy net | Leader → follower copy-trade graph from a token scan, with an empty state when there are no links |
| Leaderboard | Sortable ranking of repeat launch-pattern wallets seen on this machine |
| Provenance | Media checks: hashes, C2PA, reuse, metadata signals |

- **Grok Bot:** a three.js character on the result stage. It drops in, hovers, blinks, follows the cursor and reacts to verdicts, and its TL;DR box types out a summary of the report.
- **Verdict phrases** are mapped from each report's severity and score, for example CRITICAL → "Red flags stacking up" and LOW with a high organic score → "Looks organic". An unknown severity reads "Mixed signals", never clean. The phrases never advise buying, selling or holding.
- **Ask about this:** on report headers, holder rows, Why-flagged findings, Live feed items, Signals items and dossiers, Threats alerts, Shill/Copy net evidence panels, Leaderboard rows and Provenance records. It copies a structured prompt (view, item, evidence ID, report and timestamp, key facts, question) built only from page data. You paste it into Grok Bot yourself. If the clipboard isn't available, a selectable text box opens instead.
- **Live feed and ticker:** these replay items from the loaded reports.
- **Open / Export:** Open loads report JSON files from your device. Export saves the current report as JSON.

## Quick start
```bash
git clone https://github.com/outerheaven199X/groktheblock && cd groktheblock
python3 -m http.server 8000        # Windows: py -m http.server 8000
# open http://localhost:8000/ui/
```
- **Serve over http.** From `file://` the browser blocks the 3D modules, and the app falls back to a static bot.
- **Add `?nowebgl`** to force that fallback.

**Run the skills** (standalone; they fetch public data when run):
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python skills/token-scan/scripts/token_scan.py <mint>
.venv/bin/python skills/wallet-scan/scripts/wallet_scan.py <wallet>
.venv/bin/python skills/rug-replay/scripts/rug_replay.py <mint>
.venv/bin/python skills/signals/scripts/signals.py scan
```
Reports go to `out/`. Load them in the UI with **Open**. With Grok Bot, ask it to install the skills from this repo; each `skills/*/SKILL.md` tells it what to run.

**Tests:**
```bash
python3 tests/run_all.py                                  # backend + static UI checks
python3 tools/build_ui_data.py --check                    # embedded example data matches examples/
pip install playwright && playwright install chromium     # once, for the browser tests
python3 -m http.server 8000 &                             # from the repo root
python3 tests/ui/ui_v6.py http://localhost:8000/ui/       # v6 UI in Chromium emulation
```
- `ui_v6.py` checks:
  - zero network requests
  - Ask about this on 13 surfaces, plus the text-box fallback
  - verdict mapping
  - keyboard graph selection
  - 390 px layout and tap targets
  - reduced motion
  - the WebGL fallback
- It runs Chromium with `channel="chrome"`, so Google Chrome must be installed.
- The old `tests/ui/legacy/ui_r3.py` and `ui_r4.py` target the retired v5 UI and are not run.

## How it works
```
skills/*  ──(public data, when you run them)──▶  out/*.json  ──Open──▶  ui/
examples/*.json (synthetic) ──tools/build_ui_data.py──▶ ui/data/reports.js ──▶ ui/
```
- **Skills** (`skills/`):
  - `token-scan`, `wallet-scan`, `wallet-reputation`, `rug-replay`, `leaderboard`
  - `copy-network`, `shill-network`
  - `watch-token`, `threat-feed`
  - `promo-provenance`, `signals`, `solana-data`
- Each report carries an `assessment`: lead finding, severity, coverage and limits, findings tagged *observed*, *heuristic* or *inferred*, and next actions. If a provider is down, its values show as unknown, never as clean.
- **The UI is fully local and makes zero network requests:**
  - **Local assets only:** it loads only its own files (HTML, JS, fonts, data).
  - **No outbound calls:** there is no fetch, XHR or websocket, and the CSP sets `connect-src 'none'`.
  - **Vendored libraries:** three.js r164 and its post-processing passes are vendored in `ui/vendor/`.
  - **Self-hosted fonts:** the fonts are in `ui/fonts/`.
  - **Verified:** a Playwright test checks every request.
- **Plain JavaScript, no build step:** `index.html`, `app.js` and `stage.js`.
- **The skills do use the network:** they call public APIs when you run them. The UI never does.
- **Grok Bot integration** is copy-and-paste only: there is no chat panel, no API key and no deep link.

## Roadmap
- **Live data in the UI.** Today the UI shows saved reports; live polling runs only in `signals.py watch`.
- **Hosted alerts.** No hosted service exists yet.
- **Measured accuracy.** The human-labelled evaluation has not started, so no accuracy is claimed.
- **Dedicated market views.** Non-crypto markets share the Signals view; Token, Wallet and Replay views are Solana-only.
- **More markets.** Futures, FX and non-US equities are not covered.
- **Physical-device testing** on iOS and Android.

## Project status and limitations
- **Research preview.** Local use: CONDITIONAL GO. Hosted or public alerts: **NO GO**. Provider rights, licensed latency, monitored delivery, and load and device testing are all outstanding.
- **Evaluation is unlabeled.** The Treasury evaluation roster and sample exist, but there are **0 human labels**. The reviewer gate needs two independent reviewers, an adjudicator, 12 vignettes each and a 25-item pilot, none of which has happened yet. **No precision, recall, hit rate or lead time has been measured.** Signal rankings are uncalibrated sorting aids. See [docs/review/ROUND9-RESULTS.md](docs/review/ROUND9-RESULTS.md) and [docs/review/FINDINGS.md](docs/review/FINDINGS.md).
- **Synthetic examples.** Everything bundled in `examples/` is invented (`$SYNTHING`, `$SYNBOT`, `$SYNFART`). It describes no real token or wallet.
- **No live feed.** The UI's Live feed replays loaded reports. `signals.py watch` polls only when you run it. Its optional webhook delivery is at-least-once, deduplicated by `alertId` (not exactly-once). There is no hosted service.
- **Devices.** Tested only in Chromium emulation (desktop, 390 px, reduced motion). It has not been tested on physical iOS or Android devices. CI is staged but inactive.
- **Data limits:**
  - Without a Helius key, busy tokens may not reach launch (`reachedLaunch: false`).
  - PnL is realized SOL flow in the analyzed window.
  - Leaderboard and reputation only know what this machine has scanned.
  - X data comes from samples.
  - Release-calendar BLS times are provisional unless `GTB_CONTACT` is set.
- **Footer links:** Risk disclosure and Methodology are placeholders.

## Data sources and provider rights
- **Solana:** public RPC, DexScreener, RugCheck, and Helius (optional).
- **Cross-market:** Polymarket, Kalshi, Yahoo/Nasdaq, Cboe delayed, Treasury.gov/FRED, OKX/Coinbase, DefiLlama.
- **Filings:** SEC EDGAR (opt-in).
- **Calendars:** Federal Reserve and BLS.
- **Rights are unverified.** Display and redistribution rights for each provider haven't been confirmed, so every row in the register is "unverified, needs review/permission".
- **The default posture is self-run:** each user runs the tool for their own analysis. There is no central rebroadcast.
- See [docs/PROVIDER-RIGHTS.md](docs/PROVIDER-RIGHTS.md).

## Licenses and third-party notices
- **Code:** MIT License, © 2026 Nikki (@varien). See [LICENSE](LICENSE).
- **three.js r164:** MIT, copied unmodified (`ui/vendor/three/`, `ui/licenses/three.js-r164-MIT.txt`).
- **Fonts:** Big Shoulders Display, Martian Mono and Noto Sans JP (subset to 危険注意), all under the SIL Open Font License 1.1, with their licence texts in `ui/licenses/`.
- **Notices:** a summary is in [ui/licenses/NOTICE-v6.md](ui/licenses/NOTICE-v6.md). The licences for the archived v5 UI (`ui/legacy/`) are kept in the same folder.
- **Asset manifest:** [docs/assets-manifest.json](docs/assets-manifest.json) lists each asset's SHA-256, source and status.

## Credits
Grok The Block grew out of [CryptOSINT](https://github.com/outerheaven199X/CryptOSINT) by Nikki ([@varien](https://x.com/varien)).

## Legal notice

- **Not advice.** Nothing in this software, its output or this repository is financial, investment, legal or tax advice.
- **No recommendation.** Nothing here is an offer, solicitation or recommendation to buy, sell or hold any asset, token or security.
- **Patterns, not accusations.** Signals and labels (such as "insider", "sniper", "coordinated" or "copy") are statistical and timing patterns in public data. They are not accusations of wrongdoing, and they are not claims about any person's identity, intent or control of any wallet or account.
- **May be wrong.** Output can be wrong, incomplete, delayed or stale. Providers fail, samples are partial, and no detection accuracy has been measured.
- **No warranty.** The software is provided **"AS IS", without warranty of any kind**, express or implied, including merchantability, fitness for a particular purpose and non-infringement. **In no event shall the authors or copyright holders be liable** for any claim, damages or other liability arising from the software or its use (see [LICENSE](LICENSE)).
- **Your responsibility.** Do your own research and consult a licensed professional before making any decision. You are responsible for your own decisions.
- **Third-party data** and trademarks belong to their respective owners. Use of any provider's data is subject to that provider's terms.
- **No affiliation.** This project is not affiliated with, endorsed by or sponsored by xAI, X, Solana, Polymarket, Kalshi, the SEC, the U.S. Bureau of Labor Statistics, the Federal Reserve or any exchange or data provider.
- **Local laws.** You are responsible for complying with the laws and regulations that apply to you, including rules on market data, privacy and the use of analysis like this.
