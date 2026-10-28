# Grok The Block

**Understand what actually happened in a token's transactions.** Give Grok Bot a Solana token, a wallet, a ticker, or a promo clip, and it explains the transactions in plain English: who bought at launch, whether supply was bundled into a few wallets, who sold into whom, which wallets copy each other, whether promo accounts on X moved together, and what changed since you last looked. Each answer leads with the main finding, then its coverage and limits, the linked evidence, and what to check next. Results appear as a Page and in a local dashboard.

Grok The Block is an evolution of **[CryptOSINT](https://github.com/outerheaven199X/CryptOSINT) by Nikki ([@varien](https://x.com/varien))**. The original runs on Vite/React, Cloudflare Functions, KV, and paid Helius. This version runs on free public data (Helius optional). It adds plain-English assessments, X coordination checks, promo provenance, and watch diffs.

## What it does

| Skill | What you get |
|---|---|
| `token-scan` | Every launch-window wallet classified INSIDER / AGENT / SNIPER / COPY / ORGANIC, organic score, verdict, LP monitor (DexScreener + RugCheck), bundle signal, JSON export |
| `shill-network` | Coordinated pattern clusters among X accounts posting a ticker (near-identical text, bursts, account age, follower ratios), coordination index, network graph PNG |
| `copy-network` | Leader → follower copy-trade graph |
| `wallet-scan` | Tokens touched, per-token class, approximate SOL PnL, win rate, funders and funded wallets, reputation |
| `rug-replay` | Forensic timeline of a token's life (entries, large sells, LP pulls, mass dumps) merged with X posts |
| `leaderboard` | Repeat snipers and insiders across everything you've scanned |
| `wallet-reputation` | 0–100 suspicion score (original weights) |
| `watch-token` | What changed since the last successful scan (liquidity, authorities, LP lock, verdict, new risks) plus whale and insider-move alerts, deduplicated, with evidence links |
| `threat-feed` | Digest of LP pulls, insider dumps, rugged flags, mint/freeze authority |
| `promo-provenance` | Hashes and reuse, EXIF and generator tags, ffprobe, C2PA, frame and loop checks. Signals, never verdicts |
| `solana-data` | Shared data layer: public RPC with failover, DexScreener, RugCheck, optional Helius, local cache |

Plus `ui/`, a zero-build static dashboard in the original's dark palette that reads the JSON the scripts write.

### How results read
Every token scan, wallet scan and replay carries an `assessment`:
- **Lead finding** in one plain sentence, with why it matters.
- **Severity**, then **coverage and limits**: whether the launch was reached, how many transactions, which providers answered, and the standing limits (sampled X data, local-only reputation, approximate SOL figures). If a provider is down, its values show as unknown, never as clean.
- **Findings**, each tagged by basis: *observed* (on-chain fact), *heuristic* (rule-based classification), or *inferred* (a relationship such as a shared funder or copy timing). Each links to its evidence.
- **Next actions**: a Grok Bot request and a local command to copy. Copying runs nothing.

In the dashboard, the command bar (`/`) keeps two things separate: **1 · Search loaded reports** and **2 · Start a new analysis**, which hands you text to copy into Grok Bot or a terminal. Clicking a wallet row, graph node or timeline event opens its evidence, with links to investigate that wallet or token next. The subject bar keeps the token in view as you move between scan, wallets, copy network, X coordination and replay. A first visit opens a guided demo built from bundled examples, all badged **EXAMPLE: not live**.

## Screenshots

Open `ui/index.html` (serve the repo root, e.g. `python3 -m http.server`, then visit `/ui/`). Press `/` for the command bar, `1`–`8` for tabs, `?` for shortcuts.

![Token scan](docs/ui-token-scan.png)
![Shill network (anonymized)](docs/ui-shill-network.png)
![Rug replay timeline](docs/ui-rug-replay.png)
![Copy-trade network](docs/ui-copy-network.png)
<img src="docs/ui-mobile.png" alt="Mobile layout" width="300">

## Install

**With Grok Bot.** Tell your bot:
> Install the skills from https://github.com/outerheaven199X/CryptOSINT-GrokBot. Clone it on your computer, set up the venv from requirements.txt, and add each folder under skills/ as a skill.

Then ask it things like "scan $TICKER", "who's shilling <CA> on X", or "replay the rug on <mint>". Each skill's `SKILL.md` tells the bot exactly what to run, and to render the result as a Page.

**Standalone (no Grok Bot):**
```bash
git clone https://github.com/outerheaven199X/CryptOSINT-GrokBot && cd CryptOSINT-GrokBot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python skills/token-scan/scripts/token_scan.py <mint>
.venv/bin/python skills/wallet-scan/scripts/wallet_scan.py <wallet>
.venv/bin/python skills/rug-replay/scripts/rug_replay.py <mint>
.venv/bin/python skills/shill-network/scripts/shill_network.py '$TICKER' path/to/x-search-json/
python3 -m http.server 8000   # then open http://localhost:8000/ui/
```
Ambiguous tickers: if more than one Solana mint uses the symbol (for example `$TRUMP`), the scan stops, lists the candidates, exits with code 3 and writes `out/ambiguous-<T>.json`. Re-run with the mint or `--pick N`. To test failure handling, set `GTB_SIMULATE_FAIL=dexscreener|rugcheck|rpc` (comma-separated). `CRYPTOSINT_*` env names and `import cryptosint` still work.

Optional: `export HELIUS_API_KEY=...` for speed. Optional: `ffmpeg`, `c2patool`, and `exiftool` for promo provenance. Run `python3 tests/test_classify.py` and `python3 tests/test_watch_diff.py` to check the classifier port and the watch diff.

The shill detector reads saved X search results (the JSON from X's search API, with `expansions=author_id`). Inside Grok Bot, the bot fetches those with its built-in X tools. Standalone, bring your own export.

## Limits (honest version)
- **Launch window:** with a Helius key, scans go straight to launch on any coin (`getTransactionsForAddress`, ascending). Without one, public RPC only pages newest to oldest, so very busy tokens report `reachedLaunch: false`.
- **PnL is approximate:** it's realized SOL flow in the analyzed window. Open bags count as 0.
- **Alerts poll:** there are no webhooks. `watch_token.py check --loop 600 --every 10` polls every 10s with Helius (30s without), or run it from a routine.
- **Leaderboard and reputation** only know what this machine has scanned.
- **Classifier fidelity:** the rules are a faithful port of `classify.ts`, verified by `tests/test_classify.py`. Documented deviations (pool accounts excluded, on-chain supply, bundle signal) can be turned off with `--faithful`.

## Disclosures
- **Read-only.** No trading, no swaps, no wallet connection, no private keys, no signing. It never asks for a seed phrase.
- **Signals, not accusations.** Every output describes on-chain or on-X *patterns*. The wording is deliberate: "coordinated pattern", "flagged wallet", "signal". Don't relabel results as "bot", "scammer", or "fraud" about a named person. Check the linked evidence first.
- **No API keys required, none stored.** Optional keys come from your environment only. `cache/` and `out/` are git-ignored.
- **Conflict of interest:** the author receives creator royalties from a token associated with this project. The tool **never whitelists, skips, or special-cases any coin**, including that one. If it flags it, it flags it.

## Verification
The journeys and failure cases (bundle vs organic, flagged wallet to evidence, watch to deduplicated alert; incomplete data, ambiguous ticker, empty network, provider failure) are recorded in [docs/verification/VERIFICATION.md](docs/verification/VERIFICATION.md).

## Credits
Grok The Block is an evolution of [CryptOSINT](https://github.com/outerheaven199X/CryptOSINT) by Nikki (@varien). Data from Solana public RPC, [DexScreener](https://dexscreener.com), and [RugCheck](https://rugcheck.xyz). Content credentials via [c2patool](https://github.com/contentauth/c2pa-rs).

MIT License © Nikki (@varien)

## Verdict change: bundle-aware severity

The original verdict only counts wallets, so a launch where 24 bundled wallets held 93.7% of supply still read LOW (organic score 83). The verdict is now raised to the bundle severity when the launch slot held 25% or more of supply (HIGH at 25%, CRITICAL at 50%). This requires the scan to have reached the launch transaction. `organicScore` is unchanged and still matches classify.ts; the original verdict stays in `verdict.originalSeverity`, and `--faithful` turns the escalation off. Re-test: $Something LOW → CRITICAL (93.7%), $OpenBot LOW → CRITICAL (76.6%), Fartcoin stays LOW (no launch-slot bundle).
