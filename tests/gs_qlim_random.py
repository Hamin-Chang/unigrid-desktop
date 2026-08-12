"""G2 를 **다른 AC only 계통**에도 한계를 넣어 검증한다 (2026-08-12).

    python tests/gs_qlim_random.py

왜 이 파일이 있나
    G2(발전기 무효 한계 + 용량 원)를 맞춘 뒤, 검증이 `case14` 하나에서 파생한 두 케이스뿐이었다.
    한 계통에서만 맞는 것은 우연일 수 있으므로 크기·성격이 다른 계통 여섯에
    **한계를 넣어** GS 와 NR 이 같은 답을 내는지 본다.

한계를 어떻게 정하나
    임의의 숫자를 박으면 **한계가 안 걸리거나**(검증이 헛돈다) **해가 없어 발산한다**.
    그래서 먼저 한계 없이 NR 로 풀어 각 발전기가 실제로 낸 Q 를 보고, 그 값을 기준으로 정한다.

      조임 대상 : 전압제어(PV) 발전기 중 |Q| 가 큰 쪽 절반 (슬랙은 뺀다 — 한계를 안 건다)
      Qmax      : 조일 것은 Q × 0.7,  나머지는 |Q| × 3 + 여유 (사실상 안 걸림)
      Qmin      : 위와 대칭
      S_N       : 두 번째 판에서만 — 조일 것은 sqrt(P²+Q²) × 0.9

🚨 **"둘 다 한계를 못 걸었다" 는 통과가 아니다.**
    NR 은 한계를 걸다 실패하면 조용히 무른 답을 내놓는다(`qlim_enforced = 0`).
    그러면 GS 와 값이 같아도 **한계를 검증한 게 아니다.** 그래서 아래 표에 포화 대수를 함께 찍는다.
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
OUT = V14 / "cases_v2" / "_qlim_시험_20260812"

# 큰 계통(1888rte·6495rte·25k)은 GS 가 너무 느려 뺐다. 3권선이 든 것도 하나 넣는다.
# 🚨 **전압제어(PV) 발전기가 있는 계통만 고른다.** 배전 계통(case18·case33·case37_sj·
#    case18_154·3wtrans_modify)은 발전기가 슬랙 하나뿐이라 한계를 걸 자리가 없다 —
#    넣어 봐야 "PV 발전기 없음" 으로 헛돈다(첫 판에서 둘이 그랬다).
TARGETS = [
    "AConly_case9",            # 3대 (PV 2)
    "AConly_case14_2",         # 5대 (PV 4)
    "AConly_case14_psse",      # 5대 (PV 4) — PSS/E 에서 읽은 판
    "AConly_case30",           # 6대 (PV 5)
    "AConly_case118",          # PV 다수
    "AConly_case118_psse",     # 54대 (PV 53)
    "AConly_pandapower_3w",    # 3권선 + 한계를 함께
]

TOL = 1e-4          # 전압 pu. 결과표가 4자리 반올림이라 그 아래는 못 본다
SLACK_MODE = 3      # AC Gen Data 3열: 3 = 슬랙


def solved_pq(case):
    """한계 없이 NR 로 풀어 버스별 (P, Q) [pu] 를 돌려준다."""
    sol = app_engine.solve(case, method="nr")
    a = np.asarray(sol.AC, dtype=float)
    if a.ndim == 3:
        a = a[:, :, 0]
    base = float(np.asarray(case.tables["Base_dat"], dtype=float).ravel()[0])   # MVA
    return {int(r[0]): (r[4] / base, r[5] / base) for r in a}   # 5·6열 = Gen MW/MVAR


def make_limited(case, with_sn: bool):
    """한계를 채운 새 케이스를 돌려준다. 못 만들면 None."""
    pq = solved_pq(case)
    gen = np.asarray(case.tables["AC_gen_dat"], dtype=float).copy()
    base_va = float(np.asarray(case.tables["Base_dat"], dtype=float).ravel()[0]) * 1e6

    if gen.shape[1] < 16:                       # 12~16열 자리를 만든다
        pad = np.full((gen.shape[0], 16 - gen.shape[1]), np.nan)
        gen = np.hstack([gen, pad])

    pv = [k for k in range(gen.shape[0]) if gen[k, 2] != SLACK_MODE]
    if not pv:
        return None, 0
    # |Q| 가 큰 쪽 절반을 조인다
    qmag = {k: abs(pq.get(int(gen[k, 0]), (0.0, 0.0))[1]) for k in pv}
    tight = sorted(pv, key=lambda k: -qmag[k])[:max(1, len(pv) // 2)]

    n_tight = 0
    for k in pv:
        p, q = pq.get(int(gen[k, 0]), (0.0, 0.0))
        if k in tight and qmag[k] > 1e-6:
            hi = abs(q) * 0.7
            n_tight += 1
        else:
            hi = abs(q) * 3.0 + 0.5             # 사실상 안 걸리는 넉넉한 값
        gen[k, 11] = hi * base_va               # 12열 Qmax
        gen[k, 12] = -hi * base_va              # 13열 Qmin
        if with_sn:
            gen[k, 15] = (np.hypot(p, q) * (0.9 if k in tight else 3.0)) * base_va
        else:
            gen[k, 15] = np.nan                 # 16열 S_N 비움

    new = case.copy()
    new.tables["AC_gen_dat"] = gen
    return new, n_tight


def volts(sol):
    a = np.asarray(sol.AC, dtype=float)
    if a.ndim == 3:
        a = a[:, :, 0]
    return a[:, 0], a[:, 1], a[:, 5]


def n_saturated(sol, case, gen_tab):
    """실제로 몇 대가 한계에 앉았나.

    🚨 **유효 한계 = min(Qmax, sqrt(S_N² − P²))** 로 봐야 한다(`effective_AC_gen_qlim.m` 과 같은 식).
       첫 판에서 `Qmax` 만 보고 세는 바람에 **용량 원으로 걸린 발전기를 안 세어**
       S_N 을 넣은 쪽의 대수가 도리어 줄어 보였다(case118 26 → 19).
    """
    b, _, q = volts(sol)
    a = np.asarray(sol.AC, dtype=float)
    if a.ndim == 3:
        a = a[:, :, 0]
    p_all = a[:, 4]
    base = float(np.asarray(case.tables["Base_dat"], dtype=float).ravel()[0])
    n = 0
    for k in range(gen_tab.shape[0]):
        if gen_tab[k, 2] == SLACK_MODE or not np.isfinite(gen_tab[k, 11]):
            continue
        i = np.where(b == gen_tab[k, 0])[0]
        if not len(i):
            continue
        i = i[0]
        pg, qg = p_all[i] / base, q[i] / base
        eff = gen_tab[k, 11] / (base * 1e6)
        if gen_tab.shape[1] >= 16 and np.isfinite(gen_tab[k, 15]) and gen_tab[k, 15] > 0:
            sn = gen_tab[k, 15] / (base * 1e6)
            eff = min(eff, np.sqrt(max(sn ** 2 - pg ** 2, 0.0)))
        if abs(qg) >= eff - 1e-6:
            n += 1
    return n


def main() -> int:
    OUT.mkdir(exist_ok=True)
    print(f"\n{'계통':<24}{'무엇':<12}{'조인 대수':>8}{'포화':>6}  결과")
    print("-" * 78)
    n_ok = n_bad = n_skip = 0

    for name in TARGETS:
        src = V14 / "cases_v2" / f"{name}_v2.xlsx"
        if not src.is_file():
            print(f"{name:<24}{'—':<12}{'':>8}{'':>6}  파일 없음"); n_skip += 1; continue
        base_case = load_case(str(src))

        for with_sn in (False, True):
            what = "Q한계+용량원" if with_sn else "Q한계만"
            try:
                case, n_tight = make_limited(base_case, with_sn)
            except Exception as exc:
                print(f"{name:<24}{what:<12}{'':>8}{'':>6}  준비 실패 — {str(exc)[:30]}")
                n_bad += 1; continue
            if case is None:
                print(f"{name:<24}{what:<12}{'':>8}{'':>6}  PV 발전기 없음"); n_skip += 1; continue

            path = OUT / f"{name}_qlim{'_sn' if with_sn else ''}_v2.xlsx"
            write_case(case, path)
            case = load_case(str(path))         # 엑셀을 거쳐 다시 읽는다 (실제 경로와 같게)
            gen_tab = np.asarray(case.tables["AC_gen_dat"], dtype=float)

            try:
                nr = app_engine.solve(case, method="nr")
            except Exception as exc:
                print(f"{name:<24}{what:<12}{n_tight:>8}{'':>6}  NR 실패 — {str(exc)[:26]}")
                n_bad += 1; continue
            try:
                gs = app_engine.solve(case, method="gs")
            except Exception as exc:
                print(f"{name:<24}{what:<12}{n_tight:>8}{'':>6}  GS 못 풂 — {str(exc)[:26]}")
                n_skip += 1; continue

            bn, vn, _ = volts(nr)
            bg, vg, _ = volts(gs)
            common, i_n, i_g = np.intersect1d(bn, bg, return_indices=True)
            if common.size == 0:
                print(f"{name:<24}{what:<12}{n_tight:>8}{'':>6}  ⚠️ 견준 버스 0 — 대조 실패")
                n_bad += 1; continue

            nsat = n_saturated(nr, case, gen_tab)
            d = float(np.max(np.abs(vn[i_n] - vg[i_g])))
            mark = "같음" if d <= TOL else f"다름 {d:.2e}"
            if nsat == 0:
                mark += "  ⚠️ 포화 0 — 한계를 검증하지 못했다"
            print(f"{name:<24}{what:<12}{n_tight:>8}{nsat:>6}  {mark} (버스 {common.size})")
            if d <= TOL and nsat > 0:
                n_ok += 1
            elif d > TOL:
                n_bad += 1
            else:
                n_skip += 1

    print("-" * 78)
    print(f"통과 {n_ok} · 어긋남 {n_bad} · 검증 못 함 {n_skip}")
    print(f"만든 파일: {OUT}\n")
    return 1 if n_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
