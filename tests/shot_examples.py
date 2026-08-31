# -*- coding: utf-8 -*-
"""Releases 에 올린 **예제 계통 12개**를 앱에서 하나씩 열어 본다 (2026-08-20).

    ~/venvs/unigrid-acdc/bin/python tests/shot_examples.py

🚨 `app_engine.solve` 를 직접 부르지 않는다. 그건 **엔진이 푸나**만 보는 것이고,
   사용자가 겪는 것은 [불러오기] → 계산 thread → `_solved` → 화면 다시 그리기다.
   그래서 `win._start_solve(path)` 로 **앱이 실제로 밟는 길**을 그대로 탄다.

🚨 MatACDC 한 쌍만 길이 다르다 — [불러오기]가 아니라 [엑셀로 만들기] 를 거친다
   (`app.py:664` `_pick` — AC .m + DC .m → `matacdc_to_case` → `write_v2` → 엑셀).
"""
import os
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "shots_examples"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import warnings                                                   # noqa: E402
warnings.filterwarnings("ignore")
from PySide6.QtWidgets import QApplication, QMessageBox            # noqa: E402

qapp = QApplication([])
import app as APP                                                  # noqa: E402

# 대화상자는 사람이 누를 때까지 멈추므로 문구만 받아 둔다
_dlg = []
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(
        lambda *a, **k: _dlg.append(a[2] if len(a) > 2 else "")))

W, H = 1600, 1000
win = APP.Proto()
win.resize(W, H)
win.show()


def pump(s=0.4):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


def open_in_app(path, timeout=300):
    """[불러오기] 를 누른 것과 같은 길. thread 가 끝날 때까지 기다린다."""
    _dlg.clear()
    win._start_solve(str(path))
    end = time.time() + timeout
    while time.time() < end:
        qapp.processEvents()
        th = getattr(win, "thread", None)
        if th is not None and hasattr(th, "isFinished") and th.isFinished():
            pump(0.3)
            return
        time.sleep(0.02)
    raise TimeoutError(f"{timeout}초 안에 안 끝남")


def tabs_now():
    tt = getattr(win, "_tabs", None)
    if tt is None:
        return []
    return [APP._tab_base(tt.tabText(i)) for i in range(tt.count())]


def walk_screen():
    """열린 뒤 화면을 실제로 훑는다 — 탭·그래프에서 터지는 것을 잡으려고."""
    hits = []
    for name in tabs_now():
        win.table_tab = name
        win.rebuild()
        pump(0.15)
        hits.append(name)
    for i in range(4):
        win.graph_tab = i
        win.rebuild()
        pump(0.15)
    return hits


CASES = REPO / "cases"
PLAN = [
    ("ACDC 24시간 · DC/DC",  CASES / "ACDC_CIGRE_MVACMVDCLVDC_24h.xlsx"),
    ("AC 118버스",           CASES / "AConly_case118.xlsx"),
    ("DC 전용 21버스",       CASES / "DConly_21bus.xlsx"),
    ("발전기 한계 위반",     CASES / "ACDC_71bus_L2_genlim.xlsx"),
    ("탭 조정",              CASES / "ACDC_case24_tapctrl.xlsx"),
    ("위상 조정",            CASES / "ACDC_case24_phasectrl.xlsx"),
    ("SVC (연속)",           CASES / "ACDC_case24_shuntctrl.xlsx"),
    ("스위치드 (계단)",      CASES / "ACDC_case24_shuntstep.xlsx"),
    ("PSS/E .raw",           CASES / "psse_ieee14.raw"),
    ("MATPOWER .m",          CASES / "matpower_ieee14.m"),
]

rows = []
n = [0]


def record(label, path, ok, note, extra=""):
    n[0] += 1
    p = OUT / f"{n[0]:02d}_{label.replace(' ', '_').replace('/', '')}.png"
    win.grab().save(str(p))
    rows.append((label, Path(path).name, ok, note, extra))
    mark = "✅" if ok else "❌"
    print(f"  {mark} {label:16s} {note}")
    if extra:
        print(f"       {extra}")


print("═" * 78)
print("  예제 계통을 앱에서 하나씩 연다")
print("═" * 78)

for label, path in PLAN:
    if not path.exists():
        record(label, path, False, "파일이 없다")
        continue
    try:
        open_in_app(path)
        sol = getattr(win, "sol", None)
        if sol is None:
            record(label, path, False, f"결과가 안 왔다 — {_dlg[-1][:60] if _dlg else '까닭 없음'}")
            continue
        if not getattr(sol, "converged", False):
            record(label, path, False, "안 풀렸다")
            continue
        seen = walk_screen()
        nac = sol.AC.shape[0] if getattr(sol, "AC", None) is not None else 0
        ndc = sol.DC.shape[0] if getattr(sol, "DC", None) is not None else 0
        note = (f"풀림 · 반복 {sol.iters}회 · {sol.seconds:.1f}초 "
                f"· AC {nac} / DC {ndc}버스")
        record(label, path, True, note, f"탭 {len(seen)}개 — {', '.join(seen)}")
    except Exception as exc:
        traceback.print_exc()
        record(label, path, False, f"터짐 — {str(exc).splitlines()[0][:70]}")

# ── MatACDC 한 쌍 — [엑셀로 만들기] 를 거친다 ──────────────────────────
print("─" * 78)
label = "MatACDC 한 쌍"
try:
    import unigrid_convert
    import write_v2
    ac = CASES / "matacdc_case5_AC.m"
    dc = CASES / "matacdc_case5_DC.m"
    case = unigrid_convert.matacdc_to_case(str(ac), str(dc))
    tmp = OUT / "matacdc_case5_unigrid.xlsx"
    write_v2.write_case(case, str(tmp))
    open_in_app(tmp)
    sol = win.sol
    ok = bool(getattr(sol, "converged", False))
    nac = sol.AC.shape[0] if sol.AC is not None else 0
    ndc = sol.DC.shape[0] if sol.DC is not None else 0
    seen = walk_screen()
    record(label, tmp, ok,
           f"엑셀로 만들어 품 · 반복 {sol.iters}회 · AC {nac} / DC {ndc}버스",
           f"탭 {len(seen)}개 — {', '.join(seen)}")
except Exception as exc:
    traceback.print_exc()
    record(label, "matacdc_case5_AC.m + _DC.m", False,
           f"터짐 — {str(exc).splitlines()[0][:70]}")

print("═" * 78)
bad = [r for r in rows if not r[2]]
print(f"  계통 {len(rows)}건 · 열림 {len(rows) - len(bad)} · 실패 {len(bad)}")
for r in bad:
    print(f"    ❌ {r[0]} ({r[1]}) — {r[3]}")
print(f"  화면 {n[0]}장 → {OUT}")
print("═" * 78)
sys.exit(1 if bad else 0)
