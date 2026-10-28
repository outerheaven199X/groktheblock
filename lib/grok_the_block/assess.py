"""Investigation-first assessment shared by the scripts, the dashboard and Pages.

Every finding carries a `basis`:
  observed  - read directly from chain or a provider (transfers, authorities, liquidity)
  heuristic - a rule-based label (INSIDER/SNIPER/AGENT/COPY classes, verdicts, LP_REMOVE)
  inferred  - a relationship guessed from timing or funding (copy-trading, X clusters)
`nextActions` carry both a plain-English request for Grok Bot (`ask`) and the local
command (`cli`). Neither runs anything; the dashboard only copies text.
"""
from __future__ import annotations

RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
SOLSCAN = "https://solscan.io"


def _short(a: str | None) -> str:
    return a[:4] + "…" + a[-4:] if a and len(a) > 12 else (a or "")


def action(id_, label, why, ask, cli, target=None):
    return {"id": id_, "label": label, "why": why, "ask": ask, "cli": cli, "target": target}


def _finish(findings, coverage, actions, subject):
    findings.sort(key=lambda f: -RANK.get(f["severity"], 0))
    lead = findings[0] if findings else {"severity": "INFO", "text": "Nothing notable in the analyzed window.", "basis": "observed", "evidence": []}
    return {"subject": subject, "severity": lead["severity"], "lead": lead, "findings": findings,
            "coverage": coverage, "nextActions": actions}


def providers_cov(prov: dict) -> list[dict]:
    return [{"name": k, "ok": v.get("ok", False), "detail": v.get("detail", "")} for k, v in sorted(prov.items())]


def assess_scan(r: dict, providers: dict | None = None, history_tokens: int | None = None) -> dict:
    t, b, c, sw = r["token"], r.get("bundleSignal") or {}, r["counts"], r.get("scanWindow") or {}
    lp = r.get("lpMonitor") or {}; rc = lp.get("rugcheck") or {}
    sym, mint = t["symbol"], t["mint"]
    total = sum(c.values()) or 1
    F = []
    reached = bool(sw.get("reachedLaunch"))
    if b.get("valid") and b.get("block0SupplyBoughtPct") is not None and b["block0SupplyBoughtPct"] >= 10:
        pct = b["block0SupplyBoughtPct"]
        F.append({"id": "bundle", "severity": b.get("severity") or "MEDIUM", "basis": "observed",
                  "text": f"{b['block0Buyers']} wallets held {pct:.1f}% of supply at the end of the launch slot, and {b['block0BuyersAlreadySoldPct']}% of them have since sold out.",
                  "why": (f"The organic score ({r['organicScore']}) counts wallets: {c['ORGANIC']} of {total} look organic. "
                          f"It does not weigh how much supply each wallet holds, so many small buyers cannot offset a few wallets that took {pct:.0f}% of supply in the first slot.")
                  if r["organicScore"] >= 65 else None,
                  "evidence": [{"label": f"{_short(w)} launch-slot buyer", "kind": "wallet", "address": w, "url": f"{SOLSCAN}/account/{w}"} for w in b.get("wallets", [])[:8]]})
    if not reached:
        F.append({"id": "coverage", "severity": "MEDIUM", "basis": "observed",
                  "text": "The scan did not reach the token's launch, so INSIDER and SNIPER labels and the bundle signal are unreliable.", "evidence": []})
    if c.get("INSIDER", 0):
        top = sorted([w for w in r["wallets"] if w["type"] == "INSIDER"], key=lambda w: -w["supplyPercent"])
        F.append({"id": "insiders", "severity": "HIGH" if c["INSIDER"] >= 5 else "MEDIUM", "basis": "heuristic",
                  "text": f"{c['INSIDER']} wallets match the INSIDER rule (bought in blocks 0–1 or were funded by the deployer); together the top ones hold {sum(w['supplyPercent'] for w in top[:10]):.1f}% of supply.",
                  "evidence": [{"label": f"{_short(w['address'])} {w['supplyPercent']:.1f}% · block {w['entryBlock']}", "kind": "wallet", "address": w["address"], "url": f"{SOLSCAN}/account/{w['address']}"} for w in top[:5]]})
    if r.get("copyNetwork"):
        cn = r["copyNetwork"]
        F.append({"id": "copy", "severity": "MEDIUM", "basis": "inferred",
                  "text": f"{len(cn)} wallet{'s' if len(cn) > 1 else ''} repeatedly bought 3–30 s after the same leader, a copy-trading or shared-control pattern.",
                  "evidence": [{"label": f"{_short(x['leader'])} → {_short(x['follower'])} · {x['avgDelaySeconds']}s · {x['matchCount']} matches", "kind": "wallet", "address": x["follower"], "url": f"{SOLSCAN}/account/{x['follower']}"} for x in cn[:5]]})
    if rc.get("available"):
        if rc.get("mintAuthority") or rc.get("freezeAuthority"):
            F.append({"id": "authority", "severity": "HIGH", "basis": "observed",
                      "text": "Mint or freeze authority is still enabled: supply can be inflated or holders frozen.",
                      "evidence": [{"label": "RugCheck report", "kind": "link", "url": f"https://rugcheck.xyz/tokens/{mint}"}]})
        mk = rc.get("markets") or []
        if mk and (mk[0].get("lpLockedPct") or 0) < 50:
            F.append({"id": "lp", "severity": "HIGH", "basis": "observed", "text": f"Only {mk[0].get('lpLockedPct') or 0:.0f}% of the main pool's LP is locked or burned.",
                      "evidence": [{"label": "RugCheck report", "kind": "link", "url": f"https://rugcheck.xyz/tokens/{mint}"}]})
    dep = next((w for w in r["wallets"] if w.get("isDeployer")), None)
    if not F:
        F.append({"id": "organic", "severity": "LOW", "basis": "heuristic",
                  "text": f"No concentration signals: {c['ORGANIC']} of {total} launch-window wallets look organic and no launch-slot bundle was found.", "evidence": []})
    limits = [{"kind": "approximate", "text": "SOL flows are realized SOL in the analyzed window, not full profit and loss."},
              {"kind": "heuristic", "text": "Wallet classes are timing rules ported from CryptOSINT, not identities."}]
    if history_tokens is not None:
        limits.append({"kind": "local-only", "text": f"Reputation and prior history come only from {history_tokens} token scans on this machine."})
    if not reached:
        limits.insert(0, {"kind": "incomplete", "text": "Launch history not reached: 'block 0' is the oldest transaction found, so early-buyer labels and the bundle signal do not apply."})
    if not rc.get("available"):
        limits.append({"kind": "missing", "text": "RugCheck data unavailable: authorities, LP lock and holder risks are unknown, not clean."})
    if not lp.get("pools"):
        limits.append({"kind": "missing", "text": "DexScreener data unavailable: market cap, liquidity and pools are unknown."})
    coverage = {"reachedLaunch": reached, "transactionsAnalyzed": sw.get("transactionsAnalyzed"), "dataSource": sw.get("dataSource"),
                "window": {"first": sw.get("firstTx"), "last": sw.get("lastTx")}, "providers": providers_cov(providers or {}), "limits": limits}
    A = []
    big = sorted([w for w in r["wallets"] if w["type"] in ("INSIDER", "AGENT", "SNIPER")], key=lambda w: -w["supplyPercent"])
    if big:
        w = big[0]["address"]
        A.append(action("wallet-top", f"Scan the largest flagged wallet {_short(w)}", "See whether it repeats this pattern on other launches.",
                        f"Scan wallet {w} and tell me if it enters other launches at block 0.", f"python skills/wallet-scan/scripts/wallet_scan.py {w}", {"kind": "wallet", "key": w}))
    if dep:
        A.append(action("wallet-dev", f"Scan the deployer {_short(dep['address'])}", "Deployers that launch and exit repeatedly are a strong pattern.",
                        f"Scan the deployer wallet {dep['address']} for other tokens it launched.", f"python skills/wallet-scan/scripts/wallet_scan.py {dep['address']}", {"kind": "wallet", "key": dep["address"]}))
    A.append(action("replay", f"Replay ${sym}'s timeline", "Shows when insiders bought and sold relative to organic buyers.",
                    f"Replay the rug timeline for {mint}.", f"python skills/rug-replay/scripts/rug_replay.py {mint}", {"kind": "replay", "key": mint}))
    A.append(action("shill", f"Check X coordination for ${sym}", "Looks for clustered promo accounts posting the contract address.",
                    f"Who is shilling {mint} on X? Check for coordinated accounts.", f"(Grok Bot only: needs the X tools) shill-network for {mint}", {"kind": "shill", "key": mint}))
    if r.get("copyNetwork"):
        A.append(action("copy", "Open the copy-trade network", "Leader and follower wallets with timing.", "Show the copy-trade network for this scan.",
                        f"python skills/copy-network/scripts/copy_network.py out/scan-{sym}-{mint[:6]}.json", {"kind": "copy", "key": mint}))
    A.append(action("watch", f"Watch ${sym} for changes", "Alerts on liquidity, authority, verdict and large insider moves since the last scan.",
                    f"Watch {mint} and alert me on material changes.", f"python skills/watch-token/scripts/watch_token.py add {mint}", {"kind": "watch", "key": mint}))
    return _finish(F, coverage, A, {"kind": "token", "mint": mint, "symbol": sym, "name": t.get("name")})


def assess_wallet(r: dict) -> dict:
    w, toks = r["wallet"], r["tokens"]
    addr = w["address"]
    ins = [t for t in toks if t["classification"] in ("INSIDER", "SNIPER", "AGENT")]
    b0 = [t for t in toks if t.get("entryBlock") == 0]
    F = []
    if toks and len(ins) / len(toks) >= 0.5:
        F.append({"id": "pattern", "severity": "CRITICAL" if len(ins) >= 10 else "HIGH", "basis": "heuristic",
                  "text": f"Flagged INSIDER, SNIPER or AGENT on {len(ins)} of {len(toks)} tokens, entering at block 0 on {len(b0)}: a repeated launch-and-exit pattern.",
                  "evidence": [{"label": f"{t['symbol'].strip()} · {t['classification']} · {t['pnlSol']:+.2f} SOL", "kind": "token", "mint": t["mint"], "url": f"https://dexscreener.com/solana/{t['mint']}"} for t in sorted(ins, key=lambda t: -abs(t['pnlSol']))[:6]]})
    fw = (r.get("associations") or {}).get("fundedWallets") or []
    if fw:
        F.append({"id": "funded", "severity": "MEDIUM", "basis": "inferred", "text": f"Sent SOL to {len(fw)} other wallets in the window; they may be operated together.",
                  "evidence": [{"label": f"{_short(f['address'])} · {f['amountSol']:.2f} SOL", "kind": "wallet", "address": f["address"], "url": f"{SOLSCAN}/account/{f['address']}"} for f in fw[:6]]})
    F.append({"id": "pnl", "severity": "INFO", "basis": "observed", "text": f"Realized {w['totalPnlSol']:+.2f} SOL across {w['totalTokensTouched']} tokens, win rate {w['winRate']}%.", "evidence": []})
    limits = [{"kind": "approximate", "text": "PnL is realized SOL flow in the analyzed window; open positions count as zero."},
              {"kind": "local-only", "text": "Reputation uses only scans stored on this machine."}]
    if not w.get("historyComplete", True):
        limits.append({"kind": "incomplete", "text": "Wallet history was longer than the scan window; age and early activity are partial."})
    cov = {"transactionsAnalyzed": (r.get("window") or {}).get("transactionsAnalyzed"), "window": r.get("window"), "limits": limits, "providers": []}
    A = []
    if ins:
        t = sorted(ins, key=lambda t: -abs(t["pnlSol"]))[0]
        A.append(action("token", f"Scan {t['symbol'].strip()}, its biggest flagged trade", "See who else entered with it at launch.",
                        f"Scan token {t['mint']} and check for a launch-slot bundle.", f"python skills/token-scan/scripts/token_scan.py {t['mint']}", {"kind": "scan", "key": t["mint"]}))
    if fw:
        A.append(action("funded", f"Scan funded wallet {_short(fw[0]['address'])}", "Check whether funded wallets trade the same launches.",
                        f"Scan wallet {fw[0]['address']}.", f"python skills/wallet-scan/scripts/wallet_scan.py {fw[0]['address']}", {"kind": "wallet", "key": fw[0]["address"]}))
    A.append(action("board", "See where it ranks among repeat offenders", "Leaderboard across all tokens scanned here.", "Show the INSIDER leaderboard.",
                    "python skills/leaderboard/scripts/leaderboard.py --type INSIDER", {"kind": "board", "key": "INSIDER"}))
    return _finish(F, cov, A, {"kind": "wallet", "address": addr})


def assess_replay(r: dict) -> dict:
    s, tok, win = r["summary"], r["token"], r.get("window") or {}
    F = []
    m = s["rugMethod"]
    if m == "LP_PULL":
        F.append({"id": "lp", "severity": "CRITICAL", "basis": "heuristic", "text": "Liquidity was pulled by the deployer or an insider.", "evidence": _ev(r, "LP_REMOVE")})
    elif m == "MASS_DUMP":
        F.append({"id": "dump", "severity": "HIGH", "basis": "heuristic", "text": "Several wallets dumped large shares of supply within one minute.", "evidence": _ev(r, "MASS_DUMP") + _ev(r, "LARGE_SELL")})
    ins = [e for e in r["timeline"] if e["type"] == "INSIDER_BUY"]
    if ins:
        tot = sum(e.get("supplyPercent") or 0 for e in ins)
        F.append({"id": "early", "severity": "HIGH" if tot >= 25 else "MEDIUM", "basis": "observed",
                  "text": f"{len(ins)} insider-class wallets bought {tot:.1f}% of supply, starting {ins[0]['relativeTime']} after creation.", "evidence": _ev(r, "INSIDER_BUY")})
    F.append({"id": "flows", "severity": "INFO", "basis": "observed",
              "text": f"In the analyzed window, insider and agent wallets realized about {s['insiderProfitEstimateSol']:.1f} SOL while organic wallets put in a net {s['organicLossEstimateSol']:.1f} SOL.", "evidence": []})
    limits = [{"kind": "approximate", "text": "SOL figures are realized flows in the analyzed window, including open positions."},
              {"kind": "window", "text": f"Lifespan and events cover only the first {win.get('transactionsAnalyzed')} transactions."}]
    if s.get("xPostsMerged"):
        limits.append({"kind": "sampled", "text": f"X posts are a sample of {s['xPostsMerged']} search results, not every post."})
    if not win.get("reachedLaunch"):
        limits.append({"kind": "incomplete", "text": "Launch not reached: the first event is the oldest transaction found, not creation."})
    mint = tok["mint"]
    A = [action("scan", f"Scan ${tok['symbol']}", "Wallet classes, bundle signal and LP status.", f"Scan token {mint}.", f"python skills/token-scan/scripts/token_scan.py {mint}", {"kind": "scan", "key": mint})]
    return _finish(F, {"reachedLaunch": win.get("reachedLaunch"), "transactionsAnalyzed": win.get("transactionsAnalyzed"), "limits": limits, "providers": []}, A,
                   {"kind": "token", "mint": mint, "symbol": tok["symbol"]})


def _ev(r, typ):
    return [{"label": e["detail"][:80], "kind": "tx" if e.get("signature") else "wallet", "address": e.get("wallet"),
             "url": f"{SOLSCAN}/tx/{e['signature']}" if e.get("signature") else (f"{SOLSCAN}/account/{e['wallet']}" if e.get("wallet") else None)}
            for e in r["timeline"] if e["type"] == typ][:6]
