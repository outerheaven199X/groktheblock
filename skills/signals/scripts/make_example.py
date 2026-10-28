#!/usr/bin/env python3
"""Turn out/signals-latest.json (a real watch scan) into examples/signals-EXAMPLE.json: trimmed, wallets shortened,
labelled EXAMPLE. Usage: make_example.py [max_signals]"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
rep = json.loads((ROOT / "out/signals-latest.json").read_text())
n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
keep = [s for s in rep["signals"] if s["source"] == "cross"][:6]
keep += [s for s in rep["signals"] if s["source"] != "cross"][: n - len(keep)]
rep["signals"] = keep
rep["probes"] = {k: v for k, v in rep.get("probes", {}).items() if any(k == s["key"] for s in keep)}
txt = json.dumps(rep, ensure_ascii=False)
txt = re.sub(r'"(address|wallet|proxyWallet|maker|taker)": "0x([0-9a-fA-F]{4})[0-9a-fA-F]{32}([0-9a-fA-F]{4})"', r'"\1": "0x\2…\3"', txt)
txt = re.sub(r'"(name|pseudonym|profileImage|bio)": "[^"]*"(?=, "address")', r'"\1": null', txt)
out = {"example": True, "_note": f"EXAMPLE: a trimmed copy of one real watch scan ({rep['generatedAt']}) for documentation and UI tests. Public market data, not live; do not trade on it."}
out.update(json.loads(txt))
(ROOT / "examples/signals-EXAMPLE.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(len(keep), "signals →", ROOT / "examples/signals-EXAMPLE.json")
