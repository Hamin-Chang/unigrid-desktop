# -*- coding: utf-8 -*-
"""DC 부하 ZIP — 8열 DC Bus Data (2026-11-01, 앱 2.3 · 알고리즘 v17).

  ① 옛 6열이 8열(Z_p·I_p·P_p = 0·0·1)로 바뀌나 · Nominal Current ≠ 0 이면 막나
  ② 예제를 열면 8열인가
  ③ ZIP 을 바꾸면 DC 부하가 식대로 따라가나 (혼합 계통)
       P_L = P0 · ( Z_p·(V/V0)² + I_p·(V/V0) + P_p )
  ④ DC 단독 계통에서도 ③ 이 성립하나 (2026-11-01 DC 단독 솔버에 ZIP 을 넣음)

      python tests/test_dc_zip.py
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
import app_engine                                  # noqa: E402
from load_case import dc_bus_8, load_case          # noqa: E402

bad = 0


def ok(cond, label, extra=""):
    global bad
    print(f"  {'✅' if cond else '❌'} {label}" + (f"  — {extra}" if extra else ""))
    bad += 0 if cond else 1


print("① 6열 → 8열")
old = pd.DataFrame([[1, 0, 1.0, 1000, 0.9, 1.1], [2, np.nan, 1.02, 1000, 0.9, 1.1]])
new = dc_bus_8(old).to_numpy()
ok(new.shape == (2, 8), "8열이 된다", str(new.shape))
ok(np.allclose(new[:, 1:4], [[0, 0, 1], [0, 0, 1]]), "Z_p·I_p·P_p = 0·0·1")
ok(np.allclose(new[:, 4:8], old.to_numpy()[:, 2:6]), "V0·V_base·VM min·VM max 가 제자리로")
blank = dc_bus_8(pd.DataFrame([[np.nan] * 6])).to_numpy()
ok(blank.shape == (1, 8) and np.isnan(blank).all(), "「데이터 없음」 NaN 줄은 NaN 그대로")
try:
    dc_bus_8(pd.DataFrame([[1, 5.0, 1.0, 1000, 0.9, 1.1]]))
    ok(False, "Nominal Current ≠ 0 이면 막는다")
except ValueError:
    ok(True, "Nominal Current ≠ 0 이면 막는다")

print("② 예제를 열면 8열")
CASE = REPO / "cases/ACDC_CIGRE_MVACMVDCLVDC.xlsx"
case = load_case(CASE)
dcb = case.tables["DC_Bus_dat"].to_numpy()
ok(dcb.shape[1] == 8, f"{CASE.name} DC 버스 표", str(dcb.shape))

Z, I, P = 0.3, 0.2, 0.5


def check_zip(case, label):
    """ZIP 을 넣고 풀어 — 부하가 식대로인지 · 전압이 따라 움직이는지."""
    dcb = case.tables["DC_Bus_dat"].to_numpy()
    base = app_engine.solve(case)
    case2 = case.copy()
    t = case2.tables["DC_Bus_dat"].copy()
    t.iloc[:, 1], t.iloc[:, 2], t.iloc[:, 3] = Z, I, P
    case2.tables["DC_Bus_dat"] = t
    zip_ = app_engine.solve(case2)
    ok(base.converged and zip_.converged, f"{label} 둘 다 수렴")
    D = np.asarray(zip_.DC)
    D = D[:, :, 0] if D.ndim == 3 else D
    cols = app_engine.COLUMNS["DC"][D.shape[1]]
    iV, iL = cols.index("VM[pu]"), cols.index("Load_P[MW]")
    V0 = {int(r[0]): r[4] for r in dcb}
    pl = case.tables["DC_PLoad_dat"].to_numpy()
    P0 = {int(r[0]): r[1] * 1e-6 for r in pl if np.isfinite(r[0])}      # W → MW, 첫 시각
    n, worst = 0, 0.0
    for r in D:
        b = int(r[0])
        if P0.get(b, 0) == 0:
            continue
        x = r[iV] / V0[b]
        worst = max(worst, abs(r[iL] - P0[b] * (Z * x * x + I * x + P)))
        n += 1
    ok(n > 0, f"{label} 부하 있는 DC 버스를 견줬다", f"{n}곳")
    ok(worst < 1e-6, f"{label} Load_P 가 식과 같다", f"최대 차이 {worst:.2e} MW")
    Db = np.asarray(base.DC)
    Db = Db[:, :, 0] if Db.ndim == 3 else Db
    ok(np.abs(Db[:, iL] - D[:, iL]).max() > 1e-6, f"{label} ZIP 을 바꾸면 부하가 달라진다",
       f"최대 {np.abs(Db[:, iL] - D[:, iL]).max():.4f} MW")
    # 결과 표만 식으로 다시 쓴 것이 아니라 **조류계산이** 그 부하로 풀렸는지 — 전압이 따라 움직여야 한다
    ok(np.abs(Db[:, iV] - D[:, iV]).max() > 1e-9, f"{label} DC 전압도 따라 바뀐다",
       f"최대 {np.abs(Db[:, iV] - D[:, iV]).max():.2e} pu")


print("③ ZIP 을 바꾸면 부하가 식대로 — 혼합 계통")
check_zip(case, "혼합")
print("④ 같은 확인 — DC 단독 계통 (2026-11-01 솔버에 ZIP 을 넣음)")
check_zip(load_case(REPO / "cases/DConly_21bus.xlsx"), "DC 단독")

print(f"\n{'✅ 전부 통과' if bad == 0 else f'🚨 {bad}건 틀림'}")
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if bad else 0)
