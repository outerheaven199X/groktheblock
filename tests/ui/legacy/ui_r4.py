"""R4-03 / R4-07 UI checks in Chromium device EMULATION (not real iOS/Android/Safari).
Usage: ui_r4.py <base-url> <label> <screens-dir>   e.g. http://localhost:8768/ui/ after /tmp/shots
Checks: no overlapping badges at 375px and 200% zoom, tap targets ≥ 44px tall, visible focus on feed rows,
no exact hour span / "simultaneous" on timing-approximate related observations (desktop + mobile)."""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
U, LABEL, OUT = sys.argv[1], sys.argv[2], Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)
R = []
def res(n, ok, d=""): print("PASS" if ok else "FAIL", n, "-", str(d)[:300]); R.append(ok)
def pick(pg, sub):
    for _ in range(30):
        if sub in pg.evaluate("cur().name"): return True
        pg.keyboard.press("]"); pg.wait_for_timeout(120)
    return False
OVERLAP = """(()=>{const ov=(a,b)=>Math.max(0,Math.min(a.right,b.right)-Math.max(a.left,b.left))*Math.max(0,Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top));
const out=[];let n=0;
VIEW_EL.querySelectorAll('[data-src]:not([hidden]) .sigrow .d').forEach(d=>{const chips=[...d.querySelectorAll(':scope>.calchip')];if(!chips.length)return;n+=chips.length;
 const cr=chips.map(c=>c.getBoundingClientRect());
 for(let i=0;i<cr.length;i++)for(let j=i+1;j<cr.length;j++)if(ov(cr[i],cr[j])>1)out.push('chip/chip '+chips[i].textContent+' | '+chips[j].textContent);
 const tw=document.createTreeWalker(d,NodeFilter.SHOW_TEXT);let t;while(t=tw.nextNode()){if(t.parentElement.closest('.calchip')||!t.textContent.trim())continue;const r=document.createRange();r.selectNodeContents(t);
  for(const tr of r.getClientRects())cr.forEach((c,i)=>{if(ov(tr,c)>2)out.push('chip/text '+chips[i].textContent+' over "'+t.textContent.slice(0,30)+'"')})}
 chips.forEach((c,i)=>{const p=c.querySelector('.phase');if(p){const pr=p.getBoundingClientRect();if(pr.right>cr[i].right+0.5||pr.left<cr[i].left-0.5||pr.top<cr[i].top-0.5||pr.bottom>cr[i].bottom+0.5)out.push('phase outside chip '+c.textContent)}})});
return{n,out:out.slice(0,6)}})()"""
SIZES = [("375", {"viewport": {"width": 375, "height": 812}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}),
         ("390", {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}),
         ("zoom200", {"viewport": {"width": 720, "height": 500}, "device_scale_factor": 2}),
         ("desktop", {"viewport": {"width": 1440, "height": 1000}})]
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    for name, args in SIZES:
        pg = b.new_page(**args); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(U); pg.wait_for_function("!S.loading"); pg.evaluate("go('signals')"); pg.wait_for_timeout(300)
        pick(pg, "EXAMPLE"); pg.evaluate("scrollTo(0,0)"); pg.wait_for_timeout(500)
        pg.screenshot(path=str(OUT / f"{LABEL}-{name}-01-signals-top.png"))
        o = pg.evaluate(OVERLAP)
        if name in ("375", "390", "zoom200"):
            res(f"{name} feed badges (n={o['n']}) do not overlap each other or the title text", o["n"] > 0 and not o["out"], o)
        c = pg.locator("#app>div:not([hidden]) [data-src]:not([hidden]) .calchip").first
        if c.count():
            c.scroll_into_view_if_needed(); pg.evaluate("scrollBy(0,-120)"); pg.wait_for_timeout(300)
            pg.screenshot(path=str(OUT / f"{LABEL}-{name}-02-feed-badges.png"))
        h = pg.evaluate("Math.min(...[...VIEW_EL.querySelectorAll('[data-src]:not([hidden]) .sigrow')].map(e=>e.getBoundingClientRect().height))")
        res(f"{name} feed rows are tap targets ≥ 44px tall", h >= 44, h)
        pg.evaluate("VIEW_EL.querySelector('[data-src]:not([hidden]) .sigrow').scrollIntoView({block:'center'})")
        for _ in range(60):
            pg.keyboard.press("Tab")
            if pg.evaluate("document.activeElement.classList.contains('sigrow')"): break
        f = pg.evaluate("(()=>{const e=document.activeElement;const s=getComputedStyle(e);return{row:e.classList.contains('sigrow'),fv:e.matches(':focus-visible'),outline:s.outlineStyle!=='none'&&parseFloat(s.outlineWidth)>0||s.boxShadow!=='none'}})()")
        res(f"{name} keyboard focus on a feed row is visible", f["row"] and f["fv"] and f["outline"], f)
        pg.screenshot(path=str(OUT / f"{LABEL}-{name}-03-feed-focus.png"))
        # related observations: timing
        rep = "timing" if LABEL == "after" else "EXAMPLE"
        pick(pg, rep); pg.wait_for_timeout(500)
        cv = pg.locator("#app>div:not([hidden]) .cv").first
        if cv.count():
            cv.scroll_into_view_if_needed(); pg.evaluate("scrollBy(0,-80)"); pg.wait_for_timeout(300)
            pg.screenshot(path=str(OUT / f"{LABEL}-{name}-04-related-observations.png"))
            t = pg.evaluate("[...VIEW_EL.querySelectorAll('.cv')].map(c=>c.textContent).join(' || ')")
            low = pg.evaluate("[...VIEW_EL.querySelectorAll('.cv')].some(c=>/lower bound|estimated|daily/.test(c.textContent))")
            res(f"{name} related observations with lower-bound/estimated times show no exact span", ("0.0h" not in t and "simultaneous" not in t.lower()) or not low, t[:200])
            res(f"{name} related observations say 'timing comparison approximate'", "timing comparison approximate" in t, t[:200])
            res(f"{name} related observations say 'distinct counted evidence groups'", "distinct counted evidence groups" in t and "independent evidence groups" not in t, t[:160])
            pg.locator("#app>div:not([hidden]) [data-src]:not([hidden]) .q").first.click(); pg.wait_for_timeout(400)
            pg.screenshot(path=str(OUT / f"{LABEL}-{name}-05-dossier.png"), full_page=False)
        else:
            res(f"{name} a related-observations card exists in the {rep} report", False)
        res(f"{name} no page errors", not errs, errs[:2])
        pg.close()
    b.close()
print(f"ui_r4 [{LABEL}]: {sum(R)}/{len(R)} passed (Chromium emulation)")
sys.exit(0 if all(R) else 1)
