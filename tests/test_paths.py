# -*- coding: utf-8 -*-
"""얼려도 자리를 찾나 (2026-08-19, §7 6단계 설치본 B).

    ~/venvs/unigrid-acdc/bin/python tests/test_paths.py

계기 — 설치본을 만들려고 보니 앱이 자리를 전부 `Path(__file__)` 로 잡고 있었다.
얼리면 `__file__` 이 번들 안을 가리켜 두 가지가 깨진다.
  · **읽기** — 맥은 `mwpython` 이 `src/app_worker.py` 를 실행한다. 번들 안 경로를
    주면 못 찾는다(그 파일은 우리가 얼린 파이썬이 아니라 MATLAB 쪽이 읽는다).
  · **쓰기** — 최근 연 파일·계통도 자리를 소스 폴더에 쓰고 있었다. 얼린 번들 안은
    읽기 전용이고, 한 컴퓨터를 여럿이 쓰면 섞인다.

보는 것
    1) 안 얼린 상태 — 저장소 뿌리를 가리키고 그 아래 것들이 실제로 있나
    2) 🚨 얼린 상태 — `_MEIPASS` 를 따라가나
    3) 쓰는 자리가 **소스 폴더 밖**인가 (얼렸든 아니든)
    4) 사용자 폴더를 실제로 만들 수 있나
    5) 옛 자리에 있던 것을 **한 번 옮겨 오나** (쓰던 사람이 안 잃게)
    6) 앱 코드가 옛 상수(`PLACES`·`RECENT_FILE`)를 더 안 쓰나
"""
import os
import sys
import json
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
import paths                                                     # noqa: E402

fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<52} {got}")
    else:
        print(f"  ❌ {label:<52} {got}  (바라던 값 {want})")
        fails.append(label)


print("[1] 안 얼린 상태 — 저장소 뿌리")
check("얼렸나", paths.frozen(), False)
check("뿌리가 저장소인가", paths.files_root(), REPO)
check("app_worker.py 가 있나", paths.worker_py().is_file(), True)
check("engine/ 이 있나", paths.engine_dir().is_dir(), True)
check("cases/ 가 있나", paths.cases_dir().is_dir(), True)

print("\n[2] 🚨 얼린 상태 — _MEIPASS 를 따라가나")
fake = Path(tempfile.mkdtemp(prefix="unigrid_frozen_"))
(fake / "src").mkdir()
(fake / "engine").mkdir()
(fake / "cases").mkdir()
(fake / "src" / "app_worker.py").write_text("# 흉내\n", encoding="utf-8")
sys.frozen = True                    # PyInstaller 가 세우는 표시
sys._MEIPASS = str(fake)
try:
    check("얼렸다고 보나", paths.frozen(), True)
    check("뿌리가 _MEIPASS 인가", paths.files_root(), fake)
    check("worker 를 거기서 찾나", paths.worker_py(), fake / "src" / "app_worker.py")
    check("그 파일이 실제로 있나", paths.worker_py().is_file(), True)
    check("engine 도 따라가나", paths.engine_dir(), fake / "engine")

    print("\n[3] 🚨 쓰는 자리는 얼려도 번들 밖인가")
    rf, pf = paths.recent_file(), paths.places_file()
    print(f"    최근 연 파일  {rf}")
    print(f"    계통도 자리   {pf}")
    check("최근 연 파일이 번들 밖인가", fake not in rf.parents, True)
    check("계통도 자리가 번들 밖인가", fake not in pf.parents, True)
    check("소스 폴더 밖인가", (REPO / "src") not in rf.parents, True)
finally:
    del sys.frozen
    del sys._MEIPASS

print("\n[4] 사용자 폴더를 만들 수 있나")
d = paths.user_dir()
print(f"    {d}")
check("있나", d.is_dir(), True)
check("쓸 수 있나", os.access(d, os.W_OK), True)

print("\n[5] 옛 자리에 있던 것을 한 번 옮겨 오나")
old = Path(tempfile.mkdtemp(prefix="unigrid_old_")) / "옛것.json"
old.write_text(json.dumps({"a": 1}), encoding="utf-8")
new = Path(tempfile.mkdtemp(prefix="unigrid_new_")) / "새것.json"
paths.carried_over(old, new)
check("옮겨졌나", new.is_file(), True)
check("내용이 같나", json.loads(new.read_text(encoding="utf-8")), {"a": 1})
new.write_text(json.dumps({"a": 2}), encoding="utf-8")
paths.carried_over(old, new)          # 두 번째는 덮지 않아야 한다
check("이미 있으면 안 덮나", json.loads(new.read_text(encoding="utf-8")), {"a": 2})
check("옛것을 안 지우나", old.is_file(), True)

print("\n[6] 앱 코드가 옛 상수를 더 안 쓰나")
for f, name in [("src/topology.py", "PLACES"), ("src/app.py", "RECENT_FILE")]:
    txt = (REPO / f).read_text(encoding="utf-8")
    check(f"{f} 의 {name}", txt.count(name), 0)

print("\n" + ("🚨 실패 " + ", ".join(fails) if fails else "✅ 전부 통과"))
sys.exit(1 if fails else 0)
