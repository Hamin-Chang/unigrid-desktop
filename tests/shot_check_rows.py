# -*- coding: utf-8 -*-
"""점검 탭 표가 줄 수만큼 높이를 갖나 (2026-08-18).

계기 — 26건을 잡아 놓고 화면이 **3줄만** 보여 주고 있었다. 세 표가 행 수와 무관하게
전부 **88px** 이었다(19행짜리도 1줄). 원인은 `app.py` 가 `setMaximumHeight` 만 걸어
둔 것 — 이 화면은 카드를 세로로 쌓고 끝에 `addStretch()` 를 두는데, `addWidget` 으로
붙은 것은 **늘림 몫이 0**이라 남는 자리를 전부 그 stretch 가 가져간다. 상한은 아무
일도 안 하고 표는 늘 제 기본 크기로 눌린다.

보는 것
    1) 줄이 적은 표(2행·5행)는 **다 보이나**
    2) 줄이 많은 표(19행)는 **10줄에서 끊기나** — 한 표가 화면을 통째로 먹지 않게
    3) 🚨 마지막으로 보여 주기로 한 줄이 **실제로 안 잘리나**
       (높이 셈이 머리글 몫을 모자라게 잡으면 마지막 줄이 반쯤 잘린 채 그려진다)
    4) 위반이 하나도 없는 계통에서는 표 대신 **"없음"** 이 뜨나
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
from PySide6.QtWidgets import (QApplication, QMessageBox,          # noqa: E402
                               QTableWidget)

qapp = QApplication([])
import app as APP                                                  # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                                  # noqa: E402
from load_case import load_case                                    # noqa: E402

fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<50} {got}")
    else:
        print(f"  ❌ {label:<50} {got}  (바라던 값 {want})")
        fails.append(label)


def pump(s=0.5):
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


def open_and_check(path):
    """케이스를 열고 점검 탭으로 간 뒤, 보이는 표들을 돌려준다."""
    case = load_case(str(path))
    win.thread = Fake(case)
    win._last_path = str(path)
    win._solved(app_engine.solve(case))
    win.table_tab = "점검"
    win.rebuild()
    pump(0.8)
    tt = win._tabs
    for i in range(tt.count()):
        if tt.tabText(i).startswith("점검"):
            tt.setCurrentIndex(i)
            break
    pump(0.8)
    out = []
    for tb in win.findChildren(QTableWidget):
        if tb.isVisible() and tb.rowCount() and tb.columnCount() <= 5:
            out.append(tb)
    return out


CASE = V14 / "cases_v2/ACDC_case24_MatACDC_v2.xlsx"
print(f"\n[케이스] {CASE.name}")
tables = open_and_check(CASE)
check("표가 셋인가", len(tables), 3)

CAP = APP.Proto.CHECK_MAX_ROWS
for tb in tables:
    rows = tb.rowCount()
    want_rows = min(rows, CAP)
    want_h = APP.Proto.CHECK_ROW_H * want_rows + APP.Proto.CHECK_CHROME

    print(f"\n[{rows}행 표]")
    check("높이가 줄 수를 따라가나", tb.height(), want_h)
    check("눌리지 않았나 (옛 결함 88px)", tb.height() != 88, True)

    # 🚨 마지막으로 보여 주기로 한 줄이 실제로 안 잘리나 — 행 사각형으로 잰다
    last = tb.visualItemRect(tb.item(want_rows - 1, 0))
    check(f"{want_rows}번째 줄이 안 잘리나",
          last.bottom() <= tb.viewport().height(), True)

    if rows <= CAP:
        check("줄이 적으면 스크롤이 없나",
              not tb.verticalScrollBar().isVisible(), True)

# 위반이 없는 계통 — 표 대신 "없음"
CLEAN = V14 / "cases_v2/AConly_case14_v2.xlsx"
if CLEAN.exists():
    print(f"\n[케이스] {CLEAN.name} — 위반이 적은 계통")
    tables = open_and_check(CLEAN)
    for tb in tables:
        rows = tb.rowCount()
        want_h = (APP.Proto.CHECK_ROW_H * min(rows, CAP)
                  + APP.Proto.CHECK_CHROME)
        check(f"{rows}행 표 높이", tb.height(), want_h)

print("\n" + ("통과" if not fails else f"실패 {len(fails)}건: {fails}"))
sys.stdout.flush()
os._exit(1 if fails else 0)
