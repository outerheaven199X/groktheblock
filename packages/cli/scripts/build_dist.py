#!/usr/bin/env python3
"""Deterministically copy the approved browser runtime from ../../ui into dist/ui (allowlist only).
Excludes legacy/, caches, fixtures, dotfiles and anything not referenced as a runtime asset type.
Writes dist/BUILD-INFO.json with the source commit SHA and a sha256 per file. Usage: python3 scripts/build_dist.py"""
import hashlib, json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); PKG = os.path.dirname(HERE); REPO = os.path.dirname(os.path.dirname(PKG))
SRC = os.path.join(REPO, "ui"); DST = os.path.join(PKG, "dist", "ui")
ALLOW_TOP = {"index.html", "app.js", "registry.js", "stage.js", "data", "fonts", "licenses", "vendor"}
ALLOW_EXT = {".html", ".js", ".mjs", ".css", ".json", ".woff2", ".txt", ".md", ".svg", ".png", ".webp", ".jpg"}
def main():
    if os.path.exists(os.path.join(PKG, "dist")): shutil.rmtree(os.path.join(PKG, "dist"))
    files = {}
    for top in sorted(os.listdir(SRC)):
        if top not in ALLOW_TOP: continue
        base = os.path.join(SRC, top)
        walk = [(SRC, [], [top])] if os.path.isfile(base) else os.walk(base)
        for d, dirs, fs in walk:
            dirs[:] = sorted(x for x in dirs if not x.startswith("."))
            for f in sorted(fs):
                p = os.path.join(d, f); rel = os.path.relpath(p, SRC)
                if f.startswith(".") or os.path.islink(p) or os.path.splitext(f)[1].lower() not in ALLOW_EXT: continue
                out = os.path.join(DST, rel); os.makedirs(os.path.dirname(out), exist_ok=True)
                b = open(p, "rb").read(); open(out, "wb").write(b); os.utime(out, (0, 0))
                files[rel.replace(os.sep, "/")] = hashlib.sha256(b).hexdigest()
    lic = os.path.join(PKG, "licenses")   # top-level licence copies for the package (generated, not tracked)
    if os.path.exists(lic): shutil.rmtree(lic)
    shutil.copytree(os.path.join(SRC, "licenses"), lic)
    sha = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", REPO, "status", "--porcelain", "--", "ui"], capture_output=True, text=True).stdout.strip())
    json.dump({"sourceCommit": sha, "uiDirtyAtBuild": dirty, "files": files}, open(os.path.join(DST, "BUILD-INFO.json"), "w"), indent=1, sort_keys=True)
    print(f"dist/ui: {len(files)} files from {sha}{' (+uncommitted ui changes)' if dirty else ''}")
if __name__ == "__main__": sys.exit(main())
