"""Hostile-input and localhost-surface checks against the PACKAGED npx server (the unpacked npm tarball), not the dev server.
Chromium EMULATION (Playwright, channel=chrome, SwiftShader), CSP ENFORCED (no bypass_csp). Run the server first (any user):
    node <unpacked>/package/bin/grok-the-block.mjs --no-open --port 18765
then:  python3 tests/ui/ui_security_pkg.py --url http://127.0.0.1:18765/ [--pid PID] [--root <unpacked>/package/dist/ui]
Covers: safeExternalUrl matrix incl. control characters; every built-in report kind re-imported through the real file picker
with attribute-breaking, SVG, mXSS, template-injection, iframe/base/meta/form/style payloads in every display string and
javascript:/data:/vbscript:/control-char URLs in every URL field; every target, detail tab and view rendered; nested JSON
(5000 deep), oversized fields (6 MB), 5000-signal report, malformed encodings (invalid UTF-8, UTF-16 BOM, NUL bytes, truncated,
binary) and copy-network/board/replay graph labels; Card Explorer text fallback with poisoned data; raw-socket traversal,
encoded traversal, double encoding, NUL, backslash, hidden files, absolute-form targets, symlink escape (if --root given and
the symlinks exist), methods, Host/DNS-rebinding; loopback-only binding; zero off-origin requests; no outbound sockets
from the server process during the session (if --pid given and `sudo -n ss` works)."""
import json, os, re, socket, subprocess, sys, tempfile, threading, time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
A = sys.argv[1:]
def arg(k, d=None): return A[A.index(k) + 1] if k in A else d
U = arg("--url", "http://127.0.0.1:18765/"); PID = arg("--pid"); ROOT = arg("--root")
O = urlparse(U); ORIGIN = f"{O.scheme}://{O.netloc}"; HOST, PORT = O.hostname, O.port
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
R = []
def res(n, ok, d=""): print("PASS" if ok else "FAIL", n, "-", str(d)[:400]); R.append(bool(ok))

# ---------------- outbound-socket monitor on the server process ----------------
OUT, STOP = [], threading.Event()
def mon():
    while not STOP.is_set():
        try:
            t = subprocess.run(["sudo", "-n", "ss", "-tunap"], capture_output=True, text=True, timeout=5).stdout
            for l in t.splitlines():
                if f"pid={PID}," in l:
                    f = l.split()
                    peer = f[5] if len(f) > 5 else ""
                    if f[1] not in ("LISTEN", "UNCONN") and not peer.startswith(("127.0.0.1:", "[::ffff:127.0.0.1]:")):
                        OUT.append(l)
        except Exception as e:  # noqa: BLE001
            OUT.append("monitor error " + repr(e)); return
        time.sleep(0.2)
MON = None
if PID:
    MON = threading.Thread(target=mon, daemon=True); MON.start()

# ---------------- raw HTTP ----------------
def raw(req, timeout=5):
    s = socket.create_connection((HOST, PORT), timeout=timeout); s.sendall(req.encode("latin-1") if isinstance(req, str) else req)
    buf = b""
    try:
        while True:
            c = s.recv(65536)
            if not c: break
            buf += c
    except socket.timeout:
        pass
    s.close(); return buf
def get(path, method="GET", host=None):
    b = raw(f"{method} {path} HTTP/1.1\r\nHost: {O.netloc if host is None else host}\r\nConnection: close\r\n\r\n")
    m = re.match(rb"HTTP/1\.1 (\d{3})", b); return (int(m.group(1)) if m else None), b

SECRETS = [b"root:x:0:0", b"BEGIN OPENSSH", b"BEGIN RSA", b"_authToken", b"\"name\": \"grok-the-block\"", b"import { createServer }", b"[core]", b"HELIUS"]
TRAV = ["/../../../../etc/passwd", "/..%2f..%2f..%2fetc%2fpasswd", "/%2e%2e/%2e%2e/%2e%2e/etc/passwd", "/%252e%252e/%252e%252e/etc/passwd", "/..\\..\\etc\\passwd",
        "/%5c..%5c..%5cetc%5cpasswd", "/index.html%00.js", "/index.html\x00", "/data/../../package.json", "/../package.json", "/../bin/grok-the-block.mjs", "/bin/grok-the-block.mjs",
        "/package.json", "/.git/config", "/.env", "/.npmrc", "/data/.env", "/%2e%65nv", "/./index.html", "//etc/passwd", "/C:/Windows/win.ini", "/index.html::$DATA", "/con.html",
        "/%c0%ae%c0%ae/%c0%ae%c0%ae/etc/passwd", "/..%c0%af..%c0%afetc/passwd", "/" + "a/" * 600 + "x.js", "/leak.txt", "/rootdir/etc/passwd", "/licenses/../../package.json"]
bad = []
for t in TRAV:
    try:
        st, body = get(t)
    except Exception as e:  # noqa: BLE001
        st, body = "conn-error:" + repr(e)[:40], b""
    if st == 200 or any(x in body for x in SECRETS):
        bad.append((t[:60], st))
res(f"raw socket: {len(TRAV)} traversal/encoded/NUL/backslash/hidden/ADS/symlink targets never return outside bytes", not bad, bad)
st, body = get("/index.html"); hdr = body.split(b"\r\n\r\n")[0].decode("latin-1").lower()
res("index.html served with nosniff, DENY framing, no-referrer, CORP same-origin, no Access-Control-Allow-Origin", st == 200 and "x-content-type-options: nosniff" in hdr and "x-frame-options: deny" in hdr and "referrer-policy: no-referrer" in hdr and "cross-origin-resource-policy: same-origin" in hdr and "access-control-allow-origin" not in hdr, hdr[:300])
meth = {m: get("/index.html", m)[0] for m in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE", "CONNECT", "PROPFIND")}
res("only GET/HEAD: POST/PUT/DELETE/PATCH/OPTIONS/TRACE/PROPFIND get 405; CONNECT gets the connection closed (no tunnel)", all(v in (400, 405) for k, v in meth.items() if k != "CONNECT") and meth["CONNECT"] in (None, 400, 405), meth)
hosts = {h: get("/index.html", host=h)[0] for h in ("evil.example", f"evil.example:{PORT}", f"127.0.0.1.evil.example:{PORT}", f"localhost.:{PORT}", "", f"[::1]:{PORT}")}
res("Host header / DNS rebinding rejected (only 127.0.0.1:port and localhost:port)", all(v in (400, 421) for v in hosts.values()), hosts)
absf = raw(f"GET http://evil.example/index.html HTTP/1.1\r\nHost: {O.netloc}\r\nConnection: close\r\n\r\n")
res("absolute-form request target rejected", not absf.startswith(b"HTTP/1.1 200"), absf[:40])
big = raw(f"GET /{'A' * 5000}.js HTTP/1.1\r\nHost: {O.netloc}\r\nConnection: close\r\n\r\n")
res("oversized request target rejected", not big.startswith(b"HTTP/1.1 200"), big[:40])
if ROOT:
    links = [p for p in ("leak.txt", "rootdir") if os.path.islink(os.path.join(ROOT, p)) or subprocess.run(["sudo", "-n", "test", "-L", os.path.join(ROOT, p)]).returncode == 0]
    res("symlink escape fixtures present in the unpacked package and refused (403/404)", len(links) == 2 and get("/leak.txt")[0] in (403, 404) and get("/rootdir/etc/passwd")[0] in (403, 404), links)
# binding
lst = subprocess.run(["ss", "-ltn"], capture_output=True, text=True).stdout
mine = [l.split()[3] for l in lst.splitlines()[1:] if l.split()[3].endswith(f":{PORT}")]
res("listening socket is loopback only (127.0.0.1), never 0.0.0.0/:: or a public interface", mine and all(a.startswith("127.0.0.1:") for a in mine), mine)
ext = [ip for ip in subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout.split() if not ip.startswith("127.")]
reach = []
for ip in ext:
    try:
        s = socket.create_connection((ip, PORT), timeout=2); s.close(); reach.append(ip)
    except OSError:
        pass
res("server not reachable on this machine's non-loopback addresses", not reach, {"tried": ext, "reachable": reach})

PAY = ['"><img src=x onerror="window.__pwn=\'attr\'">', "' autofocus onfocus='window.__pwn=\"sq\"' x='", '<svg onload="window.__pwn=\'svg\'"><script>window.__pwn="svgs"</script></svg>',
       '<math><mtext><table><mglyph><style><img src=x onerror="window.__pwn=\'mxss\'">', '${window.__pwn="tpl"}', '{{constructor.constructor("window.__pwn=\'ng\'")()}}',
       '<template><img src=x onerror="window.__pwn=\'tmpl\'"></template>', '</title></style></textarea><script>window.__pwn="close"</script>',
       '<iframe srcdoc="<script>parent.__pwn=\'ifr\'</script>"></iframe>', '<a href="javascript:window.__pwn=\'a\'">x</a>', '<img src="https://evil.example/px.gif">',
       '<link rel=stylesheet href="https://evil.example/x.css">', '<style>@import "https://evil.example/i.css";body{background:url(https://evil.example/b.png)}</style>',
       '\u202e\u0000\u0007\ud800 lone-surrogate', '<base href="https://evil.example/">', '<meta http-equiv="refresh" content="0;url=https://evil.example/">',
       '<form action="https://evil.example/"><button>x</button></form>', '<object data="https://evil.example/o"></object><embed src="https://evil.example/e">']
BADURL = ["javascript:window.__pwn='u1'", "JaVaScRiPt:window.__pwn='u2'", " javascript:window.__pwn='u3'", "java\u0000script:window.__pwn='u4'", "\u0001javascript:window.__pwn='u5'",
          "javascript\t:window.__pwn='u6'", "&#x6A;avascript:window.__pwn='u7'", "%6Aavascript:window.__pwn='u8'", "data:text/html,<script>parent.__pwn='u9'</script>",
          "data:image/svg+xml,<svg onload=parent.__pwn='u10'>", "vbscript:msgbox(1)", "VBScript:msgbox(1)", "https://ok.example/\u0000x", "https://ok.example/\nx", "https://ok.example/\u202ex",
          "https://evil.example\\@good.example", "blob:https://x.example/y", "file:///etc/passwd", "ftp://x.example/", "http://evil.example/", "//evil.example/x", "https:evil", "https://u:p@evil.example/", None, 7, {"x": 1}]
GOOD = ["https://www.ecb.europa.eu/stats/", "HTTPS://fred.stlouisfed.org/series/DCOILWTICO"]
CHECK = """() => { const on = [...document.querySelectorAll('*')].filter(e => [...e.attributes].some(a => /^on/i.test(a.name))).map(e => e.tagName);
  const sel = 'iframe,object,embed,math,template,base,form,link[href*="evil"],meta[http-equiv=refresh],img[src*="evil"],img[src="x"],svg[onload],#panel script,#drawer script,#res script';
  const hrefs = [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')).filter(h => !/^(https:\\/\\/|#)/i.test(h) && !/^[\\w./-]+$/.test(h));
  return { pwn: window.__pwn || null, on: on.slice(0, 5), inj: [...document.querySelectorAll(sel)].map(e => e.tagName).slice(0, 5), hrefs: hrefs.slice(0, 5), csp: (window.__csp || []).slice(0, 5) }; }"""
def clean(c): return not c["pwn"] and not c["on"] and not c["inj"] and not c["hrefs"] and not c["csp"]

tmp = tempfile.mkdtemp(prefix="gtb-hostile-")
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=GL)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}); pg = ctx.new_page(); errs, off, dialogs, flashes = [], [], [], []
    pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
    pg.on("request", lambda r: (not r.url.startswith((ORIGIN, "data:", "blob:"))) and off.append(r.url))
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    pg.on("popup", lambda pp: dialogs.append("POPUP " + pp.url))
    pg.add_init_script("document.addEventListener('securitypolicyviolation', e => (window.__csp = window.__csp || []).push(e.violatedDirective + ' ' + e.blockedURI))")
    pg.goto(U); pg.wait_for_function("window.GTB&&GTB.ready", timeout=30000); pg.wait_for_timeout(500)
    res("packaged server: page boots under its CSP meta (hashed import map, no unsafe-inline scripts, connect-src 'none')", pg.evaluate("(()=>{const c=document.querySelector('meta[http-equiv=Content-Security-Policy]').content;return /script-src 'self' 'sha256-/.test(c)&&!/script-src[^;]*unsafe-inline/.test(c)&&/connect-src 'none'/.test(c)})()"))
    base = pg.evaluate(CHECK); res("baseline page has no inline handlers / injected elements", clean(base), base)
    bu = pg.evaluate("a=>a.map(v=>GTB_safeExternalUrl(v))", BADURL); gu = pg.evaluate("a=>a.map(v=>GTB_safeExternalUrl(v))", GOOD)
    res(f"safeExternalUrl: all {len(BADURL)} hostile URLs (control chars, encoded, mixed case, data:, vbscript:, credentials, non-https) rejected", all(x is None for x in bu), [(str(a)[:30], x) for a, x in zip(BADURL, bu) if x])
    res("safeExternalUrl: https accepted and normalised", gu == ["https://www.ecb.europa.eu/stats/", "https://fred.stlouisfed.org/series/DCOILWTICO"], gu)
    # -------- every built-in report kind, mutated, imported through the real file picker --------
    muts = pg.evaluate("""([P, Ub]) => { let n = 0; const UK = /^(url|sourceurl|href|link|uri|evidenceurl|source_url|permalink)$/i;
      const SKIP = new Set(["kind","type","severity","state","basis","outcome","status","tool","granularity","module","source","assessment","role","grade","side","mode","category","universe","access"]);
      const mut = (o) => Array.isArray(o) ? o.map(mut) : (o && typeof o === "object") ? Object.fromEntries(Object.entries(o).map(([k, v]) => [k, typeof v === "string" ? (UK.test(k) ? Ub[n++ % Ub.length] : SKIP.has(k) ? v : v + P[n++ % P.length]) : mut(v)])) : o;
      return GTB.REPORTS.map(r => ({ name: "evil-" + r.name, k: r.k, j: mut(JSON.parse(JSON.stringify(r.j))) })); }""", [PAY, [u for u in BADURL if isinstance(u, str)]])
    files = []
    for m in muts:
        fp = os.path.join(tmp, m["name"]); open(fp, "w", encoding="utf-8", errors="surrogatepass").write(json.dumps(m["j"])); files.append(fp)
    pg.on("console", lambda msg: None)
    before = set(pg.evaluate("GTB.targets().map(t=>t.id)"))
    pg.set_input_files("#pick", files); pg.wait_for_timeout(1500)
    got = pg.evaluate("GTB.REPORTS.filter(r=>r.name.startsWith('evil-')).map(r=>r.k)")
    res(f"all {len(muts)} mutated reports ({len(set(m['k'] for m in muts))} kinds) imported via the file picker", len(got) == len(muts), (len(got), sorted(set(got))))
    c = pg.evaluate(CHECK); res("after import: nothing executed or injected", clean(c), c)
    new = [t for t in pg.evaluate("GTB.targets().map(t=>t.id)") if t not in before]
    res("hostile token/wallet/replay reports became scan targets (signals/board/shill/threats/watch/prov render as views below)", len(new) == 5, new)
    # cached market data is not importable, but poison every market signal in place too (simulates a tampered data file)
    pg.evaluate("""([P, Ub]) => { let n = 0; const SK = new Set(["key","source","type","severity","basis","category","asset"]);
      (GTB_EV.EV_SIGS || []).forEach(({ s }) => { for (const k of Object.keys(s)) if (typeof s[k] === "string" && !SK.has(k)) s[k] += P[n++ % P.length];
        s.evidence = [{ label: "EV-bad" + P[n % P.length], url: Ub[n++ % Ub.length] }, { label: "EV-ok", url: "https://www.ecb.europa.eu/stats/" }];
        s.limits = (s.limits || []).concat([P[n++ % P.length]]); }); }""", [PAY, [u for u in BADURL if isinstance(u, str)]])
    tids = pg.evaluate("GTB.targets().map(t=>t.id)")
    worst, n = None, 0
    for tid in tids:
        pg.evaluate("id=>{GTB.scan(id,true);GTB.finish()}", tid); pg.wait_for_timeout(60)
        for tab in (0, 1, 2):
            pg.evaluate("t=>{const b=document.querySelector('#dtabs [data-tab=\"'+t+'\"]'); b&&b.click()}", tab); pg.wait_for_timeout(40)
            c = pg.evaluate(CHECK); n += 1
            if not clean(c): worst = (tid[:50], tab, c); break
        for s in pg.query_selector_all(".nolink")[:20]:
            try: s.click(timeout=300)
            except Exception: pass
    res(f"{len(tids)} targets (5 hostile reports + every poisoned market signal) x 3 detail tabs ({n} renders): no execution, no inline handlers, no injected elements, no unsafe hrefs, no CSP violations", len(tids) >= 70 and worst is None, worst or len(tids))
    views = ["signals", "anomalies", "universe", "board", "threats", "shill", "copy", "replay", "prov", "tcg", "home"]
    vbad = []
    for v in views:
        pg.evaluate("v=>GTB.go(v)", v); pg.wait_for_timeout(150)
        for sel in ("[data-srep^='evil-']", "[data-af]"):
            for el in pg.query_selector_all(sel)[:8]:
                try: el.click(timeout=300); pg.wait_for_timeout(60)
                except Exception: pass
        if pg.query_selector("#copyPick"):
            for o in pg.evaluate("[...document.querySelectorAll('#copyPick option')].map(o=>o.value).filter(v=>v.startsWith('evil-'))"):
                pg.select_option("#copyPick", o); pg.wait_for_timeout(100)
        for el in pg.query_selector_all("[data-uni], [data-bw], .tile .tmain")[:6]:
            try: el.click(timeout=300); pg.wait_for_timeout(60)
            except Exception: pass
        c = pg.evaluate(CHECK)
        if not clean(c): vbad.append((v, c))
    res(f"{len(views)} views incl. copy-network/board/replay graph labels with hostile reports selected: clean", not vbad, vbad[:2])
    # -------- nested JSON, oversized fields, many rows, malformed encodings --------
    deep = '{"kind":"signals","generatedAt":1,"signals":[{"key":"deep1","source":"equities","type":"X","severity":"LOW","title":"deep","when":1,"evidence":[],"metrics":' + '{"a":' * 3000 + '1' + '}' * 3000 + '}],"deep":' + '[' * 5000 + ']' * 5000 + '}'
    huge = json.dumps({"kind": "signals", "generatedAt": 1, "signals": [{"key": "huge1", "source": "equities", "type": "X", "severity": "HIGH", "title": PAY[0] * 2000, "what": "W" * (6 << 20), "when": 1, "evidence": [{"label": "L" * 100000, "url": "javascript:window.__pwn='huge'"}]}]})
    many = json.dumps({"kind": "signals", "generatedAt": 1, "signals": [{"key": f"m{i}", "source": "equities", "type": "X", "severity": "LOW", "title": PAY[i % len(PAY)], "when": i, "evidence": [{"label": "e", "url": BADURL[i % 10]}]} for i in range(5000)]})
    enc = {"bad-utf8.json": b'{"kind":"signals","generatedAt":1,"signals":[{"key":"u1","source":"equities","type":"X","severity":"LOW","title":"bad \xff\xfe\xc3\x28 \xed\xa0\x80 \xc0\xaf <img src=x onerror=window.__pwn=8>","when":1,"evidence":[]}]}',
           "utf16-bom.json": '\ufeff{"kind":"signals","generatedAt":1,"signals":[]}'.encode("utf-16-le"), "nul.json": b'{"kind":"signals",\x00"generatedAt":1}',
           "truncated.json": b'{"kind":"signals","generatedAt":1,"signals":[{"key":"t', "empty.json": b"", "binary.json": bytes(range(256)) * 64,
           "proto.json": b'{"kind":"signals","generatedAt":1,"signals":[],"__proto__":{"polluted":1},"constructor":{"prototype":{"polluted2":1}}}'}
    for nm, data in [("deep.json", deep.encode()), ("huge.json", huge.encode()), ("many.json", many.encode())] + list(enc.items()):
        open(os.path.join(tmp, nm), "wb").write(data)
    t0 = time.time(); pg.set_input_files("#pick", [os.path.join(tmp, x) for x in ("deep.json", "huge.json", "many.json")]); pg.wait_for_timeout(2500)
    pg.evaluate("GTB.go('signals')"); pg.wait_for_timeout(600)
    for el in pg.query_selector_all("[data-srep='huge.json'],[data-srep='many.json'],[data-srep='deep.json']"):
        try: el.click(timeout=2000); pg.wait_for_timeout(800)
        except Exception: pass
    pg.evaluate("GTB.go('anomalies')"); pg.wait_for_timeout(1500)
    dt = time.time() - t0; c = pg.evaluate(CHECK)
    res("nested JSON (3000-deep metrics, 5000-deep array), 6 MB field, 100 KB label, 5000-signal report: imported and rendered, clean, < 60 s", clean(c) and dt < 60 and pg.evaluate("!!document.body"), (round(dt, 1), c))
    pg.set_input_files("#pick", [os.path.join(tmp, x) for x in enc]); pg.wait_for_timeout(1500)
    c = pg.evaluate(CHECK)
    res("malformed encodings (invalid UTF-8, UTF-16 BOM, NUL, truncated, empty, binary) + __proto__ keys: no execution, no prototype pollution, page alive", clean(c) and pg.evaluate("({}).polluted===undefined&&({}).polluted2===undefined&&Object.prototype.polluted===undefined&&GTB_safeExternalUrl('javascript:1')===null"), c)
    # -------- Card Explorer text fallback with poisoned data (fresh npm install has no artwork) --------
    pg.evaluate("GTB.go('tcg')"); pg.wait_for_timeout(400)
    un = pg.evaluate("({n:document.querySelectorAll('.tcard').length, img:document.querySelectorAll('.tgrid img').length, t:(document.querySelector('.tgrid .tph')||{}).textContent||''})")
    res("Card Explorer in the package: text-card fallback, no artwork shipped, hint names the GitHub repo", un["n"] >= 20 and un["img"] == 0 and "Text card" in un["t"], un)
    pg.evaluate("""(P)=>{const T=window.GTB_EVERYTHING&&GTB_EVERYTHING.live; (T.assets||[]).filter(a=>a.universe==='mtg').slice(0,3).forEach((a,i)=>{a.name=a.name; a.url=['javascript:window.__pwn=\\'tcg\\'','data:text/html,x','vbscript:x'][i];})}""", PAY)
    pg.evaluate("GTB.go('home')"); pg.evaluate("GTB.go('tcg')"); pg.wait_for_timeout(300)
    for i in range(3):
        try: pg.locator(".tcard").nth(i).click(timeout=1000); pg.wait_for_timeout(200)
        except Exception: pass
        for s in pg.query_selector_all("#tcgDet .nolink"):
            try: s.click(timeout=300)
            except Exception: pass
    c = pg.evaluate(CHECK)
    res("Card Explorer with javascript:/data:/vbscript: source URLs: links inert, nothing executes", clean(c) and pg.evaluate("[...document.querySelectorAll('#panel a[href]')].every(a=>a.href.startsWith('https:'))"), c)
    # -------- malformed URL fragments (a crafted link to the local app) --------
    hb = []
    for h in ("#%E0%A4%A", "#token/%ZZ%ZZ", "#f/%ED%A0%80", "#" + "%" * 300, "#asset/<img src=x onerror=window.__pwn=1>"):
        q = ctx.new_page(); qe = []; q.on("pageerror", lambda e: qe.append(str(e)[:120]))
        q.goto(U + h); ok = True
        try: q.wait_for_function("window.GTB&&GTB.ready", timeout=15000)
        except Exception: ok = False
        if not ok or qe or q.evaluate("window.__pwn||null"): hb.append((h[:30], ok, qe[:1]))
        q.close()
    res("malformed / hostile URL fragments: app still boots, no page error, nothing executes", not hb, hb)
    # -------- foreign origin --------
    ev2 = ctx.new_page(); ev2.set_content("<p>attacker</p>")
    r2 = ev2.evaluate("""async (u)=>{const out={}; for (const m of ['GET','POST','PUT']) { try { const r=await fetch(u+'index.html',{method:m, body: m==='GET'?undefined:'x'}); out[m]='readable:'+r.status } catch(e) { out[m]='blocked' } } return out}""", U)
    res("foreign origin cannot read the app (no CORS) and cannot POST/PUT", all(v == "blocked" for v in r2.values()), r2)
    ev2.set_content(f"<iframe id=f src='{U}'></iframe>"); ev2.wait_for_timeout(1500)
    framed = [f.url for f in ev2.frames if f.url.startswith(ORIGIN) and f.evaluate("!!document.querySelector('#root')")]
    res("app refuses to be framed", not framed, framed)
    res("whole session: zero off-origin requests, zero dialogs/popups, zero CSP violations", not off and not dialogs and not pg.evaluate("window.__csp||[]"), (off[:3], dialogs[:3], pg.evaluate("window.__csp||[]")[:3]))
    res("whole session: no uncaught page errors", not errs, errs[:3])
    b.close()
STOP.set()
if MON:
    MON.join(2)
    res("server process opened no outbound (non-loopback) sockets during startup, browsing and the hostile session", not OUT, OUT[:3])
print(f"\nui_security_pkg: {sum(R)}/{len(R)} passed (packaged server, Chromium emulation, CSP enforced)")
sys.exit(0 if all(R) else 1)
