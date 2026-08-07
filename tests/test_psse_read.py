# -*- coding: utf-8 -*-
"""PSS/E `.raw` 읽기 — 판(rev)이 달라도 읽히나 (2026-08-06 신설).

  X1 의 목적은 **남이 자기 케이스를 그대로 여는 것**이다. 그런데 PSS/E 형식은
  판마다 첫 줄 칸 수가 다르고, 칸을 나누는 것도 쉼표일 수도 공백일 수도 있다.
  둘 다 못 읽어서 멀쩡한 파일이 터지거나 조용히 빈 표가 되고 있었다.

      python tests/test_psse_read.py
"""
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import unigrid_convert as UC                     # noqa: E402
from load_case import load_case                  # noqa: E402

bad = 0


def ok(cond, what, note=""):
    global bad
    print(f"  {'✅' if cond else '🚨'} {what}" + (f"  — {note}" if note else ""))
    if not cond:
        bad += 1


def write(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".raw", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return Path(f.name)


# ── 1. 첫 줄의 칸 수가 판마다 다르다 ───────────────────────────────────
print("1) 첫 줄 (판마다 칸 수가 다르다)")
BODY = """\
Comment 1
Comment 2
    1,'Bus 1', 345.0000,3,   1,   1,   1,1.04000,   0.0000
    2,'Bus 2', 345.0000,1,   1,   1,   1,1.00000,   0.0000
0 / END OF BUS DATA, BEGIN LOAD DATA
    2,'1 ',1,1,1,  50.000,  20.000, 0.0, 0.0, 0.0, 0.0
0 / END OF LOAD DATA, BEGIN FIXED SHUNT DATA
0 / END OF FIXED SHUNT DATA, BEGIN GENERATOR DATA
    1,'1 ',  60.000,  10.000, 100.0,-100.0,1.04000,0,100.0,0,0,0,0,1.0,1
0 / END OF GENERATOR DATA, BEGIN BRANCH DATA
    1,    2,'1 ',0.01000,0.10000,0.02000, 200.0, 200.0, 200.0,0,0,0,0,1
0 / END OF BRANCH DATA, BEGIN TRANSFORMER DATA
0 / END OF TRANSFORMER DATA, BEGIN AREA DATA
0 / END OF AREA DATA
"""
for head, want_f, tag in ((" 0,   100.00        / PSS/E-29.0", 60.0, "rev 29 (2칸)"),
                          ("0,    100.00, 30 / PSS(tm)E-30", 60.0, "rev 30 (3칸)"),
                          ("0, 100.00, 33, 0, 0, 50.00 / rev33", 50.0, "rev 33 (6칸)")):
    p = write(head + "\n" + BODY)
    try:
        c = UC.psse_to_case(p)
        base = np.asarray(c.tables["Base_dat"], float)[0]
        ok(abs(base[0] - 100.0) < 1e-9 and abs(base[1] - want_f) < 1e-9,
           f"{tag} 를 읽는다", f"기준용량 {base[0]:g} MVA · 주파수 {base[1]:g} Hz")
    except Exception as exc:
        ok(False, f"{tag} 를 읽는다", f"{type(exc).__name__}: {str(exc)[:40]}")
    p.unlink()

# 주파수 칸이 없으면 60 Hz 로 둔다 (있으면 파일 값을 쓴다 — 위 rev33 이 50 Hz)
print("     ↳ 주파수 칸이 없는 판은 60 Hz 로 두고, 있으면 파일 값을 쓴다")

# ── 2. 칸을 나누는 것이 쉼표만이 아니다 ────────────────────────────────
print("\n2) 칸 나누기 — 쉼표와 공백")
SPACED = """\
 0,   100.00        / PSS/E-29.0
Comment 1
Comment 2
    1 'Bus 1   '  345.0000 3    0.000    0.000   1   1 1.04000    0.0000  1
    2 'Bus 2   '  345.0000 1    0.000    0.000   1   1 1.00000    0.0000  1
 0   / END OF BUS DATA, BEGIN LOAD DATA
    2 '1 ' 1   1   1   50.000   20.000    0.000    0.000    0.000    0.000
 0   / END OF LOAD DATA, BEGIN GENERATOR DATA
    1 '1 '    60.00    10.00   100.00  -100.00 1.0400     0  100.00 0.0 0.1 0.0 0.0 1.0 1
 0   / END OF GENERATOR DATA, BEGIN BRANCH DATA
    1     2 '1 '   0.01000   0.10000  0.02000   200.00   200.00   200.00 0.0 0.0 0.0 0.0 1
 0   / END OF BRANCH DATA, BEGIN TRANSFORMER DATA
 0   / END OF TRANSFORMER DATA, BEGIN AREA DATA
 0   / END OF AREA DATA
"""
p = write(SPACED)
c = UC.psse_to_case(p)
gen = np.asarray(c.tables["AC_gen_dat"], float)
line = np.asarray(c.tables["AC_Line_dat"], float)
busn = np.asarray(c.tables["AC_Bus_dat"], float)
ok(busn.shape[0] == 2, "공백으로 나뉜 파일 — 버스", f"{busn.shape[0]}개")
ok(line.shape[0] == 1, "공백으로 나뉜 파일 — 선로", f"{line.shape[0]}개")
ok(gen.shape[0] == 1, "공백으로 나뉜 파일 — 발전기", f"{gen.shape[0]}대")
# 🚨 여기가 진짜 함정이었다 — 칸이 하나 밀려 Status 가 100 으로 읽혔고,
#    엔진은 1 만 '켜짐' 으로 보므로 **발전기가 전부 꺼진 계통**이 되어 발산했다.
ok(gen.size and abs(gen[0, 8] - 1.0) < 1e-9, "발전기 Status 가 1 이다 (100 이 아니라)",
   f"{gen[0, 8]:g}" if gen.size else "")
ok(gen.size and abs(gen[0, 5] - 60e6) < 1.0, "발전기 출력이 제자리",
   f"{gen[0, 5] / 1e6:g} MW" if gen.size else "")
p.unlink()

# ── 3. PSS/E 가 아닌 파일은 **터지지 말고 말해 준다** ──────────────────
print("\n3) PSS/E 가 아닌 파일")
p = write("Header 1\nHeader 2\nHeader 3\n  1 'Line 1' 1.1 -.1 /, \"comment\"\n")
try:
    UC.psse_to_case(p)
    ok(False, "PSS/E 가 아니면 막는다")
except ValueError as exc:
    msg = str(exc)
    ok("PSS/E 파일로 읽히지 않습니다" in msg, "PSS/E 가 아니면 막는다")
    ok("첫 줄:" in msg, "무엇을 봤는지 보여 준다")
    ok(".xlsx" in msg or ".m" in msg, "다른 형식으로 열어 보라고 알려 준다")
except Exception as exc:
    ok(False, "터지지 않고 ValueError 로 온다", f"{type(exc).__name__}")
p.unlink()

# ── 4. 진짜 파일 — 되던 것이 그대로 되나 ───────────────────────────────
print("\n4) 진짜 파일")
real = REPO / "cases/AConly_psse_3W_unigrid_easy.xlsx"      # 이미 변환해 둔 것
ok(real.is_file(), "3권선 케이스가 저장소에 있다")
MP = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/matpower8.0/lib/t")
t3 = MP / "t_psse_case3.raw"
if t3.is_file():
    c = UC.psse_to_case(t3)
    n = np.asarray(c.tables["AC_Bus_dat"], float).shape[0]
    ok(n == 42, "t_psse_case3.raw (rev 30) 이 읽힌다", f"버스 {n}개")

# ── 5. 옛 판은 버스 줄의 칸 배치가 다르다 ──────────────────────────────
print("\n5) 버스 줄의 칸 배치 (판마다 다르다)")
#   rev ≤ 30 : I, NAME, BASKV, IDE, **GL, BL**, AREA, ZONE, VM, VA
#   rev ≥ 31 : I, NAME, BASKV, IDE, AREA, ZONE, OWNER, VM, VA
OLD_BUS = """\
 0,   100.00        / PSS/E-29.0
c1
c2
    1 'B1' 345.0 3   1.5   -2.5   7   8 1.04000   3.5000  1
 0   / END OF BUS DATA, BEGIN LOAD DATA
 0   / END OF LOAD DATA, BEGIN GENERATOR DATA
 0   / END OF GENERATOR DATA, BEGIN BRANCH DATA
 0   / END OF BRANCH DATA, BEGIN TRANSFORMER DATA
 0   / END OF TRANSFORMER DATA, BEGIN AREA DATA
 0   / END OF AREA DATA
"""
p5 = write(OLD_BUS)
B = np.asarray(UC.psse_to_case(p5).tables["AC_Bus_dat"], float)
ok(abs(B[0, 11] - 1.04) < 1e-9, "옛 판 — 전압을 VM 자리에서 읽는다", f"{B[0, 11]:g} pu")
ok(abs(B[0, 12] - 3.5) < 1e-9, "옛 판 — 위상각을 VA 자리에서 읽는다", f"{B[0, 12]:g} deg")
ok(abs(B[0, 1] - 1.5) < 1e-9 and abs(B[0, 2] + 2.5) < 1e-9,
   "옛 판 — 버스 줄 안의 션트(GL·BL)를 집는다", f"Gs {B[0,1]:g} · Bs {B[0,2]:g}")
ok(abs(B[0, 16] - 7.0) < 1e-9, "옛 판 — Area 자리도 맞다", f"{B[0,16]:g}")
p5.unlink()

# ── 6. 🚨 버스 번호의 음수 부호는 계량단 표시일 뿐이다 ─────────────────
print("\n6) 버스 번호의 음수 부호 (계량단 표시)")
NEG = """\
0,   100.00, 33, 0, 0, 60.00 / rev33
c1
c2
    1,'B1', 345.0,3,   1,   1,   1,1.04000,   0.0000
    2,'B2', 345.0,1,   1,   1,   1,1.00000,   0.0000
0 / END OF BUS DATA, BEGIN LOAD DATA
0 / END OF LOAD DATA, BEGIN FIXED SHUNT DATA
0 / END OF FIXED SHUNT DATA, BEGIN GENERATOR DATA
0 / END OF GENERATOR DATA, BEGIN BRANCH DATA
    1,   -2,'1 ',0.01000,0.10000,0.02000, 200.0, 200.0, 200.0,0,0,0,0,1
0 / END OF BRANCH DATA, BEGIN TRANSFORMER DATA
0 / END OF TRANSFORMER DATA, BEGIN AREA DATA
0 / END OF AREA DATA
"""
p6 = write(NEG)
L = np.asarray(UC.psse_to_case(p6).tables["AC_Line_dat"], float)
ok(L.shape[0] == 1, "`1, -2` 로 적힌 선로를 버리지 않는다", f"선로 {L.shape[0]}개")
ok(L.size and L[0, 1] == 1 and L[0, 2] == 2, "부호를 떼고 2번 버스로 읽는다",
   f"{int(L[0,1])}–{int(L[0,2])}" if L.size else "")
p6.unlink()

# ── 7. MATPOWER 의 정답 변환본과 대조 ──────────────────────────────────
print("\n7) MATPOWER 정답본과 대조 (t_psse_case2)")
if (MP / "t_psse_case2.raw").is_file() and (MP / "t_psse_case2.m").is_file():
    a = load_case(str(MP / "t_psse_case2.raw"))
    b = load_case(str(MP / "t_psse_case2.m"))
    for k, lim in (("AC_Bus_dat", 0.05), ("AC_Line_dat", 0.11), ("AC_gen_dat", 1e-9)):
        x = np.asarray(a.tables[k], float); y = np.asarray(b.tables[k], float)
        if x.shape != y.shape:
            ok(False, f"{k} 모양이 같다", f"{x.shape} vs {y.shape}"); continue
        d = np.abs(np.nan_to_num(x) - np.nan_to_num(y))
        rel = (d / np.maximum(np.abs(np.nan_to_num(y)), 1.0)).max()
        ok(rel <= lim, f"{k} 가 정답본과 맞는다", f"최대 상대차 {rel:.3g}")
    # 남은 차이는 전압 한계 기본값(0.94/1.06 vs 0.9/1.1)이라 물리가 아니다

# ── 8. 3권선 STAT — 어느 권선이 빠졌나 (2026-08-07, 엔진 8차 재컴파일) ──
print("\n8) 3권선 STAT 0~4")
GRIDS = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/03_전기연자문_2026_3/"
             "04_python_conversion/02_GitHub_unigrid/acdc_powerflow/grids")
sample = GRIDS / "psse_3w_sample.raw"
if sample.is_file():
    # 이 파일은 STAT 1·2·3·4 를 하나씩 담고 있다 (이름이 3WNDSTAT1~4).
    t3 = np.asarray(load_case(str(sample)).tables["AC_3wtrans_dat"], float)
    ok(t3.shape[0] == 4, "3권선 4개가 다 들어온다 (STAT=4 도)", f"{t3.shape[0]}개")
    stats = sorted(int(v) for v in t3[:, 4])
    ok(stats == [1, 2, 3, 4], "STAT 값이 그대로 실린다", f"{stats}")
    # 🚨 STAT=4 는 **권선 1이 빠진** 것이다. 권선 1의 버스(209)는 고립이라 계통에
    #    없지만, 권선 2·3(217·218)은 살아 있어야 한다 — 옛 판은 변압기를 통째로
    #    버려 이 두 버스가 서로 끊겼다.
    row4 = t3[t3[:, 4] == 4][0]
    ok(int(row4[2]) == 217 and int(row4[3]) == 218,
       "STAT=4 의 살아 있는 권선 두 버스가 실린다", f"{int(row4[2])}·{int(row4[3])}")
else:
    print("  ⏭  psse_3w_sample.raw 이 없어 건너뛴다")

# STAT=0 은 정상적으로 "통째로 빠짐" 이다 — 예외를 던져 파일 전체를 막으면 안 된다.
ZERO = """0,  100.00, 33, 0, 0, 60.00
c1
c2
    1,'B1', 345.0,3,   1,   1,   1,1.04000,   0.0000
    2,'B2', 345.0,1,   1,   1,   1,1.00000,   0.0000
    3,'B3', 138.0,1,   1,   1,   1,1.00000,   0.0000
    4,'B4',  13.8,1,   1,   1,   1,1.00000,   0.0000
0 / END OF BUS DATA, BEGIN LOAD DATA
0 / END OF LOAD DATA, BEGIN FIXED SHUNT DATA
0 / END OF FIXED SHUNT DATA, BEGIN GENERATOR DATA
0 / END OF GENERATOR DATA, BEGIN BRANCH DATA
    1,    2,'1 ',0.01000,0.10000,0.02000, 200.0, 200.0, 200.0,0,0,0,0,1
0 / END OF BRANCH DATA, BEGIN TRANSFORMER DATA
    2,    3,    4,'1 ',1,1,1, 0.0, 0.0,2,'OFF3W       ',0,   1,1.0
0.01,0.10,100.0,0.01,0.10,100.0,0.01,0.10,100.0
1.0, 345.0, 0.0, 100.0, 100.0, 100.0,0,    0, 1.1, 0.9, 1.1, 0.9, 33, 0, 0.0, 0.0
1.0, 138.0, 0.0, 100.0, 100.0, 100.0,0,    0, 1.1, 0.9, 1.1, 0.9, 33, 0, 0.0, 0.0
1.0,  13.8, 0.0, 100.0, 100.0, 100.0,0,    0, 1.1, 0.9, 1.1, 0.9, 33, 0, 0.0, 0.0
0 / END OF TRANSFORMER DATA, BEGIN AREA DATA
0 / END OF AREA DATA
"""
p8 = write(ZERO)
try:
    c8 = UC.psse_to_case(p8)
    n8 = np.asarray(c8.tables["AC_Bus_dat"], float).shape[0]
    ok(n8 == 4, "STAT=0 인 3권선이 있어도 파일이 읽힌다", f"버스 {n8}개")
except Exception as exc:
    ok(False, "STAT=0 인 3권선이 있어도 파일이 읽힌다", str(exc)[:80])
p8.unlink()

print(f"\n{'✅ 전부 통과' if bad == 0 else f'🚨 {bad}건 틀림'}")
sys.exit(1 if bad else 0)
