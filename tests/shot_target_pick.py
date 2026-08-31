# -*- coding: utf-8 -*-
"""「비교할 버스」를 타이핑 칸에서 고르개로 바꿨다 (2026-08-30 사용자 확정).

타이핑 칸일 때 **네 가지가 조용히 어긋났다.** 12버스 계통(AC 1~6 · DC 7~12)에서 잰 것:

    ① 기본값 `3, 7, 12` 가 AC 표에서 **3 하나만** 맞았다 (7·12 는 DC 버스다)
       → 비교 화면이 선 하나로 열렸다
    ② 없는 번호(`999`)를 **아무 말 없이** 버렸다
    ③ 빈 칸 안내가 `예: 106 107`(쉼표 없음)인데 **쉼표가 없으면 통째로 버렸다**
       → 시키는 대로 치면 아무것도 안 나왔다
    ④ 같은 번호를 여러 번 받아 같은 선을 겹쳐 그렸다

**있는 것만 고르게** 하면 넷이 한꺼번에 사라진다. 여기서 그것을 지킨다.
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
                               QLabel, QLineEdit, QCheckBox,
                               QScrollArea, QPushButton)

qapp = QApplication([])
import app as APP                                            # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                            # noqa: E402
from load_case import load_case                              # noqa: E402

fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<46} {got}")
    else:
        print(f"  ❌ {label:<46} {got}  (바라던 값 {want})")
        fails.append(label)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


def pump(t=0.6):
    end = time.time() + t
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


def open_case(fn):
    """⚠️ 케이스마다 **새 창**. 한 창을 재사용하면 앞 케이스 화면이 남는다."""
    win = APP.Proto()
    win.resize(1414, 950)
    win.show()
    p = V14 / "cases_v2" / fn
    case = load_case(str(p))
    win.thread = Fake(case)
    win._last_path = str(p)
    win.base_case = case
    win._solved(app_engine.solve(case))
    win.mode = "비교"
    win.rebuild()
    pump()
    return win


print("\n[1] 고를 수 있는 것 = 계통에 실제로 있는 것 (12버스: AC 1~6 · DC 7~12)")
w = open_case("ACDC_12bus_paper_v2.xlsx")
opts = w.target_options()
print(f"    {[l for l, _ in opts]}")
check("개수", len(opts), 12)
check("AC·DC 를 갈라 보여주나", [l for l, _ in opts][:1] + [l for l, _ in opts][6:7],
      ["AC 1", "DC 7"])

print("\n[2] ① 새 파일을 열면 기본값을 그 계통 것으로 다시 잡는다")
check("기본으로 고른 것", w.target_values(), ["1", "2", "3"])
check("옛 기본값이 안 남았나", w.compare_targets == "3, 7, 12", False)

print("\n[3] ② 없는 번호는 애초에 못 고른다 — 넣어 놔도 걸러진다")
w.compare_targets = "3, 999, 7"
check("999 가 빠지나", w.target_values(), ["3", "7"])

print("\n[4] ④ 같은 번호를 여러 번 넣어도 한 번만")
w.compare_targets = "3, 3, 3"
check("중복이 접히나", w.target_values(), ["3"])

print("\n[5] ③ 사이드바에 타이핑 칸이 없다 — 문법을 틀릴 자리가 없다")
sb = next(f for f in w.findChildren(QScrollArea)
          if any(lb.text() == "현재 케이스" for lb in f.findChildren(QLabel)))
w.rebuild()
pump(0.3)
sb = next(f for f in w.findChildren(QScrollArea)
          if any(lb.text() == "현재 케이스" for lb in f.findChildren(QLabel)))
check("타이핑 칸 수", len([e for e in sb.findChildren(QLineEdit) if e.isVisible()]), 0)
notes = [lb.text() for lb in sb.findChildren(QLabel) if lb.isVisible()]
check("옛 타이핑 예시가 안 남았나", any("예:" in t for t in notes), False)

print("\n[6] 🚨 큰 계통에서도 찾을 수 있나 — 가장 큰 케이스는 버스 25,000개다")
w2 = open_case("AConly_case118_v2.xlsx")
btn = next(b for b in w2.findChildren(QPushButton)
           if b.isVisible() and b.text() == "1, 2, 3")
w2.open_target_pick(btn)
pump(0.4)
pop = w2._target_pop
boxes = pop.findChildren(QCheckBox)
check("판에 118개가 다 있나", len(boxes), 118)
pop.findChildren(QLineEdit)[0].setText("10")
pump(0.3)
# 10 · 100~110 = 12개
check("'10' 으로 줄이면", sum(1 for cb in boxes if cb.isVisible()), 12)

print("\n[7] 고른 것은 닫을 때 **한 번만** 반영된다 (그리는 도중에 판이 사라지지 않게)")
drew = []
w2.rebuild = lambda *a, **k: drew.append(1)
boxes[9].setChecked(True)          # AC 10
boxes[10].setChecked(True)         # AC 100
check("고르는 동안은 안 그리나", len(drew), 0)
pop.hide()
pump(0.3)
check("닫힐 때 한 번만 그리나", len(drew), 1)
check("고른 것이 들어갔나", "10" in w2.compare_targets, True)

print()
if fails:
    print(f"❌ 실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("DONE_TARGET_PICK — 모두 통과")
