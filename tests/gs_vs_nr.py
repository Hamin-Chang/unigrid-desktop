"""GS 와 NR 이 같은 답을 내는가 — 한 명령으로 (PDR §7.6 G0).

    python tests/gs_vs_nr.py            전부
    python tests/gs_vs_nr.py --only 3w  이름에 그 글자가 든 것만

왜 이 파일이 있나
    §7 4단계는 GS(전기연 배포본에서 옮겨온 Gauss-Seidel)를 NR(우리 엔진)과 맞추는 일이다.
    G1~G8 을 밟는 내내 **같은 명령으로** 어디까지 맞았는지 봐야 한다.

🚨 케이스 대장의 규칙 — **그 기능이 실제로 켜진 케이스**여야 한다.
    2026-08-11 에 3권선 케이스 셋 중 둘이 **탭비가 1·0** 이라 헛통과했고,
    데드밴드는 38개가 잡혔지만 대부분 `1e-06`(사실상 꺼짐)이었다.
    ⇒ 케이스를 넣을 때 표 안의 값을 열어 그 기능이 켜져 있는지 보고 넣는다.

🚨 **S_N(발전기 용량 원)이 켜진 케이스는 MATPOWER 대조에 쓰지 않는다.**
    MATPOWER 조류계산은 `QMAX`/`QMIN` 상수만 보고 용량 곡선은 **OPF 에서만** 쓴다
    (`runpf.m` 368~412행 · `makeApq.m`). 어긋나는 게 정상인데 모르고 보면 우리 결함으로 오해한다.
    여기(GS↔NR 대조)에서는 **양쪽 다 우리 엔진**이라 써도 된다.
"""
from __future__ import annotations

import sys, warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
warnings.filterwarnings("ignore")

import numpy as np
from load_case import load_case
import app_engine

V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")

# (이름, 파일, 무엇을 보는 케이스인가, 어느 G 단계에서 통과해야 하나)
CASES = [
    # case14 는 12·13열(Qmax/Qmin)이 있는 **한계 케이스**다 — GS 에 Q 한계가 없어 지금은 다르다.
    ("기본 AC 14",   V14 / "cases_v2/AConly_case14_v2.xlsx",        "Q한계(12·13열)",    "G2"),
    ("기본 AC 30",   V14 / "cases_v2/AConly_case30_v2.xlsx",        "기본",              "이미"),
    ("기본 AC 118",  V14 / "cases_v2/AConly_case118_v2.xlsx",       "기본",              "이미"),
    ("3W 일반",      V14 / "cases_v2/AConly_pandapower_3w_v2.xlsx", "3권선 · 위상 30도", "이미"),
    # 🚨 이 케이스는 3권선 탭(옛 형식 · 24열 tap side=2 · 25열 1.05)을 보려고 두었고,
    #    그쪽은 G1 전부터 이미 맞았다. 2026-08-12 에 "다름"으로 바뀐 것은 3권선과 무관하다 —
    #    발전기 무효 한계가 이 파일에도 켜져 있는데, **한계를 걸었다 무르는 판정이 두 도구에서 갈린다**:
    #      NR : 한계를 걸고 다시 풀다 실패 → 한계를 무른 답 (전압 1.010)
    #      GS : 한계를 걸고 다시 풀어 **성공** → 그 답 (전압 1.235)
    #    GS 가 틀린 게 아니라 NR 이 도달하지 못한 해에 GS 가 도달한 것이다. G8(통합)에서 규칙을 맞춘다.
    ("3W 탭",        V14 / "cases_v2/AConly_psse_3W_unigrid_easy_v2.xlsx",
     "옛 형식 탭 1.05 · 한계 갈림", "G8"),
    ("3W 권선별탭",  V14 / "cases_v2/gs_3w_wtap_v2.xlsx",           "31~33열 탭",        "G1"),
    ("Q한계+용량원", V14 / "cases_v2/gs_genlim_sn_v2.xlsx",         "S_N 50 MVA 포화",   "G2"),
    # 🚨 아래 셋은 **거부되어야 맞는** 케이스다 (2026-08-12 확정).
    #    Gauss-Seidel 은 droop 발전기를 다루지 않기로 했고, 엔진이 오류로 막는다.
    #    막기 전에는 droop 버스가 어느 분기에도 안 걸려 **조용히 틀린 답**이 나왔다.
    ("droop",        V14 / "cases_v2/gs_droop_v2.xlsx",             "Gen Mode 1",        "거부"),
    ("droop+DB",     V14 / "cases_v2/gs_droop_db_v2.xlsx",          "데드밴드 0.01",     "거부"),
    ("다시각 droop", V14 / "cases_v2/AConly_noslackAC_v2.xlsx",     "25시각 · 전부 droop", "거부"),
]

TOL = 1e-4          # 전압 pu. 결과표가 4자리 반올림이라 그 아래는 못 본다


def volts(sol):
    ac = np.asarray(sol.AC, dtype=float)
    if ac.ndim == 3:
        ac = ac[:, :, 0]
    return ac[:, 0], ac[:, 1]


def main() -> int:
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]

    print(f"\n{'케이스':<14}{'무엇을 보나':<22}{'단계':<6}결과")
    print("-" * 74)
    n_ok = n_bad = n_skip = 0

    for name, path, what, stage in CASES:
        if only and only not in path.name and only not in name:
            continue
        if not path.is_file():
            print(f"{name:<14}{what:<22}{stage:<6}파일 없음"); n_skip += 1; continue

        case = load_case(str(path))
        try:
            nr = app_engine.solve(case, method="nr")
        except Exception as exc:
            print(f"{name:<14}{what:<22}{stage:<6}⚠️ NR 실패 — {str(exc)[:40]}")
            n_bad += 1; continue
        try:
            gs = app_engine.solve(case, method="gs")
        except Exception as exc:
            # "거부" 로 표시한 케이스는 **막히는 것이 정답**이다.
            if stage == "거부":
                good = "droop 발전기를 다루지 못합니다" in str(exc)
                print(f"{name:<14}{what:<22}{stage:<6}"
                      f"{'거부됨 ✅' if good else '막히긴 했으나 다른 이유 ⚠️ ' + str(exc)[:30]}")
                n_ok += 1 if good else 0
                n_bad += 0 if good else 1
                continue
            print(f"{name:<14}{what:<22}{stage:<6}GS 못 풂 — {str(exc)[:40]}")
            n_skip += 1; continue
        if stage == "거부":
            print(f"{name:<14}{what:<22}{stage:<6}⚠️ 막혔어야 하는데 풀렸다")
            n_bad += 1; continue

        bn, vn = volts(nr)
        bg, vg = volts(gs)
        common, i_n, i_g = np.intersect1d(bn, bg, return_indices=True)
        if common.size == 0:
            print(f"{name:<14}{what:<22}{stage:<6}⚠️ 견준 버스 0 — 대조 실패")
            n_bad += 1; continue

        d = float(np.max(np.abs(vn[i_n] - vg[i_g])))
        mark = "같음" if d <= TOL else f"다름 {d:.2e}"
        print(f"{name:<14}{what:<22}{stage:<6}{mark}  (버스 {common.size})")
        if d <= TOL:
            n_ok += 1
        else:
            n_bad += 1

    print("-" * 74)
    print(f"같음 {n_ok} · 다름 {n_bad} · 건너뜀 {n_skip}\n")
    # 아직 안 맞춘 단계가 있으므로 "다름" 이 있어도 실패로 끝내지 않는다.
    # 어디까지 맞았는지 보는 것이 이 검사의 목적이다.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
