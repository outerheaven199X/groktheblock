# Provider rights register

This is a working register, not legal advice. Nothing in it says any use is permitted. **Every row is "unverified, needs review/permission"** until someone with authority reads the current terms (and, where needed, gets written permission) and records the outcome here.

**Default posture:** Grok The Block is software each user runs themselves, locally or on their own Grok Bot, for their own analysis. The project does not operate a central feed that rebroadcasts provider data. Anyone who wants to publish signals publicly, run a shared feed, or sell access should resolve the relevant rows first. **A row marked "unverified" is not permission.** No shared feed, auto-publishing of provider data, or public derived-alert path exists in this repo, and none should be added until the rights for that exact use are recorded here. A user-supplied API key is not by itself a right to broadcast that data or alerts derived from it.

Calendar contact: BLS and SEC ask automated clients for a contact. It is configured per user through `GTB_CONTACT` (calendar) and `GTB_SEC_USER_AGENT` (EDGAR). This repo ships with **no contact configured** (`data/event-calendar.json` → `contact.configured: false`); the BLS rows in the shipped calendar were fetched with a placeholder test contact and should be rebuilt.

Terms URLs are where the terms were expected to be found when this was written. Confirm the current document, because they change.

| Provider / endpoint | Owner | Terms URL (to confirm) | Caching here | Derivation | Public display of raw data | Redistribution | Attribution | Rate limits (observed/documented) | Freshness | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| Polymarket Gamma `gamma-api.polymarket.com/markets` | Polymarket | https://polymarket.com/tos | `cache/` JSON, minutes | thresholds on price/volume | unknown | unknown | link to market | per-host throttle here; provider limits undocumented to us | per scan | unverified, needs review/permission |
| Polymarket CLOB `clob.polymarket.com/prices-history` | Polymarket | https://polymarket.com/tos , https://docs.polymarket.com | minutes | 15m changes, event volatility | unknown | unknown | link | documented API limits (confirm) | per scan | unverified, needs review/permission |
| Polymarket data-api (trades, activity) | Polymarket | https://polymarket.com/tos | minutes | per-address sums, first-seen | unknown; shortened addresses only | unknown | Polygonscan tx links | confirm | per scan | unverified, needs review/permission |
| Polygonscan (links only) | Etherscan | https://polygonscan.com/terms | none | none | links only | n/a | link | n/a | n/a | unverified, needs review/permission |
| Kalshi trade API v2 `api.elections.kalshi.com/trade-api/v2` | Kalshi | https://kalshi.com/docs/kalshi-tos (confirm) , https://trading-api.readme.io | minutes | midpoint change, volume ratio | unknown | unknown | link | documented (confirm) | per scan | unverified, needs review/permission |
| Yahoo chart API `query1.finance.yahoo.com/v8/finance/chart` | Yahoo | https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html | hours | robust z, realized vol | unknown | unknown | link | undocumented | daily bars | unverified, needs review/permission |
| Nasdaq `api.nasdaq.com` (quotes history, option chains) | Nasdaq | https://www.nasdaq.com/terms-of-use (confirm) | hours | as above | unknown | unknown | link | undocumented | daily / delayed | unverified, needs review/permission |
| Cboe delayed quotes `cdn.cboe.com/api/global/delayed_quotes/options` | Cboe | https://www.cboe.com/about/legal/ (confirm); OPRA terms may apply to options data | 10 min | volume/OI/premium | unknown | unknown (OPRA rules may apply) | link | undocumented | ~15 min delayed | unverified, needs review/permission |
| Treasury par yield curve `home.treasury.gov` | US Treasury | https://home.treasury.gov/ (site policies) | hours | bp moves, regimes | likely public-domain US government work (to confirm) | to confirm | link | n/a | daily | unverified, needs review/permission |
| FRED `fred.stlouisfed.org` (DGS series) | St. Louis Fed | https://fred.stlouisfed.org/legal/ | hours | as above | series-specific (confirm) | series-specific | link and citation | documented for API keys; CSV unkeyed (confirm) | daily | unverified, needs review/permission |
| Fiscal Data auctions `api.fiscaldata.treasury.gov` | US Treasury | https://fiscaldata.treasury.gov/about/ | calendar file | event tags | to confirm | to confirm | source label | documented | as published | unverified, needs review/permission |
| Federal Reserve FOMC calendar page | Federal Reserve Board | https://www.federalreserve.gov/disclaimer.htm | calendar file | event tags | to confirm | to confirm | source label | n/a | as published | unverified, needs review/permission |
| BLS release calendar `bls.gov/schedule/news_release/bls.ics` | BLS | https://www.bls.gov/bls/linksite.htm , https://www.bls.gov/developers/ | calendar file | event tags | to confirm | to confirm | source label | contact user agent required by the site | as published | unverified, needs review/permission |
| OKX public market data (spot candles, open-interest history, funding) | OKX | https://www.okx.com/help/terms-of-service (confirm API terms) | minutes–hours | OI shock, funding tails | unknown | unknown | link | documented per endpoint | per scan / daily | unverified, needs review/permission |
| Coinbase Exchange public candles | Coinbase | https://www.coinbase.com/legal/user_agreement , developer terms (confirm) | hours | return/volume | unknown | unknown | link | documented | daily | unverified, needs review/permission |
| DefiLlama stablecoins `stablecoins.llama.fi` | DefiLlama | https://defillama.com/ (confirm terms/licence) | 30 min | supply change | unknown | unknown | link | undocumented | daily aggregate | unverified, needs review/permission |
| SEC EDGAR atom feed + Form 4 XML | SEC | https://www.sec.gov/os/accessing-edgar-data , https://www.sec.gov/privacy | hours | transaction-code clusters | to confirm (fair-access policy applies) | to confirm | link to filing | 10 req/s and declared User-Agent per SEC policy | as filed | unverified, needs review/permission |
| DexScreener / RugCheck / Jupiter / Solana RPC (token tools) | various | each provider's terms | minutes | token reports | unknown | unknown | links | provider-specific | per scan | unverified, needs review/permission |
| X (shill-network, via the user's own Grok Bot X tools) | X Corp | https://developer.x.com/en/developer-terms | local only | coordination checks | unknown | unknown | post links | per user's access | per run | unverified, needs review/permission |

## Open questions for review
- Which providers allow showing raw values (prices, volumes, OI) in a public Page or screenshot, versus only derived flags and links?
- Whether OPRA or exchange redistribution rules reach delayed options data obtained through Cboe's or Nasdaq's websites.
- Whether a hosted or shared deployment (one feed many people read) is treated differently from each user running it.
- Attribution wording each provider requires, if any.
- A licensed real-time tier (review §07 blocker 4) is not built and needs its own register rows and contracts.
