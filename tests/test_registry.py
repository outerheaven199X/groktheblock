"""Capability registry static checks (no browser): ids unique, every route points at real data, licence-gated classes are
never registered as tools, the UI's embedded everything data matches data/everything/*.json, no credentials or network in UI code."""
import json, re, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]
REG = (R / "ui/registry.js").read_text()
UNI = json.loads((R / "data/everything/universe.json").read_text())
UNI = UNI.get("universe", UNI.get("assets", UNI)) if isinstance(UNI, dict) else UNI
UIDS = {u["id"]: u for u in UNI}
FEATS = re.findall(r'\{ id: "([a-z0-9.]+)", cat: "([a-z]+)", name: "([^"]+)", route: \{([^}]*)\}[^\n]*impl: "([a-z]+)"', REG)

def test_registry_ids_unique_and_categories_known():
    ids = [f[0] for f in FEATS]; cats = set(re.findall(r'\{ id: "([a-z]+)", name: "[^"]+", families', REG))
    assert len(ids) == len(re.findall(r"\{ id: \"[a-z]+\.[a-z0-9]+\", cat:", REG)) >= 25 and len(ids) == len(set(ids)), ids
    assert all(f[1] in cats for f in FEATS), cats

def test_registry_routes_reference_real_universe_ids():
    for fid, _, _, route, _ in FEATS:
        for u in re.findall(r'"([a-z0-9-]+)"', (re.search(r"uni: \[([^\]]*)\]", route) or [None, ""])[1]):
            assert u in UIDS, (fid, u)

def test_licence_gated_classes_are_not_tools():
    tool = dict(re.findall(r'"?([a-z0-9-]+)"?: "([a-z0-9.]+)"', re.search(r"UNI_TOOL = \{([^}]*)\}", REG).group(1)))
    for u, f in tool.items():
        if u in UIDS: assert UIDS[u]["status"] != "blocked-licence", u
    names = {f[2].lower() for f in FEATS}
    for u in UIDS.values():
        if u["status"] == "blocked-licence": assert u["name"].lower() not in names, u["name"]

def test_embedded_everything_matches_data_files():
    t = (R / "ui/data/everything.js").read_text(); j = json.loads(t[t.index("{"): t.rindex("}") + 1])
    assert [u["id"] for u in j["universe"]] == [u["id"] for u in UNI]
    live = json.loads((R / "data/everything/live-derived.json").read_text())
    assert j["live"]["generatedAt"] == live["generatedAt"] and len(j["live"]["probes"]) == len(live["probes"])

def test_ui_code_has_no_credentials_or_network_calls():
    for f in ("registry.js", "app.js", "stage.js", "index.html"):
        t = (R / "ui" / f).read_text()
        assert not re.search(r"(api[_-]?key|apikey|secret|bearer|helius|password)\s*[:=]", t, re.I), f
        assert "fetch(" not in t and "XMLHttpRequest" not in t and "WebSocket" not in t, f

if __name__ == "__main__":
    n = fails = 0
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            n += 1
            try: v(); print("ok  ", k)
            except Exception as e: fails += 1; print("FAIL", k, "--", type(e).__name__, str(e)[:200])
    print(f"registry: {n - fails}/{n} passed"); sys.exit(1 if fails else 0)
