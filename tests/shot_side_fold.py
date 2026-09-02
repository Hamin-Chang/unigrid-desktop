# -*- coding: utf-8 -*-
"""왼쪽 줄 접기 확인 (2026-09-02 사용자 확정, 안 (나)).

  ① 기본은 펼침 280px · 접으면 56px 띠 · 표가 그만큼 넓어지나
  ② 접힌 띠에서 「비교」로 가면 **스스로 펼쳐지나** (갇힘 막기)
  ③ 비교·곡선에서는 접기 단추가 잠기나
  ④ 띠의 「다이나믹」이 1시각 계통에서 잠기나

🚨 `win.findChildren` 은 rebuild 뒤 안 지워진 옛 위젯도 집는다 — 지금 화면
   (`centralWidget`) 아래에서만 찾는다 (2026-09-01 에 겪은 함정).
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
                               QScrollArea, QPushButton, QTableWidget)

qapp = QApplication([])
import app as APP                                            # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                            # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/ACDC_case24_MatACDC_v2.xlsx"
OUT = Path(os.environ.get("SHOT_OUT", "/tmp"))
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


def pump(t=1.0):
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
pump(1.4)


def side_w():
    """왼쪽 줄이 지금 쓰는 가로."""
    for sa in win.centralWidget().findChildren(QScrollArea):
        w = sa.widget()
        if w is not None and w.objectName() == "sidebar":
            return sa.width()
    return 0


def table_w():
    ts = [t for t in win.centralWidget().findChildren(QTableWidget) if t.isVisible()]
    return max((t.width() for t in ts), default=0)


def btn(txt):
    """보이는 단추 중 그 글자인 것."""
    return next((b for b in win.centralWidget().findChildren(QPushButton)
                 if b.isVisible() and b.text() == txt), None)


print("[1] 기본은 펼침")
check("왼쪽 줄 가로", side_w(), 280)
wide_open = table_w()
check("접기 단추가 있나", btn("◀  접기") is not None, True)

print("[2] 접으면 띠 56px · 표가 넓어지나")
btn("◀  접기").click()
pump(1.2)
check("왼쪽 줄 가로", side_w(), 56)
folded = table_w()
check("표가 넓어졌나", folded > wide_open, True)
print(f"     표 가로 {wide_open} → {folded}px  (+{folded - wide_open})")
win.grab().save(str(OUT / "side_fold.png"))

print("[3] 접힌 띠에서 「비교」로 가면 스스로 펼쳐지나 (갇힘 막기)")
btn("⇄").click()
pump(1.2)
check("비교로 갔나", win.mode, "비교")
check("스스로 펼쳤나", side_w(), 280)
check("「무엇끼리 비교」가 보이나",
      any(b.text() == "버스끼리"
          for b in win.centralWidget().findChildren(QPushButton) if b.isVisible()), True)

print("[4] 비교에서는 접기가 잠기나")
fb = btn("◀  접기")
check("접기 단추가 잠겼나", fb is not None and not fb.isEnabled(), True)
check("까닭이 풍선말에 있나", "비교" in (fb.toolTip() if fb else ""), True)

print("[5] 스냅샷으로 돌아오면 도로 접을 수 있나")
win.set_mode("스냅샷")
pump(1.2)
check("접기 단추가 살아났나", btn("◀  접기").isEnabled(), True)

print("[6] 곡선도 같은가 — 접힌 채로 가면 펼쳐진다")
btn("◀  접기").click()
pump(1.0)
check("접혔나", side_w(), 56)
cb = btn("◠")
if cb is not None and cb.isEnabled():
    cb.click()
    pump(1.4)
    check("곡선으로 갔나", win.task, "PV·QV 곡선")
    check("스스로 펼쳤나", side_w(), 280)
    win.set_task("조류계산")
    pump(1.2)
else:
    print("     (이 계통은 곡선을 못 그린다 — 띠에서도 잠겨 있다)")
    check("잠긴 채인가", cb is not None and not cb.isEnabled(), True)
    win.toggle_side()
    pump(1.0)

print("[7] 띠의 「다이나믹」 — 1시각 계통이면 잠긴다")
win.side_open = False
win.rebuild()
pump(1.2)
db = btn("◷")
why = win.dynamic_why()
check("잠금이 계통과 맞나", db is not None and db.isEnabled(), not why)

print()
if fails:
    print(f"🚨 실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("✅ 전부 통과")
