# -*- coding: utf-8 -*-
"""checks.py — 결과에서 **점검할 것**(위반)을 걸러낸다.

  전압 위반 · 과부하 선로 · 변환기 한계 · 발전기 한계.
  순수 계산이라 화면과 무관하다 — 그래서 `app.py`(화면)와 `exporter.py`(엑셀)가
  **둘 다** 쓸 수 있게 여기로 뺐다(2026-08-06). 그전에는 `app.py` 안에 있어
  엑셀 내보내기가 못 썼다(`app.py` 가 `exporter` 를 부르므로 서로 부르는 꼴이 된다).
"""
from __future__ import annotations

import math

import numpy as np


def col_index(cols, name):
    try:
        return cols.index(name)
    except ValueError:
        return -1

def real_violations(sol, t):
    """전압 위반 · 과부하 · 변환기 한계를 결과에서 걸러낸다."""
    res = {}

    # 전압 위반 (AC · DC 둘 다 Vmin/Vmax 열을 갖고 있다)
    rows = []
    for which in ("AC", "DC"):
        arr = sol.at(which, t)
        if not arr.size:
            continue
        cols = sol.cols(which)
        iB, iV = col_index(cols, "Bus"), col_index(cols, "VM[pu]")
        iLo, iHi = col_index(cols, "Vmin[pu]"), col_index(cols, "Vmax[pu]")
        if min(iB, iV, iLo, iHi) < 0:
            continue
        for r in arr:
            v, lo, hi = r[iV], r[iLo], r[iHi]
            if v > hi:
                rows.append([f"{which} {int(r[iB])}", f"{v:.4f}",
                             f"Vmax {hi:.3f}", f"+{v - hi:.4f}"])
            elif v < lo:
                rows.append([f"{which} {int(r[iB])}", f"{v:.4f}",
                             f"Vmin {lo:.3f}", f"{v - lo:.4f}"])
    res["전압 위반"] = (["버스", "V[pu]", "한계", "초과량"], rows)

    # 과부하 선로
    rows = []
    arr = sol.at("Branch", t)
    if arr.size:
        cols = sol.cols("Branch")
        iF, iT = col_index(cols, "From"), col_index(cols, "To")
        iL = col_index(cols, "Loading[%]")
        iC = col_index(cols, "Capacity[MVA]")
        if min(iF, iT, iL) >= 0:
            for r in arr:
                if r[iL] > 100.0:
                    cap = f"{r[iC]:.1f}" if iC >= 0 else "—"
                    rows.append([str(int(r[iF])), str(int(r[iT])),
                                 f"{r[iL]:.1f}", cap])
    res["과부하 선로"] = (["From", "To", "Loading[%]", "용량[MVA]"], rows)

    # 변환기 한계 (0=한계 안 · 2=용량곡선 · 3=전류한계)
    rows = []
    label = {2: "용량곡선(S_N) 도달", 3: "전류한계 도달"}
    for i, m in enumerate(sol.IC_lim_mode or []):
        if int(m) in label:
            rows.append([f"변환기 {i + 1}", label[int(m)]])
    res["변환기 한계"] = (["변환기", "상태"], rows)

    # 발전기 한계 (2026-07-27) — 유효·무효를 따로 세고, 무효는 걸린 한계까지 밝힌다.
    res["발전기 한계"] = (GEN_LIMIT_COLS, gen_limit_rows(sol))
    return res


GEN_LIMIT_COLS = ["발전기", "항목", "걸린 한계", "출력", "한계값"]

# 발전기 한계 표의 종류 열 (1~4) → 화면에 쓸 이름
_GEN_KIND = {1: "AC", 2: "DC", 3: "AC", 4: "DC"}


def _fmt_num(x):
    """무한대·빈값은 '—' 로. 한계가 없는 발전기는 ±inf 로 온다.

    소수 2자리 — 용량 원(S_N)에 걸린 값은 0.8732 처럼 어중간해서
    1자리로는 출력과 한계값이 둘 다 '0.9' 로 보인다 (2026-07-28).
    """
    if x is None or not math.isfinite(float(x)):
        return "—"
    return f"{float(x):.2f}"


def gen_limit_rows(sol):
    """발전기 출력한계에 걸린 것만 골라 점검 탭 줄로 만든다.

    한 발전기가 유효·무효 둘 다 걸리면 두 줄이 된다 (한 줄에 뭉치면
    어느 쪽이 걸렸는지가 흐려진다).
    """
    rows = []
    tbl = getattr(sol, "gen_limit", None)
    if tbl is None or len(tbl) == 0:
        return rows

    for r in tbl:
        kind, bus = int(r[0]), int(r[1])
        name = f"{_GEN_KIND.get(kind, '?')} {bus}"

        sat_p = int(r[5])
        if sat_p:
            edge = "Pmax 상한" if sat_p > 0 else "Pmin 하한"
            limit = r[4] if sat_p > 0 else r[3]
            rows.append([name, "유효 P", edge, _fmt_num(r[2]), _fmt_num(limit)])

        sat_q = int(r[9])
        if sat_q:
            qsrc = int(r[10])
            if qsrc == 2:
                # "S_N" 은 논문에서 연계 변환기(IC)의 정격 기호($S^N_{VSC,c}$)라
                # 그대로 쓰면 헷갈린다 → 발전기 쪽임을 이름에 밝힌다 (2026-07-28).
                edge = "발전기 용량 원"
            else:
                edge = "Qmax 상한" if sat_q > 0 else "Qmin 하한"
            limit = r[8] if sat_q > 0 else r[7]
            rows.append([name, "무효 Q", edge, _fmt_num(r[6]), _fmt_num(limit)])

    return rows


def violation_count(viol) -> int:
    """점검할 것이 모두 몇 건인가."""
    return sum(len(rows) for _, rows in viol.values())


