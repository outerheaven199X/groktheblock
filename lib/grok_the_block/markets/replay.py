"""Deterministic replay/evaluation harness over point-in-time fixtures (tests/fixtures/replay/*.json).

Each fixture is a list of ticks. A tick has an availability time `at`, per-source states, and the signals a
detector would have produced from data available at `at` (no look-ahead: a tick may only reference observations
with availableTs <= at). The harness runs the real cross-market logic (canonical entity resolution, calendar
tagging, convergence / related repricing) and the real incident lifecycle, and compares alert counts against the
v1 behaviour (date-stamped keys, alert only on new key or higher severity).

These are synthetic scenarios that test plumbing and noise control. They say nothing about predictive value.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from . import detectors as X
from . import entities as EN
from . import events as EV
from . import lifecycle as LC

FIX = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "replay"


def _signal(spec: dict, at: int) -> dict:
    src = spec["source"]
    inst = spec.get("instrument")
    inst = inst if not inst or ":" in inst else f"{src}:{inst}"
    ents = EN.resolve(src, spec.get("instrument"), spec.get("text", ""))
    gran = spec.get("granularity", "intraday")
    sid = spec.get("id") or spec.get("instrument") or spec.get("text")
    typ = spec.get("type", "FIXTURE")
    avail = at - spec.get("lagS", 0)
    return {"key": X.key(src, sid, typ), "source": src, "family": EN.family_of(src, inst), "instrument": inst, "relations": {}, "type": typ, "severity": spec.get("severity", "MEDIUM"),
            "basis": spec.get("basis", "observed"), "title": spec.get("title") or spec.get("text") or f"{src} {sid}", "what": "", "when": avail,
            "subject": {"name": sid, "id": sid, "url": "https://example.org/fixture"}, "evidence": [{"label": "fixture", "url": "https://example.org/fixture"}],
            "limits": [], "metrics": {"distinctTx": spec.get("tx", [])}, "entities": ents, "calendar": [],
            "observation": {"eventTs": avail - spec.get("eventLeadS", 0), "availableTs": avail, "granularity": gran,
                            "temporalStatus": spec.get("temporalStatus", "OK"), "sourceStatus": spec.get("sourceStatus", "HEALTHY"),
                            "fastEligible": gran in ("intraday", "delayed") and spec.get("temporalStatus", "OK") == "OK"}}


def run_fixture(fx: dict) -> dict:
    cal = {"events": fx.get("calendar", [])}
    st = {"incidents": {}, "lastSuccessAt": fx["ticks"][0]["at"] - 900}  # pre-baselined so first-tick alerts count
    v1_seen: dict[str, str] = {}
    out = {"name": fx["name"], "ticks": len(fx["ticks"]), "alerts": 0, "alertsByReason": {}, "v1Alerts": 0, "convergences": 0,
           "convergenceMaxSeverity": None, "relatedRepricing": 0, "calendarTagged": 0, "falseConvergencePrevented": 0,
           "resolvedDuringOutage": 0, "finalStates": {}, "telemetry": {}}
    for tick in fx["ticks"]:
        at = tick["at"]
        sigs = [_signal(s, at) for s in tick.get("signals", [])]
        for s in sigs:
            assert s["when"] <= at, "look-ahead in fixture"
            s["calendar"] = EV.events_near(s["when"], {s["family"]}, cal, window_start=s["observation"]["eventTs"],
                                           granularity=s["observation"]["granularity"], instrument=s.get("instrument"))
            out["calendarTagged"] += bool(s["calendar"])
        conv = X.convergence(sigs, at)
        rel = X.same_family_repricing(sigs, at)
        out["convergences"] += len(conv); out["relatedRepricing"] += len(rel)
        for c in conv:
            if out["convergenceMaxSeverity"] is None or X.SEV.index(c["severity"]) > X.SEV.index(out["convergenceMaxSeverity"]):
                out["convergenceMaxSeverity"] = c["severity"]
        # naive v0: any two different sources sharing a word-level topic would have converged (what the review warned about)
        naive_pairs = {(a["source"], b["source"]) for a in sigs for b in sigs if a["source"] < b["source"] and
                       (set(a["entities"]) & set(b["entities"]) or set(_words(a)) & set(_words(b)))}
        if naive_pairs and not conv:
            out["falseConvergencePrevented"] += 1
        day0 = datetime.fromtimestamp(at, timezone.utc).strftime("%Y%m%d")
        for pr in naive_pairs:  # v1 topic/keyword convergence would have alerted once per pair per UTC day
            k1 = f"v1conv:{pr}:{day0}"
            if k1 not in v1_seen:
                v1_seen[k1] = "LOW"; out["v1Alerts"] += 1
        allsig = sigs + conv + rel
        probes = {s["key"]: next(({"ratio": x.get("magnitude", 1.0), "valid": x.get("valid", True)} for x in tick["signals"] if X.key(x["source"], x.get("id") or x.get("instrument") or x.get("text"), x.get("type", "FIXTURE")) == s["key"]), 1.0)
                  for s in sigs if s["source"] != "cross"}
        for c in conv:  # a cross incident is observed through its members
            ms = [probes.get(m) for m in c["metrics"].get("memberKeys") or []]
            if ms and all(m and m["valid"] for m in ms):
                probes[c["key"]] = {"ratio": min(m["ratio"] for m in ms), "valid": True}
        probes.update({k: v for k, v in (tick.get("probes") or {}).items()})
        before = {k: i["state"] for k, i in st["incidents"].items()}
        res = LC.step(st, allsig, probes, tick.get("sourceState", {}), at, fx.get("prefs"))
        for k, i in st["incidents"].items():
            if before.get(k) not in (None, "RESOLVED") and i["state"] == "RESOLVED" and tick.get("sourceState", {}).get(i["source"]) not in ("HEALTHY", "DEGRADED"):
                out["resolvedDuringOutage"] += 1
        out["alerts"] += len(res["alerts"])
        for a in res["alerts"]:
            out["alertsByReason"][a["alertReason"]] = out["alertsByReason"].get(a["alertReason"], 0) + 1
        for k, v in res["telemetry"].items():
            if isinstance(v, (int, float)):
                out["telemetry"][k] = out["telemetry"].get(k, 0) + v
        # v1 behaviour: key + UTC date, alert when unseen or severity rose
        day = datetime.fromtimestamp(at, timezone.utc).strftime("%Y%m%d")
        for s in sigs + rel:
            if s["severity"] == "INFO" or s["basis"] == "unverified":
                continue
            k1 = f"{s['key']}:{day}"
            if k1 not in v1_seen or X.SEV.index(s["severity"]) > X.SEV.index(v1_seen[k1]):
                out["v1Alerts"] += 1
            v1_seen[k1] = s["severity"]
    out["finalStates"] = {i["id"]: i["state"] for i in st["incidents"].values()}
    out["duplicatesAvoidedVsV1"] = out["v1Alerts"] - out["alerts"]
    return out


def _words(s):
    import re
    return [w for w in re.findall(r"[a-z]{4,}", (s["title"] + " " + str(s["subject"]["id"])).lower()) if w not in {"will", "this", "that", "fixture"}]


def run_all(fix_dir: Path = FIX) -> list[dict]:
    return [run_fixture(json.loads(p.read_text())) for p in sorted(fix_dir.glob("*.json"))]


if __name__ == "__main__":
    for r in run_all():
        print(json.dumps(r))
