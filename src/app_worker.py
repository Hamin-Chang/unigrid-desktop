"""app_worker.py — macOS에서 mwpython으로 도는 UNIGRID 계산 프로세스.

맥에서는 MATLAB 컴파일 패키지를 일반 python으로 import할 수 없고 mwpython으로만
가능하다. 그래서 app_engine.py 가 이것을 별도 프로세스로 띄운다.

**계속 살아 있는 방식(server 모드)**: MATLAB Runtime 기동에만 2.7초가 들기 때문에
계산할 때마다 프로세스를 새로 띄우면 그 시간을 매번 버린다. 한 번 띄워 두고
표준입력으로 일감을 받으면 두 번째부터 1초 안쪽에 끝난다.

  주고받는 방식 (한 줄 = 한 건)
    받음:  {"in": "<케이스 json 경로>", "out": "<결과 json 경로>"}
    보냄:  {"ok": true}            또는  {"ok": false, "error": "..."}
    종료:  {"quit": true}

한 번만 쓰는 옛 방식도 그대로 둔다:  app_worker.py in.json out.json
"""
from __future__ import annotations

import importlib
import json
import platform
import re
import sys
from pathlib import Path
from typing import Any

PACKAGE_CANDIDATES = {
    "Darwin": ("unigrid_app_mac",),
    "Windows": ("unigrid_app_win",),
    "Linux": ("unigrid_app_linux",),
}
_HERE = Path(__file__).resolve().parent
# 컴파일된 엔진은 저장소에 **한 자리**에만 둔다 — `engine/<패키지이름>/` (PDR §4.2 규칙 3).
# ⚠️ 뼈대는 `<패키지이름>/for_testing/<패키지이름>/` 이라 한 겹 더 깊었다.
#    MATLAB 빌드 산출물의 `for_testing/<패키지이름>/` 폴더를 통째로 `engine/` 안에
#    복사해 넣으면 그대로 맞는다.
ENGINE_DIR = _HERE.parent / "engine"


def _pick_package() -> str:
    for name in PACKAGE_CANDIDATES.get(platform.system(), ("unigrid_app",)):
        if (ENGINE_DIR / name).is_dir():
            return name
    return "unigrid_app_mac"


PKG_NAME = _pick_package()
sys.path.insert(0, str(ENGINE_DIR))


def _fix_mac_arch_detection() -> None:
    """맥 종류를 못 알아보는 경우를 메워 준다 (2026-07-27).

    MATLAB 이 만든 패키지의 `__init__.py` 는 `platform.mac_ver()[-1]` 로 애플
    실리콘인지 인텔인지 가린다. 그런데 mwpython 안에서 그 값이 **빈 문자열**로
    오는 맥이 있고, 그러면 애플 실리콘 맥을 인텔(maci64)로 오판해 불러오기를
    아예 거부한다.

    왜 비는가: mwpython 은 Homebrew 파이썬을 쓰는데, MATLAB 이 자기 폴더를
    라이브러리 경로 앞에 끼워 넣는다. 거기 있는 옛 `libexpat`(1.9.3, 2024년판)이
    맥OS 26 의 시스템 expat 에 맞춰 빌드된 `pyexpat` 과 안 맞아 불러오기가 깨지고,
    그 여파로 `plistlib` → `platform.mac_ver()` 가 빈 값을 돌려준다.
    (2026-07-27 Homebrew python 3.12 업데이트 뒤부터 나타났다.)

    여기서는 **값이 비었을 때만** 칩 종류를 채운다. 값이 정상인 맥에서는
    아무 일도 하지 않으므로 다른 컴퓨터의 동작은 그대로다.
    """
    if platform.system() != "Darwin" or platform.mac_ver()[-1]:
        return
    machine = platform.machine()          # arm64 또는 x86_64
    platform.mac_ver = lambda *a, **k: ("", ("", "", ""), machine)


_fix_mac_arch_detection()

pkg = importlib.import_module(PKG_NAME)
import matlab  # noqa: E402

TABLE_ORDER = (
    "Base_dat", "AC_Bus_dat", "AC_Line_dat", "AC_gen_dat", "AC_3wtrans_dat",
    "DC_Bus_dat", "DC_Line_dat", "DC_gen_dat", "IC_dat", "DCDC_Conv_dat",
    "AC_PLoad_dat", "AC_QLoad_dat", "DC_PLoad_dat",
)


def _matrix(values: list) -> Any:
    if not values:
        return matlab.double([])
    return matlab.double(values)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    # matlab 배열은 str()로 찍으면 JSON 모양이 나온다 → 다시 숫자로 되돌린다
    text = str(value)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 🚨 MATLAB 은 무한대·비수를 inf / -inf / nan 으로 찍는데 JSON 표준에는 그 낱말이 없다.
    #    그대로 두면 아래 except 로 떨어져 **문자열이 넘어가고**, 받는 쪽
    #    app_engine._arr 의 float 변환이 터져 앱이 죽는다.
    #    (재현: AConly_3wtrans_modify.xlsx — 손실 백분율이 inf 로 나온다)
    #    파이썬 json 이 알아듣는 Infinity / NaN 으로 바꿔 한 번 더 시도한다.
    #    앞의 부호(-)는 낱말 밖이라 -inf 도 -Infinity 로 잘 바뀐다.
    fixed = re.sub(r"\binf\b", "Infinity", text)
    fixed = re.sub(r"\bnan\b", "NaN", fixed, flags=re.IGNORECASE)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return text


def solve_one(app: Any, in_path: str, out_path: str) -> None:
    case = json.loads(Path(in_path).read_text(encoding="utf-8"))
    tables = case["tables"]
    args = [_matrix(tables[name]) for name in TABLE_ORDER]
    result = app.runpf_unigrid_app(
        case["case_name"], float(case["mode"]), *args, nargout=1
    )
    Path(out_path).write_text(json.dumps(_jsonable(result)), encoding="utf-8")


def serve() -> None:
    """표준입력으로 일감을 받아 계속 처리한다 (Runtime을 한 번만 띄운다)."""
    app = pkg.initialize()
    # 준비됐음을 알린다 — 엔진이 이 줄을 기다린다
    print(json.dumps({"ready": True}), flush=True)
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                job = json.loads(line)
            except json.JSONDecodeError:
                continue
            if job.get("quit"):
                break
            # 일감 번호를 그대로 돌려준다 — 부르는 쪽이 **자기 답인지** 가릴 수 있게.
            # 왜 필요한가: 계산이 안 풀리면 MATLAB 이 경고·스택을 수백 줄 찍는데,
            # 그 사이에서 답 줄을 못 찾고 넘어가면 **다음 계산이 이 답을 집어 간다**
            # (실제로 2026-08-06 에 그랬다 — 안 풀려야 할 조건이 "잘 풀렸다"로 나왔다).
            job_id = job.get("id")
            try:
                solve_one(app, job["in"], job["out"])
                print(json.dumps({"ok": True, "id": job_id}), flush=True)
            except Exception as exc:
                print(json.dumps({"ok": False, "id": job_id, "error": str(exc)}), flush=True)
    finally:
        app.terminate()


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--serve":
        serve()
        return
    if len(sys.argv) != 3:
        raise SystemExit("Usage: app_worker.py --serve | app_worker.py in.json out.json")
    app = pkg.initialize()
    try:
        solve_one(app, sys.argv[1], sys.argv[2])
    finally:
        app.terminate()


if __name__ == "__main__":
    main()
