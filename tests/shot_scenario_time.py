# -*- coding: utf-8 -*-
"""시나리오 이름에 시각이 붙나 — 여러 시각짜리 계통에서만 (2026-09-08).

사용자 지시: *"모든 시나리오에 이름을 붙이라는거지 만약 시간이 1개인 계통데이터가 아니면"*
"""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "shots_scen_time"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox
qapp = QApplication([])
import app as APP, app_engine, scenario as SC
from load_case import load_case
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))

win = APP.Proto(); win.resize(1500, 980); win.show()
ok, bad = [0], []
def chk(name, got, want):
    if got == want: ok[0] += 1; print(f"  ✅ {name}  {got!r}")
    else: bad.append(name); print(f"  🚨 {name}: {got!r} ≠ {want!r}")
def pump(s=0.4):
    e = time.time() + s
    while time.time() < e: qapp.processEvents(); time.sleep(0.01)
def shot(n):
    win.grab().save(str(OUT / f"{n}.png")); print(f"  📷 {n}.png")
class Fake:
    def __init__(self, c): self.loaded_case = c; self.case = None

def open_it(f):
    case = load_case(str(REPO / "cases" / f))
    win.thread = Fake(case); win._last_path = str(REPO / "cases" / f)
    win._solved(app_engine.solve(case)); pump()
    return case

def solve_with_changes():
    """[이 조건으로 계산] 을 누른 것과 같은 길 — `_pending_new` 까지 세운다.
    안 세우면 이름을 «전체» 로 지어 이번에 얹은 것이 안 드러난다(app.py:3951)."""
    c2 = SC.apply(win.base_case, win.applied + win.changes)
    win._pending = list(win.applied + win.changes)
    win._pending_new = list(win.changes)
    win.thread = Fake(c2)
    win._solved(app_engine.solve(c2)); pump()

# ── 1) 24시각 계통 — 이름에 시각이 붙는다 ─────────────────────────────
print("[1] 24시각 계통 (ACDC_case24_MatACDC_24h)")
open_it("ACDC_case24_MatACDC_24h.xlsx")
chk("원본 이름", win.book.items[0].name, "원본 (1 H)")

win.t = 4                                        # 5 H 를 보고 있다
win.adj_typed("AC_Line_dat", 6, 13, "1")
win.adj_typed("AC_Line_dat", 6, 14, "124")
win.adj_typed("AC_Line_dat", 6, 15, "1.00961")
pump(0.2)
solve_with_changes()
chk("탭 조정 시나리오 이름", win.book.items[1].name.endswith("(5 H)"), True)
chk("계산 뒤에도 5 H 를 보고 있다", win.t, 4)

# 조정이 아닌 변경 — 선로 끄기 (사용자: 「AC조정 뿐만 아니라」)
win.t = 16                                       # 17 H
ch = SC.toggle(win.base_case, "AC_Line_dat", 2, on=False)
win.changes = [ch]
solve_with_changes()
chk("선로 끄기 시나리오 이름", win.book.items[2].name.endswith("(17 H)"), True)

# 부하 곱하기
win.t = 22                                       # 23 H
win.changes = [SC.scale_load(1.05)]
solve_with_changes()
chk("부하 곱하기 시나리오 이름", win.book.items[3].name.endswith("(23 H)"), True)

print("   목록:")
for s in win.book.items:
    print(f"     · {s.name}")
win.table_tab = "시나리오"
win.rebuild(); pump(0.8)
shot("01_24시각")

# ── 2) 한 시각짜리 계통 — 이름이 예전 그대로 ──────────────────────────
print("\n[2] 한 시각짜리 계통 (ACDC_case24_MatACDC)")
open_it("ACDC_case24_MatACDC.xlsx")
chk("원본 이름에 시각이 없다", win.book.items[0].name, "원본")
win.changes = [SC.toggle(win.base_case, "AC_Line_dat", 2, on=False)]
solve_with_changes()
chk("바꾼 시나리오 이름에도 시각이 없다", "H)" in win.book.items[1].name, False)
print("   목록:")
for s in win.book.items:
    print(f"     · {s.name}")
win.table_tab = "시나리오"
win.rebuild(); pump(0.8)
shot("02_한시각")

print(f"\n>>> 대조 {ok[0]}개 · 실패 {len(bad)}건")
sys.exit(1 if bad else 0)
