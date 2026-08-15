# -*- coding: utf-8 -*-
"""A1 탭 자동 조정 — 엔진이 실제로 그렇게 푸는가 (2026-08-13, §7 5단계 2번).

    python tests/test_a1_tap.py

무엇을 보나
    1) **끄면 v3 때와 완전히 같은가** (위험 R1 의 완료 조건)
    2) 목표 전압을 실제로 맞추나
    3) 그 답이 맞는가 — 찾은 탭을 **고정값**으로 넣고 손 안 댄 길로 다시 풀면 같은가
    4) 한계 — 못 미치는 목표면 한계에서 멈추고 놓아주나
    5) 못 하는 설정을 분명히 막나 (위상 조정기 · 계단 탭 · 제어 버스가 PV)
    6) **한계를 비우면 0.9~1.1 로 잡고, 그렇게 잡았다고 밝히나** (2026-08-13)

⚠️ **컴파일된 엔진이 아니라 `.m` 소스를 돌린다.** 엔진에 v4 를 넣는 재컴파일은 A1 이
   끝난 뒤에 한 번에 하기로 했으므로(§7 5단계 5번), 그 전까지는 이 시험이 지킴이다.
   곡선 때 `tests/cpf_v2_match.py` 가 쓴 방식과 같다.
"""
from __future__ import annotations

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

V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
MATLAB = "/Applications/MATLAB_R2024b.app/bin/matlab"
WORK = Path("/private/tmp/claude-501/-Users-hamin-Desktop-GML-01-----------ACDC-01-Unigrid"
            "-Phase-A-Balance-newest-v14-03---UNIGRID-UNIGRID-v2"
            "/1507b381-dd60-42ab-9d1c-fcbc451d8257/scratchpad/a1/test")

CASE = "AConly_case14_v2.xlsx"
CTRL_ROW = 9        # 9번 선로 = 변압기 4→9
CTRL_BUS = 9        # 버스 9 (PQ 버스)
TARGET = 1.035      # 탭 0.8~1.2 안에서 **도달 가능한** 값
                    # 🚨 1.00 은 도달 불가능하다 — 탭 0.9~1.2 에서 전압이
                    #    1.0629~1.0128 로만 움직인다(2026-08-13 실측).
                    #    못 미치는 목표를 주면 [4] 처럼 한계에서 멈추는 게 **맞는 동작**이다.

TABLES = ["Base_dat", "AC_Bus_dat", "AC_Line_dat", "AC_gen_dat", "AC_3wtrans_dat",
          "DC_Bus_dat", "DC_Line_dat", "DC_gen_dat", "IC_dat", "DCDC_Conv_dat",
          "AC_PLoad_dat", "AC_QLoad_dat", "DC_PLoad_dat"]


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    case = load_case(str(V14 / "cases_v2" / CASE))
    T = {k: np.asarray(v, dtype=float) for k, v in case.tables.items()}
    savemat(str(WORK / "case.mat"), T)

    script = WORK / "run.m"
    script.write_text(f"""
v14 = '{V14}';
addpath(v14); addpath(fullfile(v14,'functions'));
d = '{WORK}';
S = load(fullfile(d,'case.mat'));
ORD = {{{', '.join(f"'{t}'" for t in TABLES)}}};
ROW = {CTRL_ROW};  BUS = {CTRL_BUS};  TGT = {TARGET};

function [V, err, TR] = solve_with(S, ORD, L, tag)
    a = cell(1,numel(ORD));
    for k = 1:numel(ORD)
        if strcmp(ORD{{k}},'AC_Line_dat'), a{{k}} = L; else, a{{k}} = S.(ORD{{k}}); end
    end
    TR = [];
    try
        [~, r] = evalc('runpf_unigrid_app(tag, 1, a{{:}})');
        V = r.AC_all(:,2,1);  err = '';
        if isfield(r,'Tap_result'), TR = r.Tap_result; end
    catch ME
        V = [];  err = [ME.identifier '|' ME.message];
    end
end

out = struct();
L13 = S.AC_Line_dat;
L19 = [L13, nan(size(L13,1), 6)];

% [1] 끄면 같은가
[out.V13, ~] = solve_with(S, ORD, L13, 'off13');
[out.V19, ~] = solve_with(S, ORD, L19, 'off19');

% [2] 목표를 맞추나
LT = L19;  LT(ROW,14)=1; LT(ROW,15)=BUS; LT(ROW,16)=TGT; LT(ROW,17)=0.8; LT(ROW,18)=1.2; LT(ROW,19)=0;
[out.Von, ~] = solve_with(S, ORD, LT, 'on');

% [3] 그 전압을 내는 탭을 찾아, 고정값으로 넣고 다시 푼다 (손 안 댄 길)
lo = 0.8; hi = 1.2;
for it = 1:30
    mid = (lo+hi)/2;  L = L13;  L(ROW,7) = mid;
    [Vm, ~] = solve_with(S, ORD, L, 'bis');
    if Vm(BUS) > TGT, lo = mid; else, hi = mid; end
end
out.t_star = (lo+hi)/2;
L = L13;  L(ROW,7) = out.t_star;
[out.Vfix, ~] = solve_with(S, ORD, L, 'fix');

% [4] 한계 — 못 미치는 목표
LU = L19;  LU(ROW,14)=1; LU(ROW,15)=BUS; LU(ROW,16)=0.95; LU(ROW,17)=0.8; LU(ROW,18)=1.10; LU(ROW,19)=0;
[out.Vlim, ~] = solve_with(S, ORD, LU, 'lim');
L = L13;  L(ROW,7) = 1.10;
[out.Vmax, ~] = solve_with(S, ORD, L, 'tmax');

% [5] 막아야 하는 설정
%   ⚠️ 2026-08-14: 여기 있던 두 검사가 **낡아서** 실패로 잡혔다 —
%      ① 모드 2(위상 조정기)는 08-13 에 구현돼 이제 정상 동작이고
%      ② 계단(19열)은 08-14 에 구현돼 역시 정상이다.
%      ⇒ 여전히 막아야 하는 것으로 바꾼다: 변압기가 아닌 선로에 조정 걸기 ·
%        한 단 크기가 한계 안에 자리를 못 만드는 경우.
L2 = L19;  L2(ROW,14)=1; L2(ROW,15)=BUS; L2(ROW,16)=TGT; L2(ROW,12)=0;  % 변압기가 아님
[~, out.err_mode2] = solve_with(S, ORD, L2, 'notrafo');
% 1.02~1.08 안에는 중립 1.0 에서 0.5 씩 센 자리가 하나도 없다
% (1.0 은 범위 밖이고 1.5 는 너무 크다).
L3 = L19;  L3(ROW,14)=1; L3(ROW,15)=BUS; L3(ROW,16)=TGT;
L3(ROW,17)=1.02; L3(ROW,18)=1.08; L3(ROW,19)=0.5;
[~, out.err_steps] = solve_with(S, ORD, L3, 'nostep');
L4 = L19;  L4(ROW,14)=1; L4(ROW,15)=2;  L4(ROW,16)=TGT;   % 버스 2 = 발전기(PV)
[~, out.err_pv]  = solve_with(S, ORD, L4, 'pvbus');

% [6] 한계를 비우면 0.9~1.1 로 잡히나 (2026-08-13 사용자 확정)
LN = L19;  LN(ROW,14)=1; LN(ROW,15)=BUS; LN(ROW,16)=TGT;
LN(ROW,17)=NaN; LN(ROW,18)=NaN; LN(ROW,19)=0;      % 한계를 비운다
[out.Vauto, ~, out.TRauto] = solve_with(S, ORD, LN, 'auto');
LW = LN;  LW(ROW,17)=0.9; LW(ROW,18)=1.1;          % 같은 값을 직접 적는다
[out.Vwrit, ~, out.TRwrit] = solve_with(S, ORD, LW, 'writ');

save(fullfile(d,'out.mat'), 'out');
disp('DONE');
""", encoding="utf-8")

    log = WORK / "run.log"
    with log.open("w") as fh:
        rc = subprocess.run([MATLAB, "-batch", f"run('{script}')"],
                            stdout=fh, stderr=subprocess.STDOUT,
                            timeout=1800).returncode
    if rc != 0:
        print(f"MATLAB 종료 코드 {rc} — {log}")
        print(log.read_text()[-1200:])
        return 1

    o = loadmat(str(WORK / "out.mat"), squeeze_me=True, struct_as_record=False)["out"]
    V13 = np.atleast_1d(np.asarray(o.V13, dtype=float))
    V19 = np.atleast_1d(np.asarray(o.V19, dtype=float))
    Von = np.atleast_1d(np.asarray(o.Von, dtype=float))
    Vfix = np.atleast_1d(np.asarray(o.Vfix, dtype=float))
    Vlim = np.atleast_1d(np.asarray(o.Vlim, dtype=float))
    Vmax = np.atleast_1d(np.asarray(o.Vmax, dtype=float))

    fails: list[str] = []
    n_cmp = 0

    print(f"\n[1] 끄면 v3 때와 같은가  (열을 19개로 넓혀도)")
    d19 = float(np.max(np.abs(V19 - V13)))
    n_cmp += V13.size
    print(f"    13열 ↔ 19열(제어 없음) 전압 최대차 {d19:.3e}  (버스 {V13.size}개)")
    print(f"    {'✅ 완전히 같다' if d19 == 0 else '🚨 달라졌다 — R1 위반'}")
    if d19 != 0:
        fails.append("끄면 같아야 하는데 다름")

    print(f"\n[2] 목표 전압을 맞추나")
    got = float(Von[CTRL_BUS - 1])
    n_cmp += 1
    print(f"    목표 {TARGET} → 나온 값 {got:.6f} · 오차 {abs(got - TARGET):.2e}")
    ok2 = abs(got - TARGET) < 1e-6
    print(f"    {'✅' if ok2 else '🚨 목표를 못 맞춤'}")
    if not ok2:
        fails.append("목표 미달")

    print(f"\n[3] 그 답이 맞는가 — 찾은 탭을 고정으로 넣고 다시 풀기")
    dfix = float(np.max(np.abs(Vfix - Von)))
    n_cmp += Von.size
    print(f"    그 전압을 내는 탭 {float(o.t_star):.6f} · 전압 최대차 {dfix:.3e} "
          f"(버스 {Von.size}개)")
    ok3 = dfix < 2e-4          # 결과표가 4자리로 반올림된다 — 그보다 아래는 못 본다
    print(f"    {'✅ 같은 운전점이다' if ok3 else '🚨 다른 답'}")
    if not ok3:
        fails.append("자기 대조 실패")

    print(f"\n[4] 한계 — 못 미치는 목표(0.95, 상한 1.10)")
    dlim = float(np.max(np.abs(Vlim - Vmax)))
    n_cmp += Vlim.size
    print(f"    결과 {float(Vlim[CTRL_BUS - 1]):.6f} · 탭 1.10 고정과의 차 {dlim:.3e}")
    ok4 = dlim == 0
    print(f"    {'✅ 한계에서 멈추고 놓아준다' if ok4 else '🚨 한계 처리가 다름'}")
    if not ok4:
        fails.append("한계 처리")

    print(f"\n[5] 못 하는 설정을 막나")
    for name, got_err, want in (("변압기가 아닌 선로", str(o.err_mode2), "변압기"),
                                ("계단 자리가 없음", str(o.err_steps), "자리가"),
                                ("제어 버스가 PV", str(o.err_pv), "고정")):
        blocked = want in got_err
        n_cmp += 1
        head = got_err.split("|")[-1][:46] if got_err else "(안 막힘)"
        print(f"    {name:<20} {'✅ 막힘' if blocked else '🚨 안 막힘'} — {head}")
        if not blocked:
            fails.append(f"{name} 안 막힘")

    print(f"\n[6] 한계를 비우면 0.9~1.1 로 잡나 (그리고 그렇다고 밝히나)")
    Vauto = np.atleast_1d(np.asarray(o.Vauto, dtype=float))
    Vwrit = np.atleast_1d(np.asarray(o.Vwrit, dtype=float))
    TRa = np.atleast_2d(np.asarray(o.TRauto, dtype=float))
    TRw = np.atleast_2d(np.asarray(o.TRwrit, dtype=float))
    dauto = float(np.max(np.abs(Vauto - Vwrit)))
    n_cmp += Vauto.size
    print(f"    비운 판 ↔ 0.9/1.1 을 적은 판 전압 최대차 {dauto:.3e} "
          f"(버스 {Vauto.size}개)")
    if TRa.size and TRa.shape[1] >= 8:
        lo_a, hi_a, au_a = TRa[0, 5], TRa[0, 6], TRa[0, 7]
        au_w = TRw[0, 7] if TRw.size and TRw.shape[1] >= 8 else -1
        print(f"    비운 판이 돌려준 한계 {lo_a:g} ~ {hi_a:g} · 자동 표시 {au_a:g}")
        print(f"    적은 판의 자동 표시 {au_w:g}  (0 이어야 한다)")
        ok6 = (dauto == 0 and lo_a == 0.9 and hi_a == 1.1
               and au_a == 1 and au_w == 0)
        n_cmp += 4
    else:
        print(f"    🚨 Tap_result 가 8열이 아니다: {TRa.shape}")
        ok6 = False
    print(f"    {'✅ 0.9~1.1 로 잡고 자동이라고 밝힌다' if ok6 else '🚨 아니다'}")
    if not ok6:
        fails.append("한계 기본값")

    print(f"\n>>> 대조 {n_cmp}개 · 실패 {len(fails)}건"
          + ("" if not fails else " — " + ", ".join(fails)))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
