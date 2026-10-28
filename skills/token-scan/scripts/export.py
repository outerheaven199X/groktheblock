#!/usr/bin/env python3
"""Wrap any CryptOSINT result JSON in the original export envelope
({tool, version, exportedAt, scanType, result}). usage: export.py <result.json> [--out-dir .]"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from grok_the_block.export import export_file

ap = argparse.ArgumentParser(description='Grok The Block · export: wrap a result in the original CryptOSINT export envelope.', epilog="An evolution of CryptOSINT by @varien. Read-only."); ap.add_argument("src"); ap.add_argument("--out-dir", default=".")
a = ap.parse_args(); print(export_file(a.src, a.out_dir))
