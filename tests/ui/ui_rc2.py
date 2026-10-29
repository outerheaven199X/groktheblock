"""RC2 checks in Chromium EMULATION (Playwright + SwiftShader), CSP ENFORCED. Not real devices or GPUs.
Usage: python3 tests/ui/ui_rc2.py [base-url]   (serve the repo root: python3 -m http.server 8821)
Covers: real cached markets report drives the prediction/equity/options/Treasury/crypto tools; quiet-but-assessed renders
"No findings in the assessed markets" with coverage; failing/unconfigured sources render "Unknown / not assessed" and
are never counted quiet; a STALE module shows its error and data age; Anomalies coverage table; no synthetic row in the
default Real cached feed; MTG tracked printings are paper; no off-origin requests, CSP violations or page errors."""
import json, os, re, sys
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
U = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8821/ui/"
O = urlparse(U); ORIGIN = f"{O.scheme}://{O.netloc}"
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R = []
def res(n, ok, d=""): print("PASS" if ok else "FAIL", n, "-", str(d)[:300]); R.append(bool(ok))

def page(b, **kw):
    ctx = b.new_context(**kw); pg = ctx.new_page(); pg.errs = []; pg.off = []
    pg.on("pageerror", lambda e: pg.errs.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and pg.errs.append(m.text))
    pg.on("request", lambda r: (not r.url.startswith((ORIGIN, "data:", "blob:"))) and pg.off.append(r.url))
    pg.add_init_script("document.addEventListener('securitypolicyviolation', e => (window.__csp = window.__csp || []).push(e.violatedDirective + ' ' + e.blockedURI))")
    return ctx, pg

def boot(pg, h=""):
    pg.goto(U + h); pg.wait_for_function("window.GTB&&GTB.ready"); pg.wait_for_timeout(300)

def panel(pg): return pg.evaluate("document.getElementById('panel').textContent")

def degraded_everything():
    """everything.js with kalshi + polymarket blocked, equities not configured, fx STALE (timeout): an outage, simulated in the page only."""
    src = open(os.path.join(REPO, "ui/data/everything.js")).read()
    j = json.loads(src[src.index("=") + 1:].rstrip().rstrip(";"))
    for k in ("kalshi", "polymarket"):
        j["markets"]["sourceStatus"][k].update(state="UNAVAILABLE", outcome="BLOCKED_EXTERNAL", assessment="unknown", detail="HTTP 403 (simulated)")
    j["markets"]["signals"] = [s for s in j["markets"]["signals"] if s["source"] not in ("kalshi", "polymarket", "cross")]
    j["markets"]["sourceStatus"]["equities"].update(state="NOT_CONFIGURED", outcome="NOT_CONFIGURED", assessment="unknown", detail="simulated")
    for c in j["live"]["coverage"]:
        if c["module"] == "fx": c.update(status="STALE", errorCategory="timeout")
    return "window.GTB_EVERYTHING=" + json.dumps(j) + ";\n"

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=GL)
    ctx, pg = page(b, viewport={"width": 1440, "height": 900}); boot(pg)
    M = pg.evaluate("GTB_EV.EV.markets")
    res("real cached markets report is loaded and first", M is not None and pg.evaluate("GTB.REPORTS.filter(r=>r.k==='signals')[0].name") == "markets-live-derived.json")
    st = M["sourceStatus"]
    res("every markets source has an outcome in FETCHED/DEGRADED/BLOCKED_EXTERNAL/NOT_CONFIGURED", all(v["outcome"] in ("FETCHED", "DEGRADED", "BLOCKED_EXTERNAL", "NOT_CONFIGURED") for v in st.values()), {k: v["outcome"] for k, v in st.items()})
    res("prediction/equities/options/treasury/crypto were all attempted", all(k in st for k in ("polymarket", "kalshi", "equities", "options", "treasury", "crypto")), sorted(st))
    # Each tool: findings list, quiet text, or unknown, consistent with the data
    bad = {}
    for fid in ("pm.odds", "pm.volume", "eq.signals", "eq.options", "rt.treasury", "crypto.market", "eq.sec"):
        pg.evaluate(f"GTB.goFeat('{fid}')"); pg.wait_for_timeout(60)
        t = panel(pg); src = pg.evaluate(f"GTB_REGISTRY.byId['{fid}'].route.src"); types = pg.evaluate(f"GTB_REGISTRY.byId['{fid}'].route.types||null")
        n = sum(1 for s in M["signals"] if s["source"] in src and (not types or s["type"] in types))
        ok_src = [k for k in src if k in st and st[k]["state"] in ("HEALTHY", "DEGRADED")]
        unk_src = [k for k in src if k not in st or st[k]["state"] not in ("HEALTHY", "DEGRADED")]
        items = pg.locator("#panel details.it").count()
        exp_ok = (items == n) if n else ((("No findings in the assessed markets" in t) == bool(ok_src)) and ("Nothing past threshold" not in t))
        if unk_src and not n: exp_ok = exp_ok and "Unknown / not assessed" in t
        if not exp_ok: bad[fid] = (n, items, ok_src, unk_src, t[:120])
    res("tools show findings, 'No findings in the assessed markets' or 'Unknown / not assessed' exactly as the data says", not bad, bad)
    pg.evaluate("GTB.goFeat('rt.treasury')"); pg.wait_for_timeout(60); t = panel(pg)
    res("Treasury tool shows source outcome, observed-at and data age", "treasury" in t and ("FETCHED" in t or "DEGRADED" in t or "BLOCKED_EXTERNAL" in t) and re.search(r"(h old|days old|under 1h old)", t), t[:200])
    res("no tool claims LIVE data", not re.search(r"\bLIVE\b", pg.evaluate("document.body.innerText")))
    # Anomalies default feed
    pg.evaluate("GTB.go('anomalies')"); pg.wait_for_timeout(120)
    items = pg.evaluate("GTB.anomalyItems().filter(x=>x.mode==='cached')")
    res("default Real cached feed has no synthetic or experimental item", all(not re.search(r"SYN|synthetic|example", (i.get("source") or "") + i["key"], re.I) and i["source"] != "cs2" for i in items), len(items))
    t = panel(pg)
    res("Anomalies shows a Coverage table with assessed-quiet and unknown sources", "Coverage" in t and "unknown, not assessed" in t and ("assessed, quiet" in t or "finding" in t), t[:200])
    res("Anomalies states cached data age, not live", "Not live" in t and re.search(r"(h old|days old|under 1h old)", t))
    pg.evaluate("GTB.go('tcg')"); pg.wait_for_timeout(200)
    tr = pg.evaluate("(GTB_TCG_CACHE&&GTB_TCG_CACHE.tracked||[]).filter(t=>['Black Lotus','Mox Sapphire','Ancestral Recall','Time Walk','Timetwister','Underground Sea','Volcanic Island','Mox Diamond'].includes(t.name)).map(t=>t.set)")
    res("Power 9 / duals / Mox Diamond are bound to paper printings (2ED/STH), not VMA/TPR", tr and all(s in ("2ed", "sth") for s in tr), tr)
    res("no page errors", not pg.errs, pg.errs[:3]); res("no off-origin requests", not pg.off, pg.off[:3]); res("no CSP violations", not pg.evaluate("window.__csp||[]"), pg.evaluate("window.__csp||[]"))
    ctx.close()
    # simulated outage (page-only): blocked prediction venues, unconfigured equities, stale FX
    ctx, pg = page(b, viewport={"width": 1440, "height": 900})
    body = degraded_everything()
    pg.route("**/data/everything.js", lambda r: r.fulfill(status=200, content_type="application/javascript", body=body)); boot(pg)
    pg.evaluate("GTB.goFeat('pm.odds')"); pg.wait_for_timeout(60); t = panel(pg)
    res("outage: prediction tools say Unknown / not assessed, never quiet", "Unknown / not assessed" in t and "BLOCKED_EXTERNAL" in t and "No findings in the assessed" not in t, t[:200])
    pg.evaluate("GTB.goFeat('eq.signals')"); pg.wait_for_timeout(60); t = panel(pg)
    res("outage: unconfigured equities say Unknown / not assessed", "Unknown / not assessed" in t and "NOT_CONFIGURED" in t, t[:200])
    pg.evaluate("GTB.goFeat('fx.rates')"); pg.wait_for_timeout(60); t = panel(pg)
    res("outage: stale FX module shows STALE with its error category, cached data still shown", "STALE (timeout)" in t and "EUR/USD" in t, t[:300])
    pg.evaluate("GTB.go('anomalies')"); pg.wait_for_timeout(100); t = panel(pg)
    res("outage: Anomalies coverage lists the blocked venues as unknown", t.count("unknown, not assessed") >= 3, t[:200])
    res("outage: no page errors / off-origin / CSP", not pg.errs and not pg.off and not pg.evaluate("window.__csp||[]"), (pg.errs[:2], pg.off[:2]))
    ctx.close()
    # mobile: tool status table does not overflow
    ctx, pg = page(b, viewport={"width": 375, "height": 812}, device_scale_factor=2, is_mobile=True, has_touch=True); boot(pg)
    over = {}
    for fid in ("pm.odds", "rt.treasury", "eq.options"):
        pg.evaluate(f"GTB.goFeat('{fid}')"); pg.wait_for_timeout(80)
        w = pg.evaluate("document.documentElement.scrollWidth")
        if w > 376: over[fid] = w
    pg.evaluate("GTB.go('anomalies')"); pg.wait_for_timeout(100)
    if pg.evaluate("document.documentElement.scrollWidth") > 376: over["anomalies"] = pg.evaluate("document.documentElement.scrollWidth")
    res("375px: markets tools and Anomalies have no horizontal overflow", not over, over)
    ctx.close(); b.close()
print(f"{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
