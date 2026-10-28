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
        sp = settlement_spec(text)
        if sp and sp["referenceInstrument"] and sp["referenceInstrument"] in ENTITIES.get(entity, {}).get("instruments", []):
            return "SETTLES_ON_UNDERLYING"
        if sp and sp["settlementMetric"] == "FED_FUNDS_TARGET" and entity == "fed-policy":
            return "SAME_EVENT"  # the policy decision itself; not the 2Y yield
        if _LEVEL.search(text or ""):
            return "UNRESOLVED"  # a level/threshold question without an identifiable settlement variable (R5-04)
        return "SAME_EVENT"  # candidate; prediction questions are further split by settlement/outcome in convergence
    if source == "sec":
        return "DISCLOSURE_REACTION"
    return "UNRESOLVED"


_NUM = r"\$?\s*([\d][\d,]*(?:\.\d+)?)\s*(k|K|%|bps?)?"
_DATE = re.compile(r"\b(?:on|by|at|before|after|end of)\s+((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?|20\d\d|q[1-4](?:\s+20\d\d)?|(?:the\s+)?(?:year|month))", re.I)
_CCY = {"bitcoin": "BTC", "btc": "BTC", "ethereum": "ETH", "eth": "ETH", "ether": "ETH", "solana": "SOL", "sol": "SOL"}


def settlement_spec(text: str) -> dict | None:
    """R5-04: an EXPLICIT normalized settlement spec for a price/level prediction question, or None when the text doesn't
    identify one specific instrument or economic variable. Fields: settlementMetric, referenceInstrument (None for a
    variable with no listed instrument, e.g. the Fed funds target), unit, threshold, polarity, date. Generic
    "above $X" phrasing about a company forecast is NOT a share-price settlement."""
    t = (text or "").lower()
    pol = re.search(r"\b(above|over|at least|at or above|higher than|exceed|below|under|lower than|at or below)\b\s*" + _NUM, t)
    if not pol:
        return None
    polarity = "above" if pol.group(1) in ("above", "over", "at least", "at or above", "higher than", "exceed") else "below"
    num = float(pol.group(2).replace(",", "")) * (1000 if pol.group(3) in ("k", "K") else 1)
    dm = _DATE.search(text or "")
    base = {"threshold": num, "polarity": polarity, "date": dm.group(1) if dm else None}
    if re.search(r"\b(fed(?:eral)?[- ]funds|policy rate|fed(?:'s)? (?:target )?rate|interest rate target)\b", t):
        return dict(base, settlementMetric="FED_FUNDS_TARGET", referenceInstrument=None, unit="percent")
    m = re.search(r"\b(2|10|30)[- ]?(?:year|yr|y)\b[^?]*\byield\b|\byield\b[^?]*\b(2|10|30)[- ]?(?:year|yr|y)\b", t)
    if m:
        ten = m.group(1) or m.group(2)
        return dict(base, settlementMetric=f"UST_{ten}Y_YIELD", referenceInstrument=f"treasury:{ten}Y", unit="percent")
    m = re.search(r"\b(bitcoin|btc|ethereum|ether|eth|solana|sol)\b(?:'s)?\s*(?:price\s*)?(?:be|close|trade|hit|reach|is)?\b", t)
    if m and re.search(r"\$|\bprice\b|\busd\b|\b\d+k\b", t) and pol.group(2):
        c = _CCY[m.group(1)]
        return dict(base, settlementMetric=f"{c}_USD_PRICE", referenceInstrument=f"crypto:{c}", unit="USD")
    m = re.search(r"\b([a-z][a-z .&]+?)\s+(?:stock|share price|shares)\b|\$([a-z]{1,5})\b\s+(?:close|price)", t)
    if m and re.search(r"\b(stock|share price|shares|close above|close below)\b", t):
        who = (m.group(1) or m.group(2) or "").strip()
        for ent, v in ENTITIES.items():
            if who and (who in v["aliases"] or who == ent):
                eq = [i for i in v["instruments"] if i.startswith("equities:")]
                if eq:
                    return dict(base, settlementMetric=f"{eq[0].split(':')[1]}_SHARE_PRICE", referenceInstrument=eq[0], unit="USD")
    return None


def settlement_instrument(entity: str, text: str) -> str | None:
    """The listed instrument a price-level contract settles on, ONLY from an explicit settlement spec (no guessing)."""
    sp = settlement_spec(text)
    return sp["referenceInstrument"] if sp else None


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
