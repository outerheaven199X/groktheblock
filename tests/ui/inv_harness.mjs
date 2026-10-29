// Test harness for tests/ui/ui_investigate.py: the real launcher start() serving ui/ with a LOCAL MOCK xAI endpoint
// (never the real API), a temporary state directory and an optional fake key. Prints one JSON line with the ports.
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { start } from "../../packages/cli/bin/grok-the-block.mjs";
import { startMockXai } from "../../packages/cli/test/mock-xai.mjs";
const R = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const m = startMockXai(); const mp = await m.ready;
const env = { GTB_XAI_BASE_URL: `http://127.0.0.1:${mp}/v1` };
if (arg("--key", "1") === "1") env.XAI_API_KEY = arg("--fake-key", "xai-TESTONLY-fake-key-0123456789abcdef");
const logs = [];
const app = start({ root: join(R, "ui"), port: +arg("--port", "0"), open: false, log: (s) => { logs.push(String(s)); process.stderr.write(String(s) + "\n"); }, env, stateDir: arg("--state", null) });
await app.ready;
console.log(JSON.stringify({ port: app.server.address().port, mock: mp, pid: process.pid }));
const bye = () => app.stop().then(() => m.stop()).then(() => process.exit(0)); process.on("SIGTERM", bye); process.on("SIGINT", bye);
