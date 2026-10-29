"""Everything-markets build.
  python3 tools/build_everything.py --fetch   # live keyless fetch -> data/everything/live-derived.json (+ snapshots in ./cache)
  python3 tools/build_everything.py           # regenerate universe.json, synthetic.json and ui/data/everything.js from files
  python3 tools/build_everything.py --check   # exit 1 if any generated file is stale (no network)
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
def fetch():
    from grok_the_block.everything import sources as SRC
    now = int(time.time()); sigs, probes, cov, assets = [], [], [], []

    def add(res, mod):
        s, p = res
        for x in p:
            x["module"] = mod
        sigs.extend(s); probes.extend(p)

    def spark(rows, n=90):
        return [round(r[1], 6) for r in rows[-n:]]

    # FX
    fx, via = SRC.ecb_fx()
    ecb_url = "https://data.ecb.europa.eu/data/datasets/EXR"
    if fx:
        for c, rows in sorted(fx.items()):
            add(X.daily_move("fx", "fx", f"EUR/{c}", f"EUR/{c}", rows, ecb_url, label="daily ECB reference-rate"), "fx")
            assets.append({"id": f"EUR/{c}", "universe": "fx-majors", "name": f"EUR/{c}", "last": rows[-1][1], "asOf": X._date(rows[-1][0]), "spark": spark(rows), "redistributable": True})
        cov.append({"module": "fx", "status": "HEALTHY", "via": via, "observed": len(fx), "attribution": "Source: ECB statistics"})
        usd = fx.get("USD")
        h10 = SRC.fred("DEXUSEU")
        if usd and h10:
            add(X.fx_crosscheck("EUR/USD", usd, h10, ecb_url, "https://fred.stlouisfed.org/series/DEXUSEU"), "fx")
            cov.append({"module": "fx-h10", "status": "HEALTHY", "via": "FRED fredgraph (H.10 DEXUSEU)", "observed": 1})
        else:
            cov.append({"module": "fx-h10", "status": "UNAVAILABLE", "via": "FRED", "observed": 0})
    else:
        cov.append({"module": "fx", "status": "UNAVAILABLE", "via": "ECB + Frankfurter", "observed": 0})
    # metals (ETF proxies, derived only)
    etf = {}
    for sym, nm in SRC.METAL_ETFS.items():
        rows = SRC.nasdaq_etf(sym); etf[sym] = rows
        u = f"https://www.nasdaq.com/market-activity/etf/{sym.lower()}/historical"
        if rows:
            add(X.daily_move("metals", "metals", sym, nm + " [ETF proxy]", rows, u, derived_only=True, extra_limits=["ETF closing price, a labelled proxy for spot metal."]), "metals")
            assets.append({"id": sym, "universe": {"GLD": "gold", "IAU": "gold", "SLV": "silver"}.get(sym, "pgm"), "name": nm, "asOf": X._date(rows[-1][0]), "redistributable": False})
        else:
            probes.append({**X.probe(sym, "MOVE_VS_REALIZED_VOL", None, "provider did not answer"), "module": "metals"})
    if etf.get("GLD") and etf.get("IAU"):
        add(X.pair_divergence("metals", "GLD~IAU", "Gold trackers GLD vs IAU", etf["GLD"], etf["IAU"], "https://www.nasdaq.com/market-activity/etf/gld/historical", "https://www.nasdaq.com/market-activity/etf/iau/historical"), "metals")
    cov.append({"module": "metals", "status": "HEALTHY" if all(etf.values()) else "DEGRADED", "via": "Nasdaq quote history (unofficial; derived only)", "observed": sum(1 for v in etf.values() if v)})
    # energy (EIA via FRED)
    ok = 0
    for sid, nm in SRC.ENERGY_FRED.items():
        rows = SRC.fred(sid)
        if rows:
            ok += 1; rows = rows[-400:]
            add(X.daily_move("energy", "energy", sid, nm, rows, f"https://fred.stlouisfed.org/series/{sid}", label="daily EIA spot"), "energy")
            assets.append({"id": sid, "universe": "natgas" if sid == "DHHNGSP" else "crude", "name": nm, "last": rows[-1][1], "asOf": X._date(rows[-1][0]), "spark": spark(rows), "redistributable": True})
    cov.append({"module": "energy", "status": "HEALTHY" if ok == 3 else "DEGRADED" if ok else "UNAVAILABLE", "via": "FRED fredgraph (EIA series)", "observed": ok, "attribution": "Source: U.S. Energy Information Administration"})
    # COT
    cot = SRC.cot()
    if cot:
        for m, nm in SRC.COT_MARKETS.items():
            if m in cot:
                add(X.cot_shift(m, nm, cot[m], "https://publicreporting.cftc.gov/stories/s/r4w3-av2u"), "cot")
                net = [(r["long"] - r["short"]) / r["oi"] * 100 for r in cot[m] if r["oi"]]
                assets.append({"id": nm, "universe": "softs" if any(w in m for w in ("COFFEE", "COCOA")) else "grains" if "CHICAGO" in m else "cot", "name": nm, "asOf": X._date(cot[m][-1]["ts"]), "spark": [round(v, 2) for v in net[-60:]], "sparkLabel": "speculators' net % of OI", "redistributable": True})
    cov.append({"module": "cot", "status": "HEALTHY" if cot else "UNAVAILABLE", "via": "CFTC Public Reporting (Socrata 6dca-aqww)", "observed": len(cot or {})})
    # MTG (Scryfall): today's snapshot + cross-venue spread + snapshot history gate
    cards = SRC.scryfall_snapshot()
    SNAP.joinpath("scryfall").mkdir(parents=True, exist_ok=True)
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    if cards:
        (SNAP / "scryfall" / f"{day}.json").write_text(json.dumps(cards))
    hist = {}
    for f in sorted((SNAP / "scryfall").glob("*.json")):
        ts = int(time.mktime(time.strptime(f.stem, "%Y-%m-%d")))
        for c in json.loads(f.read_text()):
            if c.get("usd"):
                hist.setdefault(c["name"], []).append((ts, c["usd"]))
    usd_eur = fx["USD"][-1] if fx and fx.get("USD") else None
    for c in cards:
        c["ts"] = now
        add(X.snapshot_move("cards", "mtg", c["name"], c["name"], hist.get(c["name"], []), c["url"]), "mtg")
        assets.append({"id": c["name"], "universe": "mtg", "name": c["name"], "url": c["url"], "asOf": day, "redistributable": False})
    if usd_eur and cards:
        add(X.cross_venue_spread("cards", cards, usd_eur[1], X._date(usd_eur[0])), "mtg")
    cov.append({"module": "mtg", "status": "HEALTHY" if cards else "UNAVAILABLE", "via": "Scryfall /cards/named (derived only)", "observed": len(cards), "snapshotDays": len(list((SNAP / "scryfall").glob("*.json")))})
    # CS2 (derived only, roadmap)
    skins = SRC.steam_snapshot()
    for s in skins:
        s["ts"] = now
        assets.append({"id": s["name"], "universe": "cs2-skins", "name": s["name"], "url": s["url"], "asOf": day, "redistributable": False})
    add(X.steam_ask_gap(skins), "cs2")
    cov.append({"module": "cs2", "status": "HEALTHY" if skins else "UNAVAILABLE", "via": "Steam priceoverview (undocumented; derived only; roadmap)", "observed": len(skins)})
    out = {"kind": "everything", "generatedAt": now, "synthetic": False, "signals": sigs, "probes": probes, "coverage": cov, "assets": assets}
    (DD / "live-derived.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(f"live: {len(sigs)} signals, {len(probes)} probes, {len(assets)} assets; " + ", ".join(f"{c['module']}={c['status']}" for c in cov))


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
    syn = synthetic()
    files = {DD / "universe.json": dump({"categories": CATS, "assets": uni}), DD / "synthetic.json": dump(syn)}
    body = json.dumps({"categories": CATS, "universe": uni, "live": live, "synthetic": syn}, ensure_ascii=False, separators=(",", ":"))
    files[R / "docs/everything/UNIVERSE.md"] = universe_md(uni)
    files[UI] = "// GENERATED by tools/build_everything.py from data/everything/*.json. Real cached derived signals + synthetic examples (flagged). Do not edit.\nwindow.GTB_EVERYTHING=" + body + ";\n"
    return files


if __name__ == "__main__":
    DD.mkdir(parents=True, exist_ok=True)
    if "--fetch" in sys.argv:
        fetch()
    files = render()
    if "--check" in sys.argv:
        stale = [str(p.relative_to(R)) for p, s in files.items() if not p.exists() or p.read_text() != s]
        print("everything data", "up to date" if not stale else "STALE: " + ", ".join(stale)); sys.exit(1 if stale else 0)
    for p, s in files.items():
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s); print("wrote", p.relative_to(R), len(s))
