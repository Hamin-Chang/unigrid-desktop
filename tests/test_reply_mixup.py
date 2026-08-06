# -*- coding: utf-8 -*-
"""앞 계산의 결과를 집어 오지 않는가 — 2026-08-06 에 실제로 있었던 결함의 파수꾼.

무슨 일이 있었나
    계산이 안 풀리면 MATLAB 이 특이 행렬 경고와 스택을 **878줄** 찍는다.
    그런데 앱은 결과 줄을 **200줄까지만** 찾고 포기했다. 포기해도 결과는 통로에 남아
    **다음 계산이 그것을 집어 갔다.** 한 번 어긋나면 계속 어긋나서 —
    안 풀려야 할 조건이 **"반복 4회로 잘 풀렸다"** 고 나왔다. 틀린 답을 옳은 답처럼 보여준 것이다.

무엇을 확인하나
    잘 풀리는 조건과 안 풀리는 조건을 **번갈아** 여러 번 던진다.
    · 잘 풀리는 것은 **매번** 같은 반복 횟수로 풀려야 한다
    · 안 풀리는 것은 **매번** 실패해야 한다 (한 번이라도 "풀렸다" 면 남의 답을 집어 온 것이다)

    python tests/test_reply_mixup.py            # 12쌍 (기본)
    python tests/test_reply_mixup.py --pairs 30 # 더 세게
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SRC = REPO / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import app_engine                       # noqa: E402
from load_case import load_case         # noqa: E402

CASE = REPO / "cases/ACDC_case24_MatACDC.xlsx"
STATUS_COL = 12          # AC Line Data 13번째 열 = Status
OFF = (107, 108)         # 이 선로를 끄면 안 풀린다 (2026-08-06 전수 확인)


def build():
    base = load_case(str(CASE))
    rows = base.tables["AC_Line_dat"].values
    hit = [i for i, r in enumerate(rows)
           if int(r[1]) == OFF[0] and int(r[2]) == OFF[1]]
    if not hit:
        raise SystemExit(f"{CASE.name} 에 선로 {OFF[0]}–{OFF[1]} 이 없습니다.")
    bad = base.copy()
    bad.tables["AC_Line_dat"].iloc[hit[0], STATUS_COL] = 0.0
    return base, bad


def main() -> int:
    ap = argparse.ArgumentParser(description="앞 계산의 결과를 집어 오지 않는지")
    ap.add_argument("--pairs", type=int, default=12, help="몇 쌍을 던져 볼지")
    args = ap.parse_args()

    base, bad = build()

    # 기준 잡기 — 원본이 몇 회 반복으로 풀리는지, 그리고 bad 가 정말 안 풀리는지
    ref = app_engine.solve(base)
    want = int(ref.iters)
    try:
        app_engine.solve(bad)
        print(f"⚠️ 선로 {OFF[0]}–{OFF[1]} 을 꺼도 풀립니다. 이 시험의 전제가 깨졌습니다.")
        print("   (케이스가 바뀌었을 수 있습니다 — 안 풀리는 다른 선로로 OFF 를 바꾸세요.)")
        return 2
    except Exception:
        pass

    print(f"{CASE.stem} · 원본은 반복 {want}회로 풀리고, "
          f"선로 {OFF[0]}–{OFF[1]} 을 끄면 안 풀린다. {args.pairs}쌍을 번갈아 던진다.")

    bad_solved = wrong_iters = good_failed = 0
    for k in range(args.pairs):
        try:
            app_engine.solve(bad)
            bad_solved += 1               # 🚨 안 풀려야 하는데 풀렸다 = 남의 답
        except Exception:
            pass
        try:
            sol = app_engine.solve(base)
            if int(sol.iters) != want:
                wrong_iters += 1          # 🚨 같은 입력인데 답이 다르다
        except Exception:
            good_failed += 1              # 🚨 잘 풀리던 것이 실패했다

    bad_n = bad_solved + wrong_iters + good_failed
    print()
    print(f"  안 풀려야 하는데 풀림 : {bad_solved}")
    print(f"  잘 풀리던 것이 실패   : {good_failed}")
    print(f"  같은 입력인데 답이 다름: {wrong_iters}")
    print()
    if bad_n:
        print("🚨 앞 계산의 결과를 집어 오고 있습니다. "
              "`app_engine._Worker` 의 일감 번호 대조를 확인하세요.")
    else:
        print(f"✅ {args.pairs}쌍 모두 제 답을 받았습니다.")
    app_engine.shutdown()
    return 1 if bad_n else 0


if __name__ == "__main__":
    sys.exit(main())
