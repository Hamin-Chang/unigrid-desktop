# -*- coding: utf-8 -*-
"""창을 줄일 수 있나 · 값을 고쳐도 보던 자리에 있나 (2026-08-13 사용자 지적 둘).

  1) 창 최소 높이가 **화면보다 작나** — 크면 아래가 잘린 채 줄일 수도 없다
  2) 🚨 **어떤 화면에서든 창이 그 화면 안에 드나** (2026-08-19 에 바꿈)
     예전에는 "세로 660px 아래로 줄어드나" 를 봤다. 그런데 창 최소는 **그래프
     바닥값이 정하고**(창 최소 = 322 + 바닥값), 그 바닥값은 *세로축 숫자가 안
     뭉개지는 크기*라 무턱대고 낮출 값이 아니다. ⇒ 잣대를 **화면에 드나**로 바꿨다.
     이제 앱이 화면 크기를 읽어 바닥값을 맞춘다(`_screen_avail`·`_graph_floor`).
  3) 조정 칸을 하나 고쳐도 **가로 스크롤이 그 자리에 있나**
  4) 다음에 칠 칸이 **미리 골라져 있나** (오른쪽으로 다시 찾아가지 않게)
  5) 🚨 **조작 줄이 길어도 창을 넓히지 않나** (2026-08-19 에 바꿈)
     예전에는 "계통 데이터 탭을 열면 화면 나눔 비율이 바뀌나" 를 봤다. 2026-08-18
     에 그 일은 **그래프 접기**가 맡게 됐고(`shot_graph_fold.py` [8] 이 지킨다),
     이 자리에는 그 대신 **가로** 문제를 둔다 — 「표 고르기」 단추는 그 계통에 있는
     표만큼 생겨서, 그 줄의 길이가 곧 창 최소 가로였다(71버스 AC/DC 는 1752px 이라
     맥북 13" 에도 안 들어갔다).

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

print("\n[2] 어떤 화면에서든 그 화면 안에 드나")
# 화면 크기를 흉내 내어 앱이 스스로 맞추는지 본다. 흔한 노트북 셋 + 지금 이 화면.
_real_avail = APP.Proto._screen_avail
SCREENS = [("맥북 13\"", 1440, 875), ("윈도우 보급형", 1366, 728),
           ("작은 노트북", 1280, 760), ("FHD", 1920, 1040)]
ok2 = True
for nm, sw, sh in SCREENS:
    APP.Proto._screen_avail = lambda self, _w=sw, _h=sh: (_w, _h)
    win.rebuild()
    pump(0.5)
    m = win.minimumSizeHint()
    fit = m.width() <= sw and m.height() <= sh
    print(f"    {nm:<12} 화면 {sw}x{sh} · 바닥값 {win._graph_floor()}px "
          f"· 창 최소 {m.width()}x{m.height()}  {'✅' if fit else '🚨 안 든다'}")
    if not fit:
        ok2 = False
APP.Proto._screen_avail = _real_avail
win.rebuild()
pump(0.4)
if not ok2:
    fails.append("화면에 안 듦")

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
        # 화면 열 = 데이터 열 + off (첫 번호 열을 왼쪽에 고정하면서 달라진다)
        off = win._grid_off
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

print("\n[5] 조작 줄이 길어도 창을 넓히지 않나")
from PySide6.QtWidgets import QScrollArea                     # noqa: E402
win.table_tab = "계통 데이터"
win.rebuild()
pump(0.5)
# 🚨 `win.findChildren` 만 쓰면 **지워지기를 기다리는 옛 줄**까지 잡힌다
#    (rebuild 를 여러 번 했으므로 10개가 잡혔다 — 위 `grid()` 주석과 같은 함정).
#    지금 화면에 붙어 있는 탭 안에서, **보이는 것**만 센다.
_page = win._tabs.currentWidget()
bars = [w for w in _page.findChildren(QScrollArea)
        if w.objectName() == "gridbar" and w.isVisible()]
print(f"    조작 줄을 밀 수 있게 감쌌나 — {len(bars)}개")
ok5 = len(bars) == 1
if ok5:
    need = bars[0].widget().sizeHint().width()
    give = bars[0].minimumSizeHint().width()
    wmin = win.minimumSizeHint().width()
    print(f"    조작 줄이 요구하는 폭 {need}px · 그 줄이 창에 요구하는 폭 {give}px "
          f"· 창 최소 가로 {wmin}px")
    # 🚨 줄이 길어도 **그 길이를 창에 떠넘기면 안 된다** — 그게 71버스에서 창 최소를
    #    1752px 로 만들어 맥북 13"(1440px)에도 안 들어가게 했다.
    #    감싼 곳이 제 몫을 하면 창에 요구하는 폭은 줄 길이보다 훨씬 작다.
    ok5 = give < need // 2
    print(f"    {'✅ 줄 길이를 창에 떠넘기지 않는다' if ok5 else '🚨 창에 그대로 떠넘긴다'}")
else:
    print("    🚨 조작 줄을 감싼 곳을 못 찾았다")
if not ok5:
    fails.append("조작 줄이 창을 넓힘")
win.table_tab = "AC 결과"
win.rebuild()
pump(0.4)

print("\n[6] 오른쪽으로 밀어도 첫 열(선로 번호)이 남아 있나")
# 🚨 창이 넓으면 19열이 다 들어와 **밀 것이 없다** — 그 상태로 "남아 있다" 는
#    아무것도 안 본 것이다(가로 최대 0). 좁혀서 실제로 밀리게 만든 뒤에 본다.
win.resize(1150, 900)
win.table_tab = "계통 데이터"
win.grid_key = "AC_Line_dat"
win.rebuild()
pump(0.6)
fz = win._grid_frozen
right = win._grid_tb
if fz is None:
    print("    🚨 고정된 표가 없다")
    fails.append("고정 표 없음")
else:
    fh = [fz.horizontalHeaderItem(i).text() for i in range(fz.columnCount())]
    rh = [right.horizontalHeaderItem(i).text() for i in range(right.columnCount())]
    print(f"    왼쪽(고정) 머리글 {fh}")
    print(f"    오른쪽 첫 머리글 {rh[:3]} … 끝 {rh[-2:]}")
    hs = right.horizontalScrollBar()
    hs.setValue(hs.maximum())
    pump(0.3)
    # 끝까지 밀어도 왼쪽 표는 제자리 · 값도 그대로
    still = fz.item(ROW, fz.columnCount() - 1)
    print(f"    끝까지 민 뒤({hs.value()}/{hs.maximum()}) 왼쪽 {ROW}번 줄 값 "
          f"= {still.text()!r} · 왼쪽 가로 자리 {fz.horizontalScrollBar().value()}")
    if hs.maximum() == 0:
        print("    🚨 밀 것이 없다 — 이 시험은 아무것도 안 본 것이다")
        fails.append("가로 범위 0")
    ok6 = (hs.maximum() > 0 and fh[-1] == "Line #" and "Line #" not in rh
           and still.text() == "9" and fz.horizontalScrollBar().value() == 0)
    print(f"    {'✅ 번호가 남아 있다' if ok6 else '🚨 안 남는다'}")
    if not ok6:
        fails.append("첫 열 고정")

    print("\n[7] 세로로는 함께 움직이나")
    vs = right.verticalScrollBar()
    if vs.maximum() == 0:
        print("    ⚠️ 세로로 밀 것이 없다 (줄이 다 보인다)")
    else:
        vs.setValue(vs.maximum())
        pump(0.25)
        same = fz.verticalScrollBar().value() == vs.value()
        print(f"    오른쪽 {vs.value()} · 왼쪽 {fz.verticalScrollBar().value()} "
              f"{'✅ 같이 움직인다' if same else '🚨 어긋난다'}")
        if not same:
            fails.append("세로 어긋남")
    win.grab().save(str(OUT / "첫열고정.png"))

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.exit(1 if fails else 0)
