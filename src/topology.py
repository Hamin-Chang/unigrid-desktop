"""topology.py — 계통 단선도 (버스와 선로를 그림으로).

MATLAB 앱의 ACDC_topology.m 을 옮긴 것. 다만 자리를 잡는 방식이 다르다.
MATLAB 은 graph 객체가 알아서 자리를 잡아 주지만(돌릴 때마다 모양이 다르다),
여기서는 **논문 계통도처럼 층으로 나눠** 놓는다 — 버스는 굵은 세로 막대,
선은 가로·세로로만, AC 는 왼쪽 DC 는 오른쪽, 그 사이를 IC 가 잇는다.
서로 밀어내는 방식(spring)도 써 봤지만 그물에나 맞지 단선도로는 어수선했다.
사용자가 마우스로 끌어 옮길 수 있고, 옮긴 자리는 케이스별로 기억한다.

읽는 값은 '결과'가 아니라 케이스의 '입력 표'다. 어느 선로가 변압기인지,
발전기가 어떤 종류인지는 계산 결과에 안 담기기 때문.
각 열이 뭘 뜻하는지는 functions/preprocess_*.m 에서 확인한 것:

  AC_Line_dat    2,3열 = 출발·도착 버스 / 12열 = 변압기면 1 / 13열 = 연결 상태
  DC_Line_dat    2,3열 = 출발·도착 버스 / 8열 = 연결 상태
  IC_dat         1열 = AC 버스 / 2열 = DC 버스 / 16열 = 상태(1이면 켜짐)
  DCDC_Conv_dat  1열 = MV 버스 / 2열 = LV 버스 / 10열 = 운전모드(0보다 크면 켜짐)
  AC_gen_dat     1열 = 버스 / 2열 = 종류(1 송전·2 동기기·3 IBR)
                 3열 = 운전모드(0 PQ·1 droop·2 PV·3 slack) / 9열 = 상태
  DC_gen_dat     1열 = 버스 / 2열 = 종류 / 3열 = 운전모드(0 정전력·1 droop·2 정전압)
                 ※ 9열은 상태가 아니라 전압 데드밴드다(DC 엔 상태 열이 없다)
  AC_3wtrans_dat 2,3,4열 = 세 버스 / 5열 = 상태
(MATLAB 은 1부터 세므로 파이썬에서는 1을 뺀다.)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ICON_DIR = HERE.parent          # 아이콘 png 들이 있는 곳
PLACES = HERE / ".topology_places.json"     # 끌어 옮긴 자리를 기억해 두는 파일

# 기호는 png 를 쓰지 않고 코드로 직접 그린다 (symbols.py).
# 그림 파일마다 투명 여백이 제각각(부하 아이콘은 가로의 63%가 빈칸)이라
# 버스에 딱 붙이는 게 불가능했고, 크기를 바꾸면 뭉개졌다.


def _tab(sol, name):
    """케이스 입력 표 하나를 2차원 배열로. 없으면 빈 배열."""
    a = sol.case_tables.get(name)
    if a is None:
        return np.zeros((0, 0))
    a = np.asarray(a, dtype=float)
    if a.ndim == 1:
        a = a.reshape(1, -1)
    return a


def _col(a, i):
    """MATLAB 기준 i번째 열 (1부터). 열이 모자라면 빈 배열."""
    if a.size == 0 or a.shape[1] < i:
        return np.zeros(0)
    return a[:, i - 1]


class Graph:
    """계통도에 그릴 것들 — 점(버스)과 선(선로)."""

    def __init__(self):
        self.keys = []          # 점 이름 ("A3", "D15", "X7")
        self.label = []         # 화면에 적을 글자
        self.kind = []          # "AC" / "DC" / "3권선"
        self.role = []          # "송전" / "동기기" / "IBR" / "3권선" / ""
        self.has_load = []      # 부하가 걸린 버스인가
        self.is_slack = []      # 기준(slack) 버스인가
        self.edges = []         # (점번호, 점번호, 종류)

    def index(self, key):
        try:
            return self.keys.index(key)
        except ValueError:
            return None

    def add(self, key, label, kind):
        self.keys.append(key)
        self.label.append(label)
        self.kind.append(kind)
        self.role.append("")
        self.has_load.append(False)
        self.is_slack.append(False)
        return len(self.keys) - 1


def build_graph(sol):
    """계산 결과와 케이스 입력에서 계통도의 점·선을 만든다."""
    g = Graph()
    if not sol.case_tables:
        return g

    ac = sol.at("AC", 0)
    dc = sol.at("DC", 0)
    ac_num = [int(v) for v in ac[:, 0] if np.isfinite(v)] if ac.size else []
    dc_num = [int(v) for v in dc[:, 0] if np.isfinite(v)] if dc.size else []

    for b in ac_num:
        g.add(f"A{b}", str(b), "AC")

    # 3권선 변압기는 가운데에 점을 하나 두고 세 버스를 그 점에 잇는다
    tw = _tab(sol, "AC_3wtrans_dat")
    tw_on = []
    if tw.size and tw.shape[1] >= 5:
        for r in tw:
            if r[4] != 1:                     # 5열 = 상태
                continue
            if not np.all(np.isfinite(r[:4])):    # NaN 이면 이 변압기만 건너뜀
                continue
            b1, b2, b3 = int(r[1]), int(r[2]), int(r[3])
            key = f"X{int(r[0])}"
            idx = g.add(key, f"3W{int(r[0])}", "3권선")
            g.role[idx] = "3권선"
            tw_on.append((idx, (b1, b2, b3)))

    # DC 버스도 번호만 적는다 — 색(파랑)과 자리(오른쪽 구역)로 이미 DC 인 게 보이므로
    # 앞에 "DC" 를 또 붙이면 글자만 길어진다.
    for b in dc_num:
        g.add(f"D{b}", str(b), "DC")

    # NaN 방어: 수렴 실패나 빈 표 때문에 버스 번호가 NaN 이면 int() 가 터진다.
    # 그런 행은 조용히 건너뛴다(그 요소만 안 그리고, 계통도 자체는 정상적으로
    # 검은 선으로 그려진다 — 사용자 지시: "NaN 이면 그냥 검은색 선로로").
    def a_of(b):
        if b is None or not np.isfinite(b):
            return None
        return g.index(f"A{int(b)}")

    def d_of(b):
        if b is None or not np.isfinite(b):
            return None
        return g.index(f"D{int(b)}")

    # ── 선 ──
    L = _tab(sol, "AC_Line_dat")
    if L.size and L.shape[1] >= 13:
        for r in L:
            if r[12] != 1:                    # 13열 = 연결 상태
                continue
            i, j = a_of(r[1]), a_of(r[2])
            if i is None or j is None or i == j:
                continue
            g.edges.append((i, j, "변압기" if r[11] == 1 else "AC"))

    for idx, buses in tw_on:                  # 3권선 → 세 갈래
        for b in buses:
            j = a_of(b)
            if j is not None:
                g.edges.append((idx, j, "AC"))

    DL = _tab(sol, "DC_Line_dat")
    if DL.size and DL.shape[1] >= 8:
        for r in DL:
            if r[7] != 1:                     # 8열 = 연결 상태
                continue
            i, j = d_of(r[1]), d_of(r[2])
            if i is None or j is None or i == j:
                continue
            g.edges.append((i, j, "DC"))

    IC = _tab(sol, "IC_dat")
    if IC.size and IC.shape[1] >= 16:
        for r in IC:
            if r[15] != 1:                    # 16열 = 상태
                continue
            i, j = a_of(r[0]), d_of(r[1])
            if i is not None and j is not None:
                g.edges.append((i, j, "IC"))

    CV = _tab(sol, "DCDC_Conv_dat")
    if CV.size and CV.shape[1] >= 10:
        for r in CV:
            if not r[9] > 0:                  # 10열 = 운전모드, 0보다 크면 켜짐
                continue
            i, j = d_of(r[0]), d_of(r[1])
            if i is not None and j is not None and i != j:
                g.edges.append((i, j, "DCDC"))

    # ── 점의 성격: 발전기 종류 ──
    # 🚨 AC 와 DC 는 2열(종류)의 번호 뜻이 다르다. MATLAB 원본 두 스크립트가
    # 서로 다르게 읽는다:
    #   ACDC_topology.m 24~25줄 : DC 는 2=동기기, 3=IBR — **1은 아예 안 그린다**
    #   DConly_topology.m 18~19줄: DC 는 2=동기기, **1=IBR**
    # 그런데 실제 케이스 파일의 DC 발전기는 **전부 종류 1**이다
    #   (12버스 9·10 / 71버스 43·52·60·67 / CIGRE 24 — 직접 찍어 확인).
    # 그래서 ACDC_topology.m 을 그대로 따르면 **어느 케이스에서도 DC 발전기가
    # 한 개도 안 그려진다**(사용자 논문 그림엔 DG9·DG10 이 있는데도).
    # ⇒ DConly 쪽 뜻(1=IBR)을 따른다. 물리적으로도 DC 버스에 붙는 전원은
    #    전부 변환기를 거치므로 "송전탑"(교류 계통 연계)은 DC 에서 말이 안 된다.
    # 모르는 번호도 IBR 로 본다 — 안 그리는 것보다 낫다(위 사고의 재발 방지).
    TYPE = {1: "송전", 2: "동기기", 3: "IBR"}
    DC_TYPE = {1: "IBR", 2: "동기기", 3: "IBR"}
    G = _tab(sol, "AC_gen_dat")
    if G.size and G.shape[1] >= 2:
        for r in G:
            if G.shape[1] >= 9 and r[8] != 1:     # 9열 = 상태
                continue
            i = a_of(r[0])
            if i is not None and np.isfinite(r[1]):
                g.role[i] = TYPE.get(int(r[1]), "")
    GD = _tab(sol, "DC_gen_dat")
    if GD.size and GD.shape[1] >= 2:
        for r in GD:
            i = d_of(r[0])
            if i is not None:
                g.role[i] = DC_TYPE.get(int(r[1]), "IBR") if np.isfinite(r[1]) \
                    else "IBR"

    # ── 기준(slack) 버스 ──
    # slack 은 발전기 '종류'(2열)가 아니라 '운전모드'(3열)로 정해진다.
    # 한 버스에 발전기가 여러 대면 모드의 평균이 3일 때 slack
    # (preprocess_AC_gen_ACDC.m 98~104줄과 같은 방식), 꺼진 발전기는 빼고 본다
    # (같은 파일 16~19줄: 9열이 1인 것만 남긴다).
    if G.size and G.shape[1] >= 3:
        modes = {}
        for r in G:
            if G.shape[1] >= 9 and r[8] != 1:
                continue
            if not (np.isfinite(r[0]) and np.isfinite(r[2])):
                continue
            modes.setdefault(int(r[0]), []).append(float(r[2]))
        for b, ms in modes.items():
            i = a_of(b)
            if i is not None and abs(sum(ms) / len(ms) - 3.0) < 1e-9:
                g.is_slack[i] = True

    # DC 쪽 기준은 정전압(CV) 유닛 — 모드 2 (preprocess_DC_gen_ACDC.m 85~91줄).
    # MATLAB 은 이걸 slack 이 아니라 CV 라고 부르지만 전압을 붙잡는 기준 역할은 같다.
    # DC 표엔 상태 열이 없어 거르지 않는다(원본도 안 거른다).
    if GD.size and GD.shape[1] >= 3:
        modes = {}
        for r in GD:
            if not (np.isfinite(r[0]) and np.isfinite(r[2])):
                continue
            modes.setdefault(int(r[0]), []).append(float(r[2]))
        for b, ms in modes.items():
            i = d_of(b)
            if i is not None and abs(sum(ms) / len(ms) - 2.0) < 1e-9:
                g.is_slack[i] = True

    # ── 부하가 걸린 버스 ──
    for tbl, num, of in (("AC_PLoad_dat", ac_num, a_of),
                         ("AC_QLoad_dat", ac_num, a_of),
                         ("DC_PLoad_dat", dc_num, d_of)):
        P = _tab(sol, tbl)
        if P.size == 0:
            continue
        for k, b in enumerate(num):
            if k >= P.shape[0]:
                break
            if np.any(P[k, 1:] != 0):      # 1열은 버스번호라 빼고 본다
                i = of(b)
                if i is not None:
                    g.has_load[i] = True
    return g


# ─────────────────────────────────────────── 위반 보기 (부하율·전압·변환기)
# 계통도가 '위반 보기'로 켜지면, 고른 시간대(t)의 결과에서 세 가지를 뽑아 얹는다.
# 계통 구조(어느 선이 있나)는 시간이 바뀌어도 안 변하고 **값만** 바뀌므로,
# 여기서 t 별로 다시 계산해 색만 갈아입힌다(구조는 build_graph 그대로).
def _busno(key):
    """노드 이름에서 버스 번호. 3권선 가운데점(X..)은 실제 버스가 아니라 None."""
    return int(key[1:]) if key[:1] in ("A", "D") else None


def branch_loading(g, sol, t):
    """시간 t 에서 각 선(edge)의 부하율[%]. **AC·DC 선로만**(IC·DCDC·3권선 제외).
    선을 Branch 표 행과 **출발·도착 버스쌍**으로 짝짓는다(순서 무관, 병렬 선로는
    같은 쌍이 여러 개면 나온 순서대로). 짝을 못 찾은 선은 넣지 않는다 → 중립색.
    (12·71버스로 확인: Branch 표 From/To 가 계통도와 같은 번호를 쓰고,
     IC 는 Branch 표에 없다.)"""
    out = {}
    br = sol.at("Branch", t)
    if not br.size:
        return out
    cols = sol.cols("Branch")
    if "Loading[%]" not in cols or "From" not in cols or "To" not in cols:
        return out
    iF, iT, iL = cols.index("From"), cols.index("To"), cols.index("Loading[%]")
    pool = {}
    for r in br:
        if not (np.isfinite(r[iF]) and np.isfinite(r[iT]) and np.isfinite(r[iL])):
            continue                       # 수렴 실패 등으로 NaN 인 행은 건너뛴다
        k = frozenset((int(r[iF]), int(r[iT])))
        pool.setdefault(k, []).append(float(r[iL]))
    used = {}
    for ei, (a, b, kind) in enumerate(g.edges):
        if kind not in ("AC", "변압기", "DC"):
            continue
        na, nb = _busno(g.keys[a]), _busno(g.keys[b])
        if na is None or nb is None:
            continue
        k = frozenset((na, nb))
        rows = pool.get(k)
        if not rows:
            continue
        j = used.get(k, 0)
        if j < len(rows):
            out[ei] = rows[j]
            used[k] = j + 1
    return out


def _branch_rows(g, sol):
    """각 AC·DC 선(edge) → Branch 표의 '행 번호'. branch_loading 과 똑같은
    From/To 짝짓기를 쓰되, 시간 t 의 값이 아니라 **행 번호**를 돌려준다
    (그 행을 시간축으로 훑으면 24h 부하율이 나온다). 병렬 선로는 나온
    순서대로 다른 행에 짝지어, 두 평행선이 같은 그래프를 안 가리키게 한다."""
    out = {}
    br = sol.at("Branch", 0)
    if not br.size:
        return out
    cols = sol.cols("Branch")
    if "From" not in cols or "To" not in cols:
        return out
    iF, iT = cols.index("From"), cols.index("To")
    pool = {}
    for ri, r in enumerate(br):
        if not (np.isfinite(r[iF]) and np.isfinite(r[iT])):
            continue
        pool.setdefault(frozenset((int(r[iF]), int(r[iT]))), []).append(ri)
    used = {}
    for ei, (a, b, kind) in enumerate(g.edges):
        if kind not in ("AC", "변압기", "DC"):
            continue
        na, nb = _busno(g.keys[a]), _busno(g.keys[b])
        if na is None or nb is None:
            continue
        k = frozenset((na, nb))
        rows = pool.get(k)
        if not rows:
            continue
        j = used.get(k, 0)
        if j < len(rows):
            out[ei] = rows[j]
            used[k] = j + 1
    return out


def loading_series(g, sol, edge_index):
    """한 선(edge)의 **시간별 부하율[%]**. (시간목록, 값목록) 을 돌려준다.
    시간은 1..T 시(H). Branch 표에서 못 찾는 선(변환기·3권선 지선 등)은 None.

    branch_loading 이 시각 하나의 값을 주는 것과 달리, 여기서는 그 선이
    짝지어진 Branch 행을 시간축(3차원의 T)으로 통째로 읽는다."""
    ri = _branch_rows(g, sol).get(edge_index)
    if ri is None:
        return None
    cols = sol.cols("Branch")
    if "Loading[%]" not in cols:
        return None
    iL = cols.index("Loading[%]")
    arr = sol.Branch
    if arr.ndim == 3:
        vals = arr[ri, iL, :]
    elif arr.ndim == 2:
        vals = np.array([arr[ri, iL]])
    else:
        return None
    vals = [float(v) for v in vals]
    if not vals or not all(np.isfinite(v) for v in vals):
        # 수렴 실패로 NaN 이 섞이면 그 지점은 빼되, 전부 NaN 이면 없는 것
        pairs = [(k + 1, v) for k, v in enumerate(vals) if np.isfinite(v)]
        if not pairs:
            return None
        return [k for k, _ in pairs], [v for _, v in pairs]
    return list(range(1, len(vals) + 1)), vals


def edge_label(g, edge_index):
    """선(edge) 을 부를 이름 — 'AC 3–7 선로' 꼴. 없는 번호면 노드 키로."""
    a, b, kind = g.edges[edge_index]
    side = "DC" if g.kind[a] == "DC" and g.kind[b] == "DC" else "AC"
    na, nb = _busno(g.keys[a]), _busno(g.keys[b])
    if na is not None and nb is not None:
        return f"{side} {na}–{nb} 선로"
    return f"{g.label[a]}–{g.label[b]} 선로"


def voltage_bad(g, sol, t):
    """시간 t 의 전압 위반 버스 → {노드 인덱스: 방향}. 방향 +1=과전압(Vmax 초과),
    -1=저전압(Vmin 미달). AC·DC 둘 다 본다(같은 열 이름 VM[pu]·Vmin[pu]·Vmax[pu]
    를 쓴다 — app_engine COLUMNS 확인). 방향은 화살표 표시 옵션에 쓴다."""
    bad = {}
    for which, pref in (("AC", "A"), ("DC", "D")):
        arr = sol.at(which, t)
        if not arr.size:
            continue
        cols = sol.cols(which)
        if not all(x in cols for x in ("Bus", "VM[pu]", "Vmin[pu]", "Vmax[pu]")):
            continue
        iB, iV = cols.index("Bus"), cols.index("VM[pu]")
        iLo, iHi = cols.index("Vmin[pu]"), cols.index("Vmax[pu]")
        for r in arr:
            if not (np.isfinite(r[iB]) and np.isfinite(r[iV])
                    and np.isfinite(r[iLo]) and np.isfinite(r[iHi])):
                continue                   # NaN(수렴 실패 등)은 위반 판정 안 함
            v, lo, hi = float(r[iV]), float(r[iLo]), float(r[iHi])
            if v > hi or v < lo:
                idx = g.index(f"{pref}{int(r[iB])}")
                if idx is not None:
                    bad[idx] = 1 if v > hi else -1
    return bad


def ic_bad(g, sol):
    """한계에 닿은 변환기(IC) edge 인덱스 집합. IC_lim_mode 는 변환기당 값 하나뿐
    (2=용량곡선 도달·3=전류한계 도달)이라 **시간축을 안 탄다** — 부하율과 달리
    시간을 바꿔도 그대로다. IC edge 를 나온 순서대로 IC_lim_mode 와 짝짓는다."""
    modes = list(sol.IC_lim_mode or [])
    bad = set()
    k = 0
    for ei, (a, b, kind) in enumerate(g.edges):
        if kind != "IC":
            continue
        if k < len(modes) and np.isfinite(modes[k]) and int(round(modes[k])) in (2, 3):
            bad.add(ei)
        k += 1
    return bad


def make_overlay(g, sol, t):
    """위반 보기용 한 벌 — 선 부하율·전압위반 버스·한계 변환기."""
    return {"load": branch_loading(g, sol, t),
            "vbad": voltage_bad(g, sol, t),
            "icbad": ic_bad(g, sol)}


# ─────────────────────────────────────────── 자리 잡기 (층으로 나눠서)
def _side(g, i):
    """이 버스가 AC 쪽인가 DC 쪽인가. 3권선은 AC 쪽으로 본다."""
    return "DC" if g.kind[i] == "DC" else "AC"


def layered_layout(g):
    """논문 계통도처럼 — AC 구역과 DC 구역을 갈라 놓고, 각 구역 안에서
    뿌리 버스부터 층을 세어 왼쪽에서 오른쪽으로 늘어놓는다.

    서로 밀어내는 방식(spring)은 그물 모양엔 맞지만 단선도로는 어수선하다.
    층으로 나누면 선이 가로·세로로만 흘러 도면처럼 보인다.
    """
    n = len(g.keys)
    pos = np.zeros((n, 2))
    if n == 0:
        return pos

    groups = {"AC": [i for i in range(n) if _side(g, i) == "AC"],
              "DC": [i for i in range(n) if _side(g, i) == "DC"]}

    # 같은 구역 안에서만 이웃으로 친다 (IC 는 구역을 잇는 다리라 뺀다)
    adj = {i: set() for i in range(n)}
    for a, b, kind in g.edges:
        if kind in ("IC",):
            continue
        if _side(g, a) == _side(g, b):
            adj[a].add(b); adj[b].add(a)

    # IC 가 붙은 버스 — 각 구역의 '문' 이라 층 세기의 출발점으로 좋다
    ic_ac, ic_dc = set(), set()
    for a, b, kind in g.edges:
        if kind == "IC":
            (ic_ac if _side(g, a) == "AC" else ic_dc).add(a)
            (ic_dc if _side(g, b) == "DC" else ic_ac).add(b)

    layers = {}
    for name, members in groups.items():
        if not members:
            continue
        # 뿌리 = IC 가 붙은 버스. 양쪽 구역 모두 여기서 층을 센다.
        # 그러면 IC 버스가 0층이 되고, AC 는 0층을 오른쪽 끝에 DC 는 왼쪽 끝에
        # 놓으므로 두 구역이 마주 보게 되어 IC 선이 짧아진다.
        gate = ic_dc if name == "DC" else ic_ac
        roots = [i for i in members if i in gate]
        if not roots:
            # IC 가 없는 구역(AC-only 등): **한 버스에서만** 층을 센다.
            # 예전엔 발전기 버스를 전부 뿌리로 썼는데, pandapower 처럼 대부분의
            # 버스에 발전기가 달린 계통은 15개가 다 0층이 되어 한 열에 쌓였다
            # (막대가 붙어 한 줄로 보임). 뿌리는 슬랙 하나 → 없으면 가장 끝
            # (연결 적은) 버스 하나. 그래야 전기적 거리대로 여러 열로 퍼진다.
            slacks = [i for i in members if g.is_slack[i]]
            roots = slacks[:1] or [min(members, key=lambda i: len(adj[i]) or 99)]

        depth = {}
        queue = [(r, 0) for r in roots]
        for r in roots:
            depth[r] = 0
        head = 0
        while head < len(queue):
            i, d = queue[head]; head += 1
            for j in adj[i]:
                if j not in depth:
                    depth[j] = d + 1
                    queue.append((j, d + 1))
        for i in members:                    # 어디에도 안 붙은 버스
            depth.setdefault(i, 0)
        layers[name] = depth

    # 구역별로 층을 열로 묶는다. AC 는 왼쪽 DC 는 오른쪽에 놓는다.
    # 0~1 을 꽉 채운다 — 발전기 기호가 들어갈 왼쪽 자리는 여기서 비율로 빼지 않고
    # 그릴 때 픽셀 여백(TopologyView._pads)으로 준다. 비율로 빼면 계통이 클수록
    # 여백도 같이 커진다.
    # 한쪽 구역만 있으면(AC-only·DC-only) 그 구역이 **전체 폭**을 쓴다. 안 그러면
    # AC-only 가 왼쪽 44% 에만 눌려 열 간격이 좁아지고 기호·선이 겹친다(3W 케이스).
    has_ac, has_dc = bool(groups["AC"]), bool(groups["DC"])
    if has_ac and has_dc:
        BOX = {"AC": (0.0, 0.44), "DC": (0.56, 1.0)}
    else:
        BOX = {"AC": (0.0, 1.0), "DC": (0.0, 1.0)}
    cols = {}
    for name, members in groups.items():
        if not members:
            continue
        depth = layers[name]
        cols[name] = {}
        for i in sorted(members, key=lambda k: (depth[k], k)):
            cols[name].setdefault(depth[i], []).append(i)

    # IC 로 이어진 AC·DC 버스를 같은 높이에 놓는다 — 그래야 다리가 곧게 간다.
    # 두 경계 열(양쪽 0층)에서, DC 쪽 순서를 짝인 AC 버스의 순서에 맞춰 다시 세운다.
    mate = {}
    for a, b, kind in g.edges:
        if kind == "IC":
            ai, di = (a, b) if _side(g, a) == "AC" else (b, a)
            mate[di] = ai
    if 0 in cols.get("AC", {}) and 0 in cols.get("DC", {}):
        rank = {i: k for k, i in enumerate(cols["AC"][0])}
        cols["DC"][0].sort(key=lambda i: (rank.get(mate.get(i, -1), 99), i))

    for name, per_depth in cols.items():
        maxd = max(per_depth) if per_depth else 0
        x0, x1 = BOX[name]
        for d, items in per_depth.items():
            frac = 0.0 if maxd == 0 else d / maxd
            if name == "AC":
                frac = 1.0 - frac        # AC 는 0층(IC 쪽)이 오른쪽 끝
            x = x0 + (x1 - x0) * frac
            m = len(items)
            for k, i in enumerate(items):
                y = 0.5 if m == 1 else 0.06 + 0.88 * k / (m - 1)
                pos[i] = [x, y]

    return pos


# ─────────────────────────────────────────── 옮긴 자리 기억하기
def load_places(case_name):
    try:
        return json.loads(PLACES.read_text(encoding="utf-8")).get(case_name, {})
    except Exception:
        return {}


def save_places(case_name, places):
    try:
        all_of = json.loads(PLACES.read_text(encoding="utf-8"))
    except Exception:
        all_of = {}
    all_of[case_name] = places
    try:
        PLACES.write_text(json.dumps(all_of, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ─────────────────────────────────────────── 그리기
from PySide6.QtCore import Qt, QPointF, QRectF                  # noqa: E402
from PySide6.QtGui import (QPainter, QPen, QColor, QFont,       # noqa: E402
                           QFontMetrics, QPainterPath, QPolygonF)
from PySide6.QtWidgets import (QFrame, QScrollArea, QSizePolicy,  # noqa: E402
                               QToolTip, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel)

import symbols                                                   # noqa: E402

# 부하가 걸린 버스에 오른쪽 화살표를 그릴지. 끈 이유는 **거의 모든 버스에 붙어서**다
# — 71버스는 71개 중 65개(92%), CIGRE 60%, 12버스 42%. 거의 다 붙으면 구별 정보가
# 아니라 잡음이 되고, 선 따라가기를 방해한다. 부하 값은 결과 표에 다 있다.
SHOW_LOAD_ARROWS = False

BUS_AC = "#d62728"        # 논문 그림과 같은 빨강/파랑
BUS_DC = "#1f5fd0"
# 기준(slack) 버스 강조색 — 막대 자체를 이 색으로 칠한다. 일반 빨강/파랑과
# 확실히 다르면서, 따뜻한색(호박)=AC · 차가운색(청록)=DC 로 AC/DC 도 유지된다.
# 위반 자홍(VIO_ACCENT)·IC 주황·DCDC 보라와도 겹치지 않게 골랐다.
SLACK_AC = "#e08a1e"      # 호박(amber)
SLACK_DC = "#12a89a"      # 청록(teal)
WIRE = "#2b3440"
IC_COLOR = "#c2570e"
DCDC_COLOR = "#7a3fb8"

# 위반 보기에서 선 색 — 부하율[%]을 신호등처럼. 낮음=초록, 100% 부근=주황,
# 초과=빨강(부하율 그래프 loading_chart 의 "100% 초과=경고색"과 뜻을 맞춘다).
_HEAT_STOPS = [(0.0, (0x2e, 0x9e, 0x5b)),      # 여유 — 초록
               (0.60, (0x9a, 0xc7, 0x3a)),     # 연두
               (0.85, (0xf0, 0xa8, 0x1e)),     # 노랑-주황
               (1.00, (0xe0, 0x6c, 0x12))]     # 꽉참 — 주황
HEAT_OVER = "#d1342f"     # 100% 초과 — 빨강
# 전압위반·변환기한계 표시색 — 과부하 빨강·IC 주황·DCDC 보라와 겹치지 않게
# 자홍(마젠타)으로. 신호등 색 계열이 아니라 "다른 종류의 경고"로 읽힌다.
VIO_ACCENT = "#d61f8f"


def heat(pct):
    """부하율[%] → 색(#rrggbb). 100% 를 넘으면 빨강으로 못 박는다."""
    if pct > 100.0:
        return HEAT_OVER
    x = max(0.0, min(1.0, pct / 100.0))
    for k in range(len(_HEAT_STOPS) - 1):
        x0, c0 = _HEAT_STOPS[k]
        x1, c1 = _HEAT_STOPS[k + 1]
        if x <= x1:
            f = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
            r = round(c0[0] + (c1[0] - c0[0]) * f)
            gg = round(c0[1] + (c1[1] - c0[1]) * f)
            bb = round(c0[2] + (c1[2] - c0[2]) * f)
            return f"#{r:02x}{gg:02x}{bb:02x}"
    return HEAT_OVER


class TopologyView(QFrame):
    """계통 단선도 — 논문 계통도 짜임새.

    버스는 굵은 세로 막대(빨강 AC · 파랑 DC), 선은 가로·세로로만 꺾인다.
    AC 는 왼쪽 DC 는 오른쪽에 놓이고 그 사이를 IC 가 잇는다. 구역을 두르는
    상자는 그리지 않는다 — 색(빨강/파랑)만으로 어느 쪽인지 이미 보인다.
    버스를 마우스로 끌어 옮길 수 있고, 옮긴 자리는 케이스별로 기억한다.
    """

    PAD = 30

    # 확대·축소 (2026-08-19 사용자 요청). 한 번에 이만큼씩 · 이 안에서만.
    ZOOM_STEP = 1.25
    ZOOM_MIN = 0.5
    ZOOM_MAX = 4.0

    def __init__(self, g, places, case_name, c, on_move=None,
                 show_violations=False, overlay=None,
                 vstyle="badge", cstyle="badge", on_line_click=None,
                 zoom=1.0, on_zoom=None):
        super().__init__()
        self.setObjectName("plot")
        self.g, self.c, self.case_name = g, c, case_name
        self.on_move = on_move
        # 선로를 클릭하면 부르는 콜백 (g, edge_index) — 앱이 24h 부하율 팝업을 띄운다
        self.on_line_click = on_line_click
        self._routes = []        # 마지막으로 그린 선들의 길 (선로 클릭 판정용)
        self._press = None       # (edge_index, 누른 좌표) — 눌렀다 뗐을 때 클릭 판정
        self.show_violations = show_violations
        # overlay = {"load": {edge_i: %}, "vbad": {node_i: ±1}, "icbad": {edge_i}}
        self.overlay = overlay or {"load": {}, "vbad": {}, "icbad": set()}
        # 전압 위반 표시 방식: "halo"(후광)·"badge"(경고 삼각형)·"arrow"(과/저전압 화살표)
        # 변환기 한계 표시 방식: "recolor"(기호 색)·"badge"(삼각형)·"ring"(고리)
        self.vstyle = vstyle
        self.cstyle = cstyle
        # 🚨 배율은 **앱이 들고 있다가 다시 넘겨준다** — 이 위젯은 계산할 때마다
        #    새로 만들어지므로(`topology_view`), 여기에만 두면 계산 한 번에 1.0 으로
        #    돌아가 버린다(그래프 접기·정렬을 앱 상태로 둔 것과 같은 까닭).
        self.zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, float(zoom)))
        self.on_zoom = on_zoom
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(300)
        self.setMouseTracking(True)
        self.pos = layered_layout(g)
        for i, key in enumerate(g.keys):
            if key in places:
                self.pos[i] = places[key]
        self.drag = None
        self._fit()

    def set_zoom(self, z, from_user=True):
        """배율을 바꾼다. 그림만 다시 그리고 **화면을 통째로 다시 만들지 않는다**."""
        z = max(self.ZOOM_MIN, min(self.ZOOM_MAX, float(z)))
        if abs(z - self.zoom) < 1e-9:
            return False
        self.zoom = z
        self._fit()
        self.updateGeometry()
        self.update()
        if from_user and self.on_zoom is not None:
            self.on_zoom(z)
        return True

    def wheelEvent(self, ev):
        """Ctrl(맥은 ⌘)을 누른 채 굴리면 확대·축소. 그냥 굴리면 화면이 밀린다."""
        mod = ev.modifiers()
        if not (mod & Qt.ControlModifier or mod & Qt.MetaModifier):
            ev.ignore()                  # 스크롤 상자가 받아 밀게 둔다
            return
        step = ev.angleDelta().y()
        if step:
            self.set_zoom(self.zoom * (self.ZOOM_STEP if step > 0
                                       else 1 / self.ZOOM_STEP))
        ev.accept()

    def _fit(self):
        """열·행 수만큼 최소 크기를 잡는다. 화면보다 크면 스크롤바가 생긴다.

        폭을 화면에 억지로 맞추면 긴 계통(71버스는 열이 38개)이 열당 26px 로
        눌려 막대와 번호가 겹친다. 그래서 **줄이지 않고 넘치게** 두고 밀어 본다.

        다만 **꼭 필요한 만큼만** 요구한다. 처음엔 행당 u*3.4 를 잡았다가
        25버스(5행)가 630px 을 요구해 391px 짜리 화면에서 세로로도 잘렸다.
        한 행에 실제로 필요한 건 버스 막대(u*1.25) + 번호(15) + 숨 쉴 틈이다.
        """
        u = self.unit()
        col = {}
        for i in range(len(self.g.keys)):
            k = round(float(self.pos[i][0]), 3)
            col[k] = col.get(k, 0) + 1
        ncol = max(1, len(col))
        nrow = max(1, max(col.values()) if col else 1)
        L, m = self._pads()
        self.setMinimumWidth(int(L + m + ncol * u * 2.9))
        self.setMinimumHeight(int(2 * m + nrow * (u * 1.25 + 20)))

    def _pads(self):
        """(왼쪽 여백, 나머지 여백) — 픽셀.

        왼쪽만 넉넉한 이유는 발전기 기호가 버스 **왼쪽**에 달리기 때문이고,
        딱 그만큼만 준다 — 잇는 선(u*0.62) + 기호(u*1.05) + 여유(u*0.32) ≈ u*2.
        여백을 폭의 비율(예전 0.09)로 잡으면 **계통이 클수록 여백도 같이 커져서**
        71버스에서는 왼쪽이 200px 넘게 비었다. 그래서 픽셀로 고정한다.
        (u*1.9 로 잡았다가 3px 모자라 발전기가 전부 아래로 매달렸다.)
        """
        return max(44.0, self.unit() * 2.1), float(self.PAD)

    def _px(self):
        L, m = self._pads()
        w = max(1, self.width() - L - m)
        h = max(1, self.height() - 2 * m)
        return (self.pos * np.array([w, h])) + np.array([L, m])

    def unit(self):
        """기호 하나의 기준 크기. **버스가 많을수록 줄인다**(사용자 확정).

        가로 스크롤이 생겼으니 안 줄여도 되지 않냐는 얘기가 나왔지만,
        큰 계통을 큰 기호로 그리면 그림이 옆으로 한없이 길어져 한눈에 안 들어온다
        → 지금대로 줄이기로 확정.
        실제 값: 12버스·CIGRE 25버스 = 30(상한) / 71버스 = 20.2 / 239버스부터 11(하한).
        """
        n = max(1, len(self.g.keys))
        base = max(11.0, min(30.0, 170.0 / np.sqrt(n)))
        # 배율은 **자동으로 정한 크기 위에** 얹는다. 이 값 하나가 기호 크기와
        # `_fit()` 의 최소 크기를 함께 정하므로, 여기만 곱하면 그림 전체가 커진다
        # (클릭·끌기도 같은 `_px()`·`unit()` 을 쓰므로 따라온다).
        return base * getattr(self, "zoom", 1.0)

    def bar_h(self):
        return self.unit() * 1.25          # 버스 막대 길이

    # ── 두 버스를 가로·세로로만 잇는 길 ──
    def _route(self, a, b, xy):
        xa, ya = xy[a]
        xb, yb = xy[b]
        if abs(ya - yb) < 1.5:                       # 같은 높이 → 곧게
            return [(xa, ya), (xb, yb)]
        gap = self.unit() * 0.55
        if abs(xa - xb) < 1.5:                       # 같은 세로줄 → 옆으로 돌아서
            off = xa + gap * 1.6
            return [(xa, ya), (off, ya), (off, yb), (xb, yb)]
        sa = gap if xb > xa else -gap
        mid = (xa + sa + xb - sa) / 2.0
        return [(xa, ya), (mid, ya), (mid, yb), (xb, yb)]

    @staticmethod
    def _bar(p, x, y, color, w, h):
        """지정한 색·폭·높이로 버스 막대 하나를 그린다."""
        pen = QPen(QColor(color)); pen.setWidthF(w)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x, y - h / 2), QPointF(x, y + h / 2))

    @staticmethod
    def _seg_box(a, b, w):
        """선분을 얇은 네모로. 선이 전부 가로 아니면 세로라 이렇게 해도 정확하다."""
        x0, x1 = (a[0], b[0]) if a[0] <= b[0] else (b[0], a[0])
        y0, y1 = (a[1], b[1]) if a[1] <= b[1] else (b[1], a[1])
        return QRectF(x0 - w, y0 - w, (x1 - x0) + 2 * w, (y1 - y0) + 2 * w)

    def _edge_layout(self, xy):
        """선을 어떻게 이을지 미리 계산한다. (half, attach, routes, vsegs) 반환.

        - half[i]: 버스 막대 절반 길이(연결 수에 비례 — 선을 막대의 서로 다른
          높이에 나눠 붙일 자리를 준다).  3권선 노드는 아이콘 크기만큼만.
        - attach[(i,ei)]: 선 ei 가 버스 i 막대에 붙는 y. 변압기·IC·DC/DC 같은
          '선로 위 소자'는 양끝을 같은 높이로(곧은 선), 나머지는 나눠 붙인다.
        - routes[ei]: 가로·세로로만 꺾는 길. 세로 구간 x 는 겹치는 것끼리 벌린다.
        - vsegs: 모든 세로 구간 (가로선이 이 위를 지날 때 점프시키려고).
        """
        n = len(self.g.keys)
        u = self.unit()
        inc = {i: [] for i in range(n)}
        for ei, (a, b, k) in enumerate(self.g.edges):
            inc[a].append((ei, b)); inc[b].append((ei, a))
        half = {}
        for i in range(n):
            if self.g.role[i] == "3권선":
                half[i] = u * 0.55
            else:
                half[i] = max(u * 0.70, min(u * 1.60, u * 0.45 * len(inc[i])))
        center = {i: float(xy[i][1]) for i in range(n)}
        DEV = ("변압기", "IC", "DCDC")
        # '곧게 그릴' 선 = 소자(변압기·IC·DC/DC) + **같은 높이의 두 버스를 잇는
        # 수평선**. 후자를 막대에 나눠 붙이면 같은 높이인데도 계단처럼 꺾인다
        # (71버스 윗줄 12~17 체인이 그랬다). 같은 높이면 그 높이로 곧게 잇고,
        # 진짜 위·아래로 벌어진 선만 막대에 나눠 붙인다.
        def _is_straight(a, b, k):
            if k in DEV:
                return True
            return (abs(float(xy[a][0]) - float(xy[b][0])) >= 2.0
                    and abs(center[a] - center[b]) < u * 0.30)

        attach = {}
        rng = {}      # (i, ei) → 이 끝이 위아래로 비켜도 되는 범위 (자기 슬롯 안)
        straight = set()
        for ei, (a, b, k) in enumerate(self.g.edges):
            if not _is_straight(a, b, k):
                continue
            straight.add(ei)
            lo = max(center[a] - half[a], center[b] - half[b]) + u * 0.12
            hi = min(center[a] + half[a], center[b] + half[b]) - u * 0.12
            if lo <= hi:
                y = min(hi, max(lo, (center[a] + center[b]) / 2))
                attach[(a, ei)] = y; attach[(b, ei)] = y
                rng[(a, ei)] = (lo, hi); rng[(b, ei)] = (lo, hi)
            else:
                attach[(a, ei)] = center[a]; attach[(b, ei)] = center[b]
                rng[(a, ei)] = (center[a], center[a])
                rng[(b, ei)] = (center[b], center[b])
        for i in range(n):
            rest = sorted([(ei, o) for (ei, o) in inc[i] if ei not in straight],
                          key=lambda t: center[t[1]])
            d = len(rest); L = 2 * half[i]; y0 = center[i] - half[i]
            step = L / max(1, d)
            for j, (ei, o) in enumerate(rest):
                attach[(i, ei)] = y0 + (j + 0.5) * step
                lo, hi = y0 + j * step + 2.0, y0 + (j + 1) * step - 2.0
                if lo > hi:                       # 슬롯이 아주 좁으면 못 움직임
                    lo = hi = attach[(i, ei)]
                rng[(i, ei)] = (lo, hi)

        # ── 가로 구간 겹침 벌리기 ──
        # 세로 구간은 아래 '레인 나누기'가 벌려 주지만, 가로 구간은 서로 다른
        # 막대에 붙는 높이가 우연히 같으면 그대로 포개졌다(21버스 4-5와 4-6).
        # 더 나쁜 건 살짝 어긋난 채 x 로 이어 붙는 경우 — 11-12와 14-15가
        # 5px 차이로 맞닿아 "11이 15에 연결된 것"처럼 읽혔다. 그래서 가로
        # 구간도 겹치거나 이어져 보이는 것끼리, 자기 슬롯(그 선이 막대에서
        # 차지한 구간) 안에서 위아래로 비켜 준다. 꺾임 x 는 아직 모르는
        # 시점이라(레인 나누기 전) 두 막대의 중간으로 어림잡는다 — 그래서
        # 겹침 판정에 여유(8px)를 두고, 어긋남은 그 여유가 흡수한다.
        # ⚠️ 벌리는 간격은 '선 굵기'가 아니라 그 구간이 실제로 차지하는 '세로
        # 높이'로 잡는다. 병렬 IC 처럼 한 구간 위에 변환기 기호(≈u*1.0)가 얹히면,
        # 선만 7px 벌려선 기호끼리 겹쳐 한 덩어리로 보인다(38-39 병렬 3IC).
        # → 소자(변압기·IC·DC/DC) 구간은 '기호 절반+여유', 보통 선은 얇게 준다.
        def _seg_pad(ei):
            k = self.g.edges[ei][2]
            if k == "변압기":
                return u * 0.92 * 1.25 / 2 + u * 0.12
            if k in ("IC", "DCDC"):
                return u * 0.80 * 1.25 / 2 + u * 0.12
            return max(3.5, u * 0.18)

        hsegs = []            # [y, x0, x1, 움직일 끝들, ei, pad]
        for ei, (a, b, k) in enumerate(self.g.edges):
            xa, xb = float(xy[a][0]), float(xy[b][0])
            ya, yb = attach[(a, ei)], attach[(b, ei)]
            same = abs(xa - xb) < 2.0
            vx = (xa + u * 1.5) if same else (xa + xb) / 2.0
            pad = _seg_pad(ei)
            if abs(ya - yb) < 1.0 and not same:        # 곧은 선 — 양끝이 함께 움직임
                hsegs.append([ya, min(xa, xb), max(xa, xb),
                              [(a, ei), (b, ei)], ei, pad])
            else:
                hsegs.append([ya, min(xa, vx), max(xa, vx), [(a, ei)], ei, pad])
                hsegs.append([yb, min(vx, xb), max(vx, xb), [(b, ei)], ei, pad])
        placedH = []          # (y, x0, x1, ei, pad)
        nodes_of = [set(e[:2]) for e in self.g.edges]

        def _h_clash(x0, x1, ei, pad, cy):
            """cy 에 놓으면 겹치는 이미 놓인 구간 개수. 벌릴 최소 간격은
            두 구간의 pad 합(각자 세로 높이의 절반) 이다."""
            n_bad = 0
            for (py, px0, px1, pei, ppad) in placedH:
                if pei == ei:
                    continue
                if min(x1, px1) - max(x0, px0) <= -8.0:
                    continue
                # 같은 버스 막대의 x 에서 양옆으로 갈리는 두 선은 겹침이 아니다
                # (CIGRE D18 양옆). 단 중간 통로에서 만나면 진짜 겹침(21버스 4-5/4-6).
                sh = nodes_of[ei] & nodes_of[pei]
                if sh:
                    xs = float(xy[next(iter(sh))][0])
                    if (min(abs(x0 - xs), abs(x1 - xs)) < 3.0
                            and min(abs(px0 - xs), abs(px1 - xs)) < 3.0
                            and min(x1, px1) - max(x0, px0) < 3.0):
                        continue
                if abs(py - cy) < pad + ppad - 0.5:
                    n_bad += 1
            return n_bad

        for seg in sorted(hsegs, key=lambda s: (s[0], s[1])):
            y, x0, x1, ends, ei, pad = seg
            lo = max(rng[e][0] for e in ends)
            hi = min(rng[e][1] for e in ends)
            if lo > hi:
                lo = hi = y
            # 이상적 y 와, 이미 놓인 구간 '바로 바깥' 후보들 중에서 겹침 없고
            # y 에 가장 가까운 자리를 고른다(다 겹치면 가장 덜 겹치는 자리).
            cands = [y]
            for (py, px0, px1, pei, ppad) in placedH:
                cands.append(py + pad + ppad)
                cands.append(py - pad - ppad)
            best = None
            for cc in sorted(set(cands), key=lambda cc: abs(cc - y)):
                cc = min(max(cc, lo), hi)
                nb = _h_clash(x0, x1, ei, pad, cc)
                if nb == 0:
                    best = (0, cc); break
                if best is None or nb < best[0]:
                    best = (nb, cc)
            cy = best[1] if best else min(max(y, lo), hi)
            for e in ends:
                attach[e] = cy
            placedH.append((cy, x0, x1, ei, pad))

        sep = max(7.0, u * 0.42)
        geo = []
        for ei, (a, b, k) in enumerate(self.g.edges):
            xa, xb = float(xy[a][0]), float(xy[b][0])
            ya, yb = attach[(a, ei)], attach[(b, ei)]
            same = abs(xa - xb) < 2.0
            base = (xa + u * 1.5) if same else (xa + xb) / 2.0
            geo.append((xa, xb, ya, yb, same, base, min(ya, yb), max(ya, yb)))
        vxs = [gg[5] for gg in geo]
        placed = []
        for i in sorted(range(len(geo)), key=lambda i: (geo[i][5], geo[i][6])):
            base, y0, y1 = geo[i][5], geo[i][6], geo[i][7]
            chosen = base
            for kk in range(80):
                got = False
                for cx in ([base] if kk == 0 else [base + kk * sep, base - kk * sep]):
                    if all(abs(px - cx) >= sep - 1 or y1 < q0 - 3 or y0 > q1 + 3
                           for (px, q0, q1) in placed):
                        chosen = cx; got = True; break
                if got:
                    break
            vxs[i] = chosen
            placed.append((chosen, y0, y1))
        routes, vsegs = [], []
        for ei, (xa, xb, ya, yb, same, base, y0, y1) in enumerate(geo):
            if abs(ya - yb) < 1.0 and not same:
                pts = [(xa, ya), (xb, yb)]
            else:
                pts = [(xa, ya), (vxs[ei], ya), (vxs[ei], yb), (xb, yb)]
            routes.append(pts)
            for kk in range(len(pts) - 1):
                (px0, py0), (px1, py1) = pts[kk], pts[kk + 1]
                if abs(px0 - px1) < 0.5 and abs(py0 - py1) >= 0.5:
                    vsegs.append((px0, min(py0, py1), max(py0, py1)))
        return half, attach, routes, vsegs

    def _edge_path(self, pts, vsegs, R):
        """길(pts)을 그릴 QPainterPath. 가로 구간이 세로선을 지나면 반원으로 점프.

        점프 = '여기서 안 닿고 넘어간다(연결 아님)' 표시. 연결은 막대에 닿는 것.
        """
        path = QPainterPath(QPointF(*pts[0]))
        for k in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[k], pts[k + 1]
            if abs(y0 - y1) < 0.5 and abs(x0 - x1) >= 0.5:      # 가로 → 점프
                a, b = (x0, x1) if x0 <= x1 else (x1, x0)
                cross = sorted(vx0 for (vx0, q0, q1) in vsegs
                               if a + R < vx0 < b - R and q0 + 1.5 < y0 < q1 - 1.5)
                seq = cross if x0 <= x1 else list(reversed(cross))
                degs = range(0, 181, 18) if x0 <= x1 else range(180, -1, -18)
                for vx0 in seq:
                    path.lineTo(QPointF(vx0 + (-R if x0 <= x1 else R), y0))
                    for dd in degs:
                        ang = dd * np.pi / 180.0
                        path.lineTo(QPointF(vx0 - R * np.cos(ang), y0 - R * np.sin(ang)))
                path.lineTo(QPointF(x1, y1))
            else:
                path.lineTo(QPointF(x1, y1))
        return path

    def paintEvent(self, ev):
        c = self.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(c["plot"]))
        if not self.g.keys:
            p.end(); return
        xy = self._px()
        u = self.unit()
        bh = self.bar_h()
        lw = max(1.1, u * 0.07)
        f = QFont(); f.setPointSize(max(7, min(12, int(u * 0.46))))
        p.setFont(f)
        fm = QFontMetrics(f)

        # ── 자리를 먼저 다 정한다 ──
        # 발전기 기호는 마지막에 놓는데, 그때 **선·부하·번호·다른 기호를 전부
        # 피할 수 있어야** 한다. 예전엔 버스 막대만 봐서 세로선이 기호를 관통했다.
        half, attach, routes, vsegs = self._edge_layout(xy)
        self._routes = routes            # 선로 클릭 판정에 쓴다(그린 그대로)
        R_hop = max(3.5, u * 0.17)       # 점프(반원) 반지름
        taken = []                       # 이미 자리를 차지한 것들
        for pts in routes:
            for k in range(len(pts) - 1):
                taken.append(self._seg_box(pts[k], pts[k + 1], 1.5))
        bars = []
        for i in range(len(self.g.keys)):
            x, y = float(xy[i][0]), float(xy[i][1])
            hb = half[i]                                      # 연결 수에 비례한 막대
            bars.append(QRectF(x - u * 0.35, y - hb, u * 0.7, 2 * hb))
            if SHOW_LOAD_ARROWS and self.g.has_load[i]:
                taken.append(QRectF(x, y + bh * 0.30 - u * 0.20,
                                    u * 1.30, u * 0.40))
        edge_sym = []
        for ei, ((a, b, kind), pts) in enumerate(zip(self.g.edges, routes)):
            spec = symbols.EDGE_DRAW.get(kind)
            if spec is None:
                continue
            fn, scale = spec
            mx, my = self._midpoint(pts)
            s = u * scale * 1.25
            edge_sym.append((ei, fn, mx, my, s, kind))
            taken.append(QRectF(mx - s / 2, my - s / 2, s, s))

        # 발전기 기호 → 버스 번호 순으로 빈자리를 잡는다. 번호를 먼저 위에 고정해
        # 두면 기호가 위로 갈 때 **잇는 선이 번호를 뚫고** 지나간다(35·36번에서 발생).
        src = {}
        for i in range(len(self.g.keys)):
            # 기준 버스는 아이콘을 안 붙인다 — 막대 자체를 다르게 그려서 표시한다
            if self.g.is_slack[i] or self.g.role[i] not in ("송전", "동기기", "IBR"):
                continue
            x, y = float(xy[i][0]), float(xy[i][1])
            # 🚨 **자기 버스 막대는 빼고** 본다. 안 빼면 좌우 자리는 여유폭이
            # 막대에 살짝 닿아 점수를 먹고 위아래만 0점이 되어, 발전기가 전부
            # 버스에 매달린 모양이 된다(논문 그림은 옆으로 붙인다).
            where, rect, box = self._place_source(
                x, y, u, 2 * half[i], taken + [r for k, r in enumerate(bars) if k != i],
                self.g.role[i])
            src[i] = (where, rect)
            taken.append(box)
            # 기호와 버스를 잇는 선도 자리를 차지한다 — 이걸 안 넣으면
            # 버스 번호가 그 선 위에 찍힌다(35·36번에서 실제로 그랬다)
            if where in ("U", "D"):
                edge_y = rect.bottom() if where == "U" else rect.top()
                far_y = y - half[i] if where == "U" else y + half[i]
                taken.append(self._seg_box((x, edge_y), (x, far_y), 2.0))
            else:
                edge_x = rect.right() if where == "L" else rect.left()
                taken.append(self._seg_box((edge_x, y), (x, y), 2.0))
        taken.extend(bars)          # 번호는 자기 막대도 피해야 한다
        lab = {}
        for i in range(len(self.g.keys)):
            # 슬랙 막대는 보통보다 길게 그리므로, 번호를 그만큼 더
            # 바깥에 놓아야 긴 막대에 안 묻힌다.
            hb = half[i] + (u * 0.30 if self.g.is_slack[i] else 0.0)
            lab[i] = self._place_label(float(xy[i][0]), float(xy[i][1]),
                                       hb, fm.horizontalAdvance(self.g.label[i]),
                                       taken)
            taken.append(lab[i])

        # ── 선 (가로·세로로만) ──
        # 위반 보기가 켜지면 AC·DC 선을 부하율 색(heat)으로 갈아입히고, 100% 를
        # 넘긴 선은 굵게 + 그 자리에 부하율 숫자를 얹는다. 꺼져 있으면 예전 그대로.
        vio = self.show_violations
        load = self.overlay.get("load", {})
        over_labels = []                       # (mx, my, "123%") — 100% 초과 선
        for ei, ((a, b, kind), pts) in enumerate(zip(self.g.edges, routes)):
            # 위반 보기에선 변환기(IC·DC/DC) 선을 검은색으로 — 부하율 색(초록→빨강)과
            # 겹쳐 헷갈리지 않게(사용자 선호). 꺼져 있으면 원래 색(주황·보라)을 쓴다.
            if vio and kind in ("IC", "DCDC"):
                col = WIRE
            else:
                col = {"IC": IC_COLOR, "DCDC": DCDC_COLOR}.get(kind, WIRE)
            width = 1.9 if kind in ("IC", "DCDC") else 1.3
            if vio and ei in load:
                pct = load[ei]
                col = heat(pct)
                width = 2.0
                if pct > 100.0:
                    width = 3.4
                    mx, my = self._midpoint(pts)
                    over_labels.append((mx, my, f"{pct:.0f}%"))
            pen = QPen(QColor(col))
            pen.setWidthF(width)
            pen.setJoinStyle(Qt.MiterJoin)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawPath(self._edge_path(pts, vsegs, R_hop))

        # ── 선 위의 기호 (변압기 · IC · DC/DC) ──
        # 위반 보기에선 변환기 기호도 검은색(선과 맞춤). 한계는 badge 로 따로 찍는다.
        # (cstyle=="recolor" 를 쓰면 기호 자체를 경고색으로 — 지금 기본은 badge)
        icbad = self.overlay.get("icbad", set()) if vio else set()
        for ei, fn, mx, my, s, kind in edge_sym:
            if vio and kind in ("IC", "DCDC"):
                col = WIRE
            else:
                col = {"IC": IC_COLOR, "DCDC": DCDC_COLOR}.get(kind, WIRE)
            if ei in icbad and self.cstyle == "recolor":
                col = VIO_ACCENT
            fn(p, mx, my, s, col, c["plot"], lw)

        # ── 위반 보기: 변환기 한계 표시(고리/삼각형) + 과부하 선 부하율 숫자 ──
        if vio:
            for ei in icbad:
                if ei >= len(routes):
                    continue
                mx, my = self._midpoint(routes[ei])
                if self.cstyle == "ring":
                    ring = QPen(QColor(VIO_ACCENT)); ring.setWidthF(2.4)
                    p.setPen(ring); p.setBrush(Qt.NoBrush)
                    rr = u * 0.85
                    p.drawEllipse(QPointF(mx, my), rr, rr)
                elif self.cstyle == "badge":
                    self._warn_badge(p, mx + u * 0.7, my - u * 0.7, u * 0.62)
            for mx, my, txt in over_labels:
                self._over_label(p, mx, my, txt, fm)

        # ── 부하 화살표 ──
        if SHOW_LOAD_ARROWS:
            for i in range(len(self.g.keys)):
                if self.g.has_load[i]:
                    self._load(p, float(xy[i][0]), float(xy[i][1]), u, bh,
                               self.g.label[i], lw)

        # ── 발전기 기호 ──
        for i, (where, rect) in src.items():
            self._draw_source(p, float(xy[i][0]), float(xy[i][1]), u, 2 * half[i],
                              self.g.role[i], lw, where, rect)

        # ── 버스 번호 ──
        p.setFont(f)
        for i in range(len(self.g.keys)):
            p.setPen(QColor(BUS_DC if self.g.kind[i] == "DC" else BUS_AC))
            p.drawText(lab[i], Qt.AlignCenter, self.g.label[i])

        # ── 버스 막대 (맨 마지막에 그린다) ──
        # 자리 잡기가 겹침을 막아 주지만 어디를 봐도 자리가 없으면 덜 나쁜 쪽에
        # 놓을 뿐이라 완벽하진 않다. 그래서 **버스 막대는 무조건 맨 위**로 올려
        # 다른 것에 절대 가리지 않게 한다.
        vbad = self.overlay.get("vbad", {}) if vio else {}
        vmarks = []               # (표시방식, x, y, 방향, 막대 절반길이) — 막대 뒤에 그림
        for i in range(len(self.g.keys)):
            x, y = float(xy[i][0]), float(xy[i][1])
            # 3권선 변압기 노드는 막대가 아니라 변압기 아이콘(맨 앞·속 채움).
            if self.g.role[i] == "3권선":
                symbols.transformer(p, x, y, u * 1.15, WIRE, self.c["plot"], lw, 3)
                continue
            col = BUS_DC if self.g.kind[i] == "DC" else BUS_AC
            direction = vbad.get(i)               # None / +1(과전압) / -1(저전압)
            halo = direction is not None and self.vstyle == "halo"
            hh = half[i]
            if halo:
                # 전압 위반 후광 — 버스 색은 그 위에 얹어 AC/DC 정체를 유지한다.
                self._bar(p, x, y, VIO_ACCENT, max(6.2, u * 0.54),
                          2 * hh + u * 0.3)
            if self.g.is_slack[i]:
                # 기준(slack) 버스 — 막대 자체를 강조색으로 칠한다(AC 호박·DC 청록).
                # 발전기 아이콘은 없다. 전압 위반이면 위 자홍 후광이 뒤에 겹친다.
                scol = SLACK_DC if self.g.kind[i] == "DC" else SLACK_AC
                self._bar(p, x, y, scol, max(3.6, u * 0.30), 2 * hh + u * 0.15)
            else:
                self._bar(p, x, y, col, max(3.0, u * 0.24), 2 * hh)
            if direction is not None and self.vstyle in ("badge", "arrow"):
                vmarks.append((self.vstyle, x, y, direction, hh))
        # 뱃지·화살표는 막대를 다 그린 뒤 그 위에(옆·위아래로 비켜) 얹는다
        for kind_m, x, y, direction, hb in vmarks:
            if kind_m == "badge":
                self._warn_badge(p, x + u * 0.55, y - hb - u * 0.30, u * 0.6)
            else:
                self._v_arrow(p, x, y, u, hb, direction)
        p.end()

    def _midpoint(self, pts):
        """꺾인 길의 한가운데 — 길이를 따라 절반 되는 지점."""
        segs = [((pts[k][0], pts[k][1]), (pts[k + 1][0], pts[k + 1][1]))
                for k in range(len(pts) - 1)]
        total = sum(np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs)
        walk = 0.0
        for a, b in segs:
            L = np.hypot(b[0] - a[0], b[1] - a[1])
            if walk + L >= total / 2:
                t = (total / 2 - walk) / max(L, 1e-6)
                return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            walk += L
        return pts[-1]

    def _over_label(self, p, mx, my, txt, fm):
        """100% 초과 선에 부하율 숫자를 알약 배경에 얹어 읽히게 한다."""
        w = fm.horizontalAdvance(txt) + 8
        h = 15.0
        box = QRectF(mx - w / 2, my - h / 2, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(HEAT_OVER))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor("#ffffff"))
        p.drawText(box, Qt.AlignCenter, txt)

    def _warn_badge(self, p, cx, cy, s):
        """경고 삼각형(△ 안에 !) — 위반 지점 옆에 붙이는 작은 표식."""
        tri = QPolygonF([QPointF(cx, cy - s * 0.55),
                         QPointF(cx - s * 0.58, cy + s * 0.48),
                         QPointF(cx + s * 0.58, cy + s * 0.48)])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(VIO_ACCENT))
        p.drawPolygon(tri)
        pen = QPen(QColor("#ffffff")); pen.setWidthF(max(1.1, s * 0.11))
        pen.setCapStyle(Qt.RoundCap); p.setPen(pen)
        p.drawLine(QPointF(cx, cy - s * 0.18), QPointF(cx, cy + s * 0.12))
        p.setBrush(QColor("#ffffff")); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy + s * 0.30), s * 0.07, s * 0.07)

    def _v_arrow(self, p, x, y, u, hb, direction):
        """전압 위반 화살표 — 과전압이면 버스 위로 ▲, 저전압이면 아래로 ▼."""
        s = u * 0.55
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(VIO_ACCENT))
        if direction > 0:                      # 과전압 — 위쪽, 위를 가리킴
            cy = y - hb - s * 0.85
            tri = QPolygonF([QPointF(x, cy - s * 0.6),
                             QPointF(x - s * 0.58, cy + s * 0.5),
                             QPointF(x + s * 0.58, cy + s * 0.5)])
        else:                                  # 저전압 — 아래쪽, 아래를 가리킴
            cy = y + hb + s * 0.85
            tri = QPolygonF([QPointF(x, cy + s * 0.6),
                             QPointF(x - s * 0.58, cy - s * 0.5),
                             QPointF(x + s * 0.58, cy - s * 0.5)])
        p.drawPolygon(tri)

    def _cost(self, rect, taken):
        """이 자리가 얼마나 나쁜가 — 이미 뭔가 있는 자리와 겹친 넓이
        + 화면 밖으로 나간 넓이. 0이면 아무것도 안 건드리는 빈자리."""
        bad = 0.0
        for b in taken:
            hit = rect.intersected(b)
            bad += hit.width() * hit.height()
        inside = rect.intersected(QRectF(self.rect()))
        # 화면 밖은 아예 안 보이므로 겹침보다 더 나쁘게 친다
        bad += 3.0 * (rect.width() * rect.height()
                      - inside.width() * inside.height())
        return bad

    def _place_source(self, x, y, u, bh, taken, role):
        """발전기 기호를 버스 어느 쪽에 달지 정한다. (방향, 차지할 네모) 를 준다.

        **여덟 자리(상하좌우 × 가까이·멀리)를 다 재보고 제일 덜 나쁜 쪽**을 고른다.
        피해야 할 것은 버스 막대만이 아니라 선·부하 화살표·다른 기호 전부다
        (taken 에 다 들어 있다). 예전엔 버스 막대만 봐서 세로선이 기호를 관통했다.

        네 자리를 순서대로 보던 것도 실패했다 — 다 막히면 마지막 후보가 그대로
        쓰여 오히려 제일 나쁜 자리에 놓였다(4번을 덮어 아래로 옮겼더니 3번을
        덮었고, 위로 올렸더니 화면 밖으로 잘렸다).
        """
        s = u * 1.05
        pad = u * 0.32
        # 배치는 상자가 아니라 기호의 **보이는 가장자리**에서 막대까지 T 만큼 선이
        # 남도록 한다. 원·송전탑은 상자를 꽉 채우지만(반높이 0.5s) 태양광 패널은
        # 세로로 0.31s 뿐이라, 상자 기준으로 붙이면 원은 연결선이 0이 되어 안 보였다.
        vy = (0.31 if role == "IBR" else 0.5) * s     # 기호 보이는 반높이(위·아래)
        bt, bb = y - bh / 2, y + bh / 2               # 막대 위·아래 끝
        best = None
        for T in (u * 0.45, u * 0.72):                # 보이는 연결선 길이(가까이·멀리)
            for tag, r in (
                ("L", QRectF(x - T - s, y - s / 2, s, s)),
                ("R", QRectF(x + T, y - s / 2, s, s)),
                ("U", QRectF(x - s / 2, bt - T - vy - s / 2, s, s)),
                ("D", QRectF(x - s / 2, bb + T + vy - s / 2, s, s)),
            ):
                box = r.adjusted(-pad, -pad, pad, pad)
                cost = self._cost(box, taken)
                if best is None or cost < best[0] - 1e-6:
                    best = (cost, tag, r, box)
        _, where, rect, box = best
        return where, rect, box

    def _place_label(self, x, y, hb, wt, taken):
        """버스 번호를 어디에 적을지. 기본은 막대 위, 막히면 아래·옆.

        hb 는 **그 버스 막대의 실제 절반 길이**다. 기준(slack) 막대는 보통보다
        길어서, 여기에 bh/2 를 넣으면 번호가 막대 위에 겹쳐 묻힌다.
        """
        w, h = wt + 6, 15.0
        best = None
        for r in (QRectF(x - w / 2, y - hb - 17, w, h),
                  QRectF(x - w / 2, y + hb + 2, w, h),
                  QRectF(x - w - 5, y - h / 2, w, h),
                  QRectF(x + 5, y - h / 2, w, h)):
            cost = self._cost(r, taken)
            if best is None or cost < best[0] - 1e-6:
                best = (cost, r)
        return best[1]

    def _draw_source(self, p, x, y, u, bh, role, lw, where, rect):
        """정해진 자리에 발전기 기호를 그리고 버스까지 짧은 선으로 잇는다.

        기호 뜻은 전력 단선도 표기: 송전탑=계통연계, 원+물결=동기발전기,
        기울인 패널=IBR(분산전원).
        """
        fn, scale = symbols.NODE_DRAW[role]
        cx, cy = rect.center().x(), rect.center().y()
        # 선을 기호 **중심**까지 긋는다 — 채워진 기호(원·패널)가 그 위를 덮어
        # 선 끝을 가리므로, 태양광 패널처럼 상자보다 작은 기호도 선이 안 닿고
        # 뜨는 일이 없다. 송전탑은 빈 윤곽이라 밑동(막대 쪽 모서리)에 잇는다.
        if role == "송전":
            ix = rect.right() if where == "L" else rect.left() if where == "R" else x
            iy = rect.bottom() if where == "U" else rect.top() if where == "D" else y
        else:
            ix, iy = cx, cy
        if where in ("U", "D"):
            b = QPointF(x, y - bh / 2 if where == "U" else y + bh / 2)
        else:
            b = QPointF(x, y)
        pen = QPen(QColor(WIRE)); pen.setWidthF(1.3)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(ix, iy), b)
        fn(p, cx, cy, rect.width() * scale, WIRE, self.c["plot"], lw)

    def _load(self, p, x, y, u, bh, label, lw):
        """부하 — 버스 오른쪽으로 나온 짧은 화살표 (논문 그림처럼)."""
        c = self.c
        y0 = y + bh * 0.30
        x1 = x + u * 0.95
        pen = QPen(QColor(WIRE)); pen.setWidthF(1.2); p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(x, y0), QPointF(x1, y0))
        symbols.load(p, x1 - u * 0.30, y0, u * 0.62, WIRE, 1.2, angle=0.0)

    # ── 끌어서 옮기기 ──
    def _hit(self, pt):
        if not self.g.keys:
            return None
        xy = self._px()
        d = np.sqrt(((xy - np.array([pt.x(), pt.y()])) ** 2).sum(1))
        i = int(np.argmin(d))
        return i if d[i] <= max(14.0, self.bar_h() * 0.8) else None

    @staticmethod
    def _seg_dist(px, py, ax, ay, bx, by):
        """점 (px,py) 에서 선분 (a→b) 까지 거리."""
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return float(np.hypot(px - ax, py - ay))
        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        return float(np.hypot(px - (ax + t * dx), py - (ay + t * dy)))

    def _hit_line(self, pt):
        """마우스가 어느 선로 위인가 → edge 번호. 부하율 데이터가 있는
        AC·DC 선로(변압기 포함)만 클릭 대상으로 본다(변환기·3권선 지선 제외).
        버스 막대 근처는 버스 잡기를 우선하려고 뺀다."""
        if self._hit(pt) is not None or not self._routes:
            return None
        px, py = pt.x(), pt.y()
        best_ei, best_d = None, 6.0
        for ei, (a, b, kind) in enumerate(self.g.edges):
            if kind not in ("AC", "변압기", "DC"):
                continue
            if _busno(self.g.keys[a]) is None or _busno(self.g.keys[b]) is None:
                continue
            if ei >= len(self._routes):
                continue
            pts = self._routes[ei]
            for k in range(len(pts) - 1):
                d = self._seg_dist(px, py, pts[k][0], pts[k][1],
                                   pts[k + 1][0], pts[k + 1][1])
                if d < best_d:
                    best_d, best_ei = d, ei
        return best_ei

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        self.drag = self._hit(ev.position())
        self._press = None
        if self.drag is None and self.on_line_click is not None:
            ei = self._hit_line(ev.position())
            if ei is not None:
                self._press = (ei, ev.position())

    def mouseMoveEvent(self, ev):
        if self.drag is None:
            i = self._hit(ev.position())
            if i is not None:
                # 번호에서 "DC" 를 뺐으므로 여기서 어느 쪽인지 밝혀 준다
                side = "DC" if self.g.kind[i] == "DC" else "AC"
                bits = [f"{side} {self.g.label[i]} 버스"]
                if self.g.is_slack[i]:
                    bits.append("기준(slack) 버스")
                if self.g.role[i]:
                    bits.append(self.g.role[i])
                if self.g.has_load[i]:
                    bits.append("부하 있음")
                QToolTip.showText(ev.globalPosition().toPoint(),
                                  "\n".join(bits), self)
                self.setCursor(Qt.OpenHandCursor)
                return
            # 버스가 아니면 선로 위인지 본다 — 클릭하면 24h 부하율이 뜬다고 알려준다
            ei = self._hit_line(ev.position()) if self.on_line_click else None
            if ei is not None:
                QToolTip.showText(ev.globalPosition().toPoint(),
                                  f"{edge_label(self.g, ei)}\n클릭 → 24시간 부하율",
                                  self)
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            return
        L, m = self._pads()          # _px 와 같은 여백을 써야 끌린 자리가 안 어긋난다
        w = max(1, self.width() - L - m)
        h = max(1, self.height() - 2 * m)
        self.pos[self.drag] = [
            min(1.0, max(0.0, (ev.position().x() - L) / w)),
            min(1.0, max(0.0, (ev.position().y() - m) / h))]
        self.update()

    def mouseReleaseEvent(self, ev):
        if self.drag is not None:
            self.drag = None
            self.setCursor(Qt.ArrowCursor)
            if self.on_move:
                self.on_move({k: [float(self.pos[i][0]), float(self.pos[i][1])]
                              for i, k in enumerate(self.g.keys)})
            return
        # 선로 클릭 — 누른 자리에서 거의 안 움직이고 뗐고, 뗀 자리도 같은
        # 선로 위일 때만 (끌다 지나간 게 아니라 진짜 클릭일 때) 콜백을 부른다.
        if self._press is not None and self.on_line_click is not None:
            ei, p0 = self._press
            self._press = None
            moved = np.hypot(ev.position().x() - p0.x(),
                             ev.position().y() - p0.y())
            if moved <= 5.0 and self._hit_line(ev.position()) == ei:
                self.on_line_click(self.g, ei)


def topology_view(c, sol, t=0, show_violations=False, on_toggle=None,
                  on_line_click=None, zoom=1.0, on_zoom=None):
    """계통도 위젯. 큰 계통은 화면보다 넓어지므로 스크롤 상자에 담아 준다.

    '위반 보기' 를 켜면 고른 시간대(t)의 부하율·전압위반·변환기한계를 계통도에
    얹는다. 계통 구조는 시간이 바뀌어도 그대로라 색만 갈아입는다. 토글을 누르면
    on_toggle(bool) 을 불러 앱이 다시 그리게 한다(계통도는 앱 상태를 모른다).
    """
    g = build_graph(sol)
    if not g.keys:
        return None
    name = str(sol.case_name)
    overlay = make_overlay(g, sol, t) if show_violations else None
    view = TopologyView(g, load_places(name), name, c,
                        on_move=lambda pl: save_places(name, pl),
                        show_violations=show_violations, overlay=overlay,
                        on_line_click=on_line_click,
                        zoom=zoom)
    box = QScrollArea()
    box.setObjectName("plot")
    box.setWidget(view)
    box.setWidgetResizable(True)          # 작은 계통은 화면에 꽉 채운다
    box.setFrameShape(QFrame.NoFrame)
    box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    box.setMinimumHeight(300)
    box.viewport().setStyleSheet(f"background:{c['plot']};")

    # ── 위반 보기 켜기/끄기 (계통도 위 작은 토글) ──
    wrap = QWidget()
    wrap.setObjectName("plot")
    wv = QVBoxLayout(wrap)
    wv.setContentsMargins(0, 0, 0, 0)
    wv.setSpacing(7)

    bar = QHBoxLayout()
    bar.setSpacing(8)
    cap = QLabel("위반 보기")
    cap.setStyleSheet(f"color:{c['muted']};font-size:13px;")
    bar.addWidget(cap)
    seg = QFrame(); seg.setObjectName("segwrap"); seg.setFixedHeight(32)
    seg.setStyleSheet(f"#segwrap {{ background:{c['bg']};border:1px solid "
                      f"{c['border']};border-radius:9px; }}")
    sh = QHBoxLayout(seg); sh.setContentsMargins(3, 3, 3, 3); sh.setSpacing(3)
    for txt, val in [("ON", True), ("OFF", False)]:
        b = QPushButton(txt)
        b.setObjectName("seg_on" if show_violations == val else "seg_off")
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedWidth(48)
        if on_toggle is not None:
            b.clicked.connect(lambda _, x=val: on_toggle(x))
        sh.addWidget(b)
    bar.addWidget(seg)
    if show_violations:            # 켜졌을 때만 색 뜻을 옆에 적어 준다
        leg = QLabel("선=부하율(초록→빨강) · 빨강+숫자=100% 초과 · "
                     "버스 테두리=전압 위반 · 고리=변환기 한계")
        leg.setStyleSheet(f"color:{c['muted']};font-size:12px;")
        bar.addSpacing(6); bar.addWidget(leg)
    bar.addStretch()

    # ── 확대·축소 (2026-08-19 사용자 요청) ──
    # 계통도는 버스가 많을수록 기호를 줄여 그리므로(`unit`), 큰 계통에서는 번호가
    # 작아 읽기 어렵다. 배율을 손으로 올릴 수 있게 한다.
    # ⚠️ **줄을 짧게 유지한다** — 이 줄은 그래프 칸 안에 있고, 표가 넓게 열리면
    #    그 칸이 330px 까지 좁아진다(실측). 「확대」 글자와 「원래 크기」 단추를
    #    넣었더니 곧바로 잘렸다 ⇒ 기호만 남기고 되돌리기는 앱이 이미 쓰는 `⟲` 로.
    zwrap = QFrame(); zwrap.setObjectName("segwrap"); zwrap.setFixedHeight(32)
    zwrap.setStyleSheet(f"#segwrap {{ background:{c['bg']};border:1px solid "
                        f"{c['border']};border-radius:9px; }}")
    zh = QHBoxLayout(zwrap); zh.setContentsMargins(3, 3, 3, 3); zh.setSpacing(3)

    pct = QLabel()
    pct.setAlignment(Qt.AlignCenter)
    pct.setFixedWidth(46)
    pct.setStyleSheet(f"color:{c['text']};font-size:13px;font-weight:600;")

    def show_pct(_z=None):
        pct.setText(f"{view.zoom * 100:.0f}%")

    # 🚨 **배율이 바뀌는 길이 둘이다** — 단추와 Ctrl+마우스휠. 단추 쪽에서만 표시를
    #    갈면 휠로 키웠을 때 숫자가 100% 에 멈춰 있다(실제로 그랬다).
    #    ⇒ `set_zoom` 이 부르는 이 한 곳에서 표시도 갈고 앱에도 알린다.
    def note_zoom(z):
        show_pct()
        if on_zoom is not None:
            on_zoom(z)

    def bump(factor):
        view.set_zoom(view.zoom * factor if factor else 1.0)

    HINT = "  (Ctrl 또는 ⌘ 을 누른 채 마우스를 굴려도 됩니다)"
    for txt, fac, tip in [("−", 1 / TopologyView.ZOOM_STEP, "계통도를 줄인다"),
                          (None, None, None),
                          ("+", TopologyView.ZOOM_STEP, "계통도를 키운다"),
                          ("⟲", None, "배율을 100% 로 되돌린다")]:
        if txt is None:
            zh.addWidget(pct)
            continue
        b = QPushButton(txt)
        b.setObjectName("seg_off")
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedWidth(32)
        # 기호 하나뿐이라 기본 크기로는 너무 작아 보인다
        b.setStyleSheet("font-size:15px;font-weight:600;")
        b.setToolTip(tip + (HINT if fac else ""))
        b.clicked.connect(lambda _, f=fac: bump(f))
        zh.addWidget(b)
    bar.addWidget(zwrap)
    view.on_zoom = note_zoom          # 정의가 위젯보다 뒤라 여기서 물린다
    show_pct()

    wv.addLayout(bar)
    wv.addWidget(box, 1)
    wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return wrap
