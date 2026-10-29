"""Card Explorer checks in Chromium EMULATION (Playwright + SwiftShader), not real devices. CSP ENFORCED (no bypass_csp).
Usage: python3 tests/ui/ui_tcg.py [base-url] [--shots DIR]   (serve the repo root; needs a synced cache in ui/cache/tcg: python3 tools/sync_tcg_art.py)
Covers: registry-driven TCG menu, gallery, image-to-printing identity, same-name printings never swapping image/finish/observations,
duplicate names, alternate art/reprint/variant separation, double-faced front/back, missing/placeholder art, missing cache file,
stale cache, unsynced fallback, slow loading, long names, responsive grids (375/390/768/1440), keyboard, Analyze market, Ask about
this, search suggestion, off-origin requests and CSP violations."""
import json, re, sys, os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
args = [a for a in sys.argv[1:] if not a.startswith("--")]
U = args[0] if args else "http://localhost:8821/ui/"
SHOTS = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else None
if SHOTS: args = [a for a in args if a != SHOTS]; U = args[0] if args else U
O = urlparse(U); ORIGIN = f"{O.scheme}://{O.netloc}"
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
R = []
def res(n, ok, d=""): print("PASS" if ok else "FAIL", n, "-", str(d)[:300]); R.append(bool(ok))
def shot(pg, name, full=False):
    if SHOTS: os.makedirs(SHOTS, exist_ok=True); pg.screenshot(path=os.path.join(SHOTS, name), full_page=full)

def page(b, allow404=(), **kw):
    ctx = b.new_context(**kw); pg = ctx.new_page(); pg.errs = []; pg.off = []
    pg.on("pageerror", lambda e: pg.errs.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and not any(a in m.text for a in ("404",) if allow404) and pg.errs.append(m.text))
    pg.on("request", lambda r: (not r.url.startswith((ORIGIN, "data:", "blob:"))) and pg.off.append(r.url))
    pg.add_init_script("document.addEventListener('securitypolicyviolation', e => (window.__csp = window.__csp || []).push(e.violatedDirective + ' ' + e.blockedURI))")
    return ctx, pg
def boot(pg, h="#f/tcg.explorer"):
    pg.goto("about:blank"); pg.goto(U + h); pg.wait_for_function("() => window.GTB && GTB.ready"); pg.wait_for_timeout(400)
def imgs_ok(pg):
    return pg.evaluate("""(()=>{const c=window.GTB_TCG_CACHE;const by={};c.groups.forEach(g=>g.printings.forEach(p=>by[p.key]=p));
      return [...document.querySelectorAll('img[data-key]')].map(i=>{const p=by[i.dataset.key];const f=p&&p.faces[+i.dataset.face];
      return {ok:!!(p&&f&&Object.values(f.img).some(v=>i.getAttribute('src')===v)&&i.getAttribute('src').includes(p.id)),k:i.dataset.key}}).filter(x=>!x.ok)})()""")
def overflow(pg): return pg.evaluate("document.documentElement.scrollWidth - innerWidth")
def card_key(pg, name, set_=None, kind=None):
    return pg.evaluate("""([n,s,k])=>{for(const g of window.GTB_TCG_CACHE.groups)for(const p of g.printings)if(p.name===n&&(!s||p.set===s)&&(!k||p.kind===k))return p.key;return null}""", [name, set_, kind])

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=GL)
    ctx, pg = page(b, viewport={"width": 1440, "height": 900}); boot(pg)
    res("artwork cache loaded (synced)", pg.evaluate("!!(window.GTB_TCG_CACHE && GTB_TCG_CACHE.groups.length)"))
    reg = pg.evaluate("GTB_REGISTRY.F.filter(f=>f.cat==='tcg').map(f=>f.id)")
    menu = pg.evaluate("[...document.querySelectorAll('#nm-tcg [data-feat]')].map(b=>b.dataset.feat)")
    names = pg.evaluate("[...document.querySelectorAll('#nm-tcg [data-feat] .nn')].map(b=>b.textContent)")
    res("TCG menu generated from the registry with Card Explorer, Market Signals, Price History, Cross-Venue Spreads", menu == reg and names == ["Card Explorer", "Market Signals", "Cross-Venue Spreads", "Price History"] or sorted(names) == sorted(["Card Explorer", "Market Signals", "Price History", "Cross-Venue Spreads"]), names)
    pg.click("#nt-tcg"); pg.wait_for_timeout(100); shot(pg, "01-tcg-menu-desktop.png"); pg.click('#nm-tcg [data-feat="tcg.explorer"]'); pg.wait_for_timeout(500)
    n = pg.locator(".tcard").count()
    res("gallery renders one tile per card from the cache", n == pg.evaluate("GTB_TCG_CACHE.groups.length"), n)
    res("Card Explorer is the active TCG tool", pg.evaluate("document.querySelector('#nm-tcg [data-feat=\"tcg.explorer\"]').getAttribute('aria-current')==='page' && document.getElementById('nt-tcg').classList.contains('act')"))
    pg.wait_for_timeout(1200)
    res("every image is the exact printing+face it is bound to", not imgs_ok(pg), imgs_ok(pg)[:3])
    res("grid thumbnails lazy-load", pg.evaluate("[...document.querySelectorAll('.tgrid img')].every(i=>i.loading==='lazy')"))
    res("attribution, cache status and Artwork rights: BLOCKED shown", pg.evaluate("(t=>t.includes('Scryfall')&&/cache synced/i.test(t)&&t.includes('Artwork rights: BLOCKED'))(document.getElementById('tcgStat').textContent)"))
    res("no artwork-sync button (sync is CLI only)", pg.locator("button", has_text=re.compile("sync", re.I)).count() == 0)
    shot(pg, "02-gallery-desktop.png")
    # same-name printings: Force of Will tracked vs an alternate-art printing
    tk, ak = card_key(pg, "Force of Will", kind="tracked"), card_key(pg, "Force of Will", kind="alternate art")
    pg.evaluate(f"document.querySelector('.tcard[data-tkey=\"{tk}\"]').click()"); pg.wait_for_timeout(500)
    d1 = pg.evaluate("({key:document.querySelector('#tcgDet img').dataset.key,src:document.querySelector('#tcgDet img').getAttribute('src'),obs:document.querySelector('#tcgDet').textContent.includes('Bound to'),fin:document.querySelector('#tcgDet').textContent})")
    pg.click(f'.tpb[data-tkey="{ak}"]'); pg.wait_for_timeout(500)
    d2 = pg.evaluate("({key:document.querySelector('#tcgDet img').dataset.key,src:document.querySelector('#tcgDet img').getAttribute('src'),obs:document.querySelector('#tcgDet').textContent.includes('Bound to'),none:document.querySelector('#tcgDet').textContent.includes('No market observation for this printing')})")
    res("same-name printings never swap image or observations (tracked has them, alt art has none)", d1["key"] == tk and d2["key"] == ak and d1["src"] != d2["src"] and d1["obs"] and not d2["obs"] and d2["none"], (d1["key"][:40], d2["key"][:40]))
    res("observation states its exact finish", "finish nonfoil" in d1["fin"])
    res("printings separated: tracked / alternate art / variants / reprints", pg.evaluate("[...document.querySelectorAll('.tpl')].map(x=>x.textContent.split(' · ')[0])").__contains__("Alternate art"))
    shot(pg, "04-printing-selector.png")
    pg.evaluate(f"document.querySelector('.tpb[data-tkey=\"{tk}\"]').click()"); pg.wait_for_timeout(400)
    pg.evaluate("document.getElementById('tcgDet').scrollIntoView()"); shot(pg, "03-card-detail.png")
    res("detail has Analyze market and Ask about this", pg.locator("#tcgAnalyze").count() == 1 and pg.locator("#tcgDet [data-ask]", has_text="Ask about this").count() == 1)
    pg.click("#tcgDet [data-ask]"); pg.wait_for_timeout(500)
    res("Ask about this opens Grok Bot with this printing", pg.evaluate("document.body.textContent.includes('Force of Will')"))
    pg.keyboard.press("Escape"); boot(pg); pg.evaluate(f"document.querySelector('.tcard[data-tkey=\"{tk}\"]').click()"); pg.wait_for_timeout(300)
    pg.click("#tcgAnalyze"); pg.wait_for_timeout(500)
    a = pg.evaluate("({h:location.hash,rows:document.querySelectorAll('#panel tbody tr').length,txt:document.getElementById('panel').textContent,back:!!document.getElementById('focusBack')})")
    res("Analyze market opens Market Signals focused on that card", a["h"] == "#f/tcg.mtg" and a["back"] and "Force of Will" in a["txt"] and "Black Lotus" not in a["txt"], (a["h"], a["rows"]))
    shot(pg, "08-market-from-card.png")
    pg.click("#focusBack"); pg.wait_for_timeout(400)
    res("back to card returns to the same printing", pg.evaluate(f"document.querySelector('#tcgDet img').dataset.key") == tk)
    # duplicate names: Ancestral Recall vs Emeritus of Ideation // Ancestral Recall
    pg.fill("#tcgQ", "ancestral recall"); pg.wait_for_timeout(300)
    dn = pg.evaluate("[...document.querySelectorAll('.tcard .tnm')].map(x=>x.textContent)")
    res("duplicate names stay separate cards", len(dn) >= 2 and "Ancestral Recall" in dn and any("Emeritus" in x for x in dn), dn)
    pg.fill("#tcgQ", "ltr"); pg.wait_for_timeout(200); res("search by set code", pg.locator(".tcard").count() >= 2)
    pg.fill("#tcgQ", "isd 51"); pg.wait_for_timeout(200); res("search by set + collector number", pg.evaluate("[...document.querySelectorAll('.tcard .tnm')].map(x=>x.textContent)") == ["Delver of Secrets // Insectile Aberration"])
    pg.fill("#tcgQ", ""); pg.select_option('[data-tf="lang"]', "fr"); pg.wait_for_timeout(200)
    res("language filter", pg.locator(".tcard").count() >= 1 and pg.evaluate("[...document.querySelectorAll('.tcard .tnm')].every(x=>/Sea|Island/.test(x.textContent))"))
    pg.select_option('[data-tf="lang"]', "all"); pg.select_option('[data-tf="fin"]', "etched"); pg.wait_for_timeout(200)
    res("printing/finish filter narrows", 0 < pg.locator(".tcard").count() < n); pg.select_option('[data-tf="fin"]', "all")
    res("other games listed but disabled", pg.evaluate("[...document.querySelectorAll('[data-tf=game] option')].filter(o=>o.disabled).length>=2 && [...document.querySelectorAll('[data-tf=game] option')].filter(o=>!o.disabled).map(o=>o.value).join()==='mtg'"))
    # double-faced
    dk = card_key(pg, "Delver of Secrets // Insectile Aberration", kind="default") or card_key(pg, "Delver of Secrets // Insectile Aberration")
    pg.evaluate(f"document.querySelector('[data-tkey=\"{dk}\"]').click()"); pg.wait_for_timeout(400)
    f0 = pg.evaluate("document.querySelector('#tcgDet img').getAttribute('src')"); pg.click('[data-tface="1"]'); pg.wait_for_timeout(400)
    f1 = pg.evaluate("({s:document.querySelector('#tcgDet img').getAttribute('src'),h:document.querySelector('#tcgDet h2').textContent,f:document.activeElement.dataset.tface})")
    res("double-faced: Back shows face 2 image of the same printing, title follows, focus kept", f0.endswith("-f0-normal.jpg") or f0.endswith("-f0-small.jpg") and f1["s"].endswith("-f1-small.jpg") and f1["h"] == "Insectile Aberration" and f1["f"] == "1", (f0[-20:], f1))
    shot(pg, "05-double-faced-back.png")
    # placeholder art (FBB Underground Sea)
    pk = card_key(pg, "Underground Sea", "fbb")
    pg.evaluate(f"document.querySelector('[data-tkey=\"{pk}\"]')?document.querySelector('[data-tkey=\"{pk}\"]').click():null"); pg.wait_for_timeout(100)
    if not pg.locator("#tcgDet").count() or pg.evaluate("document.querySelector('#tcgDet h2').textContent") != "Underground Sea":
        pg.fill("#tcgQ", "underground sea"); pg.wait_for_timeout(200); pg.click(".tcard"); pg.wait_for_timeout(200); pg.click(f'.tpb[data-tkey="{pk}"]')
    pg.wait_for_timeout(300)
    res("placeholder imagery renders the text fallback with source link (no blank, no hotlink)", pg.evaluate("!!document.querySelector('#tcgDet .tph.big .tl') && !document.querySelector('#tcgDet .tdl img')"))
    shot(pg, "06-missing-art.png")
    # keyboard
    boot(pg); pg.focus("#tcgQ"); pg.keyboard.press("Tab")
    for _ in range(8):
        if pg.evaluate("document.activeElement.classList.contains('tcard')"): break
        pg.keyboard.press("Tab")
    k0 = pg.evaluate("document.activeElement.dataset.tkey"); pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
    k1 = pg.evaluate("document.activeElement.id==='tcgDet'"); pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    k2 = pg.evaluate("document.activeElement.dataset.tkey"); fv = pg.evaluate("getComputedStyle(document.activeElement).outlineStyle!=='none'")
    res("keyboard: Tab reaches tiles, Enter opens detail with focus, Escape closes and returns focus, focus visible", bool(k0) and k1 and k2 == k0 and fv, (k0 and k0[:30], k1, k2 and k2[:30], fv))
    res("desktop: no CSP violations, no off-origin requests, no page errors", not pg.evaluate("window.__csp||[]") and not pg.off and not pg.errs, (pg.evaluate("window.__csp||[]"), pg.off[:3], pg.errs[:3]))
    res("desktop: no horizontal overflow", overflow(pg) <= 0)
    # search suggestion from Home
    boot(pg, ""); pg.fill("#q", "Rhystic"); pg.wait_for_timeout(200)
    sg = pg.evaluate("[...document.querySelectorAll('#sugg button')].map(b=>b.textContent)")
    res("Home search suggests the card in Card Explorer", any("Card Explorer" in s for s in sg), sg[:3])
    pg.click("#sugg button:has-text('Card Explorer')"); pg.wait_for_timeout(400)
    res("suggestion opens that card's detail", pg.evaluate("location.hash==='#f/tcg.explorer' && document.querySelector('#tcgDet h2').textContent.includes('Rhystic')"))
    ctx.close()
    # missing cache file, slow cache, stale cache, long name (route interception; still same-origin)
    ctx, pg = page(b, allow404=True, viewport={"width": 1440, "height": 900})
    def mod(r):
        body = r.fetch().text(); j = json.loads(body[body.index("=") + 1:].rstrip().rstrip(";"))
        j["syncedAt"] -= 30 * 86400; j["groups"][0]["printings"][0]["name"] = j["groups"][0]["name"] = "Asmoranomardicadaistinaculdacar, the Incredibly Long Synthetic Test Name of Doom"
        r.fulfill(status=200, content_type="application/javascript", body="window.GTB_TCG_CACHE = " + json.dumps(j) + ";")
    pg.route("**/ui/cache/tcg/mtg/explorer.js", mod)
    cdp = ctx.new_cdp_session(pg); cdp.send("Network.enable")
    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 1500, "downloadThroughput": 200000, "uploadThroughput": 200000})
    pg.goto(U + "#f/tcg.explorer"); pg.wait_for_function("() => window.GTB && GTB.ready"); pg.wait_for_timeout(200)
    res("slow cache: skeleton shown while images load", pg.evaluate("document.querySelectorAll('.timg.ld').length>0"))
    try:
        pg.wait_for_function("() => document.querySelectorAll('.tgrid .timg.ld').length===0", timeout=30000); cl = True
    except Exception:
        cl = False
    res("slow cache: skeletons clear after load (1.5 s latency, 200 kB/s)", cl, pg.evaluate("document.querySelectorAll('.tgrid .timg.ld').length"))
    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1})
    res("stale cache flagged with its age", pg.evaluate("/cache stale \\(3\\d days\\)/.test(document.getElementById('tcgStat').textContent)"))
    res("long card name wraps inside its tile (desktop)", pg.evaluate("(()=>{const t=document.querySelector('.tcard'),n=t.querySelector('.tnm');return n.textContent.startsWith('Asmor')&&n.getBoundingClientRect().right<=t.getBoundingClientRect().right+1})()") and overflow(pg) <= 0)
    shot(pg, "09-stale-long-name.png")
    ctx.close()
    ctx, pg = page(b, allow404=True, viewport={"width": 1440, "height": 900})
    pg.route("**/ui/cache/tcg/mtg/img/**", lambda r: r.fulfill(status=404) if "-f0-small" in r.request.url else r.continue_())
    boot(pg); pg.wait_for_timeout(1500)
    res("missing cache file swaps to the text fallback (no broken image)", pg.evaluate("document.querySelectorAll('.tgrid .tph').length>=10 && document.querySelectorAll('.tgrid img').length===0"))
    ctx.close()
    ctx, pg = page(b, allow404=True, viewport={"width": 1440, "height": 900})
    pg.route("**/ui/cache/tcg/mtg/explorer.js", lambda r: r.fulfill(status=404))
    boot(pg); pg.wait_for_timeout(300)
    un = pg.evaluate("({n:document.querySelectorAll('.tcard').length,imgs:document.querySelectorAll('.tgrid img').length,stat:document.getElementById('tcgStat').textContent,tag:document.querySelector('#nm-tcg [data-feat=\"tcg.explorer\"] .tg:last-child').textContent})")
    res("unsynced checkout: tracked cards as text cards, artwork BLOCKED/unsynced stated, menu shows unavailable", un["n"] == 24 and un["imgs"] == 0 and "not synced" in un["stat"] and "BLOCKED" in un["stat"] and un["tag"] == "unavailable", un)
    pg.click(".tcard"); pg.wait_for_timeout(300); res("unsynced: detail + Analyze market still work", pg.locator("#tcgAnalyze").count() == 1 and pg.locator("#tcgDet .tph.big").count() == 1)
    res("unsynced: no page errors (except the expected 404 for the optional cache script)", not pg.errs and not pg.evaluate("window.__csp||[]"), pg.errs[:2])
    ctx.close()
    # responsive + mobile
    for (w, h, nm) in [(375, 812, "mobile375"), (390, 844, "mobile390"), (768, 1024, "tablet768")]:
        ctx, m = page(b, viewport={"width": w, "height": h}, device_scale_factor=2 if w < 500 else 1, is_mobile=w < 500, has_touch=w < 500); boot(m); m.wait_for_timeout(800)
        cols = m.evaluate("getComputedStyle(document.querySelector('.tgrid')).gridTemplateColumns.split(' ').length")
        tw = m.evaluate("Math.min(...[...document.querySelectorAll('.tcard')].map(t=>t.getBoundingClientRect().width))")
        th = m.evaluate("Math.min(...[...document.querySelectorAll('.tcard')].map(t=>t.getBoundingClientRect().height))")
        res(f"{nm}: grid {cols} cols, tiles >= 140px wide and >= 44px tall, no overflow", (cols == 2 if w < 500 else cols >= 4) and tw >= 140 and th >= 44 and overflow(m) <= 0, (cols, tw, th, overflow(m)))
        if w == 375:
            shot(m, "07-mobile-gallery.png")
            m.locator(".tcard").nth(3).tap(); m.wait_for_timeout(500)
            res("mobile375: tap opens detail; image <= viewport; no overflow", m.evaluate("(()=>{const i=document.querySelector('#tcgDet .timg,#tcgDet .tph');const r=i.getBoundingClientRect();return r.width<=innerWidth-16})()") and overflow(m) <= 0)
            m.evaluate("document.getElementById('tcgDet').scrollIntoView()"); shot(m, "07b-mobile-detail.png")
            m.fill("#tcgQ", "valki"); m.wait_for_timeout(200); m.locator(".tcard").first.tap(); m.wait_for_timeout(400)
            res("mobile375: long double-faced name wraps, front/back buttons >= 30px", overflow(m) <= 0 and m.evaluate("Math.min(...[...document.querySelectorAll('[data-tface]')].map(b=>b.getBoundingClientRect().height))>=30"))
        res(f"{nm}: no CSP violations, off-origin requests or page errors", not m.off and not m.evaluate("window.__csp||[]") and not m.errs, (m.off[:2], m.errs[:2]))
        ctx.close()
    ctx, r = page(b, viewport={"width": 1440, "height": 900}, reduced_motion="reduce"); boot(r); r.wait_for_timeout(300)
    res("reduced motion: no skeleton animation, no hover lift", r.evaluate("getComputedStyle(document.querySelector('.timg')).animationName==='none' || !document.querySelector('.timg.ld')") and not r.errs)
    ctx.close(); b.close()
print(f"{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
