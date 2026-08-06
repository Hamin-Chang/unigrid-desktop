# -*- coding: utf-8 -*-
"""조건을 바꿔도 보고 있던 표 탭에 머무나 (화면 없이 돌린다).

  조건을 하나 바꿀 때마다 화면을 통째로 다시 그린다. 그때 탭을 되돌리지 않으면
  **매번 첫 탭(AC 결과)으로 튄다** — 계통 데이터 탭에서 일하는 동안 계속 쫓겨난다.
  2026-08-06 사용자 신고로 확인한 결함.

      python tests/test_tab_keeps.py
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication          # noqa: E402

qapp = QApplication.instance() or QApplication([])
import app as APP                                   # noqa: E402
import scenario as SC                               # noqa: E402
import app_engine                                   # noqa: E402
from load_case import load_case                     # noqa: E402

CASE = REPO / "cases/AConly_case14.xlsx"
bad = 0


def ok(cond, what, note=""):
    global bad
    print(f"  {'✅' if cond else '🚨'} {what}" + (f"  — {note}" if note else ""))
    if not cond:
        bad += 1


def tab_now(win):
    tt = win._tabs
    return APP._tab_base(tt.tabText(tt.currentIndex()))


class Fake:
    def __init__(self, case):
        self.loaded_case = case


win = APP.Proto()
case = load_case(str(CASE))
win.thread = Fake(case)
win._last_path = str(CASE)
win._solved(app_engine.solve(case))

print("조건을 바꿔도 탭에 머무나")
ok(tab_now(win) == "AC 결과", "처음엔 AC 결과", tab_now(win))

# 사용자가 계통 데이터 탭으로 간다 (탭을 눌렀을 때와 같은 신호)
tt = win._tabs
for i in range(tt.count()):
    if tt.tabText(i).startswith("계통 데이터"):
        tt.setCurrentIndex(i)
        break
ok(win.table_tab == "계통 데이터", "탭을 누르면 기억한다", win.table_tab)

# ① 선로 끄기 — flip_row 가 rebuild 한다
win.grid_key = "AC_Line_dat"
win.rebuild()
win.flip_row(0)
ok(tab_now(win) == "계통 데이터", "선로를 꺼도 그대로", tab_now(win))

# ② 부하 슬라이더
win.scale_loads(1.20)
ok(tab_now(win) == "계통 데이터", "부하를 늘려도 그대로", tab_now(win))

# ③ 값 고치기 (운전 조건) — 되돌리기까지
win.undo_changes()
ok(tab_now(win) == "계통 데이터", "되돌려도 그대로", tab_now(win))

# ④ 계산한 뒤에도 — 탭 이름에 건수가 붙었다 떨어져도 알아본다
win.flip_row(0)
ok(tt is not win._tabs, "다시 그렸다 (탭 위젯이 새로 만들어졌다)")
ok(win._tabs.tabText(win._tabs.currentIndex()).startswith("계통 데이터"),
   "이름에 건수가 붙어도 알아본다", win._tabs.tabText(win._tabs.currentIndex()))
win._pending = win.applied + win.changes
win._pending_new = list(win.changes)
win._solved(app_engine.solve(SC.apply(win.base_case, win._pending)))
ok(tab_now(win) == "계통 데이터", "계산한 뒤에도 그대로", tab_now(win))

# ⑤ 점검으로 보내면 거기 머문다
win.go_check()
ok(tab_now(win) == "점검", "위반 건수를 누르면 점검으로", tab_now(win))
win.scale_loads(1.30)
ok(tab_now(win) == "점검", "그 뒤 조건을 바꿔도 점검에 머문다", tab_now(win))

# ⑥ 없는 탭이면 첫 탭으로 (모드가 바뀌어 표가 사라지는 경우)
win.table_tab = "있지도 않은 탭"
win.rebuild()
ok(win._tabs.currentIndex() == 0, "사라진 탭이면 첫 탭으로", tab_now(win))

print(f"\n{'✅ 전부 통과' if bad == 0 else f'🚨 {bad}건 틀림'}")
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if bad else 0)
