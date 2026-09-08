# -*- coding: utf-8 -*-
"""C 덩어리(단선도 5건) 확인 (2026-09-08).

i14 조류 격자를 눌러 어느 선로인지 · i15 부하율 막대도 같게 ·
i16 엉킴 줄이기(+자리 되돌리기) · i17 확대·이동 · i18 IC·버스 클릭, 전압 위반 표시 ·
i19 변환기 24시간 그래프(엔진 `all_VSC_*`).
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
                               QPushButton, QTableWidget)
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
for f, want_max in (("ACDC_case24_MatACDC.xlsx", 20),
                    ("AConly_case118.xlsx", 60)):
    sol = app_engine.solve(load_case(str(REPO / "cases" / f)))
    g = topology.build_graph(sol)
    n = topology.count_crossings(g, topology.layered_layout(g))
    chk(f"{f.split('.')[0]} 교차가 {want_max} 아래", n < want_max, True)
    print(f"     교차 {n}개")

print("\n[i16] 버스 막대가 서로 겹치지 않나")
# 🚨 **막대 길이는 고정이 아니다** — 붙은 선 수에 비례해 위아래로 뻗는다
#    (`half = max(u*0.70, min(u*1.60, u*0.45*선수))`). `_fit()` 이 한 행에
#    `u*1.25+20` 만 잡던 탓에 case24 는 **이웃 50쌍 중 28쌍이 겹쳤다**
#    (가장 심한 것 25.9px · 2026-09-08 사용자: *"버스들끼리 너무 붙어있다"*).
#    눈으로는 「좀 빽빽하네」로 넘어가던 것이라 **숫자로 박아 둔다.**
def _overlap(view):
    gg, u = view.g, view.unit()
    xy = view._px()
    inc = {i: 0 for i in range(len(gg.keys))}
    for a, b, _k in gg.edges:
        inc[a] += 1; inc[b] += 1
    def half(i):
        return (u * 0.55 if gg.role[i] == "3권선"
                else max(u * 0.70, min(u * 1.60, u * 0.45 * inc[i])))
    cols = {}
    for i in range(len(gg.keys)):
        cols.setdefault(round(float(xy[i][0]), 1), []).append(i)
    n_over, worst, pairs = 0, 0.0, 0
    for items in cols.values():
        items.sort(key=lambda i: xy[i][1])
        for a, b in zip(items, items[1:]):
            pairs += 1
            short = (half(a) + half(b)) - (float(xy[b][1]) - float(xy[a][1]))
            if short > 0:
                n_over += 1; worst = max(worst, short)
    return pairs, n_over, worst

for f in ("ACDC_case24_MatACDC.xlsx", "AConly_case118.xlsx",
          "ACDC_CIGRE_MVACMVDCLVDC.xlsx"):
    sol_ = app_engine.solve(load_case(str(REPO / "cases" / f)))
    wrap_ = charts.build("계통 단선도", win.c, sol_, 0, 0, False, None, None)
    wrap_.resize(1100, 560); wrap_.show(); pump(0.8)
    vv_ = wrap_.findChild(QScrollArea).widget()
    pairs, n_over, worst = _overlap(vv_)
    chk(f"{f.split('.')[0]} 막대가 안 겹친다", n_over, 0)
    print(f"     이웃 {pairs}쌍 · 겹침 {n_over}쌍 · 가장 심한 것 {worst:.1f}px")

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
    self.grab().save(str(OUT / f"C_popup_{len(shots)}.png")); shots.append(self); return 0
QDialog.exec = fake_exec
win.show_bus_profile(g, acn[5]); pump(0.4)
win.show_line_profile(g, ics[0]); pump(0.4)
chk("팝업이 둘 떴다", len(shots), 2)

print("\n[i19] 변환기도 24시간 그래프 — 엔진이 시각별로 준다")
# 🚨 **`{1}` 계열 결함의 세 번째 자리**였다 (2026-09-08 오후).
#    엔진이 `a_VSC_*` 로 24벌을 계산해 놓고 **첫 시각만** 내보내서, 변환기 팝업이
#    표에 머물렀다. 오전에 고친 `Tap_result` 와 정확히 같은 꼴이다.
#    ⇒ 「그래프가 떴다」로 끝내지 않고 **시각별 값이 실제로 다른지** 까지 잰다.
cube = getattr(win.sol, "VSC_grid_all", None)
chk("VSC_grid 가 3차원", getattr(cube, "ndim", 0), 3)
chk("24시각이 다 왔다", int(cube.shape[2]) if cube is not None else 0, 24)

moved = 0
for e in ics:
    sr = topology.ic_series(g, win.sol, e)
    if sr is None:
        continue
    for vals in sr[1].values():
        if max(vals) - min(vals) > 1e-6:
            moved += 1
            break
chk("하루 동안 움직이는 변환기가 있다", moved > 0, True)
print(f"     {len(ics)} 중 {moved} 개가 움직인다 (나머지는 정전력 운전이라 평평한 게 맞다)")

ser_ic = topology.ic_series(g, win.sol, ics[0])
chk("IC 시간축이 24개", len(ser_ic[0]) if ser_ic else 0, 24)
chk("유효·무효 둘 다 준다", sorted(ser_ic[1]) if ser_ic else [],
    ["Grid_P[MW]", "Grid_Q[MVAR]"])
chk("상세 모델은 비고가 없다", ser_ic[2] if ser_ic else "?", None)

from PySide6.QtCharts import QChartView
win.show_ic_facts(g, ics[0]); pump(0.4)
chk("IC 팝업이 떴다", len(shots), 3)
chk("IC 팝업 안에 그래프가 있다",
    len(shots[-1].findChildren(QChartView)) > 0, True)
chk("표도 같이 있다", len(shots[-1].findChildren(QTableWidget)) > 0, True)

# 🚨 **병렬 변환기를 구분하나** (2026-09-08).
#    짝(AC버스, DC버스)으로만 찾으면 `38–39` 셋이 전부 첫 행을 집는다.
#    계통도 순서 = VSC 표 행 순서라 순번으로 집어야 맞다.
t0 = win.sol.vsc_at("VSC_grid", 0)
rows_found = [topology._ic_row(g, win.sol, e, t0,
                               *[topology._busno(g.keys[x]) for x in
                                 ((g.edges[e][0], g.edges[e][1])
                                  if g.kind[g.edges[e][0]] != "DC"
                                  else (g.edges[e][1], g.edges[e][0]))])
              for e in ics]
chk("변환기마다 다른 행을 집는다", rows_found, list(range(len(ics))))

print("\n[i19] toAC_P 가 곧 변환기 조류인가 — 되돌아가기의 근거")
# 🚨 이상 변환기 계통은 VSC 표가 아예 없다. 그래도 **AC 표의 `toAC_P`** 로
#    그릴 수 있는 근거가 이 대조다 — 상세 모델 계통에서 둘이 같아야 한다.
#    (같지 않으면 되돌아가기가 다른 값을 그리는 셈이 된다.)
ac0, ca = win.sol.at("AC", 0), win.sol.cols("AC")
vg0, cg = win.sol.vsc_at("VSC_grid", 0), win.sol.cols("VSC_grid")
worst = 0.0
for r in vg0:
    row = ac0[ac0[:, 0].astype(int) == int(r[0])]
    if not len(row):
        continue
    worst = max(worst,
                abs(float(row[0][ca.index("toAC_P[MW]")]) - float(r[cg.index("Grid_P[MW]")])),
                abs(float(row[0][ca.index("toAC_Q[MVAR]")]) - float(r[cg.index("Grid_Q[MVAR]")])))
chk("toAC_P·Q 가 Grid_P·Q 와 같다", worst < 0.01, True)
print(f"     가장 큰 차이 {worst:.4f} MW")

print("\n[i19] 이상 변환기 계통도 조류 그래프가 뜬다")
# 🚨 사용자 요구: *"IC 누르면 선로처럼 조류량이 나타나게 하라고"* (2026-09-08).
#    앞 판은 「이 계통은 변환기를 이상 소자로 봅니다」로 **설명만** 하고 그래프를
#    안 그렸다. 값은 AC 표에 있었으므로 그릴 수 있었다.
from PySide6.QtWidgets import QLabel
from PySide6.QtCharts import QChartView as _CV
for fn, n_ic_on_bus in (("ACDC_71bus_3IC_parallel_24h.xlsx", 3),
                        ("ACDC_CIGRE_MVACMVDCLVDC_24h.xlsx", 1)):
    open_it(fn)
    gi = topology.build_graph(win.sol)
    ei = [i for i, (a, b, k) in enumerate(gi.edges) if k == "IC"]
    tag = fn.split("_")[1]
    chk(f"{tag} 시각 수", int(win.sol.n_time), 24)
    chk(f"{tag} 이상 변환기로 본다", bool(win.sol.vsc_ideal), True)
    sr = topology.ic_series(gi, win.sol, ei[0])
    chk(f"{tag} 조류 그래프감이 나온다", sr is not None, True)
    chk(f"{tag} 24시각이다", len(sr[0]) if sr else 0, 24)
    chk(f"{tag} P·Q 둘 다", sorted(sr[1]) if sr else [], ["P [MW]", "Q [MVAr]"])
    chk(f"{tag} 값이 하루 동안 변한다",
        max(max(v) - min(v) for v in sr[1].values()) > 1e-6 if sr else False, True)
    facts = dict(topology.ic_facts(gi, win.sol, ei[0], 0))
    chk(f"{tag} 표에도 P 가 있다", "P [MW]" in facts, True)
    chk(f"{tag} 모델을 밝힌다", facts.get("모델"), "이상 변환기 (임피던스 0)")
    win.show_ic_facts(gi, ei[0]); pump(0.3)
    chk(f"{tag} 팝업에 그래프가 있다", len(shots[-1].findChildren(_CV)) > 0, True)
    txt = " ".join(l.text() for l in shots[-1].findChildren(QLabel))
    chk(f"{tag} 「시각이 하나」라고 안 한다", "시각이 하나" in txt, False)
    # 한 버스에 변환기가 여럿이면 합계라고 밝혀야 한다
    chk(f"{tag} 합계인지 밝힌다", "합친 값" in txt, n_ic_on_bus > 1)

open_it("ACDC_case24_MatACDC_24h.xlsx")     # 뒤 시험이 쓰는 계통으로 되돌린다
g = topology.build_graph(win.sol)

print("\n[i14·i15] 그래프에서 눌러 그 선로로")
br = win.sol.at("Branch", 0)
fr, to = int(br[0][0]), int(br[0][1])
n_before = len(shots)
win.pick_line_by_bus(str(fr), str(to)); pump(0.4)
chk("선로 팝업이 떴다", len(shots), n_before + 1)
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

# 🚨 **「지도처럼 커지는가」를 숫자로 박아 둔다** (2026-09-08).
#    처음 고쳤을 때 스크롤 자리만 맞추고 «커지는 방식» 은 그대로 둬서,
#    기호만 커지고 간격은 안 커졌다 — 사용자가 *"그냥 요소가 커졌다 작아졌다가
#    되는데"* 로 잡아냈다. 눈으로는 그럴듯해 보였다.
#    ⇒ **화면에서 두 버스 사이가 배율만큼 벌어지는지** 를 잰다.
def _gap(view):
    xs = sorted(set(round(float(a[0]), 1) for a in view._px()))
    return (xs[1] - xs[0]) * view.zoom if len(xs) > 1 else 0.0
vv.set_zoom(1.0); pump(0.6)
g1 = _gap(vv)
vv.set_zoom(2.0); pump(0.6)
g2 = _gap(vv)
chk("화면상 간격도 배율만큼 커진다", abs(g2 / max(g1, 1e-9) - 2.0) < 0.1, True)
print(f"     버스 사이 {g1:.0f}px → {g2:.0f}px  (×{g2/max(g1,1e-9):.2f})")
lw1, _ = vv._logical()
chk("논리 크기는 안 변한다", abs(lw1 * 2 - vv.width()) < 3, True)
print(f"     논리 폭 {lw1:.0f} · 위젯 폭 {vv.width()}")
# 확대해도 클릭이 안 어긋나나
from PySide6.QtCore import QPointF as _QPF
xy = vv._px()
chk("200% 에서도 그 버스를 집는다",
    vv._hit(_QPF(float(xy[5][0]) * 2.0, float(xy[5][1]) * 2.0)), 5)
vv.set_zoom(1.0); pump(0.4)
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
