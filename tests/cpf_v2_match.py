"""F1 — PV·QV 곡선이 v2 엑셀과 맞물리는가 (2026-08-12).

    python tests/cpf_v2_match.py

무엇을 보나
    이식본 `runCPF_app.m` 은 배포본 `runCPF.m` 의 **v1 열 번호**를 그대로 물려받았다
    (AC Bus 12열 = V0, 14열 = V_base …). 앱이 여는 것은 **v2 엑셀**이므로,
    v2 를 읽어 만든 표가 그 열 번호와 실제로 맞는지 확인해야 한다.

🚨 "돌아간다" 는 통과가 아니다. 열이 하나 밀려도 계산은 그냥 돌아간다.
    그래서 **λ = 0 지점의 전압을 앱의 조류계산(NR) 답과 견준다** — 곡선의 출발점은
    정의상 그 계통의 조류계산 답이므로, 열이 밀렸으면 여기서 어긋난다.

    ⚠️ 한 가지 아는 차이 = 앱 NR 은 **발전기 무효 한계를 늘 걸고**, CPF 의 기저
    조류계산은 걸지 않는다. 그래서 한계에 걸리는 계통은 λ=0 에서도 갈린다.
    이 시험은 그 갈림을 **세어서 보여 준다**(F1c 판단 재료).
"""
from __future__ import annotations

import json
import subprocess
import sys
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
warnings.filterwarnings("ignore")

import numpy as np
from scipy.io import savemat, loadmat

from load_case import load_case
import app_engine

V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
MATLAB = "/Applications/MATLAB_R2024b.app/bin/matlab"
WORK = Path("/private/tmp/claude-501/-Users-hamin-Desktop-GML-01-----------ACDC-01-Unigrid"
            "-Phase-A-Balance-newest-v14-03---UNIGRID-UNIGRID-v2"
            "/1507b381-dd60-42ab-9d1c-fcbc451d8257/scratchpad/f1/v2match")

TABLES = ["Base_dat", "AC_Bus_dat", "AC_Line_dat", "AC_gen_dat",
          "AC_3wtrans_dat", "AC_PLoad_dat", "AC_QLoad_dat"]

TOL = 1e-4          # p.u. — 결과표가 4자리로 반올림되므로 그보다 아래는 못 본다

# 큰 계통은 이 시험에서 뺀다(2026-08-12 사용자 지시 "너무 큰 계통 같은게 cpf가
# 안돌아가는거면 안해도 돼. 일단 되는데까지만"). 곡선 자체는 25,000버스도 돌지만
# 한 번에 171초라 매번 돌리는 시험에는 안 맞는다.
MAX_BUS = 1000


def pickable(case) -> str:
    """이 계통을 곡선이 다룰 수 있나. 못 다루면 그 이유를 돌려준다."""
    if float(case.mode) != 1.0:
        return "AC 단독이 아님"
    tw = np.asarray(case.tables["AC_3wtrans_dat"], dtype=float)
    if tw.size and not np.all(np.isnan(tw)):
        return "3권선 있음"
    g = np.asarray(case.tables["AC_gen_dat"], dtype=float)
    if g.shape[1] >= 3 and np.any(g[:, 2] == 1):
        return "droop 발전기"
    b = np.asarray(case.tables["AC_Bus_dat"], dtype=float)
    if b.shape[1] >= 9:
        z = np.nan_to_num(b[:, 3:9])
        if (np.abs(z[:, [0, 1, 3, 4]]) > 1e-12).any() or \
           (np.abs(z[:, [2, 5]] - 1.0) > 1e-12).any():
            return "ZIP 부하"
    return ""


def nr_voltage(case):
    """앱 조류계산(NR)의 첫 시각 [버스번호, 전압, 위상].

    🚨 열을 번호로 짚지 말 것 — 0열은 **버스 번호**다(전압이 아니다).
       이름표(`sol.cols('AC')`)로 찾는다. 처음에 0·1열을 전압·위상으로 읽어
       "전압이 6498 만큼 어긋난다" 는 헛 결과를 냈다.
    """
    sol = app_engine.solve(case)
    a = np.asarray(sol.at("AC", 0), dtype=float)
    cols = sol.cols("AC")
    return (a[:, cols.index("Bus")].copy(),
            a[:, cols.index("VM[pu]")].copy(),
            a[:, cols.index("Angle[deg]")].copy(), sol)


def qlim_hits(sol) -> int:
    """앱 NR 에서 무효 한계에 걸린 발전기 수 (11열 규약의 satQ)."""
    gl = getattr(sol, "gen_limit", None)
    if gl is None:
        return 0
    a = np.asarray(gl, dtype=float)
    if a.ndim == 3:
        a = a[:, :, 0]
    return int((a[:, 9] == 1).sum()) if a.size else 0


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    files = sorted((V14 / "cases_v2").glob("AConly_*_v2.xlsx"))
    if not files:
        print("v2 케이스를 못 찾음"); return 1

    jobs, skipped = [], []
    for f in files:
        name = f.stem[:-3]
        try:
            case = load_case(str(f))
        except Exception as exc:                       # noqa: BLE001
            skipped.append((name, f"못 읽음: {exc}")); continue
        nb_count = np.asarray(case.tables["AC_Bus_dat"], dtype=float).shape[0]
        if nb_count > MAX_BUS:
            skipped.append((name, f"버스 {nb_count}개 — 시험에서 뺌(상한 {MAX_BUS})")); continue
        why = pickable(case)
        if why:
            skipped.append((name, why)); continue
        try:
            nb_no, vm, va, sol = nr_voltage(case)
        except Exception as exc:                       # noqa: BLE001
            skipped.append((name, f"NR 실패: {exc}")); continue
        if not sol.converged:
            skipped.append((name, "NR 미수렴")); continue

        m = {k: np.asarray(case.tables[k], dtype=float) for k in TABLES}
        m["case_name"] = name
        savemat(str(WORK / f"{name}.mat"), m)
        jobs.append((name, nb_no, vm, va, sol))

    print(f"곡선 대상 {len(jobs)}개 · 건너뜀 {len(skipped)}개")
    for n, w in skipped:
        print(f"    - {n:28s} {w}")
    if not jobs:
        print("대조 0건 = 실패"); return 1

    script = WORK / "run_all.m"
    script.write_text(f"""
addpath('{V14}');
d = '{WORK}';
names = {{{', '.join(f"'{n}'" for n, *_ in jobs)}}};
out = struct();
for i = 1:numel(names)
    nm = names{{i}};
    S = load(fullfile(d, [nm '.mat']));
    tw = S.AC_3wtrans_dat;
    if all(isnan(tw(:))), tw = []; end
    try
        evalc(['o = runCPF_app(nm, 1, S.Base_dat, S.AC_Bus_dat, S.AC_Line_dat, ' ...
               'S.AC_gen_dat, tw, S.AC_PLoad_dat, S.AC_QLoad_dat, [], []);']);
        r.ok = 1; r.V0 = o.V_mag(:,1)'; r.A0 = o.V_ang_deg(:,1)';
        r.bus = o.bus; r.lam = o.lambda_crit; r.n = o.n_steps;
        r.nose_MW = o.nose_load_MW; r.err = '';
    catch ME
        r = struct('ok',0,'V0',[],'A0',[],'bus',[],'lam',nan,'n',0,'nose_MW',nan, ...
                   'err',[ME.identifier ' | ' ME.message]);
    end
    out.(matlab.lang.makeValidName(nm)) = r;
end
save(fullfile(d,'out.mat'), 'out');
disp('DONE');
""", encoding="utf-8")

    log = WORK / "run_all.log"
    with log.open("w") as fh:
        rc = subprocess.run([MATLAB, "-batch", f"run('{script}')"],
                            stdout=fh, stderr=subprocess.STDOUT).returncode
    if rc != 0:
        print(f"MATLAB 종료 코드 {rc} — {log}"); print(log.read_text()[-1500:]); return 1

    res = loadmat(str(WORK / "out.mat"), squeeze_me=True, struct_as_record=False)["out"]

    print(f"\n{'계통':26s} {'버스':>5s} {'λ_crit':>8s} {'스텝':>6s} "
          f"{'λ=0 전압 최대차':>14s} {'위상 최대차':>11s} {'한계':>4s}  판정")
    total_cmp = 0
    bad = 0
    for name, nb_no, vm, va, sol in jobs:
        key = name.replace("-", "_")
        r = getattr(res, key)
        if not int(r.ok):
            print(f"{name:26s} {'':>4s} {'':>8s} {'':>6s} {'':>14s} {'':>11s}  "
                  f"거부 [{r.err}]")
            bad += 1
            continue
        v0 = np.atleast_1d(np.asarray(r.V0, dtype=float))
        a0 = np.atleast_1d(np.asarray(r.A0, dtype=float))
        bus = np.atleast_1d(np.asarray(r.bus, dtype=float))

        # 🚨 순서를 믿지 말고 **버스 번호로 맞춘다**
        pos = {int(b): i for i, b in enumerate(bus)}
        pick = [pos.get(int(b), -1) for b in nb_no]
        if any(i < 0 for i in pick):
            missing = [int(b) for b, i in zip(nb_no, pick) if i < 0]
            print(f"{name:26s}  곡선 쪽에 없는 버스 {missing[:5]} ← 문제")
            bad += 1
            continue
        idx = np.array(pick)
        dv = float(np.max(np.abs(v0[idx] - vm)))
        da = float(np.max(np.abs(a0[idx] - va)))
        total_cmp += 2 * len(idx)
        nq = qlim_hits(sol)
        ok = dv < TOL and da < 1e-2
        # 어긋나도 **앱 NR 이 한계를 건 계통**이면 아는 차이다 — CPF 의 기저 조류계산은
        # 한계를 안 건다(F1c 에서 정할 일). 한계가 0 인데 어긋나면 그건 진짜 문제다.
        verdict = "같음" if ok else ("한계 탓" if nq else "⚠ 어긋남")
        if not ok and not nq:
            bad += 1
        print(f"{name:26s} {len(idx):5d} {r.lam:8.4f} {int(r.n):6d} "
              f"{dv:14.3e} {da:11.3e} {nq:4d}  {verdict}")

    print(f"\n>>> 대조 {total_cmp}개 · 설명 안 되는 어긋남 {bad}개")
    if total_cmp == 0:
        print("대조 0개 = 실패"); return 1
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
