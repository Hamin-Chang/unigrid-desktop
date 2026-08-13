# -*- coding: utf-8 -*-
"""A1 탭 조정이 「점검」 탭에 뜨나 — 확인하고 찍는다 (2026-08-13, §7 5단계 3번).

  1) 조정을 안 걸면 카드가 **안 나온다** (평소 화면이 안 지저분해진다)
  2) 걸면 카드가 나오고 **정해진 탭비**가 보인다
  3) 한계에 걸려 목표를 못 맞추면 **그렇게 말한다** (이게 이 카드의 존재 이유다)

⚠️ 이 시험은 **컴파일된 엔진**을 쓴다 — 엔진 14차(2026-08-13)부터 탭 조정이 들어 있다.
   엔진이 옛것이면 [2]에서 카드가 안 나와 실패한다.
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
                               QTabWidget, QTableWidget)

qapp = QApplication([])
import app as APP                                            # noqa: E402
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)
import app_engine                                            # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/AConly_case14_v2.xlsx"
ROW = 8          # 0부터 — 9번 선로(변압기 4→9)
BUS = 9

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


def show(case, tag):
    win.thread = Fake(case)
    win._last_path = str(CASE)
    win._solved(app_engine.solve(case))
    win.rebuild()
    pump()
    return win.sol


def with_ctrl(target, tmax):
    """조정을 건 케이스를 만든다 — 열 14~19에 값을 넣는다.

    ⚠️ **표는 DataFrame 이다.** numpy 로 갈아끼우면 앱이 `copy(deep=True)` 에서 죽는다
       (2026-08-13 에 실제로 그랬다). 열 이름은 0부터 세는 정수라 그대로 이어 붙인다.
    """
    c = load_case(str(CASE))
    df = c.tables["AC_Line_dat"].copy(deep=True)
    for j in range(df.shape[1], 19):
        df[j] = np.nan
    df.iloc[ROW, 13] = 1        # Ctrl Mode = 탭 조정
    df.iloc[ROW, 14] = BUS      # Ctrl Bus
    df.iloc[ROW, 15] = target   # Ctrl Target
    df.iloc[ROW, 16] = 0.8      # Ctrl Min
    df.iloc[ROW, 17] = tmax     # Ctrl Max
    df.iloc[ROW, 18] = 0        # Ctrl Steps (연속)
    c.tables["AC_Line_dat"] = df
    return c


def open_check_tab():
    """아래 탭 묶음에서 '점검' 을 찾아 연다 (보이는 것만)."""
    for tw in win.findChildren(QTabWidget):
        if not tw.isVisible():
            continue
        for i in range(tw.count()):
            if tw.tabText(i).startswith("점검"):
                tw.setCurrentIndex(i)
                pump(0.2)
                return True
    return False


def tap_table():
    """점검 탭 안의 조정 표를 찾는다 (머리글로 가린다).

    열 = 방식 · 선로 · 맞추는 곳 · 목표 · 정해진 값 · 움직일 수 있는 범위 · 결과
    (2026-08-13 ② 에서 위상 조정기가 들어오며 머리글이 바뀌었다)"""
    for t in win.findChildren(QTableWidget):
        if not t.isVisible():
            continue
        heads = [t.horizontalHeaderItem(i).text() if t.horizontalHeaderItem(i) else ""
                 for i in range(t.columnCount())]
        if "정해진 값" in heads:
            return t
    return None


fails = []

print("\n[1] 조정을 안 걸면 카드가 안 나오나")
show(load_case(str(CASE)), "off")
open_check_tab()
t0 = tap_table()
print(f"    탭 조정 표 {'없음 ✅' if t0 is None else '🚨 나왔다'}")
if t0 is not None:
    fails.append("안 걸었는데 카드가 나옴")

print("\n[2] 걸면 정해진 탭비가 보이나 (목표 1.035 · 상한 1.2 — 도달 가능)")
sol = show(with_ctrl(1.035, 1.2), "on")
print(f"    엔진이 돌려준 표 {np.asarray(sol.tap_ctrl).shape} · "
      f"버스 {BUS} 전압 {sol.at('AC', 0)[BUS - 1, 1]:.6f}")
open_check_tab()
t1 = tap_table()
if t1 is None:
    print("    🚨 카드가 안 나온다 — 엔진이 옛것일 수 있다")
    fails.append("걸었는데 카드가 없음")
else:
    vals = [t1.item(0, cc).text() for cc in range(t1.columnCount())]
    print(f"    표 내용 {vals}")
    ok = vals[-1] == "목표 맞춤" and vals[0] == "탭" and float(vals[4]) > 1.0
    print(f"    {'✅ 정해진 탭비와 결과가 보인다' if ok else '🚨 내용이 이상하다'}")
    if not ok:
        fails.append("카드 내용")
    win.grab().save(str(OUT / "A1_점검탭_목표맞춤.png"))

print("\n[3] 한계에 걸리면 그렇게 말하나 (목표 0.95 · 상한 1.10 — 도달 불가)")
sol2 = show(with_ctrl(0.95, 1.10), "lim")
open_check_tab()
t2 = tap_table()
if t2 is None:
    print("    🚨 카드가 없다")
    fails.append("한계 경우 카드 없음")
else:
    vals = [t2.item(0, cc).text() for cc in range(t2.columnCount())]
    print(f"    표 내용 {vals}")
    ok = "한계" in vals[-1]
    print(f"    {'✅ 목표를 포기했다고 밝힌다' if ok else '🚨 안 밝힌다'}")
    if not ok:
        fails.append("한계 안내")
    win.grab().save(str(OUT / "A1_점검탭_한계.png"))

print("\n[4] 한계를 안 적으면 0.9~1.1 로 잡고 **그렇게 잡았다고 밝히나** (2026-08-13)")
from PySide6.QtWidgets import QLabel                          # noqa: E402


def with_ctrl_nolimit(target):
    """한계 칸(17·18)을 **비운 채** 조정만 켠 케이스."""
    c = with_ctrl(target, 1.2)
    df = c.tables["AC_Line_dat"]
    df.iloc[ROW, 16] = np.nan        # Ctrl Min
    df.iloc[ROW, 17] = np.nan        # Ctrl Max
    return c


sol3 = show(with_ctrl_nolimit(1.035), "auto")
tap = np.asarray(sol3.tap_ctrl)
print(f"    엔진이 돌려준 표 {tap.shape}")
if tap.shape[1] < 8:
    print("    🚨 8열이 아니다 — 엔진이 옛것이다")
    fails.append("탭 표가 8열이 아님")
else:
    print(f"    하한 {tap[0, 5]:g} · 상한 {tap[0, 6]:g} · 자동 표시 {tap[0, 7]:g}")
    open_check_tab()
    t3 = tap_table()
    lim = t3.item(0, 5).text() if t3 is not None else "(표 없음)"   # 「움직일 수 있는 범위」
    said = [w.text() for w in win.findChildren(QLabel)
            if "0.9" in w.text() and "1.1" in w.text() and "적지 않아" in w.text()]
    print(f"    표의 「탭 한계」 칸 = {lim!r}")
    # 🚨 `findChildren` 은 **지워지기를 기다리는 옛 화면**의 라벨도 준다 —
    #    개수로 판정하면 안 된다(오늘만 세 번째로 걸린 함정). 있나 없나만 본다.
    print(f"    안내 문구 = {said[0] if said else '(없음)'}  (찾은 개수 {len(said)})")
    ok = (tap[0, 5] == 0.9 and tap[0, 6] == 1.1 and tap[0, 7] == 1
          and "자동" in lim and len(said) >= 1)
    print(f"    {'✅ 잡고, 밝힌다' if ok else '🚨 아니다'}")
    if not ok:
        fails.append("한계 자동 안내")
    win.grab().save(str(OUT / "A1_점검탭_한계자동.png"))

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.exit(1 if fails else 0)
