# -*- coding: utf-8 -*-
"""비교 항목 늘리기 (2026-08-27, 사용자 지시 ②).

  ① 항목이 4 → 24 로 늘었나
  ② 축마다 보일 것이 갈리나 (IC 는 시나리오끼리만)
  ③ 그 계통에 없는 항목은 까닭을 달고 잠기나
  ④ 「비교할 것」이 버스·선로·IC 로 바뀌나
  ⑤ 선로 부하율이 실제로 그려지나 (`106-110` 꼴로 골라서)
  ⑥ 시나리오끼리 비교가 새 항목으로도 도나
"""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "shots_compare"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
from PySide6.QtWidgets import QApplication, QLineEdit, QLabel
qapp = QApplication([])
import app as APP
import compare_items as CI
import charts, scenario as SC
win = APP.Proto(); win.resize(1600, 1000); win.show()
ok = [0]; bad = []
def chk(n, got, want):
    if got == want: ok[0] += 1; print(f"  ✅ {n}")
    else: bad.append(n); print(f"  ❌ {n}: {got!r} ≠ {want!r}")
def pump(s=0.4):
    e = time.time()+s
    while time.time() < e: qapp.processEvents(); time.sleep(0.01)

win._start_solve(str(REPO/"cases/ACDC_case24_MatACDC.xlsx"))
e = time.time()+240
while time.time() < e:
    qapp.processEvents()
    if win.thread.isFinished(): break
    time.sleep(0.02)
pump(1.2)

print("[1] 항목이 늘었나")
chk("항목 수", len(CI.SPECS), 24)
chk("옛 넷이 그대로 있나",
    all(n in CI.NAMES for n in ("전압 크기", "위상각", "주파수", "손실")), True)
chk("부하율이 들어왔나", "선로 부하율" in CI.NAMES, True)

print("[2] 축마다 보일 것이 갈리나")
chk("주파수는 버스끼리에서 안 보임", CI.shown_in("주파수", "버스끼리"), False)
chk("주파수는 시간끼리에서 보임", CI.shown_in("주파수", "시간끼리"), True)
chk("IC 는 버스끼리에서 안 보임", CI.shown_in("IC 손실", "버스끼리"), False)
chk("IC 는 시나리오끼리에서만", CI.shown_in("IC 손실", "시나리오끼리"), True)
chk("부하율은 셋 다", [CI.shown_in("선로 부하율", a)
                    for a in ("버스끼리", "시간끼리", "시나리오끼리")], [True]*3)

print("[3] 없는 항목은 까닭을 다나")
chk("이 계통엔 IC 가 있다", CI.available(win.sol, "IC 손실"), "")
win2_msg = CI.available(win.sol, "DC 전압")
chk("DC 도 있다", win2_msg, "")

print("[4] 「비교할 것」이 항목따라 바뀌나")
def label_of():
    """🚨 `win.findChildren` 은 **아직 안 지워진 옛 라벨**도 준다 — 그것 때문에
       한 번 헛읽었다. 왼쪽 판을 그 자리에서 새로 만들어 **그 안만** 본다."""
    sb = win.sidebar()
    return [w.text() for w in sb.findChildren(QLabel)
            if w.text().startswith("비교할 ") and "적어 주세요" not in w.text()]
win.mode = "비교"; win.compare_axis = "버스끼리"
win.picked = {"전압 크기"}
chk("버스만 고르면 버스", label_of(), ["비교할 버스"])
win.picked = {"선로 부하율"}
chk("부하율만 고르면 선로", label_of(), ["비교할 선로"])
win.picked = {"전압 크기", "선로 부하율"}
chk("둘 다면 둘 다", label_of(), ["비교할 버스 · 선로"])
# 🚨 `picked` 는 집합이라 차례가 실행마다 바뀔 수 있다 — 늘 같은지 못박는다
chk("차례가 늘 같은가",
    [CI.kinds_needed({"선로 부하율", "전압 크기"}, "버스끼리") for _ in range(5)],
    [["bus", "branch"]] * 5)

print("[5] 선로 부하율이 그려지나")
chk("두 번호 읽기", charts._pairs_of("106-110, 107-108"), [(106, 110), (107, 108)])
which, rows, skipped = charts._pick_rows(win.sol, "선로 부하율", [(106, 110)])
chk("그 선로를 찾았나", (which, len(rows), skipped), ("Branch", 1, []))
# 🚨 **앱이 넘기는 꼴로 시험한다** — 앱은 쉼표로 잘라 **목록**으로 넘긴다.
#    글자로 넘기면 통과하는데 화면은 비어 있었다(실제로 그랬다).
chk("목록으로 넘겨도 읽나", charts._pairs_of(["106-110", "107-108"]),
    [(106, 110), (107, 108)])
w = charts.compare_chart(win.c, win.sol, "선로 부하율", "버스끼리",
                         ["106-110", "107-108"])
# 🚨 `_note`(못 그림)도 QFrame 이고 QChartView 도 QFrame 을 물려받는다 —
#    형으로 가르면 안 된다. **그린 선이 있는지**로 가른다.
from PySide6.QtCharts import QChartView          # noqa: E402
def is_chart(w):
    return isinstance(w, QChartView) and len(w.chart().series()) > 0
chk("그래프가 나왔나", is_chart(w), True)
chk("선이 두 개인가", len(w.chart().series()) >= 2, True)
win.compare_targets = "106-110, 107-108"; win.picked = {"선로 부하율"}
win.rebuild(); pump(1.0)
win.grab().save(str(OUT/"01_선로부하율.png"))

print("[6] 시나리오끼리도 새 항목으로 도나")
win.mode = "스냅샷"; win.rebuild(); pump(0.3)
win.grid_key = "AC_Line_dat"; win.flip_row(9); pump(0.3)
win._pending = win.applied + win.changes
sol2 = APP.ENGINE.solve(SC.apply(win.base_case, win._pending))
class F: loaded_case = None; case = None
win.thread = F(); win._solved(sol2); pump(0.8)
# 🚨 필드 이름은 `solution` 이다 (`scenario.py` Scenario)
pairs = [(s.name, s.solution) for s in win.book.items if s.solved]
chk("시나리오가 둘인가", len(pairs) >= 2, True)
for it in ("선로 부하율", "발전 P", "IC 손실"):
    w = charts.compare_scenarios(win.c, pairs, it, 0)
    chk(f"{it} 가 그려지나", w is not None, True)
win.mode = "비교"; win.compare_axis = "시나리오끼리"
win.picked = {"선로 부하율", "IC 손실"}
win.rebuild(); pump(1.2)
win.grab().save(str(OUT/"02_시나리오끼리_새항목.png"))

print("═"*56)
print(f"  통과 {ok[0]} · 실패 {len(bad)}")
for b in bad: print(f"    ❌ {b}")
sys.exit(1 if bad else 0)
