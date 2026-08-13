# -*- coding: utf-8 -*-
"""③ 운전 조건 — 앱에서 값을 고쳐 실제로 답이 바뀌는지 확인하고 찍는다.

  1) 단위가 맞나 (발전기 P_gen 이 [MW] 로 10 인가, 10000000 이 아닌가)
  2) 지정전압을 고치면 답이 달라지나
  3) 고칠 수 없는 칸은 정말 막혀 있나
"""
import os
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/unigrid-desktop")
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox     # noqa: E402
from PySide6.QtCore import Qt                               # noqa: E402

qapp = QApplication([])
import app as APP                                           # noqa: E402
_seen = []
QMessageBox.warning = staticmethod(lambda *a, **k: _seen.append("경고"))
QMessageBox.information = staticmethod(lambda *a, **k: _seen.append("알림"))
QMessageBox.critical = staticmethod(lambda *a, **k: _seen.append("실패"))
import scenario as SC                                       # noqa: E402
import app_engine                                           # noqa: E402
from load_case import load_case                             # noqa: E402

CASE = REPO / "cases/AConly_case14.xlsx"
win = APP.Proto()
win.resize(1500, 950)
win.show()


def pump(s=0.35):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


def shot(name):
    pump()
    p = OUT / f"운전_{name}.png"
    win.grab().save(str(p))
    print(f"  찍음: {p.name}")


class Fake:
    def __init__(self, case):
        self.loaded_case = case


case = load_case(str(CASE))
win.thread = Fake(case)
win._last_path = str(CASE)
win._solved(app_engine.solve(case))
win.grid_key = "AC_gen_dat"
win.rebuild()

# ── 1) 단위 확인 ────────────────────────────────────────────────
# 첫 번호 열은 왼쪽 표로 따로 나갔다 — 이 함수는 담는 상자를 돌려준다(2026-08-13).
# 상자를 붙잡고 있어야 안의 표가 안 지워진다. 데이터 열 j = 화면 열 j + _grid_off.
box = win.grid_table_widget()
tb, off = win._grid_tb, win._grid_off
heads = [""] * (-off) + [tb.horizontalHeaderItem(i).text()
                         for i in range(tb.columnCount())]


def cellf(r, j):
    """데이터 열 j 의 칸 (왼쪽으로 나간 열이면 None)."""
    return tb.item(r, j + off) if j + off >= 0 else None
print("발전기 표 머리글:", heads[:9])
print("첫 줄 값       :", [cellf(0, i).text() if cellf(0, i) else "" for i in range(9)])
raw = float(np.asarray(case.tables["AC_gen_dat"].values, dtype=float)[0, 5])
print(f"  → 엔진 값 {raw:,.0f} W · 화면 값 '{cellf(0, 5).text()}' (머리글 {heads[5]})")

# ── 3) 못 고치는 칸이 정말 막혔나 ────────────────────────────────
locked = [i for i in range(tb.columnCount())
          if tb.item(0, i) and not (tb.item(0, i).flags() & Qt.ItemIsEditable)]
free = [i for i in range(tb.columnCount())
        if tb.item(0, i) and (tb.item(0, i).flags() & Qt.ItemIsEditable)]
print(f"고칠 수 있는 칸 {[heads[i - off] for i in free]}")
print(f"막힌 칸 {len(locked)}개")

# 화면에서도 발전기 표를 보이게
tabs = getattr(win, "_tabs", None)
if tabs is not None:
    for i in range(tabs.count()):
        if tabs.tabText(i).startswith("계통 데이터"):
            tabs.setCurrentIndex(i)
shot("1_발전기_운전조건")

# ── 2) 지정전압을 고치면 답이 달라지나 ──────────────────────────
v0 = float(np.nanmin(np.asarray(win.sol.AC, dtype=float)[:, 1]))
item = tb.item(0, 8)          # Vg [pu] (상태 칸이 없으므로 열 그대로)
print(f"고치는 칸: {heads[8]} · 지금 {item.text()}")
item.setText("1.02")
win.grid_edited("AC_gen_dat", item, 0, APP.GRID_SCALES.get("AC_gen_dat", {}))
print(f"바꾼 것 {len(win.changes)}건 — {SC.describe(win.changes)}")
tabs = getattr(win, "_tabs", None)
if tabs is not None:
    for i in range(tabs.count()):
        if tabs.tabText(i).startswith("계통 데이터"):
            tabs.setCurrentIndex(i)
shot("2_지정전압을_고친_뒤")

win._pending = win.applied + win.changes
sol2 = app_engine.solve(SC.apply(win.base_case, win._pending))
win.thread = Fake(case)
win._solved(sol2)
win.rebuild()
v1 = float(np.nanmin(np.asarray(sol2.AC, dtype=float)[:, 1]))
print(f"계산 뒤: 전압 최저 {v0:.4f} → {v1:.4f} ({v1 - v0:+.4f}) · 반복 {sol2.iters}회")
print("시나리오:", [s.name for s in win.book.items])
shot("3_계산한_뒤")

print("뜬 대화상자:", _seen)
app_engine.shutdown()
print("DONE_MODE")
