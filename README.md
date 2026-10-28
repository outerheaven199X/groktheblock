# CryptOSINT for Grok Bot

Read-only Solana and X forensics for Grok Bot. Give your bot a token, a wallet, a ticker, or a promo clip, and it tells you who's actually behind the chart: insiders, snipers, bot-like wallets, copy traders, coordinated promo accounts on X, and recycled or generated promo media. It presents the result as a Page.

This is a port of **[CryptOSINT](https://github.com/outerheaven199X/CryptOSINT)** by Nikki ([@varien](https://x.com/varien)). The original runs on Vite/React, Cloudflare Functions, KV, and paid Helius. This port runs on free public data, and it adds the X shill-network detector and promo provenance checks.

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
| `watch-token` | Whale and insider-move alerts, polled from a Grok Bot routine |
| `threat-feed` | Digest of LP pulls, insider dumps, rugged flags, mint/freeze authority |
| `promo-provenance` | Hashes and reuse, EXIF and generator tags, ffprobe, C2PA, frame and loop checks. Signals, never verdicts |
| `solana-data` | Shared data layer: public RPC with failover, DexScreener, RugCheck, optional Helius, local cache |

Plus `ui/`, a zero-build static dashboard in the original's dark palette that reads the JSON the scripts write.

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
Optional: `export HELIUS_API_KEY=...` for speed. Optional: `ffmpeg`, `c2patool`, and `exiftool` for promo provenance. Run `python3 tests/test_classify.py` to check the classifier port.

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

## Credits
Port of [CryptOSINT](https://github.com/outerheaven199X/CryptOSINT) by Nikki (@varien). Data from Solana public RPC, [DexScreener](https://dexscreener.com), and [RugCheck](https://rugcheck.xyz). Content credentials via [c2patool](https://github.com/contentauth/c2pa-rs).

MIT License © Nikki (@varien)

## Verdict change: bundle-aware severity

The original verdict only counts wallets, so a launch where 24 bundled wallets held 93.7% of supply still read LOW (organic score 83). The verdict is now raised to the bundle severity when the launch slot held 25% or more of supply (HIGH at 25%, CRITICAL at 50%). This requires the scan to have reached the launch transaction. `organicScore` is unchanged and still matches classify.ts; the original verdict stays in `verdict.originalSeverity`, and `--faithful` turns the escalation off. Re-test: $Something LOW → CRITICAL (93.7%), $OpenBot LOW → CRITICAL (76.6%), Fartcoin stays LOW (no launch-slot bundle).
