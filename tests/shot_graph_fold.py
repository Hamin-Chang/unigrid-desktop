# -*- coding: utf-8 -*-
"""계통을 바꿔 계산하면 그래프를 접고 표를 넓게 연다 (2026-08-15 사용자 확정).

사용자: *"계통을 바꿔서 계산하면 그냥 그래프를 일단 끄고, 사용자가 키고 싶으면
그때 그래프를 띄우고 표는 작게 줄이자"*

보는 것
    1) 파일을 처음 열었을 때는 **그래프가 펼쳐져** 있나 (작은 계통)
    2) 조건을 바꿔 계산하면 **접히고**, 표가 넓어지나
    3) 접힌 이유를 화면이 **맞게** 말하나 (큰 계통 때 문구를 그대로 쓰면 거짓말이 된다)
    4) [그래프 펼치기] 를 누르면 펼쳐지고 표가 **도로 줄어드나**
    5) 🚨 그다음 조건을 또 바꿔 계산해도 **다시 안 접히나**
       (조건 하나 바꿀 때마다 도로 접히면 못 쓴다 — 2026-08-06 에 큰 계통 자동 접기에서
        이미 정한 것과 같은 이유)
    6) 새 파일을 열면 그 기억이 **초기화되나**
    7) 🚨 펼쳤을 때 **되접는 길**이 그래프 자리에 있나
       (펼치기는 그래프 자리에 있는데 접기는 저 멀리 [숫자만] 뿐이었다 — 사용자 지적)
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
from PySide6.QtWidgets import QApplication, QMessageBox      # noqa: E402

qapp = QApplication([])
import app as APP                                            # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                            # noqa: E402
import scenario as SC                                        # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/AConly_case14_v2.xlsx"
fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<46} {got}")
    else:
        print(f"  ❌ {label:<46} {got}  (바라던 값 {want})")
        fails.append(label)


def pump(s=0.4):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


def table_h() -> int:
    """표가 받은 높이 (스플리터 아래쪽). 접혀 있으면 그래프 몫이 없다."""
    return win._split.sizes()[-1] if win._split is not None else 0


def open_case(path, tab="AC 결과"):
    """⚠️ 기본 탭이 **결과 탭**이다 (2026-08-18).

    예전에는 늘 `계통 데이터` 탭으로 열었는데, 그 탭은 이제 **표에 자리를 다 주려고
    그래프를 접는 탭**이 됐다(아래 [8]). 거기서 *"처음 열면 펼쳐져 있나"* 를 물으면
    새 규칙과 부딪힌다. 그 물음은 그래프를 펴 두는 결과 탭에서 물어야 맞다.
    """
    case = load_case(str(path))
    win.thread = Fake(case)
    win._last_path = str(path)
    win._solved(app_engine.solve(case))
    win.table_tab = tab
    win.rebuild()
    pump()
    return case


def calc(row):
    """선로 하나를 끄고 [이 조건으로 계산] 이 하는 일 그대로."""
    win.grid_key = "AC_Line_dat"
    win.flip_row(row)
    pump(0.2)
    pend = win.applied + win.changes
    win._pending, win._pending_new = pend, list(win.changes)
    win._solved(app_engine.solve(SC.apply(win.base_case, pend)))
    win.rebuild()
    pump()


win = APP.Proto()
win.resize(1414, 950)
win.show()

open_case(CASE)
print("\n[1] 파일을 처음 열면 그래프가 펼쳐져 있나 (14버스라 작은 계통)")
check("접혔나", win.numbers, False)
h_open = table_h()
print(f"    표 몫 {h_open}px")

print("\n[2] 조건을 바꿔 계산하면 접히고 표가 넓어지나")
calc(3)
h_fold = table_h()
check("접혔나", win.numbers, True)
check("표가 넓어졌나", h_fold > h_open, True)
print(f"    표 몫 {h_open} → {h_fold}px")

print("\n[3] 접힌 이유를 맞게 말하나")
check("이유", win.numbers_why, "changed")

print("\n[4] [그래프 펼치기] 를 누르면 펼쳐지고 표가 도로 줄어드나")
win.set_numbers(False)
pump()
h_show = table_h()
check("접혔나", win.numbers, False)
check("표가 줄었나", h_show < h_fold, True)
print(f"    표 몫 {h_fold} → {h_show}px")

print("\n[5] 🚨 그 뒤 조건을 또 바꿔 계산해도 다시 안 접히나")
calc(4)
check("접혔나", win.numbers, False)
check("직접 펼친 기억", win.graph_kept, True)

print("\n[6] 새 파일을 열면 그 기억이 초기화되나")
open_case(CASE)
check("직접 펼친 기억", win.graph_kept, False)

print("\n[7] 🚨 펼쳤을 때 그래프 자리에 「접기」가 있나")
calc(5)
win.set_numbers(False)
pump()
from PySide6.QtWidgets import QTabWidget, QPushButton   # noqa: E402
corner = [w.cornerWidget() for w in win.findChildren(QTabWidget)
          if w.cornerWidget() is not None]
# ⚠️ 구석에 **단추가 하나뿐이라고 보면 안 된다** (2026-08-28). 전압·위상 탭에
#    [전압|위상각] 전환 단추가 생기며 구석이 「묶음 위젯」이 됐다. 예전 방식이면
#    [그래프 접기] 를 통째로 놓친다.
names = []
for w in corner:
    if isinstance(w, QPushButton):
        names.append(w.text())
    else:
        names += [b.text() for b in w.findChildren(QPushButton)]
print(f"    그래프 탭 구석의 단추 {names}")
check("접기 단추", any("접기" in n for n in names), True)
if any("접기" in n for n in names):
    # 위 `names` 와 같은 이유로 **묶음 안까지** 뒤진다 (2026-08-28)
    def _all_btns():
        for w in corner:
            if isinstance(w, QPushButton):
                yield w
            else:
                yield from w.findChildren(QPushButton)
    btn = next(w for w in _all_btns() if "접기" in w.text())
    btn.click()
    pump()
    check("눌렀더니 접혔나", win.numbers, True)

print("\n[8] 🚨 표를 고치는 탭에서는 그래프를 접고 표에 자리를 다 주나 (2026-08-18)")
# 까닭 — 값을 고치러 들어온 자리이므로 **표에 자리를 다 준다**. 그래프는 결과 탭에서 본다.
# ⚠️ 2026-08-28 에 근거가 바뀌었다. 예전에는 「그래프 최소 높이(두 장 쌓기 425)가 표 몫을
#    뺀 나머지(34%·271px)에 안 들어간다」는 셈이었는데, 같은 날 전압·위상을 한 장씩 보이게
#    바꾸자 그 최소가 150 으로 내려가 셈이 뒤집혀 **표가 23줄 → 14줄로 줄었다**.
#    ⇒ 이제 자리를 재지 않고 **탭이 하는 일**로 접는다(`_graph_fits`).
open_case(CASE)                                   # 결과 탭에서 시작 (그래프 펼침)
check("결과 탭 — 펼쳐져 있나", win.numbers, False)
h_res = table_h()
win._table_tab_changed("계통 데이터", win._split)
pump()
check("계통 데이터 탭 — 접혔나", win.numbers, True)
check("접힌 이유", win.numbers_why, "narrow")
h_grid = table_h()
check("표가 넓어졌나", h_grid > h_res, True)
print(f"    표 몫 {h_res} → {h_grid}px")

print("\n[9] 자리가 나는 탭으로 돌아오면 도로 펴지나")
win._table_tab_changed("AC 결과", win._split)
pump()
check("펴졌나", win.numbers, False)
check("이유도 지워졌나", win.numbers_why, "")

print("\n[10] 🚨 직접 접은 것은 탭을 옮겨도 안 펴지나 (자동과 직접을 섞지 않는다)")
win.set_numbers(True)                             # 직접 접기
pump()
check("직접 접었을 때 이유는 비어 있나", win.numbers_why, "")
win._table_tab_changed("계통 데이터", win._split)
pump()
win._table_tab_changed("AC 결과", win._split)
pump()
check("여전히 접혀 있나", win.numbers, True)

print("\n[11] 🚨 어느 탭에서 펼쳐도 읽을 수 있는 크기를 주나 (2026-08-18)")
# 예전에는 이 우선권이 계통 데이터 탭에만 걸려 있어, 결과 탭에서 펼치면 393px 밖에
# 못 받아 **펼쳐 놓고도 세로축이 뭉개졌다.**
# ⚠️ 잣대가 425 에서 **평소 높이**로 바뀌었다 (2026-08-28). 425 는 전압·위상을
#    **두 장 쌓았을 때** 세로축이 안 뭉개지는 값이었는데, 그날 한 장씩 보이게
#    바꾸면서 한 장이 그만큼을 통째로 쓴다. 이제 잣대는 「한 장짜리 평소 높이」다.
floor2 = APP.Proto.GRAPH_WANT[1]
for tab in ("AC 결과", "점검", "계통 데이터"):
    open_case(CASE, tab)
    calc(3)                                       # 조건을 바꿔 자동으로 접히게
    win.set_numbers(False)                        # 사용자가 펼친다
    pump()
    g = win._split.sizes()[0]
    check(f"{tab} — 펼치면 {floor2}px 이상인가", g >= floor2, True)
    print(f"    그래프 {g}px")

print("\n[12] 🚨 표가 주인공인 탭은 **전부** 접히나 (2026-08-18)")
# 목록 = APP.Proto.TABLE_FIRST. 계통 데이터(표를 고치는 곳) · 점검(무엇이 걸렸는지 읽는 곳).
# 점검을 넣은 까닭은 자리 계산이 아니라 실측이다 — 표 셋이 352px 에 안 들어가
# **한 표도 온전히 안 보였다**(다 보이는 표 0개 → 접으면 2개).
open_case(CASE)
h_res = table_h()
for tab in APP.Proto.TABLE_FIRST:
    win._table_tab_changed(tab, win._split)
    pump()
    check(f"{tab} — 접혔나", win.numbers, True)
    check(f"{tab} — 이유", win.numbers_why, "narrow")
    print(f"    표 몫 {h_res} → {table_h()}px")
    win._table_tab_changed("AC 결과", win._split)
    pump()
    check("결과 탭으로 오면 도로 펴지나", win.numbers, False)

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if fails else 0)
