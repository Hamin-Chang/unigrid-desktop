# -*- coding: utf-8 -*-
"""SVC 를 **앱에서 손으로 쳐서** 걸 수 있나 (2026-08-13, §7 5단계 ④).

  1) 「AC 버스」 표에 조정 칸(Shunt …)이 **옛 17열 파일에서도** 보이나
  2) 그 칸을 고치면 '바꾼 것' 에 얹히나
  3) 그 조건으로 풀면 **그 버스 전압이 목표가 되나**
  4) 「점검」 탭 카드가 **SVC** 라고 말하나 (선로 자리는 「—」·값은 Mvar)
  5) 조정 칸이 아닌 곳(예: V_min)은 여전히 못 고치나

⚠️ 컴파일된 엔진을 쓴다 — SVC 는 엔진 **19차**부터 들어 있다.
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
from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtWidgets import (QApplication, QMessageBox,    # noqa: E402
                               QTableWidget, QTableWidgetItem)

qapp = QApplication([])
import app as APP                                            # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                            # noqa: E402
import scenario as SC                                        # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/AConly_case14_v2.xlsx"    # 🚨 조정이 **하나도 안 걸린** 파일
BUS = 14           # 발전기가 없는 버스
ROW = BUS - 1      # 화면 줄 (0부터)
TARGET = 1.03

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
win.grid_key = "AC_Bus_dat"
win.rebuild()
pump()

fails = []
w0 = np.asarray(case.tables["AC_Bus_dat"]).shape[1]
before = float(np.asarray(win.sol.at("AC", 0))[ROW, 1])
print(f"\n연 파일의 AC_Bus_dat 폭 = {w0}열 · 손대기 전 버스 {BUS} 전압 {before:.6f}")

print("\n[1] 옛 파일에도 조정 칸이 보이나")
tb, off = win._grid_tb, win._grid_off
heads = [tb.horizontalHeaderItem(i).text() for i in range(tb.columnCount())]
print(f"    오른쪽 끝 머리글 {heads[-5:]}")
# 머리글에는 단위가 붙는다("Shunt Step Size [Mvar]") — 떼고 견준다.
bare = [h.split("[")[0].strip() for h in heads]
ok1 = "Shunt Ctrl Mode" in bare and "Shunt Step Size" in bare
cell = tb.item(ROW, 17 + off)
editable = bool(cell.flags() & Qt.ItemIsEditable)
print(f"    버스 {BUS} 의 Shunt Ctrl Mode 칸: 값 {cell.text()!r} · 고칠 수 있나 {editable}")
ok1 = ok1 and editable
print(f"    {'✅ 보이고 고칠 수 있다' if ok1 else '🚨 아니다'}")
if not ok1:
    fails.append("칸이 안 보임")

print("\n[2] 고치면 '바꾼 것' 에 얹히나")
typed = [(17, 2), (18, TARGET), (19, -50), (20, 50), (21, 0)]
for col, val in typed:
    it = QTableWidgetItem(f"{val:g}")
    tb.setItem(ROW, col + off, it)
    win.grid_edited("AC_Bus_dat", it, off, {})
    pump(0.15)
    tb, off = win._grid_tb, win._grid_off
print(f"    바꾼 것 {len(win.changes)}건")
for ch in win.changes:
    print(f"      · {ch.label}")
ok2 = len(win.changes) == len(typed)
print(f"    {'✅' if ok2 else '🚨 건수가 다르다'}")
if not ok2:
    fails.append("바꾼 것 건수")

print("\n[3] 그 조건으로 풀면 그 버스 전압이 목표가 되나")
c2 = SC.apply(win.base_case, win.applied + win.changes)
w2 = np.asarray(c2.tables["AC_Bus_dat"]).shape[1]
sol2 = app_engine.solve(c2)
got = float(np.asarray(sol2.at("AC", 0))[ROW, 1])
tap = np.asarray(sol2.tap_ctrl, dtype=float)
print(f"    표가 {w2}열로 늘었다 · 버스 {BUS} 전압 {got:.6f} (목표 {TARGET})")
print(f"    조정 표 = {tap}")
ok3 = w2 == 22 and abs(got - TARGET) < 1e-6 and tap.shape[0] == 1 and tap[0, 8] == 3
print(f"    {'✅ 화면에서 친 것이 계산까지 갔다' if ok3 else '🚨 안 갔다'}")
if not ok3:
    fails.append("계산까지 안 감")

print("\n[4] 점검 탭 카드가 「SVC」라고 말하나")
win._solved(sol2)
win.rebuild()
pump()
tw = win._tabs
for i in range(tw.count()):
    if tw.tabText(i).startswith("점검"):
        tw.setCurrentIndex(i)
        pump(0.25)
card = None
for t in win.findChildren(QTableWidget):
    hh = [t.horizontalHeaderItem(i).text() if t.horizontalHeaderItem(i) else ""
          for i in range(t.columnCount())]
    if "정해진 값" in hh:
        card = t
if card is None:
    print("    🚨 카드가 없다")
    fails.append("카드 없음")
else:
    vals = [card.item(0, c).text() for c in range(card.columnCount())]
    print(f"    표 내용 {vals}")
    ok4 = (vals[0] == "SVC" and vals[1] == "—" and vals[2] == f"버스 {BUS}"
           and "pu" in vals[3] and "Mvar" in vals[4])
    print(f"    {'✅ 방식·단위가 SVC 용이다' if ok4 else '🚨 아니다'}")
    if not ok4:
        fails.append("카드 내용")
    win.grab().save(str(OUT / "A1_SVC_손으로입력.png"))

print("\n[5] 조정 칸이 아닌 곳은 여전히 못 고치나")
win.table_tab = "계통 데이터"
win.grid_key = "AC_Bus_dat"
win.rebuild()
pump(0.3)
tb2, off2 = win._grid_tb, win._grid_off
vmin = tb2.item(ROW, 14 + off2)          # V_min [pu]
locked = not (vmin.flags() & Qt.ItemIsEditable)
print(f"    V_min 칸 잠김 {locked} {'✅' if locked else '🚨 열려 있다'}")
if not locked:
    fails.append("V_min 이 열림")

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if fails else 0)
