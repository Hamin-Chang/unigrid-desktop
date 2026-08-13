# -*- coding: utf-8 -*-
"""여덟 표 전부에서 첫 열 고정이 제대로 되나 (2026-08-13).

사용자: *"계통데이터에서 가로 스크롤을 할 때 가장 첫 열(버스 번호나 선로 번호)을 고정시켜줘"*

첫 번호 열을 **따로 만든 표**로 왼쪽에 세우면서 화면 열 번호가 한 칸 밀렸다
(`_grid_off = -1`). 표마다 스위치 유무가 달라 왼쪽이 한 열일 수도 두 열일 수도 있다.
여기서 보는 것 — ① 왼쪽 = (상태 +) 첫 머리글 ② 오른쪽엔 그 머리글이 없다
③ off 가 -1 이다 ④ **고칠 수 있는 열이 오른쪽에서 제 이름을 갖고 있나**(④가 어긋나면
엉뚱한 열이 고쳐진다 — 조용히 틀린 값이 들어가는 가장 위험한 결함이다).

    python tests/test_frozen_col.py
"""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
from PySide6.QtWidgets import QApplication, QMessageBox
qapp = QApplication.instance() or QApplication([])
import app as APP
for n in ("warning", "information", "critical"):
    setattr(QMessageBox, n, staticmethod(lambda *a, **k: None))
import scenario as SC, app_engine
from load_case import load_case
class Fake:
    def __init__(self, case): self.loaded_case = case; self.case = None
CASE = REPO / "cases/ACDC_71bus_3IC_parallel.xlsx"   # AC/DC 혼합 — 표가 다 있다
win = APP.Proto()
case = load_case(str(CASE))
win.thread = Fake(case); win._last_path = str(CASE)
win._solved(app_engine.solve(case))
bad = 0
print(f"{'표':16s} {'스위치':4s} {'왼쪽(고정)':28s} {'off':>4s}  {'오른쪽 첫 머리글':20s} 판정")
for key, label in APP.GRID_TABLES:
    arr = SC._values(win.base_case, key)
    if not (arr.size and arr.ndim == 2):
        continue
    win.grid_key = key
    box = win.grid_table_widget()
    tb, fz, off = win._grid_tb, win._grid_frozen, win._grid_off
    sw = "O" if SC.SWITCHES.get(key) else "X"
    if fz is None:
        print(f"{key:16s} {sw:4s} {'(고정 없음 — 열이 하나뿐)':28s}")
        continue
    fh = [fz.horizontalHeaderItem(i).text() for i in range(fz.columnCount())]
    rh = [tb.horizontalHeaderItem(i).text() for i in range(tb.columnCount())]
    heads = APP.GRID_HEADERS.get(key, [])
    # ① 왼쪽 = (상태) + 첫 머리글  ② 오른쪽에 그 머리글이 없다  ③ off = -1
    ok = (fh[-1] == heads[0] and heads[0] not in rh and off == -1
          and (fh[0] == "상태") == (sw == "O"))
    # ④ 고칠 수 있는 열이 오른쪽에서 제 이름을 갖고 있나
    for j in sorted(APP.GRID_EDITABLE.get(key, set())):
        if j < len(heads) and 0 <= j + off < len(rh):
            ok = ok and rh[j + off] == heads[j]
    bad += 0 if ok else 1
    print(f"{key:16s} {sw:4s} {str(fh):28s} {off:>4d}  {rh[0][:20]:20s} {'✅' if ok else '🚨'}")
print(f"\n{'✅ 여덟 표 전부 통과' if bad == 0 else f'🚨 {bad}개 표에서 어긋남'}")
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if bad else 0)
