# -*- coding: utf-8 -*-
"""A1 ④ SVC — 엔진이 실제로 그렇게 푸는가 (2026-08-13, §7 5단계 ④).

    python tests/test_a1_svc.py

무엇을 보나
    1) **끄면 옛것과 완전히 같은가** (위험 R1 — 탭·위상 때와 같은 잣대)
    2) 목표 전압을 실제로 맞추나
    3) 그 답이 맞는가 — 찾은 Bs 를 **고정값**으로 넣고 손 안 댄 길로 다시 풀면 같은가
    4) 한계 — 못 미치는 목표면 한계에서 멈추고 놓아주나
    5) 한계를 비우면 -50 ~ 50 Mvar 로 잡고 그렇다고 밝히나
    6) 못 하는 설정을 막나 (계단 션트 · 발전기 버스 · 탭과 같은 버스)
    7) 탭·위상과 **함께** 걸어도 되나

⭐ 구조는 **탭과 같다**(위상과 다르다) — 맞추는 것이 그 버스의 전압, 곧 상태변수라
   **열만 바꿔치기**하면 정방이 유지된다. 그래서 [3] 자기 대조가 잘 듣는다.

⚠️ **컴파일된 엔진이 아니라 `.m` 소스를 돌린다** (탭·위상 때와 같다).
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
            "/1507b381-dd60-42ab-9d1c-fcbc451d8257/scratchpad/a1/svc")

CASE = "AConly_case14_v2.xlsx"
SVC_BUS = 14        # PQ 버스 (발전기가 없는 곳)
TARGET = 1.03       # 원래보다 살짝 높게 — 닿을 수 있는 값
TAP_ROW, TAP_BUS = 9, 9     # [7] 에서 탭과 같이 걸어 본다
PH_ROW = 8                  # [7] 에서 위상도 같이

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
BUS = {SVC_BUS};  TGT = {TARGET};  TR = {TAP_ROW};  TB = {TAP_BUS};  PR = {PH_ROW};

function [V, err, TAB] = solve_with(S, ORD, B, L, tag)
    a = cell(1,numel(ORD));
    for k = 1:numel(ORD)
        switch ORD{{k}}
            case 'AC_Bus_dat',  a{{k}} = B;
            case 'AC_Line_dat', a{{k}} = L;
            otherwise,          a{{k}} = S.(ORD{{k}});
        end
    end
    TAB = [];
    try
        [~, r] = evalc('runpf_unigrid_app(tag, 1, a{{:}})');
        V = r.AC_all(:,2,1);  err = '';
        if isfield(r,'Tap_result'), TAB = r.Tap_result; end
    catch ME
        V = [];  err = [ME.identifier '|' ME.message];
    end
end

out = struct();
B17 = S.AC_Bus_dat;
B22 = [B17, nan(size(B17,1), 22 - size(B17,2))];
L13 = S.AC_Line_dat;
L19 = [L13, nan(size(L13,1), 6)];
Sb  = S.Base_dat(1);   % MVA
out.Bs0 = B17(BUS, 3);

% [1] 끄면 같은가
[out.V17, ~] = solve_with(S, ORD, B17, L13, 'off17');
[out.V22, ~] = solve_with(S, ORD, B22, L13, 'off22');

% [2] 목표 전압을 맞추나
BS = B22;  BS(BUS,18)=2; BS(BUS,19)=TGT; BS(BUS,20)=-50; BS(BUS,21)=50; BS(BUS,22)=0;
[out.Von, out.err_on, out.TABon] = solve_with(S, ORD, BS, L13, 'on');

% [3] 찾은 Bs 를 고정으로 넣고 손 안 댄 길로 다시 푼다
out.Vfix = [];
if ~isempty(out.TABon)
    Bf = B17;  Bf(BUS,3) = out.TABon(1,4);      % Mvar 그대로
    [out.Vfix, ~] = solve_with(S, ORD, Bf, L13, 'fix');
end

% [4] 한계 — 닿을 듯 말 듯하게 조인다
if ~isempty(out.TABon)
    tight = abs(out.TABon(1,4)) * 0.5;
    BL = BS;  BL(BUS,20) = -tight;  BL(BUS,21) = tight;
    [out.Vlim, ~, out.TABlim] = solve_with(S, ORD, BL, L13, 'lim');
    Be = B17;  Be(BUS,3) = out.TABlim(1,4);
    [out.Vend, ~] = solve_with(S, ORD, Be, L13, 'end');
end

% [5] 한계를 비우면
BN = BS;  BN(BUS,20)=NaN; BN(BUS,21)=NaN;
[out.Vauto, ~, out.TABauto] = solve_with(S, ORD, BN, L13, 'auto');

% [6] 막아야 하는 설정
B1 = B22;  B1(BUS,18)=1; B1(BUS,19)=TGT;
[~, out.err_step] = solve_with(S, ORD, B1, L13, 'stepped');
B2 = B22;  B2(2,18)=2;   B2(2,19)=1.0;          % 버스 2 = 발전기(PV)
[~, out.err_pv]   = solve_with(S, ORD, B2, L13, 'pvbus');
B3 = B22;  B3(TB,18)=2;  B3(TB,19)=1.03;        % 탭이 보는 버스와 같은 곳
LT = L19;  LT(TR,14)=1; LT(TR,15)=TB; LT(TR,16)=1.035; LT(TR,17)=0.9; LT(TR,18)=1.1; LT(TR,19)=0;
[~, out.err_dup]  = solve_with(S, ORD, B3, LT, 'dup');

% [7] 셋을 함께
LB = L19;
LB(TR,14)=1; LB(TR,15)=TB; LB(TR,16)=1.035; LB(TR,17)=0.9; LB(TR,18)=1.1; LB(TR,19)=0;
LB(PR,14)=2; LB(PR,16)=30; LB(PR,17)=-20; LB(PR,18)=20; LB(PR,19)=0;
[out.Vall, out.err_all, out.TABall] = solve_with(S, ORD, BS, LB, 'all');
if ~isempty(out.Vall)
    [~, ra] = evalc(['runpf_unigrid_app(''all2'', 1, S.Base_dat, BS, LB, S.AC_gen_dat, ' ...
      'S.AC_3wtrans_dat, S.DC_Bus_dat, S.DC_Line_dat, S.DC_gen_dat, S.IC_dat, ' ...
      'S.DCDC_Conv_dat, S.AC_PLoad_dat, S.AC_QLoad_dat, S.DC_PLoad_dat)']);
    out.Pall = ra.Branch_all(PR, 3, 1);
    out.Vall_tap = ra.AC_all(TB,2,1);
    out.Vall_svc = ra.AC_all(BUS,2,1);
end

save(fullfile(d,'out.mat'), 'out');
disp('DONE');
""", encoding="utf-8")

    log = WORK / "run.log"
    with log.open("w") as fh:
        rc = subprocess.run([MATLAB, "-batch", f"run('{script}')"],
                            stdout=fh, stderr=subprocess.STDOUT,
                            timeout=2400).returncode
    if rc != 0:
        print(f"MATLAB 종료 코드 {rc} — {log}")
        print(log.read_text()[-2000:])
        return 1

    o = loadmat(str(WORK / "out.mat"), squeeze_me=True, struct_as_record=False)["out"]

    def arr(name):
        return np.atleast_1d(np.asarray(getattr(o, name), dtype=float))

    def err_of(name):
        v = getattr(o, name, "")
        t = "" if isinstance(v, np.ndarray) and v.size == 0 else str(v)
        return "" if t.strip() in ("", "[]") else t

    fails: list[str] = []
    n_cmp = 0

    print("\n[1] 끄면 옛것과 같은가  (버스 표를 22열로 넓혀도)")
    V17, V22 = arr("V17"), arr("V22")
    d22 = float(np.max(np.abs(V22 - V17)))
    n_cmp += V17.size
    print(f"    17열 ↔ 22열(조정 없음) 전압 최대차 {d22:.3e}  (버스 {V17.size}개)")
    print(f"    {'✅ 완전히 같다' if d22 == 0 else '🚨 달라졌다 — R1 위반'}")
    if d22 != 0:
        fails.append("끄면 같아야 하는데 다름")

    print("\n[2] 목표 전압을 맞추나")
    e = err_of("err_on")
    if e:
        print(f"    🚨 풀다가 죽었다 — {e[:200]}")
        fails.append("SVC 가 안 풀림")
    else:
        Von = arr("Von")
        got = float(Von[SVC_BUS - 1])
        tab = np.atleast_2d(np.asarray(o.TABon, dtype=float))
        n_cmp += 1
        print(f"    원래 Bs {float(o.Bs0):.3f} Mvar → 정해진 Bs {tab[0, 3]:.4f} Mvar")
        print(f"    버스 {SVC_BUS} 전압 {got:.6f} (목표 {TARGET}) · 오차 "
              f"{abs(got - TARGET):.2e}")
        ok2 = abs(got - TARGET) < 1e-6 and tab[0, 8] == 3
        print(f"    {'✅' if ok2 else '🚨 목표를 못 맞춤'}")
        if not ok2:
            fails.append("목표 미달")

        print("\n[3] 그 답이 맞는가 — 찾은 Bs 를 고정으로 넣고 다시 풀기")
        Vfix = arr("Vfix")
        dfix = float(np.max(np.abs(Vfix - Von)))
        n_cmp += Von.size
        print(f"    전압 최대차 {dfix:.3e}  (버스 {Von.size}개)")
        ok3 = dfix < 2e-4        # 결과표가 4자리로 반올림된다
        print(f"    {'✅ 같은 운전점이다' if ok3 else '🚨 다른 답'}")
        if not ok3:
            fails.append("자기 대조 실패")

        print("\n[4] 한계 — 필요한 Bs 의 절반으로 조인다")
        Vlim, Vend = arr("Vlim"), arr("Vend")
        tabl = np.atleast_2d(np.asarray(o.TABlim, dtype=float))
        dlim = float(np.max(np.abs(Vlim - Vend)))
        n_cmp += Vlim.size
        print(f"    멈춘 Bs {tabl[0, 3]:.4f} Mvar · 살아있나 {tabl[0, 4]:g} "
              f"· 그 값으로 고정한 판과의 차 {dlim:.3e}")
        ok4 = dlim == 0 and tabl[0, 4] == 0
        print(f"    {'✅ 한계에서 멈추고 놓아준다' if ok4 else '🚨 한계 처리가 다름'}")
        if not ok4:
            fails.append("한계 처리")

    print("\n[5] 한계를 비우면 -50 ~ 50 Mvar 로 잡고 밝히나")
    taba = np.atleast_2d(np.asarray(o.TABauto, dtype=float))
    Vauto, Von2 = arr("Vauto"), arr("Von")
    dauto = float(np.max(np.abs(Vauto - Von2)))
    n_cmp += Vauto.size + 3
    print(f"    비운 판 ↔ ±50 을 적은 판 전압 최대차 {dauto:.3e}")
    print(f"    하한 {taba[0, 5]:g} · 상한 {taba[0, 6]:g} Mvar · 자동 {taba[0, 7]:g}"
          f" · 방식 {taba[0, 8]:g} (3 이어야 한다)")
    ok5 = (dauto == 0 and abs(taba[0, 5] + 50) < 1e-9
           and abs(taba[0, 6] - 50) < 1e-9 and taba[0, 7] == 1 and taba[0, 8] == 3)
    print(f"    {'✅ ±50 Mvar 로 잡고 자동이라고 밝힌다' if ok5 else '🚨 아니다'}")
    if not ok5:
        fails.append("한계 기본값")

    print("\n[6] 못 하는 설정을 막나")
    for name, got_err, want in (("계단 션트(Mode 1)", err_of("err_step"), "스위치드 션트"),
                                ("발전기(PV) 버스", err_of("err_pv"), "고정"),
                                ("탭과 같은 버스", err_of("err_dup"), "둘 다")):
        blocked = want in got_err
        n_cmp += 1
        head = got_err.split("|")[-1][:44] if got_err else "(안 막힘)"
        print(f"    {name:<18} {'✅ 막힘' if blocked else '🚨 안 막힘'} — {head}")
        if not blocked:
            fails.append(f"{name} 안 막힘")

    print("\n[7] 탭·위상·SVC 셋을 함께")
    e = err_of("err_all")
    if e:
        print(f"    🚨 죽었다 — {e[:200]}")
        fails.append("셋 같이 안 됨")
    else:
        tabb = np.atleast_2d(np.asarray(o.TABall, dtype=float))
        n_cmp += 3
        print(f"    표 {tabb.shape} · 방식 {tabb[:, 8].astype(int).tolist()} "
              f"(1 탭 · 2 위상 · 3 SVC)")
        # ⚠️ **셋이 다 목표를 맞추라는 시험이 아니다.** 서로 영향을 주므로 어떤 것은
        #    한계에 걸릴 수 있고, 그때 놓아주는 것이 **맞는 동작**이다. 그래서
        #    「목표를 맞췄거나, 아니면 한계에 걸려 놓아졌거나」 로 본다.
        got = {1: float(o.Vall_tap), 2: float(o.Pall), 3: float(o.Vall_svc)}
        want = {1: 1.035, 2: 30.0, 3: TARGET}
        tol = {1: 1e-6, 2: 1e-3, 3: 1e-6}
        name = {1: f"탭  버스 {TAP_BUS} 전압", 2: "위상 8번 선로 조류",
                3: f"SVC 버스 {SVC_BUS} 전압"}
        ok7 = sorted(tabb[:, 8].astype(int)) == [1, 2, 3]
        for row in tabb:
            m = int(row[8])
            live = row[4] != 0
            hit = abs(got[m] - want[m]) < tol[m]
            at_lim = (abs(row[3] - row[5]) < 1e-9) or (abs(row[3] - row[6]) < 1e-9)
            good = hit if live else at_lim
            print(f"    {name[m]:<20} {got[m]:.6f} (목표 {want[m]}) · "
                  f"{'목표 맞춤' if live else f'한계 {row[3]:.4f} 에서 놓아줌'} "
                  f"{'✅' if good else '🚨'}")
            ok7 = ok7 and good
        print(f"    {'✅ 셋 다 맞춘다' if ok7 else '🚨 하나라도 못 맞춤'}")
        if not ok7:
            fails.append("셋 동시")

    print(f"\n>>> 대조 {n_cmp}개 · 실패 {len(fails)}건"
          + ("" if not fails else " — " + ", ".join(fails)))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
