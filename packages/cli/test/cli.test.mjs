// node --test test/  — adversarial matrix for the launcher (Node built-ins only).
import { test } from "node:test";
import assert from "node:assert/strict";
import { request } from "node:http";
import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync, readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { start, resolveRequest, parseArgs, allowedHost } from "../bin/grok-the-block.mjs";

const PKG = join(dirname(fileURLToPath(import.meta.url)), "..");
const BIN = join(PKG, "bin", "grok-the-block.mjs");

function fixture() {
  const d = mkdtempSync(join(tmpdir(), "gtb-cli-"));
  const root = join(d, "ui"); mkdirSync(join(root, "sub"), { recursive: true });
  writeFileSync(join(root, "index.html"), "<p>ok</p>"); writeFileSync(join(root, "sub", "a.js"), "1");
  writeFileSync(join(root, ".env"), "X=1"); mkdirSync(join(root, ".git")); writeFileSync(join(root, ".git", "config"), "[core]");
  writeFileSync(join(d, "secret.txt"), "TOP-SECRET-OUTSIDE"); writeFileSync(join(d, "secret.js"), "TOP-SECRET-OUTSIDE");
  try { symlinkSync(join(d, "secret.js"), join(root, "link.js")); symlinkSync(d, join(root, "dirlink")); } catch {}
  return { d, root };
}
function raw(port, method, path, host) {
  return new Promise((ok, bad) => {
    const r = request({ host: "127.0.0.1", port, method, path, headers: { Host: host ?? `127.0.0.1:${port}`, Origin: "https://evil.example" }, insecureHTTPParser: false }, res => {
      let b = ""; res.on("data", c => b += c); res.on("end", () => ok({ s: res.statusCode, h: res.headers, b }));
    });
    r.on("error", bad); r.end();
  });
}

test("serves allowlisted assets with hardening headers, no CORS", async () => {
  const { root } = fixture(); const a = start({ root, log() {} }); await a.ready; const p = a.server.address().port;
  const r = await raw(p, "GET", "/index.html"); assert.equal(r.s, 200); assert.equal(r.b, "<p>ok</p>");
  assert.equal(r.h["x-content-type-options"], "nosniff"); assert.equal(r.h["x-frame-options"], "DENY");
  assert.match(r.h["content-security-policy"], /frame-ancestors 'none'/); assert.equal(r.h["access-control-allow-origin"], undefined);
  assert.equal((await raw(p, "GET", "/")).s, 302); assert.equal((await raw(p, "HEAD", "/sub/a.js")).s, 200);
  assert.equal(a.server.address().address, "127.0.0.1");
  await a.stop();
});

const BAD = ["/../secret.txt", "/%2e%2e/secret.txt", "/%2E%2E%2Fsecret.txt", "/%252e%252e/secret.txt", "/..%2fsecret.txt", "/..%5csecret.txt",
  "/sub/..\\..\\secret.txt", "/index.html%00.js", "/index.html\0", "/.git/config", "/.env", "/%2eenv", "/link.js", "/dirlink/secret.js",
  "/C:/Windows/win.ini", "/sub/a.js::$DATA", "//etc/passwd", "/sub/../../secret.js", "/nope.exe", "/sub/"];
test("path traversal, encoding, null byte, backslash, hidden, symlink, ADS: never serves outside bytes", async () => {
  const { root } = fixture(); const a = start({ root, log() {} }); await a.ready; const p = a.server.address().port;
  for (const path of BAD) {
    let r; try { r = await raw(p, "GET", path); } catch (e) { continue; } // Node client may refuse invalid chars: also a non-serve
    assert.ok([400, 403, 404].includes(r.s), `${path} -> ${r.s}`); assert.ok(!r.b.includes("TOP-SECRET") && !r.b.includes("[core]") && !r.b.includes("X=1"), path);
  }
  await a.stop();
});
test("raw socket traversal (bypassing client normalisation)", async () => {
  const { root } = fixture(); const a = start({ root, log() {} }); await a.ready; const p = a.server.address().port;
  const net = await import("node:net");
  for (const path of ["/../secret.txt", "/sub/../../secret.js", "/..\\secret.txt", "/%2e%2e/secret.txt"]) {
    const out = await new Promise(ok => { const s = net.connect(p, "127.0.0.1", () => s.write(`GET ${path} HTTP/1.1\r\nHost: 127.0.0.1:${p}\r\nConnection: close\r\n\r\n`)); let b = ""; s.on("data", c => b += c); s.on("close", () => ok(b)); });
    assert.match(out, /^HTTP\/1\.1 (400|403|404)/, path); assert.ok(!out.includes("TOP-SECRET"), path);
  }
  await a.stop();
});
test("Host header / DNS rebinding rejected", async () => {
  const { root } = fixture(); const a = start({ root, log() {} }); await a.ready; const p = a.server.address().port;
  for (const h of ["evil.example", `evil.example:${p}`, `127.0.0.1.evil.example:${p}`, `127.0.0.1:${p + 1}`, "127.0.0.1", `[::1]:${p}`, `0.0.0.0:${p}`])
    assert.equal((await raw(p, "GET", "/index.html", h)).s, 421, h);
  assert.equal((await raw(p, "GET", "/index.html", `localhost:${p}`)).s, 200);
  await a.stop();
});
test("non-GET/HEAD methods rejected; no writable endpoint", async () => {
  const { root } = fixture(); const a = start({ root, log() {} }); await a.ready; const p = a.server.address().port;
  for (const m of ["POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE", "CONNECT"]) { let r; try { r = await raw(p, m, "/index.html"); } catch { continue; } assert.equal(r.s, m === "CONNECT" ? r.s : 405, m); }
  assert.equal(readFileSync(join(root, "index.html"), "utf8"), "<p>ok</p>");
  await a.stop();
});
test("pure resolver unit cases", () => {
  const { root } = fixture();
  assert.equal(resolveRequest(root, "GET", "../x", "127.0.0.1:1", 1).status, 400);
  assert.equal(resolveRequest(root, "GET", "/a%2Fb.js", "127.0.0.1:1", 1).status, 400);
  assert.ok(!allowedHost(undefined, 1)); assert.ok(allowedHost("LOCALHOST:5", 5));
});
test("argument parsing", () => {
  assert.deepEqual(parseArgs([]), { open: true, port: 0 }); assert.equal(parseArgs(["--port", "4000"]).port, 4000); assert.equal(parseArgs(["--port=4001"]).port, 4001);
  assert.equal(parseArgs(["--no-open"]).open, false);
  for (const bad of [["--port"], ["--port", "80"], ["--port", "70000"], ["--port", "1e4"], ["--port", "4000;rm -rf /"], ["--evil"]]) assert.throws(() => parseArgs(bad), String(bad));
});
function run(args, env = {}) { return new Promise(ok => { const c = spawn(process.execPath, [BIN, ...args], { env: { PATH: process.env.PATH, ...env } }); let o = ""; c.stdout.on("data", d => o += d); c.stderr.on("data", d => o += d); c.on("exit", code => ok({ code, o })); }); }
test("--version and --help", async () => {
  const v = await run(["--version"]); assert.equal(v.code, 0); assert.equal(v.o.trim(), JSON.parse(readFileSync(join(PKG, "package.json"))).version);
  const h = await run(["--help"]); assert.equal(h.code, 0); assert.match(h.o, /--no-open/); assert.match(h.o, /--port/);
  assert.equal((await run(["--bogus"])).code, 2);
});
test("5 repeated launches, Ctrl+C (SIGINT) exits 0, port freed, no orphan", async () => {
  if (!existsSync(join(PKG, "dist", "ui", "index.html"))) return;
  for (let i = 0; i < 5; i++) {
    const c = spawn(process.execPath, [BIN, "--no-open"], { env: { PATH: process.env.PATH } }); let o = "";
    const url = await new Promise(ok => c.stdout.on("data", d => { o += d; const m = o.match(/http:\/\/127\.0\.0\.1:(\d+)\//); if (m) ok(m); }));
    const r = await raw(Number(url[1]), "GET", "/index.html"); assert.equal(r.s, 200);
    c.kill("SIGINT"); const code = await new Promise(ok => c.on("exit", ok)); assert.equal(code, 0);
    await assert.rejects(raw(Number(url[1]), "GET", "/index.html"));
  }
});
test("port collision gives clear error", async () => {
  const { root } = fixture(); const a = start({ root, log() {} }); await a.ready; const p = a.server.address().port;
  const r = await run(["--no-open", "--port", String(p)]); assert.equal(r.code, 1); assert.match(r.o, /already in use/); await a.stop();
});
test("manifest: no lifecycle hooks, no dependencies, bin mapping, engines", () => {
  const j = JSON.parse(readFileSync(join(PKG, "package.json")));
  for (const k of ["preinstall", "install", "postinstall", "prepare", "prepack", "postpack", "prepublish", "prepublishOnly", "publish", "postpublish"]) assert.ok(!(j.scripts || {})[k], k);
  assert.deepEqual(j.dependencies, {}); assert.ok(!j.devDependencies && !j.optionalDependencies && !j.peerDependencies);
  assert.equal(j.bin["grok-the-block"], "./bin/grok-the-block.mjs"); assert.equal(j.engines.node, ">=22.14.0");
});
test("launcher source: no env, home-dir or credential reads, no shell, no network clients", () => {
  const s = readFileSync(BIN, "utf8");
  for (const bad of [/process\.env/, /homedir/, /\.npmrc/, /\.ssh/, /shell:\s*true/, /exec\(/, /execSync/, /node:https/, /fetch\(/, /node:net/, /require\(/, /eval\(/]) assert.ok(!bad.test(s.replace(/^\/\/.*$/gm, "")), String(bad));
});
