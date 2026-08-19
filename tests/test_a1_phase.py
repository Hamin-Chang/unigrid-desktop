# -*- coding: utf-8 -*-
"""A1 ② 위상 조정기 — 엔진이 실제로 그렇게 푸는가 (2026-08-13, §7 5단계 ②).

    python tests/test_a1_phase.py

무엇을 보나
    1) **끄면 옛것과 완전히 같은가** (위험 R1 — 탭 때와 같은 잣대)
    2) 목표 조류를 실제로 맞추나
    3) 그 답이 맞는가 — 찾은 위상을 **고정값**으로 넣고 손 안 댄 길로 다시 풀면 같은가
    4) 야코비안이 맞는가 — 해석식 vs 유한차분
    5) 한계 — 못 미치는 목표면 한계에서 멈추고 놓아주나
    6) 한계를 비우면 ±30도로 잡고 그렇다고 밝히나
    7) 탭과 **함께** 걸어도 되나 (한 계통에 모드 1 과 모드 2 가 같이)

🚨 탭(①)과 구조가 다르다 — 맞추는 것이 상태변수가 아니라 **선로 조류**라
   열만 바꿔치기할 수 없고 **식(행)을 하나 더한다.** 그래서 [4] 가 특히 중요하다.

⚠️ **컴파일된 엔진이 아니라 `.m` 소스를 돌린다** (탭 때와 같다).
"""
from __future__ import annotations

import os
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
            "/1507b381-dd60-42ab-9d1c-fcbc451d8257/scratchpad/a1/phase")

CASE = "AConly_case14_v2.xlsx"
PH_ROW = 8          # 8번 선로 = 변압기 4→7
                    # 🚨 case14 의 변압기는 **8·9·10** 뿐이다. 7번은 그냥 선로라
                    #    탭비 칸이 0 이고, 거기 위상을 걸면 엔진이 막는다(막는 게 맞다).
TAP_ROW = 9         # 9번 선로 = 변압기 4→9 (①에서 쓰던 자리 — [7] 에서 같이 건다)
TAP_BUS = 9

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
PR = {PH_ROW};  TR = {TAP_ROW};  TB = {TAP_BUS};

function [V, err, TAB] = solve_with(S, ORD, L, tag)
    a = cell(1,numel(ORD));
    for k = 1:numel(ORD)
        if strcmp(ORD{{k}},'AC_Line_dat'), a{{k}} = L; else, a{{k}} = S.(ORD{{k}}); end
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

% ⚠️ 그 선로의 From 쪽 조류는 **엔진의 선로 조류표**에서 읽는다.
%    Branch_all 3열 = 'From Bus P[MW]' (calc_AC_line_flow 가 만든다).
%    내가 식을 다시 적으면 단위(엑셀 R·X 는 옴, 엔진은 pu)에서 틀린다 —
%    2026-08-13 에 실제로 그렇게 틀려 -0.08 MW 라는 엉뚱한 값을 봤다.
%    그리고 이 표는 local_line_P 와 **다른 코드**라 대조로도 더 낫다.
function P = flowOf(r, i)
    P = r.Branch_all(i, 3, 1);
end

out = struct();
L13 = S.AC_Line_dat;
L19 = [L13, nan(size(L13,1), 6)];
Sb  = S.Base_dat(1);

% [1] 끄면 같은가
[out.V13, ~] = solve_with(S, ORD, L13, 'off13');
[out.V19, ~] = solve_with(S, ORD, L19, 'off19');

% 지금 그 선로에 흐르는 조류를 먼저 재고, 거기서 조금 옮긴 값을 목표로 삼는다
[~, r0] = evalc('runpf_unigrid_app(''base'', 1, S.Base_dat, S.AC_Bus_dat, L13, S.AC_gen_dat, S.AC_3wtrans_dat, S.DC_Bus_dat, S.DC_Line_dat, S.DC_gen_dat, S.IC_dat, S.DCDC_Conv_dat, S.AC_PLoad_dat, S.AC_QLoad_dat, S.DC_PLoad_dat)');
out.P0 = flowOf(r0, PR);
out.fromto = r0.Branch_all(PR, 1:2, 1);   % 줄 차례가 맞는지 확인용
TGT = out.P0 - 3.0;                 % 3 MW 만큼 옮긴다 (도달 가능한 범위)
out.TGT = TGT;

% [2] 목표 조류를 맞추나
LP = L19;  LP(PR,14)=2; LP(PR,16)=TGT; LP(PR,17)=-30; LP(PR,18)=30; LP(PR,19)=0;
[out.Von, out.err_on, out.TABon] = solve_with(S, ORD, LP, 'on');
if ~isempty(out.Von)
    [~, rr] = evalc('runpf_unigrid_app(''on2'', 1, S.Base_dat, S.AC_Bus_dat, LP, S.AC_gen_dat, S.AC_3wtrans_dat, S.DC_Bus_dat, S.DC_Line_dat, S.DC_gen_dat, S.IC_dat, S.DCDC_Conv_dat, S.AC_PLoad_dat, S.AC_QLoad_dat, S.DC_PLoad_dat)');
    out.Pon = flowOf(rr, PR);
end

% [3] 그 위상을 고정값으로 넣고 손 안 댄 길로 다시 푼다
out.Vfix = [];
if ~isempty(out.TABon)
    L = L13;  L(PR,8) = out.TABon(1,4);        % 도
    [out.Vfix, ~] = solve_with(S, ORD, L, 'fix');
end

% [5] 한계 — **닿을 듯 말 듯한** 목표로 잡는다.
%   ⚠️ 200 MW 처럼 아주 먼 목표를 주면 첫 걸음이 과해 계통이 **다른 해**로 간다
%     (조류계산은 해가 하나가 아니다). 그러면 "한계에서 멈췄나" 가 아니라
%     "어느 해로 갔나" 를 보게 된다 — 2026-08-13 에 그렇게 0.059 pu 가 어긋났다.
%   [2] 에서 목표 30.13 MW 가 10.95도로 닿았으니, 한계를 10.5도로 조여 둔다.
LU = L19;  LU(PR,14)=2; LU(PR,16)=TGT; LU(PR,17)=-10.5; LU(PR,18)=10.5; LU(PR,19)=0;
[out.Vlim, ~, out.TABlim] = solve_with(S, ORD, LU, 'lim');
if ~isempty(out.TABlim), L = L13;  L(PR,8) = out.TABlim(1,4); else, L = L13; end   % 엔진이 멈춘 값(도)
[out.Vend, ~] = solve_with(S, ORD, L, 'end');

% [6] 한계를 비우면
LN = L19;  LN(PR,14)=2; LN(PR,16)=TGT; LN(PR,17)=NaN; LN(PR,18)=NaN; LN(PR,19)=0;
[out.Vauto, ~, out.TABauto] = solve_with(S, ORD, LN, 'auto');

% [7] 탭과 함께
LB = LP;  LB(TR,14)=1; LB(TR,15)=TB; LB(TR,16)=1.035; LB(TR,17)=0.9; LB(TR,18)=1.1; LB(TR,19)=0;
[out.Vboth, out.err_both, out.TABboth] = solve_with(S, ORD, LB, 'both');
if ~isempty(out.Vboth)
    [~, rb] = evalc('runpf_unigrid_app(''both2'', 1, S.Base_dat, S.AC_Bus_dat, LB, S.AC_gen_dat, S.AC_3wtrans_dat, S.DC_Bus_dat, S.DC_Line_dat, S.DC_gen_dat, S.IC_dat, S.DCDC_Conv_dat, S.AC_PLoad_dat, S.AC_QLoad_dat, S.DC_PLoad_dat)');
    out.Pboth = flowOf(rb, PR);
    out.Vboth_ctrl = rb.AC_all(TB,2,1);
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
        """MATLAB 의 빈 char 는 여기서 `[]` 라는 **글자**로 온다 — 그걸 오류로 읽으면
        멀쩡히 풀린 것을 '죽었다' 고 한다(2026-08-13 에 실제로 그랬다)."""
        v = getattr(o, name, "")
        t = "" if isinstance(v, np.ndarray) and v.size == 0 else str(v)
        return "" if t.strip() in ("", "[]") else t

    fails: list[str] = []
    n_cmp = 0

    print("\n[1] 끄면 옛것과 같은가  (열을 19개로 넓혀도)")
    V13, V19 = arr("V13"), arr("V19")
    d19 = float(np.max(np.abs(V19 - V13)))
    n_cmp += V13.size
    print(f"    13열 ↔ 19열(제어 없음) 전압 최대차 {d19:.3e}  (버스 {V13.size}개)")
    print(f"    {'✅ 완전히 같다' if d19 == 0 else '🚨 달라졌다 — R1 위반'}")
    if d19 != 0:
        fails.append("끄면 같아야 하는데 다름")

    ft = np.atleast_1d(np.asarray(o.fromto, dtype=float))
    print(f"\n[2] 목표 조류를 맞추나  (조류표 {PH_ROW}번 줄 = 버스 "
          f"{int(ft[0])}→{int(ft[1])} — 선로 표와 같은 차례인지 확인)")
    err_on = err_of("err_on")
    if err_on:
        print(f"    🚨 풀다가 죽었다 — {err_on[:200]}")
        fails.append("위상 조정이 안 풀림")
    else:
        P0, TGT, Pon = float(o.P0), float(o.TGT), float(o.Pon)
        n_cmp += 1
        print(f"    원래 조류 {P0:.4f} MW → 목표 {TGT:.4f} MW → 나온 값 {Pon:.4f} MW")
        print(f"    오차 {abs(Pon - TGT):.2e} MW")
        ok2 = abs(Pon - TGT) < 1e-4
        print(f"    {'✅' if ok2 else '🚨 목표를 못 맞춤'}")
        if not ok2:
            fails.append("목표 미달")

        print("\n[3] 그 답이 맞는가 — 찾은 위상을 고정으로 넣고 다시 풀기")
        Von, Vfix = arr("Von"), arr("Vfix")
        dfix = float(np.max(np.abs(Vfix - Von)))
        n_cmp += Von.size
        tab = np.atleast_2d(np.asarray(o.TABon, dtype=float))
        print(f"    엔진이 정한 위상 {tab[0, 3]:.6f}° · 전압 최대차 {dfix:.3e} "
              f"(버스 {Von.size}개)")
        ok3 = dfix < 2e-4        # 결과표가 4자리로 반올림된다
        print(f"    {'✅ 같은 운전점이다' if ok3 else '🚨 다른 답'}")
        if not ok3:
            fails.append("자기 대조 실패")

    print("\n[4] 야코비안이 맞나 — 해석식 vs 유한차분")
    # 새로 생긴 모양(조류 식의 행)은 손으로 틀리기 쉽다. 엔진의 `local_phase_jac` 를
    # **그대로 꺼내** 유한차분과 견준다(복붙하면 그 코드가 틀려도 못 잡는다).
    jac = subprocess.run(
        [MATLAB, "-batch", f"run('{HERE / 'a1_phase_jac_check.m'}')"],
        env={**os.environ, "V14DIR": str(V14), "CASEMAT": str(WORK / "case.mat")},
        capture_output=True, text=True, timeout=1200)
    tail = [ln for ln in jac.stdout.splitlines()
            if ln.strip() and not ln.startswith("[경고") and "Desktop/GML" not in ln]
    for ln in tail[-8:]:
        print("    " + ln)
    ok4 = any("실패 0건" in ln for ln in tail)
    n_cmp += 57
    print(f"    {'✅ 미분이 맞다' if ok4 else '🚨 미분이 틀렸다'}")
    if not ok4:
        fails.append("야코비안")

    print("\n[5] 한계 — 목표는 10.95° 가 필요한데 한계를 ±10.5° 로 조인다")
    # ⚠️ **어느 쪽 끝에서 멈추는지 내가 짐작하지 않는다.** φ 를 키우면 From 쪽
    #    조류가 줄어들므로(∂P/∂φ < 0, 유한차분으로 확인) 조류를 낮추라는 목표는
    #    +5° 로 간다. 처음엔 -5° 를 기대하고 틀렸다 — 엔진이 알려 준 값으로 본다.
    Vlim = arr("Vlim")
    tabl = np.atleast_2d(np.asarray(o.TABlim, dtype=float))
    Vend = arr("Vend")
    dlim = float(np.max(np.abs(Vlim - Vend)))
    n_cmp += Vlim.size
    print(f"    멈춘 위상 {tabl[0, 3]:.4f}° · 살아있나 {tabl[0, 4]:g} "
          f"· 그 값으로 고정한 판과의 차 {dlim:.3e}")
    ok5 = dlim == 0 and tabl[0, 4] == 0 and abs(abs(tabl[0, 3]) - 10.5) < 1e-9
    print(f"    {'✅ 한계에서 멈추고 놓아준다' if ok5 else '🚨 한계 처리가 다름'}")
    if not ok5:
        fails.append("한계 처리")

    print("\n[6] 한계를 비우면 ±30° 로 잡고 밝히나")
    taba = np.atleast_2d(np.asarray(o.TABauto, dtype=float))
    Vauto, Von2 = arr("Vauto"), arr("Von")
    dauto = float(np.max(np.abs(Vauto - Von2)))
    n_cmp += Vauto.size + 3
    print(f"    비운 판 ↔ ±30 을 적은 판 전압 최대차 {dauto:.3e}")
    print(f"    하한 {taba[0, 5]:g}° · 상한 {taba[0, 6]:g}° · 자동 표시 {taba[0, 7]:g}"
          f" · 방식 {taba[0, 8]:g} (2 여야 한다)")
    # ⚠️ 도 → 라디안 → 도 로 왕복하므로 **정확히 -30 이 아니다**(2026-08-13에 걸림).
    ok6 = (dauto == 0 and abs(taba[0, 5] + 30) < 1e-9 and abs(taba[0, 6] - 30) < 1e-9
           and taba[0, 7] == 1 and taba[0, 8] == 2)
    print(f"    {'✅ ±30° 로 잡고 자동이라고 밝힌다' if ok6 else '🚨 아니다'}")
    if not ok6:
        fails.append("한계 기본값")

    print("\n[7] 탭과 함께 걸어도 되나 (모드 1 + 모드 2 를 한 계통에)")
    err_b = err_of("err_both")
    if err_b:
        print(f"    🚨 죽었다 — {err_b[:200]}")
        fails.append("탭+위상 같이 안 됨")
    else:
        tabb = np.atleast_2d(np.asarray(o.TABboth, dtype=float))
        Pb = float(o.Pboth)
        Vb = float(o.Vboth_ctrl)
        n_cmp += 2
        print(f"    표 {tabb.shape} · 방식 {tabb[:, 8].astype(int).tolist()}")
        print(f"    위상 쪽 조류 {Pb:.4f} MW (목표 {float(o.TGT):.4f})")
        print(f"    탭 쪽 버스 {TAP_BUS} 전압 {Vb:.6f} (목표 1.035)")
        ok7 = abs(Pb - float(o.TGT)) < 1e-4 and abs(Vb - 1.035) < 1e-6
        print(f"    {'✅ 둘 다 맞춘다' if ok7 else '🚨 하나라도 못 맞춤'}")
        if not ok7:
            fails.append("탭+위상 동시")

    print(f"\n>>> 대조 {n_cmp}개 · 실패 {len(fails)}건"
          + ("" if not fails else " — " + ", ".join(fails)))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
