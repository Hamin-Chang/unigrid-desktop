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
    2)  AC/DC 계통은 **분명히 막는가** (조용히 무시하지 않는다)

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

    row = bus = 0
    if L is not None and L.size and L.shape[1] > 11 and not is_acdc:
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
    return dict(name=name, tables=T, row=row, bus=bus, is_acdc=is_acdc, mode=mode)


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
        kind = ("AC/DC — 막혀야 함" if info["is_acdc"]
                else (f"탭 계단: {info['row']}번 선로 → 버스 {info['bus']}"
                      if info["row"] else "2권선 변압기가 없어 탭 시험 없음"))
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

function [V, F, TR, err, BN] = solve_with(S, ORD, L, tag, MODE, B)
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
    V = []; F = []; TR = []; err = ''; BN = [];
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

    % ── R1: 조정 열을 붙이기만 해도 결과가 같아야 한다 ──────────────────
    [V13, F13, ~, e13, BN13] = solve_with(S, ORD, L13, sprintf('base%d', n), P(n).mode);
    [V19, F19, ~, e19] = solve_with(S, ORD, L19, sprintf('wide%d', n), P(n).mode);
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

    R(n).skip = 0;
    if P(n).acdc
        % ── AC/DC 는 분명히 막아야 한다 ──────────────────────────────
        % 변압기 줄에 건다 — 선로가 아예 없거나 변압기가 없으면 「막는가」를
        % 물을 수 없다(엉뚱한 오류가 나서 막이가 도는지 알 수 없다).
        tr = find(L13(:,12) == 1, 1);
        if isempty(tr) || ~isfinite(L13(tr,2))
            R(n).skip = 4;  continue
        end
        LA = L19;  LA(tr,14) = 1;  LA(tr,15) = L13(tr,3);  LA(tr,16) = 1.0;
        [~, ~, ~, R(n).e_acdc] = solve_with(S, ORD, LA, sprintf('acdc%d', n), P(n).mode);
        R(n).skip = 1;
        continue
    end
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
    [Vc, ~, TRc, ec] = solve_with(S, ORD, LC, sprintf('cont%d', n), P(n).mode);
    R(n).e_cont = ec;
    if ~isempty(TRc), R(n).t_cont = TRc(1,4); else, R(n).t_cont = NaN; end
    if ~isempty(Vc), R(n).v_cont = Vc(bi); else, R(n).v_cont = NaN; end

    % ── 계단으로 ───────────────────────────────────────────────────
    LS = LC;  LS(P(n).row,19) = STEP;
    [Vs, Fs, TRs, es] = solve_with(S, ORD, LS, sprintf('step%d', n), P(n).mode);
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
        LF = L13;  LF(P(n).row,7) = R(n).t_step;
        [Vf, Ff, ~, ef] = solve_with(S, ORD, LF, sprintf('fix%d', n), P(n).mode);
        R(n).e_fix = ef;
        if isempty(ef)
            R(n).self_V = max(abs(Vs - Vf));
            if ~isempty(Fs) && numel(Fs)==numel(Ff)
                R(n).self_F = max(abs(Fs - Ff));  R(n).self_Fn = numel(Fs);
            else
                R(n).self_F = NaN;  R(n).self_Fn = 0;
            end
        else
            R(n).self_V = NaN;  R(n).self_F = NaN;  R(n).self_Fn = 0;
        end
    else
        R(n).t_step = NaN;  R(n).sz = NaN;  R(n).state = NaN;
        R(n).self_V = NaN;  R(n).self_F = NaN;  R(n).self_Fn = 0;  R(n).ncol = 0;
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
        [Vp, Fp, TRp, ep] = solve_with(S, ORD, LPH, sprintf('ph%d', n), P(n).mode);
        R(n).e_ph = ep;
        if isempty(ep) && ~isempty(TRp)
            R(n).ph_done = 1;
            R(n).ph_val  = TRp(1,4);          % deg
            R(n).ph_sz   = TRp(1,10);
            R(n).ph_state= TRp(1,11);
            % 자기 대조 — 그 위상을 고정으로 넣고 손 안 댄 길로
            LPF = L13;  LPF(P(n).row,8) = R(n).ph_val;   % 엑셀과 같은 **도**
            [Vpf, Fpf, ~, epf] = solve_with(S, ORD, LPF, sprintf('phf%d', n), P(n).mode);
            if isempty(epf)
                mv = isfinite(Vp) & isfinite(Vpf);
                R(n).ph_selfV = max([abs(Vp(mv) - Vpf(mv)); 0]);
                mf = isfinite(Fp) & isfinite(Fpf);
                R(n).ph_selfF = max([abs(Fp(mf) - Fpf(mf)); 0]);
                R(n).ph_selfN = sum(mf);
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
            [Vh, Fh, TRh, eh] = solve_with(S, ORD, L19, sprintf('sh%d', n), P(n).mode, B22);
            R(n).e_sh = eh;
            if isempty(eh) && ~isempty(TRh)
                R(n).sh_done = 1;
                R(n).sh_val  = TRh(1,4);        % Mvar
                R(n).sh_sz   = TRh(1,10);
                R(n).sh_state= TRh(1,11);
                % 자기 대조 — 그 Bs 를 **고정 션트**로 넣고 조정 없이
                BF = B17;  BF(br,3) = R(n).sh_val;
                [Vhf, Fhf, ~, ehf] = solve_with(S, ORD, L13, sprintf('shf%d', n), P(n).mode, BF);
                if isempty(ehf)
                    mv = isfinite(Vh) & isfinite(Vhf);
                    R(n).sh_selfV = max([abs(Vh(mv) - Vhf(mv)); 0]);
                    mf = isfinite(Fh) & isfinite(Fhf);
                    R(n).sh_selfF = max([abs(Fh(mf) - Fhf(mf)); 0]);
                    R(n).sh_selfN = sum(mf);
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

        if int(o.skip) == 1:
            e = _s(getattr(o, "e_acdc", ""))
            ok("A1" in e or "조정" in e or "AC/DC" in e or "혼합" in e,
               "AC/DC 경로에서 분명히 막힌다", f"— {e[:64]}")
            continue
        if int(o.skip) == 2:
            print("      · 2권선 변압기가 없어 탭 계단 시험 없음")
            continue
        if int(o.skip) == 3:
            print("      · 고른 제어 버스가 결과표에 없어 건너뜀")
            continue
        if int(o.skip) == 4:
            print("      · AC 변압기 선로가 없어 「막는가」를 물을 수 없음")
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

        sv = float(o.self_V)
        ok(np.isfinite(sv) and sv < 1e-9,
           f"자기 대조(전압) — 그 탭을 고정으로 넣고 손 안 댄 길로 풀면 같다 "
           f"{sv:.3e}")
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
