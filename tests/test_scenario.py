# -*- coding: utf-8 -*-
"""scenario.py 가 진짜로 맞나 — **엔진에 넣어서** 확인한다 (PDR §7 2단계 1번 조각).

말로 맞다고 하지 않는다. 조건을 바꿔 실제로 풀고, 답이 달라지는지·못 푸는지를 본다.

    python tests/test_scenario.py
    python tests/test_scenario.py --quick   # 엔진을 안 쓰는 것만 (빠름)
"""

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SRC = REPO / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import scenario as S                    # noqa: E402
from load_case import load_case         # noqa: E402

CASE24 = REPO / "cases/ACDC_case24_MatACDC.xlsx"
CASE71 = REPO / "cases/ACDC_71bus_3IC_parallel.xlsx"
CIGRE = REPO / "cases/ACDC_CIGRE_MVACMVDCLVDC.xlsx"

fails: list[str] = []


def ok(cond: bool, what: str, detail: str = "") -> None:
    print(f"  {'✅' if cond else '🚨'} {what}" + (f"  — {detail}" if detail else ""))
    if not cond:
        fails.append(what)


def fingerprint(sol) -> np.ndarray:
    """결과 전체를 한 줄로. 전압 최저 하나만 보면 **바뀐 것을 놓친다**
    (발전기를 세워도 최저 전압 버스는 그대로일 수 있다)."""
    return np.concatenate([
        np.nan_to_num(np.asarray(getattr(sol, k), dtype=float)).ravel()
        for k in ("AC", "DC", "Branch", "loss")])


def find_row(case, table, a, b) -> int:
    arr = np.asarray(case.tables[table].values, dtype=float)
    sw = S.SWITCHES[table]
    i, j = sw.ident
    hit = [k for k, r in enumerate(arr) if int(r[i]) == a and int(r[j]) == b]
    if not hit:
        raise SystemExit(f"{table} 에 {a}–{b} 가 없습니다.")
    return hit[0]


# ══════════════════════════════ 엔진 없이 되는 것
def without_engine() -> None:
    print("엔진 없이 — 목록·적용·쪼개짐 검사")
    case = load_case(str(CASE24))

    # 1. 원본을 안 건드린다
    before = np.asarray(case.tables["AC_Line_dat"].values, dtype=float).copy()
    row = find_row(case, "AC_Line_dat", 106, 110)
    ch = S.toggle(case, "AC_Line_dat", row, on=False)
    after = S.apply(case, [ch])
    now = np.asarray(case.tables["AC_Line_dat"].values, dtype=float)
    ok(np.array_equal(np.nan_to_num(before), np.nan_to_num(now)),
       "원본은 그대로다")
    ok(float(np.asarray(after.tables["AC_Line_dat"].values)[row, 12]) == 0.0,
       "얹은 쪽만 꺼져 있다", ch.label)

    # 2. 켜짐 여부를 바꾼 것까지 반영해 읽는다
    ok(S.is_on(case, "AC_Line_dat", row) is True, "바꾸기 전에는 켜짐")
    ok(S.is_on(case, "AC_Line_dat", row, [ch]) is False, "바꾼 뒤에는 꺼짐")

    # 3. 되돌리기 = 목록에서 빼기
    ok(np.array_equal(
        np.nan_to_num(np.asarray(S.apply(case, []).tables["AC_Line_dat"].values, dtype=float)),
        np.nan_to_num(before)), "바꾼 것을 빼면 원본과 같다")

    # 4. 엔진이 안 읽는 것은 막는다
    for table in S.CANNOT:
        try:
            S.toggle(case, table, 0, on=False)
            ok(False, f"{table} 끄기를 막는다")
        except S.NotSupported as exc:
            ok(True, f"{table} 끄기를 막는다", str(exc)[:46])

    # 5. 부하 일괄 증감 — 첫 열(버스 번호)은 안 건드린다
    big = S.apply(case, [S.scale_load(1.5)])
    a = np.asarray(case.tables["AC_PLoad_dat"].values, dtype=float)
    b = np.asarray(big.tables["AC_PLoad_dat"].values, dtype=float)
    ok(np.array_equal(a[:, 0], b[:, 0]), "부하를 늘려도 버스 번호는 그대로")
    ok(np.allclose(np.nan_to_num(b[:, 1:]), np.nan_to_num(a[:, 1:]) * 1.5),
       "부하 값만 1.5배")

    # 6. 쪼개짐 — 아는 답과 맞나 (2026-08-06 전수 확인)
    ok(S.splits(case, [ch]) is None, "106–110 은 안 쪼갠다")
    r2 = find_row(case, "AC_Line_dat", 207, 208)
    msg = S.splits(case, [S.toggle(case, "AC_Line_dat", r2, on=False)])
    ok(msg is not None, "207–208 은 쪼갠다", (msg or "")[:52])

    c71 = load_case(str(CASE71))
    n_split = sum(
        S.splits(c71, [S.toggle(c71, "AC_Line_dat", k, on=False)]) is not None
        for k in range(np.asarray(c71.tables["AC_Line_dat"].values).shape[0]))
    ok(n_split == 37, "71bus 는 AC 선로 37개가 전부 쪼갠다", f"{n_split}개")
    # 🚨 IC 끄기는 막혀 있다 — 엔진에 반쯤만 먹혀서 그럴듯한데 틀린 답이 나온다(2026-08-06 실측)
    try:
        S.toggle(c71, "IC_dat", 0, on=False)
        ok(False, "IC 끄기를 막는다")
    except S.NotSupported:
        ok(True, "IC 끄기를 막는다", "엔진에 반쯤만 먹힌다")

    # 7. DC/DC 는 Status 열이 없다 — 껐다 켜면 원래 운전모드로 돌아와야 한다
    cig = load_case(str(CIGRE))
    mode0 = float(np.asarray(cig.tables["DCDC_Conv_dat"].values, dtype=float)[0, 9])
    off = S.toggle(cig, "DCDC_Conv_dat", 0, on=False)
    on = S.toggle(cig, "DCDC_Conv_dat", 0, on=True)
    back = float(np.asarray(S.apply(cig, [off, on]).tables["DCDC_Conv_dat"].values,
                            dtype=float)[0, 9])
    ok(off.value == 0.0 and back == mode0,
       "DC/DC 를 껐다 켜면 원래 운전모드로", f"{mode0:g} → 0 → {back:g}")

    # 8. 지문 — 줄이 달라지면 알아챈다
    moved = case.copy()
    moved.tables["AC_Line_dat"].iloc[row, 1] = 999.0
    ok(S.stale(moved, [ch]) != [], "줄이 달라지면 알려 준다")
    ok(S.stale(case, [ch]) == [], "안 달라졌으면 조용하다")

    # 9. 이름 짓기
    book = S.Book()
    book.add(case, [])
    s1 = book.add(case, [ch])
    s2 = book.add(case, [ch])
    ok(book.base().name == "원본", "원본이 첫 줄")
    ok(s1.name != s2.name, "같은 이름은 겹치지 않게", f"{s1.name} / {s2.name}")


# ══════════════════════════════ 엔진에 실제로 넣어 보기
def with_engine() -> None:
    import app_engine

    print()
    print("엔진에 넣어서 — 조건을 바꾸면 답이 정말 달라지나")
    case = load_case(str(CASE24))
    base = app_engine.solve(case)
    v0 = float(np.nanmin(np.asarray(base.AC, dtype=float)[:, 1]))

    # 1. 안 쪼개는 선로를 끄면 → 풀리고, 답이 달라진다
    row = find_row(case, "AC_Line_dat", 106, 110)
    ch = S.toggle(case, "AC_Line_dat", row, on=False)
    sol = app_engine.solve(S.apply(case, [ch]))
    v1 = float(np.nanmin(np.asarray(sol.AC, dtype=float)[:, 1]))
    ok(abs(v1 - v0) > 1e-6, "선로를 끄면 답이 달라진다",
       f"전압 최저 {v0:.4f} → {v1:.4f} ({v1 - v0:+.4f})")

    # 2. 안 풀리는 조건은 예외로 온다 (converged=False 가 아니라)
    bad = find_row(case, "AC_Line_dat", 107, 108)
    try:
        app_engine.solve(S.apply(case, [S.toggle(case, "AC_Line_dat", bad, on=False)]))
        ok(False, "107–108 을 끄면 못 푼다")
    except Exception as exc:
        ok("조류계산 실패" in str(exc), "못 푸는 것은 예외로 온다",
           str(exc).splitlines()[0][:40])

    # 3. 부하를 늘리면 손실이 는다
    up = app_engine.solve(S.apply(case, [S.scale_load(1.2)]))
    l0 = float(np.nansum(np.asarray(base.loss, dtype=float)[0, :3]))
    l1 = float(np.nansum(np.asarray(up.loss, dtype=float)[0, :3]))
    ok(l1 > l0, "부하 1.2배 → 손실이 는다", f"{l0:.4g} → {l1:.4g}")

    # 4. 발전기를 세우면 답이 달라진다 (엑셀 9열 — 엔진이 PV/Slack 분류에서 뺀다)
    grow = 0
    gen = S.toggle(case, "AC_gen_dat", grow, on=False)
    g = app_engine.solve(S.apply(case, [gen]))
    f0, fg = fingerprint(base), fingerprint(g)
    vg = float(np.nanmin(np.asarray(g.AC, dtype=float)[:, 1]))
    ok(f0.shape == fg.shape and not np.allclose(f0, fg),
       "발전기를 세우면 답이 달라진다",
       f"{gen.label} · 전압 최저는 {v0:.4f} → {vg:.4f} 로 그대로지만 조류가 바뀐다")

    # 5. 71bus 에서 DC 선로를 끄면 답이 달라진다
    #    (AC 선로는 37개가 전부 계통을 쪼개고, IC 끄기는 막혀 있다 ⇒ 이 계통에서 되는 유일한 길)
    c71 = load_case(str(CASE71))
    b71 = app_engine.solve(c71)
    n_dc = np.asarray(c71.tables["DC_Line_dat"].values).shape[0]
    free = [k for k in range(n_dc)
            if S.splits(c71, [S.toggle(c71, "DC_Line_dat", k, on=False)]) is None]
    # 🚨 확인된 사실 — 71bus 는 AC 도 DC 도 **모든 선로가 계통을 쪼갠다**(방사형).
    #    IC 끄기까지 막혀 있으므로 이 계통에서는 지금 켜고 끌 수 있는 것이 **하나도 없다.**
    #    쪼개지는 조건을 막을지 경고만 할지는 아직 안 정했다(👉 사용자 판단).
    ok(free == [], "71bus 는 DC 선로도 전부 계통을 쪼갠다",
       f"DC 선로 {n_dc}개 중 안 쪼개는 것 {len(free)}개")
    dcl = S.toggle(c71, "DC_Line_dat", 0, on=False)
    s71 = app_engine.solve(S.apply(c71, [dcl]))
    f0, f1 = fingerprint(b71), fingerprint(s71)
    ok(f0.shape == f1.shape and not np.allclose(f0, f1),
       "그래도 엔진은 풀어 준다 — 막을지 경고만 할지는 미정", dcl.label)

    app_engine.shutdown()


def main() -> int:
    ap = argparse.ArgumentParser(description="scenario.py 검증")
    ap.add_argument("--quick", action="store_true", help="엔진을 안 쓰는 것만")
    args = ap.parse_args()

    without_engine()
    if not args.quick:
        with_engine()

    print()
    if fails:
        print(f"🚨 어긋남 {len(fails)}건")
        for f in fails:
            print(f"   · {f}")
        return 1
    print("✅ 전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
