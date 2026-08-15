"""format_v2.py — UNIGRID 케이스 엑셀 서식 v2 의 **정의 한 곳**.

무엇을 담나
    새 서식(v2)의 시트·열 이름·단위와, 옛 서식(v1)의 **어느 자리**에서 온 값인지를 적어 둔다.
    변환 도구(`convert_case.py`)와 나중의 읽기가 **같은 정의**를 쓰게 하려는 것이다 —
    두 곳에 따로 적으면 반드시 갈라진다.

왜 이렇게 생겼나 (설계 문서: `UNIGRID_v2/새서식_v2.md`)
    계산 엔진은 지금처럼 **열 위치**로 받는다. 그래서 v2 는 *사람이 보는 서식*이고,
    엔진에 넘길 때는 여기 적힌 `v1_col` 자리로 되돌린다.
    ⇒ **MATLAB 을 안 고쳐도 되고(재컴파일 0), 옛 파일도 계속 열린다.**

읽는 방향이 둘이다
    v1 → v2 (변환):  v2값 = v1값 * scale
    v2 → 엔진 (읽기): 엔진값 = v2값 / scale,  자리 = v1_col

🚨 v1 은 **위치로만** 뜻이 정해진다(머리글을 아무도 안 읽었다). 그래서 v1 을 읽을 때는
   머리글을 믿지 않고 위치로 읽되, **열 수가 아는 모양인지 먼저 확인**한다.
   세대가 다른 파일(예: 발전기·부하를 버스 시트에 담던 22열짜리 `AC Bus Data`)을
   같은 자리로 읽으면 조용히 엉뚱한 계통이 만들어진다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ─────────────────────────────────────────────── 단위 환산
# v1(엔진이 쓰는 단위) → v2(사람이 보는 단위) 로 갈 때 곱하는 수.
W_TO_MW = 1e-6          # W    → MW      · Var → Mvar · VA → MVA
V_TO_KV = 1e-3          # V    → kV
KEEP = 1.0              # 그대로

# 되돌릴 때 쓰는 수. ⚠️ `/ 1e-6` 이 아니라 `* 1e6` 으로 되돌린다 —
# 1e-6 은 이진수로 딱 안 떨어져 나누면 오차가 더 붙고, 1e6 은 딱 떨어진다.
MW_TO_W = 1e6
KV_TO_V = 1e3


@dataclass
class Col:
    """v2 의 열 하나."""
    name: str                     # v2 머리글 (단위는 unit 에 따로)
    unit: str = ""                # 사람이 보는 단위. 빈 값이면 단위 없음
    v1_col: int | None = None     # v1 에서 몇 번째 열이었나 (1부터). None = v2 에서 새로 생긴 열
    scale: float = KEEP           # v1값 * scale = v2값
    required: bool = True         # 없으면 못 읽는 열인가
    default: float | None = None  # v1 에 그 열이 없을 때 채울 값
    note: str = ""
    # v1 에는 아예 없던 열인데 **자리는 엔진 것**이다(v1_col 이 있다).
    # 옛 파일을 바꿀 때도 **머리글만 만들어 둔다** — 사람이 값을 채워 넣을 자리가 필요하다.
    # 값이 비어 있으면 `read_v2` 의 폭 줄이기가 옛 폭으로 되돌리므로 엔진은 못 본 척한다.
    v2_new: bool = False

    @property
    def header(self) -> str:
        return f"{self.name} [{self.unit}]" if self.unit else self.name


@dataclass
class Sheet:
    """v2 의 시트 하나."""
    name: str                       # v2 시트 이름
    v1_name: str = ""               # v1 시트 이름 (다르면 적는다)
    cols: list[Col] = field(default_factory=list)
    v1_widths: tuple[int, ...] = () # v1 에서 받아들이는 열 수. 여기 없으면 **거부한다**
    time_series: bool = False       # 부하 시트처럼 뒤가 시각만큼 늘어나는가
    optional_sheet: bool = False    # 계통에 따라 없어도 되는 시트인가

    @property
    def source_name(self) -> str:
        return self.v1_name or self.name


def _c(name, unit="", v1=None, scale=KEEP, required=True, default=None, note="",
       v2_new=False):
    return Col(name, unit, v1, scale, required, default, note, v2_new)


# A1(탭·위상·션트 자동 조정)이 쓰는 열은 **전부 비워 두는 것이 기본**이다.
# 값을 하나도 안 넣으면 폭이 옛 폭(AC Line 13 · AC Bus 17)으로 줄어 엔진이 못 본 척한다
# — 그래서 이 열을 붙여도 **옛 계통의 답이 한 자리도 안 바뀐다**(2026-08-12 회귀로 확인).
def _a1(name, unit="", v1=None, note=""):
    return _c(name, unit, v1, required=False, note=note, v2_new=True)


# ─────────────────────────────────────────────── 시트 정의
SHEETS: list[Sheet] = [

    Sheet("Mode", cols=[
        _c("Mode", "", 1, note="0 혼합 / 1 AC 전용 / 2 DC 전용"),
    ], v1_widths=(1,)),

    Sheet("Base", v1_name="Sbase,frequency", cols=[
        _c("S_base", "MVA", 1),
        _c("freq_base", "Hz", 2),
        _c("f_0", "pu", 3),
        _c("freq_min", "pu", 4),
        _c("freq_max", "pu", 5),
        _c("Frequency Control Mode", "", 6, note="0 가변 / 1 고정"),
        _c("freq_deadband", "Hz", 7),
        # v1 8열 |V| deadband 는 안 읽히던 열 — 버린다(같은 항목이 AC Gen Data 에 있고 그쪽만 쓰인다)
    ], v1_widths=(7, 8)),

    Sheet("AC Bus Data", cols=[
        _c("Bus", "", 1),
        _c("Gs", "MW", 2),
        _c("Bs", "Mvar", 3),
        _c("Z_p", "", 4), _c("I_p", "", 5), _c("P_p", "", 6),
        _c("Z_q", "", 7), _c("I_q", "", 8), _c("P_q", "", 9),
        _c("k_pw", "", 10), _c("k_qw", "", 11),
        _c("V0", "pu", 12),
        _c("Va", "deg", 13),
        _c("V_base", "kV", 14, V_TO_KV),
        _c("V_min", "pu", 15),
        _c("V_max", "pu", 16),
        _c("Area", "", 17, required=False, default=1.0),
        # ── A1 ③스위치드 션트 · ④SVC (2026-08-12) — 움직이는 것은 위 `Bs`, 맞추는 것은 이 버스 전압
        _a1("Shunt Ctrl Mode", "", 18, note="0 끔 · 1 스위치드 션트(계단) · 2 SVC(연속)"),
        _a1("Shunt Target", "pu", 19, note="맞출 전압. 비우면 V0"),
        _a1("Shunt Bmin", "Mvar", 20, note="Bs 가 내려갈 수 있는 아래끝"),
        _a1("Shunt Bmax", "Mvar", 21, note="Bs 가 올라갈 수 있는 위끝"),
        _a1("Shunt Step Size", "Mvar", 22,
            note="한 단 크기. 0 이거나 비면 연속. 예: 10 → …-10 · 0 · 10 · 20…"),
    ], v1_widths=(17,)),

    Sheet("AC Line Data", cols=[
        _c("Line #", "", 1, required=False, note="사람이 줄을 세는 번호 — 계산에 안 쓰인다"),
        _c("From", "", 2), _c("To", "", 3),
        _c("R", "Ω", 4), _c("X", "Ω", 5), _c("B", "S", 6),
        _c("Tap ratio", "", 7),
        _c("Phase shift", "deg", 8),
        _c("rateA", "MVA", 9), _c("rateB", "MVA", 10), _c("rateC", "MVA", 11),
        _c("Is Transformer", "0/1", 12, default=0.0,
           note="끄는 스위치가 아니다 — 이 선로가 변압기인지 표시"),
        _c("Status", "0/1", 13, default=1.0, note="켜고 끄기"),
        # ── A1 ①탭 조정 · ②위상 조정기 (2026-08-12)
        # 한 선로에서 둘을 같이 하지 않으므로 **열 한 벌을 같이 쓴다** — 무엇을 움직이는지는
        # `Ctrl Mode` 가 정한다(그래서 이름에 `Tap` 을 안 넣었다. 모드 2 일 때 거짓말이 된다).
        _a1("Ctrl Mode", "", 14, note="0 끔 · 1 탭 조정(전압을 맞춤) · 2 위상 조정기(조류를 맞춤)"),
        _a1("Ctrl Bus", "", 15, note="보고 맞출 버스. 비우면 To"),
        _a1("Ctrl Target", "", 16, note="모드 1 = 전압 pu · 모드 2 = 유효조류 MW"),
        _a1("Ctrl Min", "", 17,
            note="아래끝. 모드 1 = 탭비 · 모드 2 = 위상 deg. 비우면 0.9"),
        _a1("Ctrl Max", "", 18,
            note="위끝. 단위는 Ctrl Min 과 같다. 비우면 1.1"),
        # 🚨 **개수가 아니라 「한 단 크기」다**(2026-08-14 사용자 확정). 실물 명세도
        #    도구들도 그렇게 적는다 — 실제 OLTC 는 "±16단 × 0.625%", pandapower 는
        #    `tap_step_percent`, PowerWorld 는 `Step Size`. 개수로 적게 하는 건
        #    PSS/E `NTP` 뿐이고 그것도 기본값 33 + 한계 0.9/1.1 이 정확히 0.625%
        #    로 떨어지게 맞춰 둔 조합이다. 크기로 두면 **한계를 바꿔도 설 자리가
        #    안 흔들린다**(개수로 두면 Max 를 줄이는 순간 간격이 통째로 바뀐다).
        _a1("Ctrl Step Size", "", 19,
            note="한 단 크기. 0 이거나 비면 연속. 모드 1 = 탭비(예 0.00625) · 모드 2 = 도(예 0.5)"),
    ], v1_widths=(12, 13)),

    Sheet("AC Gen Data", cols=[
        _c("Bus", "", 1),
        _c("AC Gen Type", "", 2),
        _c("AC Gen Mode", "", 3),
        _c("Droop (P-f)", "%", 4),
        _c("Droop (Q-Vac)", "%", 5),
        _c("P_gen", "MW", 6, W_TO_MW),
        _c("Q_gen", "Mvar", 7, W_TO_MW),
        _c("Vg", "pu", 8),
        _c("Status", "0/1", 9, default=1.0),
        _c("Local Sbase", "MVA", 10),
        _c("|V| deadband", "pu", 11, default=0.0),
        _c("Qmax", "Mvar", 12, W_TO_MW, required=False),
        _c("Qmin", "Mvar", 13, W_TO_MW, required=False),
        _c("Pmax", "MW", 14, W_TO_MW, required=False),
        _c("Pmin", "MW", 15, W_TO_MW, required=False),
        _c("Gen S_N", "MVA", 16, W_TO_MW, required=False),
    ], v1_widths=(10, 11, 13, 15, 16)),

    Sheet("AC 3w Transformer Data", optional_sheet=True, cols=[
        _c("3w trans #", "", 1, required=False),
        _c("Bus 1", "", 2), _c("Bus 2", "", 3), _c("Bus 3", "", 4),
        _c("Status", "0/1", 5, default=1.0),
        _c("Vn1", "kV", 6), _c("Vn2", "kV", 7), _c("Vn3", "kV", 8),
        _c("Sn1", "MVA", 9), _c("Sn2", "MVA", 10), _c("Sn3", "MVA", 11),
        _c("r12", "pu", 12), _c("r23", "pu", 13), _c("r31", "pu", 14),
        _c("x12", "pu", 15), _c("x23", "pu", 16), _c("x31", "pu", 17),
        _c("vk12", "%", 18), _c("vk23", "%", 19), _c("vk31", "%", 20),
        _c("vkr12", "%", 21), _c("vkr23", "%", 22), _c("vkr31", "%", 23),
        _c("tap side", "", 24), _c("tap ratio", "", 25),
        _c("shift_deg MV", "deg", 26), _c("shift_deg LV", "deg", 27),
        _c("pfe", "kW", 28, note="일부러 남긴 예외 — 철손은 kW 로 부르는 것이 관례"),
        _c("i0", "%", 29),
        _c("winding map", "", 30),
        # 2026-08-10 신설 — 권선마다 탭비를 따로 담는다. 24·25 열은 한 권선만 담아서
        # PSS/E 처럼 권선마다 WINDV 를 주는 파일에서 나머지 둘을 버렸다.
        # 비워 두면(또는 0) 그 권선은 탭 없음(=1). 세 칸이 다 비면 24·25 열을 쓴다.
        _c("tap ratio W1", "", 31, required=False),
        _c("tap ratio W2", "", 32, required=False),
        _c("tap ratio W3", "", 33, required=False),
    ], v1_widths=(30, 33)),

    Sheet("AC P Consume Data", time_series=True, cols=[
        _c("Bus / 시각", "MW", 1),
    ]),
    Sheet("AC Q Consume Data", time_series=True, cols=[
        _c("Bus / 시각", "Mvar", 1),
    ]),

    Sheet("DC Bus Data", optional_sheet=True, cols=[
        _c("Bus", "", 1),
        _c("Nominal Current", "?", 2, note="⚠️ v1 에 단위가 안 적혀 있다 — 확인 전까지 그대로 둔다"),
        _c("V0", "pu", 3),
        _c("V_base", "kV", 4, V_TO_KV),
        _c("VM min", "pu", 5),
        _c("VM max", "pu", 6),
    ], v1_widths=(6,)),

    Sheet("DC Line Data", optional_sheet=True, cols=[
        _c("Line #", "", 1, required=False),
        _c("From", "", 2), _c("To", "", 3),
        _c("R", "Ω", 4),
        _c("rateA", "MVA", 5), _c("rateB", "MVA", 6), _c("rateC", "MVA", 7),
        _c("Status", "0/1", 8, default=1.0),
    ], v1_widths=(4, 8)),

    Sheet("DC Gen Data", optional_sheet=True, cols=[
        _c("Bus", "", 1),
        _c("DC Gen Type", "", 2),
        _c("DC Gen Mode", "", 3),
        _c("Droop (P-Vdc)", "%", 4),
        _c("P_gen", "MW", 5, W_TO_MW),
        _c("Vg", "pu", 6),
        _c("Status", "0/1", 7, default=1.0,
           note="v1 에서는 정말로 안 읽혔다 — 읽는 쪽이 꺼진 줄을 빼서 되게 만든다"),
        _c("Local Sbase", "MVA", 8),
        _c("|V| deadband", "pu", 9, default=0.0),
        _c("Pmax", "MW", 10, W_TO_MW, required=False,
           note="코드는 이 자리를 읽는데 v1 파일엔 열이 없었다"),
        _c("Pmin", "MW", 11, W_TO_MW, required=False),
    ], v1_widths=(9,)),

    Sheet("DC P Consume Data", time_series=True, optional_sheet=True, cols=[
        _c("Bus / 시각", "MW", 1),
    ]),

    Sheet("ACDC IC Data", optional_sheet=True, cols=[
        _c("From (AC)", "", 1), _c("To (DC)", "", 2),
        _c("AC Control Mode", "", 3), _c("DC Control Mode", "", 4),
        _c("Droop (f-P)", "%", 5),
        _c("Droop (P-Vdc)", "%", 6),
        _c("Droop (Q-Vac)", "%", 7),
        _c("P Operating Point", "MW", 8, W_TO_MW),
        _c("Q Operating Point", "Mvar", 9, W_TO_MW),
        _c("rateA", "MVA", 10),
        _c("Rtf", "pu", 11), _c("Xtf", "pu", 12), _c("Bf", "pu", 13),
        _c("Rc", "pu", 14), _c("Xc", "pu", 15),
        _c("Status", "0/1", 16, default=1.0),
        _c("LossA", "", 17), _c("LossB", "", 18),
        _c("LossC rec", "", 19), _c("LossC inv", "", 20),
        _c("V_base", "kV", 21, required=False),
        _c("I_max", "kA", 22, required=False, note="없으면 전류 한계를 안 건다"),
    # 22 는 엔진이 실제로 읽는 모양이다 — `preprocess_IC_sub4.m:273` 이
    # `size(IC_dat,2) >= 22` 일 때 22열을 전류 한계로 쓴다. `ACDC_71bus_L2_ic15` 가 그것이다.
    ], v1_widths=(20, 21, 22)),

    Sheet("MVDC LVDC Converter Data", optional_sheet=True, cols=[
        _c("From (MVDC)", "", 1), _c("To (LVDC)", "", 2),
        # v1 3·4·5 = 효율곡선 C0·C1·C2 → 현행 솔버 v7 이 안 읽고 케이스 56개 전부 0 이라 버린다
        _c("Droop (MV)", "", 6),
        _c("Droop (LV)", "", 7),
        _c("Operating Point (P)", "MW", 8, W_TO_MW),
        _c("rateA", "MVA", 9),
        _c("Control Mode", "", 10),
        _c("Status", "0/1", None, default=1.0,
           note="v2 에서 새로 생긴 열 — v1 은 Control Mode 0 이 끄기여서 켤 때 원래 모드를 잃었다"),
    ], v1_widths=(10,)),
]

BY_NAME = {s.name: s for s in SHEETS}
BY_V1_NAME = {s.source_name: s for s in SHEETS}


# ─────────────────────────────────────────────── 읽어보기 시트에 넣을 글
VALUE_NOTES: list[tuple[str, str, str]] = [
    ("Mode", "Mode", "0 = AC/DC 혼합 · 1 = AC 전용 · 2 = DC 전용"),
    ("Base", "Frequency Control Mode", "0 = 가변 · 1 = 고정"),
    ("AC Gen Data", "AC Gen Type", "0 = 발전기 없음 · 1 = AC 변압 · 2 = 동기기 · 3 = IBR"),
    ("AC Gen Data", "AC Gen Mode",
     "0 = PQ · 1 = Droop · 2 = PV · 3 = Slack   (같은 버스는 같은 모드여야 한다)"),
    ("AC Gen Data", "Vg", "PV 또는 Droop 모드일 때만 쓰인다"),
    ("AC Gen Data", "Status", "0 = 끔 · 1 = 켬.  끄면 그 발전기는 PV/Slack 분류에서 빠진다"),
    ("AC Line Data", "Is Transformer", "0 = 보통 선로 · 1 = 변압기.  **끄는 스위치가 아니다**"),
    ("AC Line Data", "Status", "0 = 끔(선로 개방) · 1 = 켬"),
    ("AC Line Data", "Ctrl Mode",
     "탭·위상을 계산이 스스로 움직이게 한다.  0 = 끔(지금까지처럼 Tap ratio·Phase shift 를 "
     "그대로 쓴다) · 1 = 탭 조정(Ctrl Bus 의 전압을 Ctrl Target 으로) · "
     "2 = 위상 조정기(이 선로의 유효조류를 Ctrl Target 으로).  **비워 두면 아무 일도 안 한다**"),
    ("AC Line Data", "Ctrl Target",
     "맞출 값.  모드 1 = 전압 pu(예: 1.00) · 모드 2 = 유효조류 MW"),
    ("AC Line Data", "Ctrl Min",
     "움직일 수 있는 범위.  모드 1 = 탭비(예: 0.9~1.1) · 모드 2 = 위상 deg.  "
     "끝에 닿으면 그 값에 멈추고 목표는 포기한다(발전기가 무효 한계에 걸리는 것과 같다).  "
     "**비워 두면 0.9 ~ 1.1 로 잡고, 그렇게 잡았다고 「점검」 탭에 밝힌다**"),
    ("AC Bus Data", "Shunt Ctrl Mode",
     "이 버스의 Bs 를 계산이 스스로 움직이게 한다.  0 = 끔 · 1 = 스위치드 션트(Shunt Steps "
     "단으로 붙였다 뗐다) · 2 = SVC(연속).  **비워 두면 아무 일도 안 한다**"),
    ("AC Bus Data", "Shunt Bmin",
     "Bs 가 움직일 수 있는 범위 [Mvar].  Bmax 가 콘덴서 쪽(전압을 올린다)"),
    ("AC 3w Transformer Data", "tap side", "탭이 어느 권선에 달렸는지"),
    ("AC 3w Transformer Data", "winding map", "세 권선이 어느 버스에 붙는지"),
    ("DC Gen Data", "DC Gen Mode", "0 = P 고정 · 1 = Droop · 2 = CV"),
    ("DC Gen Data", "DC Gen Type", "0 = 없음 · 1 = IBR · 2 = ESS · 3 = 연료전지 · 4 = 발전기"),
    ("ACDC IC Data", "AC Control Mode", "0 = CQ · 1 = Droop · 2 = CV"),
    ("ACDC IC Data", "DC Control Mode", "0 = CP · 1 = Droop · 2 = CV"),
    ("ACDC IC Data", "Status", "0 = 끔 · 1 = 켬"),
    ("MVDC LVDC Converter Data", "Control Mode", "운전 방식.  **끄기는 Status 열로** 한다"),
    ("MVDC LVDC Converter Data", "Status", "0 = 끔 · 1 = 켬"),
    ("(전체)", "단위", "전력 = MW · Mvar · MVA / 전압 = kV / 임피던스 = Ω 또는 pu"),
    ("(전체)", "부하 시트", "첫 열이 버스 번호, 그다음부터 시각 1·2·3… 이다"),
]


def summary() -> str:
    """서식을 한눈에 — 자기 점검용."""
    out = []
    for s in SHEETS:
        tail = " (시각만큼 늘어남)" if s.time_series else ""
        opt = " · 계통에 따라 없어도 됨" if s.optional_sheet else ""
        src = f"  ← v1 '{s.v1_name}'" if s.v1_name else ""
        out.append(f"{s.name}: {len(s.cols)}열{tail}{opt}{src}")
        for i, c in enumerate(s.cols, 1):
            mark = "" if c.required else "  (선택)"
            frm = f"v1 {c.v1_col}열" if c.v1_col else "신설"
            sc = "" if c.scale == KEEP else f" ×{c.scale:g}"
            out.append(f"   {i:2d}. {c.header:<26} {frm}{sc}{mark}")
    return "\n".join(out)


if __name__ == "__main__":
    print(summary())
