"""ZIP 부하와 발전기 한계를 **함께** 켜고 GS·NR 을 견준다 (2026-08-12, G2 × G3).

    python tests/gs_zip_qlim.py

왜 따로 보나
    두 기능이 한 줄에서 만난다 — `runpfGS_app.m` 의

        Q0(i) = imag(Sg_bus(i)) - Qd(i)

    `Sg_bus(i)` 는 한계에 걸린 버스에서 한계값으로 바뀌어 있고(G2), `Qd(i)` 는 전압에 따라
    매 반복 다시 재는 값이다(G3). 즉 **한계를 건 버스의 목표 Q 가 부하와 함께 움직인다.**
    따로 검증하면 이 자리가 안 밟힌다.

    `gs_zip.py`(ZIP 만) · `gs_qlim_random.py`(한계만) 의 재료를 그대로 가져다 쓴다.
"""
from __future__ import annotations

import sys, warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))
warnings.filterwarnings("ignore")

import numpy as np
from load_case import load_case
from write_v2 import write_case
import app_engine
from gs_zip import build                      # ZIP 계수를 넣은 판을 만든다
from gs_qlim_random import make_limited, volts, n_saturated

V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
OUT = V14 / "cases_v2" / "_zip_한계_시험_20260812"
TARGETS = ["AConly_case14", "AConly_case30", "AConly_case118", "AConly_pandapower_3w"]
TOL = 1e-4


def main() -> int:
    OUT.mkdir(exist_ok=True)
    print(f"\n{'계통':<24}{'조인 대수':>8}{'포화':>6}{'ZIP 효과':>11}   GS↔NR")
    print("-" * 70)
    n_ok = n_bad = 0

    for nm in TARGETS:
        lim, n_tight = make_limited(build(nm, True), True)      # ZIP + 한계 + 용량 원
        p = OUT / f"{nm}_zip_qlim_v2.xlsx"
        write_case(lim, p)
        lim = load_case(str(p))
        gen = np.asarray(lim.tables["AC_gen_dat"], dtype=float)

        nr = app_engine.solve(lim, method="nr")
        gs = app_engine.solve(lim, method="gs")
        bn, vn = volts(nr)[:2]
        bg, vg = volts(gs)[:2]
        common, i_n, i_g = np.intersect1d(bn, bg, return_indices=True)
        if common.size == 0:
            print(f"{nm:<24}{'':>8}{'':>6}{'':>11}   ⚠️ 견준 버스 0 — 대조 실패")
            n_bad += 1; continue
        d = float(np.max(np.abs(vn[i_n] - vg[i_g])))
        nsat = n_saturated(nr, lim, gen)

        # ZIP 을 끈 같은 조건과 견줘 ZIP 이 실제로 답을 바꾸는지 확인한다
        lim0, _ = make_limited(build(nm, False), True)
        p0 = OUT / f"{nm}_flat_qlim_v2.xlsx"
        write_case(lim0, p0)
        v_off = volts(app_engine.solve(load_case(str(p0)), method="nr"))[1]
        eff = float(np.max(np.abs(vn - v_off))) if len(v_off) == len(vn) else float("nan")

        mark = "같음" if d <= TOL else f"다름 {d:.2e}"
        if nsat == 0:
            mark += "  ⚠️ 포화 0 — 한계를 검증 못 함"
        if not (eff > TOL):
            mark += "  ⚠️ ZIP 이 답을 안 바꾼다"
        print(f"{nm:<24}{n_tight:>8}{nsat:>6}{eff:>11.2e}   {mark} (버스 {common.size})")
        if d <= TOL and nsat > 0 and eff > TOL:
            n_ok += 1
        elif d > TOL:
            n_bad += 1

    print("-" * 70)
    print(f"통과 {n_ok} · 어긋남 {n_bad}")
    print(f"만든 파일: {OUT}\n")
    return 1 if n_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
