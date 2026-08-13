# -*- coding: utf-8 -*-
"""위상 조정기를 **앱에서 손으로 쳐서** 걸 수 있나 (2026-08-13, 사용자 요청).

사용자: *"예시 파일 말고 내가 입력해서 써볼 수 있고 싶어"*

  1) **아무 것도 안 걸린 옛 파일**을 열고 8번 선로에 위상 조정을 친다
     (Ctrl Mode=2 · Target=30 MW · Min/Max=±20°)
  2) `Ctrl Mode` 에 2 를 치면 **다음 칸이 `Ctrl Target`** 이다 (Ctrl Bus 는 안 쓴다)
  3) [이 조건으로 계산] 을 누른 것과 같게 풀면 **조류가 30 MW 가 되나**
  4) 「점검」 탭 카드가 **위상**이라고 말하나

⚠️ 컴파일된 엔진을 쓴다 — 위상 조정은 엔진 **17차**부터 들어 있다.
"""
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import warnings                                              # noqa: E402
warnings.filterwarnings("ignore")
import numpy as np                                           # noqa: E402
from PySide6.QtWidgets import (QApplication, QMessageBox,    # noqa: E402
                               QTabWidget, QTableWidget, QTableWidgetItem)

qapp = QApplication([])
import app as APP                                            # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                            # noqa: E402
import scenario as SC                                        # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/AConly_case14_v2.xlsx"    # 🚨 조정이 **하나도 안 걸린** 파일
ROW = 7            # 0부터 — 8번 선로(변압기 4→7)
TARGET = 30.0      # MW

win = APP.Proto()
win.resize(1500, 950)
win.show()


def pump(s=0.35):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


case = load_case(str(CASE))
win.thread = Fake(case)
win._last_path = str(CASE)
win._solved(app_engine.solve(case))
win.table_tab = "계통 데이터"
win.grid_key = "AC_Line_dat"
win.rebuild()
pump()

fails = []
before = float(np.asarray(win.sol.at("Branch", 0))[ROW, 2])
print(f"\n손대기 전 8번 선로 From P = {before:.4f} MW")


def open_tab(name):
    tw = win._tabs
    for i in range(tw.count()):
        if tw.tabText(i).startswith(name):
            tw.setCurrentIndex(i)
            pump(0.25)
            return True
    return False


print("\n[1] 옛 파일에 손으로 위상 조정을 친다")
tb = win._grid_tb
off = win._grid_off
typed = [(13, 2), (15, TARGET), (16, -20), (17, 20), (18, 0)]   # Ctrl Bus 는 안 친다
for col, val in typed:
    it = QTableWidgetItem(f"{val:g}")
    tb.setItem(ROW, col + off, it)
    win.grid_edited("AC_Line_dat", it, off, {})
    pump(0.15)
    tb, off = win._grid_tb, win._grid_off
    if col == 13:
        nxt = (tb.currentRow(), tb.currentColumn())
        want = (ROW, 15 + off)
        print(f"\n[2] Ctrl Mode 에 2 를 친 뒤 골라진 칸 = {nxt} "
              f"(바라는 것 {want} = Ctrl Target)")
        ok2 = nxt == want
        print(f"    {'✅ Ctrl Bus 를 건너뛴다' if ok2 else '🚨 안 건너뛴다'}")
        if not ok2:
            fails.append("Ctrl Bus 안 건너뜀")
print(f"\n    바꾼 것 {len(win.changes)}건")
for ch in win.changes:
    print(f"      · {ch.label}")
ok1 = len(win.changes) == len(typed)
print(f"    {'✅' if ok1 else '🚨 건수가 다르다'}")
if not ok1:
    fails.append("바꾼 것 건수")

print("\n[3] 그 조건으로 풀면 조류가 목표가 되나")
c2 = SC.apply(win.base_case, win.applied + win.changes)
sol2 = app_engine.solve(c2)
got = float(np.asarray(sol2.at("Branch", 0))[ROW, 2])
tap = np.asarray(sol2.tap_ctrl, dtype=float)
print(f"    8번 선로 From P = {got:.4f} MW  (목표 {TARGET})  · 오차 {abs(got-TARGET):.2e}")
print(f"    조정 표 = {tap}")
ok3 = abs(got - TARGET) < 1e-3 and tap.shape[0] == 1 and tap[0, 8] == 2
print(f"    {'✅ 화면에서 친 것이 계산까지 갔다' if ok3 else '🚨 안 갔다'}")
if not ok3:
    fails.append("계산까지 안 감")

print("\n[4] 점검 탭 카드가 「위상」이라고 말하나")
win._solved(sol2)
win.rebuild()
pump()
open_tab("점검")
card = None
for t in win.findChildren(QTableWidget):
    heads = [t.horizontalHeaderItem(i).text() if t.horizontalHeaderItem(i) else ""
             for i in range(t.columnCount())]
    if "정해진 값" in heads:
        card = t
if card is None:
    print("    🚨 카드가 없다")
    fails.append("카드 없음")
else:
    vals = [card.item(0, c).text() for c in range(card.columnCount())]
    print(f"    표 내용 {vals}")
    ok4 = vals[0] == "위상" and vals[2] == "이 선로" and "MW" in vals[3] and "°" in vals[4]
    print(f"    {'✅ 방식·단위가 위상용이다' if ok4 else '🚨 아니다'}")
    if not ok4:
        fails.append("카드 내용")
    win.grab().save(str(OUT / "A1_위상_손으로입력.png"))

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if fails else 0)
