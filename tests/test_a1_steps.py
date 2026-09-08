# -*- coding: utf-8 -*-
"""A1 ③ 계단 — **예시 계통 전부**에 걸어 보고 잘 되나 (2026-08-14, §7 5단계 ③).

    ~/venvs/unigrid-acdc/bin/python tests/test_a1_steps.py

무엇을 보나 (케이스 하나하나에 대해)
    R1) 계단을 안 걸면 옛 결과와 **완전히 같은가** — 조정 열을 붙이기만 해도 안 된다
    1)  걸 수 있는 계통(AC 전용 + 2권선 변압기)에 탭 계단을 걸면
        · 나온 탭이 **자리 위**인가        — 중립 1.0 에서 한 단 크기만큼 떨어진 곳
        · 한계 **안**인가
        · 「계단으로 내렸다」 표시가 서나   — 결과표 11열 = 1
        · 연속으로 푼 값과 **반 단 안**인가 — 반올림이 제대로 됐나
        · 🚨 **자기 대조** — 그 탭을 고정으로 넣고 손 안 댄 길로 풀면 같은가.
             전압만 보지 않는다. **선로 조류표까지** 견준다(2026-08-13 에 조류표가
             옛 탭으로 계산되던 결함을 전압만 봐서 못 잡았다).
    2)  🚨 **AC/DC 계통에서도 똑같이 되는가** (2026-08-19 에 바꿈)
        2026-08-14 에 이 시험을 쓸 때 A1 계단은 **AC 전용**이라 여기서 "분명히 막는가"
        를 봤다. 2026-08-17 에 A1 을 **AC/DC 로 넓히면서 막이를 걷었는데** 시험은
        그대로여서 AC/DC 케이스 5개가 계속 실패하고 있었다(아무도 안 돌려 몰랐다).
        ⇒ 이제 AC/DC 도 **AC 와 같은 잣대**로 본다 — 자리 위인가 · 한계 안인가 ·
          표시가 서나 · 연속과 반 단 안인가 · 자기 대조가 0 인가.

⚠️ 컴파일된 엔진이 아니라 `.m` 소스를 돌린다(`test_a1_tap.py` 와 같은 이유).
"""
from __future__ import annotations

import glob
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
REPO = HERE.parent
MATLAB = "/Applications/MATLAB_R2024b.app/bin/matlab"
WORK = Path("/tmp/a1_steps_test")

TABLES = ["Base_dat", "AC_Bus_dat", "AC_Line_dat", "AC_gen_dat", "AC_3wtrans_dat",
          "DC_Bus_dat", "DC_Line_dat", "DC_gen_dat", "IC_dat", "DCDC_Conv_dat",
          "AC_PLoad_dat", "AC_QLoad_dat", "DC_PLoad_dat"]

STEP = 0.00625      # 한 단 크기 — 실물 OLTC 의 0.625% (±16단 × 0.625% = ±10%)
TMIN, TMAX = 0.9, 1.1


def scan(path: str) -> dict:
    """케이스 하나를 열어 '어디에 걸 수 있나' 를 고른다."""
    case = load_case(path)
    T = {k: np.asarray(v, dtype=float) for k, v in case.tables.items()}
    name = os.path.basename(path)

    L = T.get("AC_Line_dat")
    G = T.get("AC_gen_dat")
    # 🚨 AC 전용인지는 **Mode 로** 가른다(0 혼합 · 1 AC · 2 DC).
    #    IC 표에 값이 있나로 갈랐다가 틀렸다 — `AConly_3wtrans_modify` 는
    #    Mode=1 인데 IC 표에 안 쓰는 값이 남아 있다(2026-08-14).
    mode = float(getattr(case, "mode", 0.0) or 0.0)
    is_acdc = (mode != 1.0)

    # 🚨 2026-08-19: `not is_acdc` 를 뺐다. A1 계단이 AC/DC 로 넓어졌으므로
    #    혼합 계통에서도 **AC 변압기 줄**을 골라 똑같이 건다.
    row = bus = 0
    if L is not None and L.size and L.shape[1] > 11:
        gen_bus = set()
        if G is not None and G.size and not np.all(np.isnan(G[:, 0])):
            gen_bus = {int(b) for b in G[:, 0] if np.isfinite(b)}
        for i in range(L.shape[0]):
            if L[i, 11] != 1:                       # 변압기가 아니면 건너뛴다
                continue
            to = int(L[i, 2]) if np.isfinite(L[i, 2]) else 0
            if to and to not in gen_bus:            # 제어 버스는 PQ 여야 한다
                row, bus = i + 1, to                # MATLAB 은 1부터
                break
    # 시각 수 — 자기 대조가 몇 시각을 갈라 보는지 화면에 밝히는 데 쓴다.
    # ⚠️ 하루(2026-09-08 오전)만 이 값으로 **자기 대조를 건너뛰게** 해 뒀었다.
    #    그때 진단은 "첫 시각 탭 하나를 24시각 전부에 고정하니 어긋나는 게 당연"
    #    이었는데, 어긋난 진짜 이유는 **엔진이 시각별 탭을 앱에 안 넘긴 것**이었다
    #    (`runpf_unigrid_app.m` 이 `Tap_result` 하나만 실어 보냈다).
    #    ⇒ 엔진을 고치고 대조를 시각별로 돌렸다. 건너뛰기는 없앴다.
    nt = 1
    P = T.get("AC_PLoad_dat")
    if P is not None and P.ndim == 2 and P.shape[1] > 1:
        nt = max(1, P.shape[1] - 1)
    return dict(name=name, tables=T, row=row, bus=bus, is_acdc=is_acdc,
                mode=mode, n_times=nt)


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    paths = sorted(glob.glob(str(REPO / "cases" / "*.xlsx")))
    print(f"예시 계통 {len(paths)} 개를 훑습니다.\n")

    plan, skipped = [], []
    for p in paths:
        try:
            info = scan(p)
        except Exception as e:                       # 케이스를 못 여는 것은 여기 관심 밖
            skipped.append((os.path.basename(p), f"못 열었다: {type(e).__name__}"))
            continue
        savemat(str(WORK / f"c{len(plan)}.mat"),
                {k: v for k, v in info["tables"].items() if k in TABLES})
        plan.append(info)

    for i, info in enumerate(plan):
        where = ("AC/DC" if info["is_acdc"] else "AC")
        kind = (f"{where} · 탭 계단: {info['row']}번 선로 → 버스 {info['bus']}"
                if info["row"] else f"{where} · 2권선 변압기가 없어 탭 시험 없음")
        print(f"  [{i}] {info['name']:38s} {kind}")
    print()

    ORD = ", ".join(f"'{t}'" for t in TABLES)
    rows = "\n".join(
        f"P({i+1}).row = {p['row']};  P({i+1}).bus = {p['bus']};  "
        f"P({i+1}).acdc = {1 if p['is_acdc'] else 0};  "
        f"P({i+1}).mode = {p['mode']:g};"
        for i, p in enumerate(plan))

    script = WORK / "run.m"
    script.write_text(f"""
v14 = '{V14}';
addpath(v14); addpath(fullfile(v14,'functions'));
d = '{WORK}';
ORD = {{{ORD}}};
STEP = {STEP};  TMIN = {TMIN};  TMAX = {TMAX};
{rows}

function M = slab(r, name, ti)
%SLAB  [nr*T x nc] 로 쌓여 온 표에서 ti 시각의 [nr x nc] 를 뽑는다 (2026-09-08).
%   `runpf_unigrid_app` 은 전 시각을 **세로로 쌓아** 2차원으로 넘긴다(`*_dims`
%   가 [nr nc T]). 그래서 `r.AC_all(:,2)` 는 「첫 시각 전압」이 아니라
%   **24시각 전압을 전부 이어붙인 것**이다 — 이걸 첫 시각으로 착각한 것이
%   이 시험이 24시각 계통에서 깨진 원인이었다.
    M = [];
    if ~isfield(r, name) || isempty(r.(name)), return; end
    A = r.(name);
    dn = strrep(name, '_all', '_dims');
    if isfield(r, dn) && numel(r.(dn)) >= 3
        d = r.(dn);  nr = d(1);  T = d(3);
    else
        nr = size(A,1);  T = 1;
    end
    if nr <= 0 || T <= 0 || size(A,1) < nr*T, return; end
    ti = max(1, min(ti, T));
    M = A((ti-1)*nr + (1:nr), :);
end

function T = n_times(r)
    T = 1;
    if isfield(r,'Tap_dims') && numel(r.Tap_dims) >= 3 && r.Tap_dims(3) > 0
        T = double(r.Tap_dims(3));
    elseif isfield(r,'AC_dims') && numel(r.AC_dims) >= 3 && r.AC_dims(3) > 0
        T = double(r.AC_dims(3));
    end
end

function [V, F, TR, err, BN, r] = solve_with(S, ORD, L, tag, MODE, B)
    if nargin < 6, B = []; end
    a = cell(1,numel(ORD));
    for k = 1:numel(ORD)
        if strcmp(ORD{{k}},'AC_Line_dat')
            a{{k}} = L;
        elseif strcmp(ORD{{k}},'AC_Bus_dat') && ~isempty(B)
            a{{k}} = B;
        else
            a{{k}} = S.(ORD{{k}});
        end
    end
    V = []; F = []; TR = []; err = ''; BN = []; r = struct();
    try
        % 🚨 두 번째 인자는 **Mode** 다(0 혼합 · 1 AC · 2 DC). 늘 1 을 넘기면
        %    AC/DC 케이스를 AC 로 풀어 버린다(2026-08-14 에 그랬다).
        [~, r] = evalc('runpf_unigrid_app(tag, MODE, a{{:}})');
        V = r.AC_all(:,2,1);  BN = r.AC_all(:,1,1);   % 1열 = 실제 버스 번호
        if isfield(r,'Branch_all'), F = r.Branch_all(:,3,1); end
        if isfield(r,'Tap_result'), TR = r.Tap_result; end
    catch ME
        err = ME.message;
    end
end

function [sV, sF, sFn, err, nt, nT] = self_check(rs, S, ORD, mode, tag, kind, L13, BB, row, br)
%SELF_CHECK  조정이 답한 값을 **고정으로** 넣고 손 안 댄 길로 다시 풀어 견준다.
%   kind 1 = 탭(선로 7열) · 2 = 위상(선로 8열, 도) · 3 = 션트(버스 3열, Mvar)
%
% 🚨 2026-09-08 — **시각마다** 한다. 엔진은 시각 루프 안에서 조정하므로 24시각
%    계통이면 답이 24벌이다. 예전에는 첫 벌 하나를 24시각 전압 전부와 견줘
%    당연히 어긋났고(17시에 0.031 pu), 그것을 「시험의 한계」로 보고 건너뛰게
%    해 두었다 — 잘못된 판단이었다. 앱이 화면에 적는 값이 그 시각 계산에 실제로
%    쓰인 값인지가 이 시험의 본론이다.
%    ⇒ 첫·가운데·끝 세 시각을 뽑아 각각 대조한다(24벌 전부 하면 풀이가 24배).
    nT = n_times(rs);
    tl = unique([1, max(1,ceil(nT/2)), nT]);
    nt = numel(tl);
    sV = 0;  sF = 0;  sFn = 0;  err = '';
    for q = 1:numel(tl)
        ti = tl(q);
        Tq = slab(rs, 'Tap_all', ti);
        if isempty(Tq)
            err = 'Tap_all 이 없다 — 엔진이 낡았다(시각별 조정 결과를 안 넘긴다)';
            return
        end
        Lx = L13;  Bx = BB;
        switch kind
            case 1, Lx(row,7) = Tq(1,4);
            case 2, Lx(row,8) = Tq(1,4);
            case 3, Bx(br,3)  = Tq(1,4);
        end
        [~, ~, ~, ef, ~, rf] = solve_with(S, ORD, Lx, sprintf('%s_%d', tag, ti), mode, Bx);
        if ~isempty(ef), err = ef;  return; end
        As = slab(rs, 'AC_all', ti);  Af = slab(rf, 'AC_all', ti);
        if isempty(As) || isempty(Af) || size(As,1) ~= size(Af,1)
            err = 'AC_all 모양이 다르다';  return
        end
        % 🚨 NaN 자리를 뺀다 — 혼합 계통 결과표에는 값이 없는 줄이 섞인다
        %    (2026-08-19 에 탭 갈래에만 이게 빠져 있었다).
        v1 = As(:,2);  v2 = Af(:,2);
        mv = isfinite(v1) & isfinite(v2);
        sV = max(sV, max([abs(v1(mv) - v2(mv)); 0]));
        Bs = slab(rs, 'Branch_all', ti);  Bf2 = slab(rf, 'Branch_all', ti);
        if ~isempty(Bs) && ~isempty(Bf2) && size(Bs,1) == size(Bf2,1)
            f1 = Bs(:,3);  f2 = Bf2(:,3);
            mf = isfinite(f1) & isfinite(f2);
            sF = max(sF, max([abs(f1(mf) - f2(mf)); 0]));  sFn = sum(mf);
        end
    end
end

R = struct();
for n = 1:numel(P)
    S = load(fullfile(d, sprintf('c%d.mat', n-1)));
    % 🚨 기준은 **조정이 하나도 없는 판**이어야 한다. 케이스 파일 자체에 조정이
    %    적혀 있는 것이 있어(`case14_tapctrl`·`phasectrl`) 그대로 쓰면 «조정 켜짐»
    %    과 «조정 꺼짐» 을 견주게 되어 R1 이 거짓으로 깨진다(2026-08-14 에 그랬다).
    if size(S.AC_Line_dat,2) >= 19
        L13 = S.AC_Line_dat(:,1:13);
    else
        L13 = S.AC_Line_dat;
    end
    L19 = [L13, nan(size(L13,1), 6)];        % 조정 열은 붙이되 전부 비워 둔다

    % 🚨 **버스 표의 조정 열도 걷어낸다** (2026-08-19).
    %    선로 표는 위에서 1:13 으로 자르는데 버스 표는 그대로 넘기고 있었다.
    %    `ACDC_case24_shuntctrl` 는 버스 표 18~22 열에 SVC 가 **켜진 채로 적혀 있어**,
    %    「그 탭을 고정으로 넣고 손 안 댄 길로 풀면 같은가」를 물을 때 *손 안 댄 길*
    %    이 아니었다 — SVC 가 계속 돌아 답이 갈렸다(전압 1.4e-03 · 조류 2.0e-01).
    %    아래 션트 시험은 이미 `B0(:,1:17)` 로 걷어내고 있었다 — 여기만 빠졌다.
    if size(S.AC_Bus_dat,2) >= 22
        BB = S.AC_Bus_dat(:,1:17);
    else
        BB = S.AC_Bus_dat;
    end

    % ── R1: 조정 열을 붙이기만 해도 결과가 같아야 한다 ──────────────────
    [V13, F13, ~, e13, BN13] = solve_with(S, ORD, L13, sprintf('base%d', n), P(n).mode, BB);
    [V19, F19, ~, e19] = solve_with(S, ORD, L19, sprintf('wide%d', n), P(n).mode, BB);
    R(n).e13 = e13;  R(n).e19 = e19;
    if isempty(e13) && isempty(e19)
        % NaN 자리는 뺀다 — 혼합 계통 결과표에는 값이 없는 줄이 섞인다.
        m = isfinite(V13) & isfinite(V19);
        R(n).r1_V = max([abs(V13(m) - V19(m)); 0]);  R(n).r1_n = sum(m);
        if ~isempty(F13) && numel(F13)==numel(F19)
            mf = isfinite(F13) & isfinite(F19);
            R(n).r1_F = max([abs(F13(mf) - F19(mf)); 0]);
        else
            R(n).r1_F = NaN;
        end
    else
        R(n).r1_V = NaN;  R(n).r1_n = 0;  R(n).r1_F = NaN;
    end

    % 🚨 2026-08-19: AC/DC 를 막던 갈래를 걷었다. A1 계단이 2026-08-17 에
    %    AC/DC 로 넓어졌으므로 혼합 계통도 **아래 AC 와 똑같은 길**로 간다.
    R(n).skip = 0;
    if P(n).row == 0 || isempty(V13)
        R(n).skip = 2;  continue
    end

    % ── 목표는 **도달 가능한** 값으로 — 지금 전압에서 조금만 옮긴다 ────
    %    (2026-08-13 교훈: 아주 먼 목표를 주면 계통이 다른 해로 가고,
    %     한계에 걸려 놓아진 것을 "계단이 틀렸다"로 잘못 읽게 된다.)
    bi = find(BN13 == P(n).bus, 1);
    if isempty(bi), R(n).skip = 3; continue; end
    TGT = V13(bi) + 0.005;
    R(n).tgt = TGT;

    % ── 연속으로 (계단 없이) ────────────────────────────────────────
    LC = L19;
    LC(P(n).row,14)=1; LC(P(n).row,15)=P(n).bus; LC(P(n).row,16)=TGT;
    LC(P(n).row,17)=TMIN; LC(P(n).row,18)=TMAX; LC(P(n).row,19)=0;
    [Vc, ~, TRc, ec] = solve_with(S, ORD, LC, sprintf('cont%d', n), P(n).mode, BB);
    R(n).e_cont = ec;
    if ~isempty(TRc), R(n).t_cont = TRc(1,4); else, R(n).t_cont = NaN; end
    if ~isempty(Vc), R(n).v_cont = Vc(bi); else, R(n).v_cont = NaN; end

    % ── 계단으로 ───────────────────────────────────────────────────
    LS = LC;  LS(P(n).row,19) = STEP;
    [Vs, Fs, TRs, es, ~, rs] = solve_with(S, ORD, LS, sprintf('step%d', n), P(n).mode, BB);
    R(n).e_step = es;
    if isempty(es) && ~isempty(TRs)
        R(n).t_step  = TRs(1,4);
        R(n).ncol    = size(TRs,2);
        if size(TRs,2) >= 11
            R(n).sz  = TRs(1,10);  R(n).state = TRs(1,11);
        else
            R(n).sz  = NaN;        R(n).state = NaN;
        end
        % ── 자기 대조: 그 탭을 고정으로 넣고 **손 안 댄 길**로 다시 ────
        [sV, sF, sFn, ef, nt_, nT_] = self_check(rs, S, ORD, P(n).mode, ...
            sprintf('fix%d', n), 1, L13, BB, P(n).row, 0);
        R(n).e_fix = ef;  R(n).self_nt = nt_;  R(n).self_T = nT_;
        if isempty(ef)
            R(n).self_V = sV;
            if sFn > 0, R(n).self_F = sF;  R(n).self_Fn = sFn;
            else,       R(n).self_F = NaN; R(n).self_Fn = 0;  end
        else
            R(n).self_V = NaN;  R(n).self_F = NaN;  R(n).self_Fn = 0;
        end
    else
        R(n).t_step = NaN;  R(n).sz = NaN;  R(n).state = NaN;
        R(n).self_V = NaN;  R(n).self_F = NaN;  R(n).self_Fn = 0;  R(n).ncol = 0;
        R(n).self_nt = 0;   R(n).self_T = 0;
    end

    % ══ 위상 계단 (Ctrl Mode = 2 · 한 단 0.5도) ═══════════════════════════
    %   목표는 **지금 흐르는 조류에서 조금 옮긴 값** — 멀리 주면 계통이 다른
    %   해로 간다(2026-08-13 교훈).
    R(n).ph_done = 0;
    if ~isempty(F13) && numel(F13) >= P(n).row && isfinite(F13(P(n).row))
        PH_STEP = 0.5;
        LPH = L19;
        LPH(P(n).row,14)=2;  LPH(P(n).row,16)=F13(P(n).row) - 2;
        LPH(P(n).row,17)=-20; LPH(P(n).row,18)=20; LPH(P(n).row,19)=PH_STEP;
        [~, ~, TRp, ep, ~, rp] = solve_with(S, ORD, LPH, sprintf('ph%d', n), P(n).mode, BB);
        R(n).e_ph = ep;
        if isempty(ep) && ~isempty(TRp)
            R(n).ph_done = 1;
            R(n).ph_val  = TRp(1,4);          % deg
            R(n).ph_sz   = TRp(1,10);
            R(n).ph_state= TRp(1,11);
            % 자기 대조 — 그 위상을 고정으로 넣고 손 안 댄 길로 (시각별)
            [pV, pF, pFn, epf] = self_check(rp, S, ORD, P(n).mode, ...
                sprintf('phf%d', n), 2, L13, BB, P(n).row, 0);
            if isempty(epf)
                R(n).ph_selfV = pV;  R(n).ph_selfF = pF;  R(n).ph_selfN = pFn;
            else
                R(n).ph_selfV = NaN; R(n).ph_selfF = NaN; R(n).ph_selfN = 0;
            end
        end
    end

    % ══ 스위치드 션트 계단 (Shunt Ctrl Mode = 1 · 한 단 5 Mvar) ═══════════
    R(n).sh_done = 0;
    B0 = S.AC_Bus_dat;
    if size(B0,2) >= 22, B17 = B0(:,1:17); else, B17 = B0; end
    if size(B17,2) >= 17
        B22 = [B17, nan(size(B17,1), 22-size(B17,2))];
        br = find(B17(:,1) == P(n).bus, 1);      % 버스 표에서 그 버스의 줄
        if ~isempty(br)
            SH_STEP = 5;
            B22(br,18)=1; B22(br,19)=V13(bi)+0.005;
            B22(br,20)=-50; B22(br,21)=50; B22(br,22)=SH_STEP;
            [~, ~, TRh, eh, ~, rh] = solve_with(S, ORD, L19, sprintf('sh%d', n), P(n).mode, B22);
            R(n).e_sh = eh;
            if isempty(eh) && ~isempty(TRh)
                R(n).sh_done = 1;
                R(n).sh_val  = TRh(1,4);        % Mvar
                R(n).sh_sz   = TRh(1,10);
                R(n).sh_state= TRh(1,11);
                % 자기 대조 — 그 Bs 를 **고정 션트**로 넣고 조정 없이 (시각별)
                [hV, hF, hFn, ehf] = self_check(rh, S, ORD, P(n).mode, ...
                    sprintf('shf%d', n), 3, L13, B17, 0, br);
                if isempty(ehf)
                    R(n).sh_selfV = hV;  R(n).sh_selfF = hF;  R(n).sh_selfN = hFn;
                else
                    R(n).sh_selfV = NaN; R(n).sh_selfF = NaN; R(n).sh_selfN = 0;
                end
            end
        end
    end
end
save(fullfile(d,'out.mat'), 'R');
disp('DONE');
""", encoding="utf-8")

    print("MATLAB 으로 돕니다 (계통마다 여러 번 풀어 시간이 걸립니다) …")
    r = subprocess.run([MATLAB, "-batch", f"run('{script}')"],
                       capture_output=True, text=True)
    if "DONE" not in r.stdout:
        print(r.stdout[-3000:]);  print(r.stderr[-2000:])
        print("\n🚨 MATLAB 이 끝까지 못 갔습니다.")
        return 2

    R = loadmat(str(WORK / "out.mat"), squeeze_me=True, struct_as_record=False)["R"]
    R = np.atleast_1d(R)

    def _s(x) -> str:
        """MATLAB 에서 온 값을 문자열로. 빈 문자열은 **빈 배열**로 온다."""
        if x is None:
            return ""
        a = np.atleast_1d(x)
        if a.size == 0:
            return ""
        return str(x)

    checks = fails = 0

    def ok(cond, label, detail=""):
        nonlocal checks, fails
        checks += 1
        if not cond:
            fails += 1
        print(f"      {'✅' if cond else '🚨'} {label}" + (f"  {detail}" if detail else ""))
        return cond

    print("\n" + "=" * 74)
    for i, info in enumerate(plan):
        o = R[i]
        print(f"\n[{i}] {info['name']}")

        # R1 — 조정 열을 붙이기만 하면 아무 일도 안 일어나야 한다
        # ⚠️ MATLAB 의 빈 문자열은 여기서 **빈 배열**로 온다 — `or` 로 묶으면
        #    "빈 배열의 참거짓이 모호하다"로 죽는다. 먼저 str 로 바꾼다.
        e13 = _s(getattr(o, "e13", ""))
        e19 = _s(getattr(o, "e19", ""))
        if e13 or e19:
            print(f"      · 이 계통은 기준 풀이가 안 된다 — 건너뜀 "
                  f"({(e13 or e19)[:60]})")
        else:
            n = int(o.r1_n)
            ok(n > 0 and float(o.r1_V) == 0.0,
               f"R1 끄면 완전히 같다 — 전압 최대차 {float(o.r1_V):.3e}",
               f"(버스 {n}개 대조)")
            if np.isfinite(o.r1_F):
                ok(float(o.r1_F) == 0.0,
                   f"R1 조류표도 같다 — 최대차 {float(o.r1_F):.3e}")

        if int(o.skip) == 2:
            print("      · 2권선 변압기가 없어 탭 계단 시험 없음")
            continue
        if int(o.skip) == 3:
            print("      · 고른 제어 버스가 결과표에 없어 건너뜀")
            continue
        if int(o.skip) == 4:            # 2026-08-19 이후로는 안 나온다
            print("      · (쓰이지 않는 갈래)")
            continue

        es = _s(getattr(o, "e_step", ""))
        if es:
            ok(False, "계단을 걸고 풀린다", f"— 오류: {es[:70]}")
            continue

        t, sz = float(o.t_step), float(o.sz)
        k = (t - 1.0) / STEP
        ok(abs(k - round(k)) < 1e-6,
           f"나온 탭이 자리 위에 있다 — {t:.6f} = 1.0 + {round(k):+d}×{STEP}",
           f"(어긋남 {abs(k-round(k)):.2e}칸)")
        ok(TMIN - 1e-9 <= t <= TMAX + 1e-9, f"한계 안이다 — {TMIN} ≤ {t:.6f} ≤ {TMAX}")
        ok(int(o.ncol) >= 11, f"결과표가 11열이다 — {int(o.ncol)}열")
        ok(abs(sz - STEP) < 1e-12, f"10열 = 한 단 크기 {sz:g}")
        ok(int(o.state) == 1, f"11열 = 계단으로 내렸다 ({int(o.state)})")

        tc = float(o.t_cont)
        if np.isfinite(tc):
            ok(abs(t - tc) <= STEP / 2 + 1e-9,
               f"연속값에서 반 단 안으로 옮겼다 — 연속 {tc:.6f} → 계단 {t:.6f}",
               f"(차 {abs(t-tc):.2e}, 반 단 {STEP/2})")

        # 🚨 2026-09-08 — **건너뛰지 않는다.** 24시각 계통에서 이 대조가 깨졌을 때
        #    「시험의 한계」로 보고 건너뛰게 했던 적이 있는데, 실제 원인은 엔진이
        #    시각별 탭을 앱에 안 넘긴 것이었다. 앱이 적은 탭이 그 시각 계산에
        #    정말 쓰였는지가 이 시험의 본론이므로 시각을 갈라서 끝까지 본다.
        nt, nT = int(getattr(o, "self_nt", 1)), int(getattr(o, "self_T", 1))
        when = f"(시각 {nT}개 중 {nt}개 대조)" if nT > 1 else ""
        ef = _s(getattr(o, "e_fix", ""))
        if ef:
            ok(False, "자기 대조를 돌린다", f"— 오류: {ef[:70]}")
        else:
            sv = float(o.self_V)
            ok(np.isfinite(sv) and sv < 1e-9,
               f"자기 대조(전압) — 그 탭을 고정으로 넣고 손 안 댄 길로 풀면 같다 "
               f"{sv:.3e}", when)
            sf, sfn = float(o.self_F), int(o.self_Fn)
            ok(sfn > 0 and np.isfinite(sf) and sf < 1e-9,
               f"자기 대조(조류표) — {sf:.3e}", f"(선로 {sfn}개 대조)")

        # ── 위상 계단 ──────────────────────────────────────────────
        if int(getattr(o, "ph_done", 0)):
            pv, psz = float(o.ph_val), float(o.ph_sz)
            kk = pv / 0.5
            ok(abs(kk - round(kk)) < 1e-6,
               f"위상이 자리 위에 있다 — {pv:.4f}° = {round(kk):+d}×0.5°")
            ok(abs(psz - 0.5) < 1e-9, f"위상 10열 = 한 단 {psz:g}°")
            ok(int(o.ph_state) == 1, f"위상 11열 = 계단으로 내렸다 ({int(o.ph_state)})")
            ok(float(o.ph_selfV) < 1e-9 and int(o.ph_selfN) > 0,
               f"위상 자기 대조 — 전압 {float(o.ph_selfV):.3e} · "
               f"조류 {float(o.ph_selfF):.3e}", f"(선로 {int(o.ph_selfN)}개)")
        else:
            print(f"      · 위상 계단은 이 계통에서 안 돌렸다 "
                  f"({_s(getattr(o, 'e_ph', ''))[:50]})")

        # ── 스위치드 션트 계단 ─────────────────────────────────────
        if int(getattr(o, "sh_done", 0)):
            hv, hsz = float(o.sh_val), float(o.sh_sz)
            kk = hv / 5.0
            ok(abs(kk - round(kk)) < 1e-6,
               f"션트가 자리 위에 있다 — {hv:.4f} Mvar = {round(kk):+d}×5")
            ok(abs(hsz - 5.0) < 1e-9, f"션트 10열 = 한 단 {hsz:g} Mvar")
            ok(int(o.sh_state) == 1, f"션트 11열 = 계단으로 내렸다 ({int(o.sh_state)})")
            ok(float(o.sh_selfV) < 1e-9 and int(o.sh_selfN) > 0,
               f"션트 자기 대조 — 전압 {float(o.sh_selfV):.3e} · "
               f"조류 {float(o.sh_selfF):.3e}", f"(선로 {int(o.sh_selfN)}개)")
        else:
            print(f"      · 스위치드 션트 계단은 이 계통에서 안 돌렸다 "
                  f"({_s(getattr(o, 'e_sh', ''))[:50]})")

    for nm, why in skipped:
        print(f"\n[–] {nm}  · {why}")

    print("\n" + "=" * 74)
    print(f">>> 대조 {checks}개 · 실패 {fails}건")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
