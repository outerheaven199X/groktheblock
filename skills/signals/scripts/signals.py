#!/usr/bin/env python3
"""Grok The Block · signals: one cross-market feed of unusual activity, with evidence.

usage:
  signals.py scan  [--sources polymarket,kalshi,equities,options,treasury,solana] [--tickers SPY,NVDA] [--options SPY,NVDA]
  signals.py watch [same flags]   # incident lifecycle; alerts on new episodes / material updates / reminders
Writes out/signals-<UTCstamp>.json and out/signals-latest.json (kind: "signals"). Not financial advice.
"""
import argparse, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from grok_the_block import data as D
from grok_the_block.cli import OUT
from grok_the_block.markets import feed as F

ap = argparse.ArgumentParser(description="Grok The Block · signals: cross-market unusual activity with evidence. Not financial advice.",
                             epilog="An evolution of CryptOSINT by @varien. Read-only; never trades.")
ap.add_argument("cmd", choices=["scan", "watch"])
ap.add_argument("--sources", default=",".join(F.SOURCES))
ap.add_argument("--tickers", default="")
ap.add_argument("--options", default="")
ap.add_argument("--pm-limit", type=int, default=200)
ap.add_argument("--trace", type=int, default=6, help="Polymarket markets to trace wallets on")
ap.add_argument("--quiet", action="store_true")
ap.add_argument("--webhook", default=os.environ.get("GTB_SIGNALS_WEBHOOK", ""),
                help="watch mode: POST new alerts as JSON to this URL (or env GTB_SIGNALS_WEBHOOK). Never printed.")
ap.add_argument("--min-severity", default="MEDIUM", choices=["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
                help="watch mode: only alert at or above this severity (default MEDIUM)")
ap.add_argument("--mute", default="", help="watch mode: comma-separated sources to mute, e.g. kalshi,macro")
ap.add_argument("--quiet-hours", default="", help="watch mode: hold alerts between local hours, e.g. 22-7; released after")
ap.add_argument("--tz-offset", type=float, default=0, help="hours from UTC for --quiet-hours (e.g. -4)")
ap.add_argument("--digest", action="store_true", help="watch mode: hold alerts in a digest; release with --release-digest")
ap.add_argument("--release-digest", action="store_true")
a = ap.parse_args()
split = lambda s: [x.strip().upper() for x in s.split(",") if x.strip()]  # noqa: E731
rep = F.run([x.strip().lower() for x in a.sources.split(",") if x.strip()], split(a.tickers) or None, split(a.options) or None, a.pm_limit, a.trace)
if a.cmd == "watch":
    qh = tuple(int(x) for x in a.quiet_hours.split("-")) if a.quiet_hours else None
    prefs = {"minSeverity": a.min_severity, "mute": [x.strip().lower() for x in a.mute.split(",") if x.strip()], "quietHours": qh,
             "tzOffsetH": a.tz_offset, "digest": a.digest, "releaseDigest": a.release_digest}
    rep = F.watch(rep, D.CACHE_DIR / "signals-watch.json", prefs)
    rep["watch"]["minSeverity"] = a.min_severity
    if a.webhook and rep["watch"]["alerts"]:
        import requests
        body = {"tool": "grok-the-block", "kind": "signals-alerts", "generatedAt": rep["generatedAt"], "disclaimer": rep["disclaimer"],
                "previousSuccessfulScanAt": rep["watch"]["previousSuccessfulScanAt"],
                "alerts": [{k: x[k] for k in ("key", "incidentId", "alertReason", "severity", "basis", "source", "title", "what", "when", "evidence", "limits")} for x in rep["watch"]["alerts"]]}
        try:
            r = requests.post(a.webhook, json=body, timeout=15)
            rep["watch"]["webhook"] = {"ok": r.ok, "status": r.status_code}
        except requests.RequestException as e:
            rep["watch"]["webhook"] = {"ok": False, "error": type(e).__name__}
OUT.mkdir(parents=True, exist_ok=True)
stamp = time.strftime("%Y%m%d-%H%M", time.gmtime(rep["generatedAt"]))
D.write_json(OUT / f"signals-{stamp}.json", rep)
D.write_json(OUT / "signals-latest.json", rep)
if not a.quiet:
    print(f"{rep['assessment']['severity']}: {rep['assessment']['lead']['text']}")
    for k, v in rep["sourceStatus"].items():
        print(f"  {k:<10} {v['state']:<8} {v.get('detail') or ''}")
    print(f"  {rep['counts']['total']} signals · {rep['counts']['bySeverity']}")
    if a.cmd == "watch":
        w = rep["watch"]
        if w.get("webhook"):
            print(f"  webhook: {'delivered' if w['webhook']['ok'] else 'FAILED'} ({w['webhook'].get('status') or w['webhook'].get('error')})")
        print("  baseline set; no alerts on the first run" if w["baseline"] else f"  {len(w['alerts'])} alerts · telemetry {w['telemetry']}")
    print(f"  → out/signals-{stamp}.json")
    print("Not financial advice: unusual activity with evidence, not a prediction or a recommendation.")
