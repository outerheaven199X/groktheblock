/* Card Explorer (TCGs). Image-first browser over the LOCAL artwork cache written by tools/sync_tcg_art.py (ui/cache/tcg, gitignored).
   No network: images are same-origin cache files; remote image URLs never reach the browser. Prices are never shown as a table:
   a card only shows the derived observations bound to its exact tracked printing (Scryfall id + set + collector number + language)
   and finish. Other printings with the same name show none. Loaded before app.js; uses its helpers at call time. */
"use strict";
window.GTB_TCG_MAKE = (H) => {
const { $, $$, esc, head, askBtn, iso, render, S, EV, EV_SIGS, REG } = H;
const TCG = { q: "", set: "all", rarity: "all", lang: "all", fin: "all", game: "mtg", sel: null, face: 0, STALE_DAYS: 7 };
function tcgData() {
  const C = window.GTB_TCG_CACHE;
  if (C && Array.isArray(C.groups)) return { C, synced: true };
  // Unsynced checkout: tracked printings from committed derived data, no artwork, text fallback only.
  const groups = (EV.live.assets || []).filter(a => a.universe === "mtg").map(a => {
    const m = /scryfall\.com\/card\/([^/]+)\/([^/]+)\//.exec(a.url || "") || [];
    const p = { key: "scryfall:?:" + (m[1] || "?") + ":" + (m[2] || "?") + ":en", id: null, name: a.name, set: m[1] || "?", set_name: null, cn: m[2] || "?", lang: "en", rarity: null, finishes: ["nonfoil"], variant: [], kind: "tracked", image_status: "unknown", faces: [{ face: 0, name: a.name, img: {}, state: "not-synced" }], uri: a.url, tracked: { asset: a.name, finish: "nonfoil" } };
    return { oracle_id: a.name, name: a.name, printings: [p] };
  });
  return { C: { groups, syncedAt: null, adapters: REG.TCG_GAMES, artworkRights: "BLOCKED", attribution: "Card data: Scryfall (scryfall.com)." }, synced: false };
}
const tcgAge = (ts) => { const h = (Date.now() / 1000 - ts) / 3600; return h < 1 ? "under 1h ago" : h < 48 ? Math.round(h) + "h ago" : Math.round(h / 24) + " days ago"; };
const TCG_KIND = [["tracked", "Tracked printing"], ["default", "Default printing"], ["alternate art", "Alternate art"], ["print variant", "Print variants"], ["reprint", "Reprints"]];
const tcgAll = (C) => C.groups.flatMap(g => g.printings.map(p => ({ g, p })));
function tcgMatch(p, g) {
  const q = TCG.q.trim().toLowerCase();
  if (TCG.set !== "all" && p.set !== TCG.set) return false;
  if (TCG.rarity !== "all" && p.rarity !== TCG.rarity) return false;
  if (TCG.lang !== "all" && p.lang !== TCG.lang) return false;
  if (TCG.fin !== "all" && !(p.finishes || []).includes(TCG.fin) && p.kind !== TCG.fin) return false;
  if (!q) return true;
  return q.split(/\s+/).every(w => (g.name || "").toLowerCase().includes(w) || p.set === w || String(p.cn).toLowerCase() === w || (p.set + "/" + p.cn) === w || (p.set + " " + p.cn) === w || (p.set_name || "").toLowerCase().includes(w));
}
function tcgFaceState(p, f) {
  if (p.image_status === "placeholder") return ["placeholder", "No real artwork at the provider yet (placeholder)"];
  if (p.image_status === "missing" || f.state === "provider-missing") return ["missing", "No artwork from the provider"];
  if (f.state === "not-synced") return ["unsynced", "Artwork not synced: run python3 tools/sync_tcg_art.py"];
  if (!f.img || !f.img.small) return ["uncached", "Artwork not cached for this printing"];
  return ["ok", ""];
}
function tcgPH(p, f, why, big) {
  return `<div class="tph${big ? " big" : ""}" role="img" aria-label="${esc((f && f.name || p.name) + ": " + why)}"><span class="tn disp">${esc((f && f.name) || p.name)}</span><span class="ts">${esc(String(p.set).toUpperCase())} · #${esc(p.cn)} · ${esc(p.lang)}</span><span class="tw">${esc(why)}</span>${big && p.uri ? `<a class="tl" href="${esc(p.uri)}" target="_blank" rel="noopener noreferrer">Source: Scryfall</a>` : ""}</div>`;
}
function tcgImg(p, fi, size, big) {
  const f = p.faces[fi] || p.faces[0]; const [st, why] = tcgFaceState(p, f);
  if (st !== "ok") return tcgPH(p, f, why, big);
  const src = (size === "normal" && f.img.normal) || f.img.small;
  // data-key binds the element to ONE printing + face; tests assert the src belongs to that key.
  return `<span class="timg ld${big ? " big" : ""}"><img src="${esc(src)}" alt="${esc((f.name || p.name) + ", " + String(p.set).toUpperCase() + " #" + p.cn + (p.faces.length > 1 ? ", face " + (fi + 1) : ""))}" loading="${big ? "eager" : "lazy"}" decoding="async" data-key="${esc(p.key)}" data-face="${fi}" width="${big ? 488 : 146}" height="${big ? 680 : 204}"></span>`;
}
// Image load/error (capture phase): drop the skeleton, or swap a missing cache file for the text fallback.
document.addEventListener("load", (e) => { const i = e.target; if (i.tagName === "IMG" && i.dataset.key) i.parentElement.classList.remove("ld"); }, true);
document.addEventListener("error", (e) => {
  const i = e.target; if (i.tagName !== "IMG" || !i.dataset.key) return;
  const hit = tcgAll(tcgData().C).find(x => x.p.key === i.dataset.key); if (!hit) return;
  const f = hit.p.faces[+i.dataset.face] || hit.p.faces[0]; i.parentElement.outerHTML = tcgPH(hit.p, f, "Cache file missing: re-run the artwork sync", i.parentElement.classList.contains("big"));
}, true);
function tcgObs(p) {
  if (!p.tracked) return null;
  const nm = p.tracked.asset;
  const probes = (EV.live.probes || []).filter(x => x.module === "mtg" && x.asset === nm);
  const sigs = EV_SIGS.filter(x => x.set === "live" && x.s && (x.s.instrument === nm || (x.s.subject || {}).name === nm || JSON.stringify(x.s.metrics || {}).includes(JSON.stringify(nm))));
  return { nm, probes, sigs };
}
function vTcg(P) {
  const { C, synced } = tcgData(); const all = tcgAll(C);
  const ageDays = C.syncedAt ? (Date.now() / 1000 - C.syncedAt) / 86400 : null, stale = ageDays != null && ageDays > TCG.STALE_DAYS;
  const cacheTxt = !synced ? "artwork not synced" : stale ? "cache stale (" + Math.floor(ageDays) + " days)" : "cache synced " + tcgAge(C.syncedAt);
  head("Card Explorer", "TCGs", [C.groups.length + " cards", all.length + " printings", cacheTxt], ["TCGs", "Card Explorer", "tcg:explorer", synced ? "tcg-explorer-cache // " + iso(C.syncedAt) : "committed derived data", ["Cards: " + C.groups.length, "Printings: " + all.length, "Artwork rights: " + C.artworkRights]]);
  const opts = (k, lbl) => { const vs = [...new Set(all.map(x => x.p[k]).filter(Boolean))].sort(); return `<label class="tf"><span>${lbl}</span><select data-tf="${k === "set" ? "set" : k === "rarity" ? "rarity" : "lang"}"><option value="all">All</option>${vs.map(v => `<option value="${esc(v)}"${TCG[k === "set" ? "set" : k === "rarity" ? "rarity" : "lang"] === v ? " selected" : ""}>${esc(k === "set" ? v.toUpperCase() : v)}</option>`).join("")}</select></label>`; };
  const games = (REG.TCG_GAMES || C.adapters || []).map(a => `<option value="${esc(a.game)}"${a.active ? "" : " disabled"}${TCG.game === a.game ? " selected" : ""}>${esc(a.name)}${a.active ? "" : " (unavailable: rights not cleared)"}</option>`).join("");
  const hits = C.groups.map(g => ({ g, ps: g.printings.filter(p => tcgMatch(p, g)) })).filter(x => x.ps.length);
  const sel = TCG.sel && all.find(x => x.p.key === TCG.sel);
  const tile = ({ g, ps }) => { const p = ps[0]; const n = g.printings.length; return `<button class="tcard${sel && sel.g === g ? " on" : ""}" data-tkey="${esc(p.key)}" aria-label="${esc(g.name + ", " + String(p.set).toUpperCase() + " #" + p.cn + ", " + n + (n === 1 ? " printing" : " printings"))}">${tcgImg(p, 0, "small", false)}<span class="tcap"><span class="tnm">${esc(g.name)}</span><span class="tmt">${esc(String(p.set).toUpperCase())} #${esc(p.cn)} · ${n}P${p.tracked ? ` · <b>tracked</b>` : ""}</span></span></button>`; };
  P.innerHTML = `<div class="tcgx">
  <div class="card tbar"><label class="tf tq"><span>Search</span><input id="tcgQ" type="search" placeholder="Name, set code or collector number" value="${esc(TCG.q)}" autocomplete="off" aria-label="Search cards by name, set or collector number"></label>
  <label class="tf"><span>Game</span><select data-tf="game">${games}</select></label>${opts("set", "Set")}${opts("rarity", "Rarity")}${opts("lang", "Language")}
  <label class="tf"><span>Printing</span><select data-tf="fin"><option value="all">All</option>${["nonfoil", "foil", "etched"].map(v => `<option value="${v}"${TCG.fin === v ? " selected" : ""}>${v}</option>`).join("")}${TCG_KIND.slice(2).map(([k, l]) => `<option value="${esc(k)}"${TCG.fin === k ? " selected" : ""}>${esc(l)}</option>`).join("")}</select></label></div>
  <div class="tstat" id="tcgStat"><span>${esc(C.attribution || "")}</span><span>Cache: ${esc(cacheTxt)}${synced ? " · " + esc((C.counts || {}).thumbs ?? 0) + " thumbnails" : ""}</span><span class="tbk">Artwork rights: ${esc(C.artworkRights || "BLOCKED")}</span><span>${synced ? "Local cache only; not redistributed" : "Text fallback: no artwork in this checkout"}</span></div>
  ${sel ? tcgDetail(sel, C) : ""}
  <div class="tgrid" role="list" aria-label="Cards">${hits.map(h => `<div role="listitem">${tile(h)}</div>`).join("") || `<div class="empty">No card matches. Search covers ${C.groups.length} synced cards only.</div>`}</div></div>`;
  const q = $("#tcgQ"); q.oninput = () => { TCG.q = q.value; const pos = q.selectionStart; render(); const n = $("#tcgQ"); n.focus(); n.setSelectionRange(pos, pos); };
  $$("[data-tf]", P).forEach(s => s.onchange = () => { TCG[s.dataset.tf] = s.value; render(); const n = $(`[data-tf="${s.dataset.tf}"]`); n && n.focus(); });
}
function tcgDetail({ g, p }, C) {
  const fi = Math.min(TCG.face, p.faces.length - 1), o = tcgObs(p);
  const groups = TCG_KIND.map(([k, l]) => [l, g.printings.filter(x => x.kind === k)]).filter(([, xs]) => xs.length);
  const obsHTML = o ? `<dl class="kv"><dt>Bound to</dt><dd>${esc(String(p.set).toUpperCase())} #${esc(p.cn)} · ${esc(p.lang)} · ${esc(o.nm === p.name ? "" : o.nm + " · ")}finish ${esc(p.tracked.finish)}</dd>${o.probes.map(x => `<dt>${esc(x.type)}</dt><dd>${esc(x.state === "measured" && x.ratio != null ? x.ratio.toFixed(2) + "× threshold" : x.reason || x.state)}</dd>`).join("")}<dt>Signals</dt><dd>${o.sigs.length ? o.sigs.length + " flagged" : "none flagged"}</dd></dl><div class="lim">One daily snapshot is not a price history. Observations are derived numbers, not a price table.</div>`
    : `<div class="lim">No market observation for this printing. Observations are kept on the exact tracked printing and finish; they are never copied to another printing of the same name.</div>`;
  const tr = g.printings.find(x => x.tracked);
  const ask = askBtn("Ask about this", ["TCGs // Card Explorer", p.name + " (" + String(p.set).toUpperCase() + " #" + p.cn + ")", p.key, "tcg-explorer-cache", ["Set: " + (p.set_name || p.set), "Collector #: " + p.cn, "Language: " + p.lang, "Finishes: " + (p.finishes || []).join(", "), "Kind: " + p.kind, "Image status: " + p.image_status, o ? "Market observations: " + o.probes.length + " checks, " + o.sigs.length + " flagged" : "No market observation for this printing"]], "btn y", "Ask Grok Bot about this card");
  return `<section class="card tdet" id="tcgDet" aria-label="${esc(p.name)} detail" tabindex="-1">
  <div class="tdl">${tcgImg(p, fi, "normal", true)}${p.faces.length > 1 ? `<div class="chips tfc" role="group" aria-label="Card face">${p.faces.map((f, i) => `<button class="chip" data-tface="${i}" aria-pressed="${i === fi}">${i === 0 ? "Front" : "Back"}: ${esc(f.name || "")}</button>`).join("")}</div>` : ""}</div>
  <div class="tdr"><div class="tdh"><h2 class="disp">${esc(p.faces.length > 1 ? (p.faces[fi].name || p.name) : p.name)}</h2><button class="btn" id="tcgClose" aria-label="Close card detail">Close</button></div>
  <dl class="kv"><dt>Set</dt><dd>${esc(p.set_name || "")} (${esc(String(p.set).toUpperCase())})</dd><dt>Collector #</dt><dd>${esc(p.cn)}</dd><dt>Language</dt><dd>${esc(p.lang)}</dd><dt>Rarity</dt><dd>${esc(p.rarity || "—")}</dd><dt>Finishes</dt><dd>${esc((p.finishes || []).join(", ") || "—")}</dd><dt>Printing</dt><dd>${esc(p.kind)}${p.variant && p.variant.length ? " · " + esc(p.variant.join(", ")) : ""}${p.digital ? " · digital (MTGO)" : ""}</dd><dt>Artist</dt><dd>${esc(p.artist || "—")}</dd><dt>Identity</dt><dd class="mono">${esc(p.key)}</dd><dt>Image</dt><dd>${esc(p.image_status)} · ${esc(tcgFaceState(p, p.faces[fi])[0] === "ok" ? (p.faces[fi].img.normal ? "local cache, 488×680" : "local cache, thumbnail only (larger image not fetched)") : tcgFaceState(p, p.faces[fi])[1])}</dd><dt>Provenance</dt><dd>Scryfall${C.syncedAt ? ", synced " + esc(iso(C.syncedAt)) : ""}${p.uri ? ` · <a href="${esc(p.uri)}" target="_blank" rel="noopener noreferrer">source</a>` : ""}</dd><dt>Artwork rights</dt><dd class="tbk">${esc(C.artworkRights || "BLOCKED")} for redistribution</dd></dl>
  <h3 class="disp th3">Market observations</h3>${obsHTML}
  <div class="tact">${tr ? `<button class="btn y" id="tcgAnalyze" data-asset="${esc(tr.tracked.asset)}">Analyze market${tr !== p ? " (tracked printing)" : ""}</button>` : `<button class="btn" disabled>Not price-tracked</button>`}${ask}</div>
  <h3 class="disp th3">Printings</h3><div class="tpr">${groups.map(([l, xs]) => `<div class="tpg"><div class="tpl">${esc(l)} · ${xs.length}</div><div class="tps">${xs.map(x => `<button class="tpb" data-tkey="${esc(x.key)}" aria-pressed="${x.key === p.key}" aria-label="${esc(x.name + ", " + (x.set_name || x.set) + " #" + x.cn + ", " + x.kind)}">${tcgImg(x, 0, "small", false)}<span>${esc(String(x.set).toUpperCase())} #${esc(x.cn)}</span></button>`).join("")}</div></div>`).join("")}</div></div></section>`;
}
document.addEventListener("click", (e) => {
  if (S.view !== "tcg") return;
  const k = e.target.closest("[data-tkey]"); if (k) { TCG.sel = k.dataset.tkey; TCG.face = 0; render(); const d = $("#tcgDet"); if (d) { d.focus({ preventScroll: true }); d.scrollIntoView({ block: "nearest" }); } return; }
  const f = e.target.closest("[data-tface]"); if (f) { TCG.face = +f.dataset.tface; render(); const b = $(`[data-tface="${TCG.face}"]`); b && b.focus(); return; }
  if (e.target.closest("#tcgClose")) { const was = TCG.sel; TCG.sel = null; render(); const t = $(`.tcard[data-tkey="${CSS.escape(was)}"]`) || $("#tcgQ"); t && t.focus(); return; }
  const a = e.target.closest("#tcgAnalyze"); if (a) { GTB.analyzeCard(a.dataset.asset); }
});
document.addEventListener("keydown", (e) => { if (S.view === "tcg" && e.key === "Escape" && TCG.sel && !document.querySelector(".navm:not([hidden])")) { $("#tcgClose") && $("#tcgClose").click(); } });
return { vTcg, tcgData, TCG };
};
