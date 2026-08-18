# -*- coding: utf-8 -*-
"""결과 표를 열 머리로 늘어놓기 (2026-08-18).

계기 — 1,888버스 계통에서 결과 표가 1,888행인데 한 화면에 20줄뿐이라 끝까지 보려면
95화면을 굴려야 했다. 「전압이 가장 낮은 버스」를 찾을 길이 아예 없었다(정렬 0곳 ·
「버스 번호로 찾기」는 계통 데이터 탭에만).

보는 것
    1) 아무것도 안 눌렀을 때 **원래 순서**인가
       🚨 `setSortingEnabled(True)` 는 켜는 순간 지금 표시자(기본 0열)로 한 번
          늘어놓는다 — 실측으로 버스가 302·301·224… 로 뒤집혀 나왔다.
    2) 열 머리를 누르면 **숫자로** 늘어놓나 (글자로 견주면 10 이 9 보다 앞선다)
    3) 🚨 계산해도 **그 정렬이 유지되나** (사용자 확정 — 무엇이 달라졌는지 견주려면)
    4) 「원래 순서로」 가 되돌리나
    5) 정렬 중이면 **위반이 없어도 띠가 뜨나** (안 뜨면 되돌릴 길이 화면에 없다)
    6) 🚨 정렬이 **끝없이 돌지 않나** (`sortItems` 도 신호를 내므로 빗장이 필요하다)
    7) 🚨 정렬이 **빠른가** — 처음엔 여기서 화면을 통째로 다시 그려 6,495버스에서
       5.97초였다. 표는 Qt 가 이미 늘어놓았으니 띠만 갈아 끼우면 된다.
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

import warnings                                                   # noqa: E402
warnings.filterwarnings("ignore")
from PySide6.QtCore import Qt                                      # noqa: E402
from PySide6.QtWidgets import (QApplication, QMessageBox, QFrame,  # noqa: E402
                               QLabel, QPushButton, QTableWidget)

qapp = QApplication([])
import app as APP                                                  # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                                  # noqa: E402
import scenario as SC                                              # noqa: E402
from load_case import load_case                                    # noqa: E402

CASE = V14 / "cases_v2/ACDC_case24_MatACDC_v2.xlsx"
CLEAN = V14 / "cases_v2/ACDC_71bus_v2.xlsx"      # AC 전압 위반 0곳
BIG = V14 / "cases_v2/AConly_case6495rte_v2.xlsx"
fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<50} {got}")
    else:
        print(f"  ❌ {label:<50} {got}  (바라던 값 {want})")
        fails.append(label)


def pump(s=0.8):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


win = APP.Proto()
win.resize(1500, 950)
win.show()
pump(0.4)


def open_case(path):
    case = load_case(str(path))
    win.thread = Fake(case)
    win._last_path = str(path)
    win._solved(app_engine.solve(case))
    win.rebuild()
    pump(1.2)


def table(tab="AC 결과"):
    tt = win._tabs
    for i in range(tt.count()):
        if tt.tabText(i) == tab:
            tt.setCurrentIndex(i)
            pump(0.5)
            return tt.currentWidget().findChild(QTableWidget)
    return None


def strip(tab="AC 결과", visible_only=True):
    """표 위 띠. ⚠️ 띠는 **보일 것이 없어도 만들어 두고 숨긴다**(정렬을 누를 때
    화면을 통째로 다시 그리지 않으려면 미리 있어야 한다). 그래서 「있나」가 아니라
    **「보이나」**를 봐야 사용자가 보는 것과 같아진다."""
    tt = win._tabs
    for i in range(tt.count()):
        if tt.tabText(i) == tab:
            tt.setCurrentIndex(i)
            pump(0.4)
            bars = [f for f in tt.currentWidget().findChildren(QFrame)
                    if f.objectName() == "violbar"
                    and (f.isVisible() or not visible_only)]
            return bars[0] if bars else None
    return None


def col_of(t, name):
    return [t.horizontalHeaderItem(i).text()
            for i in range(t.columnCount())].index(name)


def firsts(t, col, k=6):
    return [float(t.item(r, col).text()) for r in range(k)]


print("\n[1] 🚨 아무것도 안 눌렀을 때 원래 순서인가")
open_case(CASE)
t = table()
bus = [int(t.item(r, 0).text()) for r in range(5)]
print(f"    앞 5줄 {bus}")
check("버스 번호가 커지는 순인가", bus == sorted(bus), True)

print("\n[2] 열 머리를 누르면 숫자로 늘어놓나")
iv = col_of(t, "VM[pu]")
t.horizontalHeader().setSortIndicator(iv, Qt.AscendingOrder)
pump(0.6)
t = table()
vs = firsts(t, iv)
print(f"    VM 앞 6개 {vs}")
check("작은 값부터인가", all(vs[i] <= vs[i + 1] for i in range(len(vs) - 1)), True)
check("적어 뒀나", win.sort_by.get("AC 결과")[0], iv)

print("\n[3] 🚨 조건을 바꿔 계산해도 정렬이 유지되나")
win.grid_key = "AC_Line_dat"
win.flip_row(3)
pump(0.2)
pend = win.applied + win.changes
win._pending, win._pending_new = pend, list(win.changes)
win._solved(app_engine.solve(SC.apply(win.base_case, pend)))
win.rebuild()
pump(1.2)
t = table()
vs = firsts(t, iv)
print(f"    VM 앞 6개 {vs}")
check("여전히 작은 값부터인가",
      all(vs[i] <= vs[i + 1] for i in range(len(vs) - 1)), True)

print("\n[5] 정렬 중이면 위반이 없어도 띠가 뜨나")
open_case(CLEAN)
# 🚨 새 파일을 열면 **앞 계통의 정렬 기억이 지워져야** 한다. 안 지우면 파일을
#    열자마자 영문 모를 순서로 늘어서 있다(시험이 이걸 잡았다).
check("새 파일을 열면 정렬 기억이 지워지나", win.sort_by, {})
n_ac = sum(1 for g, _b in win.violating_buses() if g == "AC")
check("이 계통은 AC 위반이 없나", n_ac, 0)
check("정렬 전에는 띠가 안 보이나", strip() is None, True)
hidden = strip(visible_only=False)
check("숨긴 띠는 만들어져 있나", hidden is not None, True)
check("숨긴 띠가 안 보이나", hidden.isHidden() if hidden else None, True)
# ⚠️ `height()` 로 보면 안 된다 — 숨겨도 **마지막 크기(38)가 남아** 있다.
#    자리를 먹는지는 **표가 맨 위에 붙었는지**로 본다.
check("표가 맨 위에 붙었나", table().y(), 0)
t = table()
t.horizontalHeader().setSortIndicator(col_of(t, "VM[pu]"), Qt.DescendingOrder)
pump(0.6)
b = strip()
check("정렬 뒤에는 띠가 뜨나", b is not None, True)
if b:
    say = " ".join(l.text() for l in b.findChildren(QLabel))
    print(f"    띠 — {say}")
    check("무엇으로 늘어놓았는지 말하나", "VM[pu]" in say, True)
    check("큰 값부터라고 말하나", "큰 값부터" in say, True)
    check("[원래 순서로] 가 있나",
          any("원래 순서" in w.text() for w in b.findChildren(QPushButton)), True)

print("\n[4] 「원래 순서로」 가 되돌리나")
back = next(w for w in strip().findChildren(QPushButton) if "원래 순서" in w.text())
back.click()
pump(1.2)
t = table()
bus = [int(t.item(r, 0).text()) for r in range(5)]
print(f"    앞 5줄 {bus}")
check("원래 순서로 돌아왔나", bus == sorted(bus), True)
check("기억도 지워졌나", "AC 결과" in win.sort_by, False)
check("띠도 사라졌나", strip() is None, True)
check("표가 다시 맨 위에 붙었나", table().y(), 0)

print("\n[6][7] 🚨 끝없이 돌지 않고, 큰 계통에서도 빠른가")
open_case(BIG)
t = table()
iv = col_of(t, "VM[pu]")
t0 = time.time()
t.horizontalHeader().setSortIndicator(iv, Qt.AscendingOrder)
qapp.processEvents()
dt = time.time() - t0
vs = firsts(t, iv)
print(f"    {t.rowCount():,}행 · {dt:.3f}초")
check("작은 값부터인가", all(vs[i] <= vs[i + 1] for i in range(len(vs) - 1)), True)
check("1초 안에 끝나나 (옛 방식은 5.97초)", dt < 1.0, True)

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if fails else 0)
