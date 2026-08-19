# -*- coding: utf-8 -*-
"""계통도 확대·축소 (2026-08-19 사용자 요청) + 앱을 최대화로 여는 것.

    ~/venvs/unigrid-acdc/bin/python tests/shot_topo_zoom.py

계기 — 사용자 *"토폴로지를 화면 확대, 축소 기능을 넣고 싶어"* ·
      *"처음 앱을 실행하자마자 앱 화면 크기를 모니터 화면에 최대화 해서 여는거"*

보는 것
    1) 단추(−·+·⟲)와 배율 표시가 있나
    2) 키우면 기호와 최소 크기가 **같이** 커지나 (그림이 실제로 커진다)
    3) 줄이면 작아지나
    4) 한계 밖 값을 넣으면 한계에서 멈추나
    5) 🚨 **계산을 다시 해도 배율이 남나** — 계통도 위젯은 계산 때마다 새로 만들어진다
    6) 🚨 **Ctrl+마우스휠로 바꿔도 % 표시가 따라오나** (단추 쪽에서만 갈면 안 따라온다)
    7) 그냥 굴리면 확대가 아니라 **화면이 밀려야** 한다
    8) 새 파일을 열면 배율이 100% 로 돌아가나
    9) 앱이 **최대화로** 열리나 (`main()` 이 showMaximized 를 부른다)
"""
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import warnings                                                  # noqa: E402
warnings.filterwarnings("ignore")
from PySide6.QtWidgets import (QApplication, QMessageBox,        # noqa: E402
                               QPushButton, QLabel)
from PySide6.QtCore import Qt, QPoint, QPointF                   # noqa: E402
from PySide6.QtGui import QWheelEvent                            # noqa: E402

qapp = QApplication([])
import app as APP                                                # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                                # noqa: E402
from topology import TopologyView                                # noqa: E402
from load_case import load_case                                  # noqa: E402

BIG = REPO / "cases/ACDC_71bus_3IC_parallel.xlsx"
SMALL = REPO / "cases/AConly_case14.xlsx"
fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<48} {got}")
    else:
        print(f"  ❌ {label:<48} {got}  (바라던 값 {want})")
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
pump(0.9)


def open_case(path):
    case = load_case(str(path))
    win.thread = Fake(case)
    win._last_path = str(path)
    win._solved(app_engine.solve(case))
    win.graph_tab = 3                 # 토폴로지 (앱이 rebuild 때 이 번호로 되살린다)
    win.rebuild()
    pump(1.6)


def view():
    """지금 화면에 붙어 있는 계통도.

    🚨 `findChildren` 은 **지워지기를 기다리는 옛 위젯**까지 잡는다(이 저장소에서
       여러 번 겪었다). 보이는 것 중 마지막 것이 방금 그린 것이다.
    """
    vs = [x for x in win.findChildren(TopologyView) if x.isVisible()]
    return vs[-1] if vs else None


def pct_label():
    ls = [l for l in win.findChildren(QLabel)
          if l.isVisible() and l.text().endswith("%") and len(l.text()) <= 5]
    return ls[-1] if ls else None


open_case(BIG)
v = view()
check("계통도를 찾았나", v is not None, True)

print("\n[1] 단추와 배율 표시가 있나")
btns = [b.text() for b in win.findChildren(QPushButton)
        if b.isVisible() and b.text() in ("−", "+", "⟲")]
check("단추 셋", sorted(set(btns)), sorted(["−", "+", "⟲"]))
check("배율 표시", pct_label().text() if pct_label() else None, "100%")

print("\n[2] 키우면 기호와 최소 크기가 같이 커지나")
u0, w0 = v.unit(), v.minimumWidth()
v.set_zoom(v.zoom * v.ZOOM_STEP)
pump(0.5)
u1, w1 = v.unit(), v.minimumWidth()
print(f"    기호 {u0:.1f} → {u1:.1f}px · 최소 가로 {w0} → {w1}px")
check("기호가 커졌나", u1 > u0 * 1.2, True)
check("최소 가로도 커졌나", w1 > w0 * 1.2, True)

print("\n[3] 줄이면 작아지나")
v.set_zoom(1.0)
pump(0.3)
v.set_zoom(v.zoom / v.ZOOM_STEP)
pump(0.5)
print(f"    기호 {u0:.1f} → {v.unit():.1f}px")
check("기호가 작아졌나", v.unit() < u0 * 0.9, True)

print("\n[4] 한계에서 멈추나")
v.set_zoom(99.0)
check("위 한계", v.zoom, v.ZOOM_MAX)
v.set_zoom(0.001)
check("아래 한계", v.zoom, v.ZOOM_MIN)

print("\n[5] 계산을 다시 해도 배율이 남나")
v.set_zoom(1.5)
pump(0.3)
check("앱이 적어 뒀나", round(win.topo_zoom, 4), 1.5)
win.rebuild()
pump(1.5)
check("다시 그린 뒤에도", round(view().zoom, 4), 1.5)

print("\n[6] Ctrl+마우스휠로 바꿔도 % 표시가 따라오나")
v = view()
v.set_zoom(1.0)
pump(0.4)
before = pct_label().text()
ev = QWheelEvent(QPointF(100, 100), v.mapToGlobal(QPoint(100, 100)),
                 QPoint(0, 0), QPoint(0, 120), Qt.NoButton,
                 Qt.ControlModifier, Qt.NoScrollPhase, False)
v.wheelEvent(ev)
pump(0.4)
print(f"    배율 {v.zoom:.4f} · 표시 {before} → {pct_label().text()}")
check("휠로 커졌나", v.zoom > 1.0, True)
check("표시가 따라왔나", pct_label().text(), f"{v.zoom * 100:.0f}%")

print("\n[7] 그냥 굴리면 확대가 아니라 화면이 밀려야 한다")
z_before = v.zoom
ev2 = QWheelEvent(QPointF(100, 100), v.mapToGlobal(QPoint(100, 100)),
                  QPoint(0, 0), QPoint(0, 120), Qt.NoButton,
                  Qt.NoModifier, Qt.NoScrollPhase, False)
v.wheelEvent(ev2)
pump(0.3)
check("배율이 그대로인가", v.zoom, z_before)
check("스크롤 상자에 넘겼나 (event 를 안 먹었나)", ev2.isAccepted(), False)

print("\n[8] 새 파일을 열면 100% 로 돌아가나")
open_case(SMALL)
check("배율", round(view().zoom, 4), 1.0)

print("\n[9] 앱이 최대화로 열리나")
import inspect                                                    # noqa: E402
src = inspect.getsource(APP.main)
check("main() 이 showMaximized 를 부르나", "showMaximized" in src, True)
check("그냥 show() 로 열지 않나", "\n    w.show()" not in src, True)

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if fails else 0)
