"""G3 — ZIP 부하를 GS 와 NR 이 같게 푸는가 (2026-08-12).

    python tests/gs_zip.py

왜 새 케이스를 만드나
    ZIP 계수가 **실제로 켜진** v2 파일은 10개인데 **전부 AC/DC 혼합 계통**이다
    (`ACDC_71bus_*` · `ACDC_hanjeon`). GS 는 AC 단독(Mode = 1)만 풀므로 그것들로는 못 본다.
    ⇒ AC only 계통에 계수를 넣은 판을 만들어 쓴다. 값은 71버스 계통에 실제로 있는 조합을 그대로 쓰고
    (합이 1 이라 V = V0 에서 기준 부하와 같아진다), Q 도 섞는 조합 하나를 더했다.

🚨 **"둘이 같다" 만으로는 통과가 아니다.**
    ZIP 이 무시되면 양쪽 다 정전력으로 풀어 역시 같아진다. 그래서 **ZIP 을 끈 판과 견줘
    답이 실제로 달라지는지**(= 기능이 켜졌는지) 함께 본다.
"""
from __future__ import annotations

import sys, warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
warnings.filterwarnings("ignore")

import numpy as np
from load_case import load_case
from write_v2 import write_case
import app_engine

V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
OUT = V14 / "cases_v2" / "_zip_시험_20260812"

#            Zp     Ip     Pp     Zq    Iq    Pq      ← 71버스 계통의 실제 조합 + 마지막 하나는 새로
COMBOS = np.array([
    [0.000, 0.000, 1.000, 1.00, 0.00, 0.00],
    [0.000, 0.180, 0.820, 1.00, 0.00, 0.00],
    [0.002, 0.917, 0.082, 1.00, 0.00, 0.00],
    [0.511, 0.487, 0.002, 1.00, 0.00, 0.00],
    [0.500, 0.300, 0.200, 0.50, 0.30, 0.20],
])
FLAT = np.array([0.0, 0.0, 1.0, 0.0, 0.0, 1.0])     # 정전력 — ZIP 을 끈 판

TARGETS = ["AConly_case14", "AConly_case9", "AConly_case30",
           "AConly_case118", "AConly_pandapower_3w"]
TOL = 1e-4


def build(name: str, zip_on: bool, v0: float | None = None, tag: str = ""):
    case = load_case(str(V14 / f"cases_v2/{name}_v2.xlsx"))
    bus = np.asarray(case.tables["AC_Bus_dat"], dtype=float).copy()
    for r in range(bus.shape[0]):
        bus[r, 3:9] = COMBOS[r % len(COMBOS)] if zip_on else FLAT
        if v0 is not None:
            bus[r, 11] = v0
    new = case.copy()
    new.tables["AC_Bus_dat"] = bus
    OUT.mkdir(exist_ok=True)
    p = OUT / f"{name}_{tag or ('zip' if zip_on else 'flat')}_v2.xlsx"
    write_case(new, p)
    return load_case(str(p))


def volts(sol):
    a = np.asarray(sol.AC, dtype=float)
    if a.ndim == 3:
        a = a[:, :, 0]
    return a[:, 0], a[:, 1]


def compare(case):
    bn, vn = volts(app_engine.solve(case, method="nr"))
    bg, vg = volts(app_engine.solve(case, method="gs"))
    common, i_n, i_g = np.intersect1d(bn, bg, return_indices=True)
    if common.size == 0:
        return None, 0, vn
    return float(np.max(np.abs(vn[i_n] - vg[i_g]))), common.size, vn


def main() -> int:
    print(f"\n{'계통':<24}{'무엇':<12}{'ZIP 효과':>11}   GS↔NR")
    print("-" * 70)
    n_ok = n_bad = n_skip = 0

    jobs = [(nm, None, "") for nm in TARGETS]
    jobs.append(("AConly_case14", 0.98, "zip_v0"))       # V0 가 1 이 아닌 판

    for name, v0, tag in jobs:
        what = "ZIP+V0 0.98" if v0 is not None else "ZIP"
        try:
            on = build(name, True, v0, tag)
            off = build(name, False, v0, (tag + "_flat") if tag else "")
        except Exception as exc:
            print(f"{name:<24}{what:<12}{'':>11}   준비 실패 — {str(exc)[:28]}")
            n_bad += 1; continue

        d, nbus, v_on = compare(on)
        if d is None:
            print(f"{name:<24}{what:<12}{'':>11}   ⚠️ 견준 버스 0 — 대조 실패"); n_bad += 1; continue

        # ZIP 을 끈 판과 얼마나 달라지나 — 0 이면 기능이 안 켜진 것이다
        _, _, v_off = compare(off)
        eff = float(np.max(np.abs(v_on - v_off))) if v_off is not None and \
            len(v_off) == len(v_on) else float("nan")

        mark = "같음" if d <= TOL else f"다름 {d:.2e}"
        if not (eff > TOL):
            mark += "  ⚠️ ZIP 이 답을 안 바꾼다 — 검증 못 함"
        print(f"{name:<24}{what:<12}{eff:>11.2e}   {mark} (버스 {nbus})")
        if d <= TOL and eff > TOL:
            n_ok += 1
        elif d > TOL:
            n_bad += 1
        else:
            n_skip += 1

    print("-" * 70)
    print(f"통과 {n_ok} · 어긋남 {n_bad} · 검증 못 함 {n_skip}")
    print(f"만든 파일: {OUT}\n")
    return 1 if n_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
