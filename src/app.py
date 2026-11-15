"""UNIGRID 데스크톱 — 앱 본체 (창·탭·표·그래프·계통도).

계산은 컴파일된 MATLAB 엔진이 한다(`app_engine` → `app_worker` → `engine/`).
케이스를 열기 전까지는 화면 모양을 보이려고 **가짜 값**을 그리고,
케이스를 열면 그 자리에 실제 결과가 들어온다.

실행:  ~/venvs/unigrid-acdc/bin/python src/app.py

⚠️ 아직 안 만든 것은 화면에서 그렇게 말한다 — 엑셀로 만들기(§7 3단계).
"""
import os
import sys
import time

# ── 🚨 얼린 윈도우 앱에는 `sys.stdout` 이 없다 (2026-08-20) ───────────
# PyInstaller 로 `console=False` 로 얼리면 윈도우에서 `sys.stdout`·`sys.stderr`
# 가 **`None`** 이 된다. 그러면 `print()` 한 줄에도 앱이 죽고, MATLAB Runtime 이
# 만든 파이썬 패키지는 계산을 마치고 출력을 비우는 자리에서 죽는다 —
#     "An error occurred when evaluating the result from a function.
#      Details: 플러시에서 오류가 발생했습니다."
# ⚠️ 맥에서는 안 드러난다(맥은 계산을 별도 프로세스로 돌리고 그쪽 stdout 이 산다).
# 버릴 자리를 하나 끼워 둔다. 진짜 원인은 `app_engine._mat_streams` 쪽에서
# 함수마다 따로 넘기고, 이건 그 밖의 모든 `print` 를 위한 안전망이다.
if sys.stdout is None or sys.stderr is None:
    import io as _io
    if sys.stdout is None:
        sys.stdout = _io.StringIO()
    if sys.stderr is None:
        sys.stderr = _io.StringIO()

import math
import re
import random
from pathlib import Path

import numpy as np
from PySide6.QtCore import (Qt, QThread, QTimer, Signal, QUrl, QPointF,
                            QPoint, QRect, QRectF, QEvent, QObject, QSize,
                            QPropertyAnimation, QVariantAnimation, QEasingCurve,
                            QAbstractAnimation)
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QDesktopServices,
                          QPainter, QPen, QBrush, QPainterPath, QImage,
                          QRadialGradient, QLinearGradient, QConicalGradient)
from PySide6.QtWidgets import (QProgressBar, QStyledItemDelegate, 
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QLabel, QPushButton, QFrame, QTabWidget, QTableWidget, QTableWidgetItem,
    QComboBox, QSpinBox, QDialog, QCheckBox, QLineEdit, QButtonGroup, QTabBar,
    QHeaderView, QScrollArea, QSizePolicy, QSplitter, QSplitterHandle,
    QFileDialog,
    QProgressDialog, QMessageBox, QInputDialog, QSlider,
)

import json
import app_engine as ENGINE
import engine_path
import paths
import charts
import checks
from checks import (col_index, gen_limit_rows, real_violations,   # noqa: F401
                    unrated_lines, violation_count, reached_count, GEN_LIMIT_COLS,
                    overloaded_rows as checks_overloaded)
import exporter

# 케이스 읽기는 **이 저장소 안**에 있다 (2026-08-05 들여옴).
# 예전에는 옆 폴더의 공개 파이썬 패키지를 빌려 썼는데, 그 폴더는 이 맥에만 있어
# 남의 컴퓨터에서는 앱이 떠도 파일을 하나도 못 열었다 — 공개 배포가 안 되는 구조였다.
try:
    from load_case import load_case
    _LOAD_CASE_ERR = ""
except Exception as _exc:              # 그래도 앱은 뜨게 — 대신 **왜** 못 불렀는지 붙든다
    # 🚨 2026-08-20: 윈도우 설치본에서 이게 걸렸는데 **원인이 안 보였다.**
    #    `load_case` 는 pandas 를 부르는데, 그 판 venv 에 pandas 가 없어 얼릴 때
    #    같이 안 들어갔다. 앱은 "못 찾았습니다" 한 줄만 띄워서, 무엇이 없는지
    #    알아내려고 소스로 따로 돌려 봐야 했다. ⇒ 예외 문구를 그대로 보여 준다.
    load_case = None
    _LOAD_CASE_ERR = f"{type(_exc).__name__}: {_exc}"

import scenario as SC
import adjust_panel as ADJ
import cell_rules as RULES
import compare_items as CI          # 계통 조건 바꾸기 (PDR §7 2단계)


def _grid_headers():
    """계통 데이터 탭에 쓸 열 이름 — `format_v2` 의 v2 머리글을 엔진 자리에 맞춰 편다.

    이렇게 하면 서식 정의가 **한 곳**(format_v2)에만 있고, 화면은 그것을 빌려 쓴다.
    """
    try:
        import format_v2 as F
        import read_v2
    except Exception:
        return {}
    out = {}
    for sheet in F.SHEETS:
        key = read_v2.TABLE_OF_SHEET.get(sheet.name)
        if key is None:
            continue
        cols = [c for c in sheet.cols if c.v1_col]
        if not cols:
            continue
        wide = max(c.v1_col for c in cols)
        names = [""] * wide
        for c in cols:
            names[c.v1_col - 1] = c.header
        out[key] = names
    return out


GRID_HEADERS = _grid_headers()


def _grid_scales():
    """엔진 값 → 화면 값 배율. 🚨 이게 없으면 W 를 [MW] 머리글 아래 찍는다.

    (실제로 그랬다 — 발전기 `P_gen [MW]` 칸에 10000000 이 찍혔다. 10이어야 한다.)
    """
    try:
        import format_v2 as F
        import read_v2
    except Exception:
        return {}
    out = {}
    for sheet in F.SHEETS:
        key = read_v2.TABLE_OF_SHEET.get(sheet.name)
        if key is None:
            continue
        m = {c.v1_col - 1: c.scale for c in sheet.cols
             if c.v1_col and c.scale != F.KEEP}
        if m:
            out[key] = m
    return out


GRID_SCALES = _grid_scales()

# ③ 운전 조건 — **여기만 고칠 수 있다** (0부터 센 열 번호).
# 나머지 칸은 회색으로 두어 "④ 계통 자체는 엑셀에서" 라는 선을 화면으로 보여 준다(PDR §4.3).
# 머리글은 있는데 파일엔 아직 없는 열까지 **빈 칸으로 보여 줄** 표.
# A1 조정 열(14~19)은 옛 파일에 없다 — 안 보여 주면 켤 방법이 없다.
GRID_PAD_TO_HEADERS = {"AC_Line_dat", "AC_Bus_dat"}

# 🚨 **A1 조정 칸은 여기 없다** (2026-08-27). 엑셀에는 있는 칸이고 표에 **값도 그대로
#    보여 주지만**, 고치는 곳은 `⚙ AC 조정` 패널 하나다 — 표 안에서도 고칠 수 있게 두면
#    같은 값을 고치는 자리가 둘이 되고, 표 쪽은 19칸 중 14~19번째라 화면 밖이다.
#    아래 `GRID_PANEL_COLS` 가 그 칸을 「패널에서 고친다」고 알려 준다.
GRID_EDITABLE = {
    "AC_gen_dat": {2, 3, 4, 7},        # 운전모드 · P-f droop · Q-V droop · 지정전압
    "DC_gen_dat": {2, 3, 5},           # 운전모드 · P-Vdc droop · 지정전압
    "IC_dat": {2, 3, 4, 5, 6, 7, 8},   # AC/DC 제어모드 · droop 셋 · P·Q 동작점
    "DCDC_Conv_dat": {5, 6, 7, 9},     # droop 둘 · 동작점 · 운전모드
}

# 🚨 **비울 수 있는 칸** (2026-08-14 사용자 요청). 표에서 값을 지우면 NaN 이 되는데,
#   그게 뜻을 갖는 칸은 **A1 조정 칸뿐**이다 — 비어 있음 = 「안 걸었다」·「한계를 안 적어
#   자동으로 잡는다」. 엔진이 이미 그렇게 읽는다(`isnan` 검사가 다 있다).
#   ⚠️ 나머지 편집 칸(발전기 운전모드·droop·지정전압 등)은 **비우면 어떻게 되는지
#      확인하지 않았으므로 그대로 막는다.** 넓히려면 그 칸이 NaN 일 때 엔진이 무엇을
#      하는지 먼저 확인하고 여기 더한다.
#   계기: 계단을 켠 뒤 한계를 다시 비워 자동(0.9~1.1)으로 돌리려는데 **방법이 없었다** —
#         `float("")` 이 걸려 "숫자가 아닙니다" 로 되돌아갔다.
GRID_CLEARABLE: dict[str, set[int]] = {}   # 조정 칸이 패널로 옮겨 가며 비었다 (2026-08-27)

# 표에서는 **읽기만** 하고 `⚙ AC 조정` 패널에서 고치는 칸. 회색으로 두되 칸을 짚으면
# 어디서 고치는지 말해 준다 — 안 그러면 "왜 안 고쳐지지" 로 끝난다.
GRID_PANEL_COLS = {
    "AC_Line_dat": {13, 14, 15, 16, 17, 18},   # Ctrl Mode·Bus·Target·Min·Max·Step Size
    "AC_Bus_dat": {17, 18, 19, 20, 21},        # Shunt Ctrl Mode·Target·Bmin·Bmax·Step Size
}

# 이 버스 수를 넘으면 **그래프를 접은 채로 연다** (2026-08-06 사용자 확정).
#   이유는 속도가 아니라 **읽기 어려워서**다 — 6,495버스면 점이 6,495개라 빨간 덩어리가 된다.
#   ⚠️ 접어도 별로 안 빨라진다(실측 0.86~1.49배, `실측_R4_버스수대시간.csv`). 표가 그만큼
#      넓어져 줄을 더 그리기 때문이다. 그러니 "빨라진다"고 말하지 않는다.
#   숫자는 점이 겹쳐 보이기 시작하는 지점으로 잡았다. 바꾸려면 여기 한 줄만 고치면 된다.
BIG_BUSES = 1000
# 시나리오 목록에서 **한 번에 보여 줄 줄 수**. 넘으면 목록 안에서 스크롤한다.
# 안 씌우면 한 줄에 25px 씩 카드가 계속 자라 그래프와 표를 먹는다(2026-08-15 실측).
SCENARIO_ROWS = 4
SCENARIO_ROW_H = 42   # 실측 줄 간격(렌더에서 잼 — sizeHint 증가분 25 와 다르다)

# 계통 데이터 탭에 보여 줄 표 (차례대로). 켜고 끌 수 있는 것이 앞에 온다.
def _col_name(key, col):
    h = GRID_HEADERS.get(key, [])
    return h[col] if col < len(h) else f"{col + 1}열"


def _cell_tip(key, col):
    """고칠 수 있는 칸에 붙는 설명 — 무엇을 받는지까지 말해 준다."""
    tip = ("고칠 수 있는 값입니다 — 바꾸면 계산은 안 돌고 "
           "위의 [이 조건으로 계산] 을 눌러야 풉니다")
    rule = RULES.RULES.get(key, {}).get(col)
    if rule in (RULES.BUS_AC, RULES.BUS_DC):
        tip += ("\n\n계통에 있는 "
                + ("AC" if rule == RULES.BUS_AC else "DC") + " 버스 번호여야 합니다.")
    elif rule == RULES.FLAG:
        tip += "\n\n0(끔) 아니면 1(켬) 입니다."
    elif rule == RULES.SHARE:
        tip += "\n\n0 과 1 사이입니다 (부하 나눔 비율)."
    elif rule == RULES.POS:
        tip += "\n\n0 보다 커야 합니다."
    elif rule == RULES.NONNEG:
        tip += "\n\n0 이상이어야 합니다."
    return tip


def _fit_header(t):
    """머리글이 잘리지 않을 **최소 열폭**을 걸고, 넘치면 옆으로 넘긴다 (2026-09-01).

    🚨 늘려 맞추기(Stretch)는 창 폭을 열 수로 나눈다. 창 929px 에서 「볼 항목」의
       열을 다 켜면 한 칸이 **61px** 이 되어 `Load_Q[MVAR]` 가 **「oad_Q[MVAR」**
       로 보였다 — 머리글이 가운데 정렬이고 줄임표가 없어(ElideNone) **양끝이**
       잘린다. 실측: AC 결과 11 건 · 선로 조류 7 건 · 수렴은 **기본 상태에서도** 4 건.
    ⚠️ 줄임표(ElideRight)로는 못 푼다 — 이 표의 이름은 **앞이 겹친다.**
       `Load_P[MW]` 와 `Load_Q[MVAR]` 가 둘 다 「Load_…」 가 되어, 읽기는 쉬워지고
       **두 열을 구별할 수 없게** 된다. 지금 잘린 꼴이 차라리 P·Q 는 갈렸다.
    📌 계통 데이터 탭이 이미 같은 문제를 풀어 뒀다(20 열짜리 IC 표) — 거기서는
       글자에 맞추고 옆으로 넘겼다. 여기서는 **넓은 창의 모습을 그대로 두려고**
       Stretch 를 유지한 채 아래 최소 폭만 건다.

    최소 폭은 `sectionSizeHint` 로 잡는다 — 여백(QSS padding 9)과 **정렬 화살표
    자리**까지 Qt 가 셈해 주므로 상수를 손으로 못박지 않는다. 실측 차이가 정렬을
    켠 표는 45~48px, 안 켠 표는 26~32px 로 갈렸다.
    🚨 **한 박자 미뤄서 잰다.** 표를 만들 때도, 탭에 붙일 때도 QSS(글꼴 14px·
       여백 9px)는 아직 안 입혀져 있어 머리글이 **기본 9pt** 로 재진다. 실측 —
       「가장 큰 블록」이 그때 63px, 화면에 나온 뒤 90px. 라틴 이름은 그 차이로도
       살아남지만 한글은 모자라 그대로 잘렸다. 정렬 화살표 몫도 이때 들어온다.
       (계통 데이터 표가 쓰는 `QTimer.singleShot(0, fit)` 과 같은 수법이다.)
    """
    def fit():
        try:
            hh = t.horizontalHeader()
            if t.columnCount():
                hh.setMinimumSectionSize(max(hh.sectionSizeHint(c)
                                             for c in range(t.columnCount())))
        except RuntimeError:      # 그 사이에 화면을 다시 그려 표가 지워졌다
            pass

    QTimer.singleShot(0, fit)


def _fit_button(b, extra=34):
    """단추가 글자를 안 자를 만큼 넓어지게 한다 (2026-09-01).

    🚨 **QSS 가 입혀진 뒤에 잰다.** 만들 때 재면 창의 기본 글꼴(9pt)로 재게 되어
       실제 글꼴(14px)보다 좁게 나온다 — 「OFF」가 25px 대 30px 이라 모자랐다.
       `_fit_header` 와 같은 함정이고 같은 수법으로 푼다.
    ⚠️ `sizeHint` 로는 못 푼다 — QSS 안쪽 여백을 안 센다(2026-08-28 계통도 단추에서 확인).
    """
    def fit():
        try:
            b.setMinimumWidth(b.fontMetrics().horizontalAdvance(b.text()) + extra)
        except RuntimeError:      # 그 사이에 화면을 다시 그려 단추가 지워졌다
            pass

    QTimer.singleShot(0, fit)


# 「부하 배율」은 표가 아니다 — `⚙ AC 조정`(`adjust_panel.KEY`) 과 같은 자리에
# 두는 가짜 표 이름이다 (2026-09-01). 왜 옮겼는지는 `load_bar` 머리말 참조.
LOAD_KEY = "__LOAD__"

GRID_TABLES = [
    ("AC_Line_dat", "AC 선로"), ("AC_gen_dat", "AC 발전기"),
    ("DC_Line_dat", "DC 선로"), ("DC_gen_dat", "DC 발전기"),
    ("IC_dat", "IC"), ("DCDC_Conv_dat", "DC/DC"),
    ("AC_Bus_dat", "AC 버스"), ("DC_Bus_dat", "DC 버스"),
]

# 🚨 **소스 폴더가 아니라 사용자 폴더에 쓴다** (2026-08-19, §7 6단계).
#    얼린 번들 안은 읽기 전용이고, 여러 사람이 쓰면 서로 섞인다. `paths` 참조.
#    자리를 값으로 굳히지 않고 **쓸 때마다 묻는다** — 시험이 흉내 낼 수 있어야 한다.
def iters_text(sol) -> str:
    """반복 횟수 글. 엔진이 반복 기록을 안 준 결과(DC 단독 계통 · 2026-11-03 확인)는 「0회」 가 아니라 「—」.

    엔진의 DC 단독 경로는 `iter_count` · `mis_history` 를 결과에 넣지 않는다 — 앱이 0 으로 메워
    「반복 0회」 로 보였다. 엔진(MATLAB) 쪽을 고치기 전까지 앱에서는 모른다고 적는다.
    """
    if sol is None:
        return "—"
    if "iter_count" not in (getattr(sol, "raw", None) or {}):
        return "—"
    return f"{sol.iters}회"


def load_recent() -> list:
    try:
        return json.loads(paths.recent_file().read_text(encoding="utf-8"))[:6]
    except Exception:
        return []


def save_recent(path: str, info: str) -> None:
    items = [x for x in load_recent() if x.get("path") != path]
    items.insert(0, {"path": path, "info": info})
    try:
        paths.recent_file().write_text(json.dumps(items[:6], ensure_ascii=False),
                                       encoding="utf-8")
    except Exception:
        pass


class WarmThread(QThread):
    """시작 화면에 있는 동안 계산 엔진(MATLAB Runtime)을 미리 띄워둔다."""
    ready = Signal(bool)

    def run(self):
        try:
            ENGINE.warmup()
            self.ready.emit(True)
        except Exception:
            self.ready.emit(False)


class SolveThread(QThread):
    """조류계산을 화면과 별도로 돌린다 (7초쯤 걸려 UI가 멈추면 안 되므로)."""
    done = Signal(object)
    failed = Signal(str)
    # 계산 엔진(MATLAB Runtime)이 없는 것은 **계산 실패가 아니라 설치 안내**다.
    # 남의 컴퓨터에서 가장 먼저 만나는 화면이라 따로 받는다 (PDR §4.1 · R2).
    engine_missing = Signal(str)

    def __init__(self, path, case=None, method="nr"):
        super().__init__()
        self.path = path
        self.case = case          # 있으면 이것을 푼다 (조건을 바꿔 다시 풀 때)
        self.method = method      # "nr" Newton-Raphson · "gs" Gauss-Seidel (2026-08-12)
        self.loaded_case = None   # 파일에서 읽은 원본 — 창이 받아 들고 있는다

    def run(self):
        try:
            warm = ENGINE.solved_before()   # 첫 계산이면 준비 시간이 섞인다
            t0 = time.perf_counter()
            # 위험한 형태 거르기는 `load_case` 안으로 들어갔다 (2026-08-06)
            case = self.case if self.case is not None else load_case(self.path)
            self.loaded_case = case
            sol = ENGINE.solve(case, method=self.method)
            sol.seconds = time.perf_counter() - t0   # 엑셀 읽는 시간까지 포함
            sol.warm_start = warm
            sol.method = self.method                 # 어느 해법으로 푼 결과인지 (2026-08-12)
            self.done.emit(sol)
        except engine_path.EngineNotFound as exc:
            self.engine_missing.emit(str(exc))     # 안내문을 그대로 들고 있다
        except Exception as exc:
            self.failed.emit(str(exc))

class CurveThread(QThread):
    """PV·QV 곡선을 화면과 별도로 돌린다 (14버스도 6초, 큰 계통은 몇 분)."""
    done = Signal(object)
    failed = Signal(str)
    engine_missing = Signal(str)

    def __init__(self, case, load_buses, curve_buses):
        super().__init__()
        self.case = case
        self.load_buses = load_buses
        self.curve_buses = curve_buses

    def run(self):
        try:
            cur = ENGINE.curve(self.case, self.load_buses, self.curve_buses)
            self.done.emit(cur)
        except engine_path.EngineNotFound as exc:
            self.engine_missing.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))


# ─────────────────────────────────────────── 판
# 앱의 판 번호. 「정보」 창과 윈도우 설치본(`packaging/unigrid.iss`)이 이걸 쓴다.
#   2.1   = UI 확정까지 (2026-09-02, 커밋 05a5214)
#   2.1.1 = 윈도우에서 못 쓰는 MATLAB 을 먼저 잡던 것을 고침 (2026-09-07)
#           — 2.1 설치본은 MATLAB 구성에 따라 계산이 아예 안 됐다. engine_path.py 참조
#   2.2   = 애플 유리 디자인 + 계산 엔진 v15 (2026-09-11)
#           — 허용오차 1e-3 → 1e-6. 발전기 셋을 불필요하게 포화시키던 것이 사라져
#             case24 위반이 26 → 23건이 됐다(3건이 가짜였다).
# ⚠️ 올릴 때는 `packaging/unigrid.iss` 의 AppVer 도 같이 올린다 —
#    설치본 파일 이름이 거기서 나온다.
VERSION = "2.3"


# ─────────────────────────────────────────── 색
# 🍎 **맥 앱 색을 그대로 쓴다** (2026-09-08 사용자: *"난 애플 앱처럼 디자인하고 싶어"*).
#    값은 애플 시스템 색이다 — systemBlue `#007AFF`/`#0A84FF` · systemGreen
#    `#34C759`/`#30D158` · systemOrange `#FF9500`/`#FF9F0A` · 구분선 `#D1D1D6`/`#38383A`.
#    ⭐ 맥 앱의 뼈대 = **바탕은 옅은 회색 · 내용은 흰 카드 · 카드에 테두리를 안 쓴다.**
#    그래서 `bg` 가 창 전체(사이드바 포함) 바탕이고 `surface` 가 카드다 — 지금까지
#    사이드바가 흰색이고 본문이 회색이라 **맥과 반대**였다.
# 🎨 **앱 2.3 — 테마색은 먹색(무채색)이다** (2026-11-01 사용자 확정 「① 먹색」).
#    그래프 · 계통도가 채도 있는 색을 거의 다 쓴다 — AC 빨강 2° · 경고 15° · IC 24° ·
#    AC slack 33° · 위상각 초록 145° · DC slack 청록 174° · **DC 파랑 216°** · DC/DC 보라 271° ·
#    위반 자홍 324°. 옛 강조색 `#007aff`(211°)는 DC 파랑과 거의 같았다. 테마를 무채색으로
#    두면 화면에서 색이 보이는 곳은 곧 데이터다. 경고(`warn`) · 정상(`ok`)은 상태 색이라 그대로.
#    `on_accent` = 강조색 바탕 위 글자색 · `rail*` = 왼쪽 사이드바(B 꼴 · `RailButton`).
# 🚨 2026-11-15 — 디자인 전체를 바꿨다(사용자: 「UI 디자인 전체를 바꾸고 싶은데 너가 알아서」).
#    꼴 = **진한 먹색 사이드바 + 밝고 평평한 작업 영역**. 바탕 얼룩 · 유리 · 검은 그라데이션을 걷고,
#    카드는 흰 판 + 가는 테두리, 색은 차가운 회색 계열로 맞췄다. 테마색은 먹색 그대로다(그래프 색과
#    안 겹치게 — 11-01 사용자 확정). `nav*` = 사이드바(밝은 · 어두운 화면 모두 진한 판).
#    옛 색표는 `_backup/src_20261115_after_fixes/app.py` 에 있다.
LIGHT = dict(
    bg="#eef0f4", surface="#ffffff", border="#e1e4ea", text="#15171c",
    muted="#667085", accent="#15171c", accent_soft="#eceef2", on_accent="#ffffff",
    rail="#15171c", rail_fg="#99a1b0", rail_on="#ffffff", rail_on_fg="#15171c",
    ok="#1f8f4e", warn="#c93400", plot="#ffffff",
    side="#e7e9ee", hair="#eceef2",   # 잠긴 단추 바탕 · 표 가로 구분선
    nav="#15171c", nav_card="#1e2128", nav_on="#2c303a", nav_text="#ffffff",
    nav_fg="#99a1b0", nav_line="#2a2e37",
    glass="#f5f6f8", glass_solid="rgba(255,255,255,0.34)",
    glass_plot="#f5f6f8",
    glass_bar="rgba(255,255,255,0.93)", glass_edge="#dde0e7",
)
DARK = dict(
    bg="#0d0e11", surface="#17191e", border="#292c34", text="#f1f2f4",
    muted="#99a1b0", accent="#f1f2f4", accent_soft="#262930", on_accent="#15171c",
    rail="#0d0e11", rail_fg="#99a1b0", rail_on="#f1f2f4", rail_on_fg="#15171c",
    ok="#30d158", warn="#ff9f0a", plot="#17191e",
    side="#1c1e24", hair="#22252c",
    nav="#17191e", nav_card="#1f2228", nav_on="#2c303a", nav_text="#ffffff",
    nav_fg="#99a1b0", nav_line="#2a2e37",
    glass="#1f2228", glass_solid="rgba(44,44,46,0.40)",
    glass_plot="#1c1e24",
    glass_bar="rgba(44,44,46,0.94)", glass_edge="#30343d",
)

MODES = ["스냅샷", "다이나믹", "비교"]
# 최상위 갈래 — 조류계산과 곡선은 **서로 기대지 않는다** (F1d · 2026-08-12)
TASKS = ["조류계산", "PV·QV 곡선"]

GRAPHS = {
    "스냅샷": [
        ("전압·위상", ["전압  [pu]  ·  x축 = 버스", "위상각  [deg]  ·  x축 = 버스"], "v"),
        # 🚨 **3D 가 아니다** — `charts.FlowHeatmap` 은 「출발버스 × 도착버스」 색 격자다
        #    (조류 행렬이 거의 비어 있어 3D 막대로는 안 읽힌다). 이름에만 "(3D)" 가
        #    붙어 있어 **끌어서 돌리려다 안 된다고 읽혔다** (2026-09-08 점검 i14).
        ("조류 (P·Q)", ["유효전력 P  ·  출발 × 도착 버스",
                        "무효전력 Q  ·  출발 × 도착 버스"], "h"),
        ("부하율", ["선로 부하율  [%]"], "v"),
        ("토폴로지", ["계통 단선도"], "v"),
    ],
    "다이나믹": [
        ("전압·위상", ["전압  [pu]  ·  x축 = 시간", "위상각  [deg]  ·  x축 = 시간"], "v"),
        ("주파수", ["주파수  [Hz]  ·  x축 = 시간"], "v"),
        ("토폴로지", ["계통 단선도"], "v"),
    ],
}

# 열 이름은 result_columns.py 그대로. show=기본으로 보이는 열
TABLE_SPECS = {
    "AC 결과": [
        ("Bus", 1), ("VM[pu]", 1), ("Freq[Hz]", 0), ("Angle[deg]", 1),
        ("Gen_P[MW]", 1), ("Gen_Q[MVAR]", 1), ("Load_P[MW]", 1),
        ("Load_Q[MVAR]", 1), ("toAC_P[MW]", 0), ("toAC_Q[MVAR]", 0),
        ("baseKV[kV]", 0), ("Vmin[pu]", 0), ("Vmax[pu]", 0),
    ],
    "DC 결과": [
        ("Bus", 1), ("VM[pu]", 1), ("VM_norm[pu]", 0), ("Gen_P[MW]", 1),
        ("Load_P[MW]", 1), ("toDC_P[MW]", 1), ("baseKV[kV]", 0),
        ("Vmin[pu]", 0), ("Vmax[pu]", 0),
    ],
    "선로 조류": [
        ("From", 1), ("To", 1), ("From_P[MW]", 1), ("To_P[MW]", 1),
        ("From_Q[MVAR]", 0), ("To_Q[MVAR]", 0), ("Loss_P[MW]", 1),
        ("Loss_Q[MVAR]", 0), ("Capacity[MVA]", 0), ("Loading[%]", 1),
        ("Status", 0),
    ],
    "손실": [
        ("Time[h]", 1), ("Ploss[W]", 1), ("Qloss[Var]", 1),
        ("Ploss[%]", 1), ("Qloss[%]", 1),
    ],
    "VSC 버스": [
        ("BusAC", 1), ("BusDC", 1), ("VSC_VM[pu]", 1), ("VSC_Angle[deg]", 1),
        ("Inj_P[MW]", 1), ("Inj_Q[MVAR]", 1), ("Loss[MW]", 1),
    ],
    "VSC 그리드전력": [
        ("BusAC", 1), ("BusDC", 1), ("Grid_P[MW]", 1), ("Grid_Q[MVAR]", 1),
        ("TrafFilter_P[MW]", 0), ("TrafFilter_Q[MVAR]", 0), ("Filter_Q[MVAR]", 0),
        ("VSCFilter_Q[MVAR]", 0), ("VSC_P[MW]", 1), ("VSC_Q[MVAR]", 1),
    ],
    "VSC 손실": [
        ("BusAC", 1), ("BusDC", 1), ("VSC_P[MW]", 0), ("VSC_Q[MVAR]", 0),
        ("Filter_Q[MVAR]", 0), ("TransfoLoss_P[MW]", 1), ("TransfoLoss_Q[MVAR]", 0),
        ("ReactorLoss_P[MW]", 1), ("ReactorLoss_Q[MVAR]", 0), ("VSCLoss_P[MW]", 1),
    ],
}
VSC_TABLES = ["VSC 버스", "VSC 그리드전력", "VSC 손실"]


def tables_for(mode, show_vsc):
    names = ["AC 결과", "DC 결과", "선로 조류"]
    if mode == "다이나믹":          # 손실 = 계통 전체·시간축 데이터
        names.append("손실")
    if show_vsc:
        names += VSC_TABLES
    return names


# 점검(위반) 가짜 데이터 — 실제로는 결과 표에서 걸러낸다
VIOLATIONS = {
    "전압 위반": (["Bus", "V[pu]", "한계", "초과량"],
        [["7", "1.0642", "Vmax 1.05", "+0.0142"],
         ["12", "0.9385", "Vmin 0.95", "-0.0115"]]),
    "과부하 선로": (["From", "To", "Loading[%]", "용량[MVA]"],
        [["3", "7", "112.4", "25.0"]]),
    "변환기 한계": (["BusAC", "BusDC", "상태", "S_max[MVA]"],
        [["4", "2", "용량곡선 도달", "10.0"]]),
    "발전기 한계": (["발전기", "항목", "걸린 한계", "출력", "한계값"],
        [["AC 3", "무효 Q", "용량 원 (S_N)", "18.4", "18.4"]]),
}
# 수렴 (실측값: CIGRE 케이스)
CONV = dict(
    converged=True, iters=2, threshold=1e-3,
    mis=[0.481353, 0.013484, 0.000377],
    blocks=["AC_P_mis", "AC_Q_mis", "DC_P_mis", "F_P_conv",
            "F_Q_conv", "F_P_AC", "F_Q_AC", "F_P_DC"],
    block_hist=[[0.505421, 0.362611, 0.16, 0, 0, 0, 0, 0],
                [0.380797, 0.019848, 0.001058, 1.8e-05, 0, 0, 0, 0],
                [0.413095, 0.052252, 9.5e-05, 2.2e-05, 0, 0, 0, 0]],
    dominant=["AC_P_mis", "AC_P_mis", "AC_P_mis"],
    seconds=1.39,
)



def dynamic_table(sol, bus_row):
    """다이나믹 — 고른 버스 하나의 시간별 값 (지금 앱에는 없던 표)."""
    n_ac = sol.AC.shape[0] if sol.AC.size else 0
    if bus_row < n_ac and sol.AC.size:
        arr, cols, which = sol.AC, sol.cols("AC"), "AC"
        row = bus_row
    elif sol.DC.size:
        arr, cols, which = sol.DC, sol.cols("DC"), "DC"
        row = bus_row - n_ac
    else:
        return "시간별 값", [], np.zeros((0, 0))
    row = max(0, min(row, arr.shape[0] - 1))
    # `Freq` 가 빠져 있었다 — 슬랙 없는 계통에서 시간마다 움직이는 값인데
    # 그래프에만 있고 표에는 없었다 (2026-09-08 점검 i58). 단위는 **Hz** 다.
    keep = [c for c in ("VM[pu]", "Freq[Hz]", "Angle[deg]", "Gen_P[MW]", "Gen_Q[MVAR]",
                        "Load_P[MW]", "Load_Q[MVAR]", "toAC_P[MW]", "toDC_P[MW]")
            if c in cols]
    idx = [cols.index(c) for c in keep]
    T = arr.shape[2]
    out = np.zeros((T, 1 + len(idx)))
    out[:, 0] = np.arange(1, T + 1)
    for j, ci in enumerate(idx):
        out[:, j + 1] = arr[row, ci, :]
    bus_no = int(arr[row, 0, 0])
    return f"{which} {bus_no} 시간별", ["Time[h]"] + keep, out


def _tab_base(text: str) -> str:
    """탭 이름에서 건수를 뗀다 — "점검 (3)" 은 "점검" 과 같은 탭이다.

    🚨 **꼬리가 두 꼴이다** (2026-09-08 점검 i35). 「계통 데이터」는 `(1)` 이
       무엇의 수인지 안 보여 `· 바꾼 것 1` 로 바꿨는데, 여기가 ` (` 만 떼고 있어
       그 탭이 통째로 «다른 탭» 이 됐다 — 조건을 하나 바꿀 때마다 화면이 첫 표로
       튕겼다(`test_tab_keeps` 5건이 잡았다). 둘 다 뗀다.
    """
    return text.split(" (")[0].split(" · ")[0].strip()


def real_tables(sol, mode, t, show_vsc):
    """(탭이름, 열이름들, 값행렬) 목록 — 실제 결과에서."""
    out = []
    if mode == "다이나믹":
        label, cols, arr = dynamic_table(sol, t)   # t 자리에 bus_row가 온다
        if arr.size:
            out.append((label, cols, arr))
    for which, label in [("AC", "AC 결과"), ("DC", "DC 결과"),
                         ("Branch", "선로 조류")]:
        arr = sol.at(which, t)
        if arr.size:
            out.append((label, sol.cols(which), arr))
    if mode == "다이나믹" and sol.loss.size:
        out.append(("손실", sol.cols("Loss"), sol.loss))
    if show_vsc:
        # 🚨 여태 `VSC 버스` 하나만 만들어서, `TABLE_SPECS` 에 적힌 나머지 둘이
        #    **탭조차 안 생겼다** (2026-09-08 점검 i24). 엔진은 셋 다 준다.
        for key, label in (("VSC_bus", "VSC 버스"),
                           ("VSC_grid", "VSC 그리드전력"),
                           ("VSC_power", "VSC 손실")):
            arr = getattr(sol, key, None)
            if arr is not None and arr.size:
                out.append((label, sol.cols(key), arr))
    return out


# 🚨 **항목 목록은 `compare_items.py` 가 갖는다** (2026-08-27). 여기엔 이름과
#    「늘 보이나」 두 값밖에 못 담아서, 어느 표 어느 열인지가 코드 세 군데에 글자로
#    흩어져 있었다. 늘리려면 그 셋을 다 고쳐야 했다 — 그래서 넷에서 멈춰 있었다.
COMPARE_ITEMS = [(s[0], s[6] == "all") for s in CI.SPECS]


def fake(col, row):
    random.seed(col * 97 + row * 31)
    if col == 0:
        return str(row + 1)
    return f"{random.uniform(0.94, 1.06):.4f}" if col == 1 else \
           f"{random.uniform(-8, 8):.2f}"


def hline_soft(c):
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color:{c['border']};background:{c['border']};max-height:1px;")
    return f


def _clear_scroll(w, vbar=True):
    """바탕을 안 칠하는 스크롤 상자 — 판 위에 얹어도 뒤가 그대로 보인다 (2026-11-15).

    창이 작을 때 안의 것이 창 최소 크기를 정하지 않게 담는 데 쓴다(사이드바 · 개요 · 시작 화면).
    """
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    if not vbar:
        sa.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setStyleSheet("QScrollArea { background:transparent; border:none; }")
    sa.viewport().setAutoFillBackground(False)
    sa.setWidget(w)
    w.setAutoFillBackground(False)
    sa.setMinimumHeight(0)
    return sa


def _scrollable(page):
    """카드를 세로로 쌓은 화면을 **스크롤에 담는다**.

    담지 않으면 그 화면의 키가 곧 창의 최소 높이가 되어, 화면보다 큰 창이
    만들어지고 **아래가 잘린 채 줄일 수도 없다**(2026-08-13 실측: 점검 탭 490px
    + 그래프 470px 로 창 최소 높이가 1201px 이었다).
    """
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    sa.setWidget(page)
    sa.setMinimumHeight(0)
    return sa


# ─────────────────────────────────────────── 조각
class _TintDelegate(QStyledItemDelegate):
    """칸에 준 바탕색(BackgroundRole)을 QSS 보다 먼저 칠한다 (앱 2.3 · 2026-11-02).

    🚨 `QTableWidget::item` 에 QSS 를 주면 Qt 가 `setBackground` 를 안 칠한다 —
       위반 행 옅은 빨강 바탕이 안 보였다. 대리자가 직접 칠한다. 칸 사이 틈이
       남지 않게 2px 씩 넓혀 칠하므로 색은 반투명이 아니라 불투명으로 준다.
    """

    def paint(self, p, opt, idx):
        bg = idx.data(Qt.BackgroundRole)
        if bg is not None:
            p.fillRect(opt.rect.adjusted(-2, 0, 2, 0), bg)
        super().paint(p, opt, idx)


class NumItem(QTableWidgetItem):
    """숫자로 견주는 표 칸 (2026-08-18).

    `QTableWidgetItem` 은 **보이는 글자로** 견준다. 그대로 정렬하면 버스가
    1 · 10 · 100 · 11 · 2 … 로 늘어서고, 전압도 `1.0993` 이 `0.983` 보다 앞선다.
    ⇒ 원래 숫자를 들고 있다가 그것으로 견준다.
    """

    __slots__ = ("_v",)

    def __init__(self, text, value):
        super().__init__(text)
        self._v = float(value)

    def __lt__(self, other):
        ov = getattr(other, "_v", None)
        if ov is None:
            return super().__lt__(other)
        a, b = self._v, ov
        if a != a:            # NaN 은 맨 뒤로 — 위로 올라오면 표가 못 쓰게 된다
            return False
        if b != b:
            return True
        return a < b


class _ClickLabel(QLabel):
    """누르면 알려 주는 라벨.

    한 번 = 그 시나리오로 가기 · 두 번 = 이름 고치기.
    (2026-08-15에 한 번 누르기를 더했다 — [결과 보기] 단추를 없애고 이름이 그 일을 맡는다.
     단추 하나가 줄 높이를 42px 로 만들어 목록이 자리를 크게 먹고 있었다.)
    """

    double_clicked = Signal(object)
    clicked = Signal(object)

    def mouseReleaseEvent(self, ev):
        # 🚨 두 번 누르기와 안 부딪히게 — Qt 는 두 번 누를 때도 뗌을 먼저 보낸다.
        #    잠깐 기다렸다가 그 사이에 두 번째가 안 오면 그때 한 번으로 친다.
        self._pending = getattr(self, "_pending", None) or QTimer(self)
        self._pending.setSingleShot(True)
        try:
            self._pending.timeout.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._pending.timeout.connect(lambda: self.clicked.emit(self))
        self._pending.start(QApplication.doubleClickInterval())

    def mouseDoubleClickEvent(self, ev):
        if getattr(self, "_pending", None) is not None:
            self._pending.stop()             # 한 번 누르기로 새지 않게
        self.double_clicked.emit(self)


class Card(QFrame):
    def __init__(self, c):
        super().__init__()
        self.setObjectName("card")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(14, 12, 14, 14)
        self.v.setSpacing(9)


class PlotBox(QFrame):
    """그래프 자리 (실제로 안 그림)."""

    def __init__(self, name, c):
        super().__init__()
        self.setObjectName("plot")
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        t = QLabel(name)
        t.setStyleSheet(f"color:{c['text']};font-size:14px;font-weight:600;")
        v.addWidget(t)
        v.addStretch()
        m = QLabel("〔 그래프 자리 〕")
        m.setAlignment(Qt.AlignCenter)
        m.setStyleSheet(f"color:{c['muted']};font-size:16px;")
        v.addWidget(m)
        v.addStretch()


# ─────────────────────────────────────────── 창들
class AboutDialog(QDialog):
    """판·저작권·사용 조건 (2026-08-19, §7 6단계).

    🚨 **꾸미려고 만든 창이 아니다.** MathWorks 소프트웨어 라이선스 계약이
    *"About Box, 또는 그와 비슷한 눈에 띄는 자리"* 와 함께 배포하는 문서에
    저작권 고지를 넣으라고 요구한다(`license_agreement.txt` 205–210행).
    그 고지가 **아래 `MATHWORKS` 한 줄**이다 — **지우면 배포 조건 위반**이다.
    """

    # 지우지 말 것 — 위 설명 참조. 연도는 엔진을 만든 MATLAB 판을 따른다.
    MATHWORKS = "MATLAB®. © 1984-2024 The MathWorks, Inc."

    def __init__(self, parent, c):
        super().__init__(parent)
        self.setWindowTitle("UNIGRID 정보")
        self.setMinimumWidth(520)
        self.setStyleSheet(parent.styleSheet())
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(11)

        t = QLabel("UNIGRID")
        t.setStyleSheet(f"color:{c['text']};font-size:23px;font-weight:600;"
                        "letter-spacing:1.4px;")
        v.addWidget(t)

        sub = QLabel(f"AC/DC 조류계산  ·  v{VERSION}")
        sub.setStyleSheet(f"color:{c['muted']};font-size:13px;")
        v.addWidget(sub)

        # ── 무엇으로 만들어졌나 ──
        rows = [("계산 엔진", f"MATLAB Compiler · Runtime {engine_path.REQUIRED_RELEASE}"),
                ("화면", f"PySide6 (Qt) · Python {sys.version_info.major}."
                         f"{sys.version_info.minor}"),
                ("만든 곳", "중앙대학교 GML")]
        box = QFrame()
        box.setObjectName("card")
        g = QVBoxLayout(box)
        g.setContentsMargins(14, 12, 14, 12)
        g.setSpacing(6)
        for k, val in rows:
            r = QHBoxLayout()
            r.setSpacing(10)
            a = QLabel(k)
            a.setFixedWidth(70)
            a.setStyleSheet(f"color:{c['muted']};font-size:13px;")
            b = QLabel(val)
            b.setStyleSheet(f"color:{c['text']};font-size:13px;")
            b.setTextInteractionFlags(Qt.TextSelectableByMouse)
            r.addWidget(a)
            r.addWidget(b)
            r.addStretch()
            g.addLayout(r)
        v.addWidget(box)

        # ── 저작권 고지 (배포 조건) ──
        note = QLabel(self.MATHWORKS)
        note.setStyleSheet(f"color:{c['text']};font-size:13px;font-weight:600;")
        note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(note)

        eula = paths.files_root() / "EULA.txt"
        tail = QLabel(
            "MATLAB 은 The MathWorks, Inc. 의 등록상표입니다.\n"
            "MATLAB Runtime 의 사용 조건은 그 설치 폴더의 MCR_license.txt 를 따릅니다.\n"
            + ("이 프로그램의 사용 조건은 함께 들어 있는 EULA.txt 에 있습니다."
               if eula.is_file() else ""))
        tail.setStyleSheet(f"color:{c['muted']};font-size:12px;line-height:150%;")
        tail.setWordWrap(True)
        v.addWidget(tail)

        v.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        if eula.is_file():
            b_e = QPushButton("사용 조건 보기")
            b_e.clicked.connect(lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(eula))))
            row.addWidget(b_e)
        ok = QPushButton("닫기")
        ok.setObjectName("accent")
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        v.addLayout(row)


class OpenDialog(QDialog):
    """[불러오기] 를 누르면 먼저 뜨는 창 — **어떤 형식인가** (2026-09-08 점검 i05).

    예전에는 바로 파일 고르기 창이 떴고 거르개가 `*.xlsx *.m *.raw` 하나였다.
    🚨 그러면 **MatACDC 를 열 길이 없다** — MatACDC 계통은 AC·DC 두 파일이고 둘 다
       확장자가 `.m` 이라, AC 파일 하나만 고르면 MATPOWER 로 읽혀
       「MATPOWER 파일에서 mpc.baseMVA 를 찾을 수 없습니다」 로 끝났다.
       (사용자 점검 i05: *"차라리 «불러오기»를 누르면 형식을 고르는 버튼이 있어야
        안 헷갈릴 것 같아"*)
    꼴은 「엑셀로 만들기」 창(`ConvertDialog`)과 같다 — 같은 것을 묻는 창 둘이
    서로 다른 꼴이면 그것대로 헷갈린다. 한 번 눌러 고른다(라디오+[다음] 이 아니라).
    """

    def __init__(self, parent, c):
        super().__init__(parent)
        self.setWindowTitle("계통 파일 불러오기")
        self.setMinimumWidth(520)
        self.setStyleSheet(parent.styleSheet())
        self.picked = None            # ("xlsx"|"m"|"raw"|"matacdc")
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(11)
        t = QLabel("어떤 형식입니까")
        t.setStyleSheet(f"color:{c['text']};font-size:18px;font-weight:600;")
        v.addWidget(t)
        for kind, name, desc in [
                ("xlsx",    "UNIGRID 엑셀  (.xlsx)", "이 앱이 쓰는 형식 · AC/DC 다 담는다"),
                ("m",       "MATPOWER  (.m)",        "AC 계통"),
                ("raw",     "PSS/E  (.raw)",         "AC 계통 · 3권선 포함"),
                ("matacdc", "MatACDC  (.m 두 파일)", "AC/DC 혼합 계통 · AC 와 DC 를 차례로 고른다")]:
            b = QPushButton(f"{name}\n{desc}")
            b.setMinimumHeight(60)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, k=kind: self._take(k))
            v.addWidget(b)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        v.addLayout(row)

    def _take(self, kind):
        self.picked = kind
        self.accept()


class _GripHandle(QSplitterHandle):
    """가운데에 **잡는 표시**를 그리는 나눔 손잡이 (2026-09-08).

    QSS 로는 띠 색과 테두리까지만 되고 **가운데 무늬는 못 그린다**. 그런데 색만
    바꾸면 「선이 하나 있네」로 끝나고, 그것이 *끌 수 있는 것* 인 줄은 모른다.
    ⇒ 가운데에 짧은 가로 막대 셋을 겹쳐 그린다 — 어느 앱에서나 「여기를 잡아라」로
      읽히는 모양이다. 마우스를 올리면 강조색으로 바뀐다.
    """

    def __init__(self, orientation, parent, c):
        super().__init__(orientation, parent)
        self.c = c
        self._hot = False
        self.setCursor(Qt.SplitVCursor if orientation == Qt.Vertical
                       else Qt.SplitHCursor)
        self.setToolTip("위아래로 끌면 그래프와 표의 크기가 바뀝니다")

    def enterEvent(self, ev):
        self._hot = True
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hot = False
        self.update()
        super().leaveEvent(ev)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self.orientation() != Qt.Vertical:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.c["accent"] if self._hot else self.c["border"]))
        w = 56.0 if self._hot else 40.0
        p.drawRoundedRect(QRectF(self.width() / 2 - w / 2, self.height() / 2 - 2.5, w, 5), 2.5, 2.5)
        p.end()


class _GripSplitter(QSplitter):
    """손잡이를 `_GripHandle` 로 만드는 나눔 상자."""

    def __init__(self, orientation, c):
        super().__init__(orientation)
        self._c = c

    def createHandle(self):
        return _GripHandle(self.orientation(), self, self._c)


class ConvertDialog(QDialog):
    def __init__(self, parent, c):
        super().__init__(parent)
        self.setWindowTitle("UNIGRID 엑셀로 만들기")
        self.setMinimumWidth(520)
        self.setStyleSheet(parent.styleSheet())
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(11)
        t = QLabel("UNIGRID 엑셀로 만들기")
        t.setStyleSheet(f"color:{c['text']};font-size:18px;font-weight:600;")
        v.addWidget(t)
        s = QLabel("계산만 하려면 이 창은 필요 없습니다 — 파일을 바로 열면 됩니다.\n"
                   "여기서 만든 엑셀에 DC 버스·변환기·24시간 부하를 직접 넣어\n"
                   "AC/DC 혼합 케이스를 만들 수 있습니다.")
        s.setStyleSheet(f"color:{c['muted']};font-size:13px;line-height:150%;")
        v.addWidget(s)
        s2 = QLabel("어떤 형식에서 만들까요?")
        s2.setStyleSheet(f"color:{c['text']};font-size:14px;font-weight:600;")
        v.addWidget(s2)
        for name, desc, patt in [
                ("MATPOWER  (.m)", "AC 계통", "MATPOWER 케이스 (*.m)"),
                ("PSS/E  (.raw)", "AC 계통 · 3권선 포함", "PSS/E 계통 (*.raw *.RAW)"),
                ("MatACDC", "AC/DC 혼합 계통", "")]:
            b = QPushButton(f"{name}\n{desc}")
            b.setMinimumHeight(64)
            b.clicked.connect(lambda _, n=name, p=patt: self._pick(n, p))
            v.addWidget(b)
        note = QLabel("고르면 파일 선택 창 → 변환 → 저장 위치를 묻습니다")
        note.setStyleSheet(f"color:{c['muted']};font-size:13px;")
        v.addWidget(note)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("닫기")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        v.addLayout(row)

    def _pick(self, name, patt):
        """고른 형식의 파일을 골라 → 읽어서 → v2 엑셀로 저장한다 (PDR §7 3단계 X1 (b))."""
        if not patt:
            # MatACDC 는 `.m` 을 **두 개** 받는다 (AC 계통 + DC 계통).
            # 🚨 순서가 중요하다 — 두 파일 다 확장자가 `.m` 이라 바꿔 고르면
            #    "busdc 를 찾을 수 없습니다" 같은 엉뚱한 말만 나온다. 먼저 알려 준다.
            if QMessageBox.question(
                    self, "파일을 두 개 고릅니다",
                    "MatACDC 계통은 파일이 둘로 나뉘어 있습니다.\n\n"
                    "    첫 번째 — AC 계통 (MATPOWER, bus·gen·branch)\n"
                    "    두 번째 — DC 계통 (MatACDC, busdc·convdc·branchdc)\n\n"
                    "이 순서로 고르셔야 합니다. 둘 다 확장자가 .m 이라\n"
                    "바꿔 고르면 읽지 못합니다.\n\n계속할까요?",
                    QMessageBox.Ok | QMessageBox.Cancel) != QMessageBox.Ok:
                return
            ac, _ = QFileDialog.getOpenFileName(
                self, "1/2 — 먼저 AC 계통 파일 (MATPOWER .m)", "", "MATPOWER 케이스 (*.m)")
            if not ac:
                return
            dc, _ = QFileDialog.getOpenFileName(
                self, "2/2 — 이제 DC 계통 파일 (MatACDC .m)", str(Path(ac).parent),
                "MatACDC 케이스 (*.m)")
            if not dc:
                return
            src = Path(ac)
            try:
                import unigrid_convert
                case = unigrid_convert.matacdc_to_case(ac, dc)
            except Exception as exc:
                QMessageBox.warning(self, "읽지 못했습니다",
                                    f"MatACDC 케이스를 읽지 못했습니다.\n\n{exc}")
                return
        else:
            src, _ = QFileDialog.getOpenFileName(self, f"{name} 파일 고르기", "", patt)
            if not src:
                return
            src = Path(src)
            try:
                case = load_case(str(src))
            except Exception as exc:
                QMessageBox.warning(self, "읽지 못했습니다",
                                    f"{src.name} 을 읽지 못했습니다.\n\n{exc}")
                return

        out, _ = QFileDialog.getSaveFileName(
            self, "UNIGRID 엑셀로 저장", str(src.with_name(f"{src.stem}_unigrid.xlsx")),
            "UNIGRID 케이스 (*.xlsx)")
        if not out:
            return

        try:
            import write_v2
            saved = write_v2.write_case(case, out)
        except Exception as exc:
            QMessageBox.warning(self, "저장하지 못했습니다", str(exc))
            return

        n_ac = len(case.tables.get("AC_Bus_dat", []))
        n_dc = len(case.tables.get("DC_Bus_dat", []))
        QMessageBox.information(
            self, "만들었습니다",
            f"{saved.name}\n\nAC 버스 {n_ac}개" + (f" · DC 버스 {n_dc}개" if n_dc else "") +
            "\n\n이 파일을 그대로 불러와 계산할 수 있습니다.\n"
            "DC 버스·변환기·24시간 부하는 엑셀에서 직접 채워 넣으세요.")
        self.accept()


class ImportDialog(QDialog):
    def __init__(self, parent, c):
        super().__init__(parent)
        self.setWindowTitle("불러오기")
        self.setMinimumWidth(560)
        self.setStyleSheet(parent.styleSheet())
        self.chosen = None
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(11)
        t = QLabel("불러오기 — 계통 파일 선택")
        t.setStyleSheet(f"color:{c['text']};font-size:18px;font-weight:600;")
        v.addWidget(t)

        drop = QFrame()
        drop.setObjectName("plot")
        drop.setMinimumHeight(90)
        dv = QVBoxLayout(drop)
        d1 = QLabel("여기로 파일을 끌어다 놓거나")
        d1.setAlignment(Qt.AlignCenter)
        d1.setStyleSheet(f"color:{c['text']};font-size:16px;font-weight:600;")
        d2 = QLabel(".xlsx  ·  .m  ·  .raw     (형식은 자동으로 알아냄)")
        d2.setAlignment(Qt.AlignCenter)
        d2.setStyleSheet(f"color:{c['muted']};font-size:13px;")
        dv.addWidget(d1)
        dv.addWidget(d2)
        v.addWidget(drop)

        s = QLabel("최근에 연 파일")
        s.setStyleSheet(f"color:{c['muted']};font-size:14px;")
        v.addWidget(s)
        for f, info in [("ACDC_CIGRE_MVACMVDCLVDC.xlsx", "AC/DC 혼합 · AC 14 / DC 11"),
                        ("ACDC_71bus_3IC_parallel.xlsx", "AC/DC 혼합 · AC 38 / DC 33"),
                        ("matpower_ieee14.m", "AC only · 14")]:
            b = QPushButton(f"{f}\n{info}")
            b.setMinimumHeight(58)
            b.clicked.connect(lambda _, n=f, i=info: self._choose(n, i))
            v.addWidget(b)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        pick = QPushButton("파일 찾기")
        pick.setObjectName("primary")
        pick.clicked.connect(lambda: self._choose("ACDC_CIGRE_MVACMVDCLVDC.xlsx",
                                                  "AC/DC 혼합 · AC 14 / DC 11"))
        row.addWidget(cancel)
        row.addWidget(pick)
        v.addLayout(row)

    def _choose(self, name, info):
        self.chosen = (name, info)
        self.accept()


class ExportDialog(QDialog):
    """내보내기 — 무엇을 어디에 저장할지 고르고 **실제로 파일을 쓴다**.

    파일 이름·시트 구성은 원본 MATLAB 앱과 똑같이 맞췄다(exporter.py 참고).
    원본은 묻지 않고 전부 저장했지만, 24시간 × 파일 4개는 시간이 걸려서
    고를 수 있게 뒀다.
    """

    def __init__(self, parent, c, mode, picked_items):
        super().__init__(parent)
        self.setWindowTitle("내보내기")
        self.setMinimumWidth(520)
        self.setStyleSheet(parent.styleSheet())
        self.win, self.c, self.mode = parent, c, mode
        self.sol = getattr(parent, "sol", None)
        self.tabs, self.compares = [], []       # (이름, 체크박스)
        self.folder = exporter.default_folder(
            self.sol.case_name if self.sol is not None else "결과")

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(9)

        if self.sol is None:
            t = QLabel("내보내기")
            t.setStyleSheet(f"color:{c['text']};font-size:18px;font-weight:600;")
            v.addWidget(t)
            n = QLabel("저장할 결과가 없습니다. 먼저 케이스를 불러와 계산하세요.")
            n.setStyleSheet(f"color:{c['muted']};font-size:14px;")
            v.addWidget(n)
        elif mode == "비교":
            t = QLabel("내보내기 — 비교 표만 (그림은 여기서 저장하지 않습니다)")
            t.setWordWrap(True)
            t.setStyleSheet(f"color:{c['text']};font-size:17px;font-weight:600;")
            v.addWidget(t)
            # 여기서는 **표만** 저장한다. 비교 그림은 왼쪽 아래
            # "이 비교 그림 저장" 버튼이 따로 맡는다(사용자가 그렇게 나누기로 함).
            n = QLabel("여기서는 비교 표를 엑셀로 저장합니다. "
                       "그림은 왼쪽 아래 “이 비교 그림 저장” 버튼을 쓰세요.")
            n.setWordWrap(True)
            n.setStyleSheet(f"color:{c['muted']};font-size:13px;")
            v.addWidget(n)
            for name, always in COMPARE_ITEMS:
                on = name in picked_items and (
                    always or parent.compare_axis == "시간끼리")
                cb = QCheckBox(name if on else f"{name}   (화면에서 안 고름)")
                cb.setChecked(on)
                cb.setEnabled(on)
                v.addWidget(cb)
                self.compares.append((name, cb))
        else:
            t = QLabel("내보내기 — 무엇을 저장할까요?")
            t.setStyleSheet(f"color:{c['text']};font-size:18px;font-weight:600;")
            v.addWidget(t)
            l1 = QLabel("엑셀   (한 시간에 시트 하나)")
            l1.setStyleSheet(f"color:{c['muted']};font-size:14px;")
            v.addWidget(l1)
            for name in exporter.table_names(self.sol):
                fname = exporter.TABLE_FILES[name][1]
                cb = QCheckBox(f"{name}     {fname}")
                cb.setChecked(True)
                v.addWidget(cb)
                self.tabs.append((name, cb))
            l2 = QLabel("그림   (PNG · PDF 둘 다)")
            l2.setStyleSheet(f"color:{c['muted']};font-size:14px;")
            v.addWidget(l2)
            for tab, fname in exporter.figure_names(self.sol, mode):
                # 🚨 예전에는 그래프가 접혀 있으면 이 칸을 **꺼서 못 고르게** 했다
                #    (2026-08-18 삭제). 그런데 `exporter.save_figures` 는 화면의
                #    그래프를 쓰지 않고 **결과에서 새로 그린다** — 접혀 있어도 그림 8개가
                #    멀쩡히 나오는 것을 실측으로 확인했다. 막을 까닭이 없었다.
                #    ⚠️ 게다가 **저절로 접혔을 때도** 막혔다 — 선로 하나 껐을 뿐인데
                #       *"지금은 숫자 모드라 그림을 저장할 수 없습니다"* 가 떴다.
                #       고른 적 없는 모드를 이유로 대는 셈이었다.
                cb = QCheckBox(f"{tab}     {fname}.png / .pdf")
                cb.setChecked(True)
                v.addWidget(cb)
                self.tabs.append((tab, cb))

        path = QFrame()
        path.setObjectName("plot")
        pv = QHBoxLayout(path)
        pv.setContentsMargins(12, 8, 12, 8)
        self.path_label = QLabel()
        self.path_label.setStyleSheet(f"color:{c['text']};font-size:13px;")
        self._show_folder()
        pv.addWidget(self.path_label)
        pv.addStretch()
        pb = QPushButton("바꾸기")
        pb.clicked.connect(self.pick_folder)
        pv.addWidget(pb)
        v.addWidget(path)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        self.save_btn = QPushButton("저장")
        self.save_btn.setObjectName("primary")
        self.save_btn.setEnabled(self.sol is not None)
        self.save_btn.clicked.connect(self.do_save)
        row.addWidget(cancel)
        row.addWidget(self.save_btn)
        v.addLayout(row)

    # ── 저장 위치 ──
    def _show_folder(self):
        """길면 홈 폴더를 ~ 로 줄여 보여 준다."""
        s = str(self.folder)
        home = str(Path.home())
        if s.startswith(home):
            s = "~" + s[len(home):]
        self.path_label.setText(f"저장 위치:   {s}")

    def pick_folder(self):
        got = QFileDialog.getExistingDirectory(
            self, "저장할 폴더를 고르세요", str(self.folder.parent))
        if got:
            self.folder = Path(got)
            self._show_folder()

    # ── 실제 저장 ──
    def do_save(self):
        picked = {n for n, cb in self.tabs + self.compares if cb.isChecked()}
        if not picked:
            QMessageBox.information(self, "내보내기", "저장할 항목을 하나 이상 고르세요.")
            return
        self.save_btn.setEnabled(False)
        bar = QProgressDialog("저장하는 중…", None, 0, len(picked), self)
        bar.setWindowTitle("내보내기")
        bar.setWindowModality(Qt.WindowModal)
        bar.setCancelButton(None)
        bar.setMinimumDuration(0)
        done = [0]

        def step(name):
            done[0] += 1
            bar.setValue(min(done[0], len(picked)))
            bar.setLabelText(f"{name} 저장했습니다")
            QApplication.processEvents()

        try:
            files = self._write(picked, step)
        except Exception as exc:            # 저장 실패를 조용히 넘기지 않는다
            bar.close()
            self.save_btn.setEnabled(True)
            QMessageBox.critical(self, "내보내기 실패", f"{exc}")
            return
        bar.close()
        if not files:
            self.save_btn.setEnabled(True)
            QMessageBox.information(self, "내보내기", "저장된 것이 없습니다.")
            return
        names = "\n".join(f"  · {p.name}" for p in files[:12])
        more = f"\n  … 그 밖에 {len(files) - 12}개" if len(files) > 12 else ""
        QMessageBox.information(
            self, "내보내기 완료",
            f"{len(files)}개 파일을 저장했습니다.\n\n{self.folder}\n\n{names}{more}")
        self.accept()

    def _write(self, picked, step):
        """고른 것을 실제로 쓴다. 돌려주는 값은 만들어진 파일 목록."""
        if self.mode == "비교":
            return self._write_compare(picked, step)
        files = []
        tables = [n for n in exporter.table_names(self.sol) if n in picked]
        if tables:
            files += exporter.save_tables(self.sol, self.folder, tables, step)
        figs = {t for t, _ in exporter.figure_names(self.sol, self.mode)} & picked
        if figs:
            files += exporter.save_figures(
                self.c, self.sol, self.mode, self.folder, figs,
                self.win.t, self.win.bus_row, step)
        return files

    def _write_compare(self, picked, step):
        """비교 표를 엑셀 한 권에 — 항목마다 시트 하나."""
        from openpyxl import Workbook
        targets = [t.strip() for t in self.win.compare_targets.split(",")
                   if t.strip()]
        axis = "Bus" if self.win.compare_axis == "버스끼리" else "Time"
        wb = Workbook()
        wb.remove(wb.active)
        for name, _ in self.compares:
            if name not in picked:
                continue
            got = self.win.compare_rows(name, targets)
            if got is None:
                continue
            head, rows = got
            ws = wb.create_sheet(name)
            ws.append([str(h) for h in head])
            for r in rows:
                ws.append([float(x) for x in r])
            step(name)
        if not wb.sheetnames:
            return []
        self.folder.mkdir(parents=True, exist_ok=True)
        p = self.folder / f"Comparison by {axis}.xlsx"
        wb.save(p)
        return [p]


# ─────────────────────────────────────────── 본 창
DROP_EXT = {".xlsx", ".m", ".raw"}


def dropped_path(event):
    """끌어다 놓은 것 중 우리가 읽을 수 있는 첫 파일 (없으면 None)."""
    md = event.mimeData()
    if not md.hasUrls():
        return None
    for url in md.urls():
        p = url.toLocalFile()
        if p and Path(p).suffix.lower() in DROP_EXT:
            return p
    return None


# ─────────────────────────────────────────── 유리 바탕
# 🍎 **애플 글래스모피즘** (2026-09-08 사용자: *"애플의 글래스모피즘을 하고싶다"*).
#
# 유리는 **뒤에 무언가 비쳐야** 유리로 보인다. 애플 앱은 벽지가 비치지만, 창을
# 반투명으로 만들면 ⓐ맥에만 되고(윈도우 설치본에서 안 먹는다) ⓑ화면 기록 권한이
# 없으면 캡처로 확인할 수도 없다. ⇒ **비칠 것을 앱 안에 만든다** — 바탕에 부드러운
# 색 얼룩을 깔고 그 위 카드를 반투명으로 두면, 카드가 뒤 색을 머금는다.
# 어디서나 같게 보이고 `grab()` 으로 찍힌다.
GLASS_BLOBS = [          # (x비율, y비율, 반지름비율, 밝은색, 어두운색)
    # 🚨 **색을 뺐다** (2026-09-09 사용자: *"배경을 저렇게 무지개로 하면 너무
    #    안이쁜데"* → 색 수를 줄인 안 넷 중 **「나 · 색 없이 밝기만」** 확정).
    #    앞서는 파랑·분홍·보라·초록 넷이라 판 안이 무지개로 보였다. 이제 얼룩은
    #    **밝기 차이일 뿐** 색이 없다.
    #    ⚠️ 대가 — 채도 증폭(`GLASS_SAT`)이 무채색에서는 아무 일도 안 한다.
    #       그래서 유리는 **명도 대비**(`GLASS_CON`)로 세운다.
    #    ⚠️ 얼룩은 **바탕 반대쪽으로 기운다** — 밝은 화면에서는 바탕(#f2f2f7)보다
    #       어둡게, 어두운 화면에서는 바탕(#1c1c1e)보다 밝게. 같은 쪽으로 두면
    #       (흰 바탕에 흰 얼룩) 판 안팎이 구별되지 않아 유리가 안 보인다.
    (0.34, 0.14, 0.46, "#e4e4ec", "#37373d"),
    (0.88, 0.10, 0.42, "#d6d6e0", "#26262b"),
    (0.46, 0.88, 0.50, "#e8e8ef", "#323238"),
    (0.92, 0.72, 0.44, "#d0d0da", "#202024"),
]


_DITHER = None


def dither_brush():
    """🚨 **띠(banding) 를 깨는 미세 노이즈** (2026-09-09).

    옅은 그라디언트는 8비트에서 계단이 진다. 얼룩을 바탕 반대쪽으로 기울이고
    명도를 2.4배 벌리자 배경에 **동심원 띠**가 눈에 띄게 드러났다(실측). 색 단계를
    늘릴 방법이 없으니 — 그래픽 카드가 8비트다 — 경계를 **흩뜨린다.** 사진·영화가
    쓰는 것과 같은 수법이고, 알파 7 이면 띠만 깨지고 노이즈 자체는 안 보인다.
    """
    global _DITHER
    if _DITHER is None:
        import random
        n = 64
        img = QImage(n, n, QImage.Format_ARGB32)
        rnd = random.Random(7)              # 늘 같은 무늬 — 다시 그려도 안 흔들린다
        for y in range(n):
            for x in range(n):
                v = rnd.randint(0, 255)
                img.setPixelColor(x, y, QColor(v, v, v, 7))
        _DITHER = QBrush(img)               # 텍스처 브러시 — 저절로 이어 붙는다
    return _DITHER


class Ground(QWidget):
    """유리가 비출 바탕 — 옅은 바탕색 위에 부드러운 색 얼룩.

    얼룩 진하기는 `alpha` 하나로 조절한다(밝은 화면 0.34 · 어두운 화면 0.30).
    ⚠️ 얼룩을 진하게 하면 그 위 **글자 대비가 떨어진다** — 08-27 에 유리를 붙였다
       되돌린 까닭이 그것이다(사이드바 글자가 1.31:1 까지 떨어졌다). 카드를
       반투명 흰색으로 덮어 글자 자리는 밝게 유지한다.
    """

    # 🚨 **얼룩은 «있는 줄 모를 만큼» 옅다** (2026-09-08 사용자: *"왜 배경이 꼭
    #    저렇게 무지개 같은거여야해"* → 넷을 견줘 「아주 옅게」 확정).
    #    0.55 로 깔았더니 배경이 무지개가 되어 **계통 그림의 AC 빨강·DC 파랑과
    #    색이 경쟁**했다. 유리가 «비칠 것» 만 있으면 되지 배경이 주인공일 이유는 없다.
    #    ⚠️ 어두운 화면에서는 같은 값이 더 안 보인다 — 한 단 올려 준다.
    ALPHA_LIGHT = 0.16
    ALPHA_DARK = 0.24

    def __init__(self, c, dark, alpha=None):
        super().__init__()
        if alpha is None:
            alpha = self.ALPHA_DARK if dark else self.ALPHA_LIGHT
        self.c, self.dark, self.alpha = c, dark, alpha

    # 유리 판이 «비추어 쓸» 그림. 창 크기가 바뀔 때만 다시 만든다.
    _img = None
    _frost = None
    _key = None
    _seed = None            # 채도를 올린 **작은** 얼룩 — 창 크기와 무관하다

    def _draw(self, p, W, H, dither=True):
        if FLAT_CARDS:                   # 2026-11-15 — 평평한 바탕 한 색(얼룩 · 디더 무늬를 걷었다)
            p.fillRect(0, 0, W, H, QColor(self.c["bg"]))
            return
        base = QColor(self.c["bg"])
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0.0, base if not self.dark else base.lighter(115))
        g.setColorAt(1.0, base.darker(103) if not self.dark else base)
        p.fillRect(0, 0, W, H, g)
        for fx, fy, fr, light, dark in GLASS_BLOBS:
            col = QColor(dark if self.dark else light)
            r = fr * max(W, H)          # 긴 변 기준 — 넓은 창에서도 색이 돈다
            rg = QRadialGradient(QPointF(fx * W, fy * H), r)
            col.setAlphaF(self.alpha)
            rg.setColorAt(0.0, col)
            fade = QColor(col)
            fade.setAlphaF(0.0)
            rg.setColorAt(1.0, fade)
            p.setBrush(rg)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(fx * W, fy * H), r, r)
        # 🚨 **작은 seed 에는 얹지 않는다** — seed(168×126)를 창 폭으로 늘리면
        #    노이즈 한 점이 일곱 점짜리 덩어리가 되어 판 안이 오돌토돌해진다(실측).
        #    디더는 «원본 해상도로 그리는 바탕» 에만 뜻이 있다.
        if dither:
            p.fillRect(0, 0, W, H, dither_brush())

    # 채도를 올릴 작은 그림의 크기. 🚨 **창 크기와 무관하게 못 박는다** —
    # 픽셀을 파이썬으로 훑기 때문에, 창에 비례시키면 큰 화면에서 창을 끌 때마다
    # 수만 픽셀을 다시 훑어 버벅인다. 얼룩 위치는 비율(`fx*W`)이라 작은 격자에
    # 그려도 자리가 같고, 늘려 쓰면 어차피 흐려진다.
    SEED = (168, 126)

    def _make_seed(self):
        """🍎 **간유리** — 작은 격자에 얼룩을 그리고 **채도를 올린다**.

        애플 유리를 통과한 색은 바깥보다 진해 보인다. 이 «판 안이 판 밖보다
        진하다» 가 유리로 읽히게 하는 결정적인 한 가지다. 창 크기가 바뀌어도
        이 그림은 그대로 두고 늘려 쓴다.
        """
        w, h = self.SEED
        img = QImage(w, h, QImage.Format_RGB32)
        pp = QPainter(img)
        pp.setRenderHint(QPainter.Antialiasing)
        self._draw(pp, w, h, dither=False)
        pp.end()
        # 기준 밝기 — 얼룩이 없는 바탕색. 이 값을 축으로 밝기를 벌린다.
        pivot = QColor(self.c["bg"]).value()
        con = GLASS_CON_DARK if self.dark else GLASS_CON
        for y in range(h):
            for x in range(w):
                col = img.pixelColor(x, y)
                hu, sv, v, a = col.getHsv()
                v = int(pivot + (v - pivot) * con)
                col.setHsv(hu, min(255, int(sv * GLASS_SAT)),
                           max(0, min(255, v)), a)
                img.setPixelColor(x, y, col)
        self._seed = img

    def _build(self):
        """바탕 그림과 «간유리로 본 바탕» 을 한 벌 만든다."""
        W, H = max(1, self.width()), max(1, self.height())
        if self._key == (W, H):
            return
        self._key = (W, H)
        img = QImage(W, H, QImage.Format_RGB32)
        pp = QPainter(img)
        pp.setRenderHint(QPainter.Antialiasing)
        self._draw(pp, W, H)
        pp.end()
        self._img = img
        if self._seed is None:
            self._make_seed()
        self._frost = self._seed.scaled(W, H, Qt.IgnoreAspectRatio,
                                        Qt.SmoothTransformation)

    def frost(self):
        """유리 판이 잘라 쓸 «흐리고 진한 바탕»."""
        self._build()
        return self._frost

    def paintEvent(self, e):
        self._build()
        p = QPainter(self)
        p.drawImage(0, 0, self._img)


# 🍎 유리를 통과하면 뒤가 **바깥보다 또렷하다**. 이 둘이 1.0 이면 판 안팎이 같아
#    «유리» 가 아니라 «반투명 흰 판» 으로 보인다.
#    `GLASS_SAT` = 채도 증폭. 얼룩에 색이 있을 때만 듣는다.
#    `GLASS_CON` = **명도 대비 증폭**. 무채색 얼룩에서 유리를 세우는 것은 이쪽이다
#                  — 밝은 데는 더 밝게, 어두운 데는 더 어둡게 벌린다.
GLASS_SAT = 1.0
GLASS_CON = 2.4           # 밝은 화면
GLASS_CON_DARK = 1.3      # 어두운 화면 — 세게 벌리면 흐린 글자가 4.5:1 아래로 떨어진다


class GlassCard(QFrame):
    """🍎 **애플 유리 판** (2026-09-09).

    🚨 **Qt QSS 에는 `backdrop-filter` 가 없다.** 그래서 `background:rgba(...)` 로
       만든 판은 뒤가 «비치기만» 하고 **흐려지지 않는다** — 색유리이지 간유리가
       아니다. 게다가 알파 0.90 이면 뒤가 10%만 비쳐 그냥 흰 판이 된다
       (사용자 지적: *"유리 느낌이 안나는데?"*).

    ⇒ 판을 직접 그린다. 네 겹이다.

      1. **뒤 바탕을 흐리게 비춘다** — 조상 `Ground` 의 간유리 그림에서 내 자리를
         잘라 온다. 바깥보다 채도가 높아 판 안이 더 진하다.
      2. **틴트** — 흰빛(어두우면 회색)을 덮되 **위가 진하고 아래로 옅어진다**.
         유리의 두께감이 여기서 나온다.
      3. **가장자리 빛** — 위쪽 테두리는 밝고 아래로 갈수록 사라진다. 애플 유리의
         가장 알아보기 쉬운 표시다.
      4. 그림자는 밖에서 `float_panel` 이 건다.

    ⚠️ 뒤에 `Ground` 가 없으면(대화상자 등) 틴트만 그린다 — 그때는 옛 모습 그대로다.
    """

    def __init__(self, c, dark, radius=16, tint=None, parent=None):
        super().__init__(parent)
        self.c, self.dark, self.radius = c, dark, radius
        self._hot = False
        # 위·아래 틴트 진하기. 낮출수록 뒤가 많이 비친다.
        if tint is None:
            tint = (0.62, 0.40) if not dark else (0.60, 0.40)
        self.tint = tint

    def set_hot(self, on):
        """끌어온 파일이 위에 있을 때 — 파랗게 물든다."""
        if self._hot != on:
            self._hot = on
            self.update()

    def paintEvent(self, e):
        paint_glass(self, QPainter(self), self.rect(), self.radius,
                    self.c, self.dark, self.tint, self._hot)


FLAT_CARDS = True        # False 로 두면 옛 유리 판으로 돌아간다


def _ground_of(w):
    """조상 중 `Ground` 를 찾는다 — 유리가 비출 바탕."""
    w = w.parentWidget()
    while w is not None:
        if isinstance(w, Ground):
            return w
        w = w.parentWidget()
    return None


def paint_glass(w, p, rect, radius, c, dark, tint, hot=False):
    """유리 판 하나를 그린다 — 세 겹.

    ⚠️ `rect` 는 위젯 안의 **판 자리**다(탭 판은 탭 줄 아래만 판이다).
    """
    p.setRenderHint(QPainter.Antialiasing)
    R = float(radius)
    box = QRectF(rect.x() + 0.5, rect.y() + 0.5,
                 rect.width() - 1.0, rect.height() - 1.0)
    path = QPainterPath()
    path.addRoundedRect(box, R, R)
    # 🚨 2026-11-15 — 화면 꼴이 둘이었다(개요 = 흰 카드 · 나머지 = 유리 판). 개요 꼴 하나로 맞춘다:
    #    판은 `surface` 색으로 그냥 칠한다. 파일을 끌어 올 때의 물든 판(`hot`)만 옛 그리기를 쓴다.
    if FLAT_CARDS and not hot:
        p.setPen(QPen(QColor(c["border"]), 1))      # 흰 판 + 가는 테두리
        p.setBrush(QColor(c["surface"]))
        p.drawPath(path)
        return

    # 1) 뒤 바탕을 흐리게 비춘다
    g = _ground_of(w)
    if g is not None:
        frost = g.frost()
        if frost is not None:
            off = w.mapTo(g, QPoint(rect.x(), rect.y()))
            p.save()
            p.setClipPath(path)
            p.drawImage(rect.x(), rect.y(), frost, off.x(), off.y(),
                        rect.width(), rect.height())
            # ⚠️ 판 «안» 에는 디더를 안 얹는다 — 작은 그림을 크게 늘린 것이라
            #    보간으로 이미 부드럽고, 노이즈만 오돌토돌하게 도드라진다(실측).
            p.restore()

    # 2) 틴트 — 위가 진하고 아래로 옅어진다 (유리의 두께감)
    top, bot = tint
    if hot:
        t1 = QColor(c["accent"]); t1.setAlphaF(0.34)
        t2 = QColor(c["accent"]); t2.setAlphaF(0.16)
    elif dark:
        t1 = QColor(86, 86, 92); t1.setAlphaF(top)
        t2 = QColor(52, 52, 56); t2.setAlphaF(bot)
    else:
        t1 = QColor(255, 255, 255); t1.setAlphaF(top)
        t2 = QColor(255, 255, 255); t2.setAlphaF(bot)
    lg = QLinearGradient(0, rect.y(), 0, rect.y() + rect.height())
    lg.setColorAt(0.0, t1)
    lg.setColorAt(1.0, t2)
    p.setPen(Qt.NoPen)
    p.setBrush(lg)
    p.drawPath(path)

    # 3) 가장자리 빛 — 위가 밝고 아래로 사라진다
    if hot:
        e1 = QColor(c["accent"]); e1.setAlphaF(0.90)
        e2 = QColor(c["accent"]); e2.setAlphaF(0.55)
    elif dark:
        e1 = QColor(255, 255, 255); e1.setAlphaF(0.30)
        e2 = QColor(255, 255, 255); e2.setAlphaF(0.05)
    else:
        e1 = QColor(255, 255, 255); e1.setAlphaF(0.95)
        e2 = QColor(255, 255, 255); e2.setAlphaF(0.30)
    eg = QLinearGradient(0, rect.y(), 0, rect.y() + rect.height())
    eg.setColorAt(0.0, e1)
    eg.setColorAt(1.0, e2)
    p.setPen(QPen(QBrush(eg), 1.2))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


class GlassTabs(QTabWidget):
    """🍎 그래프 판 — **탭 줄 아래만** 유리다 (2026-09-09).

    🚨 `QTabWidget::pane` 은 위젯이 아니라 **`QStyle` 이 그리는 조각**이라
       `GlassCard` 로 갈아 끼울 수 없다. 그래서 탭 판 자리를 직접 재서 거기에만
       유리를 그린다. QSS 쪽 `::pane` 은 투명하게 비워 둔다.
    """

    def __init__(self, c, dark, radius=16, parent=None):
        super().__init__(parent)
        self.setTabBar(_PillTabBar(c["surface"], self))   # 앱 2.3 — 고른 탭 알약이 미끄러진다
        self.c, self.dark, self.radius = c, dark, radius
        self.tint = (0.58, 0.38) if not dark else (0.58, 0.38)

    def _pane(self):
        """탭 판 자리 — 탭 줄(그리고 모서리 단추) 아래 6px 부터."""
        bottom = self.tabBar().geometry().bottom()
        cw = self.cornerWidget(Qt.TopRightCorner)
        if cw is not None and cw.isVisible():
            bottom = max(bottom, cw.geometry().bottom())
        top = bottom + 1 + 6            # QSS 의 `top:6px` 과 같은 값
        return QRect(0, top, self.width(), max(0, self.height() - top))

    def paintEvent(self, e):
        paint_glass(self, QPainter(self), self._pane(), self.radius,
                    self.c, self.dark, self.tint)


class Combo(QComboBox):
    """🍎 맥식 드롭다운 — 오른쪽에 **쉐브론(⌄)** 을 직접 그린다 (2026-09-08).

    🚨 **Qt QSS 로는 삼각형을 못 만든다.** `width:0; height:0` 에 `border` 를 얹어
       삼각형을 만드는 것은 **웹 CSS 기법**이고, Qt 는 그대로 네모를 그린다(실측 —
       화살표 자리에 회색 사각형이 떴다). Qt 가 아는 길은 `image:url(...)` 뿐인데
       그러면 그림 파일이 따라다녀야 한다 ⇒ **직접 그린다.**
    🚨 그리고 `QComboBox` 에 배경·테두리 QSS 를 주면 **네이티브 화살표가 아예 꺼진다**
       — 그래서 「표」 드롭다운에는 화살표가 하나도 없었다(사용자 지적).
    """

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._chev = QColor(color)
        # 앱 2.3 — 펼침 목록은 **아래로 10줄**(QSS `combobox-popup:0`)이고 모서리가 둥글다.
        # 맥 기본은 고른 줄에 겹쳐 24줄을 다 펼쳤고, 둘레가 검은 판으로 보였다(2026-11-01
        # 사용자 *"이 드랍버튼도 좀 깔끔하게"*). 펼침 창(`view().window()`)을 투명 창으로
        # 만들어 둥근 목록 판만 보이게 한다 — 이 속성은 창이 처음 뜨기 **전에** 걸어야 먹는다.
        self.setMaxVisibleItems(10)
        box = self.view().window()
        box.setObjectName("combopop")
        box.setAttribute(Qt.WA_TranslucentBackground)
        box.setProperty("own_motion", True)          # 내려오는 움직임은 `showPopup` 이 직접

    def showPopup(self):
        # 🚨 `combobox-popup:0` 이어도 맥 스타일은 펼침 창을 **콤보 위에 겹쳐** 띄웠다
        #    (2026-11-02 실제 맥 창에서 찍음 — 콤보보다 8px 왼쪽 · 23px 좁아 ⌄ 가 삐져나옴.
        #    오프스크린 시험은 창 자리를 안 봐서 못 잡았다). 띄운 뒤 콤보 바로 아래 ·
        #    같은 폭으로 옮긴다. 아래 자리가 모자라면 콤보 위로 붙인다.
        #    내려오는 움직임(`popup_in`)은 앱 전체 필터가 Show 순간의 **옛 자리**를 끝점으로
        #    잡아 창을 도로 끌고 갔다 ⇒ 콤보 펼침 창은 필터가 건너뛰고(`own_motion`)
        #    여기서 자리를 잡은 **뒤에** 움직인다.
        super().showPopup()
        box = self.view().window()
        self._pop_mv = None
        self._place_popup()
        popup_in(box)
        self._pop_mv = box._pop_anims[1]
        # 앱이 맨 앞이 아닐 때는 Show 가 한 박자 늦게 와서 맥이 창을 옛 자리로 되돌렸다
        # (2026-11-02 실측) — 그 뒤에 한 번 더 놓는다.
        QTimer.singleShot(0, self._place_popup)
        QTimer.singleShot(40, self._place_popup)

    def _place_popup(self):
        box = self.view().window()
        if not box.isVisible():
            return
        gap = 4
        top = self.mapToGlobal(QPoint(0, 0))
        h = box.height()
        y = top.y() + self.height() + gap
        scr = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        if y + h > scr.bottom() and top.y() - gap - h >= scr.top():
            y = top.y() - gap - h
        mv = getattr(self, "_pop_mv", None)
        if mv is not None and mv.state() == QAbstractAnimation.Running:
            mv.setStartValue(QPoint(top.x(), y - 6))
            mv.setEndValue(QPoint(top.x(), y))
            box.resize(self.width(), h)
        else:
            box.setGeometry(top.x(), y, self.width(), h)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self._chev)
        pen.setWidthF(1.7)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        cx = self.width() - 15
        cy = self.height() / 2
        w, h = 4.4, 2.6
        p.drawPolyline([QPointF(cx - w, cy - h + 1), QPointF(cx, cy + h),
                        QPointF(cx + w, cy - h + 1)])


def fade_in(w, ms=200, delay=0):
    """새로 뜬 내용을 **살짝 밝아지며** 들어오게 한다 (2026-09-08).

    사용자: *"버튼 같은거나 그래프 바뀔때 전환 모션도 애플처럼 바꿀 수 있나?"*

    🍎 애플의 전환은 **짧고(0.2s 안팎) 끝에서 느려진다**(ease-out). 길게 끌거나
       가운데가 빠른 곡선(ease-in-out)을 쓰면 «웹 애니메이션» 티가 난다.
    ⚠️ **위젯 하나에 효과는 하나뿐이다** — 이미 그림자가 걸린 판(`float_panel`)에는
       못 건다. 그래서 판이 아니라 **판 안의 내용**에 건다.
    ⚠️ 애니메이션 객체를 지역 변수로 두면 함수가 끝나며 사라져 **아무 일도 안 일어난다**.
       위젯에 매달아 둔다.
    """
    if w is None:
        return w
    eff = QGraphicsOpacityEffect(w)
    eff.setOpacity(0.0)
    w.setGraphicsEffect(eff)
    a = QPropertyAnimation(eff, b"opacity", w)
    a.setDuration(ms)
    a.setStartValue(0.0)
    a.setEndValue(1.0)
    a.setEasingCurve(QEasingCurve.OutCubic)
    # 끝나면 효과를 뗀다 — 남겨 두면 그 위젯이 계속 오프스크린 버퍼를 거쳐 느려진다
    a.finished.connect(lambda: w.setGraphicsEffect(None))
    if delay:                                 # `rise_in` 이 카드를 차례로 띄울 때
        def _start():
            try:
                a.start()
            except RuntimeError:              # 기다리는 새 화면을 갈아 끼워 위젯이 지워졌다
                pass
        QTimer.singleShot(delay, _start)
    else:
        a.start()
    w._fade_anim = a
    return w


# ── 앱 2.3 움직임 (2026-11-01) ───────────────────────────────────────────
# 사용자: *"클릭하거나 다른 항목으로 넘어갈 때 스무스한 애니메이션"* → Dribbble
# 「Motion UI Design for Data Dashboards」(TheMotionDot) 를 0.5초 간격 장면 48장으로
# 쪼개 읽고 셋을 옮겼다 — ① 고른 칸의 바탕이 옆 칸으로 **미끄러진다** ② 내용이
# 바뀌면 카드가 **차례로** 나타난다 ③ 숫자가 **올라가며** 바뀐다.
# 길이·곡선은 `fade_in` 과 같은 결(0.2초 안팎 · 끝에서 느려짐)로 맞춘다.
SLIDE_MS = 220
STAGGER_MS = 45


def rise_in(page):
    """② 탭을 바꾸면 그 탭의 카드(`#card`)가 위에서부터 차례로 나타난다.

    카드가 둘 미만이면 지금까지처럼 판 전체를 `fade_in` 한다.
    ③ `_count_fmt` 를 단 이름표는 숫자가 0 에서 올라간다(`count_up`).
    """
    if page is None:
        return page
    cards = page.findChildren(QFrame, "card")
    if len(cards) < 2:
        fade_in(page)
    else:
        for i, cd in enumerate(cards[:12]):           # 그 뒤는 한꺼번에 — 기다리게 하지 않는다
            fade_in(cd, delay=i * STAGGER_MS)
    for lab in page.findChildren(QLabel):
        if getattr(lab, "_count_fmt", None):
            count_up(lab)
    return page


def play_charts(page):
    """앱 2.3 — 결과 그래프가 제 움직임으로 나타난다(`charts._anim` · 그래프마다 `_play`).

    하나라도 돌렸으면 True — 부르는 쪽은 False 일 때만 판 전체를 `fade_in` 한다.
    """
    if page is None:
        return False
    # 보이는 것만 — 뒤에 숨은 탭의 계통도까지 그림을 뜨면 0.1초씩 멈춘다
    ws = [w for w in page.findChildren(QWidget)
          if callable(getattr(w, "_play", None)) and w.isVisible()]
    for w in ws:
        w._play()
    return bool(ws)


def reveal(w):
    """앱 2.3 — 가운데 판이 바뀔 때: 판은 밝아지고 그 안의 그래프는 제 움직임으로 그려진다.

    🚨 **새 판이 처음 그려질 때 시작한다.** 다시 그린 판은 첫 장면까지 0.1 ~ 0.25 초
    걸린다(모드 바꾸기 실측) — 바로 시작하면 0.2 초짜리 밝아짐이 화면에 뜨기 전에
    거의 끝나 있었다. 그때까지는 거의 투명(0.01)으로 둔다 — 0 이면 Qt 가 판을 아예
    안 그려 «첫 장면» 이 오지 않는다.
    """
    if w is None:
        return w
    eff = QGraphicsOpacityEffect(w)
    eff.setOpacity(0.01)
    w.setGraphicsEffect(eff)

    def go():
        if _alive(w):
            fade_in(w)
            play_charts(w)
    _OnFirstPaint(w, go)
    return w


def _alive(w):
    try:
        w.objectName()
        return True
    except RuntimeError:                      # 그새 화면을 또 갈아 끼워 지워졌다
        return False


def count_up(lab, ms=420):
    """③ 이름표의 숫자를 0 에서 제 값까지 올린다. `lab._count_fmt(t)` 가 0~1 의 t 로 글을 만든다."""
    a = QVariantAnimation(lab)
    a.setDuration(ms)
    a.setStartValue(0.0)
    a.setEndValue(1.0)
    a.setEasingCurve(QEasingCurve.OutCubic)
    a.valueChanged.connect(lambda t: lab.setText(lab._count_fmt(float(t))))
    a.start()
    lab._count_anim = a


class _OnFirstPaint(QObject):
    """`w` 가 처음 그려지면 `fn` 을 한 번 부른다. 끝내 안 그려져도 `fallback_ms` 뒤에는 부른다."""

    def __init__(self, w, fn, fallback_ms=180):
        super().__init__(w)
        self._w, self._fn, self._done = w, fn, False
        w.installEventFilter(self)
        QTimer.singleShot(fallback_ms, self._fire)

    def eventFilter(self, o, e):
        if e.type() == QEvent.Paint:
            QTimer.singleShot(0, self._fire)
        return False

    def _fire(self):
        if self._done:
            return
        self._done = True
        try:
            self._w.removeEventFilter(self)
        except RuntimeError:                      # 그새 화면을 또 갈아 끼워 위젯이 지워졌다
            pass
        self._fn()


def snap_central(win):
    """다시 그리기 직전 가운데 판을 (그림, 자리) 로 찍는다. 안 보이면 None."""
    cw = win.centralWidget()
    if cw is None or not cw.isVisible():
        return None
    return cw.grab(), cw.geometry()


def crossfade_from(win, snap, then, probe, ms=SLIDE_MS + 40):
    """화면을 **통째로 다시 그리는** 전환을 매끄럽게 한다 (2026-11-01, 앱 2.3).

    다시 그리는 동안 UI 가 약 0.2초 멈추고(점검 탭 실측 215 ms) 새 화면이 처음 그려질 때까지
    빈 판이 보였다. 그래서 다시 그리기 **직전 화면**(`snap`)을 그대로 덮어 두었다가, 새 화면이
    처음 그려지면(`probe`) 그 위에서 옅어지며 걷는다. `then()` 은 그때 부른다(카드가 차례로 나타남).

    `snap` = `snap_central(win)` 이 돌려준 (그림, 자리). ⚠️ 자리는 **찍을 때** 잰 것을 쓴다 —
    다시 그린 직후의 새 판은 아직 크기가 안 정해져(기본 640×480) 덮개가 일부만 덮었다.
    """
    if snap is None:
        then()
        return
    pm, rect = snap
    ov = QLabel(win)
    ov.setPixmap(pm)
    ov.setGeometry(rect)
    ov.setAttribute(Qt.WA_TransparentForMouseEvents)
    eff = QGraphicsOpacityEffect(ov)
    eff.setOpacity(1.0)
    ov.setGraphicsEffect(eff)
    ov.show()
    ov.raise_()

    def go():
        try:
            a = QPropertyAnimation(eff, b"opacity", ov)
            a.setDuration(ms)
            a.setStartValue(1.0)
            a.setEndValue(0.0)
            a.setEasingCurve(QEasingCurve.OutCubic)
            a.finished.connect(ov.deleteLater)
            a.start()
            ov._anim = a
            then()
        except RuntimeError:
            pass

    def gone():
        try:
            ov.deleteLater()
        except RuntimeError:
            pass
    QTimer.singleShot(2000, gone)                 # 무슨 일이 있어도 덮개는 남지 않는다
    _OnFirstPaint(probe.viewport() if hasattr(probe, "viewport") else probe, go)


class _Ripple(QWidget):
    """D 단추를 누른 자리에서 원이 퍼지며 옅어진다 (레퍼런스 — 핀을 누른 자리의 원)."""

    def __init__(self, btn, pos, color, ms=380):
        super().__init__(btn)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(btn.rect())
        self._p, self._c, self._t = QPointF(pos), QColor(color), 0.0
        dx = max(pos.x(), btn.width() - pos.x())
        dy = max(pos.y(), btn.height() - pos.y())
        self._R = (dx * dx + dy * dy) ** 0.5           # 가장 먼 모서리까지
        a = QVariantAnimation(self)
        a.setDuration(ms)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.valueChanged.connect(self._step)
        a.finished.connect(self.deleteLater)
        a.start()
        self._a = a
        self.show()
        self.raise_()

    def _step(self, t):
        self._t = float(t)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 9, 9)  # 단추 모서리(QSS 9px) 밖으로 안 번지게
        p.setClipPath(clip)
        col = QColor(self._c)
        col.setAlphaF(0.28 * (1.0 - self._t))
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        r = self._R * self._t
        p.drawEllipse(self._p, r, r)


def dialog_in(d, ms=160):
    """E 대화상자가 투명에서 나타난다. (크기를 키우는 움직임은 창이 떨릴 수 있어 뺐다.)"""
    d.setWindowOpacity(0.0)
    a = QPropertyAnimation(d, b"windowOpacity", d)
    a.setDuration(ms)
    a.setStartValue(0.0)
    a.setEndValue(1.0)
    a.setEasingCurve(QEasingCurve.OutCubic)
    a.start()
    d._in_anim = a


class OrbRing(QWidget):
    """계산 중 — 살아 있는 듯 출렁이는 빛 고리 (2026-11-01, 앱 2.3 · 사용자 「C 좋다」).

    레퍼런스 = Dribbble 「Sentient Orb — AI Loading State Concept」. 색은 테마(먹색 · 은빛)로.
    고리 반지름에 사인 물결 셋(3 · 5 · 2 마디, 서로 다른 속도)을 더해 쉬지 않고 모양이 바뀌고,
    먹색 → 은빛 원뿔 그라디언트가 둘레를 돈다. 흐림 효과 대신 굵기 · 투명도가 다른 선
    다섯 겹으로 빛 번짐을 낸다(Qt 2D 로 실시간에 그릴 수 있는 방식).
    """

    WAVES = ((3.0, 3, 1.7), (2.2, 5, -2.3), (1.5, 2, 1.1))     # (크기 · 마디 · 속도) — 지름 120 기준
    GLOW = ((14, .06), (9, .12), (5, .25), (2.6, .6), (1.3, 1.0))   # (굵기 · 투명도)

    def __init__(self, dark, size=120, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._pal = (("#e6e7ea", "#a9aeb8", "#5a5f6a") if dark
                     else ("#1f232b", "#6b7180", "#c9ced8"))
        self._t0 = time.perf_counter()
        self._tm = QTimer(self)
        self._tm.timeout.connect(self.update)
        self._tm.start(16)                                  # 약 60장/초

    def stop(self):
        self._tm.stop()

    def paintEvent(self, e):
        t = time.perf_counter() - self._t0
        s = self.width() / 120.0
        cx = cy = self.width() / 2
        R, n = 36 * s, 120
        path = QPainterPath()
        for i in range(n + 1):
            a = i / n * 2 * math.pi
            d = sum(amp * math.sin(k * a + sp * t) for amp, k, sp in self.WAVES) * s
            pt = QPointF(cx + (R + d) * math.cos(a), cy + (R + d) * math.sin(a))
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        path.closeSubpath()
        grad = QConicalGradient(cx, cy, -math.degrees(t * 0.8))
        dk, md, lt = (QColor(x) for x in self._pal)
        for pos, col in ((0.0, dk), (0.4, md), (0.7, lt), (1.0, dk)):
            grad.setColorAt(pos, col)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for w, a in self.GLOW:
            pen = QPen(QBrush(grad), w * s)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setOpacity(a)
            p.setPen(pen)
            p.drawPath(path)


class SolvingDialog(QDialog):
    """계산 중 창 — 출렁이는 고리 + 글 (앱 2.3 · 옛 `QProgressDialog` 막대 자리)."""

    def __init__(self, parent, c, dark, text="조류계산 중입니다..."):
        super().__init__(parent)
        self.setWindowTitle("UNIGRID")
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumWidth(340)
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 22, 28, 22)
        v.setSpacing(6)
        self.orb = OrbRing(dark, 120)
        v.addWidget(self.orb, 0, Qt.AlignHCenter)
        lab = QLabel(text)
        lab.setAlignment(Qt.AlignCenter)
        lab.setStyleSheet(f"color:{c['text']};font-size:14px;")
        v.addWidget(lab)

    def close(self):
        try:
            self.orb.stop()
        except RuntimeError:
            pass
        return super().close()


def popup_in(w, ms=150, drop=6):
    """드롭다운 · 메뉴 펼침 창이 투명에서 나타나며 `drop` 픽셀 위에서 내려온다."""
    end = w.pos()
    w.setWindowOpacity(0.0)
    w.move(end.x(), end.y() - drop)
    op = QPropertyAnimation(w, b"windowOpacity", w)
    mv = QPropertyAnimation(w, b"pos", w)
    for a, s, e in ((op, 0.0, 1.0), (mv, QPoint(end.x(), end.y() - drop), end)):
        a.setDuration(ms)
        a.setStartValue(s)
        a.setEndValue(e)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.start()
    w._pop_anims = (op, mv)


class _MotionFilter(QObject):
    """앱 전체에 한 곳에서 건다 — D 단추 누름 물결 · E 대화상자 나타남."""

    def __init__(self, win):
        super().__init__(win)
        self._win = win

    def eventFilter(self, o, e):
        try:
            t = e.type()
            if (t == QEvent.MouseButtonPress and isinstance(o, QPushButton)
                    and o.isEnabled() and o.isVisible()):
                # 누르는 순간 단추 바탕이 파랗게 바뀐다(QSS `QPushButton:pressed`) — 그 위엔
                # 흰 물결. `seg_off` 만 옅은 파랑(`accent_soft`)으로 바뀌므로 파란 물결.
                light = o.objectName() == "seg_off"
                c = self._win.c
                col = (c["rail_on"] if o.objectName() == "railbtn"     # 진한 사이드바 위
                       else c["accent"] if light else c["on_accent"])
                _Ripple(o, e.position().toPoint(), col)
            elif (t == QEvent.Show and isinstance(o, QDialog) and o.isWindow()
                    and not isinstance(o, QFileDialog)
                    and not getattr(o, "_motion_shown", False)):
                o._motion_shown = True
                dialog_in(o)
            elif (t == QEvent.Show and isinstance(o, QWidget) and o.isWindow()
                    and o.windowType() == Qt.Popup and not o.property("own_motion")):
                # 앱 2.3 — 펼침 창이 살짝 내려오며 나타난다. `Qt.Popup` 꼴이면 모두 —
                # 드롭다운 목록(표 고르기 · 시간 · 해법 …) · 메뉴 · 비교 항목 고르기 판.
                # (풍선말은 `Qt.ToolTip` 꼴이라 여기 안 걸리고 Qt 효과로 따로 켠다)
                popup_in(o)
        except Exception:                             # 움직임 때문에 앱이 서면 안 된다
            pass
        return False


def _rail_icon(p, kind, ox, oy, s=1.0):
    """사이드바 아이콘을 선으로 그린다 — 20×20 칸 기준 좌표 · (ox, oy) = 칸 왼쪽 위.

    글꼴 기호(⚠ ▦ …)는 맥 · 윈도우에서 모양이 달라 직접 그린다.
    """
    def P(x, y):
        return QPointF(ox + x * s, oy + y * s)

    def poly(*pts, close=False):
        path = QPainterPath(P(*pts[0]))
        for q in pts[1:]:
            path.lineTo(P(*q))
        if close:
            path.closeSubpath()
        p.drawPath(path)

    if kind == "open":            # 폴더
        poly((2, 6), (8, 6), (10, 8), (18, 8), (18, 16), (2, 16), close=True)
    elif kind == "result":        # 꺾은선 그래프 + 축
        poly((2, 2), (2, 18), (18, 18))
        poly((5, 14), (9, 9), (12, 12), (17, 5))
    elif kind == "check":         # 경고 세모 + 느낌표
        poly((10, 2.5), (18, 17), (2, 17), close=True)
        poly((10, 7.5), (10, 12))
        p.drawPoint(P(10, 14.5))
    elif kind == "grid":          # 표
        p.drawRoundedRect(QRectF(P(2, 3), P(18, 17)), 2 * s, 2 * s)
        poly((2, 8), (18, 8)); poly((2, 12.5), (18, 12.5)); poly((8, 3), (8, 17))
    elif kind == "scenario":      # 겹친 판
        p.drawRoundedRect(QRectF(P(6, 2), P(18, 13)), 2 * s, 2 * s)
        poly((14, 15), (14, 18), (2, 18), (2, 6), (4.5, 6))
    elif kind == "curve":         # PV 곡선 (코 모양)
        path = QPainterPath(P(3, 3))
        path.quadTo(P(22, 9), P(3, 17))
        p.drawPath(path)
        poly((2, 2), (2, 18), (18, 18))
    elif kind == "export":        # 상자 밖으로 화살표
        poly((6, 9), (3, 9), (3, 18), (17, 18), (17, 9), (14, 9))
        poly((10, 13), (10, 2)); poly((6.5, 5.5), (10, 2), (13.5, 5.5))
    elif kind == "excel":         # 문서 + 더하기
        poly((4, 2), (12.5, 2), (16.5, 6), (16.5, 18), (4, 18), close=True)
        poly((12.5, 2), (12.5, 6), (16.5, 6))
        poly((10.2, 9), (10.2, 15)); poly((7.2, 12), (13.2, 12))
    elif kind == "info":          # 원 안의 i
        p.drawEllipse(P(10, 10), 8 * s, 8 * s)
        poly((10, 9), (10, 14.5))
        p.drawPoint(P(10, 6))


class DropCard(QFrame):
    """시작 화면의 파일 놓는 칸 — 점선 테두리 둥근 판 (앱 2.3 · 2026-11-03 S1).

    끌어온 파일이 창 위에 있으면 `set_hot(True)` 로 테두리가 강조색 실선이 된다.
    """

    def __init__(self, c, dark, parent=None):
        super().__init__(parent)
        self._c, self._dark, self._hot = c, dark, False
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_hot(self, on):
        self._hot = bool(on)
        self.update()

    def paintEvent(self, _e):
        c = self._c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        # 2026-11-15 — 새 디자인: 사이드바와 같은 진한 먹색 판. 여태 시작 화면만 옛 꼴이라
        # 앱을 켜면 바뀐 것이 안 보였다(사용자: 「새 디자인 안보이는데?」).
        p.setBrush(QColor(c["nav_on"] if self._hot else c["nav"]))
        if self._hot:
            p.setPen(QPen(QColor("#ffffff"), 2))
        elif self._dark:
            p.setPen(QPen(QColor(c["nav_line"]), 1))
        else:
            p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, 20, 20)


class RailButton(QPushButton):
    """B 꼴 사이드바의 칸 — 위에 선 아이콘, 아래에 이름 (2026-11-01, 앱 2.3).

    `QPushButton` 을 이어받아 `text()`(이름) · 키보드 · 풍선말은 그대로 쓴다.
    고른 칸은 밝은 둥근 판(`rail_on`) 위에 진한 아이콘 — 레퍼런스 B 의 「고른 칸은 밝은 원」.
    """

    def __init__(self, kind, name, c, on=False, parent=None):
        super().__init__(name, parent)
        self._kind, self._c, self._on = kind, c, on
        self.setFixedSize(64, 58)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("railbtn")

    def set_on(self, on):
        self._on = on
        self.update()

    def sizeHint(self):
        return QSize(64, 58)

    def minimumSizeHint(self):
        return QSize(64, 58)

    def paintEvent(self, e):
        c = self._c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 1, -4, -1)
        if self._on:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c["rail_on"]))
            p.drawRoundedRect(r, 11, 11)
        elif self.underMouse() and self.isEnabled():
            hov = QColor(c["rail_on"]); hov.setAlphaF(0.12)
            p.setPen(Qt.NoPen)
            p.setBrush(hov)
            p.drawRoundedRect(r, 11, 11)
        fg = QColor(c["rail_on_fg"] if self._on else c["rail_fg"])
        if not self.isEnabled():
            fg.setAlphaF(0.35)
        pen = QPen(fg, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        _rail_icon(p, self._kind, self.width() / 2 - 10, 7)
        f = p.font()
        f.setPixelSize(10)
        f.setBold(self._on)
        p.setFont(f)
        # 이름이 길면(계통 데이터 · PV·QV 곡선 · 엑셀로 만들기) 두 줄로 접는다
        p.drawText(QRectF(2, 30, self.width() - 4, 26),
                   Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, self.text())

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class ThemeSwitch(QPushButton):
    """C 밝게 / 어둡게 — 해 · 달 사이를 손잡이가 미끄러진 뒤 테마를 바꾼다.

    `QPushButton` 을 이어받아 키보드(스페이스)·풍선말·글자(`text()`)는 그대로 쓴다.
    글자는 그리지 않고 손잡이로 대신한다.
    """
    flipped = Signal()

    def __init__(self, dark, c, parent=None):
        super().__init__("밝게" if dark else "어둡게", parent)
        self._c = c
        self._x = 1.0 if dark else 0.0                 # 0 = 해(밝게) 쪽 · 1 = 달(어둡게) 쪽
        self.setFixedSize(64, 30)
        # 바탕은 `paintEvent` 가 다 그린다. ⚠️ 여기에 선택자 없는 QSS 를 걸면 이 단추의
        # 풍선말까지 투명해져 맥에서 빈 검은 상자로 뜬다(2026-11-01).
        self._a = QVariantAnimation(self)
        self._a.setDuration(SLIDE_MS)
        self._a.setEasingCurve(QEasingCurve.OutCubic)
        self._a.valueChanged.connect(self._step)
        self._a.finished.connect(self.flipped.emit)
        self.clicked.connect(self._go)

    # 글자를 안 그리므로 글자 기준 권장 크기(71×37)를 쓰지 않는다 — `shot_layout` 이 잘림으로 잡았다
    def sizeHint(self):
        return QSize(64, 30)

    def minimumSizeHint(self):
        return QSize(64, 30)

    def _go(self):
        if self._a.state() == QVariantAnimation.Running:
            return
        self._a.setStartValue(self._x)
        self._a.setEndValue(1.0 - self._x)
        self._a.start()

    def _step(self, v):
        self._x = float(v)
        self.update()

    def paintEvent(self, e):
        c = self._c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(c["border"]), 1))
        p.setBrush(QColor(c["side"]))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        kx = r.left() + 3 + (r.width() - 6 - d) * self._x
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["surface"]))
        p.drawEllipse(QRectF(kx, r.top() + 3, d, d))
        f = p.font()
        f.setPointSize(11)
        p.setFont(f)
        p.setPen(QColor(c["muted"]))
        p.drawText(QRectF(r.left() + 3, r.top(), d, r.height()), Qt.AlignCenter, "☀")
        p.drawText(QRectF(r.right() - 3 - d, r.top(), d, r.height()), Qt.AlignCenter, "☾")


class _Pill(QWidget):
    """① 선택 단추 밑을 미끄러지는 알약 — `slide_segs` 가 잠깐 띄웠다가 지운다."""

    def __init__(self, parent, color):
        super().__init__(parent)
        self._color = QColor(color)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self._color)
        p.drawRoundedRect(QRectF(self.rect()), 8, 8)     # `#seg_on` 의 border-radius


def slide_segs(root, prev, color):
    """① 다시 그린 화면의 선택 단추 묶음(`#segwrap`)마다, 고른 단추가 바뀌었으면
    알약을 **옛 단추 자리에서 새 단추 자리로** 민다.

    화면은 누를 때마다 통째로 다시 그려지므로(`rebuild`) 옛 단추는 이미 없다 —
    묶음을 단추 글자로 알아보고(`prev` = {글자 묶음: 고른 글자}) 새 묶음의 같은 글자
    단추 자리에서 출발한다. 미는 동안 새 `#seg_on` 의 바탕만 비워 알약이 대신한다.
    """
    for seg in root.findChildren(QFrame, "segwrap"):
        bs = [b for b in seg.findChildren(QPushButton) if b.parent() is seg]
        on = next((b for b in bs if b.objectName() == "seg_on"), None)
        key = tuple(b.text() for b in bs)
        old = prev.get(key)
        prev[key] = on.text() if on else None
        src = next((b for b in bs if b.text() == old), None)
        if on is None or src is None or src is on:
            continue
        pill = _Pill(seg, color)
        pill.setGeometry(src.geometry())
        pill.lower()                                  # 단추 글자 밑에
        pill.show()
        on.setStyleSheet("QPushButton { background:transparent; }")   # 선택자 — 풍선말에 안 번지게
        a = QPropertyAnimation(pill, b"geometry", pill)
        a.setDuration(SLIDE_MS)
        a.setStartValue(src.geometry())
        a.setEndValue(on.geometry())
        a.setEasingCurve(QEasingCurve.OutCubic)

        def _done(p=pill, b=on):
            try:
                b.setStyleSheet("")
                p.deleteLater()
            except RuntimeError:                      # 그새 화면을 또 갈아 끼웠다
                pass
        a.finished.connect(_done)
        a.start()


class _PillTabBar(QTabBar):
    """① 그래프 탭 — 고른 탭 밑의 알약이 옛 탭에서 새 탭으로 미끄러진다.

    QSS 는 `QTabBar#pillbar::tab:selected` 바탕을 비우고, 알약은 여기서 직접 그린다.
    """

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.setObjectName("pillbar")
        self._color = QColor(color)
        self._r = None                                # 미는 중일 때의 알약 자리
        self._last = -1
        self._a = QVariantAnimation(self)
        self._a.setDuration(SLIDE_MS)
        self._a.setEasingCurve(QEasingCurve.OutCubic)
        self._a.valueChanged.connect(self._step)
        self._a.finished.connect(self._end)
        self.currentChanged.connect(self._go)

    def _go(self, i):
        old, self._last = self._last, i
        if old < 0 or old == i or old >= self.count():
            return
        self._a.stop()
        self._a.setStartValue(QRectF(self.tabRect(old)))
        self._a.setEndValue(QRectF(self.tabRect(i)))
        self._a.start()

    def _step(self, r):
        self._r = r
        self.update()

    def _end(self):
        self._r = None
        self.update()

    def paintEvent(self, e):
        r = self._r
        if r is None and self.currentIndex() >= 0:
            r = QRectF(self.tabRect(self.currentIndex()))
        if r is not None:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(self._color)
            p.drawRoundedRect(r.adjusted(0, 0, -4, 0), 7, 7)   # -4 = QSS margin-right
            p.end()
        super().paintEvent(e)


def slide_width(w, start, end, ms=240):
    """가로 폭을 **부드럽게** 바꾼다 — 사이드바 접기/펼치기 (2026-09-08).

    🍎 맥 사이드바는 폭이 «툭» 바뀌지 않고 밀려 들어간다. 페이드로는 그 느낌이
       안 난다 — 사라지는 게 아니라 **좁아지는** 것이기 때문이다.
    ⚠️ `setFixedWidth` 가 걸려 있으면 애니메이션이 안 먹는다(최소=최대라 움직일
       자리가 없다). 최소를 풀고 **최대만** 움직인 뒤, 끝나면 다시 못 박는다.
    """
    if w is None:
        return w
    w.setMinimumWidth(0)
    w.setMaximumWidth(start)
    a = QPropertyAnimation(w, b"maximumWidth", w)
    a.setDuration(ms)
    a.setStartValue(start)
    a.setEndValue(end)
    a.setEasingCurve(QEasingCurve.OutCubic)
    a.finished.connect(lambda: w.setFixedWidth(end))
    a.start()
    w._slide_anim = a
    return w


# 🍎 시작 화면의 판 둘(파일 놓는 자리 · 최근 목록)은 **폭이 같아야 한다**.
#    폭을 안 박으면 각자 «담은 글자» 만큼만 잡혀 왼쪽 끝이 어긋난다(2026-09-09).
START_CARD_W = 560

# `float_panel` 의 그림자가 판 밖으로 퍼지는 거리 — blur 26(반지름 13) + 아래로 5.
# 판을 감싸는 위젯에 이만큼 여백이 없으면 그림자가 잘려 모서리가 각져 보인다.
SHADOW_ROOM = 20


class MisChart(QWidget):
    """반복에 따른 최대 불평형 — 세로축 로그 눈금 꺾은선 (2026-11-15).

    여태 이 자리에는 「실제 그래프가 들어갈 자리」 라는 글과 숫자 칸만 있었다.
    `mis` = 반복마다의 최대 불평형(0회 = 출발점) · `thr` = 수렴 기준.
    """

    def __init__(self, mis, thr, c, parent=None):
        super().__init__(parent)
        self.mis = [float(m) for m in mis if m is not None and float(m) > 0]
        self.thr, self.c = float(thr), c
        self.setMinimumHeight(190)

    def paintEvent(self, _e):
        c = self.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(self.font()); f.setPixelSize(11); p.setFont(f)
        if not self.mis:
            p.setPen(QColor(c["muted"]))
            p.drawText(self.rect(), Qt.AlignCenter, "반복 기록이 없습니다")
            p.end(); return
        L, T_, R_, B = 58, 22, 22, 26
        w, h = self.width() - L - R_, self.height() - T_ - B
        lo = math.floor(math.log10(min(min(self.mis), self.thr))) - 0.3
        hi = math.ceil(math.log10(max(max(self.mis), self.thr))) + 0.3
        n = len(self.mis)
        X = lambda k: L + (w * k / max(1, n - 1) if n > 1 else w / 2)
        Y = lambda v: T_ + h * (hi - math.log10(v)) / (hi - lo)
        # 가로 눈금 — 10 의 거듭제곱마다 (칸이 많으면 솎는다)
        step = max(1, int(math.ceil((hi - lo) / 6)))
        for e in range(int(math.ceil(lo)), int(math.floor(hi)) + 1, step):
            y = Y(10.0 ** e)
            p.setPen(QPen(QColor(c["hair"]), 1))
            p.drawLine(QPointF(L, y), QPointF(L + w, y))
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(0, y - 9, L - 8, 18), Qt.AlignRight | Qt.AlignVCenter, f"1e{e:+d}")
        # 수렴 기준선
        yt = Y(self.thr)
        pen = QPen(QColor(c["ok"]), 1.2, Qt.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(L, yt), QPointF(L + w, yt))
        p.drawText(QRectF(L + w - 150, yt - 17, 150, 16), Qt.AlignRight | Qt.AlignVCenter,
                   f"수렴 기준 {self.thr:g}")
        # 꺾은선 · 점 · 값
        pts = [QPointF(X(k), Y(v)) for k, v in enumerate(self.mis)]
        p.setPen(QPen(QColor(c["accent"]), 2))
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)
        for k, (pt, v) in enumerate(zip(pts, self.mis)):
            done = v < self.thr
            p.setPen(QPen(QColor(c["surface"]), 2))
            p.setBrush(QColor(c["ok"] if done else c["accent"]))
            p.drawEllipse(pt, 5, 5)
            p.setPen(QColor(c["ok"] if done else c["text"]))
            up = pt.y() - 22 > T_ - 16
            if up:
                p.drawText(QRectF(pt.x() - 40, pt.y() - 24, 80, 16), Qt.AlignCenter, f"{v:.1e}")
            else:        # 맨 위 점은 위에 자리가 없다 — 오른쪽에 적는다(아래에 두면 세로축 눈금과 겹쳤다)
                p.drawText(QRectF(pt.x() + 10, pt.y() - 8, 80, 16), Qt.AlignLeft | Qt.AlignVCenter, f"{v:.1e}")
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(pt.x() - 30, T_ + h + 6, 60, 16), Qt.AlignCenter, f"{k}회")
        p.end()


def float_panel(w, dark, strong=False):
    """판을 **떠 있게** 만든다 — 그림자 (2026-09-08).

    사용자: *"사이드바, 그래프, 표 영역으로 해서 각각 floating 느낌이 나면 좋겠어"*.
    Qt 위젯에는 `box-shadow` 가 없다. `QGraphicsDropShadowEffect` 가 유일한 길이다.

    ⚠️ 그림자만으로는 안 뜬다 — **판 사이에 여백**이 있어야 각각이 따로 보인다.
       여백은 `build`(판 사이 12px · 창 가장자리 14px)가 담당한다.
    """
    eff = QGraphicsDropShadowEffect(w)
    if FLAT_CARDS:       # 개요 카드(`overview._card`)와 같은 그림자 — 넓고 옅게
        eff.setBlurRadius(22)            # 테두리가 판을 가르므로 그림자는 아주 옅게만
        eff.setOffset(0, 6)
        eff.setColor(QColor(0, 0, 0, 60 if dark else 11))
        w.setGraphicsEffect(eff)
        return w
    eff.setBlurRadius(34 if strong else 26)
    eff.setOffset(0, 7 if strong else 5)
    eff.setColor(QColor(0, 0, 0, 110 if dark else 42))
    w.setGraphicsEffect(eff)
    return w


class Proto(QMainWindow):
    DARK_PALETTE = DARK           # 개요 화면의 검은 그래프 카드가 쓴다

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)     # 파일을 창에 끌어다 놓으면 바로 연다
        self.dropzone = None
        self.drop_label = None
        self.dark = False
        # 앱 2.3 D·E — 단추 누름 물결 · 대화상자 나타남을 앱 전체에 한 곳에서 건다
        self._motion = _MotionFilter(self)
        QApplication.instance().installEventFilter(self._motion)
        # 앱 2.3 — 풍선말이 흐려졌다 나타난다 (Qt 에 이미 있는 효과를 켠다)
        #    ⚠️ 개별 효과는 「UI 효과 전체(`UI_General`)」가 켜져 있어야 돈다
        for eff in (Qt.UI_General, Qt.UI_AnimateTooltip, Qt.UI_FadeTooltip):
            QApplication.setEffectEnabled(eff, True)
        # ── 무엇을 할까 (PDR §7 4단계 F1d · 2026-08-12 사용자 확정 "조류계산이랑 아예 분리")
        #    곡선은 조류계산 결과(`self.sol`)에 **기대지 않는다.** 조류계산을 한 번도
        #    안 돌려도 곡선만 돌릴 수 있다. 공유하는 것은 케이스와 계통 조건뿐이다.
        self.task = "조류계산"        # "조류계산" · "PV·QV 곡선"
        self.cur = None               # 곡선 결과 (app_engine.Curve)
        self.curve_load = ""          # 부하를 늘릴 버스 (비면 부하가 있는 버스 전부)
        self.curve_pick = ""          # 곡선을 그릴 버스 (비면 늘린 버스와 같게)
        self.curve_x = "MW"           # 가로축 — "MW" 합계 부하 · "lambda" 배수
        self.curve_busy = False
        self.curve_err = ""
        self.numbers = False
        self.numbers_auto = False     # 큰 계통이라 **자동으로** 접힌 것인가
        self.graph_kept = False       # 사용자가 직접 펼친 적이 있나 (있으면 자동으로 안 접는다)
        self.numbers_why = ""         # 왜 접혔나 — "big"(큰 계통) · "changed"(조건을 바꿔 품)
        self.mode = "스냅샷"
        # 왼쪽 줄을 펼쳐 두었나 (2026-09-02 사용자 확정, 안 (나) — 접으면 56px 띠).
        # 접힘은 split 자리와 같은 격의 **세션 안 상태**다. 디스크에 남기는 것은
        # 최근 연 파일과 계통도 자리 둘뿐이라(`paths`) 여기 끼워 넣지 않는다.
        self.side_open = True
        # 계통 데이터 표에서 켠 열 — {표 key: {데이터 열 번호}} (2026-09-02).
        # 없으면 전부 켜진 것으로 본다. 결과 표의 `visible` 과 같은 격이되,
        # 저쪽은 **열 이름**으로 세고 여기는 **열 번호**로 센다(머리글이 파일마다
        # 다르고 빈 열이 뒤에 붙기도 해서 이름이 안 고정된다).
        self.grid_visible = {}
        self.compare_axis = "버스끼리"
        self.overlay = set()          # 겹쳐 볼 시나리오 (Book 안 자리 번호) — 비면 전부
        self.compare_targets = "3, 7, 12"
        self.picked = {"전압 크기"}
        self.case = ("ACDC_CIGRE_MVACMVDCLVDC.xlsx", "AC/DC 혼합 · AC 14 / DC 11")
        self.sol = None               # 실제 계산 결과 (없으면 화면 모양용 가짜값)
        self.t = 0                    # 보고 있는 시간대 (0부터)
        self.bus_row = 0              # 다이나믹에서 고른 버스 (행 번호)
        self.case_has_vsc = True      # AC-only 케이스면 False
        # 변환기를 이상적으로 보았나 (2026-08-31). None=변환기 자체가 없다.
        # 「없음」 칩이 무엇 때문에 없는지 가르는 데 쓴다.
        self.vsc_ideal = None
        self.show_vsc = True          # 변환기 표는 있으면 늘 낸다 (2026-09-08 i23)
        self.show_violations = False  # 계통도 '위반 보기' 켜짐 여부
        # 계통도 배율 (2026-08-19). 계통도 위젯은 계산할 때마다 새로 만들어지므로
        # **여기에 들고 있다가 다시 넘긴다** — 안 그러면 계산 한 번에 100% 로 돌아간다.
        self.topo_zoom = 1.0
        self.graph_tab = 0            # 보고 있던 그래프 탭 (재생성 때 되돌리려고)
        # 차트를 여럿 위아래로 쌓는 탭(전압·위상)에서 **몇 번째를 보고 있나** (2026-08-28).
        #   쌓아 두면 한 장이 절반씩 나눠 가져 그래프 최소 높이가 425 로 뛰고, 그만큼
        #   표가 깎인다(창 1440px 아래에서는 표가 늘 제 몫을 못 받았다). ⇒ **한 장씩
        #   보이고 탭 줄 구석 단추로 고른다.** 탭은 「전압·위상」 하나로 그대로 둔다.
        self.plot_pick = 0
        # 아래쪽 표 탭도 같이 기억한다. **번호가 아니라 이름**으로 — 모드·VSC 표시에 따라
        # 탭 개수가 달라지고, 이름에도 건수가 붙는다("점검 (3)"·"계통 데이터 (2)").
        self.table_tab = "AC 결과"
        # 표 위 두 갈래 — "결과" | "시나리오" (2026-09-08 점검 i48).
        # 시나리오가 「AC 결과」·「점검」과 한 드롭다운에 섞여 있어, **결과 표 하나**
        # 처럼 보였다(사용자: *"시나리오를 표에 포함하지 말고 탭을 따로 만들어"*).
        self.pane = "결과"
        # ── 계통 조건 (PDR §7 2단계) ──
        # 원본 케이스는 읽고 나면 바뀌지 않는다. 그 위에 "바꾼 것" 목록만 얹는다.
        self.base_case = None         # 파일에서 읽은 원본 (scenario.apply 의 바탕)
        self.applied = []             # **지금 화면의 결과**를 만든 조건 (이미 계산된 것)
        self.changes = []             # 그 위에 얹었지만 **아직 계산 안 한** 것
        self.book = SC.Book()         # 담아 둔 시나리오
        # 결과 표를 어떤 열로 늘어놓고 보고 있나 — {표 이름: (열 번호, 오름/내림)}.
        # 🚨 **계산해도 유지한다** (2026-08-18 사용자 확정). 「전압 낮은 순」으로 보다가
        #    선로를 끄고 다시 계산하면 또 전압 낮은 순으로 보여야, 무엇이 달라졌는지
        #    바로 견줄 수 있다. 매번 풀리면 그때마다 다시 눌러야 한다.
        self.sort_by = {}
        self._applying_sort = False   # 되돌아 부르는 것을 막는 빗장 (아래 _sort_changed)
        self._strips = {}             # 표 위 띠 — 정렬만 바뀌면 이것만 다시 채운다
        self.res_find = ""            # 결과 표에서 찾는 버스 번호 (계통 데이터 탭과 별개)
        self._res_tables = {}         # {표 이름: (표, 열이름들)} — 찾기를 제자리에서 건다
        self._find_label = None       # "50줄 중 3줄" 을 적는 자리
        self._find_clear = None       # 「전부 보기」 — 만들어 두고 숨김만 바꾼다
        self.grid_key = "AC_Line_dat" # 계통 데이터 탭에서 보고 있는 표
        self.grid_find = ""           # 계통 데이터 탭에서 찾는 버스 번호
        self._grid_rows = []          # 화면 줄 → 진짜 줄 (찾기로 좁혔을 때)
        # 부하 일괄 증감 슬라이더 — 끌고 있는 동안 화면을 다시 그리면 손잡이가 사라진다.
        # 그래서 놓았을 때(sliderReleased) 또는 잠깐 멈췄을 때만 반영한다.
        self._load_pending = 1.0
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.timeout.connect(lambda: self.scale_loads(self._load_pending))
        # 🚨 **처음엔 전부 보인다** (2026-09-08 점검 i26). 예전에는 `TABLE_SPECS` 에서
        #    기본 표시로 켜 둔 칸만 나왔는데, 꺼진 열이 있다는 것 자체가 화면에 안
        #    보여서 「그 값은 앱이 안 준다」로 읽혔다(머리줄 「열 선택 8/13」 은 누르기
        #    전엔 뜻이 안 통한다). 좁히는 것은 사용자가 고르면 된다.
        self.visible = {k: {n for n, _ in v} for k, v in TABLE_SPECS.items()}
        # 위아래 나눔 자리 — 탭 갈래마다 따로 ("grid" = 계통 데이터 · "other" = 나머지)
        self.split_sizes = {}
        # 계통 데이터 표를 다시 그릴 때 보던 자리로 되돌리려고 들고 있는 것
        # (2026-08-13 사용자: "숫자 하나 넣을 때마다 가로 스크롤을 다시 해야 한다")
        self._grid_tb = None           # 지금 화면의 표 (미는 쪽)
        self._grid_frozen = None       # 왼쪽에 고정한 표 (상태 + 첫 번호 열)
        self._grid_off = 0             # 화면 열 = 데이터 열 + off
        self._grid_view = None         # (가로, 세로) 스크롤 자리
        self._grid_focus = None        # 다음에 고를 칸 (화면 줄, 화면 열)
        self.setWindowTitle("UNIGRID")
        # 🚨 화면보다 큰 창으로 열면 **아래가 잘린 채 줄일 수도 없다**(2026-08-13).
        #    맥북 화면은 세로가 900 언저리라 950 도 넘친다. 쓸 수 있는 넓이에 맞춘다.
        w0, h0 = 1440, 950
        scr = QApplication.primaryScreen()
        if scr is not None:
            a = scr.availableGeometry()
            w0 = min(w0, a.width() - 40)
            h0 = min(h0, a.height() - 40)
        self.resize(w0, h0)
        # 2026-11-15 — 안의 것을 스크롤에 담아 창 최소 크기가 풀렸다(전에는 개요 1250 × 902).
        # 너무 작아지지는 않게 바닥만 둔다.
        self.setMinimumSize(1040, 660)
        self.build()

    # ── 테마 ──
    @property
    def c(self):
        # `_c_over` = 사이드바가 케이스 카드를 제 색(진한 판 위)으로 만들 때 잠깐 건다 (`navside.NavSide`)
        return getattr(self, "_c_over", None) or (DARK if self.dark else LIGHT)

    def qss(self):
        c = self.c
        return f"""
        /* 🚨 **중간 위젯이 불투명하면 유리가 막힌다** (2026-09-08).
           예전에는 `QMainWindow, QWidget, QDialog` 를 한 줄로 묶어 **모든 위젯**에
           `bg` 를 칠했다. 그래서 바탕(`Ground`)이 얼룩을 그려도 그 위에 얹힌 이름
           없는 QWidget 들이 전부 덮어 **결과 판이 `#f2f2f7` 그대로**였다(실측).
           ⇒ 바탕을 칠하는 것은 **창과 대화상자뿐**이고, 보통 위젯은 **투명**이다.
              색과 글꼴은 그대로 물려준다. */
        QWidget {{ background:transparent; color:{c['text']};
            font-family:'Apple SD Gothic Neo','Helvetica Neue',sans-serif; }}
        QLabel, QCheckBox {{ background:transparent; }}
        /* 🚨🚨 **창·대화상자 규칙은 반드시 `QWidget` 규칙 «뒤에»** (2026-09-11).
           Qt 스타일시트에서 `QDialog` 와 `QWidget` 은 **무게가 같다** — 하위 클래스라고
           특별 대우가 없고, 무게가 같으면 **뒤에 온 규칙이 이긴다.** 이 줄이 위에 있을
           때는 `QWidget {{ transparent }}` 가 이겨서 **대화상자가 전부 투명**했다(맥·윈도우
           실측 알파 0). 윈도우는 투명한 창 뒤를 **검정**으로 칠해 불러오기 창이 까맣게
           떴다(사용자 지적 — *"이거 왜 검은색이야"*). `QMessageBox`·`QInputDialog` 도
           `QDialog` 의 하위라 이 한 줄로 같이 고쳐진다. */
        QMainWindow, QDialog {{ background:{c['bg']}; }}
        /* 툴팁 — 전용 규칙이 없으면 macOS 는 배경을 어둡게 그리는데 위 QWidget
           규칙이 글자색까지 어둡게 강제해 '어두운 글자+어두운 배경'으로 안 보였다
           (계통도 위반 요소 손말풍선이 빈 상자로 떴다). 배경·글자·테두리를
           카드와 같은 팔레트로 못 박아 라이트·다크 양쪽에서 읽히게 한다. */
        QToolTip {{ background:{c['surface']}; color:{c['text']};
            border:1px solid {c['border']}; padding:6px 9px; font-size:13px; }}
        /* 🍎 **시작 화면도 떠 있는 유리다** (2026-09-09 사용자 지정 —
           *"여기에 요소들도 유리 floating 느낌나게"*). 파일 놓는 자리와
           최근 목록이 결과 화면의 판 셋과 같은 재질이라야 앱이 한 벌로 보인다.
           ⚠️ 점선 테두리를 뺐다 — 점선은 «임시로 그린 자리» 로 보여 유리와 안 맞는다.
              끌어온 파일이 창 위에 올라오면 그때 점선이 나타난다(`set_hot`). */
        /* ⚠️ 이 둘은 `GlassCard` 가 **직접 그린다** — QSS 로 배경을 주면
              그 위에 덮여 유리가 안 보인다. 여기서는 비워 둔다. */
        #dropzone, #recentcard {{ background:transparent; border:none; }}
        QPushButton#recentrow {{ background:transparent; border:none;
            border-radius:10px; text-align:left; padding:9px 14px;
            font-size:14px; font-weight:400; color:{c['text']}; }}
        QPushButton#recentrow:hover {{ background:{c['accent_soft']};
            color:{c['accent']}; }}
        QPushButton#recentrow:pressed {{ background:{c['accent']}; color:{c['on_accent']}; }}
        /* 🍎 **유리** — 카드는 불투명 판이 아니라 **반투명 유리**다. 뒤 바탕의
           색 얼룩(`Ground`)이 비쳐 들어온다. 테두리는 선이 아니라 **밝은
           하이라이트** — 애플 유리의 가장자리 빛을 흉내낸다.
           ⚠️ 표·그래프가 앉는 판은 **덜 비치게**(0.86) 한다 — 숫자와 선이
              얼룩과 겹치면 읽기 어렵다. 유리는 «틀» 에 쓰고 «내용» 에는 덜 쓴다. */
        #card {{ background:{c['glass']}; border:1px solid {c['glass_edge']};
            border-radius:12px; }}
        #plot {{ background:{c['glass_plot']}; border:1px solid {c['glass_edge']};
            border-radius:14px; }}
        /* ⚠️ 유리 판 **안** 에 놓이는 것들 — 여기에 또 배경을 주면 «상자 속 상자» 다. */
        #plotclear {{ background:transparent; border:none; }}
        /* 🍎 **머리줄·바닥줄은 판이 아니다** — 바탕 위에 글자만 얹는다. 이 둘까지
           판으로 만들면 화면이 판 다섯 장으로 갈려 어느 것이 «내용» 인지 흐려진다.
           떠 있는 판은 셋뿐이다 — **사이드바 · 그래프 · 표**(2026-09-08 사용자 지정). */
        #topbar, #statusbar {{ background:transparent; border:none; }}
        /* 사이드바는 떠 있는 **판**이다 — 둥근 모서리에 옅은 가장자리 빛.
           결과가 아니므로 거의 불투명하다. */
        /* ⚠️ 배경·테두리는 `GlassCard`·`GlassTabs` 가 **직접 그린다**.
              QSS 로 여기에 색을 주면 그 위에 덮여 유리가 사라진다. */
        #sidebar {{ background:transparent; border:none; }}
        /* 결과가 나오는 두 판 — 여기가 유리다. */
        /* ⚠️ `top:-1px` 은 판을 탭 줄 **위로 끌어올려 붙이는** 값이다(웹 탭의 관습).
           떠 있는 판에서는 탭이 판을 파고든 것처럼 보인다(2026-09-08 사용자 지적).
           양수로 바꿔 **탭 줄과 판 사이를 벌린다.** */
        QTabWidget#graphpanel::tab-bar {{ alignment:left; left:10px; }}
        QTabWidget#graphpanel::pane {{ background:transparent;
            border:none; top:6px; }}
        QWidget#tablepanel {{ background:transparent; border:none; }}
        /* 🍎 맥 단추 = **테두리 없는 옅은 판**. 누를 수 있다는 것은 테두리가 아니라
           바탕색이 알린다. 굵기는 500 까지만 쓴다(600 이상은 맥에서 무겁다). */
        QPushButton {{ background:{c['glass']}; color:{c['text']};
            border:1px solid {c['glass_edge']}; border-radius:9px;
            padding:10px 17px; font-size:14px; font-weight:500; }}
        QPushButton:hover {{ background:{c['accent_soft']}; color:{c['accent']}; }}
        /* 🍎 맥 단추는 누르는 **그 순간** 어두워진다. Qt QSS 에는 전환 시간이 없어
           애니메이션은 못 넣지만, `:pressed` 상태 하나로 «눌렸다» 는 느껴진다. */
        QPushButton:pressed {{ background:{c['accent']}; color:{c['on_accent']}; }}
        QPushButton#seg_off:pressed {{ background:{c['accent_soft']};
            color:{c['accent']}; }}
        QPushButton#primary {{ background:{c['accent']}; color:{c['on_accent']};
            border:none; font-weight:500; }}
        QPushButton#primary:hover {{ background:{c['accent']}; color:{c['on_accent']}; }}
        /* 🚨 잠긴 단추가 **잠겨 보이게** (2026-08-31). 이 규칙이 없어 `setEnabled(False)`
           를 걸어도 파란색 그대로였다 — 눌러도 아무 일 없는 파란 단추가 된다. */
        QPushButton:disabled {{ background:{c['side']}; color:{c['border']};
            border:none; }}
        QPushButton#primary:disabled {{ background:{c['side']}; color:{c['border']};
            border:none; font-weight:500; }}
        /* ⚠️ 세로 여백 8px 은 **표 셀 안**(행 30px)에서 넘친다 — 「켜짐」이
           24px 자리에 33px 을 요구했다. 5px 으로 줄여 두 자리 다 맞춘다. */
        QPushButton#seg_on {{ background:{c['accent']}; color:{c['on_accent']};
            border:none; font-weight:500; font-size:14px;
            border-radius:8px; padding:5px 14px; }}
        QPushButton#seg_off {{ background:transparent; color:{c['muted']};
            border:none; font-size:14px; font-weight:400;
            border-radius:8px; padding:5px 14px; }}
        QPushButton#seg_off:hover {{ background:{c['accent_soft']};
            color:{c['accent']}; }}
        /* 🚨 **잠긴 것과 안 고른 것이 생김새가 같았다** (2026-09-08 점검 i61·i67).
           `#seg_off` 에 `:disabled` 규칙이 없어 잠근 「다이나믹」·「PV·QV 곡선」이
           그냥 «지금 안 고른 것» 으로 보였다 — 눌러도 아무 일이 없는데 왜 그런지는
           풍선말을 띄워야 알았다. 점선 테두리로 «여긴 못 간다» 를 눈에 보이게 한다.
           (`#seg_off:disabled` 로 안 하고 이름을 따로 준 까닭 = 테두리가 생기면서
            높이가 2px 늘어 옆 단추와 어긋나므로 안쪽 여백을 같이 줄여야 한다.) */
        QPushButton#seg_lock {{ background:transparent; color:{c['muted']};
            border:1px dashed {c['border']}; font-size:14px;
            border-radius:8px; padding:4px 13px; }}
        /* 🚨 **그래프와 표 사이 손잡이가 안 보였다** (2026-09-08 사용자 지적 —
           *"여기 파란색 박스 쳐놓은 곳을 드래그하면 그래프 크기를 늘리고 줄일 수
           있잖아. 이거의 역할을 조금 더 티나게 해줘"*).
           `QSplitter::handle` 규칙이 **QSS 에 하나도 없어** Qt 기본값(빈 띠)으로
           그려졌다 — 끌 수 있는 것인 줄 모른다.
           ⇒ 옅은 띠 + 위아래 가는 선, 그리고 **가운데에 잡는 표시**를 그린다
             (`_GripHandle` — QSS 로는 가운데 무늬를 못 그린다).
           마우스를 올리면 강조색으로 바뀐다. */
        QSplitter::handle:vertical {{ background:{c['bg']};
            border-top:1px solid {c['border']};
            border-bottom:1px solid {c['border']}; }}
        QSplitter::handle:vertical:hover {{ background:{c['accent_soft']};
            border-top:1px solid {c['accent']};
            border-bottom:1px solid {c['accent']}; }}
        QSplitter::handle:vertical:pressed {{ background:{c['accent_soft']}; }}
        /* 🚨 **탭 줄 구석 단추는 탭 높이에 눌린다** (2026-09-08 실측 —
           「그래프 접기」가 32px 자리에 39px 을 요구해 **「그래쁘 섭기」로 잘렸다**).
           08-28 에 `[전압|위상각]` 이 「선압」·「뷔상삭」이 된 것과 같은 자리다.
           ⇒ 이 자리 단추는 **안쪽 여백을 줄여** 요구 높이를 자리에 맞춘다.
           ⚠️ 한글은 라틴 글자보다 위아래로 크다 — 같은 여백에서 라틴은 멀쩡한데
              한글만 잘리므로, 영문 단추로 시험하면 안 걸린다. */
        QPushButton#corner {{ padding:5px 13px; font-size:14px; }}
        QPushButton#accentline {{ border:1px solid {c['accent']};
            color:{c['accent']}; font-weight:600; }}
        QPushButton#accentline:hover {{ background:{c['accent_soft']}; }}
        QPushButton#link {{ background:transparent; border:none;
            color:{c['muted']}; font-size:13px; padding:4px 6px;
            text-decoration:underline; }}
        QPushButton#link:hover {{ color:{c['accent']}; }}
        /* 잠긴 링크 단추는 **눌리는 것과 달라 보여야** 한다 — 밑줄을 빼고 흐리게.
           2026-09-01 「잠긴 단추가 안 고른 단추와 생김새가 같다」와 같은 자리다
           (접기 단추가 비교·곡선에서 잠기는데 회색 링크 그대로였다). */
        QPushButton#link:disabled {{ color:{c['border']}; text-decoration:none; }}
        QComboBox, QSpinBox, QLineEdit {{ background:{c['glass']}; color:{c['text']};
            border:1px solid {c['glass_edge']}; border-radius:9px;
            padding:9px 12px; font-size:15px; }}
        QComboBox {{ combobox-popup:0; }}
        QComboBoxPrivateContainer {{ background:{c['surface']}; border:none; }}
        #combopop {{ background:transparent; border:none; }}
        QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{
            border:2px solid {c['accent']}; padding:7px 10px; }}
        /* 🚨 **펼친 목록은 창이 따로다** — `QWidget` 을 투명으로 바꾼 뒤 이 창이
           바탕을 잃고 **검게** 떴다(2026-09-08 사용자 지적). 목록은 판 위가 아니라
           떠 있는 창이므로 **불투명**으로 못 박는다. */
        QComboBox QAbstractItemView {{ background:{c['surface']}; color:{c['text']};
            border:1px solid {c['border']}; border-radius:10px;
            padding:5px; outline:none;
            selection-background-color:{c['accent_soft']};
            selection-color:{c['text']}; }}
        QComboBox QAbstractItemView::item {{ padding:7px 10px; border-radius:6px;
            min-height:22px; }}
        QComboBox QAbstractItemView::item:selected {{
            background:{c['accent_soft']}; color:{c['accent']}; }}
        QMenu {{ background:{c['surface']}; color:{c['text']};
            border:1px solid {c['border']}; border-radius:10px; padding:5px; }}
        QMenu::item {{ padding:7px 14px; border-radius:6px; }}
        QMenu::item:selected {{ background:{c['accent_soft']}; color:{c['accent']}; }}
        /* 화살표는 `Combo` 가 직접 그린다 — QSS 로는 삼각형을 못 만든다.
           여기서는 **자리만** 비워 둔다(오른쪽 26px). */
        QComboBox::drop-down {{ subcontrol-origin:padding; subcontrol-position:right;
            width:26px; border:none; background:transparent; }}
        QComboBox::down-arrow {{ image:none; width:0; height:0; }}
        QComboBox:hover {{ background:{c['accent_soft']}; }}
        /* 🍎 맥 탭은 **밑줄이 아니라 알약**이다(Finder 보기 전환·설정 창).
           밑줄은 웹 쪽 관습이고, 맥에서는 고른 것에 옅은 판을 깐다. */
        /* ⚠️ 안쪽 탭은 **판이 아니다** — 표 판 안에 또 판이 생기면 테두리가 겹쳐
           «상자 속 상자» 가 된다. 판 노릇은 `#tablepanel`·`#graphpanel` 만 한다. */
        QTabWidget::pane {{ border:none; background:transparent; top:6px; }}
        /* ⚠️ 탭 높이가 곧 **구석 위젯이 쓸 수 있는 자리**다 — 구석의 `[전압|위상각]`
           이 넘쳐 아래 판과 겹쳤다(2026-09-08 사용자 지적). 세로 여백을 한 단
           올려 구석에 34px 을 만들어 준다. */
        QTabBar::tab {{ background:transparent; color:{c['muted']};
            padding:15px 18px; font-size:14px; border:none;
            margin-right:4px; min-width:96px; border-radius:7px; }}
        QTabBar::tab:hover {{ background:{c['accent_soft']}; color:{c['accent']}; }}
        QTabBar::tab:selected {{ background:{c['surface']}; color:{c['text']};
            font-weight:500; }}
        /* 앱 2.3 — 그래프 탭은 알약을 `_PillTabBar` 가 직접 그려 미끄러지게 한다 */
        QTabBar#pillbar::tab:selected {{ background:transparent; }}
        /* 🍎 **맥 표에는 세로 격자선이 없다** — 가로 구분선만 아주 옅게 긋고,
           숫자는 오른쪽·이름은 왼쪽으로 맞춘다(활성 상태 보기가 색을 딱 두 곳만
           쓰고도 안 답답한 까닭 · `디자인_참고/갈래별/다1_ActivityMonitor.png`).
           줄무늬도 뺀다 — 구분선이 이미 줄을 가른다.
           🚨 줄무늬 색은 **팔레트에서** 준다(2026-09-08 점검 i63). 안 주면 Qt
              기본값(밝은 회색)이 쓰여 어두운 화면에서 짝수 줄이 안 읽혔다.
              지금은 바탕과 같은 값을 줘 «줄무늬 없음» 을 만든다. */
        QTableWidget {{ background:transparent; border:none;
            gridline-color:transparent; font-size:14px;
            alternate-background-color:transparent; color:{c['text']}; }}
        QTableWidget::item {{ border-bottom:1px solid {c['hair']};
            padding:0px 4px; }}
        QTableWidget::item:selected {{ background:{c['accent_soft']};
            color:{c['text']}; }}
        QHeaderView::section {{ background:transparent; color:{c['muted']};
            border:none; border-bottom:1px solid {c['border']};
            padding:9px; font-size:12px; font-weight:700; }}
        QCheckBox {{ font-size:14px; color:{c['text']}; spacing:7px; }}
        /* 🚨 **계산 중 창이 비어 보였다** (2026-09-08 사용자: *"조류해석하는 중이
           아무것도 안떠"*). `QProgressDialog` 는 자기 라벨과 진행 막대를 직접
           만드는데, `QWidget` 을 투명으로 돌린 뒤 그 막대에 아무 규칙이 없어
           **아무것도 안 그려졌다.** 창·글자·막대를 다 못 박는다. */
        QProgressDialog {{ background:{c['surface']}; }}
        QProgressDialog QLabel {{ color:{c['text']}; font-size:15px;
            padding:4px 2px; }}
        QProgressBar {{ background:{c['bg']}; border:none; border-radius:5px;
            height:8px; text-align:center; color:transparent; }}
        QProgressBar::chunk {{ background:{c['accent']}; border-radius:5px; }}
        QScrollArea {{ border:none; background:transparent; }}
        /* 🍎 맥 스크롤 막대 = **가는 알약**, 홈은 안 그린다. */
        /* 🚨 가로·세로 스크롤바가 만나는 **구석**. 규칙이 없으면 Qt 기본 스타일이
           «┌» 모양 검은 선을 그린다 — 유리 판 오른쪽 아래에 떠서 거슬린다
           (2026-09-09 실측). 표의 머리글 구석 단추도 같이 지운다. */
        QAbstractScrollArea::corner {{ background:transparent; border:none; }}
        QTableCornerButton::section {{ background:transparent; border:none; }}
        QScrollBar:vertical {{ background:transparent; width:11px; margin:0; }}
        QScrollBar:horizontal {{ background:transparent; height:11px; margin:0; }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background:{c['border']}; border-radius:5px; min-height:28px;
            min-width:28px; }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
            background:{c['muted']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height:0; width:0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
        """

    # ── 전체 다시 그리기 ──
    def build(self):
        self.setStyleSheet(self.qss())
        # 화면을 갈아끼우면 옛 위젯 참조는 버린다 (지워진 위젯을 만지면 죽는다)
        self.dropzone = self.drop_label = self._tabs = self._split = None
        self._tab_pick = None          # 표 고르는 드롭다운도 같이 버린다
        # ⚠️ 다이나믹으로 보는 중에 1시각 계통을 열면 **잠긴 모드에 갇힌다**
        #    (단추가 잠겨 돌아갈 길이 없다). 스냅샷으로 되돌린다 (2026-09-01).
        if self.mode == "다이나믹" and self.dynamic_why():
            self.mode = "스냅샷"
        if self.sol is None:
            # 🚨 **시작 화면도 `Ground` 위에 얹는다** (2026-09-08 사용자: *"시작 화면도
            #    왜 검은색이라 이상하고"*). `QWidget` 을 투명으로 바꾼 뒤로 바탕을
            #    그리는 것은 `Ground` 뿐인데, 시작 화면은 그걸 안 거쳐서 **아무도
            #    안 칠한 검은 창**이 됐다. 계산 중 화면도 같은 자리다.
            g = Ground(self.c, self.dark)
            gh = QHBoxLayout(g)                 # 앱 2.3 — 시작 화면에도 사이드바
            gh.setContentsMargins(12, 12, 0, 12)
            gh.setSpacing(0)
            # 시작 화면에는 사이드바를 두지 않는다 (2026-11-03 사용자: 「첫화면에서 사이드바 필요없잖아」) —
            # 열기 전엔 메뉴가 다 잠겨 있어 자리만 먹었다. 정보 · 화면 밝기는 시작 화면 안에 둔다.
            gh.addWidget(self.start_page(), 1)
            self.setCentralWidget(g)
            return
        root = Ground(self.c, self.dark)
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        # 앱 2.3 — 위쪽 줄(로고 · 불러오기 · 내보내기 · 엑셀로 만들기 · 테마 · 정보)은 전부
        # B 꼴 사이드바(`rail`)로 옮겼다. `topbar()` 는 남겨 두지만 부르지 않는다.
        mid = QHBoxLayout()
        # 판이 «떠» 보이려면 가장자리와 판 사이에 바탕이 보여야 한다
        mid.setContentsMargins(12, 12, 14, 12)
        mid.setSpacing(12)
        # 앱 2.3 (2026-11-03 사용자가 칸마다 고름) — 검은 아이콘 띠와 설정 판을 **사이드바 하나**로
        # 합쳤다(`navside.py`). 해법은 페이지 머리 오른쪽(`page_head`)으로 갔다.
        # 옛 설정 판은 고를 것이 따로 있는 두 곳(PV·QV 곡선 · 비교)에서만 입력 칸만 담아 남긴다.
        mid.addWidget(self.nav_side())
        extra = self.extra_panel()
        self._side_sa = None
        if extra is not None:
            mid.addWidget(extra)
        col = QVBoxLayout()
        col.setSpacing(12)
        col.addWidget(self.page_head())
        self._center_w = self.center()      # 전환 모션을 걸 자리
        col.addWidget(self._center_w, 1)
        mid.addLayout(col, 1)
        v.addLayout(mid, 1)
        v.addWidget(self.statusbar())

    def _old_side_panel(self, mid):
        """옛 설정 판(앱 2.3 사이드바 하나 전) — 지금은 부르지 않는다."""
        side = QScrollArea()
        side.setWidgetResizable(True)
        side.setFrameShape(QFrame.NoFrame)
        side.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        _sw = self.sidebar() if self.side_open else self.side_rail()
        _box = QWidget(); _box.setAttribute(Qt.WA_TranslucentBackground)
        _bl = QVBoxLayout(_box); _bl.setContentsMargins(0, 0, 0, 0)
        _bl.addWidget(_sw); _bl.addStretch(1)
        side.setWidget(_box)
        side.setFixedWidth(280 if self.side_open else 56)
        side.setMinimumHeight(0)
        float_panel(side, self.dark)
        self._side_sa = side                # 접기/펼치기 모션을 걸 자리
        mid.addWidget(side)

    # ── 사이드바 하나 · 페이지 머리 (앱 2.3 · 2026-11-03) ──────────────────
    def nav_side(self):
        import navside
        self._nav = navside.NavSide(self, _rail_icon)
        # 🚨 사이드바가 창 최소 세로를 정하고 있었다(826 px · 2026-11-15 실측) — 13인치 화면에서
        #    아래 상태 줄이 화면 밖으로 나갔다. 스크롤에 담아 창이 낮으면 사이드바 안이 밀리게 한다
        #    (막대는 안 그린다 — 폭 256 을 그대로 쓴다. 휠 · 트랙패드로 민다).
        sa = _clear_scroll(self._nav, vbar=False)
        sa.setFixedWidth(navside.WIDTH)
        return sa

    def open_convert(self):
        ConvertDialog(self, self.c).exec()

    def open_about(self):
        AboutDialog(self, self.c).exec()

    def nav_go(self, name):
        """사이드바 메뉴를 누르면. 「결과」 = 개요부터 · 「점검」 · 「계통 데이터」 = 자세히 화면의 그 표."""
        if name in ("시나리오", "PV·QV 곡선"):
            self.rail_go(name)
            return
        if self.task != "조류계산":
            self.task = "조류계산"
        self.pane = "결과"
        if name == "결과":
            self.overview_on = True
            if _tab_base(getattr(self, "table_tab", "")) in ("점검", "계통 데이터"):
                self.table_tab = "AC 결과"
        else:
            if self.mode == "비교":
                self.mode = "스냅샷"
            self.overview_on = False
            self.table_tab = name
        self.rebuild()
        reveal(getattr(self, "_center_w", None))

    def page_head(self):
        """페이지 머리 — 왼쪽 경로 · 큰 제목, 오른쪽 끝 해법(H1). 설명 줄은 화면 구성을 정한 뒤."""
        c = self.c
        on = self._rail_on() or ""
        if on in ("시나리오", "PV·QV 곡선"):
            path, title = "해석", on
        elif on == "결과":
            # 제목이 「스냅샷」 뿐이라 무엇의 화면인지 안 보였다 (2026-11-15) — 「결과」 를 앞에 둔다
            path = "조류계산"
            title = {"스냅샷": "결과 개요", "다이나믹": "결과 개요 · 다이나믹", "비교": "결과 · 비교"}.get(self.mode, "결과")
            if self.mode == "스냅샷" and not getattr(self, "overview_on", True):
                title = "결과 · 그래프와 표"
            elif self.mode == "다이나믹" and not getattr(self, "overview_on", True):
                title = "결과 · 다이나믹 그래프와 표"
        elif on:
            path, title = "조류계산", on
        else:
            path, title = "", "계통 파일을 여세요"
        w = QWidget()
        w.setAttribute(Qt.WA_TranslucentBackground)
        h = QHBoxLayout(w)
        h.setContentsMargins(6, 2, 2, 0)
        # 2026-11-15 — 「← 개요」 가 제목 아래에서 한 줄(40 px)을 따로 먹어 그래프가 그만큼 낮았다.
        # 제목 왼쪽의 둥근 단추로 올린다.
        if (self.sol is not None and on == "결과" and self.mode in ("스냅샷", "다이나믹")
                and not getattr(self, "overview_on", True)):
            back = QPushButton("←")
            back.setCursor(Qt.PointingHandCursor)
            back.setToolTip("결과 개요로 돌아갑니다")
            back.setFixedSize(40, 40)
            back.setStyleSheet(f"QPushButton {{ background:{c['surface']}; color:{c['text']};"
                               f"border:1px solid {c['border']}; border-radius:20px; font-size:17px;"
                               "font-weight:700; padding:0px; }"
                               f"QPushButton:hover {{ background:{c['accent_soft']}; }}")
            back.clicked.connect(self.open_overview)
            h.addWidget(back, 0, Qt.AlignBottom)
            h.addSpacing(8)
        lv = QVBoxLayout()
        lv.setSpacing(0)
        if path:
            pl = QLabel(path)
            pl.setStyleSheet(f"color:{c['muted']};font-size:12px;background:transparent;")
            lv.addWidget(pl)
        tl = QLabel(title)
        tl.setStyleSheet(f"color:{c['text']};font-size:26px;font-weight:800;background:transparent;")
        lv.addWidget(tl)
        h.addLayout(lv)
        h.addStretch()
        # 2026-11-15 — 개요 · 점검에서 **어느 시각을 보는지** 고르는 자리. 여태 개요에는 아예 없었고
        # (24시간 계통도 1 H 만 보였다), 점검에서는 한 줄을 따로 먹었다. 제목 줄 오른쪽에 둔다.
        if (self.sol is not None and self.mode == "스냅샷" and self.task != "PV·QV 곡선"
                and int(getattr(self.sol, "n_time", 1) or 1) > 1
                and (on == "점검" or (on == "결과" and getattr(self, "overview_on", True)))):
            vp = self.view_picker()
            if vp is not None:
                tbx = QFrame()
                tbx.setObjectName("headtime")
                tbx.setStyleSheet(f"#headtime {{ background:{c['surface']}; border:1px solid {c['border']};"
                                  f"border-radius:12px; }}"
                                  "#headtime QComboBox { border:none; background:transparent; }")
                th = QHBoxLayout(tbx)
                th.setContentsMargins(14, 4, 6, 4)
                th.addWidget(vp)
                h.addWidget(tbx, 0, Qt.AlignBottom)
                h.addSpacing(8)
        if self.sol is not None and self.task != "PV·QV 곡선":
            box = QFrame()
            box.setObjectName("headsolver")
            box.setStyleSheet(f"#headsolver {{ background:{c['surface']}; border:1px solid {c['border']};"
                              f"border-radius:12px; }}"
                              "#headsolver QComboBox { border:none; background:transparent; }")
            bh = QHBoxLayout(box)
            bh.setContentsMargins(14, 4, 6, 4)
            bh.setSpacing(8)
            sl = QLabel("해법")
            sl.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:600;background:transparent;")
            bh.addWidget(sl)
            bh.addLayout(self._solver_picker(heading=False))
            h.addWidget(box, 0, Qt.AlignBottom)
        return w

    def extra_panel(self):
        """고를 것이 따로 있는 화면(PV·QV 곡선 · 비교)에서만 입력 칸 판을 낸다."""
        # 2026-11-15 — 입력은 그 화면 맨 위 카드로 갔다(`_input_card`). 사이드바 옆에 판이 한 칸 더
        # 생겨 제목과 본문이 270 px 밀리던 것을 없앤다. 아래는 되살릴 때를 위해 남겨 둔다.
        return None
        sb = GlassCard(self.c, self.dark, radius=16, tint=(0.80, 0.66))
        sb.setObjectName("sidebar")
        sb.setFixedWidth(270)
        v = QVBoxLayout(sb)
        v.setContentsMargins(14, 16, 14, 14)
        v.setSpacing(8)
        if self.task == "PV·QV 곡선":
            self.curve_controls(v)
        else:
            self._compare_controls(v)
        v.addStretch()
        side = QScrollArea()
        side.setWidgetResizable(True)
        side.setFrameShape(QFrame.NoFrame)
        side.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side.setWidget(sb)
        side.setFixedWidth(270)
        float_panel(side, self.dark)
        return side

    # ── 개요 ↔ 자세히 (앱 2.3) ─────────────────────────────────────────
    # 카드 → 자세한 화면 (M1 · 2026-11-03) — 이미 있는 「자세히」 화면에서 카드에 맞는 탭을 골라 연다
    CARD_GO = {"viol": (None, "점검"), "kviol": (None, "점검"),
               "volt": ("전압·위상", "AC 결과"), "kvolt": ("전압·위상", "AC 결과"),
               "load": ("부하율", "선로 조류"), "kload": ("부하율", "선로 조류"),
               "supply": (None, "AC 결과"), "topo": ("토폴로지", None)}

    def _card_shot(self, key):
        """개요 카드 하나의 자리 · 그림 · 바탕색 — 움직임(E2)에 쓴다."""
        import overview
        host = getattr(self, "_center_w", None)
        card = getattr(self, "_ov_cards", {}).get(key)
        if host is None or card is None:
            return None
        try:
            r = QRect(card.mapTo(host, QPoint(0, 0)), card.size())
            fill = "#15171c" if (key == "volt" and overview.CHART_STYLE == "bars") else self.c["surface"]
            return r, card.grab(), fill
        except RuntimeError:
            return None

    def open_card(self, key):
        """개요 카드를 누르면 — 그 카드가 떠서 커진다(D2 · 2026-11-03). 다른 페이지로 안 넘어간다."""
        import overview
        overview.open_float(self, key)

    def open_overview(self):
        import overview
        key = getattr(self, "_ov_last", None)
        host = getattr(self, "_center_w", None)
        det_pm = host.grab() if (key and host is not None) else None
        self.overview_on = True
        self.rebuild()
        if det_pm is None:
            return
        cw = self.centralWidget()
        if cw is not None and cw.layout() is not None:
            cw.layout().activate()
        shot = self._card_shot(key)
        if shot:
            r, _cpm, fill = shot
            overview.ExpandOverlay(self._center_w, self._center_w.grab(), det_pm, r, fill,
                                   self.c["bg"], back=True)

    def open_details(self):
        self.overview_on = False
        self.rebuild()

    def goto_time(self, k):
        """다이나믹 개요에서 시각 하나를 누르면 — 그 시각의 스냅샷 개요로 간다 (2026-11-15)."""
        n_t = int(getattr(self.sol, "n_time", 1) or 1) if self.sol is not None else 1
        self.t = max(0, min(n_t - 1, int(k)))
        self.mode = "스냅샷"
        self.overview_on = True
        self.rebuild()
        reveal(getattr(self, "_center_w", None))

    def open_topology(self):
        """개요에서 계통도로 — 자세히 화면의 토폴로지 탭을 연다."""
        names = [n for n, _p, _l in GRAPHS.get(self.mode, [])]
        if "토폴로지" in names:
            self.graph_tab = names.index("토폴로지")
        self.numbers = False
        self.overview_on = False
        self.rebuild()

    def rebuild(self):
        self._float = None      # 떠 있던 카드는 옛 화면과 함께 지워진다
        self._strips = {}       # 옛 띠는 곧 지워진다 — 죽은 위젯을 붙들지 않는다
        self._res_tables = {}
        self._find_label = None
        self._find_clear = None
        self._head_res = []     # 죽은 위젯을 `_update_head_vis` 가 만지지 않게
        self._col_btn = None
        self._save_grid_view()
        # 그리기 **전에** 접힘 상태를 자리에 맞춘다. `_table_tab_changed` 에서도 부르지만
        # 그 길로만 오는 게 아니다 — 새 파일을 열 때 앞 파일의 탭이 그대로 남아 있고,
        # 표 한 칸을 고쳐도 여기로 온다. 여기서 맞춰 두면 어느 길로 와도 같아진다.
        # (다시 그리는 중이므로 돌아온 값은 안 본다 — 곧 그릴 화면이 이미 새 상태다.)
        self._fold_for_room()
        self.build()
        # 앱 2.3 — 고른 단추가 바뀐 묶음은 알약을 옛 자리에서 민다(자리가 잡힌 뒤라 다음 차례에)
        self._seg_prev = getattr(self, "_seg_prev", {})
        QTimer.singleShot(0, lambda: slide_segs(self, self._seg_prev, self.c["accent"]))

    # ── 계통 데이터 표의 "보던 자리" ───────────────────────────────────
    # 값을 한 칸 고칠 때마다 화면을 통째로 다시 그리므로, 아무것도 안 하면 표가
    # 맨 왼쪽으로 돌아간다. 조정 열은 19열 중 14~19열이라 **매번 오른쪽 끝까지
    # 다시 밀어야 했다**(2026-08-13 사용자 지적). 자리를 기억했다가 되돌린다.

    def _save_grid_view(self):
        """지금 표가 어디를 보고 있었는지 적어 둔다."""
        tb = getattr(self, "_grid_tb", None)
        if tb is None:
            return
        try:
            self._grid_view = (tb.horizontalScrollBar().value(),
                               tb.verticalScrollBar().value())
        except RuntimeError:        # 이미 지워진 위젯
            pass
        self._grid_tb = self._grid_frozen = None

    def _restore_grid_view(self, tb):
        """되돌린다 — 자리를 먼저 맞추고, 다음에 칠 칸을 고른다."""
        try:
            if self._grid_view:
                h, v = self._grid_view
                tb.horizontalScrollBar().setValue(h)
                tb.verticalScrollBar().setValue(v)
            spot = getattr(self, "_grid_focus", None)
            if spot:
                r, cc = spot
                if r < tb.rowCount() and cc < tb.columnCount():
                    tb.setCurrentCell(r, cc)
                    it = tb.item(r, cc)
                    if it is not None:
                        tb.scrollToItem(it)   # 이미 보이면 안 움직인다
                    tb.setFocus()
                self._grid_focus = None
        except RuntimeError:
            pass

    # ── 상단 ──
    # ── 앱 2.3 — B 꼴 사이드바 (2026-11-01 사용자 확정 「B로 · ① 먹색」) ───────────
    # 갈 곳이 위쪽 줄 단추 · 「무엇을 할까」 · 「결과 | 시나리오」 띠 · 표 드롭다운 네 곳에
    # 흩어져 있었다. 왼쪽에 위아래로 채운 진한 막대를 세워 「어디로 갈지」를 한 줄에 모은다.
    # 옛 자리(조작판의 「무엇을 할까」 · 띠 · 드롭다운)는 그대로 둔다 — 같은 곳으로 간다.
    def rail(self):
        c = self.c
        bar = QFrame()
        bar.setObjectName("rail")
        bar.setFixedWidth(76)
        bar.setStyleSheet(f"#rail {{ background:{c['rail']}; border-radius:16px; }}")
        v = QVBoxLayout(bar)
        v.setContentsMargins(6, 14, 6, 12)
        v.setSpacing(4)

        logo = QLabel("UNI\nGRID")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(f"color:{c['rail_on']};font-size:11px;font-weight:700;"
                           f"letter-spacing:1px;background:transparent;")
        v.addWidget(logo)
        v.addSpacing(8)

        on = self._rail_on()
        has_case = self.sol is not None
        has_base = getattr(self, "base_case", None) is not None
        n_sc = len(self.book.items) if getattr(self, "book", None) is not None else 0
        self._rail_btns = {}

        def add(kind, name, fn, enabled=True, tip=""):
            b = RailButton(kind, name, c, on=(name == on))
            b.clicked.connect(fn)
            b.setEnabled(enabled)
            if tip:
                b.setToolTip(tip)
            v.addWidget(b, 0, Qt.AlignHCenter)
            self._rail_btns[name] = b

        def sep():
            ln = QFrame()
            ln.setFixedSize(40, 1)
            ln.setStyleSheet(f"background:{c['rail_fg']};")
            v.addSpacing(4)
            v.addWidget(ln, 0, Qt.AlignHCenter)
            v.addSpacing(4)

        add("open", "불러오기", self.do_import, tip="계통 파일을 엽니다")
        sep()
        add("result", "결과", lambda: self.rail_go("결과"), has_case)
        add("check", "점검", lambda: self.rail_go("점검"), has_case,
            "한계를 넘은 것 · 한계에 도달한 것")
        add("grid", "계통 데이터", lambda: self.rail_go("계통 데이터"), has_case)
        add("scenario", "시나리오", lambda: self.rail_go("시나리오"), has_case and n_sc >= 2,
            "조건을 바꿔 푼 것이 둘 이상이면 열립니다" if n_sc < 2 else "")
        add("curve", "PV·QV 곡선", lambda: self.rail_go("PV·QV 곡선"), has_base)
        v.addStretch()
        add("export", "내보내기", self.do_export, has_case)
        add("excel", "엑셀로 만들기", lambda: ConvertDialog(self, c).exec(),
            tip="MATPOWER · PSS/E · MatACDC 파일을 UNIGRID 엑셀로")
        theme = ThemeSwitch(self.dark, c)
        theme.setToolTip("화면을 어둡게/밝게 바꿉니다")
        theme.setCursor(Qt.PointingHandCursor)
        theme.flipped.connect(self.toggle_theme)
        v.addSpacing(4)
        v.addWidget(theme, 0, Qt.AlignHCenter)
        v.addSpacing(4)
        add("info", "정보", lambda: AboutDialog(self, c).exec(), tip="판·저작권·사용 조건")
        return bar

    def _rail_on(self):
        """사이드바에서 지금 고른 칸."""
        if self.sol is None:
            return None
        if self.task == "PV·QV 곡선":
            return "PV·QV 곡선"
        if getattr(self, "pane", "결과") == "시나리오":
            return "시나리오"
        tab = getattr(self, "table_tab", "")
        return tab if tab in ("점검", "계통 데이터") else "결과"

    def _sync_rail(self):
        """화면을 다시 안 그리고 탭만 바뀐 때 — 사이드바의 고른 칸을 맞춘다."""
        on = self._rail_on()
        nav = getattr(self, "_nav", None)
        if nav is not None:
            try:
                nav.set_on(on)
            except RuntimeError:
                pass
        for name, b in getattr(self, "_rail_btns", {}).items():
            try:
                b.set_on(name == on)
            except RuntimeError:            # 이미 지워진 단추
                pass

    def rail_go(self, name):
        """사이드바 칸을 누르면 — 할 일 · 갈래 · 표 탭을 차례로 맞춘다."""
        if name == "PV·QV 곡선":
            if self.task != name:
                self.set_task(name)
            return
        if self.task != "조류계산":
            self.task = "조류계산"
            snap = snap_central(self)             # 곡선 → 결과는 화면이 통째로 바뀐다
            self.rebuild()
            crossfade_from(self, snap, lambda: play_charts(self.centralWidget()), self.centralWidget())
        if name == "시나리오":
            if self.mode == "비교":       # 비교 화면은 제 시나리오 목록을 따로 낸다 — 스냅샷으로 돌아와 연다
                self.mode = "스냅샷"
            self.set_pane("시나리오")
            return
        self.go_table(name)

    def go_table(self, want):
        """결과 표의 탭 하나로 간다. `want` = 「결과」(첫 탭) · 「점검」 · 「계통 데이터」."""
        if want == "결과" and self.mode == "비교":
            if getattr(self, "pane", "결과") != "결과":
                self.set_pane("결과")
            return                           # 비교 화면이 곧 결과다 — 표 탭은 없다
        if self.mode == "비교":       # 비교 모드엔 표가 없으니 스냅샷으로 돌아간다
            self.mode = "스냅샷"
            self.rebuild()
        if getattr(self, "pane", "결과") != "결과":
            self.pane = "결과"
            self.rebuild()
            reveal(getattr(self, "_center_w", None))
        tt = getattr(self, "_tabs", None)
        if tt is None:
            return
        for i in range(tt.count()):
            base = _tab_base(tt.tabText(i))
            if (want == "결과" and i == 0) or base == want:
                tt.setCurrentIndex(i)
                self.table_tab = base        # 다시 그려도 여기 머문다
                self._sync_rail()
                return

    def topbar(self):
        c = self.c
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(70)
        h = QHBoxLayout(bar)
        h.setContentsMargins(20, 0, 20, 0)
        h.setSpacing(9)

        logo = QLabel("UNIGRID")
        logo.setStyleSheet(
            f"color:{c['text']};font-size:23px;font-weight:600;letter-spacing:1.4px;")
        h.addWidget(logo)
        h.addSpacing(14)

        b1 = QPushButton("불러오기")
        b1.setObjectName("accentline")   # 가장 자주 쓰는 버튼이라 한 단계 위로
        b1.clicked.connect(self.do_import)
        # 비교 모드에서는 이 버튼이 **표만** 담당한다(비교 그림은 사이드바의
        # "이 비교 그림 저장" 버튼이 맡는다) → 누르기 전에 알 수 있게 이름에 박는다.
        b2 = QPushButton("내보내기 (표만)" if self.mode == "비교" else "내보내기")
        if self.mode == "비교":
            b2.setToolTip("비교 모드에서는 표(엑셀)만 내보냅니다.\n"
                          "비교 그림은 왼쪽 아래 “이 비교 그림 저장” 버튼을 쓰세요.")
        b2.clicked.connect(self.do_export)
        b3 = QPushButton("엑셀로 만들기")   # 케이스 만들 때만 쓰는 도구 → 맨 뒤
        b3.clicked.connect(lambda: ConvertDialog(self, c).exec())
        for b in (b1, b2, b3):
            h.addWidget(b)
        h.addStretch()

        # 🚨 「시간 · 버스」 고르개는 **표 줄로 내렸다** (2026-09-08 점검 i56 —
        #    사용자: *"시간 버튼 위치가 좀 이상해"*). 2026-08-29 에 사이드바에서
        #    이 맨 위 줄로 올렸던 것인데, 파일 단추(불러오기·내보내기·엑셀로 만들기)
        #    사이에 끼어 **파일을 다루는 줄에 값을 고르는 것 하나가 섞여** 있었다.
        #    ⚠️ 그때 그래프 탭 줄을 피한 까닭(계통 데이터·점검에서는 그 줄이 없다)은
        #       그대로 유효하다 — 그래서 그래프 줄이 아니라 **「표」 고르개 줄**이다.
        #       그 줄은 어느 탭에서나 있고, 바로 옆에 「표」·「위반」이 있어
        #       *지금 무엇을 보고 있나* 가 한자리에 모인다.

        # 🚨 **「정보」는 넣고 뺄 수 있는 것이 아니다** (2026-08-19).
        #    MathWorks 라이선스가 *"About Box, 또는 그와 비슷한 눈에 띄는 자리"* 에
        #    저작권 고지를 넣으라고 요구한다(license_agreement.txt 205–210행).
        #    자주 누를 것이 아니므로 오른쪽 끝에 조용히 둔다.
        # 🚨 **어두운 화면을 켤 길이 없었다** (2026-09-08 점검 i63). `toggle_theme` 은
        #    있는데 그것을 부르는 단추가 어디에도 없어, 시험 스크립트로만 켜 볼 수 있었다.
        theme = ThemeSwitch(self.dark, c)    # 앱 2.3 C — 손잡이가 미끄러진 뒤 테마를 바꾼다
        theme.setToolTip("화면을 어둡게/밝게 바꿉니다")
        theme.setCursor(Qt.PointingHandCursor)
        theme.flipped.connect(self.toggle_theme)
        h.addWidget(theme)

        info = QPushButton("정보")
        info.setToolTip("판·저작권·사용 조건")
        info.clicked.connect(lambda: AboutDialog(self, c).exec())
        h.addWidget(info)

        # 🚨 여기 있던 「표시 모드 — 숫자만 / 그림 포함」 을 **없앴다** (2026-08-18 사용자
        #    지적 *"그래프 펼치기랑 숫자만/그림 포함 이게 좀 겹치는거 같은데"*).
        #    스위치는 `self.numbers` **하나**인데 이름이 넷이었다 —
        #    위쪽 [숫자만]/[그림 포함] · 그래프 자리 [그래프 접기]/[그래프 펼치기].
        #    2026-08-15 에 그래프 자리에 접기를 넣으면서 겹침을 **툴팁으로 때웠고**
        #    (*"위쪽 [숫자만] 과 같은 일입니다"*), 그 땜질이 결국 이 지적으로 돌아왔다.
        #    남긴 쪽은 **그래프 자리**다 — 그래프 바로 옆이라 무엇을 접는지 분명하고,
        #    접혀 있을 때는 안내 띠가 상태와 이유를 함께 말해 준다. 위쪽은 그래프에서
        #    멀고 `숫자만` 이라는 이름만으로는 무슨 일이 나는지 눌러 봐야 알았다.
        #    ⚠️ 함께 사라진 것 = 그 단추의 **거짓 툴팁** *"5~7배 빠릅니다"*. 같은 파일
        #       아래쪽(안내 띠)이 이미 *"사실이 아니다 — 실측 0.86~1.49배"* 라고 적어
        #       놨는데 툴팁만 옛 문구를 달고 남아 있었다.

        return bar

    def view_picker(self):
        """맨 위 줄 가운데 — 지금 무엇을 보고 있나 (시간 · 버스).

        비교 모드는 **아직 여기 없다** — 「볼 항목」은 24개짜리라 칩+패널이 필요하고,
        그것은 따로 정한다(2026-08-29). 그때까지 비교는 사이드바에 그대로 둔다.
        """
        if self.sol is None or self.mode not in ("스냅샷", "다이나믹"):
            return None
        c = self.c
        if self.mode == "스냅샷":
            cap = "시간"
            n_t = self.sol.n_time
            items = [f"{i} H" for i in range(1, n_t + 1)]
            idx, slot = min(self.t, n_t - 1), self.set_time
        else:
            cap = "버스"
            # 🚨 AC 가 없으면 견본 「AC 1 ~ 14」 를 띄우고 있었다 — DC 단독 계통에서 고르개가
            #    없는 버스를 보였다(2026-11-03 전수 검사). 순서는 `charts._pick_bus` 와 같다(AC 다음 DC).
            items = []
            if self.sol.AC.size:
                items += [f"AC {int(b)}" for b in self.sol.AC[:, 0, 0]]
            if self.sol.DC.size:
                items += [f"DC {int(b)}" for b in self.sol.DC[:, 0, 0]]
            if not items:
                return None
            idx, slot = min(self.bus_row, len(items) - 1), self.set_bus

        w = QWidget()
        w.setObjectName("viewpick")
        # 🚨 안 주면 **자기 배경(흰색)을 칠해** 맨 위 줄에 흰 덩어리가 생긴다
        #    (2026-08-29 확대해서 확인).
        w.setStyleSheet("#viewpick { background: transparent; }")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lb = QLabel(cap)
        lb.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:600;")
        lay.addWidget(lb)
        cb = Combo(self.c['muted'])
        cb.addItems(items)
        cb.setCurrentIndex(max(0, idx))
        cb.setMinimumWidth(118)
        cb.currentIndexChanged.connect(slot)
        cb.setToolTip("그래프와 표가 이것을 같이 따라갑니다")
        lay.addWidget(cb)
        self._view_pick = cb
        return w

    # ── 좌측 ──
    def side_lock_why(self):
        """왼쪽 줄을 접을 수 없는 까닭. 접을 수 있으면 빈 글자 (2026-09-02).

        접으면 그 안에 있던 조작이 **통째로 사라진다** — 비교의 「무엇끼리 비교」·
        「비교할 버스」·「이 비교 그림 저장」, 곡선의 입력 셋. 이 둘은 맨 위 줄로
        옮길 수도 없어서(여러 개 고르는 팝업이라 꼴이 다르다) 접기를 막는다.
        🚨 잠근 자리에 **갇히지 않게** 길을 같이 낸다 — 접힌 띠에서 그 둘로 갈 때는
           스스로 펼친다(`set_mode`·`set_task`). 2026-09-01 에 두 번 겪은 함정이다.
        """
        if self.task == "PV·QV 곡선":
            return "PV·QV 곡선은 왼쪽에서 넣을 것이 있어 접을 수 없습니다."
        if self.mode == "비교":
            return "비교는 왼쪽에서 고를 것이 있어 접을 수 없습니다."
        return ""

    def toggle_side(self):
        """왼쪽 줄을 접었다 폈다. 펴는 쪽은 언제나 된다."""
        was = self.side_open
        if not self.side_open:
            self.side_open = True
        elif not self.side_lock_why():
            self.side_open = False
        self.rebuild()
        if was != self.side_open:
            # 🍎 **좁아지는 것이지 사라지는 게 아니다** — 페이드가 아니라 폭을 민다
            slide_width(getattr(self, "_side_sa", None),
                        56 if self.side_open else 280,
                        280 if self.side_open else 56)

    def _pane_strip(self):
        """표 위 두 갈래 — [결과] [시나리오 N] (2026-09-08 점검 i48).

        시나리오가 하나(원본)뿐이면 만들지 않는다 — 갈래가 하나인 갈림길은
        군더더기다(`scenario_bar()` 가 두 개 미만이면 안 만드는 것과 같은 잣대).
        """
        # 2026-11-15 — 사이드바에 「시나리오」 가 있어 같은 갈림길이 두 군데였다. 띠는 더 안 만든다
        # (시나리오 화면은 `scenario_page`). 아래는 되살릴 때를 위해 남겨 둔다.
        return None
        c = self.c
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(3)
        seg = QFrame()
        seg.setObjectName("segwrap")
        seg.setStyleSheet(
            f"#segwrap {{ background:{c['bg']};border:1px solid {c['border']};"
            f"border-radius:8px; }}")
        sh = QHBoxLayout(seg)
        sh.setContentsMargins(3, 3, 3, 3)
        sh.setSpacing(3)
        for nm, txt in [("결과", "결과"),
                        ("시나리오", f"시나리오 {len(self.book.items)}")]:
            b = QPushButton(txt)
            b.setObjectName("seg_on" if self.pane == nm else "seg_off")
            b.setCursor(Qt.PointingHandCursor)
            _fit_button(b)
            b.clicked.connect(lambda _, x=nm: self.set_pane(x))
            sh.addWidget(b)
        h.addWidget(seg)
        h.addStretch(1)
        return w

    def scenario_page(self):
        """시나리오 화면 (2026-11-15). 하나뿐이면 **어떻게 만드는지** 를 적는다.

        여태 하나뿐일 때는 사이드바 칸이 잠기고 까닭이 풍선말에만 있었다.
        """
        c = self.c
        sb = self.scenario_bar()
        if sb is not None:
            return _scrollable(sb)
        card = GlassCard(c, self.dark, radius=16)
        float_panel(card, self.dark)
        v = QVBoxLayout(card)
        v.setContentsMargins(40, 36, 40, 36)
        v.setSpacing(10)
        v.addStretch(1)
        t = QLabel("아직 비교할 시나리오가 없습니다")
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(f"color:{c['text']};font-size:19px;font-weight:800;background:transparent;")
        v.addWidget(t)
        d = QLabel("시나리오 = 조건을 바꿔 다시 푼 결과 하나입니다. 지금은 원본 하나뿐입니다.")
        d.setAlignment(Qt.AlignCenter)
        d.setStyleSheet(f"color:{c['muted']};font-size:14px;background:transparent;")
        v.addWidget(d)
        v.addSpacing(14)
        for k, txt in enumerate(["「계통 데이터」 에서 값을 바꾸거나 선로 · 발전기를 끕니다",
                                 "위쪽 띠의 「이 조건으로 계산」 을 누릅니다",
                                 "푼 결과가 여기에 쌓이고, 원본과 나란히 비교할 수 있습니다"]):
            row = QLabel(f"<span style='color:{c['muted']};font-weight:800'>{k + 1}</span>&nbsp;&nbsp;&nbsp;{txt}")
            row.setAlignment(Qt.AlignCenter)
            row.setStyleSheet(f"color:{c['text']};font-size:14px;background:transparent;")
            v.addWidget(row)
        v.addSpacing(16)
        go = QPushButton("계통 데이터로 가기")
        go.setObjectName("primary")
        go.setCursor(Qt.PointingHandCursor)
        go.clicked.connect(lambda: self.nav_go("계통 데이터"))
        v.addWidget(go, 0, Qt.AlignCenter)
        v.addStretch(2)
        return card

    def set_pane(self, name):
        if name == getattr(self, "pane", "결과"):
            return
        self.pane = name
        self.rebuild()
        reveal(getattr(self, "_center_w", None))   # 결과 ↔ 시나리오

    def side_rail(self):
        """접힌 왼쪽 띠 — 폭 56px (2026-09-02 사용자 확정, 안 (나)).

        ⚠️ **아이콘은 임시다.** 지금은 정체가 풍선말에만 있어서, 2026-09-01 에
           고친 「⚠ 26」(뜻이 툴팁에만)과 같은 결함을 스스로 만든 꼴이다.
           디자인 다듬기 때 다시 본다(사용자 확정 — *"아이콘은 디자인 다듬을 때 보자"*).
        """
        c = self.c
        sb = GlassCard(c, self.dark, radius=16, tint=(0.80, 0.66))
        sb.setObjectName("sidebar")
        sb.setFixedWidth(56)
        v = QVBoxLayout(sb)
        v.setContentsMargins(6, 14, 6, 14)
        v.setSpacing(8)

        def icon(txt, on=False, tip="", on_click=None, why=""):
            b = QPushButton(txt)
            b.setObjectName("seg_on" if on else "seg_off")
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedSize(44, 40)
            b.setStyleSheet("font-size:17px;padding:0;")
            if why:
                b.setEnabled(False)
                b.setToolTip(why)
            else:
                b.setToolTip(tip)
                if on_click is not None:
                    b.clicked.connect(on_click)
            v.addWidget(b)
            return b

        icon("☰", tip="왼쪽 줄 펼치기", on_click=lambda _: self.toggle_side())
        v.addWidget(hline_soft(c))
        icon("⌂", tip=f"케이스 — {self.case[0]}\n누르면 왼쪽 줄을 펼칩니다",
             on_click=lambda _: self.toggle_side())
        why = self.curve_why()
        for name, ch in zip(TASKS, ("▶", "◠")):
            icon(ch, on=(self.task == name), tip=f"무엇을 할까 — {name}",
                 on_click=lambda _, x=name: self.set_task(x),
                 why=(why if name == "PV·QV 곡선" and why else ""))
        v.addWidget(hline_soft(c))
        why_dyn = self.dynamic_why()
        for m, ch in zip(MODES, ("▦", "◷", "⇄")):
            icon(ch, on=(self.mode == m), tip=f"보기 — {m}",
                 on_click=lambda _, x=m: self.set_mode(x),
                 why=(why_dyn if m == "다이나믹" and why_dyn else ""))
        v.addStretch()
        return sb

    def sidebar(self):
        c = self.c
        sb = GlassCard(c, self.dark, radius=16, tint=(0.80, 0.66))
        sb.setObjectName("sidebar")
        sb.setFixedWidth(280)
        v = QVBoxLayout(sb)
        v.setContentsMargins(14, 16, 14, 14)
        v.setSpacing(8)

        # ── 접기 (2026-09-02 사용자 확정, 안 (나)) ──
        # 접으면 표가 **1198 → 1422px** 로 넓어진다(1512px 창 실측). 사이드바를
        # 아예 없애는 안 (다)는 표를 1478px 까지 넓히지만 「무엇을 할까」·「보기」가
        # 맨 위 줄로 올라가 **그 줄이 1333px 을 요구** — 창 최소 가로가 929 → 1294px
        # 로 올라가서 접었다.
        why_fold = self.side_lock_why()
        fold = QPushButton("◀  접기")
        fold.setObjectName("link")
        fold.setCursor(Qt.PointingHandCursor)
        if why_fold:
            # ⚠️ 여기서는 까닭을 **글줄로 안 적는다** — 잠긴 「다이나믹」과 달리
            #    이건 상태를 고르는 단추가 아니라 곁다리 동작이라, 못 눌러도
            #    갇히지 않는다. 사이드바 세로도 비교 모드에서 이미 807px 이다.
            fold.setEnabled(False)
            fold.setToolTip(why_fold)
        else:
            fold.setToolTip("왼쪽 줄을 접어 표를 넓게 씁니다")
            fold.clicked.connect(self.toggle_side)
        fr = QHBoxLayout()
        fr.setContentsMargins(0, 0, 0, 0)
        fr.addStretch()
        fr.addWidget(fold)
        v.addLayout(fr)

        v.addWidget(self.case_card())
        v.addSpacing(12)

        # ── 무엇을 할까 — 케이스 다음으로 큰 갈림이라 맨 위에 둔다 (F1d)
        tl = QLabel("무엇을 할까")
        tl.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:600;")
        v.addWidget(tl)
        tseg = QFrame()
        tseg.setObjectName("segwrap")
        tseg.setStyleSheet(
            f"#segwrap {{ background:{c['bg']};border:1px solid {c['border']};"
            f"border-radius:8px; }}")
        # 🚨 **가로로 눕힌다** (2026-09-02 사용자 확정, D 안 (나)).
        #    세로 2 단이라 77px 을 썼는데, 바로 아래 「보기」는 **셋을 가로로** 담고
        #    41px 이다 — 같은 급의 고르개 둘이 서로 다른 꼴이었다.
        #    ⚠️ 비교 모드 사이드바가 창 950px 에서 **5px 넘쳐 스크롤**이 생기던 것을
        #       이 36px 로 뒤집는다(839 → 803px, 자리 834px). 맨 아래 「이 비교 그림
        #       저장」이 스크롤해야 보이던 자리다.
        th = QHBoxLayout(tseg)
        th.setContentsMargins(3, 3, 3, 3)
        th.setSpacing(3)
        why = self.curve_why()
        for name in TASKS:
            b = QPushButton(name)
            b.setObjectName("seg_on" if self.task == name else "seg_off")
            b.setCursor(Qt.PointingHandCursor)
            if name == "PV·QV 곡선" and why:
                b.setEnabled(False)
                b.setObjectName("seg_lock")      # 잠겨 보이게 (2026-09-08 i67)
                b.setToolTip(why)
            else:
                b.clicked.connect(lambda _, x=name: self.set_task(x))
            th.addWidget(b)
        v.addWidget(tseg)
        if why and self.task != "PV·QV 곡선":
            # 「잠김 —」 을 앞에 붙인다 (2026-09-08 i67) — 글줄만 있으면 그냥 설명으로
            # 읽히고, 위 단추가 «못 누르는 것» 이라는 것과 이어지지 않는다.
            wn = QLabel("잠김 — " + why)
            wn.setWordWrap(True)
            wn.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            v.addWidget(wn)
        # ── 해법 (2026-09-08 점검 i10) ────────────────────────────────────
        # 「무엇을 할까」의 **바로 아래**다 — 조류계산을 *어떻게* 푸느냐라서
        # 그 갈래에 딸린 설정이고, 곡선을 고르면 뜻이 없어 안 낸다(곡선은 NR 뿐).
        if self.task != "PV·QV 곡선":
            v.addSpacing(10)
            sl = QLabel("해법")
            sl.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:600;")
            v.addWidget(sl)
            v.addLayout(self._solver_picker(heading=False))

        # 「무엇을 할까」와 그 아래를 가르는 선 (2026-08-29 사용자 확정 · 안 가-1).
        # 위 = 무엇을 할까 / 아래 = 그 작업 안에서 어떻게 볼까.
        # 셋(케이스·할 일·보기)이 같은 꼴이라 나란한 설정처럼 읽혔는데, 실은
        # 「PV·QV 곡선」을 고르면 아래가 통째로 바뀐다(이 함수가 거기서 return 한다).
        # ⚠️ 두 갈래 **앞**에 둔다 — 곡선 쪽 입력들도 「무엇을 할까」의 아래다.
        v.addSpacing(10)
        v.addWidget(hline_soft(c))
        v.addSpacing(12)

        if self.task == "PV·QV 곡선":
            self.curve_controls(v)
            v.addStretch()
            return sb

        # 모드 3분할 — 가장 큰 선택이라 이름표를 붙인다
        ml = QLabel("보기")
        ml.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:600;")
        v.addWidget(ml)
        seg = QFrame()
        seg.setObjectName("segwrap")
        seg.setStyleSheet(
            f"#segwrap {{ background:{c['bg']};border:1px solid {c['border']};"
            f"border-radius:8px; }}")
        sh = QHBoxLayout(seg)
        sh.setContentsMargins(3, 3, 3, 3)
        sh.setSpacing(3)
        why_dyn = self.dynamic_why()
        for m in MODES:
            b = QPushButton(m)
            b.setObjectName("seg_on" if self.mode == m else "seg_off")
            b.setCursor(Qt.PointingHandCursor)
            if m == "다이나믹" and why_dyn:
                # `PV·QV 곡선` 과 같은 수법 (2026-08-31 `a46a72a`) — 잠그고 까닭을 붙인다.
                b.setEnabled(False)
                b.setObjectName("seg_lock")      # 잠겨 보이게 (2026-09-08 i61)
                b.setToolTip(why_dyn + "\n시간에 따른 변화가 없어 그래프에 점 하나만 "
                                       "찍힙니다.")
            else:
                b.clicked.connect(lambda _, x=m: self.set_mode(x))
            sh.addWidget(b)
        v.addWidget(seg)
        # ⚠️ **까닭을 글로도 적는다.** 잠긴 단추는 안 고른 단추와 생김새가 같아
        #    (둘 다 `seg_off` 회색) 풍선말을 띄우기 전엔 잠긴 줄 모른다.
        #    「PV·QV 곡선」이 쓰는 것과 같은 줄이다 (2026-09-01).
        if why_dyn:
            wn2 = QLabel("잠김 — " + why_dyn)
            wn2.setWordWrap(True)
            wn2.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            v.addWidget(wn2)
        v.addSpacing(12)

        # 🚨 「시간 선택」·「버스 선택」은 **맨 위 줄로 옮겼다** (2026-08-29 사용자 확정).
        #    `view_picker()` 참조. 사이드바에는 *한 번 정하면 한동안 안 바꾸는 것*만 남긴다.
        if self.mode == "스냅샷":
            pass                                # 주파수는 맨 아래 상태바에 있다

        elif self.mode == "다이나믹":
            pass                                # 버스 고르개는 맨 위 줄에 있다

        else:  # 비교
            self._compare_controls(v)

        return sb

    def _input_card(self, kind):
        """비교 · PV·QV 곡선에서 고를 것을 **가로 한 줄 카드**로 낸다 (2026-11-15).

        `kind` = "compare" | "curve". 안의 단추 · 입력 칸은 옛 세로 판(`_compare_controls` ·
        `curve_controls`)과 같은 것이고 놓는 꼴만 다르다. 설명은 풍선말 · 빈 칸 글로 옮겼다.
        """
        c = self.c
        card = GlassCard(c, self.dark, radius=16)
        float_panel(card, self.dark)
        h = QHBoxLayout(card)
        h.setContentsMargins(18, 12, 18, 14)
        h.setSpacing(22)

        def field(cap, w, tip=""):
            box = QVBoxLayout()
            box.setSpacing(5)
            lb = QLabel(cap)
            lb.setStyleSheet(f"color:{c['muted']};font-size:12px;font-weight:700;background:transparent;")
            box.addWidget(lb)
            box.addWidget(w)
            if tip:
                w.setToolTip(tip)
            h.addLayout(box)
            return w

        def seg(opts, cur, slot):
            fr = QFrame()
            fr.setObjectName("segwrap")
            fr.setStyleSheet(f"#segwrap {{ background:{c['bg']};border:1px solid {c['border']};"
                             f"border-radius:9px; }}")
            sh = QHBoxLayout(fr)
            sh.setContentsMargins(3, 3, 3, 3)
            sh.setSpacing(3)
            for key, name in opts:
                b = QPushButton(name)
                b.setObjectName("seg_on" if cur == key else "seg_off")
                b.setCursor(Qt.PointingHandCursor)
                _fit_button(b)
                b.clicked.connect(lambda _, x=key: slot(x))
                sh.addWidget(b)
            return fr

        if kind == "compare":
            field("무엇끼리 비교", seg([(a, a) for a in ("버스끼리", "시간끼리", "시나리오끼리")],
                                    self.compare_axis, self.set_axis))
            if self.compare_axis == "시나리오끼리":
                note = QLabel("아래 시나리오 목록에서 체크한 것을 겹쳐 그립니다 · "
                              "전압 · 위상각은 x축이 버스, 주파수 · 손실은 x축이 시간입니다")
                note.setWordWrap(True)
                note.setStyleSheet(f"color:{c['muted']};font-size:12.5px;background:transparent;")
                h.addWidget(note, 1, Qt.AlignBottom)
            else:
                kinds = CI.kinds_needed(self.picked, self.compare_axis)
                what = (" · ".join(CI.UNIT_NAME[k] for k in kinds) or "버스") \
                    if self.compare_axis == "버스끼리" else "시간"
                tb = field(f"비교할 {what}", self.target_button(),
                           "누르면 이 계통에 있는 것 중에서 고릅니다 · 최대 50개")
                tb.setMinimumWidth(170)
                h.addStretch(1)
            h.addWidget(self.compare_save_button(), 0, Qt.AlignBottom)
            return card

        le = QLineEdit(self.curve_load)
        le.setPlaceholderText("비우면 부하가 있는 버스 전부")
        le.setMinimumWidth(210)
        le.textChanged.connect(lambda t: setattr(self, "curve_load", t))
        field("부하를 늘릴 버스", le, "여기에 적은 버스의 부하만 함께 늘립니다")
        le2 = QLineEdit(self.curve_pick)
        le2.setPlaceholderText("비우면 늘린 버스와 같게 (최대 8개)")
        le2.setMinimumWidth(230)
        le2.textChanged.connect(self.set_curve_pick)
        field("곡선을 그릴 버스", le2)
        field("가로축", seg([("MW", "합계 부하"), ("lambda", "배수 λ")], self.curve_x, self.set_curve_x))
        h.addStretch(1)
        why = self.curve_why()
        run = QPushButton("곡선 그리기" if not self.curve_busy else "그리는 중…")
        run.setObjectName("primary")
        run.setCursor(Qt.PointingHandCursor)
        run.setMinimumWidth(130)
        run.setEnabled(not self.curve_busy and not why)
        run.setToolTip(why or "버스가 많으면 몇 분 걸립니다")
        run.clicked.connect(self.run_curve)
        h.addWidget(run, 0, Qt.AlignBottom)
        return card

    def _compare_controls(self, v):
        """비교 모드에서 고를 것(무엇끼리 · 대상 · 저장) — 옛 설정 판에서 뺐다."""
        c = self.c
        lb = QLabel("무엇끼리 비교")
        lb.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:600;")
        v.addWidget(lb)
        seg2 = QFrame()
        seg2.setObjectName("segwrap")
        seg2.setStyleSheet(
            f"#segwrap {{ background:{c['bg']};border:1px solid {c['border']};"
            f"border-radius:8px; }}")
        s2 = QVBoxLayout(seg2)          # 세 개는 한 줄에 안 들어간다 — 두 줄로
        s2.setContentsMargins(3, 3, 3, 3)
        s2.setSpacing(3)
        top2 = QHBoxLayout()
        top2.setSpacing(3)
        for a in ["버스끼리", "시간끼리"]:
            b = QPushButton(a)
            b.setObjectName("seg_on" if self.compare_axis == a else "seg_off")
            b.clicked.connect(lambda _, x=a: self.set_axis(x))
            top2.addWidget(b)
        s2.addLayout(top2)
        b3 = QPushButton("시나리오끼리")
        b3.setObjectName(
            "seg_on" if self.compare_axis == "시나리오끼리" else "seg_off")
        b3.clicked.connect(lambda: self.set_axis("시나리오끼리"))
        s2.addWidget(b3)
        v.addWidget(seg2)
        v.addSpacing(8)

        if self.compare_axis == "시나리오끼리":
            lb3 = QLabel("겹쳐 볼 시나리오")
            lb3.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:600;")
            v.addWidget(lb3)
            n3 = QLabel("위의 시나리오 목록에서 체크한 것을 겹쳐 그립니다.\n"
                        "전압·위상각은 x축이 버스, 주파수·손실은 x축이 시간입니다.")
            n3.setWordWrap(True)
            n3.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            v.addWidget(n3)
            v.addStretch(1)
            # ⚠️ **여기서도 저장할 수 있어야 한다** (2026-09-01 전수 조사 ⑨).
            #    이 갈래가 아래 저장 단추까지 못 가고 먼저 나가는 바람에,
            #    시나리오를 겹쳐 그려 놓고 **그 그림만 저장을 못 했다.**
            v.addWidget(self.compare_save_button())
            return

        # 🚨 고른 항목이 **무엇마다 있는 값이냐**에 따라 골라 달라는 것이 다르다
        #    (버스 · 선로 · IC). 「버스」로 박아 두면 선로 부하율을 고르고도
        #    버스 번호를 적게 된다.
        kinds = CI.kinds_needed(self.picked, self.compare_axis)
        what = (" · ".join(CI.UNIT_NAME[k] for k in kinds) or "버스") \
            if self.compare_axis == "버스끼리" else "시간"
        lb2 = QLabel(f"비교할 {what}")
        lb2.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:600;")
        v.addWidget(lb2)
        # 🚨 **타이핑 칸이었다** (2026-08-30 사용자 확정으로 고르개가 됐다).
        #    타이핑 칸일 때 네 가지가 조용히 어긋났다 —
        #      ① 기본값 `3, 7, 12` 가 12버스 계통에서 3 하나만 맞았다(7·12 는 DC)
        #      ② 없는 번호(999)를 아무 말 없이 버렸다
        #      ③ 빈 칸 안내가 `예: 106 107`(쉼표 없음)인데 쉼표가 없으면 통째로 버렸다
        #      ④ 같은 번호를 여러 번 받아 같은 선을 겹쳐 그렸다
        #    **있는 것만 고르게** 하면 넷이 한꺼번에 사라진다.
        v.addWidget(self.target_button())
        n = QLabel("누르면 이 계통에 있는 것 중에서 고릅니다 · 최대 50개")
        n.setWordWrap(True)
        n.setStyleSheet(f"color:{c['muted']};font-size:13px;")
        v.addWidget(n)
        v.addSpacing(10)

        # 🚨 「볼 항목」 24개 목록은 **비교 탭 줄 구석의 칩**으로 옮겼다
        #    (2026-08-29 사용자 확정, `item_chip()`·`open_item_pick()`).
        #    고른 것이 곧 오른쪽 탭이 되므로 **같은 것을 두 번 말하고 있었고**,
        #    그 목록 하나가 사이드바의 3분의 2(1543px 중 약 1090px)를 썼다.
        v.addSpacing(10)
        v.addWidget(self.compare_save_button())

    # ── 가운데 ──
    def center(self):
        c = self.c
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)   # 바깥 `mid` 가 여백을 맡는다 (floating)
        v.setSpacing(11)

        if self.task == "PV·QV 곡선":
            bar = self.change_bar()      # 계통 조건은 조류계산과 **같이 쓴다**
            if bar is not None:
                v.addWidget(bar)
            v.addWidget(self._input_card("curve"))
            v.addWidget(self.curve_page(), 1)
            return w

        if self.mode == "비교":
            # 겹쳐 보기 체크칸이 이 목록에 있다 — 비교 모드에서 오히려 더 필요하다
            v.addWidget(self._input_card("compare"))
            sb = self.scenario_bar()
            if sb is not None:
                v.addWidget(sb)
            v.addWidget(self.compare_area(), 1)
            return w

        bar = self.change_bar()          # 바꾼 것이 있을 때만 나온다
        if bar is not None:
            v.addWidget(bar)
        # 시나리오는 제 화면이 있다 (2026-11-15) — 여태 표 판 안의 [결과][시나리오 N] 띠로만 갔고,
        # 개요가 켜져 있으면 사이드바 「시나리오」 를 눌러도 개요가 그대로 떴다.
        if getattr(self, "pane", "결과") == "시나리오":
            v.addWidget(self.scenario_page(), 1)
            return w
        # 사이드바가 맡은 화면(점검 · 계통 데이터)은 그 표만 보인다 (2026-11-15) — 「← 개요」 ·
        # 그래프 접힘 안내 · 「표」 고르개 · 「위반 N」 단추는 사이드바와 겹치거나 상관없는 것이었다.
        focus = self.sol is not None and _tab_base(getattr(self, "table_tab", "")) in self.TABLE_FIRST
        # 2026-11-15 — 점검이 숫자 표만 있어 휑했다(사용자: 「숫자만 있고 … 너무 휑해 보여서」).
        # 개요와 같은 꼴(숫자 카드 · 넘은 비율 막대 · 전압 그래프 · 부하율 막대)로 따로 그린다.
        if focus and _tab_base(self.table_tab) == "점검":
            import overview
            v.addWidget(_clear_scroll(overview.check_board(self)), 1)
            return w
        # 앱 2.3 (2026-11-03) — 스냅샷 결과는 **개요**부터 보인다. 그래프 · 표는 「자세히」로.
        if self.sol is not None and self.mode == "스냅샷" and not focus:
            if getattr(self, "overview_on", True):
                import overview
                # 개요도 스크롤에 담는다 — 카드들의 최소 높이(약 770 px)가 창 최소 세로가 되지 않게
                v.addWidget(_clear_scroll(overview.page(self)), 1)
                return w
            # (「← 개요」 단추는 제목 줄로 올렸다 — `page_head`)
        # 다이나믹도 개요부터 (2026-11-15) — 언제 · 어디가 넘는지. 그래프 · 표는 「자세히」 로.
        if (self.sol is not None and self.mode == "다이나믹" and not focus
                and getattr(self, "overview_on", True)):
            import overview
            v.addWidget(_clear_scroll(overview.dyn_page(self)), 1)
            return w
        # 🚨 시나리오 목록은 **여기 있지 않다** (2026-08-15). 위에 두면 줄마다 자리를 먹어
        #    (4줄 248px) 그래프와 표를 밀어냈다 ⇒ **아래 탭 하나로** 내려보냈다.
        #    위에는 `change_bar` 가 「지금 조건 + [⟲ 원본으로]」 한 줄만 남긴다.

        split = _GripSplitter(Qt.Vertical, c)
        split.setChildrenCollapsible(False)
        # 14px — 잡는 표시(막대 셋 + 위아래 화살촉, 세로 11px)가 들어갈 만큼.
        # 10px 이던 것을 넓혔다. 잡기도 그만큼 쉬워진다.
        split.setHandleWidth(14)
        # 🚨 `findChildren` 으로 찾으면 **지워지기를 기다리는 옛 것**이 먼저 잡힌다.
        #    지금 화면의 것은 여기에 들고 있는다(표 `_grid_tb` 와 같은 이유).
        self._split = split

        # ── 그래프 (접혀 있으면 안내 띠로 바뀐다) ──
        self._focus_grid = bool(focus and _tab_base(self.table_tab) == "계통 데이터")
        if self._focus_grid:
            tiles = self.grid_tiles()    # 표 고르개 = 숫자 카드 줄 (2026-11-15)
            if tiles is not None:
                v.addWidget(tiles)
        if focus:
            pass                         # 표만 보이는 화면 — 그래프도 안내 띠도 없다
        elif not self.numbers:
            gt = GlassTabs(c, self.dark, radius=16)
            for name, plots, layout in GRAPHS[self.mode]:
                page = QWidget()
                lay = QHBoxLayout(page) if layout == "h" else QVBoxLayout(page)
                lay.setContentsMargins(10, 10, 10, 10)
                lay.setSpacing(9)
                # 🚨 **위아래로 쌓지 않고 한 장만 그린다** (2026-08-28 사용자 확정 —
                #    *"탭은 전압이랑 위상각을 두개 갖고 있는걸로 하되, 전압만 기본적으로
                #    뜨게 하고, 버튼으로 고를 수 있게"*). 쌓으면 한 장이 절반씩 나눠 가져
                #    그래프 최소 높이가 425 로 뛰고 그만큼 표가 깎였다.
                #    ⚠️ 옆으로 놓는 탭(조류 P·Q)은 그대로 둘 다 그린다 — 세로를 안 나눈다.
                shown = plots
                if layout == "v" and len(plots) > 1:
                    shown = [plots[min(self.plot_pick, len(plots) - 1)]]
                for pname in shown:
                    # 시간과 버스를 둘 다 넘긴다 — 어느 쪽을 쓸지는 그래프가
                    # 이름(x축이 버스냐 시간이냐)을 보고 고른다.
                    # (한때 하나만 넘겨서 고른 버스가 아니라 늘 첫 버스를 그렸다)
                    real = charts.build(pname, c, self.sol, self.t, self.bus_row,
                                        self.show_violations, self.set_violations,
                                        self.show_line_profile,
                                        topo_zoom=self.topo_zoom,
                                        on_topo_zoom=self.set_topo_zoom,
                                        on_reset_places=self.reset_topo_places,
                                        on_bus_click=self.show_bus_profile,
                                        on_pick_line=self.pick_line_by_bus)
                    lay.addWidget(real if real is not None else PlotBox(pname, c))
                gt.addTab(page, name)
            # 보고 있던 탭을 되살린다 — 위반 보기 토글 등이 rebuild() 로 화면을
            # 다시 만드는데, 안 되살리면 늘 0번(전압·위상)으로 튀어 버렸다
            # (토폴로지에서 토글을 누르면 전압 그래프로 넘어가던 버그).
            gt.setCurrentIndex(min(self.graph_tab, gt.count() - 1))
            # ⚠️ 아래 처리기가 이 둘을 붙잡으므로 **여기서 먼저** 만든다.
            stack_of = {i: pl for i, (_n, pl, lo) in enumerate(GRAPHS[self.mode])
                        if lo == "v" and len(pl) > 1}
            self._plot_seg = None

            def _on_graph_tab(i, _stack=stack_of, _gt=gt):
                self.graph_tab = int(i)
                if self._plot_seg is not None:
                    self._plot_seg.setVisible(int(i) in _stack)
                pg = _gt.widget(int(i))          # 앱 2.3 — 그래프마다 제 움직임, 없으면 밝아지며
                if not play_charts(pg):
                    fade_in(pg)
            gt.currentChanged.connect(_on_graph_tab)
            # 그래프가 낮으면 QtCharts 가 x축 글자를 "..." 로 줄여 버린다. 그래서
            # **평소 높이**(아래 setSizes 620)는 넉넉히 준다. 다만 이걸 최소치로
            # 잡아 두면 창을 화면보다 작게 못 만든다 — 470 + 표 579 로 창 최소가
            # 1201px 이 돼 맥북 화면에서 아래가 잘렸다(2026-08-13 실측·사용자 지적).
            # 최소는 낮추고, 좁게 볼지는 가운데 손잡이로 사용자가 정한다.
            #
            # 🚨 **계통 데이터 탭에서는 낮춘다** (2026-08-15). 아래는 이미 표에 66% 를
            #    주도록 돼 있는데(`_apply_split`), 이 최소치가 그걸 막고 있었다 —
            #    `min(…, room - 260)` 에 걸려 표가 353 을 받으려다 275 로 깎였고,
            #    위쪽 띠가 늘어난 만큼의 손실이 **전부 표로** 갔다.
            #
            # ⚠️ 단 **얼마나 낮출 수 있는지는 차트가 몇 개 쌓이느냐가 정한다.**
            #    처음에 그냥 150 으로 낮췄더니 「전압·위상」(차트 둘이 위아래로)에서
            #    한 개당 90px 밖에 안 돌아가 **x축 글자가 `...` 로 뭉개지고 아래가 잘렸다**
            #    (사용자가 보고 *"여기가 이상한데?"*). 옆으로 놓는 탭(조류 P·Q)과 한 장짜리
            #    (부하율·토폴로지)는 한 줄이라 낮춰도 멀쩡하다.
            gt.setMinimumHeight(self._graph_floor())
            # 🚨 **펼치기가 있으면 접기도 있어야 한다** (2026-08-15 사용자 지적).
            #    접혀 있을 때는 [그래프 펼치기] 가 그래프 자리에 바로 있는데, 펼치고 나면
            #    되접는 길이 저 멀리 위쪽 [숫자만] 뿐이었다 — 이름도 달라 같은 일인 줄
            #    몰랐다. **2026-08-18 에 그 위쪽 단추를 아예 없애 여기가 유일한 길이 됐다.**
            #    탭 줄 오른쪽 구석에 둔다 — **세로 자리를 안 먹는다.**
            fold = QPushButton("그래프 접기")
            fold.setObjectName("corner")
            fold.setToolTip("그래프를 접고 표를 넓게 씁니다.")
            fold.setCursor(Qt.PointingHandCursor)
            fold.clicked.connect(lambda: self.set_numbers(True))

            # 어느 것을 볼지 고르는 단추 — 차트를 여럿 가진 탭에만 뜬다.
            # 자리는 탭 줄 구석이라 **세로를 안 먹는다**(접기 단추와 같은 수법).
            corner = fold
            if stack_of:
                cur = min(self.graph_tab, gt.count() - 1)
                names = stack_of.get(cur) or next(iter(stack_of.values()))
                seg = QFrame()
                seg.setObjectName("segwrap")
                # 🚨 **34 로 두면 한글이 세로로 잘린다** (2026-08-28 화면 캡처로 확인).
                #    QSS 의 `padding:8px 14px` 이 위아래로 16px 을 먹어 글자에 10px 밖에
                #    안 남고, 잘린 윗부분 때문에 「전압」이 **「선압」**, 「위상각」이
                #    **「뷔상삭」** 으로 보였다(ㅈ 의 윗줄·ㄱ 의 윗줄이 사라진다).
                #    VSC 표의 [ON|OFF] 는 같은 34 인데 라틴 대문자라 티가 안 났다.
                # 🚨 **40 은 이번엔 반대로 넘쳤다** (2026-09-08 사용자: *"이거 겹쳐"*).
                #    탭 구석 자리가 32px 인데 40px 을 못 박아 **8px 이 아래 판 위로**
                #    삐져나갔다. 같은 날 seg 단추 여백을 8→5px 로 줄여 요구 높이가
                #    33px 로 내려왔으므로 34 면 든다.
                #    ⭐ 교훈 = **못 박은 높이는 한 번 맞으면 끝이 아니다** — 여백을
                #      건드릴 때마다 다시 재야 한다. ⇒ **아예 못 박지 않는다.**
                #      단추가 요구하는 만큼 묶음이 커지고, 탭 줄이 거기 맞춘다.
                seg.setStyleSheet(
                    f"#segwrap {{ background:{c['bg']};border:1px solid {c['border']};"
                    f"border-radius:9px; }}")
                sh = QHBoxLayout(seg)
                # 4px — 2px 이면 고른 단추(파란 판)가 묶음 테두리에 닿아 «여백이
                # 없다» 로 보인다 (2026-09-08 사용자 지적)
                sh.setContentsMargins(4, 4, 4, 4)
                sh.setSpacing(3)
                # 🚨 **폭을 글자에서 재서 준다.** 그냥 두면 「전압」이 53px 로 나와
                #    QSS 안쪽 여백(14px x 2)을 빼면 글자에 25px 밖에 안 남아
                #    **「선압」·「위상삭」 처럼 잘려 보인다**(2026-08-28 실측·확대해서 확인).
                #    sizeHint 가 QSS padding 을 안 세는 탓이라 여기서 직접 더한다.
                fm = self.fontMetrics()
                for i, pname in enumerate(names):
                    # 이름은 축 표기를 뗀 앞부분만 — "전압  [pu] · x축 = 버스" → "전압"
                    txt = pname.split("[")[0].strip()
                    b = QPushButton(txt)
                    b.setObjectName("seg_on" if i == self.plot_pick else "seg_off")
                    b.setCursor(Qt.PointingHandCursor)
                    b.setMinimumWidth(fm.horizontalAdvance(txt) + 36)
                    b.setFixedHeight(34)
                    b.clicked.connect(lambda _, x=i: self.set_plot_pick(x))
                    sh.addWidget(b)
                seg.setVisible(cur in stack_of)
                self._plot_seg = seg
                corner = QWidget()
                ch = QHBoxLayout(corner)
                # 아래 여백 = **판과 벌리는 거리** (2026-09-08 사용자: *"조금 더 위로
                # 띄우자"*). 0 이면 `[전압|위상각]` 이 그래프 판에 닿아 붙어 보인다.
                ch.setContentsMargins(0, 0, 0, 7)
                ch.setSpacing(10)
                ch.addWidget(seg)
                ch.addWidget(fold)
            gt.setCornerWidget(corner, Qt.TopRightCorner)
            gt.setObjectName("graphpanel")
            float_panel(gt, self.dark)
            split.addWidget(gt)
        else:
            note = QFrame()
            note.setObjectName("card")
            note.setMaximumHeight(58)
            nv = QHBoxLayout(note)
            nv.setContentsMargins(16, 10, 16, 10)
            # ⚠️ 예전 문구는 "약 5~7배 빠름" 이라고 말했는데 **사실이 아니다** —
            #    실측 0.86~1.49배다(`실측_R4_버스수대시간.csv`). 표가 그만큼 넓어져
            #    줄을 더 그리기 때문이다. 안 빨라지는 것을 빨라진다고 말하지 않는다.
            if self.numbers_why == "changed":
                msg = ("계통을 바꿔 계산해서 그래프를 접고 표를 넓게 폈습니다 — "
                       "펼치면 표가 그만큼 줄어듭니다.")
            elif self.numbers_why == "narrow":
                msg = ("표를 고치는 화면이라 그래프를 접고 표를 넓게 폈습니다 — "
                       "펼치면 표가 그만큼 줄어듭니다.")
            elif self.numbers_auto and self.sol is not None:
                n_bus = int(self.sol.AC.shape[0]) + \
                    int(self.sol.DC.shape[0] if self.sol.DC.size else 0)
                msg = (f"버스가 {n_bus:,}개라 그래프를 접어 두었습니다 — "
                       f"점이 겹쳐 읽기 어렵습니다. 값은 [엑셀로 만들기] 로 보세요.")
            else:
                msg = "그래프를 접고 표를 넓게 쓰는 중입니다"
            t = QLabel(msg)
            t.setStyleSheet(f"color:{c['muted']};font-size:14px;")
            nv.addWidget(t)
            nv.addStretch()
            b = QPushButton("그래프 펼치기")
            b.setObjectName("corner")
            b.setToolTip("큰 계통에서는 점이 겹쳐 덩어리로 보입니다. 그래도 보시려면 누르세요.")
            b.clicked.connect(lambda: self.set_numbers(False))
            nv.addWidget(b)
            v.addWidget(note)

        # ── 표 ──
        tw = GlassCard(c, self.dark, radius=16, tint=(0.50, 0.34))
        tv = QVBoxLayout(tw)
        # 판 안쪽 여백 — 0 이면 도구 줄과 표가 둥근 모서리에 붙어 판 밖처럼 보인다.
        # ⚠️ 가로는 **표 열을 그만큼 밀어낸다**(실측: 12px 씩 주니 열 넘침이 24px
        #    늘었다). 둥근 모서리를 가리지 않을 만큼만 준다.
        tv.setContentsMargins(8, 10, 8, 10)
        tv.setSpacing(7)

        # 두 갈래 — [결과] [시나리오 N] (2026-09-08 점검 i48)
        pane_row = self._pane_strip()
        if pane_row is not None:
            tv.addWidget(pane_row)

        # 🚨 이 줄은 **따로 한 줄을 쓰지 않는다** (2026-08-15). 표 묶음 186px 중 표에 남는
        #    것이 19px 뿐이었는데, 그 줄 하나가 46px 을 먹고 있었다.
        #    표 탭바 오른쪽 구석으로 옮기면 **세로 자리를 안 쓴다**(그래프 접기 단추와 같은 수법).
        # 🚨 2026-08-31 — 탭바를 **드롭다운으로 바꾸면서** 이 줄이 탭바 자리를 물려받았다.
        #    구석에서 나왔지만 탭바가 사라져 세로는 **9px** 만 더 든다(실측 39 → 48px).
        head_w = QWidget()
        head = QHBoxLayout(head_w)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)

        # ── 지금 무엇을 보고 있나 — 시간(스냅샷) · 버스(다이나믹) ──
        #    2026-09-08 에 맨 위 줄에서 여기로 내렸다 (점검 i56). 자세한 까닭은
        #    `header()` 의 주석. 「표」 왼쪽이다 — 시간을 먼저 고르고 그 시각의
        #    어느 표를 볼지 고르는 차례라 읽는 순서와 같다.
        vp = self.view_picker()
        if vp is not None:
            head.addWidget(vp)
            sep0 = QLabel("│")
            sep0.setStyleSheet(f"color:{c['border']};font-size:15px;")
            head.addWidget(sep0)
            sep0.setVisible(not focus)
            if focus and _tab_base(self.table_tab) == "계통 데이터":
                vp.setVisible(False)     # 넣은 값은 시각마다 다르지 않다

        # ── 어느 표를 볼지 고르는 드롭다운 ──
        # 🚨 **이름표를 붙인다** (2026-09-01 전수 조사). 탭 줄일 때는 모양 자체가
        #    「여기서 고른다」를 말했는데, 드롭다운이 되니 값(「AC 결과」)만 남아
        #    뭘 고르는 자리인지 안 보였다. 다른 고르개(시간·버스·해법)와 같은 꼴.
        tl = QLabel("표")
        tl.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:600;")
        head.addWidget(tl)
        tl.setVisible(not focus)
        # 🚨 **탭 줄로는 원래 안 되는 일이었다** (2026-08-31 실측). 다이나믹은 탭이
        #    8 개인데 창이 1920px 이 돼야 다 보인다 — 맥북 14인치 5/8 · 사이드카 2/8.
        #    구석을 줄여도(561 → 245px) 탭바가 요구하는 폭이 그대로라 안 풀린다.
        #    ⚠️ 목록은 **탭을 다 만든 뒤** 채운다 — 아래 `_fill_tab_pick` 참조.
        pick = Combo(self.c['muted'])
        pick.setFixedHeight(34)
        pick.setMinimumWidth(180)
        pick.setCursor(Qt.PointingHandCursor)
        pick.setStyleSheet(
            f"QComboBox {{ background:{c['surface']};color:{c['text']};"
            f"border:1px solid {c['border']};border-radius:9px;padding:0 12px;"
            f"font-size:14px;font-weight:600; }}"
            f"QComboBox:hover {{ border-color:{c['accent']}; }}"
            f"QComboBox::drop-down {{ border:none;width:24px; }}")
        self._tab_pick = pick
        head.addWidget(pick)
        pick.setVisible(not focus)

        # ── 위반 건수 ──
        # 🚨 탭 이름에 찍히던 「점검 (13)」 이 드롭다운으로 가면 **고르기 전엔 안 보인다.**
        #    개수는 안 눌러도 보여야 하므로 여기 따로 낸다 (2026-08-31 사용자 확정 「ㄱ」).
        #    표 위 주황 띠로는 대신할 수 없다 — 그건 전압만 센다.
        n_v = violation_count(self.viol())
        if n_v and not focus:
            # 「⚠ 26」 만으로는 정체가 툴팁에만 있었다 (2026-09-01 전수 조사)
            # — 상태바가 쓰는 말(「위반 26건」)과 같은 낱말로 밝힌다.
            vb = QPushButton(f"⚠ 위반 {n_v:,}")
            vb.setCursor(Qt.PointingHandCursor)
            vb.setFixedHeight(34)
            vb.setToolTip(f"한계를 넘은 것이 {n_v:,}건 있습니다 — 누르면 점검으로 갑니다")
            vb.setStyleSheet(
                f"background:{c['surface']};color:{c['warn']};font-weight:600;"
                f"border:1px solid {c['warn']};border-radius:9px;"
                f"padding:0 12px;font-size:13px;")
            vb.clicked.connect(self.go_check)
            head.addWidget(vb)

        head.addStretch()
        # 🚨 여기부터는 **결과 표에만 뜻이 있는 컨트롤**이다 (2026-09-01 전수 조사).
        #    계통 데이터·점검·수렴·시나리오에서도 그대로 보여서 — 「버스 번호로
        #    찾기」가 두 벌 나란히 뜨고, 「50줄」이 안 보이는 표를 세고 있었다.
        #    「열 선택」과 같은 수법으로 표에 맞춰 숨긴다(`_update_head_vis`).
        self._head_res = []
        # 🚨 「VSC 표」 이름표는 **없을 때만** 낸다 (2026-09-08 i23). 고르개를 없앤
        #    뒤에도 이름표가 남아 머리줄에 홀로 뜬 글자가 되었다 — 붙을 것이 없는
        #    이름표다. 변환기가 없는 계통에서는 그 옆 「없음」 과 짝이라 뜻이 있다.
        if not self.case_has_vsc:
            lab = QLabel("VSC 표")
            lab.setStyleSheet(f"color:{c['muted']};font-size:13px;")
            head.addWidget(lab)
            self._head_res.append(lab)
            off = QLabel("  없음  ")
            off.setStyleSheet(
                f"background:{c['bg']};color:{c['muted']};border:1px solid "
                f"{c['border']};border-radius:7px;padding:5px 4px;font-size:12px;")
            # 🚨 **없는 까닭이 둘이다** (2026-08-31 전수 조사). 예전에는 둘 다
            #    "변환기가 없습니다" 라고 말해, IC 가 3 개인 CIGRE 케이스에서도
            #    변환기가 없다고 우겼다.
            #      변환기 자체가 없다  → `vsc_ideal is None`
            #      이상적 변환기다      → `vsc_ideal is True` (내부 회로가 없어 VSC 버스가 없다)
            # 🚨 **툴팁만으로는 못 본다** (2026-09-08 점검 i68) — 마우스를 올려야
            #    나오니 "왜 표가 없지" 로 끝난다. 까닭을 글로 옆에 적는다.
            if self.vsc_ideal:
                why = "이상적 변환기라 내부 회로가 없습니다"
                tip = ("변환기를 이상적으로 보는 계통이라 내부 회로"
                       "(변압기·필터·리액터)가 없습니다 — VSC 버스 표도 없습니다")
            else:
                why = "이 계통에는 변환기가 없습니다"
                tip = "이 계통에는 변환기(VSC)가 없습니다"
            off.setToolTip(tip)
            head.addWidget(off)
            self._head_res.append(off)
            note = QLabel(why)
            note.setToolTip(tip)
            note.setStyleSheet(f"color:{c['muted']};font-size:11.5px;")
            head.addWidget(note)
            self._head_res.append(note)
        # 🚨 보일 것이 있으면 **끄고 켤 것 없이 그냥 낸다** (2026-09-08 점검 i23).
        #    여기 있던 [ON][OFF] 고르개는 「변환기 표를 볼래 말래」를 물었는데,
        #    안 볼 까닭이 없는 표다 — 계통에 변환기가 있으면 그 표가 답의 일부다.
        #    없을 때만 위처럼 **왜 없는지** 적는다.
        #    (`show_vsc` 는 시험 스크립트가 아직 부르므로 남겨 두되 기본이 켬이고
        #     화면에는 고르개가 없다.)
        # 버스 번호로 찾기 — 계통 데이터 탭에만 있던 것을 **결과 표에도** (2026-08-18).
        # 1,888버스 계통이면 표가 1,888줄인데 한 화면에 20줄이라 찾을 길이 없었다.
        # 자리는 이 머리 줄 — 원래 비어 있던 자리라 세로를 더 안 쓴다.
        if self.sol is not None:
            fl = QLabel("버스 번호로 찾기")
            fl.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            head.addWidget(fl)
            fb = QLineEdit(self.res_find or "")
            fb.setPlaceholderText("예: 106 107 (비우면 전부)")
            fb.setFixedWidth(190)
            fb.returnPressed.connect(lambda: self.set_res_find(fb.text()))
            fb.editingFinished.connect(lambda: self.set_res_find(fb.text()))
            head.addWidget(fb)
            self._find_label = QLabel("")
            head.addWidget(self._find_label)
            self._head_res += [fl, fb, self._find_label]
            # ⚠️ **항상 만들어 두고 숨김만 바꾼다.** 찾을 때마다 이 단추를 만들려고
            #    화면을 다시 그리면 6,495버스에서 **4.58초**다(실측). 띠에서 겪은
            #    것과 같은 수법으로 푼다 — 만들어 두고 보였다 숨겼다 한다.
            self._find_clear = QPushButton("전부 보기")
            self._find_clear.setCursor(Qt.PointingHandCursor)
            self._find_clear.setStyleSheet(
                f"border:none;background:transparent;color:{c['muted']};"
                f"font-size:12px;padding:0 4px;")
            self._find_clear.clicked.connect(lambda: self.set_res_find(""))
            head.addWidget(self._find_clear)
            self._find_clear.setVisible(bool(self.res_find))

        # 🚨 「열 선택」은 **결과 표에만** 뜻이 있다 (2026-08-27).
        #    점검·수렴·계통 데이터 탭에도 보였는데 눌러도 아무 일이 안 났다 —
        #    `TABLE_SPECS` 에 그 이름이 없어 `KeyError` 가 나고 Qt 가 삼켰다.
        #    죽은 단추를 두느니 그 탭에서는 안 보이게 한다.
        cb = QPushButton("열 선택")
        cb.clicked.connect(self.pick_columns)
        cb.setVisible(_tab_base(self.table_tab) in TABLE_SPECS)
        head.addWidget(cb)
        self._col_btn = cb

        tt = QTabWidget()
        # 🚨 **구석에 넣지 않는다** (2026-08-31). 구석은 탭 줄 안에 살아서, 탭바를
        #    감추면 **구석도 같이 사라진다**(실측 — 조작 줄이 통째로 없어졌다).
        #    그래서 제 줄로 꺼내고 탭바를 감춘다. 고르는 일은 드롭다운이 한다.
        # 🚨 **이 줄이 창 최소 가로를 끌어올린다** (2026-09-08). 시간 고르개를 여기로
        #    내리면서(i56) 창 최소 가로가 **1251 → 1429px** 이 돼 1366·1280 화면에
        #    안 들어갔다(`test_grid_scroll` [2]가 잡았다).
        #    계통 데이터의 조작 줄이 2026-08-19 에 밟은 길과 같은 수법으로 푼다 —
        #    줄을 접거나 감추지 않고 **넘치는 만큼만 밀리게** 한다. 넓은 화면에서는
        #    막대가 아예 안 생겨 지금과 똑같아 보인다.
        head_sa = QScrollArea()
        head_sa.setObjectName("tablebar")     # 시험이 이 줄을 집을 이름
        head_sa.setWidget(head_w)
        head_sa.setWidgetResizable(True)
        head_sa.setFrameShape(QFrame.NoFrame)
        head_sa.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        head_sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        def _fit_head():
            # 막대가 뜰 때만 그 높이를 얹는다 — 세로는 표가 먹을 자리다
            try:
                hb = head_sa.horizontalScrollBar()
                # 「표」 고르개(34 px)가 숨으면 줄 높이를 재는 기준이 사라져 시간 고르개가 잘렸다 — 바닥을 둔다
                head_sa.setFixedHeight(max(head_w.sizeHint().height(), 44 if focus else 0)
                                       + (hb.sizeHint().height() if hb.isVisible() else 0))
            except RuntimeError:
                pass

        head_sa.horizontalScrollBar().rangeChanged.connect(lambda *_: _fit_head())
        _fit_head()
        tv.addWidget(head_sa)
        self._tabs = tt
        tt.setTabPosition(QTabWidget.North)
        tt.tabBar().setVisible(False)

        if self.sol is not None:
            key = self.bus_row if self.mode == "다이나믹" else self.t
            specs = real_tables(self.sol, self.mode, key,
                                self.show_vsc and self.case_has_vsc)
            bad = self.violating_buses()
            over = self.overloaded_rows()
            for name, cols, arr in specs:
                # 🚨 **「열 선택」을 여기서 걸러야 한다** (2026-08-27). 여태 이 자리가
                #    엔진이 준 열을 통째로 그려서, 열을 골라 [적용] 해도 화면이 안 바뀌었다
                #    (`self.visible` 을 쓰는 곳은 **결과가 없을 때의 뼈대 표**뿐이었다).
                #    ⚠️ 거르면 **열 자리가 밀린다** — 버스 번호는 원래 0열이고 위반 표시·
                #       정수 표기가 그 자리를 쓴다. 그래서 **원래 자리(`keep`)를 들고 다닌다.**
                want = self.visible.get(name)
                keep = ([i for i, n in enumerate(cols) if n in want] if want
                        else list(range(len(cols))))
                if not keep:                      # 아는 열이 하나도 안 겹치면 다 보여 준다
                    keep = list(range(len(cols)))
                # 위반 표시는 **거르기 전** 버스 번호로 정한다 (0열이 꺼져 있을 수 있다)
                # 🚨 「선로 조류」도 칠한다 (2026-09-08 점검 i22). 여태 전압 위반 버스만
                #    주황이었고, 부하율이 100%를 넘은 선로는 점검 탭에서만 보였다 —
                #    선로 조류 표를 보면서는 어느 줄이 넘쳤는지 눈으로 못 찾았다.
                #    ⚠️ 줄 번호로 짚는다. From/To 로 짝지으면 평행 선로에서 하나만
                #       넘쳤는데 둘 다 칠해진다(`checks.overloaded_rows` 주석 참조).
                if name == "선로 조류":
                    flags = [r in over for r in range(arr.shape[0])]
                else:
                    flags = [name in ("AC 결과", "DC 결과")
                             and (name[:2], int(arr[r, 0])) in bad
                             for r in range(arr.shape[0])]
                cols = [cols[i] for i in keep]
                arr = arr[:, keep]
                t = QTableWidget(arr.shape[0], len(cols))
                t.setHorizontalHeaderLabels(cols)
                t.verticalHeader().setVisible(False)
                t.verticalHeader().setDefaultSectionSize(30)
                t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                t.setAlternatingRowColors(True)
                t.setItemDelegate(_TintDelegate(t))
                warn = QColor(self.c["warn"])
                for r in range(arr.shape[0]):
                    flag = flags[r]
                    for cc in range(len(cols)):
                        val = arr[r, cc]
                        # 정수로 찍는 것은 **원래 0열(버스 번호)** 일 때만이다
                        txt = f"{val:.0f}" if keep[cc] == 0 and float(val).is_integer() \
                            else f"{val:,.4f}".rstrip("0").rstrip(".")
                        it = NumItem(txt, val)
                        if cc > 0:
                            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        if flag:
                            it.setForeground(warn)
                            _s = QColor(self.c['surface'])
                            it.setBackground(QColor(round(_s.red() * 0.87 + warn.red() * 0.13), round(_s.green() * 0.87 + warn.green() * 0.13), round(_s.blue() * 0.87 + warn.blue() * 0.13)))
                        t.setItem(r, cc, it)
                # 🚨 **칸을 다 채운 뒤에 켠다.** 채우기 전에 켜면 한 칸 넣을 때마다
                #    표를 다시 늘어놓아 느리고, 넣는 자리가 밀려 값이 어긋난다.
                # 🚨 그리고 **켜는 순간 Qt 가 제멋대로 한 번 늘어놓는다** —
                #    `setSortingEnabled(True)` 가 지금 표시자(기본 0열)로 `sortByColumn`
                #    을 부른다. 실측: 아무것도 안 눌렀는데 버스가 302·301·224… 로
                #    뒤집혀 나왔다. ⇒ 켜기 전에 **표시자를 지운다**(-1 = 없음).
                self._applying_sort = True
                try:
                    t.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
                    t.setSortingEnabled(True)
                finally:
                    self._applying_sort = False
                self._apply_sort(name, t, cols)
                t.horizontalHeader().sortIndicatorChanged.connect(
                    lambda col, order, nm=name: self._sort_changed(nm, col, order))
                self._res_tables[name] = (t, list(cols))
                self._apply_find(name)
                tt.addTab(self._with_viol_legend(name, t, bad, cols), name)
                _fit_header(t)      # 정렬을 켠 뒤 · 탭에 붙인 뒤
        else:
            for name in tables_for(self.mode, self.show_vsc and self.case_has_vsc):
                cols = [n for n, _ in TABLE_SPECS[name] if n in self.visible[name]]
                t = QTableWidget(14, len(cols))
                t.setHorizontalHeaderLabels(cols)
                t.verticalHeader().setVisible(False)
                t.verticalHeader().setDefaultSectionSize(32)
                t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                t.setAlternatingRowColors(True)
                for r in range(14):
                    for cc in range(len(cols)):
                        it = QTableWidgetItem(fake(cc, r))
                        if cc > 0:
                            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        t.setItem(r, cc, it)
                tt.addTab(t, name)
                _fit_header(t)

        # 점검 · 수렴 탭 — 카드를 세로로 쌓아서 키가 크다(점검 490 · 수렴 378).
        # 그대로 넣으면 그 키가 **창의 최소 높이**가 돼 창을 못 줄인다. 스크롤에
        # 담아 창이 작아도 아래까지 갈 수 있게 한다(2026-08-13).
        _v = self.viol()
        n = violation_count(_v) + reached_count(_v)   # 탭에 든 줄 수 (위반 + 한계 도달)
        tt.addTab(_scrollable(self.check_page()), f"점검 ({n})" if n else "점검")
        conv_tab = _scrollable(self.conv_page())
        tt.addTab(conv_tab, "수렴")
        for _t in conv_tab.findChildren(QTableWidget):   # 반복별 블록 표 하나
            _fit_header(_t)
        # 🚨 `(1)` 이 **무엇의 수인지 안 보였다** (2026-09-08 점검 i35).
        #    옆의 「점검 (26)」·「시나리오 (4)」 는 그 탭에 든 것의 수인데 여기만
        #    «아직 계산 안 한 편집» 의 수라, 같은 꼴로 적으면 표가 한 줄이라고 읽힌다.
        n_ch = len(self.changes)
        tt.addTab(self.grid_page(),
                  f"계통 데이터 · 바꾼 것 {n_ch}" if n_ch else "계통 데이터")
        # 🚨 시나리오는 **여기 안 넣는다** (2026-09-08 점검 i48) — 위 두 갈래 띠로
        #    올렸다. 「AC 결과」·「점검」과 한 드롭다운에 있으면 결과 표 하나로 읽힌다.

        # 보고 있던 탭으로 되돌린다 — 조건을 하나 바꿀 때마다 화면을 다시 그리므로,
        # 이걸 안 하면 매번 첫 탭(AC 결과)으로 튄다.
        self._restore_tab(tt)
        # 드롭다운 목록은 **여기서** 채운다 — 탭이 다 만들어지고 어느 탭에 앉을지
        # 정해진 다음이어야 고른 값이 화면과 맞는다.
        self._fill_tab_pick(tt)
        # 표를 다 만든 뒤에 「N줄 중 M줄」 을 채운다 — 보고 있는 탭 기준이라
        # 탭이 정해진 다음이어야 한다.
        self._update_find_label()
        self._update_head_vis()
        tv.addWidget(tt)

        if getattr(self, "_focus_grid", False):
            # 「열 선택」 은 표 조작 줄로 옮겨 갔다(`grid_page`) — 머리 줄에 남은 것이 없어 빈 줄이었다
            head_sa.setVisible(False)
        # 🚨 시나리오 갈래에서는 **표 줄과 표를 통째로 숨긴다** (2026-09-08 i48).
        #    지우지 않고 숨기는 까닭 = 위에서 만든 `_tab_pick`·`_res_tables` 를
        #    보는 곳이 여럿이라(찾기·열 선택·정렬) 없애면 그것들이 다 깨진다.
        if getattr(self, "pane", "결과") == "시나리오" and pane_row is not None:
            head_sa.setVisible(False)
            tt.setVisible(False)
            sp = self.scenario_bar()
            if sp is not None:
                tv.addWidget(_scrollable(sp), 1)
        # 표 묶음도 최소치를 못 박는다 — 안 그러면 가장 키 큰 탭이 창의 최소
        # 높이를 정해 버린다(Qt 는 최소치를 손으로 정하면 그것을 먼저 본다).
        tw.setMinimumHeight(170)
        tw.setObjectName("tablepanel")
        float_panel(tw, self.dark)
        split.addWidget(tw)

        if not self.numbers and not focus:
            split.setStretchFactor(0, 3)      # 표가 sizeHint 로 밀고 올라오는 걸 막는다
            split.setStretchFactor(1, 2)
            self._apply_split(split)
            # 탭을 옮기면 **그 탭에 맞는 자리**로 바꾼다 (화면은 다시 안 그린다)
            def _switch(i, w=tt, s=split):
                # 앱 2.3 — 탭이 바뀌면 카드가 차례로 나타난다. 자리가 모자라 화면을 통째로
                # 다시 그린 경우(`_table_tab_changed` 가 True)에는 옛 탭이 곧 지워지므로
                # **새로 그려진 화면의 탭**에 건다.
                if self._table_tab_changed(_tab_base(w.tabText(i)), s):
                    nt = getattr(self, "_tabs", None)
                    snap, self._pre_snap = getattr(self, "_pre_snap", None), None
                    if nt is not None:
                        pg = nt.currentWidget()
                        crossfade_from(self, snap, lambda p=pg: rise_in(p), pg)
                else:
                    rise_in(w.widget(int(i)))
                    self._sync_rail()        # 화면을 안 다시 그렸으니 사이드바만 맞춘다
            tt.currentChanged.connect(_switch)
            split.splitterMoved.connect(lambda *_: self._save_split(split))
        else:
            tt.currentChanged.connect(
                lambda i, w=tt: (setattr(self, "table_tab", _tab_base(w.tabText(i))),
                                 self._update_head_vis(), rise_in(w.widget(int(i))),
                                 self._sync_rail()))
        v.addWidget(split, 1)
        return w

    # ── 위아래 나눔 ────────────────────────────────────────────────────
    # 「계통 데이터」 는 값을 고치는 탭이라 **줄이 여럿 보여야** 하고, 결과 탭은
    # 그래프가 커야 한다. 한 자리로 둘을 다 맞출 수 없어 **탭마다 따로** 기억한다
    # (2026-08-13 사용자: "계통 데이터 탭 여기가 너무 작아서 불편해").

    def _graph_rows(self) -> int:
        """지금 그래프 탭에서 차트가 **몇 줄로 쌓이나**. 옆으로 놓는 탭은 한 줄이다."""
        # ⚠️ 2026-08-28 부터 **위아래로 쌓지 않는다** — 여럿이면 한 장씩 골라 본다
        #    (`plot_pick`). 옆으로 놓는 탭(조류 P·Q)도 원래 한 줄이라, 지금은 어느
        #    탭이든 한 줄이다. 쌓는 탭이 다시 생길 때를 대비해 셈은 남겨 둔다.
        try:
            _name, plots, layout = GRAPHS[self.mode][self.graph_tab]
        except (KeyError, IndexError):
            return 1
        return 1 if (layout != "v" or len(plots) > 1) else len(plots)

    # 그래프 높이 두 가지 — **다시 실측했다**(2026-08-18, 50버스 · 창 950px).
    # 🚨 2026-08-15 에 적어 둔 *"320 → 제대로 나온다"* 는 **틀렸다.** 두 줄짜리 탭에서
    #    320·360·400·420 이 전부 **세로축 숫자를 `...` 로 뭉갠다.** 숫자가 살아나는
    #    문턱은 **425** 다(420 뭉개짐 · 430 나옴). 한 줄짜리는 150 에서도 멀쩡하다.
    #    ⇒ 두 줄 바닥을 320 → **425** 로 올린다. 이 값을 못 주는 탭에서는 그래프를
    #      **접는다**(`_graph_fits`) — 못 읽는 그래프를 자리만 차지한 채 두지 않는다.
    #    함께 버린 안 둘: **차트 제목 떼기**(380 에서도 여전히 뭉갠다 — 제목이 원인이
    #    아니었다) · **전압·위상을 좌우로 놓기**(세로축은 살지만 50버스의 x축 번호가
    #    `1... 1... ...` 로 통째로 죽는다).
    # 🚨 2026-11-15 — 1줄 바닥 150 → 300. 11-02 에 그래프 제목 15 px · 축 글자 12 px 로 키운 뒤로는
    #    판 245 px(그림 155 px)에서 세로축 눈금이 전부 `...` 였다(1440 × 900 실측).
    GRAPH_FLOOR = {1: 300, 2: 425}
    GRAPH_WANT = {1: 340, 2: 380}
    # 그래프 말고 **나머지**가 요구하는 세로. 창 최소 = 이 값 + 그래프 최소 높이다
    # (2026-08-19 실측: 최소 높이 425 → 창 747 · 260 → 582 로 **1:1 로 따라온다**.
    #  실제 몫은 322px 이고 케이스 넷에서 모두 같았다 — AC·AC/DC 가리지 않는다).
    # 24px 을 얹어 둔다. 나중에 머리나 띠가 늘어도 바로 화면 밖으로 안 나가게.
    NON_GRAPH_H = 346
    # 이 아래로는 그래프를 줄이지 않는다 — 더 줄이면 그릴 것이 없다
    GRAPH_FLOOR_MIN = {1: 200, 2: 260}
    # 이 폭보다 좁은 화면이면 조작 줄을 **좁은 판**으로 (아래 `_narrow`)
    NARROW_W = 1400

    # 점검 탭 표 — 한 줄 높이 · 머리글이 먹는 몫 · 몇 줄에서 끊나 (2026-08-18)
    #   한 줄 30px 은 `setDefaultSectionSize(30)` 으로 못박혀 있어 폰트와 무관하다.
    #   머리글은 이 맥에서 **40px 실측**인데 폰트가 바뀌면 커질 수 있어 **6px 여유**를 둔다
    #   (모자라면 마지막 줄이 잘리고, 남으면 표 아래에 빈 띠가 6px 생길 뿐이다).
    #   가로 스크롤은 열이 `QHeaderView.Stretch` 라 뜨지 않으므로 셈에서 뺀다(실측 확인).
    CHECK_ROW_H = 30
    CHECK_CHROME = 46
    CHECK_MAX_ROWS = 10

    def _screen_avail(self):
        """이 창이 놓인 화면에서 **실제로 쓸 수 있는** 크기 (작업표시줄·독을 뺀 것).

        창을 못 띄운 상태(만드는 중)면 주 화면을 쓴다. 화면을 못 읽으면 넉넉한
        값을 돌려 **지금까지와 똑같이** 굴게 한다 — 못 읽었다고 좁은 판으로 가면
        큰 화면 쓰는 사람이 손해를 본다.
        """
        scr = self.screen() if self.isVisible() else None
        scr = scr or QGuiApplication.primaryScreen()
        if scr is None:
            return 3840, 2160
        g = scr.availableGeometry()
        return g.width(), g.height()

    def _narrow(self) -> bool:
        """조작 줄을 좁은 판으로 써야 하는 화면인가.

        🚨 2026-08-19 신설. 창 최소 가로 1392px 중 **1076px 이 「계통 데이터」 탭
        하나**가 요구하는 값이었고(다른 탭은 88~322px), 그 안에서도 한 위젯이 아니라
        **가로로 나란히 놓인 조작 줄의 합**이었다. 1366×768 노트북에서 가로가 26px
        모자라 앱이 화면에 안 들어갔다.
        """
        return self._screen_avail()[0] < self.NARROW_W

    def _graph_floor(self) -> int:
        """그래프에 남겨 둘 **최소** 높이 — **읽을 수 있는 크기**다.

        얼마나 필요한지는 차트가 몇 줄로 쌓이느냐가 정한다(위아래로 둘이면 한 장이
        절반씩 나눠 갖는다). ⚠️ 예전에는 **탭마다 달랐다** — 계통 데이터 탭은
        `GRAPH_FLOOR`, 나머지는 260. 그런데 260 도 320 도 세로축을 뭉개는 값이라
        (2026-08-18 실측) 탭을 가릴 이유가 없어졌다. **어느 탭이든 읽을 수 있는
        크기가 최소이고, 그걸 못 주면 접는다.**
        """
        rows = self._graph_rows()
        want = self.GRAPH_FLOOR.get(rows, self.GRAPH_FLOOR[2])
        # 🚨 **화면보다 큰 창은 만들지 않는다** (2026-08-19).
        #    이 값은 그래프의 `setMinimumHeight` 로 들어가 **창 최소 세로를 그대로
        #    끌어올린다**(창 최소 = NON_GRAPH_H + 이 값). 화면이 낮으면 창이 화면
        #    밖으로 나가 버려 아예 못 쓴다 — 뭉개진 축이 안 뜨는 창보다 낫다.
        cap = self._screen_avail()[1] - self.NON_GRAPH_H
        if cap < want:
            return max(self.GRAPH_FLOOR_MIN.get(rows, self.GRAPH_FLOOR_MIN[2]), cap)
        return want

    def _room_for_graph(self) -> int:
        """위아래로 나눠 쓸 수 있는 높이. `_apply_split` 이 쓰는 셈과 같게 맞춘다."""
        sp = self._split
        tot = sum(sp.sizes()) if sp is not None else 0
        room = tot if (sp is not None and sp.isVisible() and tot > 300) \
            else self.height() - 190
        return max(430, room)

    def _graph_fits(self, tab=None) -> bool:
        """그 탭에서 **읽을 수 있는 그래프**와 표 몫을 함께 줄 수 있나.

        계통 데이터 탭은 표에 66% 를 주기로 돼 있어(표를 고치는 곳이다) 그래프에
        남는 것이 34% 뿐이다. 950px 창이면 271px — **최소 높이 425 에 한참 못 미친다.**
        그럴 때 예전에는 그래프를 425 로 붙들어 표를 373 으로 깎았는데, 그러면
        **표도 좁고 그래프도 못 읽는다.** 접으면 표가 전부 갖는다.
        """
        tab = self.table_tab if tab is None else tab
        # 🚨 **표를 고치는 탭은 자리가 있어도 접는다** (2026-08-28 사용자 확정).
        #    ⚠️ 예전에는 「그래프 최소 높이(두 장 쌓기 425)가 표 몫을 뺀 나머지에
        #       안 들어간다」는 셈으로 접었다. 같은 날 전압·위상을 **한 장씩** 보이게
        #       바꾸자 그 최소가 150 으로 내려가 셈이 뒤집혔고, 계통 데이터 탭의 표가
        #       **23줄 → 14줄로 줄었다**(창 1920x1080 실측). 결과 탭에서 4줄 얻고
        #       여기서 9줄을 잃은 셈이라 되돌린다.
        #    ⇒ 접는 근거는 **자리가 아니라 그 탭이 하는 일**이다. 값을 고치러 들어온
        #       자리에는 표를 다 준다. 그래프는 결과 탭에서 본다.
        return self._split_slot(tab) != "grid"

    def _fold_for_room(self, tab=None) -> bool:
        """자리 때문에 접거나 펴야 하면 상태를 바꾸고 True. 부르는 쪽이 다시 그린다.

        사용자가 **직접 펼친 뒤**(`graph_kept`)에는 건드리지 않는다 — 그때는
        `_apply_split` 이 그래프를 우선으로 놓아 읽을 수 있는 크기를 준다.
        """
        if self.graph_kept:
            return False
        fits = self._graph_fits(tab)
        if not self.numbers and not fits:
            self.numbers, self.numbers_auto = True, True
            self.numbers_why = "narrow"
            return True
        # 좁아서 접은 것이면, 자리가 나는 탭으로 가면 도로 편다
        if self.numbers and self.numbers_why == "narrow" and fits:
            self.numbers, self.numbers_auto = False, False
            self.numbers_why = ""
            return True
        return False

    def _graph_want(self) -> int:
        """사용자가 **직접 펼쳤을 때** 그래프에 주는 높이 — 읽을 수 있는 크기."""
        return self.GRAPH_WANT.get(self._graph_rows(), 380)

    # 표가 주인공인 탭 — 그래프보다 표에 자리를 몰아 준다 (2026-08-18 사용자 확정).
    #   계통 데이터 = 표를 **고치는** 곳 · 점검 = 무엇이 걸렸는지 **읽는** 곳.
    # 🚨 둘이 접히는 까닭은 서로 다르다. 계통 데이터는 표에 66% 를 주면 그래프에
    #    425px 이 안 남는다는 **자리 계산**으로 접힌다(`_graph_fits`). 점검은 자리로만
    #    보면 431px 이 나오지만, 표 셋(전압 위반·과부하 선로·발전기 한계)이 352px 에
    #    들어가질 않아 **한 표도 온전히 안 보였다**(실측: 다 보이는 표 0개 → 접으면 2개).
    #    그래서 여기 목록에 넣어 같은 길을 타게 한다.
    # 표에 주는 몫 (2026-08-28 사용자 확정).
    #   예전에는 **결과 탭 0.38 · 계통 데이터/점검 0.66** 으로 갈랐다. 그런데
    #   **계산 결과를 읽는 자리가 데이터를 고치는 자리보다 표를 적게 받는 것**이
    #   앞뒤가 안 맞았다 — 결과 표는 14줄짜리인데 8줄만 보였다.
    # 🚨 이 값을 올려도 **그래프는 안 뭉개진다** — 아래 `keep`(=`_graph_floor`)이 하한이라
    #    그래프가 최소 높이 밑으로는 안 깎인다. 실측으로 확인: 억지로 [325, 423] 을 줘도
    #    Qt 가 [425, 323] 으로 되돌린다.
    # ⚠️ 그래서 **창이 작으면 이 값을 올려도 표가 별로 안 는다**. 전압·위상 탭은
    #    그래프를 두 장 쌓아 최소 높이가 425 라, 작은 화면에서는 이 값과 무관하게 잠긴다.
    TABLE_SHARE = 0.66

    TABLE_FIRST = ("계통 데이터", "점검")

    def _split_slot(self, tab=None):
        tab = self.table_tab if tab is None else tab
        # 점검 탭은 이름이 "점검 (26)" 처럼 건수를 달고 다니므로 앞부분으로 본다
        return "grid" if any(tab.startswith(n) for n in self.TABLE_FIRST) else "other"

    def _apply_split(self, split, tab=None):
        slot = self._split_slot(tab)
        saved = (self.split_sizes or {}).get(slot)
        if saved:
            split.setSizes(saved)
            return
        # 화면에 붙어 있으면 진짜 높이를, 아직 만드는 중이면 창 높이로 어림한다
        tot = sum(split.sizes())
        room = tot if (split.isVisible() and tot > 300) else self.height() - 190
        room = max(430, room)
        # 🚨 **직접 펼쳤으면 그래프가 우선이다** (2026-08-15 사용자 확정 —
        #    *"사용자가 키고 싶으면 그때 그래프를 띄우고 표는 작게 줄이자"*).
        #    계통 데이터 탭은 평소 표에 66% 를 주는데, 그 규칙을 그대로 두면 그래프가
        #    늘 최소 높이만 받아 **축 글자가 뭉개진 채**로 보인다. 보겠다고 누른 사람에게
        #    못 읽는 그래프를 주는 것은 안 켜 준 것과 같다.
        # ⚠️ 예전에는 `slot == "grid"` 로 잠겨 있어 **계통 데이터 탭에만** 걸렸다.
        #    그 바람에 결과 탭에서 [그래프 펼치기] 를 누르면 393px 밖에 안 받아
        #    **펼쳐 놓고도 세로축이 뭉개졌다**(2026-08-18 실측). 바로 위 주석이
        #    금지한 그 상태다. ⇒ 어느 탭에서 눌러도 읽을 수 있는 크기를 준다.
        if self.graph_kept and not self.numbers:
            # ⚠️ `room` 으로 깎지 않는다 — 다시 그리는 도중에는 그 값이 실제보다 작게
            #    잡혀(470 으로 잡힌 적이 있다) 그래프 요청이 270 까지 깎였고, 결국 최소 높이만
            #    받았다. **원하는 비율로 넘기고 남는 자리는 Qt 가 나눠 준다.**
            split.setSizes([self._graph_want(), 200])
            return
        # 데이터 고칠 땐 아래를 크게, 결과 볼 땐 그래프를 크게.
        share = self.TABLE_SHARE
        # 그래프에 남겨 둘 최소치. **위 `gt.setMinimumHeight` 과 같은 값이어야 한다** —
        # 어긋나면 그래프 최소를 낮춰 놓고도 여기서 도로 깎아 표가 안 넓어진다(2026-08-15).
        keep = self._graph_floor()
        bottom = min(max(int(room * share), 350), room - keep)
        split.setSizes([room - bottom, bottom])

    def _save_split(self, split):
        """손으로 끈 자리는 **그 탭 것으로만** 기억한다."""
        if not isinstance(self.split_sizes, dict):
            self.split_sizes = {}
        self.split_sizes[self._split_slot()] = split.sizes()

    def _table_tab_changed(self, name, split):
        if name == self.table_tab:
            return
        self._save_split(split)          # 떠나는 탭의 자리를 먼저 적어 둔다
        self.table_tab = name
        self._update_head_vis()          # 결과용 컨트롤(찾기·VSC 표·열 선택)을 표에 맞춘다
        # 자리가 모자라 접거나, 자리가 나서 도로 펴야 하면 화면을 다시 그린다
        # (그래프 자리가 통째로 안내 띠로 바뀌므로 split 만 고쳐서는 안 된다)
        if self._fold_for_room(name):
            self._pre_snap = snap_central(self)
            self.rebuild()
            return True              # 화면을 다시 그렸다 — 부른 쪽이 새 탭에 움직임을 건다
        self._apply_split(split)
        return False

    # ── 시작 화면 (파일을 아직 안 불러왔을 때) ──
    def start_page(self):
        c = self.c
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(60, 0, 60, 0)
        v.setSpacing(0)
        v.addStretch()

        title = QLabel("UNIGRID")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color:{c['text']};font-size:44px;font-weight:800;letter-spacing:4px;")
        v.addWidget(title)
        sub = QLabel("AC/DC 통합 조류계산")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color:{c['muted']};font-size:16px;")
        v.addWidget(sub)

        # 🚨 **시작 화면에도 「정보」로 가는 길을 둔다** (2026-08-19 — MathWorks 라이선스 고지에 닿아야 한다).
        #    시작 화면엔 사이드바가 없으므로(2026-11-03) 여기 단추가 그 길이다.
        ir = QHBoxLayout()
        ir.addStretch()
        about = QPushButton("정보")
        about.setObjectName("seg_off")
        about.setCursor(Qt.PointingHandCursor)
        about.setToolTip("판·저작권·사용 조건")
        about.clicked.connect(lambda: AboutDialog(self, c).exec())
        ir.addWidget(about)
        ir.addStretch()
        v.addSpacing(10)
        v.addLayout(ir)
        v.addSpacing(22)

        # 파일 놓는 자리 — 점선 칸 + 아이콘 + 형식 칩 (S1: 구성은 그대로 · 꼴만 결과 화면과 맞춤)
        import navside
        drop = DropCard(c, self.dark)
        drop.setObjectName("dropzone")
        drop.setFixedWidth(START_CARD_W)
        dv = QVBoxLayout(drop)
        dv.setContentsMargins(28, 26, 28, 22)
        dv.setSpacing(8)
        # 진한 판 위 — 흰 네모 + 먹색 아이콘
        ic = navside.IconSq("open", dict(c, text="#ffffff", surface=c["nav"]), _rail_icon, True, size=52, dark=True)
        ir = QHBoxLayout(); ir.addStretch(); ir.addWidget(ic); ir.addStretch()
        dv.addLayout(ir)
        dv.addSpacing(4)
        d1 = QLabel("계통 파일을 여기로 끌어다 놓으세요")
        d1.setAlignment(Qt.AlignCenter)
        d1.setStyleSheet(f"color:{c['nav_text']};font-size:19px;font-weight:700;background:transparent;")
        dv.addWidget(d1)
        self.dropzone = drop        # 끌어다 놓을 때 밝히려고 들고 있는다
        self.drop_label = d1
        fr = QHBoxLayout(); fr.setSpacing(6); fr.addStretch()
        for t in ("UNIGRID 엑셀 .xlsx", "MATPOWER .m", "PSS/E .raw"):
            ch = QLabel(t)
            ch.setStyleSheet(f"background:{c['nav_on']};color:{c['nav_fg']};border-radius:8px;"
                             "padding:4px 10px;font-size:12px;")
            fr.addWidget(ch)
        fr.addStretch()
        dv.addLayout(fr)
        dv.addSpacing(8)
        row = QHBoxLayout()
        row.addStretch()
        pick = QPushButton("파일 고르기")
        pick.setCursor(Qt.PointingHandCursor)
        pick.setStyleSheet(f"QPushButton {{ background:#ffffff; color:{c['nav']}; border:none; border-radius:11px;"
                           "font-size:14px; font-weight:700; padding:10px 22px; }"
                           "QPushButton:hover { background:#e6e8ee; }")
        pick.setMinimumSize(150, 44)
        pick.clicked.connect(self.do_import)
        row.addWidget(pick)
        row.addStretch()
        dv.addLayout(row)
        # 「엑셀로 만들기」 — 칸 밖 밑줄 줄이었던 것을 칸 안 한 줄로
        lk = QHBoxLayout(); lk.setSpacing(4); lk.addStretch()
        lt = QLabel("계통 파일이 없으면 →")
        lt.setStyleSheet(f"color:{c['nav_fg']};font-size:13px;background:transparent;")
        lk.addWidget(lt)
        conv = QPushButton("엑셀로 만들기")
        conv.setStyleSheet(f"QPushButton {{ background:transparent; border:none; color:{c['nav_text']};"
                           "font-size:13px; padding:4px 6px; text-decoration:underline; }")
        conv.setCursor(Qt.PointingHandCursor)
        conv.setToolTip("MATPOWER · PSS/E · MatACDC 파일을 UNIGRID 엑셀로 (DC · 변환기를 직접 넣으려면)")
        conv.clicked.connect(lambda: ConvertDialog(self, c).exec())
        lk.addWidget(conv)
        lk.addStretch()
        dv.addSpacing(4)
        dv.addLayout(lk)
        hb = QHBoxLayout()
        hb.addStretch(); hb.addWidget(drop); hb.addStretch()
        v.addLayout(hb)
        v.addSpacing(26)

        # 최근에 연 파일 — 한 카드 안 줄 목록(파일 아이콘 · 버스 수 · 계통 알약 · ›)
        recent = load_recent()
        if recent:
            cap = QLabel("최근에 연 파일")
            cap.setStyleSheet(f"color:{c['text']};font-size:14px;font-weight:800;")
            cw = QWidget()
            # 🚨 그림자가 퍼질 자리를 남긴다 (2026-09-09 — 판 오른쪽 아래 «각진 귀»)
            cw.setFixedWidth(START_CARD_W + SHADOW_ROOM * 2)
            cvv = QVBoxLayout(cw)
            cvv.setContentsMargins(SHADOW_ROOM, 0, SHADOW_ROOM, SHADOW_ROOM)
            cvv.setSpacing(9)
            cap.setContentsMargins(6, 0, 0, 0)
            cvv.addWidget(cap)
            box = GlassCard(c, self.dark, radius=18)
            box.setObjectName("recentcard")
            float_panel(box, self.dark)
            bv = QVBoxLayout(box)
            bv.setContentsMargins(14, 4, 14, 4)
            bv.setSpacing(0)
            for k, item in enumerate(recent):
                if k:
                    ln = QFrame(); ln.setFixedHeight(1); ln.setStyleSheet(f"background:{c['border']};")
                    bv.addWidget(ln)
                bv.addWidget(self._recent_row(item))
            cvv.addWidget(box)
            hb2 = QHBoxLayout()
            hb2.addStretch(); hb2.addWidget(cw); hb2.addStretch()
            v.addLayout(hb2)

        v.addStretch()
        # 최근 파일이 여섯이면 시작 화면이 893 px 을 요구했다 — 창이 낮으면 안이 밀리게 담는다
        outer.addWidget(_clear_scroll(body), 1)

        # 아래 — 엔진 준비 상태
        bar = QFrame()
        bar.setObjectName("statusbar")
        bar.setFixedHeight(42)
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(20, 0, 20, 0)
        self.warm_dot = QLabel("●")
        self.warm_dot.setStyleSheet(f"color:{c['muted']};font-size:13px;")
        self.warm_txt = QLabel("계산 엔진 준비 중...")
        self.warm_txt.setStyleSheet(f"color:{c['muted']};font-size:13px;")
        bh.addWidget(self.warm_dot)
        bh.addWidget(self.warm_txt)
        bh.addStretch()
        theme = ThemeSwitch(self.dark, c)          # 화면 밝기 — 사이드바가 없는 시작 화면의 자리
        theme.setToolTip("화면을 어둡게/밝게 바꿉니다")
        theme.setCursor(Qt.PointingHandCursor)
        theme.flipped.connect(self.toggle_theme)
        bh.addWidget(theme)
        bh.addSpacing(14)
        ver = QLabel("UNIGRID Desktop — 개발 중")
        ver.setStyleSheet(f"color:{c['muted']};font-size:12px;")
        bh.addWidget(ver)
        outer.addWidget(bar)

        if ENGINE.is_ready():
            self._warm_done(True)
        elif getattr(self, "warm", None) is None:
            self.warm = WarmThread()
            self.warm.ready.connect(self._warm_done)
            self.warm.start()
        return page

    def _recent_row(self, item):
        """최근 파일 한 줄 — 파일 아이콘 · 이름 · 버스 수 · 계통 알약(AC only / AC/DC 혼합 · DC only) · ›."""
        import navside
        c = self.c
        info = item.get("info", "") or ""
        kind = info.split("·")[0].strip()
        counts = info.split("·")[1].strip().replace(" / ", " · ") + " 버스" if "·" in info else ""
        b = QPushButton()
        b.setObjectName("recentrow2")
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(58)
        b.setToolTip(str(item["path"]))
        b.setStyleSheet(f"#recentrow2 {{ background:transparent; border:none; border-radius:10px; }}"
                        f"#recentrow2:hover {{ background:{c['bg']}; }}")
        b.clicked.connect(lambda _, p=item["path"]: self.open_path(p))
        h = QHBoxLayout(b); h.setContentsMargins(4, 0, 6, 0); h.setSpacing(12)
        ic = navside.IconSq("grid", c, _rail_icon, False, size=32, dark=self.dark)
        h.addWidget(ic)
        tv = QVBoxLayout(); tv.setSpacing(1)
        n = QLabel(Path(item["path"]).name)
        n.setStyleSheet(f"color:{c['text']};font-size:14px;font-weight:700;background:transparent;")
        m = QLabel(counts)
        m.setStyleSheet(f"color:{c['muted']};font-size:12px;background:transparent;")
        tv.addWidget(n); tv.addWidget(m)
        h.addLayout(tv, 1)
        if kind:
            mixed = "혼합" in kind
            dc_only = "DC" in kind and "AC" not in kind.replace("AC/DC", "")
            bg = ("qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(224,108,108,.22), stop:1 rgba(111,168,220,.22))"
                  if mixed else ("rgba(111,168,220,.22)" if kind.startswith("DC") else "rgba(224,108,108,.18)"))
            pl = QLabel(kind)
            pl.setStyleSheet(f"background:{bg};color:{c['muted']};border-radius:7px;padding:3px 9px;"
                             "font-size:11.5px;font-weight:700;")
            pl.setFixedHeight(24)
            h.addWidget(pl, 0, Qt.AlignVCenter)
        ar = QLabel("›"); ar.setStyleSheet(f"color:{c['muted']};font-size:20px;background:transparent;")
        h.addWidget(ar)
        for w in (ic, n, m, ar):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        if kind:
            pl.setAttribute(Qt.WA_TransparentForMouseEvents)
        return b

    def _warm_done(self, ok):
        if getattr(self, "warm_dot", None) is None:
            return
        c = self.c
        self.warm_dot.setStyleSheet(
            f"color:{c['ok'] if ok else c['warn']};font-size:13px;")
        self.warm_txt.setText("계산 엔진 준비됨" if ok
                              else "계산 엔진을 띄우지 못했습니다")
        self.warm_txt.setStyleSheet(
            f"color:{c['ok'] if ok else c['warn']};font-size:13px;")

    # ── 파일 끌어다 놓기 ──
    def dragEnterEvent(self, e):
        if dropped_path(e):
            e.acceptProposedAction()
            self.set_hot(True)
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if dropped_path(e):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self.set_hot(False)

    def dropEvent(self, e):
        path = dropped_path(e)
        self.set_hot(False)
        if not path:
            e.ignore()
            return
        e.acceptProposedAction()
        self.open_path(path)

    def set_hot(self, on):
        """끌어온 파일이 창 위에 있을 때 놓는 자리를 밝게."""
        if self.dropzone is None:
            return
        c = self.c
        if on:
            self.dropzone.set_hot(True)
            if self.drop_label is not None:
                self.drop_label.setText("놓으면 바로 계산합니다")
                self.drop_label.setStyleSheet(
                    f"color:{c['nav_text']};font-size:19px;font-weight:700;background:transparent;")
        else:
            self.dropzone.set_hot(False)
            if self.drop_label is not None:
                self.drop_label.setText("계통 파일을 여기로 끌어다 놓으세요")
                self.drop_label.setStyleSheet(
                    f"color:{c['nav_text']};font-size:19px;font-weight:700;background:transparent;")

    def open_path(self, path):
        """최근 파일에서 바로 열기."""
        if not Path(path).exists():
            QMessageBox.warning(self, "불러오기", "파일을 찾을 수 없습니다.")
            return
        self._start_solve(path)

    def case_card(self):
        """지금 무엇을 보고 있는지 — 파일 · 계통 종류 · 버스 수."""
        c = self.c
        name, info = self.case
        mode_txt = info.split("·")[0].strip()          # 예: "AC/DC 혼합"
        counts = info.split("·")[1].strip() if "·" in info else ""

        box = QFrame()
        box.setObjectName("card")
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 12, 14, 13)
        v.setSpacing(7)

        top = QHBoxLayout()
        cap = QLabel("현재 케이스")
        cap.setStyleSheet(f"color:{c['muted']};font-size:12px;font-weight:600;")
        top.addWidget(cap)
        # 🚨 여기 있던 「바꾸기」를 없앴다 (2026-09-08 점검 i07). 머리줄의
        #    「불러오기」와 **같은 `do_import` 를 부르는 같은 단추**였다 —
        #    이름이 다르니 서로 다른 일을 한다고 읽힌다(i29 와 같은 갈래).
        top.addStretch()
        v.addLayout(top)

        stem = name.replace(".xlsx", "").replace(".m", "").replace(".raw", "")
        # Qt 는 밑줄을 줄 끊는 자리로 안 쳐서 긴 이름이 그냥 잘린다.
        # 밑줄 뒤에 폭 0짜리 끊김표(U+200B)를 넣어 두 줄까지 보이게 한다.
        f = QLabel(stem.replace("_", "_​"))
        f.setWordWrap(True)
        f.setToolTip(str(getattr(self, "_last_path", "") or name))
        f.setStyleSheet(f"color:{c['text']};font-size:16px;font-weight:600;")
        v.addWidget(f)

        ext = QLabel(name.split(".")[-1].upper() + " 파일")
        ext.setStyleSheet(f"color:{c['muted']};font-size:11px;")
        v.addWidget(ext)

        # 계통 종류 = 알약 표시
        pill = QLabel("  " + mode_txt + "  ")
        pill.setStyleSheet(
            f"background:{c['accent_soft']};color:{c['accent']};"
            f"border-radius:9px;padding:4px 6px;font-size:12px;font-weight:600;")
        pr = QHBoxLayout()
        pr.addWidget(pill)
        pr.addStretch()
        v.addLayout(pr)

        # 버스 수
        if counts:
            v.addWidget(hline_soft(c))
            cr = QHBoxLayout()
            cr.setSpacing(18)
            for part in counts.split("/"):
                part = part.strip()
                if not part:
                    continue
                bits = part.split()
                lab = bits[0] if bits else part
                num = bits[-1] if len(bits) > 1 else ""
                col = QVBoxLayout()
                col.setSpacing(0)
                a = QLabel(lab + " 버스")
                a.setStyleSheet(f"color:{c['muted']};font-size:11px;")
                b = QLabel(num)
                b.setStyleSheet(
                    f"color:{c['text']};font-size:18px;font-weight:600;")
                col.addWidget(a)
                col.addWidget(b)
                cr.addLayout(col)
            # baseMVA — 계산 결과가 아니라 계통 속성이라 여기가 맞는 자리
            if self.sol is not None:
                col = QVBoxLayout()
                col.setSpacing(0)
                a = QLabel("baseMVA")
                a.setStyleSheet(f"color:{c['muted']};font-size:11px;")
                b = QLabel(f"{self.sol.baseMVA:g}")
                b.setStyleSheet(
                    f"color:{c['text']};font-size:18px;font-weight:600;")
                col.addWidget(a)
                col.addWidget(b)
                cr.addLayout(col)
            cr.addStretch()
            v.addLayout(cr)
        return box

    def freq_text(self):
        """상태바에 넣을 주파수 한 줄. 값이 없으면 None (2026-08-30 사이드바 카드에서 옮김).

        ⚠️ **스냅샷에서만 부른다** — 값이 `self.t`(지금 보는 시각)에 묶여 있어
        다이나믹·비교에는 「지금 시각」이라는 것이 아예 없다.
        """
        if self.sol is None or not self.sol.freq.size:
            return None
        f = float(self.sol.freq[min(self.t, self.sol.freq.size - 1)])
        # 기준 주파수는 케이스마다 다르다 (60 Hz / 50 Hz) — 못 박으면 안 된다
        nominal = self.sol.freq_nominal
        # 데드밴드도 케이스 파일에서 읽는다. 예전엔 ±0.05 Hz 라고 내가 정한 값을
        # 썼는데, 실제 값은 0.036 Hz 이거나 아예 0 이다(app_engine._freq_deadband).
        db = self.sol.freq_db
        # 데드밴드는 "이 폭 밖에서만 droop 이 동작한다"는 폭이다. 밖에 있다고
        # 잘못된 상태가 아니라 **droop 이 동작 중**이라는 뜻이라 경고색을 안 쓴다.
        # 진짜 위반(전압·과부하·변환기 한계)은 상태바 왼쪽과 점검 탭이 따로 센다.
        if db <= 0:
            where = "droop 동작"           # 데드밴드가 없으면 늘 동작한다
        elif abs(f - nominal) <= db:
            where = "droop 멈춤"
        else:
            where = "droop 동작 중"
        return f"{f:.2f} Hz · {where}"

    def viol(self):
        """지금 화면의 위반 목록 (실제 결과가 있으면 실제값)."""
        if self.sol is None:
            return VIOLATIONS
        return real_violations(self.sol, self.t)

    # ── 결과 표에서 버스 번호로 찾기 (2026-08-18) ─────────────────────────
    #    계통 데이터 탭에만 있던 것을 결과 표에도 붙였다. 1,888버스 계통이면 표가
    #    1,888줄인데 한 화면에 20줄이라, 특정 버스를 보려면 95화면을 굴려야 했다.
    #    ⭐ **줄을 숨겨서** 거른다 — 화면을 다시 그리지 않으므로 6,495버스에서도 즉시다.

    RES_ID_COLS = ("Bus", "From", "To")   # 버스 번호가 든 열 이름

    def _apply_find(self, name):
        """찾는 번호에 안 걸리는 줄을 숨긴다. 찾는 게 없으면 전부 보인다."""
        keep = self._res_tables.get(name)
        if keep is None:
            return 0, 0
        table, cols = keep
        want = self._find_numbers()
        idc = [i for i, cn in enumerate(cols) if cn in self.RES_ID_COLS]
        n = table.rowCount()
        if not want or not idc:
            for r in range(n):
                table.setRowHidden(r, False)
            return n, n
        shown = 0
        for r in range(n):
            hit = False
            for ci in idc:
                it = table.item(r, ci)
                if it is None:
                    continue
                try:
                    if int(float(it.text().replace(",", ""))) in want:
                        hit = True
                        break
                except ValueError:
                    continue
            table.setRowHidden(r, not hit)
            shown += int(hit)
        return n, shown

    def _find_numbers(self):
        """찾기 칸에서 뽑아낸 버스 번호들. **글자만 쳤으면 빈 집합**이다.

        빈 집합은 「비우면 전부」와 셈이 같아 `_apply_find` 가 전부 보여 준다 —
        그래서 라벨까지 같으면 사용자는 *안 먹은 건지 전부인 건지* 알 수 없다
        (2026-08-31 전수 조사). 가르는 일은 `_update_find_label` 이 한다.
        """
        return {int(x) for x in re.findall(r"\d+", self.res_find or "")}

    def _find_missing(self, name):
        """찾는 번호 중 **그 표에 없는** 것 (2026-09-08 점검 i28).

        예전에는 없는 번호를 치면 표가 통째로 비고 「1,888줄 중 0줄」만 떴다 —
        *번호가 틀린 건지 정말 그 버스에 아무것도 없는 건지* 갈리지 않았다.
        """
        want = self._find_numbers()
        keep = self._res_tables.get(name)
        if not want or keep is None:
            return set()
        table, cols = keep
        idc = [i for i, cn in enumerate(cols) if cn in self.RES_ID_COLS]
        if not idc:
            return set()
        have = set()
        for r in range(table.rowCount()):
            for ci in idc:
                it = table.item(r, ci)
                if it is None:
                    continue
                try:
                    have.add(int(float(it.text().replace(",", ""))))
                except ValueError:
                    pass
        return want - have

    def set_res_find(self, text):
        """찾는 번호가 바뀌었다 — **화면을 다시 그리지 않고** 줄만 걸러 낸다."""
        text = (text or "").strip()
        if text == (self.res_find or ""):
            return
        self.res_find = text
        for nm in list(self._res_tables):
            self._apply_find(nm)
        self._update_find_label()

    def _update_find_label(self):
        if self._find_clear is not None:
            self._find_clear.setVisible(bool(self.res_find))
        lb = self._find_label
        if lb is None:
            return
        nm = self._tabs.tabText(self._tabs.currentIndex()) if self._tabs else ""
        if nm not in self._res_tables:
            nm = next(iter(self._res_tables), "")
        if not nm:
            lb.setText("")
            return
        n, shown = self._apply_find(nm)
        c = self.c
        if self.res_find and not self._find_numbers():
            # 🚨 친 것에 숫자가 하나도 없다 — 예전에는 빈칸과 **똑같이** 「14줄」 이라
            #    아무 일도 안 난 것처럼 보였다(2026-08-31). 번호를 달라고 말한다.
            lb.setText("번호를 넣어 주세요")
            lb.setStyleSheet(f"color:{c['warn']};font-size:12px;font-weight:600;")
        elif (miss := self._find_missing(nm)):
            # 🚨 **없는 번호를 짚어 준다** (2026-09-08 점검 i28). 「0줄」만 뜨면
            #    번호를 잘못 친 건지 그 버스에 아무것도 없는 건지 갈리지 않는다.
            few = ", ".join(str(x) for x in sorted(miss)[:3])
            more = f" 외 {len(miss) - 3}" if len(miss) > 3 else ""
            lb.setText(f"{few}{more} — 이 표에 없는 번호입니다")
            lb.setStyleSheet(f"color:{c['warn']};font-size:12px;font-weight:600;")
        elif self.res_find and shown != n:
            lb.setText(f"{n:,}줄 중 {shown:,}줄")
            lb.setStyleSheet(f"color:{c['accent']};font-size:12px;font-weight:600;")
        else:
            lb.setText(f"{n:,}줄")
            lb.setStyleSheet(f"color:{c['muted']};font-size:12px;")

    # 결과 표에만 뜻이 있는 머리 줄 컨트롤 — 이 표들에서는 숨긴다 (2026-09-01).
    _HEAD_OFF = ("점검", "수렴", "계통 데이터", "시나리오")

    def _col_btn_text(self):
        """「열 선택」 단추 글자 — 숨긴 열이 있으면 **몇 개인지 밝힌다** (2026-09-02).

        🚨 안 밝히면 다음에 열었을 때 **「열이 왜 없지」** 가 된다. 숨김은 세션 내내
           남는데 화면에는 아무 표시가 없었다(결과 표도 처음부터 같았다).
           계통 데이터는 **고치는 표**라 더 아프다 — 안 보이는 열은 고칠 수도 없다.
        📌 다 켜져 있으면 숫자를 안 붙인다 — 늘 붙이면 숫자가 뜻을 잃는다.
        ⚠️ **결과 표에는 안 붙인다.** 거기는 `TABLE_SPECS` 의 `always` 로 **처음부터
           일부만** 켠다(AC 결과가 7/13) — 손대지 않아도 숫자가 뜨니 「내가 뭘 껐나」로
           읽힌다. 계통 데이터는 기본이 **전부**라 숫자가 곧 「내가 껐다」다.
        """
        tab = _tab_base(self.table_tab)
        if tab != "계통 데이터":
            return "열 선택"
        cols = getattr(self, "_grid_all_cols", None)
        if not cols:
            return "열 선택"
        vis = self.grid_visible.get(self.grid_key)
        total = len(cols)
        on = total if vis is None else sum(1 for j, _ in cols if j in vis)
        return "열 선택" if on >= total else f"열 선택 {on}/{total}"

    def _update_head_vis(self):
        """머리 줄의 결과용 컨트롤(VSC 표·찾기·N줄·열 선택)을 지금 표에 맞춘다.

        계통 데이터에서도 그대로 보여서 「버스 번호로 찾기」가 두 벌 나란히 뜨고,
        「50줄」이 **안 보이는 결과 표**를 세고 있었다 (2026-09-01 전수 조사).
        「열 선택」이 2026-08-27 에 밟은 길(뜻 없는 탭에서는 숨긴다)을 그대로 간다.
        """
        tab = _tab_base(self.table_tab)
        on = tab not in self._HEAD_OFF
        for w in getattr(self, "_head_res", []):
            w.setVisible(on)
        fc = getattr(self, "_find_clear", None)
        if fc is not None:            # 「전부 보기」는 찾는 중일 때만 — 조건을 겹친다
            fc.setVisible(on and bool(self.res_find))
        cb = getattr(self, "_col_btn", None)
        if cb is not None:
            # 계통 데이터도 켠다 (2026-09-02) — 열이 가장 많은 표가 여기다
            # (IC 20열이 1512px 창에서 903px 넘친다). 단, 조정·부하 판은 표가 아니다.
            grid_ok = (tab == "계통 데이터"
                       and self.grid_key not in (ADJ.KEY, LOAD_KEY))
            cb.setVisible(tab in TABLE_SPECS or grid_ok)
            cb.setText(self._col_btn_text())

    def _apply_sort(self, name, table, cols):
        """적어 둔 정렬을 다시 건다. 없으면 원래 순서 그대로 둔다."""
        want = self.sort_by.get(name)
        if not want:
            return
        col, order = want
        if not (0 <= col < len(cols)):
            self.sort_by.pop(name, None)      # 열 선택으로 그 열이 사라졌다
            return
        # 🚨 빗장 — `sortItems` 도 `sortIndicatorChanged` 를 낸다. 안 막으면
        #    `_sort_changed` → `rebuild` → 여기 → 또 신호 로 **끝없이 돈다.**
        self._applying_sort = True
        try:
            table.sortItems(col, order)
        finally:
            self._applying_sort = False

    def _sort_changed(self, name, col, order):
        """열 머리를 눌렀다 — 적어 두고 **띠만** 다시 채운다.

        🚨 처음엔 여기서 `rebuild()` 를 불렀는데 **못 쓸 만큼 느렸다**(실측:
           50버스 0.17초 · 1,888버스 2.05초 · **6,495버스 5.97초**). 정렬은 "이 열로
           봐야지" 하고 자주 누르는 것이고, **정렬이 가장 필요한 게 큰 계통인데
           거기서 제일 느리다.** 게다가 다시 그릴 까닭도 없다 — 표는 Qt 가 이미
           늘어놓았고, 달라지는 것은 위 띠 한 줄뿐이다.
        """
        if self._applying_sort:
            return
        self.sort_by[name] = (int(col), order)
        # 🚨 **찾기를 다시 건다.** 줄 숨김은 *줄 번호*로 걸리는데 정렬은 줄을
        #    뒤섞으므로, 다시 안 걸면 **엉뚱한 줄이 숨는다.**
        self._apply_find(name)
        self._fill_strip(name)

    def _clear_sort(self, name):
        self.sort_by.pop(name, None)
        self.rebuild()

    def _fill_strip(self, name):
        """표 위 띠의 내용을 다시 채운다. 보일 것이 없으면 숨긴다.

        띠를 **미리 만들어 두고 내용만 갈아 끼운다** — 정렬을 누를 때마다 화면을
        통째로 다시 그리지 않으려면 이 방법뿐이다(위 `_sort_changed` 참고).
        """
        keep = self._strips.get(name)
        if keep is None:
            return
        bar, cols = keep
        h = bar.layout()
        while h.count():                      # 옛 내용을 비운다
            it = h.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        c = self.c
        bad = self.violating_buses()
        if name == "선로 조류":
            n = len(self.overloaded_rows())
            what = "부하율이 100%를 넘은 선로"
        else:
            n = (sum(1 for grid, _bus in bad if grid == name[:2])
                 if name in ("AC 결과", "DC 결과") else 0)
            what = "전압이 한계를 벗어난 버스"
        sorted_by = self.sort_by.get(name)
        # 🚨 **정렬 중이면 위반이 없어도 띄운다** (2026-08-18 사용자 확정).
        #    안 그러면 성한 계통에서 정렬했을 때 되돌릴 길이 화면에 없다 —
        #    열 머리를 다시 눌러도 오름 ↔ 내림만 오갈 뿐 「원래 순서」로는 못 간다.
        if not n and not sorted_by:
            bar.hide()
            return
        bar.show()

        if n:
            sq = QLabel("■")
            sq.setStyleSheet(f"color:{c['warn']};font-size:13px;")
            h.addWidget(sq)
            txt = QLabel(f"주황 = {what} {n}곳")
            txt.setStyleSheet(f"color:{c['text']};font-size:13px;")
            h.addWidget(txt)

        if sorted_by:
            col, order = sorted_by
            col_name = cols[col] if cols and 0 <= col < len(cols) else "?"
            way = "작은 값부터" if order == Qt.AscendingOrder else "큰 값부터"
            if n:
                sep = QLabel("·")
                sep.setStyleSheet(f"color:{c['border']};font-size:13px;")
                h.addWidget(sep)
            st = QLabel(f"{col_name} {way} 늘어놓음")
            st.setStyleSheet(f"color:{c['accent']};font-size:13px;font-weight:600;")
            h.addWidget(st)
            back = QPushButton("원래 순서로")
            back.setCursor(Qt.PointingHandCursor)
            back.setStyleSheet(
                f"border:none;background:transparent;color:{c['muted']};"
                f"font-size:13px;padding:0 4px;")
            back.clicked.connect(lambda _=False, nm=name: self._clear_sort(nm))
            h.addWidget(back)

        h.addStretch()

        # 🚨 여기 있던 「자세히 보기 →」 를 없앴다 (2026-09-08 점검 i29).
        #    머리줄 「⚠ 위반 N」 과 **같은 `go_check` 를 부르는 같은 단추**였다 —
        #    한 화면에 같은 길이 둘이면 서로 다른 데로 간다고 읽힌다.
        #    개수까지 말해 주는 머리줄 쪽을 남긴다.

    def _with_viol_legend(self, name, table, bad, cols=None):
        """표 위에 띠를 얹어 돌려준다 — **주황이 무슨 뜻인지**와 **정렬 상태**.

        계기(주황) — AC·DC 결과 표에서 전압 한계를 벗어난 버스는 **줄 전체가 주황**
        인데, 그 규칙이 화면 어디에도 안 적혀 있었다. 표에 `Vmin[pu]`·`Vmax[pu]` 열이
        있어 눈으로 짚으면 짐작은 되지만, **짐작해야 한다는 게 문제**다.
        계기(정렬) — 열 머리로 늘어놓고 나면 **원래 순서로 돌아갈 길**이 필요하다.

        자리는 **탭 줄과 표 사이**다. 표 위로 끼어들므로 어떤 줄도 가리지 않는다.
        ⚠️ 보일 것이 없어도 **띠는 만들어 둔다(숨김)** — 정렬을 누를 때 이 띠만
           갈아 끼우려면 미리 있어야 한다(`_fill_strip`). 안 그러면 화면을 통째로
           다시 그려야 하고, 그건 6,495버스에서 6초다.
        """
        c = self.c
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("violbar")
        bar.setFixedHeight(38)
        bar.setStyleSheet(
            f"#violbar {{ background:{c['accent_soft']};"
            f"border-bottom:1px solid {c['border']}; }}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(14, 0, 12, 0)
        h.setSpacing(8)

        self._strips[name] = (bar, list(cols or []))
        v.addWidget(bar)
        v.addWidget(table, 1)
        # 🚨 **채우기는 레이아웃에 넣은 뒤에** (2026-08-18). Qt 는 위젯을 레이아웃에
        #    넣을 때 부모가 보이면 **자동으로 다시 보이게** 한다. 먼저 채우면서
        #    `bar.hide()` 를 불러도 그 다음 `addWidget` 이 도로 켜 버려서,
        #    위반도 정렬도 없는 계통에 **빈 파란 띠**가 그대로 남았다(시험이 잡았다).
        self._fill_strip(name)
        return box

    def violating_buses(self):
        """표에서 빨갛게 칠할 (계통, 버스번호) 집합."""
        out = set()
        if self.sol is None:
            return out
        cols, rows = self.viol().get("전압 위반", ([], []))
        for r in rows:
            parts = r[0].split()
            if len(parts) == 2 and parts[1].isdigit():
                out.add((parts[0], int(parts[1])))
        return out

    def overloaded_rows(self):
        """선로 조류 표에서 주황으로 칠할 **줄 번호** (2026-09-08 점검 i22)."""
        if self.sol is None:
            return set()
        key = self.bus_row if self.mode == "다이나믹" else self.t
        return checks_overloaded(self.sol, key)

    # ── 점검 탭 ──
    # ══════════════════════════ 계통 조건 (PDR §7 2단계) ══════════════════════════
    # 바꾸는 동안은 **계산하지 않는다.** 다 바꾸고 [이 조건으로 계산] 을 누를 때 한 번 푼다
    # (2026-08-06 사용자 확정). 버튼 한 번 = 조류계산 한 번 = 시나리오 한 줄.

    def change_bar(self):
        """무엇을 바꿨는지 + [이 조건으로 계산] · [되돌리기] · [원본으로].

        ⚠️ **예전에는 `self.changes` 가 있을 때만 만들었다.** 그래서 [이 조건으로 계산] 을
           누르는 순간 띠가 통째로 사라졌고, **원본으로 돌아갈 길이 화면에서 없어졌다.**
           길이 없던 게 아니라 시나리오 목록 안에 숨어 있었는데, 그 목록은 시나리오가
           2개 이상일 때만 그려지고 거기가 *조건을 되돌리는 곳* 이라고 말하지도 않는다.
           (사용자: *"선로 4번을 껐는데 5번을 끄고 싶다. 직접 되돌리는 게 불안하다"*)

        ⚠️ **2026-08-15 자리를 옮겼다.** 처음엔 굳은 상태에서도 이 띠를 남겼는데,
           **시나리오 카드와 같은 말을 두 곳에서** 하면서 44px + 간격을 먹었고 그만큼
           아래 표가 눌렸다(사용자: *"표가 너무 작아서 보기 힘들다"*). ⇒ 「⟲ 원본으로」는
           **시나리오 카드 머리로** 옮기고, 이 띠는 원래대로 *아직 안 푼 것이 있을 때만* 뜬다.
           단 카드가 안 그려지는 경우(시나리오가 하나뿐 — 원본을 지웠을 때)에는
           돌아갈 길이 또 사라지므로 그때는 여기가 맡는다.
        """
        # 시나리오 목록이 아래 탭으로 내려갔으므로(2026-08-15), 굳은 조건이 있으면
        # **늘** 이 한 줄이 나온다 — 지금 무슨 조건을 보고 있는지와 돌아갈 길.
        if not self.changes and not self.applied:
            return None
        c = self.c
        pending = bool(self.changes)          # 아직 안 푼 것이 있나
        edge = c["warn"] if pending else c["border"]
        bar = QFrame()
        bar.setObjectName("card")
        bar.setStyleSheet(
            f"#card {{ background:{c['surface']};border:1px solid {edge};"
            f"border-radius:10px; }}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(15, 9, 11, 9)
        h.setSpacing(11)

        if pending:
            tag = QLabel(f"바꾼 것 {len(self.changes)}건")
            tag.setStyleSheet(
                f"color:{c['warn']};font-size:12px;font-weight:600;padding:2px 9px;"
                f"border:1px solid {c['warn']};border-radius:9px;")
            h.addWidget(tag)

            what = QLabel(SC.describe(self.changes))
            what.setStyleSheet(f"color:{c['text']};font-size:13px;font-weight:600;")
            h.addWidget(what)
        else:
            # 다 계산해 놓은 상태 — 경고가 아니라 **지금 무슨 조건을 보고 있나**를 말한다.
            tag = QLabel("지금 조건")
            tag.setStyleSheet(
                f"color:{c['muted']};font-size:12px;padding:2px 9px;"
                f"border:1px solid {c['border']};border-radius:9px;")
            h.addWidget(tag)

            what = QLabel(SC.describe(self.applied))
            what.setStyleSheet(f"color:{c['text']};font-size:13px;font-weight:600;")
            h.addWidget(what)

        if pending:
            if self.task == "PV·QV 곡선":
                # 곡선은 **이 조건을 이미 쓴다**(`curve_case` 가 changes 까지 얹는다).
                # 조류계산 쪽 문구("아직 계산 안 함")를 그대로 두면 곡선이 옛 조건으로 그려진
                # 줄 알게 된다 — 실제로는 여유가 이미 달라져 있다.
                wait = QLabel("곡선은 이 조건으로 그립니다")
                wait.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            else:
                base = "원본" if not self.applied else SC.describe(self.applied)
                wait = QLabel(f"아직 계산 안 함 — 지금 화면은 「{base}」 결과입니다")
                wait.setStyleSheet(f"color:{c['warn']};font-size:12px;")
            h.addWidget(wait)

            # 쪼개짐은 **막지 않고 알려만 준다** (2026-08-06 확정 — 71bus 는 모든 선로가 쪼갠다)
            if self.base_case is not None:
                msg = SC.splits(self.base_case, self.changes)
                if msg:
                    warn = QLabel("계통이 쪼개집니다")
                    warn.setStyleSheet(
                        f"color:{c['warn']};font-size:12px;font-weight:600;"
                        f"background:{c['bg']};border-radius:8px;padding:3px 9px;")
                    warn.setToolTip(msg + "\n\n막지는 않습니다. 떨어져 나간 쪽에 전원이 없으면 "
                                          "그 답은 뜻이 없으니 결과를 볼 때 감안하세요.")
                    h.addWidget(warn)
        h.addStretch(1)

        if pending and self.task != "PV·QV 곡선":
            # 곡선 화면에는 안 붙인다 — 여기서 누르면 **조류계산**이 돈다.
            # 곡선은 왼쪽 [곡선 그리기] 가 자기 실행이다.
            run = QPushButton("▶  이 조건으로 계산")
            run.setObjectName("primary")
            run.setCursor(Qt.PointingHandCursor)
            run.clicked.connect(self.run_changes)
            h.addWidget(run)

        if pending:
            undo = QPushButton("↩ 되돌리기")
            undo.setToolTip("아직 계산 안 한 것만 물립니다.\n"
                            "이미 계산해서 보고 있는 조건은 그대로 둡니다.")
            undo.setCursor(Qt.PointingHandCursor)
            undo.clicked.connect(self.undo_changes)
            h.addWidget(undo)

        # 이미 계산해 굳은 조건이 있을 때만 — 「되돌리기」가 못 하는 일이다.
        if self.applied:
            home = QPushButton("⟲ 원본으로")
            home.setToolTip("파일을 열었을 때의 계통으로 돌아갑니다.\n"
                            "바꾼 것은 시나리오 목록에 그대로 남습니다.")
            home.setCursor(Qt.PointingHandCursor)
            home.clicked.connect(self.reset_to_base)
            h.addWidget(home)
        return bar

    def reset_to_base(self):
        """파일을 열었을 때의 계통으로 돌아간다.

        「↩ 되돌리기」와 하는 일이 다르다 — 저건 **아직 계산 안 한 것**만 지운다.
        [이 조건으로 계산] 을 누르는 순간 그 조건은 굳고, 그때부터 되돌리기로는 못 푼다.
        """
        base = self.book.base() if self.book is not None else None
        # 🚨 `book.base()` 는 원본이 없으면 **첫 시나리오로 떨어진다**(`scenario.py:481`).
        #    그걸 그대로 쓰면 「원본으로」가 엉뚱한 조건으로 데려간다 ⇒ 바꾼 것이 없는지 직접 본다.
        if base is not None and base.solved and not base.changes:
            self.show_scenario(base)      # 이미 푼 답을 들고 있으므로 **다시 안 푼다**
            return
        # 원본 결과가 없다(파일을 열고 아직 한 번도 원본으로 안 풀었다) — 조건만 비운다.
        self.changes = []
        self.applied = []
        self.rebuild()
        reveal(getattr(self, "_center_w", None))   # 원본으로 되돌리기

    # ── ② 부하 일괄 증감 ──────────────────────────────────────────────
    # 칸을 하나씩 고치는 대신 **부하 전체에 한 수를 곱한다**. 부하 여유(margin)를 보는
    # 가장 흔한 방법이라 슬라이더 하나로 둔다. 발전은 넣지 않았다 — 슬랙이 차액을 다 받아
    # 무엇 때문에 답이 달라졌는지 흐려진다.

    def load_factor(self, changes=None):
        """지금 걸려 있는 배수 (원본 대비). 곱하기가 여러 개면 다 곱한 값이다."""
        f = 1.0
        for ch in (self.applied + self.changes if changes is None else changes):
            if isinstance(ch, SC.Scale):
                f *= float(ch.factor)
        return f

    def load_total(self, changes):
        """지금 보고 있는 시각의 총 부하 [MW] — P 만 센다 (Q 는 따로 안 보여 준다)."""
        case = SC.apply(self.base_case, changes) if changes else self.base_case
        total = 0.0
        for key in ("AC_PLoad_dat", "DC_PLoad_dat"):
            arr = SC._values(case, key)
            if arr.size == 0 or arr.shape[1] < 2:
                continue
            col = min(self.t + 1, arr.shape[1] - 1)      # 0열은 버스 번호
            total += float(np.nansum(arr[:, col]))
        return total / 1e6

    def load_times(self):
        """부하표가 들고 있는 시각 수 (1이면 한 시각짜리 계통)."""
        n = 1
        for key in SC.LOAD_TABLES:
            arr = SC._values(self.base_case, key)
            if arr.size and arr.shape[1] > 1:
                n = max(n, arr.shape[1] - 1)          # 0열은 버스 번호
        return n

    def has_load(self):
        return self.base_case is not None and any(
            SC._values(self.base_case, k).size for k in SC.LOAD_TABLES)

    def load_bar(self, inline: bool = False):
        """부하 전체 ×배수 슬라이더. 여기서도 **바로 계산하지 않는다.**

        `inline` 이면 카드 테두리 없이 **표 고르기 줄 안에** 들어간다 — 따로 한 줄을
        쓰면 그만큼 표가 줄어든다(2026-08-15: 표에 19px 밖에 안 남아 있었다).
        """
        if not self.has_load():
            return None
        c = self.c
        now = self.load_factor()
        if inline:
            bar = QWidget()
            h = QHBoxLayout(bar)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
        else:
            bar = QFrame()
            bar.setObjectName("card")
            bar.setStyleSheet(f"#card {{ background:{c['surface']};"
                              f"border:1px solid {c['border']};border-radius:10px; }}")
            h = QHBoxLayout(bar)
            h.setContentsMargins(15, 7, 11, 7)
            h.setSpacing(11)

        tag = QLabel("부하 전체")
        tag.setStyleSheet(f"color:{c['text']};font-size:13px;font-weight:600;")
        h.addWidget(tag)

        sl = QSlider(Qt.Horizontal)
        sl.setRange(50, 200)
        # 적어 넣은 값이 슬라이더 범위 밖이면 손잡이를 끝에 붙여 둔다 — 값 자체는
        # 옆 칸이 그대로 보여 준다(2026-09-08 i41).
        sl.setValue(max(50, min(200, int(round(now * 100)))))
        # 좁은 화면에서는 더 줄인다 — 이 줄의 합이 창 최소 가로를 정한다(`_narrow`)
        sl.setFixedWidth((110 if self._narrow() else 150) if inline else 240)
        sl.setTickPosition(QSlider.TicksBelow)
        sl.setTickInterval(25)
        n_t = self.load_times()
        sl.setToolTip("모든 부하에 같은 수를 곱합니다."
                      + (f"\n이 계통은 {n_t}시각짜리이고, **모든 시각에 함께** 걸립니다."
                         if n_t > 1 else ""))
        h.addWidget(sl)

        # 🚨 **숫자로도 적을 수 있게** (2026-09-08 점검 i41). 여태 읽기만 하는
        #    글자라 슬라이더로만 정했는데, 슬라이더는 ×0.50~×2.00 이고 한 칸이
        #    0.01 이라 «정확히 ×1.37» 을 맞추기가 어렵다. 그리고 **범위 밖**
        #    (×2.5 로 어디서 무너지나)은 아예 못 넣었다.
        vx = QLabel("×")
        vx.setStyleSheet(f"color:{c['accent']};font-size:14px;font-weight:600;")
        h.addWidget(vx)
        val = QLineEdit(f"{now:.2f}")
        val.setFixedWidth(52)
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        val.setToolTip("바로 적어도 됩니다 — 슬라이더 범위(0.50~2.00) 밖도 넣을 수 있습니다")
        val.setStyleSheet(
            f"QLineEdit {{ color:{c['accent']};font-size:14px;font-weight:600;"
            f"background:{c['surface']};border:1px solid {c['border']};"
            f"border-radius:6px;padding:2px 5px; }}"
            f"QLineEdit:focus {{ border-color:{c['accent']}; }}")
        h.addWidget(val)

        def typed():
            """적은 값을 받는다. 못 읽을 값이면 지금 값으로 되돌린다."""
            try:
                want = float(val.text().replace("×", "").replace(",", "").strip())
            except ValueError:
                val.setText(f"{self.load_factor():.2f}")
                return
            # ⚠️ 0 이하는 막는다 — 부하가 0 이면 계통이 다른 것이 되고,
            #    음수는 부하가 발전이 되어 버린다.
            if want <= 0:
                QMessageBox.warning(self, "부하 배율",
                                    "0 보다 큰 수를 넣어 주세요.")
                val.setText(f"{self.load_factor():.2f}")
                return
            if abs(want - self.load_factor()) < 1e-9:
                return
            self.scale_loads(want)

        val.returnPressed.connect(typed)
        val.editingFinished.connect(typed)

        # 🚨 곱하기는 **모든 시각**에 걸리는데 여기 뜨는 합계는 **보고 있는 시각 하나**다.
        #    시간을 바꾸면 이 숫자도 따라 움직여서 "이 시각에만 걸리나?" 로 읽힌다
        #    (2026-08-06 사용자 질문) ⇒ 여러 시각짜리면 어느 시각인지 라벨에 밝힌다.
        base_mw = self.load_total([])
        now_mw = self.load_total(self.applied + self.changes)
        when = f" ({min(self.t, n_t - 1) + 1} H)" if n_t > 1 else ""
        tot = QLabel(f"총 부하 {base_mw:,.1f} → {now_mw:,.1f} MW{when}"
                     if abs(now - 1.0) > 1e-9 else f"총 부하 {base_mw:,.1f} MW{when}")
        tot.setStyleSheet(f"color:{c['muted']};font-size:12px;")
        if n_t > 1:
            tot.setToolTip(f"지금 보고 있는 시각의 합입니다. "
                           f"곱하기는 {n_t}시각 전부에 걸립니다.")
        h.addWidget(tot)
        if not inline:
            h.addStretch(1)

        back = QPushButton("원래대로 (×1)")
        back.setCursor(Qt.PointingHandCursor)
        back.setEnabled(abs(now - 1.0) > 1e-9)
        back.clicked.connect(lambda: self.scale_loads(1.0))
        h.addWidget(back)

        def moved(v):
            val.setText(f"{v / 100:.2f}")
            self._load_pending = v / 100
            if not sl.isSliderDown():            # 화살표키·홈 클릭 — 잠깐 뒤에 반영
                self._load_timer.start(250)

        sl.valueChanged.connect(moved)
        sl.sliderReleased.connect(lambda: self.scale_loads(sl.value() / 100))
        return bar

    def load_panel(self):
        """「⚙ 부하」 조절판 — 표 자리에 그린다 (2026-09-01).

        `⚙ AC 조정` 과 같은 격이다. 둘 다 표가 아니라 **조건을 고치는 판**이고,
        표 고르기 목록의 한 자리를 차지한다.
        """
        c = self.c
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        head = QHBoxLayout()
        t = QLabel("부하 일괄 증감")
        t.setStyleSheet(f"color:{c['text']};font-size:15px;font-weight:600;")
        head.addWidget(t)
        n_t = self.load_times()
        sub = QLabel("모든 부하에 같은 수를 곱합니다"
                     + (f" — {n_t}시각 전부에 걸립니다" if n_t > 1 else ""))
        sub.setStyleSheet(f"color:{c['muted']};font-size:12px;")
        head.addWidget(sub)
        head.addStretch(1)
        v.addLayout(head)

        bar = self.load_bar()          # 카드 꼴 (inline 아님)
        if bar is not None:
            v.addWidget(bar)
        note = QLabel("여기서 바꿔도 바로 풀지 않습니다 — 위의 [이 조건으로 계산] 을 "
                      "눌러야 반영됩니다.\n곱하기는 원본 부하를 기준으로 걸립니다.")
        note.setStyleSheet(f"color:{c['muted']};font-size:12px;line-height:165%;")
        v.addWidget(note)
        v.addStretch(1)
        return w

    def scale_loads(self, want):
        """부하를 원본의 want 배로 만든다. 이미 푼 조건에 걸린 배수는 빼고 얹는다."""
        self._load_timer.stop()
        if self.base_case is None:
            return
        done = self.load_factor(self.applied)          # 이미 계산해 놓은 몫
        self.changes = [ch for ch in self.changes if not isinstance(ch, SC.Scale)]
        need = float(want) / done
        if abs(need - 1.0) > 1e-9:
            self.changes.append(SC.Scale(tables=SC.LOAD_TABLES, factor=need,
                                         label=f"부하 전체 ×{want:g}"))
        self.rebuild()

    def grid_tiles(self):
        """계통 데이터의 표 고르개 — 표마다 **숫자 카드 하나**(이름 · 줄 수). 고른 표는 먹색 카드 (2026-11-15).

        여태는 표 판 안의 드롭다운(「AC 선로 77줄 ▾」)이었고 그 위 머리 줄은 「열 선택」 하나만 있는
        빈 줄이었다. 무엇이 몇 개 있는지가 한눈에 보이게 카드 줄로 꺼낸다.
        """
        if self.base_case is None:
            return None
        c = self.c
        picks = []
        for key, label in GRID_TABLES:
            arr = SC._values(self.base_case, key)
            if arr.size and arr.ndim == 2 and not np.all(np.isnan(arr)):
                picks.append((key, label, arr.shape[0]))
        if not picks:
            return None
        on_key = self.grid_key if self.grid_key not in (ADJ.KEY, LOAD_KEY) else None
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        for key, label, n in picks:
            on = key == on_key
            t = QFrame()
            t.setObjectName("gridtile")
            t.setCursor(Qt.PointingHandCursor)
            t.setFixedHeight(72)
            t.setToolTip(f"{label} 표를 엽니다")
            if on:
                t.setStyleSheet(f"#gridtile {{ background:{c['accent']}; border-radius:14px; }}")
            else:
                t.setStyleSheet(f"#gridtile {{ background:{c['surface']}; border:1px solid {c['border']};"
                                f"border-radius:14px; }}"
                                f"#gridtile:hover {{ border:1px solid {c['muted']}; }}")
            tv = QVBoxLayout(t)
            tv.setContentsMargins(16, 10, 14, 10)
            tv.setSpacing(0)
            a = QLabel(label)
            a.setStyleSheet(f"color:{c['on_accent'] if on else c['muted']};font-size:12px;font-weight:700;"
                            "background:transparent;")
            b = QLabel(f"{n:,}")
            b.setStyleSheet(f"color:{c['on_accent'] if on else c['text']};font-size:22px;font-weight:700;"
                            "background:transparent;")
            tv.addWidget(a)
            tv.addWidget(b)
            t.mousePressEvent = (lambda e, k=key: self.set_grid_table(k)
                                 if e.button() == Qt.LeftButton else None)
            h.addWidget(t, 1)
        return w

    def grid_page(self):
        """계통 데이터 탭 — 엑셀 값을 그대로 보여 주고, 여기서 켜고 끈다."""
        c = self.c
        w = QWidget()
        v = QVBoxLayout(w)
        # 여백·간격을 줄인다 — 표에 19px 밖에 안 남던 시절의 값이었다(2026-08-15).
        v.setContentsMargins(12, 6, 12, 8)
        v.setSpacing(6)

        if self.base_case is None:
            note = QLabel("케이스를 열면 여기에 계통 데이터가 나옵니다.")
            note.setStyleSheet(f"color:{c['muted']};font-size:14px;")
            v.addWidget(note)
            v.addStretch(1)
            return w

        # 어느 표를 볼까 — 그 계통에 실제로 있는 것만 (설비가 없으면 칸도 안 만든다)
        picks = []
        for key, label in GRID_TABLES:
            arr = SC._values(self.base_case, key)
            if arr.size and arr.ndim == 2 and not np.all(np.isnan(arr)):
                picks.append((key, label, arr.shape[0]))
        if not picks:
            v.addWidget(QLabel("보여 줄 표가 없습니다."))
            return w
        # ⚠️ 부하가 없는 계통으로 갈아타면 「⚙ 부하」 단추가 안 생긴다 — 그때
        #    `grid_key` 를 그대로 두면 **빈 조절판에 갇힌다**(돌아갈 단추가 없다).
        if self.grid_key == LOAD_KEY and not self.has_load():
            self.grid_key = picks[0][0]
        if self.grid_key not in (ADJ.KEY, LOAD_KEY) \
                and self.grid_key not in [k for k, _, _ in picks]:
            self.grid_key = picks[0][0]

        row = QHBoxLayout()
        row.setSpacing(6)
        # 이름표 — 값(「AC 선로 77줄」)만으로는 뭘 고르는 자리인지 안 보인다
        # (2026-09-01 전수 조사, 위 표 드롭다운과 같은 결함).
        # ⚠️ 이 줄은 창 929px 에서 **여유가 0** 이라(실측 — shot_grid_pick [5])
        #    좁은 화면에서는 이름표를 접는다. 찾기 칸 폭과 같은 갈림(`_narrow`).
        if not self._narrow():
            gl = QLabel("고칠 표")
            gl.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            row.addWidget(gl)
        # 🚨 **단추를 늘어놓으면 이 줄이 창 최소 가로를 정한다** (2026-08-19 부터 알던 것을
        #    2026-09-01 에 드롭다운으로 푼다). 단추는 그 계통에 있는 표만큼 생겨서
        #    AC/DC 는 여덟아홉이다 — 실측 **603px**. 표 탭에서 쓴 수법과 같게 간다.
        #    ⚠️ 「⚙ AC 조정」·「⚙ 부하」는 **여기 안 넣는다** — 표가 아니라 조건을 고치는
        #       판이라 성격이 다르고, 「⚙ 부하 ×1.37」 은 **안 눌러도 값이 보여야** 한다.
        pick = Combo(self.c['muted'])
        pick.setFixedHeight(34)
        # 폭 180 = 위 표 드롭다운과 같게. 190 이던 것을 「N줄」 단위를 넣으며
        # 줄였다 — 929px 창 여유가 0 이라 이 줄은 1px 도 못 늘린다 (2026-09-01).
        pick.setMinimumWidth(180)
        pick.setCursor(Qt.PointingHandCursor)
        pick.setStyleSheet(
            f"QComboBox {{ background:{c['surface']};color:{c['text']};"
            f"border:1px solid {c['border']};border-radius:9px;padding:0 12px;"
            f"font-size:14px;font-weight:600; }}"
            f"QComboBox:hover {{ border-color:{c['accent']}; }}"
            f"QComboBox::drop-down {{ border:none;width:24px; }}")
        # 🚨 「AC 선로 77」 은 **77번 선로**로 읽힌다 — 뒤 숫자는 줄 수이므로
        #    단위를 붙인다 (2026-09-01 전수 조사). ⚠️ 괄호는 안 쓴다 —
        #    「AC 발전기 (65줄)」 은 197px 로 최소폭 190 을 넘겨 929px 창에서 줄이 넘친다.
        pick.setToolTip("어느 표를 고칠지 고릅니다")
        pick.addItems([f"{label} {n:,}줄" for _, label, n in picks])
        # 조정·부하 판을 보고 있으면 고른 표가 없다 — 마지막으로 본 표를 그대로 둔다.
        here = self.grid_key if self.grid_key not in (ADJ.KEY, LOAD_KEY) \
            else getattr(self, "_grid_last_table", picks[0][0])
        keys = [k for k, _, _ in picks]
        pick.setCurrentIndex(keys.index(here) if here in keys else 0)
        # ⚠️ `activated` 다 — `currentIndexChanged` 로 하면 **조정·부하 판에서
        #    드롭다운에 이미 적혀 있는 표를 골라도 신호가 안 나** 못 돌아간다.
        pick.activated.connect(lambda i: self.set_grid_table(keys[i]))
        row.addWidget(pick)
        if getattr(self, "_focus_grid", False):      # 표는 위 숫자 카드 줄에서 고른다 — 같은 고르개를 두 번 안 둔다
            pick.setVisible(False)
            if not self._narrow():
                gl.setVisible(False)
        # 자동 조정은 **표가 아니라 패널**이다 — 넷이 두 표에 갈려 있고 흰 칸이
        # 화면 밖이라 따로 뺐다 (2026-08-27, `adjust_panel.py` 머리말 참조).
        ab = QPushButton(f"\u2699 AC 조정 {ADJ.count(self)}")
        ab.setObjectName("seg_on" if self.grid_key == ADJ.KEY else "seg_off")
        ab.setCursor(Qt.PointingHandCursor)
        ab.clicked.connect(lambda: self.set_grid_table(ADJ.KEY))
        row.addWidget(ab)
        # 부하 일괄 증감도 **표가 아니라 조건**이다 (2026-09-01 사용자 지시).
        #   여태 이 줄 맨 오른쪽에 슬라이더째로 붙어 있었는데, 그 줄은 「보는 것」
        #   (표 고르기·찾기)의 줄이라 성격이 혼자 달랐다. 게다가 맨 오른쪽이라
        #   줄이 넘치면 **통째로 화면 밖으로 밀려** 있는 줄도 몰랐다
        #   (실측 — 창 1194px 에서 524px 넘침 · 1512px 에서 206px).
        #   ⚠️ 단추에 지금 배율을 찍는다 — 안 눌러도 값은 보여야 한다.
        if self.has_load():
            now = self.load_factor()
            lb2 = QPushButton(f"\u2699 부하 \u00d7{now:.2f}")
            lb2.setObjectName("seg_on" if self.grid_key == LOAD_KEY else "seg_off")
            lb2.setCursor(Qt.PointingHandCursor)
            lb2.setToolTip("모든 부하에 같은 수를 곱합니다 — 누르면 조절판이 열립니다")
            lb2.clicked.connect(lambda: self.set_grid_table(LOAD_KEY))
            row.addWidget(lb2)
        # 찾기 칸을 **같은 줄에** 붙인다. 따로 한 줄을 쓰면 바가 셋이 되어
        # (표 고르기·부하·찾기) 표에 줄이 한 줄도 안 남는다(2026-08-13 실측).
        row.addSpacing(10)
        if self.grid_key not in (ADJ.KEY, LOAD_KEY):
            # 「조정」·「부하」는 표가 아니다 — 버스 번호로 좁힐 것도, 셀 줄도 없다
            # (넣어 두면 「0줄」이 찍힌다).
            row.addWidget(self.find_bar(inline=True))
        row.addStretch(1)
        # 안내는 **글줄로 두지 않고** 표 고르기 단추의 설명으로 옮겼다 — 그 자리에
        # 부하 슬라이더를 들여야 한 줄이 준다.
        for i in range(row.count()):
            wd = row.itemAt(i).widget()
            if isinstance(wd, QPushButton):
                wd.setToolTip("켜고 끄기는 바로 계산하지 않습니다 — "
                              "다 바꾼 뒤 위의 [이 조건으로 계산] 을 누르세요.")

        # 🚨 **이 줄은 넘치면 가로로 민다** (2026-08-19).
        #    「표 고르기」 단추는 **그 계통에 있는 표만큼** 생긴다 — AC 전용은 서넛인데
        #    AC/DC 는 여덟아홉이다. 그래서 **이 줄의 길이가 곧 창 최소 가로**가 됐고,
        #    계통을 열기 전에는 알 수 없는 값이 창을 넓히고 있었다.
        #    실측(2026-08-19) — 71버스 AC/DC 를 열면 창 최소 가로가 **1752px** 이라
        #    **맥북 13"(1440px)에도 안 들어갔다.** 화면 크기와 무관한 문제라
        #    「좁은 화면에서만」으로 가르면 안 된다.
        #    ⇒ 줄을 접거나 단추를 감추지 않고 **넘치는 만큼만 밀리게** 한다.
        #      넓은 화면에서는 막대가 아예 안 생겨 지금과 똑같아 보인다.
        cbtn = getattr(self, "_col_btn", None)
        if getattr(self, "_focus_grid", False) and cbtn is not None:
            row.addWidget(cbtn)              # 「열 선택」 — 머리 줄에서 이 조작 줄 오른쪽 끝으로
        holder = QWidget()
        holder.setLayout(row)
        sa = QScrollArea()
        sa.setObjectName("gridbar")          # 시험이 이 줄을 집을 이름
        sa.setWidget(holder)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        def fit_row():
            # 막대가 뜰 때만 그 높이를 얹는다 — 세로는 아껴야 한다(표가 먹을 자리다)
            try:
                hb = sa.horizontalScrollBar()
                sa.setFixedHeight(holder.sizeHint().height()
                                  + (hb.sizeHint().height() if hb.isVisible() else 0))
            except RuntimeError:
                pass

        sa.horizontalScrollBar().rangeChanged.connect(lambda *_: fit_row())
        fit_row()
        v.addWidget(sa)

        v.addWidget(self.grid_table_widget(), 1)
        return w

    # ── 버스 번호로 찾기 ──────────────────────────────────────────────
    # 🚨 큰 계통에서는 표를 다 그리는 것 자체가 비싸다 — 6,495버스 케이스의 AC 선로 표는
    #    9,019줄이고 그리는 데 1.7초다(2026-08-06 실측). 그런데 그때 하려는 일은
    #    "9천 줄 훑어보기" 가 아니라 "그 선로 하나 끊어 보기" 다. 번호로 좁힌다.

    def find_rows(self, key, arr):
        """찾는 번호에 걸리는 줄 번호들. 찾는 게 없으면 None (= 전부)."""
        want = {int(x) for x in re.findall(r"\d+", self.grid_find or "")}
        if not want:
            return None
        sw = SC.SWITCHES.get(key)
        # 그 표에서 **버스 번호가 든 열** — 스위치가 아는 것이 있으면 그것을, 없으면 0열
        idc = [ci for ci in (sw.ident if sw else (0,)) if ci < arr.shape[1]]
        out = []
        for r in range(arr.shape[0]):
            for ci in idc:
                v = arr[r, ci]
                if np.isfinite(v) and int(v) in want:
                    out.append(r)
                    break
        return out

    def find_bar(self, inline=False):
        """버스 번호로 찾기. `inline` 이면 표 고르기 줄에 얹으므로 뒤 여백을 안 둔다."""
        c = self.c
        bar = QFrame()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        lab = QLabel("버스 번호로 찾기")
        lab.setStyleSheet(f"color:{c['muted']};font-size:12px;")
        h.addWidget(lab)

        box = QLineEdit(self.grid_find or "")
        box.setPlaceholderText(("예: 38 39" if self._narrow() else
                                "예: 38 39 40 (비우면 전부)") if inline
                              else "예: 38   ·   38 39 40   (비우면 전부)")
        box.setFixedWidth((130 if self._narrow() else 200) if inline else 260)
        box.returnPressed.connect(lambda: self.set_find(box.text()))
        box.editingFinished.connect(lambda: self.set_find(box.text()))
        h.addWidget(box)

        arr = SC._values(self.base_case, self.grid_key)
        rows = self.find_rows(self.grid_key, arr)
        if rows is not None:
            got = QLabel(f"{arr.shape[0]:,}줄 중 **{len(rows):,}줄**"
                         .replace("**", ""))
            got.setStyleSheet(f"color:{c['accent']};font-size:12px;font-weight:600;")
            h.addWidget(got)
            clr = QPushButton("전부 보기")
            clr.setCursor(Qt.PointingHandCursor)
            clr.clicked.connect(lambda: self.set_find(""))
            h.addWidget(clr)
        else:
            got = QLabel(f"{arr.shape[0]:,}줄")
            got.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            h.addWidget(got)
        if not inline:
            h.addStretch(1)
        return bar

    def set_find(self, text):
        text = (text or "").strip()
        if text == (self.grid_find or ""):
            return
        self.grid_find = text
        self.rebuild()

    def grid_table_widget(self):
        """지금 고른 표 하나를 그린다 (「조정」이면 표가 아니라 패널이다).

        · 켤 수 있는 표면 첫 칸이 스위치
        · **화면 단위로 바꿔서** 보여 준다 (엔진은 W, 화면은 MW — 머리글이 [MW] 니까)
        · ③ 운전 조건 칸만 고칠 수 있고, 나머지는 회색이다
        · 자동 조정 칸도 회색이다 — 값은 보이되 고치는 곳은 [⚙ AC 조정] 패널이다
        """
        if self.grid_key == ADJ.KEY:
            return ADJ.panel(self)
        if self.grid_key == LOAD_KEY:
            return self.load_panel()
        c = self.c
        key = self.grid_key
        sw = SC.SWITCHES.get(key)
        heads = GRID_HEADERS.get(key, [])
        scales = GRID_SCALES.get(key, {})
        # 운전 조건(③)에 더해 **값 칸도 연다** (2026-08-27 사용자 지시 — PDR §4.3 ④ 뒤집기).
        # 어디까지 여는지와 무엇을 받는지는 `cell_rules.py` 가 갖는다.
        editable = GRID_EDITABLE.get(key, set()) | RULES.editable(key)
        eff = self.applied + self.changes      # 화면에 보이는 조건 = 푼 것 + 얹은 것
        arr = SC._values(SC.apply(self.base_case, eff), key)
        if key in GRID_PAD_TO_HEADERS and heads and arr.shape[1] < len(heads):
            # 파일에 없는 열은 빈 칸으로 보여 준다 — 값을 넣는 순간 표가 늘어난다
            arr = np.hstack([arr, np.full((arr.shape[0], len(heads) - arr.shape[1]),
                                          np.nan)])
        ncol = min(arr.shape[1], len(heads)) if heads else arr.shape[1]
        head_of = (lambda i: heads[i] if i < len(heads) else f"{i + 1}열")

        # 🚨 찾기로 좁히면 **보이는 줄 번호와 진짜 줄 번호가 달라진다.**
        #    켜고 끄기·값 고치기는 진짜 번호로 해야 하므로 그 대응을 들고 있는다.
        picked = self.find_rows(key, arr)
        self._grid_rows = list(range(arr.shape[0])) if picked is None else picked
        nrow = len(self._grid_rows)

        touched = {(ch.row, ch.col) for ch in self.changes
                   if isinstance(ch, SC.Cell) and ch.table == key}

        def cell(r, j):
            """진짜 줄 r · 데이터 열 j 의 칸 하나."""
            # 🚨 위상 조정기(Ctrl Mode = 2)에는 `Ctrl Bus` 가 없다 — 그 선로 **자신의**
            #    조류를 보기 때문이다. 빈 칸으로 두면 "여기 뭘 넣어야 하나" 로 읽히므로
            #    잠그고 「—」로 보여 준다(2026-08-13 사용자: "비워 둠 이거를 해결해야").
            #    엔진도 모드 2 에서는 이 칸을 안 읽는다.
            if key == "AC_Line_dat" and j == 14 and ncol > 13 and arr[r, 13] == 2:
                it = QTableWidgetItem("—")
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                it.setForeground(QColor(c["muted"]))
                it.setToolTip("위상 조정기는 그 선로 자신의 조류를 봅니다 — "
                              "볼 버스가 따로 없습니다")
                return it
            val = arr[r, j] * scales.get(j, 1.0)
            txt = "" if np.isnan(val) else (
                f"{val:.0f}" if float(val).is_integer() and abs(val) < 1e9
                else f"{val:,.4f}".rstrip("0").rstrip("."))
            it = QTableWidgetItem(txt)
            if j > 0:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if j in editable:
                tip = _cell_tip(key, j)
                # 🚨 **막지 않고 알려만 준다** — 두 칸을 차례로 고치는 동안엔
                #    중간에 반드시 어긋난다(Qmax 를 낮추려면 한 번은 뒤집힌다).
                #    막으면 고칠 방법이 없어지므로, 글자를 물들이고 까닭을 붙인다.
                note = RULES.warn(arr, key, r, j, val if np.isnan(val) else arr[r, j])
                if note:
                    it.setForeground(QColor(c["warn"]))
                    tip = f"⚠️ {note}\n\n{tip}"
                it.setToolTip(tip)
            else:
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                it.setForeground(QColor(c["muted"]))   # 여기부터는 엑셀에서
                why_id = RULES.ident_why(key, j)
                if why_id:
                    it.setToolTip(why_id)
                elif j in GRID_PANEL_COLS.get(key, set()):
                    it.setToolTip("자동 조정 값입니다 — 위의 [⚙ AC 조정] 에서 고칩니다")
            if (r, j) in touched:
                it.setForeground(QColor(c["warn"]))
            return it

        def new_table(labels):
            t = QTableWidget(nrow, len(labels))
            t.setHorizontalHeaderLabels(labels)
            t.verticalHeader().setVisible(False)
            t.verticalHeader().setDefaultSectionSize(30)
            t.setAlternatingRowColors(True)
            return t

        # ── 왼쪽(고정) / 오른쪽(미는 것) ────────────────────────────────
        # 오른쪽으로 밀면 **어느 줄인지 알 수 없다** — Ctrl 열은 19열 중 14~19열이라
        # 선로 번호가 화면 밖으로 나간다(2026-08-13 사용자: "첫 열을 고정시켜줘").
        # 그래서 상태 + 첫 번호 열을 **따로 만든 표**로 왼쪽에 세운다.
        # 🚨 데이터 열 0 은 어느 표에서도 고칠 수 있는 열이 아니다(GRID_EDITABLE 확인) —
        #    그래서 왼쪽 표에는 itemChanged 를 안 잇는다.
        freeze = ncol >= 2
        self._grid_loading = True              # 그리는 동안의 itemChanged 는 무시

        left = None
        if freeze:
            left = new_table((["상태"] if sw else []) + [head_of(0)])
            left.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            left.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            left.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            if sw:
                # 🚨 순서가 중요하다 — `ResizeToContents` 인 채로 폭을 정하면 **무시된다.**
                #    상태 칸에는 글자가 아니라 단추가 들어서 자동 폭이 22px 로 눌린다
                #    (2026-08-13 렌더로 확인: 머리글이 "태", 단추 글자 안 보임).
                left.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
                left.setColumnWidth(0, 66)
            for at, r in enumerate(self._grid_rows):
                left.setItem(at, 1 if sw else 0, cell(r, 0))

        body = [j for j in range(ncol)] if not freeze else list(range(1, ncol))
        # 고를 수 있는 열을 적어 둔다 — 「열 선택」 판이 이것으로 목록을 만든다.
        # 데이터 열 0 은 왼쪽 고정(또는 상태 옆)이라 끄고 켤 대상이 아니다.
        self._grid_all_cols = [(j, head_of(j)) for j in body]
        # ── 열 선택 (2026-09-02) — 고른 것만 남긴다.
        # 🚨 열을 숨기면 **화면 열 = 데이터 열 + 상수** 가 깨진다(빠진 자리가 생긴다).
        #    그래서 아래로는 상수 `off` 대신 **대응표 `body`** 로 오간다.
        vis = self.grid_visible.get(key)
        if vis is not None:
            kept = [j for j in body if j in vis]
            if kept:                      # 전부 끄면 표가 사라진다 — 그럴 땐 무시
                body = kept
        off = (1 if sw else 0) if not freeze else -1   # 화면 열 = 데이터 열 + off
        # 앞에 몇 칸이 먼저 붙나(상태 단추) — 대응표의 시작점.
        lead = (1 if sw else 0) if not freeze else 0
        self._grid_body = body            # 화면 열 k ↔ 데이터 열 body[k − lead]
        self._grid_lead = lead
        labels = ((["상태"] if sw else []) + [head_of(j) for j in body]) if not freeze \
            else [head_of(j) for j in body]
        tb = new_table(labels)
        # 🚨 열이 많으면 늘려 맞추기(Stretch)가 머리글을 잘라 버린다 — IC 는 20열이라
        #    "Rating Power [MW]" 가 "ng Po" 로 보였다. 그럴 땐 글자에 맞추고 옆으로 넘긴다.
        tb.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch if len(labels) <= 9 else QHeaderView.ResizeToContents)
        for at, r in enumerate(self._grid_rows):     # at = 화면 줄, r = 진짜 줄
            if sw:
                on = SC.is_on(self.base_case, key, r, eff)
                b = QPushButton("켜짐" if on else "꺼짐")
                b.setObjectName("seg_on" if on else "seg_off")
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _, rr=r: self.flip_row(rr))
                (left if freeze else tb).setCellWidget(at, 0, b)
            for k, j in enumerate(body):
                tb.setItem(at, k + lead, cell(r, j))
        self._grid_loading = False
        tb.itemChanged.connect(lambda item: self.grid_edited(key, item, off, scales))

        self._grid_tb = tb          # 스크롤 자리·다음 칸은 **미는 쪽** 기준
        self._grid_off = off        # 시험이 화면 열을 계산할 때 쓴다
        self._grid_frozen = left
        QTimer.singleShot(0, lambda: self._restore_grid_view(tb))
        if not freeze:
            return tb

        # 세로로 함께 움직인다. 줄 높이가 둘 다 30 이고 줄 단위로 구르므로 값이 같다.
        tb.verticalScrollBar().valueChanged.connect(left.verticalScrollBar().setValue)
        left.verticalScrollBar().valueChanged.connect(tb.verticalScrollBar().setValue)

        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        lwrap = QWidget()
        lv = QVBoxLayout(lwrap)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        lv.addWidget(left, 1)
        # 오른쪽에 가로 막대가 뜨면 그만큼 보이는 높이가 줄어든다. 왼쪽에도 같은
        # 높이를 비워 둬야 **마지막 줄이 어긋나지 않는다.**
        pad = QWidget()
        pad.setFixedHeight(0)
        lv.addWidget(pad)
        h.addWidget(lwrap)
        h.addWidget(tb, 1)

        def fit():
            try:
                left.setFixedWidth(left.horizontalHeader().length() + 2)
                hb = tb.horizontalScrollBar()
                pad.setFixedHeight(hb.sizeHint().height() if hb.isVisible() else 0)
            except RuntimeError:
                pass

        tb.horizontalScrollBar().rangeChanged.connect(lambda *_: fit())
        QTimer.singleShot(0, fit)
        return box

    def grid_edited(self, key, item, off, scales):
        """운전 조건 칸을 고쳤다. **계산은 안 한다** — 바꾼 목록에만 얹는다."""
        if getattr(self, "_grid_loading", False):
            return
        # 🚨 **대응표로 되찾는다** (2026-09-02). 열을 숨기면 화면 열과 데이터 열이
        #    상수만큼 어긋나지 않는다 — 빠진 자리를 건너뛰기 때문이다.
        #    (`off` 인자는 시험이 쓰던 것이라 그대로 받되 여기서는 안 쓴다.)
        k = item.column() - getattr(self, "_grid_lead", 0)
        body = getattr(self, "_grid_body", None)
        if body is None or not (0 <= k < len(body)):
            return
        col = body[k]
        # 🚨 **그리는 쪽과 같은 목록을 봐야 한다** (2026-08-27). 여기만 옛 목록을 보면
        #    새로 연 칸이 **조용히 반려**된다 — 화면은 흰 칸인데 쳐도 아무 일이 안 난다.
        if col < 0 or col not in (GRID_EDITABLE.get(key, set()) | RULES.editable(key)):
            return
        txt = item.text().strip().replace(",", "")
        if txt == "":
            # 지워서 비운 것 — 「안 적음」이다. 비워도 되는 칸에서만 받는다.
            if col not in GRID_CLEARABLE.get(key, set()):
                QMessageBox.information(
                    self, "비울 수 없는 칸입니다",
                    "이 칸은 값이 있어야 합니다. 숫자를 넣어 주세요.\n"
                    "(비울 수 있는 것은 조정 칸입니다 — 비우면 「안 걸었다」는 뜻이 됩니다.)")
                self.rebuild()
                return
            shown = value = float("nan")
        else:
            try:
                shown = float(txt)
            except ValueError:
                QMessageBox.information(self, "숫자를 넣어 주세요",
                                        f"'{item.text()}' 는 숫자가 아닙니다.")
                self.rebuild()
                return
            scale = scales.get(col, 1.0)
            value = shown * (1.0 / scale) if scale != 1.0 else shown
        # 🚨 **넣기 전에 따진다** (2026-08-27). 값 칸을 열면서 같이 들어왔다 —
        #    `From` 을 없는 버스로 고치면 계통이 끊어지고, 정격이 음수면 부하율이 뒤집힌다.
        eff0 = SC.apply(self.base_case, self.applied + self.changes)
        bad = RULES.check(eff0, key, col, value)
        if bad:
            QMessageBox.information(
                self, f"{_col_name(key, col)} — 넣을 수 없는 값입니다", bad)
            self.rebuild()
            return
        # 찾기로 좁혀 놓았으면 화면 줄 ≠ 진짜 줄
        seen = getattr(self, "_grid_rows", None)
        row = seen[item.row()] if seen and item.row() < len(seen) else item.row()
        cur = SC._values(SC.apply(self.base_case, self.applied + self.changes), key)
        before = float(cur[row, col]) if col < cur.shape[1] else float("nan")
        if np.isnan(before) and np.isnan(value):
            return                              # 비어 있던 것을 또 비웠다 — 아무 일도 아니다
        if not np.isnan(before) and abs(before - value) <= abs(before) * 1e-12:
            return                              # 안 바뀐 값 — 목록을 더럽히지 않는다
        head = GRID_HEADERS.get(key, [])
        name = head[col] if col < len(head) else f"{col + 1}열"
        self.changes = [ch for ch in self.changes
                        if not (isinstance(ch, SC.Cell) and ch.table == key
                                and ch.row == row and ch.col == col)]
        self.changes.append(SC.Cell(
            table=key, row=row, col=col, value=value,
            label=(f"{SC.describe_row(self.base_case, key, row)} {name} → "
                   + ("(비움)" if np.isnan(shown) else f"{shown:g}")),
            mark=SC.row_mark(self.base_case, key, row)))
        # 같은 줄의 **다음 고칠 수 있는 칸**을 미리 골라 둔다. 조정 열은 여섯 칸을
        # 잇달아 채우는 일이라(Mode·Bus·Target·Min·Max·Steps) 한 칸 칠 때마다
        # 오른쪽으로 다시 찾아가야 했다. 이제 바로 다음 칸에 숫자를 치면 된다.
        nxt = [x for x in sorted(GRID_EDITABLE.get(key, set())) if x > col]
        # 위상 조정기(Ctrl Mode = 2)는 `Ctrl Bus` 를 안 쓴다 — 그 선로 자신의 조류를
        # 보기 때문이다. 방금 2 를 쳤으면 그 칸을 건너뛰고 `Ctrl Target` 으로 간다.
        if key == "AC_Line_dat" and col == 13 and value == 2:
            nxt = [x for x in nxt if x != 14]
        self._grid_focus = (item.row(), (nxt[0] if nxt else col) + off)
        self.rebuild()

    # ── 자동 조정 패널이 값을 쓰는 길 (2026-08-27) ───────────────────
    #   🚨 표를 고치는 것과 **똑같이** `SC.Cell` 하나를 얹는다. 패널은 화면일 뿐이고
    #      데이터가 흐르는 길은 하나여야 [이 조건으로 계산]·시나리오·되돌리기·비교가
    #      손대지 않고 그대로 돈다.

    def adj_set(self, table, row, col, value):
        """조정 칸 하나를 값으로 쓴다 (`value` 가 NaN 이면 「안 적음」)."""
        cur = SC._values(SC.apply(self.base_case, self.applied + self.changes), table)
        before = float(cur[row, col]) if col < cur.shape[1] else float("nan")
        if np.isnan(before) and np.isnan(value):
            return
        if not np.isnan(before) and not np.isnan(value) and before == value:
            return
        head = GRID_HEADERS.get(table, [])
        name = head[col] if col < len(head) else f"{col + 1}열"
        self.changes = [ch for ch in self.changes
                        if not (isinstance(ch, SC.Cell) and ch.table == table
                                and ch.row == row and ch.col == col)]
        self.changes.append(SC.Cell(
            table=table, row=row, col=col, value=value,
            label=(f"{SC.describe_row(self.base_case, table, row)} {name} → "
                   + ("(비움)" if np.isnan(value) else f"{value:g}")),
            mark=SC.row_mark(self.base_case, table, row)))
        self.rebuild()

    def adj_typed(self, table, row, col, text):
        """패널의 숫자 칸에 친 것. 비우면 「안 적음」이다."""
        txt = (text or "").strip().replace(",", "")
        if txt == "":
            self.adj_set(table, row, col, float("nan"))
            return
        try:
            self.adj_set(table, row, col, float(txt))
        except ValueError:
            QMessageBox.information(self, "숫자를 넣어 주세요",
                                    f"'{text}' 는 숫자가 아닙니다.")
            self.rebuild()

    def adj_remove(self, table, row):
        """그 조정을 통째로 지운다 — 여섯 칸을 다 비워야 흔적이 안 남는다."""
        for col in ADJ._cols(table):
            if col is not None:
                self.adj_set(table, row, col, float("nan"))

    def set_grid_table(self, key):
        # 조정·부하 판에서 드롭다운이 무엇을 가리킬지 정하려면 **마지막으로 본 표**를
        # 기억해야 한다 (2026-09-01).
        if key not in (ADJ.KEY, LOAD_KEY):
            self._grid_last_table = key
        self.grid_key = key
        self.rebuild()
        reveal(getattr(self, "_center_w", None))   # 계통 데이터 표 갈아끼우기

    def flip_row(self, row):
        """그 줄을 켜거나 끈다. **계산은 안 한다** — 목록에만 얹는다."""
        key = self.grid_key
        eff = self.applied + self.changes
        now = SC.is_on(self.base_case, key, row, eff)
        # 같은 줄에 대한 옛 기록은 지운다 (껐다 켜면 아무것도 안 바꾼 것이 되게)
        self.changes = [ch for ch in self.changes
                        if not (isinstance(ch, SC.Cell) and ch.table == key
                                and ch.row == row)]
        try:
            ch = SC.toggle(self.base_case, key, row, on=not now)
        except SC.NotSupported as exc:
            QMessageBox.information(self, "못 바꿉니다", str(exc))
            return
        # **이미 푼 조건**과 같아지면 얹을 것이 없다 (껐다 켜면 아무것도 안 바꾼 것)
        if SC.is_on(self.base_case, key, row, self.applied) != (not now):
            self.changes.append(ch)
        self.rebuild()

    def undo_changes(self):
        """아직 안 푼 것만 물린다. 이미 계산해서 보고 있는 조건은 그대로 둔다."""
        self.changes = []
        self.rebuild()
        reveal(getattr(self, "_center_w", None))   # 앱 2.3 — 되돌리기

    def run_changes(self):
        """[이 조건으로 계산] — 여기서만 푼다."""
        if not self.changes or self.base_case is None:
            return
        self._pending = self.applied + self.changes   # 풀고 나서 시나리오로 담으려고
        # 이름은 **이번에 새로 얹은 것**으로 짓는다. 전체 목록으로 지으면 맨 앞의
        # 오래된 조건("부하 전체 ×1.3")이 계속 이름을 차지한다.
        self._pending_new = list(self.changes)
        self._start_solve(getattr(self, "_last_path", self.base_case.case_name),
                          case=SC.apply(self.base_case, self._pending))

    def overlay_pairs(self):
        """겹쳐 그릴 (이름, 결과) 목록. 체크한 것 중 **풀린 것만**."""
        out = []
        for i, s in enumerate(self.book.items):
            if self.overlay and i not in self.overlay:
                continue
            if s.solved:
                out.append((s.name, s.solution))
        return out

    def toggle_overlay(self, i, on):
        if not self.overlay:                       # 비어 있으면 '전부' 라는 뜻
            self.overlay = set(range(len(self.book.items)))
        self.overlay = (self.overlay | {i}) if on else (self.overlay - {i})
        self.rebuild()

    def compare_scenarios_area(self, picked):
        """시나리오끼리 비교 — 목록에서 체크한 것을 한 그래프에 겹쳐 그린다."""
        c = self.c
        tabs = QTabWidget()
        pairs = self.overlay_pairs()
        if len(self.book.items) < 2:
            page = QWidget(); pv = QVBoxLayout(page)
            lb = QLabel("아직 담아 둔 시나리오가 없습니다.\n"
                        "계통 데이터 탭에서 조건을 바꾸고 [이 조건으로 계산] 을 누르면 쌓입니다.")
            lb.setAlignment(Qt.AlignCenter)
            lb.setStyleSheet(f"color:{c['muted']};font-size:15px;")
            pv.addWidget(lb)
            tabs.addTab(page, "결과")
            return tabs
        for name in picked:
            page = QWidget()
            pv = QVBoxLayout(page)
            pv.setContentsMargins(10, 10, 10, 10)
            pv.setSpacing(9)
            pv.addWidget(charts.compare_scenarios(c, pairs, name, self.t), 2)
            tb = self.scenario_table(name, pairs)
            if tb is not None:
                pv.addWidget(tb, 1)
            tabs.addTab(page, name)
        return tabs

    def scenario_table(self, item, pairs):
        """겹쳐 그린 시나리오의 요약 표 — 최저·최고·원본 대비."""
        s = CI.spec(item)
        if s is None or s[5] == "system" or not pairs:
            return None
        col = s[2]
        # 전압 크기만 AC·DC 를 함께 본다 — 나머지는 그 항목이 사는 표 하나만
        kinds = ("AC", "DC") if item == "전압 크기" else (s[1],)
        rows = []
        base_lo = None
        for name, sol in pairs:
            vals = []
            for kind in kinds:
                arr = sol.at(kind, self.t) if getattr(sol, kind, None) is not None \
                    and getattr(sol, kind).ndim == 3 else getattr(sol, kind, None)
                if arr is None or not getattr(arr, "size", 0):
                    continue
                cols = sol.cols(kind)
                if col in cols:
                    vals.append(np.asarray(arr[:, cols.index(col)], dtype=float))
            if not vals:
                continue
            y = np.concatenate(vals)
            lo, hi = float(np.nanmin(y)), float(np.nanmax(y))
            if base_lo is None:
                base_lo = lo
            rows.append((name, lo, hi, lo - base_lo))
        if not rows:
            return None
        heads = ["시나리오", "최저", "최고", "첫 줄 대비"]
        tb = QTableWidget(len(rows), len(heads))
        tb.setHorizontalHeaderLabels(heads)
        tb.verticalHeader().setVisible(False)
        tb.verticalHeader().setDefaultSectionSize(28)
        tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tb.setAlternatingRowColors(True)
        for r, (name, lo, hi, d) in enumerate(rows):
            for cc, txt in enumerate([name, f"{lo:.4f}", f"{hi:.4f}",
                                      "—" if r == 0 else f"{d:+.4f}"]):
                it = QTableWidgetItem(txt)
                if cc:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if cc == 3 and r and d < -1e-6:
                    it.setForeground(QColor(self.c["warn"]))
                tb.setItem(r, cc, it)
        return tb

    def scenario_bar(self):
        """담아 둔 시나리오 목록. 원본뿐이면 안 만든다(줄 하나짜리 목록은 군더더기다).

        결과를 이미 들고 있으므로 **다시 계산하지 않고** 오갈 수 있다.
        칸이 줄마다 어긋나지 않게 **격자**로 놓는다.
        """
        if len(self.book.items) < 2:
            return None
        c = self.c
        card = QFrame()
        card.setObjectName("card")
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 9, 12, 10)
        v.setSpacing(6)

        head = QHBoxLayout()
        cap = QLabel(f"시나리오 {len(self.book.items)}")
        cap.setStyleSheet(f"color:{c['muted']};font-size:12px;font-weight:600;")
        head.addWidget(cap)
        head.addStretch(1)
        tip = QLabel("이름을 두 번 누르면 고칠 수 있습니다")
        tip.setStyleSheet(f"color:{c['muted']};font-size:11px;")
        head.addWidget(tip)
        v.addLayout(head)

        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(3)
        for j, (name, w) in enumerate(
                [("겹쳐 그리기", 74), ("이름", 0), ("", 0), ("", 0),
                 ("전압 최저", 82), ("원본 대비", 74), ("", 52)]):
            if name:
                q = QLabel(name)
                q.setStyleSheet(f"color:{c['muted']};font-size:11px;")
                g.addWidget(q, 0, j)
            if w:
                g.setColumnMinimumWidth(j, w)
        g.setColumnStretch(1, 1)

        base = self.book.base()
        for i, s in enumerate(self.book.items, start=1):
            self._scenario_row(g, i, s, base)

        # 🚨 **몇 줄까지만 보이고 넘으면 목록 안에서 스크롤한다** (2026-08-15 사용자 확정).
        #    그전에는 시나리오 한 줄에 **25px 씩 카드가 계속 자랐다** — 7개면 235px 이고,
        #    그만큼 그래프와 표가 줄었다. 6개부터는 **둘 다 바닥에 닿아** 표가 통째로 잘렸다
        #    (실측: 카드 0→110→160→235 / 그래프 523→408→353→320 / 표 275→215→186→170).
        #    ⇒ 상한을 씌워 **쌓일수록 나빠지는 것 자체를 없앤다.**
        #    시나리오는 보통 최근 것만 보므로 네 줄이면 실제로 쓸 만하다.
        v.addLayout(g)
        v.addStretch(1)
        return card

    def _scenario_row(self, g, i, s, base):
        c = self.c
        here = list(s.changes) == list(self.applied)     # 지금 화면이 이것인가

        # 🚨 이 칸에 **표시 둘이 붙어 있었다** (2026-09-08 점검 i48 — 사용자:
        #    *"겹쳐에서 선택하는것도 직관적이지가 않아"*).
        #      ●/○  = 지금 보는 것인가 (읽기만 하는 표시)
        #      체크  = 비교에서 겹쳐 그릴까 (누르는 것)
        #    나란히 있으니 ● 도 누르는 것으로 읽혔다. **●/○ 는 없앤다** —
        #    「지금 보는 것」은 이름 옆 파란 딱지가 이미 말한다(아래 `tag`).
        left0 = QHBoxLayout()
        left0.setSpacing(4)
        if s.solved:
            cb = QCheckBox()
            cb.setChecked((i - 1) in self.overlay if self.overlay else True)
            cb.setToolTip("비교 → 시나리오끼리 에서 이 시나리오를 함께 그립니다")
            cb.toggled.connect(lambda on, k=i - 1: self.toggle_overlay(k, on))
            left0.addWidget(cb)
        else:
            # 안 풀린 시나리오는 그릴 것이 없다 — 빈 칸이면 왜 없는지 안 보인다.
            no = QLabel("—")
            no.setToolTip("답을 못 찾은 조건이라 그릴 것이 없습니다")
            no.setStyleSheet(f"color:{c['border']};font-size:12px;")
            left0.addWidget(no)
        left0.addStretch(1)
        g.addLayout(left0, i, 0)

        left = QHBoxLayout()
        left.setSpacing(7)
        name = _ClickLabel(s.name)
        name.setStyleSheet(
            f"color:{c['accent'] if here else c['text']};font-size:13px;"
            f"font-weight:{'700' if here else '500'};")
        name.setToolTip(SC.describe(s.changes))
        name.double_clicked.connect(lambda _s=s: self.rename_scenario(_s))
        left.addWidget(name)
        if here:
            tag = QLabel("지금 보는 것")
            tag.setStyleSheet(
                f"color:{c['accent']};background:{c['accent_soft']};font-size:11px;"
                f"border-radius:8px;padding:1px 8px;")
            left.addWidget(tag)
        left.addStretch(1)
        g.addLayout(left, i, 1)

        def cell(col, text, color=None, bold=False, right=False, tip=""):
            q = QLabel(text)
            q.setStyleSheet(f"color:{color or c['muted']};font-size:12px;"
                            f"font-weight:{'600' if bold else '400'};")
            if right:
                q.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if tip:
                q.setToolTip(tip)
            g.addWidget(q, i, col)

        # 🚨 「바꾼 것 N건」과 「반복 N회」는 뺐다 (2026-08-15) — 앞엣것은 이름이 이미
        #    말해 주고(`AC 선로 2-4 끔`), 뒤엣것은 시나리오를 고르는 데 안 쓰인다
        #    (지금 보는 것의 반복 횟수는 아래 상태줄에 있다). 대신 **못 푼 것**은
        #    반드시 보여야 하므로 그때만 자리를 쓴다.
        if s.error:
            cell(2, s.summary, c["warn"], bold=True)
        vmin = s.vmin()
        cell(4, "—" if np.isnan(vmin) else f"{vmin:.4f} pu", c["text"], right=True)
        d = s.against(base) if (base is not None and not s.base) else float("nan")
        cell(5, "—" if np.isnan(d) else f"{d:+.4f}",
             c["warn"] if (not np.isnan(d) and d < -1e-6) else c["muted"],
             right=True, tip="원본 대비 전압 최저 변화")

        # 🚨 [결과 보기] 단추를 뺐다 — **이름을 누르면 간다.** 단추(34px)가 줄 높이를
        #    42px 로 만들고 있었고, 목록이 그만큼 자리를 먹었다(4줄 248px).
        if not here:
            name.setCursor(Qt.PointingHandCursor)
            name.clicked.connect(lambda _s=s: self.show_scenario(_s))
            name.setToolTip(SC.describe(s.changes) +
                            ("\n\n눌러서 이 결과를 봅니다" if s.solved
                             else "\n\n눌러서 이 조건만 불러옵니다"))
        act = QHBoxLayout()
        act.setSpacing(6)
        act.addStretch(1)
        if not s.base:
            # 🚨 `✕` 만 있고 무엇을 지우는지는 **풍선말에만** 있었다 (2026-09-08 i50
            #    — 사용자: *"시나리오 삭제 버튼도 명시가 안되어 있고"*). 글로 적는다.
            #    줄 높이를 안 키우게 22px 로 눌러 둔다(옛 `✕` 와 같은 키).
            x = QPushButton("지우기")
            x.setFixedHeight(22)
            x.setCursor(Qt.PointingHandCursor)
            x.setToolTip("이 시나리오를 목록에서 지웁니다 (계통은 안 건드립니다)")
            x.setStyleSheet(
                f"border:none;background:transparent;color:{c['muted']};"
                f"font-size:12px;padding:0 4px;")
            x.clicked.connect(lambda _, _s=s: self.drop_scenario(_s))
            act.addWidget(x)
        g.addLayout(act, i, 6)

    def show_scenario(self, s):
        """그 시나리오로 화면을 옮긴다. 결과를 들고 있으면 **다시 안 푼다.**"""
        self.applied = list(s.changes)
        self.changes = []
        if s.solved:
            self.sol = s.solution
            self.t = min(self.t, max(int(s.solution.n_time) - 1, 0))
        else:
            # 안 풀린 시나리오 — 조건만 깔아 준다. 화면 결과는 건드리지 않는다.
            QMessageBox.information(
                self, "안 풀린 시나리오",
                f"「{s.name}」 은 답을 못 찾은 조건입니다.\n조건만 깔아 두었으니 "
                f"여기서 더 바꿔 다시 계산해 보세요.\n\n화면의 결과는 그대로 둡니다.")
        self.rebuild()
        reveal(getattr(self, "_center_w", None))   # 시나리오 보기

    def rename_scenario(self, s):
        name, ok = QInputDialog.getText(self, "이름 바꾸기", "시나리오 이름", text=s.name)
        if ok and name.strip():
            self.book.rename(s, name.strip())
            self.rebuild()

    def drop_scenario(self, s):
        if list(s.changes) == list(self.applied):
            back = self.book.base()
            if back is not None and back.solved:
                self.show_scenario(back)          # 보고 있던 것을 지우면 원본으로
        self.book.remove(s)
        self.rebuild()
        reveal(getattr(self, "_center_w", None))   # 시나리오 지우기

    def check_page(self, parts="all"):
        """점검 표 묶음. `parts="notes"` 면 **알림 카드만**(탭 자동 조정 · 무효 한계 안내 · 정격 없는 선로) —
        새 점검 화면(`overview.check_board`)이 위쪽을 카드 · 막대 · 그래프로 따로 그리고 이것을 아래에 붙인다.
        알릴 것이 없으면 None."""
        c = self.c
        notes_only = parts == "notes"
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(*((0, 0, 0, 0) if notes_only else (14, 12, 14, 12)))
        outer.setSpacing(11)

        n = violation_count(self.viol())
        head = QFrame()
        head.setObjectName("card")
        hv = QHBoxLayout(head)
        hv.setContentsMargins(14, 10, 14, 10)
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color:{c['warn'] if n else c['ok']};font-size:15px;")
        hv.addWidget(dot)
        n_r = reached_count(self.viol())
        msg = QLabel((f"위반 {n}건" if n else "위반 없음")
                     + (f" · 한계 도달 {n_r}건" if n_r else ""))
        # 앱 2.3 — 탭에 들어오면 건수가 0 에서 올라간다(`rise_in` → `count_up`)
        msg._count_fmt = lambda t, a=n, b=n_r: (
            (f"위반 {round(a * t)}건" if a else "위반 없음")
            + (f" · 한계 도달 {round(b * t)}건" if b else ""))
        msg.setStyleSheet(
            f"color:{c['warn'] if n else c['ok']};font-size:15px;font-weight:600;")
        hv.addWidget(msg)
        hv.addStretch()
        sub = QLabel("전압 한계 · 선로 용량 · 변환기 한계 · 발전기 한계를 계산 결과에서 걸러낸 것입니다")
        sub.setStyleSheet(f"color:{c['muted']};font-size:12px;")
        hv.addWidget(sub)
        if not notes_only:
            outer.addWidget(head)

        # ── 탭 자동 조정 결과 (2026-08-13, §7 5단계 A1) ──────────────────
        # 탭은 **계산이 정한 값**이라 사용자가 볼 데가 없으면 결과를 못 읽는다.
        # 특히 한계에 걸려 목표를 못 맞춘 경우를 모르면 "목표대로 됐겠지" 하고 넘어간다.
        # 🚨 **지금 보고 있는 시각의** 탭을 쓴다 (2026-09-08). 엔진은 시각마다 따로
        #    조정하는데, 예전에는 첫 시각 표 하나(`tap_ctrl`)를 하루 내내 보여줬다.
        #    화면이 "0.96875 를 썼다"고 말하는 동안 5시 계산은 다른 값으로 풀렸다.
        #    `tap_at()` 은 옛 `.ctf`(시각별 표를 안 주는 것)면 첫 시각으로 되돌아간다.
        tap = self.sol.tap_at(self.t) if self.sol is not None else None
        if tap is not None and len(tap):
            tap_a = np.asarray(tap, dtype=float)
            miss = int((tap_a[:, 4] == 0).sum())
            # ── 계단 (2026-08-14, §7 5단계 ③) ────────────────────────────
            # 🚨 계단이면 **목표를 정확히 못 맞추는 것이 정상**이다(설 자리가
            #    정해져 있으니까). 그래서 「목표 맞춤」이라 쓰면 거짓말이 되고,
            #    반대로 경고를 달면 멀쩡한 것을 결함처럼 보이게 한다.
            #    ⇒ 11열을 보고 **계단은 계단이라고** 쓴다.
            #    2 = 계단 자리로 옮긴 뒤 다시 푸는 데 실패해 연속값이 그대로다.
            #        이것만은 경고다 — 사용자는 계단인 줄 알고 있을 테니까.
            nofit = int((tap_a[:, 10] == 2).sum()) if tap_a.shape[1] > 10 else 0
            warn_on = bool(miss or nofit)
            # 한계를 안 적어 앱이 0.9~1.1 로 잡은 것 (2026-08-13 사용자 확정).
            # **내가 정하지 않은 값이 답을 가두고 있으므로** 반드시 밝힌다.
            auto = int((tap_a[:, 7] == 1).sum()) if tap_a.shape[1] > 7 else 0
            card = QFrame()
            card.setObjectName("card")
            if warn_on:
                wc2 = QColor(c["warn"])
                card.setStyleSheet(
                    f"#card{{background:rgba({wc2.red()},{wc2.green()},{wc2.blue()},0.12);"
                    f"border:1px solid {c['warn']};}}")
            cv = QVBoxLayout(card)
            cv.setContentsMargins(14, 10, 14, 12)
            cv.setSpacing(8)

            hh = QHBoxLayout()
            ic = QLabel("⚠" if warn_on else "⚙")
            ic.setStyleSheet(
                f"color:{c['warn'] if warn_on else c['muted']};font-size:15px;")
            hh.addWidget(ic)
            kind_col = tap_a[:, 8] if tap_a.shape[1] > 8 else np.ones(len(tap_a))
            names = [n for k, n in ((1, "탭"), (2, "위상"), (3, "SVC"))
                     if (kind_col == k).any()]
            what = "·".join(names) + " 자동 조정"
            # 시각이 여럿이면 **어느 시각의 조정인지** 밝힌다 (2026-09-08).
            # 탭은 시각마다 다시 정해지므로, 시간을 바꾸면 이 표의 값도 바뀐다.
            n_t = int(getattr(self.sol, "n_time", 1) or 1)
            when = f" ({min(self.t, n_t - 1) + 1} H)" if n_t > 1 else ""
            ttl = QLabel(f"{what} {len(tap)}대{when}"
                         + (f" — {miss}대가 목표를 못 맞췄습니다" if miss else "")
                         + (f" — {nofit}대는 계단으로 못 내렸습니다" if nofit else ""))
            if n_t > 1:
                ttl.setToolTip(f"이 계통은 {n_t}시각짜리입니다. 탭은 시각마다 "
                               f"다시 정해지므로 위 시간을 바꾸면 이 표도 바뀝니다.")
            ttl.setStyleSheet(
                f"color:{c['warn'] if warn_on else c['text']};"
                f"font-size:14px;font-weight:600;")
            hh.addWidget(ttl)
            hh.addStretch()
            note = QLabel("굵은 값은 계산이 정한 것입니다"
                          + (" · 한계에 걸리면 목표를 포기합니다" if miss else "")
                          + (" · 계단은 정해진 자리에만 서므로 목표에 근접합니다"
                             if (np.asarray(tap, dtype=float).shape[1] > 9
                                 and (np.asarray(tap, dtype=float)[:, 9] > 0).any())
                             else ""))
            note.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            hh.addWidget(note)
            cv.addLayout(hh)

            heads = ["방식", "선로", "맞추는 곳", "목표", "정해진 값",
                     "움직일 수 있는 범위", "결과"]
            tt2 = QTableWidget(len(tap), len(heads))
            tt2.setHorizontalHeaderLabels(heads)
            tt2.verticalHeader().setVisible(False)
            tt2.verticalHeader().setDefaultSectionSize(28)
            tt2.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            tt2.setAlternatingRowColors(True)
            tt2.setFixedHeight(34 + 28 * len(tap))
            for r, row in enumerate(tap_a):
                live = row[4] != 0
                lo, hi = (row[5], row[6]) if len(row) > 6 else (np.nan, np.nan)
                mine = len(row) > 7 and row[7] == 1
                kind = int(row[8]) if len(row) > 8 else 1
                unit = {1: "", 2: "°", 3: " Mvar"}[kind]
                # 계단 (2026-08-14) — 10열 = 한 단 크기 · 11열 = 내렸나
                sz = float(row[9]) if len(row) > 9 else 0.0
                state = int(row[10]) if len(row) > 10 else 0
                lim = "—" if np.isnan(lo) else (
                    f"{lo:g} ~ {hi:g}{unit}" + ("  (자동)" if mine else ""))
                vals = [{1: "탭", 2: "위상", 3: "SVC"}[kind],
                        "—" if kind == 3 else f"{int(row[0])}",
                        "이 선로" if kind == 2 else f"버스 {int(row[1])}",
                        f"{row[2]:,.3f} MW" if kind == 2 else f"{row[2]:.4f} pu",
                        f"{row[3]:.4f}{unit}",
                        lim,
                        # 🚨 계단은 「목표 맞춤」이라 쓰면 거짓말이다 — 설 자리가
                        #    정해져 있어 목표에 **가까운 자리**에 설 뿐이다.
                        ("한계에 걸림 — 목표 포기" if not live
                         else "계단으로 못 내림 — 연속값 그대로" if state == 2
                         else f"계단 자리 (한 단 {sz:g}{unit})" if state == 1
                         else "목표 맞춤")]
                for cc, txt in enumerate(vals):
                    it = QTableWidgetItem(txt)
                    if cc > 0:
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if not live or state == 2:
                        it.setForeground(QColor(c["warn"]))
                    elif cc == 4 and mine:
                        it.setForeground(QColor(c["muted"]))
                    tt2.setItem(r, cc, it)
            cv.addWidget(tt2)
            if auto:
                # 사용자가 안 적어서 앱이 정한 값이다 — 어디를 고치면 되는지까지 적는다.
                # 탭이면 0.9~1.1, 위상이면 ±30° — 어느 쪽인지 갈라 적는다
                kinds = []
                if ((tap_a[:, 7] == 1) & (tap_a[:, 8] == 1)).any():
                    kinds.append("탭은 0.9 ~ 1.1")
                if ((tap_a[:, 7] == 1) & (tap_a[:, 8] == 2)).any():
                    kinds.append("위상은 -30 ~ 30°")
                if ((tap_a[:, 7] == 1) & (tap_a[:, 8] == 3)).any():
                    kinds.append("SVC 는 -50 ~ 50 Mvar")
                am = QLabel(
                    f"ⓘ {auto}대는 움직일 범위(Ctrl Min·Ctrl Max)를 적지 않아 "
                    f"{' · '.join(kinds)} 로 잡았습니다 — "
                    f"「계통 데이터」 에서 바꿀 수 있습니다.")
                am.setWordWrap(True)
                am.setStyleSheet(f"color:{c['muted']};font-size:12px;")
                cv.addWidget(am)
            outer.addWidget(card)

        # 무효출력 한계를 걸면 수렴하지 못하는 계통 — 아래 표는 한계를 적용하지 않은
        # 값이므로 눈에 띄게 밝힌다 (2026-07-31).
        qmsg = getattr(self.sol, "qlim_message", "") if self.sol else ""
        if qmsg:
            warn = QFrame()
            warn.setObjectName("card")
            # 경고색을 옅게 깐 배경. Qt 스타일시트는 '#RRGGBBAA' 를 못 읽으므로
            # rgba() 로 준다(그냥 색을 깔면 글자가 배경에 묻힌다).
            wc = QColor(c["warn"])
            warn.setStyleSheet(
                f"#card{{background:rgba({wc.red()},{wc.green()},{wc.blue()},0.12);"
                f"border:1px solid {c['warn']};}}")
            wv = QHBoxLayout(warn)
            wv.setContentsMargins(14, 10, 14, 10)
            wicon = QLabel("⚠")
            wicon.setStyleSheet(f"color:{c['warn']};font-size:16px;font-weight:600;")
            wv.addWidget(wicon)
            # 엔진이 보낸 문구를 **그대로** 쓴다. 앞에 "한계 적용 시 수렴 실패 —" 를
            # 붙이던 것은 문구 안에 이미 그 말이 들어 있어 겹쳤다 (2026-08-12).
            wtxt = QLabel(qmsg)
            wtxt.setWordWrap(True)
            wtxt.setStyleSheet(f"color:{c['warn']};font-size:13px;font-weight:600;")
            wv.addWidget(wtxt, 1)
            outer.addWidget(warn)

        # ── 한계로 묶인 발전기가 있으면 알린다 (2026-08-12, §7.6 G8)
        #    ⚠️ 이건 **경고가 아니라 참고**다. 한계로 묶는 것 자체는 정상 동작이라
        #    빨간 경고로 띄우면 정상 계통마다 떠서 경고가 무뎌진다.
        #    다만 **흡수 쪽(Qmin)에 걸리면 전압이 올라가는데** 처음 보면 놀랄 일이라 밝힌다.
        note = self._qlim_note()
        if note:
            info = QFrame()
            info.setObjectName("card")
            iv = QHBoxLayout(info)
            iv.setContentsMargins(14, 9, 14, 9)
            icon = QLabel("ⓘ")
            icon.setStyleSheet(f"color:{c['muted']};font-size:15px;font-weight:600;")
            iv.addWidget(icon)
            itxt = QLabel(note)
            itxt.setWordWrap(True)
            itxt.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            iv.addWidget(itxt, 1)
            outer.addWidget(info)

        # ── 정격이 안 적혀 부하율을 못 재는 선로가 있으면 밝힌다 (2026-08-18)
        #    ⚠️ **조용히 빼면 그것대로 못 믿는다.** 과부하 판정에서 뺀 것은 맞지만,
        #       뺐다는 사실을 화면이 말해야 사용자가 "왜 0건이지?" 를 안 겪는다.
        #       (반대 방향의 옛 결함 = 이 선로들을 전부 과부하로 세어 IEEE 118버스에서
        #        거짓 경보 186건을 띄우던 것.)
        n_unrated = unrated_lines(self.sol, self.t) if self.sol is not None else 0
        if n_unrated:
            info2 = QFrame()
            info2.setObjectName("card")
            iv2 = QHBoxLayout(info2)
            iv2.setContentsMargins(14, 9, 14, 9)
            ic2 = QLabel("ⓘ")
            ic2.setStyleSheet(f"color:{c['muted']};font-size:15px;font-weight:600;")
            iv2.addWidget(ic2)
            it2 = QLabel(
                f"선로 {n_unrated}개는 정격(용량)이 안 적혀 있어 부하율을 재지 못했습니다 — "
                f"과부하 판정에서 뺐습니다.")
            it2.setWordWrap(True)
            it2.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            iv2.addWidget(it2, 1)
            outer.addWidget(info2)

        if notes_only:
            return w if outer.count() else None
        for title, (cols, rows) in self.viol().items():
            box = QFrame()
            box.setObjectName("card")
            bv = QVBoxLayout(box)
            bv.setContentsMargins(14, 11, 14, 13)
            bv.setSpacing(8)
            th = QHBoxLayout()
            t = QLabel(title)
            t.setStyleSheet(f"color:{c['text']};font-size:14px;font-weight:600;")
            th.addWidget(t)
            cnt = QLabel(f"{len(rows)}건")
            cnt.setStyleSheet(
                f"color:{c['warn'] if rows else c['muted']};font-size:12px;")
            th.addWidget(cnt)
            th.addStretch()
            bv.addLayout(th)

            if rows:
                tb = QTableWidget(len(rows), len(cols))
                tb.setHorizontalHeaderLabels(cols)
                tb.verticalHeader().setVisible(False)
                tb.verticalHeader().setDefaultSectionSize(30)
                tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                # 🚨 **상한만 걸면 표가 눌린다** (2026-08-18 실측).
                #    이 화면은 카드를 세로로 쌓고 끝에 `outer.addStretch()` 를 두는데,
                #    `addWidget` 으로 붙은 것은 **늘림 몫이 0**이라 남는 자리를 전부 그
                #    stretch 가 가져간다. 그래서 `setMaximumHeight` 는 아무 일도 안 하고
                #    표는 늘 제 기본 크기(88px)로 눌린 채 그려졌다 — **19건짜리 표가 한 줄**.
                #    26건을 잡아 놓고 화면이 3줄만 보여 주니 기능이 없는 것과 같았다.
                #    ⇒ **높이를 못박는다**(`setFixedHeight` 는 최소·최대를 함께 건다).
                #    다 보여 주되 한 표가 화면을 통째로 먹지 않게 **10줄에서 끊는다** —
                #    그보다 많으면 표 안에서 스크롤하고, 전체 건수는 제목 옆 "N건" 이 말한다.
                #    (건수에 상한이 없다 — `checks.real_violations` 는 걸린 것을 다 담는다.)
                tb.setFixedHeight(self.CHECK_ROW_H * min(len(rows), self.CHECK_MAX_ROWS)
                                  + self.CHECK_CHROME)
                for r, row in enumerate(rows):
                    for cc, val in enumerate(row):
                        it = QTableWidgetItem(val)
                        if cc > 1:
                            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        if cc == len(row) - 1:
                            it.setForeground(QColor(self.c["warn"]))   # `Qt.red` 는 어두운 화면에서 묻혔다 (2026-11-15)
                        tb.setItem(r, cc, it)
                bv.addWidget(tb)
            else:
                ok = QLabel("없음")
                ok.setStyleSheet(f"color:{c['muted']};font-size:12px;")
                bv.addWidget(ok)
            outer.addWidget(box)

        outer.addStretch()
        return w

    def _qlim_note(self):
        """무효출력 한계 때문에 알릴 것이 있으면 그 문구, 없으면 빈 글자.

        **아래 "발전기 한계" 표가 세는 것과 같은 것을 센다** — 표는 `satQ ~= 0` 인 줄만
        보여주므로 여기서도 그 열을 본다. 두 해법이 같은 표를 내므로 안내도 같아진다.
        ⚠️ 예전에는 엔진이 따로 보내 준 값을 썼는데, 그 값을 Gauss-Seidel 만 보내는 바람에
           **안내가 한쪽에만 뜨고 표와 숫자가 어긋났다**(2026-08-12 사용자 지적).

        내용은 표가 말하지 못하는 것만 담는다 — **흡수 쪽(Qmin)에 걸리면 전압이 올라간다**.
        발전기가 빨아들이던 무효전력을 더 못 빨아들이기 때문인데, 보통은 한계를 걸면
        전압이 내려간다고 생각하므로 처음 보면 놀랄 만한 일이다.
        """
        sol = self.sol
        tbl = getattr(sol, "gen_limit", None) if sol is not None else None
        if tbl is None or len(tbl) == 0:
            return ""
        try:
            sat_q = [int(r[9]) for r in tbl]
        except (IndexError, TypeError, ValueError):
            return ""
        dn = sum(1 for s in sat_q if s < 0)
        if not any(sat_q):
            return ""

        s = ""
        if dn:
            s = (f"무효전력을 빨아들이던 발전기 {dn}대가 흡수 한계에 걸렸습니다. "
                 "더 못 빨아들이므로 그 부근 전압이 오히려 올라갑니다.")
        if getattr(sol, "method", "nr") == "gs":
            s += (" " if s else "") + (
                "한계를 건 계통은 답이 여럿일 수 있어 Newton 방식과 다른 답이 나올 수 있습니다 "
                "— 결과가 이상해 보이면 Newton 으로도 풀어 견줘 보십시오.")
        return s.strip()

    # ── 해법 고르기 (2026-08-12, §7.6 G8) ──
    def _solver_picker(self, heading=True):
        """Newton / Gauss-Seidel 을 고르는 자리. 못 쓰는 계통이면 흐리게 하고 까닭을 보여준다.

        왜 못 쓰는지 판정은 `app_engine.gs_refusal(case)`(여기서는 `ENGINE`) 이 한다 — 엔진도 같은 것을 검사해
        오류를 내지만(`runpfGS_app.m`), 여기서 **미리** 막아 사용자가 눌러 보고 실패를 겪지 않게 한다.
        """
        c = self.c
        box = QVBoxLayout()
        box.setSpacing(2)
        if heading:
            lab = QLabel("해법")
            lab.setStyleSheet(f"color:{c['muted']};font-size:11px;")
            box.addWidget(lab)

        pick = Combo(self.c['muted'])
        pick.addItem("Newton-Raphson", "nr")
        pick.addItem("Gauss-Seidel", "gs")
        pick.setCurrentIndex(1 if getattr(self, "solver", "nr") == "gs" else 0)

        why = None
        case = getattr(self, "_case_for_solver", None)
        if case is not None:
            try:
                why = ENGINE.gs_refusal(case)
            except Exception:
                why = None
        if why:
            # 고를 수 없게 흐리게 하고, 마우스를 올리면 까닭이 뜨게 한다
            model = pick.model()
            item = model.item(1)
            if item is not None:
                item.setEnabled(False)
            pick.setItemData(1, why, Qt.ToolTipRole)
            pick.setToolTip(why)
            if pick.currentIndex() == 1:
                pick.setCurrentIndex(0)

        pick.currentIndexChanged.connect(self._solver_changed)
        self._solver_pick = pick
        box.addWidget(pick)
        return box

    def _solver_changed(self, _idx):
        """해법을 바꾸면 **같은 계통을 그 해법으로 다시 푼다.**"""
        pick = getattr(self, "_solver_pick", None)
        if pick is None:
            return
        method = pick.currentData() or "nr"
        if method == getattr(self, "solver", "nr"):
            return
        path = getattr(self, "_last_path", None)
        if not path:
            self.solver = method
            return
        # 조건을 바꿔 푼 상태면 그 케이스를 그대로 쓴다 (원본으로 되돌리지 않는다)
        case = getattr(self, "_case_for_solver", None)
        self._start_solve(path, case, method)

    # ── 수렴 탭 ──
    def conv_page(self):
        c = self.c
        sol = self.sol
        conv = dict(
            converged=sol.converged if sol else CONV["converged"],
            iters=sol.iters if sol else CONV["iters"],
            threshold=sol.threshold if sol else CONV["threshold"],
            mis=list(sol.mis_history) if sol else CONV["mis"],
            # 🚨 계통을 풀었으면 견본 값(CONV)으로 메우지 않는다 — DC 단독 계통에서 반복 기록이 없을 때
            #    견본 표(AC_P_mis 5.1e-01 …)가 그대로 떠 실제 결과처럼 보였다(2026-11-03 전수 검사)
            blocks=(list(sol.block_names) if sol is not None and sol.block_names else
                    ([] if sol is not None else CONV["blocks"])),
            block_hist=(sol.block_history.tolist()
                        if sol is not None and sol.block_history.size
                        else ([] if sol is not None else CONV["block_hist"])),
            dominant=(list(sol.dominant_block) if sol is not None and sol.dominant_block
                      else ([] if sol is not None else CONV["dominant"])),
            seconds=sol.seconds if sol else CONV["seconds"],
        )
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(11)

        # 요약 줄
        head = QFrame()
        head.setObjectName("card")
        hv = QHBoxLayout(head)
        hv.setContentsMargins(14, 11, 14, 11)
        hv.setSpacing(26)

        def kv(k, v, color=None):
            b = QVBoxLayout()
            b.setSpacing(2)
            a = QLabel(k)
            a.setStyleSheet(f"color:{c['muted']};font-size:11px;")
            d = QLabel(v)
            d.setStyleSheet(
                f"color:{color or c['text']};font-size:17px;font-weight:600;")
            b.addWidget(a)
            b.addWidget(d)
            return b

        hv.addLayout(kv("수렴", "성공" if conv["converged"] else "실패",
                        c["ok"] if conv["converged"] else c["warn"]))
        hv.addLayout(kv("반복 횟수", iters_text(sol) if sol is not None else f"{conv['iters']}회"))
        hv.addLayout(kv("계산 시간", f"{conv['seconds']:.2f} s"))
        hv.addLayout(kv("수렴 기준", f"{conv['threshold']:g}"))
        # 🚨 견본(CONV)의 마지막 값 3.77e-04 를 늘 찍고 있었다 — 계통마다 같은 숫자였다(2026-11-03)
        hv.addLayout(kv("최종 불평형", f"{conv['mis'][-1]:.2e}" if conv["mis"] else "—"))
        hv.addStretch()
        # 🚨 고르는 자리는 **사이드바로 옮겼다** (2026-09-08 점검 i10 — 사용자:
        #    *"GS / NR 중에 고르는걸 수렴 탭 말고 사이드바에 넣자"*). 여기서 고르면
        #    「푸는 법」을 정하러 결과 탭 하나를 파고 들어가야 했다. 다만 **이 결과가
        #    어느 해법으로 나온 것인지**는 수렴 탭에 뜻이 있으므로 글로 남긴다.
        hv.addLayout(kv("해법", "Gauss-Seidel"
                        if getattr(sol, "method", "nr") == "gs" else "Newton-Raphson"))
        outer.addWidget(head)

        # 불평형이 줄어드는 과정
        box = QFrame()
        box.setObjectName("card")
        bv = QVBoxLayout(box)
        bv.setContentsMargins(14, 11, 14, 13)
        t = QLabel("반복에 따른 최대 불평형")
        t.setStyleSheet(f"color:{c['text']};font-size:14px;font-weight:600;")
        bv.addWidget(t)
        sub = QLabel("세로축은 로그 눈금 · 초록 점선 아래로 내려가면 수렴")
        sub.setStyleSheet(f"color:{c['muted']};font-size:11px;")
        bv.addWidget(sub)
        bv.addWidget(MisChart(conv["mis"], conv["threshold"], c))
        bar = QHBoxLayout()
        bar.setSpacing(10)
        for i, m in enumerate([]):     # 숫자 칸 줄은 그래프가 대신한다 (2026-11-15)
            cell = QFrame()
            cell.setObjectName("plot")
            cv = QVBoxLayout(cell)
            cv.setContentsMargins(10, 8, 10, 8)
            a = QLabel(f"{i}회")
            a.setStyleSheet(f"color:{c['muted']};font-size:11px;")
            d = QLabel(f"{m:.2e}")
            d.setStyleSheet(
                f"color:{c['ok'] if m < conv['threshold'] else c['text']};"
                f"font-size:15px;font-weight:600;")
            cv.addWidget(a)
            cv.addWidget(d)
            bar.addWidget(cell)
        bar.addStretch()
        bv.addLayout(bar)
        outer.addWidget(box)

        # 블록별 + 발목 잡은 곳
        box2 = QFrame()
        box2.setObjectName("card")
        b2 = QVBoxLayout(box2)
        b2.setContentsMargins(14, 11, 14, 13)
        b2.setSpacing(8)
        t2 = QLabel("무엇이 수렴을 늦추나 — 반복별 블록 최대 불평형")
        t2.setStyleSheet(f"color:{c['text']};font-size:14px;font-weight:600;")
        b2.addWidget(t2)
        # 🚨 엔진은 블록 최대값을 **줄을 지우기 전** 불평형에서 잰다(`solve_ACDC_newton_aug_v17.m`
        #    `block_max` — `row_del` 적용 전의 AC_P_mis · AC_Q_mis). 풀지 않는 줄이 섞인 열은 수렴해도
        #    값이 안 준다(case24: AC_P_mis 2.6 에 머묾 · 최종 불평형은 5e-13). 그 열을 빨갛게 «발목 잡은
        #    곳» 으로 찍고 있었다 (2026-11-15). 수렴했는데 마지막 값이 기준을 한참 넘는 열은 따로 표시한다.
        _last = conv["block_hist"][-1] if conv["block_hist"] else []
        stuck = {i for i, v in enumerate(_last)
                 if conv["converged"] and v > max(conv["threshold"] * 1e3, 1e-3)}
        tb = QTableWidget(len(conv["block_hist"]), len(conv["blocks"]) + 2)
        tb.setHorizontalHeaderLabels(["반복"] + [b + (" *" if i in stuck else "")
                                                for i, b in enumerate(conv["blocks"])] + ["가장 큰 블록"])
        tb.verticalHeader().setVisible(False)
        tb.verticalHeader().setDefaultSectionSize(30)
        tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tb.setMinimumHeight(30 * len(conv["block_hist"]) + 46)
        tb.setMaximumHeight(30 * len(conv["block_hist"]) + 46)
        for r, row in enumerate(conv["block_hist"]):
            # 줄 r = 위 「반복에 따른 최대 불평형」 의 r회(0회 = 출발점) — 1 부터 세면 반복이 4회인데
            # 표가 1 ~ 5 로 한 줄 많아 보였다(2026-11-03 전수 검사)
            tb.setItem(r, 0, QTableWidgetItem(f"{r}회"))
            live = [i for i in range(len(row)) if i not in stuck]
            worst = max(live, key=lambda i: row[i]) if live else -1
            for cc, v in enumerate(row):
                it = QTableWidgetItem("—" if v == 0 else f"{v:.1e}")
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if cc in stuck:
                    it.setForeground(QColor(c["muted"]))
                elif cc == worst and v > 0:
                    it.setForeground(QColor(c["warn"]))     # `Qt.red` 는 어두운 화면에서 묻혔다
                tb.setItem(r, cc + 1, it)
            dom = (conv["blocks"][worst] if (stuck and worst >= 0 and row[worst] > 0)
                   else ("—" if stuck else conv["dominant"][r]))
            tb.setItem(r, len(row) + 1, QTableWidgetItem(dom))
        b2.addWidget(tb)
        if stuck:
            n_st = QLabel("* 표시한 열은 풀지 않는 줄(예: slack 버스의 유효전력)까지 섞어 잰 값이라 수렴해도 줄지 않습니다. "
                          "수렴 판정은 그 줄을 뺀 「최종 불평형」 으로 합니다 — 이 열은 «가장 큰 블록» 에서 뺐습니다.")
            n_st.setWordWrap(True)
            n_st.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            b2.addWidget(n_st)
        note = QLabel("조류계산은 방정식 묶음 8종의 오차를 함께 줄여 나갑니다. "
                      "그중 오차가 가장 큰 묶음이 수렴 속도를 결정합니다 (빨간 값). "
                      "계산이 안 끝날 때 어느 방정식이 문제인지 여기서 보입니다.")
        note.setStyleSheet(f"color:{c['muted']};font-size:11px;")
        b2.addWidget(note)
        outer.addWidget(box2)

        outer.addStretch()
        return w

    def set_bus(self, idx):
        self.bus_row = int(idx)
        self.rebuild()

    def set_time(self, idx):
        self.t = int(idx)
        self.rebuild()

    def set_vsc(self, on):
        self.show_vsc = bool(on)
        self.rebuild()

    def toggle_vsc(self):
        self.set_vsc(not self.show_vsc)

    def set_plot_pick(self, i):
        """전압·위상 탭에서 어느 차트를 볼지 고른다 (2026-08-28)."""
        i = int(i)
        if i == self.plot_pick:
            return
        self.plot_pick = i
        self.rebuild()
        self._fade_graph()   # 앱 2.3 — 그래프만 바뀐다

    def reset_topo_places(self, case_name):
        """계통도에서 끌어 옮긴 버스 자리를 지우고 처음 배치로 (2026-09-08 i16).

        🚨 자리를 저장해 두면 **`layered_layout()` 을 아무리 고쳐도 그 계통만
           옛 모습**이다 — 버스를 한 번 끌면 그때의 자리 전부가 적히기 때문이다.
        """
        import topology
        if not topology.clear_places(case_name):
            return
        self.rebuild()
        self._fade_graph()   # 앱 2.3 — 계통도 배치 처음으로

    def set_topo_zoom(self, z):
        """계통도가 배율을 바꿨다고 알려 온다. **다시 그리지 않는다** — 계통도가
        스스로 그렸고, 여기서는 다음 계산 때 되살리려고 적어 두기만 한다."""
        self.topo_zoom = float(z)

    def set_violations(self, on):
        """계통도 '위반 보기' 켜기/끄기. 계통도 토글 버튼이 부른다."""
        self.show_violations = bool(on)
        self.rebuild()

    def _popup(self, title, body, min_h=380):
        """계통도 클릭에 답하는 작은 창 — 세 갈래(선로·버스·변환기)가 같이 쓴다.

        `min_h` = 최소 높이. 변환기 창은 **그래프 + 표** 를 같이 놓아 더 높다.
        """
        d = QDialog(self)
        d.setWindowTitle(title)
        d.setStyleSheet(self.styleSheet())
        d.setMinimumSize(560, min_h)
        v = QVBoxLayout(d)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)
        v.addWidget(body, 1)
        close = QPushButton("닫기")
        close.clicked.connect(d.accept)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(close)
        v.addLayout(row)
        QTimer.singleShot(0, lambda: play_charts(d))     # 앱 2.3 — 창이 뜨면 그래프가 그려진다
        d.exec()

    def pick_line_by_bus(self, a, b):
        """그래프에서 요소를 누르면 **그것이 어느 선로인지** 찾아 팝업을 띄운다
        (2026-09-08 점검 i14·i15).

        조류 P·Q 격자와 부하율 막대가 같이 쓴다. 둘 다 «출발 버스 · 도착 버스» 는
        아는데 계통도의 어느 선인지는 모른다 — 그 짝으로 `topology` 의 선을 찾는다.
        `a`·`b` 는 글자다(`"106"` · DC 는 `"DC1"`).
        """
        if self.sol is None:
            return
        import topology

        def num(x):
            x = str(x).strip().upper()
            if x.startswith("DC"):
                x = x[2:]
            try:
                return int(float(x))
            except ValueError:
                return None

        na, nb = num(a), num(b)
        if na is None or nb is None:
            return
        g = topology.build_graph(self.sol)
        for ei, (x, y, kind) in enumerate(g.edges):
            if kind not in ("AC", "변압기", "DC"):
                continue
            ba, bb = topology._busno(g.keys[x]), topology._busno(g.keys[y])
            if {ba, bb} == {na, nb}:
                self.show_line_profile(g, ei)
                return
        # 못 찾는 경우 — 3권선 지선처럼 계통도에서 갈래로 쪼개진 것
        QMessageBox.information(
            self, "그 선로를 계통도에서 못 찾았습니다",
            f"{na} – {nb} 를 잇는 선을 계통도에서 찾지 못했습니다.\n\n"
            "3권선 변압기처럼 계통도에서 여러 갈래로 쪼개 그리는 것은 "
            "짝을 맞출 수 없습니다.")

    def show_bus_profile(self, g, i):
        """계통도에서 **버스**를 누르면 24시간 전압을 띄운다 (2026-09-08 점검 i18).

        끌어 옮기기와 겹치므로, 거의 안 움직이고 뗐을 때만 여기까지 온다
        (`TopologyView.mouseReleaseEvent`).
        """
        if self.sol is None:
            return
        import topology
        c = self.c
        side = "DC" if g.kind[i] == "DC" else "AC"
        title = f"{side} {g.label[i]} 버스"
        ser = topology.bus_series(g, self.sol, i)
        if ser is None:
            body = charts._note(c, f"{title} 는 결과 표에 없습니다.")
        elif len(ser[0]) <= 1:
            lo, hi = ser[2]
            lim = f"\n한계 {lo:.3f} ~ {hi:.3f}" if lo is not None else ""
            body = charts._note(
                c, f"{title}\n이 케이스는 시간별(24h) 데이터가 없습니다.\n"
                   f"현재 전압 = {ser[1][0]:.4f} pu{lim}")
        else:
            body = charts.voltage_profile_view(c, ser[0], ser[1], ser[2],
                                               f"{title}  ·  24시간 전압")
        self._popup(f"{title} — 24시간 전압", body)

    def show_ic_facts(self, g, ei):
        """계통도에서 **변환기**를 누르면 그 값을 띄운다 (2026-09-08 점검 i18).

        위 = **하루치 전력 그래프**(`topology.ic_series`) · 아래 = 고른 시각의 표.
        1시각 계통이거나 시각별 값이 없으면 표만 놓는다.

        🚨 **선이 평평해도 고장이 아니다** — 두 선 중 «제어하는 쪽» 만 움직인다.
           case24 24h 일곱 개를 실측하면: DC 전압 제어(107-1·113-4)는 **P** 만,
           AC 전압 제어(204-2·215-6)는 **Q** 만 움직이고, 둘 다 정전력인 셋
           (301-3·123-5·217-7)은 하루 내내 그대로다.
        """
        if self.sol is None:
            return
        import topology
        c = self.c
        rows = topology.ic_facts(g, self.sol, ei, self.t)
        title = topology.edge_label(g, ei).replace(" 선로", " 변환기")
        if not rows:
            self._popup(title, charts._note(c, "이 변환기의 값이 결과에 없습니다."))
            return
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        ser = topology.ic_series(g, self.sol, ei)
        if ser is not None:
            v.addWidget(charts.ic_profile_view(c, ser[0], ser[1],
                                               f"{title}  ·  24시간 조류"), 3)

        tb = QTableWidget(len(rows), 2)
        tb.setHorizontalHeaderLabels(["항목", f"{self.t + 1}시 값"])
        tb.verticalHeader().setVisible(False)
        tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tb.setAlternatingRowColors(True)
        for r, (k, val) in enumerate(rows):
            tb.setItem(r, 0, QTableWidgetItem(k))
            it = QTableWidgetItem(val)
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tb.setItem(r, 1, it)
        if ser is not None:
            # 표는 **내용만큼만** 차지하고 나머지는 그래프에 준다 — 비율로 나누면
            # 일곱 줄짜리 표가 잘려 「한계」 줄이 스크롤 뒤로 숨는다 (2026-09-08)
            #
            # ⚠️ **높이를 지금 재면 안 된다.** 창에 붙기 전이라 머리줄이 28~31 로
            #    나오는데, QSS 가 붙으면 40 이 된다 — 그 차이만큼 마지막 줄이
            #    잘렸다(실측 표230 · 필요250). 그래서 `singleShot(0)` 으로
            #    **붙은 뒤에** 재서 고정한다.
            tb.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        v.addWidget(tb, 0)

        def _fit_table(tb=tb, n=len(rows)):
            tb.setFixedHeight(tb.horizontalHeader().height()
                              + sum(tb.rowHeight(r) for r in range(n))
                              + 2 * tb.frameWidth() + 2)
        QTimer.singleShot(0, _fit_table)

        # 그래프 갈래를 밝히거나(합계인지 등), 못 그린 까닭을 적는다
        msg = ser[2] if ser is not None else None
        if ser is None:
            # ⚠️ **왜 그래프가 없는지 갈래마다 다르다.** 처음엔 「시각이 하나라」
            #    한 줄로만 적었다가, 24시각인 71bus 3IC 계통에서 **거짓말**이 됐다
            #    (2026-09-08 사용자 지적).
            if int(getattr(self.sol, "n_time", 1) or 1) <= 1:
                msg = "이 계통은 시각이 하나라 24시간 그래프가 없습니다."
            else:
                msg = "이 변환기가 계산 결과 표에 없어 시간별 값을 못 그립니다."
        if msg:
            note = QLabel(msg)
            note.setWordWrap(True)
            note.setTextFormat(Qt.MarkdownText)
            note.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            v.addWidget(note)
        if ser is None:
            v.addStretch(1)          # 표·문구를 위로 붙인다
        self._popup(title, w, 700 if ser is not None else 400)

    def show_line_profile(self, g, ei):
        """계통도에서 선로를 클릭하면 그 선로의 24시간 부하율을 팝업으로 띄운다.
        시간별 데이터가 없는 케이스(스냅샷 1시각)면 그 사실을 적어 준다.

        🚨 **변환기(IC)도 여기로 온다** (2026-09-08 i18) — 부하율이 없으므로
           `show_ic_facts` 로 넘긴다.
        """
        if self.sol is None:
            return
        import topology
        if g.edges[ei][2] == "IC":
            self.show_ic_facts(g, ei)
            return
        c = self.c
        title = topology.edge_label(g, ei)
        ser = topology.loading_series(g, self.sol, ei)
        if ser is None:
            body = charts._note(c, f"{title} 는 부하율 결과가 없습니다.\n"
                                   "(변환기·3권선 지선이거나 Branch 표에 없는 선로)")
        elif len(ser[0]) <= 1:
            pct = ser[1][0] if ser[1] else float("nan")
            body = charts._note(
                c, f"{title}\n이 케이스는 시간별(24h) 데이터가 없습니다.\n"
                   f"현재 부하율 = {pct:.1f}%")
        else:
            body = charts.loading_profile_view(c, self.sol, ser[0], ser[1],
                                               f"{title}  ·  24시간 부하율")
        self._popup(f"{title} — 24시간 부하율", body)

    def pick_grid_columns(self):
        """계통 데이터 표의 열 선택 (2026-09-02).

        **왜 여기에도 필요한가** — 열이 가장 많은 표가 계통 데이터다. 1512px 창
        실측으로 IC 20열이 **903px**, AC 버스 21열이 541px, AC 선로 18열이 427px
        넘친다(사이드바를 접어 224px 을 보태도 넷이 남는다). 결과 표는 「열 선택」이
        있어 들어가는데 정작 넘치는 쪽에는 없었다.

        🚨 **결과 표와 다른 점 둘.**
        ① 여기 표는 **고치는 표**다 — 숨긴 열은 고칠 수도 없으므로 판에서 말해 준다.
        ② 열을 **이름이 아니라 번호**로 센다(`grid_visible`). 머리글이 파일마다 다르고
           빈 열이 뒤에 붙기도 해서(`GRID_PAD_TO_HEADERS`) 이름이 안 고정된다.
        📌 왼쪽 고정 열(데이터 열 0)은 목록에 없다 — 그게 없으면 어느 줄인지 모른다.
        """
        key = self.grid_key
        cols = getattr(self, "_grid_all_cols", None)
        if key in (ADJ.KEY, LOAD_KEY) or not cols:
            return
        label = dict(GRID_TABLES).get(key, key)
        editable = GRID_EDITABLE.get(key, set()) | RULES.editable(key)
        now = self.grid_visible.get(key)

        d = QDialog(self)
        d.setWindowTitle(f"열 선택 — {label}")
        d.setStyleSheet(self.styleSheet())
        d.setMinimumWidth(340)
        v = QVBoxLayout(d)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(7)
        info = QLabel(f"「{label}」 표에 보일 열을 고르세요")
        info.setStyleSheet(f"color:{self.c['muted']};font-size:13px;")
        v.addWidget(info)
        warn = QLabel("⚠️ 끈 열은 고칠 수도 없습니다. 고친 값은 그대로 남습니다.")
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{self.c['warn']};font-size:12px;")
        v.addWidget(warn)

        boxes = []
        bulk = QHBoxLayout()
        bulk.setSpacing(6)
        # ⚠️ 「처음대로」는 안 둔다 — 계통 데이터에는 결과 표의 `always` 같은
        #    「처음 켜져 있던 것」이 없다(늘 전부다). 두면 「전부 켜기」와 같은 단추다.
        cand = {j for j, _ in cols}
        for lab, pick in (("전부 켜기", lambda j: True),
                          ("고칠 수 있는 것만", lambda j: j in editable)):
            bb = QPushButton(lab)
            bb.setCursor(Qt.PointingHandCursor)
            # 🚨 **줄어들지 않으면 잠근다.** IC 는 22 열이 전부 고칠 수 있어 이 단추가
            #    아무 일도 안 한다 — 눌렀는데 그대로면 고장으로 읽힌다.
            if lab == "고칠 수 있는 것만" and not (cand & editable) < cand:
                bb.setEnabled(False)
                bb.setToolTip("이 표는 열이 다 고칠 수 있는 것이라 줄지 않습니다"
                              if editable else "이 표에는 고칠 수 있는 열이 없습니다")
            else:
                bb.clicked.connect(
                    lambda _=False, f=pick: [b.setChecked(f(j0))
                                             for j0, b in boxes])
            bulk.addWidget(bb)
        bulk.addStretch(1)
        v.addLayout(bulk)

        # 📌 **전부 고칠 수 있으면 꼬리를 안 붙인다** — IC 는 20 줄에 같은 말이
        #    되풀이돼 목록이 읽히지 않았다. 그럴 땐 위에서 한 번만 말한다.
        all_ed = bool(cand) and (cand & editable) == cand
        if all_ed:
            note = QLabel("이 표는 열이 다 고칠 수 있습니다.")
            note.setStyleSheet(f"color:{self.c['muted']};font-size:12px;")
            v.addWidget(note)
        for j, head in cols:
            tail = "" if all_ed or j not in editable else "   (고칠 수 있음)"
            b = QCheckBox(head + tail)
            b.setChecked(now is None or j in now)
            v.addWidget(b)
            boxes.append((j, b))

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("취소")
        cancel.clicked.connect(d.reject)
        ok = QPushButton("적용")
        ok.setObjectName("primary")
        ok.clicked.connect(d.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        v.addLayout(row)

        if d.exec():
            picked = {j for j, b in boxes if b.isChecked()}
            if not picked:
                # 결과 표와 같은 잣대 — 조용히 무시하면 "적용이 안 되네" 로 끝난다.
                QMessageBox.information(
                    self, "열을 하나는 켜 주세요",
                    "열을 전부 끄면 표가 빈칸이 됩니다.\n하나 이상 골라 주세요.")
                return
            self.grid_visible[key] = picked
            self.rebuild()
            self._fade_table()   # 앱 2.3 — 열이 바뀐 표

    def pick_columns(self):
        # 🚨 탭 글자에는 개수 꼬리가 붙는다(「점검 (25)」) — `_tab_base` 로 뗀다.
        #    안 떼면 그 표에 열 목록을 나중에 붙여도 이름이 안 맞아 또 안 열린다.
        name = _tab_base(self._tabs.tabText(self._tabs.currentIndex()))
        if name == "계통 데이터":
            return self.pick_grid_columns()
        if name not in TABLE_SPECS:      # 단추가 안 보이는 탭 — 눌릴 일이 없다
            return
        d = QDialog(self)
        d.setWindowTitle(f"열 선택 — {name}")
        d.setStyleSheet(self.styleSheet())
        d.setMinimumWidth(320)
        v = QVBoxLayout(d)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(7)
        info = QLabel("표에 보일 열을 고르세요")
        info.setStyleSheet(f"color:{self.c['muted']};font-size:13px;")
        v.addWidget(info)
        boxes = []
        # 열이 열셋까지 있어 하나씩 누르면 손이 아프다 (2026-08-27 사용자 요청).
        #   「처음대로」의 기준은 `TABLE_SPECS` 의 `always` — 표를 처음 열 때 켜져 있던 것이다.
        bulk = QHBoxLayout()
        bulk.setSpacing(6)
        for label, pick in (
                ("전부 켜기", lambda col, always: True),
                ("전부 끄기", lambda col, always: False),
                ("처음대로", lambda col, always: bool(always))):
            bb = QPushButton(label)
            bb.setCursor(Qt.PointingHandCursor)
            bb.clicked.connect(
                lambda _=False, f=pick: [b.setChecked(f(c0, a0))
                                         for (c0, a0), (_c, b) in zip(
                                             TABLE_SPECS[name], boxes)])
            bulk.addWidget(bb)
        bulk.addStretch(1)
        v.addLayout(bulk)
        for col, _always in TABLE_SPECS[name]:
            b = QCheckBox(col)
            b.setChecked(col in self.visible[name])
            v.addWidget(b)
            boxes.append((col, b))
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("취소")
        cancel.clicked.connect(d.reject)
        ok = QPushButton("적용")
        ok.setObjectName("primary")
        ok.clicked.connect(d.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        v.addLayout(row)
        if d.exec():
            picked = {col for col, b in boxes if b.isChecked()}
            if not picked:
                # 열이 하나도 없으면 표가 사라진다. 조용히 무시하면 "적용이 안 되네" 로 끝난다.
                QMessageBox.information(
                    self, "열을 하나는 켜 주세요",
                    "열을 전부 끄면 표가 빈칸이 됩니다.\n하나 이상 골라 주세요.")
                return
            self.visible[name] = picked
            self.rebuild()
            self._fade_table()   # 앱 2.3 — 열이 바뀐 표

    def target_options(self):
        """지금 고를 수 있는 것들 — [(보일 글자, 넣을 값)]. 없으면 빈 목록.

        **계통에 실제로 있는 것만** 담는다. 예전 타이핑 칸은 없는 번호도 받아 놓고
        조용히 버렸다(12버스 계통에서 기본값 `3, 7, 12` 가 3 하나만 맞았다).

        고르는 것이 무엇이냐는 **고른 항목**이 정한다 (`CI.kinds_needed`) —
        선로 부하율을 보면서 버스 번호를 고르면 아무것도 안 나온다.
        """
        sol = self.sol
        if sol is None:
            return []
        if self.compare_axis == "시간끼리":
            return [(f"{i} H", str(i)) for i in range(1, sol.n_time + 1)]

        out, seen = [], set()
        for k in (CI.kinds_needed(self.picked, self.compare_axis) or ["bus"]):
            if k == "bus":
                # 🚨 AC·DC 를 함께 담는다 — 전압 크기는 AC 표, DC 전압은 DC 표를
                #    보므로 한쪽만 담으면 다른 항목에서 고를 것이 없어진다.
                for which in ("AC", "DC"):
                    arr = getattr(sol, which, None)
                    if arr is None or not getattr(arr, "size", 0) or arr.ndim != 3:
                        continue
                    for b in arr[:, 0, 0]:
                        val = str(int(b))
                        if val not in seen:
                            seen.add(val)
                            out.append((f"{which} {val}", val))
            else:
                # 선로·IC 는 **두 번호**로 고른다 (`charts._pick_rows` 와 같은 꼴)
                which = "Branch" if k == "branch" else "VSC_bus"
                arr = getattr(sol, which, None)
                if arr is None or not getattr(arr, "size", 0):
                    continue
                a2 = arr[:, :, 0] if arr.ndim == 3 else arr
                for r in a2:
                    val = f"{int(r[0])}-{int(r[1])}"
                    if val not in seen:
                        seen.add(val)
                        out.append((f"{CI.UNIT_NAME[k]} {int(r[0])}–{int(r[1])}", val))
        return out

    def target_values(self):
        """지금 고른 것들. 계통에 **없는 것은 뺀다** — 케이스를 갈아 열면 남아 있다."""
        ok = {v for _, v in self.target_options()}
        out = []
        for t in (self.compare_targets or "").replace(";", ",").split(","):
            t = t.strip()
            if t in ok and t not in out:     # 중복도 여기서 걸린다 (옛 결함 ④)
                out.append(t)
        return out

    def target_button(self):
        c = self.c
        opts = self.target_options()
        got = self.target_values()
        if not opts:
            b = QPushButton("고를 것이 없습니다")
            b.setEnabled(False)
            return b
        # 적으면 고른 것을 그대로 보여준다 — 한 번 더 눌러 확인할 일이 없게
        txt = ", ".join(got) if 0 < len(got) <= 6 else (
            f"{len(got)}개 고름" if got else "고르기")
        b = QPushButton(txt)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(f"이 계통에 있는 {len(opts)}개 중에서 고릅니다")
        b.clicked.connect(lambda: self.open_target_pick(b))
        return b

    def open_target_pick(self, near):
        """찾는 칸이 붙은 고르개.

        ⚠️ **찾는 칸이 있어야 한다** — 가장 큰 케이스가 버스 25,000개다
        (`AConly_25k_v2.xlsx`). 목록만 내밀면 아무도 못 찾는다.

        ⚠️ 고를 때마다 `rebuild()` 하면 **이 판이 그리는 도중에 사라진다**.
           그래서 고르는 동안은 값만 고치고, 닫힐 때 한 번만 다시 그린다
           (「볼 항목」 고르개와 같은 약속).
        """
        opts = self.target_options()
        chosen = list(self.target_values())
        c = self.c
        pop = QFrame(self, Qt.Popup)
        pop.setObjectName("card")
        outer = QVBoxLayout(pop)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        find = QLineEdit()
        find.setPlaceholderText(f"찾기 — {len(opts)}개 중에서")
        outer.addWidget(find)

        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(2)
        boxes = []
        for label, val in opts:
            cb = QCheckBox(label)
            cb.setChecked(val in chosen)
            cb.stateChanged.connect(
                lambda st, x=val: (x not in chosen and chosen.append(x)) if st
                else (x in chosen and chosen.remove(x)))
            iv.addWidget(cb)
            boxes.append((cb, label))
        sa = QScrollArea()
        sa.setWidget(inner)
        sa.setWidgetResizable(True)
        sa.setFixedSize(250, min(430, inner.sizeHint().height() + 8))
        outer.addWidget(sa)

        def filt(t):
            t = t.strip().lower()
            for cb, label in boxes:
                cb.setVisible(not t or t in label.lower())
        find.textChanged.connect(filt)

        pop.hide_done = False

        def done(_e=None):
            if pop.hide_done:
                return
            pop.hide_done = True
            self.compare_targets = ", ".join(chosen[:50])
            self.rebuild()
            reveal(getattr(self, "_center_w", None))   # 앱 2.3 — 비교 대상 고른 뒤
        pop.hideEvent = lambda e: done(e)

        pop.adjustSize()
        g = near.mapToGlobal(near.rect().bottomLeft())
        pop.move(g.x(), g.y() + 6)
        pop.show()
        find.setFocus()
        self._target_pop = pop

    def usable_items(self):
        """지금 축에서 고를 수 있는 항목과, 못 고르는 까닭."""
        out = []
        for name in CI.NAMES:
            why = ""
            usable = CI.shown_in(name, self.compare_axis)
            if not usable:
                why = ("시나리오끼리 비교에서만"
                       if CI.by(name) == "ic" else "시간끼리 비교에서만")
            elif self.sol is not None:
                gone = CI.available(self.sol, name)
                if gone:
                    usable, why = False, gone
            out.append((name, usable, why))
        return out

    def item_chip(self, tabs):
        """비교 탭 줄 구석 — 「볼 항목 N」. 누르면 고르는 판이 열린다."""
        c = self.c
        n = sum(1 for nm, ok, _ in self.usable_items() if ok and nm in self.picked)
        b = QPushButton(f"볼 항목 {n}" if n else "볼 항목")
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip("고른 항목이 왼쪽 탭으로 나옵니다")
        b.clicked.connect(lambda: self.open_item_pick(b))
        tabs.setCornerWidget(b, Qt.TopRightCorner)
        return tabs

    def open_item_pick(self, near):
        """항목 고르는 판 — 여럿 고르고 닫으면 그때 한 번 다시 그린다.

        ⚠️ 고를 때마다 `rebuild()` 를 하면 **이 판이 그리는 도중에 사라진다**.
           그래서 고르는 동안은 `self.picked` 만 고치고, 닫힐 때 한 번만 다시 그린다.
        """
        c = self.c
        pop = QFrame(self, Qt.Popup)
        pop.setObjectName("card")
        pv = QVBoxLayout(pop)
        pv.setContentsMargins(14, 12, 14, 12)
        pv.setSpacing(6)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(5)
        for name, usable, why in self.usable_items():
            cb = QCheckBox(name)
            cb.setChecked(name in self.picked and usable)
            cb.setEnabled(usable)
            cb.stateChanged.connect(
                lambda st, n2=name: (self.picked.add(n2) if st
                                     else self.picked.discard(n2)))
            iv.addWidget(cb)
            if why:
                w = QLabel(f"   {why}")
                w.setStyleSheet(f"color:{c['warn']};font-size:12px;")
                iv.addWidget(w)
        sa = QScrollArea()
        sa.setWidget(inner)
        sa.setWidgetResizable(True)
        sa.setFixedSize(240, min(520, inner.sizeHint().height() + 8))
        pv.addWidget(sa)
        pop.hide_done = False

        def done(_e=None):
            if not pop.hide_done:
                pop.hide_done = True
                self.rebuild()
                reveal(getattr(self, "_center_w", None))   # 앱 2.3 — 비교 항목 고른 뒤
        pop.hideEvent = lambda e: done(e)
        pop.adjustSize()
        g = near.mapToGlobal(near.rect().bottomRight())
        pop.move(g.x() - pop.width(), g.y() + 6)
        pop.show()
        self._item_pop = pop

    def compare_area(self):
        c = self.c
        wide = self.compare_axis in ("시간끼리", "시나리오끼리")
        picked = [n for n in CI.NAMES
                  if n in self.picked and CI.shown_in(n, self.compare_axis)
                  and not (self.sol is not None and CI.available(self.sol, n))]
        if not picked and self.sol is not None:
            # 🚨 기본 항목 「전압 크기」 는 AC 표에서 읽는다 — DC 단독 계통에서는 없어서 비교 화면이
            #    빈 채로 열렸다(2026-11-03 전수 검사). 고른 것이 하나도 안 보이면 이 계통에 있는
            #    전압 항목을 대신 고른다.
            for alt in ("전압 크기", "DC 전압"):
                if CI.shown_in(alt, self.compare_axis) and not CI.available(self.sol, alt):
                    self.picked = set(self.picked) | {alt}
                    picked = [alt]
                    break
        tabs = QTabWidget()
        if not picked:
            page = QWidget()
            pv = QVBoxLayout(page)
            lb = QLabel("왼쪽에서 볼 항목을 하나 이상 고르세요")
            lb.setAlignment(Qt.AlignCenter)
            lb.setStyleSheet(f"color:{c['muted']};font-size:16px;")
            pv.addWidget(lb)
            tabs.addTab(page, "결과")
            return self.item_chip(tabs)
        if self.compare_axis == "시나리오끼리":
            return self.item_chip(self.compare_scenarios_area(picked))
        targets = [t.strip() for t in self.compare_targets.split(",") if t.strip()]
        unit = "버스" if self.compare_axis == "버스끼리" else "시간"
        for name in picked:
            # 2026-11-15 — 그래프와 표가 카드 없이 바탕에 바로 놓여 다른 화면과 어긋났다. 흰 카드에 담는다.
            page = GlassCard(c, self.dark, radius=16)
            pv = QVBoxLayout(page)
            pv.setContentsMargins(16, 14, 16, 14)
            pv.setSpacing(9)
            # 원본 앱은 "내보내기"를 눌러야 팝업창에 비교 그림을 그려 줬지만,
            # 여기서는 화면에 바로 그린다 (charts.compare_chart).
            box = charts.compare_chart(c, self.sol, name, self.compare_axis,
                                       targets)
            pv.addWidget(box, 2)
            tb = self.compare_table(name, targets)
            if tb is not None:
                pv.addWidget(tb, 1)
            tabs.addTab(page, name)
        return self.item_chip(tabs)

    def compare_save_button(self):
        """「이 비교 그림 저장」 단추 (2026-09-01).

        비교 그림 저장은 위쪽 「내보내기」와 **따로** 둔다(사용자 요청).
        원본 앱도 비교는 별도 버튼이었다(`ExportComparisonButtonPushed`).
        ⚠️ 이름을 `sb` 로 쓰면 안 된다 — 사이드바를 그리는 함수의 `sb` 는 사이드바
           자체다. 덮어쓰면 사이드바가 파이썬 참조를 잃고 사라진다(실제로 겪음).
        """
        b = QPushButton("이 비교 그림 저장  (PNG · PDF)")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(self.save_compare_figures)
        return b

    def save_compare_figures(self):
        """지금 보고 있는 비교 그림들을 그대로 파일로. (일반 내보내기와 따로)"""
        if self.sol is None:
            QMessageBox.information(self, "비교 그림 저장",
                                    "먼저 케이스를 불러와 계산하세요.")
            return
        scen = self.compare_axis == "시나리오끼리"
        items = [n for n, always in COMPARE_ITEMS
                 if n in self.picked
                 and (always or self.compare_axis in ("시간끼리", "시나리오끼리"))]
        if not items:
            QMessageBox.information(self, "비교 그림 저장",
                                    "왼쪽에서 볼 항목을 하나 이상 고르세요.")
            return
        targets = [t.strip() for t in self.compare_targets.split(",") if t.strip()]
        folder = exporter.default_folder(self.sol.case_name)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            files = exporter.save_compare_figures(
                self.c, self.sol, self.compare_axis, targets, items, folder,
                pairs=self.overlay_pairs() if scen else None, t=self.t)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "비교 그림 저장 실패", f"{exc}")
            return
        QApplication.restoreOverrideCursor()
        if not files:
            QMessageBox.information(
                self, "비교 그림 저장",
                "저장할 그림이 없습니다. 비교할 번호를 확인해 주세요.")
            return
        names = "\n".join(f"  · {p.name}" for p in files)
        box = QMessageBox(self)
        box.setWindowTitle("비교 그림 저장 완료")
        box.setText(f"{len(files)}개 파일을 저장했습니다.\n\n{folder}\n\n{names}")
        box.addButton("확인", QMessageBox.AcceptRole)
        opn = box.addButton("폴더 열기", QMessageBox.ActionRole)
        box.exec()
        if box.clickedButton() is opn:
            import subprocess
            subprocess.run(["open", str(folder)], check=False)

    def compare_rows(self, item, targets):
        """비교 대상들의 값 — (열이름들, 행들). 화면 표와 내보내기가 같이 쓴다.

        표를 만드는 부분과 값을 뽑는 부분을 갈라 둔 이유는, 내보내기에서
        **화면 위젯을 읽지 않고** 같은 숫자를 그대로 엑셀로 쓰기 위해서다.
        """
        sol = self.sol
        if sol is None or not targets or not sol.AC.size:
            return None
        s = CI.spec(item)
        # ⚠️ 표로 뽑는 것은 **AC 버스별 항목**까지다. 선로·IC 는 x 축이 버스가 아니라
        #    이 표 얼개(줄=시간·열=버스)에 안 맞는다 — 그림으로는 볼 수 있다.
        if s is None or s[5] != "bus" or s[1] != "AC":
            return None
        col = s[2]
        if col not in sol.cols("AC"):
            return None
        ci = sol.cols("AC").index(col)
        bus_ids = [int(b) for b in sol.AC[:, 0, 0]]

        if self.compare_axis == "버스끼리":
            rows, head = [], ["Time[h]"]
            picks = []
            for tgt in targets:
                if tgt.isdigit() and int(tgt) in bus_ids:
                    picks.append(bus_ids.index(int(tgt)))
                    head.append(f"버스 {tgt}")
            if not picks:
                return None
            for t in range(sol.AC.shape[2]):
                rows.append([t + 1] + [sol.AC[p, ci, t] for p in picks])
        else:
            head = ["Bus"] + [f"{t}H" for t in targets if t.isdigit()]
            times = [int(t) - 1 for t in targets if t.isdigit()]
            times = [t for t in times if 0 <= t < sol.AC.shape[2]]
            if not times:
                return None
            rows = [[bus_ids[r]] + [sol.AC[r, ci, t] for t in times]
                    for r in range(sol.AC.shape[0])]
        return head, rows

    def compare_table(self, item, targets):
        """비교 대상들의 실제 값을 표로 (그래프가 들어가기 전까지 숫자로 확인)."""
        got = self.compare_rows(item, targets)
        if got is None:
            return None
        head, rows = got
        tb = QTableWidget(len(rows), len(head))
        tb.setHorizontalHeaderLabels(head)
        tb.verticalHeader().setVisible(False)
        tb.verticalHeader().setDefaultSectionSize(28)
        tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tb.setAlternatingRowColors(True)
        for r, row in enumerate(rows):
            for cc, val in enumerate(row):
                txt = f"{val:.0f}" if cc == 0 else f"{val:.4f}"
                it = QTableWidgetItem(txt)
                if cc > 0:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                tb.setItem(r, cc, it)
        return tb

    # ── 하단 ──
    def statusbar(self):
        c = self.c
        bar = QFrame()
        bar.setObjectName("statusbar")
        bar.setFixedHeight(46)
        h = QHBoxLayout(bar)
        h.setContentsMargins(18, 0, 18, 0)
        h.setSpacing(20)

        def item(k, val, color=None):
            box = QVBoxLayout()
            box.setSpacing(0)
            a = QLabel(k)
            a.setStyleSheet(f"color:{c['muted']};font-size:11px;")
            b = QLabel(val)
            b.setStyleSheet(f"color:{color or c['text']};font-size:15px;font-weight:600;")
            box.addWidget(a)
            box.addWidget(b)
            return box

        # 곡선 화면에서는 **곡선 것**을 말한다. 조류계산의 위반·반복 횟수를 그대로 두면
        # 지금 보고 있는 그림과 상관없는 숫자가 아래에 남는다 (F1d 는 둘을 갈랐다).
        if self.task == "PV·QV 곡선":
            cur = self.cur
            dot = QLabel("●")
            good = cur is not None
            dot.setStyleSheet(
                f"color:{c['ok'] if good else c['muted']};font-size:13px;")
            h.addWidget(dot)
            if cur is None:
                h.addLayout(item("PV·QV 곡선", "아직 안 그림"))
            else:
                h.addLayout(item("버틸 수 있는 부하", f"{cur.nose_MW:,.1f} MW"))
                h.addLayout(item("남은 여유", f"{cur.lam_crit * 100:.1f} %"))
                h.addLayout(item("걸음", f"{cur.lam.size:,}회"))
                h.addLayout(item("한계에 걸린 발전기", f"{cur.switched.size}대",
                                 c["warn"] if cur.switched.size else None))
                h.addLayout(item("계산 시간", f"{cur.seconds:.2f} s"))
            h.addStretch(1)
            return bar

        sol = self.sol
        n = violation_count(self.viol())
        # 점 하나로 전체 상태를 알린다 — 수렴 실패든 위반이든 있으면 주황
        healthy = (sol is None or sol.converged) and n == 0
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{c['ok'] if healthy else c['warn']};font-size:13px;")
        h.addWidget(dot)

        # 봐야 할 순서대로 — 위반이 있으면 그게 제일 앞
        vb = QPushButton(f"위반 {n}건" if n else "위반 없음")
        vb.setCursor(Qt.PointingHandCursor)
        vb.setToolTip("누르면 점검 탭으로 갑니다")
        col = c["warn"] if n else c["ok"]
        vb.setStyleSheet(
            f"border:none;background:transparent;color:{col};"
            f"font-size:14px;font-weight:600;padding:0;text-align:left;")
        vb.clicked.connect(self.go_check)
        h.addWidget(vb)

        # 주파수는 계통 전체에 하나뿐인 값이라 여기 둔다 (2026-08-30 사이드바에서 옮김).
        # 스냅샷에서만 — 다이나믹·비교에는 「지금 시각」이 없어 값이 성립을 안 한다.
        if self.mode == "스냅샷":
            ft = self.freq_text()
            if ft is not None:
                h.addLayout(item("주파수", ft))

        on_overview = (sol is not None and self.mode == "스냅샷" and getattr(self, "overview_on", True)
                       and self._rail_on() == "결과")
        if sol is not None:
            if not on_overview:      # 개요에서는 카드 ① 수렴이 같은 값을 보인다 — 두 번 적지 않는다
                h.addLayout(item("수렴", "성공" if sol.converged else "실패",
                                 c["ok"] if sol.converged else c["warn"]))
                h.addLayout(item("반복", iters_text(sol)))
            # 파일 읽기 + 계산 전체. 엔진 기동이 섞였으면 그렇다고 밝힌다.
            tt = f"{sol.seconds:.2f} s"
            if not sol.warm_start:
                tt += "  (첫 계산 — 준비 시간 포함)"
            h.addLayout(item("계산 시간", tt))
        else:
            h.addLayout(item("수렴", "—", c["muted"]))
            h.addLayout(item("반복", "—"))
            h.addLayout(item("계산 시간", "—"))
        h.addStretch()
        return bar

    def _restore_tab(self, tt):
        """다시 그린 뒤 보고 있던 표 탭으로 되돌린다. 그 탭이 사라졌으면 첫 탭.

        🚨 **못 찾았을 때 아무것도 안 하고 나가면 안 된다** (2026-08-27). 화면은
           저절로 0번 탭에 앉는데 `table_tab` 만 옛 이름으로 남아, 보고 있는 탭과
           앱이 기억하는 탭이 갈린다. 계통을 바꾸면 실제로 그렇게 된다 —
           AC/DC 에서 `DC 결과` 를 보다가 AC 전용을 열면 그 탭이 통째로 사라진다.
           `table_tab` 을 보고 정하는 것들(「열 선택」 단추 감추기·나눔 자리·찾기 딱지)이
           그때부터 엉뚱한 탭 것을 쓴다.
        """
        if tt.count() == 0:
            return
        # 「시나리오」는 2026-09-08 부터 이 목록에 없다 (점검 i48) — 앞 판을 쓰던
        # 세션이나 시험이 그 이름을 들고 있으면 첫 표로 되돌린다.
        if getattr(self, "table_tab", None) == "시나리오":
            self.table_tab = "AC 결과"
        want = getattr(self, "table_tab", None)
        for i in range(tt.count()):
            if _tab_base(tt.tabText(i)) == want:
                tt.setCurrentIndex(i)
                return
        # 그 탭이 사라졌다 — 첫 탭으로 가고 **기억도 같이 맞춘다**
        tt.setCurrentIndex(0)
        self.table_tab = _tab_base(tt.tabText(0))

    def _fill_tab_pick(self, tt):
        """드롭다운에 탭 이름을 채우고 탭과 서로 잇는다 (2026-08-31).

        ⚠️ **신호가 되돌아오는 것을 막아야 한다.** 드롭다운을 고치면 탭이 옮겨가고,
           탭이 옮겨가면 드롭다운을 고치려 든다. `blockSignals` 로 한쪽을 끊어
           고리를 끊는다.
        """
        pick = getattr(self, "_tab_pick", None)
        if pick is None:
            return
        pick.blockSignals(True)
        pick.clear()
        # 2026-11-15 — 사이드바가 맡은 표(점검 · 계통 데이터)는 목록에서 뺀다. 같은 곳으로 가는 길이
        # 둘이었다. 탭 번호는 항목마다 붙여 둔다(목록 차례 ≠ 탭 차례).
        for i in range(tt.count()):
            if _tab_base(tt.tabText(i)) not in self.TABLE_FIRST:
                pick.addItem(tt.tabText(i), i)
        pick.setCurrentIndex(max(pick.findData(max(tt.currentIndex(), 0)), 0))
        pick.blockSignals(False)
        pick.currentIndexChanged.connect(
            lambda k, p=pick, t=tt: t.setCurrentIndex(p.itemData(k)) if p.itemData(k) is not None else None)

        def _follow(i, p=pick):
            k = p.findData(i)
            if k < 0:
                return
            p.blockSignals(True)
            p.setCurrentIndex(k)
            p.blockSignals(False)
        tt.currentChanged.connect(_follow)

    def go_check(self):
        """상태바의 위반 건수 → 점검 탭으로. (앱 2.3 — 사이드바와 같은 길 `go_table` 로 묶음)

        비교 모드면 스냅샷으로, 시나리오 갈래면 결과 쪽으로 돌아온 뒤 간다(2026-09-08 i48).
        """
        # 2026-11-15 — 개요 · 점검 화면에는 표 탭(`_tabs`)이 없어 `go_table` 이 아무 일도 안 했다
        # (개요에서 상태 줄 「위반 N건」 을 눌러도 안 넘어감). 사이드바와 같은 길로 간다.
        self.nav_go("점검")

    # ── 동작 ──
    def set_mode(self, m):
        self.mode = m
        # 접힌 띠에서 비교로 오면 왼쪽에 고를 것이 생긴다 — 스스로 펼친다.
        # 「무엇을 잠그면 이미 그 안에 있는 사람을 꺼내는 길을 같이 만든다」(2026-09-01).
        if self.side_lock_why():
            self.side_open = True
        self.rebuild()
        reveal(getattr(self, "_center_w", None))   # 보기 갈래(스냅샷·다이나믹·비교)

    def set_axis(self, a):
        self.compare_axis = a
        self.rebuild()
        reveal(getattr(self, "_center_w", None))   # 앱 2.3 — 비교 축

    # ── PV·QV 곡선 (F1d) ──────────────────────────────────────────────
    def curve_case(self):
        """곡선을 그릴 케이스 — **지금 화면의 조건이 전부 얹힌 것**.

        조류계산을 돌렸는지와 무관하다(아직 계산 안 한 `changes` 까지 얹는다).
        곡선은 자기 실행이므로 "이 조건으로 계산" 을 먼저 누를 필요가 없다.
        """
        if self.base_case is None:
            return None
        want = self.applied + self.changes
        return SC.apply(self.base_case, want) if want else self.base_case

    def dynamic_why(self):
        """다이나믹으로 못 가는 까닭. 갈 수 있으면 빈 글자 (2026-09-01 전수 조사 ⑬).

        1시각짜리 계통에서 들어가면 **점 하나짜리 그래프**가 그려지고(x축은 눈금이
        2까지 난다) 아무 안내가 없었다 — 왜 선이 없는지 알 길이 없다.
        보여 줄 것이 없으므로 `PV·QV 곡선` 과 같이 **아예 못 들어가게** 막는다.
        """
        if self.sol is None:
            return ""
        if getattr(self.sol, "n_time", 0) <= 1:
            return "다이나믹은 여러 시각짜리 계통만 봅니다. 이 계통은 1시각짜리입니다."
        return ""

    def curve_why(self):
        """곡선을 못 그리면 그 까닭. 그릴 수 있으면 None."""
        case = self.curve_case()
        if case is None:
            return "계통 파일을 먼저 여십시오."
        try:
            return ENGINE.curve_refusal(case)
        except Exception as exc:                     # noqa: BLE001
            return f"확인할 수 없습니다 ({exc})."

    def _bus_list(self, text):
        out = []
        for part in (text or "").replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.append(int(float(part)))
            except ValueError:
                continue
        return out

    def curve_controls(self, v):
        c = self.c
        lb = QLabel("부하를 늘릴 버스")
        lb.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:600;")
        v.addWidget(lb)
        le = QLineEdit(self.curve_load)
        le.setPlaceholderText("비우면 부하가 있는 버스 전부")
        le.textChanged.connect(lambda t: setattr(self, "curve_load", t))
        v.addWidget(le)
        n = QLabel("여기에 적은 버스의 부하만 함께 늘립니다")
        n.setWordWrap(True)
        n.setStyleSheet(f"color:{c['muted']};font-size:12px;")
        v.addWidget(n)
        v.addSpacing(10)

        lb2 = QLabel("곡선을 그릴 버스")
        lb2.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:600;")
        v.addWidget(lb2)
        le2 = QLineEdit(self.curve_pick)
        le2.setPlaceholderText("비우면 늘린 버스와 같게 (최대 8개)")
        le2.textChanged.connect(self.set_curve_pick)
        v.addWidget(le2)
        v.addSpacing(10)

        lb3 = QLabel("가로축")
        lb3.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:600;")
        v.addWidget(lb3)
        seg = QFrame()
        seg.setObjectName("segwrap")
        seg.setStyleSheet(
            f"#segwrap {{ background:{c['bg']};border:1px solid {c['border']};"
            f"border-radius:8px; }}")
        sh = QHBoxLayout(seg)
        sh.setContentsMargins(3, 3, 3, 3)
        sh.setSpacing(3)
        for key, name in (("MW", "합계 부하"), ("lambda", "배수 λ")):
            b = QPushButton(name)
            b.setObjectName("seg_on" if self.curve_x == key else "seg_off")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, x=key: self.set_curve_x(x))
            sh.addWidget(b)
        v.addWidget(seg)
        v.addSpacing(14)

        # 🚨 **못 그리는 계통이면 잠근다** (2026-08-31 전수 조사).
        #    AC/DC 혼합 케이스에서 오른쪽은 "곡선을 그릴 수 없습니다" 라고 말하는데
        #    이 단추만 파랗게 살아 있었고, 눌러도 **아무 일도 안 났다**(경고창도 없다).
        #    까닭은 `curve_why()` 가 이미 알고 있으니 그대로 풍선말로 붙인다.
        why = self.curve_why()
        run = QPushButton("곡선 그리기" if not self.curve_busy else "그리는 중…")
        run.setObjectName("primary")
        run.setEnabled(not self.curve_busy and not why)
        if why:
            run.setToolTip(why)
        run.clicked.connect(self.run_curve)
        v.addWidget(run)
        n2 = QLabel("버스가 많으면 몇 분 걸립니다")
        n2.setWordWrap(True)
        n2.setStyleSheet(f"color:{c['muted']};font-size:12px;")
        v.addWidget(n2)

    def set_curve_pick(self, t):
        self.curve_pick = t
        if self.cur is not None:
            self.rebuild()          # 이미 그린 곡선이면 다시 계산하지 않고 골라 보기만
            reveal(getattr(self, "_center_w", None))   # 앱 2.3 — 곡선 버스

    def set_curve_x(self, x):
        self.curve_x = x
        self.rebuild()
        reveal(getattr(self, "_center_w", None))   # 앱 2.3 — 곡선 가로축

    def set_task(self, t):
        self.task = t
        if self.side_lock_why():        # 곡선 입력이 왼쪽에 있다 — 접혀 있으면 편다
            self.side_open = True
        self.rebuild()
        reveal(getattr(self, "_center_w", None))   # 할 일 갈래(조류계산·PV·QV 곡선)

    def run_curve(self):
        case = self.curve_case()
        if case is None or self.curve_busy:
            return
        if self.curve_why():        # 못 그리는 계통 — 단추도 잠겨 있지만 여기서도 막는다
            return
        self.curve_busy = True
        self.curve_err = ""
        self.rebuild()
        reveal(getattr(self, "_center_w", None))   # 앱 2.3 — 고리 화면으로 바뀔 때
        self._cthread = CurveThread(case, self._bus_list(self.curve_load),
                                    self._bus_list(self.curve_pick))
        self._cthread.done.connect(self._curve_done)
        self._cthread.failed.connect(self._curve_failed)
        self._cthread.engine_missing.connect(self._curve_failed)
        self._cthread.start()

    def _curve_done(self, cur):
        self.curve_busy = False
        self.cur = cur
        self.curve_err = ""
        self.rebuild()
        reveal(getattr(self, "_center_w", None))   # 곡선 다 그림

    def _curve_failed(self, msg):
        self.curve_busy = False
        self.curve_err = msg
        snap = snap_central(self)   # 앱 2.3 — 실패 화면으로 바뀔 때 옛 화면이 옅어진다
        self.rebuild()
        crossfade_from(self, snap, lambda: None, self.centralWidget())

    def curve_page(self):
        c = self.c
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(11)

        why = self.curve_why()
        if why:
            v.addWidget(charts.NoData("곡선을 그릴 수 없습니다", why, c))
            return w
        if self.curve_err:
            v.addWidget(charts.NoData("곡선 실패", self.curve_err, c))
            return w
        if self.curve_busy:
            # 앱 2.3 — 조류계산 창과 같은 출렁이는 고리(`OrbRing`)를 띄운다
            v.addStretch(1)
            v.addWidget(OrbRing(self.dark, 120), 0, Qt.AlignHCenter)
            for txt, css in (("곡선을 그리는 중입니다…", f"color:{c['text']};font-size:15px;font-weight:600;"),
                             ("부하를 조금씩 올리며 더는 안 풀리는 곳까지 갑니다.",
                              f"color:{c['muted']};font-size:13px;")):
                lab = QLabel(txt)
                lab.setAlignment(Qt.AlignCenter)
                lab.setStyleSheet(css)
                v.addWidget(lab)
            v.addStretch(1)
            return w
        if self.cur is None:
            v.addWidget(charts.NoData(
                "왼쪽에서 [곡선 그리기] 를 누르십시오",
                "부하를 늘려 가며 전압이 무너지는 지점(코 끝점)을 찾습니다.", c))
            return w

        v.addWidget(self.curve_summary())
        split = _GripSplitter(Qt.Vertical, c)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(12)
        pick = self._bus_list(self.curve_pick)
        split.setHandleWidth(14)
        for chart_w in (charts.curve_chart(c, self.cur, pick, self.curve_x),
                        charts.curve_q_chart(c, self.cur, self.curve_x)):
            card = GlassCard(c, self.dark, radius=16, tint=(0.58, 0.38))
            cv = QVBoxLayout(card)
            cv.setContentsMargins(10, 10, 10, 10)
            cv.addWidget(chart_w)
            float_panel(card, self.dark)
            split.addWidget(card)
        split.setSizes([540, 440])      # 2026-11-15 — 맨 위 입력 카드만큼 아래 그래프가 눌려 세로축 이름이 잘렸다
        v.addWidget(split, 1)
        return w

    def curve_summary(self):
        """코 끝점 한 줄 요약 — 곡선에서 사람이 실제로 가져가는 숫자."""
        c = self.c
        cur = self.cur
        card = Card(c)          # Card 는 이미 세로 layout 을 갖고 있다 — 그 안에 넣는다
        h = QHBoxLayout()
        h.setContentsMargins(2, 0, 2, 0)
        h.setSpacing(26)
        card.v.addLayout(h)

        base = cur.load_MW[0] if cur.load_MW.size else 0.0
        room = cur.nose_MW - base
        items = [
            ("지금 부하", f"{base:,.1f} MW"),
            ("버틸 수 있는 부하", f"{cur.nose_MW:,.1f} MW"),
            ("남은 여유", f"{room:,.1f} MW  ({cur.lam_crit * 100:.1f} %)"),
            ("코 끝점 최저 전압", f"{float(cur.v[:, min(cur.nose, cur.v.shape[1]-1)].min()):.4f} p.u."),
        ]
        for name, val in items:
            box = QVBoxLayout()
            box.setSpacing(2)
            k = QLabel(name)
            k.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            val_l = QLabel(val.split("  (")[0])
            val_l.setStyleSheet(f"color:{c['text']};font-size:26px;font-weight:700;")
            box.addWidget(k)
            box.addWidget(val_l)
            if name == "남은 여유":
                bar = QProgressBar()
                bar.setRange(0, 1000)
                bar.setValue(int(min(1.0, cur.lam_crit) * 1000))
                bar.setTextVisible(False)
                bar.setFixedHeight(6)
                bar.setStyleSheet(f"QProgressBar {{ background:{c['hair']}; border:none; border-radius:3px; }}"
                                  f"QProgressBar::chunk {{ background:{c['ok']}; border-radius:3px; }}")
                box.addWidget(bar)
                pct = QLabel(f"지금 부하의 {cur.lam_crit * 100:.1f} % 만큼 더")
                pct.setStyleSheet(f"color:{c['muted']};font-size:11px;")
                box.addWidget(pct)
            h.addLayout(box)
        h.addStretch(1)

        if cur.switched.size:
            names = ", ".join(str(int(b)) for b in cur.switched[:6])
            more = "…" if cur.switched.size > 6 else ""
            note = QLabel(f"무효출력 한계에 걸린 발전기 {cur.switched.size}대\n"
                          f"버스 {names}{more}")
            _w = QColor(c["warn"])
            note.setStyleSheet(f"color:{c['warn']};font-size:12px;font-weight:600;"
                               f"background:rgba({_w.red()},{_w.green()},{_w.blue()},0.10);"
                               f"border-radius:10px;padding:8px 12px;")
            h.addWidget(note)
        return card

    def set_targets(self, t):
        self.compare_targets = t

    def toggle_item(self, name, state):
        if state:
            self.picked.add(name)
        else:
            self.picked.discard(name)
        self.rebuild()

    def set_numbers(self, v):
        self.numbers = v
        self.numbers_auto = False        # 사용자가 직접 골랐다 — 자동이 아니다
        # ⚠️ **이유도 함께 지운다.** 안 지우면 직접 접었는데도 앞서 자동으로 접혔던
        #    이유가 그대로 남아 *"계통을 바꿔 계산해서…"* 같은 남의 문구를 달게 된다
        #    (접힘 → 펼침 → 직접 접기 순서에서 실제로 그렇게 된다).
        self.numbers_why = ""
        if not v:
            # 직접 펼쳤다 ⇒ 이 케이스에서는 **더 이상 자동으로 접지 않는다**.
            # (조건을 바꿀 때마다 도로 접히면 못 쓴다)
            self.graph_kept = True
            # 🚨 **적어 둔 자리를 버린다.** 안 버리면 접히기 전의 「표 66%」 가 그대로
            #    되살아나 그래프가 최소 높이만 받는다 — 펼쳐 놓고도 못 읽는 꼴이 된다.
            if isinstance(self.split_sizes, dict):
                self.split_sizes.pop(self._split_slot(), None)
        # 🍎 접거나 펼치면 그래프 자리가 통째로 바뀐다 — 딱 끊기지 않게 (2026-09-08 사용자:
        #    *"그래프 펼치고 접는것도 애플처럼 모션 넣고"*). 처음엔 가운데 판만 밝아지게
        #    했는데(`fade_in`), 다시 그리는 동안 빈 판이 먼저 보여 끊겨 보였다(2026-11-01
        #    사용자 「그래프 접기 눌렀을 때도 애니메이션」). 테마 전환처럼 **옛 화면이 새
        #    화면 위에서 옅어지게** 바꾼다.
        snap = snap_central(self)
        self.rebuild()
        crossfade_from(self, snap, lambda: play_charts(self.centralWidget()), self.centralWidget())

    def toggle_theme(self):
        # 앱 2.3 C — 창 전체가 옛 테마에서 새 테마로 번진다(가운데 판만 밝아지던 것을 바꿈)
        snap = snap_central(self)
        self.dark = not self.dark
        self.rebuild()
        crossfade_from(self, snap, lambda: None, self.centralWidget())

    def do_import(self):
        # 파일 고르기 창이 처음 보여 줄 자리. 저장소의 검증용 케이스 폴더가 있으면 거기서
        # 시작한다(뼈대에서는 케이스가 널려 있던 v14 폴더였다).
        cases = paths.cases_dir()
        start = str(cases if cases.is_dir() else Path.home())

        # 🚨 **형식을 먼저 묻는다** (2026-09-08 점검 i05·i07). 자세한 까닭은
        #    `OpenDialog` 주석 — 요는 MatACDC 가 `.m` 두 파일이라 확장자로는 못 가른다.
        dlg = OpenDialog(self, self.c)
        if dlg.exec() != QDialog.Accepted or not dlg.picked:
            return
        kind = dlg.picked

        if kind == "matacdc":
            self._open_matacdc(start)
            return

        patt = {"xlsx": "UNIGRID 케이스 (*.xlsx *.xls)",
                "m":    "MATPOWER 케이스 (*.m)",
                "raw":  "PSS/E 계통 (*.raw *.RAW)"}[kind]
        path, _ = QFileDialog.getOpenFileName(self, "계통 파일 선택", start, patt)
        if not path:
            return
        if load_case is None:
            QMessageBox.warning(
                self, "불러오기",
                "케이스 읽기 모듈(load_case)을 불러오지 못했습니다.\n\n"
                f"원인 — {_LOAD_CASE_ERR or '알 수 없음'}\n\n"
                "필요한 것이 빠진 채로 앱이 만들어졌습니다. 만든 쪽에서\n"
                "`pip install -r requirements.txt` 뒤에 다시 만들어야 합니다.")
            return

        self._start_solve(path)

    def _open_matacdc(self, start):
        """MatACDC 계통을 **읽어서 바로 푼다** (2026-09-08 i05).

        「엑셀로 만들기」(`ConvertDialog._pick`)는 같은 두 파일을 읽어 **엑셀로
        저장**한다. 여기는 저장 없이 그대로 푸는 길 — 계산만 하려는 사람이
        엑셀을 한 번 거칠 까닭이 없다.
        """
        if QMessageBox.question(
                self, "파일을 두 개 고릅니다",
                "MatACDC 계통은 파일이 둘로 나뉘어 있습니다.\n\n"
                "    첫 번째 — AC 계통 (MATPOWER, bus·gen·branch)\n"
                "    두 번째 — DC 계통 (MatACDC, busdc·convdc·branchdc)\n\n"
                "이 순서로 고르셔야 합니다. 둘 다 확장자가 .m 이라\n"
                "바꿔 고르면 읽지 못합니다.\n\n계속할까요?",
                QMessageBox.Ok | QMessageBox.Cancel) != QMessageBox.Ok:
            return
        ac, _ = QFileDialog.getOpenFileName(
            self, "1/2 — 먼저 AC 계통 파일 (MATPOWER .m)", start, "MATPOWER 케이스 (*.m)")
        if not ac:
            return
        dc, _ = QFileDialog.getOpenFileName(
            self, "2/2 — 이제 DC 계통 파일 (MatACDC .m)", str(Path(ac).parent),
            "MatACDC 케이스 (*.m)")
        if not dc:
            return
        try:
            import unigrid_convert
            case = unigrid_convert.matacdc_to_case(ac, dc)
        except Exception as exc:                       # noqa: BLE001
            QMessageBox.warning(self, "읽지 못했습니다",
                                f"MatACDC 케이스를 읽지 못했습니다.\n\n{exc}")
            return
        # ⚠️ `case` 를 직접 넘기므로 `_start_solve` 가 **새 파일인 줄 모른다** —
        #    그 갈래는 `case is None` 일 때만 도는데, 그러면 앞 계통의 「바꾼 것」·
        #    곡선이 남아 화면과 어긋난다. 새 파일이라고 알려 준다.
        self._start_solve(ac, case=case, new_file=True)

    def _start_solve(self, path, case=None, method=None, new_file=False):
        # 🚨 **다른 파일**을 열 때는 아직 계산 안 한 "바꾼 것"을 버린다 (2026-08-12 확인).
        #    안 버리면 `_solved` 의 원본 갱신 분기(`not self.changes`)가 건너뛰어져
        #    **화면은 새 계통인데 base_case·시나리오·곡선은 앞 계통 것**으로 남는다
        #    (case14 에서 선로를 끈 채 case118 을 여니 화면 118버스 / base_case case14).
        #    같은 파일을 다시 푸는 것([이 조건으로 계산]·다시 풀기)에는 손대지 않는다 —
        #    거기서 지우면 사용자가 방금 한 편집이 사라진다.
        if new_file or (case is None
                        and getattr(self, "_last_path", None) not in (None, path)):
            self.changes = []
            self.cur = None
            self.curve_err = ""
        self._last_path = path
        if method is None:
            method = getattr(self, "solver", "nr")
        self.solver = method
        # 앱 2.3 — 오가는 막대 대신 출렁이는 빛 고리(`OrbRing`)
        self.prog = SolvingDialog(self, self.c, self.dark)
        self.prog.show()

        self.thread = SolveThread(path, case, method)
        self.thread.done.connect(self._solved)
        self.thread.failed.connect(self._solve_failed)
        self.thread.engine_missing.connect(self._engine_missing)
        self.thread.start()

    def _solved(self, sol):
        if getattr(self, "prog", None) is not None:
            self.prog.close()
        fresh_file = False
        # 조건을 안 바꾸고 푼 것이면 이 케이스가 **원본**이다 (바꿔서 푼 것은 원본이 아니다).
        loaded = getattr(getattr(self, "thread", None), "loaded_case", None)
        pending = getattr(self, "_pending", None)
        if pending:
            # [이 조건으로 계산] 으로 푼 것 — 시나리오 한 줄로 담고 바꾼 목록을 비운다
            self.book.add(self.base_case, pending, solution=sol,
                          name=self._new_name(pending, sol))
            self.applied = list(pending)      # 이제 이것이 화면의 조건이다
            self.changes = []
            self._pending = None
            # 🚨 **계통을 바꿔 계산하면 그래프를 접고 표를 넓게 연다** (2026-08-15 사용자 확정).
            #    계통을 고칠 때 눈이 가는 것은 표인데, 그래프가 자리를 크게 먹어 표가
            #    한두 줄로 눌렸다(사용자: *"아래 표가 너무 작아서 보기 힘들다"*).
            #    보고 싶으면 [그래프 펼치기] 를 누르면 되고, 그때는 표가 도로 줄어든다.
            #    ⚠️ **한 번이라도 직접 펼쳤으면 다시 안 접는다** — 조건 하나 바꿀 때마다
            #       도로 접히면 못 쓴다(큰 계통 자동 접기에서 정한 것과 같은 이유, 2026-08-06).
            if not self.graph_kept:
                self.numbers = True
                self.numbers_auto = True
                self.numbers_why = "changed"
        elif loaded is not None and not self.changes:
            fresh_file = True
            self.base_case = loaded
            self.applied = []
            self.changes = []
            self.book = SC.Book()
            # 🚨 원본도 시각을 단다 — 「모든 시나리오에」 (2026-09-08 사용자 지시).
            #    파일을 막 열었으므로 `self.t` 는 아직 앞 계통 것일 수 있다 ⇒ 0 으로.
            self.t = 0
            self.book.add(loaded, [], solution=sol,
                          name=f"원본{' (1 H)' if int(getattr(sol, 'n_time', 1) or 1) > 1 else ''}")
            # 새 계통을 열면 곡선은 버린다 — **앞 계통의 곡선**이라 지금 화면과 상관없다.
            self.cur = None
            self.curve_err = ""
            # 비교 대상도 같은 이유로 다시 잡는다. 기본값이 `3, 7, 12` 로 박혀 있어
            # 12버스 계통에서 AC 는 3 하나만 맞았다(7·12 는 DC 버스라 AC 표에 없다)
            # — 비교 화면이 선 하나로 열렸다. ⚠️ 여기(새 파일)에서만 한다.
            # 조건을 바꿔 다시 풀 때 하면 골라 놓은 것이 매번 날아간다.
            self._retarget = True
            # 🚨 큰 계통은 **그래프를 접은 채로 연다** (2026-08-06 사용자 확정).
            #    버스가 수천이면 점이 겹쳐 빨간 덩어리가 되어 읽을 수가 없다.
            #    보고 싶으면 [그래프 펼치기] 를 누르면 된다.
            #    조건을 바꿔 다시 풀 때는 손대지 않는다 — 사용자가 펼쳐 놓았으면 그대로 둔다.
            n_bus = int(sol.AC.shape[0]) + int(sol.DC.shape[0] if sol.DC.size else 0)
            self.numbers_auto = n_bus > BIG_BUSES
            self.numbers = self.numbers_auto
            self.numbers_why = "big" if self.numbers_auto else ""
            self.graph_kept = False       # 새 계통 — 「직접 펼쳤다」 기억도 새로
            # 정렬 기억도 새로 (2026-08-18). 계통이 달라지면 열 구성부터 달라질 수
            # 있고(AC 단독 ↔ AC/DC), 앞 계통을 보던 눈이 새 계통에 그대로 걸려 있으면
            # 파일을 열자마자 영문 모를 순서로 늘어서 있다. 위 `graph_kept` 와 같은 계열.
            self.sort_by = {}
            # 계통도 배율도 새로 — 버스 수가 달라지면 기호 크기가 자동으로 달라지는데
            # (`unit`), 앞 계통에서 올려 둔 배율이 얹히면 엉뚱한 크기로 뜬다.
            self.topo_zoom = 1.0
        # 해법 고르기가 볼 케이스 — 방금 푼 그것이다(조건을 바꿔 푼 것이면 그 케이스).
        # 이 값으로 `gs_refusal` 을 물어 Gauss-Seidel 을 흐리게 할지 정한다 (2026-08-12, G8).
        self._case_for_solver = (getattr(getattr(self, "thread", None), "case", None)
                                 or loaded or getattr(self, "base_case", None))
        self.sol = sol
        if getattr(self, "_retarget", False):
            self._retarget = False
            self.compare_targets = ", ".join(
                v for _, v in self.target_options()[:3])
        # 🚨 곡선은 **AC 단독 계통에서만** 그린다(2026-08-12 사용자 확정 — 넓히지 않는다).
        #    곡선 화면에 있는 채로 AC/DC 파일을 열면 갈래가 곡선에 머물러 있는데
        #    그 버튼은 흐려져 있어 **죽은 화면에 앉게 된다** ⇒ 조류계산으로 되돌린다.
        if self.task == "PV·QV 곡선" and self.curve_why():
            self.task = "조류계산"
            self.cur = None
        # 🚨 조건만 바꿔 다시 푼 것이면 **보던 시각을 지킨다** (2026-09-08).
        #    여태 풀 때마다 0 으로 돌려서, 5 H 를 보다가 선로 하나 끄고 다시 풀면
        #    화면이 1 H 로 튕겼다 — 24시각 계통에서 조건을 견주려면 같은 시각을
        #    봐야 한다. 시나리오 이름에 담을 때의 시각이 붙게 되면서(같은 날)
        #    이름은 `(5 H)` 인데 화면은 1 H 인 어긋남이 눈에 띄어 드러났다.
        #    새 파일을 열 때는 그대로 0 이다. `bus_row`·`show_violations` 는 안 건드린다.
        n_t_new = int(getattr(sol, "n_time", 1) or 1)
        self.t = 0 if fresh_file else min(max(int(self.t), 0), n_t_new - 1)
        self.bus_row = 0
        self.show_violations = False      # 새 케이스는 위반 보기 꺼진 채로 시작
        self.case = (Path(sol.case_name).name or "case",
                     f"{sol.mode_name} · AC {sol.AC.shape[0]} / DC {sol.DC.shape[0]}")
        self.case_has_vsc = sol.VSC_bus is not None and sol.VSC_bus.size > 0
        self.vsc_ideal = getattr(sol, "vsc_ideal", None)
        save_recent(str(getattr(self, "_last_path", sol.case_name)), self.case[1])
        if not self.case_has_vsc:
            self.show_vsc = False
        # 앱 2.3 B — 그래프가 그려지며 나타난다. 버스가 많으면 끈다(점이 많아 느려진다).
        # ponytail: 문턱 600 버스는 어림값 — 큰 계통에서 느리면 낮춘다.
        charts.SERIES_ANIM = (sol.AC.shape[0] + sol.DC.shape[0]) <= 600
        try:
            self.rebuild()
        finally:
            charts.SERIES_ANIM = False
        self._rise_result()                       # 계산이 끝나 화면이 처음 뜰 때

    def _fade_graph(self):
        """앱 2.3 — 그래프만 바뀌는 조작: 그래프 판의 지금 탭만 밝아진다(표는 그대로)."""
        gt = next(iter(self.findChildren(GlassTabs)), None)
        pg = gt.currentWidget() if gt is not None else getattr(self, "_center_w", None)
        if not play_charts(pg):
            fade_in(pg)

    def _fade_table(self):
        """앱 2.3 — 표만 바뀌는 조작(열 고르기): 표 판의 지금 탭만 밝아진다."""
        tt = getattr(self, "_tabs", None)
        fade_in(tt.currentWidget() if tt is not None else getattr(self, "_center_w", None))

    def _rise_result(self):
        """앱 2.3 A — 계산이 끝나 결과가 처음 뜰 때 그래프 판 → 표 판 차례로 나타난다.

        판(`float_panel`)에는 그림자 효과가 걸려 있어 겹칠 수 없으므로 판 **안의 내용**에 건다.
        """
        gt = next(iter(self.findChildren(GlassTabs)), None)
        tt = getattr(self, "_tabs", None)
        targets = [w for w in (gt.currentWidget() if gt else None,
                               tt.currentWidget() if tt else None) if w is not None]
        if not targets:
            reveal(getattr(self, "_center_w", None))
            return
        for i, w in enumerate(targets):
            fade_in(w, ms=260, delay=i * 90)
        if gt is not None:
            play_charts(gt.currentWidget())       # 그래프는 제 움직임으로 그려지며

    def _when_tag(self, sol=None) -> str:
        """시나리오 이름에 붙일 시각 꼬리표 — **여러 시각짜리 계통에서만** (2026-09-08).

        한 시각짜리면 빈 문자열이라 이름이 예전 그대로다.
        담을 때의 «지금 보는 시각» 을 쓴다 — 계통 변경 자체는 모든 시각에 함께
        걸리지만, 그 시나리오를 만들며 **무엇을 보고 있었나**가 목록에서 갈린다.
        """
        s = sol if sol is not None else getattr(self, "sol", None)
        n_t = int(getattr(s, "n_time", 1) or 1)
        if n_t <= 1:
            return ""
        return f"{min(max(int(self.t), 0), n_t - 1) + 1} H"

    def _new_name(self, pending, sol=None):
        """시나리오 이름 — 이번에 새로 얹은 것으로 짓고, 없으면 전체로."""
        fresh = getattr(self, "_pending_new", None)
        self._pending_new = None
        return SC.auto_name(self.base_case, fresh if fresh else pending,
                            when=self._when_tag(sol))

    # 🚨 **MATLAB 속사정을 첫 화면에 쏟지 않는다** (2026-09-08 점검 i37·i39).
    #    여태 `msg` 를 통째로 붙여서, 선로 하나 껐다가 안 풀리면 이런 것이 떴다 —
    #        File /Users/…/MatlabRuntimeCache/R2024b/unigri31/…/solve_ACDC_newton_aug_v7.m,
    #        line 1390, in solve_ACDC_newton_aug_v7
    #    쓰는 사람에게는 파일 경로도 줄 번호도 할 일이 없다. **왜 안 풀렸나**와
    #    **다음에 무엇을 해 볼까**만 보이고, 속사정은 [자세히] 안에 접어 둔다.
    _DIVERGE_TIP = (
        "다음을 해 볼 수 있습니다.\n"
        "· 부하 배율을 낮춘다\n"
        "· 전압을 잡는 변환기(DC Control Mode = 2)는 끄지 않는다\n"
        "   — 끄면 DC 망에 기준이 없어져 반드시 발산한다\n"
        "· 지고 있던 몫이 큰 선로·변환기일수록 끄면 발산하기 쉽다\n"
        "· 조건을 하나씩만 바꿔 본다 — 둘을 겹치면 여유가 금세 없어진다")

    @staticmethod
    def _fail_parts(msg: str) -> tuple[str, str]:
        """대화상자 본문과 [자세히] 안에 접을 것으로 가른다.

        `app_engine._fail_message` 가 「…실패 — 이유\n\n(자세히: 속사정)」 꼴로 만든다.
        그 함수는 **안 건드린다** — 검사 두 건이 「조류계산 실패」 글자를 본다.
        """
        m = re.search(r"\n\n\(자세히:\s*(.*?)\)\s*$", msg or "", re.S)
        if not m:
            return (msg or "").strip(), ""
        return msg[:m.start()].strip(), m.group(1).strip()

    def _fail_box(self, title, lead, msg, icon=QMessageBox.Warning):
        body, detail = self._fail_parts(msg)
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(lead)
        info = body
        if "발산" in body or "수렴" in body:
            info = f"{body}\n\n{self._DIVERGE_TIP}"
        box.setInformativeText(info)
        if detail:
            box.setDetailedText(detail)      # 눌러야 보인다
        # 🚨 Qt 기본 단추 글자가 영어로 나온다 — 한국어 번역이 안 실려 있다.
        #    「OK」·「Show Details…」 를 우리말로 바꾼다.
        box.setStandardButtons(QMessageBox.Close)
        box.button(QMessageBox.Close).setText("닫기")
        for b in box.buttons():
            if box.buttonRole(b) != QMessageBox.ActionRole:
                continue
            b.setText("자세히 보기")
            # ⚠️ 펼칠 때마다 Qt 가 "Hide Details…" 로 **되돌린다** — 누른 직후
            #    한 박자 뒤에 다시 덮는다(그 자리에서 세우면 Qt 가 나중에 이긴다).
            def _relabel(btn=b):
                btn.setText("자세히 감추기" if "Hide" in btn.text()
                            else "자세히 보기")
            b.clicked.connect(
                lambda _=False, f=_relabel: QTimer.singleShot(0, f))
        box.exec()

    def _solve_failed(self, msg):
        if getattr(self, "prog", None) is not None:
            self.prog.close()
        pending = getattr(self, "_pending", None)
        if pending:
            # 조건을 바꿔 풀다가 안 풀린 것 — **시나리오는 살려 둔다.**
            # 무엇을 바꿨는지가 목록에 남아야 다음 판단을 할 수 있다(PDR §4.3).
            # 화면은 그대로 두므로 직전 결과가 지워지지 않는다.
            self.book.add(self.base_case, pending, error=msg,
                          name=self._new_name(pending))
            self.changes = []          # applied 는 그대로 — 화면은 직전 결과 그대로다
            self._pending = None
            snap = snap_central(self)   # 앱 2.3 — 실패 화면으로 바뀔 때 옛 화면이 옅어진다
            self.rebuild()
            crossfade_from(self, snap, lambda: None, self.centralWidget())
            self._fail_box(
                "안 풀렸습니다",
                f"{SC.describe(pending)} — 이 조건으로는 답을 찾지 못했습니다.\n"
                f"시나리오 목록에 '안 풀림' 으로 남겨 두었고, 화면은 그대로 둡니다.",
                msg)
            return
        self._fail_box("계산 실패", "계산을 마치지 못했습니다.", msg,
                       icon=QMessageBox.Critical)

    def _engine_missing(self, msg):
        """계산 엔진을 못 찾았을 때 — 어디를 찾아봤는지까지 담긴 안내를 띄운다.

        안내문이 "[직접 고르기] 로 알려 주세요" 라고 말하므로 **그 버튼이 실제로 있어야 한다.**
        고른 자리는 `engine_path.remember()` 가 기억하므로 다음부터는 묻지 않는다.
        """
        if getattr(self, "prog", None) is not None:
            self.prog.close()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("계산 엔진을 찾지 못했습니다")
        box.setText(msg[:2000])
        pick = box.addButton("직접 고르기…", QMessageBox.ActionRole)
        box.addButton("닫기", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is pick:
            self._pick_engine()

    def _pick_engine(self):
        """mwpython 자리를 직접 고른다. 쓸 수 있는 자리면 기억하고 다시 계산한다."""
        start = "/Applications"
        path, _ = QFileDialog.getOpenFileName(
            self, "mwpython 자리 고르기 (보통 <설치자리>/bin/mwpython)", start)
        if not path:
            return
        p = Path(path)
        if p.name != "mwpython":
            QMessageBox.warning(
                self, "다시 골라 주세요",
                f"고른 파일 이름이 'mwpython' 이 아닙니다: {p.name}\n"
                "보통 <MATLAB 또는 Runtime 설치자리>/bin/mwpython 입니다.")
            return
        if not os.access(p, os.X_OK):
            QMessageBox.warning(self, "다시 골라 주세요",
                                f"이 파일은 실행할 수 없습니다:\n{p}")
            return

        engine_path.remember(p)
        warn = engine_path.release_warning(p)
        QMessageBox.information(
            self, "자리를 기억했습니다",
            f"{p}\n\n다음부터는 묻지 않습니다."
            + (f"\n\n{warn}" if warn else ""))
        # 방금 고른 자리로 다시 풀어 본다 (계산 프로세스가 옛 자리로 떠 있을 수 있으니 정리하고)
        last = getattr(self, "_last_path", None)
        if last:
            ENGINE.shutdown()
            self._start_solve(last)

    def do_export(self):
        ExportDialog(self, self.c, self.mode, self.picked).exec()


def main():
    app = QApplication(sys.argv)
    w = Proto()
    # 🚨 **처음부터 화면에 꽉 채워 연다** (2026-08-19 사용자 확정).
    #    이 앱은 표·그래프·계통도를 한 화면에서 같이 보는 도구라 자리가 넓을수록 낫고,
    #    「표 고르기」 줄처럼 **넓으면 밀 일이 없어지는** 것도 있다.
    #    ⚠️ 맥 전체화면(메뉴 막대까지 숨기는 것)이 아니라 **최대화**다 —
    #      다른 창과 같이 쓸 수 있어야 한다.
    #    창을 되돌리면 위 `__init__` 의 `resize` 크기로 간다.
    w.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
