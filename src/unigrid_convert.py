"""unigrid_convert.py — 외부 계통 포맷을 UniGrid case(ACDCCase)로 변환.

지원 입력 (모두 AC-only로 변환, Mode=1):
  - MATPOWER  .m   → matpower_to_case()
  - PSS/E     .raw → psse_to_case()

이 변환들은 v14 `acdcapp_0404.mlapp`의 GUI 변환 버튼
(MatpowerAConlyButton / PSSEAConlyButton)의 로직을 파이썬으로 옮긴 것이다.
차이점: 엑셀로 저장하지 않고, load_case.load_acdc_case가 만드는 것과 동일한
ACDCCase(numeric 테이블 13종)를 메모리에서 바로 만든다. AC-only이므로 DC 테이블
6종은 빈(0행) 표로 채워, 컴파일 엔진 runpf_unigrid_py의 15-인자 시그니처를 만족시킨다.
(Mode=1이면 엔진이 runpfAC로 분기해 DC 테이블은 건드리지 않는다.)

주의: 결과 테이블의 단위·열 구성은 반드시 mlapp 변환과 1:1이어야 한다
(엑셀 경유 로딩과 같은 숫자가 나오도록). 배포 전 MATLAB 결과와 대조 검증할 것.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from load_case import ACDCCase, TABLE_ORDER

# AC-only일 때 비워 둘 DC 계열 테이블과 기본 열 개수(빈 표라 값에는 영향 없음).
_EMPTY_DC_COLS = {
    "DC_Bus_dat": 6,
    "DC_Line_dat": 8,
    "DC_gen_dat": 9,
    "IC_dat": 21,
    "DCDC_Conv_dat": 15,
    "DC_PLoad_dat": 2,
}


def _empty_table(ncol: int) -> pd.DataFrame:
    return pd.DataFrame(np.zeros((0, ncol), dtype="float64"))


def _mat(arr: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(np.asarray(arr, dtype="float64"))


def _assemble_ac_case(case_name: str, ac_tables: dict[str, pd.DataFrame]) -> ACDCCase:
    """AC 테이블 dict + 빈 DC 테이블로 완전한 13-테이블 ACDCCase(Mode=1)를 만든다."""
    tables: dict[str, pd.DataFrame] = {}
    for key in TABLE_ORDER:
        if key in ac_tables:
            tables[key] = ac_tables[key]
        else:
            tables[key] = _empty_table(_EMPTY_DC_COLS[key])
    return ACDCCase(case_name=case_name, mode=1.0, tables=tables)


# =====================================================================
#  MATPOWER  .m  →  ACDCCase
# =====================================================================
def matpower_to_case(m_path: str | Path) -> ACDCCase:
    """MATPOWER m-file을 읽어 UniGrid AC-only case로 변환한다.

    mlapp MatpowerAConlyButton 로직 포팅. mpc.baseMVA/bus/gen/branch를
    텍스트에서 파싱한다(파일을 실행하지 않음).
    """
    path = Path(m_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"MATPOWER 파일을 찾을 수 없습니다: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")

    baseMVA = _mp_scalar(text, "baseMVA")
    bus = _mp_matrix(text, "bus")
    gen = _mp_matrix(text, "gen")
    branch = _mp_matrix(text, "branch")

    nbus = bus.shape[0]
    ngen = gen.shape[0]
    nline = branch.shape[0]

    # ---- Base_dat (1x7) : freq는 MATPOWER에 없어 mlapp과 동일 기본값 ----
    Base_dat = np.array([[baseMVA, 60.0, 1.0, 0.95, 1.05, 0.0, 3.6e-2]])

    # ---- AC Bus Data (nbus x 17) ----
    AC_Bus = np.zeros((nbus, 17))
    AC_Bus[:, 0] = bus[:, 0]              # Bus number
    AC_Bus[:, 1] = bus[:, 4]             # Gs [MW]
    AC_Bus[:, 2] = bus[:, 5]             # Bs [MVAr]
    AC_Bus[:, 5] = 1.0                   # P_p (ZIP 상수전력)
    AC_Bus[:, 8] = 1.0                   # P_q
    AC_Bus[:, 11] = bus[:, 7]            # V0 [pu]  (Vm)
    AC_Bus[:, 12] = bus[:, 8]            # Va [deg]
    if bus[:, 9].min() == 0:             # baseKV 하나라도 0이면 전 버스 345kV (mlapp과 동일)
        AC_Bus[:, 13] = 345.0 * 1e3
    else:
        AC_Bus[:, 13] = bus[:, 9] * 1e3  # V_base [V]
    AC_Bus[:, 14] = bus[:, 12]           # V_min [pu]
    AC_Bus[:, 15] = bus[:, 11]           # V_max [pu]
    AC_Bus[:, 16] = bus[:, 6]            # Area

    bus_ids = bus[:, 0]

    # ---- AC P/Q Consume Data (nbus x 2), 라벨행 없음 ([Bus, P|Q]) ----
    AC_PLoad = np.column_stack([bus_ids, bus[:, 2] * 1e6])   # Pd [W]
    AC_QLoad = np.column_stack([bus_ids, bus[:, 3] * 1e6])   # Qd [Var]

    # ---- AC Gen Data (ngen x 15) ----
    AC_gen = np.zeros((ngen, 15))
    AC_gen[:, 0] = gen[:, 0]                 # Bus
    for j in range(ngen):
        brow = np.where(bus_ids == gen[j, 0])[0]
        if brow.size:
            btype = bus[brow[0], 1]
            if btype == 2:                   # PV
                AC_gen[j, 1] = 2; AC_gen[j, 2] = 2
            elif btype == 3:                 # slack/ref
                AC_gen[j, 1] = 1; AC_gen[j, 2] = 3
    AC_gen[:, 5] = gen[:, 1] * 1e6           # P_gen [W]
    AC_gen[:, 6] = gen[:, 2] * 1e6           # Q_gen [Var]
    AC_gen[:, 7] = gen[:, 5]                 # Vg [pu]
    AC_gen[:, 8] = gen[:, 7]                 # Status
    # 🚨 이 칸은 MVA 다 (엔진: AC_gen_local_S / (S_base/1e6)).
    #    2026-08-06 전까지 * 1e6 을 곱해 VA 로 썼다 — droop 계수가 100만 배 어긋난다.
    AC_gen[:, 9] = gen[:, 6]                 # Local Sbase [MVA]
    AC_gen[:, 10] = 1e-6                      # |V| deadband
    AC_gen[:, 11] = gen[:, 3] * 1e6          # Qmax
    AC_gen[:, 12] = gen[:, 4] * 1e6          # Qmin
    AC_gen[:, 13] = gen[:, 8] * 1e6          # Pmax
    AC_gen[:, 14] = gen[:, 9] * 1e6          # Pmin

    # ---- AC Line Data (nline x 13) ----
    AC_Line = np.zeros((nline, 13))
    AC_Line[:, 0] = np.arange(1, nline + 1)
    AC_Line[:, 1] = branch[:, 0]             # From
    AC_Line[:, 2] = branch[:, 1]             # To
    for i in range(nline):
        fr = np.where(bus_ids == branch[i, 0])[0]
        to = np.where(bus_ids == branch[i, 1])[0]
        Vb = min(AC_Bus[fr[0], 13], AC_Bus[to[0], 13])
        Zb = Vb ** 2 / (baseMVA * 1e6)
        AC_Line[i, 3] = branch[i, 2] * Zb    # R [ohm]
        AC_Line[i, 4] = branch[i, 3] * Zb    # X [ohm]
        AC_Line[i, 5] = branch[i, 4] / Zb    # B [S]
    AC_Line[:, 6] = branch[:, 8]             # Tap ratio
    AC_Line[:, 7] = branch[:, 9]             # angle [deg]
    AC_Line[:, 8:11] = branch[:, 5:8]        # rateA/B/C
    AC_Line[AC_Line[:, 8] == 0, 8] = 9999.0  # rateA=0 → 무제한(9999)
    AC_Line[:, 11] = (branch[:, 8] != 0).astype(float)  # AC transformer status (tap!=0)
    AC_Line[:, 12] = branch[:, 10]           # connection status

    ac_tables = {
        "Base_dat": _mat(Base_dat),
        "AC_Bus_dat": _mat(AC_Bus),
        "AC_Line_dat": _mat(AC_Line),
        "AC_gen_dat": _mat(AC_gen),
        "AC_3wtrans_dat": _empty_table(30),   # MATPOWER엔 3권선 없음
        "AC_PLoad_dat": _mat(AC_PLoad),
        "AC_QLoad_dat": _mat(AC_QLoad),
    }
    return _assemble_ac_case(path.name, ac_tables)


def _mp_scalar(text: str, name: str) -> float:
    m = re.search(r"mpc\." + name + r"\s*=\s*([\d.eE+\-]+)", text)
    if not m:
        raise ValueError(f"MATPOWER 파일에서 mpc.{name}를 찾을 수 없습니다.")
    return float(m.group(1))


def _mp_matrix(text: str, name: str) -> np.ndarray:
    m = re.search(r"mpc\." + name + r"\s*=\s*\[(.*?)\]\s*;", text, re.DOTALL)
    if not m:
        raise ValueError(f"MATPOWER 파일에서 mpc.{name} 행렬을 찾을 수 없습니다.")
    rows = []
    for chunk in re.split(r"[;\n]", m.group(1)):
        chunk = re.sub(r"%.*", "", chunk).strip()   # 주석 제거
        if not chunk:
            continue
        parts = [p for p in re.split(r"[,\s]+", chunk) if p]
        rows.append([float(p) for p in parts])
    if not rows:
        raise ValueError(f"mpc.{name} 행렬이 비어 있습니다.")
    width = max(len(r) for r in rows)
    for r in rows:
        r.extend([0.0] * (width - len(r)))          # 폭 불일치 방어(보통 동일)
    return np.array(rows, dtype="float64")


# =====================================================================
#  PSS/E  .raw  →  ACDCCase   (AC-only)
# =====================================================================
def _pnum(tok: str) -> float:
    try:
        return float(tok)
    except ValueError:
        return float("nan")


def _parse_line(ln: str) -> list[float]:
    """PSS/E 한 줄을 숫자 리스트로. 따옴표 문자열은 0으로, '/' 뒤 주석은 제거."""
    ln = re.sub(r"'[^']*'", "0", ln)
    ln = re.sub(r"/.*$", "", ln)
    return [_pnum(t) for t in ln.split(",")]


def _g(v: list[float], idx1: int) -> float:
    """MATLAB v(idx1) 모사 (1-based). 범위 밖이면 0.0 (mlapp의 zero-pad와 동일 취지)."""
    i = idx1 - 1
    return v[i] if 0 <= i < len(v) else 0.0


def psse_to_case(raw_path: str | Path) -> ACDCCase:
    """PSS/E .raw를 읽어 UniGrid AC-only case로 변환한다.

    mlapp PSSEAConlyButton 로직 포팅(AC-only 부분만; DC 섹션은 무시).
    BUS/LOAD/FIXED+SWITCHED SHUNT/GENERATOR/BRANCH/TRANSFORMER(2권선+3권선)
    → 13-테이블(AC 채움 + DC 빈). IDE==4(isolated) 버스와 그에 붙은 요소는 제외.
    """
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"PSS/E 파일을 찾을 수 없습니다: {path}")
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()]

    # ---- 헤더: baseMVA, freq ----
    hdr_part = re.match(r"^([^/]+)", lines[0])
    if not hdr_part:
        raise ValueError("PSS/E 헤더를 파싱할 수 없습니다.")
    hv = [_pnum(t) for t in hdr_part.group(1).strip().split(",")]
    baseMVA = hv[1]
    freq = hv[5]

    # ---- 섹션 분리 (4번째 줄부터, BUS로 시작) ----
    sections: dict[str, list[str]] = {}
    current = "BUS"
    buf: list[str] = []
    for ln in lines[3:]:
        if ln == "":
            continue
        if re.match(r"^\s*0\s*/", ln):
            sections[current] = buf
            m = re.search(r"BEGIN\s+(.+?)\s+DATA", ln)
            if m:
                nxt = re.sub(r"[^A-Z0-9]+", "_", m.group(1).upper().strip())
                current = re.sub(r"^_|_$", "", nxt)
            else:
                current = "DONE"
            buf = []
        elif ln.upper() == "Q":
            sections[current] = buf
            break
        else:
            buf.append(ln)

    def sec(name: str) -> list[str]:
        return sections.get(name, [])

    # ---- Bus: [BusID, BASKV, IDE, VM, VA, AREA, Vmin, Vmax] ----
    bus_all = []
    for ln in sec("BUS"):
        v = _parse_line(ln)
        bus_all.append([_g(v, 1), _g(v, 3), _g(v, 4), _g(v, 8), _g(v, 9), _g(v, 5), 0.94, 1.06])
    bus_all = np.array(bus_all, dtype="float64").reshape(-1, 8)
    active = bus_all[:, 2] != 4
    active_ids = set(bus_all[active, 0].tolist())
    bus = bus_all[active, :]
    bus_ids = bus[:, 0]
    nbus = bus.shape[0]

    def is_active(bid: float) -> bool:
        return bid in active_ids

    # ---- Load: [bus, PL, QL] ----
    ld = []
    for ln in sec("LOAD"):
        v = _parse_line(ln)
        if is_active(_g(v, 1)):
            ld.append([_g(v, 1), _g(v, 6), _g(v, 7)])

    # ---- Fixed shunt: [bus, GL, BL] + Switched shunt(BINIT) ----
    sh = []
    for ln in sec("FIXED_SHUNT"):
        v = _parse_line(ln)
        if is_active(_g(v, 1)):
            sh.append([_g(v, 1), _g(v, 4), _g(v, 5)])
    for ln in sec("SWITCHED_SHUNT"):
        v = _parse_line(ln)
        if len(v) < 10:
            continue
        if _g(v, 4) == 1 and is_active(_g(v, 1)):   # STAT==1
            sh.append([_g(v, 1), 0.0, _g(v, 10)])   # Bs에 BINIT

    # ---- Generator ----
    gen = []
    for ln in sec("GENERATOR"):
        v = _parse_line(ln)
        if is_active(_g(v, 1)):
            gen.append([_g(v, 1), _g(v, 3), _g(v, 4), _g(v, 5), _g(v, 6),
                        _g(v, 7), _g(v, 9), _g(v, 15), _g(v, 17), _g(v, 18)])
    gen = np.array(gen, dtype="float64").reshape(-1, 10)
    ngen = gen.shape[0]

    # ---- Branch: [from,to,R,X,B,RateA,RateB,RateC,Status] (양끝 active) ----
    br = []
    for ln in sec("BRANCH"):
        v = _parse_line(ln)
        if is_active(_g(v, 1)) and is_active(_g(v, 2)):
            br.append([_g(v, 1), _g(v, 2), _g(v, 4), _g(v, 5), _g(v, 6),
                       _g(v, 7), _g(v, 8), _g(v, 9), _g(v, 14)])
    br = np.array(br, dtype="float64").reshape(-1, 9)

    # ---- Transformer (2권선 + 3권선) ----
    tr_list, tr3w_list = _psse_transformers(sec("TRANSFORMER"), baseMVA, active_ids)

    # ---- Base_dat ----
    Base_dat = np.array([[baseMVA, freq, 1.0, 0.95, 1.05, 0.0, 3.6e-2]])

    # ---- AC Bus Data (nbus x 17) ----
    AC_Bus = np.zeros((nbus, 17))
    AC_Bus[:, 0] = bus[:, 0]
    for k in range(len(sh)):
        rows = np.where(bus_ids == sh[k][0])[0]
        if rows.size:
            AC_Bus[rows[0], 1] += sh[k][1]
            AC_Bus[rows[0], 2] += sh[k][2]
    AC_Bus[:, 5] = 1.0
    AC_Bus[:, 8] = 1.0
    AC_Bus[:, 11] = bus[:, 3]         # VM
    AC_Bus[:, 12] = bus[:, 4]         # VA
    AC_Bus[:, 13] = bus[:, 1] * 1e3   # BASKV → V
    AC_Bus[:, 14] = bus[:, 6]         # Vmin
    AC_Bus[:, 15] = bus[:, 7]         # Vmax
    AC_Bus[:, 16] = bus[:, 5]         # Area

    # ---- AC P/Q Load ----
    AC_PLoad = np.column_stack([bus_ids, np.zeros(nbus)])
    AC_QLoad = np.column_stack([bus_ids, np.zeros(nbus)])
    for row in ld:
        rr = np.where(bus_ids == row[0])[0]
        if rr.size:
            AC_PLoad[rr[0], 1] += row[1] * 1e6
            AC_QLoad[rr[0], 1] += row[2] * 1e6

    # ---- AC Gen Data (ngen x 15) ----
    AC_gen = np.zeros((ngen, 15))
    if ngen:
        AC_gen[:, 0] = gen[:, 0]
        for k in range(ngen):
            brow = np.where(bus_ids == gen[k, 0])[0]
            if brow.size:
                ide = bus[brow[0], 2]
                if ide == 3:
                    AC_gen[k, 1] = 1; AC_gen[k, 2] = 3
                elif ide == 2:
                    AC_gen[k, 1] = 2; AC_gen[k, 2] = 2
        AC_gen[:, 5] = gen[:, 1] * 1e6
        AC_gen[:, 6] = gen[:, 2] * 1e6
        AC_gen[:, 7] = gen[:, 5]
        AC_gen[:, 8] = gen[:, 7]
        AC_gen[:, 9] = gen[:, 6]             # Local Sbase [MVA] — 여기만 MVA
        AC_gen[:, 10] = 1e-6
        AC_gen[:, 11] = gen[:, 3] * 1e6
        AC_gen[:, 12] = gen[:, 4] * 1e6
        AC_gen[:, 13] = gen[:, 8] * 1e6
        AC_gen[:, 14] = gen[:, 9] * 1e6

    # ---- AC Line Data (선로 + 2권선 변압기) ----
    nline = br.shape[0]
    ntr = tr_list.shape[0]
    all_branch = np.zeros((nline + ntr, 11))
    if nline:
        all_branch[:nline, :9] = br[:, :9]           # 선로: tap/angle = 0
    if ntr:
        all_branch[nline:, :9] = tr_list[:, :9]
        all_branch[nline:, 9] = tr_list[:, 9]        # tap
        all_branch[nline:, 10] = tr_list[:, 10]      # angle
    nbranch = all_branch.shape[0]
    AC_Line = np.zeros((nbranch, 13))
    AC_Line[:, 0] = np.arange(1, nbranch + 1)
    AC_Line[:, 1] = all_branch[:, 0]
    AC_Line[:, 2] = all_branch[:, 1]
    for i in range(nbranch):
        fr = np.where(bus_ids == all_branch[i, 0])[0]
        to = np.where(bus_ids == all_branch[i, 1])[0]
        Vb = min(AC_Bus[fr[0], 13], AC_Bus[to[0], 13])
        Zb = Vb ** 2 / (baseMVA * 1e6)
        AC_Line[i, 3] = all_branch[i, 2] * Zb
        AC_Line[i, 4] = all_branch[i, 3] * Zb
        AC_Line[i, 5] = all_branch[i, 4] / Zb
    AC_Line[:, 6] = all_branch[:, 9]                  # tap
    AC_Line[:, 7] = all_branch[:, 10]                 # angle
    AC_Line[:, 8] = all_branch[:, 5]                  # rateA
    AC_Line[:, 9] = all_branch[:, 6]                  # rateB
    AC_Line[:, 10] = all_branch[:, 7]                 # rateC
    AC_Line[:, 11] = (all_branch[:, 9] != 0).astype(float)
    if nbranch:
        AC_Line[AC_Line[:, 8] == 0, 8] = 9999.0
    AC_Line[:, 12] = all_branch[:, 8]                 # status

    # ---- AC 3w Transformer Data ----
    AC_3w = _psse_build_3w(tr3w_list, bus_all, baseMVA)

    ac_tables = {
        "Base_dat": _mat(Base_dat),
        "AC_Bus_dat": _mat(AC_Bus),
        "AC_Line_dat": _mat(AC_Line),
        "AC_gen_dat": _mat(AC_gen),
        "AC_3wtrans_dat": _mat(AC_3w) if AC_3w.shape[0] else _empty_table(30),
        "AC_PLoad_dat": _mat(AC_PLoad),
        "AC_QLoad_dat": _mat(AC_QLoad),
    }
    return _assemble_ac_case(path.name, ac_tables)


def _psse_transformers(raw_tr, baseMVA, active_ids):
    """TRANSFORMER 섹션 → (tr_list[nx11] 2권선, tr3w_list[nx30] 3권선 raw)."""
    tr_list, tr3w_list = [], []
    ii = 0
    n = len(raw_tr)
    while ii < n:
        v1 = _parse_line(raw_tr[ii])
        K = _g(v1, 3)
        if K == 0:
            # ----- 2권선 (4줄) -----
            if ii + 3 >= n:          # 완전한 4줄 레코드가 없으면 종료 (mlapp: ii+3 > length)
                break
            v2 = _parse_line(raw_tr[ii + 1])
            v3 = _parse_line(raw_tr[ii + 2])
            R12, X12, SB12 = _g(v2, 1), _g(v2, 2), _g(v2, 3)
            WINDV1, NOMV1, ANG1 = _g(v3, 1), _g(v3, 2), _g(v3, 3)
            RATA1, RATB1, RATC1 = _g(v3, 4), _g(v3, 5), _g(v3, 6)
            STAT, CW = _g(v1, 12), round(_g(v1, 5))
            if not (_g(v1, 1) in active_ids and _g(v1, 2) in active_ids):
                ii += 4
                continue
            if SB12 != 0 and abs(SB12 - baseMVA) > 1e-6:
                R_s, X_s = R12 * (baseMVA / SB12), X12 * (baseMVA / SB12)
            else:
                R_s, X_s = R12, X12
            tap = WINDV1
            if CW == 2:
                tap = WINDV1 / NOMV1 if NOMV1 > 0 else WINDV1
            tr_list.append([_g(v1, 1), _g(v1, 2), R_s, X_s, 0.0, RATA1, RATB1, RATC1, STAT, tap, ANG1])
            ii += 4
        else:
            # ----- 3권선 (5줄) -----
            if ii + 4 >= n:
                break
            v2 = _parse_line(raw_tr[ii + 1])
            v3 = _parse_line(raw_tr[ii + 2])
            v4 = _parse_line(raw_tr[ii + 3])
            v5 = _parse_line(raw_tr[ii + 4])
            stat = round(_g(v1, 12))
            if stat == 1:
                req = [_g(v1, 1), _g(v1, 2), _g(v1, 3)]
            elif stat == 2:
                req = [_g(v1, 1), _g(v1, 3)]
            elif stat == 3:
                req = [_g(v1, 1), _g(v1, 2)]
            elif stat == 4:
                ii += 5
                continue
            else:
                raise ValueError(f"지원하지 않는 3권선 변압기 STAT={stat}")
            if not all(b in active_ids for b in req):
                ii += 5
                continue
            s12 = _g(v2, 3) if _g(v2, 3) != 0 else baseMVA
            s23 = _g(v2, 6) if _g(v2, 6) != 0 else baseMVA
            s31 = _g(v2, 9) if _g(v2, 9) != 0 else baseMVA
            tr3w_list.append([
                _g(v1, 1), _g(v1, 2), _g(v1, 3), _g(v1, 12), _g(v1, 5), _g(v1, 6), _g(v1, 7), _g(v1, 8), _g(v1, 9),
                _g(v2, 1), _g(v2, 2), s12, _g(v2, 4), _g(v2, 5), s23, _g(v2, 7), _g(v2, 8), s31,
                _g(v3, 1), _g(v3, 2), _g(v3, 3), _g(v3, 4),
                _g(v4, 1), _g(v4, 2), _g(v4, 3), _g(v4, 4),
                _g(v5, 1), _g(v5, 2), _g(v5, 3), _g(v5, 4),
            ])
            ii += 5
    return (np.array(tr_list, dtype="float64").reshape(-1, 11),
            np.array(tr3w_list, dtype="float64").reshape(-1, 30))


def _psse_build_3w(tr3w_list, bus_all, baseMVA):
    """tr3w_list(raw) → AC_3wtrans_dat(n x 30) (mlapp 3권선 변환식 포팅)."""
    n3w = tr3w_list.shape[0]
    out = np.zeros((n3w, 30))
    for k in range(n3w):
        r = tr3w_list[k]
        bus1, bus2, bus3, stat, cw, cz, cm, mag1, mag2 = r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]
        R12, X12, S12, R23, X23, S23, R31, X31, S31 = r[9], r[10], r[11], r[12], r[13], r[14], r[15], r[16], r[17]
        WINDV1, NOMV1, ANG1, RATA1 = r[18], r[19], r[20], r[21]
        WINDV2, NOMV2, ANG2, RATA2 = r[22], r[23], r[24], r[25]
        WINDV3, NOMV3, ANG3, RATA3 = r[26], r[27], r[28], r[29]

        row1 = np.where(bus_all[:, 0] == bus1)[0]
        row2 = np.where(bus_all[:, 0] == bus2)[0]
        row3 = np.where(bus_all[:, 0] == bus3)[0]
        if not (row1.size and row2.size and row3.size):
            raise ValueError("3권선 변압기 버스를 BUS 섹션에서 찾지 못했습니다.")
        b1kv, b2kv, b3kv = bus_all[row1[0], 1], bus_all[row2[0], 1], bus_all[row3[0], 1]

        Vn1 = NOMV1 if NOMV1 > 0 else b1kv
        Vn2 = NOMV2 if NOMV2 > 0 else b2kv
        Vn3 = NOMV3 if NOMV3 > 0 else b3kv

        Vn = np.array([Vn1, Vn2, Vn3])
        order = np.argsort(-Vn, kind="stable")          # 내림차순
        idxHV, idxMV, idxLV = int(order[0]), int(order[1]), int(order[2])
        winding_map = 100 * (idxHV + 1) + 10 * (idxMV + 1) + (idxLV + 1)

        Sn1 = RATA1 if RATA1 > 0 else max(S12, S31, baseMVA)
        Sn2 = RATA2 if RATA2 > 0 else max(S12, S23, baseMVA)
        Sn3 = RATA3 if RATA3 > 0 else max(S23, S31, baseMVA)

        S12t, S23t, S31t = min(Sn1, Sn2), min(Sn2, Sn3), min(Sn3, Sn1)
        s12 = S12 if S12 > 0 else baseMVA
        s23 = S23 if S23 > 0 else baseMVA
        s31 = S31 if S31 > 0 else baseMVA

        czr = round(cz)
        if czr == 1:
            Z12 = complex(R12, X12) * (S12t / baseMVA)
            Z23 = complex(R23, X23) * (S23t / baseMVA)
            Z31 = complex(R31, X31) * (S31t / baseMVA)
        elif czr == 2:
            Z12 = complex(R12, X12) * (S12t / s12)
            Z23 = complex(R23, X23) * (S23t / s23)
            Z31 = complex(R31, X31) * (S31t / s31)
        elif czr == 3:
            r12p, r23p, r31p = R12 / (s12 * 1e6), R23 / (s23 * 1e6), R31 / (s31 * 1e6)
            x12p = (max(X12 ** 2 - r12p ** 2, 0)) ** 0.5
            x23p = (max(X23 ** 2 - r23p ** 2, 0)) ** 0.5
            x31p = (max(X31 ** 2 - r31p ** 2, 0)) ** 0.5
            Z12 = complex(r12p, x12p) * (S12t / s12)
            Z23 = complex(r23p, x23p) * (S23t / s23)
            Z31 = complex(r31p, x31p) * (S31t / s31)
        else:
            Z12, Z23, Z31 = complex(R12, X12), complex(R23, X23), complex(R31, X31)

        wv = [WINDV1, WINDV2, WINDV3]
        nv = [NOMV1, NOMV2, NOMV3]
        bv = [b1kv, b2kv, b3kv]
        tap_vals = [1.0, 1.0, 1.0]
        for jj in range(3):
            if wv[jj] != 0:
                if round(cw) == 2:
                    denom = nv[jj] if nv[jj] > 0 else bv[jj]
                    tap_vals[jj] = wv[jj] / denom if denom > 0 else wv[jj]
                else:
                    tap_vals[jj] = wv[jj]
        tap_dev = [abs(t - 1) for t in tap_vals]
        if any(d > 1e-9 for d in tap_dev):
            tside = int(np.argmax(tap_dev))
            tap_side, tap_ratio = tside + 1, tap_vals[tside]
        else:
            tap_side, tap_ratio = 0, 0.0

        ang = [ANG1, ANG2, ANG3]
        shift_mv = ang[idxMV] - ang[idxHV]
        shift_lv = ang[idxLV] - ang[idxHV]

        SnHV = [Sn1, Sn2, Sn3][idxHV]
        if SnHV <= 0:
            SnHV = baseMVA
        s12b = S12 if S12 > 0 else baseMVA
        if round(cm) == 2:
            pfe_kW = mag1 / 1e3
            io_pct = 100 * abs(mag2) * (s12b / SnHV)
        else:
            ymag = complex(mag1, mag2)
            pfe_kW = ymag.real * baseMVA * 1e3
            io_pct = 100 * abs(ymag) * (baseMVA / SnHV)

        statr = round(stat)
        if statr not in (1, 2, 3, 4):
            raise ValueError(f"지원하지 않는 3권선 변압기 STAT={statr}")

        out[k, :] = [k + 1, bus1, bus2, bus3, statr, Vn1, Vn2, Vn3, Sn1, Sn2, Sn3,
                     Z12.real, Z23.real, Z31.real, Z12.imag, Z23.imag, Z31.imag,
                     0, 0, 0, 0, 0, 0, tap_side, tap_ratio, shift_mv, shift_lv,
                     pfe_kW, io_pct, winding_map]
    return out


if __name__ == "__main__":
    import sys

    case = matpower_to_case(sys.argv[1])
    print("case:", case.case_name, "| mode:", case.mode)
    for key in TABLE_ORDER:
        print(f"  {key:16s}: {case.tables[key].shape}")
