# -*- coding: utf-8 -*-
"""결과 표에서 버스 번호로 찾기 (2026-08-18).

계기 — 「버스 번호로 찾기」가 **계통 데이터 탭에만** 있었다. 1,888버스 계통이면
결과 표가 1,888줄인데 한 화면에 20줄뿐이라, 특정 버스를 보려면 95화면을 굴려야 했다.

보는 것
    1) 번호를 넣으면 그 줄만 남나 · 「N줄 중 M줄」 을 맞게 말하나
    2) 선로 조류 탭은 **From·To 둘 다**로 걸리나 (그 버스에 붙은 선로가 나와야 한다)
    3) 결과 표 셋이 **같은 번호로 함께** 걸러지나
    4) 비우면 전부 돌아오나
    5) 🚨 **정렬과 함께 써도 어긋나지 않나** — 줄 숨김은 *줄 번호*로 걸리는데
       정렬은 줄을 뒤섞는다. 다시 안 걸면 엉뚱한 줄이 숨는다.
    6) 🚨 큰 계통에서도 빠른가 (줄만 숨기므로 화면을 다시 안 그린다)
    7) 계통 데이터 탭의 찾기와 **서로 안 섞이나** (딴 칸이다)
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
from PySide6.QtWidgets import (QApplication, QMessageBox,          # noqa: E402
                               QTableWidget)

qapp = QApplication([])
import app as APP                                                  # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                                  # noqa: E402
from load_case import load_case                                    # noqa: E402

CASE = V14 / "cases_v2/ACDC_case24_MatACDC_v2.xlsx"
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
    pump(1.4)


def table(tab):
    tt = win._tabs
    for i in range(tt.count()):
        if tt.tabText(i) == tab:
            tt.setCurrentIndex(i)
            pump(0.5)
            return tt.currentWidget().findChild(QTableWidget)
    return None


def shown(t, col=0):
    return [t.item(r, col).text()
            for r in range(t.rowCount()) if not t.isRowHidden(r)]


print("\n[1] 번호를 넣으면 그 줄만 남나")
open_case(CASE)
t = table("AC 결과")
n_all = t.rowCount()
check("처음엔 전부 보이나", len(shown(t)), n_all)
win.set_res_find("106 107 110")
pump(1.0)
t = table("AC 결과")
check("찾은 줄", shown(t), ["106", "107", "110"])
check("라벨", win._find_label.text(), f"{n_all:,}줄 중 3줄")

print("\n[2] 선로 조류는 From·To 둘 다로 걸리나")
t2 = table("선로 조류")
pairs = [(t2.item(r, 0).text(), t2.item(r, 1).text())
         for r in range(t2.rowCount()) if not t2.isRowHidden(r)]
want = {"106", "107", "110"}
check("보이는 줄이 있나", len(pairs) > 0, True)
check("전부 그 버스에 붙었나",
      all(a in want or b in want for a, b in pairs), True)
check("한쪽 끝만 걸린 줄도 있나 (From 만 보면 놓친다)",
      any((a in want) != (b in want) for a, b in pairs), True)

print("\n[3] 결과 표 셋이 함께 걸러지나")
for tab in ("AC 결과", "DC 결과", "선로 조류"):
    tt = table(tab)
    if tt is None:
        continue
    check(f"{tab} — 줄이 줄었나", len(shown(tt)) < tt.rowCount(), True)

print("\n[5] 🚨 정렬과 함께 써도 어긋나지 않나")
t = table("AC 결과")
iv = [t.horizontalHeaderItem(i).text()
      for i in range(t.columnCount())].index("VM[pu]")
t.horizontalHeader().setSortIndicator(iv, Qt.AscendingOrder)
pump(0.8)
t = table("AC 결과")
check("보이는 줄이 그대로 셋인가", sorted(shown(t)), ["106", "107", "110"])
vs = [float(t.item(r, iv).text())
      for r in range(t.rowCount()) if not t.isRowHidden(r)]
check("그 셋이 전압 오름차순인가",
      all(vs[i] <= vs[i + 1] for i in range(len(vs) - 1)), True)

print("\n[7] 계통 데이터 탭의 찾기와 안 섞이나")
check("딴 칸인가", win.grid_find != win.res_find or win.grid_find == "", True)
print(f"    계통 데이터 '{win.grid_find}' · 결과 표 '{win.res_find}'")

print("\n[4] 비우면 전부 돌아오나")
win.set_res_find("")
pump(1.2)
t = table("AC 결과")
check("전부 보이나", len(shown(t)), t.rowCount())

print("\n[6] 🚨 큰 계통에서도 빠른가")
open_case(BIG)
t0 = time.time()
win.set_res_find("1200 1201")
qapp.processEvents()
dt = time.time() - t0
t = table("AC 결과")
check("찾은 줄", sorted(shown(t)), ["1200", "1201"])
print(f"    {t.rowCount():,}행 · {dt:.3f}초")
check("1초 안에 끝나나", dt < 1.0, True)

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if fails else 0)
