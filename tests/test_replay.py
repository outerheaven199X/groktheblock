"""Deterministic replay over synthetic point-in-time fixtures (tests/fixtures/replay). Not market data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from grok_the_block.markets import replay as RP

R = {r["name"]: r for r in RP.run_all()}
assert R["01-arbitrage-pair"]["convergences"] == 0 and R["01-arbitrage-pair"]["relatedRepricing"] > 0, "arbitrage pair is one family"
assert R["02-keyword-false-match"]["convergences"] == 0 and R["02-keyword-false-match"]["falseConvergencePrevented"] > 0, "keyword-only match"
assert R["03-outage"]["resolvedDuringOutage"] == 0 and R["03-outage"]["telemetry"]["skippedUnavailable"] == 6, "outage never resolves"
assert list(R["03-outage"]["finalStates"].values()) == ["RESOLVED"], "resolves after recovery"
assert R["04-quiet-session"]["alerts"] == 0, "quiet session"
assert R["05-midnight-boundary"]["alerts"] == 1 and R["05-midnight-boundary"]["v1Alerts"] == 2, "midnight duplicate removed"
assert R["06-scheduled-cpi"]["convergenceMaxSeverity"] == "LOW" and R["06-scheduled-cpi"]["calendarTagged"] > 0, "calendar-explained capped"
assert R["07-cross-family-control"]["convergences"] > 0 and R["07-cross-family-control"]["convergenceMaxSeverity"] == "MEDIUM", "positive control"
print(f"replay: {len(R)} fixtures passed")
