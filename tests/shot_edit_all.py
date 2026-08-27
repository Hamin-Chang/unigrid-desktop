# -*- coding: utf-8 -*-
"""계통 데이터를 전부 고칠 수 있게 — 값 칸 열기 + 칸마다 검사 (2026-08-27).

  ① 회색이던 값 칸이 열렸나 (110/114)
  ② 엉뚱한 값을 막고 **왜 안 되는지** 말해 주나
  ③ 멀쩡한 값은 통과하고 계산까지 가나
  ④ 짝 한계·ZIP 합은 **막지 않고 알려만** 주나
  ⑤ 뜻을 모르는 칸 넷은 여전히 잠겼나
"""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "shots_edit"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
import numpy as np
from PySide6.QtWidgets import (QApplication, QMessageBox, QTableWidgetItem)
from PySide6.QtCore import Qt
qapp = QApplication([])
import app as APP
import cell_rules as RULES
import scenario as SC
import app_engine
_msg = []
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(
        lambda *a, **k: _msg.append((a[1] if len(a) > 1 else "",
                                     a[2] if len(a) > 2 else ""))))
win = APP.Proto(); win.resize(1600, 1000); win.show()
ok = [0]; bad = []
def chk(n, got, want):
    if got == want: ok[0] += 1; print(f"  ✅ {n}")
    else: bad.append(n); print(f"  ❌ {n}: {got!r} ≠ {want!r}")
def pump(s=0.4):
    e = time.time()+s
    while time.time() < e: qapp.processEvents(); time.sleep(0.01)

win._start_solve(str(REPO/"cases/ACDC_case24_tapctrl.xlsx"))
e = time.time()+240
while time.time() < e:
    qapp.processEvents()
    if win.thread.isFinished(): break
    time.sleep(0.02)
pump(1.0)
win.table_tab = "계통 데이터"

print("[1] 값 칸이 열렸나")
tot = sum(len(APP.GRID_HEADERS.get(k, [])) for k, _ in APP.GRID_TABLES)
opened = sum(len(APP.GRID_EDITABLE.get(k, set()) | RULES.editable(k)
                 | APP.GRID_PANEL_COLS.get(k, set())) for k, _ in APP.GRID_TABLES)
chk("열 수", tot, 114)
chk("손댈 수 있는 칸", opened, 110)

print("[2] 뜻을 모르는 넷은 잠겨 있나")
chk("DC/DC 효율곡선 셋", [c for c in (2, 3, 4) if c in RULES.editable("DCDC_Conv_dat")], [])
chk("DC 버스 Nominal Current", 1 in RULES.editable("DC_Bus_dat"), False)

def type_in(key, row, col, text):
    """사람이 표에 친 것과 같은 길."""
    win.grid_key = key; win.rebuild(); pump(0.3)
    tb, off = win._grid_tb, win._grid_off
    _msg.clear()
    it = QTableWidgetItem(text)
    tb.setItem(row, col + off, it)
    win.grid_edited(key, it, off, APP.GRID_SCALES.get(key, {}))
    pump(0.2)
    return _msg

def cur(key, row, col):
    a = SC._values(SC.apply(win.base_case, win.applied + win.changes), key)
    return float(a[row, col])

print("[3] 엉뚱한 값을 막나")
before = len(win.changes)
m = type_in("AC_Line_dat", 0, 1, "9999")          # From — 없는 버스
chk("없는 버스를 막나", len(win.changes), before)
chk("까닭을 말해 주나", bool(m) and "계통에 없습니다" in m[-1][1], True)
m = type_in("AC_Line_dat", 0, 12, "2")            # Status — 0/1 아님
chk("0/1 아닌 깃발을 막나", len(win.changes), before)
chk("까닭", bool(m) and "0(끔)" in m[-1][1], True)
m = type_in("AC_Line_dat", 0, 8, "-5")            # rateA — 음수
chk("음수 정격을 막나", len(win.changes), before)
m = type_in("AC_Bus_dat", 0, 3, "1.5")            # Z_p — 0~1 밖
chk("0~1 밖 비율을 막나", len(win.changes), before)

print("[4] 멀쩡한 값은 통과하나")
m = type_in("AC_Line_dat", 0, 3, "0.9")           # R
chk("R 이 들어갔나", round(cur("AC_Line_dat", 0, 3), 4), 0.9)
chk("조용히 지나가나", m, [])
m = type_in("AC_Line_dat", 0, 1, "102")           # From — 있는 버스
chk("있는 버스는 통과하나", round(cur("AC_Line_dat", 0, 1)), 102)

print("[5] 짝 한계·ZIP 은 막지 않고 알려만 주나")
n0 = len(win.changes)
m = type_in("AC_gen_dat", 0, 12, "99999")         # Qmin > Qmax
chk("막지는 않나", len(win.changes) > n0, True)
chk("대화상자는 안 뜨나", m, [])
arr = SC._values(SC.apply(win.base_case, win.applied + win.changes), "AC_gen_dat")
note = RULES.warn(arr, "AC_gen_dat", 0, 12, float(arr[0, 12]))
chk("뒤집혔다고 알려 주나", "뒤집혀" in note, True)
win.grid_key = "AC_gen_dat"; win.rebuild(); pump(0.5)
win.grab().save(str(OUT/"01_한계뒤집힘.png"))

print("[6] 고친 계통이 실제로 풀리나")
win.changes = []; win.rebuild(); pump(0.3)
type_in("AC_Line_dat", 0, 3, "1.5")               # R 을 키운다
sol = app_engine.solve(SC.apply(win.base_case, win.applied + win.changes))
chk("풀리나", bool(sol.converged), True)
win.grid_key = "AC_Line_dat"; win.rebuild(); pump(0.5)
win.grab().save(str(OUT/"02_값칸_열림.png"))

print("═"*56)
print(f"  통과 {ok[0]} · 실패 {len(bad)}")
for b in bad: print(f"    ❌ {b}")
sys.exit(1 if bad else 0)
