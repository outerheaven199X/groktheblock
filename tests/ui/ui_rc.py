"""Everything-markets release-candidate checks in Chromium EMULATION (Playwright + SwiftShader), not real devices or GPUs.
Usage: python3 tests/ui/ui_rc.py [base-url]   (serve the repo root: python3 -m http.server 8821)
CSP is ENFORCED here (no bypass_csp). Covers: asset-first navigation (hover delay, click toggle, single open menu, Escape/focus,
keyboard, viewport clipping, layering over the WebGL stage), every registry feature reaching a working destination, mobile Markets
navigation, licence-gated classes never shown as tools, instrument-aware search routing, unknown-not-quiet states, real/synthetic
separation, notification placement, result-sequence intermediate frames, mobile Home composition, overflow, reduced motion,
off-origin requests, CSP violations, unsafe imported JSON."""
import json, re, sys, os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v6_layout import check, settle, end_state
U = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8821/ui/"
O = urlparse(U); ORIGIN = f"{O.scheme}://{O.netloc}"
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
R = []
def res(n, ok, d=""): print("PASS" if ok else "FAIL", n, "-", str(d)[:300]); R.append(bool(ok))

def page(b, **kw):
    ctx = b.new_context(**kw); pg = ctx.new_page(); pg.errs = []; pg.off = []; pg.csp = []
    pg.on("pageerror", lambda e: pg.errs.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and pg.errs.append(m.text))
    pg.on("request", lambda r: (not r.url.startswith((ORIGIN, "data:", "blob:"))) and pg.off.append(r.url))
    pg.add_init_script("document.addEventListener('securitypolicyviolation', e => (window.__csp = window.__csp || []).push(e.violatedDirective + ' ' + e.blockedURI))")
    return ctx, pg

def boot(pg, hash_=""):
    pg.goto(U + hash_); pg.wait_for_function("window.GTB&&GTB.ready"); settle(pg, 300)

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=GL)
    ctx, pg = page(b, viewport={"width": 1440, "height": 900}); boot(pg)
    reg = pg.evaluate("({F: GTB_REGISTRY.F.map(f=>({id:f.id,cat:f.cat,name:f.name,view:f.route.view,impl:f.impl})), C: GTB_REGISTRY.CATS.map(c=>c.id)})")
    ids = [f["id"] for f in reg["F"]]
    res("registry: unique feature ids", len(ids) == len(set(ids)), len(ids))
    res("registry: every route targets a known renderer", all(f["view"] in ["token", "wallet", "replay", "shill", "copy", "threats", "board", "prov", "signals", "market", "universe", "tcg"] for f in reg["F"]))  # RC-M10: Card Explorer renderer (see RC-TEST-MIGRATIONS.md)
    navf = pg.evaluate("[...document.querySelectorAll('#views .navm [data-feat]')].map(b=>b.dataset.feat)")
    res("nav menus are generated from the registry (same ids, no duplicates)", sorted(navf) == sorted(i for i in ids if True) and len(navf) == len(set(navf)), len(navf))
    res("Anomalies is a top-level destination, not inside a category", pg.locator("#views > [data-view=anomalies]").count() == 1)
    # category menus: click opens correct menu, only one open at a time, never clipped on the right
    bad = []
    for c in pg.evaluate("[...document.querySelectorAll('#views [data-cat]')].map(b=>b.dataset.cat)"):
        pg.click(f"#nt-{c}"); pg.wait_for_timeout(60)
        st = pg.evaluate(f"""(()=>{{const t=document.getElementById('nt-{c}'),m=document.getElementById('nm-{c}'),r=m.getBoundingClientRect();
          const open=[...document.querySelectorAll('.navm')].filter(x=>!x.hidden).length; const it=m.querySelector('.ni').getBoundingClientRect(); const top=document.elementFromPoint(it.left+it.width/2,it.top+it.height/2);
          return {{exp:t.getAttribute('aria-expanded'),ctl:t.getAttribute('aria-controls'),vis:!m.hidden,open,right:r.right,vw:innerWidth,onTop:!!(top&&m.contains(top))}}}})()""")
        if not (st["exp"] == "true" and st["ctl"] == f"nm-{c}" and st["vis"] and st["open"] == 1 and st["right"] <= st["vw"] - 4 and st["onTop"]): bad.append((c, st))
    res("every category click opens its own menu: aria-expanded/controls, one open, not clipped, above the WebGL stage", not bad, bad)
    pg.keyboard.press("Escape"); pg.click("#nt-crypto"); pg.wait_for_timeout(300); o1 = pg.evaluate("!document.getElementById('nm-crypto').hidden"); pg.click("#nt-crypto"); pg.wait_for_timeout(60); res("click toggles the menu open and closed", o1 and pg.evaluate("document.getElementById('nm-crypto').hidden"))
    # hover intent
    pg.mouse.move(5, 600); pg.wait_for_timeout(350)
    bx = pg.locator("#nt-tcg").bounding_box(); pg.mouse.move(bx["x"] + 10, bx["y"] + 10); pg.wait_for_timeout(60)
    early = pg.evaluate("!document.getElementById('nm-tcg').hidden"); pg.wait_for_timeout(250)
    late = pg.evaluate("!document.getElementById('nm-tcg').hidden")
    res("hover opens after an intentional delay (closed at 60 ms, open by 310 ms)", (not early) and late, (early, late))
    mb = pg.locator("#nm-tcg .ni").first.bounding_box()
    for i in range(8): pg.mouse.move(bx["x"] + 10, bx["y"] + bx["height"] + (mb["y"] + 10 - bx["y"] - bx["height"]) * i / 7); pg.wait_for_timeout(25)
    pg.wait_for_timeout(400); res("menu stays open while the pointer travels from trigger to items", pg.evaluate("!document.getElementById('nm-tcg').hidden"))
    pg.mouse.move(700, 700); pg.wait_for_timeout(450); res("menu closes after the pointer leaves", pg.evaluate("document.getElementById('nm-tcg').hidden"))
    pg.click("#nt-ratesfx"); pg.mouse.click(700, 860); pg.wait_for_timeout(80); res("click outside closes the menu", pg.evaluate("document.getElementById('nm-ratesfx').hidden"))
    # keyboard
    pg.focus("#nt-commodities"); pg.keyboard.press("Enter"); pg.wait_for_timeout(60)
    k1 = pg.evaluate("!document.getElementById('nm-commodities').hidden && document.activeElement.classList.contains('ni')")
    pg.keyboard.press("ArrowDown"); k2 = pg.evaluate("document.activeElement.dataset.feat")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(40)
    k3 = pg.evaluate("document.getElementById('nm-commodities').hidden && document.activeElement.id==='nt-commodities'")
    fv = pg.evaluate("getComputedStyle(document.activeElement).outlineStyle!=='none'")
    pg.keyboard.press(" "); pg.wait_for_timeout(40); k4 = pg.evaluate("!document.getElementById('nm-commodities').hidden"); pg.keyboard.press("Escape")
    res("keyboard: Enter opens and focuses first tool, ArrowDown moves, Escape closes and returns focus, Space opens, focus visible", k1 and k2 == "cm.energy" and k3 and k4 and fv, (k1, k2, k3, k4, fv))
    pg.focus("#nt-tcg"); pg.keyboard.press("Enter"); [pg.keyboard.press("Tab") for _ in range(4)]; pg.wait_for_timeout(40)
    res("Tab moves out of an open menu and closes it", pg.evaluate("document.getElementById('nm-tcg').hidden"), pg.evaluate("document.activeElement.id||document.activeElement.className"))
    # every visible feature reaches a working destination
    broken = []
    for f in reg["F"]:
        pg.evaluate("GTB.go('home')"); pg.click(f"#nt-{f['cat']}"); pg.click(f"#nm-{f['cat']} [data-feat='{f['id']}']"); pg.wait_for_timeout(120)
        st = pg.evaluate("""(()=>({view:GTB.S.view, h:(document.querySelector('#rhead h1')||{}).textContent||'', panel:(document.getElementById('panel').textContent||'').length, unknown:/Unknown view/.test(document.body.textContent), menus:[...document.querySelectorAll('.navm')].filter(x=>!x.hidden).length, cur:(document.querySelector('#views [data-feat][aria-current=page]')||{}).dataset}))()""")
        ok = not st["unknown"] and st["menus"] == 0 and st["view"] != "home" and (st["panel"] > 40 or st["view"] in ("token", "wallet", "replay")) and st["h"]
        if not ok: broken.append((f["id"], st))
    res("every registry feature opens a working destination and the menu closes", not broken, broken)
    pg.evaluate("GTB.goFeat('tcg.spread')"); pg.wait_for_timeout(80)
    res("active category and active feature are identifiable", pg.evaluate("document.getElementById('nt-tcg').classList.contains('act') && document.querySelector('#nm-tcg [data-feat=\"tcg.spread\"]').getAttribute('aria-current')==='page'"))
    # licence-gated classes never appear as tools
    gated = pg.evaluate("GTB_EV.EV.universe.filter(u=>u.status!=='shipped').map(u=>u.name.toLowerCase())")
    names = [n.lower() for n in pg.evaluate("[...document.querySelectorAll('#views .ni .nn')].map(e=>e.textContent)")]
    res("licence-gated / uncovered classes are not offered as nav tools", not [g for g in gated if any(g == n for n in names)] and not any("pok" in n or "watch" in n or "sneaker" in n for n in names))
    pg.evaluate("GTB.go('universe')"); pg.wait_for_timeout(100)
    res("Universe: uncovered tiles have no tool link; covered tiles open a tool directly", pg.evaluate("[...document.querySelectorAll('details.rest .tile')].every(t=>!t.querySelector('[data-feat-go]')) && document.querySelectorAll('details.fam:not(.rest) .tile [data-feat-go]').length>=15"))
    pg.click("details.fam:not(.rest) .tile [data-feat-go]"); pg.wait_for_timeout(100)
    res("Universe tile goes straight to its tool (no second selection screen)", pg.evaluate("GTB.S.view==='market'||GTB.S.view==='signals'"), pg.evaluate("GTB.S.view"))
    # data pages: only appropriate instruments
    mis = {}
    for fid, allowed in [("fx.rates", r"^EUR/"), ("cm.metals", r"^(GLD|IAU|SLV|PPLT|PALL|Gold|Silver|Platinum|Palladium)"), ("cm.energy", r"(WTI|Brent|Henry|DCOIL|DHHNG|crude|oil|gas)"), ("tcg.mtg", r".")]:
        pg.evaluate(f"GTB.goFeat('{fid}')"); pg.wait_for_timeout(80)
        rows = pg.evaluate("[...document.querySelectorAll('#panel td.nmc')].map(e=>e.textContent)")
        u = pg.evaluate(f"GTB_EV.EV.live.assets.filter(a=>GTB_REGISTRY.byId['{fid}'].route.uni.includes(a.universe)).map(a=>a.name)")
        if not rows or any(r not in u or not re.search(allowed, r, re.I) for r in rows): mis[fid] = rows[:5]
    res("market pages render only instruments of their own asset class", not mis, mis)
    # search routing
    # MIGRATED (RC2): the real cached markets report is now the first signals report, so equity/option tickers come from it
    # (an options-signal ticker -> Options Activity; a fetched equities ticker with no option signal -> Equity Signals) and an
    # unknown ticker (ZZZQ) takes the limited state that AAPL used to (AAPL is now in the fetched equities universe).
    tk = pg.evaluate("(()=>{const r=GTB.REPORTS.find(x=>x.k==='signals'),o=(r.j.signals||[]).filter(s=>s.source==='options').map(s=>String(s.instrument).split(':').pop()),u=(((r.j.sourceStatus||{}).equities||{}).coverage||{}).observedInstruments||[];return {opt:o[0]||null,eq:u.find(x=>!o.includes(x))||null}})()")
    cases = {"EUR/USD": "asset:fx:EUR/USD", "eurusd": "asset:fx:EUR/USD", "usd/jpy": "lim:", "gold": "asset:metals:GLD", "wti": "asset:energy:DCOILWTICO", "black lotus": "asset:mtg:Black Lotus", "will the fed cut in december?": "feat:pm.odds", "ZZZQ": "lim:", "$SYNTHING": "token:"}
    if tk["eq"]: cases[tk["eq"]] = "feat:eq.signals"
    if tk["opt"]: cases[tk["opt"]] = "feat:eq.options"
    wrong = {q: pg.evaluate("q=>GTB_SUG(q)[0]||''", q) for q in cases}
    wrong = {q: v for q, v in wrong.items() if cases[q] not in v}
    res("search dispatches instruments to the right tool (FX, metals, energy, MTG, equities, options, prediction, crypto)", not wrong, wrong)
    res("unsupported ticker is never sent through the Solana scanner", "token:" not in pg.evaluate("GTB_SUG('ZZZQ').join()"))  # MIGRATED (RC2): AAPL -> ZZZQ
    pg.evaluate("GTB.go('home')"); pg.fill("#q", "ZZZQ"); pg.keyboard.press("Enter"); pg.wait_for_timeout(120)  # MIGRATED (RC2): AAPL -> ZZZQ
    res("recognized but unloaded instrument shows a limited state, no verdict", pg.evaluate("GTB.S.view==='limited' && /unknown, not quiet/i.test(document.getElementById('panel').textContent) && !/Nothing flagged/.test(document.body.textContent)"))
    # unknown, not quiet
    pg.evaluate("GTB.goFeat('eq.sec')"); pg.wait_for_timeout(80)
    t = pg.evaluate("document.getElementById('panel').textContent")
    # MIGRATED (RC2): directive wording "Unknown / not assessed" replaces "Provider unavailable"; quiet wording is now "No findings in the assessed markets"
    res("provider not configured (SEC) shows 'Unknown / not assessed', never a quiet result", "Unknown / not assessed" in t and "No findings in the assessed" not in t, t[:160])
    pg.evaluate("GTB.goFeat('tcg.history')"); pg.wait_for_timeout(80)
    t = pg.evaluate("document.getElementById('panel').textContent")
    res("insufficient snapshot history is unassessable, not quiet", "Unassessable" in t and "Nothing past threshold" not in t, t[:160])
    pg.evaluate("GTB.goFeat('tcg.spread')"); pg.wait_for_timeout(80)
    t = pg.evaluate("document.getElementById('panel').textContent")
    res("cross-venue page says observed spread, not executable arbitrage; no profit claims", "not executable arbitrage" in t and not re.search(r"\b(guaranteed|risk-free|profit)\b", t, re.I))
    # real vs synthetic separation
    pg.evaluate("GTB.go('anomalies')"); pg.wait_for_timeout(80)
    a = pg.evaluate("(()=>{const it=GTB.anomalyItems();return {modes:[...new Set(it.map(x=>x.mode))], cachedSyn:it.filter(x=>x.mode==='cached'&&/SYN|synthetic/i.test(x.instrument+x.source+x.report)).length, cs2:it.filter(x=>x.source==='cs2'&&x.mode==='cached').length, cats:[...new Set(it.filter(x=>x.mode==='examples').map(x=>x.cat))].length, rows:document.querySelectorAll('#panel .erow').length, mode:GTB.S.aMode}})()")
    res("Anomalies defaults to real cached; no synthetic or experimental item in that mode", a["mode"] == "cached" and a["cachedSyn"] == 0 and a["cs2"] == 0, a)
    pg.click("[data-af=aMode][data-v=examples]"); pg.wait_for_timeout(80)
    e = pg.evaluate("(()=>{const r=[...document.querySelectorAll('#panel .erow')];return {n:r.length, allSyn:r.every(x=>x.classList.contains('syn')), box:!!document.querySelector('#panel .synbox')}})()")
    res("examples mode is visibly synthetic (hatched panel, every row marked) and spans several markets", e["n"] > 5 and e["allSyn"] and e["box"] and a["cats"] >= 4, (e, a["cats"]))
    pg.click("[data-af=aCat][data-v=prediction]"); pg.wait_for_timeout(80)
    pc = pg.evaluate("[...document.querySelectorAll('#panel .erow .eb > .hd:first-child > span:first-child')].map(e=>e.textContent.split(' // ')[0])")
    res("category filter narrows to that market only", pc and all(x.startswith("Prediction") for x in pc), pc[:4])
    dup = pg.evaluate("(()=>{const it=GTB.anomalyItems();const k=it.map(x=>x.key);return k.length-new Set(k).size})()")
    res("no incident is listed twice", dup == 0, dup)
    # unsafe imported JSON
    pg.evaluate("""GTB.addReport('evil-signals.json', {kind:'signals', generatedAt: 1793238420, sourceStatus:{equities:{state:'HEALTHY'}}, signals:[{key:'x1', source:'equities', type:'RETURN_VS_REALIZED_VOL', severity:'HIGH', basis:'observed', instrument:'equities:<img src=x onerror=window.__pwn=1>', title:'<img src=x onerror=window.__pwn=1>', what:'<script>window.__pwn=2</script>', when:1793238420}]})""")
    pg.evaluate("GTB.S.aMode='cached'; GTB.go('anomalies')"); pg.wait_for_timeout(150)
    res("imported JSON is escaped (no injected elements or script execution)", pg.evaluate("!window.__pwn && !document.querySelector('#panel img')"))
    ok = pg.evaluate("""(()=>{try{const n=GTB.REPORTS.length; const r=GTB.addReport('bad.json', {nonsense:true}); return r===false && GTB.REPORTS.length===n}catch(e){return false}})()""")
    res("corrupt / non-report JSON is rejected without changing state", ok)
    # notification placement
    pg.evaluate("GTB.go('home')"); pg.wait_for_timeout(100)
    pg.evaluate("GTB.S.notifAt=0; GTB.notify({id:'t',c:'red',mkt:'FX',subject:'EUR/USD',text:'test',ts:1793238420,open:'signals'})"); pg.wait_for_timeout(500)
    nb = pg.evaluate("(()=>{const n=document.getElementById('notif').getBoundingClientRect(),v=document.getElementById('views').getBoundingClientRect(),h=document.querySelector('header').getBoundingClientRect();return {on:document.getElementById('notif').classList.contains('on'),top:n.top,navB:v.bottom,txt:document.getElementById('notif').textContent}})()")
    res("desktop notification sits below the nav and says replayed, not 'just happened'", nb["on"] and nb["top"] >= nb["navB"] and "Just happened" not in nb["txt"] and "Replayed" in nb["txt"], nb)
    pg.evaluate("document.getElementById('notif').classList.remove('on')"); pg.click("#nt-crypto")
    pg.evaluate("GTB.S.notifAt=0; GTB.notify({id:'t2',c:'red',mkt:'FX',subject:'x',text:'t',ts:1,open:'signals'})"); pg.wait_for_timeout(300)
    res("no notification while a menu is open", not pg.evaluate("document.getElementById('notif').classList.contains('on')")); pg.keyboard.press("Escape")
    # result sequence: intermediate frames (entry, punch, rows, roll, settled)
    tid = pg.evaluate("GTB.targets().find(t=>t.view==='token').id")
    for vw, vh in [(1440, 900), (1920, 1080), (768, 1024), (390, 844)]:
        pg.set_viewport_size({"width": vw, "height": vh}); pg.evaluate("id=>GTB.scan(id,true)", tid); pg.wait_for_timeout(900)
        issues = {}
        for B in [300, 420, 600, 1500, 2600, 20000]:
            pg.evaluate("B=>{GTB.S.scanning=false; GTB.S.t0=performance.now()-B}", B); pg.wait_for_timeout(200 if B < 20000 else 500)
            out = [x for x in check(pg, True) if "bot" in x or "overlap" in x or "outside" in x]
            if out: issues[B] = out
        res(f"result sequence {vw}x{vh}: no bot/RESULT/stats/verdict/TL;DR collision at entry, punch, rows, roll, settled", not issues, issues)
    # Home composition at narrow widths
    bad = {}
    for w in [320, 375, 390, 430, 768]:
        pg.set_viewport_size({"width": w, "height": 800}); pg.evaluate("GTB.go('home')"); pg.wait_for_timeout(500)
        o = check(pg, True)
        if o: bad[w] = o
    res("mobile Home: bot, headline, copy, search and controls do not collide (320/375/390/430/768)", not bad, bad)
    # overflow on all views at supported widths
    ov = {}
    for w in [320, 375, 768, 1024, 1440]:
        pg.set_viewport_size({"width": w, "height": 820})
        for v in ["universe", "anomalies", "f:fx.rates", "f:pm.odds", "f:tcg.mtg", "f:more.cs2"]:
            pg.evaluate("v=>v.startsWith('f:')?GTB.goFeat(v.slice(2)):GTB.go(v)", v); pg.wait_for_timeout(60)
            sw = pg.evaluate("document.documentElement.scrollWidth - innerWidth")
            if sw > 1: ov[f"{w}:{v}"] = sw
    res("no horizontal page overflow on directory, anomalies and tool pages (320-1440)", not ov, ov)
    pg.set_viewport_size({"width": 1024, "height": 768}); pg.evaluate("GTB.go('home')"); pg.click("#nt-more"); pg.wait_for_timeout(60)
    r = pg.evaluate("document.getElementById('nm-more').getBoundingClientRect().right")
    res("rightmost menu stays inside a 1024 px viewport", r <= 1020, r); pg.keyboard.press("Escape")
    res("CSP enforced: no violations; zero off-origin requests; no page errors (desktop)", not pg.evaluate("window.__csp||[]") and not pg.off and not pg.errs, (pg.evaluate("window.__csp||[]"), pg.off[:3], pg.errs[:3]))
    ctx.close()

    # mobile / touch
    ctx, m = page(b, viewport={"width": 375, "height": 812}, has_touch=True, is_mobile=True); boot(m)
    res("mobile: category triggers hidden, compact Markets control shown with Home and Anomalies", m.evaluate("getComputedStyle(document.getElementById('mktBtn')).display!=='none' && !document.getElementById('nt-crypto').offsetParent && !!document.querySelector('#views > [data-view=anomalies]').offsetParent && !!document.querySelector('#views > [data-view=home]').offsetParent"))
    m.tap("#mktBtn"); m.wait_for_timeout(80); m.tap("#mg-prediction"); m.wait_for_timeout(80)
    s1 = m.evaluate("!document.getElementById('mgi-prediction').hidden && document.getElementById('mg-prediction').getAttribute('aria-expanded')==='true'")
    m.tap("#mgi-prediction [data-feat='pm.volume']"); m.wait_for_timeout(120)
    s2 = m.evaluate("GTB.S.feat==='pm.volume' && document.getElementById('mobMenu').hidden && document.getElementById('mktBtn').getAttribute('aria-expanded')==='false'")
    res("mobile: tap category reveals tools, tap tool navigates and the menu closes", s1 and s2, (s1, s2))
    m.tap("#mktBtn"); m.wait_for_timeout(60); m.tap("footer p"); m.wait_for_timeout(60)
    res("mobile: tapping outside dismisses the Markets menu", m.evaluate("document.getElementById('mobMenu').hidden"))
    m.evaluate("GTB.go('home')"); m.wait_for_timeout(200)
    m.evaluate("GTB.S.notifAt=0; GTB.notify({id:'m',c:'red',mkt:'FX',subject:'x',text:'t',ts:1,open:'signals'})"); m.wait_for_timeout(400)
    res("mobile: no notification overlay over the header (counter bump instead)", not m.evaluate("document.getElementById('notif').classList.contains('on')"))
    tt = m.evaluate("[...document.querySelectorAll('#views .nt, #mobMenu .mg')].filter(e=>e.offsetParent).map(e=>e.getBoundingClientRect().height).filter(h=>h<44).length")
    res("mobile: nav tap targets >= 44 px", tt == 0, tt)
    res("mobile: no off-origin requests, CSP violations or page errors", not m.off and not m.evaluate("window.__csp||[]") and not m.errs, (m.off[:2], m.errs[:2]))
    ctx.close()

    # reduced motion + WebGL fallback
    ctx, r = page(b, viewport={"width": 1440, "height": 900}, reduced_motion="reduce"); r.goto(U + "?nowebgl"); r.wait_for_function("window.GTB&&GTB.ready"); r.wait_for_timeout(300)
    r.click("#nt-prediction"); r.wait_for_timeout(30); o1 = r.evaluate("!document.getElementById('nm-prediction').hidden"); r.keyboard.press("Escape")
    r.evaluate("id=>GTB.scan(id)", r.evaluate("GTB.targets().find(t=>t.view==='asset').id")); r.wait_for_timeout(300)
    res("reduced motion + no WebGL: menus respond, result lands immediately, static fallback shown", o1 and r.evaluate("document.getElementById('vdBox').dataset.landed==='1' && document.getElementById('stageWrap').classList.contains('stage-static') || document.querySelector('.stage-static')!==null"), o1)
    res("reduced motion: no CSP violations or page errors", not r.evaluate("window.__csp||[]") and not r.errs, r.errs[:2])
    ctx.close(); b.close()
print(f"ui_rc: {sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
