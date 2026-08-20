# -*- coding: utf-8 -*-
"""앱의 **모든 기능**을 차례로 밟으며 찍는다 (2026-08-20 사용자 요청).

    ~/venvs/unigrid-acdc/bin/python tests/shot_all.py

  · 기능 목록은 교수님께 드린 소개 자료(Artifact) 를 그대로 따라간다.
  · 가짜 화면이 아니라 **실제로 계산을 돌려** 찍는다 — 엔진이 필요하다.
  · 대화상자는 exec() 로 열면 사람이 눌러 줄 때까지 멈추므로 show() 로 띄우고 찍는다.

🚨 케이스를 고르는 데 까닭이 있다 (1차에서 헛 찍은 것들)
  · CIGRE 는 방사형이라 **선로를 하나만 꺼도 발산**한다 → 켜고끄기는 24버스로.
  · CIGRE 결과에는 **VSC_bus 가 없다**(엔진이 안 돌려준다) → VSC 표는 24버스로.
  · 발전기 한계에 걸리는 것은 71버스 genlim 케이스뿐 → 점검 탭은 두 케이스로 나눠 찍는다.
"""
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/"
           "Phase A_Balance/newest/v14")
OUT = REPO / "shots_20260820"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import warnings                                                   # noqa: E402
warnings.filterwarnings("ignore")
from PySide6.QtWidgets import QApplication, QMessageBox            # noqa: E402
from PySide6.QtCore import Qt                                      # noqa: E402

qapp = QApplication([])
import app as APP                                                  # noqa: E402
_dlg = []
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(
        lambda *a, **k: _dlg.append(a[1] if len(a) > 1 else "")))
import scenario as SC                                              # noqa: E402
import app_engine                                                  # noqa: E402
import engine_path                                                 # noqa: E402
from load_case import load_case                                    # noqa: E402

W, H = 1600, 1000
win = APP.Proto()
win.resize(W, H)
win.show()

_i = [0]
made = []
skipped = []


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


def guard(label, fn):
    try:
        fn()
    except Exception as exc:
        skipped.append(label)
        print(f"    ⚠️ {label} 건너뜀 — {str(exc).splitlines()[0]}")


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


def graph(i):
    win.graph_tab = i
    win.rebuild()


def row_of(case, a, b, key="AC_Line_dat"):
    arr = SC._values(case, key)
    hit = [i for i, r in enumerate(arr) if (int(r[1]), int(r[2])) == (a, b)]
    return hit[0] if hit else None


def head(t):
    print("═" * 62)
    print(f"  {t}")
    print("═" * 62)


CIGRE = REPO / "cases/ACDC_CIGRE_MVACMVDCLVDC.xlsx"
C24 = REPO / "cases/ACDC_case24_MatACDC.xlsx"
C14 = REPO / "cases/AConly_case14.xlsx"
GENLIM = REPO / "cases/ACDC_71bus_L2_genlim.xlsx"
H24 = V14 / "ACDC_CIGRE_MVACMVDCLVDC_24h.xlsx"

# ══════════════════════════════════════════════════════════════
head("A. 시작 · 파일 열기")
shot("시작화면", wait=1.0)
win.set_hot(True)
shot("시작화면_끌어다놓기", wait=0.5)
win.set_hot(False)

d = APP.ConvertDialog(win, win.c)
d.show()
shot("다른형식_불러오기_PSSE_MATPOWER_MatACDC", d, wait=0.4)
d.close()

d = APP.AboutDialog(win, win.c)
d.show()
shot("정보창_무엇으로_만들었나", d, wait=0.4)
d.close()

# ══════════════════════════════════════════════════════════════
head("B. 푼다 — Newton-Raphson (AC/DC 혼합)")
open_case(CIGRE)
print(f"    CIGRE: 풀림 {win.sol.converged} · 반복 {win.sol.iters}회 "
      f"· AC {win.sol.AC.shape[0]} / DC {win.sol.DC.shape[0]}버스")
shot("조류계산_결과_첫화면", wait=1.2)
tab("수렴")
shot("수렴탭_반복별_블록별_미스매치", wait=1.0)

# ══════════════════════════════════════════════════════════════
head("C. 본다 — 그래프 네 가지")
tab("AC 결과")
for i, nm in enumerate(["전압·위상", "조류PQ_3D", "부하율", "토폴로지"]):
    graph(i)
    shot(f"그래프_{nm}", wait=1.3)
win.set_topo_zoom(2.0)
shot("계통도_확대_200퍼센트", wait=1.2)
win.set_topo_zoom(1.0)
win.set_violations(True)
shot("계통도_위반보기", wait=1.2)
win.set_violations(False)
graph(0)

# ══════════════════════════════════════════════════════════════
head("D. 점검 — 위반 네 가지")
tab("점검")
shot("점검탭_전압위반과_과부하선로", wait=1.0)


def _genlim():
    open_case(GENLIM)
    tab("점검")
    shot("점검탭_발전기_한계에_걸린_것", wait=1.1)
guard("발전기 한계 케이스", _genlim)

# ══════════════════════════════════════════════════════════════
head("E. 본다 — 결과 표 (24버스 · IC 7대)")
case24 = open_case(C24)
tt = getattr(win, "_tabs", None)
print("    지금 있는 탭:",
      [APP._tab_base(tt.tabText(i)) for i in range(tt.count())])
for nm, fn in [("AC 결과", "표_AC결과"), ("DC 결과", "표_DC결과"),
               ("선로 조류", "표_선로조류")]:
    tab(nm)
    shot(fn, wait=0.9)

win.set_vsc(True)
pump(0.4)
tt = getattr(win, "_tabs", None)
print("    VSC 켠 뒤 탭:",
      [APP._tab_base(tt.tabText(i)) for i in range(tt.count())])
if tab("VSC 버스"):
    shot("표_VSC버스_변환기_주입과_손실", wait=0.9)
win.set_vsc(False)

win.sort_by["AC 결과"] = (1, Qt.AscendingOrder)
tab("AC 결과")
shot("표_전압_낮은순으로_정렬", wait=0.9)
win.sort_by = {}

win.set_res_find("101 102 103 104")
tab("AC 결과")
shot("표_버스번호로_찾기", wait=0.9)
win.set_res_find("")

win.dark = True
tab("AC 결과")
shot("어두운화면", wait=1.0)
win.dark = False
win.rebuild()

d = APP.ExportDialog(win, win.c, win.mode, win.picked)
d.show()
shot("내보내기_엑셀_다섯종과_그림", d, wait=0.4)
d.close()

# ══════════════════════════════════════════════════════════════
head("F. 계통을 바꾼다 — 사람이 바꾼다")
tab("계통 데이터")
shot("계통데이터_고칠수있는칸만_흰색", wait=1.0)

r = row_of(case24, 106, 110)
win.flip_row(r)
tab("계통 데이터")
shot("선로_켜고끄기_아직_계산전", wait=0.9)
guard("바꾼 뒤 계산", run_now)
tab("시나리오")
shot("시나리오_한줄씩_쌓인다", wait=1.0)


def _overlay():
    win.set_mode("비교")
    win.set_axis("시나리오끼리")
    shot("비교_시나리오끼리_겹쳐그리기", wait=1.3)
    win.set_mode("스냅샷")
guard("시나리오끼리 비교", _overlay)

win.scale_loads(1.3)
pump(0.5)
tab("계통 데이터")
shot("부하_일괄증감_1점3배", wait=1.0)

win.undo_changes()
pump(0.4)
shot("되돌리기_아직_계산안한_것만", wait=0.9)

win.reset_to_base()
pump(0.5)
tab("시나리오")
shot("원본으로_되돌아감", wait=1.0)

# ══════════════════════════════════════════════════════════════
head("G. 계통을 바꾼다 — 계산이 정한다 (A1)")
A1 = [("ACDC_case24_tapctrl.xlsx", "AC_Line_dat", "A1_변압기_탭조정"),
      ("ACDC_case24_phasectrl.xlsx", "AC_Line_dat", "A1_위상조정기"),
      ("ACDC_case24_shuntctrl.xlsx", "AC_Bus_dat", "A1_션트조정_SVC"),
      ("ACDC_case24_tapstep.xlsx", "AC_Line_dat", "A1_계단조정")]
for fn, key, label in A1:
    p = REPO / "cases" / fn
    if not p.exists():
        print(f"    ⚠️ 없음: {fn}")
        continue

    def _a1(p=p, key=key, label=label):
        open_case(p)
        win.grid_key = key
        tab("계통 데이터")
        shot(label, wait=1.0)
        tab("점검")
        shot(f"{label}_결과는_점검탭에_카드로", wait=1.0)
    guard(label, _a1)

# ══════════════════════════════════════════════════════════════
head("H. AC 전용 — Gauss-Seidel · PV·QV 곡선")


def _nr14():
    open_case(C14)
    tab("수렴")
    shot("해법고르기_AC전용이면_GS도_고를수있다", wait=1.0)
guard("case14 Newton", _nr14)


def _gs():
    open_case(C14, method="gs")
    print(f"    GS: 풀림 {win.sol.converged} · 반복 {win.sol.iters}회")
    tab("수렴")
    shot("GaussSeidel로_다시_푼_결과", wait=1.0)
guard("Gauss-Seidel", _gs)


def _curve():
    win.set_task("PV·QV 곡선")
    shot("곡선_설정화면", wait=1.0)
    cur = app_engine.curve(win.curve_case(), [], [])
    win._curve_done(cur)
    shot("곡선_결과_PV곡선", wait=1.3)
    win.set_task("조류계산")
guard("PV·QV 곡선", _curve)

# ══════════════════════════════════════════════════════════════
head("I. 24시간 — 다이나믹 · 비교")


def _dyn():
    open_case(H24)
    print(f"    24시간: 시간대 {win.sol.AC.shape[2]}개")
    shot("24시간_스냅샷_시간을_고른다", wait=1.2)
    win.set_mode("다이나믹")
    for i, nm in enumerate(["전압·위상", "주파수", "토폴로지"]):
        graph(i)
        shot(f"다이나믹_{nm}", wait=1.3)
    graph(0)
    tab("손실")
    shot("표_손실_시간축_전체", wait=1.0)
    win.set_mode("비교")
    for ax, nm in [("버스끼리", "비교_버스끼리"), ("시간끼리", "비교_시간끼리")]:
        win.set_axis(ax)
        shot(nm, wait=1.3)
    win.set_mode("스냅샷")


if H24.exists():
    guard("24시간", _dyn)
else:
    print(f"    ⚠️ 없음: {H24.name}")

# ══════════════════════════════════════════════════════════════
head("J. 엔진을 못 찾았을 때 — 어디를 찾아봤는지 말한다")
# 아무것도 없는 컴퓨터를 흉내 낸다 (engine_path.search 가 그러라고 인자를 받는다)
steps = engine_path.search(env={}, app_roots=[], runtime_roots=[], remembered=None)
msg = engine_path.guidance(steps)
box = QMessageBox(win)
box.setIcon(QMessageBox.Warning)
box.setWindowTitle("계산 엔진을 찾지 못했습니다")
box.setText(msg)
box.addButton("직접 고르기…", QMessageBox.ActionRole)
box.addButton("닫기", QMessageBox.RejectRole)
box.show()
box.adjustSize()
shot("엔진_못찾음_다섯자리를_다_말해준다", box, wait=0.5)
box.close()

# ══════════════════════════════════════════════════════════════
print("═" * 62)
print(f"✅ 모두 {len(made)}장 — {OUT}")
if skipped:
    print(f"🚨 건너뛴 것 {len(skipped)}: {skipped}")
else:
    print("   건너뛴 것 없음")
print("뜬 대화상자:", _dlg[:6])
sys.stdout.flush()
app_engine.shutdown()
os._exit(0)
