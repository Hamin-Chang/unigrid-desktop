# -*- coding: utf-8 -*-
"""정격이 안 적힌 선로를 과부하로 세지 않는다 (2026-08-18).

계기 — IEEE 118버스를 열면 **선로 186개가 전부 과부하**로 떴다. 용량이 0.0 MVA 인데
엔진이 그 0 으로 나눠 부하율을 `inf` 로 냈고, 판정이 `inf > 100` 이라 전부 걸렸다.
MATPOWER 에서 `rateA = 0` 은 「용량 0」이 아니라 **「정격이 안 적힘(무제한)」** 이다
(이 저장소도 `unigrid_convert.py:147` 에서 `.m` 을 읽을 때 0 → 9999 로 바꿔 왔다).

보는 것
    1) 정격이 안 적힌 케이스에서 과부하가 **0건**이 되나
    2) 🚨 정격이 있는 케이스는 **건수가 그대로**인가 (거짓 음성을 만들면 더 나쁘다)
    3) 못 잰 선로 수를 셀 수 있나 — 화면이 밝힐 수 있어야 한다
    4) ⚠️ **꺼진 선로는 안 세나** — 조류가 0 이라 부하율을 볼 일이 없는데 같이 세면
       안내에 적히는 수가 부푼다 (case33_matpower: 37 → 32)
    5) 부하율 그래프가 `inf` 때문에 축이 깨지지 않나
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import warnings                                                   # noqa: E402
warnings.filterwarnings("ignore")
import numpy as np                                                # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402

qapp = QApplication([])
import app_engine                                                 # noqa: E402
import charts as CH                                               # noqa: E402
from checks import col_index, real_violations, unrated_lines      # noqa: E402
from load_case import load_case                                   # noqa: E402

fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<52} {got}")
    else:
        print(f"  ❌ {label:<52} {got}  (바라던 값 {want})")
        fails.append(label)


def solve(rel):
    return app_engine.solve(load_case(str(V14 / rel)))


def over(sol):
    return len(real_violations(sol, 0)["과부하 선로"][1])


def raw_over(sol):
    """옛 규칙 — 부하율만 보고 셈 (inf 가 걸린다)."""
    br = sol.at("Branch", 0)
    v = np.asarray(br[:, col_index(sol.cols("Branch"), "Loading[%]")], dtype=float)
    return int((v > 100.0).sum())


print("\n[1] 정격이 안 적힌 케이스 — 과부하가 0건이 되나")
for rel in ("cases_v2/AConly_case118_v2.xlsx",
            "cases_v2/AConly_case33_std_v2.xlsx",
            "cases_v2/AConly_case18_v2.xlsx"):
    sol = solve(rel)
    name = Path(rel).name
    print(f"    {name} — 옛 규칙이면 {raw_over(sol)}건")
    check(f"{name} 과부하", over(sol), 0)
    check(f"{name} 못 잰 선로가 세어지나", unrated_lines(sol, 0) > 0, True)

print("\n[2] 🚨 정격이 있는 케이스는 건수가 그대로인가")
for rel, want in (("cases_v2/ACDC_case24_MatACDC_v2.xlsx", 2),
                  ("cases_v2/ACDC_71bus_v2.xlsx", 13),
                  ("cases_v2/AConly_case30_v2.xlsx", 1),
                  ("cases_v2/AConly_case6495rte_v2.xlsx", 20)):
    sol = solve(rel)
    name = Path(rel).name
    check(f"{name} 과부하", over(sol), want)
    check(f"{name} 옛 규칙과 같은가", over(sol), raw_over(sol))
    check(f"{name} 못 잰 선로 없음", unrated_lines(sol, 0), 0)

print("\n[4] ⚠️ 꺼진 선로는 안 세나")
sol = solve("cases_v2/AConly_case33_matpower_v2.xlsx")
br = sol.at("Branch", 0)
cols = sol.cols("Branch")
cap = np.asarray(br[:, col_index(cols, "Capacity[MVA]")], dtype=float)
st = np.asarray(br[:, col_index(cols, "Status")], dtype=float)
n_all = int((cap <= 0).sum())
n_on = int(((cap <= 0) & (st != 0)).sum())
print(f"    용량 0 인 선로 {n_all}개 중 켜진 것 {n_on}개")
check("켜진 것만 세나", unrated_lines(sol, 0), n_on)
check("꺼진 것이 실제로 있나 (시험이 헛돌지 않게)", n_all > n_on, True)

print("\n[5] 부하율 그래프의 세로축이 성한가")
sol = solve("cases_v2/AConly_case118_v2.xlsx")
view = CH.loading_chart(CH.palette(False) if hasattr(CH, "palette") else
                        __import__("app").LIGHT, sol, 0)
check("그래프가 만들어지나", view is not None, True)
if view is not None:
    # ⚠️ 범주 축(QBarCategoryAxis)도 `.max()` 를 갖는데 그건 **글자**다
    #    ('line 75-118'). 값 축만 골라야 한다.
    from PySide6.QtCharts import QValueAxis
    ys = [ax for ax in view.chart().axes() if isinstance(ax, QValueAxis)]
    check("값 축을 찾았나", len(ys) > 0, True)
    # ⚠️ 값 축이 둘이다 — 세로축(부하율 %)과, 100% 점선을 그리려고 **숨겨 둔 가로축**
    #    (범위가 0~선로수라 case118 이면 186 이 나온다). 둘을 섞어 보면 안 된다.
    from PySide6.QtCore import Qt as _Qt
    for a in ys:
        side = view.chart().axes()
        where = "세로" if a.alignment() == _Qt.AlignLeft else "숨긴 가로"
        print(f"    {where} 축 범위 {a.min()} ~ {a.max()}")
        check(f"{where} 축 위끝이 유한한가", bool(np.isfinite(float(a.max()))), True)
    left = [a for a in ys if a.alignment() == _Qt.AlignLeft]
    check("세로축이 하나 있나", len(left), 1)
    if left:
        # 모든 선로가 「정격 없음」이면 막대가 전부 0 이라 바닥값 105 가 나와야 한다
        check("세로축 위끝이 바닥값 105 인가", round(float(left[0].max())), 105)

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if fails else 0)
