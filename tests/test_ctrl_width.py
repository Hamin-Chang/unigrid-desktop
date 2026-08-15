# -*- coding: utf-8 -*-
"""조정을 켜면 **필요한 칸만 채워도** 걸리나 (2026-08-14, §7 5단계 ③ 뒤처리).

    ~/venvs/unigrid-acdc/bin/python tests/test_ctrl_width.py

🚨 왜 있나 — 엔진은 `size(표,2) >= N` 으로 기능 유무를 가린다(「폭이 곧 뜻」). 그런데
   `scenario._put` 은 **값을 넣은 칸까지만** 표를 늘린다. 그래서 사용자가 자연스럽게
   필요한 칸만 채우면(SVC 를 걸면서 계단은 안 쓰니 `Shunt Step Size` 를 비움) 표가
   21열까지만 늘고 엔진은 22열이 아니라서 **조정을 통째로 무시했다 — 오류도 없이 조용히.**
   실측: 버스 14 에 SVC 를 걸었는데 전압이 1.0075 그대로였다(사용자가 *"이거 안되는데?"*).
   ⇒ `scenario._ensure_ctrl_width` 가 모드 칸이 켜져 있으면 끝 열까지 NaN 으로 늘린다.

   ⚠️ 어제 시험들이 이걸 못 잡은 이유 = **마지막 칸까지 0 을 넣고 있었다.**
      「시험이 쓰는 길」과 「사람이 쓰는 길」이 달랐다.
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
sys.path.insert(0, str(REPO / "src"))
warnings.filterwarnings("ignore")

import numpy as np                                           # noqa: E402
import app_engine                                            # noqa: E402
import scenario as SC                                        # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/AConly_case14_v2.xlsx"
BUS14, ROW14 = 14, 13          # 버스 14 = 14번째 줄
LINE9 = 8                      # 9번 선로(4→9) = 9번째 줄

#            이름                        표            줄      (열0부터, 값)                     기대 폭
CASES = [
    ("SVC — Step Size 를 비움",          "AC_Bus_dat",  ROW14,
     [(17, 2), (18, 1.03), (19, -50), (20, 50)],                                    22),
    ("SVC — Step Size 에 0",             "AC_Bus_dat",  ROW14,
     [(17, 2), (18, 1.03), (19, -50), (20, 50), (21, 0)],                           22),
    ("스위치드 션트 — 한계를 비움",       "AC_Bus_dat",  ROW14,
     [(17, 1), (18, 1.03), (21, 5)],                                                22),
    ("탭 — Step Size 를 비움",           "AC_Line_dat", LINE9,
     [(13, 1), (14, 9), (15, 1.035), (16, 0.9), (17, 1.1)],                         19),
    ("탭 — Mode·Bus·Target 만",          "AC_Line_dat", LINE9,
     [(13, 1), (14, 9), (15, 1.035)],                                               19),
    ("위상 — Mode·Target 만",            "AC_Line_dat", LINE9,
     [(13, 2), (15, 20.0)],                                                         19),
]


def main() -> int:
    base = load_case(str(CASE))
    checks = fails = 0

    def ok(cond, label, detail=""):
        nonlocal checks, fails
        checks += 1
        if not cond:
            fails += 1
        print(f"    {'✅' if cond else '🚨'} {label}" + (f"  {detail}" if detail else ""))

    # 기준 — 조정을 하나도 안 건 판
    sol0 = app_engine.solve(base)
    v0 = np.asarray(sol0.at("AC", 0))[:, 1].copy()
    w0 = {k: np.asarray(base.tables[k]).shape[1] for k in ("AC_Line_dat", "AC_Bus_dat")}
    print(f"기준 — 표 폭 {w0} · 버스 14 전압 {v0[ROW14]:.6f}\n")

    for name, key, row, typed, want_w in CASES:
        print(f"[{name}]")
        changes = [SC.Cell(table=key, row=row, col=c, value=v, label=f"{c}={v}", mark=())
                   for c, v in typed]
        c2 = SC.apply(base, changes)
        w = np.asarray(c2.tables[key]).shape[1]
        ok(w == want_w, f"표가 {want_w}열까지 늘었다", f"— {w}열")
        try:
            sol = app_engine.solve(c2)
        except Exception as e:
            ok(False, "풀린다", f"— 오류 {str(e)[:70]}")
            continue
        tp = np.asarray(sol.tap_ctrl, dtype=float)
        ok(tp.size > 0, "조정이 실제로 걸렸다 — 결과표가 비지 않았다",
           f"(줄 {tp.shape[0] if tp.size else 0}개)")
        if tp.size:
            v = np.asarray(sol.at("AC", 0))[:, 1]
            moved = abs(v[row if key == "AC_Bus_dat" else 8] - v0[row if key == "AC_Bus_dat" else 8])
            ok(moved > 1e-6, "계통이 실제로 움직였다", f"(전압차 {moved:.2e})")

    # R1 — 아무도 안 켜면 폭을 건드리지 않는다
    print("\n[R1] 조정을 안 켜면 폭이 그대로인가")
    c3 = SC.apply(base, [])
    same = all(np.asarray(c3.tables[k]).shape[1] == w0[k] for k in w0)
    ok(same, "폭 그대로", f"— {[np.asarray(c3.tables[k]).shape[1] for k in w0]}")
    # 조정과 무관한 칸만 고쳐도 그대로여야 한다
    c4 = SC.apply(base, [SC.Cell(table="AC_gen_dat", row=0, col=3, value=0.05,
                                 label="droop", mark=())])
    same2 = all(np.asarray(c4.tables[k]).shape[1] == w0[k] for k in w0)
    ok(same2, "조정과 무관한 편집도 폭을 안 건드린다")

    print(f"\n>>> 대조 {checks}개 · 실패 {fails}건")
    app_engine.shutdown()
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
