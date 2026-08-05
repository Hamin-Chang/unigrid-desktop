# -*- coding: utf-8 -*-
"""서식 v2 검증 — **v1 원본과 변환한 v2 가 엔진에 같은 숫자를 주는가.**

왜 이걸 보나
    서식을 바꾸면서 값이 조용히 달라지는 것이 가장 무서운 실패다.
    엔진에 넘어가는 표를 v1 경로와 v2 경로 양쪽에서 만들어 **자리마다 견준다.**
    같으면 서식만 바뀌고 계통은 그대로라는 뜻이다.

    python tests/test_format_v2.py            # cases/ 전부
    python tests/test_format_v2.py --only 71  # 이름에 그 글자가 든 것만
"""

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SRC = REPO / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import convert_case                      # noqa: E402
import read_v2                           # noqa: E402
from load_case import load_case          # noqa: E402

# 엔진에 실제로 넘어가는 표들 (app_worker.TABLE_ORDER 와 같다)
KEYS = ("Base_dat", "AC_Bus_dat", "AC_Line_dat", "AC_gen_dat", "AC_3wtrans_dat",
        "DC_Bus_dat", "DC_Line_dat", "DC_gen_dat", "IC_dat", "DCDC_Conv_dat",
        "AC_PLoad_dat", "AC_QLoad_dat", "DC_PLoad_dat")

# 서식 v2 에서 **일부러 버린** 열 — 여기는 달라도 통과다(설계 문서 §4).
#   Base 8열   : 안 읽히던 |V| deadband
#   DCDC 3·4·5 : 현행 솔버 v7 이 안 읽는 효율곡선 (케이스 56개 전부 0)
DROPPED = {"Base_dat": {8}, "DCDC_Conv_dat": {3, 4, 5}}


def compare(name: str, a: np.ndarray, b: np.ndarray) -> list[str]:
    """엔진에 넘어갈 두 표를 견준다. 같으면 빈 목록."""
    bad = []
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size == 0 and b.size == 0:
        return bad

    # v2 는 버린 열만큼 폭이 짧을 수 있다 — 겹치는 데까지만 견준다
    rows = min(a.shape[0], b.shape[0]) if a.ndim == b.ndim == 2 else 0
    if a.ndim != 2 or b.ndim != 2:
        return [f"{name}: 모양이 표가 아니다 {a.shape} / {b.shape}"]
    if a.shape[0] != b.shape[0]:
        bad.append(f"{name}: 줄 수가 다름 {a.shape[0]} → {b.shape[0]}")
    cols = min(a.shape[1], b.shape[1])

    drop = DROPPED.get(name, set())
    for j in range(cols):
        if (j + 1) in drop:
            continue
        x, y = a[:rows, j], b[:rows, j]
        both_nan = np.isnan(x) & np.isnan(y)
        d = np.abs(np.nan_to_num(x) - np.nan_to_num(y))
        d[both_nan] = 0.0
        # 한쪽만 비어 있는 자리: v1 이 비었는데 v2 가 기본값을 채운 것은 통과
        only = np.isnan(x) & ~np.isnan(y)
        d[only] = 0.0
        # ⚠️ 절대 차이가 아니라 **상대 차이**로 본다. W ↔ MW 왕복은 이진 부동소수라
        #    딱 안 떨어져서, 1억 W 짜리 값은 절대 차이가 1e-8 쯤 남는다(상대로는 1e-16).
        scale = np.maximum(np.abs(np.nan_to_num(x)), 1.0)
        rel = d / scale
        m = float(np.max(rel)) if rel.size else 0.0
        if m > 1e-12:
            i = int(np.argmax(rel))
            bad.append(f"{name}: {j+1}열 최대 상대차이 {m:.3e} "
                       f"(줄 {i+1}: {x[i]:g} → {y[i]:g})")
    return bad


def check(path: Path, out_dir: Path) -> list[str]:
    v1 = load_case(str(path)).tables
    out, notes = convert_case.convert_file(path, out_dir)
    if out is None:
        return [f"변환 안 됨 — {'; '.join(notes)}"]
    v2 = read_v2.read_tables(out)

    bad = []
    for k in KEYS:
        a = np.asarray(getattr(v1.get(k), "values", v1.get(k)), dtype=float)
        bad += compare(k, a, v2.get(k, np.zeros((0, 0))))

    # 같은 진입점(`load_case`)이 새 서식도 알아보고 같은 값을 주는지.
    # 여기가 깨지면 앱이 v2 파일을 열지 못한다.
    through = load_case(str(out))
    if float(through.mode) != float(load_case(str(path)).mode):
        bad.append(f"Mode 가 다름 {load_case(str(path)).mode} → {through.mode}")
    for k in KEYS:
        a = np.asarray(getattr(v1.get(k), "values", v1.get(k)), dtype=float)
        b = np.asarray(getattr(through.tables.get(k), "values",
                               through.tables.get(k)), dtype=float)
        bad += [f"(load_case 경유) {m}" for m in compare(k, a, b)]
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description="서식 v2 — v1 과 같은 숫자가 나오는지")
    ap.add_argument("--only", metavar="글자")
    args = ap.parse_args()

    files = sorted((REPO / "cases").glob("*.xlsx"))
    files = [f for f in files if not f.stem.endswith("_v2")]
    if args.only:
        files = [f for f in files if args.only.lower() in f.name.lower()]

    out_dir = Path(tempfile.mkdtemp(prefix="unigrid_v2_"))
    ok = ng = 0
    for f in files:
        print(f"  {f.stem:<34}", end="", flush=True)
        try:
            bad = check(f, out_dir)
        except Exception as exc:
            print(f"실패 — {type(exc).__name__}: {exc}")
            ng += 1
            continue
        if bad:
            print("다름")
            for line in bad[:8]:
                print(f"      {line}")
            ng += 1
        else:
            print("같음")
            ok += 1

    print()
    print(f"같음 {ok} · 다름 {ng}")
    print(f"변환본: {out_dir}")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
