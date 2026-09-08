# -*- coding: utf-8 -*-
"""E 덩어리(작은 추가) 확인 — 사람이 밟는 길로 (2026-09-08).

i22 부하율 100% 넘는 선로를 표에도 표시 · i28 없는 버스를 짚어 준다 ·
i41 부하 배율을 숫자로 적는다 · i32 변환기 한계 시험 계통.
"""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "shots_E"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QLineEdit
qapp = QApplication([])
import app as APP, app_engine, checks
from load_case import load_case
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))

win = APP.Proto(); win.resize(1500, 980); win.show()
ok, bad = [0], []
def chk(name, got, want):
    if got == want: ok[0] += 1; print(f"  ✅ {name}  {got!r}")
    else: bad.append(name); print(f"  🚨 {name}: {got!r} ≠ {want!r}")
def pump(s=0.5):
    e = time.time() + s
    while time.time() < e: qapp.processEvents(); time.sleep(0.01)
def crop(n, x, y, w, h):
    win.grab().copy(QRect(x, y, w, h)).save(str(OUT / f"{n}.png")); print(f"  📷 {n}")
class Fake:
    def __init__(self, c): self.loaded_case = c; self.case = None
def open_it(f):
    case = load_case(str(REPO / "cases" / f))
    win.thread = Fake(case); win._last_path = str(REPO / "cases" / f)
    win._solved(app_engine.solve(case)); pump()
    win.numbers = True; win.numbers_auto = False; win.numbers_why = ""
    win.rebuild(); pump(0.5)

WARN = None
print("[i22] 부하율 100% 를 넘은 선로를 선로 조류 표에도 표시")
open_it("ACDC_case24_MatACDC.xlsx")
WARN = win.c["warn"]
over = win.overloaded_rows()
chk("과부하 줄을 골라낸다", sorted(over), [9, 47])
win.table_tab = "선로 조류"; win.rebuild(); pump(0.8)
tb, cols = win._res_tables["선로 조류"]
iL = cols.index("Loading[%]")
painted = {r for r in range(tb.rowCount())
           if tb.item(r, 0) is not None
           and tb.item(r, 0).foreground().color().name() == WARN}
chk("그 줄만 주황이다", sorted(painted), [9, 47])
vals = [float(tb.item(r, iL).text()) for r in sorted(over)]
chk("정말 100% 를 넘었다", all(v > 100 for v in vals), True)
print(f"     {[f'{v:.1f}%' for v in vals]}")
# 점검 탭의 「과부하 선로」와 건수가 같아야 한다
n_check = len(win.viol()["과부하 선로"][1])
chk("점검 탭과 건수가 같다", n_check, len(over))
crop("01_i22_선로조류_과부하", 292, 150, 1200, 200)

print("\n[i28] 없는 버스를 치면 짚어 준다")
win.table_tab = "AC 결과"; win.rebuild(); pump(0.6)
win.set_res_find("999"); pump(0.3)
chk("없는 번호를 말한다", "없는 번호" in win._find_label.text(), True)
chk("주황으로", win._find_label.styleSheet().split("color:")[1][:7], WARN)
crop("02_i28_없는버스", 292, 150, 1200, 120)
win.set_res_find("101"); pump(0.3)
chk("있는 번호면 안 뜬다", "없는 번호" in win._find_label.text(), False)
win.set_res_find(""); pump(0.3)

print("\n[i41] 부하 배율을 숫자로 적는다")
# ⚠️ 「⚙ 부하」는 표 드롭다운이 아니라 **계통 데이터 탭 안**의 단추다
#    (`grid_key = LOAD_KEY`). 표 목록에서 찾으면 못 찾는다.
win.table_tab = "계통 데이터"; win.grid_key = APP.LOAD_KEY
win.rebuild(); pump(0.9)
boxes = [e for e in win.centralWidget().findChildren(QLineEdit)
         if e.isVisible() and e.width() == 52]
chk("적는 칸이 있다", len(boxes) >= 1, True)
crop("03_i41_부하배율", 292, 150, 1200, 200)
# 슬라이더 범위 밖(×2.5)을 넣어 본다
win.scale_loads(2.5); pump(0.8)
chk("범위 밖도 들어간다", round(win.load_factor(), 2), 2.5)
lbl = [ch.label for ch in win.changes]
chk("바꾼 것에 남는다", any("×2.5" in s for s in lbl), True)
crop("04_i41_범위밖", 292, 150, 1200, 200)
win.scale_loads(1.0); pump(0.5)

print("\n[i32] 변환기 한계에 걸리는 시험 계통")
p = REPO / "cases" / "ACDC_case24_IClimit.xlsx"
chk("계통 파일이 있다", p.exists(), True)
if p.exists():
    open_it(p.name)
    rows = win.viol()["변환기 한계"][1]
    chk("변환기 한계에 걸린다", len(rows) > 0, True)
    print(f"     {rows}")
    win.table_tab = "점검"; win.rebuild(); pump(0.8)
    crop("05_i32_변환기한계", 292, 150, 1200, 260)

print(f"\n>>> 대조 {ok[0]}개 · 실패 {len(bad)}건" + (f" — {bad}" if bad else ""))
sys.exit(1 if bad else 0)
