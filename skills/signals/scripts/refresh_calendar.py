#!/usr/bin/env python3
"""Rebuild data/event-calendar.json from official schedules (Fed, BLS, Treasury FiscalData) + computed opex.

BLS asks automated clients for a contact User-Agent: set GTB_CONTACT="Your Name you@yourdomain" in your own environment
(GTB_CONTACT_USER_AGENT / GTB_SEC_USER_AGENT are accepted for compatibility). Without one, BLS events are NOT fetched and
are listed as missing, never guessed, and the file records contact.configured = false. No contact is ever invented."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import requests
from grok_the_block.markets import events as E

ua = os.environ.get("GTB_CONTACT") or os.environ.get("GTB_CONTACT_USER_AGENT") or os.environ.get("GTB_SEC_USER_AGENT") or ""
def txt(u):
    h = {"User-Agent": ua if ("bls.gov" in u and "@" in ua) else "Mozilla/5.0"}
    if "bls.gov" in u and "@" not in ua:
        return None
    try:
        r = requests.get(u, headers=h, timeout=30); return r.text if r.ok else None
    except requests.RequestException:
        return None
def js(u):
    try:
        r = requests.get(u, timeout=30); return r.json() if r.ok else None
    except (requests.RequestException, ValueError):
        return None
cal = E.build(txt, js)
cal["contact"] = {"configured": "@" in ua, "envVar": "GTB_CONTACT", "note": "value is never written to this file"}
E.CAL_PATH.parent.mkdir(exist_ok=True)
E.CAL_PATH.write_text(json.dumps(cal, indent=1))
from collections import Counter
print(Counter(e["type"] for e in cal["events"]), "missing:", cal["missing"])
