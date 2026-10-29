#!/usr/bin/env node
// Grok The Block launcher. Node built-ins only. Serves dist/ui read-only on 127.0.0.1.
// Static files: GET/HEAD only. The only other surface is the small /api/ in ../lib/investigate.mjs (same-origin, token-gated).
// Reads exactly one secret, XAI_API_KEY, and only if it was set in the launch environment; never reads ~/.npmrc, ~/.ssh or
// credential files. No network calls unless the user approves a Connected Grok request in the UI. No daemon.
// Writes only the opt-in watchlist file in its own local state directory, and only after the user saves something.
import { createServer } from "node:http";
import { readFileSync, realpathSync, statSync, createReadStream } from "node:fs";
import { join, sep, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { createApi, defaultStateDir } from "../lib/investigate.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const PKG = JSON.parse(readFileSync(join(HERE, "..", "package.json"), "utf8"));
const MIN = [22, 14, 0];
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".ico": "image/x-icon", ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf", ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8", ".glb": "model/gltf-binary", ".wasm": "application/wasm", ".sha256": "text/plain; charset=utf-8" };
const SEC = { "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Resource-Policy": "same-origin", "Cache-Control": "no-store", "Permissions-Policy": "camera=(), microphone=(), geolocation=(), usb=(), payment=()", "Content-Security-Policy": "frame-ancestors 'none'" };

const HELP = `grok-the-block ${PKG.version}
Local research preview of Grok The Block. Serves the bundled browser UI read-only on 127.0.0.1.

Usage: grok-the-block [--no-open] [--port N] [--version] [--help]
  --no-open   print the URL but do not open a browser
  --port N    listen on port N (1024-65535). Default: an OS-assigned free port
  --version   print the version and exit
  --help      show this help and exit

Optional: XAI_API_KEY in the environment (or a session-only key entered in the UI) enables Connected Grok. Nothing is
sent to xAI until you approve the evidence packet in the UI; xAI bills your account for those requests.
Watchlist state (opt-in): GTB_STATE_DIR, or the platform's local state directory.

Not financial advice. No wallet, sign-in, telemetry or background network calls. Ctrl+C to stop.`;

export function parseArgs(argv) {
  const o = { open: true, port: 0 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--help" || a === "-h") o.help = true;
    else if (a === "--version" || a === "-v") o.version = true;
    else if (a === "--no-open") o.open = false;
    else if (a === "--port" || a.startsWith("--port=")) {
      const v = a.includes("=") ? a.slice(7) : argv[++i];
      if (!/^\d{1,5}$/.test(v || "")) throw new Error("--port needs a number between 1024 and 65535");
      const n = Number(v); if (n < 1024 || n > 65535) throw new Error("--port needs a number between 1024 and 65535");
      o.port = n;
    } else throw new Error(`unknown option: ${a} (see --help)`);
  }
  return o;
}

// Returns {status} or {file}. Pure decision over the raw request target; no filesystem write paths exist.
export function resolveRequest(root, method, rawUrl, host, port) {
  if (method !== "GET" && method !== "HEAD") return { status: 405 };
  if (!allowedHost(host, port)) return { status: 421 };
  if (typeof rawUrl !== "string" || !rawUrl.startsWith("/") || rawUrl.length > 1024) return { status: 400 };
  let path = rawUrl.split("?")[0].split("#")[0];
  if (/\\|\0|%00|%2f|%5c|%25/i.test(path)) return { status: 400 };          // backslashes, null bytes, encoded slashes, double-encoding
  let dec; try { dec = decodeURIComponent(path); } catch { return { status: 400 }; }
  if (/[\\\0\x00-\x1f\x7f]/.test(dec)) return { status: 400 };
  const segs = dec.split("/").slice(1);
  if (segs.some(s => s === ".." || s === "." )) return { status: 400 };
  if (segs.some(s => s.startsWith(".") || s.includes(":"))) return { status: 404 }; // hidden files (.git, .env), drive/ADS syntax
  if (dec === "/" ) return { redirect: "/index.html" };
  if (dec.endsWith("/")) segs[segs.length - 1] = "index.html";
  const ext = extname(segs[segs.length - 1]).toLowerCase();
  if (!TYPES[ext]) return { status: 404 };
  const cand = join(root, ...segs);
  if (!cand.startsWith(root + sep)) return { status: 403 };
  let real; try { real = realpathSync(cand); } catch { return { status: 404 }; }
  if (!real.startsWith(root + sep)) return { status: 403 };                 // symlink escape
  let st; try { st = statSync(real); } catch { return { status: 404 }; }
  if (!st.isFile()) return { status: 404 };
  return { file: real, type: TYPES[ext], size: st.size };
}

export function allowedHost(host, port) {
  if (typeof host !== "string") return false;
  const h = host.toLowerCase();
  return h === `127.0.0.1:${port}` || h === `localhost:${port}`;
}

function openBrowser(url) {
  const [cmd, args] = process.platform === "win32" ? ["rundll32.exe", ["url.dll,FileProtocolHandler", url]]
    : process.platform === "darwin" ? ["open", [url]] : ["xdg-open", [url]];
  try {
    const c = spawn(cmd, args, { stdio: "ignore", shell: false, windowsHide: true });
    c.on("error", () => console.log("Could not open a browser. Open the URL above manually."));
    return c;
  } catch { return null; }
}

export function start({ root, port = 0, open = false, log = console.log, env = {}, stateDir = null, fetchImpl } = {}) {
  root = realpathSync(root);
  const sockets = new Set();
  const api = createApi({ env, stateDir, pkgRoot: join(HERE, ".."), log, fetchImpl });
  const srv = createServer((req, res) => {
    const addr = srv.address();
    if (typeof req.url === "string" && (req.url === "/api" || req.url.startsWith("/api/"))) {
      return void api.handle(req, res, addr.port).catch(() => { if (!res.headersSent) { res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" }); res.end("500"); } });
    }
    const r = resolveRequest(root, req.method, req.url, req.headers.host, addr.port);
    if (r.redirect) { res.writeHead(302, { ...clean(SEC), Location: r.redirect }); return res.end(); }
    if (r.status) {
      const h = { ...clean(SEC), "Content-Type": "text/plain; charset=utf-8" };
      if (r.status === 405) h.Allow = "GET, HEAD";
      res.writeHead(r.status, h); return res.end(req.method === "HEAD" ? undefined : String(r.status));
    }
    res.writeHead(200, { ...clean(SEC), "Content-Type": r.type, "Content-Length": r.size });
    if (req.method === "HEAD") return res.end();
    createReadStream(r.file).on("error", () => res.destroy()).pipe(res);
  });
  srv.on("connection", s => { sockets.add(s); s.on("close", () => sockets.delete(s)); });
  srv.requestTimeout = 30000; srv.headersTimeout = 10000;
  let child = null;
  const ready = new Promise((ok, bad) => {
    srv.once("error", bad);
    srv.listen({ host: "127.0.0.1", port, exclusive: true }, () => {
      const url = `http://127.0.0.1:${srv.address().port}/`;
      log(`Grok The Block ${PKG.version} running at ${url}`);
      log("Local research preview. Not financial advice. Press Ctrl+C to stop.");
      const g = api.status(); log(g.available ? "Grok: XAI_API_KEY found in the environment. Nothing is sent until you approve an evidence packet in the UI." : "Grok not connected (optional). Local-only mode.");
      if (open) child = openBrowser(url);
      ok(url);
    });
  });
  const stop = () => new Promise(done => {
    if (child && child.exitCode === null) { try { child.unref(); } catch {} }
    srv.close(() => done());
    for (const s of sockets) s.destroy();
  });
  return { server: srv, ready, stop, api };
}
function clean(o) { return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined)); }

function main() {
  const v = process.versions.node.split(".").map(Number);
  if (v[0] < MIN[0] || (v[0] === MIN[0] && (v[1] < MIN[1] || (v[1] === MIN[1] && v[2] < MIN[2])))) {
    console.error(`grok-the-block needs Node ${MIN.join(".")} or newer (found ${process.versions.node}).`); process.exit(1);
  }
  let o; try { o = parseArgs(process.argv.slice(2)); } catch (e) { console.error(e.message); process.exit(2); }
  if (o.help) { console.log(HELP); return; }
  if (o.version) { console.log(PKG.version); return; }
  const E = process.env, env = {};
  for (const k of ["XAI_API_KEY", "GTB_XAI_BASE_URL", "GTB_XAI_MODEL"]) if (typeof E[k] === "string" && E[k]) env[k] = E[k];
  const app = start({ root: join(HERE, "..", "dist", "ui"), port: o.port, open: o.open, env, stateDir: defaultStateDir(E) });
  app.ready.catch(e => { console.error(e.code === "EADDRINUSE" ? `Port ${o.port} is already in use. Try another --port or omit it.` : `Could not start: ${e.message}`); process.exit(1); });
  let stopping = false;
  const shut = () => { if (stopping) return; stopping = true; console.log("\nStopping Grok The Block."); app.stop().then(() => process.exit(0)); setTimeout(() => process.exit(0), 2000).unref(); };
  process.on("SIGINT", shut); process.on("SIGTERM", shut);
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) main();
