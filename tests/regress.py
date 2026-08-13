"""regress.py — 회귀를 한 명령으로 (PDR §6 ①층 · §7 0단계).

무엇을 하나
    cases/ 의 케이스를 전부 풀어서 **지문**(전압·조류·부하율·손실·발전기 한계·수렴 정보
    + **PV·QV 곡선**)을 tests/baseline/ 에 저장해 둔 값과 견준다.
    하나라도 다르면 **무엇이 얼마나** 달라졌는지 찍는다.

왜 필요한가
    지금까지는 엔진을 다시 만들 때마다 시험 스크립트를 새로 짰고, 그러다
    **실패 3건이 전부 스크립트 버그**였던 적이 있다(3차 재컴파일). 검증을 한 자리에 고정한다.

쓰는 법
    python tests/regress.py              # 견주기 (기본)
    python tests/regress.py --save       # 지금 결과를 기준으로 삼기 (처음 한 번, 또는 의도적으로 바뀌었을 때)
    python tests/regress.py --only 71bus # 이름에 그 글자가 든 케이스만

통과 기준 (§6.2 ①층)
    모든 값의 차이가 0.00e+00. 달라졌으면 **왜 달라졌는지 한 줄로 댈 수 있어야** 한다.
    못 대면 통과가 아니다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CASES = REPO / "cases"
BASELINE = HERE / "baseline"

# ── 계산 쪽 코드를 어디서 가져오나 ────────────────────────────────
# ✅ 1단계(이식) 완료 — 이제 이 저장소의 `src/` 를 본다(뼈대가 아니라).
SRC = REPO / "src"          # 케이스 읽기까지 전부 여기 있다 (2026-08-05 들여옴)

if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _imports():
    """무거운 것은 필요할 때만 불러온다 (--help 가 빨리 뜨게)."""
    try:
        import app_engine  # type: ignore
        from load_case import load_case  # type: ignore
    except Exception as exc:
        print("계산 쪽 코드를 불러오지 못했습니다.")
        print(f"  앱 코드   : {SRC}  ({'있음' if SRC.is_dir() else '없음'})")
        print(f"  원인      : {exc}")
        sys.exit(2)
    return app_engine, load_case


# ── 지문 ─────────────────────────────────────────────────────────
# 무엇을 지문에 넣나: 화면이 실제로 읽는 값 전부.
# 여기 없는 것이 조용히 바뀌면 회귀가 못 잡는다.
def fingerprint(sol) -> dict[str, np.ndarray]:
    f: dict[str, np.ndarray] = {}
    for name in ("AC", "DC", "Branch", "loss", "freq", "gen_limit"):
        arr = np.asarray(getattr(sol, name if name != "loss" else "loss"), dtype=float)
        f[name] = arr
    f["scalars"] = np.array([
        float(sol.converged),
        float(sol.iters),
        float(sol.threshold),
        float(sol.n_time),
        float(sol.baseMVA),
        float(getattr(sol, "qlim_enforced", True)),
    ], dtype=float)
    vsc = getattr(sol, "VSC_bus", None)
    if vsc is not None and np.size(vsc):
        f["VSC_bus"] = np.asarray(vsc, dtype=float)
    return f


def case_files(only: str | None) -> list[Path]:
    files = sorted(CASES.glob("*.xlsx"))
    if only:
        files = [p for p in files if only.lower() in p.name.lower()]
    return files


def curve_print(app_engine, case) -> dict[str, np.ndarray]:
    """곡선을 그릴 수 있는 계통이면 **곡선까지** 지문에 넣는다 (§7 4단계 F1f).

    🚨 왜 따로 넣나 — 조류계산 지문만으로는 **곡선이 틀어져도 회귀가 통과한다.**
       곡선은 `runCPF_app` 이라는 다른 진입점이라 `solve()` 가 내는 값과 겹치는 곳이 없다.
       A1(탭·위상 자동 조정)이 솔버를 건드리므로 그 전에 못 박아 둔다.

    못 그리는 계통은 **표시만** 남긴다 — 막던 것이 풀리거나 새로 막히면 `compare()` 가
    "기준에 없던 것이 생김 / 있던 것이 사라짐" 으로 잡는다(까닭 글귀는 지문에 넣지 않는다.
    글귀만 다듬어도 회귀가 깨지면 대장을 자꾸 다시 잡게 된다).
    """
    if app_engine.curve_refusal(case):
        return {"curve_refused": np.array([1.0])}
    c = app_engine.curve(case)
    return {
        "curve_lam": np.asarray(c.lam, dtype=float),
        "curve_v": np.asarray(c.v, dtype=float),
        # 코 끝점 — 화면 요약이 읽는 값 그대로
        "curve_scalars": np.array([c.lam_crit, c.nose_MW, float(c.nose)], dtype=float),
    }


def tap_print(sol) -> dict:
    """탭 자동 조정 결과를 지문에 담는다 (2026-08-13, §7 5단계 A1).

    ⚠️ 전압만 봐도 조정이 깨지면 잡히긴 한다(목표를 못 맞추면 전압이 달라지므로).
       그래도 **정해진 탭비 자체**를 담는다 — 같은 전압을 다른 탭으로 내는 경우가
       있을 수 있고, 한계에 걸려 놓아준 것(5열)은 전압만으로는 안 보인다.
    """
    t = np.asarray(getattr(sol, "tap_ctrl", np.empty((0, 5))), dtype=float)
    return {} if t.size == 0 else {"tap_ctrl": t}


def run_case(app_engine, load_case, path: Path):
    # 조류계산과 곡선이 **같은 case 를 쓴다** — 앱도 계통 조건을 둘이 공유한다(F1d 확정).
    case = load_case(str(path))
    sol = app_engine.solve(case)
    f = fingerprint(sol)
    f.update(tap_print(sol))
    f.update(curve_print(app_engine, case))
    return f


def compare(old: dict, new: dict) -> list[str]:
    """다른 곳을 사람이 읽을 수 있게 돌려준다. 같으면 빈 목록."""
    bad: list[str] = []
    for key in sorted(set(old) | set(new)):
        if key not in old:
            bad.append(f"      {key}: 기준에 없던 것이 생김")
            continue
        if key not in new:
            bad.append(f"      {key}: 기준에 있던 것이 사라짐")
            continue
        a, b = old[key], new[key]
        if a.shape != b.shape:
            bad.append(f"      {key}: 모양이 다름 {a.shape} → {b.shape}")
            continue
        if a.size == 0:
            continue
        d = np.abs(np.nan_to_num(a) - np.nan_to_num(b))
        # NaN 자리가 서로 다른 것도 잡는다 (한쪽만 NaN 이면 값이 바뀐 것)
        nan_moved = int(np.sum(np.isnan(a) != np.isnan(b)))
        m = float(np.max(d)) if d.size else 0.0
        if m > 0 or nan_moved:
            where = np.unravel_index(int(np.argmax(d)), d.shape) if d.size else ()
            msg = f"      {key}: 최대 차이 {m:.3e} (자리 {where})"
            if nan_moved:
                msg += f" · 빈칸이 바뀐 곳 {nan_moved}개"
            bad.append(msg)
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description="UNIGRID 회귀 — 한 명령으로")
    ap.add_argument("--save", action="store_true", help="지금 결과를 기준으로 삼는다")
    ap.add_argument("--only", metavar="글자", help="이름에 그 글자가 든 케이스만")
    args = ap.parse_args()

    files = case_files(args.only)
    if not files:
        print(f"케이스가 없습니다: {CASES}")
        return 2

    app_engine, load_case = _imports()
    BASELINE.mkdir(exist_ok=True)

    ok = changed = failed = 0
    t_all = time.time()

    for path in files:
        name = path.stem
        ref = BASELINE / f"{name}.npz"
        print(f"  {name:<34}", end="", flush=True)
        t0 = time.time()
        try:
            new = run_case(app_engine, load_case, path)
        except Exception as exc:
            print(f"실행 실패 — {type(exc).__name__}: {exc}")
            failed += 1
            continue
        dt = time.time() - t0

        if args.save:
            np.savez_compressed(ref, **new)
            print(f"기준으로 저장  ({dt:.2f}초)")
            ok += 1
            continue

        if not ref.exists():
            print(f"기준 없음 — --save 로 먼저 만드세요  ({dt:.2f}초)")
            failed += 1
            continue

        with np.load(ref) as z:
            old = {k: z[k] for k in z.files}
        bad = compare(old, new)
        if bad:
            print(f"바뀜  ({dt:.2f}초)")
            for line in bad:
                print(line)
            changed += 1
        else:
            print(f"같음  ({dt:.2f}초)")
            ok += 1

    print()
    if args.save:
        print(f"기준 저장 {ok}건 · 실행 실패 {failed}건  ({time.time()-t_all:.1f}초)")
        return 1 if failed else 0

    print(f"같음 {ok} · 바뀜 {changed} · 실행 실패 {failed}  ({time.time()-t_all:.1f}초)")
    if changed:
        print()
        print("⚠️ 바뀐 것이 있습니다. §6.2 ①층 기준 — **왜 달라졌는지 한 줄로 댈 수 있어야** 통과입니다.")
        print("   의도한 변경이면 `--save` 로 기준을 다시 잡고, 무엇을 왜 바꿨는지 커밋 메시지에 남기세요.")
    return 1 if (changed or failed) else 0


if __name__ == "__main__":
    sys.exit(main())
