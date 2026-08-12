# -*- coding: utf-8 -*-
"""B3 — 안 풀릴 때 어디까지면 풀리는지 (2026-08-12, §7 4단계).

  1) 곡선(F1)의 코 끝점과 답이 맞나 — 같은 물음이므로 맞아야 한다
  2) 🚨 한계를 뗀 답을 "풀림" 으로 세지 않나 — 세면 없는 여유를 있다고 말한다
  3) 곡선이 못 그리는 AC/DC 계통에서도 답이 나오나
  4) 부하를 줄여도 못 푸는 경우를 가려내나

⚠️ **이 기능은 화면에 붙이지 않았다** (2026-08-12 사용자 결정 — 아래).
   `app_engine.last_solvable` 은 검증까지 끝난 코드라 지우지 않고 두었고, 이 시험이 그것을 지킨다.
   화면에 다시 붙일 일이 생기면 단추만 달면 된다.
"""
import os
import sys
import time
from pathlib import Path

REPO = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/unigrid-desktop")
V2 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
          "/Phase A_Balance/newest/v14/cases_v2")
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import warnings                                          # noqa: E402
warnings.filterwarnings("ignore")
from PySide6.QtWidgets import QApplication                # noqa: E402

qapp = QApplication([])
import app_engine as E                                    # noqa: E402
import scenario as SC                                     # noqa: E402
from load_case import load_case                           # noqa: E402

fails = []

print("=== 1) 곡선의 코 끝점과 맞나 (case14) ===")
case = load_case(str(V2 / "AConly_case14_v2.xlsx"))
cur = E.curve(case)
nose = 1 + cur.lam_crit
heavy = SC.apply(case, [SC.scale_load(2.0)])
r = E.last_solvable(heavy)
got = r.factor * 2.0 if r.factor else float("nan")
print(f"  곡선 {nose:.4f} 배 · B3 {got:.4f} 배 · 차이 {abs(got - nose):.4f}")
ok = abs(got - nose) < 0.06          # 이분법 6회의 눈금(±0.03)보다 넉넉히
print(f"  {'✅ 맞음' if ok else '🚨 다름'}")
fails += [] if ok else ["곡선과 안 맞음"]

print("\n=== 2) 한계를 뗀 답을 풀림으로 세지 않나 ===")
# 🚨 엔진은 한계를 걸어 수렴 못 하면 **한계를 뗀 답**을 주고 qlim_enforced=False 로 밝힌다.
#    그 답은 최저 전압이 오히려 높다(case14 ×1.9 → 0.7336 / ×2.0 → 0.9825).
loose = E.last_solvable(heavy, require_qlim=False)
print(f"  한계를 안 따지면 원래 부하의 {loose.factor * 2:.3f} 배까지라고 한다")
print(f"  한계를 따지면            {got:.3f} 배 (곡선 {nose:.3f})")
ok2 = loose.factor > r.factor + 0.05
print(f"  {'✅ 둘이 갈린다 — 따지는 쪽이 맞다' if ok2 else '🚨 안 갈림 (이 계통으로는 확인 불가)'}")
fails += [] if ok2 else ["한계 구분 확인 실패"]

print("\n=== 3) 곡선이 못 하는 AC/DC 계통 ===")
ac = load_case(str(V2 / "ACDC_71bus_v2.xlsx"))
print("  곡선 거부:", E.curve_refusal(ac))
h2 = SC.apply(ac, [SC.scale_load(10.0)])
try:
    E.solve(h2)
    print("  🚨 ×10 이 풀림 — 이 시험은 못 씀")
    fails.append("AC/DC 시험 못 함")
except Exception:
    r2 = E.last_solvable(h2)
    ok3 = r2.factor is not None
    print(f"  B3 답: 원래 부하의 {r2.factor * 10:.3f} 배까지 "
          f"(조류계산 {r2.n_solve}회 · {r2.seconds:.1f}초)" if ok3 else "  🚨 답 없음")
    fails += [] if ok3 else ["AC/DC 답 없음"]

print("\n=== 4) 부하를 줄여도 못 푸는 경우 ===")
bad = SC.apply(case, [SC.Cell(table="AC_Line_dat", row=i, col=12, value=0.0,
                              label=f"선로 {i+1} 끄기") for i in range(3)])
r3 = E.last_solvable(bad, rounds=3)
ok4 = r3.factor is None and "계통 모양" in r3.note
print(f"  {r3.note[:80]}")
print(f"  {'✅ 부하 탓이 아니라고 가려낸다' if ok4 else '🚨 못 가려냄'}")
fails += [] if ok4 else ["못 푸는 경우 못 가려냄"]

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.exit(1 if fails else 0)
