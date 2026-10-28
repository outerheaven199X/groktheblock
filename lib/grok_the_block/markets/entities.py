"""Canonical entities, aliases and causal families for dependency-aware convergence.

Only explicit aliases resolve. Generic themes (crypto, AI, elections, stocks) are NOT entities and can
never create convergence by themselves. A person is not their company ("Musk" does not resolve to TSLA).
"""
from __future__ import annotations

import re

# source -> causal family. One family contributes one effective observation.
FAMILY = {"polymarket": "prediction", "kalshi": "prediction", "equities": "equity", "options": "equity",
          "treasury": "rates", "macro": "rates", "crypto": "crypto", "stablecoins": "crypto", "solana": "crypto",
          "sec": "disclosure"}
FAMILY_LABEL = {"prediction": "Prediction markets", "equity": "Equities & options", "rates": "Rates, FX & macro",
                "crypto": "Crypto (spot, perps, on-chain)", "disclosure": "Primary disclosures"}

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
