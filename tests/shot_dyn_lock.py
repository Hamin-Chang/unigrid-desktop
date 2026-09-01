# -*- coding: utf-8 -*-
"""1 시각짜리 계통에서 「다이나믹」을 잠근다 (2026-09-01 전수 조사 ⑬).

계기 — 1 시각 계통에서 다이나믹으로 가면 **점 하나짜리 그래프**가 그려졌다.
x 축 눈금은 2 까지 나고(시각은 하나뿐인데), 안내는 **한 마디도 없었다**.
경고창도 안 떴다 — 왜 선이 없는지 알 길이 없다.

보여 줄 것이 없으므로 **아예 못 들어가게** 막는다. 「PV·QV 곡선」이 못 그리는
계통에서 쓰는 것과 같은 수법이다 (2026-08-31 `a46a72a`).

여기서 지키는 것
    1) 여러 시각 계통에서는 그대로 쓸 수 있나
    2) 1 시각 계통에서 단추가 잠기고 까닭이 풍선말에 있나
    3) 🚨 **까닭이 글로도 보이나** — 잠긴 단추는 안 고른 단추와 생김새가 같아
       (둘 다 `seg_off` 회색) 풍선말을 띄우기 전엔 잠긴 줄 모른다
    4) 🚨 다이나믹으로 **보는 중에** 1 시각 계통을 열면 스냅샷으로 되돌아오나
       (안 그러면 잠긴 모드에 갇혀 돌아갈 길이 없다)
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
                               QPushButton, QFrame, QLabel)

qapp = QApplication([])
import app as APP                                            # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                            # noqa: E402
from load_case import load_case                              # noqa: E402

ONE = V14 / "cases_v2/ACDC_case24_MatACDC_v2.xlsx"        # 1 시각
MANY = V14 / "cases_v2/ACDC_matacdc_case5_24h_v2.xlsx"    # 24 시각
fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<48} {got}")
    else:
        print(f"  ❌ {label:<48} {got}  (바라던 값 {want})")
        fails.append(label)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


def pump(t=0.7):
    end = time.time() + t
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


win = APP.Proto()
win.resize(1512, 950)
win.show()
pump(0.4)


def open_case(pth):
    case = load_case(str(pth))
    win.thread = Fake(case)
    win._last_path = str(pth)
    win._solved(app_engine.solve(case))
    win.rebuild()
    pump(1.5)


def mode_btn(name):
    for fr in win.findChildren(QFrame):
        if fr.objectName() == "segwrap":
            for b in fr.findChildren(QPushButton):
                if b.text() == name and b.isVisible():
                    return b
    return None


print("\n[1] 여러 시각 계통 — 그대로 쓸 수 있어야 한다")
open_case(MANY)
check("시각 수", win.sol.n_time, 24)
check("단추가 켜져 있나", mode_btn("다이나믹").isEnabled(), True)
check("막는 까닭이 없나", win.dynamic_why(), "")
win.set_mode("다이나믹")
pump(1.2)
check("다이나믹으로 갔나", win.mode, "다이나믹")

print("\n[2] 🚨 보는 중에 1 시각 계통을 열면 갇히지 않나")
open_case(ONE)
check("시각 수", win.sol.n_time, 1)
check("스냅샷으로 되돌아왔나", win.mode, "스냅샷")

print("\n[3] 잠기고 까닭이 붙나")
b = mode_btn("다이나믹")
check("단추가 잠겼나", b.isEnabled(), False)
check("풍선말에 까닭이 있나", "1시각" in b.toolTip(), True)
check("풍선말이 점 하나까지 말하나", "점 하나" in b.toolTip(), True)
said = [w.text() for w in win.findChildren(QLabel)
        if w.isVisible() and w.text().startswith("다이나믹은 여러 시각")]
check("까닭이 글로도 보이나", len(said), 1)

print("\n[4] 잠긴 채로 눌러도 안 움직이나")
b.click()
pump(0.8)
check("모드가 그대로인가", win.mode, "스냅샷")

print()
if fails:
    print(f"❌ 실패 {len(fails)}건: {fails}")
    sys.stdout.flush()
    app_engine.shutdown()
    os._exit(1)
print("DONE_DYN_LOCK — 모두 통과")
sys.stdout.flush()
app_engine.shutdown()
os._exit(0)
