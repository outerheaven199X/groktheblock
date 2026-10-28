"""Incident lifecycle for watch mode: NEW → ACTIVE → COOLING → RESOLVED, with episodes.

Identity: signal key (provider + canonical entity + detector) + episode number. No calendar date, so a
condition that continues across UTC midnight stays one incident.
- Exit hysteresis: the measured magnitude (observed / entry threshold) falls below 0.75 for 2 consecutive valid
  observations. For a multi-member (cross-market) incident the magnitude is the HOTTEST member's: it cools only when
  every member is validly below exit, and any missing member holds it.
- Admission (R4-02): a present signal opens, escalates, reconfirms or re-alerts only with a current source observation
  (not STALE/UNAVAILABLE/NOT_CONFIGURED), a valid time, and a valid detector probe; otherwise HELD_STALE/HELD_INVALID.
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
import time
from datetime import datetime, timezone
from pathlib import Path

SEV = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
EXIT_RATIO, EXIT_COUNT, RISE = 0.75, 2, 1.25
REMIND_FIRST, REMIND_EVERY = 6 * 3600, 24 * 3600
BAD = {"UNAVAILABLE", "STALE", "NOT_CONFIGURED"}
DEAD_LETTER_MAX = 200
EVENT_RETENTION_S = 72 * 3600      # R5-01: a discrete event stays OBSERVED this long after its last NEW event, then ARCHIVED
UNCONFIRMED_AFTER_S = 24 * 3600    # R5-03: a held incident with no valid observation for this long is UNCONFIRMED …
ARCHIVE_UNRESOLVED_AFTER_S = 72 * 3600  # … and after this long ARCHIVED_UNRESOLVED (never RESOLVED)
DAILY_SOURCES = {"equities", "options", "treasury", "macro", "stablecoins"}  # one valid observation per trading session:
DAILY_AGE_S = (96 * 3600, 168 * 3600)  # a weekend or holiday must not archive a daily incident (UNCONFIRMED, ARCHIVED_UNRESOLVED)
CLOSED = {"RESOLVED", "ARCHIVED", "ARCHIVED_UNRESOLVED"}
EVENT_SOURCES = {"sec", "solana"}  # event detectors: the transaction/filing itself is the measurement (no ratio probe)


def admit(s: dict, probes: dict) -> str | None:
    """R4-02: may this present signal open, escalate, reconfirm or re-alert an incident? None = yes, else the reason.
    A source that returned data is not the same as a detector that produced a valid measurement: both are required."""
    if s["source"] == "cross":
        return None  # cross signals are built only from eligible members (detectors._eligible); members are checked on exit
    o = s.get("observation")
    if o is None:
        return None  # legacy/unit-level signal without an envelope (v1 adapter always adds one)
    if o.get("sourceStatus") in BAD:
        return f"source {o['sourceStatus']}: the provider returned no current data for this observation"
    if o.get("temporalStatus", "OK") != "OK":
        return f"time not valid ({o['temporalStatus']})"
    if s["source"] in EVENT_SOURCES:
        ids = (s.get("metrics") or {}).get("eventIds") or []
        if not ids or not all(e.get("id") and e.get("eventTs") and e.get("url") for e in ids):
            return "event without an immutable id, event time and evidence link (provenance incomplete)"
        return None
    if (s.get("metrics") or {}).get("distinctTx"):
        return None
    p = probes.get(s["key"])
    if p is None:
        return "detector produced no valid measurement (no probe recorded)"
    if isinstance(p, dict) and not (p.get("valid") and p.get("ratio") is not None):
        return f"detector produced no valid measurement ({p.get('reason') or 'invalid'})"
    return None


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


def _members(inc, new, probes, now):
    """R4-01: a recomputed convergence may list different members. Members dropped from the new list stay while their
    last valid observation is still at/above exit (or unobserved); the change is recorded, never silent."""
    old = list(inc.get("members") or [])
    keep = []
    for m in old:
        if m in new:
            continue
        r, v = _probe(probes, m)
        if not v or r >= EXIT_RATIO:
            keep.append(m)
    merged = list(dict.fromkeys(new + keep))
    if set(merged) != set(old):
        inc.setdefault("memberHistory", []).append({"at": now, "event": "MEMBERS_CHANGED", "from": old, "to": merged,
                                                    "retainedActive": keep, "note": "dropped members kept while still anomalous or unobserved"})
        inc["memberHistory"] = inc["memberHistory"][-20:]
    inc["members"] = merged


def _summary(inc):
    return {"id": inc["id"], "episode": inc["episode"], "endedAs": inc.get("endedAs") or inc["state"], "members": list(inc.get("members") or []),
            "openedAt": inc.get("openedAt"), "closedAt": inc.get("resolvedAt") or inc.get("archivedAt"), "lastConfirmedAt": inc.get("lastConfirmedAt"),
            "events": sorted(inc.get("events") or {}), "history": inc["history"][-12:], "memberHistory": (inc.get("memberHistory") or [])[-6:]}


def _close(inc, now, how, note):
    inc["endedAs"] = how
    inc["state"] = "ARCHIVED_UNRESOLVED"; inc["archivedAt"] = now
    _hist(inc, now, how, note)


def _age(inc, now, tel, missing=None):
    """R5-03: an incident that can't be validly observed is not RESOLVED, but it also stops looking freshly ACTIVE:
    UNCONFIRMED after 24h without a valid observation, ARCHIVED_UNRESOLVED after 72h (re-entry opens a new episode)."""
    last = inc.get("lastConfirmedAt") or inc.get("openedAt") or now
    if missing:
        lv = inc.get("memberLastValid") or {}
        last = min([lv.get(m) or inc.get("lastConfirmedAt") or inc.get("openedAt") or now for m in missing] + [last])
    gap = now - last
    unc, arc = DAILY_AGE_S if inc["source"] in DAILY_SOURCES else (UNCONFIRMED_AFTER_S, ARCHIVE_UNRESOLVED_AFTER_S)
    if gap >= arc:
        _close(inc, now, "ARCHIVED_UNRESOLVED", f"no valid observation of {', '.join((missing or ['this instrument'])[:3])} for {gap / 3600:.0f}h; not resolved, last confirmed {inc.get('lastConfirmedAt')}")
        tel["archivedUnresolved"] = tel.get("archivedUnresolved", 0) + 1
    elif gap >= unc and inc["state"] != "UNCONFIRMED":
        inc["state"] = "UNCONFIRMED"; inc["unconfirmedSince"] = now
        _hist(inc, now, "UNCONFIRMED", f"no valid observation for {gap / 3600:.0f}h; last observed {last}")
        tel["unconfirmed"] = tel.get("unconfirmed", 0) + 1


def _archive_event(inc, now, tel):
    inc["state"] = "ARCHIVED"; inc["archivedAt"] = now; inc["endedAs"] = "ARCHIVED"
    _hist(inc, now, "ARCHIVED", f"observation window ({EVENT_RETENTION_S // 3600}h after the last new event) ended; this is not a resolution of any market risk")
    tel["archived"] = tel.get("archived", 0) + 1


def _event_step(inc_all, s, now, tel):
    """R5-01: event episodes. Novelty = immutable event ids. A repeat of a known id changes nothing (no refreshed
    evidence time, no reminder); a new id is NEW_EVENT; evidence time is the event's own time."""
    k = s["key"]
    ids = {e["id"]: e for e in (s.get("metrics") or {}).get("eventIds") or []}
    inc = inc_all.get(k)
    known = set((inc or {}).get("events") or {}) | set((inc or {}).get("archivedEventIds") or [])
    fresh = {i: e for i, e in ids.items() if i not in known}
    if inc is not None and inc["state"] not in CLOSED:
        if fresh:
            inc["events"].update({i: {"eventTs": e["eventTs"], "url": e["url"], "firstObservedAt": now} for i, e in fresh.items()})
            inc["lastNewEventAt"] = now; inc["lastSeenAt"] = now
            inc["lastConfirmedAt"] = max(inc["lastConfirmedAt"] or 0, max(e["eventTs"] for e in fresh.values()))
            inc["newEventIds"] = sorted(fresh)
            _hist(inc, now, "NEW_EVENT", f"{len(fresh)} new event id(s)")
            tel["eventsNew"] = tel.get("eventsNew", 0) + len(fresh)
            return "NEW_EVENT"
        if now - inc["lastNewEventAt"] >= EVENT_RETENTION_S:
            _archive_event(inc, now, tel)
        else:
            tel["suppressedUnchanged"] += 1
        return None
    if not fresh:
        tel["suppressedUnchanged"] += 1  # an archived event re-appearing in a later feed is not news
        return None
    ep = (inc["episode"] + 1) if inc else 1
    archived = sorted(known)[-500:]
    inc = {"id": f"{k}#e{ep}", "key": k, "kind": "event", "episode": ep, "state": "OBSERVED", "source": s["source"], "openedAt": now, "lastSeenAt": now,
           "lastNewEventAt": now, "severity": s["severity"], "title": s["title"], "lastAlertAt": None, "remindedAt": None,
           "events": {i: {"eventTs": e["eventTs"], "url": e["url"], "firstObservedAt": now} for i, e in fresh.items()},
           "lastConfirmedAt": max(e["eventTs"] for e in fresh.values()), "newEventIds": sorted(fresh), "archivedEventIds": archived,
           "lastMagnitude": None, "lastAlertMagnitude": None, "history": [], "distinctTx": [],
           "previousEpisodes": (((inc or {}).get("previousEpisodes") or []) + ([_summary(inc)] if inc else []))[-10:]}
    inc_all[k] = inc
    _hist(inc, now, "OBSERVED", f"episode {ep}: {len(fresh)} event id(s)")
    tel["newEpisodes"] += 1; tel["eventsNew"] = tel.get("eventsNew", 0) + len(fresh)
    return "NEW_EPISODE" if ep > 1 else "NEW"


def step(st: dict, signals: list[dict], probes: dict, source_state: dict[str, str], now: int, prefs: dict | None = None) -> dict:
    """Advance the lifecycle one run. Returns {"alerts": [...], "telemetry": {...}} and mutates st."""
    prefs = prefs or {}
    floor = SEV.index(prefs.get("minSeverity", "LOW"))
    mutes = set(prefs.get("mute") or [])
    quiet = prefs.get("quietHours")
    digest_mode = prefs.get("digest", False)
    tel = {"alerts": 0, "newEpisodes": 0, "suppressedUnchanged": 0, "belowFloor": 0, "muted": 0, "deferred": 0,
           "skippedUnavailable": 0, "heldUnobserved": 0, "resolved": 0, "cooling": 0, "reminders": 0, "delivered": 0, "deliveryFailed": 0,
           "heldStale": 0, "heldInvalid": 0, "notAdmitted": 0, "notAdmittedDetail": []}
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
        why = admit(s, probes)
        if why:
            inc = inc_all.get(k)
            if inc is None or inc["state"] == "RESOLVED":
                tel["notAdmitted"] += 1
                tel["notAdmittedDetail"].append({"key": k, "reason": why})
            else:
                stale = why.startswith("source ")
                tel["heldStale" if stale else "heldInvalid"] += 1
                _hist(inc, now, "HELD_STALE" if stale else "HELD_INVALID", f"{why}; last confirmed state retained ({inc.get('lastConfirmedAt')})")
            continue
        if s["source"] in EVENT_SOURCES:
            r = _event_step(inc_all, s, now, tel)
            if r:
                raw_alerts.append((s, inc_all[k], r, 1.0))
            continue
        mag, _v = _probe(probes, k)
        if mag is None:
            mag = 1.0 + ((s.get("metrics") or {}).get("rank") or 0) / 100 if s["source"] == "cross" else 1.0
        tx = set((s.get("metrics") or {}).get("distinctTx") or [])
        inc = inc_all.get(k)
        reason = None
        new_members = list((s.get("metrics") or {}).get("memberKeys") or [])
        if inc is not None and inc["state"] not in CLOSED and new_members and inc.get("members") and not set(new_members) & set(inc["members"]):
            _close(inc, now, "SUPERSEDED", "recomputed with a disjoint member set: a different event instance, new episode")  # R5-03
        if inc is None or inc["state"] in CLOSED:
            ep = (inc["episode"] + 1) if inc else 1
            prev_eps = ((inc.get("previousEpisodes") or []) + [_summary(inc)])[-10:] if inc else []
            inc = {"id": f"{k}#e{ep}", "key": k, "episode": ep, "state": "NEW", "source": s["source"], "openedAt": now, "lastSeenAt": now,
                   "severity": s["severity"], "entryMagnitude": mag, "lastMagnitude": mag, "lastAlertMagnitude": mag, "peakMagnitude": mag,
                   "belowCount": 0, "distinctTx": sorted(tx), "lastAlertAt": None, "lastConfirmedAt": now,
                   "members": list((s.get("metrics") or {}).get("memberKeys") or []), "remindedAt": None, "history": [], "title": s["title"],
                   "memberLastValid": {}, "previousEpisodes": prev_eps}
            inc_all[k] = inc
            _hist(inc, now, "ENTERED", f"episode {ep}")
            reason = "NEW_EPISODE" if ep > 1 else "NEW"
            tel["newEpisodes"] += 1
        else:
            inc["state"] = "ACTIVE"; inc["belowCount"] = 0; inc["lastSeenAt"] = now; inc["lastMagnitude"] = mag; inc["lastConfirmedAt"] = now
            inc.pop("unconfirmedSince", None)
            if (s.get("metrics") or {}).get("memberKeys"):
                _members(inc, list(s["metrics"]["memberKeys"]), probes, now)
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
        if k in seen_now or inc["state"] in CLOSED:
            continue
        src_state = source_state.get(inc["source"], "NOT_RUN")
        if inc.get("kind") == "event":  # R5-01: discrete events are archived by time, never "resolved"; outages don't complete them
            if src_state in BAD or src_state == "NOT_RUN":
                tel["skippedUnavailable"] += 1
                _hist(inc, now, "SOURCE_UNAVAILABLE", f"{inc['source']} {src_state}: event evidence retained, archive clock paused")
            elif now - inc["lastNewEventAt"] >= EVENT_RETENTION_S:
                _archive_event(inc, now, tel)
            continue
        if inc["source"] != "cross" and (src_state in BAD or src_state == "NOT_RUN"):
            tel["skippedUnavailable"] += 1
            _hist(inc, now, "SOURCE_UNAVAILABLE", f"{inc['source']} {src_state}: last confirmed state retained")
            _age(inc, now, tel)
            continue
        keys = inc.get("members") or [k]
        obs = [_probe(probes, m) for m in keys]
        for m, (_, v) in zip(keys, obs):
            if v:
                inc.setdefault("memberLastValid", {})[m] = now
        if not all(v for _, v in obs):
            missing = [m for m, (_, v) in zip(keys, obs) if not v]
            tel["heldUnobserved"] += 1
            _hist(inc, now, "HELD_UNOBSERVED", f"not validly observed this run ({', '.join(missing[:3])}); last confirmed {inc.get('lastConfirmedAt')}")
            _age(inc, now, tel, missing)
            continue
        # R4-01: a multi-member incident cools only when EVERY member is validly below exit: the hottest member decides
        r = max(x for x, _ in obs)
        inc["lastMagnitude"] = r
        inc.pop("unconfirmedSince", None)
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
        if inc.get("kind") == "event":
            s = dict(s, newEventIds=list(inc.get("newEventIds") or []))
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
        for k in sorted((k for k, v in inc_all.items() if v["state"] in CLOSED), key=lambda k: inc_all[k].get("resolvedAt") or inc_all[k].get("archivedAt") or 0)[:len(inc_all) - 3000]:
            del inc_all[k]
    return {"alerts": alerts, "telemetry": tel, "baseline": first_run}


def deliver(st: dict, alerts: list[dict], send, tel: dict | None = None, max_attempts: int = 5) -> dict:
    """Webhook outbox (AT-LEAST-ONCE: a crash between a successful POST and saving state re-sends the same alertId;
    receivers must dedupe by alertId). Retry exhaustion moves the item to a bounded dead-letter list (retry_dead_letter).
    Queue alerts, try every pending item via send(alert) -> bool, count delivered only on success,
    keep failures for the next run (bounded attempts). Restart-safe: the outbox and sent ids live in the state."""
    tel = tel if tel is not None else {}
    box = st.setdefault("outbox", [])
    sent = st.setdefault("sentIds", [])
    known = {x["alert"]["alertId"] for x in box} | set(sent)
    for a in alerts:
        if a["alertId"] not in known:
            box.append({"alert": a, "attempts": 0}); known.add(a["alertId"])
    keep = []
    dead = list(st.get("deadLetter") or [])
    for item in box:
        ok, err = False, None
        try:
            ok = bool(send(item["alert"]))
        except Exception as e:  # noqa: BLE001 - a failed webhook must not stop the scan
            ok, err = False, type(e).__name__
        item["attempts"] += 1
        if ok:
            sent.append(item["alert"]["alertId"]); tel["delivered"] = tel.get("delivered", 0) + 1
        else:
            tel["deliveryFailed"] = tel.get("deliveryFailed", 0) + 1
            item["lastError"] = err or "non-2xx response"
            if item["attempts"] < max_attempts:
                keep.append(item)
            else:  # R4-06: retry exhaustion is a durable, user-visible terminal state, not a silent drop
                dead.append({"alert": item["alert"], "attempts": item["attempts"], "lastError": item["lastError"], "deadAt": int(time.time())})
    st["outbox"] = keep
    st["sentIds"] = sent[-2000:]
    st["deadLetter"] = dead[-DEAD_LETTER_MAX:]
    tel["pendingDelivery"] = len(keep)
    tel["deadLetter"] = len(st["deadLetter"])
    return tel


def retry_dead_letter(st: dict) -> int:
    """Explicit user action: move dead-lettered alerts back into the outbox with a fresh attempt budget."""
    dead = st.get("deadLetter") or []
    box = st.setdefault("outbox", [])
    for d in dead:
        box.append({"alert": d["alert"], "attempts": 0, "retriedFromDeadLetter": True})
    st["deadLetter"] = []
    return len(dead)
