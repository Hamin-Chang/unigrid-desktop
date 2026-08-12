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
        "AC_3wtrans_dat": _empty_table(33),   # MATPOWER엔 3권선 없음
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
    """PSS/E 한 줄을 숫자 리스트로. 따옴표 문자열은 0으로, '/' 뒤 주석은 제거.

    🚨 **칸을 나누는 것이 쉼표만이 아니다** (2026-08-06 확인). PSS/E 는 쉼표와 공백을
       둘 다 허용하고, 옛 판 파일은 공백만 쓰기도 한다:

         rev 33 :  `    1,'1     ', 115.0000,1,   1,   1,   1,1.02700,   6.5179`
         rev 29 :  `    1 'Bus 1   '  16.5000 3    0.000    0.000   1   1 1.04000`

       예전에는 쉼표로만 잘라서, 공백 파일은 **한 줄이 통째로 칸 하나**가 되었다.
       그래서 `t_psse_case2.raw` 가 버스는 읽히는데 **선로·발전기가 0개**로 나왔고
       엔진이 빈 표에서 터졌다. 따옴표 안의 공백은 먼저 없애므로 안전하다.
    """
    ln = re.sub(r"'[^']*'", "0", ln)             # 따옴표 문자열(공백 포함)을 먼저 지운다
    ln = re.sub(r"/.*$", "", ln)
    return [_pnum(t) for t in re.split(r"[,\s]+", ln.strip()) if t != ""]


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
    # 🚨 첫 줄의 칸 수가 **판(rev)마다 다르다** (2026-08-06 확인):
    #     rev 29 : `0, 100.00`                     2칸 — 주파수 칸이 아예 없다
    #     rev 30 : `0, 100.00, 30`                 3칸 — 역시 없다
    #     rev 33+: `0, 100.00, 33, 0, 0, 60.00`    6칸 — 6번째가 주파수(BASFRQ)
    #    예전에는 6번째를 그냥 집어서 옛 판 파일이 **터졌다**
    #    (`IndexError: list index out of range`). 없으면 60 Hz 로 둔다.
    hdr_part = re.match(r"^([^/]+)", lines[0]) if lines else None
    hv = [_pnum(t) for t in hdr_part.group(1).strip().split(",")] if hdr_part else []
    if len(hv) < 2 or not np.isfinite(hv[1]) or hv[1] <= 0:
        raise ValueError(
            f"'{path.name}' 은(는) PSS/E 파일로 읽히지 않습니다.\n"
            f"  첫 줄: {lines[0][:70] if lines else '(빈 파일)'}\n\n"
            "PSS/E `.raw` 는 첫 줄이 `0, 100.00, 33, …` 처럼 시작하고 "
            "두 번째 칸이 기준 용량(MVA)입니다.\n"
            "다른 형식이라면 그 형식으로 열어 보세요 (.xlsx · .m).")
    baseMVA = hv[1]
    freq = hv[5] if len(hv) >= 6 and np.isfinite(hv[5]) and hv[5] > 0 else 60.0
    # 판(rev). 없으면 29 로 본다 — 칸이 2개뿐인 것은 rev 29 다.
    rev = int(hv[2]) if len(hv) >= 3 and np.isfinite(hv[2]) and hv[2] > 0 else 29

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
    # 🚨 **버스 레코드의 칸 배치가 판마다 다르다** (2026-08-06 확인).
    #    rev ≤ 30 : I, NAME, BASKV, IDE, **GL, BL**, AREA, ZONE, VM, VA, OWNER
    #    rev ≥ 31 : I, NAME, BASKV, IDE, AREA, ZONE, OWNER, VM, VA, …
    #      (rev 31 부터 버스 안에 있던 션트 GL·BL 이 FIXED SHUNT 구역으로 빠졌고,
    #       그만큼 뒤 칸이 두 자리 앞으로 당겨졌다.)
    #    새 판 자리로만 읽어서 옛 판 파일은 **VM 자리에서 VA 를 읽었다** —
    #    전압이 전부 1.0 이 되고 위상각에 전압이 들어가 발산했다
    #    (`t_psse_case2.raw`: MATPOWER 정답본과 버스 값이 최대 1.04 어긋났다).
    old_bus = rev <= 30
    i_vm, i_va, i_area = (9, 10, 7) if old_bus else (8, 9, 5)
    bus_all, bus_shunt = [], []
    for ln in sec("BUS"):
        v = _parse_line(ln)
        bus_all.append([_g(v, 1), _g(v, 3), _g(v, 4),
                        _g(v, i_vm), _g(v, i_va), _g(v, i_area), 0.94, 1.06])
        if old_bus and (_g(v, 5) or _g(v, 6)):
            # 옛 판은 션트가 버스 줄 안에 있다 (새 판의 FIXED SHUNT 구역에 해당)
            bus_shunt.append([_g(v, 1), _g(v, 5), _g(v, 6)])
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
        if is_active(_g(v, 1)) and _g(v, 3) == 1:      # STATUS == 1
            # PSS/E 부하는 세 갈래다 — 상수전력(PL·QL) · 정전류(IP·IQ) · 정임피던스(YP·YQ).
            # 🚨 2026-08-07 전에는 **PL·QL 만 가져왔다.** `psse_3w_sample` 은 부하 389 MW 중
            #    96 MW(25%)가 그렇게 사라졌다.
            ld.append([_g(v, 1), _g(v, 6), _g(v, 7),      # PL, QL
                       _g(v, 8), _g(v, 9),                # IP, IQ
                       _g(v, 10), _g(v, 11)])             # YP, YQ

    # ---- Fixed shunt: [bus, GL, BL] + Switched shunt(BINIT) ----
    sh = []
    sh.extend(bus_shunt)                 # 옛 판(rev ≤ 30)은 버스 줄 안에 션트가 있다
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
        # 🚨 PSS/E 는 **계량단(metered end)을 버스 번호의 음수 부호**로 나타낸다.
        #    `151, -152` 는 152번 버스이고, 계량을 152 쪽에서 한다는 뜻일 뿐이다.
        #    부호를 안 떼서 `is_active(-152)` 가 거짓이 되어 **선로가 통째로 버려졌다**
        #    (`t_psse_case3.raw`: 30개 중 **26개**가 사라졌다 — 2026-08-06 확인).
        i, j = abs(_g(v, 1)), abs(_g(v, 2))
        if is_active(i) and is_active(j):
            br.append([i, j, _g(v, 4), _g(v, 5), _g(v, 6),
                       _g(v, 7), _g(v, 8), _g(v, 9), _g(v, 14)])
            # 🚨 2026-08-07: **선로 끝 션트(GI·BI·GJ·BJ)를 안 읽고 있었다.**
            #    pu 라서 baseMVA 를 곱해 양끝 버스의 Gs·Bs 로 넣는다.
            #    `psse_3w_sample` 버스 151 이 (2.3, −50.1) MVA 만큼 통째로 빠져 있었다.
            if _g(v, 14) == 1:                     # ST == 1 인 선로만
                for b, gi, bi in ((i, _g(v, 10), _g(v, 11)), (j, _g(v, 12), _g(v, 13))):
                    if gi or bi:
                        sh.append([b, gi * baseMVA, bi * baseMVA])
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
    # 엔진 식:  P = P0 · ( Z_p·(V/V0)² + I_p·(V/V0) + P_p )
    # PSS/E  :  P = PL + IP·V + YP·V²   ·   Q = QL + IQ·V − YQ·V²
    #   ⇒ P0 = PL + IP·V0 + YP·V0²  로 두면 계수가 딱 떨어지고 합이 1 이 된다.
    #     P_p = PL/P0 · I_p = IP·V0/P0 · Z_p = YP·V0²/P0     (Q 는 YQ 부호가 반대)
    AC_PLoad = np.column_stack([bus_ids, np.zeros(nbus)])
    AC_QLoad = np.column_stack([bus_ids, np.zeros(nbus)])
    zip_p = np.zeros((nbus, 3))                    # PL, IP, YP 합
    zip_q = np.zeros((nbus, 3))                    # QL, IQ, YQ 합
    for row in ld:
        rr = np.where(bus_ids == row[0])[0]
        if not rr.size:
            continue
        i = rr[0]
        zip_p[i] += [row[1], row[3], row[5]]
        zip_q[i] += [row[2], row[4], row[6]]
    for i in range(nbus):
        V0 = AC_Bus[i, 11] if AC_Bus[i, 11] > 0 else 1.0
        PL, IP, YP = zip_p[i]
        QL, IQ, YQ = zip_q[i]
        P0 = PL + IP * V0 + YP * V0 ** 2
        Q0 = QL + IQ * V0 - YQ * V0 ** 2
        AC_PLoad[i, 1] = P0 * 1e6
        AC_QLoad[i, 1] = Q0 * 1e6
        if abs(P0) > 1e-12:
            AC_Bus[i, 3] = YP * V0 ** 2 / P0        # Z_p
            AC_Bus[i, 4] = IP * V0 / P0             # I_p
            AC_Bus[i, 5] = PL / P0                  # P_p
        if abs(Q0) > 1e-12:
            AC_Bus[i, 6] = -YQ * V0 ** 2 / Q0       # Z_q
            AC_Bus[i, 7] = IQ * V0 / Q0             # I_q
            AC_Bus[i, 8] = QL / Q0                  # P_q

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
        "AC_3wtrans_dat": _mat(AC_3w) if AC_3w.shape[0] else _empty_table(33),
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
        # 선로와 같은 이유로 버스 번호의 부호를 뗀다 (PSS/E 는 부호로 계량단을 표시한다).
        for _k in (1, 2, 3):
            if 0 <= _k - 1 < len(v1) and np.isfinite(v1[_k - 1]):
                v1[_k - 1] = abs(v1[_k - 1])
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
            # 🚨 2026-08-07: CZ 를 보지 않고 **SBASE12 로 무조건 되잡고** 있었다.
            #   CZ = 1 이면 임피던스가 **이미 시스템 base pu** 라 되잡으면 안 된다.
            #   `t_psse_case2` 의 변압기 셋이 전부 CZ=1·SBASE 250/200/150 이라
            #   리액턴스가 2.5·2.0·1.5배 작아졌고, 그게 MATPOWER 와 상시 어긋나던
            #   원인이었다(전압 2.3e-3 pu · 위상 1.3도). 3권선 쪽은 원래부터 갈라 썼다.
            CZ = round(_g(v1, 6))
            sb = SB12 if SB12 > 0 else baseMVA
            if CZ == 1:                       # 시스템 base pu — 그대로
                R_s, X_s = R12, X12
            elif CZ == 3:                     # R 은 와트 단위 동손, X 는 |Z| (권선 base pu)
                r_pu = R12 / (sb * 1e6)
                x_pu = max(X12 ** 2 - r_pu ** 2, 0.0) ** 0.5
                R_s, X_s = r_pu * (baseMVA / sb), x_pu * (baseMVA / sb)
            else:                             # CZ = 2 — 권선 base pu
                R_s, X_s = R12 * (baseMVA / sb), X12 * (baseMVA / sb)
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
            # PSS/E 3권선 STAT — 어느 권선이 빠졌나
            #   1 = 다 있음 · 2 = 권선2 빠짐 · 3 = 권선3 빠짐 · 4 = **권선1 빠짐** · 0 = 통째로 빠짐
            # 🚨 2026-08-06 전에는 **STAT=4 를 통째로 버렸다.** 권선 1만 빠지고 2·3 은 살아
            #    있는데 변압기를 통째로 없애 버리니, **버스 두 개가 서로 끊긴 계통**이 됐다.
            #    `psse_3w_sample.raw` 가 그 경우다(209·217·218) — MATPOWER 는 217·218 을
            #    중성점으로 이어 두는데 우리만 끊겨 전압이 크게 어긋났다(215 버스 0.92 vs 1.11).
            # 🚨 STAT=0(통째로 빠짐)은 정상인데 **예외를 던져 파일 전체를 못 읽게** 했다.
            stat = round(_g(v1, 12))
            need = {1: (1, 2, 3), 2: (1, 3), 3: (1, 2), 4: (2, 3)}.get(stat)
            if need is None:                      # 0 = 통째로 빠짐 (그 밖의 값도 조용히 넘긴다)
                ii += 5
                continue
            # ✅ 2026-08-07 8차 재컴파일로 엔진이 STAT=4 를 받는다
            #    (`decode_threeW_status` case 4 → branch_on=[false true true], is_active=1).
            #    권선 1의 버스는 계통에 없어도 된다 — 엔진의 `missing_active` 는 **켜진 권선의
            #    버스만** 요구한다.
            req = [_g(v1, k) for k in need]
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
    """tr3w_list(raw) → AC_3wtrans_dat(n x 33) (mlapp 3권선 변환식 포팅)."""
    n3w = tr3w_list.shape[0]
    out = np.zeros((n3w, 33))
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
        # 24·25 열(tap side·tap ratio)은 탭이 가장 크게 벗어난 권선 하나만 담는다.
        # 🚨 2026-08-10: PSS/E 는 권선마다 WINDV 를 따로 준다 — `psse_3w_sample` 의
        #    3002-3001-3011 이 1.01010/1.05000/1.01000 이라 두 개가 버려졌다.
        #    이제 31~33 열에 셋을 그대로 담고, 24·25 열은 옛 엔진용으로 남긴다.
        tap_dev = [abs(t - 1) for t in tap_vals]
        if any(d > 1e-9 for d in tap_dev):
            tside = int(np.argmax(tap_dev))
            tap_side, tap_ratio = tside + 1, tap_vals[tside]
        else:
            tap_side, tap_ratio = 0, 0.0

        # 🚨 2026-08-07: PSS/E 의 ANG 는 그 권선이 **앞선다**는 뜻이고, 우리 표의 위상 칸은
        #    **뒤진다**는 뜻이다(pandapower `shift_mv_degree` 와 같음). 부호를 뒤집어 넣는다.
        #    안 뒤집어 `psse_3w_sample` 버스 3010 의 위상이 MATPOWER 와 59도 어긋났었다
        #    (그 변압기는 `D1y0y0`·ANG3=30도).
        ang = [ANG1, ANG2, ANG3]
        shift_mv = -(ang[idxMV] - ang[idxHV])
        shift_lv = -(ang[idxLV] - ang[idxHV])

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
                     pfe_kW, io_pct, winding_map,
                     tap_vals[0], tap_vals[1], tap_vals[2]]
    return out


# =====================================================================
#  MatACDC  (.m 두 개: MATPOWER AC + MatACDC DC)  →  ACDCCase (AC/DC 혼합)
# =====================================================================
#
# 원본: `acdcapp_0404.mlapp` 의 `MatACDCACDCButtonPushed`(1477~1925행 = 449줄).
# 엑셀 쓰기 20여 회는 통째로 빠진다 — 여기서는 `ACDCCase` 를 바로 만든다.
#
# 🚨 원본 button 과 **일부러 다르게** 한 곳 셋 (2026-08-10, 근거를 원문에서 확인):
#   ① IC 손실 4개의 `* 10` 을 **안 한다.** MatACDC 정의는 LossA [MW]·LossB [kV]·
#      LossCrec/inv [Ohm](`MatACDC1.0/idx_convdc.m:42-45`)이고 우리 엔진도 그 단위를
#      그대로 읽는다(`functions/preprocess_IC_sub4.m:227-230`). 검증된
#      `ACDC_case24_MatACDC.xlsx` 도 1.103 그대로다 — `*10` 이면 손실이 10배가 된다.
#   ② **DC 부하를 살린다.** 원본은 `busdc(:,4)`(PDC)를 안 읽고 DC P Consume 을 0 으로 썼다.
#   ③ IC 21열 `V_base [kV]` 를 **채운다**(`convdc(:,12)` = BASEKVC). 원본 코드엔 없는데
#      실제 케이스 파일에는 손으로 넣어 뒀다. 엔진은 20·21·22열을 다 받는다.
#
# ⚠️ AC 절반은 `matpower_to_case` 와 규칙이 갈린다(발전기 Type 배정 · DB 기본값 ·
#    rateA=0 처리 · Area 열 · baseKV=0 대체값). **여기서는 button 규칙을 따른다** —
#    논문에 쓰는 MatACDC 케이스들이 그 규칙으로 만들어졌다.
def matacdc_to_case(ac_path: str | Path, dc_path: str | Path) -> ACDCCase:
    """MATPOWER AC `.m` + MatACDC DC `.m` → UNIGRID AC/DC 혼합 case (Mode=0)."""
    ac_p, dc_p = Path(ac_path).expanduser().resolve(), Path(dc_path).expanduser().resolve()
    for p in (ac_p, dc_p):
        if not p.is_file():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {p}")

    ac_txt, dc_txt = _read_m(ac_p), _read_m(dc_p)

    # ⚠️ MatACDC 의 DC 케이스는 `mpc.` 를 안 붙이고 `busdc = [...]` 로 쓴다.
    #    AC 쪽도 파일마다 갈려서, 접두사를 **선택**으로 두고 찾는다(button 과 같은 방식).
    baseMVA = _m_scalar(ac_txt, "baseMVA")
    bus = _m_matrix(ac_txt, "bus")
    gen = _m_matrix(ac_txt, "gen")
    branch = _m_matrix(ac_txt, "branch")

    baseMVAdc = _m_scalar(dc_txt, "baseMVAdc", baseMVA)
    pol = _m_scalar(dc_txt, "pol", 1.0)          # 극수 (1 단극 / 2 쌍극)
    busdc = _m_matrix(dc_txt, "busdc")
    convdc = _m_matrix(dc_txt, "convdc")
    branchdc = _m_matrix(dc_txt, "branchdc")

    nbus, nline = bus.shape[0], branch.shape[0]
    bus_ids = bus[:, 0]

    # ---- Base (1x7) : [Sbase, freq, f_0, freq_min, freq_max, 제어모드, deadband] ----
    Base = np.array([[baseMVA, 60.0, 1.0, 0.975, 1.02, 0.0, 3.6e-2]])

    # ---- AC Bus Data (nbus x 17) ----
    AC_Bus = np.full((nbus, 17), np.nan)
    AC_Bus[:, 0] = bus[:, 0]
    AC_Bus[:, 1] = bus[:, 4]              # Gs [MW]
    AC_Bus[:, 2] = bus[:, 5]              # Bs [MVar]
    AC_Bus[:, 3:11] = [0, 0, 1, 0, 0, 1, 0, 0]     # ZIP + 주파수 의존 (상수전력)
    AC_Bus[:, 11] = bus[:, 7]             # V0 [pu]
    AC_Bus[:, 12] = bus[:, 8]             # Va [deg]
    AC_Bus[:, 13] = bus[:, 9] * 1e3       # V_base [V]
    AC_Bus[:, 14] = bus[:, 12]            # V_min [pu]
    AC_Bus[:, 15] = bus[:, 11]            # V_max [pu]
    AC_Bus[:, 16] = bus[:, 10]            # Area — ⚠️ button 은 ZONE(11열)을 넣는다(안 쓰는 칸)

    # ---- AC Line Data (nline x 13) ----
    pos = {int(b): i for i, b in enumerate(bus_ids)}
    if any(int(b) not in pos for b in branch[:, 0]) or \
       any(int(b) not in pos for b in branch[:, 1]):
        raise ValueError("AC Line: branch 의 from/to 버스가 bus 표에 없습니다.")
    fi = np.array([pos[int(b)] for b in branch[:, 0]])
    ti = np.array([pos[int(b)] for b in branch[:, 1]])
    baseV = np.minimum(bus[fi, 9], bus[ti, 9]) * 1e3
    Zbase = baseV ** 2 / (baseMVA * 1e6)

    AC_Line = np.full((nline, 13), np.nan)
    AC_Line[:, 0] = np.arange(1, nline + 1)
    AC_Line[:, 1] = branch[:, 0]
    AC_Line[:, 2] = branch[:, 1]
    AC_Line[:, 3] = branch[:, 2] * Zbase          # R [ohm]
    AC_Line[:, 4] = branch[:, 3] * Zbase          # X [ohm]
    AC_Line[:, 5] = branch[:, 4] / Zbase          # B [S]
    AC_Line[:, 6] = branch[:, 8]                  # tap
    AC_Line[:, 7] = branch[:, 9]                  # shift [deg]
    AC_Line[:, 8:11] = branch[:, 5:8]             # rateA/B/C
    AC_Line[:, 11] = (branch[:, 8] != 0).astype(float)
    AC_Line[:, 12] = branch[:, 10]                # status

    # ---- AC Gen Data (n x 15) — inf 버스는 slack 더미 발전기를 만든다 ----
    AC_gen = _matacdc_gen(bus, gen, baseMVA, pos)

    # ---- DC Bus Data (n x 6) ----
    ndc = busdc.shape[0]
    DC_Bus = np.full((ndc, 6), np.nan)
    DC_Bus[:, 0] = busdc[:, 0]            # DC 버스 번호
    DC_Bus[:, 1] = 0.0                    # Nominal Current
    DC_Bus[:, 2] = busdc[:, 4]            # V0 [pu]
    DC_Bus[:, 3] = busdc[:, 5] * 1e3      # V_base [V]
    DC_Bus[:, 4] = busdc[:, 7]            # VM min
    DC_Bus[:, 5] = busdc[:, 6]            # VM max

    # ---- DC Line Data (n x 8) ----
    posdc = {int(b): i for i, b in enumerate(busdc[:, 0])}
    ndcl = branchdc.shape[0]
    if any(int(b) not in posdc for b in branchdc[:, 0]) or \
       any(int(b) not in posdc for b in branchdc[:, 1]):
        raise ValueError("DC Line: branchdc 의 from/to 버스가 busdc 표에 없습니다.")
    dfi = np.array([posdc[int(b)] for b in branchdc[:, 0]])
    dti = np.array([posdc[int(b)] for b in branchdc[:, 1]])
    baseVdc = np.minimum(busdc[dfi, 5], busdc[dti, 5]) * 1e3
    Zbase_dc = baseVdc ** 2 / (baseMVAdc * 1e6)

    DC_Line = np.full((ndcl, 8), np.nan)
    DC_Line[:, 0] = np.arange(1, ndcl + 1)
    DC_Line[:, 1] = branchdc[:, 0]
    DC_Line[:, 2] = branchdc[:, 1]
    # 🚨 극수(`pol`)를 저항으로 흡수한다. MatACDC 는 DC 전력을 `Pdc = pol * V .* (Ybusdc*V)`
    #    로 계산하지만(`MatACDC1.0/dcnetworkpf.m:58`) 우리 엔진에는 극수 칸이 없다.
    #    R 을 pol 로 나누면 어드미턴스가 pol 배가 되어 **같은 식**이 된다.
    #    원본 button 은 `pol` 을 읽고도 쓰지 않는다 — 쌍극(pol=2) 계통에서 DC 손실이 2배가 된다.
    DC_Line[:, 3] = branchdc[:, 2] * Zbase_dc / pol       # R [ohm]
    DC_Line[:, 4:8] = branchdc[:, 5:9]            # rateA/B/C · status

    # ---- ACDC IC Data (n x 21) ----
    IC = _matacdc_ic(busdc, convdc, posdc, baseMVA, baseMVAdc)

    # ---- 부하 3종 ----
    AC_PLoad = np.column_stack([bus_ids, bus[:, 2] * 1e6])       # Pd [W]
    AC_QLoad = np.column_stack([bus_ids, bus[:, 3] * 1e6])       # Qd [Var]
    # 🚨 button 은 여기를 0 으로 뒀다. `busdc(:,4)` = PDC 가 DC 부하다.
    DC_PLoad = np.column_stack([busdc[:, 0], busdc[:, 3] * 1e6])

    tables = {
        "Base_dat": _mat(Base),
        "AC_Bus_dat": _mat(AC_Bus),
        "AC_Line_dat": _mat(AC_Line),
        "AC_gen_dat": _mat(AC_gen),
        "AC_3wtrans_dat": _empty_table(33),      # MatACDC 에 3권선 없음
        "DC_Bus_dat": _mat(DC_Bus),
        "DC_Line_dat": _mat(DC_Line),
        "DC_gen_dat": _empty_table(9),           # button 도 머리글만 썼다
        "IC_dat": _mat(IC),
        "DCDC_Conv_dat": _empty_table(10),       # MVDC/LVDC 는 MatACDC 에 없다
        "AC_PLoad_dat": _mat(AC_PLoad),
        "AC_QLoad_dat": _mat(AC_QLoad),
        "DC_PLoad_dat": _mat(DC_PLoad),
    }
    return ACDCCase(case_name=f"{ac_p.stem} + {dc_p.stem}", mode=0.0, tables=tables)


def _read_m(path: Path) -> str:
    """`.m` 을 읽고 `%` 주석을 걷는다 (button 과 같은 방식)."""
    txt = path.read_text(encoding="utf-8", errors="replace")
    return re.sub(r"%[^\n]*", "", txt)


def _m_scalar(text: str, name: str, default: float | None = None) -> float:
    """`mpc.` 접두사가 있어도 없어도 찾는다. 없고 기본값도 없으면 오류."""
    m = re.search(r"(?<![A-Za-z0-9_])(?:mpc\.)?" + re.escape(name) + r"\s*=\s*([\d.eE+\-]+)", text)
    if m:
        return float(m.group(1))
    if default is not None:
        return default
    raise ValueError(f"`.m` 파일에서 {name} 를 찾을 수 없습니다.")


def _m_matrix(text: str, name: str) -> np.ndarray:
    """`mpc.` 접두사가 있어도 없어도 찾는다."""
    m = re.search(r"(?<![A-Za-z0-9_])(?:mpc\.)?" + re.escape(name) + r"\s*=\s*\[(.*?)\]\s*;",
                  text, re.DOTALL)
    if m is None:
        raise ValueError(f"`.m` 파일에서 {name} 행렬을 찾을 수 없습니다.")
    rows = []
    for chunk in re.split(r"[;\n]", m.group(1)):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p for p in re.split(r"[,\s]+", chunk) if p]
        rows.append([float(p) for p in parts])
    if not rows:
        raise ValueError(f"{name} 행렬이 비어 있습니다.")
    width = max(len(r) for r in rows)
    for r in rows:
        r.extend([0.0] * (width - len(r)))
    return np.array(rows, dtype="float64")


def _matacdc_gen(bus, gen, baseMVA, pos) -> np.ndarray:
    """AC Gen Data. MATPOWER 의 `inf` 버스형을 slack 으로 보고 더미 발전기를 만든다.

    ⚠️ `matpower_to_case` 와 규칙이 다르다 — 여기서는 2열(Type)이 **늘 2** 이고
       3열(BusTypeMapped)이 버스형(PQ=1 → 0, inf → 3)이다. button 이 그렇게 쓴다.
    """
    BUS_TYPE, VM = 1, 7                       # bus 표 (0부터)
    PG, QG, QMAX, QMIN, VG, MBASE, ST, PMAX, PMIN = 1, 2, 3, 4, 5, 6, 7, 8, 9

    rows = []
    if gen.shape[0]:
        for g in gen:
            b = int(g[0])
            if b not in pos:
                raise ValueError(f"AC Gen: 발전기 버스 {b} 가 bus 표에 없습니다.")
            bt = bus[pos[b], BUS_TYPE]
            mapped = 0.0 if bt == 1 else (3.0 if np.isinf(bt) else bt)
            rows.append([g[0], 2.0, mapped, 0.0, 0.0,
                         g[PG] * 1e6, g[QG] * 1e6, g[VG], g[ST], g[MBASE], 0.01,
                         g[QMAX] * 1e6, g[QMIN] * 1e6, g[PMAX] * 1e6, g[PMIN] * 1e6])

    # `inf` 버스인데 발전기가 없는 곳에 slack 더미를 세운다
    inf_ids = [int(b[0]) for b in bus if np.isinf(b[BUS_TYPE])]
    have = {int(g[0]) for g in gen} if gen.shape[0] else set()
    for b in inf_ids:
        if b in have:
            continue
        rows.append([float(b), 2.0, 3.0, 0.0, 0.0, 0.0, 0.0, bus[pos[b], VM], 1.0,
                     baseMVA, 0.01, baseMVA * 1e6, -baseMVA * 1e6,
                     baseMVA * 1e6, -baseMVA * 1e6])

    return np.array(rows, dtype="float64").reshape(-1, 15)


def _matacdc_ic(busdc, convdc, posdc, baseMVA, baseMVAdc):
    """ACDC IC Data (21열). MatACDC `convdc` → UNIGRID 변환기 표."""
    n = convdc.shape[0]
    if any(int(b) not in posdc for b in convdc[:, 0]):
        raise ValueError("IC: convdc 의 DC 버스가 busdc 표에 없습니다.")
    bi = np.array([posdc[int(b)] for b in convdc[:, 0]])

    def _map(x):
        # MatACDC 제어모드 → UNIGRID 모드 번호
        return np.where(x == 2, 2.0, np.where(x == 1, 0.0, np.where(x == 3, 1.0, x)))

    # droop 은 열이 있고 값이 0 이 아닐 때만 (`convdc` 는 droop 없으면 20열)
    has_droop = convdc.shape[1] >= 21 and np.any(convdc[:, 20] != 0)

    IC = np.zeros((n, 21))
    IC[:, 0] = busdc[bi, 1]              # 붙은 AC 버스
    IC[:, 1] = convdc[:, 0]              # DC 버스
    IC[:, 2] = _map(convdc[:, 2])        # AC 제어모드
    IC[:, 3] = _map(convdc[:, 1])        # DC 제어모드
    IC[:, 4] = 0.0                       # 주파수 droop 계수
    IC[:, 5] = 0.0                       # DC 전압 droop 계수
    IC[:, 6] = 0.0                       # 무효전력 droop 계수
    IC[:, 8] = convdc[:, 4] * (-1e6)     # Q_s [var]
    IC[:, 9] = 100.0                     # rateA [MVA] — button 이 100 고정

    if has_droop:
        # 🚨 원본 button 의 droop 식은 틀렸다 (2026-08-10).
        #   MatACDC 는 `Pdc = -Pdcset - (1/droop)*(Vdc - Vdcset)` 로 **Vdcset 을 중심으로**
        #   기울기 1/droop 을 건다(`MatACDC1.0/dcnetworkpf.m:57-58, 67`).
        #   우리 엔진은 `P = k*V_norm + P_0`, `V_norm = (V - 중점)/(반폭)`,
        #   `k = (100/F0)*(rateA/S_base)` 다(`preprocess_IC_sub4.m:112`,
        #   `solve_ACDC_newton_aug_v7.m:452,471`). 두 식을 같게 놓으면
        #        F0 = 200 * rateA * droop / (폭 * baseMVAdc)
        #   인데, button 은 `0.5*폭/(droop*baseMVA)*100` 으로 **droop 에 반비례**한다.
        #   그리고 button 은 `Vdcset` 을 아예 안 옮긴다 — 중점과 다르면 그만큼 어긋난다.
        #   ⇒ 기울기는 위 식으로, 중점과 Vdcset 의 차이는 **운전점 P_0 에 접어 넣는다.**
        droop = convdc[:, 20]
        Vdcset = convdc[:, 22] if convdc.shape[1] >= 23 else np.ones(n)
        dVdcset = convdc[:, 23] if convdc.shape[1] >= 24 else np.zeros(n)
        Vdcmax, Vdcmin = busdc[bi, 6], busdc[bi, 7]
        span = Vdcmax - Vdcmin
        mid = 0.5 * (Vdcmax + Vdcmin)

        # MatACDC 기울기 = `1/(droop*baseMVA)` [pu P / pu V]
        #   (`runacdcpf.m:290` 가 `PVdroop = droop*baseMVA` 로 만들고
        #    `dcnetworkpf.m:67` 이 `1./PVdroop .* (Vdc - Vdcset)` 를 더한다)
        # 우리 기울기 = `(100/F0)*(rateA/S_base) / (0.5*폭)`
        #   ⇒ F0 = 200 * rateA * droop / 폭   (rateA·S_base 가 같은 MVA 기준일 때)
        # 이 식은 손으로 만든 `ACDC_matacdc_case5.xlsx` 의 값(500/700/500)과 맞는다.
        rateA = IC[:, 9]
        with np.errstate(divide="ignore", invalid="ignore"):
            IC[:, 5] = np.where(droop != 0, 200.0 * rateA * droop / span, 0.0)
        IC[:, 4] = 1e10                  # 주파수 droop 은 안 걸리게 큰 값

        # 운전점: 우리 droop 은 **전압 한계의 중점**을 기준으로 걸리는데 MatACDC 는
        # `Vdcset` 을 기준으로 건다 ⇒ 그 차이만큼을 P_0 에 미리 접어 넣는다 [MW].
        with np.errstate(divide="ignore", invalid="ignore"):
            shift = np.where(droop != 0,
                             (mid - Vdcset) / (droop * baseMVA) * baseMVA, 0.0)
        IC[:, 7] = (convdc[:, 21] + shift) * (-1e6)

        if np.any(np.abs(dVdcset) > 1e-12):
            raise ValueError(
                "이 DC 케이스는 droop 불감대(`dVdcset`)를 쓰는데 UNIGRID 변환기가 아직 "
                "그것을 옮기지 못합니다. 값이 0 인 케이스만 변환할 수 있습니다.")
    else:
        IC[:, 7] = convdc[:, 3] * (-1e6)         # P_g [W]

    IC[:, 10:15] = convdc[:, 6:11]       # rtf, xtf, bf, rc, xc
    IC[:, 15] = convdc[:, 15]            # status
    # 🚨 button 의 `* 10` 을 안 한다 (파일 머리 주석 ① 참고)
    IC[:, 16:20] = convdc[:, 16:20]      # LossA [MW], LossB [kV], LossCrec/inv [Ohm]
    IC[:, 20] = convdc[:, 11]            # V_base [kV] — button 엔 없다(주석 ③)
    return IC


if __name__ == "__main__":
    import sys

    case = matpower_to_case(sys.argv[1])
    print("case:", case.case_name, "| mode:", case.mode)
    for key in TABLE_ORDER:
        print(f"  {key:16s}: {case.tables[key].shape}")
