# -*- coding: utf-8 -*-
"""비교에서 볼 수 있는 항목 (2026-08-27, 사용자 지시 ②).

여태 넷뿐이었다 — 전압 크기·위상각·주파수·손실. 사용자 지시:
*"시나리오끼리 비교하는것도 지금은 전압만 기본적으로 뜨는데, 이것도 다른 결과들도
여러가지 사용자가 선택할 수 있게 고칠거야."*

🚨 늘리기가 간단하지 않았던 까닭 — **항목 이름이 코드 세 군데에 글자로 흩어져 있었다.**
   `COMPARE_ITEMS` 는 `(이름, 늘 보임)` 두 값뿐이라 **어느 표 어느 열인지 담을 자리가 없고**,
   그래프 두 곳이 `if item == "전압 크기"` 로 갈라 보고, 표와 저장에 같은 대응표가 또 있었다.
   ⇒ **여기 한곳에 모은다.** 항목을 더할 때 이 표에 한 줄만 보태면 된다.

무엇마다 있는 값인가 (`by`)
---------------------------
    "bus"     버스마다 — AC·DC 를 함께 본다. x 축이 버스 번호
    "branch"  선로마다 — `106-110` 꼴로 고른다
    "ic"      변환기마다 — `301-3` 꼴 (AC 버스 - DC 버스)
    "system"  계통에 하나뿐 — 주파수·전체 손실

🚨 **IC 는 시간을 가로지르는 비교가 안 된다.** 엔진이 `VSC_bus` 를 **늘 2차원**으로 준다
   (버스 × 열, 시간 축 없음 — 24시각 케이스에서도 그렇다. `app_engine.py:981`).
   그래서 `ic` 항목은 **시나리오끼리에서만** 보인다. 없는 것을 있는 척하지 않는다.
"""
from __future__ import annotations

# (이름, 어느 표, 열 이름, 단위, 소수 자릿수, 무엇마다, 어디서 보이나)
#   어디서 보이나: "all" 셋 다 · "wide" 시간끼리·시나리오끼리 · "scen" 시나리오끼리만
SPECS = [
    # ── 버스마다 ────────────────────────────────────────────────
    ("전압 크기",      "AC", "VM[pu]",       "pu",   3, "bus", "all"),
    ("위상각",         "AC", "Angle[deg]",   "deg",  2, "bus", "all"),
    ("발전 P",         "AC", "Gen_P[MW]",    "MW",   2, "bus", "all"),
    ("발전 Q",         "AC", "Gen_Q[MVAR]",  "Mvar", 2, "bus", "all"),
    ("부하 P",         "AC", "Load_P[MW]",   "MW",   2, "bus", "all"),
    ("부하 Q",         "AC", "Load_Q[MVAR]", "Mvar", 2, "bus", "all"),
    ("AC 주입 P",      "AC", "toAC_P[MW]",   "MW",   2, "bus", "all"),
    ("AC 주입 Q",      "AC", "toAC_Q[MVAR]", "Mvar", 2, "bus", "all"),
    ("DC 전압",        "DC", "VM[pu]",       "pu",   3, "bus", "all"),
    ("DC 발전 P",      "DC", "Gen_P[MW]",    "MW",   2, "bus", "all"),
    ("DC 부하 P",      "DC", "Load_P[MW]",   "MW",   2, "bus", "all"),
    ("DC 주입 P",      "DC", "toDC_P[MW]",   "MW",   2, "bus", "all"),
    # ── 선로마다 ────────────────────────────────────────────────
    ("선로 부하율",     "Branch", "Loading[%]",   "%",    1, "branch", "all"),
    ("선로 조류 P",     "Branch", "From_P[MW]",   "MW",   2, "branch", "all"),
    ("선로 조류 Q",     "Branch", "From_Q[MVAR]", "Mvar", 2, "branch", "all"),
    ("선로 손실 P",     "Branch", "Loss_P[MW]",   "MW",   4, "branch", "all"),
    ("선로 손실 Q",     "Branch", "Loss_Q[MVAR]", "Mvar", 4, "branch", "all"),
    # ── 변환기마다 (시나리오끼리만 — 머리말 참조) ─────────────────
    ("IC 주입 P",      "VSC_bus", "Inj_P[MW]",      "MW",   2, "ic", "scen"),
    ("IC 주입 Q",      "VSC_bus", "Inj_Q[MVAR]",    "Mvar", 2, "ic", "scen"),
    ("IC 손실",        "VSC_bus", "Loss[MW]",       "MW",   4, "ic", "scen"),
    ("IC 전압",        "VSC_bus", "VSC_VM[pu]",     "pu",   3, "ic", "scen"),
    ("IC 위상",        "VSC_bus", "VSC_Angle[deg]", "deg",  2, "ic", "scen"),
    # ── 계통에 하나 ────────────────────────────────────────────
    ("주파수",         None, None, "Hz", 4, "system", "wide"),
    ("손실",           None, None, "MW", 3, "system", "wide"),
]

BY_NAME = {s[0]: s for s in SPECS}
NAMES = [s[0] for s in SPECS]

# 무엇마다 있는 값인지 → 화면에서 뭐라고 부르나
UNIT_NAME = {"bus": "버스", "branch": "선로", "ic": "IC"}
# 그것을 어떻게 적나
HINT = {"bus": "예: 106 107", "branch": "예: 106-110", "ic": "예: 301-3"}


def spec(name):
    return BY_NAME.get(name)


def by(name) -> str:
    s = BY_NAME.get(name)
    return s[5] if s else "system"


def unit(name) -> str:
    s = BY_NAME.get(name)
    return s[3] if s else ""


def digits(name) -> int:
    s = BY_NAME.get(name)
    return s[4] if s else 3


def shown_in(name, axis: str) -> bool:
    """그 비교 축에서 이 항목이 보이나."""
    s = BY_NAME.get(name)
    if s is None:
        return False
    where = s[6]
    if where == "all":
        return True
    if where == "wide":
        return axis in ("시간끼리", "시나리오끼리")
    return axis == "시나리오끼리"          # "scen"


def kinds_needed(picked, axis) -> list[str]:
    """고른 항목들이 무엇을 골라 달라고 하나 — 버스·선로·IC 중에서.

    🚨 **`picked` 를 그대로 돌면 안 된다** — 집합이라 순서가 실행마다 바뀌어
       화면 글자가 「버스 · 선로」였다 「선로 · 버스」였다 한다(실제로 그랬다).
       항목표 순서(`NAMES`)로 돌아 **늘 같은 차례**가 되게 한다.
    """
    out = []
    for n in NAMES:
        if n not in picked or not shown_in(n, axis):
            continue
        k = by(n)
        if k != "system" and k not in out:
            out.append(k)
    return out


def available(sol, name) -> str:
    """그 계통에서 이 항목을 볼 수 있나. 안 되면 **왜 안 되는지**."""
    s = BY_NAME.get(name)
    if s is None:
        return "모르는 항목입니다"
    if s[5] == "system":
        return ""
    arr = getattr(sol, s[1], None)
    if arr is None or getattr(arr, "size", 0) == 0:
        return {"AC": "AC 계통이 없습니다", "DC": "DC 계통이 없습니다",
                "Branch": "선로 결과가 없습니다",
                "VSC_bus": "이 계통에는 변환기 결과가 없습니다"}.get(s[1], "결과가 없습니다")
    if s[2] not in sol.cols(s[1]):
        return f"이 계통 결과에 {s[2]} 열이 없습니다"
    return ""
