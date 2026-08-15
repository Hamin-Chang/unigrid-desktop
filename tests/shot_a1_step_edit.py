# -*- coding: utf-8 -*-
"""계단을 **앱에서 손으로 쳐서** 걸 수 있나 (2026-08-14, §7 5단계 ③).

  1) 「AC 선로」 표에 `Ctrl Step Size` 칸이 **옛 13열 파일에서도** 보이나
  2) 조정 다섯 칸 + 한 단 크기를 치면 '바꾼 것' 에 얹히나
  3) 그 조건으로 풀면 탭이 **자리 위**(1.0 에서 한 단 배수)에 서나
  4) 「점검」 탭 카드가 **「계단 자리 (한 단 …)」** 라고 말하나
     🚨 계단은 목표를 정확히 못 맞추는 게 정상이라 「목표 맞춤」이라 쓰면 거짓말이고,
        경고를 달면 멀쩡한 것을 결함처럼 보이게 한다.
  5) 한 단 크기를 **지워서 비우면** 다시 연속으로 돌아가나 (2026-08-14 사용자 요청으로 고침)
  6) 한계를 비우면 **자동(0.9~1.1)** 으로 돌아가고 「자동으로 잡았다」 표시가 서나
  7) 비우면 안 되는 칸(발전기 운전모드)은 여전히 막나

⚠️ 컴파일된 엔진을 쓴다 — 계단은 엔진 **20차**부터 들어 있다.
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

CASE = V14 / "cases_v2/AConly_case14_v2.xlsx"   # 🚨 조정이 **하나도 안 걸린** 파일
ROW = 8            # 화면 줄(0부터) = 9번 선로 = 변압기 4→9
CTRL_BUS = 9
TARGET = 1.035
STEP = 0.00625     # 실물 OLTC 의 0.625%
TMIN, TMAX = 0.9, 1.1

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
w0 = np.asarray(case.tables["AC_Line_dat"]).shape[1]
print(f"\n연 파일의 AC_Line_dat 폭 = {w0}열")

print("\n[1] 옛 파일에도 「Ctrl Step Size」 칸이 보이나")
tb, off = win._grid_tb, win._grid_off
heads = [tb.horizontalHeaderItem(i).text() for i in range(tb.columnCount())]
print(f"    오른쪽 끝 머리글 {heads[-6:]}")
ok1 = "Ctrl Mode" in heads and "Ctrl Step Size" in heads
cell = tb.item(ROW, 18 + off)                    # 19열(1부터) = Ctrl Step Size
editable = bool(cell.flags() & Qt.ItemIsEditable)
print(f"    9번 선로의 Ctrl Step Size 칸: 값 {cell.text()!r} · 고칠 수 있나 {editable}")
ok1 = ok1 and editable
print(f"    {'✅ 보이고 고칠 수 있다' if ok1 else '🚨 아니다'}")
if not ok1:
    fails.append("칸이 안 보임")

print("\n[2] 조정 + 한 단 크기를 치면 '바꾼 것' 에 얹히나")
typed = [(13, 1), (14, CTRL_BUS), (15, TARGET), (16, TMIN), (17, TMAX), (18, STEP)]
for col, val in typed:
    it = QTableWidgetItem(f"{val:g}")
    tb.setItem(ROW, col + off, it)
    win.grid_edited("AC_Line_dat", it, off, {})
    pump(0.15)
    tb, off = win._grid_tb, win._grid_off
print(f"    바꾼 것 {len(win.changes)}건")
for ch in win.changes:
    print(f"      · {ch.label}")
ok2 = len(win.changes) == len(typed)
print(f"    {'✅' if ok2 else '🚨 건수가 다르다'}")
if not ok2:
    fails.append("바꾼 것 건수")

print("\n[3] 풀면 탭이 자리 위에 서나")
c2 = SC.apply(win.base_case, win.applied + win.changes)
sol2 = app_engine.solve(c2)
tap = np.asarray(sol2.tap_ctrl, dtype=float)
print(f"    조정 표 = {tap}")
ok3 = tap.shape[0] == 1 and tap.shape[1] >= 11
if ok3:
    t = tap[0, 3]
    k = (t - 1.0) / STEP
    on_step = abs(k - round(k)) < 1e-6
    sz_ok = abs(tap[0, 9] - STEP) < 1e-12
    st_ok = int(tap[0, 10]) == 1
    print(f"    탭 {t:.6f} = 1.0 {round(k):+d}×{STEP}  (어긋남 {abs(k-round(k)):.2e}칸)")
    print(f"    10열 한 단 크기 {tap[0, 9]:g} · 11열 계단 상태 {int(tap[0, 10])}")
    ok3 = on_step and sz_ok and st_ok and TMIN - 1e-9 <= t <= TMAX + 1e-9
print(f"    {'✅ 계단 자리에 섰다' if ok3 else '🚨 아니다'}")
if not ok3:
    fails.append("계단 자리가 아님")

print("\n[4] 점검 탭 카드가 「계단 자리」라고 말하나")
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
    ok4 = vals[0] == "탭" and "계단" in vals[-1] and "한 단" in vals[-1]
    print(f"    {'✅ 계단이라고 말한다' if ok4 else '🚨 아니다 — 마지막 칸 ' + vals[-1]!r}")
    if not ok4:
        fails.append("카드가 계단이라 안 함")
    win.grab().save(str(OUT / "A1_계단_손으로입력.png"))

print("\n[5] 한 단 크기를 지워서 비우면 다시 연속인가")
# 🚨 2026-08-14 이전에는 **빈 칸을 아예 못 받았다** — `float("")` 이 걸려 "숫자가
#    아닙니다" 로 되돌아갔다. 계단은 0 = 연속이라 넘어갈 수 있었지만 **한계처럼
#    0 이 다른 뜻인 칸은 비울 방법이 없었다.** 이제 조정 칸은 비울 수 있다.
win.table_tab = "계통 데이터"
win.grid_key = "AC_Line_dat"
win.rebuild()
pump(0.3)
tb2, off2 = win._grid_tb, win._grid_off
it = QTableWidgetItem("")                       # 지워서 비운다 = 연속
tb2.setItem(ROW, 18 + off2, it)
win.grid_edited("AC_Line_dat", it, off2, {})
pump(0.2)
c3 = SC.apply(win.base_case, win.applied + win.changes)
sol3 = app_engine.solve(c3)
tap3 = np.asarray(sol3.tap_ctrl, dtype=float)
t3 = tap3[0, 3]
sz3 = tap3[0, 9] if tap3.shape[1] > 9 else np.nan
st3 = int(tap3[0, 10]) if tap3.shape[1] > 10 else -1
v3 = float(np.asarray(sol3.at("AC", 0))[CTRL_BUS - 1, 1])
print(f"    탭 {t3:.6f} · 10열 {sz3:g} · 11열 {st3} · 버스 {CTRL_BUS} 전압 {v3:.6f}")
ok5 = sz3 == 0 and st3 == 0 and abs(v3 - TARGET) < 1e-6
print(f"    {'✅ 연속으로 돌아가 목표를 정확히 맞춘다' if ok5 else '🚨 아니다'}")
if not ok5:
    fails.append("연속 복귀 안 됨")

print("\n[6] 한계를 비우면 자동(0.9~1.1)으로 돌아가나")
win.rebuild()
pump(0.3)
tb3, off3 = win._grid_tb, win._grid_off
for cc in (16, 17):                              # Ctrl Min · Ctrl Max
    it = QTableWidgetItem("")
    tb3.setItem(ROW, cc + off3, it)
    win.grid_edited("AC_Line_dat", it, off3, {})
    pump(0.15)
    tb3, off3 = win._grid_tb, win._grid_off
c4 = SC.apply(win.base_case, win.applied + win.changes)
sol4 = app_engine.solve(c4)
tap4 = np.asarray(sol4.tap_ctrl, dtype=float)
lo4, hi4, auto4 = tap4[0, 5], tap4[0, 6], int(tap4[0, 7])
print(f"    한계 {lo4:g} ~ {hi4:g} · 자동으로 잡았나 {auto4}")
ok6 = abs(lo4 - 0.9) < 1e-12 and abs(hi4 - 1.1) < 1e-12 and auto4 == 1
print(f"    {'✅ 비우니 자동으로 잡고 그렇다고 밝힌다' if ok6 else '🚨 아니다'}")
if not ok6:
    fails.append("한계 비우기")

print("\n[7] 비우면 안 되는 칸은 여전히 막나")
win.grid_key = "AC_gen_dat"
win.rebuild()
pump(0.3)
tb4, off4 = win._grid_tb, win._grid_off
n_before = len(win.changes)
it = QTableWidgetItem("")
tb4.setItem(0, 2 + off4, it)                     # AC Gen Mode — 비우면 안 되는 칸
win.grid_edited("AC_gen_dat", it, off4, {})
pump(0.2)
ok7 = len(win.changes) == n_before
print(f"    바꾼 것 {n_before} → {len(win.changes)} "
      f"{'✅ 안 얹혔다(막힘)' if ok7 else '🚨 얹혔다'}")
if not ok7:
    fails.append("막아야 할 칸이 열림")

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if fails else 0)
