# -*- coding: utf-8 -*-
"""자동 조정 패널 시험 (2026-08-27) — 사람이 밟는 길로만 탄다."""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "shots_adjust"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
import numpy as np
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
qapp = QApplication([])
import app as APP
import adjust_panel as ADJ
import scenario as SC
_dlg = []
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: _dlg.append(a[2] if len(a) > 2 else "")))
win = APP.Proto(); win.resize(1600, 1000); win.show()
ok = [0]; bad = []
def chk(name, got, want):
    if got == want: ok[0] += 1; print(f"  ✅ {name}")
    else: bad.append(name); print(f"  ❌ {name}: {got!r} ≠ {want!r}")
def pump(s=0.4):
    e = time.time()+s
    while time.time() < e: qapp.processEvents(); time.sleep(0.01)
def open_it(f):
    win._start_solve(str(REPO/"cases"/f))
    e = time.time()+240
    while time.time() < e:
        qapp.processEvents()
        if win.thread.isFinished(): break
        time.sleep(0.02)
    pump(0.8)
def shot(n):
    win.grab().save(str(OUT/f"{n}.png")); print(f"  📷 {n}.png")

print("[1] 탭 조정 케이스 — 패널이 그 하나를 잡나")
open_it("ACDC_case24_tapctrl.xlsx")
chk("걸린 조정 수", ADJ.count(win), 1)
chk("선로 줄", ADJ.rows_on(win, ADJ.LINE), [6])
win.table_tab = "계통 데이터"; win.grid_key = ADJ.KEY; win.rebuild(); pump(1.0)
shot("01_탭조정")

print("[2] 션트 케이스 — 버스 쪽도 같은 패널에 오나")
open_it("ACDC_case24_shuntctrl.xlsx")
win.table_tab = "계통 데이터"; win.grid_key = ADJ.KEY; win.rebuild(); pump(1.0)
chk("걸린 조정 수", ADJ.count(win), 1)
chk("버스 줄", ADJ.rows_on(win, ADJ.BUS), [5])
shot("02_SVC")

print("[3] 아무것도 없는 계통 — 빈 안내가 나오나")
open_it("AConly_case118.xlsx")
win.table_tab = "계통 데이터"; win.grid_key = ADJ.KEY; win.rebuild(); pump(1.0)
chk("걸린 조정 수", ADJ.count(win), 0)
shot("03_빈패널")

print("[4] 새로 걸기 — 값이 진짜 들어가나")
QDialog.exec = lambda self: QDialog.Accepted
n0 = len(win.changes)
ADJ.add_dialog(win); pump(0.5)
chk("바꾼 목록이 하나 늘었나", len(win.changes) - n0, 1)
chk("패널에 하나 잡히나", ADJ.count(win), 1)
row = ADJ.rows_on(win, ADJ.LINE)[0]
win.adj_typed(ADJ.LINE, row, 15, "1.05"); pump(0.3)
win.adj_typed(ADJ.LINE, row, 16, "0.9"); pump(0.3)
win.adj_typed(ADJ.LINE, row, 17, "1.1"); pump(0.3)
a = SC._values(SC.apply(win.base_case, win.applied + win.changes), ADJ.LINE)
chk("목표가 들어갔나", float(a[row, 15]), 1.05)
chk("최소가 들어갔나", float(a[row, 16]), 0.9)
win.rebuild(); pump(0.8); shot("04_새로걺")

print("[5] 지우기 — 흔적이 남나")
win.adj_remove(ADJ.LINE, row); pump(0.5)
chk("패널에서 사라졌나", ADJ.count(win), 0)
a = SC._values(SC.apply(win.base_case, win.applied + win.changes), ADJ.LINE)
chk("목표도 비었나", bool(np.isnan(a[row, 15])), True)

print("[6] 계산까지 — 패널로 건 것이 실제로 풀리나")
open_it("ACDC_case24_tapctrl.xlsx")
row = ADJ.rows_on(win, ADJ.LINE)[0]
win.adj_typed(ADJ.LINE, row, 15, "1.03"); pump(0.3)
win._pending = win.applied + win.changes
sol = APP.ENGINE.solve(SC.apply(win.base_case, win._pending))
chk("풀리나", bool(sol.converged), True)
tap = getattr(sol, "tap_ctrl", None)   # 🚨 이름은 tap_ctrl 이다 (app_engine.py:108)
chk("탭 결과가 오나", tap is not None and len(tap) > 0, True)
# 맞추라고 한 곳의 전압이 실제로 목표에 붙었나 — 이것이 진짜 확인이다
if tap is not None and len(tap):
    # tap_ctrl 한 줄 = [선로, 맞추는 버스, 목표, 정해진 값, …] (실측 2026-08-27)
    chk("패널에 친 목표가 엔진까지 갔나", round(float(tap[0][2]), 4), 1.03)
    bus = int(tap[0][1])
    AC = sol.AC                       # 🚨 (버스 × 열 × 시간) 3차원이다
    idx = [i for i in range(AC.shape[0]) if int(AC[i, 0, 0]) == bus]
    chk("맞추는 버스를 결과에서 찾았나", len(idx), 1)
    if idx:
        chk("그 버스가 목표 1.03 에 붙었나", round(float(AC[idx[0], 1, 0]), 4), 1.03)

print("[7] 표 쪽은 그대로 도나 (안 깨졌나)")
win.grid_key = "AC_Line_dat"; win.rebuild(); pump(0.6)
chk("표로 되돌아오나", win.grid_key, "AC_Line_dat")
win.grid_key = "AC_gen_dat"; win.rebuild(); pump(0.4)
chk("다른 표도 되나", win.grid_key, "AC_gen_dat")

print("═"*60)
print(f"  통과 {ok[0]} · 실패 {len(bad)}")
for b in bad: print(f"    ❌ {b}")
sys.exit(1 if bad else 0)
