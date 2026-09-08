# -*- coding: utf-8 -*-
"""모션이 **넣은 곳에서 돌고 안 넣은 곳에서 안 도는가** (2026-09-08)."""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
from PySide6.QtWidgets import QApplication, QMessageBox, QGraphicsOpacityEffect
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

print(f"\n>>> 대조 {len(ok)}개 · 실패 {len(ok) - sum(ok)}건")
