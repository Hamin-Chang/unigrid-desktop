# -*- coding: utf-8 -*-
"""24시각 계통에서 **화면의 탭이 시각마다 달라지는가** (2026-09-08).

예전에는 앱이 첫 시각 탭 하나를 하루 내내 보여줬다 — 화면이 계산과 달랐다.
사람이 밟는 길(⚙ 조정 패널에 치고 → 계산 → 시간 바꾸기)로 점검 탭을 찍는다.
"""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "shots_tap_bytime"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox
qapp = QApplication([])
import app as APP
import app_engine
import scenario as SC
from load_case import load_case

for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))

CASE = REPO / "cases" / "ACDC_case24_MatACDC_24h.xlsx"
ROW, CTRL_BUS, TARGET = 6, 124, 1.009608       # 7번 선로 (0부터 6)
TMIN, TMAX, STEP = 0.9, 1.1, 0.00625

win = APP.Proto(); win.resize(1500, 980); win.show()

def pump(s=0.4):
    e = time.time() + s
    while time.time() < e:
        qapp.processEvents(); time.sleep(0.01)

class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None

case = load_case(str(CASE))
win.thread = Fake(case)
win._last_path = str(CASE)
win._solved(app_engine.solve(case))
pump()
print(f"열림 — 수렴 {win.sol.converged} · 시각 {win.sol.n_time}")

ok, bad = [0], []
def chk(name, got, want):
    if got == want: ok[0] += 1; print(f"  ✅ {name}  {got!r}")
    else: bad.append(name); print(f"  🚨 {name}: {got!r} ≠ {want!r}")
def shot(n):
    win.grab().save(str(OUT / f"{n}.png")); print(f"  📷 {n}.png")

print("\n[1] ⚙ 조정 패널에 탭 조정을 친다 (사람이 밟는 길)")
for col, val in ((13, 1), (14, CTRL_BUS), (15, TARGET),
                 (16, TMIN), (17, TMAX), (18, STEP)):
    win.adj_typed("AC_Line_dat", ROW, col, f"{val:g}")
    pump(0.1)
print(f"    바꾼 것 {len(win.changes)}건")

print("\n[2] [이 조건으로 계산] 을 누른 것과 같은 길로 푼다")
# `_pending` 을 채워 두면 `_solved` 가 「바꾼 것」을 비우고 시나리오로 담는다 —
# 안 채우면 「아직 계산 안 함」 배너가 남아 화면이 사실과 다르게 보인다.
c2 = SC.apply(win.base_case, win.applied + win.changes)
win._pending = list(win.applied + win.changes)
win.thread = Fake(c2)
win._solved(app_engine.solve(c2))
pump()
sol = win.sol
print(f"    수렴 {sol.converged} · tap_all {np.asarray(sol.tap_all).shape}")
chk("탭이 시각 24벌로 온다", np.asarray(sol.tap_all).shape[2], 24)
vals = [round(float(sol.tap_at(t)[0, 3]), 10) for t in range(24)]
chk("값이 하나로 굳지 않았다", len(set(vals)) > 1, True)
chk("첫 시각 탭", round(vals[0], 5), 0.96875)
chk("17시 탭이 첫 시각과 다르다", vals[16] != vals[0], True)

print("\n[3] 시간을 바꾸며 점검 탭을 찍는다")
win.table_tab = "점검"
for t, tag in ((0, "01_1H"), (4, "02_5H"), (16, "03_17H"), (23, "04_24H")):
    win.t = t
    win.rebuild(); pump(0.8)
    tp = sol.tap_at(t)
    print(f"    {t+1:2d} H — 탭 {tp[0,3]:.6f} · "
          f"{'목표 맞춤' if tp[0,4] else '⚠ 한계에 걸려 목표 포기'}")
    shot(tag)

print(f"\n>>> 대조 {ok[0]}개 · 실패 {len(bad)}건")
sys.exit(1 if bad else 0)
