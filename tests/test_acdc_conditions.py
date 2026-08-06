# -*- coding: utf-8 -*-
"""AC/DC 망에서 계통 조건이 제대로 먹히나 (엔진까지 실제로 돌린다).

  AC 전용 케이스와 다른 것들만 본다 — IC · DC/DC · DC 발전기, 그리고
  **같은 자리에 여러 대가 붙은 계통**(71bus 는 AC 38 ↔ DC 39 사이 IC 3대 병렬).

      python tests/test_acdc_conditions.py
"""
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import scenario as SC                               # noqa: E402
import app_engine                                   # noqa: E402
from load_case import load_case                     # noqa: E402

bad = 0


def ok(cond, what, note=""):
    global bad
    print(f"  {'✅' if cond else '🚨'} {what}" + (f"  — {note}" if note else ""))
    if not cond:
        bad += 1


def case(name):
    return load_case(str(REPO / f"cases/{name}.xlsx"))


def vmin(sol, t=0):
    a = np.asarray(sol.AC, dtype=float)
    return float(np.nanmin((a[..., t] if a.ndim == 3 else a)[:, 1]))


def finger(sol):
    out = []
    for n in ("AC", "DC", "Branch", "loss"):
        a = np.asarray(getattr(sol, n), dtype=float)
        out.append(np.nan_to_num(a).ravel())
    return np.concatenate(out)


# ── 1. 같은 자리에 여러 대가 붙으면 이름이 갈린다 ───────────────────────
print("1) 병렬로 붙은 설비 이름 (71bus · IC 3대가 같은 버스 쌍)")
c71 = case("ACDC_71bus_3IC_parallel")
names = [SC.describe_row(c71, "IC_dat", i) for i in range(3)]
ok(len(set(names)) == 3, "IC 3대가 서로 다른 이름", " / ".join(n[-12:] for n in names))
ok(all(n.endswith(("1번", "2번", "3번")) for n in names), "몇 번째인지 붙는다")

# 빈 표(전부 NaN)에서 죽지 않는다 — 71bus 의 DC/DC 가 그렇다
try:
    got = SC.describe_row(c71, "DCDC_Conv_dat", 0)
    ok("번째 줄" in got, "값이 빈 줄도 이름을 만든다", got)
except Exception as exc:
    ok(False, "값이 빈 줄도 이름을 만든다", f"{type(exc).__name__}: {exc}")

# ── 2. IC 를 끄면 답이 달라진다 (71bus · 이상적 변환기) ─────────────────
print("\n2) 71bus — IC 끄기가 엔진에 닿나")
base71 = app_engine.solve(c71)
off71 = app_engine.solve(SC.apply(c71, [SC.toggle(c71, "IC_dat", 0, on=False)]))
f0, f1 = finger(base71), finger(off71)
ok(f0.shape == f1.shape and not np.allclose(f0, f1), "IC 1번을 끄면 답이 달라진다",
   f"Branch 최대차 {np.abs(np.nan_to_num(np.asarray(base71.Branch, dtype=float)) - np.nan_to_num(np.asarray(off71.Branch, dtype=float))).max():.4g}")
# 3대가 완전히 같은 설비다 → 어느 것을 꺼도 같은 답이어야 한다
off71b = app_engine.solve(SC.apply(c71, [SC.toggle(c71, "IC_dat", 1, on=False)]))
ok(np.allclose(f1, finger(off71b)), "똑같은 3대 중 어느 것을 꺼도 같은 답",
   f"전압최저 {vmin(off71):.4f}")
ok(base71.VSC_bus is None,
   "71bus 는 이상적 변환기라 변환기별 표가 없다 (화면에서 분담을 못 본다)")

# ── 3. case24 — 변환기별 표가 나오고, 끄면 나머지가 받는다 ──────────────
print("\n3) case24 — 변환기별 표로 분담이 보이나")
c24 = case("ACDC_case24_MatACDC")
b24 = app_engine.solve(c24)
ok(b24.VSC_bus is not None, "상세 변환기 모델이라 변환기별 표가 있다",
   str(np.asarray(b24.VSC_bus).shape))


def by_pair(sol):
    v = np.asarray(sol.VSC_bus, dtype=float)
    sl = v[..., 0] if v.ndim == 3 else v
    col = sol.cols("VSC_bus")
    j = col.index("Inj_P[MW]")
    return {(int(r[0]), int(r[1])): float(r[j]) for r in sl}


a = by_pair(b24)
o24 = app_engine.solve(SC.apply(c24, [SC.toggle(c24, "IC_dat", 2, on=False)]))  # 301↔3
b = by_pair(o24)
ok((301, 3) in a and (301, 3) not in b, "끈 변환기는 결과 표에서 빠진다",
   f"{len(a)}대 → {len(b)}대")
moved = {k: (a[k], b[k]) for k in b if abs(b[k] - a[k]) > 0.01}
ok(len(moved) >= 1, "나머지 중 누군가가 부족분을 받는다",
   " · ".join(f"{k[0]}↔{k[1]} {x:.1f}→{y:.1f} MW" for k, (x, y) in moved.items()))
ok(abs(vmin(o24) - vmin(b24)) > 1e-3, "AC 전압최저가 눈에 띄게 달라진다",
   f"{vmin(b24):.4f} → {vmin(o24):.4f}")

# 안 풀리는 조건은 예외로 온다 (앱은 이걸 받아 '안 풀림' 으로 담는다)
try:
    app_engine.solve(SC.apply(c24, [SC.toggle(c24, "IC_dat", 0, on=False)]))
    ok(False, "IC 1번(107↔1)을 끄면 안 풀린다")
except Exception as exc:
    ok("조류계산 실패" in str(exc), "못 푸는 조건은 예외로 온다",
       str(exc).splitlines()[0][:38])

# ── 4. DC/DC 와 DC 발전기 (CIGRE) ───────────────────────────────────────
print("\n4) CIGRE — DC/DC 와 DC 발전기")
cg = case("ACDC_CIGRE_MVACMVDCLVDC")
bg = app_engine.solve(cg)
for table, label in (("DCDC_Conv_dat", "DC/DC"), ("DC_gen_dat", "DC 발전기"),
                     ("DC_Line_dat", "DC 선로")):
    ch = SC.toggle(cg, table, 0, on=False)
    try:
        s = app_engine.solve(SC.apply(cg, [ch]))
        same = np.allclose(finger(bg), finger(s)) if finger(bg).shape == finger(s).shape else False
        ok(not same, f"{label} 를 끄면 답이 달라진다",
           f"{ch.label} · 전압최저 {vmin(bg):.4f} → {vmin(s):.4f}")
    except Exception as exc:
        ok("조류계산 실패" in str(exc), f"{label} 를 끄면 안 풀린다 (그것도 답이다)",
           str(exc).splitlines()[0][:38])

# ── 5. 부하 일괄 증감이 DC 부하에도 걸린다 ──────────────────────────────
print("\n5) 부하 일괄 증감 — DC 부하까지")
up = SC.apply(cg, [SC.scale_load(1.5)])
for k in ("AC_PLoad_dat", "AC_QLoad_dat", "DC_PLoad_dat"):
    x, y = SC._values(cg, k), SC._values(up, k)
    ok(np.allclose(np.nan_to_num(y[:, 1:]), np.nan_to_num(x[:, 1:]) * 1.5),
       f"{k} 가 1.5배")
    ok(np.array_equal(x[:, 0], y[:, 0]), f"{k} 의 버스 번호는 그대로")

print(f"\n{'✅ 전부 통과' if bad == 0 else f'🚨 {bad}건 틀림'}")
sys.stdout.flush()
app_engine.shutdown()
os._exit(1 if bad else 0)
