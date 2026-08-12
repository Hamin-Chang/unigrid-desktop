# -*- coding: utf-8 -*-
"""3권선 변압기 모델 — 탭·위상이 어느 끝에 걸리나 (2026-08-07, 엔진 10·11차).

  탭은 **권선 버스 쪽**에 걸리고, 위상 칸은 "MV·LV 가 HV 보다 그만큼 뒤진다" 는 뜻이다
  (pandapower `shift_mv_degree` 와 같음). 그리고 탭이 걸린 끝의 전력은 **탭 뒤 전압**으로
  잰다 — 안 그러면 손실이 부풀고, 실제로 지선 손실 합이 **음수**로 나오기도 했다.

  정답본 두 개로 못 박는다:
    · pandapower `example_multivoltage`  → 논문 §4 3권선 검증에 쓴 그 계통
    · MATPOWER `psse2mpc` + `runpf`      → PSS/E `.raw` 쪽

      python tests/test_3w_model.py
"""
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import app_engine                                  # noqa: E402
from load_case import load_case                    # noqa: E402

bad = 0


def ok(cond, what, note=""):
    global bad
    print(f"  {'✅' if cond else '🚨'} {what}" + (f"  — {note}" if note else ""))
    if not cond:
        bad += 1


# ── 1. 논문 §4 3권선 검증 (pandapower) ─────────────────────────────────
# 아래 숫자는 pandapower 3.5.4 의 example_multivoltage 를 `pandapower/3w_revise.py`
# 와 같이 손질한 뒤(MV-LV 2권선의 pfe_kw·i0_percent = 0, q_mvar = -0.96 인 shunt 를 0)
# `runpp` 로 얻은 값이다. 만드는 스크립트는 scratchpad 의 `pp_ref.py`·`pp_flow.py`.
PP_VM = (1.014305, 1.000999, 1.001289)          # HV, MV, LV
PP_DMV, PP_DLV = -31.7618, -31.6224             # MV−HV, LV−HV [도]
PP_P = (+8.656341, -3.000000, -5.650618)        # 3권선 갈래 P [MW]
PP_LOSS_P = 0.005723                            # 3권선 손실 [MW]

print("1) 논문 3권선 검증 — pandapower example_multivoltage")
case = load_case(str(REPO / "cases/AConly_pandapower_3w.xlsx"))
t3 = np.asarray(case.tables["AC_3wtrans_dat"], float)[0]
hv, mv, lv = int(t3[1]), int(t3[2]), int(t3[3])
ok(t3[25] == 30 and t3[26] == 30, "이 케이스는 위상 30도/30도를 쓴다",
   f"MV {t3[25]:g}도 · LV {t3[26]:g}도")

sol = app_engine.solve(case)
ok(sol.converged, "풀린다", f"반복 {sol.iters}회")
d = {int(r[0]): (r[1], r[3]) for r in sol.AC[:, :, 0]}
vm = [d[b][0] for b in (hv, mv, lv)]
va = [d[b][1] for b in (hv, mv, lv)]
ok(max(abs(a - b) for a, b in zip(vm, PP_VM)) < 5e-4, "전압이 pandapower 와 맞는다",
   f"최대차 {max(abs(a-b) for a, b in zip(vm, PP_VM)):.2e} pu")
ok(abs((va[1] - va[0]) - PP_DMV) < 5e-3 and abs((va[2] - va[0]) - PP_DLV) < 5e-3,
   "위상차가 pandapower 와 맞는다 — 위상 부호가 뒤집히면 60도 어긋난다",
   f"MV−HV {va[1]-va[0]:.4f}도 · LV−HV {va[2]-va[0]:.4f}도")

# ── 2. 3권선 **조류**도 맞나 (탭 뒤 전압으로 재나) ──────────────────────
print("\n2) 3권선 갈래 조류")
cb = sol.cols("Branch")
iF, iT = cb.index("From"), cb.index("To")
iPf, iPt = cb.index("From_P[MW]"), cb.index("To_P[MW]")
br = sol.Branch[:, :, 0]
# 중성점은 **세 갈래가 모두 걸리는** 버스다. `hv → ?` 한 조건만 보면 평범한 선로가 걸린다.
pairs = {(int(r[iF]), int(r[iT])) for r in br}
aux = next((b for b in {t for f, t in pairs if f == hv}
            if (b, mv) in pairs and (b, lv) in pairs), None)
ok(aux is not None, "중성점 버스가 지선 표에 있다", f"{aux}")
got = {}
for r in br:
    f, t = int(r[iF]), int(r[iT])
    if f == hv and t == aux:
        got["HV"] = r[iPf]
    elif f == aux and t == mv:
        got["MV"] = r[iPt]
    elif f == aux and t == lv:
        got["LV"] = r[iPt]
for i, e in enumerate(("HV", "MV", "LV")):
    ok(abs(got.get(e, 1e9) - PP_P[i]) < 5e-3, f"{e} 끝 유효전력이 맞는다",
       f"{got.get(e, float('nan')):.6f} vs {PP_P[i]:.6f} MW")
loss = sum(got.values())
ok(abs(loss - PP_LOSS_P) < 5e-4, "3권선 손실이 맞는다 — 탭 뒤 전압으로 재지 않으면 17배 부푼다",
   f"{loss:.6f} vs {PP_LOSS_P:.6f} MW")

# ── 3. 전력 수지 — 지선 손실 합이 음수가 되면 안 된다 ────────────────────
print("\n3) 전력 수지 (발전 − 부하 ≈ 지선 손실 합)")
ca = sol.cols("AC")
for name, lim in (("AConly_3wtrans_modify", 0.05), ("AConly_psse_3W_unigrid_easy", 0.3)):
    s = app_engine.solve(load_case(str(REPO / f"cases/{name}.xlsx")))
    gen = s.AC[:, ca.index("Gen_P[MW]"), 0].sum()
    load = s.AC[:, ca.index("Load_P[MW]"), 0].sum()
    lo = (s.Branch[:, iPf, 0] + s.Branch[:, iPt, 0]).sum()
    ok(lo > 0, f"{name} — 지선 손실 합이 양수다", f"{lo:.4f} MW")
    ok(abs(gen - load - lo) < lim, f"{name} — 수지가 맞는다",
       f"어긋남 {abs(gen-load-lo):.4f} MW")

# ── 4. PSS/E `.raw` — MATPOWER 와 대조 ────────────────────────────────
print("\n4) PSS/E .raw — MATPOWER 정답본과 대조")
RAW = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/03_전기연자문_2026_3/"
           "04_python_conversion/02_GitHub_unigrid/acdc_powerflow/grids/psse_3w_sample.raw")
# MATPOWER 값 (psse2mpc + runpf). 이 파일은 STAT 1·2·3·4 를 하나씩 담은 시험 계통이다.
MP = {215: (1.112700, -2.78), 3010: (1.003100, 27.66)}
if RAW.is_file():
    s = app_engine.solve(load_case(str(RAW)))
    ok(s.converged, "풀린다", f"반복 {s.iters}회")
    dd = {int(r[0]): (r[1], r[3]) for r in s.AC[:, :, 0]}
    # 🚨 215 는 STAT=3 변압기의 권선 2 (WINDV2 = 1.1) — 탭 방향이 뒤집혀 있으면 0.92 가 나온다.
    ok(abs(dd[215][0] - MP[215][0]) < 0.02, "버스 215 전압 — 탭이 권선 버스 쪽에 걸린다",
       f"{dd[215][0]:.4f} vs {MP[215][0]:.4f}")
    # 🚨 3010 은 STAT=2 변압기의 권선 3 (`D1y0y0`·ANG3 = 30도) — 부호가 반대면 59도 어긋난다.
    dv = abs(dd[3010][1] - MP[3010][1])
    ok(dv < 2.0, "버스 3010 위상 — PSS/E 의 ANG 부호를 뒤집어 읽는다", f"차 {dv:.2f}도")

    # 🚨 2026-08-10 — 권선별 탭. 3권선 `1 `(3002-3001-3011)의 WINDV 가 권선마다
    #    1.01010 / 1.05000 / 1.01000 로 다르다. 표가 탭을 하나만 담던 때는 1.05 만
    #    살아남아 버스 3001·3003 이 0.0086 pu 어긋났다. 33 열(권선별 탭비)이
    #    빠지거나 무시되면 이 두 줄이 먼저 깨진다.
    PW = {3001: 1.037123, 3003: 1.036311}
    for b, ref in PW.items():
        dvv = abs(dd[b][0] - ref)
        ok(dvv < 1e-3, f"버스 {b} 전압 — 권선마다 탭이 따로 걸린다",
           f"{dd[b][0]:.4f} vs {ref:.4f} (차 {dvv:.5f})")
else:
    print("  ⏭  psse_3w_sample.raw 이 없어 건너뛴다")

app_engine.shutdown()
print(f"\n{'✅ 전부 통과' if bad == 0 else f'🚨 {bad}건 틀림'}")
sys.stdout.flush()
os._exit(1 if bad else 0)
