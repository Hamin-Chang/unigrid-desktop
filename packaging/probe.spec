# -*- mode: python ; coding: utf-8 -*-
"""얼린 자리에서 `import` 가 왜 죽는지 보는 probe (2026-08-20).

    packaging\\diag_win.bat

**왜 따로 만드나.** 진짜 앱은 `console=False` 라 오류가 화면에 안 나오고,
`app.py` 가 `load_case` 실패를 삼켜서 "못 찾았습니다" 한 줄만 뜬다. 이 probe 는
**같은 조건**(같은 `pathex`·같은 `excludes`)으로 얼리되 **검은 창**을 띄워
예외를 그대로 찍는다.

🚨 `excludes` 를 여기 베껴 쓰지 않는다 — 진짜 spec 에서 **읽어 온다**. 두 벌로 두면
   한쪽만 고쳐져 "probe 는 되는데 앱은 안 된다"가 되고, 그게 제일 헷갈린다.
"""
import ast
import re
from pathlib import Path

REPO = Path(SPECPATH).resolve().parent           # noqa: F821  (PyInstaller 가 준다)
_spec = (REPO / "packaging" / "unigrid.spec").read_text(encoding="utf-8")
excludes = ast.literal_eval(re.search(r"excludes = (\[.*?\])", _spec, re.S).group(1))

a = Analysis(                                    # noqa: F821
    [str(REPO / "packaging" / "probe_import.py")],
    pathex=[str(REPO / "src")],
    binaries=[],
    datas=[],
    hiddenimports=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)                                # noqa: F821
exe = EXE(                                       # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="PROBE",
    debug=False,
    strip=False,
    upx=False,
    console=True,                                # 🚨 여기가 진짜 앱과 다른 유일한 곳
)
coll = COLLECT(                                  # noqa: F821
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="PROBE",
)
