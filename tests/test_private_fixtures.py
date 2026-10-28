"""Optional developer check: run the real provider parsers against REAL saved payloads kept only locally in the
gitignored tests/fixtures/private/ directory (never committed; see docs/PROVIDER-RIGHTS.md). Offline. Prints SKIPPED
and exits 0 when the directory is absent (CI, fresh clones).  Run: python tests/test_private_fixtures.py"""
import json, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "lib"))
from grok_the_block.markets import sources as S  # noqa: E402

D = R / "tests/fixtures/private"


def load(p):
    t = p.read_text(errors="ignore")
    try:
        j = json.loads(t)
    except ValueError:
        return t
    return j.get("payload", j) if isinstance(j, dict) and "payload" in j and "provider" in j else j


def check(p):
    n = p.name.lower(); x = load(p)
    if "yahoo" in n: return S.parse_yahoo_chart(x) is not None
    if "nasdaq" in n and "hist" in n: return S.parse_nasdaq_hist(x) is not None
    if "okx" in n and "candle" in n: return S.parse_okx_candles(x) is not None
    if "coinbase" in n: return S.parse_coinbase_candles(x) is not None
    if "treasury" in n: return S.parse_treasury_csv(x) is not None
    if "kalshi" in n: return (S.parse_kalshi_events(x) or S.parse_kalshi_markets(x)) is not None
    if "gamma" in n or "polymarket" in n: return S.parse_gamma(x) is not None
    if "llama" in n: return S.parse_llama(x) is not None
    if "cboe" in n: return S.parse_cboe(x, 0) is not None
    return None


def main():
    files = sorted(p for p in D.glob("*") if p.is_file()) if D.is_dir() else []
    if not files:
        print("SKIPPED: no local private fixtures (tests/fixtures/private/ absent or empty)"); return 0
    ok = bad = other = 0
    for p in files:
        try:
            r = check(p)
        except Exception as e:  # noqa: BLE001
            r = False; print(f"ERROR {p.name}: {type(e).__name__}")
        if r is None: other += 1
        elif r: ok += 1
        else: bad += 1; print(f"FAIL  {p.name}")
    print(f"private fixtures: {ok} parsed, {bad} failed, {other} not mapped to a parser (of {len(files)})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
