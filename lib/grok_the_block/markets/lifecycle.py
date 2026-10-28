"""Incident lifecycle for watch mode: NEW → ACTIVE → COOLING → RESOLVED, with episodes.

Identity: signal key (provider + canonical entity + detector) + episode number. No calendar date, so a
condition that continues across UTC midnight stays one incident.
- Exit hysteresis: the measured magnitude (observed / entry threshold) falls below 0.75 for 2 valid observations.
- Re-alert: a new episode (re-entry after RESOLVED), a new distinct transaction, a ≥25% rise in magnitude, or
  a severity escalation. Unresolved HIGH/CRITICAL: reminder at 6h, then at most daily.
- Observation validity (P0.01): resolution needs a VALID probe for the incident's own instrument+detector key.
  An absent or invalid probe is "not observed", never zero: the incident is HELD with its lastConfirmedAt, even
  when its source as a whole is DEGRADED but healthy for other instruments. Cross-market incidents keep their
  member keys and resolve only when every member was validly observed below exit.
- Quiet hours use an IANA zone (prefs.quietTz); the fixed tzOffsetH flag remains as a fallback.
- Webhook delivery is tracked in an outbox with idempotent ids; "delivered" is counted only on confirmed success.
- Telemetry separates suppressed-unchanged, below the user's floor, muted, deferred by quiet hours/digest, and
  skipped because the source was unavailable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SEV = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
EXIT_RATIO, EXIT_COUNT, RISE = 0.75, 2, 1.25
REMIND_FIRST, REMIND_EVERY = 6 * 3600, 24 * 3600
BAD = {"UNAVAILABLE", "STALE", "NOT_CONFIGURED"}


def load(path: Path) -> dict:
    try:
        st = json.loads(path.read_text())
    except (OSError, ValueError):
        st = {}
    if "incidents" not in st:  # adapter: v1 state had {"seen": {key: severity}} → start a fresh lifecycle, keep the baseline flag
        st = {"incidents": {}, "lastSuccessAt": st.get("lastSuccessAt"), "sourceLastValid": {}, "digest": [], "legacySeen": len(st.get("seen") or {})}
    return st


def _hist(inc, at, event, note=""):
    inc["history"].append({"at": at, "event": event, "state": inc["state"], "severity": inc["severity"], "magnitude": inc.get("lastMagnitude"), "note": note})
    inc["history"] = inc["history"][-40:]


def _quiet(at: int, quiet: tuple[int, int] | None, tz_offset_h: float, tz: str | None = None) -> bool:
    if not quiet:
        return False
    if tz:
        from zoneinfo import ZoneInfo
        h = datetime.fromtimestamp(at, ZoneInfo(tz)).hour
    else:
        h = (datetime.fromtimestamp(at, timezone.utc).hour + tz_offset_h) % 24
    a, b = quiet
    return (a <= h < b) if a < b else (h >= a or h < b)


def _probe(probes, k):
    """→ (ratio, valid). Accepts v3 dict probes or legacy floats (treated as valid)."""
    p = probes.get(k)
    if p is None:
        return None, False
    if isinstance(p, dict):
        return p.get("ratio"), bool(p.get("valid")) and p.get("ratio") is not None
    return float(p), True


def step(st: dict, signals: list[dict], probes: dict, source_state: dict[str, str], now: int, prefs: dict | None = None) -> dict:
    """Advance the lifecycle one run. Returns {"alerts": [...], "telemetry": {...}} and mutates st."""
    prefs = prefs or {}
    floor = SEV.index(prefs.get("minSeverity", "LOW"))
    mutes = set(prefs.get("mute") or [])
    quiet = prefs.get("quietHours")
    digest_mode = prefs.get("digest", False)
    tel = {"alerts": 0, "newEpisodes": 0, "suppressedUnchanged": 0, "belowFloor": 0, "muted": 0, "deferred": 0,
           "skippedUnavailable": 0, "heldUnobserved": 0, "resolved": 0, "cooling": 0, "reminders": 0, "delivered": 0, "deliveryFailed": 0}
    qargs = (quiet, prefs.get("tzOffsetH", 0), prefs.get("quietTz"))
    inc_all = st.setdefault("incidents", {})
    first_run = not st.get("lastSuccessAt")
    raw_alerts = []
    seen_now = set()
    for s in signals:
        if s["basis"] == "unverified" or s["severity"] == "INFO":
            continue
        k = s["key"]
        seen_now.add(k)
        mag, _v = _probe(probes, k)
        if mag is None:
            mag = 1.0 + ((s.get("metrics") or {}).get("rank") or 0) / 100 if s["source"] == "cross" else 1.0
        tx = set((s.get("metrics") or {}).get("distinctTx") or [])
        inc = inc_all.get(k)
        reason = None
        if inc is None or inc["state"] == "RESOLVED":
            ep = (inc["episode"] + 1) if inc else 1
            inc = {"id": f"{k}#e{ep}", "key": k, "episode": ep, "state": "NEW", "source": s["source"], "openedAt": now, "lastSeenAt": now,
                   "severity": s["severity"], "entryMagnitude": mag, "lastMagnitude": mag, "lastAlertMagnitude": mag, "peakMagnitude": mag,
                   "belowCount": 0, "distinctTx": sorted(tx), "lastAlertAt": None, "lastConfirmedAt": now,
                   "members": list((s.get("metrics") or {}).get("memberKeys") or []), "remindedAt": None, "history": [], "title": s["title"]}
            inc_all[k] = inc
            _hist(inc, now, "ENTERED", f"episode {ep}")
            reason = "NEW_EPISODE" if ep > 1 else "NEW"
            tel["newEpisodes"] += 1
        else:
            inc["state"] = "ACTIVE"; inc["belowCount"] = 0; inc["lastSeenAt"] = now; inc["lastMagnitude"] = mag; inc["lastConfirmedAt"] = now
            if (s.get("metrics") or {}).get("memberKeys"):
                inc["members"] = list(s["metrics"]["memberKeys"])
            inc["peakMagnitude"] = max(inc["peakMagnitude"], mag); inc["title"] = s["title"]
            new_tx = tx - set(inc["distinctTx"])
            if SEV.index(s["severity"]) > SEV.index(inc["severity"]):
                reason = "ESCALATED"
            elif new_tx:
                reason = "NEW_TRANSACTION"
            elif mag >= RISE * (inc["lastAlertMagnitude"] or mag):
                reason = "MAGNITUDE_RISE"
            elif SEV.index(s["severity"]) >= 3 and inc.get("lastAlertAt"):
                due = (inc["openedAt"] + REMIND_FIRST) if not inc.get("remindedAt") else (inc["remindedAt"] + REMIND_EVERY)
                if now >= due:
                    reason = "REMINDER"
            inc["distinctTx"] = sorted(set(inc["distinctTx"]) | tx)[-200:]
            inc["severity"] = s["severity"] if reason == "ESCALATED" else inc["severity"]
            _hist(inc, now, reason or "UNCHANGED")
        if reason:
            raw_alerts.append((s, inc, reason, mag))
        else:
            tel["suppressedUnchanged"] += 1
    # incidents not signalled this run
    for k, inc in inc_all.items():
        if k in seen_now or inc["state"] == "RESOLVED":
            continue
        src_state = source_state.get(inc["source"], "NOT_RUN")
        if inc["source"] != "cross" and (src_state in BAD or src_state == "NOT_RUN"):
            tel["skippedUnavailable"] += 1
            _hist(inc, now, "SOURCE_UNAVAILABLE", f"{inc['source']} {src_state}: last confirmed state retained")
            continue
        keys = inc.get("members") or [k]
        obs = [_probe(probes, m) for m in keys]
        if not all(v for _, v in obs):
            missing = [m for m, (_, v) in zip(keys, obs) if not v]
            tel["heldUnobserved"] += 1
            _hist(inc, now, "HELD_UNOBSERVED", f"not validly observed this run ({', '.join(missing[:3])}); last confirmed {inc.get('lastConfirmedAt')}")
            continue
        r = min(x for x, _ in obs)
        inc["lastMagnitude"] = r
        if r < EXIT_RATIO:
            inc["belowCount"] += 1
            if inc["belowCount"] >= EXIT_COUNT:
                inc["state"] = "RESOLVED"; inc["resolvedAt"] = now; tel["resolved"] += 1
                _hist(inc, now, "RESOLVED", f"below {EXIT_RATIO:.0%} of entry for {EXIT_COUNT} valid observations")
            else:
                inc["state"] = "COOLING"; tel["cooling"] += 1
                _hist(inc, now, "COOLING", f"magnitude {r:.2f} of entry threshold (valid observation)")
        else:
            inc["state"] = "ACTIVE"; inc["belowCount"] = 0; inc["lastConfirmedAt"] = now
            _hist(inc, now, "HELD", f"magnitude {r:.2f}: inside the hysteresis band")
    alerts = []
    for s, inc, reason, mag in raw_alerts:
        if first_run:
            continue  # baseline run: record, don't notify
        if SEV.index(s["severity"]) < floor:
            tel["belowFloor"] += 1; continue
        if s["source"] in mutes:
            tel["muted"] += 1; continue
        a = dict(s, alertReason=reason, incidentId=inc["id"], incidentState=inc["state"], episode=inc["episode"],
                 previousSuccessfulScanAt=st.get("lastSuccessAt"), magnitude=round(mag, 3), lifecycle=inc["history"][-6:])
        inc["lastAlertAt"] = now; inc["lastAlertMagnitude"] = mag
        if reason == "REMINDER":
            inc["remindedAt"] = now; tel["reminders"] += 1
        if digest_mode or _quiet(now, *qargs):
            st.setdefault("digest", []).append(a); tel["deferred"] += 1; continue
        alerts.append(a)
    # release a held digest outside quiet hours (or on the digest run)
    if st.get("digest") and not _quiet(now, *qargs) and (not digest_mode or prefs.get("releaseDigest")):
        alerts = st["digest"] + alerts; st["digest"] = []
    # idempotent ids: a restart that replays the same run doesn't double-deliver
    sent = st.setdefault("emittedIds", [])
    uniq = []
    for a in alerts:
        a["alertId"] = a.get("alertId") or f"{a['incidentId']}|{a['alertReason']}|{a.get('lifecycle', [{}])[-1].get('at', now)}"
        if a["alertId"] in sent or any(u["alertId"] == a["alertId"] for u in uniq):
            continue
        uniq.append(a)
    alerts = uniq
    st["emittedIds"] = (sent + [a["alertId"] for a in alerts])[-2000:]
    tel["alerts"] = len(alerts)
    for src, state in source_state.items():
        if state in ("HEALTHY", "DEGRADED"):
            st.setdefault("sourceLastValid", {})[src] = now
    if any(v in ("HEALTHY", "DEGRADED") for v in source_state.values()):
        st["lastSuccessAt"] = now
    # keep the file bounded
    if len(inc_all) > 3000:
        for k in sorted((k for k, v in inc_all.items() if v["state"] == "RESOLVED"), key=lambda k: inc_all[k].get("resolvedAt", 0))[:len(inc_all) - 3000]:
            del inc_all[k]
    return {"alerts": alerts, "telemetry": tel, "baseline": first_run}


def deliver(st: dict, alerts: list[dict], send, tel: dict | None = None, max_attempts: int = 5) -> dict:
    """Webhook outbox: queue alerts, try every pending item via send(alert) -> bool, count delivered only on success,
    keep failures for the next run (bounded attempts). Restart-safe: the outbox and sent ids live in the state."""
    tel = tel if tel is not None else {}
    box = st.setdefault("outbox", [])
    sent = st.setdefault("sentIds", [])
    known = {x["alert"]["alertId"] for x in box} | set(sent)
    for a in alerts:
        if a["alertId"] not in known:
            box.append({"alert": a, "attempts": 0}); known.add(a["alertId"])
    keep = []
    for item in box:
        ok = False
        try:
            ok = bool(send(item["alert"]))
        except Exception:  # noqa: BLE001 - a failed webhook must not stop the scan
            ok = False
        item["attempts"] += 1
        if ok:
            sent.append(item["alert"]["alertId"]); tel["delivered"] = tel.get("delivered", 0) + 1
        else:
            tel["deliveryFailed"] = tel.get("deliveryFailed", 0) + 1
            if item["attempts"] < max_attempts:
                keep.append(item)
    st["outbox"] = keep
    st["sentIds"] = sent[-2000:]
    tel["pendingDelivery"] = len(keep)
    return tel
