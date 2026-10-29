"""Adversarial browser checks against the npm launcher (packages/cli), Chromium EMULATION via Playwright + SwiftShader.
CSP is ENFORCED (no bypass_csp). Usage: python3 tests/ui/ui_security.py [path-to-cli-bin]
Starts `node <bin> --no-open`, then: safeExternalUrl unit matrix in-page, javascript:/data:/vbscript:/file: evidence and
universe links (click, no execution), HTML/SVG/event-handler/template/1MB payloads, prototype pollution, off-origin
requests, CSP violations, framing/POST/PUT from a foreign origin, 10-view navigation, JSON import via the file picker."""
import json, os, re, subprocess, sys, time, tempfile
from playwright.sync_api import sync_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIN = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "packages/cli/bin/grok-the-block.mjs")
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
R = []
def res(n, ok, d=""): print("PASS" if ok else "FAIL", n, "-", str(d)[:300]); R.append(bool(ok))
proc = subprocess.Popen(["node", BIN, "--no-open"], stdout=subprocess.PIPE, text=True, env={"PATH": os.environ["PATH"]})
U = None
for _ in range(50):
    m = re.search(r"http://127\.0\.0\.1:\d+/", proc.stdout.readline())
    if m: U = m.group(0); break
ORIGIN = U.rstrip("/")
import atexit; atexit.register(lambda: proc.poll() is None and proc.kill())
BADURLS = ["javascript:window.__pwn=1", "JaVaScRiPt:window.__pwn=1", " javascript:window.__pwn=1", "\tjavascript:window.__pwn=1", "java\nscript:window.__pwn=1",
  "javascript%3Awindow.__pwn=1", "&#106;avascript:window.__pwn=1", "data:text/html,<script>parent.__pwn=1</script>", "vbscript:msgbox(1)", "file:///etc/passwd",
  "http://example.com", "//evil.example/x", "https:evil", "https://user:pw@evil.example/", "https://exa mple.com", "https:\\\\evil.example", "", None, 42, {"toString": 1}]
GOOD = ["https://www.ecb.europa.eu/stats/", "HTTPS://fred.stlouisfed.org/series/DCOILWTICO"]
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=GL)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}); pg = ctx.new_page(); errs, off = [], []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
    pg.on("request", lambda r: (not r.url.startswith((ORIGIN, "data:", "blob:"))) and off.append(r.url))
    pg.on("dialog", lambda d: (errs.append("DIALOG " + d.message), d.dismiss()))
    pg.add_init_script("document.addEventListener('securitypolicyviolation', e => (window.__csp = window.__csp || []).push(e.violatedDirective + ' ' + e.blockedURI))")
    # tamper the universe data: first class gets a javascript: source link (simulates a poisoned data file)
    def tamper(route):
        r = route.fetch(); body = r.text().replace('"sourceUrl":"', '"sourceUrl":"javascript:window.__pwn=9;//', 1); route.fulfill(response=r, body=body)
    pg.route("**/data/everything.js", tamper)
    pg.goto(U); pg.wait_for_function("window.GTB&&GTB.ready", timeout=20000); pg.wait_for_timeout(400)
    res("served by the npm launcher with CSP meta (no unsafe-inline in script-src)", pg.evaluate("(()=>{const c=document.querySelector('meta[http-equiv=Content-Security-Policy]').content;return /script-src 'self' 'sha256-/.test(c)&&!/script-src[^;]*unsafe-inline/.test(c)&&/connect-src 'none'/.test(c)})()"))
    res("import map executed under hashed CSP (three.js stage loaded)", pg.evaluate("!!document.querySelector('canvas')") and not pg.evaluate("window.__csp||[]"), pg.evaluate("window.__csp||[]"))
    bad = pg.evaluate("(a)=>a.map(v=>GTB_safeExternalUrl(v))", BADURLS); good = pg.evaluate("(a)=>a.map(v=>GTB_safeExternalUrl(v))", GOOD)
    res("safeExternalUrl rejects every non-https / malformed / encoded / credentialed variant", all(x is None for x in bad), list(zip(map(str, BADURLS), bad)))
    res("safeExternalUrl accepts explicit https and normalises", good == ["https://www.ecb.europa.eu/stats/", "https://fred.stlouisfed.org/series/DCOILWTICO"], good)
    # malicious imported evidence links + HTML payloads + 1MB string + prototype pollution
    big = "A" * (1 << 20)
    ev = [{"label": "EV-" + str(i), "url": u} for i, u in enumerate(BADURLS[:10])] + [{"label": "EV-OK", "url": GOOD[0]}]
    rep = {"kind": "signals", "generatedAt": 1793238420, "sourceStatus": {"equities": {"state": "HEALTHY"}}, "signals": [{"key": "sec1", "source": "equities", "type": "RETURN_VS_REALIZED_VOL", "severity": "HIGH", "basis": "observed",
        "instrument": "equities:EVIL", "title": "<svg onload=window.__pwn=2><img src=x onerror=window.__pwn=3>{{constructor.constructor('window.__pwn=4')()}}", "what": "\"'><script>window.__pwn=5</script>\u202e\u0000 " + big,
        "when": 1793238420, "evidence": ev}]}
    t0 = time.time()
    pg.evaluate("""(s)=>{const j=JSON.parse(s); return GTB.addReport('evil.json', j)}""", json.dumps(rep))
    proto = '{"kind":"signals","generatedAt":1,"signals":[],"__proto__":{"polluted":1,"isAdmin":true},"constructor":{"prototype":{"polluted2":1}},"nested":{"__proto__":{"polluted3":1}}}'
    pg.evaluate("(s)=>GTB.addReport('proto.json', JSON.parse(s))", proto)
    # evidence links come from market data (everything.js signals); poison one signal's evidence list in-page
    tid = pg.evaluate("(ev)=>{const x=GTB_EV.EV_SIGS[0]; if(!x) return null; x.s.evidence=ev; x.s.title='<svg onload=window.__pwn=2><img src=x onerror=window.__pwn=3>'+x.s.title; return GTB.targets().find(t=>t.sig===x.s).id}", ev)
    res("poisoned evidence attached to a real target", bool(tid), tid)
    pg.evaluate("id=>GTB.scan(id,true)", tid); pg.evaluate("GTB.finish()"); pg.wait_for_timeout(300)
    pg.evaluate("(()=>{const b=document.querySelector('#dtabs [data-tab=\"2\"]'); b&&b.click()})()"); pg.wait_for_timeout(400)
    links = pg.evaluate("[...document.querySelectorAll('a')].filter(a=>/EV-/.test(a.textContent)).map(a=>a.textContent+'|'+a.getAttribute('href'))")
    inert = pg.evaluate("[...document.querySelectorAll('.nolink')].filter(a=>/EV-/.test(a.textContent)).length")
    res("only the https evidence is a link; 10 malicious URLs render as inert text", links == ["EV-OK|" + GOOD[0]] and inert == 10, (links, inert))
    for s in pg.query_selector_all(".nolink"):
        try: s.click(timeout=500)
        except Exception: pass
    pg.wait_for_timeout(300)
    res("clicking malicious evidence executes nothing, no navigation", not pg.evaluate("window.__pwn") and pg.url.startswith(U), pg.evaluate("window.__pwn"))
    res("HTML/SVG/event/template payloads inert (no injected svg/img/script in panel)", pg.evaluate("!window.__pwn && !document.querySelector('#panel svg[onload], img[onerror], #panel script, #drawer svg[onload]')"))
    res("1MB string handled without hang", time.time() - t0 < 15, round(time.time() - t0, 2))
    res("prototype pollution: no global prototype mutated", pg.evaluate("({}).polluted===undefined && ({}).isAdmin===undefined && ({}).polluted2===undefined && ({}).polluted3===undefined && Object.prototype.polluted===undefined"))
    res("sanitizer unchanged after pollution attempt", pg.evaluate("GTB_safeExternalUrl('javascript:1')===null && GTB_safeExternalUrl('https://a.example/')==='https://a.example/'"))
    # poisoned universe sourceUrl
    pg.evaluate("GTB.go('universe')"); pg.wait_for_timeout(300)
    first = pg.evaluate("(()=>{const b=document.querySelector('[data-uni]'); b&&b.click(); return !!b})()"); pg.wait_for_timeout(300)
    det = pg.evaluate("(()=>{const d=document.getElementById('uniDetail'); if(!d) return null; return {a:[...d.querySelectorAll('a')].map(a=>a.getAttribute('href')), inert:d.querySelectorAll('.nolink').length}})()")
    # find the tampered class (first in data, not necessarily first tile): open each until inert link found
    if det and not det["inert"]:
        for i in range(60):
            pg.evaluate(f"(()=>{{const b=document.querySelectorAll('[data-uni]')[{i}]; b&&b.click()}})()"); pg.wait_for_timeout(60)
            det = pg.evaluate("(()=>{const d=document.getElementById('uniDetail'); if(!d) return null; return {a:[...d.querySelectorAll('a')].map(a=>a.getAttribute('href')), inert:d.querySelectorAll('.nolink').length}})()")
            if det and det["inert"]: break
    res("poisoned universe sourceUrl renders as inert text; other source links stay https", bool(det) and det["inert"] == 1 and all((h or "").startswith("https://") for h in det["a"]), det)
    pg.evaluate("document.querySelector('#uniDetail .nolink') && document.querySelector('#uniDetail .nolink').click()"); pg.wait_for_timeout(200)
    res("clicking poisoned universe source executes nothing", not pg.evaluate("window.__pwn"))
    # 10-view navigation
    views = ["home", "signals", "anomalies", "universe", "board", "threats", "shill", "copy", "replay", "market"]
    for v in views: pg.evaluate("v=>GTB.go(v)", v); pg.wait_for_timeout(150)
    res("10-view navigation without page errors", not errs, errs[:3])
    # JSON import through the real file picker
    fd, fp = tempfile.mkstemp(suffix=".json"); os.write(fd, json.dumps(rep).replace("sec1", "sec2").encode()); os.close(fd)
    pg.set_input_files("#pick", fp); pg.wait_for_timeout(600)
    res("file-picker import of hostile JSON: no execution", not pg.evaluate("window.__pwn"))
    res("CSP enforced: zero violations, zero off-origin requests, no dialogs", not pg.evaluate("window.__csp||[]") and not off and not any(e.startswith("DIALOG") for e in errs), (pg.evaluate("window.__csp||[]"), off[:3]))
    # foreign origin: fetch/POST/PUT/frame against the launcher
    ev2 = b.new_page(); ev2.set_content("<p>attacker</p>")
    r2 = ev2.evaluate("""async (u)=>{const out={}; for (const m of ['GET','POST','PUT']) { try { const r=await fetch(u+'index.html',{method:m, body: m==='GET'?undefined:'x'}); out[m]='readable:'+r.status } catch(e) { out[m]='blocked' } } return out}""", U)
    res("foreign origin cannot read (no CORS) and POST/PUT are not accepted", all(v == "blocked" for v in r2.values()), r2)
    ev2.set_content(f"<iframe id=f src='{U}'></iframe>"); ev2.wait_for_timeout(1500)
    fr = ev2.evaluate("(()=>{try{return document.getElementById('f').contentWindow.document.body.innerHTML.length}catch(e){return 'cross-origin'}})()")
    framed = [f.url for f in ev2.frames if f.url.startswith(ORIGIN) and f.evaluate("!!document.querySelector('#root')") ] if True else []
    res("launcher refuses to be framed (X-Frame-Options DENY + frame-ancestors 'none')", not framed, framed)
    b.close()
proc.send_signal(2); code = proc.wait(5)
res("launcher exits 0 on Ctrl+C after browser session", code == 0, code)
print(f"\nui_security: {sum(R)}/{len(R)} passed (Chromium emulation, CSP enforced)")
sys.exit(0 if all(R) else 1)
