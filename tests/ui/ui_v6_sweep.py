"""Viewport / DPR / zoom layout sweep for the v6 UI in Chromium EMULATION (Playwright). Not real devices.
Usage: python tests/ui/ui_v6_sweep.py [base-url] [--quick]   (serve the repo root: python -m http.server 8821)
Browser zoom Z is emulated as CSS viewport W/Z x H/Z at device scale DPR*Z (what Chrome does at Z zoom)."""
import json, sys, time
from playwright.sync_api import sync_playwright
sys.path.insert(0, __import__("os").path.dirname(__file__))
from v6_layout import inject, end_state, check, settle
args = [a for a in sys.argv[1:] if not a.startswith("--")]
U = args[0] if args else "http://localhost:8821/ui/"
QUICK = "--quick" in sys.argv
VPS = [(2560, 1440), (1920, 1080), (1680, 1050), (1600, 900), (1536, 864), (1440, 900), (1366, 768), (1280, 800), (1280, 720), (1280, 600), (1180, 680),
       (1024, 768), (1024, 556), (800, 600), (820, 1180), (768, 1024), (844, 390), (667, 375), (430, 932), (414, 896), (390, 844), (375, 667), (360, 640), (320, 568)]
SCALES = [(1, 1)]
EXTRA = [(1.25, 1), (1.5, 1), (1, 1.25), (1, 1.5)]  # (dpr, zoom)
EXTRA_VPS = [(1920, 1080), (1536, 864), (1366, 768), (1280, 720), (1024, 556), (390, 844)]
combos = [(vp, 1, 1) for vp in VPS] + [(vp, d, z) for vp in EXTRA_VPS for d, z in EXTRA]
if QUICK: combos = [c for c in combos if c[0] in [(1024, 556), (1280, 720), (390, 844), (844, 390), (320, 568)]]
TOK = ["token:SYNTHING", "token:SYNFART", "token:SYNBOT", "token:SYNTHETICEXTRALONGTICKERNAME2026", "token:SYNMISS", "token:SYNEMPTY"]
fails, total = [], 0
def rec(tag, issues):
    global total; total += 1
    if issues: fails.append((tag, issues)); print("FAIL", tag, issues[:4], flush=True)
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    for (w, h), dpr, z in combos:
        tag0 = f"{w}x{h}@dpr{dpr}" + (f"/zoom{int(z*100)}" if z != 1 else "")
        ctx = b.new_context(viewport={"width": round(w / z), "height": round(h / z)}, device_scale_factor=dpr * z, reduced_motion="reduce", bypass_csp=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(U); pg.wait_for_function("window.GTB&&GTB.ready"); inject(pg); settle(pg, 400)
        rec(tag0 + " home", check(pg))
        ids = [t for t in pg.evaluate("GTB.targets().map(t=>t.id)") if t.startswith(("wallet", "replay"))][:2]
        for tid in TOK + ids:
            end_state(pg, tid); rec(f"{tag0} {tid} end", check(pg))
        end_state(pg, "token:SYNTHING")
        for i in range(3):
            tabs = pg.locator("#details [role=tab]")
            if tabs.count() > i: tabs.nth(i).click(); pg.wait_for_timeout(80); rec(f"{tag0} details tab {i}", check(pg, False))
        pg.evaluate("GTB.go('token')") if False else None
        pg.click("#feedBtn"); pg.wait_for_timeout(250); rec(f"{tag0} feed open", check(pg, False)); pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        pg.evaluate("GTB.notify && GTB.notify(GTB.targets()[0] && {id:'x',mkt:'Solana',subject:'$SYNTHETICEXTRALONGTICKERNAME2026',text:'A very long synthetic notification title that keeps going to test wrapping inside the toast',sev:'HIGH'})"); pg.wait_for_timeout(200)
        rec(f"{tag0} toast", check(pg, False))
        for v in ["signals", "threats", "shill", "copy", "board", "prov"]:
            pg.evaluate("v=>GTB.go(v)", v); pg.wait_for_timeout(120); rec(f"{tag0} view {v}", check(pg, False))
        if errs: rec(tag0 + " page errors", errs)
        ctx.close()
    # resize mid-animation and after the result (motion ON)
    for (w0, h0), (w1, h1) in [((1440, 900), (1024, 556)), ((1024, 556), (390, 844)), ((390, 844), (1366, 768)), ((1920, 1080), (844, 390))]:
        ctx = b.new_context(viewport={"width": w0, "height": h0}, bypass_csp=True); pg = ctx.new_page()
        pg.goto(U); pg.wait_for_function("window.GTB&&GTB.ready"); settle(pg, 300)
        pg.evaluate("GTB.scan('token:SYNTHING',true)"); pg.wait_for_timeout(1500); pg.set_viewport_size({"width": w1, "height": h1})
        pg.wait_for_function("document.getElementById('vdBox').dataset.landed==='1'", timeout=60000); pg.wait_for_timeout(2500)
        rec(f"resize mid-animation {w0}x{h0}->{w1}x{h1}", check(pg))
        pg.set_viewport_size({"width": w0, "height": h0}); pg.wait_for_timeout(2500); rec(f"resize after result {w1}x{h1}->{w0}x{h0}", check(pg))
        ctx.close()
print(json.dumps({"checks": total, "failed": len(fails)}))
json.dump({"checks": total, "fails": fails}, open("/tmp/v6-sweep.json", "w"), indent=1)
sys.exit(1 if fails else 0)
