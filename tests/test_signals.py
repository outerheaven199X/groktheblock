"""Fixture tests for the cross-market signal detectors and watch diff (synthetic data, clearly not live)."""
import json, sys, tempfile
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib"))
from grok_the_block.markets import detectors as X, feed as F

NOW = 1_800_000_000
FX = json.loads((R / "tests/fixtures/signals-fixtures.json").read_text())
ok = 0

def check(cond, msg):
    global ok
    assert cond, msg
    ok += 1

def shape(s):
    for k in ("key", "source", "type", "severity", "basis", "title", "what", "when", "subject", "evidence", "limits", "topics"):
        check(k in s, f"signal missing {k}")
    check(s["basis"] in ("observed", "heuristic", "inferred"), "basis")
    check(s["severity"] in X.SEV, "severity")
    check(s["evidence"] and all(e["url"].startswith("https://") for e in s["evidence"]), "evidence links")
    check(not any(w in (s["title"] + s["what"]).lower() for w in ("buy now", "sell now", "you should")), "no advice language")

# Polymarket odds jump: observed, HIGH; near-resolution downgraded; sports skipped
pm = FX["polymarket"]
s = X.pm_odds_jump(pm["jump"], NOW); shape(s)
check(s["type"] == "ODDS_JUMP" and s["severity"] == "HIGH" and s["basis"] == "observed", s)
r = X.pm_odds_jump(dict(pm["jump"], endTs=NOW + 3600), NOW)
check(r["severity"] == "MEDIUM" and any("resolution" in l for l in r["limits"]), "near-resolution downgrade")
check(X.pm_odds_jump(dict(pm["jump"], category="sports"), NOW) is None, "sports skipped")
check(X.pm_odds_jump(pm["quiet"], NOW) is None, "quiet market: no signal")
# Volume spike vs baseline; brand-new market has no baseline
s = X.pm_volume_spike(pm["spike"], NOW); shape(s)
check(s["basis"] == "heuristic" and s["metrics"]["ratio"] == 20.0, s["metrics"])
check(X.pm_volume_spike(dict(pm["spike"], startTs=NOW - 3600), NOW) is None, "new market skipped")
# Fresh-wallet bets (Polymarket on-chain): only wallets new to Polymarket, inferred when the odds moved
fs = {k: NOW - v for k, v in FX["firstSeenAgo"].items()}
s = X.pm_fresh_wallet_bets(pm["jump"], FX["trades"], fs, NOW, moved=True); shape(s)
check(s["basis"] == "inferred" and s["metrics"]["wallets"] == 2 and s["metrics"]["usd"] == 60000.0, s["metrics"])
check(all("polygonscan.com/tx/" in e["url"] for e in s["evidence"][:-1]), "Polygon tx evidence")
check(X.pm_fresh_wallet_bets(pm["jump"], FX["trades"], fs, NOW, moved=False)["basis"] == "heuristic", "not moved -> heuristic")
check(X.pm_fresh_wallet_bets(pm["jump"], FX["trades"], {k: None for k in fs}, NOW) is None, "unknown wallet age is not fresh")
# Kalshi price shock + volume spike; sports skipped
k = X.kalshi_shock(FX["kalshi"]["shock"], NOW)
check(sorted(x["type"] for x in k) == ["PRICE_SHOCK", "VOLUME_SPIKE"], [x["type"] for x in k]); [shape(x) for x in k]
check(X.kalshi_shock(dict(FX["kalshi"]["shock"], category="Sports"), NOW) == [], "kalshi sports skipped")
# Equities z-scores
rows = [tuple(r) for r in FX["equity"]]
e = X.equity_anomaly("TEST", rows, "https://finance.yahoo.com/quote/TEST")
check(sorted(x["type"] for x in e) == ["PRICE_Z", "VOLUME_Z"], [x["type"] for x in e]); [shape(x) for x in e]
check(X.equity_anomaly("TEST", rows[:-1], "https://finance.yahoo.com/quote/TEST") == [], "normal day: nothing")
# Options volume vs OI; 0DTE excluded
o = X.options_unusual("TEST", FX["options"], "https://www.cboe.com/delayed_quotes/test/quote_table", NOW); shape(o)
check(o["metrics"]["contracts"] == 2 and o["metrics"]["tilt"] == "calls", o["metrics"])
# Treasuries: sudden move + inversion
t = X.treasury_signals([(d, y) for d, y in FX["treasury"]], "https://home.treasury.gov/")
check({"YIELD_MOVE", "CURVE_INVERSION"} <= {x["type"] for x in t}, [x["type"] for x in t]); [shape(x) for x in t]
# Cross-market: same topic in 2+ sources -> inferred, never above MEDIUM with 2 sources
allsig = [X.pm_odds_jump(pm["jump"], NOW)] + X.kalshi_shock(FX["kalshi"]["shock"], NOW)
c = X.cross_market(allsig, NOW)
check(c and c[0]["basis"] == "inferred" and c[0]["severity"] == "MEDIUM" and set(c[0]["metrics"]["sources"]) == {"kalshi", "polymarket"}, c)
check(X.cross_market([allsig[0]], NOW) == [], "one source is not cross-market")
check("fed-rates" in X.topics("Will the Fed cut rates in December?") and "bitcoin" in X.topics("COIN volume") and "bitcoin" not in X.topics("coinbase"), "topics")
# Solana watch alerts re-surface
sol = X.solana_from_reports([FX["watch"]], NOW)
check(len(sol) == 1 and sol[0]["source"] == "solana", sol)

# Feed: failed provider is UNKNOWN (never quiet); watch dedupes and escalates
import grok_the_block.markets.sources as S
S.polymarket_markets = lambda limit=200: None
S.treasury_curve = lambda: {"rows": [(d, y) for d, y in FX["treasury"]], "via": "fixture", "url": "https://home.treasury.gov/"}
from grok_the_block import data as D
D.PROVIDERS.update({"polymarket": {"ok": False, "detail": "fixture outage"}, "treasury": {"ok": True, "detail": "fixture"}})
rep = F.run(["polymarket", "treasury"], now=NOW)
check(rep["sourceStatus"]["polymarket"]["state"] == "unknown" and rep["status"] == "partial", rep["sourceStatus"])
check("unknown, not quiet" in rep["assessment"]["lead"]["text"], rep["assessment"]["lead"])
check(any(l["kind"] == "failed" for l in rep["coverage"]["limits"]), "failure listed in coverage")
check("Not financial advice" in rep["disclaimer"], "disclaimer")
with tempfile.TemporaryDirectory() as td:
    sp = Path(td) / "w.json"
    a = F.watch(json.loads(json.dumps(rep)), sp)["watch"]
    check(a["baseline"] and a["alerts"] == [], "first run is a baseline")
    b = F.watch(json.loads(json.dumps(rep)), sp)["watch"]
    check(b["alerts"] == [] and b["suppressedDuplicates"] == len(rep["signals"]), "repeat suppressed")
    rep2 = json.loads(json.dumps(rep)); rep2["signals"][-1]["severity"] = "CRITICAL"
    c2 = F.watch(rep2, sp)["watch"]
    check(len(c2["alerts"]) == 1 and c2["alerts"][0]["alertType"] == "ESCALATED" and c2["previousSuccessfulScanAt"] == NOW, c2["alerts"])
    dead = dict(json.loads(json.dumps(rep)), status="failed", signals=[])
    check(F.watch(dead, sp)["watch"]["alerts"] == [], "failed run: no alerts")
# Crypto perps: OI shock + extreme funding
oi = [(NOW - (9 - i) * 86400, 3.0e9) for i in range(9)] + [(NOW, 3.9e9)]
fr = [(NOW - (20 - i) * 28800, 0.0001) for i in range(20)] + [(NOW, 0.0012)]
cp = X.crypto_perp_shock("BTC", oi, fr, "https://www.okx.com/trade-swap/btc-usdt-swap")
check({x["type"] for x in cp} == {"OI_SHOCK", "FUNDING_EXTREME"} and all("bitcoin" in x["topics"] for x in cp), cp); [shape(x) for x in cp]
# Stablecoin supply mint
sc = X.stablecoin_flows([{"symbol": "USDX", "name": "Fixture USD", "id": "1", "now": 52e9, "d1": 50e9, "w1": 49e9, "url": "https://defillama.com/stablecoin/x"},
                         {"symbol": "USDQ", "name": "Quiet USD", "id": "2", "now": 10e9, "d1": 10e9, "w1": 10e9, "url": "https://defillama.com/stablecoin/q"}], NOW)
check(len(sc) == 1 and sc[0]["type"] == "SUPPLY_MINT" and sc[0]["severity"] == "HIGH", sc); shape(sc[0])
# VIX spike
vix = [(NOW - (30 - i) * 86400, 15 + (i % 3) * 0.2, 0) for i in range(30)] + [(NOW, 22.0, 0)]
mv = X.macro_move("^VIX", "VIX volatility index", vix, "https://finance.yahoo.com/quote/%5EVIX")
check(len(mv) == 1 and mv[0]["severity"] == "HIGH", mv); shape(mv[0])
check(X.macro_move("GC=F", "Gold", vix[:-1], "https://finance.yahoo.com/quote/GC=F") == [], "calm gold: nothing")
# SEC: Form 4 cluster + severe 8-K item
f4 = [{"form": "4", "name": "FIXTURE CORP", "cik": "1", "role": "Issuer", "url": f"https://www.sec.gov/f{i}", "items": [], "ts": NOW} for i in range(5)]
f8 = [{"form": "8-K", "name": "FIXTURE CORP", "cik": "1", "role": "Filer", "url": "https://www.sec.gov/8k", "items": ["4.02", "9.01"], "ts": NOW},
      {"form": "8-K", "name": "Routine Inc", "cik": "2", "role": "Filer", "url": "https://www.sec.gov/8k2", "items": ["8.01"], "ts": NOW}]
ed = X.edgar_events(f4, f8, NOW)
check(sorted((x["type"], x["severity"]) for x in ed) == [("8K_EVENT", "HIGH"), ("INSIDER_FILING_CLUSTER", "MEDIUM")], ed); [shape(x) for x in ed]
# Convergence: 3 independent sources on one entity scores higher than 2, broad topics discounted
a1 = X.pm_odds_jump(pm["jump"], NOW); k1 = X.kalshi_shock(FX["kalshi"]["shock"], NOW)
t3 = X.treasury_signals([(d, y) for d, y in FX["treasury"]], "https://home.treasury.gov/")
for x in t3: x["when"] = NOW
c3 = X.cross_market([a1] + k1 + t3, NOW); X.convergence(c3, [a1] + k1 + t3)
c2 = X.cross_market([a1] + k1, NOW); X.convergence(c2, [a1] + k1)
best3 = max(c["metrics"]["convergence"] for c in c3); best2 = max(c["metrics"]["convergence"] for c in c2)
check(best3 > best2 and all(c["metrics"]["chain"] and c["title"].startswith("Convergence") for c in c3), (best3, best2))
print(f"signals detectors: {ok} checks passed")
