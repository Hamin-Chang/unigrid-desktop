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

def _rated(row, iC, iL):
    """이 선로의 **부하율을 믿을 수 있나**.

    믿을 수 없는 경우 둘 —
      · 용량이 0 이하다 (정격이 안 적혔다는 뜻. MATPOWER 관례로 `rateA = 0` = 무제한)
      · 부하율이 유한하지 않다 (0 으로 나눈 `inf`, 또는 `NaN`)
    """
    if iC >= 0 and not (row[iC] > 0):
        return False
    return math.isfinite(float(row[iL]))


def unrated_lines(sol, t) -> int:
    """정격이 안 적혀 **부하율을 못 재는** 선로가 몇 개인가.

    조용히 빼면 그것대로 못 믿으므로, 화면이 이 수를 밝힐 수 있게 따로 센다.

    ⚠️ **꺼진 선로는 안 센다.** 꺼져 있으면 조류가 0 이라 부하율을 볼 일이 없는데,
       같이 세면 안내에 적히는 수가 부푼다 (case33_matpower: 37 → 32. 그 5개는
       `Status = 0` 이고 부하율도 0 이라 옛 규칙에서도 과부하가 아니었다).
    """
    arr = sol.at("Branch", t) if sol is not None else None
    if arr is None or not arr.size:
        return 0
    cols = sol.cols("Branch")
    iL, iC = col_index(cols, "Loading[%]"), col_index(cols, "Capacity[MVA]")
    iS = col_index(cols, "Status")
    if iL < 0:
        return 0
    return sum(1 for r in arr
               if (iS < 0 or r[iS] != 0) and not _rated(r, iC, iL))


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
                # 🚨 **정격이 안 적힌 선로는 과부하를 잴 수 없다** (2026-08-18).
                #    MATPOWER 에서 `rateA = 0` 은 「용량이 0」이 아니라 **「정격이 안
                #    적힘(무제한)」** 이라는 뜻이다. 그런데 엔진은 그 0 으로 나눠
                #    부하율을 `inf` 로 내고, 여기 `r[iL] > 100.0` 이 `inf > 100` 이라
                #    참이 되어 **그 선로를 전부 과부하로 잡았다.**
                #    실측 — IEEE 118버스에서 **선로 186개 전부**가 과부하로 떴다.
                #    (`unigrid_convert.py:147` 은 `.m` 을 읽을 때 rateA=0 을 9999 로
                #     바꿔 이미 이 관례를 지키고 있었다. 판정하는 이쪽만 몰랐다.)
                if not _rated(r, iC, iL):
                    continue
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


