# -*- coding: utf-8 -*-
"""부하 일괄 증감 — 앱 쪽 셈이 맞나 (화면 없이 돌린다).

  scenario.py 의 Scale 자체는 `test_scenario.py` 가 본다. 여기서 보는 것은 **앱의 셈**이다:
  슬라이더는 "원본 대비 몇 배" 를 뜻하므로, 이미 ×1.3 을 풀어 놓은 상태에서 1.5 로 옮기면
  얹히는 몫은 1.5/1.3 이어야 하고 결과는 원본의 1.5 배여야 한다 (1.3×1.5 = 1.95 가 아니다).

      python tests/test_load_scale.py
"""
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication          # noqa: E402

qapp = QApplication.instance() or QApplication([])
import app as APP                                   # noqa: E402
import scenario as SC                               # noqa: E402
from load_case import load_case                     # noqa: E402

CASE = REPO / "cases/AConly_case14.xlsx"
bad = 0


def ok(cond, what, note=""):
    global bad
    print(f"  {'✅' if cond else '🚨'} {what}" + (f"  — {note}" if note else ""))
    if not cond:
        bad += 1


def total(win, changes):
    return win.load_total(changes)


win = APP.Proto()
case = load_case(str(CASE))
win.base_case = case
win.applied = []
win.changes = []
win.t = 0
base_mw = total(win, [])

print("부하 일괄 증감 — 앱의 셈")

# 1. 아무것도 안 했으면 ×1
ok(abs(win.load_factor() - 1.0) < 1e-12, "처음엔 ×1", f"총 부하 {base_mw:,.1f} MW")

# 2. 1.3 으로 옮기면 얹히는 몫이 1.3
win.scale_loads(1.30)
sc = [c for c in win.changes if isinstance(c, SC.Scale)]
ok(len(sc) == 1 and abs(sc[0].factor - 1.30) < 1e-12, "1.3 → 얹히는 몫 1.3")
ok(abs(total(win, win.changes) - base_mw * 1.3) < 1e-6, "총 부하가 1.3배",
   f"{base_mw:,.1f} → {total(win, win.changes):,.1f} MW")

# 3. 슬라이더를 또 움직여도 **곱이 쌓이지 않는다** (아직 안 푼 상태)
win.scale_loads(1.10)
sc = [c for c in win.changes if isinstance(c, SC.Scale)]
ok(len(sc) == 1, "곱하기는 언제나 한 줄만 남는다")
ok(abs(win.load_factor() - 1.10) < 1e-12, "1.3 뒤에 1.1 → ×1.1 (×1.43 아님)")

# 4. 푼 뒤에 다시 올리면 — 이미 푼 몫을 빼고 얹는다
win.applied = list(win.changes)          # ×1.1 을 계산했다고 치고
win.changes = []
win.scale_loads(1.50)
sc = [c for c in win.changes if isinstance(c, SC.Scale)]
ok(len(sc) == 1 and abs(sc[0].factor - 1.50 / 1.10) < 1e-12,
   "이미 ×1.1 을 풀었으면 얹히는 몫은 1.5/1.1", f"factor={sc[0].factor:.6f}")
ok(abs(win.load_factor() - 1.50) < 1e-12, "원본 대비로는 ×1.5")
ok(abs(total(win, win.applied + win.changes) - base_mw * 1.5) < 1e-6,
   "총 부하도 원본의 1.5배", f"{total(win, win.applied + win.changes):,.1f} MW")

# 5. [원래대로] 는 푼 몫을 되돌린다
win.scale_loads(1.0)
ok(abs(win.load_factor() - 1.0) < 1e-12, "원래대로 → ×1")
ok(abs(total(win, win.applied + win.changes) - base_mw) < 1e-6, "총 부하가 원본으로")

# 6. 켜고 끄기와 섞여도 곱하기만 갈아 끼운다
win.applied = []
win.changes = []
win.grid_key = "AC_Line_dat"
win.changes.append(SC.toggle(case, "AC_Line_dat", 0, on=False))
win.scale_loads(1.20)
win.scale_loads(1.40)
kinds = [type(c).__name__ for c in win.changes]
ok(kinds.count("Scale") == 1 and kinds.count("Cell") == 1,
   "선로 끄기는 그대로 두고 곱하기만 바뀐다", " · ".join(kinds))
ok(SC.auto_name(case, win.changes).startswith("AC 선로"),
   "이름은 첫 줄로", SC.auto_name(case, win.changes))

# 7. 부하 표가 없는 계통이면 슬라이더를 안 만든다
ok(win.has_load(), "case14 는 부하가 있다")

# 8. 옆에 뜨는 합계에 **어느 시각인지**가 붙는다 (2026-08-06 사용자 질문)
#    곱하기는 모든 시각에 걸리는데 합계는 보고 있는 시각 하나라, 안 밝히면 오해한다.
from PySide6.QtWidgets import QLabel                # noqa: E402


def load_labels(w):
    bar = w.load_bar()
    return [bar.layout().itemAt(i).widget().text()
            for i in range(bar.layout().count())
            if isinstance(bar.layout().itemAt(i).widget(), QLabel)]


win.applied = []
win.changes = []
win.t = 0
ok(win.load_times() == 1, "case14 는 한 시각짜리")
ok(not any("H)" in s for s in load_labels(win)),
   "한 시각짜리면 시각을 안 붙인다", " · ".join(load_labels(win)))

win24 = APP.Proto()
c24 = load_case(str(REPO / "cases/ACDC_71bus_3IC_parallel.xlsx"))
win24.base_case = c24
win24.applied = []
win24.changes = []
win24.t = 0
ok(win24.load_times() == 24, "71bus 는 24시각", str(win24.load_times()))
ok(any("(1 H)" in s for s in load_labels(win24)),
   "여러 시각이면 어느 시각인지 붙인다", " · ".join(load_labels(win24)))
t0 = [s for s in load_labels(win24) if "총 부하" in s][0]
win24.t = 1
t1 = [s for s in load_labels(win24) if "총 부하" in s][0]
ok("(2 H)" in t1 and t0 != t1, "시간을 바꾸면 합계도 따라간다", f"{t0}  →  {t1}")

# 곱하기는 **모든 시각**에 걸린다 — 합계가 한 시각만 보여 준다고 곱하기까지 한 시각인 건 아니다
win24.scale_loads(1.20)
a = SC._values(c24, "AC_PLoad_dat")
b = SC._values(SC.apply(c24, win24.changes), "AC_PLoad_dat")
ok(np.allclose(np.nan_to_num(b[:, 1:]), np.nan_to_num(a[:, 1:]) * 1.2),
   "곱하기는 24시각 전부에 걸린다",
   f"1 H {np.nansum(a[:,1])/1e6:.3f}→{np.nansum(b[:,1])/1e6:.3f} · "
   f"24 H {np.nansum(a[:,24])/1e6:.3f}→{np.nansum(b[:,24])/1e6:.3f} MW")

print(f"\n{'✅ 전부 통과' if bad == 0 else f'🚨 {bad}건 틀림'}")
# Proto 가 띄워 둔 스레드가 정리되기 전에 파이썬이 내려가면 Qt 가 죽으며 134 를 뱉는다.
# 판정은 위에서 끝났으니 곧바로 나간다.
sys.stdout.flush()
os._exit(1 if bad else 0)
