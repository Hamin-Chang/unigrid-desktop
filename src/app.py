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
import math
import random
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QTabWidget, QTableWidget, QTableWidgetItem,
    QComboBox, QSpinBox, QDialog, QCheckBox, QLineEdit, QButtonGroup,
    QHeaderView, QScrollArea, QSizePolicy, QSplitter, QFileDialog,
    QProgressDialog, QMessageBox, QInputDialog, QSlider,
)

import json
import app_engine as ENGINE
import engine_path
import charts
import exporter

# 케이스 읽기는 **이 저장소 안**에 있다 (2026-08-05 들여옴).
# 예전에는 옆 폴더의 공개 파이썬 패키지를 빌려 썼는데, 그 폴더는 이 맥에만 있어
# 남의 컴퓨터에서는 앱이 떠도 파일을 하나도 못 열었다 — 공개 배포가 안 되는 구조였다.
try:
    from load_case import load_case
except Exception:                      # 그래도 앱은 뜨게 (무엇이 없는지는 불러올 때 알린다)
    load_case = None

import scenario as SC          # 계통 조건 바꾸기 (PDR §7 2단계)


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
GRID_EDITABLE = {
    "AC_gen_dat": {2, 3, 4, 7},        # 운전모드 · P-f droop · Q-V droop · 지정전압
    "DC_gen_dat": {2, 3, 5},           # 운전모드 · P-Vdc droop · 지정전압
    "IC_dat": {2, 3, 4, 5, 6, 7, 8},   # AC/DC 제어모드 · droop 셋 · P·Q 동작점
    "DCDC_Conv_dat": {5, 6, 7, 9},     # droop 둘 · 동작점 · 운전모드
}

# 계통 데이터 탭에 보여 줄 표 (차례대로). 켜고 끌 수 있는 것이 앞에 온다.
GRID_TABLES = [
    ("AC_Line_dat", "AC 선로"), ("AC_gen_dat", "AC 발전기"),
    ("DC_Line_dat", "DC 선로"), ("DC_gen_dat", "DC 발전기"),
    ("IC_dat", "IC"), ("DCDC_Conv_dat", "DC/DC"),
    ("AC_Bus_dat", "AC 버스"), ("DC_Bus_dat", "DC 버스"),
]

RECENT_FILE = _HERE_RECENT = Path(__file__).resolve().parent / ".recent.json"


def load_recent() -> list:
    try:
        return json.loads(RECENT_FILE.read_text(encoding="utf-8"))[:6]
    except Exception:
        return []


def save_recent(path: str, info: str) -> None:
    items = [x for x in load_recent() if x.get("path") != path]
    items.insert(0, {"path": path, "info": info})
    try:
        RECENT_FILE.write_text(json.dumps(items[:6], ensure_ascii=False),
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

    def __init__(self, path, case=None):
        super().__init__()
        self.path = path
        self.case = case          # 있으면 이것을 푼다 (조건을 바꿔 다시 풀 때)
        self.loaded_case = None   # 파일에서 읽은 원본 — 창이 받아 들고 있는다

    def run(self):
        try:
            warm = ENGINE.solved_before()   # 첫 계산이면 준비 시간이 섞인다
            t0 = time.perf_counter()
            # 위험한 형태 거르기는 `load_case` 안으로 들어갔다 (2026-08-06)
            case = self.case if self.case is not None else load_case(self.path)
            self.loaded_case = case
            sol = ENGINE.solve(case)
            sol.seconds = time.perf_counter() - t0   # 엑셀 읽는 시간까지 포함
            sol.warm_start = warm
            self.done.emit(sol)
        except engine_path.EngineNotFound as exc:
            self.engine_missing.emit(str(exc))     # 안내문을 그대로 들고 있다
        except Exception as exc:
            self.failed.emit(str(exc))

# ─────────────────────────────────────────── 색
LIGHT = dict(
    bg="#eef1f5", surface="#ffffff", border="#d5dae2", text="#1b2430",
    muted="#6b7684", accent="#0b6ab8", accent_soft="#e3eefb",
    ok="#1a7f4b", warn="#c2570e", plot="#f7f9fc",
)
DARK = dict(
    bg="#161a20", surface="#1e242c", border="#333c47", text="#e6ebf2",
    muted="#95a1b1", accent="#4da3ff", accent_soft="#22303f",
    ok="#3ecf8e", warn="#e0873f", plot="#232a33",
)

MODES = ["스냅샷", "다이나믹", "비교"]

GRAPHS = {
    "스냅샷": [
        ("전압·위상", ["전압  [pu]  ·  x축 = 버스", "위상각  [deg]  ·  x축 = 버스"], "v"),
        ("조류 (P·Q)", ["유효전력 P  (3D)", "무효전력 Q  (3D)"], "h"),
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
        ("Bus", 1), ("VM[pu]", 1), ("Freq[pu]", 0), ("Angle[deg]", 1),
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


def col_index(cols, name):
    try:
        return cols.index(name)
    except ValueError:
        return -1


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
    keep = [c for c in ("VM[pu]", "Angle[deg]", "Gen_P[MW]", "Gen_Q[MVAR]",
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
    """탭 이름에서 건수를 뗀다 — "점검 (3)" · "계통 데이터 (2)" 는 같은 탭이다."""
    return text.split(" (")[0].strip()


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
    if show_vsc and sol.VSC_bus is not None and sol.VSC_bus.size:
        out.append(("VSC 버스", sol.cols("VSC_bus"), sol.VSC_bus))
    return out


def real_violations(sol, t):
    """전압 위반 · 과부하 · 변환기 한계를 결과에서 걸러낸다."""
    res = {}

    # 전압 위반 (AC · DC 둘 다 Vmin/Vmax 열을 갖고 있다)
    rows = []
    for which in ("AC", "DC"):
        arr = sol.at(which, t)
        if not arr.size:
            continue
        cols = sol.cols(which)
        iB, iV = col_index(cols, "Bus"), col_index(cols, "VM[pu]")
        iLo, iHi = col_index(cols, "Vmin[pu]"), col_index(cols, "Vmax[pu]")
        if min(iB, iV, iLo, iHi) < 0:
            continue
        for r in arr:
            v, lo, hi = r[iV], r[iLo], r[iHi]
            if v > hi:
                rows.append([f"{which} {int(r[iB])}", f"{v:.4f}",
                             f"Vmax {hi:.3f}", f"+{v - hi:.4f}"])
            elif v < lo:
                rows.append([f"{which} {int(r[iB])}", f"{v:.4f}",
                             f"Vmin {lo:.3f}", f"{v - lo:.4f}"])
    res["전압 위반"] = (["버스", "V[pu]", "한계", "초과량"], rows)

    # 과부하 선로
    rows = []
    arr = sol.at("Branch", t)
    if arr.size:
        cols = sol.cols("Branch")
        iF, iT = col_index(cols, "From"), col_index(cols, "To")
        iL = col_index(cols, "Loading[%]")
        iC = col_index(cols, "Capacity[MVA]")
        if min(iF, iT, iL) >= 0:
            for r in arr:
                if r[iL] > 100.0:
                    cap = f"{r[iC]:.1f}" if iC >= 0 else "—"
                    rows.append([str(int(r[iF])), str(int(r[iT])),
                                 f"{r[iL]:.1f}", cap])
    res["과부하 선로"] = (["From", "To", "Loading[%]", "용량[MVA]"], rows)

    # 변환기 한계 (0=한계 안 · 2=용량곡선 · 3=전류한계)
    rows = []
    label = {2: "용량곡선(S_N) 도달", 3: "전류한계 도달"}
    for i, m in enumerate(sol.IC_lim_mode or []):
        if int(m) in label:
            rows.append([f"변환기 {i + 1}", label[int(m)]])
    res["변환기 한계"] = (["변환기", "상태"], rows)

    # 발전기 한계 (2026-07-27) — 유효·무효를 따로 세고, 무효는 걸린 한계까지 밝힌다.
    res["발전기 한계"] = (GEN_LIMIT_COLS, gen_limit_rows(sol))
    return res


GEN_LIMIT_COLS = ["발전기", "항목", "걸린 한계", "출력", "한계값"]

# 발전기 한계 표의 종류 열 (1~4) → 화면에 쓸 이름
_GEN_KIND = {1: "AC", 2: "DC", 3: "AC", 4: "DC"}


def _fmt_num(x):
    """무한대·빈값은 '—' 로. 한계가 없는 발전기는 ±inf 로 온다.

    소수 2자리 — 용량 원(S_N)에 걸린 값은 0.8732 처럼 어중간해서
    1자리로는 출력과 한계값이 둘 다 '0.9' 로 보인다 (2026-07-28).
    """
    if x is None or not math.isfinite(float(x)):
        return "—"
    return f"{float(x):.2f}"


def gen_limit_rows(sol):
    """발전기 출력한계에 걸린 것만 골라 점검 탭 줄로 만든다.

    한 발전기가 유효·무효 둘 다 걸리면 두 줄이 된다 (한 줄에 뭉치면
    어느 쪽이 걸렸는지가 흐려진다).
    """
    rows = []
    tbl = getattr(sol, "gen_limit", None)
    if tbl is None or len(tbl) == 0:
        return rows

    for r in tbl:
        kind, bus = int(r[0]), int(r[1])
        name = f"{_GEN_KIND.get(kind, '?')} {bus}"

        sat_p = int(r[5])
        if sat_p:
            edge = "Pmax 상한" if sat_p > 0 else "Pmin 하한"
            limit = r[4] if sat_p > 0 else r[3]
            rows.append([name, "유효 P", edge, _fmt_num(r[2]), _fmt_num(limit)])

        sat_q = int(r[9])
        if sat_q:
            qsrc = int(r[10])
            if qsrc == 2:
                # "S_N" 은 논문에서 연계 변환기(IC)의 정격 기호($S^N_{VSC,c}$)라
                # 그대로 쓰면 헷갈린다 → 발전기 쪽임을 이름에 밝힌다 (2026-07-28).
                edge = "발전기 용량 원"
            else:
                edge = "Qmax 상한" if sat_q > 0 else "Qmin 하한"
            limit = r[8] if sat_q > 0 else r[7]
            rows.append([name, "무효 Q", edge, _fmt_num(r[6]), _fmt_num(limit)])

    return rows


def violation_count(viol=None):
    src = viol if viol is not None else VIOLATIONS
    return sum(len(rows) for _, rows in src.values())


COMPARE_ITEMS = [
    ("전압 크기", True), ("위상각", True),
    ("주파수", False), ("손실", False),      # False = 시간끼리 비교에서만
]


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


# ─────────────────────────────────────────── 조각
class _ClickLabel(QLabel):
    """두 번 누르면 알려 주는 라벨 (시나리오 이름 고치기용)."""

    double_clicked = Signal(object)

    def mouseDoubleClickEvent(self, ev):
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
        t.setStyleSheet(f"color:{c['text']};font-size:18px;font-weight:700;")
        v.addWidget(t)
        s = QLabel("계산만 하려면 이 창은 필요 없습니다 — 파일을 바로 열면 됩니다.\n"
                   "여기서 만든 엑셀에 DC 버스·변환기·24시간 부하를 직접 넣어\n"
                   "AC/DC 혼합 케이스를 만들 수 있습니다.")
        s.setStyleSheet(f"color:{c['muted']};font-size:13px;line-height:150%;")
        v.addWidget(s)
        s2 = QLabel("어떤 형식에서 만들까요?")
        s2.setStyleSheet(f"color:{c['text']};font-size:14px;font-weight:600;")
        v.addWidget(s2)
        for name, desc in [("MATPOWER  (.m)", "AC 계통"),
                           ("PSS/E  (.raw)", "AC 계통 · 3권선 포함"),
                           ("MatACDC", "AC/DC 혼합 계통")]:
            b = QPushButton(f"{name}\n{desc}")
            b.setMinimumHeight(64)
            b.clicked.connect(lambda _, n=name: self._pick(n))
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

    def _pick(self, name):
        d = QDialog(self)
        d.setWindowTitle("아직 만들지 않았습니다")
        d.setStyleSheet(self.styleSheet())
        v = QVBoxLayout(d)
        v.setContentsMargins(22, 20, 22, 20)
        lb = QLabel(f"여기서 '{name}' 파일 선택 창이 열립니다.\n"
                    "(이 기능은 아직 만들지 않았습니다 — PDR §7 3단계)")
        v.addWidget(lb)
        ok = QPushButton("확인")
        ok.clicked.connect(d.accept)
        v.addWidget(ok)
        d.exec()


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
        t.setStyleSheet(f"color:{c['text']};font-size:18px;font-weight:700;")
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

    def __init__(self, parent, c, mode, numbers_only, picked_items):
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
            t.setStyleSheet(f"color:{c['text']};font-size:18px;font-weight:700;")
            v.addWidget(t)
            n = QLabel("저장할 결과가 없습니다. 먼저 케이스를 불러와 계산하세요.")
            n.setStyleSheet(f"color:{c['muted']};font-size:14px;")
            v.addWidget(n)
        elif mode == "비교":
            t = QLabel("내보내기 — 비교 표만 (그림은 여기서 저장하지 않습니다)")
            t.setWordWrap(True)
            t.setStyleSheet(f"color:{c['text']};font-size:17px;font-weight:700;")
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
            t.setStyleSheet(f"color:{c['text']};font-size:18px;font-weight:700;")
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
                cb = QCheckBox(f"{tab}     {fname}.png / .pdf")
                cb.setChecked(not numbers_only)
                cb.setEnabled(not numbers_only)
                v.addWidget(cb)
                self.tabs.append((tab, cb))
            if numbers_only:
                w = QLabel("지금은 숫자 모드라 그림을 저장할 수 없습니다")
                w.setStyleSheet(f"color:{c['warn']};font-size:13px;")
                v.addWidget(w)

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


class Proto(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)     # 파일을 창에 끌어다 놓으면 바로 연다
        self.dropzone = None
        self.drop_label = None
        self.dark = False
        self.numbers = False
        self.mode = "스냅샷"
        self.compare_axis = "버스끼리"
        self.overlay = set()          # 겹쳐 볼 시나리오 (Book 안 자리 번호) — 비면 전부
        self.compare_targets = "3, 7, 12"
        self.picked = {"전압 크기"}
        self.case = ("ACDC_CIGRE_MVACMVDCLVDC.xlsx", "AC/DC 혼합 · AC 14 / DC 11")
        self.sol = None               # 실제 계산 결과 (없으면 화면 모양용 가짜값)
        self.t = 0                    # 보고 있는 시간대 (0부터)
        self.bus_row = 0              # 다이나믹에서 고른 버스 (행 번호)
        self.case_has_vsc = True      # AC-only 케이스면 False
        self.show_vsc = False
        self.show_violations = False  # 계통도 '위반 보기' 켜짐 여부
        self.graph_tab = 0            # 보고 있던 그래프 탭 (재생성 때 되돌리려고)
        # 아래쪽 표 탭도 같이 기억한다. **번호가 아니라 이름**으로 — 모드·VSC 표시에 따라
        # 탭 개수가 달라지고, 이름에도 건수가 붙는다("점검 (3)"·"계통 데이터 (2)").
        self.table_tab = "AC 결과"
        # ── 계통 조건 (PDR §7 2단계) ──
        # 원본 케이스는 읽고 나면 바뀌지 않는다. 그 위에 "바꾼 것" 목록만 얹는다.
        self.base_case = None         # 파일에서 읽은 원본 (scenario.apply 의 바탕)
        self.applied = []             # **지금 화면의 결과**를 만든 조건 (이미 계산된 것)
        self.changes = []             # 그 위에 얹었지만 **아직 계산 안 한** 것
        self.book = SC.Book()         # 담아 둔 시나리오
        self.grid_key = "AC_Line_dat" # 계통 데이터 탭에서 보고 있는 표
        # 부하 일괄 증감 슬라이더 — 끌고 있는 동안 화면을 다시 그리면 손잡이가 사라진다.
        # 그래서 놓았을 때(sliderReleased) 또는 잠깐 멈췄을 때만 반영한다.
        self._load_pending = 1.0
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.timeout.connect(lambda: self.scale_loads(self._load_pending))
        self.visible = {k: {n for n, d in v if d} for k, v in TABLE_SPECS.items()}
        self.split_sizes = None
        self.setWindowTitle("UNIGRID")
        self.resize(1440, 950)
        self.build()

    # ── 테마 ──
    @property
    def c(self):
        return DARK if self.dark else LIGHT

    def qss(self):
        c = self.c
        return f"""
        QMainWindow, QWidget, QDialog {{ background:{c['bg']}; color:{c['text']};
            font-family:'Apple SD Gothic Neo','Helvetica Neue',sans-serif; }}
        QLabel, QCheckBox {{ background:transparent; }}
        /* 툴팁 — 전용 규칙이 없으면 macOS 는 배경을 어둡게 그리는데 위 QWidget
           규칙이 글자색까지 어둡게 강제해 '어두운 글자+어두운 배경'으로 안 보였다
           (계통도 위반 요소 손말풍선이 빈 상자로 떴다). 배경·글자·테두리를
           카드와 같은 팔레트로 못 박아 라이트·다크 양쪽에서 읽히게 한다. */
        QToolTip {{ background:{c['surface']}; color:{c['text']};
            border:1px solid {c['border']}; padding:6px 9px; font-size:13px; }}
        #dropzone {{ background:{c['surface']}; border:2px dashed {c['border']};
            border-radius:14px; }}
        #card, #plot {{ background:{c['surface']};
            border:1px solid {c['border']}; border-radius:9px; }}
        #plot {{ background:{c['plot']}; }}
        #topbar {{ background:{c['surface']}; border-bottom:1px solid {c['border']}; }}
        #sidebar {{ background:{c['surface']}; border-right:1px solid {c['border']}; }}
        #statusbar {{ background:{c['surface']}; border-top:1px solid {c['border']}; }}
        QPushButton {{ background:{c['surface']}; color:{c['text']};
            border:1px solid {c['border']}; border-radius:7px;
            padding:10px 17px; font-size:14px; }}
        QPushButton:hover {{ border-color:{c['accent']}; }}
        QPushButton#primary {{ background:{c['accent']}; color:#ffffff;
            border:none; font-weight:600; }}
        QPushButton#seg_on {{ background:{c['accent']}; color:#ffffff;
            border:none; font-weight:700; font-size:14px;
            border-radius:8px; padding:8px 14px; }}
        QPushButton#seg_off {{ background:transparent; color:{c['muted']};
            border:none; font-size:14px; border-radius:8px; padding:8px 14px; }}
        QPushButton#seg_off:hover {{ background:{c['accent_soft']};
            color:{c['accent']}; }}
        QPushButton#accentline {{ border:1px solid {c['accent']};
            color:{c['accent']}; font-weight:600; }}
        QPushButton#accentline:hover {{ background:{c['accent_soft']}; }}
        QPushButton#link {{ background:transparent; border:none;
            color:{c['muted']}; font-size:13px; padding:4px 6px;
            text-decoration:underline; }}
        QPushButton#link:hover {{ color:{c['accent']}; }}
        QComboBox, QSpinBox, QLineEdit {{ background:{c['surface']}; color:{c['text']};
            border:1px solid {c['border']}; border-radius:6px;
            padding:9px 12px; font-size:16px; }}
        QTabWidget::pane {{ border:1px solid {c['border']}; border-radius:8px;
            background:{c['surface']}; top:-1px; }}
        QTabBar::tab {{ background:transparent; color:{c['muted']};
            padding:10px 18px; font-size:14px; border:none;
            margin-right:3px; min-width:96px; }}
        QTabBar::tab:selected {{ color:{c['accent']};
            border-bottom:2px solid {c['accent']}; font-weight:700; }}
        QTableWidget {{ background:{c['surface']}; border:none;
            gridline-color:{c['border']}; font-size:14px; }}
        QHeaderView::section {{ background:{c['bg']}; color:{c['muted']};
            border:none; border-bottom:1px solid {c['border']};
            padding:9px; font-size:14px; font-weight:600; }}
        QCheckBox {{ font-size:14px; color:{c['text']}; spacing:7px; }}
        QScrollArea {{ border:none; background:transparent; }}
        """

    # ── 전체 다시 그리기 ──
    def build(self):
        self.setStyleSheet(self.qss())
        # 화면을 갈아끼우면 옛 위젯 참조는 버린다 (지워진 위젯을 만지면 죽는다)
        self.dropzone = self.drop_label = self._tabs = None
        if self.sol is None:
            self.setCentralWidget(self.start_page())
            return
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.topbar())
        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(0)
        mid.addWidget(self.sidebar())
        mid.addWidget(self.center(), 1)
        v.addLayout(mid, 1)
        v.addWidget(self.statusbar())

    def rebuild(self):
        self.build()

    # ── 상단 ──
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
            f"color:{c['text']};font-size:23px;font-weight:800;letter-spacing:1.4px;")
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

        lb = QLabel("표시 모드")
        lb.setStyleSheet(f"color:{c['muted']};font-size:13px;")
        h.addWidget(lb)
        h.addSpacing(2)
        seg = QFrame()
        seg.setObjectName("segwrap")
        seg.setFixedHeight(40)
        seg.setStyleSheet(
            f"#segwrap {{ background:{c['bg']};border:1px solid {c['border']};"
            f"border-radius:10px; }}")
        sh = QHBoxLayout(seg)
        sh.setContentsMargins(4, 4, 4, 4)
        sh.setSpacing(4)
        for txt, val in [("숫자만", True), ("그림 포함", False)]:
            b = QPushButton(txt)
            b.setObjectName("seg_on" if self.numbers == val else "seg_off")
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumWidth(104)
            b.setToolTip("그래프를 그리지 않아 5~7배 빠릅니다" if val
                         else "모든 그래프를 그립니다")
            b.clicked.connect(lambda _, x=val: self.set_numbers(x))
            sh.addWidget(b)
        h.addWidget(seg)

        return bar

    # ── 좌측 ──
    def sidebar(self):
        c = self.c
        sb = QFrame()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(280)
        v = QVBoxLayout(sb)
        v.setContentsMargins(14, 16, 14, 14)
        v.setSpacing(8)

        v.addWidget(self.case_card())
        v.addSpacing(12)

        # 모드 3분할 — 가장 큰 선택이라 이름표를 붙인다
        ml = QLabel("보기")
        ml.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:700;")
        v.addWidget(ml)
        seg = QFrame()
        seg.setObjectName("segwrap")
        seg.setStyleSheet(
            f"#segwrap {{ background:{c['bg']};border:1px solid {c['border']};"
            f"border-radius:8px; }}")
        sh = QHBoxLayout(seg)
        sh.setContentsMargins(3, 3, 3, 3)
        sh.setSpacing(3)
        for m in MODES:
            b = QPushButton(m)
            b.setObjectName("seg_on" if self.mode == m else "seg_off")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, x=m: self.set_mode(x))
            sh.addWidget(b)
        v.addWidget(seg)
        v.addSpacing(12)

        if self.mode == "스냅샷":
            lb = QLabel("시간 선택")
            lb.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:700;")
            v.addWidget(lb)
            cb = QComboBox()
            n_t = self.sol.n_time if self.sol is not None else 24
            cb.addItems([f"{i} H" for i in range(1, n_t + 1)])
            cb.setCurrentIndex(min(self.t, n_t - 1))
            cb.currentIndexChanged.connect(self.set_time)
            v.addWidget(cb)
            n = QLabel("그래프와 표가 이 시간을 같이 따라갑니다")
            n.setWordWrap(True)
            n.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            v.addWidget(n)
            v.addSpacing(14)
            v.addWidget(self.freq_card())

        elif self.mode == "다이나믹":
            lb = QLabel("버스 선택")
            lb.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:700;")
            v.addWidget(lb)
            cb = QComboBox()
            if self.sol is not None and self.sol.AC.size:
                buses = [f"AC {int(b)}" for b in self.sol.AC[:, 0, 0]]
                if self.sol.DC.size:
                    buses += [f"DC {int(b)}" for b in self.sol.DC[:, 0, 0]]
            else:
                buses = [f"AC {i}" for i in range(1, 15)]
            cb.addItems(buses)
            cb.setCurrentIndex(min(self.bus_row, len(buses) - 1))
            cb.currentIndexChanged.connect(self.set_bus)
            v.addWidget(cb)
            n = QLabel("그래프와 표가 이 버스를 같이 따라갑니다")
            n.setWordWrap(True)
            n.setStyleSheet(f"color:{c['muted']};font-size:12px;")
            v.addWidget(n)

        else:  # 비교
            lb = QLabel("무엇끼리 비교")
            lb.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:700;")
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
                lb3.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:700;")
                v.addWidget(lb3)
                n3 = QLabel("위의 시나리오 목록에서 체크한 것을 겹쳐 그립니다.\n"
                            "전압·위상각은 x축이 버스, 주파수·손실은 x축이 시간입니다.")
                n3.setWordWrap(True)
                n3.setStyleSheet(f"color:{c['muted']};font-size:12px;")
                v.addWidget(n3)
                v.addStretch(1)
                return sb

            lb2 = QLabel("비교할 " + ("버스" if self.compare_axis == "버스끼리" else "시간"))
            lb2.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:700;")
            v.addWidget(lb2)
            le = QLineEdit(self.compare_targets)
            le.setPlaceholderText("예: 3, 7, 12   (최대 50개)")
            le.textChanged.connect(self.set_targets)
            v.addWidget(le)
            n = QLabel("최대 50개 · 한 그래프에 겹쳐 그립니다")
            n.setWordWrap(True)
            n.setStyleSheet(f"color:{c['muted']};font-size:13px;")
            v.addWidget(n)
            v.addSpacing(10)

            lb3 = QLabel("볼 항목")
            lb3.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:700;")
            v.addWidget(lb3)
            for name, always in COMPARE_ITEMS:
                usable = always or self.compare_axis == "시간끼리"
                cb = QCheckBox(name)
                cb.setChecked(name in self.picked and usable)
                cb.setEnabled(usable)
                cb.stateChanged.connect(
                    lambda st, n2=name: self.toggle_item(n2, st))
                v.addWidget(cb)
                if not usable:
                    w = QLabel("   시간끼리 비교에서만")
                    w.setStyleSheet(f"color:{c['warn']};font-size:12px;")
                    v.addWidget(w)
            # 비교 그림 저장은 위쪽 "내보내기"와 **따로** 둔다(사용자 요청).
            # 원본 앱도 비교는 별도 버튼이었다(ExportComparisonButtonPushed).
            # ⚠️ 이름을 sb 로 쓰면 안 된다 — 이 함수의 sb 는 사이드바 자체다.
            #    덮어쓰면 사이드바가 파이썬 참조를 잃고 사라진다(실제로 겪음).
            v.addSpacing(10)
            savebtn = QPushButton("이 비교 그림 저장  (PNG · PDF)")
            savebtn.clicked.connect(self.save_compare_figures)
            v.addWidget(savebtn)

        v.addStretch()
        return sb

    # ── 가운데 ──
    def center(self):
        c = self.c
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 14, 16, 12)
        v.setSpacing(11)

        if self.mode == "비교":
            # 겹쳐 보기 체크칸이 이 목록에 있다 — 비교 모드에서 오히려 더 필요하다
            sb = self.scenario_bar()
            if sb is not None:
                v.addWidget(sb)
            v.addWidget(self.compare_area(), 1)
            return w

        bar = self.change_bar()          # 바꾼 것이 있을 때만 나온다
        if bar is not None:
            v.addWidget(bar)
        sb = self.scenario_bar()         # 담아 둔 것이 있을 때만 나온다
        if sb is not None:
            v.addWidget(sb)

        split = QSplitter(Qt.Vertical)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(10)

        # ── 그래프 (숫자 모드면 접음) ──
        if not self.numbers:
            gt = QTabWidget()
            for name, plots, layout in GRAPHS[self.mode]:
                page = QWidget()
                lay = QHBoxLayout(page) if layout == "h" else QVBoxLayout(page)
                lay.setContentsMargins(10, 10, 10, 10)
                lay.setSpacing(9)
                for pname in plots:
                    # 시간과 버스를 둘 다 넘긴다 — 어느 쪽을 쓸지는 그래프가
                    # 이름(x축이 버스냐 시간이냐)을 보고 고른다.
                    # (한때 하나만 넘겨서 고른 버스가 아니라 늘 첫 버스를 그렸다)
                    real = charts.build(pname, c, self.sol, self.t, self.bus_row,
                                        self.show_violations, self.set_violations,
                                        self.show_line_profile)
                    lay.addWidget(real if real is not None else PlotBox(pname, c))
                gt.addTab(page, name)
            # 보고 있던 탭을 되살린다 — 위반 보기 토글 등이 rebuild() 로 화면을
            # 다시 만드는데, 안 되살리면 늘 0번(전압·위상)으로 튀어 버렸다
            # (토폴로지에서 토글을 누르면 전압 그래프로 넘어가던 버그).
            gt.setCurrentIndex(min(self.graph_tab, gt.count() - 1))
            gt.currentChanged.connect(
                lambda i: setattr(self, "graph_tab", int(i)))
            # 그래프가 낮으면 QtCharts 가 x축 글자를 "..." 로 줄여 버린다.
            # 두 개를 위아래로 쌓는 탭이 있으므로 넉넉히 잡아 준다.
            gt.setMinimumHeight(470)
            split.addWidget(gt)
        else:
            note = QFrame()
            note.setObjectName("card")
            note.setMaximumHeight(58)
            nv = QHBoxLayout(note)
            nv.setContentsMargins(16, 10, 16, 10)
            t = QLabel("숫자 모드 — 그래프를 접어 표를 넓게 씁니다  (약 5~7배 빠름)")
            t.setStyleSheet(f"color:{c['muted']};font-size:14px;")
            nv.addWidget(t)
            nv.addStretch()
            b = QPushButton("그래프 펼치기")
            b.clicked.connect(lambda: self.set_numbers(False))
            nv.addWidget(b)
            v.addWidget(note)

        # ── 표 ──
        tw = QWidget()
        tv = QVBoxLayout(tw)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(7)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addStretch()
        lab = QLabel("VSC 표")
        lab.setStyleSheet(f"color:{c['muted']};font-size:13px;")
        head.addWidget(lab)

        if not self.case_has_vsc:
            off = QLabel("  없음  ")
            off.setStyleSheet(
                f"background:{c['bg']};color:{c['muted']};border:1px solid "
                f"{c['border']};border-radius:7px;padding:5px 4px;font-size:12px;")
            off.setToolTip("이 케이스에는 변환기(VSC)가 없습니다")
            head.addWidget(off)
        else:
            seg = QFrame()
            seg.setObjectName("segwrap")
            seg.setFixedHeight(34)
            seg.setStyleSheet(
                f"#segwrap {{ background:{c['bg']};border:1px solid {c['border']};"
                f"border-radius:9px; }}")
            sh = QHBoxLayout(seg)
            sh.setContentsMargins(3, 3, 3, 3)
            sh.setSpacing(3)
            for txt, val in [("ON", True), ("OFF", False)]:
                b = QPushButton(txt)
                b.setObjectName("seg_on" if self.show_vsc == val else "seg_off")
                b.setCursor(Qt.PointingHandCursor)
                b.setFixedWidth(52)
                b.clicked.connect(lambda _, x=val: self.set_vsc(x))
                sh.addWidget(b)
            head.addWidget(seg)
        cb = QPushButton("열 선택")
        cb.clicked.connect(self.pick_columns)
        head.addWidget(cb)
        tv.addLayout(head)

        tt = QTabWidget()
        self._tabs = tt
        tt.setTabPosition(QTabWidget.North)

        if self.sol is not None:
            key = self.bus_row if self.mode == "다이나믹" else self.t
            specs = real_tables(self.sol, self.mode, key,
                                self.show_vsc and self.case_has_vsc)
            bad = self.violating_buses()
            for name, cols, arr in specs:
                t = QTableWidget(arr.shape[0], len(cols))
                t.setHorizontalHeaderLabels(cols)
                t.verticalHeader().setVisible(False)
                t.verticalHeader().setDefaultSectionSize(30)
                t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                t.setAlternatingRowColors(True)
                warn = QColor(self.c["warn"])
                for r in range(arr.shape[0]):
                    flag = name in ("AC 결과", "DC 결과") and \
                        (name[:2], int(arr[r, 0])) in bad
                    for cc in range(len(cols)):
                        val = arr[r, cc]
                        txt = f"{val:.0f}" if cc == 0 and float(val).is_integer() \
                            else f"{val:,.4f}".rstrip("0").rstrip(".")
                        it = QTableWidgetItem(txt)
                        if cc > 0:
                            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        if flag:
                            it.setForeground(warn)
                        t.setItem(r, cc, it)
                tt.addTab(t, name)
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

        # 점검 · 수렴 탭
        n = violation_count(self.viol())
        tt.addTab(self.check_page(), f"점검 ({n})" if n else "점검")
        tt.addTab(self.conv_page(), "수렴")
        n_ch = len(self.changes)
        tt.addTab(self.grid_page(),
                  f"계통 데이터 ({n_ch})" if n_ch else "계통 데이터")

        # 보고 있던 탭으로 되돌린다 — 조건을 하나 바꿀 때마다 화면을 다시 그리므로,
        # 이걸 안 하면 매번 첫 탭(AC 결과)으로 튄다.
        self._restore_tab(tt)
        tt.currentChanged.connect(
            lambda i, w=tt: setattr(self, "table_tab", _tab_base(w.tabText(i))))
        tv.addWidget(tt)
        split.addWidget(tw)

        if not self.numbers:
            split.setStretchFactor(0, 3)      # 표가 sizeHint 로 밀고 올라오는 걸 막는다
            split.setStretchFactor(1, 2)
            split.setSizes(self.split_sizes or [620, 300])
            split.splitterMoved.connect(
                lambda *_: setattr(self, "split_sizes", split.sizes()))
        v.addWidget(split, 1)
        return w

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
        v.addSpacing(34)

        # 파일 놓는 자리
        drop = QFrame()
        drop.setObjectName("dropzone")
        drop.setMinimumHeight(170)
        drop.setMaximumWidth(720)
        dv = QVBoxLayout(drop)
        dv.setSpacing(7)
        d1 = QLabel("계통 파일을 여기로 끌어다 놓으세요")
        d1.setAlignment(Qt.AlignCenter)
        d1.setStyleSheet(f"color:{c['text']};font-size:19px;font-weight:700;")
        dv.addWidget(d1)
        self.dropzone = drop        # 끌어다 놓을 때 밝히려고 들고 있는다
        self.drop_label = d1
        d2 = QLabel("UNIGRID 엑셀 (.xlsx)  ·  MATPOWER (.m)  ·  PSS/E (.raw)"
                    "     — 형식은 자동으로 알아냅니다")
        d2.setAlignment(Qt.AlignCenter)
        d2.setStyleSheet(f"color:{c['muted']};font-size:13px;")
        dv.addWidget(d2)
        dv.addSpacing(10)
        row = QHBoxLayout()
        row.addStretch()
        pick = QPushButton("파일 고르기")
        pick.setObjectName("primary")
        pick.setMinimumSize(150, 44)
        pick.clicked.connect(self.do_import)
        row.addWidget(pick)
        row.addStretch()
        dv.addLayout(row)
        hb = QHBoxLayout()
        hb.addStretch(); hb.addWidget(drop); hb.addStretch()
        v.addLayout(hb)
        v.addSpacing(12)

        # 작은 링크 — 계산이 아니라 "케이스 파일을 새로 만드는" 도구
        lk = QHBoxLayout()
        lk.addStretch()
        conv = QPushButton("AC 계통 파일을 UNIGRID 엑셀로 만들기 (DC·변환기를 직접 넣으려면)")
        conv.setObjectName("link")
        conv.setCursor(Qt.PointingHandCursor)
        conv.clicked.connect(lambda: ConvertDialog(self, c).exec())
        lk.addWidget(conv)
        lk.addStretch()
        v.addLayout(lk)
        v.addSpacing(22)

        # 최근에 연 파일
        recent = load_recent()
        if recent:
            cap = QLabel("최근에 연 파일")
            cap.setStyleSheet(f"color:{c['muted']};font-size:13px;font-weight:700;")
            cw = QWidget()
            cw.setMaximumWidth(720)
            cvv = QVBoxLayout(cw)
            cvv.setContentsMargins(0, 0, 0, 0)
            cvv.setSpacing(7)
            cvv.addWidget(cap)
            for item in recent:
                name = Path(item["path"]).name
                b = QPushButton(f"{name}\n{item.get('info', '')}")
                b.setMinimumHeight(54)
                b.setStyleSheet(
                    f"text-align:left;padding:9px 14px;font-size:14px;")
                b.clicked.connect(lambda _, p=item["path"]: self.open_path(p))
                cvv.addWidget(b)
            hb2 = QHBoxLayout()
            hb2.addStretch(); hb2.addWidget(cw); hb2.addStretch()
            v.addLayout(hb2)

        v.addStretch()
        outer.addWidget(body, 1)

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
            self.dropzone.setStyleSheet(
                f"#dropzone {{ background:{c['accent_soft']};"
                f" border:2px dashed {c['accent']}; border-radius:14px; }}")
            if self.drop_label is not None:
                self.drop_label.setText("놓으면 바로 계산합니다")
                self.drop_label.setStyleSheet(
                    f"color:{c['accent']};font-size:19px;font-weight:700;")
        else:
            self.dropzone.setStyleSheet("")
            if self.drop_label is not None:
                self.drop_label.setText("계통 파일을 여기로 끌어다 놓으세요")
                self.drop_label.setStyleSheet(
                    f"color:{c['text']};font-size:19px;font-weight:700;")

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
        cap.setStyleSheet(f"color:{c['muted']};font-size:12px;font-weight:700;")
        top.addWidget(cap)
        top.addStretch()
        ch = QPushButton("바꾸기")
        ch.setFixedHeight(24)
        ch.setStyleSheet(
            f"border:none;background:transparent;color:{c['accent']};"
            f"font-size:12px;padding:0;")
        ch.setCursor(Qt.PointingHandCursor)
        ch.clicked.connect(self.do_import)
        top.addWidget(ch)
        v.addLayout(top)

        stem = name.replace(".xlsx", "").replace(".m", "").replace(".raw", "")
        # Qt 는 밑줄을 줄 끊는 자리로 안 쳐서 긴 이름이 그냥 잘린다.
        # 밑줄 뒤에 폭 0짜리 끊김표(U+200B)를 넣어 두 줄까지 보이게 한다.
        f = QLabel(stem.replace("_", "_​"))
        f.setWordWrap(True)
        f.setToolTip(str(getattr(self, "_last_path", "") or name))
        f.setStyleSheet(f"color:{c['text']};font-size:16px;font-weight:700;")
        v.addWidget(f)

        ext = QLabel(name.split(".")[-1].upper() + " 파일")
        ext.setStyleSheet(f"color:{c['muted']};font-size:11px;")
        v.addWidget(ext)

        # 계통 종류 = 알약 표시
        pill = QLabel("  " + mode_txt + "  ")
        pill.setStyleSheet(
            f"background:{c['accent_soft']};color:{c['accent']};"
            f"border-radius:9px;padding:4px 6px;font-size:12px;font-weight:700;")
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
                    f"color:{c['text']};font-size:18px;font-weight:700;")
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
                    f"color:{c['text']};font-size:18px;font-weight:700;")
                col.addWidget(a)
                col.addWidget(b)
                cr.addLayout(col)
            cr.addStretch()
            v.addLayout(cr)
        return box

    def freq_card(self):
        """시스템 주파수 — 계통 전체에 하나뿐인 값이라 크게 보여준다."""
        c = self.c
        if self.sol is not None and self.sol.freq.size:
            f = float(self.sol.freq[min(self.t, self.sol.freq.size - 1)])
        else:
            f = 60.02
        # 기준 주파수는 케이스마다 다르다 (60 Hz / 50 Hz) — 못 박으면 안 된다
        nominal = self.sol.freq_nominal if self.sol is not None else 60.0
        # 데드밴드도 케이스 파일에서 읽는다. 예전엔 ±0.05 Hz 라고 내가 정한 값을
        # 썼는데, 실제 값은 0.036 Hz 이거나 아예 0 이다(app_engine._freq_deadband).
        db = self.sol.freq_db if self.sol is not None else 0.0
        dev = f - nominal
        box = QFrame()
        box.setObjectName("card")
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 11, 14, 13)
        v.setSpacing(3)
        t = QLabel("시스템 주파수")
        t.setStyleSheet(f"color:{c['muted']};font-size:12px;font-weight:600;")
        v.addWidget(t)
        row = QHBoxLayout()
        row.setSpacing(5)
        big = QLabel(f"{f:.2f}")
        big.setStyleSheet(f"color:{c['text']};font-size:30px;font-weight:800;")
        row.addWidget(big)
        unit = QLabel("Hz")
        unit.setStyleSheet(f"color:{c['muted']};font-size:14px;")
        unit.setAlignment(Qt.AlignBottom)
        row.addWidget(unit)
        row.addStretch()
        v.addLayout(row)
        d = QLabel(f"기준 {nominal:.0f} Hz 대비 {dev:+.2f} Hz")
        d.setStyleSheet(f"color:{c['muted']};font-size:12px;")
        v.addWidget(d)
        # 데드밴드는 "발전기가 주파수에 응동하기 시작하는 폭"이다. 밖에 있다고
        # 잘못된 상태가 아니라 **발전기가 응동 중**이라는 뜻이라 경고색을 안 쓴다.
        # 진짜 위반(전압·과부하·변환기 한계)은 상태바와 점검 탭이 따로 센다.
        if db > 0:
            where = "안 — 발전기 응동 없음" if abs(dev) <= db else "밖 — 발전기 응동 중"
            txt = f"데드밴드 ±{db:g} Hz {where}"
        else:
            txt = "데드밴드 없음 — 작은 편차에도 발전기가 응동"
        s = QLabel(txt)
        s.setStyleSheet(f"color:{c['muted']};font-size:12px;")
        v.addWidget(s)
        return box

    def viol(self):
        """지금 화면의 위반 목록 (실제 결과가 있으면 실제값)."""
        if self.sol is None:
            return VIOLATIONS
        return real_violations(self.sol, self.t)

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

    # ── 점검 탭 ──
    # ══════════════════════════ 계통 조건 (PDR §7 2단계) ══════════════════════════
    # 바꾸는 동안은 **계산하지 않는다.** 다 바꾸고 [이 조건으로 계산] 을 누를 때 한 번 푼다
    # (2026-08-06 사용자 확정). 버튼 한 번 = 조류계산 한 번 = 시나리오 한 줄.

    def change_bar(self):
        """무엇을 바꿨는지 + [이 조건으로 계산] · [되돌리기]. 바꾼 게 없으면 안 만든다."""
        if not self.changes:
            return None
        c = self.c
        bar = QFrame()
        bar.setObjectName("card")
        bar.setStyleSheet(
            f"#card {{ background:{c['surface']};border:1px solid {c['warn']};"
            f"border-radius:10px; }}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(15, 9, 11, 9)
        h.setSpacing(11)

        tag = QLabel(f"바꾼 것 {len(self.changes)}건")
        tag.setStyleSheet(
            f"color:{c['warn']};font-size:12px;font-weight:600;padding:2px 9px;"
            f"border:1px solid {c['warn']};border-radius:9px;")
        h.addWidget(tag)

        what = QLabel(SC.describe(self.changes))
        what.setStyleSheet(f"color:{c['text']};font-size:13px;font-weight:600;")
        h.addWidget(what)

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

        run = QPushButton("▶  이 조건으로 계산")
        run.setObjectName("primary")
        run.setCursor(Qt.PointingHandCursor)
        run.clicked.connect(self.run_changes)
        h.addWidget(run)

        undo = QPushButton("↩ 되돌리기")
        undo.setCursor(Qt.PointingHandCursor)
        undo.clicked.connect(self.undo_changes)
        h.addWidget(undo)
        return bar

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

    def load_bar(self):
        """부하 전체 ×배수 슬라이더. 여기서도 **바로 계산하지 않는다.**"""
        if not self.has_load():
            return None
        c = self.c
        now = self.load_factor()
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
        sl.setValue(int(round(now * 100)))
        sl.setFixedWidth(240)
        sl.setTickPosition(QSlider.TicksBelow)
        sl.setTickInterval(25)
        n_t = self.load_times()
        sl.setToolTip("모든 부하에 같은 수를 곱합니다."
                      + (f"\n이 계통은 {n_t}시각짜리이고, **모든 시각에 함께** 걸립니다."
                         if n_t > 1 else ""))
        h.addWidget(sl)

        val = QLabel(f"×{now:.2f}")
        val.setFixedWidth(52)
        val.setStyleSheet(f"color:{c['accent']};font-size:14px;font-weight:700;")
        h.addWidget(val)

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
        h.addStretch(1)

        back = QPushButton("원래대로 (×1)")
        back.setCursor(Qt.PointingHandCursor)
        back.setEnabled(abs(now - 1.0) > 1e-9)
        back.clicked.connect(lambda: self.scale_loads(1.0))
        h.addWidget(back)

        def moved(v):
            val.setText(f"×{v / 100:.2f}")
            self._load_pending = v / 100
            if not sl.isSliderDown():            # 화살표키·홈 클릭 — 잠깐 뒤에 반영
                self._load_timer.start(250)

        sl.valueChanged.connect(moved)
        sl.sliderReleased.connect(lambda: self.scale_loads(sl.value() / 100))
        return bar

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

    def grid_page(self):
        """계통 데이터 탭 — 엑셀 값을 그대로 보여 주고, 여기서 켜고 끈다."""
        c = self.c
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 11, 14, 12)
        v.setSpacing(9)

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
        if self.grid_key not in [k for k, _, _ in picks]:
            self.grid_key = picks[0][0]

        row = QHBoxLayout()
        row.setSpacing(6)
        for key, label, n in picks:
            b = QPushButton(f"{label} {n}")
            b.setObjectName("seg_on" if key == self.grid_key else "seg_off")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, k=key: self.set_grid_table(k))
            row.addWidget(b)
        row.addStretch(1)
        hint = QLabel("켜고 끄기는 바로 계산하지 않습니다 — 다 바꾼 뒤 위의 [이 조건으로 계산]")
        hint.setStyleSheet(f"color:{c['muted']};font-size:12px;")
        row.addWidget(hint)
        v.addLayout(row)

        load = self.load_bar()                 # ② 부하 일괄 증감
        if load is not None:
            v.addWidget(load)

        v.addWidget(self.grid_table_widget(), 1)
        return w

    def grid_table_widget(self):
        """지금 고른 표 하나를 그린다.

        · 켤 수 있는 표면 첫 칸이 스위치
        · **화면 단위로 바꿔서** 보여 준다 (엔진은 W, 화면은 MW — 머리글이 [MW] 니까)
        · ③ 운전 조건 칸만 고칠 수 있고, 나머지는 회색이다
        """
        c = self.c
        key = self.grid_key
        sw = SC.SWITCHES.get(key)
        heads = GRID_HEADERS.get(key, [])
        scales = GRID_SCALES.get(key, {})
        editable = GRID_EDITABLE.get(key, set())
        eff = self.applied + self.changes      # 화면에 보이는 조건 = 푼 것 + 얹은 것
        arr = SC._values(SC.apply(self.base_case, eff), key)
        ncol = min(arr.shape[1], len(heads)) if heads else arr.shape[1]
        cols = (["상태"] if sw else []) + \
               [heads[i] if i < len(heads) else f"{i + 1}열" for i in range(ncol)]

        tb = QTableWidget(arr.shape[0], len(cols))
        tb.setHorizontalHeaderLabels(cols)
        tb.verticalHeader().setVisible(False)
        tb.verticalHeader().setDefaultSectionSize(30)
        # 🚨 열이 많으면 늘려 맞추기(Stretch)가 머리글을 잘라 버린다 — IC 는 20열이라
        #    "Rating Power [MW]" 가 "ng Po" 로 보였다. 그럴 땐 글자에 맞추고 옆으로 넘긴다.
        tb.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch if len(cols) <= 9 else QHeaderView.ResizeToContents)
        tb.setAlternatingRowColors(True)

        touched = {(ch.row, ch.col) for ch in self.changes
                   if isinstance(ch, SC.Cell) and ch.table == key}
        off = 1 if sw else 0
        self._grid_loading = True              # 그리는 동안의 itemChanged 는 무시
        for r in range(arr.shape[0]):
            if sw:
                on = SC.is_on(self.base_case, key, r, eff)
                b = QPushButton("켜짐" if on else "꺼짐")
                b.setObjectName("seg_on" if on else "seg_off")
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _, rr=r: self.flip_row(rr))
                tb.setCellWidget(r, 0, b)
            for j in range(ncol):
                val = arr[r, j] * scales.get(j, 1.0)
                txt = "" if np.isnan(val) else (
                    f"{val:.0f}" if float(val).is_integer() and abs(val) < 1e9
                    else f"{val:,.4f}".rstrip("0").rstrip("."))
                it = QTableWidgetItem(txt)
                if j > 0:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j in editable:
                    it.setToolTip("고칠 수 있는 값입니다 — 바꾸면 계산은 안 돌고 "
                                  "위의 [이 조건으로 계산] 을 눌러야 풉니다")
                else:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    it.setForeground(QColor(c["muted"]))   # 여기부터는 엑셀에서
                if (r, j) in touched:
                    it.setForeground(QColor(c["warn"]))
                tb.setItem(r, j + off, it)
        self._grid_loading = False
        tb.itemChanged.connect(lambda item: self.grid_edited(key, item, off, scales))
        return tb

    def grid_edited(self, key, item, off, scales):
        """운전 조건 칸을 고쳤다. **계산은 안 한다** — 바꾼 목록에만 얹는다."""
        if getattr(self, "_grid_loading", False):
            return
        col = item.column() - off
        if col < 0 or col not in GRID_EDITABLE.get(key, set()):
            return
        txt = item.text().strip().replace(",", "")
        try:
            shown = float(txt)
        except ValueError:
            QMessageBox.information(self, "숫자를 넣어 주세요",
                                    f"'{item.text()}' 는 숫자가 아닙니다.")
            self.rebuild()
            return
        scale = scales.get(col, 1.0)
        value = shown * (1.0 / scale) if scale != 1.0 else shown
        row = item.row()
        before = float(SC._values(
            SC.apply(self.base_case, self.applied + self.changes), key)[row, col])
        if abs(before - value) <= abs(before) * 1e-12:
            return                              # 안 바뀐 값 — 목록을 더럽히지 않는다
        head = GRID_HEADERS.get(key, [])
        name = head[col] if col < len(head) else f"{col + 1}열"
        self.changes = [ch for ch in self.changes
                        if not (isinstance(ch, SC.Cell) and ch.table == key
                                and ch.row == row and ch.col == col)]
        self.changes.append(SC.Cell(
            table=key, row=row, col=col, value=value,
            label=f"{SC.describe_row(self.base_case, key, row)} {name} → {shown:g}",
            mark=SC.row_mark(self.base_case, key, row)))
        self.rebuild()

    def set_grid_table(self, key):
        self.grid_key = key
        self.rebuild()

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
        if item in ("주파수", "손실") or not pairs:
            return None
        col = {"전압 크기": "VM[pu]", "위상각": "Angle[deg]"}.get(item)
        if col is None:
            return None
        rows = []
        base_lo = None
        for name, sol in pairs:
            vals = []
            for kind in ("AC", "DC"):
                arr = sol.at(kind, self.t)
                cols = sol.cols(kind)
                if arr.size and col in cols:
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
                [("겹쳐", 46), ("이름", 0), ("바꾼 것", 52), ("결과", 66),
                 ("전압 최저", 82), ("원본 대비", 74), ("", 210)]):
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
        v.addLayout(g)
        return card

    def _scenario_row(self, g, i, s, base):
        c = self.c
        here = list(s.changes) == list(self.applied)     # 지금 화면이 이것인가

        left0 = QHBoxLayout()
        left0.setSpacing(4)
        dot = QLabel("●" if here else "○")
        dot.setStyleSheet(f"color:{c['accent'] if here else c['border']};font-size:12px;")
        left0.addWidget(dot)
        if s.solved:
            cb = QCheckBox()
            cb.setChecked((i - 1) in self.overlay if self.overlay else True)
            cb.setToolTip("비교 모드에서 겹쳐 그릴지")
            cb.toggled.connect(lambda on, k=i - 1: self.toggle_overlay(k, on))
            left0.addWidget(cb)
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

        cell(2, "—" if s.base else f"{len(s.changes)}건")
        cell(3, s.summary, c["warn"] if s.error else c["muted"], bold=bool(s.error))
        vmin = s.vmin()
        cell(4, "—" if np.isnan(vmin) else f"{vmin:.4f} pu", c["text"], right=True)
        d = s.against(base) if (base is not None and not s.base) else float("nan")
        cell(5, "—" if np.isnan(d) else f"{d:+.4f}",
             c["warn"] if (not np.isnan(d) and d < -1e-6) else c["muted"],
             right=True, tip="원본 대비 전압 최저 변화")

        act = QHBoxLayout()
        act.setSpacing(6)
        act.addStretch(1)
        if not here:
            b = QPushButton("결과 보기" if s.solved else "조건만 불러오기")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, _s=s: self.show_scenario(_s))
            act.addWidget(b)
        if not s.base:
            x = QPushButton("지우기")
            x.setCursor(Qt.PointingHandCursor)
            x.setToolTip("이 시나리오를 목록에서 지웁니다 (계통은 안 건드립니다)")
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

    def check_page(self):
        c = self.c
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(14, 12, 14, 12)
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
        msg = QLabel(f"한계를 벗어난 항목 {n}건" if n else "한계를 벗어난 항목 없음")
        msg.setStyleSheet(
            f"color:{c['warn'] if n else c['ok']};font-size:15px;font-weight:700;")
        hv.addWidget(msg)
        hv.addStretch()
        sub = QLabel("전압 한계 · 선로 용량 · 변환기 한계 · 발전기 한계를 계산 결과에서 걸러낸 것입니다")
        sub.setStyleSheet(f"color:{c['muted']};font-size:12px;")
        hv.addWidget(sub)
        outer.addWidget(head)

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
            wicon.setStyleSheet(f"color:{c['warn']};font-size:16px;font-weight:700;")
            wv.addWidget(wicon)
            wtxt = QLabel("한계 적용 시 수렴 실패 — " + qmsg)
            wtxt.setWordWrap(True)
            wtxt.setStyleSheet(f"color:{c['warn']};font-size:13px;font-weight:700;")
            wv.addWidget(wtxt, 1)
            outer.addWidget(warn)

        for title, (cols, rows) in self.viol().items():
            box = QFrame()
            box.setObjectName("card")
            bv = QVBoxLayout(box)
            bv.setContentsMargins(14, 11, 14, 13)
            bv.setSpacing(8)
            th = QHBoxLayout()
            t = QLabel(title)
            t.setStyleSheet(f"color:{c['text']};font-size:14px;font-weight:700;")
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
                tb.setMaximumHeight(30 * len(rows) + 42)
                for r, row in enumerate(rows):
                    for cc, val in enumerate(row):
                        it = QTableWidgetItem(val)
                        if cc > 1:
                            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        if cc == len(row) - 1:
                            it.setForeground(Qt.red)
                        tb.setItem(r, cc, it)
                bv.addWidget(tb)
            else:
                ok = QLabel("없음")
                ok.setStyleSheet(f"color:{c['muted']};font-size:12px;")
                bv.addWidget(ok)
            outer.addWidget(box)

        outer.addStretch()
        return w

    # ── 수렴 탭 ──
    def conv_page(self):
        c = self.c
        sol = self.sol
        conv = dict(
            converged=sol.converged if sol else CONV["converged"],
            iters=sol.iters if sol else CONV["iters"],
            threshold=sol.threshold if sol else CONV["threshold"],
            mis=list(sol.mis_history) if sol else CONV["mis"],
            blocks=list(sol.block_names) if sol and sol.block_names else CONV["blocks"],
            block_hist=(sol.block_history.tolist()
                        if sol is not None and sol.block_history.size
                        else CONV["block_hist"]),
            dominant=list(sol.dominant_block) if sol and sol.dominant_block
            else CONV["dominant"],
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
                f"color:{color or c['text']};font-size:17px;font-weight:700;")
            b.addWidget(a)
            b.addWidget(d)
            return b

        hv.addLayout(kv("수렴", "성공" if conv["converged"] else "실패",
                        c["ok"] if conv["converged"] else c["warn"]))
        hv.addLayout(kv("반복 횟수", f"{conv['iters']}회"))
        hv.addLayout(kv("계산 시간", f"{conv['seconds']:.2f} s"))
        hv.addLayout(kv("수렴 기준", f"{conv['threshold']:g}"))
        hv.addLayout(kv("최종 불평형", f"{CONV['mis'][-1]:.2e}"))
        hv.addStretch()
        outer.addWidget(head)

        # 불평형이 줄어드는 과정
        box = QFrame()
        box.setObjectName("card")
        bv = QVBoxLayout(box)
        bv.setContentsMargins(14, 11, 14, 13)
        t = QLabel("반복에 따른 최대 불평형")
        t.setStyleSheet(f"color:{c['text']};font-size:14px;font-weight:700;")
        bv.addWidget(t)
        sub = QLabel("실제 그래프가 들어갈 자리 — 세로축은 로그 눈금")
        sub.setStyleSheet(f"color:{c['muted']};font-size:11px;")
        bv.addWidget(sub)
        bar = QHBoxLayout()
        bar.setSpacing(10)
        for i, m in enumerate(conv["mis"]):
            cell = QFrame()
            cell.setObjectName("plot")
            cv = QVBoxLayout(cell)
            cv.setContentsMargins(10, 8, 10, 8)
            a = QLabel(f"{i}회")
            a.setStyleSheet(f"color:{c['muted']};font-size:11px;")
            d = QLabel(f"{m:.2e}")
            d.setStyleSheet(
                f"color:{c['ok'] if m < conv['threshold'] else c['text']};"
                f"font-size:15px;font-weight:700;")
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
        t2.setStyleSheet(f"color:{c['text']};font-size:14px;font-weight:700;")
        b2.addWidget(t2)
        tb = QTableWidget(len(conv["block_hist"]), len(conv["blocks"]) + 2)
        tb.setHorizontalHeaderLabels(["반복"] + conv["blocks"] + ["가장 큰 블록"])
        tb.verticalHeader().setVisible(False)
        tb.verticalHeader().setDefaultSectionSize(30)
        tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tb.setMinimumHeight(30 * len(conv["block_hist"]) + 46)
        tb.setMaximumHeight(30 * len(conv["block_hist"]) + 46)
        for r, row in enumerate(conv["block_hist"]):
            tb.setItem(r, 0, QTableWidgetItem(str(r + 1)))
            worst = max(range(len(row)), key=lambda i: row[i])
            for cc, v in enumerate(row):
                it = QTableWidgetItem("—" if v == 0 else f"{v:.1e}")
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if cc == worst and v > 0:
                    it.setForeground(Qt.red)
                tb.setItem(r, cc + 1, it)
            tb.setItem(r, len(row) + 1, QTableWidgetItem(conv["dominant"][r]))
        b2.addWidget(tb)
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

    def set_violations(self, on):
        """계통도 '위반 보기' 켜기/끄기. 계통도 토글 버튼이 부른다."""
        self.show_violations = bool(on)
        self.rebuild()

    def show_line_profile(self, g, ei):
        """계통도에서 선로를 클릭하면 그 선로의 24시간 부하율을 팝업으로 띄운다.
        시간별 데이터가 없는 케이스(스냅샷 1시각)면 그 사실을 적어 준다."""
        if self.sol is None:
            return
        import topology
        c = self.c
        title = topology.edge_label(g, ei)
        ser = topology.loading_series(g, self.sol, ei)
        d = QDialog(self)
        d.setWindowTitle(f"{title} — 24시간 부하율")
        d.setStyleSheet(self.styleSheet())
        d.setMinimumSize(560, 380)
        v = QVBoxLayout(d)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)
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
        v.addWidget(body, 1)
        close = QPushButton("닫기")
        close.clicked.connect(d.accept)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(close)
        v.addLayout(row)
        d.exec()

    def pick_columns(self):
        name = self._tabs.tabText(self._tabs.currentIndex())
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
        for col, _ in TABLE_SPECS[name]:
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
            if picked:
                self.visible[name] = picked
                self.rebuild()

    def compare_area(self):
        c = self.c
        wide = self.compare_axis in ("시간끼리", "시나리오끼리")
        picked = [n for n, always in COMPARE_ITEMS
                  if n in self.picked and (always or wide)]
        tabs = QTabWidget()
        if not picked:
            page = QWidget()
            pv = QVBoxLayout(page)
            lb = QLabel("왼쪽에서 볼 항목을 하나 이상 고르세요")
            lb.setAlignment(Qt.AlignCenter)
            lb.setStyleSheet(f"color:{c['muted']};font-size:16px;")
            pv.addWidget(lb)
            tabs.addTab(page, "결과")
            return tabs
        if self.compare_axis == "시나리오끼리":
            return self.compare_scenarios_area(picked)
        targets = [t.strip() for t in self.compare_targets.split(",") if t.strip()]
        unit = "버스" if self.compare_axis == "버스끼리" else "시간"
        for name in picked:
            page = QWidget()
            pv = QVBoxLayout(page)
            pv.setContentsMargins(10, 10, 10, 10)
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
        return tabs

    def save_compare_figures(self):
        """지금 보고 있는 비교 그림들을 그대로 파일로. (일반 내보내기와 따로)"""
        if self.sol is None:
            QMessageBox.information(self, "비교 그림 저장",
                                    "먼저 케이스를 불러와 계산하세요.")
            return
        items = [n for n, always in COMPARE_ITEMS
                 if n in self.picked and (always or self.compare_axis == "시간끼리")]
        if not items:
            QMessageBox.information(self, "비교 그림 저장",
                                    "왼쪽에서 볼 항목을 하나 이상 고르세요.")
            return
        targets = [t.strip() for t in self.compare_targets.split(",") if t.strip()]
        folder = exporter.default_folder(self.sol.case_name)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            files = exporter.save_compare_figures(
                self.c, self.sol, self.compare_axis, targets, items, folder)
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
        col = {"전압 크기": "VM[pu]", "위상각": "Angle[deg]"}.get(item)
        if col is None or col not in sol.cols("AC"):
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
            box = QHBoxLayout()
            box.setSpacing(6)
            a = QLabel(k)
            a.setStyleSheet(f"color:{c['muted']};font-size:14px;")
            b = QLabel(val)
            b.setStyleSheet(
                f"color:{color or c['text']};font-size:14px;font-weight:600;")
            box.addWidget(a)
            box.addWidget(b)
            return box

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
            f"font-size:14px;font-weight:700;padding:0;text-align:left;")
        vb.clicked.connect(self.go_check)
        h.addWidget(vb)

        if sol is not None:
            h.addLayout(item("수렴", "성공" if sol.converged else "실패",
                             c["ok"] if sol.converged else c["warn"]))
            h.addLayout(item("반복", f"{sol.iters}회"))
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
        """다시 그린 뒤 보고 있던 표 탭으로 되돌린다. 그 탭이 사라졌으면 첫 탭."""
        want = getattr(self, "table_tab", None)
        if not want:
            return
        for i in range(tt.count()):
            if _tab_base(tt.tabText(i)) == want:
                tt.setCurrentIndex(i)
                return

    def go_check(self):
        """상태바의 위반 건수 → 점검 탭으로."""
        if self.mode == "비교":       # 비교 모드엔 표가 없으니 스냅샷으로 돌아간다
            self.mode = "스냅샷"
            self.rebuild()
        tt = getattr(self, "_tabs", None)
        if tt is None:
            return
        for i in range(tt.count()):
            if tt.tabText(i).startswith("점검"):
                tt.setCurrentIndex(i)
                self.table_tab = "점검"      # 다시 그려도 여기 머문다
                return

    # ── 동작 ──
    def set_mode(self, m):
        self.mode = m
        self.rebuild()

    def set_axis(self, a):
        self.compare_axis = a
        self.rebuild()

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
        self.rebuild()

    def toggle_theme(self):
        self.dark = not self.dark
        self.rebuild()

    def do_import(self):
        # 파일 고르기 창이 처음 보여 줄 자리. 저장소의 검증용 케이스 폴더가 있으면 거기서
        # 시작한다(뼈대에서는 케이스가 널려 있던 v14 폴더였다).
        cases = Path(__file__).resolve().parent.parent / "cases"
        start = str(cases if cases.is_dir() else Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "계통 파일 선택", start,
            "계통 파일 (*.xlsx *.m *.raw);;모든 파일 (*)")
        if not path:
            return
        if load_case is None:
            QMessageBox.warning(self, "불러오기",
                                "케이스 읽기 모듈(load_case)을 찾지 못했습니다.")
            return

        self._start_solve(path)

    def _start_solve(self, path, case=None):
        self._last_path = path
        self.prog = QProgressDialog("조류계산 중입니다...", None, 0, 0, self)
        self.prog.setWindowTitle("UNIGRID")
        self.prog.setWindowModality(Qt.WindowModal)
        self.prog.setMinimumWidth(340)
        self.prog.setCancelButton(None)
        self.prog.show()

        self.thread = SolveThread(path, case)
        self.thread.done.connect(self._solved)
        self.thread.failed.connect(self._solve_failed)
        self.thread.engine_missing.connect(self._engine_missing)
        self.thread.start()

    def _solved(self, sol):
        if getattr(self, "prog", None) is not None:
            self.prog.close()
        # 조건을 안 바꾸고 푼 것이면 이 케이스가 **원본**이다 (바꿔서 푼 것은 원본이 아니다).
        loaded = getattr(getattr(self, "thread", None), "loaded_case", None)
        pending = getattr(self, "_pending", None)
        if pending:
            # [이 조건으로 계산] 으로 푼 것 — 시나리오 한 줄로 담고 바꾼 목록을 비운다
            self.book.add(self.base_case, pending, solution=sol,
                          name=self._new_name(pending))
            self.applied = list(pending)      # 이제 이것이 화면의 조건이다
            self.changes = []
            self._pending = None
        elif loaded is not None and not self.changes:
            self.base_case = loaded
            self.applied = []
            self.changes = []
            self.book = SC.Book()
            self.book.add(loaded, [], solution=sol, name="원본")
        self.sol = sol
        self.t = 0
        self.bus_row = 0
        self.show_violations = False      # 새 케이스는 위반 보기 꺼진 채로 시작
        self.case = (Path(sol.case_name).name or "case",
                     f"{sol.mode_name} · AC {sol.AC.shape[0]} / DC {sol.DC.shape[0]}")
        self.case_has_vsc = sol.VSC_bus is not None and sol.VSC_bus.size > 0
        save_recent(str(getattr(self, "_last_path", sol.case_name)), self.case[1])
        if not self.case_has_vsc:
            self.show_vsc = False
        self.rebuild()

    def _new_name(self, pending):
        """시나리오 이름 — 이번에 새로 얹은 것으로 짓고, 없으면 전체로."""
        fresh = getattr(self, "_pending_new", None)
        self._pending_new = None
        return SC.auto_name(self.base_case, fresh if fresh else pending)

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
            self.rebuild()
            QMessageBox.warning(
                self, "안 풀렸습니다",
                f"{SC.describe(pending)}\n\n이 조건으로는 답을 찾지 못했습니다. "
                f"시나리오 목록에 '안 풀림' 으로 남겨 두었고, 화면은 그대로 둡니다."
                f"\n\n{msg[:600]}")
            return
        QMessageBox.critical(self, "계산 실패", msg[:1500])

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
        ExportDialog(self, self.c, self.mode, self.numbers, self.picked).exec()


def main():
    app = QApplication(sys.argv)
    w = Proto()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
