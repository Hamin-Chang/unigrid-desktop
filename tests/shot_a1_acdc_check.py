# -*- coding: utf-8 -*-
"""「점검」 탭이 **AC/DC 케이스의** A1 결과를 읽나 (2026-08-18, §7 6단계 뒤처리).

🚨 왜 있나 — 08-17 에 A1 을 AC/DC 로 넓히고 결과표 열 규약을 11열로 맞춰 뒀지만
   **「점검」 탭이 그것을 AC 단독과 같은 코드로 읽는지는 확인하지 않았다**(그날 저널의
   「다음 할 일」 3번). 기존 화면 시험(`shot_a1_*`)은 전부 **AC 단독** 케이스를 쓴다.

무엇을 보나 — AC/DC 케이스 넷을 열어 ① 카드가 그려지나 ② 방식 이름이 맞나
(탭/위상/SVC) ③ 단위가 방식별로 맞나 ④ 계단 줄이 「계단 자리」로 나오나.
"""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidget
qapp = QApplication([])
import app as APP
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine
from load_case import load_case

CASES = [("ACDC_case24_tapctrl", "탭"), ("ACDC_case24_phasectrl", "위상"),
         ("ACDC_case24_svc", "SVC"), ("ACDC_case24_tapstep", "탭")]

class Fake:
    def __init__(s, c): s.loaded_case = c; s.case = None

def pump(s=0.3):
    e = time.time() + s
    while time.time() < e: qapp.processEvents(); time.sleep(0.01)

win = APP.Proto(); win.resize(1500, 950); win.show()
fails = []
for name, want_kind in CASES:
    case = load_case(str(REPO / "cases" / f"{name}.xlsx"))
    win.thread = Fake(case); win._last_path = name
    win._solved(app_engine.solve(case)); pump()
    tw = win._tabs
    for i in range(tw.count()):
        if tw.tabText(i).startswith("점검"): tw.setCurrentIndex(i); pump(0.25)
    card = None
    for t in win.findChildren(QTableWidget):
        hh = [t.horizontalHeaderItem(i).text() if t.horizontalHeaderItem(i) else ""
              for i in range(t.columnCount())]
        if "정해진 값" in hh: card = t
    if card is None:
        print(f"🚨 {name}: 점검 카드가 **없다** — AC/DC 결과가 화면까지 못 갔다")
        fails.append(name); continue
    vals = [card.item(0, c).text() for c in range(card.columnCount())]
    ok = vals[0] == want_kind
    unit_ok = ("MW" in vals[3]) if want_kind == "위상" else ("pu" in vals[3])
    step_ok = ("계단" in vals[-1]) if name.endswith("tapstep") else True
    good = ok and unit_ok and step_ok
    print(f"{'✅' if good else '🚨'} {name:24s} {vals}")
    if not good: fails.append(name)
    if name.endswith("tapstep"):
        win.grab().save(str(Path(__file__).resolve().parent / "A1_ACDC_점검탭.png"))

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush(); app_engine.shutdown(); os._exit(1 if fails else 0)
