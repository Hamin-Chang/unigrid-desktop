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

_HERE = Path(__file__).resolve().parent
# 컴파일된 엔진은 저장소에 **한 자리**에만 둔다 (README 폴더 규칙 · PDR §4.2 규칙 3).
_ENGINE_DIR = _HERE.parent / "engine"

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


def solve(case: Any, *, mwpython: str | Path | None = None) -> Solution:
    """조류계산 한 번 — 전 시간대 결과를 담은 Solution 을 돌려준다."""
    global _solve_count
    t0 = time.perf_counter()
    raw = _run(case, mwpython)
    _solve_count += 1
    sol = _build(raw, time.perf_counter() - t0)
    sol.freq_nominal = _nominal_freq(case)
    sol.freq_db = _freq_deadband(case)
    try:
        sol.case_tables = {k: np.asarray(v, dtype=float)
                           for k, v in case.tables.items()}
    except Exception:
        sol.case_tables = {}
    return sol


def _run(case: Any, mwpython: str | Path | None) -> dict[str, Any]:
    if platform.system() == "Windows":
        return _run_in_process(case)
    return _run_via_mwpython(case, mwpython)


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


def _run_via_mwpython(case: Any, mwpython: str | Path | None) -> dict[str, Any]:
    """계속 살아 있는 일꾼에게 일감을 넘긴다 (Runtime 기동 2.7초를 한 번만 낸다)."""
    worker = _Worker.get(mwpython)
    return worker.solve(_case_payload(case))


class _Worker:
    """mwpython 일꾼 프로세스 하나를 띄워두고 재사용한다.

    주의: MATLAB이 '[ACDC NR] 수렴: 2회 반복' 같은 메시지를 같은 통로로 찍는다.
    그래서 응답을 읽을 때 JSON 줄이 나올 때까지 건너뛴다.
    """

    _KEYS = ("ok", "ready", "error")

    def _read_reply(self, timeout_lines: int = 200) -> dict:
        for _ in range(timeout_lines):
            line = self.proc.stdout.readline()
            if not line:
                err = self.proc.stderr.read() if self.proc.stderr else ""
                _Worker._inst = None
                raise RuntimeError(f"계산 일꾼이 응답하지 않습니다.\n{err[-1500:]}")
            line = line.strip()
            if not line.startswith("{"):
                continue                      # MATLAB이 찍은 메시지 — 건너뜀
            try:
                ans = json.loads(line)
            except json.JSONDecodeError:
                continue
            if any(k in ans for k in self._KEYS):
                return ans
        raise RuntimeError("계산 일꾼의 응답을 찾지 못했습니다.")

    _inst: "_Worker | None" = None

    def __init__(self, mwpython: str | Path | None):
        # 자리를 못 찾으면 engine_path 가 EngineNotFound(안내문을 들고 있음)를 던진다.
        # 부르는 쪽(app.py)이 그것을 받아 안내 대화상자로 띄운다.
        self.exe = str(mwpython or engine_path.find_mwpython())
        self.proc = subprocess.Popen(
            [self.exe, str(_HERE / "app_worker.py"), "--serve"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        # 준비 신호를 기다린다 (Runtime 기동)
        ans = self._read_reply()
        if not ans.get("ready"):
            raise RuntimeError(f"계산 일꾼을 띄우지 못했습니다: {ans}")
        self.dir = tempfile.mkdtemp(prefix="unigrid_")

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

    def solve(self, payload: dict[str, Any]) -> dict[str, Any]:
        inp = Path(self.dir) / "case.json"
        out = Path(self.dir) / "result.json"
        if out.exists():
            out.unlink()
        inp.write_text(json.dumps(payload), encoding="utf-8")
        self.proc.stdin.write(
            json.dumps({"in": str(inp), "out": str(out)}) + "\n")
        self.proc.stdin.flush()
        ans = self._read_reply()
        if not ans.get("ok"):
            raise RuntimeError(f"조류계산 실패\n{ans.get('error', '')[:1500]}")
        return json.loads(out.read_text(encoding="utf-8"))


def _run_in_process(case: Any) -> dict[str, Any]:
    import importlib
    sys.path.insert(0, str(_ENGINE_DIR))
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
        # (원래 원인은 일꾼 쪽에서 고쳤지만, 다른 경로로 또 들어와도 창은 떠야 한다)
        print(f"[결과] '{key}' 를 숫자로 바꾸지 못해 비웁니다: {str(v)[:120]}")
        return np.zeros((0, 0))


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
        qlim_enforced=bool(np.ravel(raw.get("qlim_enforced", [1]))[0]),
        qlim_message=str(raw.get("qlim_message", "") or ""),
        seconds=seconds,
        raw=raw,
    )


def warmup(mwpython: str | Path | None = None) -> bool:
    """계산 일꾼을 미리 띄워둔다 (시작 화면에서 부르면 첫 계산이 빨라진다)."""
    if platform.system() == "Windows":
        return True
    _Worker.get(mwpython)
    return True


def is_ready() -> bool:
    return platform.system() == "Windows" or (
        _Worker._inst is not None and _Worker._inst.proc.poll() is None)


def shutdown() -> None:
    """앱을 닫을 때 일꾼 프로세스를 정리한다."""
    if platform.system() != "Windows":
        _Worker.shutdown()


if __name__ == "__main__":
    # 자체 확인:  python src/app_engine.py <케이스파일>
    sys.path.insert(0, str(_HERE))
    from load_case import load_case  # type: ignore

    path = sys.argv[1] if len(sys.argv) > 1 else "ACDC_CIGRE_MVACMVDCLVDC_24h.xlsx"
    case_obj = load_case(path)
    sol = solve(case_obj)
    sol2 = solve(case_obj)   # 두 번째 — 일꾼 재사용
    print(f"case      : {sol.case_name}  ({sol.mode_name})")
    print(f"시간대    : {sol.n_time}")
    print(f"AC        : {sol.AC.shape}   열={sol.cols('AC')[:4]}...")
    print(f"Branch    : {sol.Branch.shape}")
    print(f"수렴      : {sol.converged}  반복 {sol.iters}회  기준 {sol.threshold}")
    print(f"불평형    : {[f'{m:.2e}' for m in sol.mis_history]}")
    print(f"계산 시간 : 1회차 {sol.seconds:.2f} s / 2회차 {sol2.seconds:.2f} s")
    if sol.n_time > 1:
        print(f"버스1 전압 시간변화(앞 5개): {sol.series('AC', 1, 0)[:5]}")
