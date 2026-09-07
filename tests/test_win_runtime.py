# -*- coding: utf-8 -*-
"""윈도우에서 엔진이 쓸 자리를 PATH 맨 앞에 놓나 (2026-09-07).

    ~/venvs/unigrid-acdc/bin/python tests/test_win_runtime.py

계기 — 시연용 윈도우에서 계산이 안 됐다. 앱은 뜨는데 누르면 영어 한 줄:

    Could not find the directory C:\\Program Files\\MATLAB\\R2024b\\toolbox\\compiler_sdk\\pysdk_py

그 컴퓨터에는 **MATLAB 정식판 R2024b** 가 있었고 거기엔 Compiler SDK 툴박스가
없었다(`pysdk_py` 가 없다 — 설치할 때 따로 고르는 항목이라 대개 빠진다).
엔진 패키지는 PATH 를 위에서부터 훑어 **처음 걸린 자리**를 쓰고, 그 자리가 못 쓰는
것이면 **뒤에 쓸 수 있는 자리가 있어도 보지 않는다.**

여기서 지키는 것
    1) `pysdk_py` 가 있는 자리만 「쓸 수 있다」로 본다 (정식판이냐 Runtime 이냐는 안 본다)
    2) 못 쓰는 것이 PATH 앞에 있으면 쓸 수 있는 것을 그 앞에 넣는다
    3) 🚨 이미 쓸 수 있는 것이 맨 앞이면 **건드리지 않는다** (남의 PATH 를 함부로 늘리지 않는다)
    4) 쓸 수 있는 것이 하나도 없으면 **아무것도 안 한다** — 던지지 않는다
       (설치 방식이 우리 예상과 다를 수 있고, 그때는 엔진이 스스로 찾을 수도 있다)
    5) 못 찾았을 때 안내가 **무엇을 깔아야 하는지** 말하나
    6) 🚨 맥에서는 아무 일도 하지 않는다
"""
import os
import platform
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
import engine_path as E                                          # noqa: E402

fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<52} {got}")
    else:
        print(f"  🚨 {label:<52} {got}   (기대: {want})")
        fails.append(label)


def make_root(base: Path, name: str, *, sdk: bool, dll: bool = True) -> Path:
    """가짜 MATLAB 설치 자리를 만든다 → `…/runtime/win64` 를 돌려준다."""
    rt = base / name / "runtime" / "win64"
    rt.mkdir(parents=True, exist_ok=True)
    if dll:
        (rt / E.RUNTIME_DLL).write_text("")
    if sdk:
        (base / name).joinpath(*E.SDK_MARK).mkdir(parents=True, exist_ok=True)
    return rt


tmp = Path(tempfile.mkdtemp(prefix="unigrid_win_"))
GOOD = make_root(tmp, "MATLAB Runtime/R2024b", sdk=True)     # Runtime — 쓸 수 있다
BAD = make_root(tmp, "MATLAB/R2024b", sdk=False)             # 정식판 — pysdk_py 가 없다
NODLL = make_root(tmp, "MATLAB/R2023a", sdk=True, dll=False)  # DLL 이 없다 → 후보 아님

print("[1] pysdk_py 가 있는 자리만 「쓸 수 있다」")
check("Runtime (pysdk_py 있음)", E.usable_runtime(GOOD), True)
check("정식판 (pysdk_py 없음)", E.usable_runtime(BAD), False)
check("DLL 이 없는 자리", E.usable_runtime(NODLL), False)

print("\n[2] PATH 에서 쓸 수 있는 것과 없는 것을 가른다")
env = {"PATH": os.pathsep.join([str(BAD), str(NODLL), str(GOOD)])}
ok, bad = E.win_runtime_dirs(env, roots=[])
check("쓸 수 있는 것 수", len(ok), 1)
check("못 쓰는 것 수", len(bad), 1)
check("쓸 수 있는 것이 Runtime 인가", ok[0] == GOOD if ok else None, True)

print("\n[3] 못 쓰는 것이 앞에 있으면 쓸 수 있는 것을 앞에 넣는다")
_real = platform.system
E.platform.system = lambda: "Windows"          # 맥에서도 그 길을 밟게
try:
    env = {"PATH": os.pathsep.join([str(BAD), str(GOOD)])}
    note = E.ensure_runtime_on_path(env, roots=[])
    first = env["PATH"].split(os.pathsep)[0]
    check("무언가 했다고 말하나", bool(note), True)
    check("맨 앞이 쓸 수 있는 자리인가", Path(first) == GOOD, True)
    check("앞에 있던 못 쓰는 자리도 남아 있나", str(BAD) in env["PATH"], True)

    print("\n[4] 이미 쓸 수 있는 것이 맨 앞이면 건드리지 않는다")
    env2 = {"PATH": os.pathsep.join([str(GOOD), str(BAD)])}
    before = env2["PATH"]
    note2 = E.ensure_runtime_on_path(env2, roots=[])
    check("아무것도 안 했다고 하나", note2, None)
    check("PATH 가 그대로인가", env2["PATH"] == before, True)

    print("\n[5] 쓸 수 있는 것이 없으면 아무것도 안 한다 (던지지 않는다)")
    env3 = {"PATH": str(BAD)}
    before3 = env3["PATH"]
    note3 = E.ensure_runtime_on_path(env3, roots=[])
    check("아무것도 안 했다고 하나", note3, None)
    check("PATH 가 그대로인가", env3["PATH"] == before3, True)
finally:
    E.platform.system = _real

print("\n[6] 맥에서는 아무 일도 하지 않는다")
if _real() == "Darwin":
    env4 = {"PATH": os.pathsep.join([str(BAD), str(GOOD)])}
    before4 = env4["PATH"]
    check("None 을 돌려주나", E.ensure_runtime_on_path(env4, roots=[]), None)
    check("PATH 가 그대로인가", env4["PATH"] == before4, True)
else:
    print("  (맥이 아니라 건너뜀)")

print("\n[7] 못 찾았을 때 안내가 무엇을 깔아야 하는지 말하나")
g = E.windows_guidance(RuntimeError("Could not find the directory ..."))
for must in ("pysdk_py", "MATLAB Runtime", E.REQUIRED_RELEASE, E.RUNTIME_URL):
    check(f"안내에 「{must}」 가 있나", must in g, True)
check("굵게 표시(**)를 안 넣었나", "**" not in g, True)
check("원래 오류를 함께 보여주나", "Could not find the directory" in g, True)

print("\n[8] 화면 쪽이 아는 예외 하나로 온다")
check("EngineNotFound 에 message 를 줄 수 있나",
      str(E.EngineNotFound([], "안내글")) == "안내글", True)

import shutil
shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.exit(1 if fails else 0)
