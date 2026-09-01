# -*- coding: utf-8 -*-
"""계통 데이터 조작 줄 — 표 고르개 + 「⚙ 부하」 (2026-09-01 전수 조사 ⑥).

**한 뿌리의 두 증상**이었다. 이 줄에 「표 고르기 단추 여럿 + 찾기 + 부하 슬라이더」가
한꺼번에 있어서 폭이 **1380px** 이었고, 창이 그보다 좁으면 오른쪽부터 밀려났다.

    창 1512 맥북 14"   206px 넘침    부하 슬라이더 반쪽
    창 1194 사이드카   524px 넘침    부하 슬라이더 **안 보임**
    창  929 최소       676px 넘침    부하 슬라이더 **안 보임**

⇒ 두 가지를 했다.
  ① **부하 배율을 조건 자리로** — `SC.Scale` 을 얹는 **조건 변경**인데 「보는 것」
     (표 고르기·찾기)의 줄에 혼자 섞여 있었다. `⚙ AC 조정` 과 같은 격의 항목
     (`LOAD_KEY`)으로 빼고, 배율은 **단추에 찍어** 안 눌러도 보이게 했다.
  ② **표 고르기 단추 → 드롭다운** — 단추는 그 계통에 있는 표만큼 생겨서 AC/DC 는
     여덟아홉이다(실측 603px). 이 줄의 길이가 곧 창 최소 가로였다.

여기서 지키는 것
    1) 드롭다운에 그 계통의 표가 다 들어 있나 · 골라서 옮겨지나
    2) 🚨 「⚙ 부하」 판에서 **드롭다운에 이미 적힌 표**를 다시 골라도 돌아오나
       (`currentIndexChanged` 로 걸면 신호가 안 나 **못 돌아간다** — `activated` 여야 한다)
    3) 「⚙ 부하」 판에 슬라이더가 있고 배율이 단추에 찍히나
    4) 🚨 부하 없는 계통으로 갈아타면 **빈 판에 갇히지 않나** (단추가 사라지므로)
    5) 좁은 창(929px)에서 이 줄이 안 넘치나
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
                               QComboBox, QScrollArea, QPushButton,
                               QSlider)

qapp = QApplication([])
import app as APP                                            # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                            # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/ACDC_case24_MatACDC_v2.xlsx"
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


def pump(t=0.7):
    end = time.time() + t
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


win = APP.Proto()
win.resize(1194, 900)
win.show()
pump(0.4)
case = load_case(str(CASE))
win.thread = Fake(case)
win._last_path = str(CASE)
win._solved(app_engine.solve(case))
win.rebuild()
pump(1.4)


def grid_page():
    tt = win._tabs
    for i in range(tt.count()):
        if tt.tabText(i).startswith("계통 데이터"):
            tt.setCurrentIndex(i)
            pump(0.6)
            return tt.currentWidget()
    return None


def bar():
    return grid_page().findChild(QScrollArea, "gridbar")


def combo():
    return bar().widget().findChild(QComboBox)


def gear(word):
    for b in bar().widget().findChildren(QPushButton):
        if word in b.text():
            return b
    return None


print("\n[1] 드롭다운이 표를 다 담나")
cb = combo()
check("드롭다운이 있나", cb is not None, True)
names = [cb.itemText(i) for i in range(cb.count())]
check("표가 여럿 들어 있나", cb.count() >= 4, True)
check("지금 표를 가리키나", names[cb.currentIndex()].startswith("AC 선로"), True)

print("\n[2] 골라서 옮겨지나")
want = next(i for i, n in enumerate(names) if n.startswith("AC 버스"))
cb.activated.emit(want)
pump(1.0)
check("고른 표로 갔나", win.grid_key, "AC_Bus_dat")

print("\n[3] 「⚙ 부하」 판")
lb = gear("부하")
check("단추가 있나", lb is not None, True)
check("단추에 배율이 찍히나", "×1.00" in lb.text(), True)
win.set_grid_table(APP.LOAD_KEY)
pump(1.0)
check("판으로 갔나", win.grid_key, APP.LOAD_KEY)
check("슬라이더가 있나",
      grid_page().findChild(QSlider) is not None, True)
win.scale_loads(1.30)
pump(1.2)
check("배율을 바꾸면 단추도 따라오나", "×1.30" in gear("부하").text(), True)
check("드롭다운은 마지막으로 본 표를 그대로 가리키나",
      combo().currentText().startswith("AC 버스"), True)

print("\n[4] 🚨 판에서 **같은 항목**을 다시 골라도 돌아오나")
cb = combo()
cb.activated.emit(cb.currentIndex())      # 사람이 이미 적힌 것을 다시 고른 것
pump(1.2)
check("표로 돌아왔나", win.grid_key, "AC_Bus_dat")

print("\n[5] 🚨 부하 없는 계통이면 갇히지 않나")
win.set_grid_table(APP.LOAD_KEY)
pump(0.8)
# ⚠️ 원본을 **꺼내 두었다가 도로 넣는다.** `del` 로 지우면 덮어쓴 것과 함께
#    원래 메서드까지 없어져 다음 `rebuild()` 가 죽는다.
_orig_has_load = APP.Proto.has_load
APP.Proto.has_load = lambda self: False   # 부하 없는 계통을 흉내
win.rebuild()
pump(1.2)
check("판에서 빠져나왔나", win.grid_key != APP.LOAD_KEY, True)
check("「⚙ 부하」 단추도 사라졌나", gear("부하") is None, True)
APP.Proto.has_load = _orig_has_load

print("\n[6] 좁은 창에서 이 줄이 안 넘치나")
win.rebuild()
pump(1.2)
for W in (1512, 1194, 929):
    win.resize(W, 900)
    pump(1.0)
    sa = bar()
    over = max(0, sa.widget().sizeHint().width() - sa.viewport().width())
    check(f"창 {W}px 에서 넘치는 몫", over, 0)

print()
if fails:
    print(f"❌ 실패 {len(fails)}건: {fails}")
    sys.stdout.flush()
    app_engine.shutdown()
    os._exit(1)
print("DONE_GRID_PICK — 모두 통과")
sys.stdout.flush()
app_engine.shutdown()
os._exit(0)
