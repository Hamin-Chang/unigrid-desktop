# -*- coding: utf-8 -*-
"""scenario.py — 계통 조건을 바꾸고, 그 결과를 시나리오로 담는다 (PDR §4.3 · §7 2단계).

화면이 없다. 그래서 Qt 없이 시험할 수 있고, 회귀에 걸 수 있다.

들고 있는 방식
    원본 케이스는 **읽고 나면 바뀌지 않는다.** 그 위에 "바꾼 것" 목록을 얹고,
    계산 직전에 원본 + 목록을 합쳐 한 벌을 만들어 엔진에 넘긴다.
    · 되돌리기가 공짜다 — 목록에서 한 줄 빼면 끝
    · "무엇을 바꿨나" 가 곧 목록이라 화면에 그대로 보여 주면 된다
    · 저장하면 몇 줄이다 (71bus 표 전체가 아니라 "선로 12 끔" 한 줄)

언제 푸나 (2026-08-06 사용자 확정)
    바꾸는 동안은 **안 푼다.** 다 바꾸고 버튼을 누를 때 한 번 푼다.
    ⇒ 버튼 한 번 = 조류해석 한 번 = 시나리오 한 줄.

    python src/scenario.py cases/ACDC_case24_MatACDC.xlsx     # 스스로 점검
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Sequence

import numpy as np


# ────────────────────────────────────────────── 켜고 끌 수 있는 것
@dataclass(frozen=True)
class Switch:
    """어느 표의 어느 열이 '켜짐/꺼짐' 인가 (열 번호는 **0부터**)."""

    table: str
    col: int
    off: float
    on: float | None          # None = 끄기 전 값을 그대로 되살린다
    ident: tuple[int, ...]    # 그 줄을 알아보는 열들 (지문)
    ident_names: tuple[str, ...]
    name: str                 # 사람이 부르는 이름
    two_sided: bool = False   # 양 끝이 서로 다른 계열인가 (IC 는 AC↔DC)


# 🚨 여기 있는 것만 **엔진에 정말로 먹힌다.**
#
#    어떻게 알았나 (2026-08-06): 소스를 읽어 판단하지 않았다 — 그 방법으로 **두 번 틀렸다**
#    (컴파일에 쓰인 `v14/functions/` 대신 `v14_lite/functions/` 를 읽어 엉뚱한 결론을 냈다).
#    대신 **그 칸을 0으로 만들어 실제로 풀고 답이 달라지는지**로 가렸다(케이스 4개).
#    답이 한 비트도 안 달라지면 그 칸은 계산에 안 쓰이는 것이다. 근거: `probe.log`
SWITCHES: dict[str, Switch] = {
    "AC_Line_dat": Switch(
        "AC_Line_dat", 12, 0.0, 1.0, (1, 2), ("From", "To"), "AC 선로"),
    #   v14/functions/preprocess_AC_network.m:46-47 — 상태 0인 줄을 **표에서 지운다**
    "DC_Line_dat": Switch(
        "DC_Line_dat", 7, 0.0, 1.0, (1, 2), ("From", "To"), "DC 선로"),
    #   v14/functions/preprocess_DC_network_ACDC.m:52-53 — 같은 방식
    "AC_gen_dat": Switch(
        "AC_gen_dat", 8, 0.0, 1.0, (0,), ("버스",), "AC 발전기"),
    #   v14/functions/preprocess_AC_gen_ACDC.m:17-18 — "꺼진 발전기는 PV/Slack 분류에서 제외"
    "DC_gen_dat": Switch(
        "DC_gen_dat", 6, 0.0, 1.0, (0,), ("버스",), "DC 발전기"),
    #   v14/functions/preprocess_DC_gen_ACDC.m:18-25 — 2026-08-06 에 **고쳐서 다시 컴파일했다(7차).**
    #   그전에는 7열을 아예 안 읽어서, 껐는데 답이 한 비트도 안 달라졌다.
    "IC_dat": Switch(
        "IC_dat", 15, 0.0, 1.0, (0, 1), ("AC 버스", "DC 버스"), "IC", two_sided=True),
    #   v14/functions/preprocess_IC_sub4.m:40-42 — 2026-08-06 에 **고쳐서 다시 컴파일했다(6차).**
    #   그전에는 IC_status 를 읽어 IC_status_on 만 만들고 거르지 않아서, 엑셀에서 IC 를 꺼도
    #   계통에서 안 빠졌다(71bus 는 3대를 다 꺼도 답이 그대로였다). 이제 선로·발전기와 같이
    #   **꺼진 줄을 표에서 지운다.**
    #   ⚠️ 고칠 파일은 `preprocess_IC.m` 이 아니라 **`preprocess_IC_sub4.m`** 이다 —
    #      실제로 불리는 것은 `runpfACDC.m:83` 의 sub4 판이다(한 번 헛짚었다).
    "DCDC_Conv_dat": Switch(
        "DCDC_Conv_dat", 9, 0.0, None, (0, 1), ("MVDC 버스", "LVDC 버스"), "DC/DC",
        two_sided=True),
    #   v14/functions/preprocess_DCDC_conv.m:48-49 — conv.mode = 10열 · status = mode > 0
    #   ⚠️ DC/DC 는 따로 된 Status 열이 없다. **운전모드가 0이면 꺼진 것**으로 친다.
    #      그래서 다시 켤 때 1이 아니라 **끄기 전 모드 값**을 되살려야 한다(on=None).
}

# 🚨 엑셀에 칸은 있는데 **믿을 수 없는 것.** 끄는 시늉만 하거나, 계통에 따라 되기도 하고 안 되기도 한다.
# 지금은 비어 있다 — 2026-08-06 에 IC 와 DC 발전기를 엔진에서 고쳐 다섯 가지가 전부 먹힌다.
# 못 하는 것이 다시 생기면 여기에 **왜 못 하는지**와 함께 넣는다(막기만 하면 사용자가 이유를 모른다).
CANNOT: dict[str, str] = {}

# 일괄 증감이 건드리는 표 (첫 열은 버스 번호라 건드리지 않는다)
LOAD_TABLES = ("AC_PLoad_dat", "AC_QLoad_dat", "DC_PLoad_dat")


class NotSupported(ValueError):
    """지금은 못 바꾸는 것 — 왜 못 바꾸는지 말해 준다."""


# ────────────────────────────────────────────── 바꾼 것 한 줄
@dataclass(frozen=True)
class Cell:
    """칸 하나를 바꾼다."""

    table: str
    row: int                      # 0부터
    col: int                      # 0부터 (엔진이 아는 자리)
    value: float
    label: str
    mark: tuple[tuple[str, float], ...] = ()   # 지문 — 그 줄을 알아보는 값

    def kind(self) -> str:
        return "칸"


@dataclass(frozen=True)
class Scale:
    """여러 표의 값을 통째로 곱한다 (부하 일괄 증감).

    칸 목록으로 펼치지 않는 이유: 71bus 24시각 부하는 칸이 **수천 개**다.
    """

    tables: tuple[str, ...]
    factor: float
    label: str
    skip_first_col: bool = True   # 첫 열은 버스 번호

    def kind(self) -> str:
        return "곱하기"


Change = Cell | Scale


# ────────────────────────────────────────────── 표 다루기 (DataFrame · ndarray 둘 다)
def _values(case: Any, key: str) -> np.ndarray:
    t = case.tables.get(key)
    if t is None:
        return np.zeros((0, 0))
    arr = np.asarray(getattr(t, "values", t), dtype=float)
    return arr if arr.ndim == 2 else np.zeros((0, 0))


def _put(case: Any, key: str, row: int, col: int, value: float) -> None:
    t = case.tables[key]
    if hasattr(t, "iloc"):
        t.iloc[row, col] = value
    else:
        t[row, col] = value


def _has_row(case: Any, key: str, row: int) -> bool:
    arr = _values(case, key)
    return arr.ndim == 2 and 0 <= row < arr.shape[0]


# ────────────────────────────────────────────── 켜고 끄기
def toggle(case: Any, table: str, row: int, on: bool) -> Cell:
    """그 줄을 켜거나 끄는 '바꾼 것' 한 줄을 만든다. (케이스는 안 건드린다)"""
    if table in CANNOT:
        raise NotSupported(f"{CANNOT[table]} 는 아직 앱에서 못 끕니다.")
    sw = SWITCHES.get(table)
    if sw is None:
        raise NotSupported(f"'{table}' 은 켜고 끄는 대상이 아닙니다.")
    arr = _values(case, table)
    if not (0 <= row < arr.shape[0]):
        raise NotSupported(f"{sw.name} 에 {row + 1}번째 줄이 없습니다.")

    if on:
        value = sw.on if sw.on is not None else _original_on(case, table, row)
    else:
        value = sw.off
    return Cell(table=table, row=row, col=sw.col, value=float(value),
                label=f"{describe_row(case, table, row)} {'켬' if on else '끔'}",
                mark=row_mark(case, table, row))


def _original_on(case: Any, table: str, row: int) -> float:
    """다시 켤 때 되살릴 값 (DC/DC 는 1이 아니라 원래 운전모드다)."""
    sw = SWITCHES[table]
    v = float(_values(case, table)[row, sw.col])
    return v if v and v != sw.off else 1.0


def row_mark(case: Any, table: str, row: int) -> tuple[tuple[str, float], ...]:
    """그 줄의 지문 — 파일을 다시 읽어 줄이 밀렸을 때 알아채려고 남긴다."""
    sw = SWITCHES.get(table)
    if sw is None:
        return ()
    arr = _values(case, table)
    return tuple((name, float(arr[row, c]))
                 for name, c in zip(sw.ident_names, sw.ident) if c < arr.shape[1])


def describe_row(case: Any, table: str, row: int) -> str:
    """줄 하나를 사람이 부르는 이름으로.

    양쪽이 **다른 계열**이면(IC 는 AC↔DC) 어느 쪽이 어느 쪽인지 밝힌다 —
    "IC 107–1" 만 보면 107이 AC 버스인지 DC 버스인지 알 수 없다.
    """
    sw = SWITCHES.get(table)
    if sw is None:
        return f"{table} {row + 1}번째 줄"
    mark = row_mark(case, table, row)
    if not mark:
        return f"{sw.name} {row + 1}번째 줄"
    if sw.two_sided:                                  # 양 끝이 다른 계열 — 어느 쪽인지 밝힌다
        return f"{sw.name} ({' ↔ '.join(f'{n} {int(v)}' for n, v in mark)})"
    return f"{sw.name} {'–'.join(str(int(v)) for _, v in mark)}"


def is_on(case: Any, table: str, row: int, changes: Sequence[Change] = ()) -> bool:
    """바꾼 것까지 반영해서, 지금 켜져 있나."""
    sw = SWITCHES.get(table)
    if sw is None:
        return True
    value = float(_values(case, table)[row, sw.col])
    for ch in changes:
        if isinstance(ch, Cell) and ch.table == table and ch.row == row and ch.col == sw.col:
            value = ch.value
    return value != sw.off


def scale_load(factor: float) -> Scale:
    return Scale(tables=LOAD_TABLES, factor=float(factor),
                 label=f"부하 전체 ×{factor:g}")


# ────────────────────────────────────────────── 원본 + 바꾼 것 → 한 벌
def apply(case: Any, changes: Sequence[Change]) -> Any:
    """원본은 그대로 두고, 바꾼 것을 얹은 **새 케이스**를 돌려준다."""
    out = case.copy()
    for ch in changes:
        if isinstance(ch, Cell):
            if not _has_row(out, ch.table, ch.row):
                raise NotSupported(
                    f"'{ch.label}' 을 넣을 자리가 없습니다 "
                    f"({ch.table} 에 {ch.row + 1}번째 줄이 없음).")
            _put(out, ch.table, ch.row, ch.col, ch.value)
        else:
            for key in ch.tables:
                t = out.tables.get(key)
                arr = _values(out, key)
                if arr.size == 0:
                    continue
                start = 1 if ch.skip_first_col else 0
                if hasattr(t, "iloc"):
                    t.iloc[:, start:] = t.iloc[:, start:] * ch.factor
                else:
                    t[:, start:] = t[:, start:] * ch.factor
    return out


def stale(case: Any, changes: Sequence[Change]) -> list[str]:
    """지문이 안 맞는 것 — 파일을 다시 읽어 줄이 밀렸는지 알려 준다."""
    bad = []
    for ch in changes:
        if not isinstance(ch, Cell) or not ch.mark:
            continue
        now = row_mark(case, ch.table, ch.row) if _has_row(case, ch.table, ch.row) else ()
        if now != ch.mark:
            was = ", ".join(f"{n} {v:g}" for n, v in ch.mark)
            bad.append(f"{ch.label} — 그 줄이 달라졌습니다 (담을 때: {was})")
    return bad


def describe(changes: Sequence[Change]) -> str:
    if not changes:
        return "바꾼 것 없음"
    return " · ".join(ch.label for ch in changes)


# ────────────────────────────────────────────── 두 조각이 나는지 (계산 전에)
def _groups(case: Any, changes: Sequence[Change] = ()) -> list[set]:
    """켜져 있는 것만 이어 붙여 **덩어리**를 만든다.

    🚨 AC 선로만 세면 틀린다. AC 로 끊겨도 IC·DC 선로·DC/DC 로 이어져 있으면 멀쩡히 풀린다
       (71bus 는 IC 가 3대 병렬로 붙어 있다). 그래서 넷을 함께 센다.
    """
    live = apply(case, changes) if changes else case
    parent: dict[Any, Any] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    def ok(*vals) -> bool:
        return all(v is not None and not np.isnan(v) for v in vals)

    for side, key in (("AC", "AC_Bus_dat"), ("DC", "DC_Bus_dat")):
        arr = _values(live, key)
        for b in (arr[:, 0] if arr.size else []):
            if ok(b):
                find((side, int(b)))

    # (표, From열, To열, 어느 쪽 버스인가, 상태 열, 꺼진 값)
    EDGES = (
        ("AC_Line_dat", 1, 2, ("AC", "AC"), 12, 0.0),
        ("DC_Line_dat", 1, 2, ("DC", "DC"), 7, 0.0),
        ("IC_dat", 0, 1, ("AC", "DC"), 15, 0.0),
        ("DCDC_Conv_dat", 0, 1, ("DC", "DC"), 9, 0.0),
    )
    for key, ci, cj, (si, sj), cs, off in EDGES:
        arr = _values(live, key)
        for r in arr:
            if r.size <= max(ci, cj) or not ok(r[ci], r[cj]):
                continue
            if r.size > cs and r[cs] == off:
                continue                          # 꺼진 것은 잇지 않는다
            union((si, int(r[ci])), (sj, int(r[cj])))

    out: dict[Any, set] = {}
    for k in list(parent):
        out.setdefault(find(k), set()).add(k)
    return list(out.values())


def n_islands(case: Any, changes: Sequence[Change] = ()) -> int:
    return len(_groups(case, changes))


def splits(case: Any, changes: Sequence[Change]) -> str | None:
    """이 조건이 계통을 쪼개나. 쪼개면 사람이 읽을 설명, 아니면 None.

    ⭐ **막지 않는다. 경고만 한다** (2026-08-06 사용자 확정).
       처음에는 계산 전에 막기로 했는데, 실제로 재 보니 **71bus 는 AC 37개·DC 32개가
       전부 계통을 쪼갠다**(방사형 배전 계통이라 당연하다). 막으면 그 계통에서는
       켜고 끌 수 있는 것이 하나도 없어진다. 게다가 엔진은 쪼개진 상태도 풀어 준다.
       ⇒ 부르는 쪽은 이 말을 **띄우기만 하고 계산은 그대로 진행**한다.

    ⚠️ 쪼개짐은 **발산과 다르다** — 발산은 "못 찾은 것"이고 이것은 "원래 그런 모양"이다.
       떨어져 나간 쪽에 전원이 없으면 그 답은 뜻이 없으므로, 결과를 볼 때 감안해야 한다.
    """
    was = n_islands(case)
    now = n_islands(case, changes)
    if now <= was:
        return None
    groups = sorted(_groups(case, changes), key=len)
    small = groups[0]
    names = ", ".join(f"{s} {n}" for s, n in sorted(small)[:6])
    more = f" 외 {len(small) - 6}곳" if len(small) > 6 else ""
    return (f"계통이 {was}덩어리에서 {now}덩어리로 쪼개집니다. "
            f"떨어져 나가는 곳: {names}{more}")


# ────────────────────────────────────────────── 시나리오
@dataclass
class Scenario:
    """담아 둔 것 한 줄. 결과나 실패 사유를 함께 들고 있다."""

    name: str
    changes: tuple[Change, ...] = ()
    solution: Any = None                  # app_engine.Solution
    error: str | None = None              # 안 풀렸으면 그 사유
    base: bool = False                    # 원본인가

    @property
    def solved(self) -> bool:
        return self.solution is not None and self.error is None

    @property
    def summary(self) -> str:
        if self.error:
            return "안 풀림"
        if self.solution is None:
            return "아직 계산 안 함"
        return f"반복 {int(self.solution.iters)}회"

    def vmin(self) -> float:
        if not self.solved:
            return float("nan")
        ac = np.asarray(self.solution.AC, dtype=float)
        return float(np.nanmin(ac[:, 1])) if ac.size else float("nan")

    def against(self, other: "Scenario") -> float:
        """원본 대비 전압 최저가 얼마나 달라졌나."""
        a, b = other.vmin(), self.vmin()
        return b - a if not (np.isnan(a) or np.isnan(b)) else float("nan")


def auto_name(case: Any, changes: Sequence[Change]) -> str:
    """담을 때 자동으로 붙는 이름 — 사용자가 고칠 수 있다."""
    if not changes:
        return "원본"
    if len(changes) == 1:
        return changes[0].label
    # 곱하기가 섞여 있어도 첫 줄 이름을 쓴다 — "바꾼 것 2건" 은 무엇인지 안 보인다.
    return f"{changes[0].label} 외 {len(changes) - 1}건"


@dataclass
class Book:
    """세션 안에서만 사는 시나리오 목록. 파일로 저장·불러오기는 아직 안 만든다(PDR 미결 M1)."""

    items: list[Scenario] = field(default_factory=list)

    def add(self, case: Any, changes: Sequence[Change], solution=None,
            error: str | None = None, name: str | None = None) -> Scenario:
        s = Scenario(name=name or self._unique(auto_name(case, changes)),
                     changes=tuple(changes), solution=solution, error=error,
                     base=not changes)
        self.items.append(s)
        return s

    def _unique(self, name: str) -> str:
        used = {s.name for s in self.items}
        if name not in used:
            return name
        n = 2
        while f"{name} ({n})" in used:
            n += 1
        return f"{name} ({n})"

    def base(self) -> Scenario | None:
        for s in self.items:
            if s.base:
                return s
        return self.items[0] if self.items else None

    def remove(self, s: Scenario) -> None:
        if s in self.items:
            self.items.remove(s)

    def rename(self, s: Scenario, name: str) -> None:
        i = self.items.index(s)
        self.items[i] = replace(s, name=self._unique(name))


# ────────────────────────────────────────────── 스스로 점검
def _selfcheck(path: str) -> int:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from load_case import load_case

    case = load_case(path)
    print(f"{Path(path).name}   덩어리 {n_islands(case)}개")

    for table, sw in SWITCHES.items():
        arr = _values(case, table)
        n = arr.shape[0] if arr.size and not np.all(np.isnan(arr)) else 0
        print(f"  {sw.name:<8} {n:>4}줄", end="")
        if n:
            before = _values(case, table).copy()      # 원본을 미리 떠 둔다
            ch = toggle(case, table, 0, on=False)
            after = apply(case, [ch])
            moved = float(_values(after, table)[0, sw.col])
            kept = np.array_equal(np.nan_to_num(before),
                                  np.nan_to_num(_values(case, table)))
            print(f"   보기: {ch.label}  (그 칸 {moved:g}) "
                  f"· 원본 그대로 {'예' if kept else '🚨 아니오'}", end="")
            split = splits(case, [ch])
            print(f"  → {'쪼개짐' if split else '안 쪼개짐'}")
        else:
            print()

    for table, why in CANNOT.items():
        arr = _values(case, table)
        if arr.size and not np.all(np.isnan(arr)):
            try:
                toggle(case, table, 0, on=False)
                print(f"  🚨 {table} 을 껐다 — 막혔어야 한다")
                return 1
            except NotSupported as exc:
                print(f"  막힘 확인: {exc}")

    book = Book()
    book.add(case, [])
    ch = toggle(case, "AC_Line_dat", 0, on=False)
    book.add(case, [ch])
    print(f"  목록: {[s.name for s in book.items]}")
    print(f"  설명: {describe([ch, scale_load(1.1)])}")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_selfcheck(sys.argv[1] if len(sys.argv) > 1
                                else "cases/ACDC_case24_MatACDC.xlsx"))
