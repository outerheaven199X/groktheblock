#!/usr/bin/env python3
"""R7-02: official macro release dates (FOMC decisions, CPI, Employment Situation) for 2019-2026, used only to stratify the
evaluation sample by calendar-release status. Dates only, no provider data. Sources: federalreserve.gov FOMC calendars
(current + historical 2019/2020 pages) and BLS news-release archive indexes (release date encoded in archive file names).
Writes docs/review/eval-treasury/release-calendar.json with source URLs and page SHA-256s.
Usage: python tools/build_release_calendar.py"""
import hashlib, json, re, urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0 (research; contact nick@example.com)"}  # BLS rejects agents without a contact
M = "January|February|March|April|May|June|July|August|September|October|November|December"
MI = {m: i + 1 for i, m in enumerate(M.split("|"))}
MI.update({m[:3]: i for m, i in list(MI.items())})
MA = M + "|" + "|".join(m[:3] for m in M.split("|"))
SRC = {"fomc": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
       "fomc2019": "https://www.federalreserve.gov/monetarypolicy/fomchistorical2019.htm",
       "fomc2020": "https://www.federalreserve.gov/monetarypolicy/fomchistorical2020.htm",
       "cpi": "https://www.bls.gov/bls/news-release/cpi.htm", "empsit": "https://www.bls.gov/bls/news-release/empsit.htm"}
YEARS = range(2019, 2027)


def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read()


def main():
    pages = {k: get(u) for k, u in SRC.items()}
    ev = []
    for k in ("fomc2019", "fomc2020"):
        y = int(k[-4:])
        for m, d1, d2 in re.findall(rf"({M}) (\d+)(?:-(\d+))?(?: \(unscheduled\))? Meeting - {y}", pages[k].decode("utf-8", "ignore")):
            mo, dd = MI[m], int(d2 or d1)  # "April/May 30-1": the matched month is the end month
            ev.append(("FOMC", date(y, mo, dd).isoformat()))
    txt = re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", pages["fomc"].decode("utf-8", "ignore")))
    parts = re.split(r"(\d{4}) FOMC Meetings", txt)
    for y, body in zip(parts[1::2], parts[2::2]):
        y = int(y)
        for m1, m2, d1, d2 in re.findall(rf"\b({MA})(?:/({MA}))? (\d+)(?:-(\d+))?\*? (?:Statement|Minutes|Press|Projection|Implementation|Notation)", body):
            mo, dd = MI[m2 or m1], int(d2 or d1)
            ev.append(("FOMC", date(y, mo, dd).isoformat()))
    for typ, k in (("CPI", "cpi"), ("NFP", "empsit")):
        for mm, dd, yy in re.findall(rf"archives/{k}_(\d\d)(\d\d)(\d{{4}})\.htm", pages[k].decode("utf-8", "ignore")):
            ev.append((typ, f"{yy}-{mm}-{dd}"))
    ev = sorted({e for e in ev if int(e[1][:4]) in YEARS}, key=lambda e: (e[1], e[0]))
    out = {"_provenance": "public-official", "_note": "Release DATES only (no data values). Used to stratify evaluation windows; a window is a release window if its session date is a release date.",
           "sources": {k: {"url": u, "sha256": hashlib.sha256(pages[k]).hexdigest()} for k, u in SRC.items()},
           "counts": {t: sum(1 for e in ev if e[0] == t) for t in ("FOMC", "CPI", "NFP")},
           "events": [{"type": t, "date": d} for t, d in ev]}
    p = ROOT / "docs/review/eval-treasury/release-calendar.json"
    p.write_text(json.dumps(out, indent=0) + "\n")
    print(out["counts"])


if __name__ == "__main__":
    main()
