"""Run every offline test suite and print per-suite results, SKIPPED lines and a TOTAL.  Run: python tests/run_all.py"""
import re, subprocess, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SUITES = ["test_no_leaks.py", "test_ui_v6_static.py", "test_registry.py", "test_tcg.py", "test_refresh.py", "test_everything.py", "test_round9.py", "test_round8.py", "test_round7.py", "test_round6.py", "test_round5.py", "test_round4.py", "test_round3.py", "test_replay.py", "test_signals.py",
          "test_classify.py", "test_watch_diff.py", "test_private_fixtures.py"]


def main():
    total_p = total_n = failed = skipped = 0
    for s in SUITES:
        p = subprocess.run([sys.executable, str(R / "tests" / s)], cwd=R, capture_output=True, text=True)
        out = p.stdout + p.stderr
        m = re.findall(r"(\d+)/(\d+) passed", out)
        sk = [l for l in out.splitlines() if "SKIPPED" in l]
        m2 = re.findall(r"all (\d+) (?:tests|checks) passed|(\d+) fixtures passed", out)
        if m:
            a, b = map(int, m[-1]); total_p += a; total_n += b
            res = f"{a}/{b} passed"
        elif m2 and p.returncode == 0:
            a = int(m2[-1][0] or m2[-1][1]); total_p += a; total_n += a
            res = f"{a}/{a} passed"
        else:
            res = ("passed" if p.returncode == 0 else "FAILED") + " (no numeric count; last line: " + (out.strip().splitlines() or ["-"])[-1][:70] + ")"
        if sk:
            skipped += 1
            res = "SKIPPED (not counted in TOTAL)"
        status = "SKIP" if (sk and p.returncode == 0) else ("PASS" if p.returncode == 0 else "FAIL")
        failed += p.returncode != 0
        print(f"{status:4} {s:28} {res}" + (f"  [{sk[0].strip()}]" if sk else ""))
        if p.returncode:
            print("\n".join("     " + l for l in out.splitlines() if "FAIL" in l)[:2000])
    print(f"TOTAL: {total_p}/{total_n} counted tests passed; suites failed: {failed}; suites SKIPPED (not counted): {skipped}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
