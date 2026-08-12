"""GS 와 NR 이 **정말 서로 다른 해법인가** — 수렴 양상으로 확인한다 (2026-08-12).

    python tests/gs_vs_nr_convergence.py

왜 이 검사가 필요한가
    지금까지의 검사는 전부 *"두 해법이 같은 답을 내는가"* 만 봤다. 그런데 답이 같다는 것만으로는
    **두 해법이 실제로 다른 길로 풀고 있는지** 알 수 없다 — 예를 들어 어디선가 잘못 이어져
    GS 를 부르면 Newton 이 돌고 있어도 검사는 전부 통과한다.

무엇을 보면 갈리나 — 교과서적 성질
    · **Newton-Raphson 은 2차 수렴**이라 반복 횟수가 계통 크기와 **거의 무관**하다(대개 3~10회).
    · **Gauss-Seidel 은 1차(선형) 수렴**이라 반복 횟수가 계통이 커질수록 **크게 늘어난다**.
    ⇒ 버스 수를 늘려 가며 반복 횟수를 재면, 두 해법이 구분돼 있는지가 **양상으로** 드러난다.
       비슷하게 나오면 그게 이상한 것이다.

읽는 법
    · `반복비` = GS 반복 ÷ NR 반복. 계통이 커질수록 커져야 정상이다.
    · `NR 반복` 이 계통 크기와 무관하게 한 자릿수에 머무르는지도 함께 본다.
"""
from __future__ import annotations

import sys, time, warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
warnings.filterwarnings("ignore")

import numpy as np
from load_case import load_case
import app_engine

V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")

# 버스 수가 커지는 차례로 (GS 가 너무 느린 1888rte·6495rte·25k 는 뺐다)
CASES = [
    "AConly_case9", "AConly_case14", "AConly_case30",
    "AConly_pandapower_3w", "AConly_case118", "AConly_case118_psse",
]
REPEAT = 3          # 시간은 흔들리므로 여러 번 재서 가장 빠른 값을 쓴다


def run(case, method):
    """(반복 횟수, 가장 빠른 시간[초], 버스 수)"""
    best = float("inf")
    sol = None
    for _ in range(REPEAT):
        t0 = time.perf_counter()
        sol = app_engine.solve(case, method=method)
        best = min(best, time.perf_counter() - t0)
    a = np.asarray(sol.AC, dtype=float)
    if a.ndim == 3:
        a = a[:, :, 0]
    return int(sol.iters), best, a.shape[0]


def main() -> int:
    print(f"\n{'계통':<22}{'버스':>5}{'NR 반복':>8}{'GS 반복':>9}{'반복비':>8}"
          f"{'NR 초':>8}{'GS 초':>8}{'시간비':>8}")
    print("-" * 78)
    rows = []
    for name in CASES:
        p = V14 / f"cases_v2/{name}_v2.xlsx"
        if not p.is_file():
            print(f"{name:<22}파일 없음"); continue
        case = load_case(str(p))
        try:
            n_it, n_t, nb = run(case, "nr")
            g_it, g_t, _ = run(case, "gs")
        except Exception as exc:
            print(f"{name:<22}{'':>5}실패 — {str(exc)[:40]}"); continue
        r_it = g_it / n_it if n_it else float("nan")
        r_t = g_t / n_t if n_t else float("nan")
        print(f"{name:<22}{nb:>5}{n_it:>8}{g_it:>9}{r_it:>8.1f}"
              f"{n_t:>8.3f}{g_t:>8.3f}{r_t:>8.1f}")
        rows.append((nb, n_it, g_it))

    print("-" * 78)
    if len(rows) < 2:
        print("⚠️ 견줄 케이스가 모자라 판정할 수 없습니다.\n")
        return 1

    rows.sort()
    nb0, n0, g0 = rows[0]
    nb1, n1, g1 = rows[-1]
    print(f"버스 {nb0} → {nb1} 로 커질 때")
    print(f"   NR 반복 {n0} → {n1}   ({n1 / n0:.1f}배)")
    print(f"   GS 반복 {g0} → {g1}   ({g1 / g0:.1f}배)")

    # 판정 — 교과서적 성질이 실제로 나타나는가
    ok = True
    if max(n for _, n, _ in rows) > 30:
        print("   ⚠️ NR 반복이 30회를 넘는다 — 2차 수렴답지 않다"); ok = False
    if min(g for _, _, g in rows) < 20:
        print("   ⚠️ GS 반복이 20회 미만인 계통이 있다 — 1차 수렴답지 않다"); ok = False
    if (g1 / g0) <= (n1 / n0) * 1.5:
        print("   ⚠️ 계통이 커져도 GS 반복이 NR 만큼밖에 안 는다 — 두 해법이 구분되는지 의심스럽다")
        ok = False
    print(f"\n{'✅ 두 해법의 수렴 양상이 확실히 다르다 — 서로 다른 알고리즘이 맞다' if ok else '🚨 양상이 기대와 다르다 — 확인이 필요하다'}\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
