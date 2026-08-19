# -*- coding: utf-8 -*-
"""표 위의 「주황이 무슨 뜻인지」 띠 (2026-08-18).

계기 — AC 결과 표에서 전압 한계를 벗어난 버스는 **줄 전체가 주황**인데, 그 규칙이
화면 어디에도 안 적혀 있었다. 표에 `Vmin[pu]`·`Vmax[pu]` 열이 있어 눈으로 짚으면
짐작은 되지만, 짐작해야 한다는 게 문제다 — 주황이 「위반」인지 「고른 줄」인지 모른다.

보는 것
    1) AC 결과 탭에 띠가 뜨나 · 건수가 **그 계통의 위반 버스 수**와 맞나
    2) 🚨 DC 결과 탭에도 뜨나 (사용자 요청 — 주황 규칙이 거기도 걸린다)
       ⚠️ DC 위반이 있는 케이스로 봐야 한다. case24 는 DC 가 0곳이라 안 뜨는 게 맞고,
          그걸로 "DC 는 안 된다" 고 볼 뻔했다.
    3) AC 탭과 DC 탭이 **각자 제 계통 것만** 세나 (합쳐 세면 둘 다 4곳이 된다)
    4) 위반이 없는 표에는 띠를 **안 보이나** (성한 계통에 군더더기를 남기지 않는다)
       ⚠️ 띠는 정렬 때문에 **항상 만들어 둔다** — 그러니 '있나' 가 아니라 '보이나' 로 본다
    5) 다른 탭(선로 조류 등)에는 없나
    6) 띠가 표를 **가리지 않나** — 탭 줄과 표 사이에 들어가야 한다
    7) [자세히 보기] 가 점검 탭으로 보내나
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
from PySide6.QtWidgets import (QApplication, QMessageBox, QFrame,  # noqa: E402
                               QLabel, QPushButton, QTableWidget)

qapp = QApplication([])
import app as APP                                                  # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                                  # noqa: E402
from load_case import load_case                                    # noqa: E402

# AC 19곳 · DC 0곳  /  AC 1곳 · DC 3곳  /  AC 2곳(작은 계통)
MANY = V14 / "cases_v2/ACDC_case24_MatACDC_v2.xlsx"
BOTH = V14 / "cases_v2/ACDC_CIGRE_MV_droop_v098_v2.xlsx"
fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<50} {got}")
    else:
        print(f"  ❌ {label:<50} {got}  (바라던 값 {want})")
        fails.append(label)


def pump(s=0.7):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


win = APP.Proto()
win.resize(1500, 950)
win.show()
pump(0.4)


def open_case(path):
    case = load_case(str(path))
    win.thread = Fake(case)
    win._last_path = str(path)
    win._solved(app_engine.solve(case))
    win.rebuild()
    pump(1.0)


def tab_bar(name):
    """그 탭에서 **보이는** 띠 — 없으면 None.

    🚨 `findChildren` 만 쓰면 안 된다. 2026-08-18 정렬을 넣으면서 띠를
    **항상 만들어 두고 보일 것이 없으면 숨기는** 방식으로 바꿨다
    (`_fill_strip` — 정렬할 때마다 화면을 통째로 다시 그리지 않으려고).
    그래서 숨은 띠도 `findChildren` 에 잡히고, 그러면 [4]·[5] 가
    "성한 표에도 띠가 있다" 고 거짓 실패한다.
    """
    tt = win._tabs
    for i in range(tt.count()):
        if tt.tabText(i) != name:
            continue
        tt.setCurrentIndex(i)
        pump(0.5)
        bars = [f for f in tt.currentWidget().findChildren(QFrame)
                if f.objectName() == "violbar" and f.isVisible()]
        return bars[0] if bars else None
    return None


def said(bar):
    """띠가 말하는 건수."""
    for lb in bar.findChildren(QLabel):
        t = lb.text()
        if "곳" in t:
            return int("".join(ch for ch in t if ch.isdigit()))
    return -1


def counts():
    bad = win.violating_buses()
    return (sum(1 for g, _b in bad if g == "AC"),
            sum(1 for g, _b in bad if g == "DC"))


print(f"\n[케이스] {MANY.name}")
open_case(MANY)
n_ac, n_dc = counts()
print(f"    위반 버스 — AC {n_ac}곳 · DC {n_dc}곳")

print("\n[1] AC 결과 탭에 띠가 뜨고 건수가 맞나")
b = tab_bar("AC 결과")
check("띠가 있나", b is not None, True)
if b:
    check("건수", said(b), n_ac)

print("\n[4] DC 는 위반이 없으니 띠가 없어야 한다")
check("DC 탭 띠 없음", tab_bar("DC 결과") is None, n_dc == 0)

print("\n[5] 다른 탭에는 없나")
check("선로 조류", tab_bar("선로 조류") is None, True)

print(f"\n[2][3] 🚨 DC 위반이 있는 케이스 — {BOTH.name}")
open_case(BOTH)
n_ac, n_dc = counts()
print(f"    위반 버스 — AC {n_ac}곳 · DC {n_dc}곳")
check("둘 다 위반이 있는 케이스인가", n_ac > 0 and n_dc > 0, True)
ba, bd = tab_bar("AC 결과"), tab_bar("DC 결과")
check("AC 탭 띠", ba is not None, True)
check("DC 탭 띠", bd is not None, True)
if ba and bd:
    check("AC 탭은 AC 것만 세나", said(ba), n_ac)
    check("DC 탭은 DC 것만 세나", said(bd), n_dc)
    check("둘이 다른 수인가 (합쳐 세면 같아진다)", said(ba) != said(bd), True)

print("\n[6] 띠가 표를 가리지 않나 — 표보다 위에 있어야 한다")
if bd:
    tbl = bd.parent().findChild(QTableWidget)
    check("표가 띠 아래에 있나", tbl.y() >= bd.y() + bd.height(), True)
    check("표 첫 줄이 안 잘렸나",
          tbl.visualItemRect(tbl.item(0, 0)).top() >= 0, True)

print("\n[7] [자세히 보기] 가 점검 탭으로 보내나")
if bd:
    go = next((w for w in bd.findChildren(QPushButton) if "자세히" in w.text()), None)
    check("단추가 있나", go is not None, True)
    if go:
        go.click()
        pump(0.6)
        check("점검 탭으로 갔나", win.table_tab, "점검")

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if fails else 0)
