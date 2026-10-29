/* Grok The Block v6 UI. Vanilla JS, no network: data comes from data/reports.js (window.GTB_REPORTS) or files the user opens. */
"use strict";
(() => {
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
// Central external-link gate: only explicit https: URLs become links; everything else renders as inert text.
function safeExternalUrl(v) {
  if (typeof v !== "string") return null;
  const raw = v.trim(); if (!raw || raw.length > 2048 || /[\u0000-\u001f\u007f-\u009f\s\\\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]/.test(raw)) return null;
  if (!/^https:\/\//i.test(raw)) return null;
  let u; try { u = new URL(raw); } catch (e) { return null; }
  if (u.protocol !== "https:" || !u.hostname || u.username || u.password) return null;
  return u.href;
}
const extLink = (url, label) => { const h = safeExternalUrl(url); return h ? `<a href="${esc(h)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : `<span class="nolink" title="Link not shown: only https links are allowed">${esc(label)}</span>`; };
window.GTB_safeExternalUrl = safeExternalUrl;
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const RM = matchMedia("(prefers-reduced-motion: reduce)");
const reduced = () => RM.matches;
const C = { red: "#ff3d00", amber: "#faf905", green: "#6584f8", grey: "#6a6a72", ink: "#ffffff" };
const SEVC = { CRITICAL: "red", HIGH: "red", MEDIUM: "amber", LOW: "green" };
const pad = (n) => String(n).padStart(2, "0");
const utc = (d) => pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes());
// Imported reports are untrusted: an unparseable or out-of-range timestamp reads "unknown time" instead of throwing (RC2-final F-2).
// Hash/title encoding must never throw on untrusted input (lone surrogates, malformed %-escapes): RC2-final F-3.
const encU = (v) => { try { return encodeURIComponent(v); } catch (e) { return encodeURIComponent(String(v).replace(/[\ud800-\udfff]/g, "\ufffd")); } };
const decU = (v) => { try { return decodeURIComponent(v); } catch (e) { return ""; } };
const iso = (ts) => { if (ts == null) return "unknown time"; const d = new Date(typeof ts === "number" ? (ts < 1e12 ? ts * 1000 : ts) : Date.parse(ts)); return isNaN(d.getTime()) ? "unknown time" : d.toISOString().replace(".000Z", "Z").replace("T", " "); };
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
// Real cached markets report (prediction markets, equities, options, Treasury, crypto) first, so the market tools read it; the
// embedded synthetic examples stay available under Anomalies > Examples.
if (window.GTB_EVERYTHING && window.GTB_EVERYTHING.markets) addReport("markets-live-derived.json", window.GTB_EVERYTHING.markets);
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
/* ---------------- everything markets (data/everything.js: real cached derived signals + flagged synthetic examples) ---------------- */
const EV = window.GTB_EVERYTHING || { categories: [], universe: [], live: { signals: [], probes: [], coverage: [], assets: [] }, synthetic: { signals: [], probes: [] } };
const EV_SIGS = (EV.live.signals || []).map(s => ({ s, set: "live" })).concat((EV.synthetic.signals || []).map(s => ({ s, set: "synthetic" })));
// Tracked-but-quiet assets: every live asset with no signal gets a "nothing past threshold" (or "unknown") evidence view.
const MOD_CAT = { fx: "fx", metals: "metals", energy: "energy", cot: "positioning", mtg: "cards", cs2: "skins" };
(EV.live.assets || []).forEach(a => {
  if ((EV.live.signals || []).some(s => s.asset === a.id)) return;
  const ps = (EV.live.probes || []).filter(p => p.asset === a.id || p.asset === a.name); if (!ps.length) return;
  const m = ps.filter(p => p.state === "measured").sort((x, y) => y.ratio - x.ratio)[0], u = ps.find(p => p.state === "unknown"), mod = ps[0].module;
  EV_SIGS.push({ set: "live", quiet: true, s: { key: mod + ":" + a.id + ":CHECKS", source: mod, category: MOD_CAT[mod] || mod, asset: a.id, name: a.name, type: m ? m.type : u.type, severity: m ? "NONE" : "UNKNOWN", basis: "observed",
    title: m ? a.name + ": nothing past threshold (closest check " + m.type.replace(/_/g, " ").toLowerCase() + " at " + m.ratio.toFixed(2) + "×)" : a.name + ": unknown, not quiet (" + u.reason + ")",
    what: ps.map(p => p.type.replace(/_/g, " ").toLowerCase() + ": " + (p.state === "measured" ? p.ratio.toFixed(2) + "× threshold" : "unknown, " + p.reason)).join("; ") + ".",
    when: EV.live.generatedAt, metrics: Object.fromEntries(ps.slice(0, 4).map(p => [p.type.toLowerCase().replace(/_(.)/g, (x, c) => c.toUpperCase()), p.state === "measured" ? p.ratio.toFixed(2) + "×" : "unknown"])),
    trigger: m ? { observed: m.ratio.toFixed(2), threshold: 1, unit: "× threshold", window: "latest observation" } : {}, evidence: a.url ? [{ label: "Item page", url: a.url }] : [], limits: ["A quiet check is not an all-clear: it only means this detector did not cross its threshold on the cached data."], derivedOnly: !a.redistributable, synthetic: false } });
});
const CAT_OF = { fx: "FX", metals: "Metals", energy: "Energy", positioning: "Agriculture", cards: "Cards", skins: "Skins", games: "Games", collectibles: "Collectibles" };
const UNI_OF = (s) => { const a = (EV.live.assets || []).find(x => x.id === s.asset || x.name === s.asset); return a ? a.universe : ({ fx: "fx-majors", metals: "gold", energy: "crude", cot: "cot", mtg: "mtg", cs2: "cs2-skins" })[s.source] || null; };
const EV_VI = { CRITICAL: 7, HIGH: 6, MEDIUM: 4, LOW: 3, INFO: 3, NONE: 2, UNKNOWN: 3 };
function evReport(set) { return { name: set === "live" ? "everything-live-derived.json" : "everything-synthetic.json", j: set === "live" ? EV.live : EV.synthetic }; }
const fmtM = (k, v) => [k.replace(/([A-Z])/g, " $1").replace(/^./, c => c.toUpperCase()).replace(" Pct", " %").replace(" Bp", " (bp)"), typeof v === "number" ? (Math.abs(v) >= 1000 ? num(v) : String(v)) : typeof v === "object" ? Object.entries(v).map(([a, b]) => a + " " + b).join(", ") : String(v)];
function assetTarget({ s, set }) {
  const r = evReport(set), a = (EV.live.assets || []).find(x => x.id === s.asset || x.name === s.asset) || {};
  const tr = s.trigger || {}, PR = (set === "live" ? EV.live.probes : EV.synthetic.probes) || [], mod = (PR.find(q => q.asset === s.asset || q.asset.startsWith(s.asset + "/")) || {}).module, peers = PR.filter(p => p.module === mod).slice(0, 14);
  const spark = a.spark || [], mx = Math.max(...spark, 0), mn = Math.min(...spark, mx);
  const events = spark.length ? spark.map((v, i) => [Math.round(i / Math.max(1, spark.length - 1) * 100), i === spark.length - 1 ? SEVC[s.severity] || "grey" : "green", (a.sparkLabel || "value") + " " + v + " · point " + (i + 1) + " of " + spark.length, null, (v - mn) / ((mx - mn) || 1)]) : [[100, SEVC[s.severity] || "grey", s.title.replace(/^\[SYNTHETIC\]\s*/, "")]];
  return {
    id: "asset:" + s.key + (set === "synthetic" ? ":syn" : ""), view: "asset", r, kind: (CAT_OF[s.category] || s.category) + (set === "synthetic" ? " · synthetic example" : " · cached real data"), title: s.name.replace(/\s*\[ETF proxy\]/, ""), evId: s.key, set, sig: s,
    feat: ({ fx: s.type === "FIX_CROSSCHECK" ? "fx.h10" : "fx.rates", metals: "cm.metals", energy: "cm.energy", cot: "cm.cot", mtg: s.type === "CROSS_VENUE_SPREAD" ? "tcg.spread" : "tcg.mtg", cs2: "more.cs2" })[s.source] || null,
    chips: [s.type.replace(/_/g, " ").toLowerCase(), s.basis, s.derivedOnly ? "derived signal only" : "official data", "observed " + (a.asOf || iso(s.when).slice(0, 10)), set === "live" ? "ingested " + iso(EV.live.generatedAt).slice(0, 10) + ", cached, not live" : "synthetic"],
    sev: s.severity, vi: EV_VI[s.severity] ?? 3, vc: SEVC[s.severity] || "grey", verdictNote: s.title.replace(/^\[SYNTHETIC\]\s*/, ""),
    score: { label: "Trigger", value: String(tr.observed ?? "—"), unit: tr.unit ? "/ " + tr.threshold + " " + tr.unit : "", note: "Threshold " + tr.threshold + " " + (tr.unit || "") + " over " + (tr.window || "the window") + ". Severity is distance past the threshold, not a probability." },
    metrics: Object.entries(s.metrics || {}).filter(([k]) => k !== "fxDate" && k !== "z").slice(0, 4).map(([k, v]) => fmtM(k, v)),
    rowsLabel: "Same module", rows: peers.map(p => ({ a: p.asset, full: p.asset, cls: p.state === "unknown" ? "unknown" : p.ratio >= 1 ? "flagged" : "measured", c: p.state === "unknown" ? "grey" : p.ratio >= 1 ? "amber" : "green", share: p.ratio == null ? "—" : p.ratio.toFixed(2) + "×", note: p.state === "unknown" ? "Unknown, not quiet: " + p.reason : p.type.replace(/_/g, " ").toLowerCase() + " at " + p.ratio.toFixed(2) + "× threshold" })),
    events, evidence: s.evidence || [], why: [s.title.replace(/^\[SYNTHETIC\]\s*/, ""), s.what].filter(Boolean), whyId: s.type, limits: (s.limits || []).concat(set === "synthetic" ? ["Synthetic example: invented item and prices, shown to demonstrate the detector."] : []),
  };
}
function assetTargets() { return EV_SIGS.map(assetTarget); }
window.GTB_EV = { EV, EV_SIGS, assetTargets };
function targets() { return of("token").map(tokenTarget).concat(of("wallet").map(walletTarget), of("replay").map(replayTarget), assetTargets()); }

/* ---------------- state ---------------- */
const VIEWS = [["home", "Home"], ["market", "Market"], ["limited", "Limited"], ["universe", "Universe"], ["anomalies", "Anomalies"], ["tcg", "Card Explorer"], ["token", "Token"], ["wallet", "Wallet"], ["replay", "Replay"], ["signals", "Signals"], ["threats", "Threats"], ["shill", "Shill net"], ["copy", "Copy net"], ["board", "Leaderboard"], ["prov", "Provenance"]];
const S = { view: "home", target: null, scanning: false, brel: 0, t0: 0, tab: 0, open: false, scrub: 62, withX: false, dl: 0, dc: 0, dh: 0, feed: [], pool: [], paused: false, notifAt: 0, sel: {}, sort: { col: "appearances", dir: -1 }, filter: "ALL", sigFilter: "all", lastAsk: null, uCat: "All", uStat: "all", uSel: null, aCat: "all", aSet: "both", aMode: "cached", aSrc: "all", aSev: "all", feat: null, uQ: "", uOpen: {}, limited: null };
window.GTB = { S, REPORTS, targets, addReport };
const three = () => window.GTB_STAGE || null;
// Wide = fixed full-height grid. If that leaves the stage too short for the result (short windows, zoom), fall back to the scrolling layout.
const shortKey = () => innerWidth + "x" + innerHeight + "|" + S.view + "|" + (S.target && S.target.id);
const wide = () => innerWidth >= 1180 && innerHeight >= 680 && S.tooShort !== shortKey();

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
const MKT = { fx: "FX", metals: "Metals", energy: "Energy", cot: "Agriculture", mtg: "Cards", cs2: "Skins", synthetic: "Synthetic", polymarket: "Prediction", kalshi: "Prediction", equities: "Stocks", options: "Stocks", treasury: "Rates", crypto: "Crypto", stablecoins: "Crypto", cross: "Cross-market", macro: "Macro", sec: "Filings", solana: "Crypto" };
function buildPool() {
  const out = [];
  of("signals").forEach(r => {
    (r.j.signals || []).forEach(s => out.push({ id: s.key, mkt: MKT[s.source] || s.source, subject: s.instrument || (s.subject || {}).name || s.source, text: String(s.title || "").replace(/^\[SYNTHETIC\]\s*/, ""), c: SEVC[s.severity] || "grey", sev: s.severity, ts: s.when, open: "signals", report: repLabel(r) }));
    Object.entries(r.j.sourceStatus || {}).forEach(([k, v]) => { if (v.state === "UNAVAILABLE") out.push({ id: "status:" + k, mkt: MKT[k] || k, subject: k, text: "No answer from source. Unknown, not quiet.", c: "grey", sev: null, ts: r.j.generatedAt, open: "signals", report: repLabel(r) }); });
  });
  of("threats").forEach(r => r.j.forEach(a => out.push({ id: a.id || a.key, mkt: "Crypto", subject: "$" + a.tokenSymbol, text: a.detail, c: SEVC[a.severity] || "grey", sev: a.severity, ts: a.timestamp, open: "threats", report: repLabel(r) })));
  of("watch").forEach(r => (r.j.alerts || []).slice(0, 12).forEach(a => out.push({ id: a.key || a.signature, mkt: "Crypto", subject: "$" + a.tokenSymbol, text: a.detail || a.type, c: SEVC[a.severity] || "grey", sev: a.severity, ts: a.timestamp, open: "token:" + a.tokenSymbol, report: repLabel(r) })));
  EV_SIGS.filter(x => x.set === "live" && !x.quiet).forEach(({ s }) => out.push({ id: s.key, mkt: MKT[s.source] || s.source, subject: s.name, text: s.title, c: SEVC[s.severity] || "grey", sev: s.severity, ts: s.when, open: "asset:" + s.key, report: "everything-live-derived.json" }));
  return out.sort((a, b) => (b.ts || 0) - (a.ts || 0));
}
S.pool = buildPool(); S.feed = S.pool.slice(0, 9); let poolI = 9;
const fTime = (f) => f.ts ? utc(new Date(f.ts < 1e12 ? f.ts * 1000 : f.ts)) : "--:--";
function openItem(o) { if (!o) return; if (o.startsWith("token:") || o.startsWith("asset:")) { const t = targets().find(x => x.id === o); if (t) return scan(t.id); } go(o); }
function renderFeed() {
  $("#feedN").textContent = S.feed.length;
  $("#feedList").innerHTML = S.feed.map(f => `<div class="fi${f.id === S.newId ? " new" : ""}"><button class="o" ${f.open ? `data-open="${esc(f.open)}"` : ""}><span style="width:8px;height:8px;margin-top:4px;background:${C[f.c]}"></span><span style="display:flex;flex-direction:column;gap:4px;min-width:0"><span class="up" style="display:flex;justify-content:space-between;gap:8px;font-size:10px;color:var(--m)"><span>${esc(f.mkt)} // ${esc(f.subject)}</span><span>${fTime(f)}</span></span><span style="font-size:12px;line-height:17px;overflow-wrap:anywhere">${esc(f.text)}</span></span></button><span style="padding-top:10px">${askBtn("Ask", ["Feed // " + f.mkt, f.subject, f.id, f.report, ["Market: " + f.mkt, "Event: " + f.text, "Severity: " + (f.sev || "no data"), "Time: " + iso(f.ts)]])}</span></div>`).join("") || `<div class="empty">No items in the loaded reports.</div>`;
  const tk = S.feed.slice(0, 10); const items = tk.concat(tk).map(f => `<button class="tk" tabindex="-1" ${f.open ? `data-open="${esc(f.open)}"` : ""}><span class="sq" style="background:${C[f.c]}"></span><span class="up dim">${esc(f.mkt)} // ${esc(f.subject)}</span><span>${esc(f.text.length > 90 ? f.text.slice(0, 88) + "…" : f.text)}</span><span style="color:var(--b)">${fTime(f)}</span></button>`).join("");
  const tr = $("#track"); if (tr.dataset.sig !== tk.map(f => f.id).join()) { tr.innerHTML = items; tr.dataset.sig = tk.map(f => f.id).join(); tr.style.setProperty("--dur", Math.max(30, tk.length * 7) + "s"); }
}
document.addEventListener("click", (e) => { const b = e.target.closest("[data-open]"); if (b && (b.closest("#feed") || b.closest("#ticker"))) openItem(b.dataset.open); });
function pushFeed() { if (poolI >= S.pool.length) return; const it = S.pool[poolI++]; S.feed = [it].concat(S.feed).slice(0, 40); S.newId = it.id; renderFeed(); maybeNotify(it); }
function maybeNotify(it) {
  // Never over navigation, search or an open menu: on narrow screens only the feed counter changes; on desktop it sits under the nav bar.
  if (S.view !== "home" || $("#root").className !== "wide" || innerWidth < 1024 || NAV.open || !$("#mobMenu").hidden || /INPUT|TEXTAREA/.test((document.activeElement || {}).tagName || "")) { $("#feedBtn").classList.add("bump"); setTimeout(() => $("#feedBtn").classList.remove("bump"), 900); return; }
  if ($("#feed").classList.contains("on") || !["red", "amber"].includes(it.c)) return; const now = Date.now(); if (now - S.notifAt < 9000) return; S.notifAt = now;
  const n = $("#notif"); n.hidden = false; n.style.top = Math.round($("#views").getBoundingClientRect().bottom - $("#root").getBoundingClientRect().top + 8) + "px";
  n.innerHTML = `<div class="up" style="display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:10px"><span style="color:var(--y);display:flex;align-items:center;gap:8px"><span class="blinkdot"></span>${it.replay === false ? "New in this session" : "Replayed from loaded reports"}</span><span class="dim">observed ${fTime(it)} UTC</span></div><div style="display:grid;grid-template-columns:8px minmax(0,1fr);gap:10px"><span style="width:8px;height:8px;background:${C[it.c]};margin-top:5px"></span><span style="display:flex;flex-direction:column;gap:2px"><span class="up dim" style="font-size:10px">${esc(it.mkt)} // ${esc(it.subject)}</span><span style="font-size:13px;line-height:19px;overflow-wrap:anywhere">${esc(it.text)}</span></span></div><div style="display:flex;justify-content:flex-end;gap:6px"><button class="btn" id="nfX">Dismiss</button><button class="btn y" id="nfGo" style="border-color:var(--y)">${it.open && it.open.startsWith("token:") ? "Scan it" : "Open feed"}</button></div>`;
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
/* ---------------- search: instrument-aware routing ---------------- */
const ISO = "USD EUR JPY GBP CHF CAD AUD NZD CNY HKD SGD SEK NOK DKK PLN CZK HUF TRY ZAR MXN BRL INR KRW IDR THB MYR PHP ILS ISK RON BGN".split(" ");
const COMMOD = [[/^(gold|xau|gld|iau)$/, "cm.metals", "GLD"], [/^(silver|xag|slv)$/, "cm.metals", "SLV"], [/^(platinum|xpt|pplt)$/, "cm.metals", "PPLT"], [/^(palladium|xpd|pall)$/, "cm.metals", "PALL"], [/^(oil|crude|wti|cl)$/, "cm.energy", "DCOILWTICO"], [/^brent$/, "cm.energy", "DCOILBRENTEU"], [/^(natgas|natural gas|henry hub|ng)$/, "cm.energy", "DHHNGSP"], [/^(corn|wheat|soy|soybeans?|coffee|cocoa)$/, "cm.cot", null]];
// classify(q) -> [{label, kind, id, domain}] best first. Ids: scan target ids, "feat:<id>", "view:<v>", or "lim:<json>" (limited state).
function classify(raw) {
  const q = raw.trim(), lq = q.toLowerCase().replace(/^\$/, ""), out = [], T = targets();
  if (!q) return out;
  const lim = (title, kind, headTxt, text, feat) => ({ label: title, kind: kind + " · no data loaded", id: "lim:" + JSON.stringify({ title, kind, head: headTxt, text, feat }), domain: kind });
  const assetHit = (pred) => T.filter(t => t.view === "asset" && t.set === "live" && pred(t));
  // currency pair
  const fx = q.toUpperCase().replace(/[\s\-_]/g, "").match(/^([A-Z]{3})\/?([A-Z]{3})$/);
  if (fx && ISO.includes(fx[1]) && ISO.includes(fx[2])) {
    const p = fx[1] + "/" + fx[2], inv = fx[2] + "/" + fx[1], h = assetHit(t => t.sig.asset === p || t.sig.asset === inv);
    if (h.length) out.push({ label: h[0].title, kind: "FX pair · cached ECB rate", id: h[0].id, domain: "FX" });
    else out.push(lim(p, "FX pair", "Pair not in the cached ECB set", "Cached ECB reference rates are quoted against EUR (" + (EV.live.assets || []).filter(a => a.universe === "fx-majors").length + " pairs). " + p + " is not one of them; a cross rate would be derived, not observed.", "fx.rates"));
  }
  COMMOD.forEach(([re, feat, id]) => { if (re.test(lq)) { const h = id ? assetHit(t => t.sig.asset === id) : assetHit(t => (t.sig.asset || "").toLowerCase().includes(lq.replace(/s$/, ""))); h.length ? out.push({ label: h[0].title, kind: catName("commodities") + " · " + REG.byId[feat].name, id: h[0].id, domain: "Commodities" }) : out.push({ label: REG.byId[feat].name, kind: catName("commodities"), id: "feat:" + feat, domain: "Commodities" }); } });
  // MTG cards and CS2 items (cached, derived only)
  if (lq.length >= 3) assetHit(t => (t.sig.source === "mtg" || t.sig.source === "cs2") && t.sig.asset.toLowerCase().includes(lq)).slice(0, 4).forEach(t => out.push({ label: t.title, kind: t.sig.source === "mtg" ? "TCG · MTG card (derived only)" : "CS2 item · experimental", id: t.id, domain: t.sig.source === "mtg" ? "TCGs" : "More" }));
  // Card Explorer: printings in the local artwork cache (or tracked printings when unsynced)
  if (lq.length >= 3 && TCGX) TCGX.tcgData().C.groups.filter(g => (g.name || "").toLowerCase().includes(lq)).slice(0, 3).forEach(g => out.push({ label: g.name, kind: "TCGs · Card Explorer · " + g.printings.length + " printings", id: "card:" + g.printings[0].key, domain: "TCGs" }));
  // prediction market questions or venues
  if (/\b(will|polymarket|kalshi|odds|election|fed cut|by (dec|jan|end))\b|\?$/.test(lq)) {
    const rep = of("signals")[0], m = rep && (rep.j.signals || []).filter(s => ["polymarket", "kalshi"].includes(s.source) && String(s.title).toLowerCase().includes(lq.replace(/\?$/, "").slice(0, 24)));
    out.push({ label: m && m.length ? "Prediction market match" : "Prediction Markets: Odds Moves", kind: "Prediction market" + (rep && isSynRep(rep) ? " · example data" : ""), id: "feat:pm.odds", domain: "Prediction" });
  }
  // tickers: crypto token targets vs equity instruments in the loaded signals report
  if (/^\$?[a-z]{1,6}$/i.test(q)) {
    const sym = lq.toUpperCase(), tok = T.filter(t => t.view === "token" && t.title.replace("$", "").toUpperCase() === sym);
    const rep = of("signals")[0], eq = rep ? (rep.j.signals || []).filter(s => ["equities", "options"].includes(s.source) && String(s.instrument || "").toUpperCase().endsWith(":" + sym)) : [];
    const cr = rep ? (rep.j.signals || []).filter(s => ["crypto", "stablecoins"].includes(s.source) && String(s.instrument || "").toUpperCase().endsWith(":" + sym)) : [];
    // assessed but quiet: the ticker is in the fetched equities universe even with no finding
    const inEq = rep && !eq.length && (((rep.j.sourceStatus || {}).equities || {}).coverage || {}).observedInstruments; if (inEq && inEq.includes(sym)) eq.push({ source: "equities" });
    tok.forEach(t => out.push({ label: t.title, kind: "Crypto · Token Scanner", id: t.id, domain: "Crypto" }));
    if (eq.length) out.push({ label: sym, kind: "Stocks & Options · " + (eq[0].source === "options" ? "Options Activity" : "Equity Signals"), id: "feat:" + (eq[0].source === "options" ? "eq.options" : "eq.signals"), domain: "Stocks" });
    if (cr.length) out.push({ label: sym, kind: "Crypto · Spot & Stablecoin Signals", id: "feat:crypto.market", domain: "Crypto" });
    if (!tok.length && !eq.length && !cr.length && !out.length && q.startsWith("$") === false && /^[A-Z]{1,5}$/.test(q)) out.push(lim(sym, "Ticker", "Ticker not in the loaded reports", sym + " is not in the loaded equities universe or the crypto reports. Nothing is scanned through the wrong tool.", "eq.signals"));
  }
  // Solana-style base58 address or mint
  if (/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(q)) { const h = T.filter(t => (t.evId || "") === q || (t.r && JSON.stringify(t.r.j).includes(q))).slice(0, 2); h.forEach(t => out.push({ label: t.title, kind: t.kind, id: t.id, domain: "Crypto" })); if (!h.length) out.push(lim(short(q), "Solana address", "Address not in the loaded reports", "This looks like a Solana mint or wallet. It is not in any loaded report; run token-scan or wallet-scan locally and open the JSON.", "crypto.token")); }
  return out;
}
function suggestions(qRaw) {
  const q = qRaw.trim().toLowerCase().replace("$", "");
  const routed = classify(qRaw);
  const feats = REG.F.filter(featVisible).map(f => ({ label: f.name, kind: catName(f.cat) + " · " + DATA_TAG[dataState(f)], id: "feat:" + f.id, hay: (f.name + " " + catName(f.cat) + " " + (f.filters || []).join(" ")).toLowerCase() }));
  const all = targets().map(t => ({ label: t.title, kind: t.kind, id: t.id, hay: (t.title + " " + t.kind + " " + t.evId).toLowerCase().replace("$", "") })).concat(feats, [{ label: "Anomalies", kind: "Every market, one feed", id: "view:anomalies", hay: "anomalies every market feed" }]);
  if (!q) return targets().filter(t => t.view !== "asset").slice(0, 3).map(t => ({ label: t.title, kind: t.kind, id: t.id })).concat(feats.filter(f => ["feat:pm.odds", "feat:fx.rates", "feat:tcg.mtg"].includes(f.id)));
  const ids = new Set(routed.map(r => r.id));
  return routed.concat(all.filter(s => !ids.has(s.id) && s.hay.includes(q))).slice(0, 9);
}
function wireSearch(inp, box) {
  let sel = 0;
  const draw = () => { const sg = suggestions(inp.value); box.hidden = document.activeElement !== inp || !sg.length; box.innerHTML = sg.map((g, i) => `<button data-id="${esc(g.id)}" class="${i === sel ? "on" : ""}"><span>${esc(g.label)}</span><span class="k">${esc(g.kind)}</span></button>`).join(""); return sg; };
  inp.addEventListener("input", () => { sel = 0; draw(); }); inp.addEventListener("focus", draw); inp.addEventListener("blur", () => setTimeout(() => box.hidden = true, 150));
  box.addEventListener("mousedown", (e) => { const b = e.target.closest("button"); if (b) { e.preventDefault(); pickId(b.dataset.id); } });
  inp.addEventListener("keydown", (e) => { const sg = suggestions(inp.value); if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(sg.length - 1, sel + 1); draw(); } if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); draw(); } if (e.key === "Enter") { e.preventDefault(); submit(inp, sel); } if (e.key === "Escape") inp.blur(); });
}
function pickId(id) { $("#q").value = ""; $("#hq").value = ""; document.activeElement && document.activeElement.blur(); if (id.startsWith("view:")) go(id.slice(5)); else if (id.startsWith("card:")) { if (TCGX) { TCGX.TCG.sel = id.slice(5); TCGX.TCG.face = 0; } goFeat("tcg.explorer"); } else if (id.startsWith("feat:")) goFeat(id.slice(5)); else if (id.startsWith("lim:")) { S.limited = JSON.parse(id.slice(4)); S.feat = null; S.view = "limited"; history.replaceState(null, "", "#limited"); render(); } else scan(id); }
function submit(inp, sel = 0) { const sg = suggestions(inp.value); const doms = [...new Set(classify(inp.value).map(x => x.domain))]; if (sel === 0 && doms.length > 1 && !inp.dataset.chose) { inp.dataset.chose = "1"; inp.dispatchEvent(new Event("focus")); return flash("Matches " + doms.join(" and ") + ". Pick one"); } delete inp.dataset.chose; if (inp.value.trim() && sg[sel]) pickId(sg[sel].id); else if (!inp.value.trim()) pickId(targets()[0].id); else flash('Nothing loaded matches "' + inp.value.trim().slice(0, 40) + '"'); }
wireSearch($("#q"), $("#sugg")); wireSearch($("#hq"), $("#hsugg"));
$("#scanBtn").onclick = () => submit($("#q"));
addEventListener("keydown", (e) => {
  const typing = /INPUT|TEXTAREA/.test(document.activeElement.tagName);
  if (((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") || (e.key === "/" && !typing)) { e.preventDefault(); const i = S.view === "home" ? $("#q") : $("#hq"); i.focus(); }
  if (e.key === "Escape") { $("#fbk").classList.remove("on"); if ($("#feed").classList.contains("on")) toggleFeed(false); }
});

/* ---------------- navigation ---------------- */
/* ---------------- asset-first navigation (driven by ui/registry.js) ---------------- */
const REG = window.GTB_REGISTRY || { CATS: [], F: [], byId: {}, UNI_TOOL: {} };
const isSynRep = (r) => !!(r && r.j && (r.j.synthetic === true || r.j.example === true || /SYN|EXAMPLE|sample/i.test(r.name)));
const UNI_MOD = { "fx-majors": "fx", "fx-h10": "fx", gold: "metals", silver: "metals", pgm: "metals", crude: "energy", natgas: "energy", cot: "cot", grains: "cot", softs: "cot", mtg: "mtg", "cs2-skins": "cs2" };
const featAssets = (f) => (EV.live.assets || []).filter(a => (f.route.uni || []).includes(a.universe));
const featProbes = (f) => { const names = new Set(featAssets(f).flatMap(a => [a.id, a.name])); const mods = new Set((f.route.uni || []).map(u => UNI_MOD[u])); return (EV.live.probes || []).filter(p => (names.has(p.asset) || (mods.has(p.module) && p.type === "FIX_CROSSCHECK" && (f.route.types || []).includes("FIX_CROSSCHECK"))) && (!f.route.types || f.route.types.includes(p.type))); };
// Data state is resolved from what is actually loaded, never from the registry's hopes.
function dataState(f) {
  const r = f.route;
  if (r.view === "universe") return "cached";
  if (r.view === "tcg") return window.GTB_TCG_CACHE ? "cached" : "unavailable";
  if (r.view === "market") { const ps = featProbes(f); if (!ps.length && !featAssets(f).length) return "unavailable"; if (ps.length && ps.every(p => p.state === "unknown")) return "insufficient"; return "cached"; }
  if (r.view === "signals") { const rep = of("signals")[0]; if (!rep) return "unavailable"; const st = rep.j.sourceStatus || {}; const srcs = (r.src || []).filter(k => st[k]); if (srcs.length && srcs.every(k => st[k].state !== "HEALTHY")) return "unavailable"; return isSynRep(rep) ? "synthetic" : "cached"; }
  const reps = (f.kinds || []).flatMap(k => of(k)); if (!reps.length) return "unavailable"; return reps.every(isSynRep) ? "synthetic" : "cached";
}
const DATA_LBL = { cached: "Cached real data", synthetic: "Synthetic examples", unavailable: "Unavailable", insufficient: "Insufficient history" };
const DATA_TAG = { cached: "cached", synthetic: "examples", unavailable: "unavailable", insufficient: "insufficient" };
const RIGHTS_LBL = { verified: "Terms read for local research use", unverified: "Rights unverified", restricted: "Restricted: derived numbers only" };
const featVisible = (f) => f.impl !== "planned";
const catOfFeat = (id) => (REG.byId[id] || {}).cat;
function navHTML() {
  const item = (f) => { const d = dataState(f); return `<button class="ni" role="menuitem" data-feat="${esc(f.id)}"><span class="nn">${esc(f.name)}</span><span class="ns">${f.experimental ? `<span class="tg x">experimental</span>` : f.impl === "partial" ? `<span class="tg">partial</span>` : ""}<span class="tg d-${d}">${DATA_TAG[d]}</span></span></button>`; };
  const cats = REG.CATS.map(c => { const fs = REG.F.filter(f => f.cat === c.id && featVisible(f)); return fs.length ? { c, fs } : null; }).filter(Boolean);
  return `<button class="nt" data-view="home">Home</button><button class="nt mk" id="mktBtn" aria-expanded="false" aria-controls="mobMenu">Markets<span class="car" aria-hidden="true">▾</span></button>`
    + cats.map(({ c, fs }) => `<div class="ng"><button class="nt cat" id="nt-${c.id}" data-cat="${c.id}" aria-expanded="false" aria-controls="nm-${c.id}" aria-haspopup="true">${esc(c.name)}<span class="car" aria-hidden="true">▾</span></button><div class="navm" id="nm-${c.id}" role="menu" aria-labelledby="nt-${c.id}" hidden>${fs.map(item).join("")}</div></div>`).join("")
    + `<button class="nt an" data-view="anomalies"><span class="sqy" aria-hidden="true"></span>Anomalies</button>`
    + `<div class="mob" id="mobMenu" hidden>${cats.map(({ c, fs }) => `<div class="mgw"><button class="mg" id="mg-${c.id}" aria-expanded="false" aria-controls="mgi-${c.id}" data-mcat="${c.id}">${esc(c.name)}<span class="car" aria-hidden="true">▾</span></button><div class="mgi" id="mgi-${c.id}" hidden>${fs.map(item).join("")}</div></div>`).join("")}</div>`;
}
const NAV = { open: null, tOpen: 0, tClose: 0 };
function menuPlace(id) {
  const t = $("#nt-" + id), m = $("#nm-" + id); if (!t || !m) return;
  const r = t.getBoundingClientRect(), nb = $("#views").getBoundingClientRect(); m.style.top = Math.round(nb.bottom) + "px";
  m.style.left = "0px"; const w = m.offsetWidth; m.style.left = Math.round(Math.max(8, Math.min(r.left, innerWidth - w - 8))) + "px";
}
function openMenu(id, focusFirst) {
  clearTimeout(NAV.tOpen); clearTimeout(NAV.tClose);
  if (NAV.open && NAV.open !== id) closeMenu(false);
  const t = $("#nt-" + id), m = $("#nm-" + id); if (!t || !m) return;
  if ($("#feed").classList.contains("on")) toggleFeed(false); m.hidden = false; t.setAttribute("aria-expanded", "true"); NAV.open = id; menuPlace(id); $("#notif").classList.remove("on");
  if (focusFirst) { const f = $(".ni", m); f && f.focus(); }
}
function closeMenu(refocus) {
  clearTimeout(NAV.tOpen); clearTimeout(NAV.tClose); const id = NAV.open; if (!id) return;
  const t = $("#nt-" + id), m = $("#nm-" + id); if (m) m.hidden = true; if (t) t.setAttribute("aria-expanded", "false"); NAV.open = null; if (refocus && t) t.focus();
}
function toggleMob(on) { const b = $("#mktBtn"), m = $("#mobMenu"); on = on ?? m.hidden; m.hidden = !on; b.setAttribute("aria-expanded", on); if (on) { if ($("#feed").classList.contains("on")) toggleFeed(false); m.style.top = Math.round($("#views").getBoundingClientRect().bottom) + "px"; $("#notif").classList.remove("on"); } }
function wireNav() {
  const V = $("#views"); V.innerHTML = navHTML();
  V.addEventListener("click", (e) => {
    const f = e.target.closest("[data-feat]"); if (f) { closeMenu(false); toggleMob(false); return goFeat(f.dataset.feat); }
    const v = e.target.closest("[data-view]"); if (v) { closeMenu(false); toggleMob(false); return go(v.dataset.view); }
    const c = e.target.closest("[data-cat]"); if (c) { NAV.open === c.dataset.cat ? closeMenu(false) : openMenu(c.dataset.cat, e.detail === 0); return; }
    const g = e.target.closest("[data-mcat]"); if (g) { const box = $("#mgi-" + g.dataset.mcat), on = box.hidden; $$(".mgi", V).forEach(x => x.hidden = true); $$(".mg", V).forEach(x => x.setAttribute("aria-expanded", "false")); box.hidden = !on; g.setAttribute("aria-expanded", on); return; }
    if (e.target.closest("#mktBtn")) toggleMob();
  });
  $$(".ng", V).forEach(g => {
    const id = $("[data-cat]", g).dataset.cat;
    g.addEventListener("pointerenter", (e) => { if (e.pointerType !== "mouse") return; clearTimeout(NAV.tClose); if (NAV.open === id) return; clearTimeout(NAV.tOpen); NAV.tOpen = setTimeout(() => openMenu(id), NAV.open ? 60 : 150); });
    g.addEventListener("pointerleave", (e) => { if (e.pointerType !== "mouse") return; clearTimeout(NAV.tOpen); NAV.tClose = setTimeout(() => { if (NAV.open === id) closeMenu(false); }, 280); });
    g.addEventListener("keydown", (e) => {
      const items = $$(".ni", g), i = items.indexOf(document.activeElement);
      if (e.key === "ArrowDown") { e.preventDefault(); if (NAV.open !== id) openMenu(id, true); else (items[i + 1] || items[0]).focus(); }
      if (e.key === "ArrowUp") { e.preventDefault(); if (i >= 0) (items[i - 1] || items[items.length - 1]).focus(); }
      if (e.key === "Escape" && NAV.open === id) { e.stopPropagation(); closeMenu(true); }
    });
    g.addEventListener("focusout", (e) => { if (!g.contains(e.relatedTarget) && NAV.open === id && e.relatedTarget) closeMenu(false); });
  });
  document.addEventListener("pointerdown", (e) => { if (NAV.open && !e.target.closest(".ng")) closeMenu(false); if (!$("#mobMenu").hidden && !e.target.closest("#mobMenu,#mktBtn")) toggleMob(false); });
  addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#mobMenu").hidden) { toggleMob(false); $("#mktBtn").focus(); } });
  addEventListener("resize", () => { if (NAV.open) menuPlace(NAV.open); });
  addEventListener("scroll", () => { if (NAV.open) menuPlace(NAV.open); if (!$("#mobMenu").hidden) $("#mobMenu").style.top = Math.round($("#views").getBoundingClientRect().bottom) + "px"; }, { passive: true });
}
function navState() {
  const fc = S.feat ? catOfFeat(S.feat) : S.view === "tcg" ? "tcg" : (S.view === "token" || S.view === "wallet" || S.view === "replay" ? "crypto" : S.view === "asset" && S.target && S.target.feat ? catOfFeat(S.target.feat) : null);
  $$("#views [data-view]").forEach(b => b.dataset.view === S.view && !S.feat ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
  $$("#views [data-cat]").forEach(b => b.classList.toggle("act", b.dataset.cat === fc));
  $("#mktBtn").classList.toggle("act", !!fc);
  const curF = S.feat || (S.view === "asset" && S.target && S.target.feat) || ({ token: "crypto.token", wallet: "crypto.wallet", replay: "crypto.replay", shill: "crypto.shill", copy: "crypto.copy", threats: "crypto.threats", board: "crypto.board", prov: "more.prov", universe: "more.all", tcg: "tcg.explorer" })[S.view];
  $$("#views [data-feat]").forEach(b => b.dataset.feat === curF ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
}
function goFeat(id, push = true) {
  const f = REG.byId[id]; if (!f) return go("home");
  const r = f.route; closeMenu(false); toggleMob(false);
  if (["token", "wallet", "replay"].includes(r.view)) { S.feat = null; return go(r.view); }
  S.feat = r.view === "signals" || r.view === "market" ? id : null; S.sigFilter = "all"; S.focus = null;
  S.view = r.view; if (push) history.replaceState(null, "", "#f/" + id);
  if (three()) three().setMode("result");
  render(); scrollTo(0, 0);
}
wireNav();
$("#logo").onclick = () => go("home");
function go(v) {
  S.feat = null; closeMenu(false);
  if (v === "token" || v === "wallet" || v === "replay" || v === "asset") { const t = targets().find(x => x.view === v && (!S.target || S.target.view !== v ? true : x.id === S.target.id)); if (t) return scan(t.id, true); }
  S.view = v; history.replaceState(null, "", "#" + v); if (three()) { three().setMode(v === "home" ? "home" : "result"); three().spin && v !== "home" && three().spin(); }
  render();
}
window.GTB.go = go; window.GTB.goFeat = (id) => goFeat(id);
// Card Explorer -> that card's existing research data (MTG market tool focused on the tracked printing's instrument).
window.GTB.analyzeCard = (asset) => { goFeat("tcg.mtg"); S.focus = asset; render(); };
const TCGX = window.GTB_TCG_MAKE ? window.GTB_TCG_MAKE({ $, $$, esc, head, askBtn, iso, render, S, EV, EV_SIGS, REG }) : null;
addEventListener("hashchange", () => { const h2 = decU(location.hash.slice(1)); if (h2.startsWith("f/") && h2.slice(2) !== S.feat) goFeat(h2.slice(2), false); });

/* ---------------- scan + kinetic result sequence ---------------- */
let scanT;
function scan(id, quiet) {
  const t = targets().find(x => x.id === id); if (!t) return flash("Nothing loaded matches that");
  S.view = t.view; S.feat = null; S.target = t; S.tab = 0; S.open = false; S.brel = 0; S.dl = 0; S.dc = 0; S.dh = 0; S.scrub = 62; S._rv = -1; S._slam = false;
  { const vb = $("#vdBox"), rw = $("#resWord"); vb.dataset.landed = "0"; [vb, rw].forEach(e => { e.style.transition = "none"; e.style.opacity = 0; }); void vb.offsetWidth; requestAnimationFrame(() => requestAnimationFrame(() => { vb.style.transition = ""; })); } // a re-scan never animates the old verdict back out across the TL;DR
  history.replaceState(null, "", "#" + t.view + "/" + encU(t.title.replace("$", "")) + (t.set ? "|" + t.set : ""));
  if (three()) { three().setMode("result"); three().set && three().set(); }
  clearTimeout(scanT);
  if (reduced()) { S.scanning = false; S.t0 = performance.now() - 20000; render(); return; }
  S.scanning = true; S.t0 = 0; render();
  scanT = setTimeout(() => { S.scanning = false; S.t0 = performance.now(); S._rv = -1; if (three()) three().spin(); render(); }, quiet ? 700 : 1600);
}
window.GTB.scan = scan;
/* test/automation hook: jump the current result sequence to its end state */
window.GTB.finish = () => { clearTimeout(scanT); S.scanning = false; S.t0 = performance.now() - 20000; S._rv = -1; render(); };
const boardRows = (t) => [[t.score.label, t.score.value + (t.score.unit && t.score.unit.startsWith("/") ? " " + t.score.unit : ""), null]].concat(t.metrics).slice(0, 5);
function reveal(t, B) { const n = boardRows(t).length; const raw = Math.floor(Math.max(0, B - 900) / 420); const land = 900 + n * 420 + 1700; const r = raw > n ? (B >= land ? n + 1 : n) : raw; return { r, n, land }; }
function dlgLines(t) {
  if (S.view === "home" || !t) return ["Hey. I'm Grok Bot.", "Drop a token, wallet or ticker and I'll read the loaded reports for you.", "I show the evidence and where it stops. Signals, not predictions."];
  const unit = t.score.unit && t.score.unit.startsWith("/") ? " " + t.score.unit : "";
  return ["TL;DR on " + t.title + ": " + HYPE[t.vi][0] + ".", t.verdictNote, t.score.label + ": " + t.score.value + unit + ". " + t.score.note, t.metrics.slice(0, 3).map(([k, v]) => k + " " + v).join(", ") + ".", t.why[1] || t.why[0] || "No further findings in this report.", "Signals, not predictions. Ask me about any row."].filter(Boolean);
}
function shake(px) { if (reduced()) return; const el = $("#stageWrap"); if (!el.animate) return; const k = []; for (let i = 0; i < 8; i++) { const a = px * (1 - i / 8); k.push({ transform: "translate(" + ((i % 2 ? 1 : -1) * a).toFixed(1) + "px," + ((i % 3 - 1) * a * 0.6).toFixed(1) + "px)" }); } k.push({ transform: "none" }); el.animate(k, { duration: 320, easing: "linear" }); }
/* ---------------- stage layout: everything is sized from the stage box so nothing clips ---------------- */
function longest(a) { return a.reduce((m, x) => x.length > m.length ? x : m, ""); }
function layoutStage(t) {
  const W = $("#stageWrap"); if (W.hidden) return;
  const home = S.view === "home" || !t, sw = W.clientWidth; if (!sw) return;
  if ($("#root").className === "wide" && W.clientHeight < 440) { S.tooShort = shortKey(); $("#root").className = "narrow"; }
  const narrow = $("#root").className !== "wide";
  const sh0 = narrow ? Math.max(380, Math.min(560, Math.round(innerHeight * 0.78))) : W.clientHeight;
  const key = [S.view, t && t.id, sw, sh0, innerHeight, document.fonts ? document.fonts.status : ""].join("|");
  if (S.L && S.L.key === key) { window.GTB_BOX = S.L.box; return; }
  const side = sw >= 640, dlg = $("#dlg"), P = 16;
  // TL;DR box: reserve the height of the longest line so typing never moves anything
  const lines = dlgLines(t);
  const dlgH = (dw) => { const inner = Math.max(80, dw - 64), cpl = Math.max(8, Math.floor(inner / 8.4)); const n = Math.max(2, Math.max(...lines.map(l => Math.ceil(l.length / cpl) + (l.length > cpl ? 1 : 0)))); return { box: n * 22 + 38, all: n * 22 + 38 + 22 }; };
  const L = { key, side, narrow };
  if (home) {
    const hm = $("#home"), h1 = $("#homeH1"); const hw = side ? Math.min(520, Math.round(sw * 0.48)) : sw - 40;
    const dw = side ? sw - (32 + hw) - 24 - P : sw - 2 * P, dh = dlgH(dw);
    Object.assign(hm.style, { left: side ? "32px" : "20px", width: hw + "px", transform: "none" });
    let hs = Math.max(40, Math.min(120, Math.floor(hw * 0.23), side ? Math.floor((sh0 - 230) * 0.5) : 72));
    h1.style.fontSize = hs + "px"; let hh = hm.offsetHeight;
    while (side && hh > sh0 - 2 * P && hs > 40) { hs -= 6; h1.style.fontSize = hs + "px"; hh = hm.offsetHeight; }
    const req = side ? Math.max(hh + 2 * P, dh.all + 150 + 3 * P) : 20 + hh + 12 + 150 + 12 + dh.all + P;
    const sh = narrow ? Math.max(sh0, req) : sh0;
    hm.style.top = (side ? Math.max(P, Math.round((sh - hh) / 2)) : 20) + "px";
    Object.assign(dlg.style, { left: (side ? 32 + hw + 24 : P) + "px", right: P + "px" }); $("#dlg .box").style.minHeight = dh.box + "px";
    const dTop = sh - P - dh.all;
    L.box = side ? { x: 32 + hw + 24, y: P, w: sw - (32 + hw + 24) - P, h: dTop - 12 - P } : { x: P, y: 20 + hh + 12, w: sw - 2 * P, h: dTop - 12 - (20 + hh + 12) };
    L.sh = sh;
  } else {
    const st = $("#stats"), rows = boardRows(t), box = $("#srows");
    if (box.dataset.t !== t.id) { box.dataset.t = t.id; box.innerHTML = rows.map(() => `<div class="srow"><span class="k disp"></span><span class="v disp"></span></div>`).join(""); }
    // measure with the final values and the longest verdict phrase the slot-roll can show
    $$(".srow", box).forEach((el, i) => { el.children[0].textContent = rows[i][0]; el.children[1].textContent = rows[i][1]; });
    const vt = $("#vdTx"), vj = $("#vdJp"), keepT = vt.textContent, keepJ = vj.style.display;
    vt.textContent = longest(HYPE.map(h => h[0])); vj.textContent = "危険"; vj.style.display = "inline"; vt.style.whiteSpace = "nowrap";
    const colW = side ? Math.round(Math.min(480, Math.max(250, sw * 0.44))) : sw - 2 * P - 8;
    const setF = (f) => { $$(".srow .k", box).forEach(e => e.style.fontSize = f + "px"); $$(".srow .v", box).forEach(e => e.style.fontSize = Math.round(f * 1.3) + "px"); $("#vdLab").style.fontSize = f + "px"; $("#vdBox").style.fontSize = Math.round(f * 1.5) + "px"; vj.style.fontSize = Math.round(f * 1.12) + "px"; };
    st.style.width = "max-content"; st.style.transform = "none";
    const dwSide = sw - colW - 2 * P - 24, dh = dlgH(side ? dwSide : sw - 2 * P);
    const fits = (f) => { setF(f); const w = st.offsetWidth, h = st.offsetHeight; return w + h * 0.07 <= colW && (!side || h + w * 0.07 <= sh0 - 2 * P); };
    let f = side ? 30 : 24; while (f > 11 && !fits(f)) f -= 1; if (f <= 11) setF(f);
    vt.textContent = keepT; vj.style.display = keepJ; vt.style.whiteSpace = "";
    st.style.width = colW + "px"; st.style.transform = ""; const sH = st.offsetHeight;
    const rs = side ? Math.round(Math.max(34, Math.min(80, (sw - colW - 3 * P) * 0.26, sh0 * 0.15))) : Math.round(Math.max(34, Math.min(56, sw * 0.13)));
    const rsp = $("#resSpan"); rsp.style.fontSize = rs + "px"; const rw = $("#resWord"), w0 = rw.offsetWidth, h0 = rw.offsetHeight;
    const rTop = P + Math.ceil(w0 * 0.14) - Math.round(h0 * 0.1); rw.style.left = (P + 8) + "px"; rw.style.top = rTop + "px"; const rBot = rTop + h0 + 4;
    let sh, sTop;
    if (side) { const req = Math.max(sH + colW * 0.07 + 2 * P, rBot + 150 + dh.all + 2 * P); sh = narrow ? Math.max(sh0, Math.ceil(req)) : sh0; sTop = Math.max(P + colW * 0.035, (sh - sH) / 2); }
    else { sTop = rBot + 8 + colW * 0.035; const sBot = sTop + sH + colW * 0.035; const req = sBot + 12 + 150 + 12 + dh.all + P; sh = narrow ? Math.max(sh0, Math.ceil(req)) : sh0; }
    Object.assign(st.style, { top: Math.round(sTop) + "px", right: P + "px" });
    Object.assign(dlg.style, { left: P + "px", right: (side ? colW + P + 24 : P) + "px" }); $("#dlg .box").style.minHeight = dh.box + "px";
    const dTop = sh - P - dh.all;
    L.box = side ? { x: P, y: rBot + 8, w: sw - colW - 2 * P - 24, h: dTop - 12 - (rBot + 8) } : { x: P, y: sTop + sH + colW * 0.035 + 12, w: sw - 2 * P, h: dTop - 12 - (sTop + sH + colW * 0.035 + 12) };
    L.sh = sh; L.f = f;
  }
  if (narrow) W.style.height = L.sh + "px"; else W.style.height = "";
  L.box.sw = sw; L.box.sh = L.sh; S.L = L; window.GTB_BOX = L.box;
  W.dataset.layout = (L.side ? "side" : "stack") + (L.f ? " f" + L.f : "");
}
function frame() {
  const t = S.target, stageView = ["home", "token", "wallet", "replay", "asset"].includes(S.view);
  if (stageView) {
    const B = S.view === "home" || S.scanning || !S.t0 ? 0 : performance.now() - S.t0; S.brel = B;
    layoutStage(t);
    if (S.view !== "home" && t) seqFrame(t, B);
    typeFrame(t, B);
  }
  if (!reduced() && !S.paused && Date.now() - (S.lastPush || 0) > 3800) { S.lastPush = Date.now(); if (S.lastPushInit) pushFeed(); S.lastPushInit = true; }
  requestAnimationFrame(frame);
}
// Verdict entry scale: v6 slams in from 2.4x, clamped so the scaled box never crosses the stage edge (narrow screens).
// The roll swaps the verdict text, so the clamp uses the widest verdict word at the current font size (measured once per size).
const VDW = {};
function vdMaxW(vb) { const k = vb.style.fontSize + "|" + innerWidth; if (VDW[k]) return VDW[k]; const tx = $("#vdTx"), old = tx.textContent; let m = 0; HYPE.forEach(([w]) => { tx.textContent = w; m = Math.max(m, vb.offsetWidth); }); tx.textContent = old; return (VDW[k] = m); }
function vdEntry(vb) { const sw = $("#stageWrap").getBoundingClientRect(), r = vb.getBoundingClientRect(), w = Math.max(vb.offsetWidth, vdMaxW(vb)), h = vb.offsetHeight; if (!w || !h) return 2.4; const cy = (r.top + r.bottom) / 2; return Math.max(1, Math.min(2.4, (r.right - sw.left - 4) / w, 2 * (cy - sw.top - 2) / h, 2 * (sw.bottom - cy - 2) / h)).toFixed(3); }
function seqFrame(t, B) {
  const L = S.L || {};
  const { r, n, land } = reveal(t, B);
  if (B >= 280 && !S._slam) { S._slam = true; shake(9); three() && three().punch(); } if (B < 280) S._slam = false;
  if (r !== S._rv) { if (r > S._rv && three()) { if (r === n + 1) { three().react(t.vc); three().punch(); shake(t.vc === "red" ? 14 : 8); } else if (r > 0) three().hop(); } S._rv = r; }
  const wp = B < 50 ? 0 : B < 260 ? 1 : 2; const wipe = $("#wipe");
  wipe.style.transition = wp === 0 ? "none" : "clip-path .2s cubic-bezier(.7,0,.3,1)"; wipe.style.clipPath = S.scanning ? "inset(0 100% 0 0)" : wp === 0 ? "inset(0 100% 0 0)" : wp === 1 ? "inset(0 0 0 0)" : "inset(0 0 0 100%)";
  const rw = $("#resWord"); rw.style.opacity = B >= 280 ? 1 : 0; rw.style.transition = B >= 280 ? "transform .26s cubic-bezier(.2,1.08,.4,1), opacity .08s" : "none"; rw.style.transform = B >= 280 ? "rotate(-8deg) scale(1)" : "rotate(-8deg) scale(1.3)";
  $("#hzTop").style.transform = B >= 750 ? "scaleX(1)" : "scaleX(0)"; $("#hzMid").style.transform = r > n - 1 && B >= 900 + n * 420 ? "scaleX(1)" : "scaleX(0)";
  const rows = boardRows(t); const box = $("#srows");
  $$(".srow", box).forEach((el, i) => { const [k, v, c] = rows[i]; const on = r > i; const pp = easeO(Math.min(1, Math.max(0, B - 900 - i * 420) / 380)); el.classList.toggle("on", on); el.children[0].textContent = k; el.children[1].textContent = on ? countTo(v, pp) : v; el.children[1].style.color = c === "red" ? C.red : C.ink; });
  const rollStart = 900 + n * 420 + 150, steps = 22; let hi = t.vi, rolling = false;
  if (B >= rollStart && B < land) { rolling = true; const pr = easeO((B - rollStart) / (land - rollStart)); hi = ((t.vi - steps + Math.floor(pr * steps)) % HYPE.length + HYPE.length) % HYPE.length; }
  const tone = TONE[HYPE[hi][1]], done = r > n; const vb = $("#vdBox");
  $("#vdLab").style.opacity = B >= rollStart ? 1 : 0; 
  vb.style.opacity = B >= rollStart ? 1 : 0; vb.style.transform = done ? "scale(1)" : rolling ? "scale(0.92)" : "scale(" + vdEntry(vb) + ")"; vb.style.background = tone.bg; vb.style.color = tone.color; vb.style.borderColor = tone.border;
  $("#vdJp").textContent = tone.jp; $("#vdJp").style.display = tone.jp ? "inline" : "none"; $("#vdTx").textContent = HYPE[hi][0];
  vb.dataset.landed = done ? "1" : "0"; vb.dataset.tone = HYPE[hi][1];
}
function typeFrame(t, B) {
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
  const h = $("#rhead"); h.hidden = false; h.dataset.v = S.view;
  h.innerHTML = `<div class="l"><h1 class="disp">${esc(title)}</h1><span class="meta up">${esc(kindTxt)}${chips.length ? " // " + chips.map(esc).join(" // ") : ""}</span></div><div class="acts">${askArgs ? askBtn("Ask about this", askArgs, "btn y", "Ask Grok Bot about this report") : ""}${extra}<button class="btn" id="exportBtn">Export</button></div>`;
}
function render() {
  $("#root").className = wide() ? "wide" : "narrow";
  navState();
  const stageView = ["home", "token", "wallet", "replay", "asset"].includes(S.view);
  $("#stageWrap").hidden = !stageView; $("#panel").hidden = stageView; $("#home").hidden = S.view !== "home"; $("#res").hidden = !stageView || S.view === "home";
  $("#details").hidden = !stageView || S.view === "home"; $("#hsbox").hidden = S.view === "home"; $("#rhead").hidden = S.view === "home";
  if (three()) three().setVisible(stageView);
  if (S.view === "home") { $("#tryChips").innerHTML = targets().filter((t, i, a) => (a.findIndex(x => x.view === t.view) === i && t.view !== "asset") || t.view === "token").slice(0, 3).concat(assetTargets().filter(t => t.set === "live").slice(0, 1)).map(t => `<button data-scan="${esc(t.id)}">${esc(t.title)}</button>`).join(""); if (INV) INV.homePulse($("#hpulse")); return; }
  if (stageView) {
    const t = S.target;
    head(t.title, t.kind, t.chips, [t.kind, t.title, t.evId, repLabel(t.r), [t.score.label + ": " + t.score.value + (t.score.unit ? " " + t.score.unit : ""), "Verdict phrase: " + HYPE[t.vi][0] + " (severity " + (t.sev || "n/a") + ")"].concat(t.metrics.slice(0, 3).map(([k, v]) => k + ": " + v))],
      `<button class="btn" id="rescanBtn">${S.scanning ? "Scanning…" : "Re-scan"}</button>` + (INV && t.view === "asset" && t.set === "live" && t.sig ? `<button class="btn y" data-inv="${esc(t.sig.key)}">Investigate</button>` : "") + (targets().filter(x => x.view === t.view).length > 1 ? `<button class="btn" id="nextRep">Next report</button>` : ""));
    $("#rescanBtn").onclick = () => scan(t.id); const nr = $("#nextRep"); if (nr) nr.onclick = () => { const l = targets().filter(x => x.view === t.view); scan(l[(l.findIndex(x => x.id === t.id) + 1) % l.length].id); };
    renderDetails(); return;
  }
  const P = $("#panel"); P.innerHTML = ""; ((S.feat && REG.byId[S.feat] && (S.view === "signals" || S.view === "market") ? (P) => (S.view === "market" ? vMarket : vFeatSignals)(P, REG.byId[S.feat]) : null) || ({ limited: vLimited, tcg: (P) => TCGX ? TCGX.vTcg(P) : (P.innerHTML = `<div class="empty">Card Explorer not loaded.</div>`), universe: vUniverse, anomalies: vAnomalies, signals: vSignals, threats: vThreats, shill: vShill, copy: vCopy, board: vBoard, prov: vProv, investigate: (P) => INV ? INV.vInvestigate(P) : (P.innerHTML = `<div class="empty">Investigations not loaded.</div>`), pulse: (P) => INV ? INV.vPulse(P) : (P.innerHTML = `<div class="empty">Pulse not loaded.</div>`), watch: (P) => INV ? INV.vWatch(P) : (P.innerHTML = `<div class="empty">Watchlist not loaded.</div>`) }[S.view] || (() => P.innerHTML = `<div class="empty">Unknown view.</div>`)))(P);
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
    const bars = Array.from({ length: 40 }, (_, i) => { const pct = (i + 0.5) / 40 * 100; let c = (t.events[0] || [0, "grey"])[1]; t.events.forEach(e => { if (e[0] <= pct) c = e[1]; }); const sp = t.events.length > 2 && t.events[0][4] != null ? t.events[Math.min(t.events.length - 1, Math.floor(i / 40 * t.events.length))][4] : null; const h = sp != null ? 8 + sp * 90 : 18 + Math.abs(Math.sin(i * 1.7 + t.title.length)) * 50 * (1 - i / 60); return `<span style="height:${h.toFixed(0)}px;background:${C[c]};opacity:${pct <= S.scrub ? 1 : .25}"></span>`; }).join("");
    const xs = t.xposts && S.withX ? t.xposts.slice(0, 3) : [];
    B.innerHTML = t.events.length ? `<div style="padding:16px"><div class="bars">${bars}<span class="cur" style="left:${S.scrub}%"></span></div><input type="range" id="scrub" min="0" max="100" value="${S.scrub}" aria-label="Scrub timeline" style="width:100%;height:28px;margin-top:8px"><div id="evText" style="display:flex;gap:10px;align-items:flex-start;padding:8px 0;text-wrap:pretty"><span style="width:8px;height:8px;background:${C[ev[1]]};margin-top:5px;flex-shrink:0"></span>${esc(ev[2])}</div>${t.xposts ? `<label style="display:flex;gap:8px;align-items:center;min-height:32px"><input type="checkbox" id="withx" ${S.withX ? "checked" : ""}> Overlay X posts (${t.xposts.length} merged)</label>` + xs.map(x => `<div class="lim">${esc((x.relativeTime || "") + " · " + (x.detail || "X post"))}</div>`).join("") : ""}</div>` : `<div class="empty">No timeline in this report.</div>`;
    const sc = $("#scrub"); if (sc) sc.oninput = () => { S.scrub = +sc.value; renderDetails(); $("#scrub").focus(); };
    const wx = $("#withx"); if (wx) wx.onchange = () => { S.withX = wx.checked; renderDetails(); };
  }
  if (S.tab === 2) B.innerHTML = `<div style="display:flex;flex-direction:column;gap:12px;padding:16px"><div class="why">${t.why.map(y => `<div>${esc(y)}</div>`).join("") || "<div>No findings in this report.</div>"}<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:10px;flex-wrap:wrap"><span style="font-size:10px;letter-spacing:.04em">FINDING // FROM THE REPORT // DO NOT PARAPHRASE</span>${askBtn("Ask about this", [t.kind + " // Why flagged", t.title, t.evId + "#finding:" + t.whyId, repLabel(t.r), t.why.slice(0, 4)], "ask", "Ask Grok Bot about this finding").replace('class="ask"', 'class="ask" style="background:#0b0b0d;border-color:#0b0b0d"')}</div></div>${(t.evidence || []).map(e => `<div class="lim">Source: ${extLink(e.url, e.label)}</div>`).join("")}${t.limits.map(y => `<div class="lim">${esc(y)}</div>`).join("")}</div>`;
}
$("#dtabs").addEventListener("click", (e) => { const b = e.target.closest("[data-tab]"); if (!b) return; const i = +b.dataset.tab; S.open = S.tab === i ? !S.open : true; S.tab = i; if (three()) three().spin(); renderDetails(); });

/* ---------------- panel views ---------------- */
const sq = (c) => `<span class="sq" style="background:${C[c] || C.grey}"></span>`;
function vSignals(P) {
  const all = of("signals"), r = all.find(x => x.name === S.sigRep) || all[0]; if (!r) { head("Signals", "Cross-market", [], null); P.innerHTML = `<div class="empty">No signals report loaded. Open a signals JSON file from the Export menu.</div>`; return; }
  const j = r.j, a = j.assessment || {}, cov = j.coverage || {}, w = j.watch || {}, tel = w.telemetry || {};
  head("Signals", "Cross-market report", [num((j.signals || []).length) + " signals", "status " + (j.status || "?"), genAt(r)], ["Signals", "Signals report", "signals:" + (a.lead || {}).signal, repLabel(r), ["Lead: " + (a.lead || {}).text, "Severity: " + a.severity, "Status: " + j.status]]);
  const srcs = Object.entries(j.sourceStatus || {});
  const fams = ["all"].concat([...new Set((j.signals || []).map(s => s.source))]);
  const sigs = (j.signals || []).filter(s => S.sigFilter === "all" || s.source === S.sigFilter);
  const pick = all.length > 1 ? `<div class="chips" role="group" aria-label="Signals report">${all.map(x => `<button class="chip" data-srep="${esc(x.name)}" aria-pressed="${x === r}">${esc(isSynRep(x) ? "Example: " + x.name : "Real cached: " + x.name)}</button>`).join("")}</div>` : "";
  P.innerHTML = (pick ? `<div class="card">${pick}</div>` : "") + (isSynRep(r) ? `<div class="card synbox"><div class="lim">Example report: synthetic generator, no provider contacted. Instruments and moves are invented.</div></div>` : "") + `<div class="card"><h2 class="disp">Summary</h2><dl class="kv"><dt>What happened</dt><dd>${esc((a.lead || {}).text)}</dd><dt>How fresh</dt><dd>${esc(genAt(r))}</dd><dt>What was observed</dt><dd>${srcs.filter(([, v]) => v.state === "HEALTHY").length} of ${srcs.length} sources answered; ${esc(srcs.filter(([, v]) => v.state !== "HEALTHY").map(([k, v]) => k + " " + v.state).join(", "))}</dd><dt>Why it was flagged</dt><dd>${esc((a.lead || {}).why || "—")}</dd></dl></div>
  <div class="grid2"><div class="card"><h2 class="disp">Feed</h2><div class="chips" role="group" aria-label="Source filter">${fams.map(f => `<button class="chip" data-sf="${esc(f)}" aria-pressed="${S.sigFilter === f}">${esc(f)}</button>`).join("")}</div><div class="list">${sigs.map(s => sigItem(s, r)).join("") || `<div class="empty">No signals from this source.</div>`}</div></div>
  <div style="display:flex;flex-direction:column;gap:12px"><div class="card"><h2 class="disp">Calendar</h2>${((j.calendar || {}).upcoming || []).map(c => `<div class="lim">${esc(c.label)} · ${esc(c.time)}${c.timeExact ? "" : " (approximate)"}</div>`).join("") || `<div class="empty">No calendar events.</div>`}</div>
  <div class="card"><h2 class="disp">Watch telemetry</h2><dl class="kv">${Object.entries(tel).filter(([, v]) => typeof v === "number").map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl></div></div></div>
  <div class="card"><h2 class="disp">Coverage</h2><div class="tw"><table class="t"><thead><tr><th>Source</th><th>Family</th><th>Status</th><th>Last valid</th><th>Universe</th><th>Observed</th><th>Note</th></tr></thead><tbody>${(cov.matrix || []).map(m => `<tr><td>${esc(m.source)}</td><td>${esc(m.family || "—")}</td><td style="color:${m.status === "HEALTHY" ? C.green : m.status === "UNAVAILABLE" ? C.red : C.amber}">${esc(m.status)}</td><td>${esc(m.lastValidAt || "—")}</td><td>${esc(m.universe || "—")}</td><td>${m.observed ?? "—"}</td><td class="dim">${esc(m.detail || "")}</td></tr>`).join("")}</tbody></table></div>${(cov.limits || []).map(l => `<div class="lim">${esc(l.kind)}: ${esc(l.text)}</div>`).join("")}</div>`;
  $$("[data-sf]", P).forEach(b => b.onclick = () => { S.sigFilter = b.dataset.sf; render(); });
  $$("[data-srep]", P).forEach(b => b.onclick = () => { S.sigRep = b.dataset.srep; S.sigFilter = "all"; render(); });
}
/* ---------------- universe + anomalies ---------------- */
const ST = { shipped: ["Shipped", "t-amber"], "feasible-next": ["Next", "t-green"], "blocked-licence": ["Licence", "t-red"] };
const ACC = { "free-redistributable": "Free, redistributable", "derived-signals-only": "Derived signals only", paid: "Paid", "partner-only": "Partner only", blocked: "Blocked" };
const sparkSVG = (v, w = 120, h = 28) => { if (!v || v.length < 2) return ""; const mx = Math.max(...v), mn = Math.min(...v), d = v.map((x, i) => (i / (v.length - 1) * w).toFixed(1) + "," + (h - 2 - (x - mn) / ((mx - mn) || 1) * (h - 4)).toFixed(1)).join(" "); return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${d}" fill="none" stroke="#faf905" stroke-width="1.5"/></svg>`; };
const evFor = (uid, quiet = false) => EV_SIGS.filter(x => UNI_OF(x.s) === uid && !!x.quiet === quiet);
const SEV_RANK = (s) => ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"].indexOf(s);
function uniDetail(u) {
  const ev = evFor(u.id);
  return `<div class="card" id="uniDetail"><div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start"><h2 class="disp">${esc(u.name)}</h2><button class="btn" id="uniClose" aria-label="Close details">×</button></div><dl class="kv"><dt>Status</dt><dd>${ST[u.status][0]}${u.status === "blocked-licence" ? " (blocked by a data licence, not by code)" : ""}</dd><dt>Venues</dt><dd>${esc(u.venues)}</dd><dt>Common arbitrage</dt><dd>${esc(u.arbitrage)}</dd><dt>Best source</dt><dd>${extLink(u.sourceUrl, u.source)}</dd><dt>Access</dt><dd>${esc(ACC[u.access])}${u.verified ? " · terms read 2026-10-28" : " · terms not yet verified"}</dd>${u.note ? `<dt>Note</dt><dd>${esc(u.note)}</dd>` : ""}</dl>
  ${evFor(u.id, true).length ? `<div class="dim" style="margin:10px 0 6px">Tracked, nothing past threshold</div><div class="chips">${evFor(u.id, true).slice(0, 30).map(x => `<button class="chip" data-scan="${esc("asset:" + x.s.key)}">${esc(x.s.name.replace(/\s*\(.*?\)$/, "").slice(0, 26))}</button>`).join("")}</div>` : ""}<div class="list" style="margin-top:8px">${ev.map(x => evRow(x)).join("") || `<div class="empty">${u.status === "shipped" ? "Nothing past threshold in the cached run." : "No detector runs on this class yet."}</div>`}</div><div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">${u.status === "shipped" && REG.byId[REG.UNI_TOOL[u.id]] ? `<button class="btn y" data-feat-go="${esc(REG.UNI_TOOL[u.id])}">Open ${esc(REG.byId[REG.UNI_TOOL[u.id]].name)}</button>` : ""}${askBtn("Ask about this", ["Universe", u.name, "universe:" + u.id, "everything-universe.json", ["Status: " + u.status, "Access: " + u.access, "Source: " + u.source, "Arbitrage pattern: " + u.arbitrage]], "btn y")}</div></div>`;
}
function evRow({ s, set }) {
  const id = "asset:" + s.key + (set === "synthetic" ? ":syn" : "");
  return `<div class="erow${set === "synthetic" ? " syn" : ""}">${sq(SEVC[s.severity])}<span class="eb"><span class="hd"><span>${esc(CAT_OF[s.category] || s.category)} // ${esc(s.name)}</span><span>${esc(s.severity)} · ${esc(s.basis)}${set === "synthetic" ? " · synthetic" : ""}</span></span><span class="ti">${esc(s.title.replace(/^\[SYNTHETIC\]\s*/, ""))}</span></span><span class="ea"><button class="btn y" data-scan="${esc(id)}">Evidence</button>${askBtn("Ask", ["Anomalies", s.title, s.key, evReport(set).name, ["Type: " + s.type, "Severity: " + s.severity, "Basis: " + s.basis, "What: " + String(s.what).slice(0, 140)]])}</span></div>`;
}
/* ---------------- cross-market anomalies (one normalized list, provenance kept, duplicates counted once) ---------------- */
const SRC_CAT = { fx: "ratesfx", "fx-h10": "ratesfx", treasury: "ratesfx", macro: "ratesfx", metals: "commodities", energy: "commodities", cot: "commodities", mtg: "tcg", cs2: "more", synthetic: "more", polymarket: "prediction", kalshi: "prediction", cross: "prediction", equities: "stocks", options: "stocks", sec: "stocks", crypto: "crypto", stablecoins: "crypto", solana: "crypto" };
const EVCAT = { fx: "ratesfx", metals: "commodities", energy: "commodities", positioning: "commodities", cards: "tcg", skins: "more", games: "more", collectibles: "more" };
const SRC_FEAT = { polymarket: "pm.odds", kalshi: "pm.odds", cross: "pm.related", equities: "eq.signals", options: "eq.options", sec: "eq.sec", treasury: "rt.treasury", crypto: "crypto.market", stablecoins: "crypto.market", fx: "fx.rates", metals: "cm.metals", energy: "cm.energy", cot: "cm.cot", mtg: "tcg.mtg", cs2: "more.cs2" };
function anomalyItems() {
  const out = [], seen = new Map();
  const add = (it) => { const k = it.dedupe || it.key; if (seen.has(k)) { const o = seen.get(k); o.reports.add(it.report); return; } it.reports = new Set([it.report]); seen.set(k, it); out.push(it); };
  EV_SIGS.filter(x => !x.quiet).forEach(({ s, set }) => add({ key: s.key + (set === "synthetic" ? ":syn" : ""), mode: set === "synthetic" ? "examples" : s.source === "cs2" ? "experimental" : "cached", cat: EVCAT[s.category] || SRC_CAT[s.source] || "more", instrument: s.name, type: s.type, sev: s.severity, when: s.when, ingested: set === "live" ? EV.live.generatedAt : null, source: s.source === "synthetic" ? "synthetic generator" : s.source, title: s.title.replace(/^\[SYNTHETIC\]\s*/, ""), limits: s.limits || [], evidence: s.evidence || [], scan: "asset:" + s.key + (set === "synthetic" ? ":syn" : ""), feat: SRC_FEAT[s.source], report: evReport(set).name, dedupe: s.source + "|" + s.name + "|" + s.type + "|" + set }));
  of("signals").forEach(r => { const syn = isSynRep(r); (r.j.signals || []).forEach(s => add({ key: s.key, mode: syn ? "examples" : "cached", cat: SRC_CAT[s.source] || "more", instrument: s.instrument || (s.subject || {}).name || s.source, type: s.type, sev: s.severity, when: s.when, ingested: r.j.generatedAt, source: s.source, title: String(s.title || "").replace(/^\[SYNTHETIC\]\s*/, ""), limits: (s.derivedOnly ? (s.limits || []).slice(0, 1).concat(["Derived observation: provider values are not stored; follow the evidence link."]) : [s.what]).filter(Boolean), evidence: s.evidence || [], feat: SRC_FEAT[s.source], report: r.name, dedupe: s.key })); });
  of("threats").forEach(r => { const syn = isSynRep(r); r.j.forEach(a => add({ key: a.id || a.key, mode: syn ? "examples" : "cached", cat: "crypto", instrument: "$" + a.tokenSymbol, type: a.type || "ALERT", sev: a.severity, when: a.timestamp, ingested: null, source: "solana", title: a.detail, limits: [], evidence: [], feat: "crypto.threats", report: r.name, dedupe: "sol|" + a.tokenSymbol + "|" + (a.type || "") + "|" + a.timestamp })); });
  of("watch").forEach(r => { const syn = isSynRep(r); (r.j.alerts || []).forEach(a => add({ key: a.key || a.signature, mode: syn ? "examples" : "cached", cat: "crypto", instrument: "$" + a.tokenSymbol, type: a.type || "ALERT", sev: a.severity, when: a.timestamp, ingested: null, source: "solana", title: a.detail || a.type, limits: [], evidence: [], scan: "token:" + a.tokenSymbol, feat: "crypto.threats", report: r.name, dedupe: "sol|" + a.tokenSymbol + "|" + (a.type || "") + "|" + a.timestamp })); });
  return out;
}
window.GTB.anomalyItems = anomalyItems; window.GTB_SUG = (q) => suggestions(q).slice(0, 3).map(x => x.label + " -> " + x.id.slice(0, 40));
const MODE_LBL = { cached: "Real cached", experimental: "Experimental", examples: "Examples (synthetic)" };
function aRow(it) {
  const tid = it.scan && targets().some(t => t.id === it.scan) ? it.scan : null;
  return `<div class="erow${it.mode === "examples" ? " syn" : ""}" data-akey="${esc(it.key)}">${sq(SEVC[it.sev])}<span class="eb"><span class="hd"><span>${esc(catName(it.cat))} // ${esc(it.instrument)}</span><span>${esc(String(it.type).replace(/_/g, " ").toLowerCase())} · ${esc(it.sev || "no severity")} · ${esc(it.source)}${it.mode === "examples" ? " · synthetic" : it.mode === "experimental" ? " · experimental" : ""}</span></span><span class="ti">${esc(it.title)}</span><span class="hd"><span>${it.mode === "examples" ? "synthetic example · " : ""}observed ${esc(iso(it.when))}${it.ingested ? " · ingested " + esc(iso(it.ingested)) : ""}</span><span>${it.reports.size > 1 ? "same incident in " + it.reports.size + " reports, counted once" : esc(it.report)}</span></span>${it.limits[0] ? `<span class="lim">${esc(String(it.limits[0]).slice(0, 220))}</span>` : ""}</span><span class="ea">${tid ? `<button class="btn y" data-scan="${esc(tid)}">Evidence</button>` : ""}${INV && it.mode !== "examples" && INV.index().has(it.key) ? `<button class="btn" data-inv="${esc(it.key)}">Investigate</button>` : ""}${it.feat ? `<button class="btn" data-feat-go="${esc(it.feat)}">Open tool</button>` : ""}${askBtn("Ask", ["Anomalies", it.title, it.key, it.report, ["Category: " + catName(it.cat), "Type: " + it.type, "Severity: " + it.sev, "Data: " + MODE_LBL[it.mode]]])}</span></div>`;
}
function vAnomalies(P) {
  const all = anomalyItems(), modeOf = (m) => all.filter(x => x.mode === m);
  const inMode = modeOf(S.aMode), cats = ["all"].concat(REG.CATS.map(c => c.id).filter(c => inMode.some(x => x.cat === c))), srcs = ["all"].concat([...new Set(inMode.map(x => x.source))]), sevs = ["all"].concat(["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"].filter(s => inMode.some(x => x.sev === s)));
  if (!cats.includes(S.aCat)) S.aCat = "all"; if (!srcs.includes(S.aSrc)) S.aSrc = "all"; if (!sevs.includes(S.aSev)) S.aSev = "all";
  const vis = inMode.filter(x => (S.aCat === "all" || x.cat === S.aCat) && (S.aSrc === "all" || x.source === S.aSrc) && (S.aSev === "all" || x.sev === S.aSev)).sort((a, b) => SEV_RANK(b.sev) - SEV_RANK(a.sev) || (b.when || 0) - (a.when || 0));
  const unk = (EV.live.probes || []).filter(p => p.state === "unknown"), meas = (EV.live.probes || []).filter(p => p.state === "measured");
  head("Anomalies", "Every market, one feed", [modeOf("cached").length + " real cached", modeOf("experimental").length + " experimental", modeOf("examples").length + " examples", meas.length + " checks measured", unk.length + " unknown"], ["Anomalies", "Unified anomaly feed", "anomalies:" + S.aMode, "everything-live-derived.json", ["Mode: " + MODE_LBL[S.aMode], "Shown: " + vis.length, "Unknown checks: " + unk.length]], INV ? `<button class="btn" data-view-go="pulse">Pulse</button><button class="btn" data-view-go="watch">Watchlist</button>` : "");
  const chips = (label, key, vals, name) => `<div class="chips" role="group" aria-label="${label}">${vals.map(v => `<button class="chip" data-af="${key}" data-v="${esc(v)}" aria-pressed="${S[key] === v}">${esc(name(v))}</button>`).join("")}</div>`;
  const CR = coverageRows().filter(c => !c.exp && (S.aCat === "all" || c.cat === S.aCat)), crA = CR.filter(c => c.state !== "unknown"), crU = CR.filter(c => c.state === "unknown");
  const empty = S.aMode === "cached" ? (crA.length ? `<div class="empty">No findings in the assessed markets${S.aCat !== "all" ? " in " + esc(catName(S.aCat)) : ""}: ${crA.length} sources assessed (${esc(crA.map(c => c.src).join(", "))}).${crU.length ? " Unknown / not assessed: " + esc(crU.map(c => c.src + " " + c.outcome).join(", ")) + "." : ""}</div>` : `<div class="empty limited">Unknown / not assessed${S.aCat !== "all" ? " in " + esc(catName(S.aCat)) : ""}: ${crU.length ? esc(crU.map(c => c.src + " " + c.outcome).join(", ")) : "no source covers this filter"}. No verdict without data.</div>`) : `<div class="empty">Nothing in this filter.</div>`;
  const covCard = `<div class="card"><h2 class="disp">Coverage</h2><div class="tw"><table class="t"><thead><tr><th>Source</th><th>Outcome</th><th>Assessment</th><th>Last success</th></tr></thead><tbody>${CR.map(c => `<tr><td>${esc(c.src)}</td><td style="color:${c.outcome === "FETCHED" ? C.green : c.outcome === "DEGRADED" ? C.amber : C.red}">${esc(c.outcome)}</td><td>${c.state === "unknown" ? "unknown, not assessed" : c.state === "quiet" ? "assessed, quiet" : c.n + " finding" + (c.n === 1 ? "" : "s")}</td><td>${esc(c.last ? age(c.last) : "never")}</td></tr>`).join("") || `<tr><td colspan="4">No source covers this filter.</td></tr>`}</tbody></table></div></div>`;
  P.innerHTML = `<div class="card"><div class="frow">${chips("Data mode", "aMode", ["cached", "experimental", "examples"], v => MODE_LBL[v] + " (" + modeOf(v).length + ")")}</div><div class="frow" style="margin-top:8px">${chips("Category filter", "aCat", cats, v => v === "all" ? "All markets" : catName(v))}${chips("Severity filter", "aSev", sevs, v => v === "all" ? "Any severity" : v)}</div><div class="frow" style="margin-top:8px">${chips("Source filter", "aSrc", srcs, v => v === "all" ? "Any source" : v)}</div></div>
  <div class="grid2"><div class="card${S.aMode === "examples" ? " synbox" : ""}"><h2 class="disp">${esc(MODE_LBL[S.aMode])}</h2><div class="lim" style="margin-bottom:6px">${S.aMode === "cached" ? "Cached real data from the last refresh (" + esc(iso(EV.live.generatedAt)) + ", " + esc(age(EV.live.generatedAt)) + (EV.markets ? "; markets " + esc(age(EV.markets.generatedAt)) : "") + "). Not live." : S.aMode === "experimental" ? "Undocumented or unverified sources. Derived numbers only; not part of the default feed." : "Synthetic examples: invented instruments and prices that demonstrate the detectors. Not market activity."}</div><div class="list">${vis.map(aRow).join("") || empty}</div></div>
  <div style="display:flex;flex-direction:column;gap:12px">${S.aMode === "cached" ? covCard : ""}<div class="card"><h2 class="disp">Closest to threshold</h2>${meas.slice().sort((x, y) => y.ratio - x.ratio).slice(0, 8).map(p => `<div class="lim">${esc(p.asset)} · ${esc(p.type.replace(/_/g, " ").toLowerCase())} at ${p.ratio.toFixed(2)}× threshold</div>`).join("") || `<div class="empty">No measured checks.</div>`}</div>
  <div class="card"><h2 class="disp">Unknown, not quiet</h2>${unk.slice(0, 8).map(p => `<div class="lim">${esc(p.asset)} · ${esc(p.type.replace(/_/g, " ").toLowerCase())}: ${esc(p.reason)}</div>`).join("") || `<div class="empty">Every check returned a measurement.</div>`}${unk.length > 8 ? `<div class="lim">…and ${unk.length - 8} more</div>` : ""}</div></div></div>`;
  $$("[data-af]", P).forEach(b => b.onclick = () => { S[b.dataset.af] = b.dataset.v; if (b.dataset.af === "aMode") { S.aCat = S.aSrc = S.aSev = "all"; } render(); });
}
/* ---------------- Universe: Explore all markets (directory, grouped by family, usable classes first) ---------------- */
function vUniverse(P) {
  const U = EV.universe || [], n = (st) => U.filter(u => u.status === st).length, q = (S.uQ || "").toLowerCase();
  head("All Markets", "Explore all markets", [U.length + " asset classes", n("shipped") + " covered", (U.length - n("shipped")) + " not covered yet"], ["Universe", "Asset directory", "universe:" + U.length, "everything-universe.json", ["Asset classes: " + U.length, "Covered: " + n("shipped")]]);
  const match = (u) => (!q || (u.name + " " + u.category + " " + u.venues).toLowerCase().includes(q)) && (S.uCat === "All" || u.category === S.uCat);
  const tile = (u) => { const tool = u.status === "shipped" ? REG.byId[REG.UNI_TOOL[u.id]] : null, ev = evFor(u.id).filter(x => x.set === "live"), a = (EV.live.assets || []).find(x => x.universe === u.id && x.spark && x.redistributable), d = tool ? dataState(tool) : null;
    return `<div class="tile${S.uSel === u.id ? " on" : ""}">${tool ? `<button class="tmain" data-feat-go="${esc(tool.id)}"><span class="disp nm">${esc(u.name)}</span><span class="dim cat">${esc(tool.name)} · ${esc(DATA_TAG[d])}${ev.length ? " · " + ev.length + " flag" : ""}</span>${a ? sparkSVG(a.spark) : `<span class="nospark"></span>`}</button>` : `<span class="tmain"><span class="disp nm">${esc(u.name)}</span><span class="dim cat">${u.status === "blocked-licence" ? "Data licence needed" : "Not covered yet"}</span><span class="nospark"></span></span>`}<button class="tinfo" data-uni="${esc(u.id)}" aria-pressed="${S.uSel === u.id}" aria-label="Details: ${esc(u.name)}">Details</button></div>`; };
  const fams = EV.categories.filter(c => U.some(u => u.category === c && u.status === "shipped" && match(u)));
  const rest = U.filter(u => u.status !== "shipped" && match(u)), sel = U.find(u => u.id === S.uSel);
  const famOpen = (c) => S.uOpen[c] ?? innerWidth >= 768;
  P.innerHTML = `<div class="card"><div class="frow"><label class="uq"><span class="dim">Find</span><input id="uq" value="${esc(S.uQ || "")}" placeholder="GOLD, CARDS, WATCHES…" aria-label="Filter asset classes" autocomplete="off"></label><div class="chips" role="group" aria-label="Family filter">${["All"].concat(EV.categories.filter(c => U.some(u => u.category === c))).map(c => `<button class="chip" data-ucat="${esc(c)}" aria-pressed="${S.uCat === c}">${esc(c)}</button>`).join("")}</div></div></div>
  <div class="unigrid${sel ? " withsel" : ""}"><div>${fams.map(c => `<details class="fam" data-fam="${esc(c)}" ${famOpen(c) ? "open" : ""}><summary><span class="disp">${esc(c)}</span><span class="dim">${U.filter(u => u.category === c && u.status === "shipped" && match(u)).length} covered</span></summary><div class="tiles">${U.filter(u => u.category === c && u.status === "shipped" && match(u)).map(tile).join("")}</div></details>`).join("") || `<div class="empty">No covered class matches.</div>`}
  ${rest.length ? `<details class="fam rest" data-fam="__rest" ${S.uOpen.__rest || q ? "open" : ""}><summary><span class="disp">Not covered yet</span><span class="dim">${rest.length} classes · documented, no live tool</span></summary><div class="tiles">${rest.map(tile).join("")}</div></details>` : ""}</div>${sel ? uniDetail(sel) : ""}</div>`;
  const uq = $("#uq", P); uq.oninput = () => { S.uQ = uq.value; const pos = uq.selectionStart; render(); const n2 = $("#uq"); n2.focus(); n2.setSelectionRange(pos, pos); };
  $$("[data-ucat]", P).forEach(b => b.onclick = () => { S.uCat = b.dataset.ucat; render(); });
  $$("details.fam", P).forEach(d => d.addEventListener("toggle", () => { S.uOpen[d.dataset.fam] = d.open; }));
  $$("[data-uni]", P).forEach(b => b.onclick = () => { S.uSel = S.uSel === b.dataset.uni ? null : b.dataset.uni; render(); const d = $("#uniDetail"); if (d && $("#root").className === "narrow") d.scrollIntoView({ block: "nearest" }); });
  const cl = $("#uniClose"); if (cl) cl.onclick = () => { S.uSel = null; render(); };
}
/* ---------------- capability pages (Signals engine or market engine, filtered by the registry route) ---------------- */
const age = (ts) => { if (ts == null) return "unknown age"; const ms = Date.now() - (typeof ts === "number" ? (ts < 1e12 ? ts * 1000 : ts) : Date.parse(ts)); if (!(ms >= 0)) return "time unknown"; const h = ms / 36e5; return h < 1 ? "under 1h old" : h < 48 ? Math.round(h) + "h old" : Math.round(h / 24) + " days old"; };
function statusStrip(f, d) {
  return `<div class="sstrip" role="group" aria-label="Capability status"><span><b>Implementation</b>${esc(f.impl)}${f.experimental ? " · experimental" : ""}</span><span class="d-${d}"><b>Data</b>${esc(DATA_LBL[d])}</span><span><b>Rights</b>${esc(RIGHTS_LBL[f.rights] || f.rights)}</span><span><b>Evidence</b>${esc(f.evidence)}</span></div>`;
}
const catName = (id) => (REG.CATS.find(c => c.id === id) || {}).name || id;
const OUTCOME_OF = { HEALTHY: "FETCHED", DEGRADED: "DEGRADED", STALE: "DEGRADED", UNAVAILABLE: "BLOCKED_EXTERNAL", NOT_CONFIGURED: "NOT_CONFIGURED" };
// One coverage list across the everything modules and the markets report: assessed-and-quiet vs findings vs unknown.
function coverageRows() {
  const out = [], H = Object.fromEntries((EV.live.health || []).map(h => [h.module, h]));
  (EV.live.coverage || []).forEach(c => { const h = H[c.module] || {}, ok = ["HEALTHY", "DEGRADED"].includes(c.status), n = (EV.live.signals || []).filter(s => s.module === c.module || (c.module === "fx-h10" && s.type === "FIX_CROSSCHECK")).length;
    out.push({ src: c.module, cat: SRC_CAT[c.module] || "more", outcome: OUTCOME_OF[c.status] || c.status, observed: c.observed, state: ok ? (n ? "findings" : "quiet") : "unknown", n, last: c.lastSuccessAt || h.lastSuccessAt || EV.live.generatedAt, err: c.errorCategory || null, exp: c.module === "cs2" }); });
  const M = EV.markets; if (M) Object.entries(M.sourceStatus || {}).forEach(([k, v]) => out.push({ src: k, cat: SRC_CAT[k] || "more", outcome: v.outcome || OUTCOME_OF[v.state] || v.state, observed: (v.coverage || {}).observed, state: v.assessment || (["HEALTHY", "DEGRADED"].includes(v.state) ? "quiet" : "unknown"), n: v.signals || 0, last: v.lastSuccessAt || null, err: v.state === "NOT_CONFIGURED" ? "not configured" : null, detail: v.detail }));
  return out;
}
function vFeatSignals(P, f) {
  const d = dataState(f), rep = of("signals")[0], r = f.route;
  head(f.name, catName(f.cat), [DATA_TAG[d]], rep ? [catName(f.cat), f.name, "feature:" + f.id, repLabel(rep), ["Data: " + DATA_LBL[d], "Sources: " + (r.src || []).join(", ")]] : null);
  if (!rep) { P.innerHTML = statusStrip(f, d) + `<div class="card limited"><h2 class="disp">No report loaded</h2><div class="lim">This tool reads a signals report. None is loaded, so the state is unknown, not quiet. Open a signals JSON file with Open.</div></div>`; return; }
  const j = rep.j, st = j.sourceStatus || {}, syn = isSynRep(rep);
  const sigs = (j.signals || []).filter(s => (r.src || []).includes(s.source) && (!r.types || r.types.includes(s.type)));
  const srcRows = (r.src || []).filter(k => st[k]).map(k => { const v = st[k], c = (v.coverage || {}), oc = v.outcome || OUTCOME_OF[v.state] || v.state; return `<tr><td>${esc(k)}</td><td style="color:${oc === "FETCHED" ? C.green : oc === "DEGRADED" ? C.amber : C.red}">${esc(oc)}</td><td>${esc(v.lastValidAt || "—")}</td><td>${esc(v.lastSuccessAt ? iso(v.lastSuccessAt) : iso(j.generatedAt))}</td><td>${esc(v.lastValidAt ? age(v.lastValidAt) : "no valid data")}</td><td class="dim">${c.observed != null ? esc(num(c.observed)) + " observed · " : ""}${esc(c.universe || "")}${v.detail ? " · " + esc(v.detail) : ""}</td></tr>`; }).join("");
  const assessed = (r.src || []).filter(k => st[k] && ["HEALTHY", "DEGRADED"].includes(st[k].state)), unassessed = (r.src || []).filter(k => !st[k] || !["HEALTHY", "DEGRADED"].includes(st[k].state));
  const nObs = assessed.reduce((n, k) => n + ((st[k].coverage || {}).observed || 0), 0);
  const unkTxt = unassessed.length ? `<div class="card limited"><h2 class="disp">Unknown / not assessed</h2>${unassessed.map(k => `<div class="lim">${esc(k)}: ${esc(st[k] ? (st[k].outcome || OUTCOME_OF[st[k].state] || st[k].state) : "not in this report")}. ${esc((st[k] || {}).detail || "")}</div>`).join("")}<div class="lim">Unknown, not quiet: no verdict is given when the source did not answer or is not configured.</div></div>` : "";
  const empty = !assessed.length ? unkTxt
    : `<div class="empty">No findings in the assessed markets: ${esc(assessed.join(", "))}, ${esc(num(nObs))} instruments or markets observed${syn ? "" : ", fetched " + esc(age(j.generatedAt))}. Quiet means no detector crossed its threshold, not an all-clear.</div>` + unkTxt;
  const cal = r.cal ? `<div class="card"><h2 class="disp">Calendar</h2>${((j.calendar || {}).upcoming || []).map(c => `<div class="lim">${esc(c.label)} · ${esc(c.time)}${c.timeExact ? "" : " (approximate)"}</div>`).join("") || `<div class="empty">No calendar events in this report.</div>`}<div class="lim">Settlement rules for individual contracts are not parsed yet.</div></div>` : "";
  P.innerHTML = statusStrip(f, d) + (syn ? `<div class="card synbox"><div class="lim">Example report: ${esc(String(j._note || "synthetic generator, no provider contacted").replace(/\.+\s*$/, ""))}. Instruments and moves are invented to exercise the detectors.</div></div>` : "")
    + `<div class="grid2"><div class="card${syn ? " synbox" : ""}"><h2 class="disp">${esc(f.name)}</h2><div class="list">${sigs.map(s => sigItem(s, rep)).join("") || empty}</div></div><div style="display:flex;flex-direction:column;gap:12px">${cal}<div class="card"><h2 class="disp">Sources</h2><div class="tw"><table class="t"><thead><tr><th>Source</th><th>Outcome</th><th>Observed at</th><th>Last success</th><th>Data age</th><th>Coverage</th></tr></thead><tbody>${srcRows || `<tr><td colspan="6">No source status in this report.</td></tr>`}</tbody></table></div></div></div></div>`;
}
const SPREAD_LIM = "Observed spread, not executable arbitrage. Trading fees, currency conversion, bid/ask, available depth, taxes, shipping, insurance, grading, settlement delays and stale listings are not measured.";
function assetTid(a) { const x = EV_SIGS.find(e => e.set === "live" && (e.s.asset === a.id || e.s.asset === a.name)); return x ? "asset:" + x.s.key : null; }
function vMarket(P, f) {
  const d = dataState(f), A = featAssets(f).filter(a => !S.focus || a.id === S.focus || a.name === S.focus), PR = featProbes(f).filter(p => !S.focus || p.asset === S.focus), mods = [...new Set((f.route.uni || []).map(u => UNI_MOD[u]))];
  const cov = (EV.live.coverage || []).filter(c => mods.includes(c.module) || (f.id === "fx.h10" && c.module === "fx-h10"));
  const sigs = EV_SIGS.filter(x => x.set === "live" && !x.quiet && (f.route.uni || []).includes(UNI_OF(x.s)) && (!f.route.types || f.route.types.includes(x.s.type)) && (!S.focus || JSON.stringify(x.s).includes(JSON.stringify(S.focus))));
  const meas = PR.filter(p => p.state === "measured"), unk = PR.filter(p => p.state === "unknown");
  const obs = A.map(a => a.asOf).filter(Boolean).sort(), spread = (f.route.types || []).includes("CROSS_VENUE_SPREAD") || f.id === "tcg.mtg";
  head(f.name, catName(f.cat), [A.length + " instruments", meas.length + " checks measured", unk.length + " unknown", DATA_TAG[d]], [catName(f.cat), f.name, "feature:" + f.id, "everything-live-derived.json", ["Data: " + DATA_LBL[d], "Instruments: " + A.length, "Measured: " + meas.length, "Unknown: " + unk.length]], S.focus ? `<button class="btn" id="focusBack">Card: ${esc(S.focus)} · back to card</button><button class="btn" id="focusAll">Show all cards</button>` : "");
  if (S.focus) { $("#focusAll").onclick = () => { S.focus = null; render(); }; $("#focusBack").onclick = () => { S.focus = null; goFeat("tcg.explorer"); }; }
  const lims = [].concat(spread ? [SPREAD_LIM] : [], f.id === "cm.metals" ? ["ETF prices are stand-ins for spot metal, not the benchmark price."] : [], f.experimental ? ["Experimental: undocumented endpoint, kept out of the default Anomalies feed until access and rights are resolved."] : [], f.id === "cm.ag" ? ["Positioning only: no agricultural price feed is integrated yet."] : [], f.id === "tcg.history" ? ["A trend needs 14 daily snapshots; the cache has " + ((cov[0] || {}).snapshotDays ?? "?") + ". Moves are unassessable until then, never quiet."] : [], ["A cached fetch is not live data. Refresh with python3 tools/build_everything.py --fetch, or opt in to the scheduled runner (docs/everything/REFRESH.md)."]);
  const verdict = sigs.length ? `<div class="list">${sigs.map(evRow).join("")}</div>`
    : !PR.length ? `<div class="card limited"><div class="lim">No checks loaded for this tool: unknown, not quiet.</div></div>`
    : !meas.length ? `<div class="empty limited">Unassessable: ${esc(unk[0].reason)}. No verdict until the detector has enough history.</div>`
    : `<div class="empty">Nothing past threshold in the cached run (${meas.length} measured${unk.length ? ", " + unk.length + " unknown and not counted as quiet" : ""}).</div>`;
  const row = (a) => { const ps = PR.filter(p => p.asset === a.id || p.asset === a.name), tid = assetTid(a); const pv = ps.map(p => p.state === "measured" ? p.type.replace(/_/g, " ").toLowerCase() + " " + p.ratio.toFixed(2) + "×" : "unknown: " + p.reason).join("; ") || "no check of this type";
    return `<tr><td class="nmc">${esc(a.name)}</td><td>${a.redistributable ? esc(String(a.last ?? "—")) : `<span class="dim">derived only</span>`}</td><td>${a.redistributable && a.spark ? sparkSVG(a.spark, 90, 22) : ""}</td><td>${esc(a.asOf || "—")}</td><td class="dim">${esc(pv)}</td><td>${tid ? `<button class="btn" data-scan="${esc(tid)}">Evidence</button>` : ""}</td></tr>`; };
  P.innerHTML = statusStrip(f, d) + `<div class="grid2"><div class="card"><h2 class="disp">Findings</h2>${verdict}<h2 class="disp" style="margin-top:14px">Instruments</h2><div class="tw"><table class="t"><thead><tr><th>Instrument</th><th>Last</th><th>History</th><th>Observed</th><th>Check</th><th></th></tr></thead><tbody>${A.filter(a => !f.route.types || PR.some(p => p.asset === a.id || p.asset === a.name)).map(row).join("") || `<tr><td colspan="6">${PR.length ? PR.map(p => esc(p.asset + ": " + (p.state === "measured" ? p.ratio.toFixed(2) + "× threshold" : p.reason))).join("<br>") : "No instruments loaded."}</td></tr>`}</tbody></table></div></div>
  <div style="display:flex;flex-direction:column;gap:12px"><div class="card"><h2 class="disp">Data status</h2><dl class="kv"><dt>Provider</dt><dd>${cov.map(c => esc(c.via) + (c.attribution ? " · " + esc(c.attribution) : "")).join("<br>") || "—"}</dd><dt>Observed at</dt><dd>${esc(obs.length ? obs[0] + (obs[0] !== obs[obs.length - 1] ? " to " + obs[obs.length - 1] : "") : "—")}</dd><dt>Ingested at</dt><dd>${esc(iso(EV.live.generatedAt))} (${esc(age(EV.live.generatedAt))})</dd><dt>Data type</dt><dd>${esc(DATA_LBL[d])}${f.experimental ? " · experimental" : ""}</dd><dt>Module health</dt><dd>${cov.map(c => esc(c.module + " " + c.status + (c.errorCategory ? " (" + c.errorCategory + ")" : "") + (c.lastSuccessAt ? ", last success " + age(c.lastSuccessAt) : ""))).join("<br>") || "—"}</dd></dl></div><div class="card"><h2 class="disp">Limitations</h2>${lims.map(l => `<div class="lim">${esc(l)}</div>`).join("")}</div></div></div>`;
}
function vLimited(P) {
  const L = S.limited || {}; const f = REG.byId[L.feat];
  head(L.title || "Not loaded", L.kind || "Search", ["limited"], null);
  P.innerHTML = `<div class="card limited"><h2 class="disp">${esc(L.head || "Recognized, no data loaded")}</h2><div class="lim">${esc(L.text || "")}</div><div class="lim">No verdict is shown: missing data is unknown, not quiet.</div>${f ? `<div style="margin-top:10px"><button class="btn y" data-feat-go="${esc(f.id)}">Open ${esc(f.name)}</button></div>` : ""}</div>`;
}
document.addEventListener("click", (e) => { const b = e.target.closest("[data-feat-go]"); if (b) goFeat(b.dataset.featGo); });
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
function curReport() { if (S.target && ["token", "wallet", "replay", "asset"].includes(S.view)) return S.target.r; if (S.view === "universe") return { name: "everything-universe.json", j: { categories: EV.categories, assets: EV.universe } }; if (S.view === "anomalies") return { name: "everything-anomalies.json", j: { live: EV.live, synthetic: EV.synthetic } }; return ({ signals: of("signals")[0], threats: of("threats")[0], shill: of("shill")[0], copy: of("token").find(x => x.name === S.copyRep) || of("token")[0], board: of("board")[0], prov: of("prov")[0] })[S.view]; }
function doExport() { const r = curReport(); if (!r) return flash("Nothing to export"); const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(r.j, null, 2)], { type: "application/json" })); a.download = r.name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); flash("Exported " + r.name); }
$("#pick").onchange = async (e) => { let n = 0; for (const f of e.target.files) { try { if (addReport(f.name, JSON.parse(await f.text()))) n++; } catch (x) { } } S.pool = buildPool(); flash(n ? "Opened " + n + " report" + (n > 1 ? "s" : "") : "Not a Grok The Block report"); render(); };
window.GTB.open = () => $("#pick").click();
$("#openBtn").onclick = () => $("#pick").click();

/* ---------------- investigations (ui/investigate.js) ---------------- */
const INV = window.GTB_INV_MAKE ? window.GTB_INV_MAKE({ $, $$, esc, iso, age, head, flash, render, S, EV, EV_SIGS, REPORTS, of, isSynRep, anomalyItems, coverageRows, catName, safeExternalUrl, extLink, SEVC, C, go, sq }) : null;
window.GTB.inv = INV;
/* ---------------- boot ---------------- */
addEventListener("resize", () => { const w = wide(); if ((w ? "wide" : "narrow") !== $("#root").className) render(); });
RM.addEventListener && RM.addEventListener("change", render);
renderFeed();
const h = decU(location.hash.slice(1));
if (h.startsWith("f/")) goFeat(h.slice(2), false); else if (INV && h.startsWith("investigate/")) INV.open(h.slice(12)); else if (INV && (h === "pulse" || h === "watch")) go(h); else if (h.includes("/")) { const [v, sym] = h.split("/"); const t = targets().find(x => x.view === v && x.title.replace("$", "") === sym.split("|")[0] && (v !== "asset" || !sym.includes("|") || x.set === sym.split("|")[1])); if (t) scan(t.id); else go(v); } else if (VIEWS.some(([k]) => k === h)) go(h); else render();
requestAnimationFrame(frame);
window.GTB.ready = true;
})();
