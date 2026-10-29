"""Keyless, terms-checked sources for the everything-markets slice. Parsers are pure; fetchers go through
markets.http (per-host throttle, retries, cache under ./cache which is gitignored).

Terms summary (see docs/everything/UNIVERSE.md for URLs):
- ECB reference rates: free reuse with "Source: ECB statistics" (raw values redistributable).
- Frankfurter v1: serves the ECB reference rates (used when the ECB host is unreachable); still ECB data.
- FRED fredgraph CSV: only public-domain US-government series are used here (H.10 FX, EIA spot energy).
- Nasdaq quote history: unofficial endpoint, no published terms -> derived signals + link only, never price tables.
- CFTC COT (publicreporting.cftc.gov, Socrata): US-government public data.
- Scryfall: free, must add value, no repackaging; prices are TCGplayer/Cardmarket -> derived signals + link only.
- Steam Community Market priceoverview: undocumented, not covered by the Steam Web API terms -> derived only, roadmap.
"""
from __future__ import annotations

import csv
import io
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

from ..markets import http as H
from ..markets.sources import parse_nasdaq_hist  # noqa: F401  (re-exported for metal ETFs)

UA = {"User-Agent": "GrokTheBlock/0.6 (local research preview)", "Accept": "application/json;q=0.9,*/*;q=0.8"}
FX_CCYS = ["USD", "JPY", "GBP", "CHF", "CNY", "AUD", "CAD", "MXN", "TRY", "INR", "BRL", "ZAR", "SEK", "NOK", "KRW", "PLN"]
METAL_ETFS = {"GLD": "Gold (SPDR Gold Shares)", "IAU": "Gold (iShares Gold Trust)", "SLV": "Silver (iShares Silver Trust)",
              "PPLT": "Platinum (abrdn Platinum)", "PALL": "Palladium (abrdn Palladium)"}
ENERGY_FRED = {"DCOILWTICO": "WTI crude oil spot (EIA via FRED)", "DCOILBRENTEU": "Brent crude oil spot (EIA via FRED)",
               "DHHNGSP": "Henry Hub natural gas spot (EIA via FRED)"}
FRED_FX = {"DEXUSEU": ("USD", "USD per EUR"), "DEXJPUS": ("JPY", "JPY per USD"), "DEXUSUK": ("GBP", "USD per GBP")}
COT_MARKETS = {"GOLD - COMMODITY EXCHANGE INC.": "Gold futures (COMEX)", "SILVER - COMMODITY EXCHANGE INC.": "Silver futures (COMEX)",
               "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE": "WTI crude futures (NYMEX)",
               "WHEAT-SRW - CHICAGO BOARD OF TRADE": "SRW wheat futures (CBOT)", "CORN - CHICAGO BOARD OF TRADE": "Corn futures (CBOT)",
               "SOYBEANS - CHICAGO BOARD OF TRADE": "Soybean futures (CBOT)", "COFFEE C - ICE FUTURES U.S.": "Coffee C futures (ICE US)",
               "COCOA - ICE FUTURES U.S.": "Cocoa futures (ICE US)"}


def _day(s: str) -> int:
    return int(datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


# ---------------- FX ----------------
def parse_ecb_csv(txt: str) -> dict[str, list[tuple[int, float]]] | None:
    """ECB SDMX csvdata (KEY,FREQ,CURRENCY,CURRENCY_DENOM,...,TIME_PERIOD,OBS_VALUE) -> {ccy: [(ts, units per EUR)]}."""
    if not txt or "TIME_PERIOD" not in txt[:2000]:
        return None
    out: dict[str, list] = {}
    for r in csv.DictReader(io.StringIO(txt)):
        try:
            v = float(r["OBS_VALUE"])
        except (KeyError, ValueError, TypeError):
            continue
        out.setdefault(r.get("CURRENCY", "?"), []).append((_day(r["TIME_PERIOD"]), v))
    for k in out:
        out[k].sort()
    return out or None


def parse_frankfurter(j) -> dict[str, list[tuple[int, float]]] | None:
    """Frankfurter v1 time series (base EUR; ECB reference rates) -> same shape as parse_ecb_csv."""
    rates = (j or {}).get("rates") if isinstance(j, dict) else None
    if not isinstance(rates, dict) or (j.get("base") not in (None, "EUR")):
        return None
    out: dict[str, list] = {}
    for d, m in sorted(rates.items()):
        if not isinstance(m, dict):
            continue
        for c, v in m.items():
            if isinstance(v, (int, float)) and v > 0:
                out.setdefault(c, []).append((_day(d), float(v)))
    return out or None


def parse_fred_csv(txt: str) -> list[tuple[int, float]] | None:
    """fredgraph.csv (observation_date,SERIES) -> [(ts, value)]; '.' (no observation) rows are skipped."""
    if not txt or "," not in txt.splitlines()[0]:
        return None
    rows = list(csv.reader(io.StringIO(txt)))
    out = []
    for r in rows[1:]:
        if len(r) < 2 or not re.match(r"\d{4}-\d{2}-\d{2}", r[0]):
            continue
        try:
            out.append((_day(r[0]), float(r[1])))
        except ValueError:
            continue
    return out or None


def ecb_fx(start: str = "2025-06-01") -> tuple[dict | None, str | None]:
    """Primary: ECB SDMX. Fallback: Frankfurter (same ECB reference rates). Returns (series, via)."""
    ccys = "+".join(FX_CCYS)
    t = H.get(f"https://data-api.ecb.europa.eu/service/data/EXR/D.{ccys}.EUR.SP00.A?startPeriod={start}&format=csvdata",
              "ecb", as_text=True, max_age=6 * 3600, timeout=40, headers=UA)
    s = parse_ecb_csv(t) if t else None
    if s:
        return s, "ECB SDMX (data-api.ecb.europa.eu)"
    j = H.get(f"https://api.frankfurter.dev/v1/{start}..?base=EUR&symbols={','.join(FX_CCYS)}", "frankfurter", max_age=6 * 3600, headers=UA)
    s = parse_frankfurter(j)
    return (s, "Frankfurter v1 (ECB reference rates; ECB host unreachable from this machine)") if s else (None, None)


def fred(series: str) -> list[tuple[int, float]] | None:
    t = H.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}", "fred", as_text=True, max_age=6 * 3600, timeout=60, headers=UA)
    return parse_fred_csv(t) if t else None


def nasdaq_etf(sym: str, start: str = "2025-06-01") -> list[tuple] | None:
    j = H.get(f"https://api.nasdaq.com/api/quote/{sym}/historical?assetclass=etf&fromdate={start}&limit=400", "nasdaq", max_age=6 * 3600)
    return parse_nasdaq_hist(j)


# ---------------- CFTC COT ----------------
def parse_cot(rows) -> dict[str, list[dict]] | None:
    """Legacy futures-only rows -> {market: [{ts, mm_long, mm_short, oi}]} oldest first (non-commercial = speculators)."""
    if not isinstance(rows, list):
        return None
    out: dict[str, list] = {}
    for r in rows:
        try:
            out.setdefault(r["market_and_exchange_names"], []).append({
                "ts": _day(r["report_date_as_yyyy_mm_dd"]), "long": float(r["noncomm_positions_long_all"]),
                "short": float(r["noncomm_positions_short_all"]), "oi": float(r["open_interest_all"])})
        except (KeyError, ValueError, TypeError):
            continue
    for k in out:
        out[k].sort(key=lambda x: x["ts"])
    return out or None


def cot(weeks: int = 80) -> dict | None:
    names = ",".join("'" + n.replace("'", "''") + "'" for n in COT_MARKETS)
    url = ("https://publicreporting.cftc.gov/resource/6dca-aqww.json?$select=market_and_exchange_names,report_date_as_yyyy_mm_dd,"
           "noncomm_positions_long_all,noncomm_positions_short_all,open_interest_all"
           f"&$where=market_and_exchange_names in({quote(names)})&$order=report_date_as_yyyy_mm_dd DESC&$limit={weeks * len(COT_MARKETS)}")
    return parse_cot(H.get(url.replace(" ", "%20"), "cftc", max_age=12 * 3600, timeout=60, headers=UA))


# ---------------- collectibles ----------------
def parse_scryfall_card(c: dict) -> dict | None:
    """Keep only identity + the two venue prices we derive signals from (never re-published as a table)."""
    if not isinstance(c, dict) or c.get("object") != "card":
        return None
    p = c.get("prices") or {}
    f = lambda k: float(p[k]) if p.get(k) not in (None, "") else None  # noqa: E731
    return {"id": c.get("id"), "name": c.get("name"), "set": c.get("set"), "set_name": c.get("set_name"),
            "usd": f("usd"), "eur": f("eur"), "usd_foil": f("usd_foil"), "url": c.get("scryfall_uri", "").split("?")[0]}


SCRYFALL_WATCH = ["Black Lotus", "Mox Sapphire", "Ancestral Recall", "Time Walk", "Timetwister", "Underground Sea", "Volcanic Island",
                  "Gaea's Cradle", "The One Ring", "Sheoldred, the Apocalypse", "Ragavan, Nimble Pilferer", "Orcish Bowmasters",
                  "Mana Crypt", "Jeweled Lotus", "Force of Will", "Wrenn and Six", "Mox Diamond", "Cyclonic Rift", "Rhystic Study",
                  "Dockside Extortionist", "Smothering Tithe", "Fierce Guardianship", "Imperial Seal", "Grim Monolith"]


def scryfall_snapshot(names=SCRYFALL_WATCH) -> list[dict]:
    """Cheapest-printing price per watched card via /cards/named (Scryfall asks for 50-100 ms between requests; we wait 150 ms)."""
    out = []
    for n in names:
        j = H.get(f"https://api.scryfall.com/cards/named?exact={quote(n)}", "scryfall", max_age=20 * 3600, headers=UA)
        c = parse_scryfall_card(j) if j else None
        if c:
            out.append(c)
        time.sleep(0.15)
    return out


def parse_steam_price(s: str | None) -> float | None:
    if not s:
        return None
    m = re.search(r"[\d.,]+", s)
    return float(m.group(0).replace(",", "")) if m else None


def parse_steam_overview(j) -> dict | None:
    if not isinstance(j, dict) or not j.get("success"):
        return None
    vol = j.get("volume")
    return {"lowest": parse_steam_price(j.get("lowest_price")), "median": parse_steam_price(j.get("median_price")),
            "volume24h": int(vol.replace(",", "")) if isinstance(vol, str) and vol.replace(",", "").isdigit() else 0}


STEAM_WATCH = ["AK-47 | Redline (Field-Tested)", "AWP | Asiimov (Field-Tested)", "AK-47 | Vulcan (Field-Tested)", "M4A4 | Howl (Field-Tested)",
               "Operation Breakout Weapon Case", "Kilowatt Case", "Revolution Case", "Sticker | Natus Vincere | Paris 2023",
               "Desert Eagle | Blaze (Factory New)", "USP-S | Kill Confirmed (Field-Tested)"]


def steam_snapshot(names=STEAM_WATCH, gap_s: float = 4.0) -> list[dict]:
    """~15 req/min, well under the commonly reported ~20/min per IP. Raw responses stay in ./cache (gitignored)."""
    out = []
    for n in names:
        j = H.get(f"https://steamcommunity.com/market/priceoverview/?appid=730&currency=1&market_hash_name={quote(n)}", "steam",
                  max_age=20 * 3600, headers=UA)
        o = parse_steam_overview(j)
        if o:
            o.update(name=n, url=f"https://steamcommunity.com/market/listings/730/{quote(n)}")
            out.append(o)
        time.sleep(gap_s)
    return out
