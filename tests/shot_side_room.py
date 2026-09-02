# -*- coding: utf-8 -*-
"""펼친 사이드바가 세로 자리에 들어가나 (2026-09-02, D 안 (나)).

  ① 「무엇을 할까」가 「보기」와 같은 **가로** 배치인가
  ② 비교 모드가 창 950px 에서 안 넘치나 — 여기가 넘치면 맨 아래
     「이 비교 그림 저장」이 스크롤해야 보인다(고치기 전 +5px 넘침)
  ③ 다른 모드도 들어가나

📌 창을 더 줄이면(900px 아래) 비교는 여전히 넘친다 — (나)는 케이스 카드를 안 건드리는
   안이라 거기까지는 못 간다. 그건 사용자가 알고 고른 것이다.
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
                               QScrollArea, QFrame, QPushButton, QHBoxLayout)

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
        print(f"  ✅ {label:<50} {got}")
    else:
        print(f"  ❌ {label:<50} {got}  (바라던 값 {want})")
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


def side():
    for sa in win.centralWidget().findChildren(QScrollArea):
        w = sa.widget()
        if w is not None and w.objectName() == "sidebar":
            return sa, w
    return None, None


print("[1] 「무엇을 할까」가 가로인가")
_, sb = side()
seg = None
for f in sb.findChildren(QFrame, "segwrap"):
    if [b.text() for b in f.findChildren(QPushButton)] == list(APP.TASKS):
        seg = f
check("찾았나", seg is not None, True)
check("가로 배치인가", isinstance(seg.layout(), QHBoxLayout), True)
# 「보기」와 같은 꼴인지 — 높이로 잰다(세로 2 단이면 훨씬 크다)
view = None
for f in sb.findChildren(QFrame, "segwrap"):
    if [b.text() for b in f.findChildren(QPushButton)] == list(APP.MODES):
        view = f
if view is not None:
    check("「보기」와 높이가 같은가", seg.height() == view.height(), True)

print("[2] 비교 모드가 950px 창에 들어가나")
win.mode = "비교"
win.rebuild()
pump(1.5)
sa, sb = side()
room, used = sa.height(), sb.sizeHint().height()
check("안 넘치나", used <= room, True)
print(f"     자리 {room}px · 요구 {used}px · 남음 {room - used}")
# 맨 아래 단추가 스크롤 없이 닿는 자리인가
save = next((b for b in sb.findChildren(QPushButton)
             if b.text().startswith("이 비교 그림 저장")), None)
check("저장 단추가 있나", save is not None, True)
if save is not None:
    bottom = save.mapTo(sb, save.rect().bottomLeft()).y()
    check("저장 단추가 자리 안에 드나", bottom <= room, True)

print("[3] 다른 모드도 들어가나")
for mode in ("스냅샷",):
    win.mode = mode
    win.rebuild()
    pump(1.3)
    sa, sb = side()
    check(f"{mode}", sb.sizeHint().height() <= sa.height(), True)
win.mode = "스냅샷"
win.task = "PV·QV 곡선"
win.rebuild()
pump(1.4)
sa, sb = side()
check("PV·QV 곡선", sb.sizeHint().height() <= sa.height(), True)

print()
if fails:
    print(f"🚨 실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("✅ 전부 통과")
