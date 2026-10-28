#!/usr/bin/env python3
"""Fail if tracked files contain post links, API key values, or local machine paths."""
import re, subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATTERNS = {
    "t.co short link": r"\bt\.co/",
    "x.com / twitter.com status URL": r"(?:x|twitter)\.com/[^\s\"']*/status",
    "api-key value": r"api[-_]key=(?!\{)[A-Za-z0-9-]{6,}",
    "home path": "/" + r"home/",
    "workspace path": "/" + r"workspace\b",
}
SELF = pathlib.Path(__file__).resolve()

def main():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    bad = []
    for f in files:
        p = ROOT / f
        if p.resolve() == SELF or p.suffix in (".png", ".jpg", ".mp4", ".zip"):
            continue
        try:
            text = p.read_text(errors="ignore")
        except (IsADirectoryError, FileNotFoundError):
            continue
        for name, pat in PATTERNS.items():
            for m in re.finditer(pat, text):
                line = text.count("\n", 0, m.start()) + 1
                bad.append(f"{f}:{line}: {name}")
    if bad:
        print("leak check FAILED:\n" + "\n".join(bad[:50]))
        sys.exit(1)
    print(f"leak check: {len(files)} tracked files clean")

if __name__ == "__main__":
    main()
