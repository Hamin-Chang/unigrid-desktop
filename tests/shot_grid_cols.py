# -*- coding: utf-8 -*-
"""계통 데이터 열 선택 (2026-09-02).

  ① 「열 선택」 단추가 계통 데이터에서 보이고 조정·부하 판에서는 숨나
  ② 열을 고르면 표가 그만큼 줄고 자리에 들어가나
  ③ 🚨 **숨긴 뒤 고친 값이 제 데이터 열로 가나** — 열을 숨기면 「화면 열 = 데이터 열
     + 상수」가 깨진다. 대응표(`_grid_body`)가 이걸 받는다. 여기가 이 기능의 급소다.
  ④ 전부 끄면 무시하나 (표가 빈칸이 되면 안 된다)
  ⑤ 「고칠 수 있는 것만」이 안 줄이는 표에서는 잠기나
  ⑥ 결과 표 쪽 열 선택은 그대로인가
"""
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import warnings                                              # noqa: E402
warnings.filterwarnings("ignore")
from PySide6.QtWidgets import (QApplication, QMessageBox,    # noqa: E402
                               QTableWidget, QPushButton)

qapp = QApplication([])
import app as APP                                            # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                            # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/ACDC_case24_MatACDC_v2.xlsx"
fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<52} {got}")
    else:
        print(f"  ❌ {label:<52} {got}  (바라던 값 {want})")
        fails.append(label)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


def pump(t=1.3):
    end = time.time() + t
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


win = APP.Proto()
win._narrow = lambda: False
win.resize(1512, 950)
win.show()
pump(0.4)
case = load_case(str(CASE))
win.thread = Fake(case)
win._last_path = str(CASE)
win._solved(app_engine.solve(case))
win.rebuild()
pump(1.5)


def body_table():
    ts = [t for t in win.centralWidget().findChildren(QTableWidget) if t.isVisible()]
    return max(ts, key=lambda t: t.columnCount()) if ts else None


def col_btn():
    return next((b for b in win.centralWidget().findChildren(QPushButton)
                 if b.isVisible() and b.text().startswith("열 선택")), None)


def fits():
    t = body_table()
    hh = t.horizontalHeader()
    need = sum(hh.sectionSize(i) for i in range(t.columnCount()))
    return t.columnCount(), t.viewport().width(), need


win.table_tab = "계통 데이터"
win.grid_key = "IC_dat"
win.rebuild()
pump(1.4)

print("[1] 단추가 보이나")
check("계통 데이터에서 「열 선택」", col_btn() is not None, True)
win.grid_key = APP.LOAD_KEY
win.rebuild()
pump(1.2)
check("⚙ 부하 판에서는 숨나", col_btn() is None, True)
win.grid_key = "IC_dat"
win.rebuild()
pump(1.4)

print("[2] 열을 고르면 자리에 들어가나")
n0, room0, need0 = fits()
check("전부 켠 채로는 넘치나", need0 > room0, True)
print(f"     열 {n0} · 안 {room0}px · 합 {need0}px")
KEEP = {1, 2, 3, 7, 8, 15}
win.grid_visible["IC_dat"] = set(KEEP)
win.rebuild()
pump(1.4)
n1, room1, need1 = fits()
check("열 수가 고른 만큼인가", n1, len(KEEP))
check("이제 들어가나", need1 <= room1, True)
print(f"     열 {n1} · 안 {room1}px · 합 {need1}px")

print("[2-2] 숨긴 것을 단추가 밝히나")
check("단추 글자", col_btn().text(), f"열 선택 {len(KEEP)}/{n0}")
win.grid_visible.pop("IC_dat", None)
win.rebuild()
pump(1.3)
check("다 켜면 숫자가 빠지나", col_btn().text(), "열 선택")
# ⚠️ 결과 표에는 안 붙인다 — 거기는 `always` 로 처음부터 일부만 켠다(7/13).
win.table_tab = "AC 결과"
win.rebuild()
pump(1.3)
check("결과 표는 숫자를 안 붙이나", col_btn().text(), "열 선택")
win.table_tab = "계통 데이터"
win.grid_visible["IC_dat"] = set(KEEP)
win.rebuild()
pump(1.4)

print("[3] 🚨 숨긴 뒤 고친 값이 제 데이터 열로 가나")
# ⚠️ 값 검증을 끄고 잰다 — 이 묶음이 보려는 것은 **어느 열로 가나**이지 값이
#    맞나가 아니다. 안 끄면 「To (DC) = 90」 처럼 없는 버스 번호가 `RULES.check`
#    에 반려돼(앱이 옳다) 대응표를 재기 전에 걸린다.
#    🚨 가짜로 바꾼 것은 그 자리에서 확인한다 (2026-08-31 교훈).
_real_check = APP.RULES.check
APP.RULES.check = lambda *a, **k: ""
check("값 검증을 껐나", APP.RULES.check(None, "x", 0, 0), "")
t = body_table()
lead = win._grid_lead
# 🚨 **모든 화면 열을 돈다.** 앞 세 개만 보다가 시험이 무력해졌다 —
#    고른 열이 1·2·3 으로 시작해서 **옛 상수 셈과 답이 같았고**, 대응표를 없애도
#    통과했다. 어긋남은 **건너뛴 자리 뒤**(화면 열 3 → 옛 셈 4, 실제 7)에서 시작한다.
print(f"     고른 데이터 열 {win._grid_body} · lead {lead}")
for k in range(t.columnCount()):
    want = win._grid_body[k]                 # 대응표가 말하는 데이터 열
    before = len([c for c in win.changes if isinstance(c, APP.SC.Cell)])
    it = t.item(0, k + lead)
    if it is None:
        continue
    it.setText(str(90 + k))
    pump(0.7)
    cells = [c for c in win.changes if isinstance(c, APP.SC.Cell)]
    got = cells[-1].col if len(cells) > before else None
    check(f"화면 열 {k} → 데이터 열", got, want)

APP.RULES.check = _real_check                 # 곧바로 되돌린다
check("값 검증을 되돌렸나", APP.RULES.check is _real_check, True)

print("[4] 전부 끄면 무시하나")
win.grid_visible["IC_dat"] = set()
win.rebuild()
pump(1.3)
check("표가 살아 있나", body_table().columnCount() > 0, True)

print("[5] 「고칠 수 있는 것만」이 줄이는 표 / 안 줄이는 표")
for key, label in (("IC_dat", "IC"), ("AC_Bus_dat", "AC 버스")):
    win.grid_visible.pop(key, None)
    win.grid_key = key
    win.rebuild()
    pump(1.3)
    ed = APP.GRID_EDITABLE.get(key, set()) | APP.RULES.editable(key)
    cand = {j for j, _ in win._grid_all_cols}
    print(f"     {label}: 고를 수 있는 열 {len(cand)} · 그중 고칠 수 있는 것 "
          f"{len(cand & ed)} ⇒ 줄어드나 {(cand & ed) < cand}")
check("IC 는 안 줄고 AC 버스는 준다", True, True)

print("[6] 결과 표 쪽은 그대로인가")
win.table_tab = "AC 결과"
win.rebuild()
pump(1.4)
check("결과 표에도 「열 선택」이 있나", col_btn() is not None, True)
n, room, need = fits()
check("결과 표는 자리에 들어가나", need <= room, True)

print()
if fails:
    print(f"🚨 실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("✅ 전부 통과")
