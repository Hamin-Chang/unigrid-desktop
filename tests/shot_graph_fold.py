# -*- coding: utf-8 -*-
"""계통을 바꿔 계산하면 그래프를 접고 표를 넓게 연다 (2026-08-15 사용자 확정).

사용자: *"계통을 바꿔서 계산하면 그냥 그래프를 일단 끄고, 사용자가 키고 싶으면
그때 그래프를 띄우고 표는 작게 줄이자"*

보는 것
    1) 파일을 처음 열었을 때는 **그래프가 펼쳐져** 있나 (작은 계통)
    2) 조건을 바꿔 계산하면 **접히고**, 표가 넓어지나
    3) 접힌 이유를 화면이 **맞게** 말하나 (큰 계통 때 문구를 그대로 쓰면 거짓말이 된다)
    4) [그래프 펼치기] 를 누르면 펼쳐지고 표가 **도로 줄어드나**
    5) 🚨 그다음 조건을 또 바꿔 계산해도 **다시 안 접히나**
       (조건 하나 바꿀 때마다 도로 접히면 못 쓴다 — 2026-08-06 에 큰 계통 자동 접기에서
        이미 정한 것과 같은 이유)
    6) 새 파일을 열면 그 기억이 **초기화되나**
    7) 🚨 펼쳤을 때 **되접는 길**이 그래프 자리에 있나
       (펼치기는 그래프 자리에 있는데 접기는 저 멀리 [숫자만] 뿐이었다 — 사용자 지적)
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
from PySide6.QtWidgets import QApplication, QMessageBox      # noqa: E402

qapp = QApplication([])
import app as APP                                            # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                            # noqa: E402
import scenario as SC                                        # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/AConly_case14_v2.xlsx"
fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<46} {got}")
    else:
        print(f"  ❌ {label:<46} {got}  (바라던 값 {want})")
        fails.append(label)


def pump(s=0.4):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


def table_h() -> int:
    """표가 받은 높이 (스플리터 아래쪽). 접혀 있으면 그래프 몫이 없다."""
    return win._split.sizes()[-1] if win._split is not None else 0


def open_case(path):
    case = load_case(str(path))
    win.thread = Fake(case)
    win._last_path = str(path)
    win._solved(app_engine.solve(case))
    win.table_tab = "계통 데이터"
    win.rebuild()
    pump()
    return case


def calc(row):
    """선로 하나를 끄고 [이 조건으로 계산] 이 하는 일 그대로."""
    win.grid_key = "AC_Line_dat"
    win.flip_row(row)
    pump(0.2)
    pend = win.applied + win.changes
    win._pending, win._pending_new = pend, list(win.changes)
    win._solved(app_engine.solve(SC.apply(win.base_case, pend)))
    win.rebuild()
    pump()


win = APP.Proto()
win.resize(1414, 950)
win.show()

open_case(CASE)
print("\n[1] 파일을 처음 열면 그래프가 펼쳐져 있나 (14버스라 작은 계통)")
check("접혔나", win.numbers, False)
h_open = table_h()
print(f"    표 몫 {h_open}px")

print("\n[2] 조건을 바꿔 계산하면 접히고 표가 넓어지나")
calc(3)
h_fold = table_h()
check("접혔나", win.numbers, True)
check("표가 넓어졌나", h_fold > h_open, True)
print(f"    표 몫 {h_open} → {h_fold}px")

print("\n[3] 접힌 이유를 맞게 말하나")
check("이유", win.numbers_why, "changed")

print("\n[4] [그래프 펼치기] 를 누르면 펼쳐지고 표가 도로 줄어드나")
win.set_numbers(False)
pump()
h_show = table_h()
check("접혔나", win.numbers, False)
check("표가 줄었나", h_show < h_fold, True)
print(f"    표 몫 {h_fold} → {h_show}px")

print("\n[5] 🚨 그 뒤 조건을 또 바꿔 계산해도 다시 안 접히나")
calc(4)
check("접혔나", win.numbers, False)
check("직접 펼친 기억", win.graph_kept, True)

print("\n[6] 새 파일을 열면 그 기억이 초기화되나")
open_case(CASE)
check("직접 펼친 기억", win.graph_kept, False)

print("\n[7] 🚨 펼쳤을 때 그래프 자리에 「접기」가 있나")
calc(5)
win.set_numbers(False)
pump()
from PySide6.QtWidgets import QTabWidget, QPushButton   # noqa: E402
corner = [w.cornerWidget() for w in win.findChildren(QTabWidget)
          if w.cornerWidget() is not None]
names = [w.text() for w in corner if isinstance(w, QPushButton)]
print(f"    그래프 탭 구석의 단추 {names}")
check("접기 단추", any("접기" in n for n in names), True)
if any("접기" in n for n in names):
    btn = next(w for w in corner if isinstance(w, QPushButton) and "접기" in w.text())
    btn.click()
    pump()
    check("눌렀더니 접혔나", win.numbers, True)

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if fails else 0)
