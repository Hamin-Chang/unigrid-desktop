% 위상 조정기 야코비안 — 해석식 vs 유한차분 (2026-08-13, §7 5단계 ②)
%
% 새로 만든 것은 둘이다:
%   (가) 미스매치를 φ 로 미분한 **열**   dP_dp · dQ_dp
%   (나) 조류 식을 V·θ·φ 로 미분한 **행** dF_dV · dF_dth · dF_dp
% (나)는 이번에 처음 생긴 모양이라 특히 틀리기 쉽다.
v14 = getenv('V14DIR');
addpath(v14); addpath(fullfile(v14,'functions'));

S  = load(getenv('CASEMAT'));
L  = [S.AC_Line_dat, nan(size(S.AC_Line_dat,1), 6)];
i  = 8;                       % 8번 선로 (변압기 4→7) — case14 의 변압기는 8·9·10 뿐
L(i,14)=2; L(i,16)=0; L(i,17)=-30; L(i,18)=30; L(i,19)=0;
L(i,8) = 0.07;                % 0 이 아닌 위상에서 재야 뜻이 있다

n = size(S.AC_Bus_dat,1);
rng_seed = 0;                 %#ok<NASGU>
Vm = 0.95 + 0.1*((1:n)'/n);   % 아무 운전점이나 — 미분은 그 점에서 맞으면 된다
Va = 0.02*((1:n)' - n/2);
freq = 1;

live = true;
[dP, dQ, dFV, dFth, dFp] = local_phase_jac_probe(L, Vm, Va, freq, i, live, n);

h = 1e-7;
bad = 0; ncmp = 0;

fprintf('=== (가) 미스매치를 phi 로 미분한 열 ===\n');
Lp = L;  Lp(i,8) = L(i,8) + h;
Lm = L;  Lm(i,8) = L(i,8) - h;
[Pp, Qp] = inj(Lp, Vm, Va, freq, n);
[Pm, Qm] = inj(Lm, Vm, Va, freq, n);
% 미스매치 = 지정 - 계산 이므로 d(미스매치)/dphi = -dP_cal/dphi
numP = -(Pp - Pm)/(2*h);   numQ = -(Qp - Qm)/(2*h);
eP = max(abs(numP - dP));  eQ = max(abs(numQ - dQ));
ncmp = ncmp + 2*n;
fprintf('  dP/dphi 최대차 %.3e · dQ/dphi 최대차 %.3e  (버스 %d개씩)\n', eP, eQ, n);
if eP > 1e-6 || eQ > 1e-6, bad = bad + 1; fprintf('  FAIL\n'); else, fprintf('  OK\n'); end

fprintf('=== (나) 조류 식의 행 ===\n');
% dF/dphi
Fp = -lp(Lp, i, Vm, Va, freq);   Fm = -lp(Lm, i, Vm, Va, freq);
nFp = (Fp - Fm)/(2*h);
ncmp = ncmp + 1;
fprintf('  dF/dphi  해석 %.6e  수치 %.6e  차 %.3e\n', dFp, nFp, abs(dFp-nFp));
if abs(dFp - nFp) > 1e-6, bad = bad + 1; fprintf('  FAIL\n'); else, fprintf('  OK\n'); end

% dF/dtheta · dF/dV — 그 선로 양 끝만 0 이 아니어야 한다
worst_th = 0; worst_v = 0;
for k = 1:n
    Vap = Va; Vap(k) = Va(k) + h;   Vam = Va; Vam(k) = Va(k) - h;
    nth = (-lp(L,i,Vm,Vap,freq) + lp(L,i,Vm,Vam,freq))/(2*h);
    worst_th = max(worst_th, abs(nth - dFth(k)));
    Vmp = Vm; Vmp(k) = Vm(k) + h;   Vmm = Vm; Vmm(k) = Vm(k) - h;
    nv  = (-lp(L,i,Vmp,Va,freq) + lp(L,i,Vmm,Va,freq))/(2*h);
    worst_v = max(worst_v, abs(nv - dFV(k)));
    ncmp = ncmp + 2;
end
fprintf('  dF/dtheta 최대차 %.3e · dF/dV 최대차 %.3e  (버스 %d개씩)\n', ...
        worst_th, worst_v, n);
if worst_th > 1e-6 || worst_v > 1e-6, bad = bad + 1; fprintf('  FAIL\n'); else, fprintf('  OK\n'); end

fprintf('\n>>> 대조 %d개 · 실패 %d건\n', ncmp, bad);
fprintf('DONE_JAC\n');

% ── 아래는 엔진과 **같은 식을 다시 적은 것**이 아니라 엔진 것을 그대로 부른다 ──
function [P, Q] = inj(L, Vm, Va, freq, n)
    Y = ybus_of(L, Vm, freq, n);
    V = Vm .* exp(1i*Va);
    S = V .* conj(Y*V);
    P = real(S);  Q = imag(S);
end

function Y = ybus_of(L, ~, freq, n)
    Y = sparse(n, n);
    for i = 1:size(L,1)
        f=L(i,2); o=L(i,3); R=L(i,4); X=L(i,5)*freq; B=L(i,6)*freq;
        t=L(i,7); ph=L(i,8);
        if isnan(t)||t==0, t=1; end
        if isnan(ph), ph=0; end
        if L(i,12)==0, t=1; end
        Yl = 1/(R+1i*X);  tp = t*exp(1i*ph);
        Y(f,o)=Y(f,o) - Yl/conj(tp);
        Y(o,f)=Y(o,f) - Yl/tp;
        Y(f,f)=Y(f,f) + (Yl+1i*B/2)/(abs(tp)^2);
        Y(o,o)=Y(o,o) + Yl+1i*B/2;
    end
end

function P = lp(L, i, Vm, Va, freq)
    f=L(i,2); o=L(i,3); R=L(i,4); X=L(i,5)*freq; B=L(i,6)*freq;
    t=L(i,7); ph=L(i,8);
    if isnan(t)||t==0, t=1; end
    Yl=1/(R+1i*X); tp=t*exp(1i*ph);
    Yff=(Yl+1i*B/2)/(abs(tp)^2); Yft=-Yl/conj(tp);
    Vf=Vm(f)*exp(1i*Va(f)); Vo=Vm(o)*exp(1i*Va(o));
    P = real(Vf*conj(Yff*Vf + Yft*Vo));
end

function [dP,dQ,dFV,dFth,dFp] = local_phase_jac_probe(L, Vm, Va, freq, i, live, n)
    % 엔진의 local_phase_jac 를 **그대로** 꺼내 쓴다 (복붙하면 그 코드가 틀려도 못 잡는다)
    src = fileread(fullfile(getenv('V14DIR'),'functions','solve_AC_newton_v4.m'));
    j0 = strfind(src, 'function [dP_dp, dQ_dp, dF_dV, dF_dth, dF_dp] =');
    body = src(j0:end);
    body = strrep(body, 'local_phase_jac', 'probe_phase_jac');
    p = tempname; mkdir(p);
    fid = fopen(fullfile(p,'probe_phase_jac.m'),'w','n','UTF-8');
    fwrite(fid, unicode2native(body,'UTF-8')); fclose(fid);
    addpath(p);
    [dP,dQ,dFV,dFth,dFp] = probe_phase_jac(L, Vm, Va, freq, i, live, n);
    rmpath(p);
end
