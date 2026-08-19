# -*- coding: utf-8 -*-
"""파일 자리를 한 곳에서 정한다 — 얼려도 맞게 (§7 6단계 설치본, 2026-08-19).

**왜 필요한가.** 지금까지는 모든 자리를 `Path(__file__)` 로 잡았다. 소스에서 돌릴
때는 맞지만, PyInstaller 로 **얼리면 `__file__` 이 번들 안**을 가리켜 두 가지가 깨진다.

자리는 **성격이 둘**이고, 얼리면 서로 다른 곳으로 간다.

| | 무엇 | 얼리면 |
|---|---|---|
| **읽기** | 같이 넣어 주는 것 — `src/app_worker.py` · `engine/` · `cases/` | 번들 안 (`sys._MEIPASS`) |
| **쓰기** | 사람마다 달라지는 것 — 최근 연 파일 · 계통도에서 끌어 옮긴 자리 | **번들 안에 못 쓴다** (읽기 전용이고 여러 사람이 쓰면 섞인다) → 사용자 폴더 |

🚨 **`src/app_worker.py` 는 특별하다** — 맥에서 그 파일을 **`mwpython` 이 실행**한다
(`app_engine._Worker`). 우리가 얼린 파이썬이 아니라 MATLAB Runtime 쪽 파이썬이므로
**진짜 `.py` 파일로 디스크에 있어야** 하고, 그 옆(`../engine`)에 엔진이 있어야 한다.
⇒ 설치본에서도 이 배치를 지킨다:

    <뿌리>/src/app_worker.py
    <뿌리>/engine/unigrid_app_mac/

⚠️ **자리를 값으로 굳혀 두지 않는다.** 함수로 두면 시험이 얼린 상태를 흉내 낼 수 있다
(모듈을 읽는 순간 계산해 버리면 못 바꾼다).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "UNIGRID"


def frozen() -> bool:
    """PyInstaller 로 얼린 채 도는 중인가."""
    return bool(getattr(sys, "frozen", False))


def files_root() -> Path:
    """같이 넣어 준 것들의 뿌리 — 이 아래에 `src/`·`engine/`·`cases/` 가 있다."""
    if frozen():
        # PyInstaller 는 동봉물을 `_MEIPASS` 에 푼다(한 폴더 방식이면 실행파일 옆).
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent      # 저장소 뿌리


def worker_py() -> Path:
    """맥에서 `mwpython` 이 실행할 계산 프로세스 파일."""
    return files_root() / "src" / "app_worker.py"


def engine_dir() -> Path:
    return files_root() / "engine"


def cases_dir() -> Path:
    return files_root() / "cases"


def user_dir() -> Path:
    """사람마다 달라지는 것을 두는 자리. 없으면 만든다.

    맥 `~/Library/Application Support/UNIGRID` · 윈도우 `%APPDATA%\\UNIGRID` ·
    그 밖 `~/.unigrid`. 못 만들면 홈으로 물러난다 — 여기서 터지면 앱이 안 뜬다.
    """
    try:
        if sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        elif os.name == "nt":
            base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        else:
            d = Path.home() / ".unigrid"
            d.mkdir(parents=True, exist_ok=True)
            return d
        d = base / APP_NAME
        d.mkdir(parents=True, exist_ok=True)
        return d
    except Exception:
        return Path.home()


def carried_over(old: Path, new: Path) -> Path:
    """옛 자리에 있던 것을 새 자리로 한 번만 옮겨 온다.

    소스 폴더 안에 쌓아 두던 것을 사용자 폴더로 옮기면서, **쓰던 사람이 잃지 않게**
    한 번 복사한다. 옛 파일은 지우지 않는다 — 소스에서 돌리던 판이 아직 볼 수 있다.
    """
    try:
        if old.is_file() and not new.exists():
            shutil.copyfile(old, new)
    except Exception:
        pass
    return new


def recent_file() -> Path:
    """최근 연 파일 목록."""
    new = user_dir() / "recent.json"
    return carried_over(Path(__file__).resolve().parent / ".recent.json", new)


def places_file() -> Path:
    """계통도에서 끌어 옮긴 버스 자리 (케이스별)."""
    new = user_dir() / "topology_places.json"
    return carried_over(Path(__file__).resolve().parent / ".topology_places.json", new)
