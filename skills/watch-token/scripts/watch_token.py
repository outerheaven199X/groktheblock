#!/usr/bin/env python3
"""Whale watch (polling replacement for the original Helius webhooks).
Each run fetches the newest txs for every watched mint since the last run and
reports large buys/sells, insider moves (wallets flagged by an earlier scan), and LP changes.

usage:
  watch_token.py add <mint|$TICKER> [--min-sol 10]
  watch_token.py remove <mint>
  watch_token.py list
  watch_token.py check [--json]      # run from a routine; prints nothing if no alerts

Each check also takes a snapshot scan and diffs it against the previous *successful*
snapshot (liquidity, authorities, LP lock, verdict, bundle, RugCheck risks). Alerts carry
a dedupe key; a key already alerted is suppressed. Results go to out/watch-<SYM>-<mint6>.json.
A failed provider never replaces the last good snapshot.
"""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from grok_the_block import data as D, history
from grok_the_block.cli import resolve_mint
from grok_the_block.threats import detect_lp_removals
from grok_the_block.cli import OUT

SKILLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS / 'token-scan' / 'scripts'))

WATCH = D.CACHE_DIR / "watchlist.json"


def load(): return json.loads(WATCH.read_text()) if WATCH.exists() else {}
def save(w): D.CACHE_DIR.mkdir(parents=True, exist_ok=True); WATCH.write_text(json.dumps(w, indent=2))


def check(entry, mint):
    sigs, _ = D.get_signatures(mint, max_pages=1, page_size=100, newest_only=True)
    last = entry.get("lastSlot", 0)
    new = [s for s in sigs if s["slot"] > last]
    if not last:  # first run: set baseline, no alerts
        entry["lastSlot"] = max((s["slot"] for s in sigs), default=0); return []
    txs = D.fetch_transactions(new, 100, progress=False)
    entry["lastSlot"] = max([last] + [s["slot"] for s in new])
    flagged = {r["wallet"]: r["classification"] for r in history.load_all() if r["tokenMint"] == mint}
    flows = {}
    alerts = []
    for tx in txs:
        f = D.sol_flows([tx], mint)
        for w, sol in f.items():
            if D.is_program_account(w): continue
            kind = flagged.get(w)
            if abs(sol) >= entry["minSol"] or (kind in ("INSIDER", "AGENT") and sol > 0.5):
                t = "INSIDER_MOVE" if kind == "INSIDER" else ("WHALE_SELL" if sol > 0 else "LARGE_BUY")
                alerts.append({"type": t, "severity": "HIGH" if t != "LARGE_BUY" else "MEDIUM", "tokenSymbol": entry["symbol"], "tokenMint": mint,
                               "wallet": w, "walletType": kind, "amountSol": round(abs(sol), 3), "timestamp": tx["timestamp"],
                               "signature": tx["signature"], "url": f"https://solscan.io/tx/{tx['signature']}",
                               "key": f"{t}:{tx['signature']}:{w}",
                               "evidence": [{"label": "transaction", "url": f"https://solscan.io/tx/{tx['signature']}"}, {"label": D.short(w), "url": f"https://solscan.io/account/{w}"}],
                               "detail": f"{D.short(w)}{' (' + kind + ')' if kind else ''} {'sold for' if sol > 0 else 'bought with'} {abs(sol):.2f} SOL"})
    for x in detect_lp_removals(txs, mint, entry["symbol"]):
        x.setdefault("key", f"LP:{x.get('signature') or x.get('id')}")
        if x.get("signature"): x.setdefault("evidence", [{"label": "transaction", "url": f"https://solscan.io/tx/{x['signature']}"}])
        alerts.append(x)
    return alerts


def snapshot(scan_result: dict) -> dict:
    r = scan_result; lp = r.get("lpMonitor") or {}; rc = lp.get("rugcheck") or {}; b = r.get("bundleSignal") or {}
    mk = rc.get("markets") or []
    return {"at": int(time.time()), "verdict": r["verdict"]["severity"], "organicScore": r["organicScore"],
            "bundleSeverity": b.get("severity"), "bundlePct": b.get("block0SupplyBoughtPct"),
            "liquidityUsd": lp.get("totalLiquidityUsd") if lp.get("pools") else None, "mcap": r["token"].get("mcap") or None,
            "mintAuthority": bool(rc.get("mintAuthority")) if rc.get("available") else None,
            "freezeAuthority": bool(rc.get("freezeAuthority")) if rc.get("available") else None,
            "lpLockedPct": mk[0].get("lpLockedPct") if mk else None,
            "risks": sorted(x["name"] for x in rc.get("risks") or []) if rc.get("available") else None,
            "insiders": r["counts"].get("INSIDER")}


def diff(prev: dict, cur: dict, mint: str, sym: str) -> list[dict]:
    """Material changes between two successful snapshots. None means 'unknown', never 'changed'."""
    ev_rc = {"label": "RugCheck report", "url": f"https://rugcheck.xyz/tokens/{mint}"}
    ev_dx = {"label": "DexScreener", "url": f"https://dexscreener.com/solana/{mint}"}
    out = []
    def add(typ, sev, what, before, after, ev, key=None):
        out.append({"type": typ, "severity": sev, "tokenSymbol": sym, "tokenMint": mint, "detail": what, "before": before, "after": after,
                    "timestamp": cur["at"], "previousScanAt": prev["at"], "basis": "observed", "evidence": ev,
                    "key": key or f"{typ}:{after}"})
    a, b = prev.get("liquidityUsd"), cur.get("liquidityUsd")
    if a and b is not None and a > 0 and abs(b - a) / a >= 0.3:
        drop = b < a
        add("LIQUIDITY_DROP" if drop else "LIQUIDITY_RISE", "HIGH" if drop and b < a * 0.5 else "MEDIUM",
            f"Liquidity {'fell' if drop else 'rose'} {abs(b - a) / a * 100:.0f}% (${a:,.0f} → ${b:,.0f}) since the last successful scan.", a, b, [ev_dx],
            key=f"LIQ:{'down' if drop else 'up'}:{round(b, -3)}")
    for f, lab in (("mintAuthority", "Mint authority"), ("freezeAuthority", "Freeze authority")):
        if prev.get(f) is not None and cur.get(f) is not None and prev[f] != cur[f]:
            add("AUTHORITY_CHANGE", "CRITICAL" if cur[f] else "LOW", f"{lab} {'was re-enabled' if cur[f] else 'was revoked'}.", prev[f], cur[f], [ev_rc], key=f"{f}:{cur[f]}")
    a, b = prev.get("lpLockedPct"), cur.get("lpLockedPct")
    if a is not None and b is not None and a - b >= 10:
        add("LP_UNLOCK", "CRITICAL" if b < 50 else "HIGH", f"Locked LP fell from {a:.0f}% to {b:.0f}%.", a, b, [ev_rc], key=f"LPLOCK:{round(b)}")
    if prev.get("verdict") and cur.get("verdict") and prev["verdict"] != cur["verdict"]:
        add("VERDICT_CHANGE", cur["verdict"], f"Verdict changed {prev['verdict']} → {cur['verdict']}.", prev["verdict"], cur["verdict"], [ev_dx])
    if prev.get("risks") is not None and cur.get("risks") is not None:
        new = sorted(set(cur["risks"]) - set(prev["risks"]))
        if new:
            add("NEW_RISK", "MEDIUM", "RugCheck added: " + ", ".join(new) + ".", prev["risks"], cur["risks"], [ev_rc], key="RISK:" + "|".join(new))
    return out


def run_snapshot(entry: dict, mint: str) -> tuple[list[dict], str]:
    import token_scan
    try:
        res = token_scan.scan(mint, 300, 5, 0, record=False)
    except Exception as e:
        return [], f"snapshot scan failed: {e}"
    failed = [k for k, v in D.provider_report().items() if not v["ok"]]
    if failed:
        return [], "provider failure (" + ", ".join(failed) + "); previous successful snapshot kept"
    cur = snapshot(res)
    prev = entry.get("snapshot")
    entry["snapshot"] = cur
    return (diff(prev, cur, mint, entry["symbol"]) if prev else []), ("baseline set" if not prev else "ok")


def emit(entry: dict, mint: str, alerts: list[dict], status: str) -> tuple[list[dict], int]:
    seen = entry.setdefault("seenKeys", [])
    fresh, dup = [], 0
    for x in alerts:
        if x["key"] in seen: dup += 1; continue
        seen.append(x["key"]); fresh.append(x)
    entry["seenKeys"] = seen[-500:]
    hist = (entry.get("alertHistory") or []) + fresh
    entry["alertHistory"] = hist[-50:]
    entry["lastCheck"] = {"at": int(time.time()), "status": status, "new": len(fresh), "suppressed": dup}
    rep = {"kind": "watch", "token": {"symbol": entry["symbol"], "mint": mint}, "checkedAt": entry["lastCheck"]["at"],
           "status": status, "previousSuccessfulScanAt": (entry.get("prevSnapshotAt")), "snapshot": entry.get("snapshot"),
           "alerts": fresh, "suppressedDuplicates": dup, "recentAlerts": entry["alertHistory"][-20:],
           "notes": ["Changes compare against the previous successful snapshot; a failed provider never counts as a change.",
                     "Each alert has a dedupe key; repeats are suppressed and counted.", "Signals, not accusations."]}
    D.write_json(OUT / f"watch-{entry['symbol']}-{mint[:6]}.json", rep)
    return fresh, dup


def main():
    ap = argparse.ArgumentParser(description='Grok The Block · watch: report material changes in a token since the last successful scan, with evidence.', epilog="An evolution of CryptOSINT by @varien. Read-only."); ap.add_argument("cmd", choices=["add", "remove", "list", "check"]); ap.add_argument("token", nargs="?")
    ap.add_argument("--min-sol", type=float, default=10); ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-snapshot", action="store_true", help="only check new transactions; skip the snapshot diff")
    ap.add_argument("--loop", type=int, default=0, help="keep polling for N seconds (webhook-free fast mode)")
    ap.add_argument("--every", type=int, default=0, help="seconds between polls in --loop (default 10 with Helius, 30 without)")
    a = ap.parse_args(); w = load()
    if a.cmd == "add":
        m = resolve_mint(a.token); meta = D.token_metadata(m)
        w[m] = {"symbol": meta["symbol"], "minSol": a.min_sol, "addedAt": int(time.time()), "lastSlot": 0}
        check(w[m], m); save(w); print(f"Watching ${meta['symbol']} {m} (alerts >= {a.min_sol} SOL)")
    elif a.cmd == "remove":
        w.pop(a.token, None); save(w); print("removed")
    elif a.cmd == "list":
        for m, e in w.items(): print(f"${e['symbol']} {m} min {e['minSol']} SOL")
    else:
        end = time.time() + a.loop
        every = a.every or (10 if D.has_helius() else 30)
        while True:
            run_check(w, a)
            if time.time() + every > end:
                break
            time.sleep(every)


def run_check(w, a):
    if True:
        allx = []
        for m, e in w.items():
            D.PROVIDERS.clear()
            try: tx_alerts = check(e, m)
            except Exception as ex: tx_alerts = []; print(f"tx check failed for {e['symbol']}: {ex}", file=sys.stderr)
            prev_at = (e.get("snapshot") or {}).get("at")
            changes, status = run_snapshot(e, m) if not a.no_snapshot else ([], "snapshot skipped")
            if (e.get("snapshot") or {}).get("at") != prev_at: e["prevSnapshotAt"] = prev_at
            fresh, dup = emit(e, m, tx_alerts + changes, status)
            if not a.json: print(f"${e['symbol']}: {status}; {len(fresh)} new alert(s), {dup} duplicate(s) suppressed")
            allx += fresh
        save(w)
        if a.json: print(json.dumps(allx, indent=2))
        else:
            for x in allx: print(f"[{x['severity']}] {x['type']} ${x['tokenSymbol']}: {x['detail']} {x.get('url', '')}")


if __name__ == "__main__":
    main()
