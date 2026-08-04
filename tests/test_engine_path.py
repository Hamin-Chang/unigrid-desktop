"""엔진 자리 찾기 시험 — PDR §4.1 · §7 0단계.

숫자 회귀(`regress.py`)와 성격이 다르다. 저건 *결과가 그대로인가*를 보고,
이건 *남의 컴퓨터에서 엔진을 찾아내는가*를 본다. 그래서 파일을 따로 둔다.

⚠️ 이 맥에는 MATLAB Runtime 이 깔려 있지 않다. 그래서 **정작 고치려던 3번 자리를
실제로는 확인할 수 없다** ⇒ 가짜 Runtime 폴더를 만들어 흉내 낸다.
(§6 — 만들고 끝내지 말고 확인한다.)

    python tests/test_engine_path.py
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import engine_path as ep  # noqa: E402

ok = 0
bad: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        bad.append(name)
        print(f"  ❌ {name}  {detail}")


def fake_mwpython(root: Path, release: str) -> Path:
    """<root>/<release>/bin/mwpython 을 실행 가능한 빈 파일로 만든다."""
    p = root / release / "bin" / "mwpython"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/sh\nexit 0\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


print("=== (1) 아무것도 없으면 안내가 나온다 (안 죽는다) ===")
try:
    ep.find_mwpython(env={}, app_roots=[], runtime_roots=[], remembered=None)
    check("EngineNotFound 를 던진다", False, "예외가 안 났다")
except ep.EngineNotFound as exc:
    msg = str(exc)
    check("EngineNotFound 를 던진다", True)
    check("받는 곳 주소가 들어 있다", ep.RUNTIME_URL in msg)
    check("필요한 판을 알려 준다", ep.REQUIRED_RELEASE in msg)
    check("어디를 봤는지 알려 준다", "찾아본 자리" in msg)
    check("직접 고르기를 안내한다", "직접 고르기" in msg)

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    print("\n=== (2) ⭐ Runtime 자리를 본다 (뼈대에 빠져 있던 줄) ===")
    rt = tmp / "MATLAB_Runtime"
    want = fake_mwpython(rt, ep.REQUIRED_RELEASE)
    got = ep.find_mwpython(env={}, app_roots=[], runtime_roots=[rt], remembered=None)
    check("Runtime 안의 mwpython 을 찾는다", got == want, f"{got}")
    steps = ep.search(env={}, app_roots=[], runtime_roots=[rt], remembered=None)
    hit = [s for s in steps if s.found]
    check("3번 자리에서 잡힌다", hit and hit[0].order == 3,
          f"order={hit[0].order if hit else '없음'}")

    print("\n=== (3) 전체 MATLAB 보다 Runtime 이 먼저다 ===")
    apps = tmp / "Applications"
    app_mw = apps / f"MATLAB_{ep.REQUIRED_RELEASE}.app" / "bin" / "mwpython"
    app_mw.parent.mkdir(parents=True, exist_ok=True)
    app_mw.write_text("#!/bin/sh\nexit 0\n")
    app_mw.chmod(app_mw.stat().st_mode | stat.S_IXUSR)
    got = ep.find_mwpython(env={}, app_roots=[apps], runtime_roots=[rt], remembered=None)
    check("Runtime 을 고른다", got == want, f"{got}")

    print("\n=== (4) 판이 다르면 알려 준다 ===")
    rt2 = tmp / "OtherRuntime"
    other = "R2021a" if ep.REQUIRED_RELEASE != "R2021a" else "R2020b"
    p_other = fake_mwpython(rt2, other)
    got = ep.find_mwpython(env={}, app_roots=[], runtime_roots=[rt2], remembered=None)
    check("판이 달라도 일단 찾는다", got == p_other, f"{got}")
    w = ep.release_warning(got)
    check("판이 다르다고 말해 준다", bool(w) and other in w, f"{w}")
    check("맞는 판에는 경고가 없다", ep.release_warning(want) is None)

    print("\n=== (5) 같은 자리에 두 판이 있으면 맞는 판을 고른다 ===")
    rt3 = tmp / "BothRuntime"
    fake_mwpython(rt3, other)
    right = fake_mwpython(rt3, ep.REQUIRED_RELEASE)
    got = ep.find_mwpython(env={}, app_roots=[], runtime_roots=[rt3], remembered=None)
    check(f"{ep.REQUIRED_RELEASE} 를 고른다", got == right, f"{got}")

    print("\n=== (6) 순서: 환경변수 > 기억한 자리 > Runtime ===")
    envp = fake_mwpython(tmp / "ByEnv", ep.REQUIRED_RELEASE)
    memp = fake_mwpython(tmp / "ByMemory", ep.REQUIRED_RELEASE)
    got = ep.find_mwpython(env={"MWPYTHON": str(envp)}, app_roots=[],
                           runtime_roots=[rt], remembered=memp)
    check("환경변수가 이긴다", got == envp, f"{got}")
    got = ep.find_mwpython(env={}, app_roots=[], runtime_roots=[rt], remembered=memp)
    check("기억한 자리가 Runtime 보다 먼저", got == memp, f"{got}")

    print("\n=== (7) 없는 자리를 가리키면 무시하고 다음으로 간다 ===")
    got = ep.find_mwpython(env={"MWPYTHON": str(tmp / "없는것")}, app_roots=[],
                           runtime_roots=[rt], remembered=None)
    check("죽지 않고 Runtime 으로 넘어간다", got == want, f"{got}")

print(f"\n{'─' * 50}\n통과 {ok}건 / 실패 {len(bad)}건")
if bad:
    for b in bad:
        print(f"  ❌ {b}")
raise SystemExit(1 if bad else 0)
