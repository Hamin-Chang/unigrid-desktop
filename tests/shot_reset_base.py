# -*- coding: utf-8 -*-
"""「⟲ 원본으로」 — 계산해서 굳은 조건에서 원본으로 돌아갈 수 있나 (2026-08-15).

사용자가 짚은 것: *"선로 4번을 껐는데, 다음 시나리오로 5번을 끄고 싶다.
직접 되돌리는 게 불안하다"*

무엇이 문제였나
    「↩ 되돌리기」는 **아직 계산 안 한 것**만 지운다. [이 조건으로 계산] 을 누르는 순간
    그 조건은 굳고, 조건 띠는 `changes` 가 비면 **통째로 사라진다**.
    원본으로 가는 길은 시나리오 목록 안에만 있었고, 그 목록은 시나리오가 2개 이상일 때만
    그려지며 거기가 *조건을 되돌리는 곳* 이라고 말하지도 않는다.
    ⇒ 기능은 있는데 **길이 안 보였다.**

이 시험이 보는 것
    1) 계산해서 굳은 뒤에도 조건 띠가 **남아 있나** (예전엔 사라졌다)
    2) 그 띠에 [⟲ 원본으로] 가 있고, 물릴 것이 없으니 [↩ 되돌리기] 는 **없나**
    3) 눌렀을 때 **원본 결과로 돌아가나** (선로가 다시 켜지나)
    4) 그 뒤 **선로 5번만** 끌 수 있나  ← 사용자가 하려던 바로 그 일
    5) 원본으로 갔다고 **시나리오가 지워지지는 않나**
    6) 원본을 보고 있을 때는 [⟲ 원본으로] 가 **안 뜨나** (갈 곳이 없다)
"""
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import warnings                                              # noqa: E402
warnings.filterwarnings("ignore")
import numpy as np                                           # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton   # noqa: E402

qapp = QApplication([])
import app as APP                                            # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                            # noqa: E402
import scenario as SC                                        # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/AConly_case14_v2.xlsx"
LINE_A, LINE_B = 3, 4          # 화면 줄(0부터) = 선로 4번 · 5번

win = APP.Proto()
win.resize(1500, 950)
win.show()


def pump(s=0.3):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


def buttons() -> list[str]:
    """지금 화면 위쪽(조건 띠 + 시나리오 카드)에 붙어 있는 단추 이름들.

    ⚠️ 「⟲ 원본으로」는 2026-08-15 하루에 **두 번 옮겨졌다** — 조건 띠 → 시나리오 카드 머리
       (띠가 카드와 같은 말을 하며 44px 을 먹었다) → **다시 조건 띠**(시나리오 목록을 아래
       탭으로 내리면서 위쪽에 남은 것이 얇은 띠뿐이 됐다). **지금 자리는 조건 띠다.**
       ⇒ 시험은 단추가 **어디에** 있는지가 아니라 **화면에 있는지**를 봐야 하므로 둘 다 훑는다.
       자리가 또 바뀌어도 이 시험은 안 깨진다.
    """
    out = []
    for w in (win.change_bar(), win.scenario_bar()):
        if w is not None:
            out += [b.text() for b in w.findChildren(QPushButton)]
    return out


def solve_now():
    """[이 조건으로 계산] 이 하는 일을 그대로 — 풀어서 시나리오로 담는다."""
    pend = win.applied + win.changes
    sol = app_engine.solve(SC.apply(win.base_case, pend))
    win._pending, win._pending_new = pend, list(win.changes)
    win._solved(sol)
    win.rebuild()
    pump()


fails = []
case = load_case(str(CASE))
win.thread = Fake(case)
win._last_path = str(CASE)
win._solved(app_engine.solve(case))
win.rebuild()
pump()

v_base = float(np.asarray(win.sol.AC, dtype=float)[:, 1].min())
print(f"\n원본 — 시나리오 {len(win.book.items)}개 · 전압 최저 {v_base:.5f} pu")

print("\n[6] 원본을 보고 있을 때는 「원본으로」가 안 떠야 한다 (갈 곳이 없다)")
b0 = buttons()
ok6 = not any("원본으로" in t for t in b0)
print(f"    띠의 단추 {b0}  {'✅ 없다' if ok6 else '🚨 떠 있다'}")
if not ok6:
    fails.append("원본에서도 버튼이 뜬다")

print("\n[0] 선로 4번을 끄고 계산한다 (사용자가 한 그대로)")
win.grid_key = "AC_Line_dat"
win.flip_row(LINE_A)
pump(0.2)
solve_now()
v_a = float(np.asarray(win.sol.AC, dtype=float)[:, 1].min())
print(f"    바꾼 것 {len(win.changes)}건 · 굳은 조건 {len(win.applied)}건 · "
      f"전압 최저 {v_a:.5f} pu · 시나리오 {len(win.book.items)}개")

print("\n[1] 계산해서 굳은 뒤에도 **돌아갈 자리**가 화면에 남아 있나")
# 보는 것은 *자리가 있나* 다 — 조건 띠든 시나리오 카드든 한쪽만 있으면 된다.
ok1 = win.change_bar() is not None or win.scenario_bar() is not None
print(f"    돌아갈 자리 {'있다 ✅' if ok1 else '없다 🚨'}")
if not ok1:
    fails.append("돌아갈 자리 없음")

print("\n[2] [⟲ 원본으로] 는 있고 [↩ 되돌리기] 는 없나")
b1 = buttons()
has_home = any("원본으로" in t for t in b1)
has_undo = any("되돌리기" in t for t in b1)
print(f"    띠의 단추 {b1}")
ok2 = has_home and not has_undo
print(f"    원본으로 {has_home} · 되돌리기 {has_undo} "
      f"{'✅ (물릴 것이 없으니 되돌리기는 안 뜬다)' if ok2 else '🚨'}")
if not ok2:
    fails.append("단추 구성")

print("\n[3] 누르면 원본 결과로 돌아가나")
win.reset_to_base()
pump()
v_back = float(np.asarray(win.sol.AC, dtype=float)[:, 1].min())
on = SC.is_on(win.base_case, "AC_Line_dat", LINE_A, win.applied)
print(f"    굳은 조건 {len(win.applied)}건 · 전압 최저 {v_back:.5f} pu "
      f"· 선로 {LINE_A + 1}번 켜짐 {on}")
ok3 = (not win.applied) and on and abs(v_back - v_base) < 1e-12
print(f"    {'✅ 원본이다' if ok3 else '🚨 아니다'}")
if not ok3:
    fails.append("원본으로 안 돌아감")

print("\n[4] 그 뒤 선로 5번만 끌 수 있나  ← 사용자가 하려던 일")
win.grid_key = "AC_Line_dat"
win.flip_row(LINE_B)
pump(0.2)
a_on = SC.is_on(win.base_case, "AC_Line_dat", LINE_A, win.applied + win.changes)
b_on = SC.is_on(win.base_case, "AC_Line_dat", LINE_B, win.applied + win.changes)
print(f"    선로 {LINE_A + 1}번 켜짐 {a_on} · 선로 {LINE_B + 1}번 켜짐 {b_on}")
ok4 = a_on and not b_on and len(win.changes) == 1
print(f"    {'✅ 5번만 꺼졌다' if ok4 else '🚨 아니다'}")
if not ok4:
    fails.append("5번만 끄기")

print("\n[5] 원본으로 갔다고 시나리오가 지워지지는 않나")
names = [s.name for s in win.book.items]
ok5 = len(win.book.items) >= 2
print(f"    시나리오 {names}  {'✅ 남아 있다' if ok5 else '🚨 지워졌다'}")
if not ok5:
    fails.append("시나리오 사라짐")

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if fails else 0)
