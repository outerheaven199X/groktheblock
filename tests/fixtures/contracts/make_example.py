"""Regenerate examples/signals-EXAMPLE.json from SYNTHETIC inputs only (R5-02). Every provider fetcher is replaced by a
synthetic generator (tests/fixtures/contracts/synth.py) passed through the production parsers; no network, no vendor data.
Run: python tests/fixtures/contracts/make_example.py"""
import json, math, sys, tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

R = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(R / "lib"), str(R / "tests"), str(Path(__file__).parent)]
from grok_the_block.markets import feed as F, sources as S  # noqa: E402
import synth as SY  # noqa: E402
import test_round4 as R4  # noqa: E402

NOW = int(datetime(2026, 10, 28, 18, 5, tzinfo=ZoneInfo("America/New_York")).timestamp())
END = date(2026, 10, 28)


def equity(sym):
    spike = {"SYNX": True}.get(sym, False)
    return {"symbol": sym, "rows": R4._rows(END, spike, seed=len(sym)), "via": "synthetic", "url": f"https://example.invalid/synthetic/{sym}", "tz": "America/New_York"}


def treasury():
    rows = S.parse_treasury_csv(SY.treasury_csv(SY.weekdays(END, 60)))
    d, y = rows[-1]
    rows[-1] = (d, dict(y, **{"2Y": y["2Y"] + 0.22}))  # synthetic +22bp day
    return {"rows": rows, "via": "synthetic", "url": "https://example.invalid/synthetic/treasury"}


def crypto(ccy):
    rows = S.parse_okx_candles(SY.okx_candles(END, 90, 50_000.0 if ccy == "BTC" else 3_000.0))
    if ccy == "SOL" and rows:
        t, c, *rest = rows[-1]; rows[-1] = (t, rows[-2][1] * 0.86, *rest)
    return {"symbol": ccy, "rows": rows, "via": "synthetic", "url": f"https://example.invalid/synthetic/{ccy}"} if rows else None


def kalshi():
    ms = [SY.kalshi_market("SYNTH-FED-26DEC", price="0.7100", prev="0.4800", title="Synthetic: Fed funds target above 4.00% after the December 2026 meeting?"),
          SY.kalshi_market("SYNTH-CPI-26NOV", price="0.3300", prev="0.3100", title="Synthetic: CPI above 3.0% in November 2026?")]
    return S.parse_kalshi_events(SY.kalshi_events(ms))


def options(sym):
    j = SY.cboe_chain(12, "2026-10-28 15:56:14", 90.0)
    for i in (3, 7):  # two synthetic far-dated contracts with heavy volume vs open interest
        j["data"]["options"][i].update(volume=6000.0, open_interest=900.0, last_trade_price=2.6)
    c = S.parse_cboe(j, NOW - 600)
    return dict(c, symbol=sym, via="synthetic", url=f"https://example.invalid/synthetic/options/{sym}") if c else None


def polymarket(limit=200):
    return S.parse_gamma([SY.gamma_market(0, question="Synthetic: Will the Fed cut rates in December 2026?", oneHourPriceChange=-0.15, oneDayPriceChange=-0.21,
                                          outcomePrices='["0.31", "0.69"]', volume24hr=900000.0, volume1wk=1500000.0, startDate="2026-06-01T00:00:00Z"),
                          SY.gamma_market(1, question="Synthetic: Will Bitcoin be above $150,000 on December 31, 2026?")])


PATCH = {"equity_daily": equity, "options_chain": options, "treasury_curve": treasury, "crypto_daily": crypto, "crypto_perps": lambda c: None,
         "stablecoins": lambda: S.parse_llama(SY.llama()), "edgar_current": lambda *a, **k: None, "kalshi_markets": lambda *a, **k: kalshi(),
         "polymarket_markets": polymarket, "polymarket_history": lambda *a, **k: None, "polymarket_trades": lambda *a, **k: [],
         "polymarket_first_seen": lambda *a, **k: None, "macro_daily": lambda s: None}


CAL = {"builtAt": "2026-10-28T12:00:00Z", "provenance": "synthetic", "sources": [], "missing": [], "contact": {"configured": False},
       "notIncluded": ["Synthetic calendar for the example only."],
       "events": [{"type": "FOMC", "label": "[SYNTHETIC] FOMC decision", "ts": NOW - 4 * 3600, "source": "synthetic", "timeExact": True, "eventId": "FOMC:SYNTH:1"},
                  {"type": "CPI", "label": "[SYNTHETIC] CPI release", "ts": NOW + 2 * 86400, "source": "synthetic", "timeExact": True, "eventId": "CPI:SYNTH:1"},
                  {"type": "AUCTION", "label": "[SYNTHETIC] 10-Year Note auction", "ts": NOW + 6 * 86400, "source": "synthetic", "timeExact": False, "tenor": "10Y", "eventId": "AUCTION:SYNTH:10Y"}]}


def main():
    old = {k: getattr(S, k) for k in PATCH}
    try:
        for k, v in PATCH.items():
            setattr(S, k, v)
        for src in ("polymarket", "kalshi", "equities", "options", "treasury", "crypto", "stablecoins", "sec", "macro"):
            F.D.PROVIDERS[src] = {"state": "HEALTHY", "detail": "synthetic generator (no provider contacted)"}
        rep = F.run(tickers=["SYNA", "SYNB", "SYNX"], option_tickers=["SYNO"], now=NOW, local_reports=[], calendar=CAL)
        with tempfile.TemporaryDirectory() as d:
            rep = F.watch(rep, Path(d) / "s.json", {"minSeverity": "LOW"})
    finally:
        for k, v in old.items():
            setattr(S, k, v)
    def tag(o):  # visible on every card, incident and screenshot, not only in the file header
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "title" and isinstance(v, str) and not v.startswith("[SYNTHETIC]"):
                    o[k] = "[SYNTHETIC] " + v
                elif k in ("url", "api") and isinstance(v, str) and v.startswith("http") and not v.startswith("https://example.invalid/"):
                    o[k] = "https://example.invalid/synthetic/" + v.split("://", 1)[1].split("/", 1)[0]  # no link to a real page for invented data
                else:
                    tag(v)
        elif isinstance(o, list):
            for v in o:
                tag(v)
    tag(rep)
    rep["example"] = True
    rep["synthetic"] = True
    rep["_note"] = ("SYNTHETIC EXAMPLE: every number, title and link in this file is invented by tests/fixtures/contracts/make_example.py "
                    "from synthetic generators run through the production parsers. It contains no provider data and describes no real market. "
                    "Not financial advice.")
    rep["_provenance"] = "synthetic"
    p = R / "examples/signals-EXAMPLE.json"
    p.write_text(json.dumps(rep, indent=1, default=str) + "\n")
    print(f"wrote {p.relative_to(R)}: {len(rep.get('signals') or [])} signals, sources {sorted((rep.get('sourceStatus') or {}).items(), key=lambda x: x[0]) and {k: v['state'] for k, v in rep['sourceStatus'].items()}}")


if __name__ == "__main__":
    main()
