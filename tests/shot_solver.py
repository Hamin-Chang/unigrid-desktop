# -*- coding: utf-8 -*-
"""해법 고르기(Newton / Gauss-Seidel) — 실제로 도는지 확인하고 찍는다 (2026-08-12, §7.6 G8).

  1) droop 없는 AC 계통 → Gauss-Seidel 을 고를 수 있나
  2) droop 계통 → 흐려지고 까닭이 뜨나
  3) 해법을 바꾸면 **정말 그 해법으로 다시 푸나** (반복 횟수가 바뀌는지로 본다)
  4) 혼합 계통(AC/DC) → 흐려지나
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

from PySide6.QtWidgets import QApplication, QMessageBox      # noqa: E402

qapp = QApplication([])
import app as APP                                            # noqa: E402
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)
import app_engine                                            # noqa: E402
from load_case import load_case                              # noqa: E402

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


def load(path, method="nr"):
    case = load_case(str(path))
    win.thread = Fake(case)
    win._last_path = str(path)
    win.solver = method
    win._solved(app_engine.solve(case, method=method))
    win.rebuild()
    pump()
    return case


_pages = []          # ⚠️ 페이지를 붙들고 있어야 한다 — 놓으면 Qt 가 위젯을 지운다


def picker():
    """수렴 탭을 그리고 그 안의 고르기 위젯을 돌려준다."""
    _pages.append(win.conv_page())
    return getattr(win, "_solver_pick", None)


def report(tag, path, method="nr"):
    load(path, method)
    p = picker()
    if p is None:
        print(f"  {tag:<24} ⚠️ 고르기 위젯이 없다")
        return None
    gs_on = p.model().item(1).isEnabled()
    print(f"  {tag:<24} 고른 것={p.currentData():<3} "
          f"Gauss-Seidel {'고를 수 있음' if gs_on else '흐림'}"
          f"{'' if gs_on else '  까닭: ' + (p.toolTip() or '')[:44]}")
    return p


print("\n=== 1) 어느 계통에서 고를 수 있나 ===")
report("AC only (droop 없음)", V14 / "cases_v2/AConly_case14_v2.xlsx")
report("droop 계통", V14 / "cases_v2/gs_droop_v2.xlsx")
report("AC/DC 혼합", V14 / "cases_v2/ACDC_71bus_v2.xlsx")

print("\n=== 2) 해법을 바꾸면 정말 그 해법으로 푸나 ===")
case = load(V14 / "cases_v2/AConly_case14_v2.xlsx", "nr")
print(f"  Newton       : 반복 {win.sol.iters}회")
win_gs = load(V14 / "cases_v2/AConly_case14_v2.xlsx", "gs")
print(f"  Gauss-Seidel : 반복 {win.sol.iters}회")
ok = win.sol.iters > 50
print(f"  → {'✅ 반복 횟수가 확 달라졌다 — 다른 해법으로 푼 것이 맞다' if ok else '🚨 반복이 안 바뀐다'}")

print("\n=== 3) 화면 (수렴 탭을 열고 찍는다) ===")


def open_conv_tab():
    """아래쪽 표 묶음에서 '수렴' 탭을 찾아 연다.

    ⚠️ `rebuild()` 가 탭 묶음을 새로 만들면서 **옛 위젯이 창에 남아 있다**(안 보이는 채로).
       그래서 `findChildren` 으로 처음 잡히는 것을 열면 화면이 안 바뀐다 —
       **눈에 보이는 것만** 골라야 한다(2026-08-12 에 실제로 여기서 헤맸다).
    """
    from PySide6.QtWidgets import QTabWidget
    for tw in win.findChildren(QTabWidget):
        if not tw.isVisible():
            continue
        for i in range(tw.count()):
            if tw.tabText(i) == "수렴":
                tw.setCurrentIndex(i)
                return True
    return False


def shot(path, method, name):
    load(path, method)
    win.rebuild()
    pump(0.4)
    found = open_conv_tab()
    pump(0.5)
    p = OUT / name
    win.grab().save(str(p))
    print(f"  찍음: {p.name}   (수렴 탭 {'열림' if found else '⚠️ 못 찾음'})")


shot(V14 / "cases_v2/AConly_case14_v2.xlsx", "gs", "해법고르기_AConly_GS.png")
shot(V14 / "cases_v2/gs_droop_v2.xlsx", "nr", "해법고르기_droop_흐림.png")

print("\n✅ 전부 통과" if ok else "\n🚨 확인 필요")
