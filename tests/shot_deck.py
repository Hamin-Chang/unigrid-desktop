# -*- coding: utf-8 -*-
"""발표(2026-09-08 교수님 시연) 순서 그대로 찍는다.

    ~/venvs/unigrid-acdc/bin/python tests/shot_deck.py

  · `shot_all.py` 와 다른 점 = **발표 덩어리 순서**로 찍고, 1·2부를 한 계통
    (`ACDC_case24_MatACDC_24h`) 에서 다 뽑는다. 계통을 바꿀 때마다 흐름이 끊겨서다.
  · 가짜 화면이 아니라 **실제로 계산을 돌려** 찍는다 — 엔진이 필요하다.
  · 파일 이름 = `<부>_<번호>_<무엇>.png`.
"""
import os
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "shots_deck_20260908"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import warnings                                                   # noqa: E402
warnings.filterwarnings("ignore")
from PySide6.QtWidgets import (QApplication, QMessageBox,          # noqa: E402
                               QDialog)
from PySide6.QtCore import Qt                                      # noqa: E402

qapp = QApplication([])
import app as APP                                                  # noqa: E402

# 자동 실행이라 대화상자를 눌러 줄 사람이 없다.
_msg = []
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(
        lambda *a, **k: _msg.append(a[1] if len(a) > 1 else "")))

# exec() 로 여는 판은 사람이 닫을 때까지 멈춘다 → show() 로 바꾸고 참조를 잡아 둔다.
_opened = []
_real_exec = QDialog.exec


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
from load_case import load_case                                    # noqa: E402

W, H = 1600, 1000
win = APP.Proto()
win.resize(W, H)
win.show()

made, skipped = [], []
_part = ["0"]
_i = [0]


def pump(s=0.6):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


def part(p, title):
    _part[0] = p
    print("═" * 66)
    print(f"  {p}부 — {title}")
    print("═" * 66)


def shot(name, widget=None, wait=0.7):
    pump(wait)
    _i[0] += 1
    p = OUT / f"{_part[0]}_{_i[0]:02d}_{name}.png"
    (widget or win).grab().save(str(p))
    made.append(p.name)
    print(f"  📷 {p.name}")


def dlg_shot(name, call, wait=0.5):
    """exec() 로 여는 판을 열어 찍고 닫는다."""
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
    print(f"    ⚠️ '{name}' 탭이 없다 — 있는 탭: "
          f"{[APP._tab_base(tt.tabText(i)) for i in range(tt.count())]}")
    return False


def unfold():
    """그래프를 편 채로 둔다.

    🚨 표가 주인공인 탭(계통 데이터·점검)에 들어가면 `_fold_for_room` 이 그래프를
       접는다(`numbers=True`). 그 상태가 그대로 남아 **그래프 캡처 자리에 표가
       찍혔다**. `graph_kept` 를 세우면 앱이 자동으로 접지 않는다 —
       사람이 [그래프 펼치기] 를 누른 것과 같은 상태다.
    """
    win.graph_kept = True
    win.numbers = False
    win.numbers_auto = False
    win.numbers_why = ""


def graph(i):
    unfold()
    win.graph_tab = i
    win.rebuild()


def row_of(case, a, b, key="AC_Line_dat"):
    arr = SC._values(case, key)
    hit = [i for i, r in enumerate(arr) if (int(r[1]), int(r[2])) == (a, b)]
    return hit[0] if hit else None


C = REPO / "cases"
C24H = C / "ACDC_case24_MatACDC_24h.xlsx"
TAPCTRL = C / "ACDC_case24_tapctrl.xlsx"
SHUNTSTEP = C / "ACDC_case24_shuntstep.xlsx"
PHASECTRL = C / "ACDC_case24_phasectrl.xlsx"
SHUNTCTRL = C / "ACDC_case24_shuntctrl.xlsx"
P71 = C / "ACDC_71bus_3IC_parallel_24h.xlsx"
C118 = C / "AConly_case118.xlsx"
CIGRE24 = C / "ACDC_CIGRE_MVACMVDCLVDC_24h.xlsx"
DC21 = C / "DConly_21bus.xlsx"
GENLIM = C / "ACDC_71bus_L2_genlim.xlsx"
PSSE = C / "psse_ieee14.raw"
MPC = C / "matpower_ieee14.m"

t_all = time.time()

# ══════════════════════════════════════════════════════════════════════
part("1", "계통 하나로 다 된다 — case24 (AC 50 / DC 7 / IC 7 / 24시각)")

shot("시작화면", wait=1.0)
win.set_hot(True)
shot("시작화면_끌어다놓기", wait=0.5)
win.set_hot(False)

case24 = open_case(C24H)
print(f"    case24_24h: 풀림 {win.sol.converged} · 반복 {win.sol.iters}회 "
      f"· AC {win.sol.AC.shape} / DC {win.sol.DC.shape}")
shot("푼_직후_첫화면", wait=1.4)

tab("수렴")
shot("수렴_반복별_블록별_미스매치", wait=1.1)

tab("AC 결과")
for i, nm in enumerate(["전압·위상", "조류PQ_3D", "부하율", "단선도"]):
    graph(i)
    shot(f"그래프_{nm}", wait=1.4)

win.set_topo_zoom(2.0)
shot("단선도_확대_200퍼센트", wait=1.3)
win.set_topo_zoom(1.0)
win.set_violations(True)
shot("단선도_위반만_빨갛게", wait=1.3)
win.set_violations(False)
graph(0)

# ── 결과 표 7종
for nm, fn in [("AC 결과", "표_AC결과"), ("DC 결과", "표_DC결과"),
               ("선로 조류", "표_선로조류")]:
    tab(nm)
    shot(fn, wait=0.9)

win.set_vsc(True)
pump(0.4)
tt = getattr(win, "_tabs", None)
print("    VSC 켠 뒤 탭:",
      [APP._tab_base(tt.tabText(i)) for i in range(tt.count())])
for nm, fn in [("VSC 버스", "표_VSC버스"),
               ("VSC 그리드전력", "표_VSC그리드전력"),
               ("VSC 손실", "표_VSC손실")]:
    if tab(nm):
        shot(fn, wait=0.9)
win.set_vsc(False)

# ── 표를 다루는 세 가지
tab("AC 결과")
dlg_shot("열선택_판", win.pick_columns)

win.sort_by["AC 결과"] = (1, Qt.AscendingOrder)
tab("AC 결과")
shot("표_전압_낮은순_정렬", wait=0.9)
win.sort_by = {}

win.set_res_find("101 102 103 104")
tab("AC 결과")
shot("표_버스번호로_찾기", wait=0.9)
win.set_res_find("")

# ── 점검
tab("점검")
shot("점검_전압위반과_과부하선로", wait=1.1)


def _genlim():
    open_case(GENLIM)
    tab("점검")
    shot("점검_발전기_한계에_걸린_것", wait=1.1)
    open_case(C24H)                       # 되돌려 놓는다
guard("발전기 한계", _genlim)

# ── 내보내기 · 어두운 화면
def _export():
    d = APP.ExportDialog(win, win.c, win.mode, win.picked)
    d.show()
    shot("내보내기_무엇을_저장할까", d, wait=0.5)
    d.close()
guard("내보내기", _export)

win.dark = True
tab("AC 결과")
shot("어두운화면", wait=1.1)
win.dark = False
win.rebuild()

# ══════════════════════════════════════════════════════════════════════
part("2", "조건을 바꿔가며 따져본다")

tab("계통 데이터")
shot("계통데이터_고칠수있는칸만_흰색", wait=1.1)

dlg_shot("계통데이터_열선택_판", win.pick_grid_columns)

# ── IC 표
win.grid_key = "IC_dat"
tab("계통 데이터")
shot("IC표_7대", wait=1.0)


def _ic_off():
    """215-6 을 끈다 — 113-4 가 −116 MW 를 받는 장면.

    🚨 IC 표는 **0열 = AC 버스 · 1열 = DC 버스**다 (AC 선로는 1·2열이라 다르다).
       3열 = DC Control Mode (0=CP · 1=Droop · 2=CV). 107-1·113-4 만 2 이고,
       그 둘을 끄면 DC 망에 전압 기준이 없어져 **발산한다** — 끄면 안 되는 둘이다.
    """
    arr = SC._values(win.base_case, "IC_dat")
    print(f"    IC 목록: {[(int(r[0]), int(r[1]), int(r[3])) for r in arr]}")
    hit = [i for i, r in enumerate(arr)
           if (int(r[0]), int(r[1])) == (215, 6)]
    assert hit, "215-6 을 못 찾았다"
    r = hit[0]
    win.grid_key = "IC_dat"
    win.flip_row(r)
    tab("계통 데이터")
    shot("IC_215-6_끔_아직_계산전", wait=1.0)
    run_now()
    win.set_vsc(True)
    pump(0.4)
    tab("VSC 버스")
    shot("IC_끄고_푼_뒤_113-4가_부족분을_받는다", wait=1.0)
    win.set_vsc(False)
    tab("점검")
    shot("IC_끈_뒤_점검", wait=1.0)
guard("IC 끄기", _ic_off)

tab("시나리오")
shot("시나리오_한줄씩_쌓인다", wait=1.1)


def _overlay():
    win.set_mode("비교")
    win.set_axis("시나리오끼리")
    unfold()
    shot("비교_시나리오끼리_겹쳐그리기", wait=1.4)
    win.set_mode("스냅샷")
guard("시나리오끼리 비교", _overlay)

# ── 선로 끄기 · 부하 배율 · 되돌리기
win.grid_key = "AC_Line_dat"
r = row_of(win.base_case, 106, 110)
if r is not None:
    win.flip_row(r)
tab("계통 데이터")
shot("선로_켜고끄기", wait=1.0)

win.scale_loads(1.3)
pump(0.5)
tab("계통 데이터")
shot("부하_일괄증감_1점3배", wait=1.0)

win.undo_changes()
pump(0.4)
shot("되돌리기_아직_계산안한것만", wait=0.9)

win.reset_to_base()
pump(0.5)
tab("시나리오")
shot("원본으로_되돌아감", wait=1.0)

# ── AC 자동 조정 4종
A1 = [(TAPCTRL, "AC_Line_dat", "자동조정_변압기_탭"),
      (PHASECTRL, "AC_Line_dat", "자동조정_위상"),
      (SHUNTCTRL, "AC_Bus_dat", "자동조정_션트_SVC"),
      (SHUNTSTEP, "AC_Bus_dat", "자동조정_션트_계단")]
for p, key, label in A1:
    if not p.exists():
        print(f"    ⚠️ 없음: {p.name}")
        continue

    def _a1(p=p, key=key, label=label):
        open_case(p)
        win.grid_key = APP.ADJ.KEY
        tab("계통 데이터")
        shot(f"{label}_패널", wait=1.1)
        tab("점검")
        shot(f"{label}_결과는_점검탭에", wait=1.1)
    guard(label, _a1)

# ══════════════════════════════════════════════════════════════════════
part("3", "시간에 따라 본다")


def _dyn24():
    open_case(C24H)
    nt = win.sol.AC.shape[2]
    print(f"    case24_24h: 시각 {nt}개")
    shot("24시각_스냅샷_시간을_고른다", wait=1.3)
    win.set_time(min(18, nt - 1))
    pump(0.4)
    shot("18시_피크로_옮긴_뒤", wait=1.2)
    win.set_time(0)
    win.set_mode("다이나믹")
    unfold()
    for i, nm in enumerate(["전압·위상", "주파수", "단선도"]):
        graph(i)
        shot(f"다이나믹_{nm}", wait=1.4)
    graph(0)
    tab("손실")
    shot("표_손실_시간축_전체", wait=1.0)
    win.set_mode("비교")
    unfold()
    for ax, nm in [("버스끼리", "비교_버스끼리"), ("시간끼리", "비교_시간끼리")]:
        win.set_axis(ax)
        unfold()
        shot(nm, wait=1.4)
    win.set_mode("스냅샷")
guard("case24 24시각", _dyn24)


def _freq():
    """슬랙이 없는 계통 — 주파수가 부하 따라 움직인다."""
    open_case(P71)
    import numpy as np
    f = np.asarray(win.sol.freq).ravel()   # 이미 Hz 다 (pu 아니다)
    print(f"    71bus 주파수 {f.min():.4f} ~ {f.max():.4f} Hz")
    win.set_mode("다이나믹")
    unfold()
    graph(1)
    shot("71bus_슬랙없는계통_주파수가_움직인다", wait=1.5)
    win.set_mode("스냅샷")
guard("71bus 주파수", _freq)

# ══════════════════════════════════════════════════════════════════════
part("4", "어디까지 담고 어디까지 푸나")


def _nr118():
    open_case(C118)
    print(f"    case118 NR: 반복 {win.sol.iters}회")
    tab("수렴")
    shot("case118_NewtonRaphson_4회", wait=1.1)
guard("case118 NR", _nr118)


def _gs118():
    open_case(C118, method="gs")
    print(f"    case118 GS: 반복 {win.sol.iters}회")
    tab("수렴")
    shot("case118_GaussSeidel_2704회", wait=1.1)
guard("case118 GS", _gs118)


def _curve():
    open_case(C118)
    win.set_task("PV·QV 곡선")
    shot("곡선_설정화면", wait=1.1)
    cur = app_engine.curve(win.curve_case(), [], [])
    win._curve_done(cur)
    shot("곡선_결과_PV곡선", wait=1.5)
    win.set_task("조류계산")
guard("PV·QV 곡선", _curve)


def _cigre():
    open_case(CIGRE24)
    win.grid_key = "DCDC_Conv_dat"
    tab("계통 데이터")
    shot("CIGRE_DCDC_변환기표", wait=1.1)
    graph(3)
    tab("AC 결과")
    shot("CIGRE_단선도_MVAC_MVDC_LVDC", wait=1.4)
    graph(0)
guard("CIGRE DC/DC", _cigre)


def _convert():
    d = APP.ConvertDialog(win, win.c)
    d.show()
    shot("남의형식_PSSE_MATPOWER_MatACDC", d, wait=0.5)
    d.close()
guard("형식 변환 판", _convert)


def _psse():
    open_case(PSSE)
    shot("PSSE_raw_를_그대로_열었다", wait=1.3)
guard("PSS/E raw", _psse)


def _mpc():
    open_case(MPC)
    shot("MATPOWER_m_을_그대로_열었다", wait=1.3)
guard("MATPOWER m", _mpc)


def _dconly():
    open_case(DC21)
    shot("DC전용_21버스", wait=1.3)
guard("DConly", _dconly)


def _about():
    d = APP.AboutDialog(win, win.c)
    d.show()
    shot("정보창_판번호와_무엇으로_만들었나", d, wait=0.5)
    d.close()
guard("정보 창", _about)

# ══════════════════════════════════════════════════════════════════════
print("═" * 66)
print(f"  찍은 것 {len(made)}장 · 건너뛴 것 {len(skipped)}개 "
      f"· {time.time() - t_all:.0f}초")
if skipped:
    for s in skipped:
        print(f"    ⚠️ {s}")
print(f"  → {OUT}")
