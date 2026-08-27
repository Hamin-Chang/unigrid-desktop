# -*- coding: utf-8 -*-
"""AC 자동 조정 패널 — A1 조정 넷을 한자리에 모은다 (2026-08-27, §7 5단계).

⚠️ **AC 전용이다.** 넷 다 AC 표에 산다 — DC 선로·DC 발전기·IC·DC/DC 에는 조정 칸이
   아예 없다. 그래서 이름에 「AC」를 넣는다(2026-08-27 사용자 지적 — 안 넣으면
   「DC 것도 여기 있나」로 읽힌다).

왜 만드나
---------
A1 조정은 **넷**인데 **표 두 개에 갈려** 있다:

    AC 선로 표 14~19칸   Ctrl Mode 1 = 탭 조정   · 2 = 위상 조정
    AC 버스 표 18~22칸   Shunt Mode 1 = 스위치드(계단) · 2 = SVC(연속)

넷이 하는 일은 같다 — **목표를 정해 주면 계산이 값을 스스로 움직인다.** 다른 것은
움직이는 대상뿐이다(탭비·위상각·션트 용량). 그런데 표가 갈려 있어 표 고르기 줄에서
다섯 칸 떨어져 있고, **두 표 다 흰 칸이 화면 밖**이다(선로 19칸 중 14~19 · 버스 22칸 중 18~22).

게다가 조정이 걸리는 줄은 극히 적다 — 실측(2026-08-27): case24 는 **77줄 중 1줄**,
case118 은 **186줄 중 0줄**. 19칸짜리 표를 밀어 가며 채울 자리가 아니다.

⇒ 조정만 따로 패널로 뺀다. 표는 계통이 **무엇인지** 보여 주고, 패널은 계산에
   **무엇을 시킬지** 받는다. 결과는 점검 탭이 이미 같은 칸으로 보여 준다(둘이 짝).

어떻게 얹었나
-------------
값은 **표를 고치는 것과 똑같은 길**로 나간다 — `SC.Cell` 하나를 `win.changes` 에 얹는다.
그래서 [이 조건으로 계산]·시나리오·되돌리기·비교가 손대지 않고 그대로 돈다.
패널은 화면일 뿐이고 데이터 구조는 하나도 안 바뀐다.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)

import scenario as SC

KEY = "__ADJ__"          # 표 고르기 줄에서 이 패널을 가리키는 이름

# ── 조정 넷 ────────────────────────────────────────────────────────────
#   cols = (모드, 맞추는 곳, 목표, 최소, 최대, 한 단) — 없으면 None
LINE = "AC_Line_dat"
BUS = "AC_Bus_dat"
LINE_COLS = (13, 14, 15, 16, 17, 18)
BUS_COLS = (17, None, 18, 19, 20, 21)

KINDS = [
    # (표, 모드값, 이름, 목표 단위, 무엇이 움직이나, 지금 값 열, 범위 단위, 한 단)
    #   한 단: "" = 안 적으면 연속 · "필수" = 계단이라 있어야 한다 · None = 쓰면 안 된다
    (LINE, 1, "탭 조정",      "pu",  "탭비",     6, "",     ""),
    (LINE, 2, "위상 조정",    "MW",  "위상각",   7, "deg",  ""),
    (BUS,  1, "스위치드 션트", "pu",  "션트 용량", 2, "Mvar", "필수"),
    (BUS,  2, "SVC",         "pu",  "션트 용량", 2, "Mvar", None),
]


def _cols(table):
    return LINE_COLS if table == LINE else BUS_COLS


def kind_of(table, mode):
    """그 모드가 무엇인지 — 이름·목표 단위·움직이는 것·지금 값 열·범위 단위·한 단."""
    for t, m, name, unit, moves, cur, runit, step in KINDS:
        if t == table and m == mode:
            return name, unit, moves, cur, runit, step
    return f"모드 {mode:g}", "", "", None, "", ""


def _arr(win, table):
    """지금 화면이 보여 주는 값 — 원본 + 이미 푼 것 + 아직 안 푼 것."""
    a = SC._values(SC.apply(win.base_case, win.applied + win.changes), table)
    need = max(c for c in _cols(table) if c is not None) + 1
    if a.ndim == 2 and a.shape[1] < need:      # 옛 파일엔 조정 열이 아예 없다
        a = np.hstack([a, np.full((a.shape[0], need - a.shape[1]), np.nan)])
    return a


def rows_on(win, table):
    """그 표에서 조정이 걸린 줄 번호."""
    if win.base_case is None:
        return []
    a = _arr(win, table)
    if a.ndim != 2 or not a.size:
        return []
    m = a[:, _cols(table)[0]]
    return [int(i) for i in np.where(~np.isnan(m) & (m != 0))[0]]


def count(win):
    return len(rows_on(win, LINE)) + len(rows_on(win, BUS))


def _what(win, table, row):
    """무엇에 걸린 조정인지 — `선로 7 (103→124)` · `버스 106`."""
    a = SC._values(win.base_case, table)
    if table == BUS:
        return f"버스 {a[row, 0]:g}"
    return f"선로 {a[row, 0]:g} ({a[row, 1]:g}→{a[row, 2]:g})"


def _num(v, unit=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    s = f"{v:g}"
    return f"{s} {unit}".strip()


# ── 화면 ───────────────────────────────────────────────────────────────

def panel(win):
    """자동 조정 패널 하나를 그린다."""
    c = win.c
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(8)

    head = QHBoxLayout()
    t = QLabel("AC 자동 조정")
    t.setStyleSheet(f"color:{c['text']};font-size:15px;font-weight:600;")
    head.addWidget(t)
    s = QLabel("목표를 정해 주면 계산이 값을 스스로 움직입니다 — AC 변압기와 AC 버스 션트")
    s.setStyleSheet(f"color:{c['muted']};font-size:12px;")
    head.addWidget(s)
    head.addStretch(1)
    add = QPushButton("+ 조정 추가")
    add.setCursor(Qt.PointingHandCursor)
    add.clicked.connect(lambda: add_dialog(win))
    head.addWidget(add)
    v.addLayout(head)

    items = ([(LINE, r) for r in rows_on(win, LINE)]
             + [(BUS, r) for r in rows_on(win, BUS)])

    if not items:
        box = QLabel("걸린 조정이 없습니다.\n\n"
                     "[+ 조정 추가] 를 눌러 AC 변압기의 탭·위상, 또는\n"
                     "AC 버스의 션트를 걸 수 있습니다.\n"
                     "건 뒤 위의 [이 조건으로 계산] 을 눌러야 풉니다.\n\n"
                     "조정은 AC 에만 있습니다 — DC 쪽에는 이 칸이 없습니다.")
        box.setAlignment(Qt.AlignCenter)
        box.setStyleSheet(
            f"color:{c['muted']};font-size:13px;line-height:170%;"
            f"border:1px dashed {c['border']};border-radius:8px;padding:32px;")
        v.addWidget(box, 1)
        return w

    inner = QWidget()
    iv = QVBoxLayout(inner)
    iv.setContentsMargins(0, 0, 0, 0)
    iv.setSpacing(8)
    for table, row in items:
        iv.addWidget(_card(win, table, row))
    iv.addStretch(1)

    sa = QScrollArea()
    sa.setObjectName("adjlist")
    sa.setWidget(inner)
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    v.addWidget(sa, 1)
    return w


def _card(win, table, row):
    """조정 하나 — 한 줄짜리 칸."""
    c = win.c
    cols = _cols(table)
    a = _arr(win, table)
    mode = float(a[row, cols[0]])
    name, unit, moves, cur_col, runit, step_kind = kind_of(table, mode)
    ru = f" [{runit}]" if runit else ""

    card = QFrame()
    card.setObjectName("adjcard")
    card.setStyleSheet(
        f"#adjcard{{background:{c['surface']};border:1px solid {c['border']};"
        f"border-radius:8px;}}")
    h = QHBoxLayout(card)
    h.setContentsMargins(14, 10, 14, 10)
    h.setSpacing(16)

    def field(label, widget, wide=False):
        box = QWidget()
        bv = QVBoxLayout(box)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(3)
        lb = QLabel(label)
        lb.setStyleSheet(f"color:{c['muted']};font-size:11px;")
        bv.addWidget(lb)
        bv.addWidget(widget)
        if not wide:
            box.setMaximumWidth(150)
        h.addWidget(box)
        return box

    # 방식 — 바꾸면 모드가 바뀐다(같은 표 안에서만)
    kind = QComboBox()
    same = [k for k in KINDS if k[0] == table]
    for k in same:
        kind.addItem(k[2], k[1])
    kind.setCurrentIndex(max(0, [k[1] for k in same].index(mode)
                             if mode in [k[1] for k in same] else 0))
    kind.currentIndexChanged.connect(
        lambda _i, k=kind: win.adj_set(table, row, cols[0], float(k.currentData())))
    field("방식", kind)

    # 무엇을 — 못 고친다(지우고 다시 건다)
    what = QLabel(_what(win, table, row))
    what.setStyleSheet(f"color:{c['text']};font-size:13px;")
    field("무엇을", what)

    # 지금 값 — 표를 안 봐도 되게 옆에 적는다
    if cur_col is not None:
        base = SC._values(win.base_case, table)
        nowv = float(base[row, cur_col]) if cur_col < base.shape[1] else float("nan")
        nv = QLabel(_num(nowv))
        nv.setStyleSheet(f"color:{c['muted']};font-size:13px;")
        field(f"지금 {moves}", nv)

    # 맞추는 곳 — 위상 조정기는 안 쓴다(그 선로 자신의 조류를 본다)
    if cols[1] is not None:
        if table == LINE and mode == 2:
            lb = QLabel("이 선로 자신")
            lb.setStyleSheet(f"color:{c['muted']};font-size:13px;")
            field("맞추는 곳", lb)
        else:
            field("맞추는 곳", _edit(win, table, row, cols[1], a, "버스 번호"))
    else:
        lb = QLabel("이 버스")
        lb.setStyleSheet(f"color:{c['muted']};font-size:13px;")
        field("맞추는 곳", lb)

    field(f"목표 [{unit}]", _edit(win, table, row, cols[2], a))
    field(f"최소{ru}", _edit(win, table, row, cols[3], a, "자동"))
    field(f"최대{ru}", _edit(win, table, row, cols[4], a, "자동"))
    if step_kind is None:
        # 🚨 SVC 는 전력전자라 연속이다 — 한 단을 적으면 **엔진이 막는다**
        #    (`a1_parse_svc.m:52`). 칸을 열어 두면 적어 놓고 왜 막히는지 모른다.
        lb = QLabel("연속 — 쓰지 않음")
        lb.setStyleSheet(f"color:{c['muted']};font-size:13px;")
        field("한 단", lb)
    else:
        hint = "있어야 합니다" if step_kind == "필수" else "비우면 연속"
        field(f"한 단{ru}", _edit(win, table, row, cols[5], a, hint, zero_blank=True))

    h.addStretch(1)
    rm = QPushButton("지우기")
    rm.setCursor(Qt.PointingHandCursor)
    rm.setStyleSheet(f"border:none;background:transparent;color:{c['warn']};"
                     f"font-size:12px;")
    rm.clicked.connect(lambda: win.adj_remove(table, row))
    h.addWidget(rm)
    return card


def _edit(win, table, row, col, a, hint="", zero_blank=False):
    """숫자 한 칸. 비우면 「안 적음」(NaN) 이 된다.

    `zero_blank` — 한 단은 **0 도 「연속」이라는 뜻**이라 0 을 그대로 찍으면
    "한 단이 0" 으로 읽힌다. 빈 칸으로 두고 자리글씨가 뜻을 말하게 한다.
    """
    e = QLineEdit()
    val = float(a[row, col])
    blank = np.isnan(val) or (zero_blank and val == 0)
    e.setText("" if blank else f"{val:g}")
    e.setPlaceholderText(hint)
    e.setMaximumWidth(150)
    e.setAlignment(Qt.AlignRight)
    e.editingFinished.connect(
        lambda w=e: win.adj_typed(table, row, col, w.text()))
    return e


# ── 새로 걸기 ──────────────────────────────────────────────────────────

def add_dialog(win):
    c = win.c
    d = QDialog(win)
    d.setWindowTitle("AC 조정 추가")
    d.setStyleSheet(win.styleSheet())
    d.setMinimumWidth(360)
    v = QVBoxLayout(d)
    v.setContentsMargins(20, 18, 20, 18)
    v.setSpacing(12)
    info = QLabel("AC 계통의 무엇에 어떤 조정을 걸까요?")
    info.setStyleSheet(f"color:{c['muted']};font-size:13px;")
    v.addWidget(info)

    form = QFormLayout()
    kind = QComboBox()
    for k in KINDS:
        kind.addItem(f"{k[2]} — {k[4]} 를 움직인다", (k[0], k[1]))
    target = QComboBox()

    def refill():
        table, mode = kind.currentData()
        target.clear()
        base = SC._values(win.base_case, table)
        on = set(rows_on(win, table))
        for r in range(base.shape[0]):
            if r in on:
                continue                      # 이미 걸린 것은 안 보여 준다
            if table == LINE and mode in (1, 2) and base.shape[1] > 11 \
                    and base[r, 11] != 1:
                continue                      # 탭·위상은 변압기에만 단다
            target.addItem(_what(win, table, r), r)

    kind.currentIndexChanged.connect(lambda _i: refill())
    refill()
    form.addRow("방식", kind)
    form.addRow("무엇에", target)
    v.addLayout(form)

    note = QLabel("건 뒤 목표와 범위를 채우고, 위의 [이 조건으로 계산] 을 누르세요.")
    note.setStyleSheet(f"color:{c['muted']};font-size:12px;")
    v.addWidget(note)

    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    v.addWidget(bb)

    if d.exec() != QDialog.Accepted:
        return
    if target.currentData() is None:
        return
    table, mode = kind.currentData()
    win.adj_set(table, int(target.currentData()), _cols(table)[0], float(mode))
