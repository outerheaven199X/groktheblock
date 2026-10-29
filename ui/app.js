/* Grok The Block v6 UI. Vanilla JS, no network: data comes from data/reports.js (window.GTB_REPORTS) or files the user opens. */
"use strict";
(() => {
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const RM = matchMedia("(prefers-reduced-motion: reduce)");
const reduced = () => RM.matches;
const C = { red: "#ff3d00", amber: "#faf905", green: "#6584f8", grey: "#6a6a72", ink: "#ffffff" };
const SEVC = { CRITICAL: "red", HIGH: "red", MEDIUM: "amber", LOW: "green" };
const pad = (n) => String(n).padStart(2, "0");
const utc = (d) => pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes());
const iso = (ts) => ts == null ? "unknown time" : new Date((typeof ts === "number" ? (ts < 1e12 ? ts * 1000 : ts) : Date.parse(ts))).toISOString().replace(".000Z", "Z").replace("T", " ");
const short = (a) => !a ? "—" : a.length > 12 ? a.slice(0, 4) + "…" + a.slice(-4) : a;
const num = (n, d = 0) => n == null || isNaN(n) ? "—" : Number(n).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
const usd = (n) => n == null ? "—" : n >= 1e6 ? "$" + (n / 1e6).toFixed(2) + "M" : n >= 1e3 ? "$" + (n / 1e3).toFixed(1) + "K" : "$" + num(n);
const easeO = (x) => 1 - Math.pow(1 - x, 3);
function countTo(str, p) { const m = String(str).match(/^([^0-9]*?)([-+−]?)([0-9][0-9,]*\.?[0-9]*)(.*)$/); if (!m) return str; const raw = m[3]; const n = parseFloat(raw.replace(/,/g, "")); const dec = (raw.split(".")[1] || "").length; let v = (n * p).toFixed(dec); if (raw.includes(",")) v = Number(v).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }); return m[1] + m[2] + v + m[4]; }

/* ---------------- verdict phrases (PRD-safe: no advice, no predictions, no accusations) ---------------- */
const HYPE = [["Spotless. For now.", "good"], ["Looks organic", "good"], ["Nothing flagged", "good"], ["Mixed signals", "caution"], ["Something smells off", "caution"], ["Sketchy patterns", "caution"], ["High risk", "bad"], ["Red flags stacking up", "bad"], ["Every alarm is on", "bad"]];
const TONE = { good: { bg: "#0b0b0d", color: "#6584f8", border: "#6584f8", jp: "" }, caution: { bg: "#0b0b0d", color: "#faf905", border: "#faf905", jp: "注意" }, bad: { bg: "#ff3d00", color: "#0b0b0d", border: "#ff3d00", jp: "危険" } };
/** Map a report's severity and 0-100 score to a phrase index. `scoreIsRisk` means higher = worse. */
function verdictIndex(severity, score, scoreIsRisk, flagged) {
  const s = String(severity || "").toUpperCase();
  if (s === "CRITICAL") return score != null && (scoreIsRisk ? score >= 90 : score <= 20) ? 8 : 7;
  if (s === "HIGH") return 6;
  if (s === "MEDIUM") return score != null && (scoreIsRisk ? score >= 60 : score < 60) ? 5 : 4;
  if (s === "LOW") { if (flagged === 0) return 0; return score != null && (scoreIsRisk ? score <= 20 : score >= 90) ? 1 : 2; }
  return 3; // unknown / unassessed: never reads as clean
}
window.GTB_verdictIndex = verdictIndex; window.GTB_HYPE = HYPE;

/* ---------------- reports ---------------- */
const REPORTS = [];
function kind(j) { if (!j || typeof j !== "object") return null; if (j.tool && j.result) return kind(j.result); if (Array.isArray(j)) return "threats"; if (j.kind === "signals") return "signals"; if (j.kind === "watch") return "watch"; if (j.organicScore != null) return "token"; if (j.coordinationIndex != null) return "shill"; if (j.wallet && j.tokens) return "wallet"; if (j.timeline) return "replay"; if (j.entries) return "board"; if (j.results) return "prov"; return null; }
function addReport(name, j) { if (j && j.tool && j.result) j = j.result; const k = kind(j); if (!k) return false; const i = REPORTS.findIndex(r => r.name === name); const r = { name, k, j }; if (i >= 0) REPORTS[i] = r; else REPORTS.push(r); return true; }
(window.GTB_REPORTS || []).forEach(r => addReport(r.name, r.json));
const of = (k) => REPORTS.filter(r => r.k === k);
const genAt = (r) => { const j = r.j; const g = j.generatedAt ?? j.checkedAt ?? (j.wallet && j.window && j.window.to) ?? (j.token && j.token.createdAt); return g == null ? "generated time not in report" : "generated " + iso(g); };
const repLabel = (r) => r.name + " // " + genAt(r);

/* ---------------- targets (stage views) ---------------- */
function tokenTarget(r) {
  const j = r.j, t = j.token || {}, a = j.assessment || {}, b = j.bundleSignal || {}, rc = (j.lpMonitor || {}).rugcheck || {};
  const sev = a.severity || (j.verdict || {}).severity; const c = j.counts || {};
  const flagged = (c.INSIDER || 0) + (c.SNIPER || 0) + (c.AGENT || 0) + (c.COPY || 0);
  const rep = of("replay").find(x => x.j.token && x.j.token.mint === t.mint);
  const wallets = (j.wallets || []).slice().sort((x, y) => (y.supplyPercent || 0) - (x.supplyPercent || 0));
  const events = rep ? replayEvents(rep.j) : wallets.slice().sort((x, y) => (x.entryBlock ?? 1e9) - (y.entryBlock ?? 1e9)).slice(0, 8).map((w, i, arr) => [Math.round(i / Math.max(1, arr.length - 1) * 90), SEVC[w.type === "INSIDER" ? "HIGH" : w.type === "SNIPER" ? "MEDIUM" : "LOW"] || "grey", "Block " + (w.entryBlock ?? "?") + " · " + short(w.address) + " entered (" + w.type + "-pattern)"]);
  return {
    id: "token:" + t.symbol, view: "token", r, kind: "Token scan", title: "$" + (t.symbol || "?"), evId: "scan:" + t.mint,
    chips: [num((j.scanWindow || {}).transactionsAnalyzed) + " txs from launch", (j.scanWindow || {}).dataSource || "source n/a", (t.age || "?") + " old"],
    sev, vi: verdictIndex(sev, j.organicScore, false, flagged), vc: SEVC[sev] || "grey",
    verdictNote: a.lead ? a.lead.text : (j.verdict || {}).summary || "",
    score: { label: "Organic score", value: String(j.organicScore ?? "—"), unit: "/ 100", note: "Counts wallets, not supply." + ((j.verdict || {}).originalSeverity ? " The unescalated verdict was " + j.verdict.originalSeverity + "." : "") },
    metrics: [["Bundle signal", b.valid ? num(b.block0SupplyBoughtPct, 1) + "%" : "n/a", SEVC[b.severity] === "red" ? "red" : null], ["Market cap", usd(t.mcap)], ["Liquidity", usd((j.lpMonitor || {}).totalLiquidityUsd)], ["Mint authority", rc.available ? (rc.mintAuthority ? "Enabled" : "Revoked") : "unknown", rc.mintAuthority ? "red" : "green"], ["Holders", num(t.totalHolders)]],
    rowsLabel: "Holders", rows: wallets.slice(0, 12).map(w => ({ a: short(w.address), full: w.address, cls: w.type, c: { INSIDER: "red", SNIPER: "amber", ORGANIC: "green" }[w.type] || "grey", share: num(w.supplyPercent, 1) + "%", note: (w.tag ? w.tag + " · " : "") + "entry block " + (w.entryBlock ?? "?") + " · " + num(w.txCount) + " txs" })),
    events, why: [a.lead && a.lead.text].concat((a.findings || []).filter(f => !a.lead || f.id !== a.lead.id).map(f => f.text)).filter(Boolean).slice(0, 4),
    whyId: a.lead ? a.lead.id : "verdict", limits: ((a.coverage || {}).limits || []).map(l => l.text || l).slice(0, 4).concat([j.disclaimer].filter(Boolean)),
  };
}
function replayEvents(j) {
  const tl = (j.timeline || []).filter(e => e.type !== "X_POST"); if (!tl.length) return [];
  const t0 = tl[0].timestamp, t1 = tl[tl.length - 1].timestamp || t0 + 1;
  const pick = tl.length > 14 ? tl.filter((e, i) => i % Math.ceil(tl.length / 14) === 0 || /SELL|LIQ|RUG/.test(e.type)) : tl;
  return pick.map(e => [Math.round(((e.timestamp - t0) / Math.max(1, t1 - t0)) * 95), /SELL|LIQ|RUG|INSIDER/.test(e.type) ? "red" : /SNIPER/.test(e.type) ? "amber" : "green", (e.relativeTime || "") + " · " + e.detail, e]);
}
function walletTarget(r) {
  const j = r.j, w = j.wallet, a = j.assessment || {}, sev = a.severity || (j.verdict || {}).severity, rep = w.reputation || {};
  const toks = j.tokens || [];
  return {
    id: "wallet:" + w.address, view: "wallet", r, kind: "Wallet scan", title: short(w.address), evId: "wallet:" + w.address,
    chips: [num((j.window || {}).transactionsAnalyzed) + " txs", ((j.window || {}).from || "").slice(0, 10) + " → " + ((j.window || {}).to || "").slice(5, 10), (w.walletAge || "?") + " old"],
    sev, vi: verdictIndex(sev, rep.score, true, toks.filter(t => t.classification !== "ORGANIC").length), vc: SEVC[sev] || "grey",
    verdictNote: a.lead ? a.lead.text : (j.verdict || {}).summary || "",
    score: { label: "Pattern score", value: String(rep.score ?? "—"), unit: "/ 100", note: "Higher means a more launch-slot-like trading history. A pattern score, not an identity." },
    metrics: [["Win rate", (w.winRate ?? "—") + "%"], ["Tokens touched", num(w.totalTokensTouched)], ["PnL in window", (w.totalPnlSol >= 0 ? "+" : "") + num(w.totalPnlSol, 2) + " SOL", w.totalPnlSol >= 0 ? "green" : "red"], ["Grade", rep.grade || "—", rep.grade === "EXTREME" ? "red" : null], ["Funded wallets", num(((j.associations || {}).fundedWallets || []).length)]],
    rowsLabel: "Tokens", rows: toks.slice(0, 14).map(t => ({ a: "$" + (t.symbol || "?"), full: t.mint, cls: t.classification, c: { INSIDER: "red", SNIPER: "amber", EARLY: "amber", ORGANIC: "green" }[t.classification] || "grey", share: (t.pnlSol >= 0 ? "+" : "") + num(t.pnlSol, 2), note: "entry block " + (t.entryBlock ?? "?") + (t.tag ? " · " + t.tag : "") })),
    events: toks.slice().sort((x, y) => (x.firstTx || 0) - (y.firstTx || 0)).slice(0, 10).map((t, i, arr) => [Math.round(i / Math.max(1, arr.length - 1) * 95), { INSIDER: "red", SNIPER: "amber" }[t.classification] || "green", iso(t.firstTx).slice(0, 16) + " · $" + t.symbol + " entered at block " + (t.entryBlock ?? "?") + " (" + t.classification + "-pattern)"]),
    why: [a.lead && a.lead.text].concat((a.findings || []).filter(f => !a.lead || f.id !== a.lead.id).map(f => f.text)).filter(Boolean).slice(0, 4), whyId: a.lead ? a.lead.id : "verdict",
    limits: ((a.coverage || {}).limits || []).map(l => l.text || l).slice(0, 3).concat(["A pattern score is not an identity or an accusation."]),
  };
}
function replayTarget(r) {
  const j = r.j, t = j.token || {}, s = j.summary || {}, a = j.assessment || {}, sev = a.severity, wb = j.walletBreakdown || {};
  const ev = replayEvents(j);
  return {
    id: "replay:" + t.symbol, view: "replay", r, kind: "Rug replay", title: "$" + (t.symbol || "?"), evId: "replay:" + t.mint,
    chips: [num((j.window || {}).transactionsAnalyzed) + " txs", num(s.xPostsMerged) + " X posts merged", s.lifespan || ""],
    sev, vi: verdictIndex(sev, null, true, (wb.INSIDER || 0) + (wb.SNIPER || 0)), vc: SEVC[sev] || "grey",
    verdictNote: a.lead ? a.lead.text : "",
    score: { label: "Peak holders", value: num(s.peakHolders), unit: "", note: "Peak holder count inside the analyzed window." },
    metrics: [["Insider-pattern est.", num(s.insiderProfitEstimateSol, 1) + " SOL", "red"], ["Organic loss est.", num(s.organicLossEstimateSol, 1) + " SOL", "red"], ["Lifespan", (s.lifespan || "—").split(" (")[0]], ["Rug method", s.rugMethod || "—"], ["X posts merged", num(s.xPostsMerged)]],
    rowsLabel: "Wallet classes", rows: Object.entries(wb).map(([k, n]) => ({ a: k + "-pattern", full: k, cls: k, c: { INSIDER: "red", SNIPER: "amber", ORGANIC: "green" }[k] || "grey", share: String(n), note: "wallets in the analyzed window" })),
    events: ev, xposts: (j.timeline || []).filter(e => e.type === "X_POST"),
    why: [a.lead && a.lead.text].concat((a.findings || []).map(f => f.text)).filter(Boolean).slice(0, 4), whyId: a.lead ? a.lead.id : "lead",
    limits: ((a.coverage || {}).limits || []).map(l => l.text || l).slice(0, 3).concat((j.notes || []).slice(0, 1)),
  };
}
function targets() { return of("token").map(tokenTarget).concat(of("wallet").map(walletTarget), of("replay").map(replayTarget)); }

/* ---------------- state ---------------- */
const VIEWS = [["home", "Home"], ["token", "Token"], ["wallet", "Wallet"], ["replay", "Replay"], ["signals", "Signals"], ["threats", "Threats"], ["shill", "Shill net"], ["copy", "Copy net"], ["board", "Leaderboard"], ["prov", "Provenance"]];
const S = { view: "home", target: null, scanning: false, brel: 0, t0: 0, tab: 0, open: false, scrub: 62, withX: false, dl: 0, dc: 0, dh: 0, feed: [], pool: [], paused: false, notifAt: 0, sel: {}, sort: { col: "appearances", dir: -1 }, filter: "ALL", sigFilter: "all", lastAsk: null };
window.GTB = { S, REPORTS, targets, addReport };
const three = () => window.GTB_STAGE || null;
const wide = () => innerWidth >= 1180 && innerHeight >= 680;

/* ---------------- ask about this ---------------- */
function ask(view, item, evId, report, facts) {
  const text = ["Grok The Block — explain this evidence.", "View: " + view, "Item: " + item, "Evidence ID: " + evId, "Report: " + report, "Key facts: " + facts.filter(Boolean).slice(0, 5).join("; "), "Question: What happened here, and what does the evidence support or not support?"].join("\n");
  S.lastAsk = text;
  const fallback = () => { $("#fbkTa").value = text; $("#fbk").classList.add("on"); setTimeout(() => { $("#fbkTa").focus(); $("#fbkTa").select(); }, 30); };
  try { if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(() => flash("Copied — paste into Grok Bot"), fallback); else fallback(); } catch (e) { fallback(); }
}
window.GTB.ask = ask;
const ASKS = new Map(); let askN = 0;
const askBtn = (label, args, cls = "ask", aria = "Ask Grok Bot about this") => { const id = "a" + (++askN); ASKS.set(id, args); return `<button class="${cls}" data-ask="${id}" aria-label="${esc(aria)}">${esc(label)}</button>`; };
document.addEventListener("click", (e) => { const b = e.target.closest("[data-ask]"); if (!b) return; e.preventDefault(); e.stopPropagation(); const a = ASKS.get(b.dataset.ask); if (a) ask(...a); }, true);
let toastT; function flash(m) { const t = $("#toast"); t.textContent = m; t.style.display = "block"; clearTimeout(toastT); toastT = setTimeout(() => t.style.display = "none", 1800); }
$("#fbkClose").onclick = $("#fbkSh").onclick = () => $("#fbk").classList.remove("on");

/* ---------------- feed (replays loaded reports; never invents items) ---------------- */
const MKT = { polymarket: "Prediction", kalshi: "Prediction", equities: "Stocks", options: "Stocks", treasury: "Rates", crypto: "Crypto", stablecoins: "Crypto", cross: "Cross-market", macro: "Macro", sec: "Filings", solana: "Crypto" };
function buildPool() {
  const out = [];
  of("signals").forEach(r => {
    (r.j.signals || []).forEach(s => out.push({ id: s.key, mkt: MKT[s.source] || s.source, subject: s.instrument || (s.subject || {}).name || s.source, text: String(s.title || "").replace(/^\[SYNTHETIC\]\s*/, ""), c: SEVC[s.severity] || "grey", sev: s.severity, ts: s.when, open: "signals", report: repLabel(r) }));
    Object.entries(r.j.sourceStatus || {}).forEach(([k, v]) => { if (v.state === "UNAVAILABLE") out.push({ id: "status:" + k, mkt: MKT[k] || k, subject: k, text: "No answer from source. Unknown, not quiet.", c: "grey", sev: null, ts: r.j.generatedAt, open: "signals", report: repLabel(r) }); });
  });
  of("threats").forEach(r => r.j.forEach(a => out.push({ id: a.id || a.key, mkt: "Crypto", subject: "$" + a.tokenSymbol, text: a.detail, c: SEVC[a.severity] || "grey", sev: a.severity, ts: a.timestamp, open: "threats", report: repLabel(r) })));
  of("watch").forEach(r => (r.j.alerts || []).slice(0, 12).forEach(a => out.push({ id: a.key || a.signature, mkt: "Crypto", subject: "$" + a.tokenSymbol, text: a.detail || a.type, c: SEVC[a.severity] || "grey", sev: a.severity, ts: a.timestamp, open: "token:" + a.tokenSymbol, report: repLabel(r) })));
  return out.sort((a, b) => (b.ts || 0) - (a.ts || 0));
}
S.pool = buildPool(); S.feed = S.pool.slice(0, 9); let poolI = 9;
const fTime = (f) => f.ts ? utc(new Date(f.ts < 1e12 ? f.ts * 1000 : f.ts)) : "--:--";
function openItem(o) { if (!o) return; if (o.startsWith("token:")) { const t = targets().find(x => x.id === o); if (t) return scan(t.id); } go(o); }
function renderFeed() {
  $("#feedN").textContent = S.feed.length;
  $("#feedList").innerHTML = S.feed.map(f => `<div class="fi${f.id === S.newId ? " new" : ""}"><button class="o" ${f.open ? `data-open="${esc(f.open)}"` : ""}><span style="width:8px;height:8px;margin-top:4px;background:${C[f.c]}"></span><span style="display:flex;flex-direction:column;gap:4px;min-width:0"><span class="up" style="display:flex;justify-content:space-between;gap:8px;font-size:10px;color:var(--m)"><span>${esc(f.mkt)} // ${esc(f.subject)}</span><span>${fTime(f)}</span></span><span style="font-size:12px;line-height:17px;overflow-wrap:anywhere">${esc(f.text)}</span></span></button><span style="padding-top:10px">${askBtn("Ask", ["Live feed // " + f.mkt, f.subject, f.id, f.report, ["Market: " + f.mkt, "Event: " + f.text, "Severity: " + (f.sev || "no data"), "Time: " + iso(f.ts)]])}</span></div>`).join("") || `<div class="empty">No items in the loaded reports.</div>`;
  const tk = S.feed.slice(0, 10); const items = tk.concat(tk).map(f => `<button class="tk" tabindex="-1" ${f.open ? `data-open="${esc(f.open)}"` : ""}><span class="sq" style="background:${C[f.c]}"></span><span class="up dim">${esc(f.mkt)} // ${esc(f.subject)}</span><span>${esc(f.text.length > 90 ? f.text.slice(0, 88) + "…" : f.text)}</span><span style="color:var(--b)">${fTime(f)}</span></button>`).join("");
  const tr = $("#track"); if (tr.dataset.sig !== tk.map(f => f.id).join()) { tr.innerHTML = items; tr.dataset.sig = tk.map(f => f.id).join(); tr.style.setProperty("--dur", Math.max(30, tk.length * 7) + "s"); }
}
document.addEventListener("click", (e) => { const b = e.target.closest("[data-open]"); if (b && (b.closest("#feed") || b.closest("#ticker"))) openItem(b.dataset.open); });
function pushFeed() { if (poolI >= S.pool.length) return; const it = S.pool[poolI++]; S.feed = [it].concat(S.feed).slice(0, 40); S.newId = it.id; renderFeed(); maybeNotify(it); }
function maybeNotify(it) {
  if ($("#feed").classList.contains("on") || !["red", "amber"].includes(it.c)) return; const now = Date.now(); if (now - S.notifAt < 9000) return; S.notifAt = now;
  const n = $("#notif"); n.hidden = false;
  n.innerHTML = `<div class="up" style="display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:10px"><span style="color:var(--y);display:flex;align-items:center;gap:8px"><span class="blinkdot"></span>Just happened</span><span class="dim">${fTime(it)} UTC</span></div><div style="display:grid;grid-template-columns:8px minmax(0,1fr);gap:10px"><span style="width:8px;height:8px;background:${C[it.c]};margin-top:5px"></span><span style="display:flex;flex-direction:column;gap:2px"><span class="up dim" style="font-size:10px">${esc(it.mkt)} // ${esc(it.subject)}</span><span style="font-size:13px;line-height:19px;overflow-wrap:anywhere">${esc(it.text)}</span></span></div><div style="display:flex;justify-content:flex-end;gap:6px"><button class="btn" id="nfX">Dismiss</button><button class="btn y" id="nfGo" style="border-color:var(--y)">${it.open && it.open.startsWith("token:") ? "Scan it" : "Open feed"}</button></div>`;
  requestAnimationFrame(() => n.classList.add("on"));
  clearTimeout(S.notifT); S.notifT = setTimeout(() => n.classList.remove("on"), 5000);
  $("#nfX").onclick = () => n.classList.remove("on");
  $("#nfGo").onclick = () => { n.classList.remove("on"); if (it.open && it.open.startsWith("token:")) openItem(it.open); else toggleFeed(true); };
}
window.GTB.pushFeed = pushFeed; window.GTB.notify = maybeNotify;
function toggleFeed(on) { const f = $("#feed"), b = $("#feedBtn"); on = on ?? !f.classList.contains("on"); f.classList.toggle("on", on); f.setAttribute("aria-hidden", on ? "false" : "true"); b.classList.toggle("on", on); b.setAttribute("aria-expanded", on); if (on) $("#notif").classList.remove("on"); }
$("#feedBtn").onclick = () => toggleFeed(); $("#feedClose").onclick = () => toggleFeed(false);
$("#pauseBtn").onclick = () => { S.paused = !S.paused; $("#pauseBtn").textContent = S.paused ? "Resume" : "Pause"; };

/* ---------------- search ---------------- */
function suggestions(q) {
  q = q.trim().toLowerCase().replace("$", "");
  const all = targets().map(t => ({ label: t.title, kind: t.kind, id: t.id, hay: (t.title + " " + t.kind + " " + t.evId).toLowerCase().replace("$", "") }))
    .concat([["signals", "Signals", "Cross-market report"], ["threats", "Threats", "Alert feed"], ["shill", "Shill net", "Social graph"], ["copy", "Copy net", "Copy-trade graph"], ["board", "Leaderboard", "Wallet ranking"], ["prov", "Provenance", "Media checks"]].map(([v, l, k]) => ({ label: l, kind: k, id: "view:" + v, hay: (l + " " + k).toLowerCase() })));
  return q ? all.filter(s => s.hay.includes(q)) : all.slice(0, 6);
}
function wireSearch(inp, box) {
  let sel = 0;
  const draw = () => { const sg = suggestions(inp.value); box.hidden = document.activeElement !== inp || !sg.length; box.innerHTML = sg.map((g, i) => `<button data-id="${esc(g.id)}" class="${i === sel ? "on" : ""}"><span>${esc(g.label)}</span><span class="k">${esc(g.kind)}</span></button>`).join(""); return sg; };
  inp.addEventListener("input", () => { sel = 0; draw(); }); inp.addEventListener("focus", draw); inp.addEventListener("blur", () => setTimeout(() => box.hidden = true, 150));
  box.addEventListener("mousedown", (e) => { const b = e.target.closest("button"); if (b) { e.preventDefault(); pickId(b.dataset.id); } });
  inp.addEventListener("keydown", (e) => { const sg = suggestions(inp.value); if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(sg.length - 1, sel + 1); draw(); } if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); draw(); } if (e.key === "Enter") { e.preventDefault(); submit(inp, sel); } if (e.key === "Escape") inp.blur(); });
}
function pickId(id) { $("#q").value = ""; $("#hq").value = ""; document.activeElement && document.activeElement.blur(); if (id.startsWith("view:")) go(id.slice(5)); else scan(id); }
function submit(inp, sel = 0) { const sg = suggestions(inp.value); if (inp.value.trim() && sg[sel]) pickId(sg[sel].id); else if (!inp.value.trim()) pickId(targets()[0].id); else flash('Nothing loaded matches "' + inp.value.trim().slice(0, 40) + '"'); }
wireSearch($("#q"), $("#sugg")); wireSearch($("#hq"), $("#hsugg"));
$("#scanBtn").onclick = () => submit($("#q"));
addEventListener("keydown", (e) => {
  const typing = /INPUT|TEXTAREA/.test(document.activeElement.tagName);
  if (((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") || (e.key === "/" && !typing)) { e.preventDefault(); const i = S.view === "home" ? $("#q") : $("#hq"); i.focus(); }
  if (e.key === "Escape") { $("#fbk").classList.remove("on"); if ($("#feed").classList.contains("on")) toggleFeed(false); }
});

/* ---------------- navigation ---------------- */
$("#views").innerHTML = VIEWS.map(([k, l]) => `<button data-view="${k}">${esc(l)}</button>`).join("");
$("#views").addEventListener("click", (e) => { const b = e.target.closest("[data-view]"); if (b) go(b.dataset.view); });
$("#logo").onclick = () => go("home");
function go(v) {
  if (v === "token" || v === "wallet" || v === "replay") { const t = targets().find(x => x.view === v && (!S.target || S.target.view !== v ? true : x.id === S.target.id)); if (t) return scan(t.id, true); }
  S.view = v; history.replaceState(null, "", "#" + v); if (three()) { three().setMode(v === "home" ? "home" : "result"); three().spin && v !== "home" && three().spin(); }
  render();
}
window.GTB.go = go;

/* ---------------- scan + kinetic result sequence ---------------- */
let scanT;
function scan(id, quiet) {
  const t = targets().find(x => x.id === id); if (!t) return flash("Nothing loaded matches that");
  S.view = t.view; S.target = t; S.tab = 0; S.open = false; S.brel = 0; S.dl = 0; S.dc = 0; S.dh = 0; S.scrub = 62; S._rv = -1; S._slam = false;
  $("#vdBox").dataset.landed = "0";
  history.replaceState(null, "", "#" + t.view + "/" + encodeURIComponent(t.title.replace("$", "")));
  if (three()) { three().setMode("result"); three().set && three().set(); }
  clearTimeout(scanT);
  if (reduced()) { S.scanning = false; S.t0 = performance.now() - 20000; render(); return; }
  S.scanning = true; S.t0 = 0; render();
  scanT = setTimeout(() => { S.scanning = false; S.t0 = performance.now(); S._rv = -1; if (three()) three().spin(); render(); }, quiet ? 700 : 1600);
}
window.GTB.scan = scan;
const boardRows = (t) => [[t.score.label, t.score.value + (t.score.unit && t.score.unit.startsWith("/") ? " " + t.score.unit : ""), null]].concat(t.metrics).slice(0, 5);
function reveal(t, B) { const n = boardRows(t).length; const raw = Math.floor(Math.max(0, B - 900) / 420); const land = 900 + n * 420 + 1700; const r = raw > n ? (B >= land ? n + 1 : n) : raw; return { r, n, land }; }
function dlgLines(t) {
  if (S.view === "home" || !t) return ["Hey. I'm Grok Bot.", "Drop a token, wallet or ticker and I'll read the loaded reports for you.", "I show the evidence and where it stops. Signals, not predictions."];
  const unit = t.score.unit && t.score.unit.startsWith("/") ? " " + t.score.unit : "";
  return ["TL;DR on " + t.title + ": " + HYPE[t.vi][0] + ".", t.verdictNote, t.score.label + ": " + t.score.value + unit + ". " + t.score.note, t.metrics.slice(0, 3).map(([k, v]) => k + " " + v).join(", ") + ".", t.why[1] || t.why[0] || "No further findings in this report.", "Signals, not predictions. Ask me about any row."].filter(Boolean);
}
function shake(px) { if (reduced()) return; const el = $("#stageWrap"); if (!el.animate) return; const k = []; for (let i = 0; i < 8; i++) { const a = px * (1 - i / 8); k.push({ transform: "translate(" + ((i % 2 ? 1 : -1) * a).toFixed(1) + "px," + ((i % 3 - 1) * a * 0.6).toFixed(1) + "px)" }); } k.push({ transform: "none" }); el.animate(k, { duration: 320, easing: "linear" }); }
function frame() {
  const t = S.target, stageView = ["home", "token", "wallet", "replay"].includes(S.view);
  if (stageView) {
    const B = S.view === "home" || S.scanning || !S.t0 ? 0 : performance.now() - S.t0; S.brel = B;
    if (S.view !== "home" && t) seqFrame(t, B);
    typeFrame(t, B);
  }
  if (!reduced() && !S.paused && Date.now() - (S.lastPush || 0) > 3800) { S.lastPush = Date.now(); if (S.lastPushInit) pushFeed(); S.lastPushInit = true; }
  requestAnimationFrame(frame);
}
function seqFrame(t, B) {
  const sw = $("#stageWrap").clientWidth, sh = $("#stageWrap").clientHeight, side = sw >= 640, big = side && sh >= 520;
  const { r, n, land } = reveal(t, B);
  if (B >= 280 && !S._slam) { S._slam = true; shake(9); three() && three().punch(); } if (B < 280) S._slam = false;
  if (r !== S._rv) { if (r > S._rv && three()) { if (r === n + 1) { three().react(t.vc); three().punch(); shake(t.vc === "red" ? 14 : 8); } else if (r > 0) three().hop(); } S._rv = r; }
  const wp = B < 50 ? 0 : B < 260 ? 1 : 2; const wipe = $("#wipe");
  wipe.style.transition = wp === 0 ? "none" : "clip-path .2s cubic-bezier(.7,0,.3,1)"; wipe.style.clipPath = S.scanning ? "inset(0 100% 0 0)" : wp === 0 ? "inset(0 100% 0 0)" : wp === 1 ? "inset(0 0 0 0)" : "inset(0 0 0 100%)";
  const rw = $("#resWord"); rw.style.opacity = B >= 280 ? 1 : 0; rw.style.transition = B >= 280 ? "transform .32s cubic-bezier(.2,1.6,.4,1), opacity .08s" : "none"; rw.style.transform = B >= 280 ? "rotate(-8deg) scale(1)" : "rotate(-14deg) scale(2.8)";
  $("#resSpan").style.fontSize = big ? "80px" : "56px";
  const st = $("#stats"); st.style.width = side ? "clamp(280px,46%,420px)" : "62%"; st.style.bottom = side ? "16px" : "136px";
  $("#hzTop").style.transform = B >= 750 ? "scaleX(1)" : "scaleX(0)"; $("#hzMid").style.transform = r > n - 1 && B >= 900 + n * 420 ? "scaleX(1)" : "scaleX(0)";
  const rows = boardRows(t); const box = $("#srows");
  if (box.dataset.t !== t.id) { box.dataset.t = t.id; box.innerHTML = rows.map(() => `<div class="srow"><span class="k disp"></span><span class="v disp"></span></div>`).join(""); }
  $$(".srow", box).forEach((el, i) => { const [k, v, c] = rows[i]; const on = r > i; const pp = easeO(Math.min(1, Math.max(0, B - 900 - i * 420) / 380)); el.classList.toggle("on", on); el.children[0].textContent = k; el.children[0].style.fontSize = big ? "26px" : "20px"; el.children[1].textContent = on ? countTo(v, pp) : v; el.children[1].style.fontSize = big ? "34px" : "24px"; el.children[1].style.color = c === "red" ? C.red : C.ink; });
  const rollStart = 900 + n * 420 + 150, steps = 22; let hi = t.vi, rolling = false;
  if (B >= rollStart && B < land) { rolling = true; const pr = easeO((B - rollStart) / (land - rollStart)); hi = ((t.vi - steps + Math.floor(pr * steps)) % HYPE.length + HYPE.length) % HYPE.length; }
  const tone = TONE[HYPE[hi][1]], done = r > n; const vb = $("#vdBox");
  $("#vdLab").style.opacity = B >= rollStart ? 1 : 0; $("#vdLab").style.fontSize = big ? "26px" : "20px";
  vb.style.opacity = B >= rollStart ? 1 : 0; vb.style.transform = done ? "scale(1)" : rolling ? "scale(0.92)" : "scale(2.4)"; vb.style.background = tone.bg; vb.style.color = tone.color; vb.style.borderColor = tone.border; vb.style.fontSize = big ? "40px" : "28px";
  $("#vdJp").textContent = tone.jp; $("#vdJp").style.display = tone.jp ? "inline" : "none"; $("#vdJp").style.fontSize = big ? "30px" : "22px"; $("#vdTx").textContent = HYPE[hi][0];
  vb.dataset.landed = done ? "1" : "0"; vb.dataset.tone = HYPE[hi][1];
}
function typeFrame(t, B) {
  const dlg = $("#dlg"), sw = $("#stageWrap").clientWidth;
  dlg.style.left = S.view === "home" && sw >= 640 ? "calc(52% + 8px)" : "16px"; dlg.style.right = S.view === "home" ? "16px" : sw >= 640 ? "calc(clamp(280px,46%,420px) + 44px)" : "16px";
  const lines = dlgLines(t); const L = lines[S.dl] || "";
  const ready = S.view === "home" ? true : (!S.scanning && t && reveal(t, B).r > reveal(t, B).n);
  if (S.scanning) { $("#dlgTx").textContent = "Scanning " + t.title + "…"; $("#dlgArr").style.display = "none"; three() && three().setTalking(false); return; }
  if (!ready) { $("#dlgTx").textContent = B < 900 ? "Scan done. Here is what I found." : "…"; $("#dlgPos").textContent = ""; $("#dlgArr").style.display = "none"; return; }
  const now = performance.now(); const dt = Math.min(100, now - (S._tl || now)); S._tl = now;
  if (reduced()) S.dc = L.length; else if (S.dc < L.length) S.dc = Math.min(L.length, S.dc + dt * 0.04); else if (S.dl < lines.length - 1) { S.dh += dt; if (S.dh > 2800) { S.dl++; S.dc = 0; S.dh = 0; } }
  $("#dlgTx").textContent = L.slice(0, Math.floor(S.dc)); $("#dlgPos").textContent = (S.dl + 1) + "/" + lines.length; $("#dlgArr").style.display = S.dc >= L.length ? "block" : "none";
  three() && three().setTalking(S.dc < L.length);
}
$("#dlg").onclick = () => { if (S.scanning) return; const L = dlgLines(S.target)[S.dl] || ""; const n = dlgLines(S.target).length; if (S.dc < L.length) S.dc = L.length; else { S.dl = S.dl < n - 1 ? S.dl + 1 : 0; S.dc = 0; S.dh = 0; } };

/* ---------------- render ---------------- */
function head(title, kindTxt, chips, askArgs, extra = "") {
  const h = $("#rhead"); h.hidden = false;
  h.innerHTML = `<div class="l"><h1 class="disp">${esc(title)}</h1><span class="meta up">${esc(kindTxt)}${chips.length ? " // " + chips.map(esc).join(" // ") : ""}</span></div><div class="acts">${askArgs ? askBtn("Ask about this", askArgs, "btn y", "Ask Grok Bot about this report") : ""}${extra}<button class="btn" id="exportBtn">Export</button></div>`;
}
function render() {
  $("#root").className = wide() ? "wide" : "narrow";
  $$("#views [data-view]").forEach(b => b.dataset.view === S.view ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
  const stageView = ["home", "token", "wallet", "replay"].includes(S.view);
  $("#stageWrap").hidden = !stageView; $("#panel").hidden = stageView; $("#home").hidden = S.view !== "home"; $("#res").hidden = !stageView || S.view === "home";
  $("#details").hidden = !stageView || S.view === "home"; $("#hsbox").hidden = S.view === "home"; $("#rhead").hidden = S.view === "home";
  if (three()) three().setVisible(stageView);
  const sw = $("#stageWrap").clientWidth || innerWidth;
  const hm = $("#home"); Object.assign(hm.style, sw >= 640 ? { left: "48px", top: "50%", transform: "translateY(-60%)", width: "min(520px,48%)" } : { left: "20px", top: "24px", transform: "none", width: "calc(100% - 40px)" }); $("#homeH1").style.fontSize = sw >= 900 ? "120px" : "72px";
  if (S.view === "home") { $("#tryChips").innerHTML = targets().filter((t, i, a) => a.findIndex(x => x.view === t.view) === i || t.view === "token").slice(0, 4).map(t => `<button data-scan="${esc(t.id)}">${esc(t.title)}</button>`).join(""); return; }
  if (stageView) {
    const t = S.target;
    head(t.title, t.kind, t.chips, [t.kind, t.title, t.evId, repLabel(t.r), [t.score.label + ": " + t.score.value + (t.score.unit ? " " + t.score.unit : ""), "Verdict phrase: " + HYPE[t.vi][0] + " (severity " + (t.sev || "n/a") + ")"].concat(t.metrics.slice(0, 3).map(([k, v]) => k + ": " + v))],
      `<button class="btn" id="rescanBtn">${S.scanning ? "Scanning…" : "Re-scan"}</button>` + (targets().filter(x => x.view === t.view).length > 1 ? `<button class="btn" id="nextRep">Next report</button>` : ""));
    $("#rescanBtn").onclick = () => scan(t.id); const nr = $("#nextRep"); if (nr) nr.onclick = () => { const l = targets().filter(x => x.view === t.view); scan(l[(l.findIndex(x => x.id === t.id) + 1) % l.length].id); };
    renderDetails(); return;
  }
  const P = $("#panel"); P.innerHTML = ""; ({ signals: vSignals, threats: vThreats, shill: vShill, copy: vCopy, board: vBoard, prov: vProv }[S.view] || (() => P.innerHTML = `<div class="empty">Unknown view.</div>`))(P);
}
document.addEventListener("click", (e) => { const b = e.target.closest("[data-scan]"); if (b) scan(b.dataset.scan); if (e.target.id === "exportBtn") doExport(); });
function renderDetails() {
  const t = S.target, labels = [t.rowsLabel, "Timeline", "Why flagged"];
  $("#details").classList.toggle("open", S.open);
  $("#dtabs").innerHTML = labels.map((l, i) => `<button role="tab" data-tab="${i}" aria-expanded="${S.open && S.tab === i}">${esc(l)}</button>`).join("") + `<span class="hint up">${S.open ? "Click the tab again to close" : "Details"}</span>`;
  const B = $("#dbody");
  if (S.tab === 0) B.innerHTML = t.rows.map(r => `<div class="hrow"><span class="a"><b>${esc(r.a)}</b><small>${esc(r.note)}</small></span><span class="tag ${r.c === "grey" ? "" : "t-" + r.c}">${esc(r.cls)}-pattern</span><span class="sh" style="text-align:right">${esc(r.share)}</span>${askBtn("Ask", [t.kind + " // " + t.rowsLabel, r.full || r.a, t.evId + "#" + (r.full || r.a), repLabel(t.r), ["Class: " + r.cls + " (timing pattern, not identity)", (t.rowsLabel === "Holders" ? "Supply share: " : "Value: ") + r.share, "Note: " + r.note, "Parent: " + t.title]])}</div>`).join("") || `<div class="empty">No rows in this report.</div>`;
  if (S.tab === 1) {
    let ev = t.events[0]; t.events.forEach(e => { if (e[0] <= S.scrub) ev = e; });
    const bars = Array.from({ length: 40 }, (_, i) => { const pct = (i + 0.5) / 40 * 100; let c = (t.events[0] || [0, "grey"])[1]; t.events.forEach(e => { if (e[0] <= pct) c = e[1]; }); const h = 18 + Math.abs(Math.sin(i * 1.7 + t.title.length)) * 50 * (1 - i / 60); return `<span style="height:${h.toFixed(0)}px;background:${C[c]};opacity:${pct <= S.scrub ? 1 : .25}"></span>`; }).join("");
    const xs = t.xposts && S.withX ? t.xposts.slice(0, 3) : [];
    B.innerHTML = t.events.length ? `<div style="padding:16px"><div class="bars">${bars}<span class="cur" style="left:${S.scrub}%"></span></div><input type="range" id="scrub" min="0" max="100" value="${S.scrub}" aria-label="Scrub timeline" style="width:100%;height:28px;margin-top:8px"><div id="evText" style="display:flex;gap:10px;align-items:flex-start;padding:8px 0;text-wrap:pretty"><span style="width:8px;height:8px;background:${C[ev[1]]};margin-top:5px;flex-shrink:0"></span>${esc(ev[2])}</div>${t.xposts ? `<label style="display:flex;gap:8px;align-items:center;min-height:32px"><input type="checkbox" id="withx" ${S.withX ? "checked" : ""}> Overlay X posts (${t.xposts.length} merged)</label>` + xs.map(x => `<div class="lim">${esc((x.relativeTime || "") + " · " + (x.detail || "X post"))}</div>`).join("") : ""}</div>` : `<div class="empty">No timeline in this report.</div>`;
    const sc = $("#scrub"); if (sc) sc.oninput = () => { S.scrub = +sc.value; renderDetails(); $("#scrub").focus(); };
    const wx = $("#withx"); if (wx) wx.onchange = () => { S.withX = wx.checked; renderDetails(); };
  }
  if (S.tab === 2) B.innerHTML = `<div style="display:flex;flex-direction:column;gap:12px;padding:16px"><div class="why">${t.why.map(y => `<div>${esc(y)}</div>`).join("") || "<div>No findings in this report.</div>"}<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:10px;flex-wrap:wrap"><span style="font-size:10px;letter-spacing:.04em">FINDING // FROM THE REPORT // DO NOT PARAPHRASE</span>${askBtn("Ask about this", [t.kind + " // Why flagged", t.title, t.evId + "#finding:" + t.whyId, repLabel(t.r), t.why.slice(0, 4)], "ask", "Ask Grok Bot about this finding").replace('class="ask"', 'class="ask" style="background:#0b0b0d;border-color:#0b0b0d"')}</div></div>${t.limits.map(y => `<div class="lim">${esc(y)}</div>`).join("")}</div>`;
}
$("#dtabs").addEventListener("click", (e) => { const b = e.target.closest("[data-tab]"); if (!b) return; const i = +b.dataset.tab; S.open = S.tab === i ? !S.open : true; S.tab = i; if (three()) three().spin(); renderDetails(); });

/* ---------------- panel views ---------------- */
const sq = (c) => `<span class="sq" style="background:${C[c] || C.grey}"></span>`;
function vSignals(P) {
  const r = of("signals")[0]; if (!r) { head("Signals", "Cross-market", [], null); P.innerHTML = `<div class="empty">No signals report loaded. Open a signals JSON file from the Export menu.</div>`; return; }
  const j = r.j, a = j.assessment || {}, cov = j.coverage || {}, w = j.watch || {}, tel = w.telemetry || {};
  head("Signals", "Cross-market report", [num((j.signals || []).length) + " signals", "status " + (j.status || "?"), genAt(r)], ["Signals", "Signals report", "signals:" + (a.lead || {}).signal, repLabel(r), ["Lead: " + (a.lead || {}).text, "Severity: " + a.severity, "Status: " + j.status]]);
  const srcs = Object.entries(j.sourceStatus || {});
  const fams = ["all"].concat([...new Set((j.signals || []).map(s => s.source))]);
  const sigs = (j.signals || []).filter(s => S.sigFilter === "all" || s.source === S.sigFilter);
  P.innerHTML = `<div class="card"><h2 class="disp">Summary</h2><dl class="kv"><dt>What happened</dt><dd>${esc((a.lead || {}).text)}</dd><dt>How fresh</dt><dd>${esc(genAt(r))}</dd><dt>What was observed</dt><dd>${srcs.filter(([, v]) => v.state === "HEALTHY").length} of ${srcs.length} sources answered; ${esc(srcs.filter(([, v]) => v.state !== "HEALTHY").map(([k, v]) => k + " " + v.state).join(", "))}</dd><dt>Why it was flagged</dt><dd>${esc((a.lead || {}).why || "—")}</dd></dl></div>
  <div class="grid2"><div class="card"><h2 class="disp">Feed</h2><div class="chips" role="group" aria-label="Source filter">${fams.map(f => `<button class="chip" data-sf="${esc(f)}" aria-pressed="${S.sigFilter === f}">${esc(f)}</button>`).join("")}</div><div class="list">${sigs.map(s => sigItem(s, r)).join("") || `<div class="empty">No signals from this source.</div>`}</div></div>
  <div style="display:flex;flex-direction:column;gap:12px"><div class="card"><h2 class="disp">Calendar</h2>${((j.calendar || {}).upcoming || []).map(c => `<div class="lim">${esc(c.label)} · ${esc(c.time)}${c.timeExact ? "" : " (approximate)"}</div>`).join("") || `<div class="empty">No calendar events.</div>`}</div>
  <div class="card"><h2 class="disp">Watch telemetry</h2><dl class="kv">${Object.entries(tel).filter(([, v]) => typeof v === "number").map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl></div></div></div>
  <div class="card"><h2 class="disp">Coverage</h2><div class="tw"><table class="t"><thead><tr><th>Source</th><th>Family</th><th>Status</th><th>Last valid</th><th>Universe</th><th>Observed</th><th>Note</th></tr></thead><tbody>${(cov.matrix || []).map(m => `<tr><td>${esc(m.source)}</td><td>${esc(m.family || "—")}</td><td style="color:${m.status === "HEALTHY" ? C.green : m.status === "UNAVAILABLE" ? C.red : C.amber}">${esc(m.status)}</td><td>${esc(m.lastValidAt || "—")}</td><td>${esc(m.universe || "—")}</td><td>${m.observed ?? "—"}</td><td class="dim">${esc(m.detail || "")}</td></tr>`).join("")}</tbody></table></div>${(cov.limits || []).map(l => `<div class="lim">${esc(l.kind)}: ${esc(l.text)}</div>`).join("")}</div>`;
  $$("[data-sf]", P).forEach(b => b.onclick = () => { S.sigFilter = b.dataset.sf; render(); });
}
function sigItem(s, r) {
  const m = s.metrics || {};
  const timing = (m.timingComparable === false || m.spanHours == null) ? "timing comparison approximate" : (m.spanHours != null ? m.spanHours + "h apart" : "");
  const rel = s.type === "CONVERGENCE" ? `<div><b style="font-weight:400;color:var(--y)">Related observations</b> · ${esc(timing)}</div>${(m.contributing || []).map(c => `<div class="lim">${esc(c.title || c.key || "")} ${c.temporalCertainty && c.temporalCertainty !== "exact" ? "(time " + esc(c.temporalCertainty) + ")" : ""}</div>`).join("")}` : "";
  return `<details class="it"><summary>${sq(SEVC[s.severity])}<span style="display:flex;flex-direction:column;gap:4px;min-width:0"><span class="hd"><span>${esc(MKT[s.source] || s.source)} // ${esc(s.instrument || (s.subject || {}).name || "")}</span><span>${esc(s.severity)} · ${esc(s.basis)}</span></span><span class="ti">${esc(s.title)}</span></span>${askBtn("Ask", ["Signals", s.title, s.key, repLabel(r), ["Type: " + s.type, "Severity: " + s.severity, "Basis: " + s.basis, "When: " + iso(s.when)]])}</summary><div class="dz"><div>${esc(s.what)}</div><dl class="kv"><dt>Key</dt><dd>${esc(s.key)}</dd><dt>When</dt><dd>${esc(iso(s.when))}</dd><dt>Basis</dt><dd>${esc(s.basis)}</dd>${m.rank != null ? `<dt>Sort aid</dt><dd>${esc(m.rank)} (uncalibrated, not a probability)</dd>` : ""}</dl>${rel}${askBtn("Ask about this dossier", ["Signals // dossier", s.title, s.key, repLabel(r), ["What: " + String(s.what).slice(0, 160), "Basis: " + s.basis, timing && "Timing: " + timing]], "btn y")}</div></details>`;
}
function vThreats(P) {
  const rs = of("threats"), ws = of("watch");
  const items = [].concat(...rs.map(r => r.j.map(a => ({ a, r, id: a.id || a.key }))), ...ws.map(r => (r.j.alerts || []).map(a => ({ a, r, id: a.key || a.signature }))));
  head("Threats", "Alert feed", [items.length + " alerts", items.filter(x => /HIGH|CRITICAL/.test(x.a.severity)).length + " high or critical"], items[0] ? ["Threats", "Alert feed", "threats:" + items.length, rs.concat(ws).map(repLabel).join(" + "), ["Alerts: " + items.length]] : null);
  const sevs = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"]; const vis = items.filter(x => S.filter === "ALL" || x.a.severity === S.filter);
  const snap = ws[0] && ws[0].j.snapshot;
  P.innerHTML = `<div class="grid2"><div class="card"><h2 class="disp">Alerts</h2><div class="chips" role="group" aria-label="Severity filter">${sevs.map(s => `<button class="chip" data-sev="${s}" aria-pressed="${S.filter === s}">${s}</button>`).join("")}</div><div class="list">${vis.map(({ a, r, id }) => `<details class="it"><summary>${sq(SEVC[a.severity])}<span style="display:flex;flex-direction:column;gap:4px;min-width:0"><span class="hd"><span>${esc(a.type)} // $${esc(a.tokenSymbol)}</span><span>${esc(a.severity)}${a.timestamp ? " · " + fTime(a) : ""}</span></span><span class="ti">${esc(a.detail || a.type)}</span></span>${askBtn("Ask", ["Threats", "$" + a.tokenSymbol + " " + a.type, id, repLabel(r), ["Type: " + a.type, "Severity: " + a.severity, "Detail: " + (a.detail || ""), a.wallet && "Wallet: " + a.wallet, a.amountSol != null && "Amount: " + a.amountSol + " SOL"]])}</summary><div class="dz"><dl class="kv"><dt>Alert ID</dt><dd>${esc(id)}</dd><dt>Mint</dt><dd>${esc(a.tokenMint)}</dd>${a.wallet ? `<dt>Wallet</dt><dd>${esc(a.wallet)}</dd>` : ""}${a.amountSol != null ? `<dt>Amount</dt><dd>${esc(a.amountSol)} SOL</dd>` : ""}${a.timestamp ? `<dt>Time</dt><dd>${esc(iso(a.timestamp))}</dd>` : ""}${a.evidence ? `<dt>Evidence</dt><dd>${esc(typeof a.evidence === "string" ? a.evidence : JSON.stringify(a.evidence).slice(0, 240))}</dd>` : ""}</dl></div></details>`).join("") || `<div class="empty">No alerts at this severity.</div>`}</div></div>
  <div class="card"><h2 class="disp">Monitoring</h2>${snap ? `<dl class="kv"><dt>Token</dt><dd>$${esc(ws[0].j.token.symbol)}</dd><dt>Checked</dt><dd>${esc(iso(ws[0].j.checkedAt))}</dd><dt>Verdict</dt><dd>${esc(snap.verdict)}</dd><dt>Organic score</dt><dd>${esc(snap.organicScore)}</dd><dt>Bundle</dt><dd>${esc(num(snap.bundlePct, 1))}% (${esc(snap.bundleSeverity)})</dd><dt>Liquidity</dt><dd>${esc(usd(snap.liquidityUsd))}</dd><dt>Mint authority</dt><dd>${snap.mintAuthority ? "enabled" : "revoked"}</dd><dt>LP locked</dt><dd>${esc(snap.lpLockedPct)}%</dd></dl>${(ws[0].j.notes || []).map(n => `<div class="lim">${esc(n)}</div>`).join("")}` : `<div class="empty">No watch report loaded.</div>`}</div></div>`;
  $$("[data-sev]", P).forEach(b => b.onclick = () => { S.filter = b.dataset.sev; render(); });
}
function graphSVG(nodes, edges, key) {
  const W = 640, H = 420, cx = W / 2, cy = H / 2; const main = nodes.filter(n => n.deg > 0), iso_ = nodes.filter(n => !n.deg);
  main.forEach((n, i) => { const a = i / main.length * Math.PI * 2 - Math.PI / 2, rr = main.length < 4 ? 90 : 140; n.x = cx + Math.cos(a) * rr * (n.lead ? 0 : 1); n.y = cy + Math.sin(a) * rr * (n.lead ? 0 : 1); });
  iso_.forEach((n, i) => { const a = i / iso_.length * Math.PI * 2; n.x = cx + Math.cos(a) * 196; n.y = cy + Math.sin(a) * 196 * 0.95; });
  const sel = S.sel[key]; const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
  return `<svg class="graph" viewBox="0 0 ${W} ${H}" role="group" aria-label="Graph. Tab to a node, Enter to select, arrows to move.">${edges.map(e => { const a = byId[e.a], b = byId[e.b]; if (!a || !b) return ""; const on = sel && (e.a === sel || e.b === sel); return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${on ? "#faf905" : "#6584f8"}" stroke-opacity="${on ? 1 : .5}" stroke-width="${Math.min(6, 1 + (e.w || 1) / 4)}"/>` + (e.label && (on || edges.length < 6) ? `<text x="${(a.x + b.x) / 2}" y="${(a.y + b.y) / 2 - 6}" fill="#c8c8cc" font-size="10" text-anchor="middle">${esc(e.label)}</text>` : ""); }).join("")}
  ${nodes.map(n => `<g class="n" tabindex="0" role="button" data-node="${esc(n.id)}" aria-pressed="${sel === n.id}" aria-label="${esc(n.label)}${n.deg ? ", " + n.deg + " links" : ", isolated"}"><circle class="ring" cx="${n.x}" cy="${n.y}" r="${n.deg ? 11 + Math.min(10, n.deg * 1.5) : 6}" fill="${sel === n.id ? "#faf905" : n.deg ? (n.color || "#16161a") : "#2a2a30"}" stroke="${sel === n.id ? "#faf905" : n.deg ? "#6584f8" : "#6a6a72"}" stroke-width="2"/>${n.deg || sel === n.id ? `<text x="${n.x}" y="${n.y + (n.deg ? 11 + Math.min(10, n.deg * 1.5) : 6) + 13}" fill="#fff" font-size="10" text-anchor="middle">${esc(n.short || n.label)}</text>` : ""}</g>`).join("")}</svg>`;
}
function wireGraph(P, key, rerender) {
  const ns = $$(".n", P);
  ns.forEach((g, i) => { g.onclick = () => { S.sel[key] = g.dataset.node; rerender(g.dataset.node); };
    g.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); g.onclick(); } else if (/Arrow/.test(e.key)) { e.preventDefault(); const d = /Right|Down/.test(e.key) ? 1 : -1; ns[(i + d + ns.length) % ns.length].focus(); } else if (e.key === "Escape") { S.sel[key] = null; rerender(null); } }; });
}
function vShill(P) {
  const r = of("shill")[0]; if (!r) { head("Shill net", "Social graph", [], null); P.innerHTML = `<div class="empty">No shill-network report loaded. Empty network.</div>`; return; }
  const j = r.j; const deg = {}; (j.edges || []).forEach(e => { deg[e.a] = (deg[e.a] || 0) + 1; deg[e.b] = (deg[e.b] || 0) + 1; });
  const accts = j.accounts || []; const clusterOf = {}; (j.clusters || []).forEach((c, i) => c.accounts.forEach(a => clusterOf[a] = i));
  const nodes = accts.slice(0, 40).map(a => ({ id: a.id, label: a.username, short: a.username.replace("account", "#"), deg: deg[a.id] || 0, color: clusterOf[a.id] != null ? ["#16161a", "#2a2a30"][clusterOf[a.id] % 2] : null, a }));
  const edges = (j.edges || []).map(e => ({ a: e.a, b: e.b, w: e.text + e.burst + e.created, label: e.text + " text" }));
  head(j.ticker + " shill net", "Shill network", [num(j.sample.posts) + " posts", num(j.sample.accounts) + " accounts", "coordination " + j.coordinationIndex + "%"], ["Shill net", j.ticker, "shill:" + j.ticker, repLabel(r), ["Coordination index: " + j.coordinationIndex + "% (signal, not a verdict)", "Clusters: " + (j.clusters || []).length, "Exact duplicate texts: " + (j.exactDuplicateTexts || []).length]]);
  const draw = (sel) => {
    const n = nodes.find(x => x.id === sel); const es = (j.edges || []).filter(e => e.a === sel || e.b === sel);
    const c = sel && clusterOf[sel] != null ? j.clusters[clusterOf[sel]] : null;
    P.innerHTML = `<div class="grid2" style="flex:1"><div class="card" style="padding:0;display:flex;flex-direction:column"><div style="padding:10px 14px" class="dim">${nodes.filter(x => x.deg).length} linked accounts · ${nodes.filter(x => !x.deg).length} isolated (outer ring) · ${(j.clusters || []).length} clusters</div>${graphSVG(nodes, edges, "shill")}</div>
    <div class="card" id="evPanel"><h2 class="disp">Evidence</h2>${n ? `<dl class="kv"><dt>Account</dt><dd>${esc(n.label)}</dd><dt>Followers</dt><dd>${esc(n.a.followers)}</dd><dt>Age</dt><dd>${esc(n.a.ageBucket)}</dd><dt>Posts</dt><dd>${esc(n.a.posts)}</dd><dt>Flags</dt><dd>${esc((n.a.flags || []).join(", ") || "none")}</dd><dt>Links</dt><dd>${es.length}</dd>${c ? `<dt>Cluster</dt><dd>${c.size} accounts, ${c.posts} posts, ${c.textLinks} text links</dd>` : ""}</dl>${es.slice(0, 6).map(e => `<div class="lim">${esc(e.a)} ↔ ${esc(e.b)} · ${e.text} similar texts · ${e.burst} burst · ${e.created} creation</div>`).join("")}<div style="margin-top:10px">${askBtn("Ask about this", ["Shill net // evidence", n.label, "shill:" + j.ticker + "#account:" + n.id, repLabel(r), ["Links: " + es.length, c ? "Cluster size: " + c.size : "Not in a cluster", "Followers: " + n.a.followers, "Account age: " + n.a.ageBucket]], "btn y")}</div>` : `<div class="empty">Select an account (click, tap, or Tab + Enter) to see its evidence.</div>`}<div class="lim" style="margin-top:10px">${esc(j.disclaimer)}</div></div></div>`;
    wireGraph(P, "shill", (s) => { draw(s); const g = $(`[data-node="${CSS.escape(s || "")}"]`, P); g && g.focus(); });
  };
  draw(S.sel.shill);
}
function vCopy(P) {
  const all = of("token"); const withNet = all.filter(r => (r.j.copyNetwork || []).length);
  const r = all.find(x => x.name === S.copyRep) || withNet[0] || all[0];
  const pick = all.length > 1 ? `<select id="copyPick" aria-label="Token report" style="height:30px;background:var(--p);color:var(--w);border:1px solid var(--b)">${all.map(x => `<option value="${esc(x.name)}" ${x === r ? "selected" : ""}>$${esc(x.j.token.symbol)}${(x.j.copyNetwork || []).length ? "" : " (no copy links)"}</option>`).join("")}</select>` : "";
  if (!r) { head("Copy net", "Copy-trade graph", [], null); P.innerHTML = `<div class="empty">No token report loaded.</div>`; return; }
  const net = r.j.copyNetwork || [];
  head("$" + r.j.token.symbol + " copy net", "Copy-trade network", [net.length + " links", "from the token scan"], net.length ? ["Copy net", "$" + r.j.token.symbol, "copy:" + r.j.token.mint, repLabel(r), ["Links: " + net.length]] : null, pick);
  const pk = $("#copyPick"); if (pk) pk.onchange = () => { S.copyRep = pk.value; S.sel.copy = null; render(); };
  if (!net.length) { P.innerHTML = `<div class="card"><div class="empty">No copy-trade links in $${esc(r.j.token.symbol)}'s scan. An empty network means none were detected in the analyzed window, not that none exist.</div></div>`; return; }
  const ids = [...new Set(net.flatMap(e => [e.leader, e.follower]))]; const leaders = new Set(net.map(e => e.leader));
  const nodes = ids.map(id => ({ id, label: (leaders.has(id) ? "Leader " : "Follower ") + short(id), short: short(id), deg: net.filter(e => e.leader === id || e.follower === id).length, lead: leaders.has(id) && leaders.size === 1, color: leaders.has(id) ? "#2a2a30" : "#16161a" }));
  const edges = net.map(e => ({ a: e.leader, b: e.follower, w: e.matchCount, label: "follows " + e.avgDelaySeconds + "s · " + e.matchCount + "×" }));
  const draw = (sel) => {
    const es = net.filter(e => e.leader === sel || e.follower === sel); const role = sel ? (leaders.has(sel) ? "Leader" : "Follower") : "";
    P.innerHTML = `<div class="grid2" style="flex:1"><div class="card" style="padding:0">${graphSVG(nodes, edges, "copy")}</div><div class="card" id="evPanel"><h2 class="disp">Evidence</h2>${sel ? `<dl class="kv"><dt>Wallet</dt><dd>${esc(sel)}</dd><dt>Role</dt><dd>${role} (timing relationship, not control)</dd></dl>${es.map(e => `<div class="lim">${esc(short(e.leader))} → ${esc(short(e.follower))} · avg delay ${e.avgDelaySeconds}s · ${e.matchCount} matched trades</div>`).join("")}<div style="margin-top:10px">${askBtn("Ask about this", ["Copy net // evidence", sel, "copy:" + r.j.token.mint + "#wallet:" + sel, repLabel(r), ["Role: " + role, "Links: " + es.length].concat(es.slice(0, 2).map(e => "Avg delay " + e.avgDelaySeconds + "s over " + e.matchCount + " trades"))], "btn y")}</div>` : `<div class="empty">Select a leader or follower (click, tap, or Tab + Enter).</div>`}<div class="lim" style="margin-top:10px">Copy-trade links are timing matches between wallets, not proof that one controls the other.</div></div></div>`;
    wireGraph(P, "copy", (s) => { draw(s); const g = $(`[data-node="${CSS.escape(s || "")}"]`, P); g && g.focus(); });
  };
  draw(S.sel.copy);
}
function vBoard(P) {
  const r = of("board")[0]; if (!r) { head("Leaderboard", "Wallet ranking", [], null); P.innerHTML = `<div class="empty">No leaderboard loaded.</div>`; return; }
  const j = r.j; const cols = [["address", "Wallet"], ["appearances", "Seen"], ["winRate", "Win rate"], ["avgEntryBlock", "Avg entry block"], ["totalEstimatedPnlSol", "Est. PnL (SOL)"], ["lastSeen", "Last seen"]];
  const rows = j.entries.slice().sort((a, b) => { const x = a[S.sort.col], y = b[S.sort.col]; return (x > y ? 1 : x < y ? -1 : 0) * S.sort.dir; });
  head("Leaderboard", j.type + "-pattern wallets", [num(j.totalWalletsTracked) + " wallets tracked", num(j.tokensScanned) + " tokens", j.dataSpan], ["Leaderboard", j.type + " board", "board:" + j.type, repLabel(r), ["Wallets tracked: " + j.totalWalletsTracked, "Tokens scanned: " + j.tokensScanned, "Span: " + j.dataSpan]]);
  P.innerHTML = `<div class="card"><div class="lim" style="margin-bottom:8px">${esc(j.note)} Rankings describe launch-timing patterns, not identities.</div><div class="tw"><table class="t"><thead><tr><th>#</th>${cols.map(([k, l]) => `<th ${S.sort.col === k ? `aria-sort="${S.sort.dir > 0 ? "ascending" : "descending"}"` : ""}><button data-sort="${k}">${esc(l)}${S.sort.col === k ? (S.sort.dir > 0 ? " ▲" : " ▼") : ""}</button></th>`).join("")}<th></th></tr></thead><tbody>${rows.map((e, i) => `<tr><td>${i + 1}</td><td title="${esc(e.address)}">${esc(short(e.address))}</td><td>${e.appearances}</td><td>${e.winRate}%</td><td>${num(e.avgEntryBlock, 1)}</td><td style="color:${e.totalEstimatedPnlSol >= 0 ? C.green : C.red}">${num(e.totalEstimatedPnlSol, 2)}</td><td>${esc(String(e.lastSeen).slice(0, 16))}</td><td>${askBtn("Ask", ["Leaderboard", e.address, "board:" + j.type + "#" + e.address, repLabel(r), ["Seen: " + e.appearances + "×", "Win rate: " + e.winRate + "%", "Avg entry block: " + e.avgEntryBlock]])}</td></tr>`).join("")}</tbody></table></div></div>`;
  $$("[data-sort]", P).forEach(b => b.onclick = () => { const k = b.dataset.sort; S.sort = { col: k, dir: S.sort.col === k ? -S.sort.dir : -1 }; render(); const nb = $(`[data-sort="${k}"]`); nb && nb.focus(); });
}
function vProv(P) {
  const r = of("prov")[0]; if (!r) { head("Provenance", "Media checks", [], null); P.innerHTML = `<div class="empty">No provenance report loaded.</div>`; return; }
  const j = r.j;
  head("Provenance", "Promo provenance", [j.results.length + " files"], ["Provenance", "Media checks", "prov:" + j.results.map(x => (x.sha256 || "").slice(0, 12)).join(","), repLabel(r), ["Files: " + j.results.length, "Disclaimer: " + j.disclaimer]]);
  P.innerHTML = `<div class="card"><div class="lim">${esc(j.disclaimer)}</div></div>` + j.results.map(x => `<div class="card"><div style="display:flex;justify-content:space-between;gap:10px;align-items:baseline;flex-wrap:wrap"><h2 class="disp" style="overflow-wrap:anywhere">${esc(x.file)}</h2>${askBtn("Ask about this", ["Provenance", x.file, "prov:" + x.sha256, repLabel(r), (x.signals || []).slice(0, 3).concat(["C2PA: " + ((x.c2pa || {}).present ? "present" : "absent")])], "btn y")}</div><dl class="kv"><dt>SHA-256</dt><dd>${esc(x.sha256)}</dd><dt>Size</dt><dd>${num(x.sizeBytes)} bytes</dd><dt>C2PA</dt><dd>${(x.c2pa || {}).present ? "present" : "absent"}</dd><dt>Reuse matches</dt><dd>${(x.reuseMatches || []).length}</dd><dt>Label</dt><dd>${esc(typeof x.label === "string" ? x.label : JSON.stringify(x.label || "—"))}</dd></dl><div style="margin-top:8px">${(x.signals || []).map(s => `<div class="lim">${esc(s)}</div>`).join("")}${(x.notes || []).map(s => `<div class="lim">${esc(s)}</div>`).join("")}</div></div>`).join("");
}

/* ---------------- export / open (no network) ---------------- */
function curReport() { if (S.target && ["token", "wallet", "replay"].includes(S.view)) return S.target.r; return ({ signals: of("signals")[0], threats: of("threats")[0], shill: of("shill")[0], copy: of("token").find(x => x.name === S.copyRep) || of("token")[0], board: of("board")[0], prov: of("prov")[0] })[S.view]; }
function doExport() { const r = curReport(); if (!r) return flash("Nothing to export"); const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(r.j, null, 2)], { type: "application/json" })); a.download = r.name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); flash("Exported " + r.name); }
$("#pick").onchange = async (e) => { let n = 0; for (const f of e.target.files) { try { if (addReport(f.name, JSON.parse(await f.text()))) n++; } catch (x) { } } S.pool = buildPool(); flash(n ? "Opened " + n + " report" + (n > 1 ? "s" : "") : "Not a Grok The Block report"); render(); };
window.GTB.open = () => $("#pick").click();

/* ---------------- boot ---------------- */
addEventListener("resize", () => { const w = wide(); if ((w ? "wide" : "narrow") !== $("#root").className) render(); });
RM.addEventListener && RM.addEventListener("change", render);
renderFeed();
const h = decodeURIComponent(location.hash.slice(1));
if (h.includes("/")) { const [v, sym] = h.split("/"); const t = targets().find(x => x.view === v && x.title.replace("$", "") === sym); if (t) scan(t.id); else go(v); } else if (VIEWS.some(([k]) => k === h)) go(h); else render();
requestAnimationFrame(frame);
window.GTB.ready = true;
})();
