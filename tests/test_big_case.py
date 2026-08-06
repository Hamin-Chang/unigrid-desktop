# -*- coding: utf-8 -*-
"""큰 계통은 그래프를 접은 채로 열리나 (2026-08-06 사용자 확정).

  버스가 수천이면 점이 겹쳐 빨간 덩어리가 되어 읽을 수가 없다 ⇒ 접은 채로 연다.
  보고 싶으면 [그래프 펼치기]. **사용자가 펼쳐 놓았으면 다시 접지 않는다** —
  조건을 바꿀 때마다 도로 접히면 못 쓴다.

      python tests/test_big_case.py
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/Phase A_Balance/newest/v14")
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QLabel     # noqa: E402

qapp = QApplication.instance() or QApplication([])
import app as APP                                                   # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import scenario as SC                                               # noqa: E402
import app_engine                                                   # noqa: E402
from load_case import load_case                                     # noqa: E402

bad = 0


def ok(cond, what, note=""):
    global bad
    print(f"  {'✅' if cond else '🚨'} {what}" + (f"  — {note}" if note else ""))
    if not cond:
        bad += 1


class Fake:
    def __init__(self, case):
        self.loaded_case = case


def open_case(win, path):
    case = load_case(str(path))
    sol = app_engine.solve(case)
    win.thread = Fake(case)
    win._last_path = str(path)
    win._solved(sol)
    return sol


win = APP.Proto()
print(f"기준 {APP.BIG_BUSES:,}버스")

# ── 1. 작은 계통은 그대로 펼쳐 둔다 ────────────────────────────────────
print("\n1) 열 때")
sol = open_case(win, REPO / "cases/AConly_case14.xlsx")
ok(not win.numbers, "14버스 — 펼친 채로 열린다")
ok(not win.numbers_auto, "자동으로 접힌 것이 아니다")

big = V14 / "AConly_case6495rte.xlsx"
if not big.is_file():
    print("  ⏭  큰 케이스가 없어 나머지는 건너뛴다")
    sys.exit(0)

sol = open_case(win, big)
n = int(sol.AC.shape[0])
ok(win.numbers and win.numbers_auto, f"{n:,}버스 — 접힌 채로 열린다")

# ── 2. 접혔을 때 왜 접혔는지 말해 주나 ─────────────────────────────────
print("\n2) 화면에 뜨는 말")


def note_text(w):
    mid = w.center()
    for lb in mid.findChildren(QLabel):
        if "그래프를 접" in lb.text() or "접어 두었" in lb.text():
            return lb.text()
    return ""


msg = note_text(win)
ok(f"{n:,}" in msg, "버스 수를 밝힌다", msg)
ok("읽기 어렵" in msg, "왜 접었는지 말한다 (읽기 어려워서)")
ok("빠" not in msg, "빨라진다고 말하지 않는다 — 실측 0.86~1.49배라 사실이 아니다")
ok("엑셀" in msg, "값을 어디서 보는지 알려 준다")

# ── 3. 펼치면 펼쳐지고, 다시 안 접힌다 ─────────────────────────────────
print("\n3) 펼친 뒤")
win.set_numbers(False)
ok(not win.numbers, "[그래프 펼치기] 를 누르면 펼쳐진다")
ok(not win.numbers_auto, "이제 '자동' 이 아니다 (사용자가 골랐다)")

win.grid_key = "AC_Line_dat"
win.rebuild()
win.flip_row(0)
win._pending = win.applied + win.changes
win._pending_new = list(win.changes)
win._solved(app_engine.solve(SC.apply(win.base_case, win._pending)))
ok(not win.numbers, "조건을 바꿔 다시 풀어도 펼친 채 그대로")

# ── 4. 다른 큰 케이스를 새로 열면 다시 접는다 ──────────────────────────
print("\n4) 새 케이스를 열면")
other = V14 / "AConly_case1888rte.xlsx"
if other.is_file():
    open_case(win, other)
    ok(win.numbers and win.numbers_auto, "1,888버스를 새로 열면 다시 접힌다")
    open_case(win, REPO / "cases/AConly_case14.xlsx")
    ok(not win.numbers, "작은 케이스를 열면 다시 펼쳐진다")

print(f"\n{'✅ 전부 통과' if bad == 0 else f'🚨 {bad}건 틀림'}")
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if bad else 0)
