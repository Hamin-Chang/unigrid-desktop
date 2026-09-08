# -*- coding: utf-8 -*-
"""계통 데이터 칸에 무엇을 넣을 수 있나 (2026-08-27, §7 「전부 고칠 수 있게」).

여태 앱에서 고칠 수 있는 칸은 **114열 중 18칸**(운전 조건)뿐이었다. 나머지는 회색으로
두고 "계통 자체는 엑셀에서" 라는 선을 화면으로 보여 줬다(PDR §4.3 ④). 사용자 지시로
그 선을 걷는다 — *"일단 모든 거를 다 바꾼 다음에 계통 시나리오를 돌릴 수 있게"*.

🚨 그런데 **회색 96칸은 운전 조건과 성격이 다르다.** 운전 조건은 값의 범위가 뻔하지만
   여기엔 **버스를 가리키는 번호**(`From`·`To`·`Bus`)와 **물리량**(R·X·정격)이 섞여 있다.
   `From` 을 없는 버스로 고치면 계통이 끊어지고, 정격을 음수로 두면 부하율이 뒤집힌다.
   ⇒ 칸마다 **무엇을 받을지**를 여기에 적어 두고, 값이 들어올 때마다 검사한다.

검사는 **막는 것이 아니라 알려 주는 것**이다 — 왜 안 되는지 말해 주고 그 칸을 되돌린다.

⚠️ 여기서 **일부러 안 여는 칸**이 있다
  · `DC/DC` 의 3·4·5번째 칸 — v1 의 효율곡선 C0·C1·C2 다. **지금 솔버가 안 읽고**
    케이스 56개가 전부 0 이라 `format_v2` 가 이름조차 안 붙였다. 열어 봐야 아무 일도
    안 일어나므로 회색으로 둔다.
  · `DC 버스` 의 `Nominal Current` — **v1 에 단위가 안 적혀 있다**(`format_v2.py:208`).
    무엇을 넣으라고 말할 수 없어 확인 전까지 그대로 둔다.
"""
from __future__ import annotations

import numpy as np

# 규칙 이름
BUS_AC = "bus_ac"        # AC 버스 표에 있는 번호여야 한다
BUS_DC = "bus_dc"        # DC 버스 표에 있는 번호여야 한다
FLAG = "flag"            # 0 아니면 1
INT_POS = "int_pos"      # 1 이상 정수
INT = "int"              # 정수
POS = "pos"              # 0 보다 커야 한다
NONNEG = "nonneg"        # 0 이상
FREE = "free"            # 아무 실수나
SHARE = "share"          # 0~1 (부하 나눔 비율)

# 짝이 되는 한계 — (아래 칸, 위 칸)
PAIRS = {
    "AC_gen_dat": [(12, 11), (14, 13)],      # Qmin≤Qmax · Pmin≤Pmax
    "DC_gen_dat": [(10, 9)],                 # Pmin≤Pmax
    "AC_Bus_dat": [(14, 15)],                # V_min≤V_max
    "DC_Bus_dat": [(4, 5)],                  # VM min≤VM max
}

# 합이 1 이어야 하는 묶음 — ZIP 부하 (설명, 칸들)
SUMS = {
    "AC_Bus_dat": [("유효전력 ZIP 비율", (3, 4, 5)), ("무효전력 ZIP 비율", (6, 7, 8))],
}

RULES = {
    "AC_Line_dat": {
        0: INT_POS, 1: BUS_AC, 2: BUS_AC, 3: FREE, 4: FREE, 5: FREE,
        6: POS, 7: FREE, 8: NONNEG, 9: NONNEG, 10: NONNEG, 11: FLAG, 12: FLAG,
    },
    "AC_gen_dat": {
        0: BUS_AC, 1: INT, 5: FREE, 6: FREE, 8: FLAG, 9: POS, 10: NONNEG,
        11: FREE, 12: FREE, 13: FREE, 14: FREE, 15: POS,
    },
    "DC_Line_dat": {
        0: INT_POS, 1: BUS_DC, 2: BUS_DC, 3: FREE,
        4: NONNEG, 5: NONNEG, 6: NONNEG, 7: FLAG,
    },
    "DC_gen_dat": {
        0: BUS_DC, 1: INT, 4: FREE, 6: FLAG, 7: POS, 8: NONNEG, 9: FREE, 10: FREE,
    },
    "IC_dat": {
        0: BUS_AC, 1: BUS_DC, 9: NONNEG, 10: FREE, 11: FREE, 12: FREE,
        13: FREE, 14: FREE, 15: FLAG, 16: FREE, 17: FREE, 18: FREE, 19: FREE,
        20: POS, 21: POS,
    },
    "DCDC_Conv_dat": {
        0: BUS_DC, 1: BUS_DC, 8: NONNEG,
        # 2·3·4 는 안 연다 (머리말 참조)
    },
    "AC_Bus_dat": {
        0: BUS_AC, 1: FREE, 2: FREE,
        3: SHARE, 4: SHARE, 5: SHARE, 6: SHARE, 7: SHARE, 8: SHARE,
        9: FREE, 10: FREE, 11: POS, 12: FREE, 13: POS, 14: POS, 15: POS, 16: INT,
    },
    "DC_Bus_dat": {
        0: BUS_DC, 2: POS, 3: POS, 4: POS, 5: POS,
        # 1(Nominal Current) 은 안 연다 — 단위 미상 (머리말 참조)
    },
}


# 🚨 **계통을 가리키는 번호는 안 연다** (2026-09-08 점검 i33).
#
#   2026-08-27 에 *"일단 모든 거를 다 바꾼 다음에 계통 시나리오를 돌릴 수 있게"* 라는
#   지시로 96칸을 열었는데, 그때 **식별자까지 같이 열렸다.** 버스 번호를 고치면 그
#   번호를 가리키던 선로·발전기·변환기가 한꺼번에 어긋난다 — 값이 틀리는 게 아니라
#   **계통이 다른 것이 된다.**
#
#   ⚠️ 지시를 뒤집는 것이 아니다. 그 지시의 목적은 **시나리오를 돌리는 것**이고,
#      그 대상인 물리량·운전 조건 **85칸은 그대로 열려 있다**. 식별자를 바꾸는 일은
#      시나리오가 아니라 **계통을 새로 만드는** 일이라, 앱에 이미 있는 다른 길
#      (「엑셀로 만들기」로 뽑아 엑셀에서 고치기)이 맡는다.
IDENT = {
    "AC_Line_dat":   {0: "선로 번호", 1: "From 버스", 2: "To 버스"},
    "DC_Line_dat":   {0: "선로 번호", 1: "From 버스", 2: "To 버스"},
    "AC_gen_dat":    {0: "발전기가 붙는 버스"},
    "DC_gen_dat":    {0: "발전기가 붙는 버스"},
    "IC_dat":        {0: "변환기의 AC 버스", 1: "변환기의 DC 버스"},
    "DCDC_Conv_dat": {0: "DC/DC 의 한쪽 버스", 1: "DC/DC 의 다른 쪽 버스"},
    "AC_Bus_dat":    {0: "버스 번호"},
    "DC_Bus_dat":    {0: "버스 번호"},
}


def ident_why(table: str, col: int) -> str:
    """식별자 칸이면 **왜 회색인지** 한 줄. 아니면 빈 글."""
    name = IDENT.get(table, {}).get(col)
    if not name:
        return ""
    return (f"{name} — 계통을 가리키는 번호라 여기서는 못 고칩니다.\n"
            f"이 번호를 바꾸면 이것을 가리키던 다른 표가 어긋납니다.\n\n"
            f"바꾸려면 위의 [엑셀로 만들기] 로 뽑아 엑셀에서 고치세요.")


def editable(table: str) -> set[int]:
    """그 표에서 값을 고칠 수 있는 칸 (운전 조건은 `GRID_EDITABLE` 이 따로 갖는다)."""
    return set(RULES.get(table, {})) - set(IDENT.get(table, {}))


def _buses(case, which):
    import scenario as SC
    a = SC._values(case, "AC_Bus_dat" if which == BUS_AC else "DC_Bus_dat")
    if a.ndim != 2 or not a.size:
        return None                      # 그 표가 없으면 못 따진다 — 통과시킨다
    return {int(v) for v in a[:, 0] if not np.isnan(v)}


def check(case, table: str, col: int, value: float) -> str:
    """넣어도 되나. 되면 빈 글, 안 되면 **왜 안 되는지** 한 줄."""
    rule = RULES.get(table, {}).get(col)
    if rule is None:
        return ""
    if np.isnan(value):
        return "이 칸은 비울 수 없습니다. 숫자를 넣어 주세요."
    if rule in (BUS_AC, BUS_DC):
        have = _buses(case, rule)
        if have is None:
            return ""
        if int(value) != value:
            return "버스 번호는 정수여야 합니다."
        if int(value) not in have:
            kind = "AC" if rule == BUS_AC else "DC"
            near = sorted(have)[:6]
            return (f"{kind} 버스 {value:g} 번이 계통에 없습니다.\n"
                    f"있는 번호 (앞 6개) — {', '.join(str(b) for b in near)} …")
        return ""
    if rule == FLAG:
        return "" if value in (0, 1) else "0(끔) 아니면 1(켬) 이어야 합니다."
    if rule == INT_POS:
        if int(value) != value or value < 1:
            return "1 이상의 정수여야 합니다."
        return ""
    if rule == INT:
        return "" if int(value) == value else "정수여야 합니다."
    if rule == POS:
        return "" if value > 0 else "0 보다 커야 합니다."
    if rule == NONNEG:
        return "" if value >= 0 else "0 이상이어야 합니다."
    if rule == SHARE:
        return "" if 0 <= value <= 1 else "0 과 1 사이여야 합니다."
    return ""


def warn(arr, table: str, row: int, col: int, value: float) -> str:
    """막지는 않되 **알려 줄 것**. 짝 한계가 뒤집혔나 · ZIP 합이 1 이 아닌가.

    🚨 막지 않는 까닭 — 두 칸을 차례로 고치는 동안에는 **중간에 반드시 어긋난다.**
       Qmax 를 낮추려면 Qmax 를 먼저 치든 Qmin 을 먼저 치든 한 번은 뒤집힌다.
       막으면 고칠 방법이 없어진다.

    ⚠️ **표를 그릴 때 그 자리에서 부른다** — 고칠 때 적어 두고 들고 다니면 낡는다.
       그래서 케이스가 아니라 **그리는 데 쓰는 배열**을 받는다.
    """
    a = np.asarray(arr, dtype=float)
    if a.ndim != 2 or row >= a.shape[0]:
        return ""

    def val(c):
        return value if c == col else (float(a[row, c]) if c < a.shape[1] else np.nan)

    for lo, hi in PAIRS.get(table, []):
        if col not in (lo, hi):
            continue
        x, y = val(lo), val(hi)
        if not np.isnan(x) and not np.isnan(y) and x > y:
            return f"아래 한계({x:g})가 위 한계({y:g})보다 큽니다 — 뒤집혀 있습니다."
    for label, cols in SUMS.get(table, []):
        if col not in cols:
            continue
        vs = [val(c) for c in cols]
        if any(np.isnan(v) for v in vs):
            continue
        s = sum(vs)
        if abs(s - 1.0) > 1e-9:
            return f"{label} 합이 {s:g} 입니다 — 1 이어야 합니다."
    return ""
