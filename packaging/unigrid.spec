# -*- mode: python ; coding: utf-8 -*-
"""UNIGRID 설치본 포장 설정 (PyInstaller) — §7 6단계 B, 2026-08-19.

    ~/venvs/unigrid-acdc/bin/pyinstaller packaging/unigrid.spec --noconfirm

**한 폴더(onedir) 방식**을 쓴다. 한 파일(onefile)로 묶으면 켤 때마다 임시 폴더에
통째로 풀어서 느리고, 맥에서는 `mwpython` 이 그 임시 자리의 `app_worker.py` 를
실행하게 되어 자리가 매번 바뀐다. 앱은 자주 켜는 도구라 켜는 속도가 낫다.

🚨 **같이 넣는 것의 배치를 지켜야 한다** (`src/paths.py` 참조).
   맥은 계산을 `mwpython`(MATLAB Runtime 쪽 파이썬) 별도 프로세스로 돌리는데,
   그 프로세스가 `src/app_worker.py` 를 **진짜 파일로** 읽고 그 옆 `../engine` 에서
   엔진을 찾는다. 우리가 얼린 파이썬 안에 넣어 버리면 못 찾는다.

       <뿌리>/src/app_worker.py
       <뿌리>/engine/unigrid_app_mac/   (윈도우는 unigrid_app_win)
"""
import sys
from pathlib import Path

REPO = Path(SPECPATH).resolve().parent          # noqa: F821  (PyInstaller 가 준다)
IS_MAC = sys.platform == "darwin"
PKG = "unigrid_app_mac" if IS_MAC else "unigrid_app_win"

# ── 같이 넣을 것 ─────────────────────────────────────────────────
datas = [
    # 맥에서 mwpython 이 실행할 파일 — **진짜 파일로** 있어야 한다
    (str(REPO / "src" / "app_worker.py"), "src"),
    # 컴파일된 계산 엔진 (그 운영체제 것만)
    (str(REPO / "engine" / PKG), f"engine/{PKG}"),
]
# ── 예제 계통 — 🚨 **넣지 않는다** (2026-08-20 사용자 결정) ──────
# 사용자 지시: *"설치본에는 일단 계통은 다 빼"* — 지금은 교수님께 보여 드리는
# 단계라 예제가 필요 없다. 고객에게 줄 때 다시 본다.
#
# ⚠️ 비어도 앱은 안 죽는다 — 「불러오기」가 그 폴더를 못 찾으면 **사용자 홈 폴더**
#    에서 창을 연다(`src/app.py` 의 `do_import`: `... else Path.home()`).
#
# 되살리는 법 = 아래 목록에 이름을 다시 적는다(그 밑 배선은 그대로 두었다).
# 빼기 전에 담던 12개와 그 까닭:
#     ACDC_matacdc_case5.xlsx           가장 작다 (AC 5 · DC 3 · IC 3)
#     ACDC_CIGRE_MVACMVDCLVDC.xlsx      작은데 AC·DC·IC·DC/DC 가 다 있다
#     ACDC_case24_MatACDC.xlsx          논문 §4-A 검증 (AC 50 · IC 7)
#     ACDC_71bus_3IC_parallel.xlsx      마이크로그리드 · 논문 §4-C
#     ACDC_71bus_L2_genlim.xlsx         점검 탭이 실제로 걸린다 (발전기 한계)
#     AConly_case14.xlsx                AC 전용 → Gauss-Seidel · PV·QV 곡선
#     AConly_case118.xlsx               큰 AC — 찾기·정렬이 쓸모 있어지는 크기
#     ACDC_case24_tapstep.xlsx          계산이 정하는 조정 (계단)
#     DConly_21bus.xlsx                 DC 전용 (Mode 2)
#     ACDC_CIGRE_MVACMVDCLVDC_24h.xlsx  24시간 → 다이나믹 · 비교
#     psse_ieee14.raw                   남의 형식 그대로 열기
#     matpower_ieee14.m                   〃  (셋 다 같은 IEEE 14 계통이다)
EXAMPLES = []
_missing = [n for n in EXAMPLES if not (REPO / "cases" / n).is_file()]
# 🚨 조용히 빠지면 설치본을 열어 보기 전에는 모른다 — 여기서 멈춘다.
assert not _missing, f"예제 계통이 없습니다: {_missing}"
for _n in EXAMPLES:
    datas.append((str(REPO / "cases" / _n), "cases"))
# 🚨 사용 조건 — **넣고 빼고 할 것이 아니다.** MathWorks 라이선스가 앱과 함께
#    배포하는 문서에 조건과 저작권 고지를 넣으라고 요구한다(3.26·23.3·205–210행).
#    「정보」 창의 [사용 조건 보기] 가 이 파일을 연다.
datas.append((str(REPO / "EULA.txt"), "."))

# ── 뺄 것 ───────────────────────────────────────────────────────
# 앱이 실제로 쓰는 Qt 는 QtCore·QtGui·QtWidgets·QtCharts 넷뿐이다(전수 확인).
# 나머지를 빼지 않으면 PySide6 가 통째로 들어와 설치본이 몇 배가 된다.
# ⚠️ 여기 적은 이름을 늘릴 때는 **빼고 나서 앱을 실제로 켜 보고** 정한다.
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtQml",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtSensors",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtTest", "PySide6.QtSql",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    # 우리가 안 쓰는 무거운 것들
    "tkinter", "matplotlib", "scipy", "IPython", "pytest", "PyInstaller",
    # 🚨 `matlab` 과 엔진 패키지는 **넣지 않는다** — MATLAB Runtime 쪽에 있고,
    #    돌 때 `sys.path` 로 찾는다. 얼려 넣으면 오히려 판이 어긋난다.
    "matlab", "unigrid_app_mac", "unigrid_app_win",
]

a = Analysis(                                    # noqa: F821
    [str(REPO / "src" / "app.py")],
    pathex=[str(REPO / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)                                # noqa: F821

exe = EXE(                                       # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="UNIGRID",
    debug=False,
    strip=False,
    upx=False,
    console=False,                               # 창만 뜨고 검은 명령창은 안 뜬다
)
coll = COLLECT(                                  # noqa: F821
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="UNIGRID",
)

if IS_MAC:
    app = BUNDLE(                                # noqa: F821
        coll,
        name="UNIGRID.app",
        icon=None,
        bundle_identifier="kr.ac.cau.gml.unigrid",
        info_plist={
            "CFBundleName": "UNIGRID",
            "CFBundleDisplayName": "UNIGRID",
            "NSHighResolutionCapable": True,
            # 계통 파일을 앱으로 끌어다 놓을 수 있게 (나중에 쓸 자리)
            "LSMinimumSystemVersion": "11.0",
        },
    )
