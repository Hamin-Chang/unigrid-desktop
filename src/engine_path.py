"""계산 엔진을 부를 `mwpython` 자리를 찾는다 — PDR §4.1 (§7 0단계).

**왜 필요한가.** 뼈대는 `/Applications/MATLAB_R2024b.app` 과 `R2025a.app` **두 자리만**
본다(`app_engine.py:300-306`). 둘 다 *전체 MATLAB* 설치 자리다. 공개 배포에서는 남이
전체 MATLAB 을 갖고 있을 리 없고 **무료 MATLAB Runtime** 만 깐다. Runtime 에도
`mwpython` 은 있다(`matlabroot/bin`) — 지금은 **그 자리를 안 볼 뿐**이다.

**찾는 순서 (위에서부터, 처음 걸리는 것을 쓴다)**

1. 환경변수 `MWPYTHON` — 사용자가 직접 지정한 것이 항상 이긴다
2. 앱이 기억해 둔 자리 — 한 번 직접 고르면 다음부터 안 묻는다
3. **MATLAB Runtime 기본 자리** — 배포 대상의 표준 경로. **지금 빠져 있는 줄이 이것이다**
4. 전체 MATLAB — 판 번호를 붙박지 않고 훑는다
5. 못 찾으면 **안내**(무엇을 어디서 찾아봤는지 + 받는 곳 + 직접 고르기)

⚠️ **판이 맞아야 한다.** 컴파일된 엔진(`engine/unigrid_app_mac.ctf`)과 Runtime 은 **같은 판**
이어야 불러와진다. 다른 판만 있으면 지금은 "mwpython을 찾지 못했습니다"로만 나와 원인을
알 수 없다 ⇒ 여기서는 **찾되 판이 다르면 그 사실을 말해 준다**.

윈도우는 `mwpython` 이 필요 없다(같은 프로세스에서 바로 import). `needs_mwpython()` 참조.

혼자서도 돌려 볼 수 있다:
    python src/engine_path.py           # 어디를 훑었고 무엇을 골랐는지
    python src/engine_path.py --blind   # 아무것도 없는 컴퓨터인 척 → 안내가 나오는지
"""

from __future__ import annotations

import json
import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path

# 엔진을 컴파일한 판. `engine/unigrid_app_mac.ctf` 를 다시 만들면 여기도 바꾼다.
REQUIRED_RELEASE = "R2024b"

# 받는 곳 (안내 화면에 그대로 보여 준다)
RUNTIME_URL = "https://www.mathworks.com/products/compiler/matlab-runtime.html"

_SETTINGS = Path.home() / ".unigrid" / "settings.json"


def needs_mwpython() -> bool:
    """맥에서만 mwpython 이 필요하다.

    맥은 그래픽 코드를 주 스레드에서 못 부르는 제약이 있어 MATLAB 컴파일 패키지를
    일반 `python` 으로 불러올 수 없다. 윈도우는 그 제약이 없어 같은 프로세스에서 import 한다.
    """
    return platform.system() == "Darwin"


@dataclass
class Step:
    """찾는 순서 한 칸의 결과 — 안내 화면과 자기 점검이 같이 쓴다."""
    order: int
    where: str            # 사람이 읽을 자리 이름
    path: Path | None     # 실제로 본 자리 (없으면 None)
    found: bool
    note: str = ""


class EngineNotFound(RuntimeError):
    """다섯 자리를 다 훑어도 없을 때. **오류 문구로 끝내지 않고** 안내를 들고 있는다."""

    def __init__(self, steps: list[Step]):
        self.steps = steps
        super().__init__(guidance(steps))


# ─────────────────────────────────────────────── 찾기
def search(explicit: str | Path | None = None, *,
           env: dict | None = None,
           app_roots: list[Path] | None = None,
           runtime_roots: list[Path] | None = None,
           remembered: Path | None = None) -> list[Step]:
    """다섯 자리를 순서대로 훑고 **본 자리를 전부** 돌려준다.

    자리 목록을 인자로 받는 이유: *아무것도 없는 컴퓨터*를 흉내 내 안내가 제대로
    나오는지 시험하기 위해서다(§6 — 만들고 끝내지 말고 확인한다).
    """
    env = os.environ if env is None else env
    steps: list[Step] = []

    # 0) 부르는 쪽이 직접 준 자리 (순서 밖 — 늘 최우선)
    if explicit:
        p = Path(explicit)
        steps.append(Step(0, "직접 지정", p, _ok(p), "인자로 받은 자리"))
        if steps[-1].found:
            return steps

    # 1) 환경변수
    raw = env.get("MWPYTHON")
    p = Path(raw) if raw else None
    steps.append(Step(1, "환경변수 MWPYTHON", p, _ok(p) if p else False,
                      "" if raw else "설정 안 됨"))
    if steps[-1].found:
        return steps

    # 2) 기억해 둔 자리
    p = remembered if remembered is not None else _remembered()
    steps.append(Step(2, "앱이 기억한 자리", p, _ok(p) if p else False,
                      "" if p else "기억된 것 없음"))
    if steps[-1].found:
        return steps

    # 3) MATLAB Runtime  ← 뼈대에 빠져 있던 자리
    hits = _scan(runtime_roots if runtime_roots is not None else _runtime_roots())
    steps.append(_pick(3, "MATLAB Runtime", hits))
    if steps[-1].found:
        return steps

    # 4) 전체 MATLAB
    hits = _scan(app_roots if app_roots is not None else _app_roots())
    steps.append(_pick(4, "전체 MATLAB", hits))
    if steps[-1].found:
        return steps

    # 5) 없음
    steps.append(Step(5, "안내", None, False, "다섯 자리 모두 없음"))
    return steps


def find_mwpython(explicit: str | Path | None = None, **kw) -> Path:
    """찾으면 자리를, 못 찾으면 `EngineNotFound`(안내를 들고 있음)를 던진다."""
    steps = search(explicit, **kw)
    for s in steps:
        if s.found and s.path is not None:
            return s.path
    raise EngineNotFound(steps)


def release_of(path: Path) -> str | None:
    """자리에서 판 번호를 뽑는다 (`…/MATLAB_Runtime/R2024b/bin/mwpython` → `R2024b`)."""
    m = re.search(r"R20\d{2}[ab]", str(path))
    return m.group(0) if m else None


def release_warning(path: Path) -> str | None:
    """판이 엔진과 다르면 그 사실을 한 줄로. 같거나 알 수 없으면 None."""
    rel = release_of(path)
    if rel is None or rel == REQUIRED_RELEASE:
        return None
    return (f"⚠️ 판이 다릅니다 — 엔진은 {REQUIRED_RELEASE} 로 만들었는데 찾은 것은 {rel} 입니다.\n"
            f"   불러오기가 실패하면 {REQUIRED_RELEASE} Runtime 을 받아 주세요: {RUNTIME_URL}")


# ─────────────────────────────────────────────── 안내
def guidance(steps: list[Step]) -> str:
    """못 찾았을 때 보여 줄 글. **어디를 봤는지까지** 말한다.

    ⚠️ 이 글은 **화면 대화상자에 그대로 뜬다** — 여기에는 `**굵게**` 같은 글 표시를 넣지 않는다.
    별표가 그대로 보인다(2026-08-05에 실제로 보고 걷어냈다).
    """
    looked = "\n".join(
        f"    {s.order}. {s.where}: " + (str(s.path) if s.path else (s.note or "없음"))
        for s in steps if s.order > 0 and s.order < 5)
    return (
        "계산 엔진을 실행할 MATLAB Runtime 을 찾지 못했습니다.\n\n"
        "  UNIGRID 의 계산은 MATLAB 에서 컴파일한 엔진이 합니다.\n"
        f"  그 엔진을 돌리려면 MATLAB Runtime {REQUIRED_RELEASE} 가 필요합니다(무료).\n\n"
        f"  받는 곳: {RUNTIME_URL}\n\n"
        "  찾아본 자리:\n" + looked + "\n\n"
        "  이미 깔려 있다면 [직접 고르기] 로 mwpython 자리를 알려 주세요.\n"
        "  (보통 <설치자리>/bin/mwpython 입니다. 한 번 고르면 다음부터 묻지 않습니다.)"
    )


def remember(path: str | Path) -> None:
    """직접 고른 자리를 기억한다 — 다음부터 3·4번 훑기를 건너뛴다."""
    _SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    data = _read_settings()
    data["mwpython"] = str(path)
    _SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def forget() -> None:
    data = _read_settings()
    data.pop("mwpython", None)
    if _SETTINGS.parent.exists():
        _SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────── 잡동사니
def _ok(p: Path | None) -> bool:
    return bool(p) and Path(p).exists() and os.access(p, os.X_OK)


def _read_settings() -> dict:
    try:
        return json.loads(_SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _remembered() -> Path | None:
    v = _read_settings().get("mwpython")
    return Path(v) if v else None


def _runtime_roots() -> list[Path]:
    """맥 Runtime 기본 자리. 판 폴더는 훑는다(R2024b 만 붙박지 않는다)."""
    return [Path("/Applications/MATLAB/MATLAB_Runtime"),
            Path("/opt/MATLAB/MATLAB_Runtime"),          # 손으로 다른 데 깐 경우
            Path.home() / "MATLAB_Runtime"]


def _app_roots() -> list[Path]:
    return [Path("/Applications")]


def _scan(roots: list[Path]) -> list[Path]:
    """자리들 아래에서 mwpython 을 훑는다. 엔진과 같은 판을 **앞으로** 놓는다."""
    hits: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for pat in ("*/bin/mwpython", "MATLAB_R*.app/bin/mwpython"):
            hits.extend(p for p in root.glob(pat) if _ok(p))
    # 같은 판 먼저, 그다음 이름 역순(최신 판이 앞)
    hits.sort(key=lambda p: (release_of(p) != REQUIRED_RELEASE, str(p)), reverse=False)
    seen, out = set(), []
    for p in hits:
        if str(p) not in seen:
            seen.add(str(p))
            out.append(p)
    return out


def _pick(order: int, where: str, hits: list[Path]) -> Step:
    if not hits:
        return Step(order, where, None, False, "없음")
    p = hits[0]
    note = release_warning(p) or ""
    if len(hits) > 1:
        note = (note + f"  (후보 {len(hits)}개 중 첫 번째)").strip()
    return Step(order, where, p, True, note)


# ─────────────────────────────────────────────── 자기 점검
def _selfcheck(blind: bool) -> int:
    print(f"운영체제: {platform.system()}  ·  mwpython 필요: {needs_mwpython()}")
    print(f"엔진 판 : {REQUIRED_RELEASE}\n")

    kw = {}
    if blind:
        print("── 아무것도 없는 컴퓨터인 척 (--blind) ──")
        kw = {"env": {}, "app_roots": [], "runtime_roots": [], "remembered": None}

    steps = search(**kw)
    for s in steps:
        mark = "✅" if s.found else "  "
        line = str(s.path) if s.path else (s.note or "없음")
        print(f"  {mark} {s.order}. {s.where:<18} {line}")
        if s.note and s.path:
            print(f"        {s.note}")

    print()
    try:
        p = find_mwpython(**kw)
    except EngineNotFound as exc:
        if blind:
            print("✅ 안 죽고 안내가 나왔다 — 0단계 완료 조건(R2):\n")
            print("  " + str(exc).replace("\n", "\n  "))
            return 0
        print("❌ 이 맥에서 찾지 못했습니다:\n")
        print(str(exc))
        return 1
    if blind:
        print("❌ 아무것도 없다고 했는데 무언가를 찾았다 — 시험이 잘못됐다")
        return 1
    print(f"✅ 고른 자리: {p}")
    w = release_warning(p)
    if w:
        print(w)
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_selfcheck("--blind" in sys.argv))
