"""v6 UI static checks (no browser): local-only assets, embedded data in sync, licences shipped, product-rule wording."""
import re, subprocess, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]
UI = R / "ui"
CODE = ["index.html", "app.js", "stage.js", "registry.js"] + [str(p.relative_to(UI)) for p in (UI / "vendor").rglob("*.js")]

def test_v6_loads_nothing_from_the_network():
    pat = re.compile(r"""(?:\bsrc=|\bhref=|url\(|\bimport\s*\(|\bfrom\s+|\bfetch\s*\(|XMLHttpRequest|new\s+WebSocket|EventSource)\s*['"]?(?:https?:)?//""", re.I)
    for f in CODE:
        t = (UI / f).read_text(errors="ignore")
        assert not pat.search(t), (f, pat.search(t).group(0))
    for f in ("index.html", "app.js", "stage.js"):
        t = (UI / f).read_text()
        assert "fetch(" not in t and "XMLHttpRequest" not in t and "WebSocket" not in t, f
    assert "connect-src 'none'" in (UI / "index.html").read_text()

def test_v6_embedded_reports_match_examples():
    r = subprocess.run([sys.executable, str(R / "tools/build_ui_data.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

def test_v6_vendored_three_r164_postprocessing_and_fonts_with_licences():
    assert '="164"' in (UI / "vendor/three/build/three.module.min.js").read_text() and (UI / "vendor/three/VERSION").read_text().startswith("0.164.1")
    for n in ("EffectComposer", "RenderPass", "AfterimagePass", "UnrealBloomPass", "OutputPass"):
        assert (UI / f"vendor/three/examples/jsm/postprocessing/{n}.js").exists(), n
    for f in ("BigShouldersDisplay-900-latin.woff2", "MartianMono-var-latin.woff2", "NotoSansJP-400-kiken-chui.woff2"):
        assert (UI / "fonts" / f).stat().st_size > 1000, f
    for l in ("three.js-r164-MIT.txt", "BigShouldersDisplay-OFL.txt", "MartianMono-OFL.txt", "NotoSansJP-OFL.txt"):
        assert "Permission" in (UI / "licenses" / l).read_text() or "SIL OPEN FONT LICENSE" in (UI / "licenses" / l).read_text().upper(), l
    assert (UI / "licenses/NOTICE-v6.md").exists()

def test_v6_product_rules_in_copy():
    t = (UI / "index.html").read_text() + (UI / "app.js").read_text()
    assert "Not financial advice" in t and "counsel" not in t.lower() and "draft" not in t.lower()
    phrases = re.search(r"const HYPE = (\[.*?\]);", t).group(1).lower()
    assert not re.search(r"\b(buy|sell|hold|moon|pump|scam|rug ?pull)\b", phrases), phrases
    assert "prefers-reduced-motion" in t and "nowebgl" in (UI / "stage.js").read_text()

if __name__ == "__main__":
    n = fails = 0
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            n += 1
            try:
                v(); print("ok  ", k)
            except Exception as e:  # noqa: BLE001
                fails += 1; print("FAIL", k, "--", type(e).__name__, str(e)[:200])
    print(f"ui_v6_static: {n - fails}/{n} passed")
    sys.exit(1 if fails else 0)
