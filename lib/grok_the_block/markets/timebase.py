"""Time, trading calendars and source-health/freshness policy.

Every observation carries: eventTime (when it happened at the venue, or the close/observation it
describes), availableTime (when the provider made it available to us, best estimate), ingestTime
(when this run read it), validAsOf (the latest moment the value describes) and a source status.

Holiday lists are curated from the NYSE holiday page and SIFMA's recommended bond-market closures
(Columbus Day and Veterans Day added for Treasuries). Verify each year; see docs/PROVIDER-RIGHTS.md.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
NYSE_HOLIDAYS = {  # source: NYSE "Holidays & Trading Hours" (curated, verify annually)
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01",
    "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26",
    "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25",
    "2027-12-24",
}
BOND_EXTRA = {"2025-10-13", "2025-11-11", "2026-10-12", "2026-11-11", "2027-10-11", "2027-11-11"}  # SIFMA (curated)

STATES = ("HEALTHY", "DEGRADED", "STALE", "UNAVAILABLE", "NOT_CONFIGURED")


def now() -> int:
    return int(time.time())


def iso(ts: int | None) -> str | None:
    return None if ts is None else datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_session(d: date, market: str = "equity") -> bool:
    s = d.isoformat()
    if d.weekday() >= 5 or s in NYSE_HOLIDAYS:
        return False
    return not (market == "bond" and s in BOND_EXTRA)


def last_completed_session(ts: int, market: str = "equity", close_hm=(16, 0)) -> date:
    """Most recent session whose close (NY time) is at or before ts."""
    t = datetime.fromtimestamp(ts, NY)
    d = t.date()
    if (t.hour, t.minute) < close_hm or not is_session(d, market):
        d -= timedelta(days=1)
    while not is_session(d, market):
        d -= timedelta(days=1)
    return d


def ny_ts(d: date, hh: int, mm: int = 0) -> int:
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).timestamp())


# Freshness policy per source: returns (status, expected validAsOf, note)
def freshness(source: str, valid_as_of: int | None, at: int) -> tuple[str, str]:
    if valid_as_of is None:
        return "UNAVAILABLE", "no timestamp in the data"
    age_h = (at - valid_as_of) / 3600
    if source in ("equities", "options", "macro"):
        # A daily bar is fresh if it is the last completed NYSE session (weekends/holidays aware).
        want = last_completed_session(at)
        got = datetime.fromtimestamp(valid_as_of, NY).date()
        if source == "options":  # delayed intraday snapshot: fresh within 1h during a session, else last session
            t = datetime.fromtimestamp(at, NY)
            in_session = is_session(t.date()) and (9, 30) <= (t.hour, t.minute) <= (16, 15)
            if in_session:
                return ("HEALTHY", "delayed ~15 min") if age_h <= 1 else ("STALE", f"snapshot {age_h:.1f}h old during a session")
            return ("HEALTHY", "last session snapshot") if got >= want else ("STALE", f"snapshot from {got}, expected {want}")
        if got >= want or (source == "macro" and age_h <= 30):
            return "HEALTHY", f"daily bar for {got}"
        return "STALE", f"latest bar {got}, expected {want}"
    if source == "treasury":
        # Par yields for day D are published on D (late afternoon ET); allow until the next bond session's evening.
        want = last_completed_session(at - 6 * 3600, "bond", (18, 0))
        got = datetime.fromtimestamp(valid_as_of, NY).date()
        return ("HEALTHY", f"curve for {got}") if got >= want else ("STALE", f"curve {got}, expected {want}")
    limits = {"polymarket": 2, "kalshi": 2, "crypto": 26, "stablecoins": 26, "sec": 72, "solana": 72}
    lim = limits.get(source, 24)
    return ("HEALTHY", f"{age_h:.1f}h old") if age_h <= lim else ("STALE", f"{age_h:.1f}h old (limit {lim}h)")


def obs(event: int | None, available: int | None, ingest: int, valid_as_of: int | None, status: str, coverage: dict,
        limitations: list[str], approx: bool = False) -> dict:
    """The observation envelope attached to every signal."""
    return {"eventTime": iso(event), "availableTime": iso(available), "ingestTime": iso(ingest), "validAsOf": iso(valid_as_of),
            "eventTs": event, "availableTs": available, "ingestTs": ingest, "validAsOfTs": valid_as_of,
            "timesApproximate": approx, "sourceStatus": status, "coverage": coverage, "limitations": limitations}
