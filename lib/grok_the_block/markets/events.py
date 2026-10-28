"""Scheduled-event calendar: tags signals that coincide with expected volatility.

Sources (official where available; see data/event-calendar.json "sources"):
- FOMC meetings: federalreserve.gov FOMC calendar page.
- CPI and Employment Situation (NFP): BLS release calendar (bls.ics).
- Treasury note/bond auctions: fiscaldata.treasury.gov auctions_query.
- Monthly equity options expiration: computed (third Friday; Thursday if that Friday is an NYSE holiday).
- Earnings: NOT INCLUDED (no free official schedule). Listed tickers are never tagged for earnings.
A tag means "this move coincided with a scheduled event", which usually explains it. It is context, not a finding.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import timebase as T

CAL_PATH = Path(__file__).resolve().parents[3] / "data" / "event-calendar.json"
# Which causal families each event type is expected to move.
AFFECTS = {"FOMC": {"prediction", "equity", "rates", "crypto"}, "CPI": {"prediction", "equity", "rates", "crypto"},
           "NFP": {"prediction", "equity", "rates", "crypto"}, "AUCTION": {"rates"}, "OPEX": {"equity"}}


def third_friday(y: int, m: int) -> date:
    d = date(y, m, 15)
    d += timedelta(days=(4 - d.weekday()) % 7)
    return d - timedelta(days=1) if not T.is_session(d) else d


def load(path: Path = CAL_PATH) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {"events": [], "sources": {}, "notIncluded": []}


PHASES = ("PRE_EVENT_POSITIONING", "RELEASE_REACTION", "POST_EVENT_CONTEXT", "UNRELATED")
REACTION_S = 60 * 60       # 0–60 min after a known-time release = RELEASE_REACTION
PRE_S = 24 * 3600          # up to 24h before = PRE_EVENT_POSITIONING (context; never a cap)
POST_S = 30 * 3600         # after the reaction window up to 30h = POST_EVENT_CONTEXT
_TENOR = re.compile(r"(\d+)-(Year|Month|Week)", re.I)


def normalize(e: dict) -> dict:
    """Add eventId, timeExact and tenor to a stored calendar entry (older files lack them)."""
    e = dict(e)
    if e["type"] == "AUCTION":
        e.setdefault("timeExact", False)   # fiscaldata gives the auction DATE only; no time is manufactured
        m = _TENOR.search(e.get("label", ""))
        e.setdefault("tenor", (m.group(1) + {"year": "Y", "month": "M", "week": "W"}[m.group(2).lower()]) if m else None)
    else:
        e.setdefault("timeExact", e["type"] in ("FOMC", "CPI", "NFP", "OPEX"))
    e.setdefault("eventId", f"{e['type']}:{T.datetime.fromtimestamp(e['ts'], T.NY).date().isoformat()}:{(e.get('tenor') or '')}")
    return e


def _tenors(instrument: str | None) -> set[str]:
    tick = (instrument or "").split(":")[-1]
    return {"2s10s": {"2Y", "10Y"}}.get(tick, {tick} if tick else set())


def events_near(ts: int, families: set[str], cal: dict, before_h: float = 24, after_h: float = 30, *, window_start: int | None = None,
                granularity: str = "intraday", instrument: str | None = None) -> list[dict]:
    """Calendar relationships for one observation, each with eventId, scheduled time, phase and rationale.

    ts = when the move was observable (availability); window_start = start of the measured move.
    - PRE_EVENT_POSITIONING: the release is still in the future at ts (up to 24h). Context only; never explains the move.
    - RELEASE_REACTION: a known-time release at or before ts, within 0–60 min, observed intraday.
    - POST_EVENT_CONTEXT: later than the reaction window (up to 30h), or any daily/approximate observation.
    - Treasury auctions match only the same tenor and are date-only, so they are never RELEASE_REACTION."""
    out = []
    ws = window_start if window_start is not None else ts
    for raw in cal.get("events", []):
        if not (AFFECTS.get(raw["type"], set()) & families):
            continue
        if not (raw["ts"] - before_h * 3600 <= ts <= raw["ts"] + after_h * 3600):
            continue
        e = normalize(raw)
        if e["type"] == "AUCTION":
            if not (e.get("tenor") and e["tenor"] in _tenors(instrument)):
                continue
            same_day = T.datetime.fromtimestamp(ts, T.NY).date() == T.datetime.fromtimestamp(e["ts"], T.NY).date()
            phase, why = ("POST_EVENT_CONTEXT", f"same-day {e['tenor']} auction; dataset has the date only, so timing can't be checked") if same_day \
                else ("UNRELATED", "different day")
            if phase == "UNRELATED":
                continue
        elif e["ts"] > ts:
            phase, why = "PRE_EVENT_POSITIONING", f"observed {(e['ts'] - ts) / 3600:.1f}h BEFORE the scheduled release; the release can't explain it"
        elif e["timeExact"] and granularity == "intraday" and ts - e["ts"] <= REACTION_S and ws <= e["ts"] + REACTION_S:
            phase, why = "RELEASE_REACTION", f"observed {(ts - e['ts']) / 60:.0f} min after a known-time release"
        else:
            phase, why = "POST_EVENT_CONTEXT", (f"{(ts - e['ts']) / 3600:.1f}h after the release" + ("; daily/approximate timing, context only" if granularity != "intraday" else ""))
        out.append({"eventId": e["eventId"], "type": e["type"], "label": e["label"], "time": T.iso(e["ts"]), "timeExact": e["timeExact"],
                    "tenor": e.get("tenor"), "phase": phase, "rationale": why, "availableAtObservation": e["ts"] <= ts, "source": e.get("source")})
    return out


def build(fetch_text, fetch_json, years=(2025, 2026, 2027)) -> dict:
    """Build the calendar from official sources. fetch_* return None on failure (then that type is listed as missing)."""
    import re
    ev, missing = [], []
    html = fetch_text("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
    if html:
        heads = [(m.start(), int(m.group(1))) for m in re.finditer(r"(\d{4}) FOMC Meetings</a></h4>", html)]
        months = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])}
        for m in re.finditer(r"fomc-meeting__month[^>]*><strong>(\w+)</strong>.*?fomc-meeting__date[^>]*>([^<]*)<", html, re.S):
            prior = [y for p, y in heads if p < m.start()]
            yr = prior[-1] if prior else None
            mon = months.get(m.group(1).split("/")[-1])
            days = re.findall(r"\d+", m.group(2))
            if yr in years and mon and days and "notation" not in m.group(2):
                d = date(yr, mon, int(days[-1]))
                ev.append({"type": "FOMC", "label": f"FOMC decision {d}", "ts": T.ny_ts(d, 14), "source": "federalreserve.gov"})
    else:
        missing.append("FOMC (federalreserve.gov unreachable)")
    ics = fetch_text("https://www.bls.gov/schedule/news_release/bls.ics")
    if ics:
        for blk in ics.split("BEGIN:VEVENT")[1:]:
            s = re.search(r"SUMMARY:(.*)", blk); d = re.search(r"DTSTART;TZID=US-Eastern:(\d{8})T(\d{2})(\d{2})", blk)
            if not s or not d:
                continue
            typ = {"Consumer Price Index": "CPI", "Employment Situation": "NFP"}.get(s.group(1).strip())
            dd = datetime.strptime(d.group(1), "%Y%m%d").date()
            if typ and dd.year in years:
                ev.append({"type": typ, "label": f"{s.group(1).strip()} {dd}", "ts": T.ny_ts(dd, int(d.group(2)), int(d.group(3))), "source": "bls.gov"})
    else:
        missing.append("CPI/NFP (bls.gov calendar unreachable; BLS asks for a contact User-Agent)")
    j = fetch_json("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
                   f"?filter=auction_date:gte:{years[0]}-01-01,security_type:in:(Note,Bond)&fields=auction_date,security_type,security_term&page%5Bsize%5D=1000")
    if j and j.get("data"):
        for a in j["data"]:
            dd = date.fromisoformat(a["auction_date"])
            ev.append(normalize({"type": "AUCTION", "label": f"{a['security_term']} {a['security_type']} auction {dd}", "ts": T.ny_ts(dd, 0), "timeExact": False, "source": "fiscaldata.treasury.gov"}))
    else:
        missing.append("Treasury auctions (fiscaldata unreachable)")
    for y in years:
        for m in range(1, 13):
            d = third_friday(y, m)
            ev.append({"type": "OPEX", "label": f"Monthly options expiration {d}", "ts": T.ny_ts(d, 16), "source": "computed (third Friday rule)"})
    ev.sort(key=lambda e: e["ts"])
    return {"builtAt": T.iso(T.now()), "events": ev, "missing": missing,
            "sources": {"FOMC": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", "CPI/NFP": "https://www.bls.gov/schedule/news_release/bls.ics",
                        "AUCTION": "https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/", "OPEX": "computed: third Friday, NYSE-holiday aware"},
            "notIncluded": ["Earnings dates: no free official schedule; listed tickers are not tagged for earnings.", "PCE (BEA) and political milestones: not yet included."]}
