# -*- coding: utf-8 -*-
"""시나리오 목록을 **실제로 돌려서** 찍는다.

  원본 → 선로 하나 끔 → 선로 둘 끔 → 안 풀리는 조건(107–108) 까지 담고,
  마지막에 원본으로 되돌아가 본다.
"""
import os
import sys
import time
from pathlib import Path

REPO = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/unigrid-desktop")
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication      # noqa: E402

qapp = QApplication([])
import app as APP                               # noqa: E402

# 자동 실행이라 대화상자를 눌러 줄 사람이 없다 — 뜬 것만 적고 넘어간다.
from PySide6.QtWidgets import QMessageBox        # noqa: E402
_seen = []
QMessageBox.warning = staticmethod(
    lambda *a, **k: _seen.append(("경고", a[1] if len(a) > 1 else "")))
QMessageBox.information = staticmethod(
    lambda *a, **k: _seen.append(("알림", a[1] if len(a) > 1 else "")))
QMessageBox.critical = staticmethod(
    lambda *a, **k: _seen.append(("실패", a[1] if len(a) > 1 else "")))
import scenario as SC                           # noqa: E402
import app_engine                               # noqa: E402
from load_case import load_case                 # noqa: E402

CASE = REPO / "cases/ACDC_case24_MatACDC.xlsx"
win = APP.Proto()
win.resize(1500, 980)
win.show()


def pump(sec=0.35):
    end = time.time() + sec
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


def shot(name):
    pump()
    p = OUT / f"목록_{name}.png"
    win.grab().save(str(p))
    print(f"  찍음: {p.name}")


class Fake:
    def __init__(self, case):
        self.loaded_case = case


case = load_case(str(CASE))
win.thread = Fake(case)
win._last_path = str(CASE)
win._solved(app_engine.solve(case))


def row_of(a, b):
    arr = SC._values(case, "AC_Line_dat")
    return [i for i, r in enumerate(arr) if (int(r[1]), int(r[2])) == (a, b)][0]


def press_run():
    """[이 조건으로 계산] 을 누른 것과 같은 경로 (스레드만 뺐다)."""
    win._pending = win.applied + win.changes
    try:
        sol = app_engine.solve(SC.apply(win.base_case, win._pending))
    except Exception as exc:
        win._solve_failed(str(exc))
        return False
    win.thread = Fake(case)
    win._solved(sol)
    win.rebuild()
    return True


# 시나리오 ①  선로 하나
win.flip_row(row_of(106, 110)); press_run()
# 시나리오 ②  거기에 하나 더 (앞의 조건 위에 얹는다)
win.flip_row(row_of(102, 104)); press_run()
# 시나리오 ③  안 풀리는 조건 — 원본으로 돌아가서 107–108 만
win.show_scenario(win.book.base())
win.flip_row(row_of(107, 108))
ok = press_run()

print("담긴 시나리오:")
for s in win.book.items:
    print(f"   {s.name:<28} {s.summary:<8} 전압최저 {s.vmin():.4f}")
shot("1_시나리오_넷")

# 원본으로 되돌아가기 — 다시 계산하지 않는다
t0 = time.perf_counter()
win.show_scenario(win.book.base())
print(f"원본으로 되돌아가는 데 {1000 * (time.perf_counter() - t0):.0f} ms "
      f"(계산 안 함) · 지금 반복 {win.sol.iters}회")
shot("2_원본으로_되돌아감")

print("뜬 대화상자:", [f"{k}: {v}" for k, v in _seen])
app_engine.shutdown()
print("DONE_BOOK")
