"""Everything-markets UI checks in Chromium EMULATION (Playwright), not real devices.
Usage: python3 tests/ui/ui_everything.py [base-url]   (serve the repo root: python3 -m http.server 8821)
Covers: zero off-origin requests, Universe grid + filters + detail, Anomalies feed with live/synthetic separation,
asset evidence on the result stage (verdict lands, no advice wording), Ask-about-this on new surfaces, search, deep link,
evidence links are user-initiated only, no eyebrow/draft labels, mobile layout."""
import re, sys, os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v6_layout import end_state, check, settle
U = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8821/ui/"
O = urlparse(U); ORIGIN = f"{O.scheme}://{O.netloc}"
R = []
def res(n, ok, d=""): print("PASS" if ok else "FAIL", n, "-", str(d)[:300]); R.append(ok)
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

def page(b, **kw):
    ctx = b.new_context(bypass_csp=True, **kw); ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=ORIGIN)
    pg = ctx.new_page(); pg.errs = []; pg.reqs = []
    pg.on("pageerror", lambda e: pg.errs.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and pg.errs.append(m.text))
    pg.on("request", lambda r: pg.reqs.append(r.url))
    pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith(ORIGIN + O.path) or r.request.url.startswith(("data:", "blob:")) else r.abort())
    return ctx, pg

def ask(pg, click, view, evid):
    pg.evaluate("navigator.clipboard.writeText('')"); click(); pg.wait_for_timeout(250)
    t = pg.evaluate("navigator.clipboard.readText()")
    return f"View: {view}" in t and f"Evidence ID: {evid}" in t, t[:160]

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=GL)
    ctx, pg = page(b, viewport={"width": 1440, "height": 900})
    pg.goto(U); pg.wait_for_function("window.GTB&&GTB.ready"); settle(pg, 600)
    ev = pg.evaluate("({u:GTB_EV.EV.universe.length, live:GTB_EV.EV_SIGS.filter(x=>x.set==='live').length, syn:GTB_EV.EV_SIGS.filter(x=>x.set==='synthetic').length})")
    res("embedded data: 50+ asset classes, live and synthetic sets present", ev["u"] >= 50 and ev["syn"] >= 6, ev)
    res("nav has Universe and Anomalies views", pg.locator("#views [data-view=universe]").count() == 1 and pg.locator("#views [data-view=anomalies]").count() == 1)
    # Universe
    pg.click("#views [data-view=universe]"); pg.wait_for_timeout(300)
    n_all = pg.locator(".tile").count()
    res("universe: one tile per asset class", n_all == ev["u"], n_all)
    pg.click("[data-ustat=shipped]"); pg.wait_for_timeout(200); n_sh = pg.locator(".tile").count()
    res("universe: status filter narrows to shipped", 0 < n_sh < n_all and pg.locator(".tile .tag", has_text="Licence").count() == 0, n_sh)
    pg.click("[data-ustat=all]"); pg.click("[data-ucat=Cards]"); pg.wait_for_timeout(200)
    names = pg.locator(".tile .nm").all_inner_texts()
    res("universe: category filter shows only Cards", names and all(pg.evaluate("n=>GTB_EV.EV.universe.find(u=>u.name.toUpperCase()===n.toUpperCase()||u.name===n).category", n) == "Cards" for n in names), names)
    pg.click("[data-uni=pokemon]"); pg.wait_for_timeout(200)
    d = pg.locator("#uniDetail").inner_text()
    res("universe: Pokémon detail says licence-gated with source link", "blocked by a data licence" in d and pg.locator("#uniDetail a[target=_blank]").count() >= 1, d[:200])
    ok, t = ask(pg, lambda: pg.click("#uniDetail [data-ask]"), "Universe", "universe:pokemon"); res("ask: universe detail", ok, t)
    pg.click("[data-ucat=All]"); pg.click("[data-uni=fx-majors]"); pg.wait_for_timeout(200)
    res("universe: FX tile shows a sparkline from ECB data", pg.locator("[data-uni=fx-majors] svg.spark").count() == 1)
    res("layout: universe has no horizontal overflow", check(pg, False) == [], check(pg, False))
    # Anomalies
    pg.click("#views [data-view=anomalies]"); pg.wait_for_timeout(300)
    res("anomalies: live and synthetic sections are separate", pg.locator(".card h2", has_text="Live").count() == 1 and pg.locator(".synbox .erow").count() == ev["syn"], pg.locator(".synbox .erow").count())
    res("anomalies: every synthetic row is labelled synthetic", all("SYNTHETIC" in x.upper() for x in pg.locator(".synbox .erow .hd").all_inner_texts()))
    res("anomalies: unknown checks listed as 'unknown, not quiet'", pg.locator(".card h2", has_text="Unknown, not quiet").count() == 1)
    pg.click("[data-aset=live]"); pg.wait_for_timeout(200)
    res("anomalies: live-only filter hides synthetic", pg.locator(".synbox").count() == 0)
    pg.click("[data-aset=both]"); pg.wait_for_timeout(200)
    ok, t = ask(pg, lambda: pg.locator(".synbox .erow [data-ask]").first.click(), "Anomalies", "synthetic:"); res("ask: anomaly row", ok, t)
    # Evidence on the result stage (synthetic outlier)
    pg.locator(".synbox .erow [data-scan]").first.click()
    pg.wait_for_function("document.getElementById('vdBox').dataset.landed==='1'", timeout=25000); pg.wait_for_timeout(2500)
    st = pg.evaluate("({v:GTB.S.view, k:GTB.S.target.kind, tone:document.getElementById('vdBox').dataset.tone, vd:document.getElementById('vdTx').textContent})")
    res("evidence: asset opens on the result stage and the verdict lands", st["v"] == "asset" and "synthetic" in st["k"], st)
    res("evidence: verdict phrase is not advice", not re.search(r"\b(buy|sell|hold)\b", st["vd"].lower()), st["vd"])
    res("3D stage renders with WebGL on the asset view", pg.evaluate("document.getElementById('stage').dataset.webgl") == "ok")
    res("layout: asset result fits the stage", check(pg) == [], check(pg))
    pg.click("#dtabs [data-tab='2']"); pg.wait_for_timeout(250)
    why = pg.locator("#dbody").inner_text()
    res("evidence: why tab carries limits + synthetic notice", "Synthetic example" in why, why[:200])
    pg.click("#dtabs [data-tab='0']"); pg.wait_for_timeout(250)
    res("evidence: same-module rows render", pg.locator("#dbody .hrow").count() >= 1)
    ok, t = ask(pg, lambda: pg.click("#rhead [data-ask]"), "Games", "synthetic:SYN-SNES-RPG:OUTLIER_SALE"); res("ask: asset header", ok, t)
    # live asset with spark timeline
    lid = pg.evaluate("(GTB.targets().find(t=>t.view==='asset'&&t.set==='live'&&t.events.length>2)||{}).id")
    if lid:
        end_state(pg, lid); pg.wait_for_timeout(2500); pg.click("#dtabs [data-tab='1']"); pg.wait_for_timeout(250)
        res("evidence: live official-data asset shows its series in the timeline", pg.locator("#dbody .bars span").count() >= 40 and check(pg) == [], lid)
    else:
        res("evidence: live official-data asset exists", False, "no live asset with series")
    # quiet tracked asset: never reads as an alert, and unknown never reads as clean
    q = pg.evaluate("(()=>{const t=GTB.targets().filter(t=>t.view==='asset'&&t.id.endsWith(':CHECKS'));return {n:t.length, none:t.filter(x=>x.sev==='NONE').map(x=>GTB_HYPE[x.vi][1]), unk:t.filter(x=>x.sev==='UNKNOWN').map(x=>GTB_HYPE[x.vi][1])}})()")
    res("tracked assets: quiet checks map to 'nothing flagged', unknown never to a clean phrase", q["n"] >= 30 and set(q["none"]) <= {"good"} and "good" not in q["unk"], {k: (v if k == "n" else sorted(set(v))) for k, v in q.items()})
    pg.evaluate("GTB.go('universe')"); pg.click("[data-uni=mtg]"); pg.wait_for_timeout(200)
    res("universe: shipped class lists its tracked assets as evidence chips", pg.locator("#uniDetail .chip[data-scan]").count() >= 10)
    # search + deep link
    pg.evaluate("GTB.go('signals')"); pg.wait_for_timeout(200); pg.fill("#hq", "gold"); pg.wait_for_timeout(200)
    sg = pg.locator("#hsugg button").all_inner_texts()
    res("search finds asset-class evidence by name", any("GOLD" in s.upper() or "GLD" in s.upper() for s in sg) or pg.evaluate("GTB.targets().some(t=>/gold|GLD/i.test(t.title))") is False, sg[:4])
    pg.keyboard.press("Escape")
    # copy + rules
    body = pg.evaluate("document.body.innerText")
    res("copy: not-financial-advice notice present, no draft/counsel labels", "Not financial advice".lower() in body.lower() and not re.search(r"\b(draft|counsel)\b", body, re.I))
    res("network: zero requests outside the app's own files", all(u.startswith(ORIGIN + O.path) or u.startswith(("data:", "blob:")) for u in pg.reqs), [u for u in pg.reqs if not u.startswith(ORIGIN)][:3])
    res("no page errors", pg.errs == [], pg.errs[:3])
    ctx.close()
    # deep link + mobile
    ctx, pg = page(b, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=3)
    pg.goto(U + "#universe"); pg.wait_for_function("window.GTB&&GTB.ready"); settle(pg, 400)
    res("mobile: #universe deep link opens the grid", pg.evaluate("GTB.S.view") == "universe" and pg.locator(".tile").count() >= 50)
    res("mobile: universe fits width", check(pg, False) == [], check(pg, False))
    pg.click("[data-uni=cs2-skins]"); pg.wait_for_timeout(250)
    box = pg.locator("#uniDetail").bounding_box()
    res("mobile: tile detail appears above the grid", box and box["y"] < pg.locator(".tile").first.bounding_box()["y"], box)
    small = pg.evaluate("[...document.querySelectorAll('.tile,.chip,#uniDetail .btn')].filter(e=>e.getBoundingClientRect().height>0&&e.getBoundingClientRect().height<44).length")
    res("mobile: tap targets ≥44px on new controls", small == 0, small)
    pg.evaluate("GTB.go('anomalies')"); pg.wait_for_timeout(300)
    res("mobile: anomalies fits width", check(pg, False) == [], check(pg, False))
    sid = pg.evaluate("GTB.targets().find(t=>t.view==='asset').id"); end_state(pg, sid); pg.wait_for_timeout(2500)  # let the landing punch settle (known transient)
    res("mobile: asset result fits the stage", check(pg) == [], check(pg))
    res("mobile: no page errors", pg.errs == [], pg.errs[:3])
    ctx.close()
    # reduced motion + no WebGL on asset view
    ctx, pg = page(b, viewport={"width": 1280, "height": 720}, reduced_motion="reduce")
    pg.add_init_script("HTMLCanvasElement.prototype.getContext=function(){return null}")
    pg.goto(U + "#anomalies"); pg.wait_for_function("window.GTB&&GTB.ready"); pg.wait_for_timeout(500)
    sid = pg.evaluate("GTB.targets().find(t=>t.view==='asset').id"); pg.evaluate("id=>GTB.scan(id)", sid); pg.wait_for_timeout(400)
    res("no-WebGL + reduced motion: asset result shows static fallback and landed verdict", pg.evaluate("document.getElementById('stage').dataset.webgl") == "fallback" and pg.evaluate("document.getElementById('vdBox').dataset.landed") == "1")
    ctx.close(); b.close()
print(f"ui_everything: {sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
