"""app_engine.py — UNIGRID 앱이 조류계산을 부르는 통로.

한 번 부르면 **전 시간대 결과**가 한꺼번에 온다. 그래서 앱은 파일을 불러올 때
한 번만 계산하고, 이후 시간·버스를 바꾸는 것은 이미 받아둔 결과를 다시 보는
것뿐이다(다시 계산하지 않는다).

맥: mwpython 별도 프로세스로 실행 (MATLAB 컴파일 패키지의 맥 제약)
윈도우: 같은 프로세스에서 직접 import (나중에 unigrid_app_win 컴파일 후)
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

import engine_path
import paths

_HERE = Path(__file__).resolve().parent
# 컴파일된 엔진은 저장소에 **한 자리**에만 둔다 (README 폴더 규칙 · PDR §4.2 규칙 3).
# 🚨 자리를 **값으로 굳히지 않는다** — 얼리면 `__file__` 이 번들 안을 가리킨다.
#    윈도우는 이 폴더를 `sys.path` 에 넣어 엔진을 **같은 프로세스에서** 부르므로
#    여기가 어긋나면 계산이 아예 안 된다 (`paths` 참조, 2026-08-19).

# 결과 표의 열 이름 (result_columns.py 와 동일 · 폭으로 고른다)
COLUMNS: dict[str, dict[int, list[str]]] = {
    "AC": {
        13: ["Bus", "VM[pu]", "Freq[pu]", "Angle[deg]", "Gen_P[MW]", "Gen_Q[MVAR]",
             "Load_P[MW]", "Load_Q[MVAR]", "toAC_P[MW]", "toAC_Q[MVAR]",
             "baseKV[kV]", "Vmin[pu]", "Vmax[pu]"],
        11: ["Bus", "VM[pu]", "Freq[pu]", "Angle[deg]", "Gen_P[MW]", "Gen_Q[MVAR]",
             "Load_P[MW]", "Load_Q[MVAR]", "baseKV[kV]", "Vmin[pu]", "Vmax[pu]"],
    },
    "DC": {
        9: ["Bus", "VM[pu]", "VM_norm[pu]", "Gen_P[MW]", "Load_P[MW]", "toDC_P[MW]",
            "baseKV[kV]", "Vmin[pu]", "Vmax[pu]"],
        7: ["Bus", "VM[pu]", "Gen_P[MW]", "Load_P[MW]", "baseKV[kV]",
            "Vmin[pu]", "Vmax[pu]"],
    },
    "Branch": {
        11: ["From", "To", "From_P[MW]", "To_P[MW]", "From_Q[MVAR]", "To_Q[MVAR]",
             "Loss_P[MW]", "Loss_Q[MVAR]", "Capacity[MVA]", "Loading[%]", "Status"],
        12: ["From", "To", "From_P[MW]", "To_P[MW]", "From_Q[MVAR]", "To_Q[MVAR]",
             "Loss_P[MW]", "Loss_Q_Qft[MVAR]", "Loss_Q_I2X[MVAR]", "Capacity[MVA]",
             "Loading[%]", "Status"],
        8: ["From", "To", "From_P[MW]", "To_P[MW]", "Loss_P[MW]", "Capacity[MVA]",
            "Loading[%]", "Status"],
    },
    "Loss": {
        5: ["Time[h]", "Ploss[W]", "Qloss[Var]", "Ploss[%]", "Qloss[%]"],
        3: ["Time[h]", "Ploss[W]", "Ploss[%]"],
    },
    "VSC_bus": {
        7: ["BusAC", "BusDC", "VSC_VM[pu]", "VSC_Angle[deg]", "Inj_P[MW]",
            "Inj_Q[MVAR]", "Loss[MW]"],
    },
}


@dataclass
class Solution:
    """계산 결과 한 벌 — 전 시간대를 통째로 들고 있는다."""
    case_name: str
    mode: int                      # 0=AC/DC 혼합 1=AC only 2=DC only
    baseMVA: float
    n_time: int
    AC: np.ndarray                 # 버스 x 열 x 시간
    DC: np.ndarray
    Branch: np.ndarray
    loss: np.ndarray               # 시간 x 열
    freq: np.ndarray               # 시간
    VSC_bus: np.ndarray | None
    converged: bool
    iters: int
    threshold: float
    mis_history: list[float]
    block_names: list[str]
    block_history: np.ndarray
    dominant_block: list[str]
    IC_lim_mode: list[float]
    # 발전기 출력한계 포화 표 (2026-07-27). 한 줄 = 발전기 1대, 열 11개:
    #   [종류, 버스, P, Pmin, Pmax, satP, Q, Qmin, Qmax, satQ, Qlim종류]
    #   종류 1=AC droop 2=DC droop 3=AC 전압제어 4=DC 전압제어
    #   satP/satQ 0=한계 안 +1=상한 포화 -1=하한 포화
    #   Qlim종류 0=한계 안 1=사각 한계 2=용량 원(S_N)
    gen_limit: np.ndarray = field(default_factory=lambda: np.empty((0, 11)))
    # 무효출력 한계를 실제로 걸었는지. AC 전용 경로에서 한계를 걸면 수렴하지 못하는
    # 계통이 있는데, 그때는 한계를 적용하지 않은 값을 돌려주므로 반드시 화면에 밝혀야 한다.
    qlim_enforced: bool = True
    qlim_message: str = ""
    # 무효출력 한계로 묶인 발전기 (2026-08-12, §7.6 G8). 묶는 것 자체는 정상이지만
    # **흡수 쪽(Qmin)에 걸리면 전압이 올라가므로** 사용자가 알아야 한다.
    qlim_bound: int = 0
    qlim_bound_up: int = 0        # 발생(Qmax) 쪽
    qlim_bound_dn: int = 0        # 흡수(Qmin) 쪽 ← 전압이 올라간다
    # 탭 자동 조정 결과 (2026-08-13, §7 5단계 A1). 한 줄 = 조정 걸린 변압기 1대, 열 5개:
    #   [선로번호, 제어버스, 목표전압, 최종탭, 살아있나]
    #   ⚠️ **살아있나 = 0 이면 목표를 못 맞춘 것**(탭이 한계에 걸려 놓아줬다).
    tap_ctrl: np.ndarray = field(default_factory=lambda: np.empty((0, 9)))
    method: str = "nr"            # 어느 해법으로 푼 결과인가
    seconds: float = 0.0        # 파일 읽기 + 계산까지 걸린 전체 시간
    warm_start: bool = True     # 계산 엔진이 이미 켜져 있었나 (아니면 기동 시간이 섞임)
    freq_nominal: float = 60.0  # 이 계통의 기준 주파수 (60 Hz / 50 Hz) — 케이스마다 다름
    freq_db: float = 0.0        # 주파수 데드밴드 [Hz] — 이 폭 밖에서만 발전기가 응동
    # 계통도를 그리려면 '결과'가 아니라 '입력'이 필요하다
    # (어느 선로가 변압기인지·발전기 종류가 뭔지는 결과에 안 담긴다)
    case_tables: dict[str, Any] = field(default_factory=dict, repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    # ── 열 이름 ──
    def cols(self, which: str) -> list[str]:
        arr = getattr(self, which if which != "Loss" else "loss")
        n = arr.shape[1] if arr.ndim >= 2 else 0
        table = COLUMNS.get(which, {})
        return table.get(n, [f"c{i}" for i in range(n)])

    # ── 한 시각의 표 ──
    def at(self, which: str, t: int = 0) -> np.ndarray:
        arr = getattr(self, which)
        if arr.size == 0:
            return arr
        if arr.ndim == 3:
            return arr[:, :, min(t, arr.shape[2] - 1)]
        return arr

    # ── 한 버스의 시간 변화 ──
    def series(self, which: str, col: int, bus_row: int) -> np.ndarray:
        arr = getattr(self, which)
        if arr.ndim != 3:
            return np.array([])
        return arr[bus_row, col, :]

    @property
    def mode_name(self) -> str:
        return {0: "AC/DC 혼합", 1: "AC only", 2: "DC only"}.get(self.mode, "?")


# ─────────────────────────────────────────── 실행
_solve_count = 0


def solved_before() -> bool:
    """이 엔진으로 이미 한 번이라도 풀어 봤나.

    엔진 프로세스가 떠 있어도(is_ready) **첫 계산**은 여전히 느리다
    (MATLAB 쪽 코드가 처음 불릴 때 준비되는 몫 — 여기선 약 2.6 s → 0.6 s).
    그래서 "따뜻한 계산"인지는 프로세스가 아니라 이 횟수로 판단해야 한다.
    """
    return _solve_count > 0


def _nominal_freq(case: Any) -> float:
    """이 계통의 기준 주파수.

    MATLAB 은 기준선을 freq_0 * freq_base 로 그린다(ACDC_snapshotgraph.m 81줄),
    여기서 freq_base = Base_dat 2열, freq_0 = 3열 (preprocess_AC_network.m 30~31줄).
    60 Hz 로 못 박으면 50 Hz 계통(예: ACDC_71bus_3IC_parallel)에서
    멀쩡한 값을 "60 Hz 대비 -10 Hz" 라고 잘못 알린다.
    """
    try:
        b = np.asarray(case.tables["Base_dat"], dtype=float).ravel()
        if b.size >= 3 and b[1] > 0:
            return float(b[1]) * float(b[2])
    except Exception:
        pass
    return 60.0


def _freq_deadband(case: Any) -> float:
    """주파수 데드밴드 [Hz]. 이 폭 **안**에서는 발전기가 주파수에 응동하지 않는다.

    Base_dat 7열 — 케이스 엑셀 `Sbase,frequency` 시트의 "freq_deadband(±) [Hz]" 칸.
    MATLAB 은 freq_base 로 나눠 pu 로 쓰지만(preprocess_AC_network.m 32줄)
    화면엔 Hz 로 보여 주므로 여기서는 그대로 쓴다.
    쓰임새: 편차가 이 폭을 넘은 만큼만 droop 출력을 더한다
    (solve_ACDC_newton.m 295줄·371~374줄).
    **0 이면 데드밴드가 없다**는 뜻 — 아무리 작은 편차에도 바로 응동한다.
    실제 값: 12버스·CIGRE·matacdc case5 = 0.036 / 71버스·울산 = 0.
    """
    try:
        b = np.asarray(case.tables["Base_dat"], dtype=float).ravel()
        if b.size >= 7 and np.isfinite(b[6]):
            return abs(float(b[6]))
    except Exception:
        pass
    return 0.0


def solve(case: Any, *, mwpython: str | Path | None = None,
          method: str = "nr") -> Solution:
    """조류계산 한 번 — 전 시간대 결과를 담은 Solution 을 돌려준다.

    `method` = "nr" 이면 Newton, **"gs" 면 Gauss-Seidel**(2026-08-11 §7 4단계 B2).
    GS 는 AC 단독(Mode=1)만 풀고 발전기 droop·데드밴드·한계를 아직 안 본다 —
    NR 과 답이 다를 수 있다(PDR §7.6 의 G 단계에서 맞추는 중).
    """
    global _solve_count
    t0 = time.perf_counter()
    if method == "gs":
        raw = _gs_solve_all_times(case, mwpython)
    else:
        raw = _run(case, mwpython, method)
    _solve_count += 1
    sol = _build(raw, time.perf_counter() - t0)
    # 어느 해법으로 푼 결과인지는 **여기서** 붙인다 — 화면이 이걸 보고 안내를 고른다.
    # (`app.py` 의 SolveThread 도 붙이지만, 엔진을 직접 부르는 길도 있어 여기가 확실하다.)
    sol.method = method
    sol.freq_nominal = _nominal_freq(case)
    sol.freq_db = _freq_deadband(case)
    try:
        sol.case_tables = {k: np.asarray(v, dtype=float)
                           for k, v in case.tables.items()}
    except Exception:
        sol.case_tables = {}
    return sol


def gs_refusal(case: Any) -> str | None:
    """이 계통을 Gauss-Seidel 로 풀 수 없으면 그 이유를, 풀 수 있으면 None 을 돌려준다.

    엔진(`runpfGS_app.m`)도 같은 것을 검사해 오류를 낸다 — 여기는 **미리 알리기 위한 것**이다.
    화면에서 해법을 고르게 만들 때(§7.6 G8) 이 함수를 불러 Gauss-Seidel 을 흐리게 하고
    까닭을 띄우면, 사용자가 눌러 보고 나서 실패를 겪지 않는다.

    ⚠️ 두 곳에서 같은 것을 검사하는 것은 일부러다 — 화면이 미리 알리고, 엔진이 마지막에 막는다.
       엔진 쪽 검사를 지우면 안 된다(화면을 거치지 않는 호출도 있다).
    """
    try:
        mode = float(case.mode)
    except (TypeError, ValueError):
        mode = float("nan")
    if mode != 1:
        return "Gauss-Seidel 은 AC 단독 계통만 풉니다. 이 계통은 Newton 으로 푸십시오."
    gen = case.tables.get("AC_gen_dat")
    if gen is None:
        return None
    arr = np.asarray(getattr(gen, "values", gen), dtype=float)
    if arr.ndim != 2 or arr.shape[1] < 3:
        return None
    n = int((arr[:, 2] == 1).sum())
    if n:
        return (f"Gauss-Seidel 은 droop 발전기를 다루지 못합니다 (droop 발전기 {n}대). "
                "이 계통은 Newton 방식으로 푸십시오.")
    return None


class Curve:
    """PV·QV 곡선 한 번의 결과. 조류계산의 `Solution` 과 **아무 것도 공유하지 않는다.**

    바깥에서 보는 것
        bus          버스 번호 (nb,)
        lam          부하 배수 λ (n,) — 0 이 지금 부하, 1 이면 두 배
        v            전압 (nb, n) p.u.
        ang          위상 (nb, n) deg
        load_MW      늘린 버스들의 합계 유효부하 (n,) MW
        nose         코 끝점 걸음 번호 (0부터)
        lam_crit     코 끝점의 λ
        nose_MW      코 끝점의 합계 부하 MW
        stop_reason  왜 멈췄나
        pv_bus·pv_Qg 발전기 무효 (n, npv) MVAr — 한계에 걸리는 자리를 볼 때 쓴다
        switched     한계에 걸려 전압을 못 잡게 된 버스 번호
        switch_lam   그 버스가 걸린 λ
    """

    __slots__ = ("bus", "lam", "v", "ang", "load_MW", "nose", "lam_crit",
                 "nose_MW", "stop_reason", "pv_bus", "pv_Qg", "pv_Pg",
                 "switched", "switch_lam", "load_buses", "curve_buses",
                 "use_q_limits", "seconds", "case_name")

    def at(self, bus: int) -> np.ndarray:
        """버스 하나의 전압 곡선 (n,)."""
        idx = int(np.argmin(np.abs(self.bus - float(bus))))
        return self.v[idx, :]


def curve(case: Any, load_buses=None, curve_buses=None, *,
          opts: dict | None = None, mwpython: str | Path | None = None) -> Curve:
    """PV·QV 곡선 한 번 (`runCPF_app`).

    `load_buses`  부하를 늘릴 버스 번호. 비우면 **부하가 있는 버스 전부**.
    `curve_buses` 곡선을 그릴 버스 번호. 비우면 늘린 버스와 같게.

    ⚠️ 조류계산과 **아예 따로** 돈다 — `solve()` 를 부른 적이 없어도 된다.
       대신 화면에서 바꾼 계통 조건(선로·발전기 켜고끄기, 부하 배율)은
       `case.tables` 에 이미 반영돼 있으므로 그대로 따라온다.
    """
    why = curve_refusal(case)
    if why:
        raise RuntimeError(f"곡선을 그릴 수 없습니다 — {why}")

    t0 = time.perf_counter()
    payload = _case_payload(case)
    payload["cpf"] = {
        "load_buses": [float(b) for b in (load_buses or [])],
        "curve_buses": [float(b) for b in (curve_buses or [])],
        "opts": dict(opts or {}),
    }
    if platform.system() == "Windows":
        raw = _curve_in_process(payload)
    else:
        raw = _Worker.get(mwpython).solve(payload, "cpf")
    return _build_curve(raw, time.perf_counter() - t0)


def _build_curve(raw: dict[str, Any], seconds: float) -> Curve:
    c = Curve()
    c.bus = np.asarray(_flat(raw, "bus"), dtype=float)
    c.lam = np.asarray(_flat(raw, "lambda"), dtype=float)
    c.v = _arr(raw, "V_mag")
    c.ang = _arr(raw, "V_ang_deg")
    c.load_MW = np.asarray(_flat(raw, "stressed_load_MW"), dtype=float)
    c.nose = int(raw.get("nose_index", 1)) - 1        # MATLAB 은 1부터 센다
    c.lam_crit = float(raw.get("lambda_crit", float("nan")))
    c.nose_MW = float(raw.get("nose_load_MW", float("nan")))
    c.stop_reason = str(raw.get("stop_reason", ""))
    c.pv_bus = np.asarray(_flat(raw, "pv_bus"), dtype=float)
    c.pv_Qg = _arr(raw, "pv_Qg_MVAR")
    c.pv_Pg = _arr(raw, "pv_Pg_MW")
    c.load_buses = np.asarray(_flat(raw, "load_buses"), dtype=float)
    c.curve_buses = np.asarray(_flat(raw, "curve_buses"), dtype=float)
    c.use_q_limits = bool(raw.get("use_q_limits", 0))
    c.case_name = str(raw.get("case_name", ""))
    c.seconds = seconds

    sw = np.asarray(_flat(raw, "pv_switched"), dtype=float)
    lamsw = np.asarray(_flat(raw, "pv_switch_lam"), dtype=float)
    hit = np.flatnonzero(sw > 0.5)
    c.switched = c.bus[hit] if c.bus.size >= sw.size else np.asarray([], dtype=float)
    c.switch_lam = lamsw[hit] if lamsw.size == sw.size else np.asarray([], dtype=float)
    return c


class Reach:
    """안 풀리는 조건에서 **어디까지면 풀리는지** 찾은 결과 (B3).

        factor      풀리는 가장 큰 부하 배수 (1.0 = 지금 부하). 못 찾으면 None
        sol         그 배수에서의 조류계산 결과 (없으면 None)
        tried       실제로 풀어 본 배수와 결과 [(배수, 풀림 여부), …]
        n_solve     조류계산을 몇 번 돌렸나
        seconds     걸린 시간
        note        사람이 읽을 한 줄
    """

    __slots__ = ("factor", "sol", "tried", "n_solve", "seconds", "note")


def last_solvable(case: Any, *, lo: float = 0.05, rounds: int = 6,
                  mwpython: str | Path | None = None,
                  method: str = "nr", require_qlim: bool = True,
                  on_step=None) -> Reach:
    """부하를 줄여 가며 **풀리는 마지막 지점**을 찾는다 (PDR §7 4단계 B3).

    발산은 "왜 안 되는지"를 말해 주지 않는다. 그런데 사용자가 정작 알고 싶은 것은
    *이 조건이 얼마나 모자라나* 이다 ⇒ 부하 배수를 이분법으로 좁혀
    **"지금 부하의 몇 %까지는 풀린다"** 로 답한다.

    F1(곡선)의 코 끝점과 **같은 뜻**이지만 여기는 앱의 조류계산 엔진을 그대로 쓴다
    ⇒ AC/DC 혼합·IC·DC/DC·droop·3권선 계통에서도 된다(곡선은 AC 단독만).

    `lo`      여기까지 줄여도 안 풀리면 부하 문제가 아니라고 본다
    `rounds`  이분법 횟수. 조류계산 호출은 최대 `rounds + 2`회
    `require_qlim`  **"풀렸다"의 뜻을 정한다.** 참이면 *발전기 무효 한계를 실제로 걸고*
              푼 것만 풀린 것으로 센다.
    `on_step` 진행을 알리고 싶을 때 (배수, 풀림여부, 몇번째) 를 받는 함수

    🚨 `require_qlim` 이 없으면 **없는 여유를 있다고 말한다.** 엔진은 한계를 걸어 수렴하지
       못하면 **한계를 뗀 답**을 돌려주고 `qlim_enforced=False` 로 밝힌다. case14 를 재 보면
       ×1.90 부터 그렇게 되는데, 그 답은 최저 전압이 ×1.73 때보다 오히려 **높다**
       (0.7336 → 0.9825). 발전기가 한계를 넘어야 성립하는 답이라 운전점이 아니다.
       이걸 세면 B3 가 원래 부하의 1.97배까지 된다고 말한다 — 곡선은 1.73배라 한다.
    """
    import scenario as _SC

    t0 = time.perf_counter()
    r = Reach()
    r.tried, r.n_solve, r.factor, r.sol = [], 0, None, None

    def solve_at(k: float):
        nonlocal r
        c = case if k == 1.0 else _SC.apply(case, [_SC.scale_load(k)])
        r.n_solve += 1
        try:
            s = solve(c, mwpython=mwpython, method=method)
            ok = bool(s.converged)
            if ok and require_qlim and not getattr(s, "qlim_enforced", True):
                ok = False          # 한계를 뗀 답 — 운전점이 아니다
        except Exception:                              # noqa: BLE001
            s, ok = None, False
        r.tried.append((k, ok))
        if on_step is not None:
            on_step(k, ok, r.n_solve)
        return ok, s

    # 아래쪽 끝이 풀리는지부터 본다 — 안 풀리면 부하를 줄이는 것으로는 답이 없다.
    ok_lo, sol_lo = solve_at(lo)
    if not ok_lo:
        r.factor, r.sol = None, None
        r.seconds = time.perf_counter() - t0
        r.note = (f"부하를 지금의 {lo * 100:.0f}% 까지 줄여도 안 풀립니다. "
                  f"부하가 많아서가 아니라 계통 모양이나 값 문제일 수 있습니다 "
                  f"— 계통이 두 조각으로 갈라졌는지, 발전기·선로 값이 맞는지 보십시오.")
        return r

    hi = 1.0
    r.factor, r.sol = lo, sol_lo
    for _ in range(rounds):
        mid = 0.5 * (r.factor + hi)
        ok, s = solve_at(mid)
        if ok:
            r.factor, r.sol = mid, s
        else:
            hi = mid

    r.seconds = time.perf_counter() - t0
    r.note = (f"지금 부하의 약 {r.factor * 100:.0f}% 까지는 풀립니다 "
              f"(조류계산 {r.n_solve}회 · {r.seconds:.1f}초).")
    if require_qlim:
        r.note += " 발전기 무효 한계를 지키면서 푼 것만 셌습니다."
    return r


def curve_refusal(case: Any) -> str | None:
    """이 계통으로 곡선을 못 그리면 그 이유를, 그릴 수 있으면 None 을 돌려준다.

    엔진(`runCPF_app.m` 56~86행)도 같은 넷을 검사해 오류를 낸다 — 여기는 **미리 알리기
    위한 것**이다. 화면이 이걸 보고 '곡선' 갈래를 흐리게 하고 까닭을 띄운다.
    (`gs_refusal` 과 같은 짜임 — 화면이 미리 알리고, 엔진이 마지막에 막는다.
     엔진 쪽 검사를 지우면 안 된다.)
    """
    def _tab(name):
        v = case.tables.get(name)
        if v is None:
            return None
        a = np.asarray(getattr(v, "values", v), dtype=float)
        return a if a.ndim == 2 else None

    try:
        mode = float(case.mode)
    except (TypeError, ValueError):
        mode = float("nan")
    if mode != 1:
        return "PV·QV 곡선은 AC 단독 계통만 그립니다."

    tw = _tab("AC_3wtrans_dat")
    if tw is not None and tw.size and not np.all(np.isnan(tw)):
        return (f"PV·QV 곡선은 3권선 변압기가 있는 계통을 아직 다루지 못합니다 "
                f"(3권선 {tw.shape[0]}대).")

    gen = _tab("AC_gen_dat")
    if gen is not None and gen.shape[1] >= 3:
        n = int((gen[:, 2] == 1).sum())
        if n:
            return f"PV·QV 곡선은 droop 발전기를 다루지 못합니다 (droop 발전기 {n}대)."

    bus = _tab("AC_Bus_dat")
    if bus is not None and bus.shape[1] >= 9:
        z = np.nan_to_num(bus[:, 3:9])
        if (np.abs(z[:, [0, 1, 3, 4]]) > 1e-12).any() or \
           (np.abs(z[:, [2, 5]] - 1.0) > 1e-12).any():
            return "PV·QV 곡선은 ZIP 부하(전압에 따라 변하는 부하)를 아직 다루지 못합니다."

    if bus is not None and bus.shape[1] >= 3:
        pl = _tab("AC_PLoad_dat")
        ql = _tab("AC_QLoad_dat")
        has = False
        for t in (pl, ql):
            if t is not None and t.shape[1] >= 2 and np.nan_to_num(t[:, 1:]).any():
                has = True
        if not has:
            return "부하가 있는 버스가 없어 부하를 늘릴 곳이 없습니다."
    return None


def _curve_in_process(payload: dict[str, Any]) -> dict[str, Any]:
    import importlib
    sys.path.insert(0, str(paths.engine_dir()))
    pkg = importlib.import_module("unigrid_app_win")
    import matlab
    app = pkg.initialize()
    try:
        order = ("Base_dat", "AC_Bus_dat", "AC_Line_dat", "AC_gen_dat",
                 "AC_3wtrans_dat", "AC_PLoad_dat", "AC_QLoad_dat")
        args = [matlab.double(payload["tables"][k]) if payload["tables"][k]
                else matlab.double([]) for k in order]
        cpf = payload.get("cpf") or {}

        def row(v):
            return matlab.double([[float(x) for x in v]]) if v else matlab.double([])

        res = app.runCPF_app(payload["case_name"], payload["mode"], *args,
                             row(cpf.get("load_buses")), row(cpf.get("curve_buses")),
                             matlab.double([]), nargout=1)
    finally:
        app.terminate()
    return {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in res.items()}


def _fail_message(err: str, kind: str = "조류계산") -> str:
    """계산이 실패했을 때 사용자에게 보일 문구를 만든다.

    MATLAB 이 돌려주는 글은 이렇게 생겼다 —

        An error occurred when evaluating the result from a function. Details:
          File /…/runpfGS_app.m, line 56, in runpfGS_app
        Gauss-Seidel 은 droop 발전기를 다루지 못합니다 (…). 이 계통은 Newton 으로 푸십시오.

    **우리가 쓴 안내는 맨 끝에 있다.** 그대로 내보내면 화면에는 "조류계산 실패" 와
    영어 잡음만 보이고 정작 이유가 안 보인다(2026-08-12 에 실제로 그랬다).
    ⇒ 한글이 든 마지막 줄을 찾아 **맨 앞으로 올린다.** 못 찾으면 옛 모양 그대로 둔다.
    """
    err = (err or "")[:1500]
    lines = [ln.strip() for ln in err.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if any("가" <= ch <= "힣" for ch in ln):     # 한글이 든 줄
            rest = "\n".join(l for l in lines if l != ln)
            # ⚠️ "조류계산 실패" 를 **빼지 않는다.** 이유만 남기면 사용자도 검사도
            #    무엇이 실패한 것인지 알 수 없다(2026-08-12 에 빼 봤다가 검사 2건이 깨졌다).
            head = f"{kind} 실패 — {ln}"
            return f"{head}\n\n(자세히: {rest})" if rest else head
    return f"{kind} 실패\n{err}"


_GS_LOAD_TABLES = ("AC_PLoad_dat", "AC_QLoad_dat")


def _n_times(case: Any) -> int:
    """부하 표에 시각이 몇 개나 들어 있나. 1열은 버스 번호라 뺀다."""
    n = 1
    for name in _GS_LOAD_TABLES:
        v = case.tables.get(name)
        if v is None:
            continue
        a = np.asarray(getattr(v, "values", v), dtype=float)
        if a.ndim == 2 and a.shape[1] >= 2:
            n = max(n, a.shape[1] - 1)
    return n


def _gs_solve_all_times(case: Any, mwpython: str | Path | None) -> dict[str, Any]:
    """Gauss-Seidel 로 **모든 시각**을 풀어 NR 과 같은 모양으로 돌려준다 (§7.6 G7).

    `runpfGS_app.m` 은 부하 표의 **2열(첫 시각)만** 읽는다(147~154행). 엔진을 시각 루프로
    감싸는 대신 **여기서 시각마다 표를 한 칸씩 잘라 엔진을 다시 부른다.**

    왜 파이썬에서 하나
        · MATLAB 쪽을 안 건드리니 **재컴파일이 없다**(윈도우 빌드 부담도 안 늘어난다).
        · 부하 말고는 시각에 따라 바뀌는 게 없어서, 자를 것이 부하 표 둘뿐이라 단순하다.
        · Newton 도 내부에서 시각마다 다시 푼다 — 차이는 warm start 정도다.

    ⚠️ 시각이 하나뿐이면 예전과 똑같이 한 번만 부른다(빠른 길).
    """
    T = _n_times(case)
    if T <= 1:
        return _gs_to_nr_shape(_run(case, mwpython, "gs"))

    parts: list[dict[str, Any]] = []
    for t in range(T):
        one = case.copy()
        for name in _GS_LOAD_TABLES:
            v = case.tables.get(name)
            if v is None:
                continue
            a = np.asarray(getattr(v, "values", v), dtype=float)
            if a.ndim == 2 and a.shape[1] >= t + 2:
                one.tables[name] = np.column_stack([a[:, 0], a[:, t + 1]])
        parts.append(_gs_to_nr_shape(_run(one, mwpython, "gs")))

    out = dict(parts[0])
    for nr_key in ("AC_all", "DC_all", "Branch_all"):
        blocks = [np.asarray(p[nr_key], dtype=float) for p in parts if nr_key in p]
        if len(blocks) != T:
            continue                      # 어느 시각에서 빠졌으면 손대지 않는다
        shapes = {b.shape for b in blocks}
        if len(shapes) != 1:
            raise RuntimeError(
                f"시각마다 {nr_key} 의 크기가 다릅니다 {sorted(shapes)} — 결과를 쌓을 수 없습니다.")
        nr, nc = blocks[0].shape
        out[nr_key] = np.vstack(blocks).tolist()
        out[nr_key.replace("_all", "_dims")] = [[float(nr), float(nc), float(T)]]
    # 시각별 반복 횟수도 모은다 (NR 의 `all_iter_count` 와 같은 뜻).
    iters = [float(p.get("iter_count", 0) or 0) for p in parts]
    out["iter_count"] = iters[0]
    out["all_iter_count"] = iters
    out["Load_varytime"] = T
    return out


def _gs_to_nr_shape(raw: dict[str, Any]) -> dict[str, Any]:
    """GS 결과를 NR 결과와 같은 모양으로 맞춘다.

    `runpfGS_app` 은 한 시각짜리 2차원 표(`AC_result`·`Branch_result`…)를 주고,
    `runpf_unigrid_app` 은 전 시간대 3차원(`AC_all`·`Branch_all`…)을 준다.
    `_build` 는 뒤쪽 이름을 보므로 여기서 **한 시각을 시간 축 1 짜리로** 감싸 넘긴다.
    (GS 는 아직 한 시각만 푼다 — 다시각은 PDR §7.6 의 G7.)
    """
    out = dict(raw)
    for gs_key, nr_key in (("AC_result", "AC_all"),
                           ("DC_result", "DC_all"),
                           ("Branch_result", "Branch_all")):
        if nr_key in out:
            continue
        v = raw.get(gs_key)
        if v is None:
            continue
        a = np.asarray(v, dtype=float)
        if a.ndim != 2 or a.size == 0:
            continue
        # `cube()` 는 [nr*T x nc] 로 **평평하게** 쌓인 것 + `*_dims`([nr nc T]) 를 본다.
        # GS 는 한 시각이므로 표를 그대로 두고 T=1 짜리 dims 만 붙여 주면 된다.
        out[nr_key] = a.tolist()
        out[nr_key.replace("_all", "_dims")] = [[float(a.shape[0]), float(a.shape[1]), 1.0]]
    # 🚨 반복 횟수의 **이름이 다르다** — GS 는 `iterations`, NR 은 `iter_count` 이고
    #    `_build` 는 뒤쪽만 본다. 옮겨 주지 않으면 화면에 늘 "반복 0회" 로 나온다
    #    (2026-08-12 에 수렴성을 견주려다 발견 — GS 가 232회를 돌았는데 0 으로 왔다).
    if "iter_count" not in out and "iterations" in raw:
        out["iter_count"] = raw["iterations"]
    out.setdefault("Load_varytime", 1)
    return out


def _run(case: Any, mwpython: str | Path | None,
         method: str = "nr") -> dict[str, Any]:
    if platform.system() == "Windows":
        return _run_in_process(case, method)
    return _run_via_mwpython(case, mwpython, method)


def _case_payload(case: Any) -> dict[str, Any]:
    tables = {k: _as_rows(v) for k, v in case.tables.items()}
    return {"case_name": str(case.case_name), "mode": float(case.mode),
            "tables": tables}


def _as_rows(v: Any) -> list:
    if v is None:
        return []
    arr = np.asarray(getattr(v, "values", v), dtype=float)
    if arr.size == 0:
        return []
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    return arr.tolist()


def _run_via_mwpython(case: Any, mwpython: str | Path | None,
                      method: str = "nr") -> dict[str, Any]:
    """계속 살아 있는 계산 프로세스에 일감을 넘긴다 (Runtime 기동 2.7초를 한 번만 낸다)."""
    worker = _Worker.get(mwpython)
    return worker.solve(_case_payload(case), method)


class _Worker:
    """mwpython 계산 프로세스 하나를 띄워두고 재사용한다.

    주의: MATLAB이 '[ACDC NR] 수렴: 2회 반복' 같은 메시지를 같은 통로로 찍는다.
    그래서 응답을 읽을 때 JSON 줄이 나올 때까지 건너뛴다.
    """

    _KEYS = ("ok", "ready", "error")

    # 한 계산에서 나올 수 있는 MATLAB 메시지의 넉넉한 상한.
    # 🚨 **여기를 작게 잡으면 답을 못 찾고 넘어간다.** 예전에 200이었는데,
    #    계산이 안 풀리면 MATLAB 이 특이 행렬 경고와 스택을 **878줄** 찍는다.
    #    그때 답 줄이 통로에 남고 **다음 계산이 그 답을 집어 가서**,
    #    안 풀려야 할 조건이 "잘 풀렸다"로 나왔다(2026-08-06 실제로 확인).
    #    지금은 상한이 아니라 **일감 번호**로 자기 답을 가린다. 이 값은 폭주 방지용일 뿐이다.
    _MAX_LINES = 200_000

    def _read_reply(self, want_id: int | None = None) -> dict:
        """내 일감의 답이 나올 때까지 읽는다.

        want_id 가 있으면 **번호가 맞는 답만** 받는다. 번호가 다른 답(= 앞 계산이
        남기고 간 것)은 버린다. 못 찾고 상한까지 가면 통로가 어긋난 것이므로
        **프로세스를 정리해서** 다음 계산이 깨끗한 상태에서 시작하게 한다.
        """
        stale = 0
        for _ in range(self._MAX_LINES):
            line = self.proc.stdout.readline()
            if not line:
                err = self.proc.stderr.read() if self.proc.stderr else ""
                _Worker._inst = None
                raise RuntimeError(f"계산 엔진이 응답하지 않습니다.\n{err[-1500:]}")
            line = line.strip()
            if not line.startswith("{"):
                continue                      # MATLAB이 찍은 메시지 — 건너뜀
            try:
                ans = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not any(k in ans for k in self._KEYS):
                continue
            if want_id is not None and ans.get("id") != want_id:
                stale += 1                    # 앞 계산이 남기고 간 답 — 버린다
                continue
            return ans
        self._drop("계산 엔진이 너무 많은 메시지를 쏟아내 결과를 찾지 못했습니다.")
        raise RuntimeError(
            "계산 엔진에서 결과를 받지 못했습니다.\n"
            f"(메시지 {self._MAX_LINES}줄을 읽고도 못 찾았습니다"
            + (f" · 버린 옛 답 {stale}개" if stale else "") + ")")

    def _drop(self, why: str = "") -> None:
        """이 프로세스를 버린다 — 다음 계산은 새로 띄운 것에서 시작한다.

        통로가 한 번 어긋나면 그 뒤 답은 전부 한 칸씩 밀린다. 되살리려 하지 말고 버린다.
        """
        try:
            self.proc.kill()
        except Exception:
            pass
        if _Worker._inst is self:
            _Worker._inst = None

    _inst: "_Worker | None" = None

    def __init__(self, mwpython: str | Path | None):
        # 자리를 못 찾으면 engine_path 가 EngineNotFound(안내문을 들고 있음)를 던진다.
        # 부르는 쪽(app.py)이 그것을 받아 안내 대화상자로 띄운다.
        self.exe = str(mwpython or engine_path.find_mwpython())
        self.proc = subprocess.Popen(
            [self.exe, str(paths.worker_py()), "--serve"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        # 준비 신호를 기다린다 (Runtime 기동)
        ans = self._read_reply()
        if not ans.get("ready"):
            raise RuntimeError(f"계산 엔진을 띄우지 못했습니다: {ans}")
        self.dir = tempfile.mkdtemp(prefix="unigrid_")
        self.job = 0                          # 일감 번호 — 답이 자기 것인지 가리는 데 쓴다

    @classmethod
    def get(cls, mwpython: str | Path | None = None) -> "_Worker":
        if cls._inst is None or cls._inst.proc.poll() is not None:
            cls._inst = _Worker(mwpython)
        return cls._inst

    @classmethod
    def shutdown(cls) -> None:
        if cls._inst is not None and cls._inst.proc.poll() is None:
            try:
                cls._inst.proc.stdin.write(json.dumps({"quit": True}) + "\n")
                cls._inst.proc.stdin.flush()
                cls._inst.proc.wait(timeout=5)
            except Exception:
                cls._inst.proc.kill()
        cls._inst = None

    def solve(self, payload: dict[str, Any], method: str = "nr") -> dict[str, Any]:
        self.job += 1
        job_id = self.job
        # 일감마다 다른 파일에 쓴다. 앞 계산의 결과 파일이 남아 있어도 그것을 읽을 일이 없다.
        inp = Path(self.dir) / f"case_{job_id}.json"
        out = Path(self.dir) / f"result_{job_id}.json"
        inp.write_text(json.dumps(payload), encoding="utf-8")
        self.proc.stdin.write(
            json.dumps({"in": str(inp), "out": str(out), "id": job_id,
                        "method": method}) + "\n")
        self.proc.stdin.flush()
        ans = self._read_reply(want_id=job_id)
        if not ans.get("ok"):
            # 안 풀린 것뿐이다 — 프로세스는 멀쩡하니 그대로 두고 다음 계산을 받는다.
            kind = "곡선" if method == "cpf" else "조류계산"
            raise RuntimeError(_fail_message(ans.get("error", ""), kind))
        if not out.exists():
            self._drop()
            raise RuntimeError("계산은 끝났다는데 결과 파일이 없습니다.")
        try:
            return json.loads(out.read_text(encoding="utf-8"))
        finally:
            for f in (inp, out):              # 오래 켜 두어도 쌓이지 않게
                try:
                    f.unlink()
                except OSError:
                    pass


def _run_in_process(case: Any, method: str = "nr") -> dict[str, Any]:
    import importlib
    sys.path.insert(0, str(paths.engine_dir()))
    pkg = importlib.import_module("unigrid_app_win")
    import matlab
    app = pkg.initialize()
    try:
        payload = _case_payload(case)
        order = ("Base_dat", "AC_Bus_dat", "AC_Line_dat", "AC_gen_dat",
                 "AC_3wtrans_dat", "DC_Bus_dat", "DC_Line_dat", "DC_gen_dat",
                 "IC_dat", "DCDC_Conv_dat", "AC_PLoad_dat", "AC_QLoad_dat",
                 "DC_PLoad_dat")
        args = [matlab.double(payload["tables"][k]) if payload["tables"][k]
                else matlab.double([]) for k in order]
        if method == "gs":
            gs_order = ("Base_dat", "AC_Bus_dat", "AC_Line_dat", "AC_gen_dat",
                        "AC_3wtrans_dat", "AC_PLoad_dat", "AC_QLoad_dat")
            gs_args = [matlab.double(payload["tables"][k]) if payload["tables"][k]
                       else matlab.double([]) for k in gs_order]
            res = app.runpfGS_app(payload["case_name"], payload["mode"],
                                  *gs_args, nargout=1)
        else:
            res = app.runpf_unigrid_app(payload["case_name"], payload["mode"],
                                        *args, nargout=1)
    finally:
        app.terminate()
    return {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in res.items()}


# ─────────────────────────────────────────── 결과 정리
def _arr(raw: dict, key: str) -> np.ndarray:
    v = raw.get(key)
    if v is None:
        return np.zeros((0, 0))
    try:
        return np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        # 숫자로 못 바꾸는 값이 오면 앱을 죽이지 말고 그 표만 비운다.
        # (원래 원인은 계산 프로세스 쪽에서 고쳤지만, 다른 경로로 또 들어와도 창은 떠야 한다)
        print(f"[결과] '{key}' 를 숫자로 바꾸지 못해 비웁니다: {str(v)[:120]}")
        return np.zeros((0, 0))


TAP_COLS = 11
"""탭·위상 조정 결과의 열 수.

[선로, 보는버스, 목표, 정한값, 살아있나, 하한, 상한, 한계자동, **방식**]
방식 1 = 탭 조정(목표 pu · 값 탭비) · 2 = 위상 조정기(목표 MW · 값 deg, 보는버스 0)."""


def _tap_arr(raw: dict) -> np.ndarray:
    """탭 자동 조정 결과를 항상 (줄수, 8) 모양으로 (2026-08-13, A1).

    한 대뿐이면 MATLAB 이 1차원으로 넘긴다 — 모양을 여기서 맞춘다.
    옛 엔진(그 필드가 없는 것)이면 빈 표가 된다.
    ⚠️ 옛 엔진도 받는다 — 5열(15차)·8열(16차). 모자란 칸은 비워 채우되 **방식은 1**
       로 둔다(그 엔진들엔 탭밖에 없었다). 앱이 안 죽고 새 안내만 안 뜬다.
    """
    a = _arr(raw, "Tap_result")
    if a.size == 0:
        return np.empty((0, TAP_COLS))
    # 🚨 **옛 엔진의 열 수를 여기 다 적어 둬야 한다.** 하나라도 빠지면 표를 통째로
    #    버리고, 화면에는 "조정을 안 걸었다" 로 보인다 — 조용히 사라지는 종류다.
    #    5열(15차) · 8열(16차) · 9열(17~19차, 방식이 붙음) · 11열(20차, 계단).
    OK = (5, 8, 9, TAP_COLS)
    if a.ndim == 1:
        a = a.reshape(1, -1) if a.size in OK else np.empty((0, TAP_COLS))
    if a.ndim != 2 or a.shape[1] not in OK:
        print(f"[결과] 탭 조정 표의 열 수가 {OK} 중 하나가 아니라 비웁니다: {a.shape}")
        return np.empty((0, TAP_COLS))
    if a.shape[1] < TAP_COLS:                 # 옛 엔진
        had = a.shape[1]
        pad = np.full((a.shape[0], TAP_COLS - had), np.nan)
        a = np.hstack([a, pad])
        if had < 9:
            a[:, 8] = 1                       # 그 엔진들엔 탭밖에 없었다
        # 계단 칸은 **0 으로** 채운다(NaN 이 아니라) — 화면이 int() 로 읽는다.
        a[:, 9] = 0.0                         # 한 단 크기 없음 = 연속
        a[:, 10] = 0.0                        # 계단으로 내린 적 없음
    return a


def _gen_limit_arr(raw: dict) -> np.ndarray:
    """발전기 출력한계 표를 항상 (줄수, 11) 모양으로 돌려준다.

    발전기가 한 대뿐이면 MATLAB 이 한 줄짜리를 1차원으로 넘기는 일이 있어
    모양을 여기서 한 번 맞춘다. 옛 엔진(그 필드가 없는 것)이면 빈 표가 된다.
    """
    a = _arr(raw, "Gen_limit_result")
    if a.size == 0:
        return np.empty((0, 11))
    if a.ndim == 1:
        a = a.reshape(1, -1) if a.size == 11 else np.empty((0, 11))
    if a.ndim != 2 or a.shape[1] != 11:
        print(f"[결과] 발전기 한계 표의 열 수가 11이 아니라 비웁니다: {a.shape}")
        return np.empty((0, 11))
    return a


def _flat(raw: dict, key: str) -> list[float]:
    a = _arr(raw, key)
    return [float(x) for x in a.reshape(-1)] if a.size else []


def _fix_loss_percent(loss: np.ndarray, mode: int) -> np.ndarray:
    """🚨 손실 백분율이 1e6 배 부풀려져 오는 것을 여기서 한 번만 바로잡는다.

    `functions/extract_ACDC_results.m` 106·109줄에서 **분자와 분모의 단위가
    다르다** — 분자 `P_loss_spec` 은 W(99·100줄에서 1e6 을 곱한다)인데
    분모 `P_gen_sum` 은 MW 다(103줄 주석이 직접 "Gen[MW]" 라고 적어 놨다).
    그래서 값이 1,000,000 배로 나온다:
      12버스 Ploss[%] = 155,086 (실제 0.155%) / CIGRE = 4.89e6 (실제 4.89%).

    **AC only·DC only 경로는 정상**이다 — `extract_AC_results.m` 85줄과
    `extract_DC_results.m` 58줄은 분모가 `sum(P_G)*S_base` 라 분자와 같은
    W 단위다. 그래서 **혼합(mode 0) 결과만** 고친다.

    고칠 자리는 원래 MATLAB 쪽이지만 사용자가 **원본은 그대로 두고 앱에서만
    바로잡기로** 정했다(2026-07-19). 여기 한 곳에서 고치므로 화면 표·비교
    그래프·내보낸 엑셀이 **전부 같은 값**을 쓴다.
    ⚠️ 그 결과 `Loss_results.xlsx` 의 백분율 열은 **원본 앱이 뽑던 값과
    다르다**(이쪽이 맞는 값이다).
    """
    if mode != 0 or loss.size == 0 or loss.ndim != 2:
        return loss
    out = loss.astype(float, copy=True)
    for j in (3, 4):                       # 4·5열 = Ploss[%], Qloss[%]
        if j < out.shape[1]:
            out[:, j] /= 1e6
    return out


def _build(raw: dict[str, Any], seconds: float) -> Solution:
    n_time = int(raw.get("Load_varytime", 1) or 1)

    def cube(key: str) -> np.ndarray:
        """[nr*T x nc] 로 쌓여 온 것을 [nr x nc x T] 로 되돌린다."""
        a = _arr(raw, key)
        dims = _arr(raw, key.replace("_all", "_dims")).reshape(-1)
        if a.size == 0 or dims.size < 3:
            return np.zeros((0, 0, 0))
        nr, nc, T = (int(x) for x in dims[:3])
        if nr == 0 or nc == 0 or T == 0:
            return np.zeros((0, 0, 0))
        out = np.zeros((nr, nc, T))
        for t in range(T):
            out[:, :, t] = a[t * nr:(t + 1) * nr, :]
        return out

    names = raw.get("block_names") or []
    if isinstance(names, str):
        names = [names]
    dom = raw.get("dominant_block") or []
    if isinstance(dom, str):
        dom = [dom]

    mode = int(round(float(raw.get("mode", 0))))
    return Solution(
        case_name=str(raw.get("case_name", "")),
        mode=mode,
        baseMVA=float(raw.get("baseMVA", 0.0)),
        n_time=n_time,
        AC=cube("AC_all"),
        DC=cube("DC_all"),
        Branch=cube("Branch_all"),
        loss=_fix_loss_percent(_arr(raw, "total_loss_table"), mode),
        freq=np.asarray(_flat(raw, "freq_all"), dtype=float),
        VSC_bus=(_arr(raw, "VSC_bus") if "VSC_bus" in raw else None),
        converged=bool(float(raw.get("converged", 0))),
        iters=int(float(raw.get("iter_count", 0))),
        threshold=float(raw.get("threshold", 0.0)),
        mis_history=_flat(raw, "mis_history"),
        block_names=[str(x) for x in names],
        block_history=_arr(raw, "block_history"),
        dominant_block=[str(x) for x in dom],
        IC_lim_mode=_flat(raw, "IC_lim_mode"),
        gen_limit=_gen_limit_arr(raw),
        tap_ctrl=_tap_arr(raw),
        qlim_enforced=bool(np.ravel(raw.get("qlim_enforced", [1]))[0]),
        qlim_message=str(raw.get("qlim_message", "") or ""),
        qlim_bound=int(float(np.ravel(raw.get("qlim_bound", [0]))[0] or 0)),
        qlim_bound_up=int(float(np.ravel(raw.get("qlim_bound_up", [0]))[0] or 0)),
        qlim_bound_dn=int(float(np.ravel(raw.get("qlim_bound_dn", [0]))[0] or 0)),
        seconds=seconds,
        raw=raw,
    )


def warmup(mwpython: str | Path | None = None) -> bool:
    """계산 엔진을 미리 띄워둔다 (시작 화면에서 부르면 첫 계산이 빨라진다)."""
    if platform.system() == "Windows":
        return True
    _Worker.get(mwpython)
    return True


def is_ready() -> bool:
    return platform.system() == "Windows" or (
        _Worker._inst is not None and _Worker._inst.proc.poll() is None)


def shutdown() -> None:
    """앱을 닫을 때 계산 프로세스를 정리한다."""
    if platform.system() != "Windows":
        _Worker.shutdown()


if __name__ == "__main__":
    # 자체 확인:  python src/app_engine.py <케이스파일>
    sys.path.insert(0, str(_HERE))
    from load_case import load_case  # type: ignore

    path = sys.argv[1] if len(sys.argv) > 1 else "ACDC_CIGRE_MVACMVDCLVDC_24h.xlsx"
    case_obj = load_case(path)
    sol = solve(case_obj)
    sol2 = solve(case_obj)   # 두 번째 — 계산 프로세스 재사용
    print(f"case      : {sol.case_name}  ({sol.mode_name})")
    print(f"시간대    : {sol.n_time}")
    print(f"AC        : {sol.AC.shape}   열={sol.cols('AC')[:4]}...")
    print(f"Branch    : {sol.Branch.shape}")
    print(f"수렴      : {sol.converged}  반복 {sol.iters}회  기준 {sol.threshold}")
    print(f"불평형    : {[f'{m:.2e}' for m in sol.mis_history]}")
    print(f"계산 시간 : 1회차 {sol.seconds:.2f} s / 2회차 {sol2.seconds:.2f} s")
    if sol.n_time > 1:
        print(f"버스1 전압 시간변화(앞 5개): {sol.series('AC', 1, 0)[:5]}")
