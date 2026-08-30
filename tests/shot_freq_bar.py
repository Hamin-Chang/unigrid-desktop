# -*- coding: utf-8 -*-
"""시스템 주파수를 사이드바 카드에서 맨 아래 상태바 한 줄로 옮겼다 (2026-08-30 사용자 확정).

사이드바는 *한 번 정하면 한동안 안 바꾸는 것*만 담는 자리인데, 주파수는 고르는 게
아니라 **읽는 값**이라 결과 옆으로 내려왔다. ①시간·버스 고르개(맨 위 줄) ·
②볼 항목(비교 탭 구석 단추) 에 이은 세 번째 이사다.

보는 것
    1) 데드밴드 **밖**이면 `droop 동작 중` 이라 하나
    2) 데드밴드 **안**이면 `droop 멈춤` 이라 하나
    3) 데드밴드가 **없으면**(0) `droop 동작` 이라 하나 — 늘 동작하므로 「중」이 없다
    4) 🚨 **다이나믹·비교에서는 아예 안 보이나** — 값이 `self.t`(지금 보는 시각)에
       묶여 있는데 그 두 모드엔 「지금 시각」이라는 것이 없다
    5) 사이드바에 옛 카드가 **안 남았나**

⚠️ 케이스마다 **창을 새로 만든다.** 한 창을 재사용하며 케이스를 갈아 열면 앞 케이스
   화면이 그대로 남아, 멀쩡한 앱을 결함으로 오인하게 된다 (2026-08-30에 실제로 겪음).
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
                               QLabel, QFrame)

qapp = QApplication([])
import app as APP                                            # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                            # noqa: E402
from load_case import load_case                              # noqa: E402

fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<44} {got}")
    else:
        print(f"  ❌ {label:<44} {got}  (바라던 값 {want})")
        fails.append(label)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


def open_fresh(fn, mode="스냅샷"):
    """케이스 하나를 **새 창**에 열고 (상태바 글자, 사이드바에 카드 남았나) 를 준다."""
    win = APP.Proto()
    win.resize(1414, 950)
    win.show()
    path = V14 / "cases_v2" / fn
    case = load_case(str(path))
    win.thread = Fake(case)
    win._last_path = str(path)
    win.base_case = case
    win._solved(app_engine.solve(case))
    if mode != "스냅샷":
        win.mode = mode
    win.rebuild()
    end = time.time() + 0.6
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)
    # ⚠️ 창에 `statusbar` 가 **둘**이다 — 시작 화면용과 결과용. 결과용은 나중에
    #    만들어지므로 **마지막 것**을 잡는다. 첫 것을 잡으면 늘 시작 화면 글자가 나온다.
    bars = [f for f in win.findChildren(QFrame) if f.objectName() == "statusbar"]
    bar = bars[-1] if bars else None
    txts = [lb.text() for lb in bar.findChildren(QLabel)] if bar else []
    card = any(lb.text() == "시스템 주파수" for lb in win.findChildren(QLabel))
    return win, txts, card


def freq_of(txts):
    """상태바 글자에서 「주파수」 바로 뒤 값. 없으면 None."""
    return txts[txts.index("주파수") + 1] if "주파수" in txts else None


print("\n[1] 데드밴드 밖 — droop 이 동작 중이다 (12버스, 기준 50 Hz)")
w1, t1, c1 = open_fresh("ACDC_12bus_paper_v2.xlsx")
print(f"    상태바: {t1}")
check("데드밴드 밖 문구", (freq_of(t1) or "").endswith("droop 동작 중"), True)
check("사이드바에 옛 카드", c1, False)

print("\n[2] 데드밴드 안 — droop 이 멈춰 있다 (CIGRE MV, 기준 60 Hz)")
w2, t2, c2 = open_fresh("ACDC_CIGRE_MV_v2.xlsx")
print(f"    주파수 칸: {freq_of(t2)}")
check("데드밴드 안 문구", (freq_of(t2) or "").endswith("droop 멈춤"), True)

print("\n[3] 데드밴드가 없다 — 늘 동작하므로 「중」을 안 붙인다 (71버스)")
w3, t3, c3 = open_fresh("ACDC_71bus_v2.xlsx")
print(f"    주파수 칸: {freq_of(t3)}")
check("데드밴드 없음 문구", (freq_of(t3) or "").endswith("droop 동작"), True)
check("「중」이 안 붙었나", (freq_of(t3) or "").endswith("동작 중"), False)

print("\n[4] 🚨 다이나믹에는 「지금 시각」이 없으니 주파수도 없다")
w4, t4, c4 = open_fresh("ACDC_12bus_paper_24h_v2.xlsx", mode="다이나믹")
print(f"    상태바: {t4}")
check("주파수 칸이 없나", freq_of(t4), None)
check("나머지는 그대로 있나", "수렴" in t4 and "반복" in t4, True)

print("\n[5] 비교 모드도 마찬가지")
w5, t5, c5 = open_fresh("ACDC_12bus_paper_v2.xlsx", mode="비교")
check("주파수 칸이 없나", freq_of(t5), None)

print()
if fails:
    print(f"❌ 실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("DONE_FREQ_BAR — 모두 통과")
