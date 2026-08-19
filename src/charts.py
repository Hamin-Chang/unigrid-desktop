"""charts.py — 실제 그래프 그리기 (QtCharts).

matplotlib 대신 Qt 가 들고 있는 QtCharts 를 쓴다. 이유:
  · 이미 깔려 있다 (PySide6_Addons) → 윈도우 설치본에 얹을 짐이 안 늘어난다
  · Qt 위젯이라 창 색·글꼴이 앱과 그대로 맞는다
  · 축·눈금·범례를 알아서 그려 준다

그리는 내용은 MATLAB 앱의 ACDC_snapshotgraph.m 을 따른다.
다만 거기서 y축 두 개(전압·위상각)를 겹쳐 그리던 것을, 이 앱에서는
**위아래 두 그래프로 나눈다**(그렇게 하기로 정함).
"""
from __future__ import annotations

from math import ceil

import numpy as np
from PySide6.QtCharts import (QChart, QChartView, QLineSeries, QScatterSeries,
                              QValueAxis, QCategoryAxis, QBarSet, QBarSeries,
                              QStackedBarSeries, QBarCategoryAxis)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (QFrame, QSizePolicy, QToolTip,
                               QVBoxLayout, QLabel)

# MATLAB 그림에서 쓰던 색을 그대로 (빨강=AC, 파랑=DC, 초록=위상각)
AC_RED = "#d1342f"
DC_BLUE = "#1f6fd0"
ANGLE_GREEN = "#1f9d55"
LIMIT_GRAY = "#8a94a3"

MAX_TICKS = 25          # 버스가 많으면 x축 글자를 솎는다 (MATLAB 과 동일)


# ─────────────────────────────────────────── 공통 틀
def _new_chart(c, title):
    ch = QChart()
    ch.setTitle(title)
    ch.setBackgroundVisible(False)
    # ⚠️ setMargins 를 좁히지 말 것 — 이 여백이 곧 "축 글자가 그려지는 자리"라서
    #    좁히면 눈금 글자가 전부 "..." 로 줄어든다. 기본값을 그대로 쓴다.
    ch.setTitleBrush(QColor(c["text"]))
    f = QFont()
    f.setPointSize(11)
    f.setBold(True)
    ch.setTitleFont(f)
    # 범례는 오른쪽에 세로로 — 위에 깔면 가뜩이나 낮은 그래프의 한 줄을 더 먹는다
    ch.legend().setAlignment(Qt.AlignRight)
    ch.legend().setLabelColor(QColor(c["muted"]))
    lf = QFont()
    lf.setPointSize(9)
    ch.legend().setFont(lf)
    ch.setAnimationOptions(QChart.NoAnimation)   # 다시 그릴 때 튀지 않게
    return ch


def _view(ch, c):
    v = QChartView(ch)
    v.setRenderHint(QPainter.Antialiasing)
    v.setStyleSheet(f"background:{c['plot']};border:1px solid {c['border']};"
                    f"border-radius:9px;")
    v.setMinimumHeight(150)
    return v


def _style_axis(ax, c, title=""):
    ax.setTitleText(title)
    ax.setTitleBrush(QColor(c["muted"]))
    ax.setLabelsColor(QColor(c["muted"]))
    ax.setLinePenColor(QColor(c["border"]))
    ax.setGridLineColor(QColor(c["border"]))
    f = QFont()
    f.setPointSize(9)
    ax.setLabelsFont(f)
    tf = QFont()
    tf.setPointSize(10)
    ax.setTitleFont(tf)
    return ax


def _bus_axis(c, labels):
    """x축 — 버스 번호를 눈금 글자로. 버스가 많으면 솎아서 겹치지 않게."""
    ax = QCategoryAxis()
    ax.setLabelsPosition(QCategoryAxis.AxisLabelsPositionOnValue)
    n = len(labels)
    step = max(1, -(-n // MAX_TICKS))       # 올림 나눗셈
    for i in range(0, n, step):
        ax.append(labels[i], i + 1)
    ax.setRange(0.5, n + 0.5)
    ax.setStartValue(0.5)
    # ⚠️ x축에 제목("버스")을 달지 말 것 — 그래프가 낮으면 QtCharts 가 제목에
    #    자리를 내주느라 눈금 글자를 전부 "..." 로 줄여 버린다(실제로 겪음).
    #    어차피 x축이 버스라는 건 그래프 제목과 탭 이름이 말해 준다.
    return _style_axis(ax, c)


def _line(pts, color, width=1.6, dashed=False, name=""):
    s = QLineSeries()
    s.setName(name)
    for x, y in pts:
        s.append(float(x), float(y))
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    if dashed:
        pen.setStyle(Qt.DashLine)
    s.setPen(pen)
    return s


def _dots(pts, color, name, size=8.0):
    s = QScatterSeries()
    s.setName(name)
    s.setMarkerSize(size)
    s.setColor(QColor(color))
    s.setBorderColor(QColor(color))
    for x, y in pts:
        s.append(float(x), float(y))
    return s


def _hide_from_legend(ch, series):
    for m in ch.legend().markers(series):
        m.setVisible(False)


# ─────────────────────────────────────────── 버스 값 모으기
def _bus_table(sol, t):
    """AC 다음 DC 순서로 [버스이름, 전압, Vmin, Vmax] 를 모은다.

    MATLAB 쪽(ACDC_snapshotgraph.m 20~26줄)과 같은 순서·같은 이름표.
    """
    names, vm, vmin, vmax, kind = [], [], [], [], []
    ac = sol.at("AC", t)
    if ac.size:
        cols = sol.cols("AC")
        i_v, i_lo, i_hi = (cols.index("VM[pu]"), cols.index("Vmin[pu]"),
                           cols.index("Vmax[pu]"))
        for r in ac:
            names.append(f"{int(r[0])}")
            vm.append(r[i_v]); vmin.append(r[i_lo]); vmax.append(r[i_hi])
            kind.append("AC")
    dc = sol.at("DC", t)
    if dc.size:
        cols = sol.cols("DC")
        i_v, i_lo, i_hi = (cols.index("VM[pu]"), cols.index("Vmin[pu]"),
                           cols.index("Vmax[pu]"))
        for r in dc:
            names.append(f"DC{int(r[0])}")
            vm.append(r[i_v]); vmin.append(r[i_lo]); vmax.append(r[i_hi])
            kind.append("DC")
    return names, np.array(vm), np.array(vmin), np.array(vmax), kind


# ─────────────────────────────────────────── 전압
def voltage_chart(c, sol, t):
    names, vm, vmin, vmax, kind = _bus_table(sol, t)
    if not names:
        return None
    n = len(names)
    x = np.arange(1, n + 1)

    ch = _new_chart(c, "전압  [pu]")
    # 전체를 잇는 검은 선 (범례에서는 감춘다 — MATLAB 도 같음)
    body = _line(zip(x, vm), c["text"], 1.4)
    ch.addSeries(body)
    lo = _line(zip(x, vmin), LIMIT_GRAY, 1.0, dashed=True, name="한계")
    hi = _line(zip(x, vmax), LIMIT_GRAY, 1.0, dashed=True)
    ch.addSeries(lo); ch.addSeries(hi)

    acp = [(x[i], vm[i]) for i in range(n) if kind[i] == "AC"]
    dcp = [(x[i], vm[i]) for i in range(n) if kind[i] == "DC"]
    dots = []
    if acp:
        d = _dots(acp, AC_RED, "AC 전압"); ch.addSeries(d); dots.append(d)
    if dcp:
        d = _dots(dcp, DC_BLUE, "DC 전압"); ch.addSeries(d); dots.append(d)

    ax = _bus_axis(c, names)
    # y축 제목은 안 넣는다 — 그래프 제목이 이미 "전압 [pu]" 라 겹치고,
    # 세로로 세운 글자가 좁은 그래프에서 잘린다.
    ay = _style_axis(QValueAxis(), c)
    ay.setLabelFormat("%.3f")
    ay.setTickCount(6)
    top = max(float(vmax.max()), float(vm.max())) + 0.01
    bot = min(float(vmin.min()), float(vm.min())) - 0.01
    ay.setRange(bot, top)

    ch.addAxis(ax, Qt.AlignBottom)
    ch.addAxis(ay, Qt.AlignLeft)
    for s in [body, lo, hi] + dots:
        s.attachAxis(ax); s.attachAxis(ay)
    _hide_from_legend(ch, body)
    _hide_from_legend(ch, hi)
    return _view(ch, c)


# ─────────────────────────────────────────── 위상각
def angle_chart(c, sol, t):
    """위상각은 AC 버스만 (DC 에는 위상이 없다)."""
    ac = sol.at("AC", t)
    if not ac.size:
        return None
    cols = sol.cols("AC")
    ang = ac[:, cols.index("Angle[deg]")]
    names_all, _, _, _, _ = _bus_table(sol, t)
    names = [f"{int(r[0])}" for r in ac]
    x = np.arange(1, len(names) + 1)

    ch = _new_chart(c, "위상각  [deg]")
    ln = _line(zip(x, ang), ANGLE_GREEN, 1.4, dashed=True)
    ch.addSeries(ln)
    dt = _dots(list(zip(x, ang)), ANGLE_GREEN, "위상각")
    ch.addSeries(dt)

    ax = _bus_axis(c, names)
    ay = _style_axis(QValueAxis(), c)
    ay.setLabelFormat("%.1f")
    ay.setTickCount(6)
    lo, hi = float(np.min(ang)), float(np.max(ang))
    pad = max(0.5, (hi - lo) * 0.12)
    ay.setRange(lo - pad, hi + pad)

    ch.addAxis(ax, Qt.AlignBottom)
    ch.addAxis(ay, Qt.AlignLeft)
    ln.attachAxis(ax); ln.attachAxis(ay)
    dt.attachAxis(ax); dt.attachAxis(ay)
    # 선이 하나뿐이라 범례가 제목("위상각 [deg]")을 되풀이할 뿐 → 안 띄운다
    ch.legend().setVisible(False)
    return _view(ch, c)


# ─────────────────────────────────────────── 선로 조류 (출발버스 × 도착버스)
def flow_matrix(sol, t, which):
    """MATLAB ACDC_snapshotgraph.m 92~143줄과 같은 행렬을 만든다.

    (출발 i, 도착 j) 칸 = 그 선로의 출발쪽 전력, (j, i) 칸 = 도착쪽 전력.
    부호가 반대로 들어가므로 행렬은 대각선 기준으로 거의 대칭·역부호가 되고,
    그래서 색으로 그리면 **어느 쪽으로 흐르는지**가 그대로 보인다.

    which : "P" 또는 "Q"
    돌려주는 것 : (행렬, 값이 있는 칸 표시, 버스이름)
    """
    ac = sol.at("AC", t)
    dc = sol.at("DC", t)
    ac_num = [int(v) for v in ac[:, 0]] if ac.size else []
    dc_num = [int(v) for v in dc[:, 0]] if dc.size else []
    names = [str(b) for b in ac_num] + [f"DC{b}" for b in dc_num]
    n = len(names)
    if n == 0:
        return None, None, []

    # 버스번호 → 행렬에서의 자리. AC 를 먼저, DC 를 뒤에 붙인다.
    # (확인함: CIGRE·71bus·12bus·matacdc5·case24·울산 6개 케이스 모두
    #  AC 버스번호와 DC 버스번호가 겹치지 않는다 → 번호만으로 찾아도 안전)
    where = {}
    for i, b in enumerate(ac_num):
        where[("AC", b)] = i
    for i, b in enumerate(dc_num):
        where[("DC", b)] = len(ac_num) + i
    ac_set, dc_set = set(ac_num), set(dc_num)

    def slot(b):
        if b in ac_set:
            return where[("AC", b)]
        if b in dc_set:
            return where[("DC", b)]
        return None

    br = sol.at("Branch", t)
    if not br.size:
        return None, None, names
    cols = sol.cols("Branch")
    cf = cols.index("From_P[MW]" if which == "P" else "From_Q[MVAR]")
    ct = cols.index("To_P[MW]" if which == "P" else "To_Q[MVAR]")

    mat = np.zeros((n, n))
    used = np.zeros((n, n), dtype=bool)
    for row in br:
        i, j = slot(int(row[0])), slot(int(row[1]))
        if i is None or j is None or i == j:
            continue
        mat[i, j] += row[cf]
        mat[j, i] += row[ct]
        used[i, j] = used[j, i] = True
    np.fill_diagonal(mat, 0.0)
    np.fill_diagonal(used, False)
    return mat, used, names


def _diverging(v, vmax, c):
    """0 을 가운데 둔 색 — 음수는 파랑, 양수는 빨강. 전력의 방향이 보이게."""
    if vmax <= 0:
        return QColor(c["plot"])
    f = max(-1.0, min(1.0, float(v) / vmax))
    a = abs(f)
    # 아주 작은 값도 눈에 보이게 최소 진하기를 준다
    a = 0.18 + 0.82 * (a ** 0.6)
    if f >= 0:
        r, g, b = 200, 62, 47          # 빨강
    else:
        r, g, b = 31, 111, 208         # 파랑
    return QColor(int(255 - (255 - r) * a),
                  int(255 - (255 - g) * a),
                  int(255 - (255 - b) * a))


class FlowHeatmap(QFrame):
    """선로 조류를 '출발버스 × 도착버스' 색 격자로 그린다.

    3D 막대 대신 이걸 쓰는 이유: 이 행렬은 거의 다 비어 있다
    (CIGRE 25버스 = 625칸 중 50칸만 값이 있음 · 71버스는 2.7%).
    3D 로 세우면 빈 바닥이 화면의 90% 넘게 차지하고 앞 막대가 뒤를 가린다.
    """

    PAD_L, PAD_T, PAD_R, PAD_B = 52, 44, 74, 26

    def __init__(self, title, mat, used, names, unit, c):
        super().__init__()
        self.setObjectName("plot")
        self.title, self.mat, self.used, self.names = title, mat, used, names
        self.unit, self.c = unit, c
        self.vmax = float(np.abs(mat).max()) if mat is not None and mat.size else 0.0
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(180)
        self.setMouseTracking(True)      # 칸에 마우스를 올리면 값을 띄우려고
        self._cell = None

    # ── 격자 자리 계산 ──
    def _geom(self):
        n = len(self.names)
        w = self.width() - self.PAD_L - self.PAD_R
        h = self.height() - self.PAD_T - self.PAD_B
        if n == 0 or w <= 0 or h <= 0:
            return None
        cell = max(2.0, min(w / n, h / n))          # 칸은 정사각
        x0 = self.PAD_L + (w - cell * n) / 2.0
        y0 = self.PAD_T + (h - cell * n) / 2.0
        return x0, y0, cell, n

    def paintEvent(self, ev):
        c = self.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.fillRect(self.rect(), QColor(c["plot"]))

        # 제목
        p.setPen(QColor(c["text"]))
        f = QFont(); f.setPointSize(11); f.setBold(True)
        p.setFont(f)
        p.drawText(0, 6, self.width(), 22, Qt.AlignHCenter | Qt.AlignVCenter,
                   self.title)

        g = self._geom()
        if g is None or self.mat is None:
            p.end(); return
        x0, y0, cell, n = g

        # 칸 채우기
        for i in range(n):
            for j in range(n):
                rx, ry = x0 + j * cell, y0 + i * cell
                if not self.used[i, j]:
                    continue                       # 선로가 없는 칸은 비워 둔다
                p.fillRect(int(rx), int(ry), int(cell) + 1, int(cell) + 1,
                           _diverging(self.mat[i, j], self.vmax, c))

        # 격자선 (칸이 넉넉할 때만 — 좁으면 선이 칸을 덮는다)
        p.setPen(QPen(QColor(c["border"]), 1))
        if cell >= 9:
            for k in range(n + 1):
                p.drawLine(int(x0), int(y0 + k * cell),
                           int(x0 + n * cell), int(y0 + k * cell))
                p.drawLine(int(x0 + k * cell), int(y0),
                           int(x0 + k * cell), int(y0 + n * cell))
        else:
            p.drawRect(int(x0), int(y0), int(n * cell), int(n * cell))

        # 버스 이름 — 글자가 겹치지 않을 만큼만 솎는다.
        # 가로는 글자 '폭', 세로는 글자 '높이' 기준이라 솎는 간격이 서로 다르다.
        f2 = QFont(); f2.setPointSize(8); p.setFont(f2)
        fm = QFontMetrics(f2)
        p.setPen(QColor(c["muted"]))
        wmax = max(fm.horizontalAdvance(s) for s in self.names)
        step_x = max(1, int(ceil((wmax + 7) / cell)))
        step_y = max(1, int(ceil((fm.height() + 2) / cell)))

        for k in range(0, n, step_y):                 # 왼쪽 (출발 버스)
            yy = y0 + k * cell + cell / 2
            p.drawText(0, int(yy - 7), self.PAD_L - 6, 14,
                       Qt.AlignRight | Qt.AlignVCenter, self.names[k])
        for k in range(0, n, step_x):                 # 위 (도착 버스) — 눕혀서
            xx = x0 + k * cell + cell / 2
            p.drawText(int(xx - wmax / 2 - 3), int(y0 - 17), int(wmax + 6), 14,
                       Qt.AlignHCenter | Qt.AlignVCenter, self.names[k])

        # 축이 뭔지 한 줄로
        p.setPen(QColor(c["muted"]))
        p.drawText(int(x0), int(y0 + n * cell + 4), int(n * cell), 18,
                   Qt.AlignHCenter | Qt.AlignTop, "가로 = 도착 버스 · 세로 = 출발 버스")

        self._draw_scale(p, y0, n * cell)
        p.end()

    def _draw_scale(self, p, y0, gh):
        """오른쪽 색 눈금 — 위가 +(내보냄), 아래가 −(받음)."""
        c = self.c
        bx = self.width() - self.PAD_R + 12
        bw, bh = 13, max(40.0, gh)
        for k in range(int(bh)):
            v = self.vmax * (1 - 2.0 * k / bh)
            p.fillRect(bx, int(y0 + k), bw, 1, _diverging(v, self.vmax, c))
        p.setPen(QPen(QColor(c["border"]), 1))
        p.drawRect(bx, int(y0), bw, int(bh))
        f = QFont(); f.setPointSize(8); p.setFont(f)
        p.setPen(QColor(c["muted"]))
        for frac, val in ((0.0, self.vmax), (0.5, 0.0), (1.0, -self.vmax)):
            p.drawText(bx + bw + 3, int(y0 + bh * frac) - 7, 46, 14,
                       Qt.AlignLeft | Qt.AlignVCenter, f"{val:+.2g}")
        p.drawText(bx - 4, int(y0 + bh) + 4, 60, 14,
                   Qt.AlignLeft | Qt.AlignTop, self.unit)

    # ── 마우스를 올리면 정확한 값 ──
    def mouseMoveEvent(self, ev):
        g = self._geom()
        if g is None or self.mat is None:
            return
        x0, y0, cell, n = g
        j = int((ev.position().x() - x0) // cell)
        i = int((ev.position().y() - y0) // cell)
        if 0 <= i < n and 0 <= j < n and self.used[i, j]:
            QToolTip.showText(ev.globalPosition().toPoint(),
                              f"{self.names[i]} → {self.names[j]}\n"
                              f"{self.mat[i, j]:+.4g} {self.unit}", self)
        else:
            QToolTip.hideText()


def flow_chart(c, sol, t, which, title, unit):
    mat, used, names = flow_matrix(sol, t, which)
    if mat is None:
        return None
    return FlowHeatmap(title, mat, used, names, unit, c)


# ─────────────────────────────────────────── 한 버스의 시간 변화 (다이나믹)
class NoData(QFrame):
    """그릴 게 없을 때 이유를 적어 두는 자리 (빈 상자로 두지 않는다)."""

    def __init__(self, title, why, c):
        super().__init__()
        self.setObjectName("plot")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(150)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        t = QLabel(title)
        t.setAlignment(Qt.AlignHCenter)
        t.setStyleSheet(f"color:{c['text']};font-size:14px;font-weight:700;")
        v.addWidget(t)
        v.addStretch()
        m = QLabel(why)
        m.setAlignment(Qt.AlignCenter)
        m.setWordWrap(True)
        m.setStyleSheet(f"color:{c['muted']};font-size:14px;")
        v.addWidget(m)
        v.addStretch()


def _pick_bus(sol, bus_row):
    """다이나믹에서 고른 버스가 AC 몇 번째 줄인지 / DC 몇 번째 줄인지.

    옆 목록이 AC 를 먼저, DC 를 뒤에 붙여 만들어지므로 그 순서를 되짚는다.
    """
    nac = sol.AC.shape[0] if sol.AC.size else 0
    if bus_row < nac:
        return "AC", bus_row
    return "DC", bus_row - nac


def voltage_series(c, sol, bus_row):
    """고른 버스 하나의 전압이 시간에 따라 어떻게 변하는지.

    MATLAB ACDC_dynamicgraph.m 10~43줄과 같다 — AC 는 빨강, DC 는 파랑,
    그 버스의 상·하한을 가로 점선으로 깐다(한계는 시간에 안 변한다).
    """
    kind, row = _pick_bus(sol, bus_row)
    arr = sol.AC if kind == "AC" else sol.DC
    if arr.size == 0 or row >= arr.shape[0]:
        return None
    cols = sol.cols(kind)
    v = np.asarray(sol.series(kind, cols.index("VM[pu]"), row), dtype=float)
    if v.size == 0:
        return None
    lo = float(arr[row, cols.index("Vmin[pu]"), 0])
    hi = float(arr[row, cols.index("Vmax[pu]"), 0])
    bus = int(arr[row, 0, 0])
    label = f"{kind} {bus}"
    color = AC_RED if kind == "AC" else DC_BLUE
    x = np.arange(1, v.size + 1)

    ch = _new_chart(c, f"전압  [pu]   ·   {label}")
    ln = _line(zip(x, v), color, 1.6, name=f"{label} 전압")
    ch.addSeries(ln)
    dt = _dots(list(zip(x, v)), color, f"{label} 전압", size=7.0)
    ch.addSeries(dt)
    xa, xb = float(x[0]), float(x[-1]) if x.size > 1 else float(x[0]) + 1
    top = _line([(xa, hi), (xb, hi)], LIMIT_GRAY, 1.0, dashed=True, name="한계")
    bot = _line([(xa, lo), (xb, lo)], LIMIT_GRAY, 1.0, dashed=True)
    ch.addSeries(top); ch.addSeries(bot)

    ax = _style_axis(QValueAxis(), c)
    ax.setLabelFormat("%d")
    ax.setRange(xa, xb)
    ax.setTickCount(min(12, max(2, v.size)))
    ay = _style_axis(QValueAxis(), c)
    ay.setLabelFormat("%.3f")
    ay.setTickCount(6)
    ay.setRange(min(lo, float(v.min())) - 0.02, max(hi, float(v.max())) + 0.02)

    ch.addAxis(ax, Qt.AlignBottom); ch.addAxis(ay, Qt.AlignLeft)
    for s in (ln, dt, top, bot):
        s.attachAxis(ax); s.attachAxis(ay)
    _hide_from_legend(ch, ln)      # 선과 점이 같은 것
    _hide_from_legend(ch, bot)     # 상·하한은 범례에 한 번만
    return _view(ch, c)


def angle_series(c, sol, bus_row):
    """고른 버스의 위상각 시간 변화 — DC 버스에는 위상각이 없다."""
    kind, row = _pick_bus(sol, bus_row)
    if kind == "DC":
        dc = sol.DC
        bus = int(dc[row, 0, 0]) if dc.size and row < dc.shape[0] else "?"
        return NoData("위상각  [deg]",
                      f"DC {bus} 버스에는 위상각이 없습니다.\n"
                      "위상각은 AC 버스에서만 정의됩니다.", c)
    ac = sol.AC
    if ac.size == 0 or row >= ac.shape[0]:
        return None
    cols = sol.cols("AC")
    a = np.asarray(sol.series("AC", cols.index("Angle[deg]"), row), dtype=float)
    if a.size == 0:
        return None
    bus = int(ac[row, 0, 0])
    x = np.arange(1, a.size + 1)

    ch = _new_chart(c, f"위상각  [deg]   ·   AC {bus}")
    ln = _line(zip(x, a), ANGLE_GREEN, 1.6, dashed=True)
    ch.addSeries(ln)
    dt = _dots(list(zip(x, a)), ANGLE_GREEN, "위상각", size=7.0)
    ch.addSeries(dt)

    ax = _style_axis(QValueAxis(), c)
    ax.setLabelFormat("%d")
    ax.setRange(float(x[0]), float(x[-1]) if x.size > 1 else float(x[0]) + 1)
    ax.setTickCount(min(12, max(2, a.size)))
    ay = _style_axis(QValueAxis(), c)
    ay.setLabelFormat("%.2f")
    ay.setTickCount(6)
    lo, hi = float(a.min()), float(a.max())
    pad = max(0.05, (hi - lo) * 0.15)
    ay.setRange(lo - pad, hi + pad)

    ch.addAxis(ax, Qt.AlignBottom); ch.addAxis(ay, Qt.AlignLeft)
    ln.attachAxis(ax); ln.attachAxis(ay)
    dt.attachAxis(ax); dt.attachAxis(ay)
    ch.legend().setVisible(False)
    return _view(ch, c)


# ─────────────────────────────────────────── 주파수 (x축 = 시간)
def freq_chart(c, sol):
    """계통 주파수의 시간 변화.

    MATLAB ACDC_snapshotgraph.m 77~88줄과 같다 — 값을 선+점으로 그리고,
    기준 주파수를 검은 점선으로 깐다. 기준은 케이스마다 다르다(60/50 Hz).
    """
    fr = np.asarray(sol.freq, dtype=float).ravel()
    if fr.size == 0:
        return None
    x = np.arange(1, fr.size + 1)
    nom = float(sol.freq_nominal)

    ch = _new_chart(c, "주파수  [Hz]")
    ln = _line(zip(x, fr), AC_RED, 1.6, name="주파수")
    ch.addSeries(ln)
    dt = _dots(list(zip(x, fr)), AC_RED, "주파수", size=7.0)
    ch.addSeries(dt)
    base = _line([(x[0], nom), (x[-1], nom)], c["text"], 1.4, dashed=True,
                 name=f"기준 {nom:g} Hz")
    ch.addSeries(base)

    ax = _style_axis(QValueAxis(), c)
    ax.setLabelFormat("%d")
    ax.setRange(float(x[0]), float(x[-1]) if x.size > 1 else float(x[0]) + 1)
    ax.setTickCount(min(12, max(2, fr.size)))
    ay = _style_axis(QValueAxis(), c)
    ay.setLabelFormat("%.3f")
    ay.setTickCount(6)
    # 기준선이 항상 보이도록 값 범위와 기준을 함께 감싼다
    lo = min(float(fr.min()), nom)
    hi = max(float(fr.max()), nom)
    pad = max((hi - lo) * 0.15, 0.02)
    ay.setRange(lo - pad, hi + pad)

    ch.addAxis(ax, Qt.AlignBottom)
    ch.addAxis(ay, Qt.AlignLeft)
    for s in (ln, dt, base):
        s.attachAxis(ax); s.attachAxis(ay)
    _hide_from_legend(ch, ln)      # 선과 점이 같은 것이라 범례엔 한 번만
    return _view(ch, c)


# ─────────────────────────────────────────── 선로 부하율
def line_names(br):
    """선로 이름 — MATLAB functions/make_line_names.m 과 같은 규칙.

    "line 3-7" 꼴, 같은 이름이 또 나오면 " #2" 를 붙인다(병렬 선로).
    """
    seen, out = {}, []
    for r in br:
        base = f"line {int(r[0])}-{int(r[1])}"
        seen[base] = seen.get(base, 0) + 1
        out.append(base if seen[base] == 1 else f"{base} #{seen[base]}")
    return out


def loading_chart(c, sol, t):
    """선로별 부하율 막대 (MATLAB ACDC_snapshotgraph.m 191~204줄).

    100% 를 넘는 선로는 주황으로 칠하고 100% 자리에 점선을 그어,
    어느 선로가 용량을 넘겼는지 색만 보고도 알게 한다.
    """
    br = sol.at("Branch", t)
    if not br.size:
        return None
    cols = sol.cols("Branch")
    if "Loading[%]" not in cols:
        return None
    load = np.asarray(br[:, cols.index("Loading[%]")], dtype=float)
    # 🚨 **정격이 안 적힌 선로는 부하율이 `inf` 다** (2026-08-18).
    #    MATPOWER 관례로 `rateA = 0` 은 「무제한」인데 엔진이 그 0 으로 나눈다.
    #    그대로 두면 아래 `load.max()` 가 `inf` 가 되어 세로축이 `[0 ~ inf]` 로 잡히고
    #    (Qt 로그: *Attempting to set invalid range for value axis*) **막대가 안 보인다.**
    #    ⇒ **잴 수 있는 선로**(부하율이 유한하고 용량이 0 보다 큼)만 값으로 쓰고
    #      나머지는 0 으로 눕힌다.
    measurable = np.isfinite(load)
    if "Capacity[MVA]" in cols:
        cap = np.asarray(br[:, cols.index("Capacity[MVA]")], dtype=float)
        measurable &= cap > 0
    # 꺼진 선로는 **「못 잰 것」이 아니다** — 조류가 0 이라 부하율을 볼 일이 없다.
    # 세는 데서만 빼고(안내 수가 부풀지 않게) 그리는 값은 0 그대로다.
    # ⚠️ 한때 이 줄을 `measurable |= (st == 0)` 으로 써서 **꺼진 선로를 「잴 수 있음」으로
    #    쳤다.** 그러면 case33_matpower(못 잼 32 + 꺼짐 5)에서 `measurable.any()` 가 참이
    #    되어 아래 안내가 안 뜨고 **빈 그래프**가 그대로 나간다.
    off = (np.asarray(br[:, cols.index("Status")], dtype=float) == 0
           if "Status" in cols else np.zeros(len(load), dtype=bool))
    n_bad = int((~measurable & ~off).sum())
    # ⚠️ **하나도 못 재면 빈 그래프를 주지 않는다** (2026-08-18 사용자 지적
    #    *"이거 막대그래프 아예 없는데 정상인거야?"*). 막대가 0 이면 화면은 그냥
    #    비어 보이고, 보는 사람에겐 **앱이 고장 난 것**으로 읽힌다. 점검 탭에 안내를
    #    달아 두긴 했지만 그래프를 보러 온 사람은 그 탭을 안 열어 봤을 수 있다.
    #    ⇒ **그 자리에서 이유를 말한다.**
    if not measurable.any():
        n_say = n_bad or int((~measurable).sum())
        return _note(c, f"선로 {n_say}개 모두 정격(용량)이 안 적혀 있어\n"
                        f"부하율을 그릴 수 없습니다.\n\n"
                        f"계통 데이터 탭의 rateA 열에 용량을 넣으면 그려집니다.")
    load = np.where(measurable, load, 0.0)
    names = line_names(br)
    n = len(names)
    x = np.arange(1, n + 1)

    # 일부만 못 재면 그 사실을 **제목에** 붙인다 — 나머지는 정상으로 그리되
    # 몇 개가 빠졌는지 모른 채 읽지 않게 한다.
    title = "선로 부하율  [%]"
    if n_bad:
        title += f"    ·    {n_bad}개는 정격이 없어 뺐습니다"
    ch = _new_chart(c, title)
    ok = QBarSet("100% 이내")
    over = QBarSet("100% 초과")
    ok.setColor(QColor(DC_BLUE)); ok.setBorderColor(QColor(DC_BLUE))
    over.setColor(QColor(c["warn"])); over.setBorderColor(QColor(c["warn"]))
    for v in load:
        # 한 막대는 한 쪽에만 값을 넣고 다른 쪽은 0 → 색이 갈린다
        ok.append(0.0 if v > 100.0 else float(v))
        over.append(float(v) if v > 100.0 else 0.0)
    bars = QStackedBarSeries()
    bars.append(ok); bars.append(over)
    bars.setBarWidth(0.85)
    ch.addSeries(bars)

    ax = QBarCategoryAxis()
    step = max(1, -(-n // MAX_TICKS))
    ax.append([names[i] if i % step == 0 else "" for i in range(n)])
    _style_axis(ax, c)
    ax.setLabelsAngle(-90)          # 이름이 길어 눕히면 겹친다 → 세운다

    ay = _style_axis(QValueAxis(), c)
    ay.setLabelFormat("%.0f")
    ay.setTickCount(6)
    top = max(105.0, float(load.max()) * 1.08)
    ay.setRange(0.0, top)

    ch.addAxis(ax, Qt.AlignBottom)
    ch.addAxis(ay, Qt.AlignLeft)
    bars.attachAxis(ax); bars.attachAxis(ay)

    # 100% 선 — 막대와 축이 다르므로 따로 붙인다
    lim = _line([(0, 100.0), (n, 100.0)], c["warn"], 1.2, dashed=True,
                name="100%")
    ch.addSeries(lim)
    lx = _style_axis(QValueAxis(), c)
    lx.setRange(0.0, float(n))
    lx.setVisible(False)
    ch.addAxis(lx, Qt.AlignTop)
    lim.attachAxis(lx); lim.attachAxis(ay)

    if not (load > 100.0).any():
        for m in ch.legend().markers(bars):
            if m.label() == "100% 초과":
                m.setVisible(False)      # 넘은 게 없으면 범례에서 뺀다
    return _view(ch, c)


def loading_profile_view(c, sol, times, values, title):
    """한 선로의 **시간별 부하율[%]** 꺾은선. 계통도에서 선로를 클릭하면
    이걸 팝업에 담아 띄운다. 100% 를 넘는 시각은 점을 주황으로 얹고
    100% 자리에 점선을 그어, 언제 용량을 넘겼는지 한눈에 보이게 한다."""
    ch = _new_chart(c, title)
    pts = list(zip(times, values))
    ln = _line(pts, DC_BLUE, 2.2, name="부하율 [%]")
    ch.addSeries(ln)
    hot = [(x, y) for x, y in pts if y > 100.0]
    if hot:
        ch.addSeries(_dots(hot, c["warn"], "100% 초과", 10.0))
    lim = _line([(times[0], 100.0), (times[-1], 100.0)], c["warn"], 1.2,
                dashed=True, name="100%")
    ch.addSeries(lim)

    xa = _style_axis(QValueAxis(), c, "시간 [H]")
    xa.setRange(float(times[0]), float(times[-1]))
    xa.setTickCount(min(len(times), 12))
    xa.setLabelFormat("%d")
    ya = _style_axis(QValueAxis(), c, "부하율 [%]")
    top = max(105.0, max(values) * 1.1)
    ya.setRange(0.0, top)
    ya.setTickCount(6)
    ya.setLabelFormat("%.0f")
    ch.addAxis(xa, Qt.AlignBottom)
    ch.addAxis(ya, Qt.AlignLeft)
    for s in (ln, lim) + ((ch.series()[1],) if hot else tuple()):
        s.attachAxis(xa); s.attachAxis(ya)
    if not hot:
        _hide_from_legend(ch, lim)      # 넘은 게 없으면 100% 선은 범례에서 뺀다
    return _view(ch, c)


# ─────────────────────────────────────────── 이름 → 그래프
# ─────────────────────────────────────────── 비교 (여러 개를 한 그래프에 겹쳐)
# 원본 MATLAB 앱의 ExportComparisonButtonPushed(935~1195줄)가 그리던 그림을
# 옮긴 것. 원본은 "내보내기"를 눌러야 팝업창에 그려 줬지만 여기서는 화면에
# 바로 그린다. 겹쳐 그릴 때 쓰는 색은 서로 잘 구분되는 순서로 골랐다.
CYCLE = ["#d1342f", "#1f6fd0", "#1f9d55", "#e08a1e",
         "#7a3fb8", "#0f9b9b", "#c2570e", "#5a6b7f"]


def _note(c, msg):
    """그릴 수 없을 때 **이유를 적어** 돌려준다 — 빈 상자만 띄우는 것보다 낫다."""
    box = QFrame()
    box.setStyleSheet(f"background:{c['plot']};border:1px solid {c['border']};"
                      f"border-radius:9px;")
    v = QVBoxLayout(box)
    lb = QLabel(msg)
    lb.setAlignment(Qt.AlignCenter)
    lb.setWordWrap(True)
    lb.setStyleSheet(f"color:{c['muted']};font-size:14px;")
    v.addWidget(lb)
    box.setMinimumHeight(150)
    return box


def _nums(targets):
    """쉼표로 적어 넣은 대상에서 숫자만 골라낸다."""
    return [int(str(t).strip()) for t in targets if str(t).strip().isdigit()]


def _fmt(top):
    """축 글자 서식 — 값이 크면 소수점을 줄이고, 작으면 늘린다.

    고정으로 "%.3f" 를 쓰면 값이 작을 때 축이 전부 "0.000" 이 되고
    (12버스는 손실이 2.8e-5 MW), 클 때는 자릿수가 넘쳐 잘린다.
    """
    a = abs(float(top))
    if a >= 1000:
        return "%.0f"
    if a >= 10:
        return "%.1f"
    if a >= 1:
        return "%.2f"
    if a >= 0.01:
        return "%.3f"
    return "%.2e"


def _find_bus(sol, no):
    """실제 버스 번호 → ("AC"|"DC", 몇 번째 줄). 없으면 None.

    AC 를 먼저 보고 없으면 DC — MATLAB 도 [AC; DC] 순서로 이어 붙인다.
    """
    for kind in ("AC", "DC"):
        arr = getattr(sol, kind)
        if arr.size:
            ids = [int(b) for b in arr[:, 0, 0]]
            if no in ids:
                return kind, ids.index(no)
    return None


def _finish(ch, c, xa, ya):
    """축을 붙이고 화면에 얹을 위젯으로."""
    ch.addAxis(xa, Qt.AlignBottom)
    ch.addAxis(ya, Qt.AlignLeft)
    for s in ch.series():
        s.attachAxis(xa)
        s.attachAxis(ya)
    return _view(ch, c)


def _cmp_by_bus(c, sol, item, nos):
    """버스끼리 — x축이 **시간**이고 버스마다 선 하나 (원본 1053~1078줄).

    상·하한 점선은 깔지 않는다. 버스마다 한계가 다른데 여러 개를 겹치면
    어느 선의 한계인지 알 수 없기 때문이다(원본도 같은 이유로 생략했다).
    """
    col = {"전압 크기": "VM[pu]", "위상각": "Angle[deg]"}[item]
    ch = _new_chart(c, f"{item} 비교   ·   x축 = 시간")
    lo = hi = None
    n = 0
    skipped = []
    for k, no in enumerate(nos):
        got = _find_bus(sol, no)
        if got is None:
            skipped.append(f"{no}(없음)")
            continue
        kind, row = got
        cols = sol.cols(kind)
        if col not in cols:              # DC 버스에는 위상각이 없다
            skipped.append(f"{no}(DC)")
            continue
        y = np.asarray(sol.series(kind, cols.index(col), row), dtype=float)
        if y.size == 0:
            continue
        x = np.arange(1, y.size + 1)
        color = CYCLE[k % len(CYCLE)]
        name = f"버스 {no}"
        ch.addSeries(_line(zip(x, y), color, 1.8, name=name))
        d = _dots(list(zip(x, y)), color, name, size=7.0)
        ch.addSeries(d)
        _hide_from_legend(ch, d)         # 선과 점이 같은 것이라 범례엔 한 번만
        lo = float(y.min()) if lo is None else min(lo, float(y.min()))
        hi = float(y.max()) if hi is None else max(hi, float(y.max()))
        n = max(n, int(y.size))
    if not n:
        why = ("고른 버스에 위상각이 없습니다 (위상각은 AC 버스만 있습니다)"
               if item == "위상각" else "고른 버스를 찾지 못했습니다")
        return _note(c, why)

    xa = _style_axis(QValueAxis(), c)
    xa.setLabelFormat("%d")
    xa.setRange(1, max(2, n))
    xa.setTickCount(min(12, max(2, n)))
    ya = _style_axis(QValueAxis(), c)
    ya.setLabelFormat("%.3f" if item == "전압 크기" else "%.2f")
    ya.setTickCount(6)
    pad = max(1e-4, (hi - lo) * 0.15)
    ya.setRange(lo - pad, hi + pad)
    if skipped:                          # 왜 빠졌는지 제목에 남긴다
        ch.setTitle(ch.title() + f"   (뺀 버스: {', '.join(skipped)})")
    return _finish(ch, c, xa, ya)


def _cmp_by_time(c, sol, item, times):
    """시간끼리 — x축이 **버스**고 시간마다 선 하나 (원본 1065~1092·1116~1128줄).

    전압은 AC·DC 를 다 그리고 상·하한을 검은 점선으로 깐다(원본과 같음,
    이때는 모든 선이 같은 버스를 보므로 한계가 뜻을 갖는다).
    위상각은 AC 버스만 그린다.
    """
    ac_only = item == "위상각"
    ch = _new_chart(c, f"{item} 비교   ·   x축 = 버스")
    names, lo_all, hi_all = [], None, None
    ys = []
    for k, h in enumerate(times):
        t = h - 1                        # 화면은 1시부터, 배열은 0부터
        if item == "전압 크기":
            nm, vm, vmin, vmax, _ = _bus_table(sol, t)
            vals = vm
        else:
            ac = sol.at("AC", t)
            if not ac.size:
                continue
            cols = sol.cols("AC")
            nm = [f"{int(r[0])}" for r in ac]
            vals = np.asarray(ac[:, cols.index("Angle[deg]")], dtype=float)
            vmin = vmax = None
        if not len(nm):
            continue
        names = nm
        x = np.arange(1, len(nm) + 1)
        color = CYCLE[k % len(CYCLE)]
        name = f"{h}H"
        ch.addSeries(_line(zip(x, vals), color, 1.8, name=name))
        d = _dots(list(zip(x, vals)), color, name, size=7.0)
        ch.addSeries(d)
        _hide_from_legend(ch, d)
        ys.append(np.asarray(vals, dtype=float))
        if vmin is not None:
            lo_all, hi_all = np.asarray(vmin), np.asarray(vmax)
    if not ys:
        return _note(c, "그릴 값이 없습니다 (고른 시간을 확인해 주세요)"
                     if not ac_only else "AC 버스가 없어 위상각을 그릴 수 없습니다")

    x = np.arange(1, len(names) + 1)
    if lo_all is not None:               # 상·하한 (범례에선 감춘다 — 원본과 같음)
        top = _line(zip(x, hi_all), LIMIT_GRAY, 1.0, dashed=True, name="한계")
        bot = _line(zip(x, lo_all), LIMIT_GRAY, 1.0, dashed=True)
        ch.addSeries(top); ch.addSeries(bot)
        _hide_from_legend(ch, bot)
    xa = _bus_axis(c, names)
    ya = _style_axis(QValueAxis(), c)
    ya.setLabelFormat("%.3f" if item == "전압 크기" else "%.2f")
    ya.setTickCount(6)
    lo = min(float(np.min(y)) for y in ys)
    hi = max(float(np.max(y)) for y in ys)
    if lo_all is not None:
        lo, hi = min(lo, float(lo_all.min())), max(hi, float(hi_all.max()))
    pad = max(1e-4, (hi - lo) * 0.12)
    ya.setRange(lo - pad, hi + pad)
    return _finish(ch, c, xa, ya)


def _cmp_freq(c, sol, times):
    """주파수 — 고른 시간의 값만 이어 그린다 (원본 1134~1146줄, 주황 한 줄)."""
    if sol.freq.size == 0:
        return _note(c, "주파수 결과가 없습니다")
    keep = [h for h in times if 1 <= h <= sol.freq.size]
    if not keep:
        return _note(c, "고른 시간이 결과 범위를 벗어났습니다")
    y = np.asarray([sol.freq[h - 1] for h in keep], dtype=float)
    x = np.arange(1, len(keep) + 1)
    ch = _new_chart(c, "주파수 비교   ·   x축 = 고른 시간")
    ch.addSeries(_line(zip(x, y), "#d95f0e", 1.8, name="주파수"))
    d = _dots(list(zip(x, y)), "#d95f0e", "주파수", size=8.0)
    ch.addSeries(d)
    _hide_from_legend(ch, d)
    xa = _bus_axis(c, [f"{h}H" for h in keep])   # 눈금 글자만 시간으로 바꿔 쓴다
    ya = _style_axis(QValueAxis(), c)
    ya.setLabelFormat("%.3f")
    ya.setTickCount(6)
    lo, hi = float(y.min()), float(y.max())
    pad = max(0.01, (hi - lo) * 0.3)
    ya.setRange(lo - pad, hi + pad)
    return _finish(ch, c, xa, ya)


def _cmp_loss(c, sol, times):
    """손실 — 왼축은 실제 손실 막대, 오른축은 백분율 선 (원본 1149~1190줄).

    DC only 계통은 손실 표에 P 만 있어 막대·선도 P 하나씩만 나온다.
    """
    if sol.loss.size == 0:
        return _note(c, "손실 결과가 없습니다")
    cols = sol.cols("Loss")
    keep = [h for h in times if 1 <= h <= sol.loss.shape[0]]
    if not keep:
        return _note(c, "고른 시간이 결과 범위를 벗어났습니다")
    idx = [h - 1 for h in keep]
    has_q = "Qloss[Var]" in cols
    p_raw = sol.loss[idx, cols.index("Ploss[W]")]
    q_raw = sol.loss[idx, cols.index("Qloss[Var]")] if has_q else None
    p_pct = sol.loss[idx, cols.index("Ploss[%]")]
    q_pct = sol.loss[idx, cols.index("Qloss[%]")] if has_q else None
    # 손실 표의 단위는 W·Var 다. 원본 앱은 무조건 1e6 으로 나눠 MW 로 적었는데,
    # baseMVA 가 0.001 인 12버스 케이스에서는 값이 2.8e-5 MW 라 축 글자가
    # 전부 "0.000" 이 된다 → **값 크기를 보고 단위를 고른다**.
    big = max(float(np.max(np.abs(p_raw))),
              float(np.max(np.abs(q_raw))) if has_q else 0.0)
    div, unit = ((1e6, "MW / MVar") if big >= 1e6 else
                 (1e3, "kW / kVar") if big >= 1e3 else (1.0, "W / Var"))
    p_act = p_raw / div
    q_act = q_raw / div if has_q else None

    ch = _new_chart(c, "손실 비교   ·   x축 = 고른 시간")
    bars = QBarSeries()
    bp = QBarSet(f"P 손실 [{unit.split(' / ')[0]}]")
    bp.append([float(v) for v in p_act])
    bp.setColor(QColor(AC_RED)); bp.setBorderColor(QColor(AC_RED))
    bars.append(bp)
    if has_q:
        bq = QBarSet(f"Q 손실 [{unit.split(' / ')[1]}]")
        bq.append([float(v) for v in q_act])
        bq.setColor(QColor(DC_BLUE)); bq.setBorderColor(QColor(DC_BLUE))
        bars.append(bq)
    ch.addSeries(bars)

    x = np.arange(len(keep))             # 막대 축은 0부터 세는 칸 번호다
    lp = _line(zip(x, p_pct), AC_RED, 2.0, name="P 손실 [%]")
    ch.addSeries(lp)
    if has_q:
        lq = _line(zip(x, q_pct), DC_BLUE, 2.0, name="Q 손실 [%]")
        pen = lq.pen()                   # pen() 은 복사본이라 고쳐서 되돌려줘야 한다
        pen.setStyle(Qt.DashLine)
        lq.setPen(pen)
        ch.addSeries(lq)

    xa = _style_axis(QBarCategoryAxis(), c)
    xa.append([f"{h}H" for h in keep])
    ya = _style_axis(QValueAxis(), c, f"실제 손실 [{unit}]")
    ya.setTickCount(6)
    top = max(float(np.max(p_act)), float(np.max(q_act)) if has_q else 0.0)
    ya.setRange(0.0, max(1e-9, top) * 1.25)
    ya.setLabelFormat(_fmt(top))
    yb = _style_axis(QValueAxis(), c, "손실 [%]")
    yb.setTickCount(6)
    ptop = max(float(np.max(p_pct)), float(np.max(q_pct)) if has_q else 0.0)
    yb.setRange(0.0, max(1e-9, ptop) * 1.25)
    yb.setLabelFormat(_fmt(ptop))

    ch.addAxis(xa, Qt.AlignBottom)
    ch.addAxis(ya, Qt.AlignLeft)
    ch.addAxis(yb, Qt.AlignRight)
    bars.attachAxis(xa); bars.attachAxis(ya)
    for s in (lp, lq) if has_q else (lp,):
        s.attachAxis(xa)
        s.attachAxis(yb)
    return _view(ch, c)


def is_chart(w) -> bool:
    """진짜 그래프인가, 아니면 이유를 적은 상자인가.

    `compare_chart` 는 못 그릴 때도 위젯을 돌려주므로(빈 화면보다 낫다),
    저장할 때는 이걸로 걸러 **안내 문구를 그림 파일로 저장하는 일**을 막는다.
    """
    return isinstance(w, QChartView)


def _cmp_by_scenario(c, pairs, item, t):
    """시나리오끼리 — x축이 **버스**고 시나리오마다 선 하나 (PDR §7 2단계).

    pairs = [(이름, Solution), ...] · t = 볼 시각 (0부터)

    왜 x축이 버스인가: 선로를 끊었을 때 보고 싶은 것은 **전압 곡선이 어떻게 주저앉나**다.
    한 버스만 시간축으로 보면 그 그림이 안 나온다.
    상·하한 점선은 깐다 — 모든 선이 같은 버스들을 보므로 한계가 뜻을 갖는다.
    """
    ch = _new_chart(c, f"{item} 비교   ·   x축 = 버스   ·   {t + 1}H")
    names, lo_all, hi_all, ys = [], None, None, []
    skipped = []
    for k, (label, sol) in enumerate(pairs):
        if sol is None:
            skipped.append(label)
            continue
        if item == "전압 크기":
            nm, vals, vmin, vmax, _ = _bus_table(sol, t)
        else:
            ac = sol.at("AC", t)
            if not ac.size:
                skipped.append(label)
                continue
            cols = sol.cols("AC")
            nm = [f"{int(r[0])}" for r in ac]
            vals = np.asarray(ac[:, cols.index("Angle[deg]")], dtype=float)
            vmin = vmax = None
        if not len(nm):
            skipped.append(label)
            continue
        # 🚨 버스 수가 다르면 겹쳐 그릴 수 없다. 조건을 바꿔도 버스는 그대로지만,
        #    다른 케이스를 섞으면 어긋난다 — 조용히 어긋난 그림을 그리느니 뺀다.
        if names and len(nm) != len(names):
            skipped.append(f"{label}(버스 수 다름)")
            continue
        names = nm
        x = np.arange(1, len(nm) + 1)
        color = CYCLE[k % len(CYCLE)]
        ch.addSeries(_line(zip(x, vals), color, 1.8, name=label))
        d = _dots(list(zip(x, vals)), color, label, size=7.0)
        ch.addSeries(d)
        _hide_from_legend(ch, d)
        ys.append(np.asarray(vals, dtype=float))
        if vmin is not None:
            lo_all, hi_all = np.asarray(vmin), np.asarray(vmax)
    if not ys:
        return _note(c, "그릴 시나리오가 없습니다 — 목록에서 하나 이상 체크하세요")

    x = np.arange(1, len(names) + 1)
    if lo_all is not None:
        top = _line(zip(x, hi_all), LIMIT_GRAY, 1.0, dashed=True, name="한계")
        bot = _line(zip(x, lo_all), LIMIT_GRAY, 1.0, dashed=True)
        ch.addSeries(top); ch.addSeries(bot)
        _hide_from_legend(ch, bot)
    xa = _bus_axis(c, names)
    ya = _style_axis(QValueAxis(), c)
    ya.setLabelFormat("%.3f" if item == "전압 크기" else "%.2f")
    ya.setTickCount(6)
    lo = min(float(np.min(y)) for y in ys)
    hi = max(float(np.max(y)) for y in ys)
    if lo_all is not None:
        lo, hi = min(lo, float(lo_all.min())), max(hi, float(hi_all.max()))
    pad = max(1e-4, (hi - lo) * 0.12)
    ya.setRange(lo - pad, hi + pad)
    if skipped:
        ch.setTitle(ch.title() + f"   (뺀 것: {', '.join(skipped)})")
    return _finish(ch, c, xa, ya)


def _cmp_scen_scalar(c, pairs, item):
    """주파수·손실을 시나리오끼리 — 이 둘은 계통에 하나뿐이라 x축이 **시간**이다."""
    ch = _new_chart(c, f"{item} 비교   ·   x축 = 시간")
    ys = []
    for k, (label, sol) in enumerate(pairs):
        if sol is None:
            continue
        if item == "주파수":
            y = np.asarray(sol.freq, dtype=float).ravel()
        else:
            arr = np.asarray(sol.loss, dtype=float)
            y = np.nansum(arr[:, :3], axis=1) if arr.size else np.array([])
        if y.size == 0:
            continue
        x = np.arange(1, y.size + 1)
        color = CYCLE[k % len(CYCLE)]
        ch.addSeries(_line(zip(x, y), color, 1.8, name=label))
        d = _dots(list(zip(x, y)), color, label, size=7.0)
        ch.addSeries(d)
        _hide_from_legend(ch, d)
        ys.append(y)
    if not ys:
        return _note(c, "그릴 시나리오가 없습니다 — 목록에서 하나 이상 체크하세요")
    n = max(y.size for y in ys)
    xa = _style_axis(QValueAxis(), c)
    xa.setLabelFormat("%d")
    xa.setRange(1, max(2, n))
    xa.setTickCount(min(12, max(2, n)))
    ya = _style_axis(QValueAxis(), c)
    ya.setTickCount(6)
    lo = min(float(np.min(y)) for y in ys)
    hi = max(float(np.max(y)) for y in ys)
    pad = max(1e-9, (hi - lo) * 0.15) if hi > lo else max(1e-9, abs(hi) * 0.05)
    ya.setRange(lo - pad, hi + pad)
    return _finish(ch, c, xa, ya)


def compare_scenarios(c, pairs, item, t):
    """시나리오끼리 비교 그래프 하나. 못 그리면 이유를 적은 상자를 돌려준다."""
    if not pairs:
        return _note(c, "겹쳐 볼 시나리오를 목록에서 체크하세요")
    try:
        if item in ("주파수", "손실"):
            return _cmp_scen_scalar(c, pairs, item)
        if item == "위상각" and int(getattr(pairs[0][1], "mode", 0)) == 2:
            return _note(c, "DC only 계통이라 위상각이 없습니다")
        return _cmp_by_scenario(c, pairs, item, t)
    except Exception as exc:
        print(f"[시나리오 비교] {item} 실패: {exc}")
        return _note(c, f"{item} 을 그리지 못했습니다 ({type(exc).__name__})")


def compare_chart(c, sol, item, axis, targets):
    """비교 모드 그래프 하나. 못 그리면 이유를 적은 상자를 돌려준다.

    item  = 전압 크기 / 위상각 / 주파수 / 손실
    axis  = "버스끼리"(x축이 시간) / "시간끼리"(x축이 버스)
    """
    if sol is None:
        return _note(c, "먼저 케이스를 불러와 계산하세요")
    nos = _nums(targets)
    if not nos:
        unit = "버스" if axis == "버스끼리" else "시간"
        return _note(c, f"비교할 {unit} 번호를 왼쪽에 적어 주세요")
    try:
        if item in ("주파수", "손실"):
            # 이 둘은 계통 전체에 하나뿐인 값이라 버스끼리 비교가 성립하지 않는다
            if axis != "시간끼리":
                return _note(c, f"{item} 은 계통 전체에 하나뿐이라 "
                                f"시간끼리 비교에서만 볼 수 있습니다")
            return _cmp_freq(c, sol, nos) if item == "주파수" \
                else _cmp_loss(c, sol, nos)
        if item == "위상각" and int(getattr(sol, "mode", 0)) == 2:
            return _note(c, "DC only 계통이라 위상각이 없습니다")
        return (_cmp_by_bus(c, sol, item, nos) if axis == "버스끼리"
                else _cmp_by_time(c, sol, item, nos))
    except Exception as exc:              # 한 그래프가 죽어도 앱은 살아 있게
        print(f"[비교 그래프] {item} 실패: {exc}")
        return _note(c, f"그리지 못했습니다: {exc}")


def build(name, c, sol, t=0, bus_row=0, show_violations=False, on_toggle=None,
          on_line_click=None, topo_zoom=1.0, on_topo_zoom=None):
    """그래프 이름에 맞는 그림을 만든다. 아직 못 그리는 것은 None(자리만 표시).

    ⚠️ 이름만 앞부분으로 맞추면 안 된다 — 스냅샷의 "전압 … x축 = 버스" 와
       다이나믹의 "전압 … x축 = 시간" 이 둘 다 "전압" 으로 시작하는데
       그리는 게 완전히 다르다. x축이 뭔지까지 보고 갈라야 한다.
    """
    if sol is None:
        return None
    by_time = "시간" in name
    try:
        if name.startswith("주파수"):
            return freq_chart(c, sol)
        if name.startswith("전압"):
            return (voltage_series(c, sol, bus_row) if by_time
                    else voltage_chart(c, sol, t))
        if name.startswith("위상각"):
            return (angle_series(c, sol, bus_row) if by_time
                    else angle_chart(c, sol, t))
        if name.startswith("유효전력"):
            return flow_chart(c, sol, t, "P", "유효전력 P", "MW")
        if name.startswith("무효전력"):
            return flow_chart(c, sol, t, "Q", "무효전력 Q", "MVAr")
        if "부하율" in name:
            return loading_chart(c, sol, t)
        if "단선도" in name or "토폴로지" in name:
            import topology
            return topology.topology_view(c, sol, t, show_violations, on_toggle,
                                          on_line_click,
                                          zoom=topo_zoom, on_zoom=on_topo_zoom)
    except Exception as exc:          # 한 그래프가 죽어도 앱은 살아 있게
        print(f"[그래프] {name} 실패: {exc}")
    return None
    return None


# ─────────────────────────────────────────── PV·QV 곡선 (2026-08-12, §7 4단계 F1d)

# 여러 버스를 한 그림에 겹쳐 그리므로 색이 여럿 필요하다.
CURVE_COLORS = ("#d1342f", "#1f6fd0", "#1f9d55", "#b8860b", "#8b3fb0",
                "#0f8f8f", "#c25b1e", "#5566aa")


def curve_chart(c, cur, buses=None, x_axis="MW"):
    """PV 곡선 — 부하를 늘려 갈 때 버스 전압이 어떻게 내려가는가.

    `cur`      app_engine.Curve
    `buses`    그릴 버스 번호 목록. 비우면 곡선 대상 버스 전부(많으면 앞 8개).
    `x_axis`   "MW" 면 늘린 버스들의 합계 부하, "lambda" 면 배수 λ.

    코 끝점(더는 안 풀리는 지점)에 점을 찍는다 — **거기가 곡선의 뜻 그 자체**라
    선만 그리면 어디가 한계인지 안 보인다.
    """
    title = "PV 곡선 — 부하를 늘릴 때의 전압"
    ch = _new_chart(c, title)

    if cur is None or cur.lam.size == 0:
        return _view(ch, c)

    pick = list(buses) if buses is not None and len(buses) else list(cur.curve_buses)
    pick = [float(b) for b in pick][:8]

    x = cur.load_MW if x_axis == "MW" else cur.lam
    ymin, ymax = 1e9, -1e9
    for i, b in enumerate(pick):
        y = cur.at(b)
        col = CURVE_COLORS[i % len(CURVE_COLORS)]
        s = _line(list(zip(x, y)), col, width=1.8, name=f"버스 {int(b)}")
        ch.addSeries(s)
        ymin = min(ymin, float(np.min(y)))
        ymax = max(ymax, float(np.max(y)))

    # 코 끝점 — 버스마다 하나씩, 선과 같은 색으로
    k = max(0, min(int(cur.nose), x.size - 1))
    nose_pts = [(x[k], float(cur.at(b)[k])) for b in pick]
    if nose_pts:
        d = _dots(nose_pts, c["text"], "코 끝점 (한계)", size=9.0)
        ch.addSeries(d)

    ax = _style_axis(QValueAxis(), c,
                     "늘린 버스 합계 부하 [MW]" if x_axis == "MW" else "부하 배수 λ")
    ay = _style_axis(QValueAxis(), c, "전압 [p.u.]")
    ch.addAxis(ax, Qt.AlignBottom)
    ch.addAxis(ay, Qt.AlignLeft)
    for s in ch.series():
        s.attachAxis(ax)
        s.attachAxis(ay)
    ax.setRange(float(np.min(x)), float(np.max(x)) * 1.02)
    pad = max(0.02, (ymax - ymin) * 0.08)
    ay.setRange(max(0.0, ymin - pad), ymax + pad)
    ax.setLabelFormat("%.0f" if x_axis == "MW" else "%.2f")
    ay.setLabelFormat("%.2f")
    return _view(ch, c)


def curve_q_chart(c, cur, x_axis="MW"):
    """발전기 무효출력 — 어느 발전기가 언제 한계에 걸려 전압을 못 잡게 되는가.

    PV 곡선이 "얼마나 버티나"라면 이 그림은 **"왜 거기서 꺾이나"**를 보여 준다.
    한계에 걸린 자리에서 선이 평평해진다.
    """
    ch = _new_chart(c, "발전기 무효출력 — 한계에 걸리는 자리")
    if cur is None or cur.pv_Qg.size == 0:
        return _view(ch, c)

    x = cur.load_MW if x_axis == "MW" else cur.lam
    n = min(cur.pv_Qg.shape[1], 8)
    lo, hi = 1e9, -1e9
    for i in range(n):
        y = cur.pv_Qg[:, i]
        col = CURVE_COLORS[i % len(CURVE_COLORS)]
        ch.addSeries(_line(list(zip(x, y)), col, width=1.6,
                           name=f"버스 {int(cur.pv_bus[i])}"))
        lo = min(lo, float(np.min(y)))
        hi = max(hi, float(np.max(y)))

    ax = _style_axis(QValueAxis(), c,
                     "늘린 버스 합계 부하 [MW]" if x_axis == "MW" else "부하 배수 λ")
    ay = _style_axis(QValueAxis(), c, "무효출력 [MVAr]")
    ch.addAxis(ax, Qt.AlignBottom)
    ch.addAxis(ay, Qt.AlignLeft)
    for s in ch.series():
        s.attachAxis(ax)
        s.attachAxis(ay)
    ax.setRange(float(np.min(x)), float(np.max(x)) * 1.02)
    pad = max(1.0, (hi - lo) * 0.08)
    ay.setRange(lo - pad, hi + pad)
    ax.setLabelFormat("%.0f" if x_axis == "MW" else "%.2f")
    ay.setLabelFormat("%.0f")
    return _view(ch, c)
