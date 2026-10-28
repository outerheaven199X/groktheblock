"""UI-01 (RE-AUDIT §05): Chrome device emulation, NOT real devices. 375/390/768/desktop, 200% zoom, keyboard, reduced motion."""
import json, sys
from playwright.sync_api import sync_playwright
U = "http://localhost:8768/ui/"; UE = "http://localhost:8769/ui/"
R = []
def res(n, ok, d=""): print("PASS" if ok else "FAIL", n, "-", d); R.append(ok)
def pick(pg, sub):
    for _ in range(30):
        if sub in pg.evaluate("cur().name"): return True
        pg.keyboard.press("]"); pg.wait_for_timeout(120)
    return False
OVER = """(()=>{const W=document.documentElement.clientWidth;const bad=[...VIEW_EL.querySelectorAll('*')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.right>W+1&&!e.closest('.tw')&&getComputedStyle(e).position!=='fixed'}).slice(0,5).map(e=>e.tagName+'.'+e.className);
const h=VIEW_EL.querySelector('.band h1');return{sw:document.documentElement.scrollWidth,W,bad,h1:h?h.scrollWidth<=h.clientWidth+1&&h.getBoundingClientRect().right<=W+1:false,
sum:(()=>{const s=VIEW_EL.querySelector('.sum');return s?s.getBoundingClientRect().top<innerHeight:false})()}})()"""
SIZES = [("375", {"viewport": {"width": 375, "height": 812}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}),
         ("390", {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}),
         ("768", {"viewport": {"width": 768, "height": 1024}, "device_scale_factor": 2, "has_touch": True}),
         ("desktop", {"viewport": {"width": 1440, "height": 1000}}),
         ("zoom200", {"viewport": {"width": 720, "height": 500}, "device_scale_factor": 2}),  # 1440×1000 at 200% browser zoom = 720×500 CSS px
         ("reduced", {"viewport": {"width": 390, "height": 844}, "reduced_motion": "reduce", "is_mobile": True, "has_touch": True})]
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    for name, args in SIZES:
        pg = b.new_page(**args); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(U); pg.wait_for_function("!S.loading"); pg.evaluate("go('signals')"); pg.wait_for_timeout(300)
        for rep in ("EXAMPLE", "outage", "v1-legacy"):
            pick(pg, rep); pg.evaluate("scrollTo(0,0)"); pg.wait_for_timeout(500)
            o = pg.evaluate(OVER)
            res(f"{name} {rep} no horizontal overflow", o["sw"] <= o["W"] and not o["bad"], json.dumps(o))
            res(f"{name} {rep} hero title not clipped", o["h1"])
            res(f"{name} {rep} first screen shows the summary", o["sum"])
        pick(pg, "EXAMPLE"); pg.evaluate("scrollTo(0,0)")
        t = pg.evaluate("""(()=>{const s=VIEW_EL.querySelector('.sum');return s?[...s.querySelectorAll('.lab')].map(x=>x.textContent):[]})()""")
        res(f"{name} summary answers what/fresh/observed/why", t == ["What happened", "How fresh", "What was observed", "Why it was flagged"], t)
        res(f"{name} no prominent rank in hero", not pg.evaluate("VIEW_EL.querySelector('.read').textContent.toLowerCase().includes('rank')"))
        # dossier: no duplicated timestamps
        q = pg.locator("#app>div:not([hidden]) [data-src]:not([hidden]) .q").first; q.scroll_into_view_if_needed(); q.click(); pg.wait_for_timeout(300)
        d = pg.evaluate("""(()=>{const li=[...VIEW_EL.querySelectorAll('.a:not([hidden]) .tline')[0].querySelectorAll('li')].map(l=>(l.textContent.match(/\\d{4}-\\d\\d-\\d\\d \\d\\d:\\d\\d UTC/)||[''])[0]).filter(Boolean);return{li,dup:li.length!==new Set(li).size}})()""")
        res(f"{name} dossier timeline has no duplicated timestamps", not d["dup"], d)
        for rep in ("EXAMPLE", "optsnap", "outage"):
            pick(pg, rep); pg.wait_for_timeout(300)
            pg.evaluate("VIEW_EL.querySelectorAll('[data-src]:not([hidden]) .q').forEach(q=>{if(q.getAttribute('aria-expanded')!=='true')q.click()})"); pg.wait_for_timeout(600)
            dc = pg.evaluate("""(()=>{const W=document.documentElement.clientWidth;return [...VIEW_EL.querySelectorAll('.dossier *')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&(r.right>W+1||e.scrollWidth>e.clientWidth+2&&getComputedStyle(e).overflowX!=='visible')}).slice(0,4).map(e=>e.tagName+'.'+e.className+' '+e.textContent.slice(0,40))})()""")
            n = pg.evaluate("VIEW_EL.querySelectorAll('.dossier').length")
            res(f"{name} {rep} every dossier ({n}) readable without clipping", not dc and n > 0, dc)
        if name in ("375", "390"):
            res(f"{name} coverage matrix stacked", pg.evaluate("getComputedStyle(VIEW_EL.querySelector('table.matrix thead')).display==='none'"))
            cl = pg.evaluate("""[...VIEW_EL.querySelectorAll('table.matrix td')].filter(td=>{const r=td.getBoundingClientRect(),t=td.closest('.tw').getBoundingClientRect();return td.scrollWidth>td.clientWidth+1||r.right>t.right+1}).length""")
            res(f"{name} coverage matrix cells not clipped", cl == 0, cl)
        if name == "reduced":
            res("reduced: hero has no marquee animation", pg.evaluate("!VIEW_EL.querySelector('.band .track')"))
        # graph: keyboard selection + persistence (shill view)
        if name in ("desktop", "390", "zoom200"):
            pg.evaluate("go('shill')"); pg.wait_for_timeout(1500)
            pg.evaluate("VIEW_EL.querySelector('#g').focus()"); pg.keyboard.press("ArrowRight"); pg.wait_for_timeout(200); pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
            on = pg.evaluate("VIEW_EL.querySelector('#gp').classList.contains('on')")
            res(f"{name} graph node selected by keyboard", on)
            fv = pg.evaluate("document.activeElement.id==='g'&&document.activeElement.matches(':focus-visible')")
            res(f"{name} graph keyboard focus visible", fv)
            pg.evaluate("go('signals')"); pg.wait_for_timeout(300); pg.evaluate("go('shill')"); pg.wait_for_timeout(1200)
            res(f"{name} graph selection persists across tab switch", pg.evaluate("VIEW_EL.querySelector('#gp').classList.contains('on')"))
        res(f"{name} no page errors", not errs, errs)
        pg.close()
    # zero convergence: one sentence, no rank
    pg = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg.goto(U); pg.wait_for_function("!S.loading"); pg.evaluate("go('signals')"); pick(pg, "empty"); pg.wait_for_timeout(400)
    z = pg.evaluate("""(()=>{const h=[...VIEW_EL.querySelectorAll('h2')].find(h=>h.textContent==='Related observations');const b=h&&h.closest('section').querySelector('.body');return b?b.textContent.trim():null})()""")
    res("zero related observations collapse to one sentence", z == "No related observations across independent evidence groups this run.", z)
    pg.close()
print("ALL PASS" if all(R) else "SOME FAIL", f"{sum(R)}/{len(R)}")
