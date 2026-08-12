# -*- coding: utf-8 -*-
"""PV·QV 곡선 화면 — 실제로 도는지 확인하고 찍는다 (2026-08-12, §7 4단계 F1d).

  1) 최상위 갈래가 생겼나 (조류계산 ↔ PV·QV 곡선)
  2) 못 그리는 계통에서 갈래가 흐려지고 까닭이 뜨나 (3권선·droop)
  3) 곡선을 실제로 그리나 (코 끝점 숫자가 곡선 결과와 맞나)
  4) 계통 조건이 따라오나 — 선로 하나를 끄면 여유가 줄어드나
  5) 조류계산을 **한 번도 다시 안 돌리고** 곡선만 다시 그려지나
"""
import os
import sys
import time
from pathlib import Path

REPO = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/unigrid-desktop")
V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton   # noqa: E402

qapp = QApplication([])
import app as APP                                            # noqa: E402
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)
import app_engine                                            # noqa: E402
import scenario as SC                                        # noqa: E402
from load_case import load_case                              # noqa: E402

win = APP.Proto()
win.resize(1500, 950)
win.show()


def pump(s=0.3):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


def load(path):
    """파일을 새로 여는 것과 **같은 길**로 간다.

    ⚠️ 예전에는 `_last_path` 를 직접 박고 `_solved` 만 불렀는데, 그러면 파일을 여는
       길에만 있는 처리(앞 계통의 '바꾼 것' 버리기)를 건너뛰어 **시험이 실제와 달라진다**
       (2026-08-12 에 실제로 여기서 갈렸다).
    """
    case = load_case(str(path))
    win.thread = Fake(case)
    if getattr(win, "_last_path", None) not in (None, str(path)):
        win.changes = []
        win.cur = None
        win.curve_err = ""
    win._last_path = str(path)
    win._solved(app_engine.solve(case))
    win.rebuild()
    pump()
    return case


def run_curve_now():
    """[곡선 그리기] 를 누른 것과 같게 — 다만 스레드를 기다린다."""
    win.run_curve()
    for _ in range(6000):                       # 최대 60초
        qapp.processEvents()
        if not win.curve_busy:
            break
        time.sleep(0.01)
    pump()


fails = []

print("\n=== 1) 최상위 갈래 ===")
load(V14 / "cases_v2/AConly_case14_v2.xlsx")
names = [b.text() for b in win.findChildren(QPushButton) if b.isVisible()]
has = "PV·QV 곡선" in names and "조류계산" in names
print(f"  갈래 두 개가 보이나 : {'✅' if has else '🚨 안 보인다'}")
fails += [] if has else ["갈래 없음"]

print("\n=== 2) 못 그리는 계통은 막히나 ===")
for name, patt in (("3권선", "AConly_pandapower_3w_v2.xlsx"),
                   ("droop", "gs_droop_v2.xlsx"),
                   ("AC/DC 혼합", "ACDC_71bus_v2.xlsx")):
    p = V14 / "cases_v2" / patt
    if not p.exists():
        print(f"  {name:<10} (파일 없음 — 건너뜀)")
        continue
    load(p)
    why = win.curve_why()
    print(f"  {name:<10} {'막힘: ' + why[:52] if why else '🚨 안 막힘'}")
    if not why:
        fails.append(f"{name} 안 막힘")

print("\n=== 3) 곡선을 실제로 그리나 ===")
case14 = load(V14 / "cases_v2/AConly_case14_v2.xlsx")
win.set_task("PV·QV 곡선")
pump()
run_curve_now()
if win.cur is None:
    print(f"  🚨 곡선이 없다 — {win.curve_err[:200]}")
    fails.append("곡선 실패")
else:
    cur = win.cur
    base = float(cur.load_MW[0])
    print(f"  λ_crit {cur.lam_crit:.4f} · 지금 {base:,.1f} MW → 버틸 수 있는 "
          f"{cur.nose_MW:,.1f} MW · 걸음 {cur.lam.size}")
    print(f"  한계에 걸린 발전기 {cur.switched.size}대 · {cur.seconds:.1f}초")
    # 요약 카드가 곡선 결과와 같은 숫자를 말하나
    ok = abs((1 + cur.lam_crit) * base - cur.nose_MW) < max(0.5, base * 1e-3)
    print(f"  코 끝 부하 = (1+λ)×지금 부하 : {'✅' if ok else '🚨 안 맞음'}")
    fails += [] if ok else ["요약 숫자 안 맞음"]
    win.grab().save(str(OUT / "곡선_case14.png"))

print("\n=== 4) 계통 조건이 따라오나 (선로 3 끄기) ===")
before = win.cur.lam_crit if win.cur is not None else float("nan")
n_solve_before = app_engine._solve_count
win.changes = [SC.Cell(table="AC_Line_dat", row=2, col=12, value=0.0,
                       label="선로 3 끄기")] if hasattr(SC, "Cell") else []
if not win.changes:
    print("  (scenario.Cell 을 못 찾음 — 건너뜀)")
else:
    win.rebuild()
    run_curve_now()
    after = win.cur.lam_crit if win.cur is not None else float("nan")
    print(f"  λ_crit {before:.4f} → {after:.4f}")
    ok = after < before
    print(f"  선로를 끄면 여유가 줄어드나 : {'✅' if ok else '🚨 안 줄어듦'}")
    fails += [] if ok else ["조건이 안 따라옴"]

    print("\n=== 5) 조류계산은 안 돌았나 (아예 분리) ===")
    n_after = app_engine._solve_count
    print(f"  곡선을 두 번 그리는 동안 조류계산 횟수 {n_solve_before} → {n_after}")
    ok2 = n_after == n_solve_before
    print(f"  {'✅ 조류계산을 한 번도 안 불렀다' if ok2 else '🚨 조류계산이 딸려 돌았다'}")
    fails += [] if ok2 else ["조류계산이 딸려 돎"]
    win.grab().save(str(OUT / "곡선_case14_선로끔.png"))

print("\n=== 6) 곡선 화면에서 AC/DC 파일을 열면 (AC 단독 못박기) ===")
# 곡선은 **AC 단독에서만** 그린다(2026-08-12 사용자 확정). 곡선 화면에 있는 채로
# AC/DC 파일을 열면 갈래가 곡선에 머무는데 그 버튼은 흐려져 **죽은 화면**이 됐었다.
load(V14 / "cases_v2/AConly_case14_v2.xlsx")
win.set_task("PV·QV 곡선")
run_curve_now()
had = win.cur is not None
load(V14 / "cases_v2/ACDC_71bus_v2.xlsx")
back = win.task == "조류계산"
gone = win.cur is None
print(f"  곡선을 그려 뒀다      : {'✅' if had else '🚨 못 그림'}")
print(f"  갈래가 조류계산으로   : {'✅' if back else '🚨 곡선에 머무름'}")
print(f"  앞 계통 곡선이 지워짐 : {'✅' if gone else '🚨 남아 있음'}")
fails += [] if (had and back and gone) else ["AC/DC 를 열었을 때 처리"]

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.exit(1 if fails else 0)
