# -*- coding: utf-8 -*-
"""C 덩어리(단선도 5건) 확인 (2026-09-08).

i14 조류 격자를 눌러 어느 선로인지 · i15 부하율 막대도 같게 ·
i16 엉킴 줄이기(+자리 되돌리기) · i17 확대·이동 · i18 IC·버스 클릭, 전압 위반 표시.
"""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "shots_C"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
import numpy as np
from PySide6.QtCore import QPointF, Qt, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (QApplication, QMessageBox, QDialog, QScrollArea,
                               QPushButton)
qapp = QApplication([])
import app as APP, app_engine, topology, charts
from load_case import load_case
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))

ok, bad = [0], []
def chk(name, got, want):
    if got == want: ok[0] += 1; print(f"  ✅ {name}  {got!r}")
    else: bad.append(name); print(f"  🚨 {name}: {got!r} ≠ {want!r}")
def pump(s=0.6):
    e = time.time() + s
    while time.time() < e: qapp.processEvents(); time.sleep(0.01)

win = APP.Proto(); win.resize(1500, 980); win.show()
class Fake:
    def __init__(self, c): self.loaded_case = c; self.case = None
def open_it(f):
    case = load_case(str(REPO / "cases" / f))
    win.thread = Fake(case); win._last_path = str(REPO / "cases" / f)
    win._solved(app_engine.solve(case)); pump()

print("[i16] 배치 — 선이 서로 넘나드는 수")
для = None
for f, want_max in (("ACDC_case24_MatACDC.xlsx", 20),
                    ("AConly_case118.xlsx", 60)):
    sol = app_engine.solve(load_case(str(REPO / "cases" / f)))
    g = topology.build_graph(sol)
    n = topology.count_crossings(g, topology.layered_layout(g))
    chk(f"{f.split('.')[0]} 교차가 {want_max} 아래", n < want_max, True)
    print(f"     교차 {n}개")

print("\n[i16] 자리 되돌리기")
topology.save_places("__시험__.xlsx", {"A1": [0.1, 0.2]})
chk("옮긴 자리가 있다고 안다", topology.has_places("__시험__.xlsx"), True)
chk("지운다", topology.clear_places("__시험__.xlsx"), True)
chk("지운 뒤엔 없다", topology.has_places("__시험__.xlsx"), False)

open_it("ACDC_case24_MatACDC_24h.xlsx")
g = topology.build_graph(win.sol)

print("\n[i18] 전압 위반 버스를 「위반 보기」 없이도 표시")
wrap = charts.build("계통 단선도", win.c, win.sol, 0, 0, False, None,
                    win.show_line_profile, on_bus_click=win.show_bus_profile)
v = wrap.findChild(QScrollArea).widget()
chk("위반 보기는 꺼져 있다", v.show_violations, False)
chk("그래도 위반 버스가 실렸다", len(v.overlay["vbad"]) > 0, True)
chk("선 색칠은 안 켠다", len(v.overlay["load"]), 0)
print(f"     위반 버스 {len(v.overlay['vbad'])}곳")

print("\n[i18] IC 도 눌리고, 버스는 24시간 전압")
ics = [i for i, (a, b, k) in enumerate(g.edges) if k == "IC"]
chk("IC 가 있다", len(ics) > 0, True)
facts = topology.ic_facts(g, win.sol, ics[0], 0)
chk("IC 값이 나온다", bool(facts) and len(facts) >= 3, True)
acn = [i for i in range(len(g.keys)) if g.keys[i].startswith("A")]
ser = topology.bus_series(g, win.sol, acn[5])
chk("버스 24시간 전압", ser is not None and len(ser[0]), 24)
chk("한계도 같이 준다", ser[2][0] is not None, True)

shots = []
def fake_exec(self):
    self.grab().save(str(OUT / f"C_popup_{len(shots)}.png")); shots.append(1); return 0
QDialog.exec = fake_exec
win.show_bus_profile(g, acn[5]); pump(0.4)
win.show_line_profile(g, ics[0]); pump(0.4)
chk("팝업이 둘 떴다", len(shots), 2)

print("\n[i14·i15] 그래프에서 눌러 그 선로로")
br = win.sol.at("Branch", 0)
fr, to = int(br[0][0]), int(br[0][1])
win.pick_line_by_bus(str(fr), str(to)); pump(0.4)
chk("선로 팝업이 떴다", len(shots), 3)
print(f"     {fr}–{to} 로 눌러 봄")

print("\n[i17] 확대는 보던 자리 기준 · 휠 눌러 밀기")
wrap2 = charts.build("계통 단선도", win.c, win.sol, 0, 0, False, None,
                     win.show_line_profile)
wrap2.resize(900, 600); wrap2.show(); pump(0.8)
sa = wrap2.findChild(QScrollArea); vv = sa.widget()
chk("스크롤 상자를 찾는다", vv._scroller() is sa, True)
hb, vb = sa.horizontalScrollBar(), sa.verticalScrollBar()
hb.setValue(hb.maximum() // 2); vb.setValue(vb.maximum() // 2); pump(0.3)
f0 = ((hb.value() + sa.viewport().width() / 2) / vv.width(),
      (vb.value() + sa.viewport().height() / 2) / vv.height())
vv.set_zoom(2.0); pump(0.6)
f1 = ((hb.value() + sa.viewport().width() / 2) / vv.width(),
      (vb.value() + sa.viewport().height() / 2) / vv.height())
d = max(abs(f1[0] - f0[0]), abs(f1[1] - f0[1]))
chk("확대해도 보던 자리에 머문다", d < 0.05, True)
print(f"     어긋남 {d:.4f}")
vv.set_zoom(1.0); pump(0.4)
hb.setValue(hb.maximum() // 2); vb.setValue(vb.maximum() // 2); pump(0.2)
h0, v0 = hb.value(), vb.value()
def me(kind, x, y, btn):
    return QMouseEvent(kind, QPointF(x, y), QPointF(x, y), btn, btn, Qt.NoModifier)
vv.mousePressEvent(me(QEvent.MouseButtonPress, 400, 300, Qt.MiddleButton))
vv.mouseMoveEvent(me(QEvent.MouseMove, 340, 250, Qt.MiddleButton))
vv.mouseReleaseEvent(me(QEvent.MouseButtonRelease, 340, 250, Qt.MiddleButton))
pump(0.3)
chk("휠을 눌러 끌면 밀린다", (hb.value(), vb.value()) != (h0, v0), True)

print(f"\n>>> 대조 {ok[0]}개 · 실패 {len(bad)}건" + (f" — {bad}" if bad else ""))
sys.exit(1 if bad else 0)
