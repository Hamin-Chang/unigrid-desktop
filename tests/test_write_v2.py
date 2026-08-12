"""test_write_v2.py — 남의 케이스를 v2 엑셀로 저장하는 길(X1 (b)) 검사.

가리는 것
  1) `.raw`·`.m` 을 읽어 만든 케이스를 v2 엑셀로 쓰고 **되읽으면 같은 표**가 나오는가
     (폭이 곧 뜻이라 열 수가 하나만 달라도 계통이 달라진다)
  2) 저장한 엑셀을 앱이 그대로 열어 **같은 답**을 내는가
  3) 3권선 권선별 탭(33 열)이 엑셀을 거쳐도 살아 있는가
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import app_engine                      # noqa: E402
import read_v2                         # noqa: E402
from load_case import load_case        # noqa: E402
from write_v2 import write_case        # noqa: E402

bad = 0


def ok(cond, name, extra=""):
    global bad
    print(f"  {'✅' if cond else '🚨'} {name}" + (f"  — {extra}" if extra else ""))
    if not cond:
        bad += 1


SAMPLE = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/"
              "Phase A_Balance/newest/PSSE/sample")
GRIDS = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/03_전기연자문_2026_3/"
             "04_python_conversion/02_GitHub_unigrid/acdc_powerflow/grids")

tmp = Path(tempfile.mkdtemp(prefix="unigrid_writev2_"))

SOURCES = [
    ("PSS/E 3권선", GRIDS / "psse_3w_sample.raw"),
    ("PSS/E 14버스", SAMPLE / "ieee-14-bus.raw"),
    ("MATPOWER 118버스", Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/matpower8.0/data/case118.m")),
]

# ── 1. 썼다 되읽으면 같은 표인가 ──────────────────────────────────────
print("1) v2 로 저장했다 되읽기")
saved = {}
for name, src in SOURCES:
    if not src.is_file():
        print(f"  ⏭  {name} — 파일이 없어 건너뛴다 ({src.name})")
        continue
    case = load_case(str(src))
    out = write_case(case, tmp / f"{src.stem}_v2.xlsx")
    saved[name] = (case, out)
    ok(out.is_file(), f"{name} — 엑셀이 만들어진다", out.name)
    ok(read_v2.is_v2(out), f"{name} — v2 파일로 읽힌다")

    back = read_v2.read_tables(out)
    for key, orig in case.tables.items():
        a = np.asarray(orig, dtype=float)
        b = np.asarray(back.get(key, np.zeros((0, 0))), dtype=float)
        if a.size == 0 or np.all(np.isnan(a)):
            continue                     # 없는 설비는 견줄 것이 없다
        if a.shape != b.shape:
            ok(False, f"{name} · {key} — 표 모양이 같다", f"{a.shape} → {b.shape}")
            continue
        m = ~(np.isnan(a) & np.isnan(b))
        d = np.nanmax(np.abs(a[m] - b[m]) / np.maximum(np.abs(a[m]), 1.0)) if m.any() else 0.0
        ok(d < 1e-9, f"{name} · {key} — 값이 같다 ({a.shape[1]}열)", f"최대 상대차 {d:.2e}")

# ── 2. 저장한 엑셀로 계산하면 같은 답인가 ─────────────────────────────
print("\n2) 저장한 엑셀로 계산하면 같은 답인가")
for name, (case, out) in saved.items():
    s1 = app_engine.solve(case)
    s2 = app_engine.solve(load_case(str(out)))
    ok(s1.converged and s2.converged, f"{name} — 둘 다 풀린다",
       f"{s1.iters}회 / {s2.iters}회")
    dv = float(np.nanmax(np.abs(s1.AC[:, 1, 0] - s2.AC[:, 1, 0])))
    da = float(np.nanmax(np.abs(s1.AC[:, 3, 0] - s2.AC[:, 3, 0])))
    ok(dv < 1e-6 and da < 1e-4, f"{name} — 전압·위상이 같다",
       f"전압 {dv:.2e} pu · 위상 {da:.2e} deg")

# ── 3. 3권선 권선별 탭이 엑셀을 거쳐도 사는가 ─────────────────────────
print("\n3) 3권선 권선별 탭(33 열)이 엑셀을 거쳐도 사는가")
if "PSS/E 3권선" in saved:
    case, out = saved["PSS/E 3권선"]
    t3 = np.asarray(read_v2.read_tables(out)["AC_3wtrans_dat"], dtype=float)
    ok(t3.shape[1] == 33, "3권선 표가 33 열로 되읽힌다", f"{t3.shape[1]}열")
    # 3권선 `1 `(3002-3001-3011) 의 WINDV = 1.01010 / 1.05000 / 1.01000
    row = next((r for r in t3 if int(r[1]) == 3002 and int(r[2]) == 3001), None)
    ok(row is not None, "3002-3001-3011 줄이 있다")
    if row is not None:
        got = (row[30], row[31], row[32])
        want = (1.01010, 1.05000, 1.01000)
        d = max(abs(g - w) for g, w in zip(got, want))
        ok(d < 1e-6, "권선 셋의 탭비가 그대로다",
           f"{got[0]:.5f} / {got[1]:.5f} / {got[2]:.5f}")
else:
    print("  ⏭  psse_3w_sample.raw 이 없어 건너뛴다")

app_engine.shutdown()
print(f"\n{'✅ 전부 통과' if bad == 0 else f'🚨 {bad}건 틀림'}")
print(f"저장한 곳: {tmp}")
sys.stdout.flush()
os._exit(1 if bad else 0)
