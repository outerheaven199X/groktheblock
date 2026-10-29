"""v6 UI checks in Chromium EMULATION (Playwright), not real devices.
Usage: python tests/ui/ui_v6.py [base-url]   default http://localhost:8821/ui/ (serve the repo root: python -m http.server 8821)
Covers: zero network requests beyond the app's own local files, Ask-about-this clipboard per surface (+ textarea fallback),
verdict mapping, reduced motion, WebGL fallback, legal footer, tap targets, keyboard graph selection, no horizontal overflow."""
import json, sys, re
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
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
    pg.on("request", lambda r: pg.reqs.append((r.resource_type, r.url)))
    return ctx, pg

def clip(pg): return pg.evaluate("navigator.clipboard.readText()")
def ask_check(pg, name, click, view, evid):
    pg.evaluate("navigator.clipboard.writeText('')"); click(); pg.wait_for_timeout(250)
    t = clip(pg); toast = pg.locator("#toast").inner_text()
    res(f"ask: {name} copies view + evidence id", f"View: {view}" in t and f"Evidence ID: {evid}" in t and "Question: What happened here" in t and "copied" in toast.lower(), t[:200])

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=GL)
    ctx, pg = page(b, viewport={"width": 1440, "height": 900})
    pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith(ORIGIN + O.path) or r.request.url.startswith(("data:", "blob:")) else r.abort())
    pg.goto(U); pg.wait_for_function("window.GTB&&GTB.ready"); pg.wait_for_timeout(1500)
    res("3D stage renders with WebGL (not the fallback)", pg.evaluate("document.getElementById('stage').dataset.webgl") == "ok", pg.evaluate("document.getElementById('stage').dataset.webgl"))
    # verdict mapping from real data
    v = pg.evaluate("Object.fromEntries(GTB.targets().map(t=>[t.id,[t.sev,GTB_HYPE[t.vi][0],GTB_HYPE[t.vi][1]]]))")
    res("verdict: CRITICAL $SYNTHING maps to a bad phrase", v["token:SYNTHING"][2] == "bad", v["token:SYNTHING"])
    res("verdict: LOW $SYNFART (organic 99) maps to a good phrase", v["token:SYNFART"][2] == "good", v["token:SYNFART"])
    res("verdict: unknown severity never reads as clean", pg.evaluate("GTB_HYPE[GTB_verdictIndex(null,100,false,0)][1]") == "caution")
    phrases = pg.evaluate("GTB_HYPE.map(h=>h[0]).join(' ').toLowerCase()")
    res("verdict phrases contain no buy/sell/hold advice", not re.search(r"\b(buy|sell|hold|moon|pump|guaranteed)\b", phrases), phrases)
    # surfaces
    pg.evaluate("GTB.scan('token:SYNTHING')"); pg.wait_for_function("document.getElementById('vdBox').dataset.landed==='1'", timeout=20000)
    res("result sequence lands the verdict", pg.evaluate("document.getElementById('vdTx').textContent") == v["token:SYNTHING"][1])
    mint = "SyndEgM54DeN9b1EW53uvu9uTxkHqz7WX6qVJfM7HxHq"
    ask_check(pg, "token report header", lambda: pg.click("#rhead [data-ask]"), "Token scan", "scan:" + mint)
    pg.click("#dtabs [data-tab='0']"); pg.wait_for_timeout(300)
    ask_check(pg, "holder row", lambda: pg.locator("#dbody .hrow [data-ask]").first.click(), "Token scan // Holders", "scan:" + mint + "#Syn")
    pg.click("#dtabs [data-tab='2']"); pg.wait_for_timeout(300)
    ask_check(pg, "why-flagged finding", lambda: pg.click("#dbody .why [data-ask]"), "Token scan // Why flagged", "scan:" + mint + "#finding:")
    pg.click("#dtabs [data-tab='1']"); pg.wait_for_timeout(300)
    res("timeline tab renders a scrubber", pg.locator("#scrub").count() == 1)
    pg.click("#feedBtn"); pg.wait_for_timeout(400)
    ask_check(pg, "live feed item", lambda: pg.locator("#feedList [data-ask]").first.click(), "Live feed // ", "")
    pg.click("#feedClose")
    pg.evaluate("GTB.go('wallet')"); pg.wait_for_timeout(900)
    ask_check(pg, "wallet header", lambda: pg.click("#rhead [data-ask]"), "Wallet scan", "wallet:SynHEe")
    pg.evaluate("GTB.go('replay')"); pg.wait_for_timeout(900)
    ask_check(pg, "replay header", lambda: pg.click("#rhead [data-ask]"), "Rug replay", "replay:" + mint)
    pg.evaluate("GTB.go('signals')"); pg.wait_for_timeout(400)
    ask_check(pg, "signals feed item", lambda: pg.locator("#panel details.it summary [data-ask]").first.click(), "Signals", "cross:fed-policy:CONVERGENCE")
    pg.locator("#panel details.it summary").first.click(); pg.wait_for_timeout(200)
    ask_check(pg, "signals expanded dossier", lambda: pg.locator("#panel details[open] .dz [data-ask]").first.click(), "Signals // dossier", "cross:fed-policy:CONVERGENCE")
    res("dossier marks approximate timing (R4 rule)", "timing comparison approximate" in pg.locator("#panel details[open]").inner_text())
    pg.evaluate("GTB.go('threats')"); pg.wait_for_timeout(400)
    ask_check(pg, "threats alert", lambda: pg.locator("#panel details.it summary [data-ask]").first.click(), "Threats", "mintauth-")
    pg.evaluate("GTB.go('shill')"); pg.wait_for_timeout(400)
    pg.locator("#panel .n").first.focus(); pg.keyboard.press("ArrowRight"); pg.keyboard.press("Enter"); pg.wait_for_timeout(200)
    res("shill net: node selected by keyboard", pg.locator("#panel .n[aria-pressed=true]").count() == 1 and pg.evaluate("document.activeElement.classList.contains('n')"))
    ask_check(pg, "shill net evidence panel", lambda: pg.click("#evPanel [data-ask]"), "Shill net // evidence", "shill:$SYNTHING#account:")
    pg.evaluate("GTB.go('copy')"); pg.wait_for_timeout(400)
    pg.locator("#panel .n").first.click(); pg.wait_for_timeout(200)
    ask_check(pg, "copy net evidence panel", lambda: pg.click("#evPanel [data-ask]"), "Copy net // evidence", "copy:SynA6W")
    pg.select_option("#copyPick", label="$SYNFART (no copy links)"); pg.wait_for_timeout(300)
    res("copy net: empty state for a scan without links", "No copy-trade links" in pg.locator("#panel").inner_text())
    pg.evaluate("GTB.go('board')"); pg.wait_for_timeout(300)
    pg.click("[data-sort=winRate]"); pg.wait_for_timeout(200)
    wr = [int(x.rstrip("%")) for x in pg.locator("#panel tbody tr td:nth-child(4)").all_inner_texts()]
    pg.click("[data-sort=winRate]"); pg.wait_for_timeout(200)
    wr2 = [int(x.rstrip("%")) for x in pg.locator("#panel tbody tr td:nth-child(4)").all_inner_texts()]
    res("leaderboard sorts by header click, both directions", wr == sorted(wr, reverse=True) and wr2 == sorted(wr2) and pg.locator("th[aria-sort]").count() == 1, (wr[:3], wr2[:3]))
    ask_check(pg, "leaderboard row", lambda: pg.locator("#panel tbody [data-ask]").first.click(), "Leaderboard", "board:INSIDER#")
    pg.evaluate("GTB.go('prov')"); pg.wait_for_timeout(300)
    ask_check(pg, "provenance record", lambda: pg.locator("#panel .card [data-ask]").first.click(), "Provenance", "prov:")
    res("legal footer flagged for counsel review", pg.locator("[data-legal-status=NEEDS_COUNSEL_REVIEW]").count() == 1 and "not financial advice" in pg.locator("footer").inner_text().lower())
    bad = [r for r in pg.reqs if not r[1].startswith(ORIGIN + O.path) or r[0] in ("fetch", "xhr", "websocket", "eventsource")]
    res("zero network requests beyond the app's own local files (no fetch/XHR/websocket, no other origin)", not bad and len(pg.reqs) > 0, bad[:5] or f"{len(pg.reqs)} local file loads")
    res("no page errors (1440)", not pg.errs, pg.errs[:3])
    ctx.close()
    # clipboard fallback
    ctx = b.new_context(bypass_csp=True, viewport={"width": 1440, "height": 900}); pg = ctx.new_page()
    pg.add_init_script("Object.defineProperty(navigator,'clipboard',{value:undefined})")
    pg.goto(U + "#signals"); pg.wait_for_function("window.GTB&&GTB.ready"); pg.wait_for_timeout(300)
    pg.locator("#panel details.it summary [data-ask]").first.click(); pg.wait_for_timeout(200)
    res("clipboard unavailable -> selectable textarea with the prompt", pg.locator("#fbk.on textarea").count() == 1 and "Evidence ID: cross:fed-policy" in pg.input_value("#fbkTa"))
    ctx.close()
    # mobile
    ctx, pg = page(b, viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    pg.goto(U); pg.wait_for_function("window.GTB&&GTB.ready"); pg.wait_for_timeout(600)
    for v in ["home", "token", "wallet", "replay", "signals", "threats", "shill", "copy", "board", "prov"]:
        pg.evaluate(f"GTB.go('{v}')"); pg.wait_for_timeout(300)
        ow = pg.evaluate("document.documentElement.scrollWidth-innerWidth")
        small = pg.evaluate("[...document.querySelectorAll('[data-ask],.btn,nav#views button')].filter(e=>e.offsetParent).map(e=>e.getBoundingClientRect()).filter(r=>r.height<44||r.width<44).length")
        res(f"390 {v}: no horizontal overflow, Ask/buttons ≥44px", ow <= 1 and small == 0, f"overflow={ow} small={small}")
    res("no page errors (390)", not pg.errs, pg.errs[:3]); ctx.close()
    # reduced motion
    ctx, pg = page(b, viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    pg.goto(U); pg.wait_for_function("window.GTB&&GTB.ready"); pg.wait_for_timeout(800)
    res("reduced motion: ticker marquee off", pg.evaluate("getComputedStyle(document.getElementById('track')).animationName") == "none")
    n0 = pg.evaluate("GTB.S.feed.length"); pg.wait_for_timeout(4500)
    res("reduced motion: no idle feed pushes", pg.evaluate("GTB.S.feed.length") == n0)
    pg.evaluate("GTB.scan('token:SYNTHING')"); pg.wait_for_timeout(300)
    res("reduced motion: verdict shown without the slot roll", pg.evaluate("document.getElementById('vdBox').dataset.landed") == "1")
    ctx.close()
    # no WebGL
    ctx, pg = page(b, viewport={"width": 1440, "height": 900})
    pg.goto(U + "?nowebgl"); pg.wait_for_function("window.GTB&&GTB.ready"); pg.wait_for_timeout(800)
    res("WebGL unavailable -> static bot fallback", pg.evaluate("document.getElementById('stage').dataset.webgl") == "fallback" and pg.locator("#fallback").is_visible())
    ctx.close()
    b.close()
print(("ALL PASS" if all(R) else "SOME FAIL"), f"{sum(R)}/{len(R)}")
sys.exit(0 if all(R) else 1)
