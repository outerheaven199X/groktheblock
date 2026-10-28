"""Fixture test for the watch diff: synthetic snapshots (clearly not live data)."""
import sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(R / "lib"), str(R / "skills/watch-token/scripts")]
import watch_token as W

prev = {"at": 1000, "verdict": "CRITICAL", "organicScore": 90, "bundleSeverity": "CRITICAL", "bundlePct": 76.6, "liquidityUsd": 36000,
        "mcap": 160000, "mintAuthority": False, "freezeAuthority": False, "lpLockedPct": 100, "risks": [], "insiders": 11}
cur = dict(prev, at=2000, liquidityUsd=9000, lpLockedPct=40, risks=["High holder correlation"])
missing = dict(prev, at=3000, liquidityUsd=None, mintAuthority=None, lpLockedPct=None, risks=None)

ch = W.diff(prev, cur, "MINT", "TEST")
types = sorted(c["type"] for c in ch)
assert types == ["LIQUIDITY_DROP", "LP_UNLOCK", "NEW_RISK"], types
assert all(c["evidence"] and c["key"] and c["previousScanAt"] == 1000 for c in ch)
assert W.diff(prev, missing, "MINT", "TEST") == [], "unknown values must never count as changes"
entry = {"symbol": "TEST"}
W.OUT = Path("/tmp/gtb-test-out"); W.OUT.mkdir(exist_ok=True)
f1, d1 = W.emit(entry, "MINT", ch, "ok")
f2, d2 = W.emit(entry, "MINT", W.diff(prev, cur, "MINT", "TEST"), "ok")
assert (len(f1), d1, len(f2), d2) == (3, 0, 0, 3), (len(f1), d1, len(f2), d2)
print("watch diff: all checks passed", types)
