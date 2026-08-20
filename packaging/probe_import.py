# -*- coding: utf-8 -*-
"""Frozen-import probe (2026-08-20).

Why this exists
    The Windows installer opened but could not read any grid file:
    `load_case` came back None. `load_case` is the only module in `src/`
    that imports pandas at module level, and the app swallows the reason.
    This probe is frozen with the SAME pathex and excludes, but with a
    console, so it PRINTS the real traceback.

        packaging\\diag_win.bat

    !! Every import below must be a PLAIN STATIC `import x` statement.
       PyInstaller only bundles what it can SEE in the source. A first
       version used `__import__(name)` in a loop and nothing at all got
       bundled - every line said "No module named ..." even on a machine
       where all of them were installed.

Output is ASCII only - cmd.exe mangles UTF-8 Korean.
"""
import sys
import traceback

RESULT = []


def _ok(name, mod):
    RESULT.append((name, getattr(mod, "__version__", ""), None))


def _bad(name):
    RESULT.append((name, "", traceback.format_exc()))


try:
    import numpy
    _ok("numpy", numpy)
except Exception:
    _bad("numpy")

try:
    import dateutil
    _ok("dateutil", dateutil)
except Exception:
    _bad("dateutil")

try:
    import pytz
    _ok("pytz", pytz)
except Exception:
    _bad("pytz")

try:
    import openpyxl
    _ok("openpyxl", openpyxl)
except Exception:
    _bad("openpyxl")

try:
    import pandas
    _ok("pandas", pandas)
except Exception:
    _bad("pandas")

try:
    import case_guard
    _ok("case_guard", case_guard)
except Exception:
    _bad("case_guard")

try:
    import read_v2
    _ok("read_v2", read_v2)
except Exception:
    _bad("read_v2")

try:
    import load_case
    _ok("load_case", load_case)
except Exception:
    _bad("load_case")


print("=" * 62)
print("frozen :", bool(getattr(sys, "frozen", False)))
print("python :", sys.version.split()[0])
print("meipass:", getattr(sys, "_MEIPASS", "(none)"))
print("=" * 62)

bad = 0
for name, ver, err in RESULT:
    if err is None:
        print(f"[ OK ] {name:12s} {ver}")
    else:
        bad += 1
        print(f"[FAIL] {name}")
        print(err.rstrip())
        print("-" * 62)

print("=" * 62)
print(f"done - {bad} failed of {len(RESULT)}")
