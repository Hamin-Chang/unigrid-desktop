# -*- coding: utf-8 -*-
"""그래프 접기 스위치는 **하나뿐**이고, 접혀도 그림을 내보낼 수 있나 (2026-08-18).

계기 — 사용자 *"그래프 펼치기랑 숫자만/그림 포함 이게 좀 겹치는거 같은데"*.
스위치는 `self.numbers` 하나인데 이름이 넷이었다: 위쪽 [숫자만]/[그림 포함] ·
그래프 자리 [그래프 접기]/[그래프 펼치기]. 2026-08-15 에 그래프 자리에 접기를
넣으면서 겹침을 툴팁(*"위쪽 [숫자만] 과 같은 일입니다"*)으로 때웠고, 그 땜질이
이 지적으로 돌아왔다. ⇒ 위쪽 「표시 모드」 를 없애고 그래프 자리만 남겼다.

보는 것
    1) 위쪽 띠에 [숫자만]·[그림 포함]·「표시 모드」 가 **없나**
    2) 펼쳐져 있을 때 접는 길이 **그래프 자리에 있나** (없애 놓고 길까지 막으면 안 된다)
    3) 접혀 있을 때 펴는 길이 **안내 띠에 있나**
    4) 🚨 접혀 있어도 내보내기에서 **그림을 고를 수 있나**
       — 예전에는 꺼져 있었다. 화면이 접혔다고 그림을 못 만드는 게 아니다:
         `exporter.save_figures` 는 화면을 안 보고 **결과에서 새로 그린다**.
    5) 🚨 **저절로** 접혔을 때도 마찬가지인가
       — 선로 하나 껐을 뿐인데 *"지금은 숫자 모드라…"* 로 막히던 자리다.
    6) 접혀 있어도 그림 파일이 **실제로 만들어지나** (칸만 열어 두고 안 나오면 헛것이다)
    7) 어디에도 **"5~7배 빠릅니다"** 가 안 남아 있나 (실측 0.86~1.49배 — 거짓 문구)
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

import warnings                                                   # noqa: E402
warnings.filterwarnings("ignore")
from PySide6.QtWidgets import (QApplication, QMessageBox,          # noqa: E402
                               QPushButton, QLabel, QTabWidget)

qapp = QApplication([])
import app as APP                                                  # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                                  # noqa: E402
import exporter                                                    # noqa: E402
import scenario as SC                                              # noqa: E402
from load_case import load_case                                    # noqa: E402

CASE = V14 / "cases_v2/ACDC_case24_MatACDC_v2.xlsx"
fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<52} {got}")
    else:
        print(f"  ❌ {label:<52} {got}  (바라던 값 {want})")
        fails.append(label)


def pump(s=0.6):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


def texts():
    return [w.text() for w in win.findChildren(QPushButton)] + \
           [w.text() for w in win.findChildren(QLabel)]


def corner_buttons():
    return [w.cornerWidget().text()
            for w in win.findChildren(QTabWidget)
            if isinstance(w.cornerWidget(), QPushButton)]


def figure_boxes():
    """내보내기 창에서 **그림** 칸들이 고를 수 있나."""
    d = APP.ExportDialog(win, win.c, win.mode, win.picked)
    figs = {t for t, _f in exporter.figure_names(win.sol, win.mode)}
    boxes = [cb for n, cb in d.tabs if n in figs]
    out = (len(boxes), sum(1 for cb in boxes if cb.isEnabled()))
    d.deleteLater()
    return out


win = APP.Proto()
win.resize(1500, 950)
win.show()
pump(0.4)
case = load_case(str(CASE))
win.thread = Fake(case)
win._last_path = str(CASE)
win._solved(app_engine.solve(case))
win.rebuild()
pump(1.0)

print("\n[1] 위쪽 「표시 모드」 가 사라졌나")
t = texts()
for gone in ("숫자만", "그림 포함", "표시 모드"):
    check(f"{gone} 없나", gone not in t, True)

print("\n[2] 펼쳐져 있을 때 접는 길이 그래프 자리에 있나")
check("접혀 있나", win.numbers, False)
check("[그래프 접기]", any("접기" in n for n in corner_buttons()), True)

print("\n[3] 접혀 있을 때 펴는 길이 안내 띠에 있나")
win.set_numbers(True)
pump()
check("접혔나", win.numbers, True)
check("[그래프 펼치기]", "그래프 펼치기" in texts(), True)

print("\n[4] 🚨 접혀 있어도 내보내기에서 그림을 고를 수 있나")
n_fig, n_on = figure_boxes()
check(f"그림 칸 {n_fig}개가 다 열려 있나", n_on, n_fig)

print("\n[5] 🚨 저절로 접혔을 때도 마찬가지인가")
win.set_numbers(False)                 # 되돌려 놓고
win.graph_kept = False                 # 「직접 펼쳤다」 기억을 지워 자동 접힘이 살아나게
pump()
win.grid_key = "AC_Line_dat"
win.flip_row(3)
pump(0.2)
pend = win.applied + win.changes
win._pending, win._pending_new = pend, list(win.changes)
win._solved(app_engine.solve(SC.apply(win.base_case, pend)))
win.rebuild()
pump()
check("저절로 접혔나", win.numbers, True)
check("이유", win.numbers_why, "changed")
n_fig, n_on = figure_boxes()
check(f"그림 칸 {n_fig}개가 다 열려 있나", n_on, n_fig)

print("\n[6] 접혀 있어도 그림 파일이 실제로 만들어지나")
out = Path(os.environ.get("TMPDIR", "/tmp")) / "unigrid_shot_one_switch"
names = {t for t, _f in exporter.figure_names(win.sol, win.mode)}
made = exporter.save_figures(win.c, win.sol, win.mode, out, names)
check(f"파일 {len(made)}개", len(made) > 0, True)
check("빈 파일은 없나", all(f.stat().st_size > 1000 for f in made), True)
for f in made:
    f.unlink(missing_ok=True)

print("\n[7] 거짓 문구가 안 남았나")
src = (REPO / "src" / "app.py").read_text(encoding="utf-8")
live = "\n".join(ln for ln in src.split("\n")
                 if not ln.lstrip().startswith("#"))
check("\"5~7배\" 가 화면 문구에 없나", "5~7배" not in live, True)

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if fails else 0)
