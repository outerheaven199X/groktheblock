"""Investigations UI suite: real launcher (start()) + LOCAL MOCK xAI via tests/ui/inv_harness.mjs; static-preview checks via
a plain static URL. Never calls the real xAI API.
usage: ui_investigate.py STATIC_URL [--shots DIR]     e.g. http://127.0.0.1:8833/ui/
"""
import json, os, re, subprocess, sys, tempfile, time, html as H
from pathlib import Path
from urllib.request import Request, urlopen
from playwright.sync_api import sync_playwright

R = Path(__file__).resolve().parents[2]
STATIC = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "http://127.0.0.1:8833/ui/"
SHOTS = Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
FAKE = "xai-TESTONLY-fake-key-0123456789abcdef"
SESSION_KEY = "xaiTESTONLYsessionKey0123456789abcdefXYZ"
FX, MTG = "fx:EUR/AUD:CHECKS", "mtg:Time Walk:CROSS_VENUE_SPREAD"
ok = fails = 0
def res(name, cond, info=""):
    global ok, fails
    if cond: ok += 1
    else: fails += 1
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else " - " + str(info)[:400]), flush=True)
def shot(pg, name, full=False):
    if SHOTS: SHOTS.mkdir(parents=True, exist_ok=True); pg.screenshot(path=str(SHOTS / name), full_page=full)

class Harness:
    def __init__(self, state, key=True):
        self.p = subprocess.Popen(["node", str(R / "tests/ui/inv_harness.mjs"), "--state", state, "--key", "1" if key else "0", "--fake-key", FAKE], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(R))
        j = json.loads(self.p.stdout.readline()); self.port, self.mock = j["port"], j["mock"]; self.url = f"http://127.0.0.1:{self.port}/"
    def scenario(self, s): urlopen(Request(f"http://127.0.0.1:{self.mock}/__scenario", data=json.dumps({"scenario": s}).encode(), method="POST")).read()
    def stop(self):
        self.p.terminate()
        try: out, err = self.p.communicate(timeout=5)
        except Exception: self.p.kill(); out, err = self.p.communicate()
        return err

def watch(pg, origin):
    st = {"errs": [], "off": [], "api": [], "req": []}
    pg.on("pageerror", lambda e: st["errs"].append(str(e)[:200]))
    pg.on("console", lambda m: m.type == "error" and st["errs"].append(m.text[:200]))
    def rq(r):
        st["req"].append(r.url)
        if not r.url.startswith((origin, "data:", "blob:")): st["off"].append(r.url)
        if "/api/" in r.url: st["api"].append(r.url)
    pg.on("request", rq)
    return st
def boot(pg, url):
    pg.goto(url); pg.wait_for_function("window.GTB&&GTB.ready&&GTB.inv", timeout=30000); pg.wait_for_timeout(400)
def gstate(pg): return pg.evaluate("(()=>{const e=[...document.querySelectorAll('#invAns [data-grok-state]')].pop();return e?e.dataset.grokState:null})()")
def T(pg, sel): return pg.evaluate("(s)=>{const e=document.querySelector(s);return e?e.textContent:''}", sel)
def wait_state(pg, want, t=15000):
    try: pg.wait_for_function("(w)=>{const e=[...document.querySelectorAll('#invAns [data-grok-state]')].pop();return e&&w.includes(e.dataset.grokState)}", arg=want, timeout=t)
    except Exception: pass
    return gstate(pg)
def download(pg, sel):
    with pg.expect_download() as d: pg.click(sel)
    dl = d.value; p = dl.path(); return dl.suggested_filename, Path(p).read_text()
def connected(pg):
    pg.click('[data-invmode="connected"]'); pg.wait_for_timeout(300); return wait_state(pg, ["connected", "not-connected", "no-launcher"])
def ask(pg, scenario=None, H=None, timeout_s=None):
    if scenario and H: H.scenario(scenario)
    if timeout_s: pg.fill("#invTimeout", str(timeout_s)); pg.dispatch_event("#invTimeout", "change"); pg.wait_for_timeout(100)
    if pg.locator("details.send:not([open]) > summary").count(): pg.click("details.send:not([open]) > summary")
    pg.check("#invConsent"); pg.wait_for_timeout(100); pg.click("#invSend")
    return wait_state(pg, ["answered", "auth", "rate", "timeout", "interrupted", "malformed", "upstream", "budget", "cancelled", "network", "rejected", "error"], 20000)

tmp = Path(tempfile.mkdtemp(prefix="gtb-uiinv-")); STATE = str(tmp / "state")
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=GL)
    # ---------------- 1. static preview: offline paths work, no /api request is ever made ----------------
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True); pg = ctx.new_page()
    origin = re.match(r"https?://[^/]+", STATIC).group(0); st = watch(pg, origin); boot(pg, STATIC)
    res("static: home shows 'What's weird right now?' with cached real rows only", pg.evaluate("(()=>{const h=document.getElementById('hpulse');return /what's weird right now/i.test(h.textContent)&&h.querySelectorAll('[data-inv]').length>0&&[...h.querySelectorAll('[data-inv]')].every(b=>!/syn|SYN/.test(b.dataset.inv))})()"))
    shot(pg, "01-home-pulse-desktop.png")
    pg.evaluate(f"GTB.scan('asset:{FX}')"); pg.wait_for_timeout(1500)
    res("static: FX quiet instrument result has an Investigate action", pg.locator(f'[data-inv="{FX}"]').count() > 0)
    pg.click(f'[data-inv="{FX}"] >> nth=0'); pg.wait_for_timeout(500)
    res("static: investigation opens with the exact stable id and evidence id", pg.evaluate("[document.querySelector('[data-stable-id]').dataset.stableId,document.querySelector('.rail [data-evidence-id]').dataset.evidenceId]") == ["fx:EUR/AUD", FX])
    res("static: quiet instrument says nothing past threshold (not an all-clear)", "not an all-clear" in T(pg, "#panel"))
    res("static: Local-only answer is evidence-only and says Grok not connected", gstate(pg) == "not-connected" and "Grok not connected" in T(pg, "#invAns"))
    res("static: answer has the five sections", pg.evaluate("[...document.querySelectorAll('#invAns [data-sec]')].map(e=>e.dataset.sec).join()") == "observed,context,interpretation,disprove,limits")
    shot(pg, "02-investigate-fx-local-desktop.png")
    fn, js = download(pg, "#invJson"); d = json.loads(js)
    fh, ht = download(pg, "#invHtml")
    res("dossier: file names carry the case id", fn == "gtb-" + d["caseId"] + ".json" and fh == "gtb-" + d["caseId"] + ".html", (fn, fh))
    res("dossier JSON: schema, instrument, evidence, provenance, analysis none, limitations, disclosure", d["schemaVersion"] == "gtb-investigation/v1" and d["instrument"]["stableId"] == "fx:EUR/AUD" and d["observations"][0]["id"] == FX and d["analysis"]["provider"] == "none" and d["limitations"] and "Not financial advice" in d["disclosure"] and d["provenance"]["coverage"])
    rehash = pg.evaluate("(j)=>{const c={...j};delete c.exportSha256;return GTB.inv.sha256(GTB.inv.canon(c))}", d)
    res("dossier JSON: exportSha256 verifies over the canonical JSON", rehash == d["exportSha256"], (rehash, d["exportSha256"]))
    m = re.search(r'<pre id="gtb-case-json">(.*?)</pre>', ht, re.S)
    res("dossier HTML: embeds the same case as the JSON export", m and json.loads(H.unescape(m.group(1))) == d)
    res("dossier HTML: standalone, CSP script-src 'none', no scripts/fonts/images/remote assets", "script-src 'none'" in ht and not re.search(r"<script|<img|<link|@font-face|<iframe", ht, re.I) and not re.search(r'(src|href)="(?!https://)', ht))
    res("dossier HTML: evidence ids and checksum are attributes", f'data-evidence-id="{H.escape(FX)}"' in ht and f'data-export-sha256="{d["exportSha256"]}"' in ht)
    res("dossier: no local paths, emails or keys", not re.search(r"/(home|Users|tmp)/|[A-Za-z]:\\\\Users|@[a-z0-9-]+\.[a-z]{2,}|xai-", js + ht, re.I))
    # determinism: same evidence + same time -> same case id and checksum
    same = pg.evaluate("Promise.all([GTB.inv.dossier(null,{now:'2026-10-29T00:00:00Z'}),GTB.inv.dossier(null,{now:'2026-10-29T00:00:00Z'})]).then(([a,b])=>[a.json.caseId===b.json.caseId,a.json.exportSha256===b.json.exportSha256,a.html===b.html])")
    res("dossier: deterministic for the same evidence and time", same == [True, True, True], same)
    (tmp / "sample-dossier.json").write_text(js); (tmp / "sample-dossier.html").write_text(ht)
    pg.click('[data-invmode="copy"]'); pg.wait_for_timeout(200)
    pt = pg.input_value("#invPrompt")
    res("Copy to Grok: bounded prompt contains the packet and the rules, nothing sent", "gtb-evidence/v1" in pt and "not arbitrage" in pt and len(pt) < 40000 and not st["api"])
    res("static: Connected Grok explains the launcher is needed (no /api call)", connected(pg) == "no-launcher" and not st["api"], st["api"])
    pg.click('[data-invmode="local"]'); pg.wait_for_timeout(100)
    # Pulse: real vs Demo separation
    pg.evaluate("GTB.go('pulse')"); pg.wait_for_timeout(400)
    real = pg.evaluate("[...document.querySelectorAll('#pulseReal [data-pkey]')].map(e=>e.dataset.mode)")
    res("Pulse: cached real list has only cached observations; Demo hidden by default", real and set(real) == {"cached"} and pg.locator("#pulseDemo").count() == 0, real)
    res("Pulse: unknown sources listed as 'not quiet'", "Unknown, not quiet" in T(pg, "#pulseUnknown"))
    shot(pg, "03-pulse-desktop.png")
    pg.click("#pDemo"); pg.wait_for_timeout(300)
    demo = pg.evaluate("[...document.querySelectorAll('#pulseDemo [data-pkey]')].map(e=>e.dataset.mode)")
    res("Pulse Demo: synthetic rows only inside the hatched Demo box", demo and set(demo) == {"examples"} and pg.evaluate("document.getElementById('pulseDemo').classList.contains('synbox')") and set(pg.evaluate("[...document.querySelectorAll('#pulseReal [data-pkey]')].map(e=>e.dataset.mode)")) == {"cached"}, demo)
    shot(pg, "04-pulse-demo-desktop.png")
    pg.click("#pulseDemo [data-inv] >> nth=0"); pg.wait_for_timeout(400)
    res("Demo investigation: labelled synthetic, not watchable", "Demo: synthetic example" in T(pg, "#panel") and pg.locator("#invWatch").count() == 0 and pg.evaluate("document.getElementById('invKind').dataset.kind") == "synthetic-demo")
    pg.click("#pDemo") if pg.locator("#pDemo").count() else None
    pg.evaluate("GTB.inv.IV.demo=false; GTB.go('pulse')"); pg.wait_for_timeout(200)
    k = pg.evaluate("[...GTB.inv.index().keys()].find(k=>k.endsWith(':syn'))"); pg.evaluate(f"GTB.inv.open({json.dumps(k)})"); pg.wait_for_timeout(300)
    res("Demo off: synthetic deep link refuses to open", "need the Demo switch" in T(pg, "#panel"))
    pg.evaluate("GTB.go('watch')"); pg.wait_for_timeout(300)
    res("static: watchlist explains it needs the launcher; refresh is snapshot-only with the manual command", "Watchlist unavailable" in T(pg, "#panel") and "build_everything.py --fetch" in T(pg, "#watchRefresh"))
    # MTG printing identity
    pg.evaluate("GTB.goFeat('tcg.explorer')"); pg.wait_for_timeout(800)
    tk = pg.evaluate("(()=>{for(const g of (window.GTB_TCG_CACHE||{groups:[]}).groups)for(const p of g.printings)if(p.name==='Time Walk'&&p.tracked)return p.key;return null})()")
    other = pg.evaluate("(()=>{for(const g of (window.GTB_TCG_CACHE||{groups:[]}).groups)for(const p of g.printings)if(p.name==='Time Walk'&&!p.tracked)return p.key;return null})()")
    if tk:
        pg.evaluate(f"document.querySelector('.tcard[data-tkey=\"{tk}\"]').click()"); pg.wait_for_timeout(500)
        res("Card Explorer: tracked printing has Investigate bound to its observation", pg.locator(f'#tcgDet [data-inv="{MTG}"]').count() == 1)
        shot(pg, "05-tcg-detail-investigate-desktop.png")
        if other:
            pg.evaluate(f"document.querySelector('.tpb[data-tkey=\"{other}\"]')&&document.querySelector('.tpb[data-tkey=\"{other}\"]').click()"); pg.wait_for_timeout(400)
            res("Card Explorer: other same-name printing cannot investigate the tracked printing's data", pg.locator("#tcgDet [data-inv]").count() == 0)
            pg.evaluate(f"document.querySelector('.tpb[data-tkey=\"{tk}\"]')&&document.querySelector('.tpb[data-tkey=\"{tk}\"]').click()"); pg.wait_for_timeout(400)
        pg.click(f'#tcgDet [data-inv="{MTG}"]'); pg.wait_for_timeout(500)
    else:
        pg.evaluate(f"GTB.inv.open({json.dumps(MTG)})"); pg.wait_for_timeout(400)
    pr = pg.evaluate("(()=>{const e=document.querySelector('[data-printing]');return e?e.dataset.printing:null})()")
    res("MTG investigation keeps provider id + set + collector number + language + finish", pg.evaluate("document.querySelector('[data-stable-id]').dataset.stableId") == "mtg:scryfall:ade7d00d-4e7b-46e9-ace1-63f628a589fc:2ed:84:en:nonfoil" and pr == "2ed|84|en|nonfoil", pr)
    mj = pg.evaluate("GTB.inv.dossier().then(x=>x.json)")
    res("MTG dossier: printing identity, spread wording (no arbitrage), no raw price table", mj["instrument"]["printing"]["cn"] == "84" and not re.search(r"(?<!executable )arbitrage", json.dumps(mj["analysis"]), re.I) and "artwork" in mj["disclosure"])
    shot(pg, "06-investigate-mtg-desktop.png")
    res("static: zero off-origin requests, zero /api requests, no page errors", not st["off"] and not st["api"] and not st["errs"], (st["off"][:3], st["api"][:3], st["errs"][:3]))
    ctx.close()

    # ---------------- 2. launcher + mock xAI (env key) ----------------
    Hn = Harness(STATE, key=True)
    try:
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True); pg = ctx.new_page(); st = watch(pg, Hn.url.rstrip("/")); boot(pg, Hn.url)
        pg.evaluate(f"GTB.inv.open({json.dumps(FX)})"); pg.wait_for_timeout(500)
        res("launcher: Connected Grok shows the env key state and 'live API path unverified'", connected(pg) == "connected" and "live API path unverified" in T(pg, "#invAns"))
        res("launcher: 'What will be sent to Grok?' shows the exact packet; web/X off by default; Send disabled until consent",
            "gtb-evidence/v1" in T(pg, "#invPacket") and not pg.is_checked("#invWeb") and not pg.is_checked("#invX") and pg.is_disabled("#invSend"))
        res("launcher: billing note names tokens and search calls", "bills tokens plus each web or X search call" in T(pg, "#invAns"))
        shot(pg, "07-connected-consent-desktop.png")
        pkt = json.loads(T(pg, "#invPacket"))
        s0 = ask(pg, "success", Hn)
        res("mock success: answered, labelled mock, cited context link, usage as reported", s0 == "answered" and "mock xAI endpoint" in T(pg, "#invAns") and pg.locator('#invAns [data-sec="context"] a[href^="https://"]').count() >= 1 and "input / " in T(pg, "#invUsage"), s0)
        res("mock success: observed claim points at the packet's evidence id", pg.locator(f'#invAns [data-sec="observed"] [data-evidence-id="{FX}"]').count() >= 1)
        shot(pg, "08-connected-answer-mock-desktop.png")
        fn, js = download(pg, "#invJson"); dj = json.loads(js); fh, ht = download(pg, "#invHtml")
        res("dossier after Grok: analysis provider xai, model, mock flag, liveVerified false, sources", dj["analysis"]["provider"] == "xai" and dj["analysis"]["mock"] is True and dj["analysis"]["liveVerified"] is False and dj["analysis"]["sources"], dj["analysis"].get("model"))
        (tmp / "sample-dossier-grok-mock.json").write_text(js); (tmp / "sample-dossier-grok-mock.html").write_text(ht)
        pg.fill("#invFu", "What would disprove this?"); pg.click("#invFuGo"); s1 = wait_state(pg, ["answered", "upstream", "network"])
        res("follow-up: answered and counted (3 max)", s1 == "answered" and "2 left" in T(pg, "#panel"), s1)
        for sc, want, txt in [("auth401", "auth", "401"), ("rate429", "rate", "429"), ("interrupted", "interrupted", "interrupted"), ("malformed", "malformed", "malformed"), ("budget", "budget", "Budget")]:
            s = ask(pg, sc, Hn)
            res(f"mock {sc}: clear '{want}' state, falls back to the evidence-only summary", s == want and txt in T(pg, "#invAns") and "evidence-only summary" in T(pg, "#invAns"), (s, T(pg, "#invAns")[:200]))
        shot(pg, "09-connected-error-429-desktop.png") if False else None
        s = ask(pg, "injection", Hn)
        res("mock prompt injection: unsafe claims listed as rejected, not shown as answer text", s == "answered" and pg.locator('[data-sec="rejected"]').count() == 1 and not re.search(r"strong buy|XAI_API_KEY|curl evil", pg.evaluate("[...document.querySelectorAll('#invAns .ait')].map(e=>e.textContent).join(' ')"), re.I))
        shot(pg, "09-connected-injection-rejected-desktop.png")
        s = ask(pg, "badcitation", Hn)
        res("mock malformed citation: dropped; uncited claim labelled", s == "answered" and "uncited" in T(pg, "#invAns") and "dropped" in T(pg, "#invAns") and pg.locator('#invAns a[href^="javascript"], #invAns a[href^="http:"]').count() == 0)
        s = ask(pg, "timeout", Hn, timeout_s=5)
        res("mock timeout: request cancelled at the user's time limit", s == "timeout", s)
        Hn.scenario("timeout"); pg.fill("#invTimeout", "60"); pg.dispatch_event("#invTimeout", "change"); pg.wait_for_timeout(100)
        if pg.locator("details.send:not([open]) > summary").count(): pg.click("details.send:not([open]) > summary")
        pg.check("#invConsent"); pg.click("#invSend"); wait_state(pg, ["running"], 5000); shot(pg, "10-connected-running-cancel-desktop.png"); pg.click("#invCancel")
        res("cancel: user cancel stops the request", wait_state(pg, ["cancelled"], 8000) == "cancelled")
        Hn.scenario("toolerror"); s = ask(pg)
        res("mock tool error: unknown id/function handled, still a bounded answer", s == "answered")
        # watchlist
        pg.click("#invWatch"); pg.wait_for_timeout(400)
        pg.evaluate("GTB.go('watch')"); pg.wait_for_timeout(500)
        res("watchlist: saved item listed with stable id and 'unchanged' comparison", pg.locator('[data-wid="fx:EUR/AUD"] .wst[data-state="unchanged"]').count() == 1, T(pg, "#panel")[:300])
        pg.check("#wNotify"); pg.wait_for_timeout(400)
        shot(pg, "11-watchlist-desktop.png")
        f = Path(STATE) / "watchlist.json"
        res("watchlist file: 0600 in a 0700 state dir, holds no key or packet", f.exists() and (f.stat().st_mode & 0o777) == 0o600 and (Path(STATE).stat().st_mode & 0o777) == 0o700 and FAKE not in f.read_text() and "gtb-evidence" not in f.read_text())
        dom = pg.content() + json.dumps(pg.evaluate("({ls:{...localStorage},ss:{...sessionStorage},iv:JSON.stringify(GTB.inv.IV.api)})"))
        res("key never reaches the page, storage or downloads", FAKE not in dom and FAKE not in js and FAKE not in ht)
        res("launcher: browser requests are same-origin only (xAI is called by the launcher, not the page)", not st["off"] and not any(str(Hn.mock) in u for u in st["req"]), st["off"][:3])
        res("launcher: no page errors", not [e for e in st["errs"] if "status of 4" not in e and "status of 5" not in e], st["errs"][:4])
        ctx.close()
        # cross-origin page cannot use the API
        ctx = b.new_context(); pg = ctx.new_page(); pg.goto(STATIC)
        x = pg.evaluate("(u)=>fetch(u+'api/session',{method:'POST',headers:{'Content-Type':'application/json','X-GTB-Request':'1'},body:'{}'}).then(r=>'status '+r.status).catch(e=>'blocked')", Hn.url)
        y = pg.evaluate("(u)=>fetch(u+'api/watchlist',{method:'POST',mode:'no-cors',headers:{'Content-Type':'text/plain'},body:JSON.stringify({op:'clear'})}).then(()=>'sent').catch(()=>'blocked')", Hn.url)
        res("cross-origin page: API request blocked (no CORS, Origin check) and a no-cors 'clear' changes nothing", x == "blocked" and f.exists(), (x, y))
        ctx.close()
    finally:
        err = Hn.stop()
    res("launcher log: key and prompts never logged", FAKE not in err and "What would disprove" not in err)
    # ---------------- 3. restart: watchlist persists, no false notification; session-key flow ----------------
    Hn = Harness(STATE, key=False)
    try:
        ctx = b.new_context(viewport={"width": 1440, "height": 900}); pg = ctx.new_page(); st = watch(pg, Hn.url.rstrip("/")); flashes = []
        pg.expose_function("__flash", lambda t: flashes.append(t))
        pg.add_init_script("new MutationObserver(()=>{const f=document.getElementById('toast');if(f&&f.textContent)window.__flash&&window.__flash(f.textContent)}).observe(document,{subtree:true,childList:true,characterData:true})")
        boot(pg, Hn.url); pg.wait_for_timeout(800)
        pg.evaluate("GTB.go('watch')"); pg.wait_for_timeout(600)
        res("restart: watchlist item and notify setting persisted", pg.locator('[data-wid="fx:EUR/AUD"]').count() == 1 and pg.is_checked("#wNotify"))
        n = pg.evaluate("GTB.inv.checkNotify().then(x=>x.length)")
        res("restart: no false notification for an unchanged snapshot", n == 0 and not any("Watchlist:" in t for t in flashes), (n, flashes))
        pg.evaluate(f"GTB.inv.open({json.dumps(FX)})"); pg.wait_for_timeout(300)
        res("no env key: Connected shows 'Grok not connected' + session key field", connected(pg) == "not-connected" and pg.locator("#invKey").count() == 1)
        shot(pg, "12-connected-no-key-desktop.png")
        pg.fill("#invKey", SESSION_KEY); pg.click("#invKeyGo"); pg.wait_for_timeout(500)
        res("session key: connected, field cleared, key absent from the DOM", gstate(pg) == "connected" and SESSION_KEY not in pg.content() and "session key" in T(pg, "#invAns"))
        pg.click("#invForget"); pg.wait_for_timeout(400)
        res("forget key: back to not connected", gstate(pg) == "not-connected")
        pg.evaluate("GTB.go('watch')"); pg.wait_for_timeout(400); pg.click("#wClear"); pg.wait_for_timeout(200)
        res("clear watchlist: needs a second click", "Confirm" in T(pg, "#wClear") and (Path(STATE) / "watchlist.json").exists())
        pg.click("#wClear"); pg.wait_for_timeout(500)
        res("clear watchlist: local data removed", not (Path(STATE) / "watchlist.json").exists() and "Nothing saved yet" in T(pg, "#panel"))
        ctx.close()
        # ---------------- 4. viewports, reduced motion, no WebGL ----------------
        for w, h in [(1440, 900), (1920, 1080), (768, 1024), (390, 844), (375, 812), (320, 568)]:
            ctx = b.new_context(viewport={"width": w, "height": h}); pg = ctx.new_page(); st = watch(pg, Hn.url.rstrip("/")); boot(pg, Hn.url)
            pg.evaluate(f"GTB.inv.open({json.dumps(FX)})"); pg.wait_for_timeout(400)
            ov1 = pg.evaluate("document.documentElement.scrollWidth-innerWidth")
            if w in (390, 320): shot(pg, f"13-investigate-{w}.png")
            pg.evaluate("GTB.go('pulse')"); pg.wait_for_timeout(300); ov2 = pg.evaluate("document.documentElement.scrollWidth-innerWidth")
            if w in (390, 320): shot(pg, f"14-pulse-{w}.png")
            pg.evaluate("GTB.go('home')"); pg.wait_for_timeout(400); ov3 = pg.evaluate("document.documentElement.scrollWidth-innerWidth")
            if w in (390, 320): shot(pg, f"15-home-pulse-{w}.png")
            res(f"{w}x{h}: investigate, Pulse and home have no horizontal overflow; no page errors", max(ov1, ov2, ov3) <= 1 and not st["errs"], (ov1, ov2, ov3, st["errs"][:2]))
            ctx.close()
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce"); pg = ctx.new_page(); st = watch(pg, Hn.url.rstrip("/")); boot(pg, Hn.url + "?nowebgl")
        pg.evaluate(f"GTB.scan('asset:{FX}')"); pg.wait_for_timeout(800); pg.click(f'[data-inv="{FX}"] >> nth=0'); pg.wait_for_timeout(400)
        res("reduced motion + no WebGL: investigate opens and works", pg.locator(".rail").count() == 1 and gstate(pg) == "not-connected" and not st["errs"], st["errs"][:2])
        ctx.close()
    finally:
        Hn.stop()
    b.close()
print(f"ui_investigate: {ok}/{ok + fails} passed"); print("artifacts:", tmp)
sys.exit(1 if fails else 0)
