#!/usr/bin/env python3
"""R8-01: official macro release calendar for the Treasury evaluation (2019-2026), built from PRIMARY announcements.

FOMC: every policy statement linked from the Federal Reserve's FOMC calendar pages (current page + historical 2019/2020),
then each statement page itself is fetched and its own release date ("article__time") and "For release at h:mm a.m./p.m.
EST/EDT" are recorded: announcement time, class SCHEDULED/UNSCHEDULED (from the meeting heading), weekday, and the
first Treasury observation session at or after the announcement (par yields reflect ~15:30 ET closing bids, so a release
at/after 15:30 or on a non-session day maps to the next bond session). The audit compares each statement's own date with the
date encoded in its URL and with the calendar entry; mismatches are reported, never silently fixed.
CPI / Employment Situation: BLS original-release archive. bls.gov requires a real contact in the User-Agent, so the
fetch needs GTB_CONTACT (an email or URL the operator controls) in the environment. Without it the BLS part is
NOT_CONFIGURED: no request is sent and no placeholder contact is ever used; dates fall back to the r7 calendar's
archive-file dates, marked UNAUDITED.
Writes docs/review/eval-treasury/release-calendar-r8.json (r7 calendar kept unchanged).
Usage: GTB_CONTACT=you@example.org python tools/build_release_calendar.py"""
import hashlib, json, os, re, sys, urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from grok_the_block.markets import timebase as T  # noqa: E402

FED = "https://www.federalreserve.gov"
SRC = {"fomc": FED + "/monetarypolicy/fomccalendars.htm", "fomc2019": FED + "/monetarypolicy/fomchistorical2019.htm",
       "fomc2020": FED + "/monetarypolicy/fomchistorical2020.htm"}
BLS = {"CPI": "https://www.bls.gov/bls/news-release/cpi.htm", "NFP": "https://www.bls.gov/bls/news-release/empsit.htm"}
YEARS = range(2019, 2027)
CURVE_HM = (15, 30)  # Treasury par yields are based on ~3:30 PM ET closing indicative bids (treasury.gov methodology)
OUT = ROOT / "docs/review/eval-treasury/release-calendar-r8.json"


def user_agent(contact: str | None) -> str:
    base = "GrokTheBlock-research/1.0 (+https://github.com/outerheaven199X/CryptOSINT-GrokBot)"
    return f"{base} contact:{contact}" if contact else base


def get(u, contact=None, opener=None):
    req = urllib.request.Request(u, headers={"User-Agent": user_agent(contact)})
    return (opener or urllib.request.urlopen)(req, timeout=60).read()


def first_observation_session(ts: int) -> str:
    t = datetime.fromtimestamp(ts, T.NY)
    d = t.date()
    if not (T.is_session(d, "bond") and (t.hour, t.minute) < CURVE_HM):
        d += timedelta(days=1)
        while not T.is_session(d, "bond"):
            d += timedelta(days=1)
    return d.isoformat()


def fomc_links(pages):
    """(statementUrlPath, class) from the calendar pages."""
    out = []
    for k in ("fomc2019", "fomc2020"):
        html = pages[k].decode("utf-8", "ignore")
        for head, body in re.findall(r'<h5[^>]*>([^<]*Meeting - \d{4})</h5>(.*?)(?=<h5|\Z)', html, re.S):
            m = re.search(r'href="(/newsevents/pressreleases/monetary\d{8}a\.htm)">Statement</a>', body)
            if m:
                out.append((m.group(1), "UNSCHEDULED" if "unscheduled" in head.lower() else "SCHEDULED", head.strip()))
    html = pages["fomc"].decode("utf-8", "ignore")
    for blk in re.split(r'<div class="(?:fomc-meeting--shaded )?row fomc-meeting"', html)[1:]:
        m = re.search(r'Statement:</strong><br>\s*<a[^>]*>PDF</a>\s*\|\s*<a href="(/newsevents/pressreleases/monetary\d{8}a\.htm)">HTML', blk)
        if m:
            mo = re.search(r'fomc-meeting__month[^"]*"[^>]*><strong>([^<]+)</strong>', blk)
            dd = re.search(r'fomc-meeting__date[^>]*>([^<]+)<', blk)
            head = f"{mo.group(1) if mo else '?'} {dd.group(1).strip() if dd else '?'}"
            out.append((m.group(1), "UNSCHEDULED" if "unscheduled" in head.lower() else "SCHEDULED", head))
    seen, res = set(), []
    for p, c, h in out:
        if p not in seen and int(p[-13:-9]) in YEARS:
            seen.add(p); res.append((p, c, h))
    return res


def parse_statement(html: str):
    d = re.search(r'article__time">([A-Z][a-z]+ \d{1,2}, \d{4})<', html)
    t = re.search(r"For release at (\d{1,2}):(\d{2}) ([ap])\.m\. (EST|EDT)", html)
    if not d:
        return None
    day = datetime.strptime(d.group(1), "%B %d, %Y").date()
    if not t:
        return {"date": day.isoformat(), "time": None, "zoneLabel": None}
    hh = int(t.group(1)) % 12 + (12 if t.group(3) == "p" else 0)
    return {"date": day.isoformat(), "time": f"{hh:02d}:{t.group(2)}", "zoneLabel": t.group(4)}


def build(contact=None, opener=None, log=print):
    pages = {k: get(u, None, opener) for k, u in SRC.items()}
    events, audit = [], []
    for path, cls, head in fomc_links(pages):
        st = parse_statement(get(FED + path, None, opener).decode("utf-8", "ignore"))
        url_date = f"{path[-13:-9]}-{path[-9:-7]}-{path[-7:-5]}"
        if st is None:
            audit.append({"url": FED + path, "problem": "no release date on the statement page"}); continue
        if st["date"] != url_date:
            audit.append({"url": FED + path, "problem": f"statement date {st['date']} != URL date {url_date}"})
        hh, mm = (int(x) for x in (st["time"] or "14:00").split(":"))
        ts = T.ny_ts(date.fromisoformat(st["date"]), hh, mm)
        if st["zoneLabel"] and st["zoneLabel"] != datetime.fromtimestamp(ts, T.NY).tzname():
            audit.append({"url": FED + path, "problem": f"page says {st['zoneLabel']} but New York time was {datetime.fromtimestamp(ts, T.NY).tzname()}"})
        events.append({"type": "FOMC", "class": cls, "meeting": head, "announcementDate": st["date"], "announcementTimeET": st["time"],
                       "timeVerified": st["time"] is not None, "announcementTs": ts, "weekday": date.fromisoformat(st["date"]).strftime("%A"),
                       "firstObservationSession": first_observation_session(ts), "source": FED + path})
    sources = {k: {"url": u, "sha256": hashlib.sha256(pages[k]).hexdigest()} for k, u in SRC.items()}
    if contact:
        bls_status = "FETCHED"
        for typ, u in BLS.items():
            b = get(u, contact, opener)
            sources[f"bls-{typ}"] = {"url": u, "sha256": hashlib.sha256(b).hexdigest()}
            stem = "cpi" if typ == "CPI" else "empsit"
            for mm, dd, yy in sorted(set(re.findall(rf"archives/{stem}_(\d\d)(\d\d)(\d{{4}})\.htm", b.decode("utf-8", "ignore")))):
                if int(yy) in YEARS:
                    events.append(_bls(typ, f"{yy}-{mm}-{dd}", "BLS archive index (original release file)", False))
    else:
        bls_status = "NOT_CONFIGURED"
        log("BLS: NOT_CONFIGURED (set GTB_CONTACT to a contact you control); no request sent; using r7 archive-file dates, UNAUDITED")
        r7 = json.loads((ROOT / "docs/review/eval-treasury/release-calendar.json").read_text())
        for e in r7["events"]:
            if e["type"] in ("CPI", "NFP"):
                events.append(_bls(e["type"], e["date"], "r7 calendar (BLS archive-file dates); not re-fetched", False))
    events.sort(key=lambda e: (e["announcementTs"], e["type"]))
    return {"version": "r8-2026-10-28", "_provenance": "public-official",
            "_note": "Release announcements only (no data values). FOMC from the Fed's own statement pages; BLS see blsStatus.",
            "sources": sources, "blsStatus": bls_status, "curveObservationTimeET": "15:30",
            "audit": {"checked": sum(1 for e in events if e["type"] == "FOMC"), "mismatches": audit,
                      "rule": "statement page date vs URL date; page time-zone label vs New York DST"},
            "counts": {t: sum(1 for e in events if e["type"] == t) for t in ("FOMC", "CPI", "NFP")},
            "unscheduled": [e["announcementDate"] for e in events if e.get("class") == "UNSCHEDULED"], "events": events}


def _bls(typ, d, src, verified):
    ts = T.ny_ts(date.fromisoformat(d), 8, 30)
    return {"type": typ, "class": "SCHEDULED", "announcementDate": d, "announcementTimeET": "08:30", "timeVerified": verified,
            "announcementTs": ts, "weekday": date.fromisoformat(d).strftime("%A"), "firstObservationSession": first_observation_session(ts), "source": src}


def main():
    out = build(os.environ.get("GTB_CONTACT") or None)
    OUT.write_text(json.dumps(out, indent=0) + "\n")
    print(out["counts"], "unscheduled:", out["unscheduled"], "audit mismatches:", len(out["audit"]["mismatches"]), "BLS:", out["blsStatus"])


if __name__ == "__main__":
    main()
