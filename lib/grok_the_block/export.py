"""JSON export envelope, same shape as CryptOSINT src/lib/export.ts."""
import json, re, time
from datetime import datetime, timezone
from pathlib import Path

TOOL, VERSION = "CryptOSINT", "0.3-grokbot"


def scan_type(r: dict) -> str:
    if "organicScore" in r: return "token"
    if "timeline" in r: return "replay"
    if "wallet" in r and "tokens" in r: return "wallet"
    if "coordinationIndex" in r: return "shill"
    return "other"


def envelope(r: dict) -> dict:
    return {"tool": TOOL, "version": VERSION, "exportedAt": datetime.now(timezone.utc).isoformat(), "scanType": scan_type(r), "result": r}


def export_file(src: str, out_dir: str = ".") -> Path:
    r = json.loads(Path(src).read_text())
    ident = (r.get("token") or {}).get("symbol") or (r.get("wallet") or {}).get("address", "")[:8] or r.get("ticker", "x")
    p = Path(out_dir) / f"grok-the-block-{scan_type(r)}-{re.sub(r'[^a-zA-Z0-9_-]', '', ident)}-{int(time.time() * 1000)}.json"
    p.write_text(json.dumps(envelope(r), indent=2))
    return p
