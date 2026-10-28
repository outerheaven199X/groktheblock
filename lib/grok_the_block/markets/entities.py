"""Canonical entities, aliases and causal families for dependency-aware convergence.

Only explicit aliases resolve. Generic themes (crypto, AI, elections, stocks) are NOT entities and can
never create convergence by themselves. A person is not their company ("Musk" does not resolve to TSLA).
"""
from __future__ import annotations

import re

# source -> causal family. One family contributes one effective observation.
FAMILY = {"polymarket": "prediction", "kalshi": "prediction", "equities": "equity", "options": "equity",
          "treasury": "rates", "macro": "macro", "crypto": "crypto", "stablecoins": "crypto", "solana": "crypto",
          "sec": "disclosure"}
FAMILY_LABEL = {"prediction": "Prediction markets", "equity": "Equities & options", "rates": "Rates",
                "fx": "FX", "commodities": "Commodities", "volatility": "Volatility",
                "crypto": "Crypto (spot, perps, on-chain)", "disclosure": "Primary disclosures"}
MACRO_FAMILY = {"^VIX": "volatility", "DX-Y.NYB": "fx", "EURUSD=X": "fx", "USDJPY=X": "fx", "GC=F": "commodities", "CL=F": "commodities"}


def family_of(source: str, instrument: str | None = None) -> str | None:
    """Causal family; macro splits into FX / commodities / volatility (more families never imply more independence)."""
    if source == "macro" and instrument:
        return MACRO_FAMILY.get(instrument.split(":")[-1], "macro")
    return FAMILY.get(source)


# Typed relations between an observation and an entity (P1.04). Only SAME_UNDERLYING, SAME_EVENT and the listed
# event-linked instruments count toward CONVERGENCE; MACRO_EXPOSURE / UNRESOLVED produce RELATED_ACTIVITY only.
REL = ("SAME_UNDERLYING", "DIRECT_PROXY", "SAME_EVENT", "SETTLES_ON_UNDERLYING", "DISCLOSURE_REACTION", "MACRO_EXPOSURE", "UNRESOLVED")
# R4-05: a prediction contract that settles on the level of a listed instrument ("10-year yield above 4.5%", "BTC above
# $100k") carries the same public price information as that instrument: it joins the instrument's dependency group.
_LEVEL = re.compile(r"\b(above|below|over|under|at least|at or above|higher than|lower than|between)\b\s*\$?\d|\b(yield|price|close)\b[^?]*\b(above|below|over|under)\b", re.I)
# instrument -> (entity, relation). Anything not listed but matched by alias is UNRESOLVED (non-prediction) or
# SAME_EVENT-candidate (prediction market whose text names the entity's event).
LINKS = {
    "treasury:2Y": [("fed-policy", "SAME_EVENT"), ("us-treasuries", "SAME_UNDERLYING")],
    "treasury:10Y": [("us-treasuries", "SAME_UNDERLYING"), ("fed-policy", "MACRO_EXPOSURE")],
    "treasury:30Y": [("us-treasuries", "SAME_UNDERLYING"), ("fed-policy", "MACRO_EXPOSURE")],
    "treasury:2s10s": [("us-treasuries", "SAME_UNDERLYING"), ("fed-policy", "MACRO_EXPOSURE")],
    "equities:TLT": [("us-treasuries", "DIRECT_PROXY"), ("fed-policy", "MACRO_EXPOSURE")],
    "options:TLT": [("us-treasuries", "DIRECT_PROXY"), ("fed-policy", "MACRO_EXPOSURE")],
    "crypto:BTC": [("bitcoin", "SAME_UNDERLYING")], "crypto:ETH": [("ethereum", "SAME_UNDERLYING")], "crypto:SOL": [("solana", "SAME_UNDERLYING")],
    "equities:MSTR": [("microstrategy", "SAME_UNDERLYING"), ("bitcoin", "MACRO_EXPOSURE")],
    "equities:COIN": [("coinbase", "SAME_UNDERLYING"), ("bitcoin", "MACRO_EXPOSURE")],
    "options:COIN": [("coinbase", "SAME_UNDERLYING"), ("bitcoin", "MACRO_EXPOSURE")],
    "macro:CL=F": [("oil", "SAME_UNDERLYING")], "equities:USO": [("oil", "DIRECT_PROXY")], "equities:XLE": [("oil", "MACRO_EXPOSURE")],
    "macro:GC=F": [("gold", "SAME_UNDERLYING")], "equities:GLD": [("gold", "DIRECT_PROXY")],
    "macro:DX-Y.NYB": [("us-dollar", "SAME_UNDERLYING")], "equities:UUP": [("us-dollar", "DIRECT_PROXY")],
    "macro:USDJPY=X": [("yen", "SAME_UNDERLYING")], "macro:EURUSD=X": [("euro", "SAME_UNDERLYING")],
    "macro:^VIX": [("volatility", "SAME_UNDERLYING")],
}
# Mechanical dependence: these instruments (or an issuer's filing and its own stock/options) are ONE piece of evidence.
DEPENDENT_GROUPS = [{"macro:CL=F", "equities:USO"}, {"macro:GC=F", "equities:GLD"}, {"macro:DX-Y.NYB", "equities:UUP"},
                    {"treasury:10Y", "treasury:30Y", "equities:TLT", "options:TLT", "treasury:2s10s"},
                    {"crypto:BTC", "equities:MSTR"}, {"equities:SPY", "options:SPY"}, {"equities:QQQ", "options:QQQ"}]
COUNTING = {"SAME_UNDERLYING", "SAME_EVENT", "DIRECT_PROXY", "SETTLES_ON_UNDERLYING"}  # SETTLES_ON_UNDERLYING counts only inside its instrument's group


def relation(instrument: str | None, entity: str, source: str, text: str = "") -> str:
    """Typed relation of one observation to an entity."""
    if instrument:
        for e, r in LINKS.get(instrument, []):
            if e == entity:
                return r
        if instrument in ENTITIES.get(entity, {}).get("instruments", []):
            return "SAME_UNDERLYING"
        tick = instrument.split(":", 1)[-1]
        if source in ("equities", "options") and f"equities:{tick}" in ENTITIES.get(entity, {}).get("instruments", []):
            return "SAME_UNDERLYING"
    if source in ("polymarket", "kalshi"):
        if _LEVEL.search(text or "") and ENTITIES.get(entity, {}).get("instruments"):
            return "SETTLES_ON_UNDERLYING"
        return "SAME_EVENT"  # candidate; prediction questions are further split by settlement/outcome in convergence
    if source == "sec":
        return "DISCLOSURE_REACTION"
    return "UNRESOLVED"


def settlement_instrument(entity: str, text: str) -> str | None:
    """The listed instrument a price-level contract settles on (tenor words for Treasuries, else the entity's first)."""
    m = re.search(r"\b(2|10|30)[- ]?(?:year|yr|y)\b", (text or "").lower())
    if m and f"treasury:{m.group(1)}Y" in ENTITIES.get(entity, {}).get("instruments", []):
        return f"treasury:{m.group(1)}Y"
    ins = ENTITIES.get(entity, {}).get("instruments") or []
    return ins[0] if ins else None


def dependency_group(instrument: str | None, source: str, subject_id: str | None = None) -> str:
    """Observations sharing a group id are mechanically linked and count once."""
    if not instrument:
        return f"{source}:{subject_id}"
    tick = instrument.split(":", 1)[-1]
    for i, g in enumerate(DEPENDENT_GROUPS):
        if instrument in g:
            return f"dep{i}"
    if source in ("equities", "options", "sec"):
        return f"issuer:{tick}"  # a filing, its stock and its options are one disclosure-reaction chain
    return instrument

# canonical id -> aliases (case-insensitive word match), instrument ids (exact), related instruments for divergence
ENTITIES = {
    "fed-policy": {"aliases": ["fed", "fomc", "federal reserve", "fed funds", "rate cut", "rate cuts", "rate hike", "powell", "interest rates"],
                   "instruments": ["treasury:2Y", "equities:TLT", "options:TLT"], "related": ["treasury:2Y", "equities:TLT"]},
    "inflation": {"aliases": ["cpi", "inflation", "pce"], "instruments": [], "related": ["treasury:2Y", "macro:GC=F"]},
    "us-treasuries": {"aliases": ["treasury yield", "10-year yield", "2-year yield", "treasuries"],
                      "instruments": ["treasury:2Y", "treasury:10Y", "treasury:30Y", "treasury:2s10s", "equities:TLT", "options:TLT"],
                      "related": ["treasury:10Y", "equities:TLT"]},
    "bitcoin": {"aliases": ["bitcoin", "btc"], "instruments": ["crypto:BTC", "equities:COIN", "equities:MSTR", "options:COIN"],
                "related": ["crypto:BTC", "equities:COIN", "equities:MSTR"]},
    "ethereum": {"aliases": ["ethereum", "ether"], "instruments": ["crypto:ETH"], "related": ["crypto:ETH"]},
    "solana": {"aliases": ["solana"], "instruments": ["crypto:SOL"], "related": ["crypto:SOL"]},
    "oil": {"aliases": ["oil", "crude", "wti", "brent", "opec"], "instruments": ["macro:CL=F", "equities:USO", "equities:XLE"],
            "related": ["macro:CL=F", "equities:USO"]},
    "gold": {"aliases": ["gold"], "instruments": ["macro:GC=F", "equities:GLD"], "related": ["macro:GC=F", "equities:GLD"]},
    "us-dollar": {"aliases": ["us dollar", "dollar index", "dxy"], "instruments": ["macro:DX-Y.NYB", "equities:UUP"], "related": ["macro:DX-Y.NYB"]},
    "yen": {"aliases": ["yen", "boj", "bank of japan"], "instruments": ["macro:USDJPY=X"], "related": ["macro:USDJPY=X"]},
    "euro": {"aliases": ["euro", "ecb"], "instruments": ["macro:EURUSD=X"], "related": ["macro:EURUSD=X"]},
    "volatility": {"aliases": ["vix", "volatility index"], "instruments": ["macro:^VIX"], "related": ["macro:^VIX", "equities:SPY"]},
    "sp500": {"aliases": ["s&p 500", "s&p500", "sp500", "spx"], "instruments": ["equities:SPY", "options:SPY"], "related": ["equities:SPY"]},
    "nasdaq-100": {"aliases": ["nasdaq-100", "nasdaq 100", "ndx"], "instruments": ["equities:QQQ", "options:QQQ"], "related": ["equities:QQQ"]},
    "nvidia": {"aliases": ["nvidia"], "instruments": ["equities:NVDA", "options:NVDA"], "related": ["equities:NVDA"]},
    "tesla": {"aliases": ["tesla"], "instruments": ["equities:TSLA", "options:TSLA"], "related": ["equities:TSLA"]},
    "apple": {"aliases": ["apple inc", "iphone maker"], "instruments": ["equities:AAPL"], "related": ["equities:AAPL"]},
    "microsoft": {"aliases": ["microsoft"], "instruments": ["equities:MSFT"], "related": ["equities:MSFT"]},
    "coinbase": {"aliases": ["coinbase"], "instruments": ["equities:COIN", "options:COIN"], "related": ["equities:COIN"]},
    "microstrategy": {"aliases": ["microstrategy", "strategy inc"], "instruments": ["equities:MSTR"], "related": ["equities:MSTR"]},
    "tether": {"aliases": ["tether", "usdt"], "instruments": ["stablecoins:USDT"], "related": []},
    "usdc": {"aliases": ["usdc", "circle"], "instruments": ["stablecoins:USDC"], "related": []},
}
GENERIC = {"crypto", "ai", "elections", "election", "stocks", "markets", "token", "recession"}
_RX = {k: re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(a) for a in v["aliases"]) + r")(?![a-z0-9])", re.I)
       for k, v in ENTITIES.items() if v["aliases"]}
_BY_INSTRUMENT: dict[str, list[str]] = {}
for _k, _v in ENTITIES.items():
    for _i in _v["instruments"]:
        _BY_INSTRUMENT.setdefault(_i, []).append(_k)


def resolve(source: str, instrument: str | None, text: str) -> list[str]:
    """Canonical entities for one observation: exact instrument match first, then explicit aliases in the title."""
    out = []
    if instrument:
        out += _BY_INSTRUMENT.get(f"{source}:{instrument}", [])
    for k, rx in _RX.items():
        if k not in out and rx.search(text or ""):
            out.append(k)
    return out
