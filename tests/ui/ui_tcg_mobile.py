"""Card Explorer mobile first fold, in Chromium EMULATION (Playwright + SwiftShader), not real phones. CSP ENFORCED.
Usage: python3 tests/ui/ui_tcg_mobile.py [base-url] [--shots DIR]   (serve the repo root; synced cache in ui/cache/tcg)
Covers: a card image (or the text card when unsynced) inside the INITIAL viewport at 375x812 and 390x844, first-viewport
measurements at 320/375/390/430/768, one Filters control (collapsed on phones) with active count and Reset, one-line
cache/rights status with details on demand, 2-column phone grid with correct aspect ratio and lazy thumbnails, 44px touch
targets, labels, focus return, detail view title/Close first on narrow screens with no clipping or overflow, printing selector,
front/back flip, stage hidden behind the panel, no off-origin requests, no CSP violations."""
import json, os, sys
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
args = [a for a in sys.argv[1:] if not a.startswith("--")]
SHOTS = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else None
if SHOTS: args = [a for a in args if a != SHOTS]
U = args[0] if args else "http://127.0.0.1:8833/ui/"
O = urlparse(U); ORIGIN = f"{O.scheme}://{O.netloc}"
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
R = []
def res(n, ok, d=""): print("PASS" if ok else "FAIL", n, "-", str(d)[:300]); R.append(bool(ok))
def shot(pg, name):
    if SHOTS: os.makedirs(SHOTS, exist_ok=True); pg.screenshot(path=os.path.join(SHOTS, name))

def page(b, w, h, unsynced=False):
    ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2, is_mobile=w < 768, has_touch=w < 768)
    pg = ctx.new_page(); pg.errs = []; pg.off = []
    pg.on("pageerror", lambda e: pg.errs.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and not (unsynced and "404" in m.text) and pg.errs.append(m.text))
    pg.on("request", lambda r: (not r.url.startswith((ORIGIN, "data:", "blob:"))) and pg.off.append(r.url))
    pg.add_init_script("document.addEventListener('securitypolicyviolation', e => (window.__csp = window.__csp || []).push(e.violatedDirective + ' ' + e.blockedURI))")
    if unsynced:
        pg.route("**/cache/tcg/**", lambda r: r.fulfill(status=404, body=""))
    pg.goto(U + "#f/tcg.explorer"); pg.wait_for_function("() => window.GTB && GTB.ready"); pg.wait_for_timeout(900)
    return ctx, pg

FOLD = """() => { const t = document.querySelector('.tgrid .tcard'); const v = t && t.querySelector('img,.tph'); if (!v) return null;
  const r = v.getBoundingClientRect(), img = v.tagName === 'IMG';
  return { top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height), w: Math.round(r.width), vh: innerHeight, img,
           loaded: img ? (v.complete && v.naturalWidth > 0) : null, visible: Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0)),
           scrollY: scrollY, cols: getComputedStyle(document.querySelector('.tgrid')).gridTemplateColumns.split(' ').length,
           ratio: +(r.width / r.height).toFixed(3) } }"""
SMALL = """(sel) => [...document.querySelectorAll(sel)].filter(e => e.offsetParent).map(e => { const r = e.getBoundingClientRect(); return { s: (e.id || e.className || e.tagName) + '', h: Math.round(r.height), w: Math.round(r.width) } }).filter(x => x.h < 44 || x.w < 44)"""
OVER = "document.documentElement.scrollWidth - innerWidth"

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=GL)
    meas = {}
    for (w, h) in [(320, 568), (375, 812), (390, 844), (430, 932), (768, 1024)]:
        ctx, pg = page(b, w, h)
        f = pg.evaluate(FOLD); meas[w] = f
        if w in (375, 390):
            res(f"{w}x{h}: a real card image is fully inside the initial viewport (no scroll)", f and f["img"] and f["loaded"] and f["scrollY"] == 0 and f["bottom"] <= h and f["visible"] >= f["h"] - 1, f)
        elif w in (430, 768):
            res(f"{w}x{h}: first card image fully inside the initial viewport", f and f["img"] and f["bottom"] <= h, f)
        else:
            res(f"{w}x{h}: first card tile starts inside the initial viewport (partial: short screen)", f and f["top"] < h, f)
        res(f"{w}: no horizontal overflow; grid columns {'2' if w < 768 else '>=3'}", pg.evaluate(OVER) <= 0 and ((f["cols"] == 2) if w < 768 else f["cols"] >= 3), (pg.evaluate(OVER), f["cols"]))
        res(f"{w}: thumbnail keeps card aspect ratio (146:204) and lazy-loads", abs(f["ratio"] - 146 / 204) < 0.02 and pg.evaluate("[...document.querySelectorAll('.tgrid img')].every(i=>i.loading==='lazy')"), f["ratio"])
        if w == 375:
            shot(pg, "mobile-375-immediate-load.png")
            res("375: search usable in first fold (visible, labelled, >=44px)", pg.evaluate("(()=>{const i=document.getElementById('tcgQ');const r=i.getBoundingClientRect();return r.bottom<innerHeight&&r.height>=44&&!!i.getAttribute('aria-label')})()"))
            st = pg.evaluate("(()=>{const l=document.querySelector('#tcgStat .tst1');const lh=parseFloat(getComputedStyle(l).lineHeight)||16;return {h:l.getBoundingClientRect().height,lh,t:document.getElementById('tcgStat').textContent,open:document.querySelector('#tcgStat details').open}})()")
            res("375: cache/rights status is one line; attribution + rights detail available behind a disclosure", st["h"] <= st["lh"] * 1.5 and "Artwork rights: BLOCKED" in st["t"] and "Scryfall" in st["t"] and not st["open"], st)
            pg.click("#tcgStat summary"); pg.wait_for_timeout(150)
            res("375: status details open on tap and show attribution", pg.evaluate("document.querySelector('#tcgStat details').open && document.querySelector('#tcgStat details').getBoundingClientRect().height > 44"))
            res("375: filters collapsed into one Filters control (aria-expanded=false, panel hidden)", pg.evaluate("document.getElementById('tcgFb').getAttribute('aria-expanded')==='false' && !document.getElementById('tcgFp').offsetParent && !document.getElementById('tcgReset')"))
            pg.click("#tcgFb"); pg.wait_for_timeout(200)
            res("375: Filters expands set/rarity/language/printing/game; focus stays on Filters", pg.evaluate("document.getElementById('tcgFb').getAttribute('aria-expanded')==='true' && document.querySelectorAll('#tcgFp select').length===5 && [...document.querySelectorAll('#tcgFp select')].every(s=>s.offsetParent) && document.activeElement.id==='tcgFb'"))
            n0 = pg.locator(".tcard").count()
            pg.select_option('[data-tf="lang"]', "fr"); pg.wait_for_timeout(200); pg.select_option('[data-tf="rarity"]', pg.evaluate("[...document.querySelectorAll('[data-tf=rarity] option')].map(o=>o.value).find(v=>v!=='all')")); pg.wait_for_timeout(200)
            a = pg.evaluate("({c:(document.querySelector('#tcgFb .tfn')||{}).textContent,l:document.getElementById('tcgFb').getAttribute('aria-label'),r:!!document.getElementById('tcgReset'),n:document.querySelectorAll('.tcard').length})")
            res("375: active-filter count shown on Filters (2) and Reset appears", a["c"] == "2" and "2 active" in a["l"] and a["r"] and a["n"] < n0, a)
            res("375: touch targets >=44px (search, Filters, Reset, selects, status disclosure, card tiles)", not pg.evaluate(SMALL, "#tcgQ,#tcgFb,#tcgReset,#tcgFp select,#tcgStat summary,.tcard"), pg.evaluate(SMALL, "#tcgQ,#tcgFb,#tcgReset,#tcgFp select,#tcgStat summary,.tcard")[:4])
            shot(pg, "mobile-375-filters-open.png")
            pg.click("#tcgReset"); pg.wait_for_timeout(200)
            res("375: Reset clears every filter and returns focus to Filters", pg.evaluate("document.querySelectorAll('.tcard').length") == n0 and pg.evaluate("!document.getElementById('tcgReset') && document.activeElement.id==='tcgFb' && !document.querySelector('#tcgFb .tfn')"))
            pg.click("#tcgFb"); pg.wait_for_timeout(150)
            # detail
            pg.locator(".tcard").first.click(); pg.wait_for_timeout(700)
            d = pg.evaluate("""(()=>{const d=document.getElementById('tcgDet');const c=document.getElementById('tcgClose').getBoundingClientRect();const t=d.querySelector('.tdh h2').getBoundingClientRect();
              const i=d.querySelector('.timg,.tph').getBoundingClientRect();return {focus:document.activeElement===d,cTop:c.top,cBottom:c.bottom,cL:c.left,cR:c.right,cH:c.height,titleBeforeImg:t.bottom<=i.top+1,
              imgW:i.width,vw:innerWidth,vh:innerHeight,stage:document.getElementById('stageWrap').hidden}})()""")
            res("375 detail: focus moves to detail; title and Close above the artwork; Close fully on screen and >=44px", d["focus"] and d["titleBeforeImg"] and 0 <= d["cTop"] and d["cBottom"] <= d["vh"] and 0 <= d["cL"] and d["cR"] <= d["vw"] and d["cH"] >= 44, d)
            res("375 detail: artwork within viewport width; no horizontal overflow; 3D stage hidden (no overlap)", d["imgW"] <= d["vw"] - 16 and pg.evaluate(OVER) <= 0 and d["stage"], d)
            shot(pg, "mobile-375-selected-detail.png")
            pb = pg.evaluate("[...document.querySelectorAll('.tpb')].map(b=>{const r=b.getBoundingClientRect();return {h:r.height,r:r.right,l:r.left}})")
            res("375 detail: printing selector buttons >=44px tall and inside the viewport", pb and all(x["h"] >= 44 and x["l"] >= 0 and x["r"] <= 375 for x in pb), pb[:3])
            k2 = pg.evaluate("(()=>{const b=[...document.querySelectorAll('.tpb')].find(b=>b.getAttribute('aria-pressed')==='false');return b&&b.dataset.tkey})()")
            if k2:
                pg.locator(f'.tpb[data-tkey="{k2}"]').click(); pg.wait_for_timeout(500)
                res("375 detail: choosing another printing keeps the detail on screen with Close reachable", pg.evaluate("(k=>{const d=document.getElementById('tcgDet');const c=document.getElementById('tcgClose').getBoundingClientRect();return d&&document.querySelector('.tpb[aria-pressed=true]').dataset.tkey===k&&c.top>=0&&c.bottom<=innerHeight})", k2))
            pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
            res("375 detail: Escape closes and returns focus to a card tile", pg.evaluate("!document.getElementById('tcgDet') && !!document.activeElement.closest('.tcard,#tcgQ')"))
            # double-faced + long title on narrow
            dfc = pg.evaluate("(()=>{for(const g of GTB_TCG_CACHE.groups)for(const p of g.printings)if(p.faces.length>1)return p.key;return null})()")
            if dfc:
                pg.fill("#tcgQ", pg.evaluate("(k=>{for(const g of GTB_TCG_CACHE.groups)for(const p of g.printings)if(p.key===k)return g.name.split(' ')[0]})", dfc)); pg.wait_for_timeout(300)
                pg.evaluate("k=>document.querySelector('.tcard[data-tkey=\"'+k+'\"]')||0", dfc)
                el = pg.locator(f'.tcard[data-tkey="{dfc}"]')
                if el.count():
                    el.first.click(); pg.wait_for_timeout(500); f0 = pg.evaluate("(document.querySelector('#tcgDet img')||{}).src")
                    pg.click('[data-tface="1"]'); pg.wait_for_timeout(400); f1 = pg.evaluate("(document.querySelector('#tcgDet img')||{}).src")
                    res("375 detail: double-faced front/back flip works; buttons >=44px; long title wraps without overflow", f0 != f1 and pg.evaluate("Math.min(...[...document.querySelectorAll('[data-tface]')].map(b=>b.getBoundingClientRect().height))>=44") and pg.evaluate(OVER) <= 0, (f0[-40:] if f0 else None, f1[-40:] if f1 else None))
                    shot(pg, "mobile-375-double-faced-back.png")
        if w == 390:
            shot(pg, "mobile-390-immediate-load.png")
        res(f"{w}: no off-origin requests, no CSP violations, no page errors", not pg.off and not pg.evaluate("window.__csp||[]") and not pg.errs, (pg.off[:2], pg.evaluate("window.__csp||[]")[:2], pg.errs[:2]))
        ctx.close()
    # unsynced (fresh npm install / fresh clone): text cards in the first fold, hint names the GitHub repo
    for (w, h) in [(375, 812), (390, 844)]:
        ctx, pg = page(b, w, h, unsynced=True)
        f = pg.evaluate(FOLD)
        res(f"{w} unsynced: a text card (fallback) is fully inside the initial viewport", f and not f["img"] and f["bottom"] <= h, f)
        t = pg.evaluate("document.getElementById('tcgStat').textContent + ' || ' + document.querySelector('.tgrid .tph').textContent")
        res(f"{w} unsynced: fallback says artwork is not in the npm package and that the sync script comes from the GitHub repo", "not included in the npm package" in t and "github.com/outerheaven199X/groktheblock" in t and "Text card" in t, t[:200])
        if w == 375:
            shot(pg, "mobile-375-unsynced-text-cards.png")
            pg.locator(".tcard").first.click(); pg.wait_for_timeout(400)
            res("375 unsynced detail: big text card explains the optional repo-only sync; Close on screen", pg.evaluate("(()=>{const t=document.querySelector('#tcgDet .tph').textContent;const c=document.getElementById('tcgClose').getBoundingClientRect();return t.includes('clone github.com/outerheaven199X/groktheblock')&&c.bottom<=innerHeight&&c.top>=0})()"))
            shot(pg, "mobile-375-unsynced-detail.png")
        res(f"{w} unsynced: no off-origin requests, no CSP violations", not pg.off and not pg.evaluate("window.__csp||[]"), pg.off[:2])
        ctx.close()
    print("first-viewport measurements:", json.dumps(meas))
    b.close()
print(f"{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
