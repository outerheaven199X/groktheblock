/* Grok The Block capability registry: the single list that drives navigation menus, search suggestions, Universe links,
   asset result destinations, feature visibility and status labels. Local data only; no network.
   Three independent status dimensions per capability (never collapsed into one "supported" badge):
     impl:   implemented | partial | planned
     data:   cached (actual cached real data) | synthetic | unavailable | insufficient   (resolved at runtime from loaded data)
     rights: verified | unverified | restricted   (for local research use; hosted redistribution is a separate gate) */
"use strict";
window.GTB_REGISTRY = (() => {
  const CATS = [
    { id: "crypto", name: "Crypto", families: ["Crypto"] },
    { id: "prediction", name: "Prediction Markets", families: ["Prediction", "Sports", "Events"] },
    { id: "stocks", name: "Stocks & Options", families: ["Equities"] },
    { id: "ratesfx", name: "Rates & FX", families: ["Rates", "FX"] },
    { id: "commodities", name: "Commodities", families: ["Metals", "Energy", "Agriculture"] },
    { id: "tcg", name: "TCGs", families: ["Cards"] },
    { id: "more", name: "More Markets", families: [] },
  ];
  // route.view: an existing renderer. route.src/types: filters applied by the Signals engine. route.uni: Universe ids for the market engine.
  const F = [
    // Crypto: existing v6 tools (embedded reports are synthetic SYN* examples)
    { id: "crypto.token", cat: "crypto", name: "Token Scanner", route: { view: "token" }, kinds: ["token"], impl: "implemented", rights: "verified", evidence: "holders, timing classes, timeline", filters: ["mint", "$TICKER"] },
    { id: "crypto.wallet", cat: "crypto", name: "Wallet Analysis", route: { view: "wallet" }, kinds: ["wallet"], impl: "implemented", rights: "verified", evidence: "entries, timing patterns", filters: ["address"] },
    { id: "crypto.shill", cat: "crypto", name: "Shill Network", route: { view: "shill" }, kinds: ["shill"], impl: "implemented", rights: "verified", evidence: "account graph", filters: ["token"] },
    { id: "crypto.copy", cat: "crypto", name: "Copy Network", route: { view: "copy" }, kinds: ["copy", "board"], impl: "implemented", rights: "verified", evidence: "copy-trade graph", filters: ["wallet"] },
    { id: "crypto.replay", cat: "crypto", name: "Rug Replay", route: { view: "replay" }, kinds: ["replay"], impl: "implemented", rights: "verified", evidence: "event timeline", filters: ["token"] },
    { id: "crypto.threats", cat: "crypto", name: "Threat Monitoring", route: { view: "threats" }, kinds: ["threats", "watch"], impl: "implemented", rights: "verified", evidence: "alert feed", filters: ["severity"] },
    { id: "crypto.board", cat: "crypto", name: "Leaderboard", route: { view: "board" }, kinds: ["board"], impl: "implemented", rights: "verified", evidence: "wallet ranking", filters: ["class"] },
    { id: "crypto.market", cat: "crypto", name: "Spot & Stablecoin Signals", route: { view: "signals", src: ["crypto", "stablecoins"] }, kinds: ["signals"], impl: "implemented", rights: "unverified", evidence: "return vs realized vol, supply change", filters: ["BTC", "ETH", "SOL"] },
    // Prediction markets: Signals engine filtered to Polymarket/Kalshi
    { id: "pm.odds", cat: "prediction", name: "Odds Moves", route: { view: "signals", src: ["polymarket", "kalshi"], types: ["ODDS_REPRICING"] }, kinds: ["signals"], impl: "implemented", rights: "unverified", evidence: "odds repricing vs window", filters: ["venue", "market"] },
    { id: "pm.volume", cat: "prediction", name: "Volume Signals", route: { view: "signals", src: ["polymarket", "kalshi"], types: ["VOLUME_SPIKE"] }, kinds: ["signals"], impl: "implemented", rights: "unverified", evidence: "24h volume vs prior average", filters: ["venue"] },
    { id: "pm.related", cat: "prediction", name: "Related Observations", route: { view: "signals", src: ["cross"], types: ["CONVERGENCE"] }, kinds: ["signals"], impl: "implemented", rights: "unverified", evidence: "co-timed observations, not causation", filters: ["topic"] },
    { id: "pm.context", cat: "prediction", name: "Event Calendar Context", route: { view: "signals", src: ["polymarket", "kalshi", "macro"], cal: true }, kinds: ["signals"], impl: "partial", rights: "verified", evidence: "Fed / BLS release calendar; settlement rules not parsed", filters: ["event"] },
    // Stocks & options
    { id: "eq.signals", cat: "stocks", name: "Equity Signals", route: { view: "signals", src: ["equities"] }, kinds: ["signals"], impl: "implemented", rights: "unverified", evidence: "daily return vs realized vol", filters: ["ticker"] },
    { id: "eq.options", cat: "stocks", name: "Options Activity", route: { view: "signals", src: ["options"] }, kinds: ["signals"], impl: "implemented", rights: "unverified", evidence: "volume vs open interest", filters: ["underlying"] },
    { id: "eq.sec", cat: "stocks", name: "SEC Filings", route: { view: "signals", src: ["sec"] }, kinds: ["signals"], impl: "implemented", rights: "verified", evidence: "EDGAR Form 4 / 8-K (needs SEC user agent)", filters: ["ticker"] },
    // Rates & FX
    { id: "rt.treasury", cat: "ratesfx", name: "Treasury Yield Shifts", route: { view: "signals", src: ["treasury"] }, kinds: ["signals"], impl: "implemented", rights: "verified", evidence: "yield move vs robust daily change, curve", filters: ["2Y", "10Y", "30Y", "2s10s"] },
    { id: "fx.rates", cat: "ratesfx", name: "FX Rates", route: { view: "market", uni: ["fx-majors"], types: ["MOVE_VS_REALIZED_VOL"] }, kinds: ["everything"], impl: "implemented", rights: "verified", evidence: "ECB reference rates, move vs realized vol", filters: ["EUR/USD", "pairs"] },
    { id: "fx.h10", cat: "ratesfx", name: "ECB/Fed Cross-check", route: { view: "market", uni: ["fx-majors", "fx-h10"], types: ["FIX_CROSSCHECK"] }, kinds: ["everything"], impl: "implemented", rights: "verified", evidence: "ECB fix vs Fed H.10 (FRED)", filters: ["EUR/USD"] },
    // Commodities
    { id: "cm.metals", cat: "commodities", name: "Metals", route: { view: "market", uni: ["gold", "silver", "pgm"] }, kinds: ["everything"], impl: "implemented", rights: "unverified", evidence: "ETF proxies (GLD, IAU, SLV, PPLT, PALL), not spot", filters: ["GLD", "SLV"] },
    { id: "cm.energy", cat: "commodities", name: "Energy", route: { view: "market", uni: ["crude", "natgas"] }, kinds: ["everything"], impl: "implemented", rights: "verified", evidence: "EIA spot series via FRED", filters: ["WTI", "Brent", "Henry Hub"] },
    { id: "cm.ag", cat: "commodities", name: "Agricultural Markets", route: { view: "market", uni: ["grains", "softs"] }, kinds: ["everything"], impl: "partial", rights: "verified", evidence: "CFTC positioning only; no ag price feed yet", filters: ["corn", "wheat", "coffee"] },
    { id: "cm.cot", cat: "commodities", name: "CFTC Positioning", route: { view: "market", uni: ["cot", "grains", "softs"], types: ["COT_POSITIONING_SHIFT"] }, kinds: ["everything"], impl: "implemented", rights: "verified", evidence: "weekly Commitments of Traders", filters: ["contract"] },
    // TCGs (Card Explorer browses the local artwork cache; the market tools carry the derived observations)
    { id: "tcg.explorer", cat: "tcg", name: "Card Explorer", route: { view: "tcg" }, kinds: [], impl: "implemented", rights: "restricted", evidence: "Scryfall printings + locally cached artwork; artwork rights BLOCKED for redistribution", filters: ["card", "set", "collector #"] },
    { id: "tcg.mtg", cat: "tcg", name: "Market Signals", route: { view: "market", uni: ["mtg"] }, kinds: ["everything"], impl: "implemented", rights: "unverified", evidence: "card- and printing-level anomalies from Scryfall daily prices (derived only)", filters: ["card"] },
    { id: "tcg.spread", cat: "tcg", name: "Cross-Venue Spreads", route: { view: "market", uni: ["mtg"], types: ["CROSS_VENUE_SPREAD"] }, kinds: ["everything"], impl: "implemented", rights: "unverified", evidence: "observed USD vs EUR price gap, not executable arbitrage", filters: ["card"] },
    { id: "tcg.history", cat: "tcg", name: "Price History", route: { view: "market", uni: ["mtg"], types: ["GUIDE_MOVE_VS_30D_MEDIAN"] }, kinds: ["everything"], impl: "partial", rights: "unverified", evidence: "collected daily snapshots and their dates; needs 14 before it can assess a move", filters: ["card"] },
    // More markets
    { id: "more.cs2", cat: "more", name: "CS2 Skins (experimental)", route: { view: "market", uni: ["cs2-skins"] }, kinds: ["everything"], impl: "partial", rights: "restricted", experimental: true, evidence: "undocumented Steam endpoint; derived numbers only", filters: ["skin", "case"] },
    { id: "more.prov", cat: "more", name: "Media Provenance", route: { view: "prov" }, kinds: ["provenance"], impl: "implemented", rights: "verified", evidence: "media integrity checks", filters: [] },
    { id: "more.all", cat: "more", name: "All Markets directory", route: { view: "universe" }, kinds: [], impl: "implemented", rights: "verified", evidence: "53 asset classes and their data status", filters: ["family", "status"], directory: true },
  ];
  const GLOBAL = [{ id: "home", name: "Home", route: { view: "home" } }, { id: "anomalies", name: "Anomalies", route: { view: "anomalies" } }];
  const byId = Object.fromEntries(F.map(f => [f.id, f]));
  // Universe id -> best capability (Universe tiles open the tool directly).
  const UNI_TOOL = { "fx-majors": "fx.rates", "fx-h10": "fx.h10", gold: "cm.metals", silver: "cm.metals", pgm: "cm.metals", crude: "cm.energy", natgas: "cm.energy", grains: "cm.ag", softs: "cm.ag", cot: "cm.cot", treasuries: "rt.treasury", "fed-bls": "pm.context", equities: "eq.signals", options: "eq.options", sec: "eq.sec", mtg: "tcg.mtg", "cs2-skins": "more.cs2", polymarket: "pm.odds", kalshi: "pm.odds", "prediction-markets": "pm.odds", "solana-tokens": "crypto.token", "crypto-spot": "crypto.market", stablecoins: "crypto.market", "crypto-majors": "crypto.market" };
  // Card games behind one adapter interface. Only active games are browsable; the rest are listed as unavailable, never supported.
  const TCG_GAMES = [
    { game: "mtg", name: "Magic: The Gathering", provider: "Scryfall", active: true },
    { game: "pokemon", name: "Pokémon TCG", provider: "TCGdex", active: false, reason: "artwork and price rights not cleared" },
    { game: "pokemon-scrydex", name: "Pokémon / Lorcana / One Piece", provider: "Scrydex", active: false, reason: "paid API; written redistribution permission required" },
  ];
  return { CATS, F, GLOBAL, byId, UNI_TOOL, TCG_GAMES };
})();
