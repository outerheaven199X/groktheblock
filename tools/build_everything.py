"""Everything-markets build.
  python3 tools/build_everything.py --fetch   # live keyless fetch -> data/everything/live-derived.json (+ snapshots in ./cache)
  python3 tools/build_everything.py           # regenerate universe.json, synthetic.json and ui/data/everything.js from files
  python3 tools/build_everything.py --check   # exit 1 if any generated file is stale (no network)
  python3 tools/build_everything.py --scheduled [--only=fx,mtg]   # opt-in scheduled refresh: only modules that are due; lock,
                                              # atomic writes, backoff, health log in cache/everything/refresh-log.jsonl
  See docs/everything/REFRESH.md for Windows Task Scheduler and cron setup.
Committed files hold ECB/EIA/H.10/CFTC values (redistributable) and only DERIVED numbers for vendor data."""
import json, math, random, sys, time
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib")); sys.path.insert(0, str(R / "tools"))
import universe_src  # noqa: E402
from grok_the_block.everything import detectors as X  # noqa: E402

DD = R / "data/everything"; UI = R / "ui/data/everything.js"; SNAP = R / "cache/everything"
CATS = ["FX", "Metals", "Energy", "Agriculture", "Rates", "Equities", "Crypto", "Prediction", "Sports", "Skins", "Cards", "Games",
        "Collectibles", "Digital", "Hardware", "Events", "Payments", "Environmental", "Logistics", "Real estate"]


def dump(o):
    return json.dumps(o, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


# ---------------- live ----------------
# Each module fetches independently. A module that fails (exception, timeout, 429/5xx after backoff, empty answer) keeps its
# previous good signals/probes/assets, marked STALE with lastSuccessAt preserved: a provider failure never clears findings
# and never turns "unknown" into "quiet". Cadences are per provider; --scheduled only runs modules that are due.
H_DAY, H_WEEK = 86400, 7 * 86400
CADENCE = {"fx": H_DAY, "metals": H_DAY, "energy": H_DAY, "cot": H_DAY, "mtg": H_DAY, "cs2": H_DAY, "markets": 6 * 3600}
PROVIDERS = {"fx": ["frankfurter", "ecb", "fred"], "metals": ["nasdaq"], "energy": ["fred"], "cot": ["cftc"], "mtg": ["scryfall"], "cs2": ["steam"],
             "markets": ["gamma", "clob", "pmdata", "kalshi", "yahoo", "nasdaq", "cboe", "treasury", "fred", "okx", "coinbase", "llama", "edgar"]}
MODULE_BUDGET_S = 900


def _spark(rows, n=90):
    return [round(r[1], 6) for r in rows[-n:]]


def mod_fx(ctx):
    from grok_the_block.everything import sources as SRC
    S, P, A, cov = [], [], [], []
    fx, via = SRC.ecb_fx()
    ecb_url = "https://data.ecb.europa.eu/data/datasets/EXR"
    if not fx:
        return None
    ctx["fx"] = fx
    for c, rows in sorted(fx.items()):
        s, p = X.daily_move("fx", "fx", f"EUR/{c}", f"EUR/{c}", rows, ecb_url, label="daily ECB reference-rate"); S += s; P += p
        A.append({"id": f"EUR/{c}", "universe": "fx-majors", "name": f"EUR/{c}", "last": rows[-1][1], "asOf": X._date(rows[-1][0]), "spark": _spark(rows), "redistributable": True})
    asof = max(r[-1][0] for r in fx.values())
    cov.append({"module": "fx", "status": "HEALTHY", "via": via, "observed": len(fx), "attribution": "Source: ECB statistics", "sourceAsOf": X._date(asof)})
    usd, h10 = fx.get("USD"), SRC.fred("DEXUSEU")
    if usd and h10:
        s, p = X.fx_crosscheck("EUR/USD", usd, h10, ecb_url, "https://fred.stlouisfed.org/series/DEXUSEU"); S += s; P += p
        cov.append({"module": "fx-h10", "status": "HEALTHY", "via": "FRED fredgraph (H.10 DEXUSEU)", "observed": 1, "sourceAsOf": X._date(h10[-1][0])})
    else:
        cov.append({"module": "fx-h10", "status": "UNAVAILABLE", "via": "FRED", "observed": 0})
    return S, P, A, cov


def mod_metals(ctx):
    from grok_the_block.everything import sources as SRC
    S, P, A, etf = [], [], [], {}
    for sym, nm in SRC.METAL_ETFS.items():
        rows = SRC.nasdaq_etf(sym); etf[sym] = rows
        u = f"https://www.nasdaq.com/market-activity/etf/{sym.lower()}/historical"
        if rows:
            s, p = X.daily_move("metals", "metals", sym, nm + " [ETF proxy]", rows, u, derived_only=True, extra_limits=["ETF closing price, a labelled proxy for spot metal."]); S += s; P += p
            A.append({"id": sym, "universe": {"GLD": "gold", "IAU": "gold", "SLV": "silver"}.get(sym, "pgm"), "name": nm, "asOf": X._date(rows[-1][0]), "redistributable": False})
        else:
            P.append(X.probe(sym, "MOVE_VS_REALIZED_VOL", None, "provider did not answer"))
    if not any(etf.values()):
        return None
    if etf.get("GLD") and etf.get("IAU"):
        s, p = X.pair_divergence("metals", "GLD~IAU", "Gold trackers GLD vs IAU", etf["GLD"], etf["IAU"], "https://www.nasdaq.com/market-activity/etf/gld/historical", "https://www.nasdaq.com/market-activity/etf/iau/historical"); S += s; P += p
    asof = max(r[-1][0] for r in etf.values() if r)
    return S, P, A, [{"module": "metals", "status": "HEALTHY" if all(etf.values()) else "DEGRADED", "via": "Nasdaq quote history (unofficial; derived only)", "observed": sum(1 for v in etf.values() if v), "sourceAsOf": X._date(asof)}]


def mod_energy(ctx):
    from grok_the_block.everything import sources as SRC
    S, P, A, ok, asof = [], [], [], 0, 0
    for sid, nm in SRC.ENERGY_FRED.items():
        rows = SRC.fred(sid)
        if rows:
            ok += 1; rows = rows[-400:]; asof = max(asof, rows[-1][0])
            s, p = X.daily_move("energy", "energy", sid, nm, rows, f"https://fred.stlouisfed.org/series/{sid}", label="daily EIA spot"); S += s; P += p
            A.append({"id": sid, "universe": "natgas" if sid == "DHHNGSP" else "crude", "name": nm, "last": rows[-1][1], "asOf": X._date(rows[-1][0]), "spark": _spark(rows), "redistributable": True})
    if not ok:
        return None
    return S, P, A, [{"module": "energy", "status": "HEALTHY" if ok == 3 else "DEGRADED", "via": "FRED fredgraph (EIA series)", "observed": ok, "attribution": "Source: U.S. Energy Information Administration", "sourceAsOf": X._date(asof)}]


def mod_cot(ctx):
    from grok_the_block.everything import sources as SRC
    S, P, A = [], [], []
    cot = SRC.cot()
    if not cot:
        return None
    for m, nm in SRC.COT_MARKETS.items():
        if m in cot:
            s, p = X.cot_shift(m, nm, cot[m], "https://publicreporting.cftc.gov/stories/s/r4w3-av2u"); S += s; P += p
            net = [(r["long"] - r["short"]) / r["oi"] * 100 for r in cot[m] if r["oi"]]
            A.append({"id": nm, "universe": "softs" if any(w in m for w in ("COFFEE", "COCOA")) else "grains" if "CHICAGO" in m else "cot", "name": nm, "asOf": X._date(cot[m][-1]["ts"]), "spark": [round(v, 2) for v in net[-60:]], "sparkLabel": "speculators' net % of OI", "redistributable": True})
    asof = max(v[-1]["ts"] for v in cot.values())
    return S, P, A, [{"module": "cot", "status": "HEALTHY", "via": "CFTC Public Reporting (Socrata 6dca-aqww)", "observed": len(cot), "sourceAsOf": X._date(asof)}]


def _usd_eur(ctx, prev):
    fx = ctx.get("fx")
    if fx and fx.get("USD"):
        return fx["USD"][-1][1], X._date(fx["USD"][-1][0])
    a = next((a for a in prev.get("assets", []) if a.get("id") == "EUR/USD"), None)
    return (a["last"], a["asOf"]) if a and a.get("last") else (None, None)


def mod_mtg(ctx):
    """Paper-pinned snapshot, one file per UTC day (idempotent: a second run the same day replaces that day's file).
    History is keyed by exact printing (set + collector number), so a re-pinned printing starts its own history."""
    from grok_the_block.everything import sources as SRC
    S, P, A = [], [], []
    cards = SRC.scryfall_snapshot()
    if not cards:
        return None
    now = ctx["now"]; day = time.strftime("%Y-%m-%d", time.gmtime(now))
    SNAP.joinpath("scryfall").mkdir(parents=True, exist_ok=True)
    atomic_write(SNAP / "scryfall" / f"{day}.json", json.dumps(cards))
    hist = {}
    for f in sorted((SNAP / "scryfall").glob("*.json")):
        ts = int(time.mktime(time.strptime(f.stem, "%Y-%m-%d")))
        try:
            rows = json.loads(f.read_text())
        except ValueError:
            continue  # a damaged snapshot is skipped, never trusted
        for c in rows:
            if c.get("usd") and c.get("cn"):
                hist.setdefault((c["set"], c["cn"]), []).append((ts, c["usd"]))
    for c in cards:
        c["ts"] = now
        s, p = X.snapshot_move("cards", "mtg", c["name"], c["name"], hist.get((c["set"], c["cn"]), []), c["url"]); S += s; P += p
        A.append({"id": c["name"], "universe": "mtg", "name": c["name"], "url": c["url"], "asOf": day, "redistributable": False,
                  "printing": {"provider": "scryfall", "id": c["id"], "set": c["set"], "cn": c["cn"], "lang": c["lang"], "finish": c["finish"], "paper": c["paper"]}})
    rate, fxd = _usd_eur(ctx, ctx["prev"])
    if rate:
        s, p = X.cross_venue_spread("cards", cards, rate, fxd); S += s; P += p
    days = len(list((SNAP / "scryfall").glob("*.json")))
    paper_days = len({ts for v in hist.values() for ts, _ in v})
    return S, P, A, [{"module": "mtg", "status": "HEALTHY", "via": "Scryfall /cards (paper printings pinned; derived only)", "observed": len(cards), "snapshotDays": paper_days, "snapshotFiles": days, "sourceAsOf": day}]


def mod_cs2(ctx):
    from grok_the_block.everything import sources as SRC
    skins = SRC.steam_snapshot()
    if not skins:
        return None
    day = time.strftime("%Y-%m-%d", time.gmtime(ctx["now"])); A = []
    for s in skins:
        s["ts"] = ctx["now"]
        A.append({"id": s["name"], "universe": "cs2-skins", "name": s["name"], "url": s["url"], "asOf": day, "redistributable": False})
    S, P = X.steam_ask_gap(skins)
    return S, P, A, [{"module": "cs2", "status": "HEALTHY", "via": "Steam priceoverview (undocumented; derived only; roadmap)", "observed": len(skins), "sourceAsOf": day}]


# --- prediction markets, equities/options, Treasury, crypto, SEC: the existing signals engine (markets.feed.run) ---
OUTCOME = {"HEALTHY": "FETCHED", "DEGRADED": "DEGRADED", "STALE": "DEGRADED", "UNAVAILABLE": "BLOCKED_EXTERNAL", "NOT_CONFIGURED": "NOT_CONFIGURED"}
# Raw provider values (volumes, prices) are kept only where the data is public-domain US-government data; for the
# rest the committed cache carries the derived observation (type, ratio, severity, time, link), never the vendor numbers.
RAW_OK = {"treasury", "sec", "cross", "macro"}
KEEP_METRICS = {"z", "ratio", "multiple", "rank", "granularity", "spanHours", "timingComparable", "movePct", "changeBp", "zRobust"}


def _scrub(t):
    """Drop provider dollar amounts from a title outside the quoted market question (the question text is its identity)."""
    import re
    t = re.sub(r"\s*\(≈\$[\d.,]+[KMB]?\s*premium\)", "", t or "")
    return re.sub(r"\$[\d,]+(?:\.\d+)?[KMB]? traded", "volume traded", t)


def derive_signal(s):
    keep = {k: s.get(k) for k in ("key", "source", "family", "relations", "type", "severity", "basis", "title", "when", "subject", "entities", "instrument", "evidence", "limits", "calendar")}
    keep["subject"] = {k: (s.get("subject") or {}).get(k) for k in ("name", "id", "url")} if s.get("subject") else None
    m = s.get("metrics") or {}
    if s.get("source") in RAW_OK:
        keep["what"] = s.get("what"); keep["metrics"] = m
    else:
        keep["what"] = "Derived observation: provider values are not stored in the committed cache. Follow the evidence link for the source data."
        keep["metrics"] = {k: v for k, v in m.items() if k in KEEP_METRICS and not isinstance(v, (list, dict))}
        keep["derivedOnly"] = True; keep["title"] = _scrub(keep["title"])
    keep["evidence"] = [{"label": e.get("label"), "url": e.get("url")} for e in (s.get("evidence") or []) if isinstance(e, dict)]
    return keep


def mod_markets(ctx):
    from grok_the_block.markets import feed as F
    rep = F.run(F.SOURCES)
    prev = (ctx["prev"].get("markets") or {})
    prev_sigs = {s["key"]: s for s in prev.get("signals", [])}
    st = rep.get("sourceStatus") or {}
    sigs = [derive_signal(s) for s in rep.get("signals", [])]
    # a source that failed this run keeps its previous signals (carried, marked stale): failure never clears a finding
    for k, v in st.items():
        if v["state"] in ("UNAVAILABLE", "STALE"):
            for s in prev_sigs.values():
                if s["source"] == k and s["key"] not in {x["key"] for x in sigs}:
                    sigs.append(dict(s, carried=True, limits=(s.get("limits") or []) + [f"Carried from the last successful {k} fetch; this run's fetch failed."]))
    status = {}
    for k, v in st.items():
        pv = (prev.get("sourceStatus") or {}).get(k, {})
        ok = v["state"] in ("HEALTHY", "DEGRADED")
        cov = v.get("coverage") or {}
        n_sig = sum(1 for s in sigs if s["source"] == k and not s.get("carried"))
        status[k] = {"state": v["state"], "outcome": OUTCOME.get(v["state"], "BLOCKED_EXTERNAL"), "detail": v.get("detail"),
                     "coverage": {kk: cov.get(kk) for kk in ("universe", "observed", "active24h", "sampleFraction", "exclusions", "priceHistory", "failedInstruments", "observedInstruments") if kk in cov},
                     "lastValidAt": v.get("lastValidAt") or pv.get("lastValidAt"), "lastValidTs": v.get("lastValidTs") or pv.get("lastValidTs"),
                     "lastAttemptAt": ctx["now"], "lastSuccessAt": ctx["now"] if ok else pv.get("lastSuccessAt"),
                     "assessment": ("quiet" if not n_sig else "findings") if ok else "unknown", "signals": n_sig}
    return {"kind": "signals", "version": 2, "generatedAt": rep["generatedAt"], "derivedOnly": True, "sources": rep.get("sources"),
            "status": rep.get("status"), "sourceStatus": status, "signals": sigs, "counts": rep.get("counts"),
            "assessment": {k: rep["assessment"].get(k) for k in ("severity", "lead")} if rep.get("assessment") else {},
            "coverage": {"limits": rep["coverage"]["limits"], "matrix": [dict(m, outcome=OUTCOME.get(m["status"], "BLOCKED_EXTERNAL")) for m in rep["coverage"]["matrix"]]},
            "calendar": rep.get("calendar"), "disclaimer": rep.get("disclaimer"),
            "_note": "Real cached derived signals from the last markets refresh (prediction markets, equities, options, Treasury, crypto). Not live."}


MODULES = {"fx": mod_fx, "metals": mod_metals, "energy": mod_energy, "cot": mod_cot, "mtg": mod_mtg, "cs2": mod_cs2, "markets": mod_markets}


def atomic_write(path, text):
    import os
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with open(tmp, "w") as fh:
        fh.write(text); fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, path)


class Lock:
    """Single-run lock (O_EXCL lock file with pid + time). A lock left by a killed run is reclaimed when its pid is gone
    or it is older than 2 h."""
    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        import os
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "at": int(time.time())}).encode()); os.close(fd)
                return self
            except FileExistsError:
                try:
                    info = json.loads(self.path.read_text() or "{}")
                except ValueError:
                    info = {}
                alive = False
                try:
                    if info.get("pid"):
                        os.kill(int(info["pid"]), 0); alive = True
                except (OSError, ValueError):
                    alive = False
                if alive and time.time() - info.get("at", 0) < 7200:
                    raise SystemExit(f"refresh already running (pid {info['pid']}); exiting without touching the cache")
                log_event({"event": "stale_lock_reclaimed", "lock": info})
                self.path.unlink(missing_ok=True)
        raise SystemExit("could not take the refresh lock")

    def __exit__(self, *a):
        self.path.unlink(missing_ok=True)


def log_event(ev):
    SNAP.mkdir(parents=True, exist_ok=True)
    with open(SNAP / "refresh-log.jsonl", "a") as fh:
        fh.write(json.dumps(dict(ev, at=ev.get("at") or int(time.time()), atIso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))) + "\n")


def _err_category(mod, exc=None):
    from grok_the_block.markets import http as HT
    if exc is not None:
        n = type(exc).__name__.lower()
        return "timeout" if "timeout" in n else "interrupted" if "interrupt" in n else "exception:" + type(exc).__name__
    errs = [HT.LAST_ERR[p] for p in PROVIDERS.get(mod, []) if p in HT.LAST_ERR]
    return errs[0] if errs else "no_data"


class _Budget(Exception):
    pass


def fetch(only=None, scheduled=False):
    import signal
    now = int(time.time())
    prev = json.loads((DD / "live-derived.json").read_text()) if (DD / "live-derived.json").exists() else {}
    prev_mk = json.loads((DD / "markets-derived.json").read_text()) if (DD / "markets-derived.json").exists() else {}
    prev["markets"] = prev_mk
    health = {h["module"]: h for h in prev.get("health", [])}
    ctx = {"now": now, "prev": prev}
    sigs, probes, assets, cov, out_health, markets = [], [], [], [], [], prev_mk or None
    by_mod = lambda xs, m: [x for x in xs if x.get("module") == m]  # noqa: E731
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    log_event({"event": "run_start", "run": run_id, "only": only, "scheduled": scheduled})
    for m, fn in MODULES.items():
        h = dict(health.get(m) or {"module": m}); h["cadenceS"] = CADENCE[m]
        due = (not only or m in only) and (not scheduled or now - (h.get("lastSuccessAt") or 0) >= CADENCE[m] - 600)
        res, err = None, None
        if due:
            h["lastAttemptAt"] = now
            t0 = time.time()
            if hasattr(signal, "SIGALRM"):
                signal.signal(signal.SIGALRM, lambda *a: (_ for _ in ()).throw(_Budget("module budget exceeded")))
                signal.alarm(MODULE_BUDGET_S)
            try:
                res = fn(ctx)
            except _Budget as e:
                err = "timeout:module_budget"; res = None; _ = e
            except Exception as e:  # noqa: BLE001 - one module's failure must not stop the others or corrupt the cache
                err = _err_category(m, e); res = None
            finally:
                if hasattr(signal, "SIGALRM"):
                    signal.alarm(0)
            if res is None and err is None:
                err = _err_category(m)
            log_event({"event": "module", "run": run_id, "module": m, "ok": res is not None, "error": err, "seconds": round(time.time() - t0, 1)})
        if m == "markets":
            if res is not None:
                markets = res; h.update(status="HEALTHY" if res.get("status") == "ok" else "DEGRADED", lastSuccessAt=now, errorCategory=None, sourceAsOf=time.strftime("%Y-%m-%d", time.gmtime(res["generatedAt"])))
            elif due:
                h.update(status="STALE" if markets else "UNAVAILABLE", errorCategory=err)
                if markets:
                    markets = dict(markets, stale=True, lastAttemptAt=now, lastError=err)
            h["nextExpectedRun"] = (h.get("lastSuccessAt") or now) + CADENCE[m]
            out_health.append(h); continue
        if res is not None:
            S, P, A, C = res
            for x in S + P + A + C:
                x["module"] = x.get("module") if x in C else m
            sigs += S; probes += P; assets += A
            for c in C:
                c.update(lastAttemptAt=now, lastSuccessAt=now)
            cov += C
            h.update(status=C[0]["status"], lastSuccessAt=now, errorCategory=None, sourceAsOf=C[0].get("sourceAsOf"))
        else:
            # keep the last good data for this module; mark it stale (or unavailable if there never was any)
            ps, pp, pa = by_mod(prev.get("signals", []), m), by_mod(prev.get("probes", []), m), by_mod(prev.get("assets", []), m)
            sigs += ps; probes += pp; assets += pa
            pc = [c for c in prev.get("coverage", []) if c.get("module") == m or (m == "fx" and c.get("module") == "fx-h10")]
            for c in pc or [{"module": m, "via": m, "observed": 0}]:
                c = dict(c)
                if due:
                    c.update(status="STALE" if (pa or ps) else "UNAVAILABLE", lastAttemptAt=now, errorCategory=err)
                cov.append(c)
            if due:
                h.update(status="STALE" if (pa or ps) else "UNAVAILABLE", errorCategory=err)
        h["nextExpectedRun"] = (h.get("lastSuccessAt") or now) + CADENCE[m]
        out_health.append(h)
    out = {"kind": "everything", "generatedAt": now, "synthetic": False, "signals": sigs, "probes": probes, "coverage": cov, "assets": assets, "health": out_health,
           "lastRun": {"id": run_id, "at": now, "scheduled": scheduled, "only": only, "ok": all(h.get("errorCategory") is None for h in out_health if h.get("lastAttemptAt") == now)}}
    keys = [s["key"] for s in sigs]
    assert len(keys) == len(set(keys)), "duplicate event ids in live-derived"
    atomic_write(DD / "live-derived.json", json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    if markets:
        atomic_write(DD / "markets-derived.json", json.dumps(markets, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    log_event({"event": "run_end", "run": run_id, "ok": out["lastRun"]["ok"], "health": {h["module"]: [h.get("status"), h.get("errorCategory")] for h in out_health}})
    print(f"live: {len(sigs)} signals, {len(probes)} probes, {len(assets)} assets; " + ", ".join(f"{h['module']}={h.get('status')}" + (f"({h['errorCategory']})" if h.get("errorCategory") else "") for h in out_health))
    return out


# ---------------- synthetic examples (deterministic) ----------------
def synthetic():
    rnd = random.Random(20261028); t0 = 1790000000; day = 86400; sigs, probes = [], []
    U = "https://example.invalid/synthetic"

    def sales(n, base, grades, spread=0.05, start=t0):
        out = []
        for i in range(n):
            g = grades[i % len(grades)]
            out.append({"ts": start + i * day // 2, "price": round(base[g] * (1 + rnd.uniform(-spread, spread)), 2), "grade": g})
        return out

    def run(res):
        s, p = res; sigs.extend(s); probes.extend(p)
    # 1. outlier sale, repeated -> MEDIUM
    ss = sales(24, {"CIB": 420.0, "loose": 180.0}, ["CIB", "loose"], spread=0.18)
    last = ss[-1]["ts"]
    ss += [{"ts": last + day, "price": 1290.0, "grade": "CIB"}, {"ts": last + 2 * day, "price": 1340.0, "grade": "CIB"}]
    run(X.outlier_sale("games", "synthetic", "SYN-SNES-RPG", "Example SNES RPG cartridge", ss, U, synthetic=True))
    # 2. grade-mix shift
    prev = sales(12, {"raw": 40.0, "PSA 10": 400.0}, ["raw", "raw", "raw", "PSA 10"])
    cur = sales(12, {"raw": 41.0, "PSA 10": 405.0}, ["raw", "PSA 10"], start=t0 + 30 * day)
    run(X.grade_mix("cards", "synthetic", "SYN-HOLO-CARD", "Example holo trading card", prev, cur, U, synthetic=True))
    # 3. wash / round-trip pattern
    w = [{"ts": t0 + 40 * day + i * day, "price": p, "grade": "PSA 9"} for i, p in enumerate([250, 310, 250, 310, 250, 310, 250])]
    run(X.wash_pattern("cards", "synthetic", "SYN-SPORTS-CARD", "Example rookie sports card", w, U, synthetic=True))
    # 4. supply shock (graded population jump)
    counts = [(t0 + i * day, 120 + rnd.randint(-3, 3)) for i in range(30)] + [(t0 + 30 * day, 410)]
    run(X.supply_shock("cards", "synthetic", "SYN-POP-REPORT", "Example PSA 10 population", counts, U, synthetic=True))
    # 5. guide lag
    gs = sales(10, {"NM": 95.0}, ["NM"])
    run(X.guide_divergence("collectibles", "synthetic", "SYN-COMIC", "Example key-issue comic (CGC 9.8)", 60.0, gs, U, synthetic=True))
    # 6. CS2 skin ask gap + thin market
    run(X.steam_ask_gap([{"name": "SYN skin (Field-Tested)", "lowest": 71.0, "median": 52.0, "volume24h": 40, "url": U, "ts": t0},
                         {"name": "SYN sticker capsule", "lowest": 3.1, "median": 3.0, "volume24h": 1, "url": U, "ts": t0}]))
    for s in sigs:
        if not s["synthetic"]:
            s["synthetic"] = True; s["title"] = "[SYNTHETIC] " + s["title"]
    # 7. sneaker/watch cross-venue spread (synthetic)
    run(X.cross_venue_spread("collectibles", [{"name": "SYN sneaker (size 10)", "usd": 420.0, "eur": 230.0, "url": U, "ts": t0}], 1.08, "synthetic", source="synthetic"))
    sigs[-1]["synthetic"] = True; sigs[-1]["title"] = "[SYNTHETIC] " + sigs[-1]["title"]
    # 8. sparse gate (unknown, not quiet)
    probes.append(X.sparse_gate("SYN-RARE-WATCH", [{"ts": t0, "price": 9000}], 5))
    for p in probes:
        p["module"] = "synthetic"
    return {"kind": "everything", "synthetic": True, "note": "Synthetic examples only: invented items and prices that exercise the thin-market detectors. Not real market data.", "signals": sigs, "probes": probes}


def universe_md(uni):
    st = {"shipped": "Shipped (this branch or main)", "feasible-next": "Feasible next", "blocked-licence": "Blocked by licence"}
    out = ["# Asset universe: everything people trade or arbitrage", "",
           "Generated by `tools/build_everything.py` from `tools/universe_src.py` (also `data/everything/universe.json`). Do not edit by hand.",
           "Checked 2026-10-28. **Verified = yes** means the access or terms page was read live that day; **no** means it comes from memory or secondary sources and must be confirmed before anything is built on it.",
           "Access: *free-redistributable* (raw values may be shown with attribution), *derived-signals-only* (show z-scores, % moves and counts plus a link, never price tables), *paid*, *partner-only*, *blocked* (no licensed path found).", ""]
    for k in ("shipped", "feasible-next", "blocked-licence"):
        out.append(f"- {st[k]}: {sum(1 for u in uni if u['status'] == k)}")
    out += ["", f"Total: {len(uni)} asset classes.", ""]
    for c in CATS:
        rows = [u for u in uni if u["category"] == c]
        if not rows:
            continue
        out += [f"## {c}", "", "| Asset class | Venues | Common arbitrage pattern | Best data source | Access | Status | Verified | Notes |", "|---|---|---|---|---|---|---|---|"]
        for u in rows:
            out.append(f"| {u['name']} | {u['venues']} | {u['arbitrage']} | [{u['source']}]({u['sourceUrl']}) | {u['access']} | {st[u['status']]} | {'yes' if u['verified'] else 'no'} | {u['note']} |")
        out.append("")
    return "\n".join(out)


def render():
    uni = universe_src.rows()
    live = json.loads((DD / "live-derived.json").read_text()) if (DD / "live-derived.json").exists() else {"signals": [], "probes": [], "coverage": [], "assets": []}
    mk = json.loads((DD / "markets-derived.json").read_text()) if (DD / "markets-derived.json").exists() else None
    syn = synthetic()
    files = {DD / "universe.json": dump({"categories": CATS, "assets": uni}), DD / "synthetic.json": dump(syn)}
    body = json.dumps({"categories": CATS, "universe": uni, "live": live, "synthetic": syn, "markets": mk}, ensure_ascii=False, separators=(",", ":"))
    files[R / "docs/everything/UNIVERSE.md"] = universe_md(uni)
    files[UI] = "// GENERATED by tools/build_everything.py from data/everything/*.json. Real cached derived signals + synthetic examples (flagged). Do not edit.\nwindow.GTB_EVERYTHING=" + body + ";\n"
    return files


if __name__ == "__main__":
    DD.mkdir(parents=True, exist_ok=True)
    only = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--only=")), None)
    if "--fetch" in sys.argv or "--scheduled" in sys.argv:
        with Lock(SNAP / "refresh.lock"):
            fetch(only=only, scheduled="--scheduled" in sys.argv)
            files = render()
            for p, s in files.items():
                atomic_write(p, s)
            print("rendered", len(files), "files")
            import subprocess  # keep docs/assets-manifest.json hashes in step with the refreshed data files
            subprocess.run([sys.executable, str(R / "tools/build_asset_manifest.py")], cwd=R, check=False)
        sys.exit(0)
    files = render()
    if "--check" in sys.argv:
        stale = [str(p.relative_to(R)) for p, s in files.items() if not p.exists() or p.read_text() != s]
        print("everything data", "up to date" if not stale else "STALE: " + ", ".join(stale)); sys.exit(1 if stale else 0)
    for p, s in files.items():
        atomic_write(p, s); print("wrote", p.relative_to(R), len(s))
