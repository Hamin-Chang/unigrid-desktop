# -*- coding: utf-8 -*-
"""A1 조정을 「계통 데이터」 탭에서 켤 수 있나 (2026-08-13, §7 5단계 3번 나머지).

  1) **옛 파일(13열)에도** 조정 칸이 빈 칸으로 보이나 — 안 보이면 켤 방법이 없다
  2) 그 칸을 고치면 '바꾼 것' 에 얹히나 (계산은 아직 안 돈다)
  3) [이 조건으로 계산] 을 누른 것과 같게 풀면 **탭이 실제로 움직이나**
  4) 조정 칸이 아닌 곳(예: 선로 저항)은 여전히 못 고치나
"""
import os
import sys
import time
from pathlib import Path

REPO = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/unigrid-desktop")
V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import warnings                                              # noqa: E402
warnings.filterwarnings("ignore")
import numpy as np                                           # noqa: E402
from PySide6.QtWidgets import (QApplication, QMessageBox,    # noqa: E402
                               QTableWidget, QTableWidgetItem)
from PySide6.QtCore import Qt                                # noqa: E402

qapp = QApplication([])
import app as APP                                            # noqa: E402
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)
import app_engine                                            # noqa: E402
import scenario as SC                                        # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/AConly_case14_v2.xlsx"     # 🚨 조정 칸이 **없는** 옛 파일
ROW = 8          # 0부터 — 9번 선로(변압기 4→9)
BUS = 9
TARGET = 1.035

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


case = load_case(str(CASE))
win.thread = Fake(case)
win._last_path = str(CASE)
win._solved(app_engine.solve(case))
win.grid_key = "AC_Line_dat"
win.rebuild()
pump()

fails = []
print(f"\n연 파일의 AC_Line_dat 폭 = {np.asarray(case.tables['AC_Line_dat']).shape[1]}열")


def grid():
    """계통 데이터 탭의 표를 찾는다 (머리글로 가린다)."""
    for t in win.findChildren(QTableWidget):
        heads = [t.horizontalHeaderItem(i).text() if t.horizontalHeaderItem(i) else ""
                 for i in range(t.columnCount())]
        if "Ctrl Mode" in heads:
            return t, heads
    return None, []


print("\n[1] 옛 파일에도 조정 칸이 보이나")
tb, heads = grid()
if tb is None:
    print("    🚨 Ctrl 칸이 안 보인다")
    fails.append("칸이 안 보임")
else:
    print(f"    보인다 ✅ — 머리글 뒤쪽 {heads[-6:]}")
    off = 1 if SC.SWITCHES.get("AC_Line_dat") else 0
    cell = tb.item(ROW, 13 + off)
    editable = bool(cell.flags() & Qt.ItemIsEditable)
    print(f"    9번 줄 Ctrl Mode 칸: 값 {cell.text()!r} · 고칠 수 있나 {editable}")
    if not editable:
        fails.append("Ctrl Mode 를 못 고침")

print("\n[2] 고치면 '바꾼 것' 에 얹히나")
off = 1 if SC.SWITCHES.get("AC_Line_dat") else 0
for col, val in ((13, 1), (14, BUS), (15, TARGET), (16, 0.9), (17, 1.1), (18, 0)):
    it = QTableWidgetItem(f"{val:g}")
    tb.setItem(ROW, col + off, it)          # 사람이 친 것과 같은 길
    win.grid_edited("AC_Line_dat", it, off, {})
    tb, heads = grid()                      # rebuild 로 표가 새로 만들어진다
print(f"    바꾼 것 {len(win.changes)}건")
for ch in win.changes:
    print(f"      · {ch.label}")
ok2 = len(win.changes) == 6
print(f"    {'✅' if ok2 else '🚨 6건이 아니다'}")
if not ok2:
    fails.append("바꾼 것 건수")

print("\n[3] 그 조건으로 풀면 탭이 실제로 움직이나")
c2 = SC.apply(win.base_case, win.applied + win.changes)
w = np.asarray(c2.tables["AC_Line_dat"]).shape[1]
sol2 = app_engine.solve(c2)
v9 = sol2.at("AC", 0)[BUS - 1, 1]
tap = np.asarray(sol2.tap_ctrl)
print(f"    표가 {w}열로 늘었다 · 버스 {BUS} 전압 {v9:.6f} (목표 {TARGET})")
print(f"    탭 결과 {tap}")
ok3 = w == 19 and abs(v9 - TARGET) < 1e-6 and tap.shape[0] == 1
print(f"    {'✅ 화면에서 켠 것이 계산까지 갔다' if ok3 else '🚨 안 갔다'}")
if not ok3:
    fails.append("계산까지 안 감")

print("\n[4] 조정 칸이 아닌 곳은 여전히 못 고치나")
tb, heads = grid()
r_cell = tb.item(ROW, 3 + off)              # 4열 = R
locked = not (r_cell.flags() & Qt.ItemIsEditable)
print(f"    R 칸 잠김 {locked} {'✅' if locked else '🚨 열려 있다'}")
if not locked:
    fails.append("R 칸이 열림")

# ⚠️ 표를 다시 그린 직후에 바로 찍으면 **빈 화면**이 나온다(2026-08-13 실측).
#    「계통 데이터」 탭을 열고 이벤트를 한 번 돌린 뒤에 찍는다.
from PySide6.QtWidgets import QTabWidget                     # noqa: E402
win.grid_key = "AC_Line_dat"
win.rebuild()
pump(0.4)
for tw in win.findChildren(QTabWidget):
    if not tw.isVisible():
        continue
    for i in range(tw.count()):
        if tw.tabText(i).startswith("계통 데이터"):
            tw.setCurrentIndex(i)
            pump(0.5)
win.grab().save(str(OUT / "A1_계통데이터_편집.png"))
print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.exit(1 if fails else 0)
