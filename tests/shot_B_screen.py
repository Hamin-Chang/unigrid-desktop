# -*- coding: utf-8 -*-
"""B 덩어리(화면 정리 11건) 확인 — 사람이 밟는 길로 (2026-09-08)."""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "shots_B"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QPushButton
qapp = QApplication([])
import app as APP, app_engine, scenario as SC
from load_case import load_case
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))

win = APP.Proto(); win.resize(1500, 980); win.show()
ok, bad = [0], []
def chk(name, got, want):
    if got == want: ok[0] += 1; print(f"  ✅ {name}  {got!r}")
    else: bad.append(name); print(f"  🚨 {name}: {got!r} ≠ {want!r}")
def pump(s=0.5):
    e = time.time() + s
    while time.time() < e: qapp.processEvents(); time.sleep(0.01)
def shot(n): win.grab().save(str(OUT / f"{n}.png")); print(f"  📷 {n}.png")
class Fake:
    def __init__(self, c): self.loaded_case = c; self.case = None
def open_it(f):
    case = load_case(str(REPO / "cases" / f))
    win.thread = Fake(case); win._last_path = str(REPO / "cases" / f)
    win._solved(app_engine.solve(case)); pump()

def texts(w):
    return [b.text() for b in w.findChildren(QPushButton)]

print("[i05·i07] 불러오기 — 형식 고르는 창")
dlg = APP.OpenDialog(win, win.c)
names = [t.split("\n")[0] for t in texts(dlg)]
print(f"    단추 {names}")
chk("네 형식이 다 있다", sum(1 for n in names if "UNIGRID" in n or "MATPOWER" in n
                            or "PSS/E" in n or "MatACDC" in n), 4)
dlg.grab().save(str(OUT / "07_형식고르는창.png")); print("  📷 07_형식고르는창.png")
dlg.deleteLater()

open_it("ACDC_case24_MatACDC_24h.xlsx")
print("\n[i07] 케이스 카드에 「바꾸기」가 없다")
chk("바꾸기 없음", "바꾸기" in texts(win.centralWidget()), False)

print("\n[i10] 사이드바에 해법 고르개")
from PySide6.QtWidgets import QComboBox
combos = [cb for cb in win.centralWidget().findChildren(QComboBox)
          if cb.count() == 2 and cb.itemText(0) == "Newton-Raphson"]
chk("해법 고르개가 화면에 있다", len(combos) >= 1, True)
chk("그 자리가 사이드바다", any(cb.width() > 150 for cb in combos), True)

print("\n[i23] VSC 표 셋이 다 나오고 ON/OFF 고르개는 없다")
tabs = [win._tab_pick.itemText(i) for i in range(win._tab_pick.count())]
chk("VSC 표 셋", sum(1 for t in tabs if t.startswith("VSC")), 3)
# ⚠️ 화면 전체로 세면 안 된다 — **계통도 「위반 보기」에도 ON/OFF 가 있다**.
# 지운 것은 표 줄(`_head_res`)의 VSC 고르개다. 거기만 본다.
_hr = [w for w in getattr(win, "_head_res", []) if isinstance(w, QPushButton)]
chk("표 줄에 ON/OFF 없음", [b.text() for b in _hr if b.text() in ("ON", "OFF")], [])
chk("VSC 표 이름표도 없다",
    any(getattr(w, "text", lambda: "")() == "VSC 표" for w in getattr(win, "_head_res", [])),
    False)

print("\n[i26] 열 선택 기본이 전부")
chk("AC 결과 13열", len(win._res_tables["AC 결과"][1]), 13)
chk("선로 조류 11열", len(win._res_tables["선로 조류"][1]), 11)

print("\n[i29] 「자세히 보기 →」 가 사라졌다")
chk("자세히 보기 없음",
    any("자세히 보기" in t for t in texts(win.centralWidget())), False)

print("\n[i35] 계통 데이터 탭 이름")
win.changes = [SC.toggle(win.base_case, "AC_Line_dat", 2, on=False)]
win.rebuild(); pump()
tabs = [win._tab_pick.itemText(i) for i in range(win._tab_pick.count())]
got = [t for t in tabs if t.startswith("계통 데이터")]
chk("무엇의 수인지 밝힌다", got, ["계통 데이터 · 바꾼 것 1"])
win.changes = []; win.rebuild(); pump()

print("\n[i48·i50] 시나리오 — 두 갈래 띠 · 지우기")
win.t = 4
win.changes = [SC.toggle(win.base_case, "AC_Line_dat", 2, on=False)]
c2 = SC.apply(win.base_case, win.changes)
win._pending = list(win.changes); win._pending_new = list(win.changes)
win.thread = Fake(c2); win._solved(app_engine.solve(c2)); pump()
tabs = [win._tab_pick.itemText(i) for i in range(win._tab_pick.count())]
chk("표 목록에 시나리오가 없다", any(t.startswith("시나리오") for t in tabs), False)
chk("두 갈래 띠가 있다",
    "결과" in texts(win.centralWidget()) and "시나리오 2" in texts(win.centralWidget()), True)
win.set_pane("시나리오"); pump(0.7)
chk("지우기가 글자다", "지우기" in texts(win.centralWidget()), True)
chk("✕ 는 없다", "✕" in texts(win.centralWidget()), False)
shot("08_시나리오_갈래")
win.set_pane("결과"); pump(0.5)

print("\n[i56] 시간 고르개가 표 줄에 · 머리줄에는 없다")
shot("09_결과_갈래")

print("\n[i61] 1시각 계통 — 다이나믹이 잠겨 보인다")
open_it("ACDC_case24_MatACDC.xlsx")
locked = [b for b in win.centralWidget().findChildren(QPushButton)
          if b.text() == "다이나믹"]
chk("다이나믹이 잠겼다", locked and not locked[0].isEnabled(), True)
chk("잠긴 꼴로 그린다", locked and locked[0].objectName(), "seg_lock")

print("\n[i67] DC 전용 — PV·QV 곡선이 잠겨 보인다")
open_it("DConly_21bus.xlsx")
locked = [b for b in win.centralWidget().findChildren(QPushButton)
          if b.text() == "PV·QV 곡선"]
chk("곡선이 잠겼다", locked and not locked[0].isEnabled(), True)
chk("잠긴 꼴로 그린다", locked and locked[0].objectName(), "seg_lock")
shot("10_DC전용")

print(f"\n>>> 대조 {ok[0]}개 · 실패 {len(bad)}건" + (f" — {bad}" if bad else ""))
sys.exit(1 if bad else 0)
