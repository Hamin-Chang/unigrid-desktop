# -*- coding: utf-8 -*-
"""비교 그림 저장 — 「시나리오끼리」에서도 되나 (2026-09-01 전수 조사 ⑨).

계기 — 사이드바를 훑다가 찾았다. 「시나리오끼리」를 고르면 **「이 비교 그림 저장」
단추가 아예 없었다.** 그 갈래가 안내 라벨을 붙이고 `return sb` 로 먼저 나가는데,
저장 단추는 그 뒤에 있었다. 시나리오를 겹쳐 그려 놓고 그 그림만 저장을 못 했다.

🚨 **단추만 달면 안 된다.** 화면은 이 갈래에서 `charts.compare_scenarios` 를 쓰는데
   내보내기는 `charts.compare_chart` 만 알고 있었다 — 그대로 두면 엉뚱한 그림을
   저장하거나(항목에 따라) 한 장도 못 만든다. 내보내기에 길을 냈다
   (`save_compare_figures(..., pairs=, t=)`).

여기서 지키는 것
    1) 세 갈래(버스끼리·시간끼리·시나리오끼리) 모두 저장 단추가 있나
    2) 🚨 시나리오끼리에서 **실제로 파일이 나오나** (고치기 전에는 0 장이었다)
    3) 버스끼리도 그대로 되나 (회귀)
"""
import os
import shutil
import sys
import tempfile
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
                               QPushButton, QScrollArea, QLabel)

qapp = QApplication([])
import app as APP                                            # noqa: E402
_seen = []
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(
        lambda *a, **k: _seen.append(a[1] if len(a) > 1 else "")))
QMessageBox.exec = lambda self, *a, **k: None                # 완료 창은 안 띄운다
import app_engine                                            # noqa: E402
import exporter                                              # noqa: E402
import scenario as SC                                        # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/ACDC_case24_MatACDC_v2.xlsx"
OUT = Path(tempfile.mkdtemp(prefix="cmpsave_"))              # 바탕화면을 안 더럽힌다
exporter.default_folder = lambda name: OUT / str(name)
fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<46} {got}")
    else:
        print(f"  ❌ {label:<46} {got}  (바라던 값 {want})")
        fails.append(label)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


def pump(t=0.6):
    end = time.time() + t
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


win = APP.Proto()
win.resize(1512, 950)
win.show()
pump(0.4)
case = load_case(str(CASE))
win.thread = Fake(case)
win._last_path = str(CASE)
win._solved(app_engine.solve(case))
win.rebuild()
pump(1.2)


def row_of(a, b):
    arr = SC._values(case, "AC_Line_dat")
    return [i for i, r in enumerate(arr) if (int(r[1]), int(r[2])) == (a, b)][0]


def press_run():
    """[이 조건으로 계산] 을 누른 것과 같은 경로 (스레드만 뺐다)."""
    win._pending = win.applied + win.changes
    sol = app_engine.solve(SC.apply(win.base_case, win._pending))
    win.thread = Fake(case)
    win._solved(sol)
    win.rebuild()
    pump(0.8)


print("\n[0] 시나리오 둘을 만든다")
win.flip_row(row_of(106, 110)); press_run()
win.flip_row(row_of(102, 104)); press_run()
check("담긴 시나리오 수가 둘 이상인가", len(win.book.items) >= 2, True)


def save_button():
    """⚠️ **보이는 것만 집는다.** 화면을 다시 그려도 옛 사이드바가 잠시 살아 있어,
       `isVisible()` 을 안 보면 **지워진 단추를 찾아내** 시험이 통과해 버린다
       (2026-09-01 실측 — 단추를 지우고도 「있다」가 나왔다)."""
    for b in win.findChildren(QPushButton):
        if b.isVisible() and b.text().startswith("이 비교 그림 저장"):
            return b
    return None


# 🚨 **어느 그림 함수를 불렀는지 센다.** 파일이 나왔다는 것만으로는 모자라다 —
#    `compare_chart` 도 시나리오끼리에서 그림을 한 장 만들어 내므로, 갈래가 없으면
#    **엉뚱한 그림**이 저장되는데 파일 수는 똑같다.
import charts                                              # noqa: E402
_calls = {"scen": 0, "plain": 0}
_orig_scen, _orig_plain = charts.compare_scenarios, charts.compare_chart


def _spy_scen(*a, **k):
    _calls["scen"] += 1
    return _orig_scen(*a, **k)


def _spy_plain(*a, **k):
    _calls["plain"] += 1
    return _orig_plain(*a, **k)


charts.compare_scenarios = _spy_scen
charts.compare_chart = _spy_plain
import exporter as _exp                                    # noqa: E402
_exp.charts = charts


def saved_files():
    return sorted(p.name for p in OUT.rglob("*.png"))


win.mode = "비교"
for axis in ("버스끼리", "시간끼리", "시나리오끼리"):
    win.compare_axis = axis
    win.rebuild()
    pump(1.0)
    print(f"\n[{axis}]")
    check("저장 단추가 있나", save_button() is not None, True)

print("\n[🚨 시나리오끼리에서 실제로 파일이 나오나]")
shutil.rmtree(OUT, ignore_errors=True)
win.compare_axis = "시나리오끼리"
win.rebuild()
pump(1.0)
_seen.clear()
_calls.update(scen=0, plain=0)
win.save_compare_figures()
pump(0.6)
got = saved_files()
print("   저장된 것:", got or "없음", "· 뜬 안내:", _seen or "없음",
      "· 부른 함수:", dict(_calls))
check("한 장 이상 나왔나", len(got) >= 1, True)
check("🚨 시나리오 그림 함수를 불렀나", _calls["scen"] >= 1, True)
check("🚨 엉뚱한 함수를 안 불렀나", _calls["plain"], 0)

print("\n[버스끼리도 그대로 되나 — 회귀]")
shutil.rmtree(OUT, ignore_errors=True)
win.compare_axis = "버스끼리"
win.rebuild()
pump(1.0)
_seen.clear()
win.save_compare_figures()
pump(0.6)
got2 = saved_files()
print("   저장된 것:", got2 or "없음", "· 뜬 안내:", _seen or "없음")
check("한 장 이상 나왔나", len(got2) >= 1, True)

shutil.rmtree(OUT, ignore_errors=True)
print()
if fails:
    print(f"❌ 실패 {len(fails)}건: {fails}")
    sys.stdout.flush()
    app_engine.shutdown()
    os._exit(1)
print("DONE_COMPARE_SAVE — 모두 통과")
sys.stdout.flush()
app_engine.shutdown()
os._exit(0)
