# -*- coding: utf-8 -*-
"""끄기가 **정말로** 계산에 반영되나 — 다섯 가지를 엔진에 넣어 확인한다.

소스를 읽어 판단하지 않는다(이미 두 번 틀렸다 — v14_lite 를 v14 로 착각).
그 칸을 0으로 만들어 실제로 풀고, **답이 달라지는지**로 가린다.
답이 한 비트도 안 달라지면 그 칸은 계산에 안 쓰이는 것이다.
"""
import sys
from pathlib import Path

import numpy as np

REPO = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/unigrid-desktop")
sys.path.insert(0, str(REPO / "src"))

import app_engine                              # noqa: E402
from load_case import load_case                # noqa: E402

# (표, 상태 열(0부터), 끄면 넣을 값, 사람 이름)
KNOBS = [
    ("AC_Line_dat",   12, 0.0, "AC 선로"),
    ("DC_Line_dat",    7, 0.0, "DC 선로"),
    ("AC_gen_dat",     8, 0.0, "AC 발전기"),
    ("DC_gen_dat",     6, 0.0, "DC 발전기"),
    ("IC_dat",        15, 0.0, "IC"),
    ("DCDC_Conv_dat",  9, 0.0, "DC/DC (운전모드→0)"),
]
CASES = ["ACDC_71bus_3IC_parallel", "ACDC_CIGRE_MVACMVDCLVDC",
         "ACDC_case24_MatACDC", "AConly_case14"]


def fingerprint(sol) -> np.ndarray:
    return np.concatenate([np.nan_to_num(np.asarray(getattr(sol, k), dtype=float)).ravel()
                           for k in ("AC", "DC", "Branch", "loss")])


for name in CASES:
    path = REPO / f"cases/{name}.xlsx"
    case = load_case(str(path))
    try:
        base = app_engine.solve(case)
    except Exception as exc:
        print(f"{name}: 원본이 안 풀립니다 — {exc}")
        continue
    f0 = fingerprint(base)
    print(f"\n{name}")
    for table, col, off, label in KNOBS:
        t = case.tables.get(table)
        arr = np.asarray(getattr(t, "values", t), dtype=float) if t is not None else np.zeros((0, 0))
        if arr.size == 0 or arr.ndim != 2 or np.all(np.isnan(arr)) or arr.shape[1] <= col:
            print(f"  {label:<18} —  (이 계통엔 없음)")
            continue
        # 켜져 있는 줄 하나를 고른다
        live = [i for i in range(arr.shape[0]) if arr[i, col] != off and not np.isnan(arr[i, col])]
        if not live:
            print(f"  {label:<18} —  (켜져 있는 줄이 없음)")
            continue
        row = live[0]
        mod = case.copy()
        tt = mod.tables[table]
        if hasattr(tt, "iloc"):
            tt.iloc[row, col] = off
        else:
            tt[row, col] = off
        try:
            sol = app_engine.solve(mod)
        except Exception as exc:
            msg = str(exc).strip().splitlines()[0][:28]
            print(f"  {label:<18} ✅ 반영됨 (못 풀게 됨: {msg})   {row + 1}번째 줄")
            continue
        f1 = fingerprint(sol)
        same = f0.shape == f1.shape and np.allclose(f0, f1)
        mark = "🚨 무시됨" if same else "✅ 반영됨"
        print(f"  {label:<18} {mark}   {row + 1}번째 줄"
              + ("  ← 답이 한 비트도 안 달라졌다" if same else ""))

app_engine.shutdown()
print("\nDONE_PROBE")
