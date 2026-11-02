# -*- coding: utf-8 -*-
"""모션이 **넣은 곳에서 돌고 안 넣은 곳에서 안 도는가** (2026-09-08)."""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
from PySide6.QtWidgets import (QApplication, QMessageBox, QGraphicsOpacityEffect,
                               QLabel, QPushButton)
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
qapp = QApplication([])
import app as APP
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
def pump(s=0.5):
    e = time.time() + s
    while time.time() < e: qapp.processEvents(); time.sleep(0.005)

win = APP.Proto(); win.resize(1700, 1000); win.show(); pump(0.5)
win._start_solve(str(REPO / "cases" / "ACDC_case24_MatACDC_24h.xlsx"))
for _ in range(60):
    pump(0.5)
    if getattr(win, "sol", None) is not None: break
pump(1.2)

def fading():
    # 앱 2.3 — 화면을 통째로 바꾸는 전환(테마)은 옛 화면 덮개가 옅어진다(`crossfade_from`)
    for ch in win.children():
        if isinstance(ch, QLabel) and isinstance(ch.graphicsEffect(), QGraphicsOpacityEffect):
            return min(round(ch.graphicsEffect().opacity(), 2), 0.98)
    w = getattr(win, "_center_w", None)
    if w is None: return None
    eff = w.graphicsEffect()
    return round(eff.opacity(), 2) if isinstance(eff, QGraphicsOpacityEffect) else None

def probe(name, fn, want):
    """부른 직후 페이드가 도는가."""
    fn(); pump(0.04)
    v = fading()
    got = v is not None and v < 0.99
    mark = "✅" if got == want else "🚨"
    print(f"  {mark} {name:26} {'돈다' if got else '안 돈다':6} (바람: {'돈다' if want else '안 돈다'})"
          f"{'' if v is None else f'  투명도 {v}'}")
    pump(0.5)
    return got == want

print("── 넣은 곳: 돌아야 한다 ──")
ok = []
ok.append(probe("set_mode(다이나믹)",  lambda: win.set_mode("다이나믹"), True))
ok.append(probe("set_mode(스냅샷)",    lambda: win.set_mode("스냅샷"), True))
# ⚠️ `set_pane` 은 **시나리오가 둘 이상일 때만** 갈래가 생긴다
#    (`_pane_strip` 이 `len(book.items) < 2` 면 「결과」로 되돌린다).
#    원본 하나뿐인 상태에서 재면 «안 돈다» 가 나오는데 그건 정상이다.
if len(win.book.items) >= 2:
    ok.append(probe("set_pane(시나리오)", lambda: win.set_pane("시나리오"), True))
    ok.append(probe("set_pane(결과)", lambda: win.set_pane("결과"), True))
else:
    print("  ⏭  set_pane — 시나리오가 하나뿐이라 건너뜀")
ok.append(probe("set_numbers(접기)",   lambda: win.set_numbers(True), True))
ok.append(probe("set_numbers(펼치기)", lambda: win.set_numbers(False), True))
ok.append(probe("toggle_theme",        lambda: win.toggle_theme(), True))
ok.append(probe("toggle_theme(되돌림)", lambda: win.toggle_theme(), True))

print("\n── 안 넣은 곳: 안 돌아야 한다 (깜빡이면 못 쓴다) ──")
ok.append(probe("set_time(5시)",       lambda: win.set_time(4), False))
ok.append(probe("set_vsc",             lambda: win.set_vsc(True), False))
ok.append(probe("set_violations",      lambda: win.set_violations(True), False))
ok.append(probe("set_find",            lambda: win.set_find("106"), False))
win.set_find("")

print("\n── 사이드바 폭 모션 ──")
before = win._side_sa.width()
win.toggle_side(); pump(0.05)
seen = []
for _ in range(12):
    pump(0.025)
    seen.append(win._side_sa.maximumWidth())
pump(0.4)
after = win._side_sa.width()
moved = len(set(seen)) > 2
print(f"  {'✅' if moved else '🚨'} 폭 자취 {seen[:8]} …  {before} → {after}")
ok.append(moved)
win.toggle_side(); pump(0.6)

print("\n── 앱 2.3 — 단추 누름 물결(D) · 대화상자(E) · 테마 스위치(C) ──")
# D: 누르기만 하고 떼지 않는다(떼면 눌린 것이 되어 창이 뜰 수 있다)
btn = next(b for b in win.findChildren(QPushButton)
           if b.isVisible() and b.isEnabled() and b.text() == "정보")
QTest.mousePress(btn, Qt.LeftButton); pump(0.05)
rip = [ch for ch in btn.children() if type(ch).__name__ == "_Ripple"]
print(f"  {'✅' if rip else '🚨'} 단추를 누르면 물결이 생긴다  ({len(rip)}개)")
ok.append(bool(rip))
btn.setDown(False); pump(0.5)
gone = not [ch for ch in btn.children() if type(ch).__name__ == "_Ripple"]
print(f"  {'✅' if gone else '🚨'} 물결은 0.4초 안에 사라진다")
ok.append(gone)
# E: 대화상자를 띄우면 투명에서 나타난다
dlg = APP.AboutDialog(win, win.c); dlg.show(); pump(0.04)
op = dlg.windowOpacity()
print(f"  {'✅' if op < 0.99 else '🚨'} 대화상자가 투명에서 나타난다  (띄운 직후 {op:.2f})")
ok.append(op < 0.99)
pump(0.3); dlg.close(); pump(0.1)
# C: 테마 스위치 — 손잡이가 미끄러진 뒤 테마가 바뀐다
sw = next(b for b in win.findChildren(APP.ThemeSwitch) if b.isVisible())
dark0 = win.dark
sw.click(); pump(0.06)
mid = 0.0 < sw._x < 1.0
pump(0.6)
print(f"  {'✅' if mid else '🚨'} 손잡이가 미끄러진다 · {'✅' if win.dark != dark0 else '🚨'} 테마가 바뀐다")
ok.append(mid); ok.append(win.dark != dark0)
win.toggle_theme(); pump(0.6)

print("\n── 앱 2.3 — 전수검사로 더한 곳 ──")
from PySide6.QtWidgets import QWidget as _QW
from PySide6.QtCore import Qt as _Qt


def any_fade():
    """덮개(옛 화면)든 판 하나든 — 창 안 어디서든 밝아지는 중인가."""
    for ch in win.children():
        if isinstance(ch, QLabel) and isinstance(ch.graphicsEffect(), QGraphicsOpacityEffect):
            return True
    for w in win.findChildren(_QW):
        e = w.graphicsEffect()
        if isinstance(e, QGraphicsOpacityEffect) and e.opacity() < 0.99:
            return True
    return bool(drawing())


def drawing():
    """앱 2.3 — 그래프가 제 움직임(`charts._anim`)으로 그려지는 중인 것들."""
    from PySide6.QtCore import QAbstractAnimation
    return [w for w in win.findChildren(_QW)
            if getattr(w, "_play_anim", None) is not None and w.isVisible()
            and w._play_anim.state() == QAbstractAnimation.Running]


def probe2(name, fn):
    fn(); pump(0.04)
    got = any_fade()
    print(f"  {'✅' if got else '🚨'} {name:30} {'돈다' if got else '안 돈다'}")
    pump(0.6)
    return got


ok.append(probe2("그래프 고르기 (전압·위상 탭)", lambda: win.set_plot_pick(1 - int(win.plot_pick))))
# 옮긴 자리가 없으면 함수가 아무것도 안 하고 끝난다(맞는 동작) — 있는 것으로 두고 본다
import topology as _T
_clear = _T.clear_places
_T.clear_places = lambda name: True
ok.append(probe2("계통도 배치 처음으로", lambda: win.reset_topo_places(win.sol.case_name)))
_T.clear_places = _clear
ok.append(probe2("바꾼 것 되돌리기", lambda: win.undo_changes()))
win.set_mode("비교"); pump(0.6)
ok.append(probe2("비교 축 바꾸기", lambda: win.set_axis(
    "시나리오끼리" if win.compare_axis == "버스끼리" else "버스끼리")))
win.set_mode("스냅샷"); pump(0.6)
ok.append(probe2("사이드바 PV·QV 곡선", lambda: win.rail_go("PV·QV 곡선")))
ok.append(probe2("사이드바 곡선 → 결과", lambda: win.rail_go("결과")))
print("\n── 앱 2.3 — 결과 그래프마다 제 움직임 ──")
import charts as _C
def probe3(name, fn):
    # 0.3 초 뒤에 본다 — 그래프는 새 판이 처음 그려질 때 시작하고(최대 0.18 초) 0.65 초 넘게 돈다
    fn(); pump(0.3)
    got = drawing()
    kinds = sorted({type(w).__name__ for w in got})
    print(f"  {'✅' if got else '🚨'} {name:30} {'그려진다' if got else '안 그려진다'}  {kinds}")
    pump(1.1)
    return bool(got)
gt = lambda: [g for g in win.findChildren(APP.GlassTabs) if g.isVisible()][-1]
for i, nm in enumerate(["전압·위상", "조류 P·Q", "부하율", "토폴로지"]):
    ok.append(probe3(f"스냅샷 {nm} 탭", lambda i=i: gt().setCurrentIndex((i + 1) % 4) or gt().setCurrentIndex(i)))
ok.append(probe3("다이나믹으로 바꾸기", lambda: win.set_mode("다이나믹")))
for i, nm in enumerate(["전압·위상", "주파수", "토폴로지"]):
    ok.append(probe3(f"다이나믹 {nm} 탭", lambda i=i: gt().setCurrentIndex((i + 1) % 3) or gt().setCurrentIndex(i)))
# 위에서 축을 「버스끼리」로 바꿨다 — 버스를 안 골라 그래프가 없다(맞는 동작). 시간끼리로 본다.
win.compare_axis = "시간끼리"
ok.append(probe3("비교로 바꾸기", lambda: win.set_mode("비교")))
win.set_mode("스냅샷"); pump(0.8)
ok.append(probe3("그래프 펼치기", lambda: (win.set_numbers(True), pump(0.4), win.set_numbers(False))))
print("  ⏭  set_time 은 위 「안 넣은 곳」 에서 안 도는 것을 이미 본다")

eff = APP.QApplication.isEffectEnabled(_Qt.UI_FadeTooltip)
print(f"  {'✅' if eff else '🚨'} 풍선말 흐려짐 효과 켜짐")
ok.append(eff)

print(f"\n>>> 대조 {len(ok)}개 · 실패 {len(ok) - sum(ok)}건")
