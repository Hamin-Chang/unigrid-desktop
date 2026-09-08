# -*- coding: utf-8 -*-
"""직접 써보기 체크리스트용 — **발표 덱이 안 다룬 기능**을 찍는다 (2026-09-08).

    ~/venvs/unigrid-acdc/bin/python tests/shot_checklist.py

  덱(`shot_deck.py`)은 「화면이 이렇게 생겼다」를 보여주는 자료라, **눌러야 알 수 있는
  것**이 빠져 있다. 이 스크립트는 그 나머지를 찍는다 — 정렬 되돌리기, 시나리오
  이름 고치기, QV 곡선, 실제 저장 같은 것들.
"""
import os
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "shots_check_20260908"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import warnings                                                   # noqa: E402
warnings.filterwarnings("ignore")
from PySide6.QtWidgets import (QApplication, QMessageBox,          # noqa: E402
                               QDialog, QInputDialog, QFileDialog)
from PySide6.QtCore import Qt                                      # noqa: E402

qapp = QApplication([])
import app as APP                                                  # noqa: E402

_msg = []
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(
        lambda *a, **k: _msg.append(a[1] if len(a) > 1 else "")))

# exec() 판을 show() 로 바꿔 잡아 둔다
_opened = []


def _fake_exec(self):
    _opened.append(self)
    self.show()
    end = time.time() + 0.4
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)
    return 0


QDialog.exec = _fake_exec

import scenario as SC                                              # noqa: E402
import app_engine                                                  # noqa: E402
import adjust_panel as ADJP                                        # noqa: E402
from load_case import load_case                                    # noqa: E402

W, H = 1600, 1000
win = APP.Proto()
win.resize(W, H)
win.show()

made, skipped = [], []
_i = [0]


def pump(s=0.6):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


def shot(name, widget=None, wait=0.7):
    pump(wait)
    _i[0] += 1
    p = OUT / f"{_i[0]:02d}_{name}.png"
    (widget or win).grab().save(str(p))
    made.append(p.name)
    print(f"  📷 {p.name}")


def dlg_shot(name, call, wait=0.5):
    _opened.clear()
    try:
        call()
    except Exception as exc:
        skipped.append(name)
        print(f"    ⚠️ {name} 건너뜀 — {str(exc).splitlines()[0]}")
        return
    if not _opened:
        skipped.append(name)
        print(f"    ⚠️ {name} — 판이 안 떴다")
        return
    d = _opened[-1]
    shot(name, d, wait)
    d.close()
    pump(0.2)


def guard(label, fn):
    try:
        fn()
    except Exception as exc:
        skipped.append(label)
        print(f"    ⚠️ {label} 건너뜀 — {str(exc).splitlines()[0]}")
        traceback.print_exc(limit=2)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


def open_case(path, method="nr"):
    case = load_case(str(path))
    win.thread = Fake(case)
    win._last_path = str(path)
    sol = app_engine.solve(case, method=method)
    sol.method = method
    win._solved(sol)
    pump(0.5)
    return case


def run_now():
    win._pending = win.applied + win.changes
    sol = app_engine.solve(SC.apply(win.base_case, win._pending))
    win.thread = Fake(win.base_case)
    win._solved(sol)
    win.rebuild()
    pump(0.5)


def tab(name):
    win.table_tab = name
    win.rebuild()
    tt = getattr(win, "_tabs", None)
    if tt is None:
        return False
    for i in range(tt.count()):
        if APP._tab_base(tt.tabText(i)) == name:
            tt.setCurrentIndex(i)
            return True
    print(f"    ⚠️ '{name}' 탭이 없다 — {[APP._tab_base(tt.tabText(i)) for i in range(tt.count())]}")
    return False


def unfold():
    win.graph_kept = True
    win.numbers = False
    win.numbers_auto = False
    win.numbers_why = ""


def graph(i):
    unfold()
    win.graph_tab = i
    win.rebuild()


def head(t):
    print("═" * 62)
    print(f"  {t}")
    print("═" * 62)


C = REPO / "cases"
C24H = C / "ACDC_case24_MatACDC_24h.xlsx"
CIGRE24 = C / "ACDC_CIGRE_MVACMVDCLVDC_24h.xlsx"
C118 = C / "AConly_case118.xlsx"
MPC = C / "matpower_ieee14.m"
TAPCTRL = C / "ACDC_case24_tapctrl.xlsx"

t0 = time.time()

# ══════════════════════════════════════════════════════════════════════
head("A. 시작 화면 — 최근 연 파일")
# 앞선 캡처들이 이미 파일을 열었으므로 기록이 쌓여 있다
shot("시작화면_최근_연_파일", wait=1.0)


def _eula():
    d = APP.AboutDialog(win, win.c)
    d.show()
    pump(0.4)
    # 「사용 조건 보기」 를 눌렀을 때
    from PySide6.QtWidgets import QPushButton
    for b in d.findChildren(QPushButton):
        if "사용 조건" in b.text():
            _opened.clear()
            b.click()
            pump(0.5)
            if _opened:
                shot("EULA_사용조건_보기", _opened[-1], wait=0.4)
                _opened[-1].close()
            else:
                shot("EULA_누른_뒤", d, wait=0.4)
            break
    d.close()
guard("사용 조건 보기", _eula)

# ══════════════════════════════════════════════════════════════════════
head("B. 표 다루기 — 정렬·찾기 되돌리기, 자세히 보기")
case = open_case(C24H)

win.sort_by["AC 결과"] = (1, Qt.AscendingOrder)
tab("AC 결과")
shot("정렬한_상태_띠에_원래순서로_단추", wait=1.0)
win._clear_sort("AC 결과")
pump(0.4)
tab("AC 결과")
shot("원래_순서로_되돌린_뒤", wait=0.9)

win.set_res_find("101 102 103")
tab("AC 결과")
shot("찾기_켠_상태_띠에_전부보기_단추", wait=1.0)
win.set_res_find("")
pump(0.4)
shot("전부_보기로_되돌린_뒤", wait=0.9)


def _gocheck():
    tab("AC 결과")
    pump(0.4)
    win.go_check()          # 표 위 띠의 「자세히 보기 →」
    pump(0.6)
    shot("자세히_보기_누르면_점검탭으로", wait=1.0)
guard("자세히 보기", _gocheck)

# ══════════════════════════════════════════════════════════════════════
head("C. 계통 데이터 — 값 고치기 · DC 쪽 켜고 끄기")
win.grid_key = "AC_Line_dat"
tab("계통 데이터")
shot("AC선로표_흰칸이_고칠수_있는_칸", wait=1.0)


def _edit_cell():
    """표 칸 값을 실제로 고친다 (사람이 타이핑한 것과 같은 길)."""
    arr = SC._values(win.base_case, "AC_Line_dat")
    r = 0
    # 저항 열(6열쯤)을 조금 바꾼다 — `Cell` 로 얹는다
    ch = SC.Cell(table="AC_Line_dat", row=r, col=6,
                 value=float(arr[r][6]) * 1.5, label="AC 선로 저항")
    win.changes.append(ch)
    win.rebuild()
    tab("계통 데이터")
    shot("값을_고친_뒤_바뀐_칸이_표시된다", wait=1.0)
    win.undo_changes()
    pump(0.3)
guard("값 고치기", _edit_cell)


def _dcgen():
    win.grid_key = "DC_gen_dat"
    tab("계통 데이터")
    shot("DC발전기표", wait=1.0)
guard("DC 발전기 표", _dcgen)


def _dcdc():
    open_case(CIGRE24)
    win.grid_key = "DCDC_Conv_dat"
    tab("계통 데이터")
    shot("DCDC표_Status로_끈다", wait=1.0)
    arr = SC._values(win.base_case, "DCDC_Conv_dat")
    if len(arr):
        win.flip_row(0)
        tab("계통 데이터")
        shot("DCDC_하나_끈_뒤", wait=1.0)
        win.reset_to_base()
        pump(0.4)
guard("DC/DC 켜고 끄기", _dcdc)

# ══════════════════════════════════════════════════════════════════════
head("D. 부하 배율 되돌리기")
open_case(C24H)
win.scale_loads(1.3)
pump(0.5)
win.grid_key = APP.LOAD_KEY
tab("계통 데이터")
shot("부하배율_1점3배_원래대로_단추가_보인다", wait=1.0)
win.scale_loads(1.0)
pump(0.5)
tab("계통 데이터")
shot("원래대로_×1_누른_뒤", wait=1.0)

# ══════════════════════════════════════════════════════════════════════
head("E. 시나리오 — 이름 고치기 · 지우기 · 겹쳐 볼 것 고르기")
win.grid_key = "AC_Line_dat"
arr = SC._values(win.base_case, "AC_Line_dat")
hit = [i for i, r in enumerate(arr) if (int(r[1]), int(r[2])) == (101, 102)]
if hit:
    win.flip_row(hit[0])
guard("바꾼 뒤 계산 1", run_now)
win.scale_loads(1.15)
pump(0.4)
guard("바꾼 뒤 계산 2", run_now)
tab("시나리오")
shot("시나리오_세_줄_쌓인_상태", wait=1.1)


def _rename():
    """이름 바꾸기 판 — `QInputDialog` 라 따로 띄운다."""
    items = list(win.book.items)
    if not items:
        raise RuntimeError("시나리오가 없다")
    d = QInputDialog(win)
    d.setWindowTitle("이름 바꾸기")
    d.setLabelText("시나리오 이름")
    d.setTextValue(items[-1].name)
    d.setStyleSheet(win.styleSheet())
    d.show()
    shot("시나리오_이름_바꾸기_판", d, wait=0.5)
    d.close()
guard("이름 바꾸기", _rename)


def _overlay_pick():
    win.set_mode("비교")
    win.set_axis("시나리오끼리")
    unfold()
    items = list(win.book.items)
    for i in range(min(2, len(items))):
        win.toggle_overlay(i, True)
    pump(0.5)
    shot("겹쳐_볼_시나리오를_체크한다", wait=1.3)
guard("겹쳐 볼 것 체크", _overlay_pick)


def _cmp_pick():
    win.set_mode("비교")
    win.set_axis("버스끼리")
    unfold()
    shot("비교_버스_고르개", wait=1.3)
    win.set_mode("스냅샷")
guard("비교 고르개", _cmp_pick)


def _drop():
    items = list(win.book.items)
    if len(items) >= 2:
        win.drop_scenario(items[-1])
        pump(0.5)
        tab("시나리오")
        shot("시나리오_하나_지운_뒤", wait=1.0)
guard("시나리오 지우기", _drop)

# ══════════════════════════════════════════════════════════════════════
head("F. AC 자동 조정을 새로 건다")


def _add_adj():
    open_case(C24H)
    win.grid_key = ADJP.KEY
    tab("계통 데이터")
    shot("조정이_하나도_없는_계통의_패널", wait=1.1)
    dlg_shot("조정_추가_판", lambda: ADJP.add_dialog(win))
guard("+ 조정 추가", _add_adj)

# ══════════════════════════════════════════════════════════════════════
head("G. PV·QV 곡선 — QV 쪽")


def _qv():
    open_case(C118)
    win.set_task("PV·QV 곡선")
    pump(0.5)
    cur = app_engine.curve(win.curve_case(), [], [])
    win._curve_done(cur)
    unfold()
    shot("PV곡선", wait=1.4)
    for name in ("QV", "QV 곡선", "Q-V"):
        try:
            win.set_curve_pick(name)
            pump(0.5)
            break
        except Exception:
            continue
    unfold()
    shot("QV곡선으로_바꾼_뒤", wait=1.4)
    win.set_task("조류계산")
guard("QV 곡선", _qv)

# ══════════════════════════════════════════════════════════════════════
head("H. 엑셀로 만들기 · 내보내기 · 창 최소 크기")


def _convert():
    d = APP.ConvertDialog(win, win.c)
    d.show()
    shot("엑셀로_만들기_판_비어있음", d, wait=0.5)
    # 파일을 넣은 상태
    try:
        d._ac = str(MPC)
        if hasattr(d, "_refresh"):
            d._refresh()
        elif hasattr(d, "refresh"):
            d.refresh()
        pump(0.4)
        shot("엑셀로_만들기_파일을_넣은_뒤", d, wait=0.5)
    except Exception as exc:
        print(f"    ⚠️ 파일 넣기 못 함 — {exc}")
    d.close()
guard("엑셀로 만들기", _convert)


def _export():
    open_case(C24H)
    d = APP.ExportDialog(win, win.c, win.mode, win.picked)
    d.show()
    shot("내보내기_판_무엇을_저장할까", d, wait=0.5)
    d.close()
guard("내보내기 판", _export)


def _small():
    win.resize(929, 704)
    pump(0.8)
    win.rebuild()
    shot("창을_최소_929×704_로_줄인_모습", wait=1.4)
    win.resize(W, H)
    pump(0.6)
    win.rebuild()
guard("최소 창 크기", _small)


def _folded():
    open_case(C24H)
    win.side_open = False
    win.rebuild()
    shot("왼쪽_줄을_접은_모습", wait=1.2)
    win.side_open = True
    win.rebuild()
guard("사이드바 접기", _folded)

# ══════════════════════════════════════════════════════════════════════
print("═" * 62)
print(f"  찍은 것 {len(made)}장 · 건너뛴 것 {len(skipped)}개 · {time.time()-t0:.0f}초")
for s in skipped:
    print(f"    ⚠️ {s}")
print(f"  → {OUT}")
