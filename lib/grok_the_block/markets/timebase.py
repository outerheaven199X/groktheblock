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

# NYSE early closes at 13:00 ET (curated from NYSE holiday notices, verify annually)
EARLY_CLOSE = {"2025-07-03", "2025-11-28", "2025-12-24", "2026-11-27", "2026-12-24", "2027-11-26"}
PUBLISH_LAG_S = 15 * 60  # assumed delay before a closed daily bar is published by the free providers (estimate)

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


LONDON = ZoneInfo("Europe/London")
OPTION_SLOTS = [(h, 0) for h in range(10, 17)]  # delayed option snapshots expected hourly while the exchange is open (10:00…16:00 ET)


def cadence(source: str, instrument: str | None = None) -> str:
    """R7-03: the expected-update clock for a source/instrument, in words (used in lifecycle explanations)."""
    i = instrument or ""
    if source == "treasury":
        return "Treasury par curve, ~18:00 ET each bond-market session (SIFMA holidays)"
    if source == "equities":
        return "NYSE daily bar, session close (13:00 on early-close days) + 15 min"
    if source == "options":
        return "delayed option snapshot, hourly while the exchange is open"
    if source == "stablecoins":
        return "stablecoin aggregate, every 24h on a 7-day calendar"
    if source == "macro":
        if i == "^VIX":
            return "Cboe VIX close, 16:15 ET each NYSE session"
        if i.endswith("=X"):
            return "FX daily bar, end of the London calendar day (Mon-Fri, London DST)"
        return "futures/index daily bar, 17:00 ET each session"
    return "polled source"


def expected_update(source: str, instrument: str | None, last: int, n: int = 1) -> int | None:
    """R7-03: when the n-th update after `last` is expected from this source/instrument's own schedule
    (None = polled source without a schedule). Reuses the session calendars above; no second table."""
    i = instrument or ""
    if source == "stablecoins":
        return last + n * 86400
    if source == "macro" and i.endswith("=X"):
        d = datetime.fromtimestamp(last, LONDON).date()
        k = 0
        while True:
            end = int((datetime(d.year, d.month, d.day, tzinfo=LONDON) + timedelta(days=1)).timestamp())
            if d.weekday() < 5 and end > last:
                k += 1
                if k == n:
                    return end
            d += timedelta(days=1)
    if source == "options":
        d = datetime.fromtimestamp(last, NY).date()
        k = 0
        while True:
            if is_session(d):
                for hh, mm in OPTION_SLOTS:
                    t = ny_ts(d, hh, mm)
                    if t > last:
                        k += 1
                        if k == n:
                            return t
            d += timedelta(days=1)
    if source in ("treasury", "equities", "macro"):
        market = "bond" if source == "treasury" else "equity"
        d0 = d = datetime.fromtimestamp(last, NY).date()
        k = 0
        while True:
            if is_session(d, market):
                if source == "treasury":
                    t = ny_ts(d, 18)
                elif source == "equities":
                    t = ny_ts(d, *session_close(d)) + PUBLISH_LAG_S
                elif i == "^VIX":
                    t = ny_ts(d, 16, 15)
                else:
                    t = ny_ts(d, 17)
                # treasury/equities: the n-th session after the NY date of `last` (an observation taken during a session
                # shows the previous close; R6-02 holiday logic kept); macro clocks: the n-th close after `last`
                if (d > d0) if source in ("treasury", "equities") else (t > last):
                    k += 1
                    if k == n:
                        return t
            d += timedelta(days=1)
    return None


def session_close(d: date) -> tuple[int, int]:
    return (13, 0) if d.isoformat() in EARLY_CLOSE else (16, 0)


def daily_bar_status(source: str, symbol: str, bar_ts: int, now_ts: int, tz: str | None = None) -> dict:
    """When is a daily bar complete, and when could it first be known? (R4-04: provider clocks are explicit.)

    The bar's SESSION DATE is read in the provider's own clock: `tz` = the provider's exchange timezone (Yahoo
    meta.exchangeTimezoneName). Without one, a stamp at exactly 00:00 UTC is a date-only row (Nasdaq, OKX 1Dutc) and
    keeps its UTC calendar date; anything else is read in New York time.
    equities (NYSE): complete at the session close (13:00 on early-close days), available ≈ close + PUBLISH_LAG_S.
    macro: VIX at 16:15 ET; CME futures and DXY at 17:00 ET. Yahoo FX pairs are stamped at London midnight and cover the
    London calendar day, so they complete at the END of that day (not 17:00 ET); the difference is flagged in clockNote.
    crypto: UTC candle, complete at 00:00 UTC of the next day.
    PUBLISH_LAG_S is a conservative hold, NOT evidence the provider published a final bar: availability stays "estimated".
    Never clamps a future availability to now: an incomplete bar is reported as incomplete, not as available."""
    note = None
    if source == "crypto":
        close = bar_ts + 86400 if bar_ts % 86400 == 0 else int(datetime.fromtimestamp(bar_ts, timezone.utc).replace(hour=0, minute=0, second=0).timestamp()) + 86400
        d = datetime.fromtimestamp(close - 86400, timezone.utc).date()
        basis = "UTC candle close"
        if bar_ts % 86400:
            note = f"provider stamped {datetime.fromtimestamp(bar_ts, timezone.utc):%H:%M} UTC; read as the UTC candle of {d}"
    else:
        clock = ZoneInfo(tz) if tz else (timezone.utc if bar_ts % 86400 == 0 else NY)
        local = datetime.fromtimestamp(bar_ts, clock)
        d = local.date()
        ny_local = datetime.fromtimestamp(bar_ts, NY)
        if source == "equities":
            hh, mm = session_close(d); basis = "NYSE close" + (" (early close)" if (hh, mm) == (13, 0) else "")
            if (ny_local.hour, ny_local.minute) not in ((9, 30), (0, 0)) and bar_ts % 86400:
                note = f"provider stamp {ny_local:%H:%M} ET is neither the 09:30 open nor a date-only row"
            close = ny_ts(d, hh, mm)
        elif symbol == "^VIX":
            basis = "Cboe VIX close"; close = ny_ts(d, 16, 15)
        elif tz and tz not in ("America/New_York", "America/Chicago") and symbol.endswith("=X"):
            nxt = datetime(d.year, d.month, d.day, tzinfo=clock) + timedelta(days=1)
            close = int(nxt.timestamp())
            basis = f"{tz} calendar day end (provider clock)"
            note = f"provider stamps this FX bar at {tz} midnight ({ny_local:%Y-%m-%d %H:%M} ET); it covers the {tz} day {d}, which ends after the 17:00 ET convention"
        else:
            basis = "17:00 ET trading-day end (FX / CME futures)"; close = ny_ts(d, 17, 0)
    avail = close + PUBLISH_LAG_S
    return {"complete": now_ts >= avail, "eventTs": close, "availableTs": avail, "basis": basis, "estimated": True,
            "sessionDate": d.isoformat(), "providerClock": tz or ("UTC date-only" if bar_ts % 86400 == 0 else "America/New_York"), "clockNote": note}
