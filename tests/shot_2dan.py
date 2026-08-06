# -*- coding: utf-8 -*-
"""2단계 화면을 **실제로 돌려서** 찍는다 — 시안이 아니라 진짜 앱.

  1) 케이스를 연다            → 찍는다 (계통 데이터 탭)
  2) 선로 두 개를 끈다        → 찍는다 (알림줄 + 꺼진 표시)
  3) [이 조건으로 계산] 을 누른다 → 찍는다 (시나리오로 담긴 뒤)
"""
import os
import sys
import time
from pathlib import Path

REPO = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/unigrid-desktop")
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication          # noqa: E402
from PySide6.QtCore import QTimer                   # noqa: E402

qapp = QApplication([])
import app as APP                                   # noqa: E402
import scenario as SC                               # noqa: E402
from load_case import load_case                     # noqa: E402
import app_engine                                   # noqa: E402

CASE = REPO / "cases/ACDC_case24_MatACDC.xlsx"

win = APP.Proto()
win.resize(1500, 950)
win.show()


def pump(seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


def shot(name):
    pump(0.4)
    p = OUT / f"실행_{name}.png"
    win.grab().save(str(p))
    print(f"  찍음: {p.name}")


# ── 1) 케이스 열기 (스레드 대신 곧바로 — 화면 흐름은 같다) ───────────
case = load_case(str(CASE))
sol = app_engine.solve(case)


class FakeThread:
    loaded_case = case


win.thread = FakeThread()
win._last_path = str(CASE)
win._solved(sol)
win.grid_key = "AC_Line_dat"
win.rebuild()
# 아래 탭에서 '계통 데이터' 를 고른다
tabs = getattr(win, "_tabs", None)
if tabs is not None:
    for i in range(tabs.count()):
        if tabs.tabText(i).startswith("계통 데이터"):
            tabs.setCurrentIndex(i)
print(f"원본: 반복 {sol.iters}회")
shot("1_계통데이터탭")

# ── 2) 선로 두 개 끄기 (계산은 안 돌아야 한다) ──────────────────────
rows = [i for i, r in enumerate(SC._values(case, "AC_Line_dat"))
        if (int(r[1]), int(r[2])) in {(106, 110), (102, 104)}]
for r in rows:
    win.flip_row(r)
tabs = getattr(win, "_tabs", None)
if tabs is not None:
    for i in range(tabs.count()):
        if tabs.tabText(i).startswith("계통 데이터"):
            tabs.setCurrentIndex(i)
print(f"바꾼 것 {len(win.changes)}건 · 아직 계산 안 함 (반복은 그대로 {win.sol.iters}회)")
shot("2_조건을_바꾼_뒤")

# ── 3) 계산 버튼 (스레드 없이 같은 경로를 밟는다) ────────────────────
win._pending = list(win.changes)
sol2 = app_engine.solve(SC.apply(win.base_case, win.changes))
win.thread = FakeThread()
win._solved(sol2)
win.rebuild()
tabs = getattr(win, "_tabs", None)
if tabs is not None:
    for i in range(tabs.count()):
        if tabs.tabText(i).startswith("계통 데이터"):
            tabs.setCurrentIndex(i)
print(f"계산 뒤: 반복 {sol2.iters}회 · 시나리오 {[s.name for s in win.book.items]}")
shot("3_계산한_뒤")

app_engine.shutdown()
print("DONE_SHOT")
