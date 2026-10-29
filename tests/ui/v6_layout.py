"""Shared v6 layout checks (Chromium EMULATION via Playwright). Used by ui_v6.py and ui_v6_sweep.py."""
import copy, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]

CHECK_JS = r"""(stageEnd) => {
  const out = [], vw = innerWidth, de = document.documentElement;
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && +cs.opacity !== 0 && !e.closest('[hidden]'); };
  if (de.scrollWidth > vw + 1) out.push('page horizontal scroll ' + de.scrollWidth + '>' + vw);
  const clipped = (e) => { for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) { const ox = getComputedStyle(a).overflowX; if (ox !== 'visible') return true; } return false; };
  const off = [...document.querySelectorAll('body *')].filter(e => !['SCRIPT','STYLE'].includes(e.tagName) && vis(e) && !e.closest('#feed[aria-hidden=true]')).filter(e => { const r = e.getBoundingClientRect(); return (r.right > vw + 1 || r.left < -1) && !clipped(e); });
  off.slice(0, 3).forEach(e => out.push('offscreen ' + e.tagName + '#' + e.id + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().left) + '..' + Math.round(e.getBoundingClientRect().right)));
  // text cut by an ellipsis/overflow anywhere visible (headings, chips, rows)
  const W = document.getElementById('stageWrap');
  if (stageEnd && W && !W.hidden) {
    const s = W.getBoundingClientRect(), home = GTB.S.view === 'home';
    const R = (sel) => { const e = document.querySelector(sel); return vis(e) ? e.getBoundingClientRect() : null; };
    const boxes = home ? { home: R('#home'), dlg: R('#dlg') } : { result: R('#resWord'), stats: R('#stats'), verdict: R('#vdBox'), dlg: R('#dlg') };
    for (const [k, r] of Object.entries(boxes)) { if (!r) { out.push('missing ' + k); continue; } if (r.left < s.left - 2 || r.right > s.right + 2 || r.top < s.top - 2 || r.bottom > s.bottom + 2) out.push(k + ' outside stage [' + [r.left - s.left, r.top - s.top, r.right - s.left, r.bottom - s.top].map(Math.round) + '] stage ' + Math.round(s.width) + 'x' + Math.round(s.height)); }
    const ks = Object.keys(boxes); const ov = (a, b) => a && b && a.left < b.right - 2 && b.left < a.right - 2 && a.top < b.bottom - 2 && b.top < a.bottom - 2;
    for (let i = 0; i < ks.length; i++) for (let j = i + 1; j < ks.length; j++) if (!(ks[i] === 'stats' && ks[j] === 'verdict') && ov(boxes[ks[i]], boxes[ks[j]])) out.push('overlap ' + ks[i] + '/' + ks[j]);
    document.querySelectorAll('#srows .srow .k, #srows .srow .v, #vdTx').forEach(e => { if (vis(e) && e.scrollWidth > e.clientWidth + 1) out.push('truncated "' + e.textContent + '"'); });
    if (home) { const h = document.getElementById('homeH1'); if (h.scrollWidth > h.clientWidth + 2) out.push('home title overflows'); }
    const b = (document.getElementById('stage').dataset.bot || '').split(',').map(Number);
    if (b.length === 3 && b.every(isFinite)) {
      const [cx, cy, r] = [s.left + b[0], s.top + b[1], b[2]];
      if (cx - r < s.left - 2 || cx + r > s.right + 2 || cy - r < s.top - 2 || cy + r > s.bottom + 2) out.push('bot outside stage');
      for (const [k, q] of Object.entries(boxes)) if (q) { const nx = Math.max(q.left, Math.min(cx, q.right)), ny = Math.max(q.top, Math.min(cy, q.bottom)); if ((nx - cx) ** 2 + (ny - cy) ** 2 < (r - 3) ** 2) out.push('bot intersects ' + k); }
      if (r < 18) out.push('bot too small r=' + r);
    } else out.push('bot position unknown');
  }
  return out;
}"""

def variants():
    """Synthetic edge-case reports derived from the repo's synthetic example (never private fixtures)."""
    j = json.loads((ROOT / "examples/scan-SYNTHING-SyndEg.json").read_text()); j = j.get("result", j)
    long = copy.deepcopy(j); long["token"]["symbol"] = "SYNTHETICEXTRALONGTICKERNAME2026"; long["token"]["mint"] = "Syn" + "x" * 84
    long["assessment"]["severity"] = "MEDIUM"; long["organicScore"] = 55
    for w in long["wallets"][:3]: w["address"] = "Syn" + "L" * 80
    miss = copy.deepcopy(j); miss["token"] = {"symbol": "SYNMISS"}
    for k in ("assessment", "verdict", "lpMonitor", "bundleSignal", "scanWindow", "counts"): miss.pop(k, None)
    empty = {"organicScore": 0, "token": {"symbol": "SYNEMPTY"}}
    return {"long": long, "missing": miss, "empty": empty}

def inject(pg):
    for name, j in variants().items(): pg.evaluate("([n,j])=>GTB.addReport('variant-'+n+'.json', j)", [name, j])

def settle(pg, ms=150):
    pg.wait_for_timeout(ms)
    pg.wait_for_function("+document.getElementById('stage').dataset.frames>0 || document.getElementById('stage').dataset.webgl==='fallback'", timeout=15000)

def end_state(pg, tid):
    pg.evaluate("id=>{GTB.scan(id,true);GTB.finish()}", tid); pg.wait_for_timeout(120)
    pg.wait_for_function("document.getElementById('vdBox').dataset.landed==='1'", timeout=15000)
    f0 = pg.evaluate("+document.getElementById('stage').dataset.frames||0")
    try: pg.wait_for_function(f"(+document.getElementById('stage').dataset.frames||0)>{f0}+2 || document.getElementById('stage').dataset.webgl==='fallback'", timeout=15000)
    except Exception: pass

def check(pg, stage_end=True): return pg.evaluate(CHECK_JS, stage_end)
