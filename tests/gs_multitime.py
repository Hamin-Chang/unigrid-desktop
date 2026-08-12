"""G7 — 여러 시각(24h)을 GS 와 NR 이 같게 푸는가 (2026-08-12).

    python tests/gs_multitime.py

왜 새 케이스를 만드나
    v2 파일 중 시각이 여럿인 것은 15개인데 **하나도 쓸 수 없다** —
    14개는 AC/DC 혼합(Mode 0)이고, 하나뿐인 AC 단독(`AConly_noslackAC`)은 **droop 계통**이라
    2026-08-12 확정에 따라 GS 가 거부한다. ⇒ AC only 계통의 부하 표를 24시각으로 늘려 쓴다.

부하 곡선
    하루 모양을 흉내 낸다 — 새벽에 낮고 낮·저녁에 높은 곡선에, 버스마다 조금씩 다른 위상을 준다
    (전 버스가 똑같이 오르내리면 전압 분포가 안 변해 시각을 나눈 보람이 없다).

🚨 **"둘이 같다" 만으로는 통과가 아니다.**
    시각을 안 나누고 첫 시각만 24번 풀어도 양쪽이 같아질 수 있다.
    ⇒ **시각에 따라 답이 실제로 달라지는지**(시각 효과)를 함께 찍는다.
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
OUT = V14 / "cases_v2" / "_다시각_시험_20260812"
TARGETS = ["AConly_case14", "AConly_case9", "AConly_case30", "AConly_pandapower_3w"]
NT = 24
TOL = 1e-4


def build(name: str, nt: int = NT):
    case = load_case(str(V14 / f"cases_v2/{name}_v2.xlsx"))
    hours = np.arange(nt)
    new = case.copy()
    for tab in ("AC_PLoad_dat", "AC_QLoad_dat"):
        a = np.asarray(case.tables[tab], dtype=float)
        base = a[:, 1]                                   # 첫 시각 = 기준 부하
        # 버스마다 위상을 조금씩 어긋내 하루 곡선을 만든다 (0.75 ~ 1.15 배)
        phase = np.arange(a.shape[0])[:, None] * 0.35
        curve = 0.95 + 0.20 * np.sin((hours[None, :] - 6) / 24 * 2 * np.pi + phase)
        new.tables[tab] = np.column_stack([a[:, 0], base[:, None] * curve])
    OUT.mkdir(exist_ok=True)
    p = OUT / f"{name}_24h_v2.xlsx"
    write_case(new, p)
    return load_case(str(p))


def cube(sol):
    a = np.asarray(sol.AC, dtype=float)
    if a.ndim == 2:
        a = a[:, :, None]
    return a


def main() -> int:
    print(f"\n{'계통':<24}{'시각':>5}{'시각 효과':>11}   GS↔NR")
    print("-" * 62)
    n_ok = n_bad = 0

    for name in TARGETS:
        case = build(name)
        nr = cube(app_engine.solve(case, method="nr"))
        gs = cube(app_engine.solve(case, method="gs"))
        if nr.shape[2] != NT or gs.shape[2] != NT:
            print(f"{name:<24}{'':>5}{'':>11}   ⚠️ 시각 수가 다르다 "
                  f"(NR {nr.shape[2]} · GS {gs.shape[2]})")
            n_bad += 1; continue

        # 버스를 번호로 맞춘다 (3권선은 aux 버스가 붙어 개수가 다를 수 있다)
        common, i_n, i_g = np.intersect1d(nr[:, 0, 0], gs[:, 0, 0], return_indices=True)
        if common.size == 0:
            print(f"{name:<24}{NT:>5}{'':>11}   ⚠️ 견준 버스 0 — 대조 실패")
            n_bad += 1; continue
        d = float(np.max(np.abs(nr[i_n, 1, :] - gs[i_g, 1, :])))
        # 시각에 따라 답이 실제로 달라지나 — 0 이면 시각을 나눈 보람이 없다
        eff = float(np.max(gs[i_g, 1, :].max(axis=1) - gs[i_g, 1, :].min(axis=1)))

        mark = "같음" if d <= TOL else f"다름 {d:.2e}"
        if not (eff > TOL):
            mark += "  ⚠️ 시각에 따라 답이 안 변한다 — 검증 못 함"
        print(f"{name:<24}{NT:>5}{eff:>11.2e}   {mark} (버스 {common.size})")
        if d <= TOL and eff > TOL:
            n_ok += 1
        elif d > TOL:
            n_bad += 1

    print("-" * 62)
    print(f"통과 {n_ok} · 어긋남 {n_bad}")
    print(f"만든 파일: {OUT}\n")
    return 1 if n_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
