# -*- coding: utf-8 -*-
"""창을 줄일 수 있나 · 값을 고쳐도 보던 자리에 있나 (2026-08-13 사용자 지적 둘).

  1) 창 최소 높이가 **화면보다 작나** — 크면 아래가 잘린 채 줄일 수도 없다
  2) 실제로 작게 줄여지나
  3) 조정 칸을 하나 고쳐도 **가로 스크롤이 그 자리에 있나**
  4) 다음에 칠 칸이 **미리 골라져 있나** (오른쪽으로 다시 찾아가지 않게)

계기: 사용자 *"앱 창 크기를 우리가 맘대로 조절을 못해. 아래가 안보여"* ·
      *"숫자 하나를 넣을때마다 다시 가로 스크롤을 해서 다음 숫자 넣을곳을 찾아야한다"*
실측(고치기 전): 창 최소 1201px · 사이드바 665 · 점검 탭 490 · 그래프 470
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
from PySide6.QtWidgets import (QApplication, QMessageBox,    # noqa: E402
                               QTabWidget, QTableWidget, QTableWidgetItem)

qapp = QApplication([])
import app as APP                                            # noqa: E402
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
import app_engine                                            # noqa: E402
import scenario as SC                                        # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/AConly_case14_v2.xlsx"
ROW = 8          # 0부터 — 9번 선로(변압기 4→9)

# 맥북 화면에서 쓸 수 있는 세로. 창 최소가 이보다 크면 아래가 잘린다.
SCREEN_H = 900

win = APP.Proto()
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
pump()

fails = []

print("\n[1] 창 최소 높이가 화면 안에 드나")
mh = win.minimumSizeHint().height()
print(f"    최소 높이 {mh}px (맥북 쓸 수 있는 세로 {SCREEN_H}px)")
if mh >= SCREEN_H:
    print("    🚨 화면보다 크다 — 아래가 잘린다")
    fails.append(f"창 최소 {mh}")
else:
    print("    ✅ 든다")

print("\n[2] 실제로 작게 줄여지나")
win.resize(1000, 640)
pump(0.3)
print(f"    1000x640 으로 줄인 결과 {win.width()}x{win.height()}")
if win.height() > 660:
    print("    🚨 안 줄어든다")
    fails.append("안 줄어듦")
else:
    print("    ✅ 줄어든다")

win.resize(1400, 900)
pump(0.3)


def open_grid_tab():
    for tw in win.findChildren(QTabWidget):
        if not tw.isVisible():
            continue
        for i in range(tw.count()):
            if tw.tabText(i).startswith("계통 데이터"):
                tw.setCurrentIndex(i)
                pump(0.3)
                return True
    return False


def grid():
    """지금 화면에 붙어 있는 표.

    🚨 `findChildren` 만 쓰면 **지워지기를 기다리는 옛 표**가 먼저 잡힌다
       (화면을 다시 그려도 옛 위젯이 잠깐 살아 있다). 그걸 집으면 스크롤도
       고른 칸도 옛것을 읽어 시험이 거짓으로 통과·실패한다(2026-08-13에 겪음).
       앱이 들고 있는 것(`_grid_tb`)이 곧 화면의 표다.
    """
    tb = getattr(win, "_grid_tb", None)
    if tb is not None:
        return tb
    for t in win.findChildren(QTableWidget):
        heads = [t.horizontalHeaderItem(i).text() if t.horizontalHeaderItem(i) else ""
                 for i in range(t.columnCount())]
        if "Ctrl Mode" in heads:
            return t
    return None


print("\n[3] 값을 고쳐도 가로 스크롤이 그 자리에 있나")
win.grid_key = "AC_Line_dat"
win.rebuild()
pump()
open_grid_tab()
tb = grid()
if tb is None:
    print("    🚨 표를 못 찾겠다")
    fails.append("표 없음")
else:
    hs = tb.horizontalScrollBar()
    hs.setValue(hs.maximum())          # 오른쪽 끝(조정 열)까지 민다
    pump(0.2)
    before = hs.value()
    print(f"    오른쪽 끝까지 밀었다 — 가로 자리 {before} (최대 {hs.maximum()})")
    if before == 0:
        print("    ⚠️ 스크롤 범위가 0 이라 이 시험은 뜻이 없다")
        fails.append("스크롤 범위 0")
    else:
        off = 1 if SC.SWITCHES.get("AC_Line_dat") else 0
        it = QTableWidgetItem("1")
        tb.setItem(ROW, 13 + off, it)          # Ctrl Mode = 1
        win.grid_edited("AC_Line_dat", it, off, {})
        pump(0.4)                               # 되돌리기는 화면을 한 번 그린 뒤에 돈다
        tb2 = grid()
        after = tb2.horizontalScrollBar().value()
        print(f"    고친 뒤 가로 자리 {after}")
        if after < before * 0.8:
            print("    🚨 왼쪽으로 돌아갔다")
            fails.append(f"스크롤 {before}→{after}")
        else:
            print("    ✅ 그 자리에 있다")

        print("\n[4] 다음에 칠 칸이 미리 골라져 있나 (Ctrl Mode 다음 = Ctrl Bus)")
        cur_c = tb2.currentColumn()
        cur_r = tb2.currentRow()
        want = 14 + off
        print(f"    골라진 칸 = 줄 {cur_r} · 열 {cur_c} (바라는 것 줄 {ROW} · 열 {want})")
        if (cur_r, cur_c) != (ROW, want):
            print("    🚨 안 골라졌다")
            fails.append("다음 칸")
        else:
            print("    ✅ 바로 숫자를 치면 된다")

        win.grab().save(str(OUT / "창크기_가로자리.png"))

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.exit(1 if fails else 0)
