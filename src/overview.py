# -*- coding: utf-8 -*-
"""결과 개요 — 조류계산을 풀고 처음 보는 화면 (앱 2.3 · 2026-11-03).

배치(Soft UI 꼴, 사용자 확정)
    [숫자 카드 넷 — 위반 · 버스 전압 범위 · 최대 부하율 · 수급]
    [위반 목록 표                   | 요약 카드(글 + 잘린 계통도)]
    [버스 전압 그래프(검은 카드)      | 선로 부하율 상위]

색 — 화면 강조는 검정, **위반은 노랑-주황**. 빨강 · 파랑은 AC · DC 뜻에만 쓴다.
요약 카드의 계통도 = 퍼짐 배치를 오른쪽 아래로 크게 그려 카드 밖으로 잘리게 한다.
선 색 = 부하율(옅은 회색 → 남색), 위반 = 주황. 버스가 150 을 넘으면 묶음 60 개로 줄인다.
"""
from __future__ import annotations

from collections import deque

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, QRect
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QLinearGradient, QBrush
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget, QGraphicsDropShadowEffect,
                               QGraphicsOpacityEffect, QScrollArea, QTableWidget,
                               QTableWidgetItem, QHeaderView, QAbstractItemView)

import charts
import checks
import topology as T

AMB = "#f5a300"            # 위반
AMB_TEXT = "#b07400"       # 흰 바탕 위 위반 글자
LOAD_LO, LOAD_HI = "#dfe3ea", "#2e3d57"
COARSE_OVER = 150          # 버스가 이보다 많으면 묶어서 그린다
COARSE_K = 60              # 묶음 수 — case24(버스 57)와 비슷한 밀도


def _mix(a, b, f):
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * f),
                  round(ca.green() + (cb.green() - ca.green()) * f),
                  round(ca.blue() + (cb.blue() - ca.blue()) * f))


# ── 결과에서 숫자 뽑기 ───────────────────────────────────────────────
def _col(sol, which, name):
    cols = sol.cols(which)
    return cols.index(name) if name in cols else -1


def _lim(x):
    """한계값을 반올림하지 않고 적는다 — 1.039 를 1.04 로 적으면 넘지 않은 것처럼 보인다."""
    s = f"{float(x):.3f}".rstrip("0")
    return s + "0" if s.endswith(".") or len(s.split(".")[-1]) < 2 else s


def summary(sol, t):
    """카드에 쓸 숫자를 한 번에 모은다."""
    viol = checks.real_violations(sol, t)
    vrows = viol["전압 위반"][1]
    lrows = viol["과부하 선로"][1]
    s = dict(n_v=len(vrows), n_l=len(lrows), n_ic=len(viol["변환기 한계"][1]))
    vm = []
    gen = load = 0.0
    for which in ("AC", "DC"):
        arr = sol.at(which, t)
        if not arr.size:
            continue
        iv, ig, il = (_col(sol, which, "VM[pu]"), _col(sol, which, "Gen_P[MW]"),
                      _col(sol, which, "Load_P[MW]"))
        vm += list(arr[:, iv])
        gen += float(arr[:, ig].sum()) if ig >= 0 else 0.0
        load += float(arr[:, il].sum()) if il >= 0 else 0.0
    s["vmin"], s["vmax"] = (min(vm), max(vm)) if vm else (np.nan, np.nan)
    s["gen"], s["load"] = gen, load
    br = sol.at("Branch", t)
    s["loss"] = float(br[:, _col(sol, "Branch", "Loss_P[MW]")].sum()) if br.size else 0.0
    # 최대 부하율 — 과부하 판정과 같은 잣대(정격이 적힌 선로만)
    top = None
    if br.size:
        iF, iT = _col(sol, "Branch", "From"), _col(sol, "Branch", "To")
        iL, iC = _col(sol, "Branch", "Loading[%]"), _col(sol, "Branch", "Capacity[MVA]")
        for r in br:
            if iL >= 0 and checks._rated(r, iC, iL):
                if top is None or r[iL] > top[0]:
                    top = (float(r[iL]), f"{int(r[iF])}–{int(r[iT])}")
    s["top"] = top
    # 위반 줄 — 넘은 비율 순
    rows = []
    for name, v, lim, ex in vrows:
        hi = float(lim.split()[-1])
        rows.append(("전압", name, f"{float(v):.4f} pu", f"{_lim(hi)} pu", ex,
                     abs(float(v) - hi) / 0.1))
    for f, to, L, cap in lrows:
        rows.append(("선로", f"{f}–{to}", f"{float(L):.1f} %", "100 %",
                     f"+{float(L) - 100:.1f} %", (float(L) - 100) / 100))
    rows.sort(key=lambda r: -r[5])
    s["rows"] = rows
    # 「살펴볼 곳」(2026-11-03 실무 차례) — 넘음 → 한계 도달 → 근접. 줄 = (상태, 종류, 대상, 값, 한계, 넘은 양·여유, 비율)
    work = [("넘음",) + r for r in rows]
    reached = viol["발전기 한계"][1] + [[n, "변환기", st, "—", "—"] for n, st in viol["변환기 한계"][1]]
    for r in viol["발전기 한계"][1]:
        work.append(("도달", "발전기", r[0], f"{r[1]} {r[3]}", r[2], "—", 0.0))
    for nm, st in viol["변환기 한계"][1]:
        work.append(("도달", "변환기", nm, st, "—", "—", 0.0))
    near = []
    for which in ("AC", "DC"):
        arr = sol.at(which, t)
        if not arr.size:
            continue
        ib, iv = _col(sol, which, "Bus"), _col(sol, which, "VM[pu]")
        ilo, ihi = _col(sol, which, "Vmin[pu]"), _col(sol, which, "Vmax[pu]")
        if min(ib, iv, ilo, ihi) < 0:
            continue
        for r in arr:
            v, lo, hi = float(r[iv]), float(r[ilo]), float(r[ihi])
            if lo <= v <= hi and min(hi - v, v - lo) < NEAR_PU:
                m = min(hi - v, v - lo)
                near.append(("근접", "전압", f"{which} {int(r[ib])}", f"{v:.4f} pu",
                             f"{_lim(hi if hi - v < v - lo else lo)} pu", f"여유 {m:.4f}", m))
    near.sort(key=lambda r: r[6])
    work += near
    s["work"], s["n_near"], s["n_reach"] = work, len(near), len(reached)
    s["n_gen_lim"], s["n_ic_lim"] = len(viol["발전기 한계"][1]), len(viol["변환기 한계"][1])
    s["n_ic"] = len(getattr(sol, "IC_lim_mode", None) or [])
    s["iters"] = getattr(sol, "iters", None) if "iter_count" in (getattr(sol, "raw", None) or {}) else None
    mh = list(getattr(sol, "mis_history", []) or [])
    s["mis"] = float(mh[-1]) if mh else None
    s["converged"] = bool(getattr(sol, "converged", True))
    return s


# ── 큰 계통 간소화 ───────────────────────────────────────────────────
def _bfs(adj, seeds, n):
    dist, own, q = [-1] * n, [-1] * n, deque()
    for c, s in enumerate(seeds):
        dist[s], own[s] = 0, c
        q.append(s)
    while q:
        u = q.popleft()
        for w in adj[u]:
            if dist[w] < 0:
                dist[w], own[w] = dist[u] + 1, own[u]
                q.append(w)
    return dist, own


def _coarsen(g, load, vbad):
    """버스를 묶음 COARSE_K 개로 — 씨앗(선로 단계로 가장 먼 것부터) → 가장 가까운 씨앗에 붙이기.
    AC 버스와 DC 버스는 따로 묶는다. 돌려주는 것 = 새 그래프 · 묶음 부하율 · 위반 묶음."""
    n = len(g.keys)
    grp = ["DC" if k == "DC" else "AC" for k in g.kind]   # 3권선 점 등은 AC 쪽으로
    adj = [[] for _ in range(n)]
    for a, b, _k in g.edges:
        if grp[a] == grp[b]:
            adj[a].append(b)
            adj[b].append(a)
    own = [-1] * n
    kinds, base = [], 0
    for kind in ("AC", "DC"):
        ids = [i for i in range(n) if grp[i] == kind]
        if not ids:
            continue
        k = max(1, round(COARSE_K * len(ids) / n))
        seeds = [ids[0]]
        for _ in range(k - 1):
            dist, _ = _bfs(adj, seeds, n)
            far = max(ids, key=lambda i: (dist[i] < 0, dist[i]))
            if dist[far] == 0:
                break
            seeds.append(far)
        _, o = _bfs(adj, seeds, n)
        for i in ids:
            own[i] = base + max(o[i], 0)
        kinds += [kind] * len(seeds)
        base += len(seeds)
    edges, eload = {}, {}
    for ei, (a, b, kd) in enumerate(g.edges):
        ca, cb = own[a], own[b]
        if ca == cb:
            continue
        key = (min(ca, cb), max(ca, cb))
        edges.setdefault(key, kd if kd in ("AC", "DC") else "IC")
        if ei in load:
            eload[key] = max(eload.get(key, 0.0), load[ei])
    cg = T.Graph()
    cg.keys = [f"C{i}" for i in range(base)]
    cg.kind = kinds
    cg.edges = [(a, b, k) for (a, b), k in edges.items()]
    cload = {i: eload[(a, b)] for i, (a, b, _k) in enumerate(cg.edges) if (a, b) in eload}
    cbad = {own[i] for i in vbad}
    return cg, cload, cbad


class TopoMini(QWidget):
    """요약 카드 바탕 — 잘린 계통도. 글은 위에 따로 얹는다(이 위젯은 그리기만)."""

    def __init__(self, sol, t, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        g = T.build_graph(sol)
        ov = T.make_overlay(g, sol, t) if g.keys else {"load": {}, "vbad": {}}
        load = dict(ov.get("load", {}))
        vbad = set(ov.get("vbad", {}).keys())
        self.coarse = len(g.keys) > COARSE_OVER
        if self.coarse:
            g, load, vbad = _coarsen(g, load, vbad)
        self.g, self.load, self.vbad = g, load, vbad
        self.pos = T.spread_layout(g) if g.keys else np.zeros((0, 2))

    def paintEvent(self, _e):
        if not len(self.pos):
            return
        w, h = self.width(), self.height()
        # 그린 범위를 재서 [왼쪽 44 % ~ 오른쪽 끝 너머 12 %] × [위 8 % ~ 아래 끝 너머 14 %] 에
        # 맞춘다 — 오른쪽 · 아래만 조금 잘리고, 작은 계통도 큰 계통도 대부분 보인다
        xs, ys = self.pos[:, 0], 1 - self.pos[:, 1]
        bw, bh = max(1e-6, np.ptp(xs)), max(1e-6, np.ptp(ys))
        L, R, Tp, Bt = max(w * .44, 250), w * 1.12, h * .08, h * 1.14   # 250 = 왼쪽 글 줄 폭(좁은 창에서 겹쳤음)
        s = min((R - L) / bw, (Bt - Tp) / bh)
        ox = L - xs.min() * s + ((R - L) - bw * s) / 2
        oy = Tp - ys.min() * s + ((Bt - Tp) - bh * s) / 2
        P = [(ox + x * s, oy + y * s) for x, y in zip(xs, ys)]
        over = {i for i, v in self.load.items() if v > 100}
        hot = [P[i] for i in self.vbad] + [((P[a][0] + P[b][0]) / 2, (P[a][1] + P[b][1]) / 2)
                                         for i, (a, b, _k) in enumerate(self.g.edges) if i in over]
        if hot:   # 위반 자리가 잘리면 카드 안으로 당긴다(왼쪽 · 위로만)
            dx = min(0.0, (w - 24) - max(q[0] for q in hot))
            dy = min(0.0, (h - 24) - max(q[1] for q in hot))
            P = [(x + dx, y + dy) for x, y in P]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setClipRect(QRectF(L - 14, 0, w - L + 14, h))   # 글 자리(왼쪽)에는 안 그린다
        for i, (a, b, k) in enumerate(self.g.edges):
            if i in over:
                col, wd = QColor(AMB), 2.8
            else:
                f = min(1.0, self.load.get(i, 0.0) / 100.0)
                col = _mix(LOAD_LO, LOAD_HI, f ** .8) if i in self.load else \
                    QColor("#9fb4d0" if k == "DC" else "#d4d9e1")
                wd = .8 + 1.6 * f if i in self.load else 1.0
            pen = QPen(col, wd)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(*P[a]), QPointF(*P[b]))
        for i, (x, y) in enumerate(P):
            dc, bad = self.g.kind[i] == "DC", i in self.vbad
            if bad:
                p.setPen(Qt.NoPen)
                c = QColor(AMB); c.setAlphaF(.22)
                p.setBrush(c)
                p.drawEllipse(QPointF(x, y), 9, 9)
            r = 4.0 if bad else 3.2
            if dc and not bad:
                p.setBrush(QColor("#ffffff")); p.setPen(QPen(QColor("#7f9cc4"), 1.6))
            else:
                p.setPen(Qt.NoPen); p.setBrush(QColor(AMB if bad else "#aab3c0"))
            p.drawEllipse(QPointF(x, y), r, r)
        p.end()


class LoadBars(QWidget):
    """선로 부하율 상위 — 가로 막대. 100 % 넘음 = 주황."""

    def __init__(self, sol, t, c, n=5, cap=16, parent=None):
        super().__init__(parent)
        self.c = c
        rows = []
        br = sol.at("Branch", t)
        if br.size:
            iF, iT = _col(sol, "Branch", "From"), _col(sol, "Branch", "To")
            iL, iC = _col(sol, "Branch", "Loading[%]"), _col(sol, "Branch", "Capacity[MVA]")
            rows = [(f"{int(r[iF])}–{int(r[iT])}", float(r[iL])) for r in br
                    if iL >= 0 and checks._rated(r, iC, iL)]
        rows.sort(key=lambda r: -r[1])
        self.all = rows[:cap]
        self.rows = rows[:n]
        # 바닥은 5줄만 — 줄 수는 그릴 때 높이에 맞춰 늘린다. 8줄을 바닥으로 두면 1440 × 900 창에서
        # 개요가 창보다 10 px 커져 스크롤 막대가 생겼다 (2026-11-15)
        self.setMinimumHeight(28 * max(1, min(len(self.rows), 5)))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        if not self.all:
            _empty(p, QRectF(0, 0, w, self.height()), self.c, "—",
                   "부하율을 잴 수 없습니다", "선로에 정격(용량)이 안 적혀 있습니다 — 계통 데이터의 rateA 열에 넣으면 그려집니다")
            p.end(); return
        # 카드 높이만큼 줄 수를 늘리고 줄 간격을 고르게 편다 — 아래 빈 곳을 남기지 않는다
        nfit = max(1, min(len(self.all), int(self.height() // 30)))
        self.rows = self.all[:nfit]
        pitch = self.height() / max(1, nfit)
        mx = max(140.0, max((v for _n, v in self.rows), default=0) * 1.05)
        f = QFont(self.font()); f.setPixelSize(12); p.setFont(f)
        x0, x1 = 74, w - 52
        for k, (name, v) in enumerate(self.rows):
            y = pitch * (k + .5)
            p.setPen(QColor(self.c["muted"]))
            p.drawText(QRectF(0, y - 9, 70, 18), Qt.AlignVCenter | Qt.AlignLeft, name)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(self.c["hair"]))
            p.drawRoundedRect(QRectF(x0, y - 4, x1 - x0, 8), 4, 4)
            p.setBrush(QColor(AMB if v > 100 else self.c["accent"]))
            p.drawRoundedRect(QRectF(x0, y - 4, (x1 - x0) * min(v, mx) / mx, 8), 4, 4)
            p.setPen(QPen(QColor(self.c["muted"]), 1))
            xr = x0 + (x1 - x0) * 100 / mx
            p.drawLine(QPointF(xr, y - 8), QPointF(xr, y + 8))
            p.setPen(QColor(AMB_TEXT if v > 100 else self.c["muted"]))
            p.drawText(QRectF(x1 + 6, y - 9, 46, 18), Qt.AlignVCenter | Qt.AlignRight, f"{v:.0f}%")
        p.end()


def _empty(p, rect, c, mark, title, note):
    """내용이 없는 카드 — 가운데에 표시 하나 · 한 줄 · 까닭 (2026-11-15)."""
    cx, cy = rect.center().x(), rect.center().y()
    p.setPen(Qt.NoPen); p.setBrush(QColor(c["accent_soft"]))
    p.drawEllipse(QPointF(cx, cy - 34), 20, 20)
    f = QFont(p.font()); f.setPixelSize(18); f.setBold(True); p.setFont(f)
    p.setPen(QColor(c["muted"]))
    p.drawText(QRectF(cx - 20, cy - 54, 40, 40), Qt.AlignCenter, mark)
    f.setPixelSize(14); p.setFont(f); p.setPen(QColor(c["text"]))
    p.drawText(QRectF(rect.x(), cy - 6, rect.width(), 22), Qt.AlignCenter, title)
    f.setPixelSize(12); f.setBold(False); p.setFont(f); p.setPen(QColor(c["muted"]))
    p.drawText(QRectF(rect.x() + 12, cy + 18, rect.width() - 24, 40),
               Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, note)


CHART_STYLE = "bars"      # 카드 바탕 — 검은 카드(전압 카드). 그래프 꼴은 아래 `volt_style` 이 버스 수로 고른다
AC_COL, DC_COL = "#ef7f7f", "#7fb2e5"   # 검은 바탕 위 AC 빨강 · DC 파랑 계열 (뜻 색)
SORTED_OVER = 150                       # 버스가 이보다 많으면 높은 순 곡선(G3), 아니면 점 + 선(G1)
NEAR_PU = 0.01                          # 「근접」 = 한계까지 이만큼 안 (임시 기준)


def volt_style(n):
    """2026-11-03 사용자 — 「모선이 150개 이하면 G1 이상이면 G3」."""
    return "sorted" if n > SORTED_OVER else "dots"


class VoltChart(QWidget):
    """버스 전압 — 대시보드 꼴로 직접 그린다(틀 · 범례 상자 없음, 옅은 눈금).

    dots (G1)   = 버스 순서대로 점 + 가는 선, 한계 띠, 위반 = 주황 + 둘레 빛
    sorted (G3) = 버스를 전압 높은 순으로 세운 곡선 + 상한 · 하한 선, 넘음 · 근접 점
    점 색 — AC 빨강 · DC 파랑 계열, 위반 주황.
    """

    def __init__(self, sol, t, c, dark, style=None, parent=None):
        super().__init__(parent)
        self.names, self.vm, self.lo, self.hi, self.kind = charts._bus_table(sol, t)
        self.c, self.dark = c, dark
        self.style = style or volt_style(len(self.names))
        self.setMinimumHeight(160)

    def paintEvent(self, _e):
        n = len(self.names)
        if not n:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        fg = QColor("#f2f2f4") if self.dark else QColor(self.c["text"])
        mute = QColor(255, 255, 255, 120) if self.dark else QColor(self.c["muted"])
        grid = QColor(255, 255, 255, 26) if self.dark else QColor(0, 0, 0, 18)
        L, R, Tp, B = 46, w - 8, 8, h - 24
        top = max(float(self.hi.max()), float(self.vm.max())) + .01
        bot = min(float(self.lo.min()), float(self.vm.min())) - .01

        def Y(v):
            return B - (v - bot) / (top - bot) * (B - Tp)
        f = QFont(self.font()); f.setPixelSize(11); p.setFont(f)
        st = .05 if top - bot > .12 else .02
        for v in np.arange(np.ceil(bot / st) * st, top + 1e-9, st):
            p.setPen(QPen(grid, 1, Qt.DashLine)); p.drawLine(QPointF(L, Y(v)), QPointF(R, Y(v)))
            p.setPen(mute); p.drawText(QRectF(0, Y(v) - 8, L - 8, 16), Qt.AlignRight | Qt.AlignVCenter, f"{v:.2f}")
        bad = [(self.vm[i] > self.hi[i] + 1e-9) or (self.vm[i] < self.lo[i] - 1e-9) for i in range(n)]
        near = [(not bad[i]) and (self.hi[i] - self.vm[i] < NEAR_PU or self.vm[i] - self.lo[i] < NEAR_PU)
                for i in range(n)]

        def kcol(i):
            return QColor(AMB) if bad[i] else QColor(DC_COL if self.kind[i] == "DC" else AC_COL)

        if self.style == "sorted":
            order = sorted(range(n), key=lambda i: -self.vm[i])
            X = (lambda j: L + (R - L) * j / max(1, n - 1))
            # 상한 · 하한 선 — 가장 흔한 한계값(AC 버스 기준)
            for lim, col, txt in ((float(np.median(self.hi)), QColor(AMB), "상한"),
                                  (float(np.median(self.lo)), mute, "하한")):
                p.setPen(QPen(col, 1.2, Qt.DashLine)); p.drawLine(QPointF(L, Y(lim)), QPointF(R, Y(lim)))
                # 곡선이 왼쪽에서 높고 오른쪽에서 낮다 — 상한 이름은 오른쪽, 하한 이름은 왼쪽에 둬야 곡선과 안 겹친다
                box = (QRectF(R - 120, Y(lim) - 17, 118, 14) if txt == "상한" else QRectF(L + 6, Y(lim) + 3, 118, 14))
                p.setPen(col); p.drawText(box, Qt.AlignRight if txt == "상한" else Qt.AlignLeft, f"{txt} {lim:.2f}")
            pts = [QPointF(X(j), Y(self.vm[i])) for j, i in enumerate(order)]
            path = QPainterPath(pts[0])
            for q in pts[1:]:
                path.lineTo(q)
            area = QPainterPath(path)
            area.lineTo(pts[-1].x(), B); area.lineTo(pts[0].x(), B); area.closeSubpath()
            gr = QLinearGradient(0, Tp, 0, B)
            c0 = QColor(fg); c0.setAlpha(70); c1 = QColor(fg); c1.setAlpha(0)
            gr.setColorAt(0, c0); gr.setColorAt(1, c1)
            p.setPen(Qt.NoPen); p.setBrush(QBrush(gr)); p.drawPath(area)
            p.setBrush(Qt.NoBrush); p.setPen(QPen(fg, 2)); p.drawPath(path)
            for j, i in enumerate(order):
                if bad[i] or near[i]:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(AMB) if bad[i] else QColor("#e6b800"))
                    p.drawEllipse(pts[j], 3.6, 3.6)
            names = [self.names[i] for i in order]
            step = max(1, int(np.ceil(40 / ((R - L) / max(1, n)))))
            p.setPen(mute)
            for j in range(0, n, step):
                p.drawText(QRectF(X(j) - 22, B + 4, 44, 16), Qt.AlignCenter, names[j])
            p.end()
            return

        dx = (R - L) / n
        X = (lambda i: L + dx * (i + .5))
        band = QColor(255, 255, 255, 16) if self.dark else QColor(46, 61, 87, 14)
        p.setPen(Qt.NoPen); p.setBrush(band)
        for i in range(n):
            p.drawRect(QRectF(L + dx * i, Y(self.hi[i]), dx + .5, Y(self.lo[i]) - Y(self.hi[i])))
        pts = [QPointF(X(i), Y(self.vm[i])) for i in range(n)]
        line = QColor(fg); line.setAlpha(90)
        p.setPen(QPen(line, 1.2)); p.setBrush(Qt.NoBrush)
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)
        r0 = max(2.2, min(4.0, dx * .32))
        for i in range(n):
            p.setPen(Qt.NoPen)
            if bad[i]:
                halo = QColor(AMB); halo.setAlpha(60)
                p.setBrush(halo); p.drawEllipse(pts[i], r0 * 2.4, r0 * 2.4)
            p.setBrush(kcol(i)); p.drawEllipse(pts[i], r0 * (1.25 if bad[i] else 1), r0 * (1.25 if bad[i] else 1))
        step = max(1, int(np.ceil(34 / dx)))
        p.setPen(mute)
        for i in range(0, n, step):
            p.drawText(QRectF(X(i) - 20, B + 4, 40, 16), Qt.AlignCenter, self.names[i])
        p.end()


def _legend_chip(color, text, c, dark):
    w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(5)
    dot = QFrame(); dot.setFixedSize(9, 9)
    dot.setStyleSheet(f"background:{color}; border-radius:4px;")
    h.addWidget(dot, 0, Qt.AlignVCenter)
    h.addWidget(_label(text, 12, "rgba(255,255,255,.65)" if dark else c["muted"]))
    return w


class ViolTable(QWidget):
    """살펴볼 곳 — 상태 · 종류 · 대상 · 값 · 한계 · 넘은 양 · 여유 · 넘은 비율 막대. 줄을 누르면 그 카드가 커진다."""
    COLS = (("상태", 0.0), ("종류", .09), ("대상", .19), ("값", .35), ("한계", .52), ("넘은 양 · 여유", .64), ("넘은 비율", .82))
    STATE = {"넘음": AMB, "도달": "#e6b800", "근접": "#e6b800"}

    def __init__(self, rows, c, on_pick=None, parent=None, kind_col=True):
        super().__init__(parent)
        self.rows, self.c, self.on_pick = rows, c, on_pick
        self.kind_col = kind_col
        self.setCursor(Qt.PointingHandCursor if rows else Qt.ArrowCursor)
        # 6줄에서 끊기면 「+ N건 더」 한 줄 자리(22 px)를 더 잡는다 — 안 잡으면 그 줄이 카드 밖으로 밀려 안 보였다
        self.setMinimumHeight(28 + 34 * max(3, min(len(rows), 6)) + (22 if len(rows) > 6 else 0))

    def mousePressEvent(self, e):
        k = int((e.position().y() - 28) // 34)
        if self.on_pick and 0 <= k <= len(self.rows):     # 「+ N건 더」 줄도 누를 수 있다
            self.on_pick(self.rows[min(k, len(self.rows) - 1)] if self.rows else None)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        f = QFont(self.font()); f.setPixelSize(11); f.setBold(True); p.setFont(f)
        p.setPen(QColor(self.c["muted"]))
        cols = self.COLS if self.kind_col else (("상태", 0.0), ("대상", .12), ("값", .31), ("한계", .50),
                                                ("넘은 양 · 여유", .64), ("넘은 비율", .82))
        xs, ws = ((.19, .35, .52, .64), (.16, .17, .12, .18)) if self.kind_col else \
                 ((.12, .31, .50, .64), (.19, .19, .14, .18))
        for name, x in cols:
            p.drawText(QRectF(w * x + 6, 0, 120, 22), Qt.AlignVCenter | Qt.AlignLeft, name)
        if not self.rows:
            # 빈 표를 왼쪽 위 한 줄로 두면 큰 빈 카드로 보였다(2026-11-15) — 가운데에 «다 괜찮다» 로 적는다
            _empty(p, QRectF(0, 22, w, self.height() - 22), self.c, "✓",
                   "살펴볼 곳이 없습니다", "한계를 넘거나 한계에 가까운 버스 · 선로 · 설비가 없습니다")
            p.end(); return
        f.setBold(False); f.setPixelSize(13); p.setFont(f)
        nfit = max(0, (self.height() - 28) // 34)
        for k, (state, kind, name, val, lim, ex, ratio) in enumerate(self.rows[:nfit]):
            y = 28 + k * 34
            p.setPen(QPen(QColor(self.c["hair"]), 1))
            p.drawLine(QPointF(0, y), QPointF(w, y))
            cy = y + 17
            sc = QColor(self.STATE.get(state, AMB))
            soft = QColor(sc); soft.setAlpha(40)
            ff = QFont(f); ff.setPixelSize(11); ff.setBold(True); p.setFont(ff)
            # 넘음 = 채운 칩 · 도달 · 근접 = 테두리만 — 주황과 노랑이 가까워 색만으로는 안 갈렸다 (2026-11-15)
            if state == "넘음":
                p.setPen(Qt.NoPen); p.setBrush(soft)
            else:
                p.setPen(QPen(sc, 1)); p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(4.5, cy - 9.5, 41, 19), 7, 7)
            dark_bg = QColor(self.c["surface"]).lightness() < 128
            p.setPen(QColor(AMB if dark_bg else AMB_TEXT) if state == "넘음"
                     else QColor("#e6b800" if dark_bg else "#8a6d00"))
            p.drawText(QRectF(4, cy - 10, 42, 20), Qt.AlignCenter, state)
            ff.setBold(False); p.setFont(ff)
            if self.kind_col:
                p.setPen(Qt.NoPen); p.setBrush(QColor(self.c["accent_soft"]))
                p.drawRoundedRect(QRectF(w * .09 + 4, cy - 10, 44, 20), 7, 7)
                p.setPen(QColor(self.c["muted"]))
                p.drawText(QRectF(w * .09 + 4, cy - 10, 44, 20), Qt.AlignCenter, kind)
            p.setFont(f)
            for txt, x, col, ww in ((name, xs[0], self.c["text"], ws[0]), (val, xs[1], self.c["text"], ws[1]),
                                    (lim, xs[2], self.c["muted"], ws[2]),
                                    (ex, xs[3], (AMB if dark_bg else AMB_TEXT) if state == "넘음"
                                     else ("#e6b800" if dark_bg else "#8a6d00"), ws[3])):
                p.setPen(QColor(col))
                p.drawText(QRectF(w * x + 6, cy - 10, w * ww, 20), Qt.AlignVCenter | Qt.AlignLeft, txt)
            if state == "넘음":
                bx, bw = w * .82 + 6, w * .16
                p.setPen(Qt.NoPen); p.setBrush(QColor(self.c["hair"]))
                p.drawRoundedRect(QRectF(bx, cy - 3, bw, 6), 3, 3)
                p.setBrush(QColor(AMB))
                p.drawRoundedRect(QRectF(bx, cy - 3, bw * min(1.0, max(.06, ratio * 2.2)), 6), 3, 3)
        if len(self.rows) > nfit:
            p.setPen(QColor(self.c["muted"]))
            p.drawText(QRectF(6, 28 + nfit * 34, w, 20), Qt.AlignVCenter | Qt.AlignLeft,
                       f"+ {len(self.rows) - nfit}건 더 — 누르면 전부 보입니다")
        p.end()


# ── 카드 틀 ─────────────────────────────────────────────────────────
def _card(c, dark_card=False):
    f = QFrame()
    f.setObjectName("ovcard")
    bg = "#15171c" if dark_card else c["surface"]
    # 어두운 화면에서는 검은 카드가 다른 카드와 안 갈렸다 (2026-11-15) — 더 검게 + 옅은 테두리
    on_dark = QColor(c["surface"]).lightness() < 128
    if dark_card and on_dark:
        f.setStyleSheet("#ovcard { background:#101012; border:1px solid rgba(255,255,255,.14); border-radius:16px; }")
        bg = None
    if bg is not None:
        # 2026-11-15 — 흰 판 + 가는 테두리(진한 카드는 테두리 없이). 그림자는 아주 옅게.
        edge = "" if dark_card else f"border:1px solid {c['border']};"
        f.setStyleSheet(f"#ovcard {{ background:{bg}; {edge} border-radius:16px; }}")
    sh = QGraphicsDropShadowEffect(f)
    sh.setBlurRadius(22); sh.setOffset(0, 6)
    sh.setColor(QColor(0, 0, 0, 60 if on_dark else 11))
    f.setGraphicsEffect(sh)
    return f


def _label(text, size, color, bold=False):
    lb = QLabel(text)
    lb.setStyleSheet(f"color:{color}; font-size:{size}px; font-weight:{700 if bold else 400};"
                     "background:transparent;")
    return lb


def _kpi(c, title, value, note, warn, icon, ok=False):
    f = _card(c)
    f.setFixedHeight(92)
    h = QHBoxLayout(f)
    h.setContentsMargins(20, 14, 18, 14)
    v = QVBoxLayout(); v.setSpacing(2)
    v.addWidget(_label(title, 13, c["muted"], True))
    row = QHBoxLayout(); row.setSpacing(8)
    row.addWidget(_label(value, 24, c["text"], True))
    nl = _label(note, 13, AMB_TEXT if warn else c["muted"], True)
    # 좁은 창에서 이 글의 폭이 카드 최소 폭이 되어 오른쪽 카드가 창 밖으로 밀렸다 (2026-11-15) —
    # 폭을 요구하지 않게 한다(모자라면 글 끝이 잘리고, 전체는 풍선말에 있다)
    nl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    row.addWidget(nl, 1, Qt.AlignBottom)
    v.addLayout(row)
    h.addLayout(v, 1)
    sq = QLabel(icon)
    sq.setFixedSize(46, 46)
    sq.setAlignment(Qt.AlignCenter)
    # 2026-11-15 — 그라데이션 네모를 걷고 **옅은 바탕 + 진한 기호**로(상태는 색으로만 가른다)
    on_dark = QColor(c["surface"]).lightness() < 128
    if warn:
        tint, fg = ("rgba(245,163,0,.20)", AMB) if on_dark else ("#fff1d6", AMB_TEXT)
    elif ok:
        tint, fg = ("rgba(48,209,88,.18)", c["ok"]) if on_dark else ("#e2f4e9", c["ok"])
    else:
        tint, fg = c["accent_soft"], c["muted"]
    sq.setStyleSheet(f"background:{tint}; color:{fg}; border-radius:12px; font-size:18px; font-weight:700;")
    h.addWidget(sq)
    f.setToolTip(f"{title} — {value} {note}")
    # 창이 좁으면 글이 잘렸다(1100 px 창에서 「발전기 0 · 변환기 0/7」) — 그때는 아이콘 자리를 글에 준다
    f.resizeEvent = lambda e, s=sq, fr=f: s.setVisible(fr.width() >= 236)
    return f


def page(app):
    """개요 화면 — `app` 은 Proto(창). 쓰는 것: c · sol · t · 콜백 몇 개."""
    c, sol, t = app.c, app.sol, app.t
    s = summary(sol, t)
    nviol = s["n_v"] + s["n_l"]

    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(18); g.setVerticalSpacing(18)

    # ── 숫자 카드 넷
    top = s["top"]
    # 실무자가 결과를 받으면 보는 차례 (2026-11-03 V2) — ① 수렴 ② 전압 ③ 열 용량 ④ 설비 한계
    conv_ok = s["converged"]
    mis = f"불평형 {s['mis']:.1e}" if s["mis"] is not None else ""
    n_dev = s["n_gen_lim"] + s["n_ic_lim"]
    kp = [
        _kpi(c, "① 수렴", f"{s['iters']} 회" if s["iters"] else "—", mis or "반복 기록 없음",
             not conv_ok, "✓" if conv_ok else "!", ok=conv_ok),
        _kpi(c, "② 버스 전압", f"{s['n_v']} 곳", f"넘음 · 근접 {s['n_near']}", s["n_v"] > 0, "↕",
             ok=(s["n_v"] == 0 and s["n_near"] == 0)),
        _kpi(c, "③ 열 용량", f"{s['n_l']} 곳" if top else "—",
             f"넘음 · 최대 {top[0]:.0f} %" if top else "선로 정격이 안 적힘", s["n_l"] > 0, "≡",
             ok=bool(top) and s["n_l"] == 0),
        _kpi(c, "④ 설비 한계", f"{n_dev} 대",
             f"발전기 {s['n_gen_lim']} · 변환기 {s['n_ic_lim']}/{s['n_ic']}" if s["n_ic"] else f"발전기 {s['n_gen_lim']}",
             n_dev > 0, "⚙", ok=(n_dev == 0)),
    ]
    krow = QHBoxLayout(); krow.setSpacing(18)
    for k in kp:
        krow.addWidget(k, 1)
    g.addLayout(krow, 0, 0, 1, 2)

    # ── 위반 목록
    tc = _card(c)
    tv = QVBoxLayout(tc); tv.setContentsMargins(20, 16, 20, 12); tv.setSpacing(8)
    th = QHBoxLayout()
    th.addWidget(_label("살펴볼 곳", 15, c["text"], True)); th.addStretch()
    # 카드마다 세는 것이 달라 보였다(「8건 위반」 · 「근접 9」 · 「11건 더」) — 여기서 셋을 한 줄로 밝힌다
    th.addWidget(_label(f"넘음 {nviol} · 한계 도달 {s['n_reach']} · 근접 {s['n_near']}  —  줄을 누르면 전부", 13, c["muted"]))
    tv.addLayout(th)
    tv.addWidget(ViolTable(s["work"], c, on_pick=lambda _r: app.open_card("viol")), 1)
    g.addWidget(tc, 1, 0)

    # ── 요약 카드(잘린 계통도 위에 글)
    sc = _card(c)
    sc.setMinimumHeight(264)
    mini = TopoMini(sol, t, sc)
    sv = QVBoxLayout(sc); sv.setContentsMargins(20, 16, 20, 16); sv.setSpacing(2)
    sv.addWidget(_label(f"{nviol}건 위반" if nviol else "위반 없음", 19, c["text"], True))
    sv.addWidget(_label("한계를 넘은 곳 · 가장 큰 것부터" if nviol else "모든 버스 · 선로가 한계 안",
                        13, c["muted"]))
    sv.addSpacing(12)
    if s["rows"]:
        k0, nm, val, *_ = s["rows"][0]
        sv.addWidget(_label(f"{nm}  <span style='color:{AMB_TEXT}'>{val}</span>", 20, c["text"], True))
        sv.addWidget(_label("가장 많이 넘은 " + ("선로" if k0 == "선로" else "버스 전압"), 13, c["muted"]))
    elif top:
        sv.addWidget(_label(f"{top[1]}  {top[0]:.0f} %", 20, c["text"], True))
        sv.addWidget(_label("가장 무거운 선로", 13, c["muted"]))
    sv.addSpacing(10)
    gk = T.build_graph(sol)
    nb_ac = sum(k == "AC" for k in gk.kind); nb_dc = sum(k == "DC" for k in gk.kind)
    n_icn = sum(k == "IC" for _a, _b, k in gk.edges)
    parts = [f"AC {nb_ac}"] + ([f"DC {nb_dc}"] if nb_dc else []) + ([f"IC {n_icn}"] if n_icn else [])
    sv.addWidget(_label(" · ".join(parts), 18, c["text"], True))
    sv.addWidget(_label("계통 구성" + (" · 그림은 묶어서 줄임" if mini.coarse else ""), 13, c["muted"]))
    sv.addSpacing(10)
    leg = QWidget(); lh = QHBoxLayout(leg); lh.setContentsMargins(0, 0, 0, 0); lh.setSpacing(6)
    lh.addWidget(_label("선 색 = 부하율", 12, c["muted"]))
    bar = QFrame(); bar.setFixedSize(60, 6)
    bar.setStyleSheet(f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {LOAD_LO}, stop:1 {LOAD_HI});"
                      "border-radius:3px;")
    lh.addWidget(bar, 0, Qt.AlignVCenter); lh.addWidget(_label("100 %", 12, c["muted"])); lh.addStretch()
    sv.addWidget(leg)
    sv.addStretch()
    go = QPushButton("계통도 보기 ↗")
    go.setCursor(Qt.PointingHandCursor)
    go.setStyleSheet(f"QPushButton {{ background:{c['accent']}; color:{c['on_accent']}; border:none;"
                     "border-radius:9px; padding:7px 14px; font-weight:600; font-size:13px; }")
    go.clicked.connect(lambda: app.open_card("topo"))
    sv.addWidget(go, 0, Qt.AlignLeft)
    sc.resizeEvent = lambda e, m=mini, f=sc: m.setGeometry(0, 0, f.width(), f.height())
    mini.lower()
    g.addWidget(sc, 1, 1)

    # ── 버스 전압 그래프(검은 카드)
    dk = CHART_STYLE == "bars"
    vc = _card(c, dark_card=dk)
    vv = QVBoxLayout(vc); vv.setContentsMargins(20, 16, 20, 12); vv.setSpacing(2)
    vh = QHBoxLayout(); vh.setSpacing(14)
    vh.addWidget(_label("버스 전압", 15, "#f2f2f4" if dk else c["text"], True)); vh.addStretch()
    _bt = charts._bus_table(sol, t)
    vstyle = volt_style(len(_bt[0]))
    if vstyle == "dots":     # 높은 순 곡선(G3)에는 AC · DC 색이 없다 — 범례에도 안 낸다
        if any(k == "AC" for k in _bt[4]):
            vh.addWidget(_legend_chip(AC_COL, "AC", c, dk))
        if any(k == "DC" for k in _bt[4]):
            vh.addWidget(_legend_chip(DC_COL, "DC", c, dk))
    vh.addWidget(_legend_chip(AMB, "위반", c, dk))
    if vstyle == "sorted":
        vh.addWidget(_legend_chip("#e6b800", "근접", c, dk))
    else:
        vh.addWidget(_legend_chip("rgba(255,255,255,.18)" if dk else "rgba(46,61,87,.16)", "한계 안", c, dk))
    vv.addLayout(vh)
    sub = (f"높은 순으로 줄 세움 · 넘음 {s['n_v']} · 근접 {s['n_near']}" if vstyle == "sorted"
           else f"{s['vmin']:.3f} – {s['vmax']:.3f} pu · 버스 순서대로")
    vv.addWidget(_label(sub, 13, "rgba(255,255,255,.55)" if dk else c["muted"]))
    vv.addSpacing(6)
    vv.addWidget(VoltChart(sol, t, c, dk), 1)
    g.addWidget(vc, 2, 0)

    # ── 부하율 상위
    lc = _card(c)
    lv = QVBoxLayout(lc); lv.setContentsMargins(20, 16, 20, 14); lv.setSpacing(4)
    lv.addWidget(_label("선로 부하율", 15, c["text"], True))
    lv.addWidget(_label(f"<span style='color:{AMB_TEXT};font-weight:700'>{s['n_l']}곳</span> 이 100 % 넘음 · 높은 것부터"
                        if s["n_l"] else "100 % 넘은 선로 없음 · 높은 것부터", 13, c["muted"]))
    lv.addSpacing(6)
    lv.addWidget(LoadBars(sol, t, c, 8), 1)
    det = QPushButton("그래프 · 표 자세히 →")
    det.setCursor(Qt.PointingHandCursor)
    det.setStyleSheet(f"QPushButton {{ background:transparent; color:{c['muted']}; border:none;"
                      "font-size:13px; font-weight:600; text-align:right; }")
    det.clicked.connect(lambda: app.open_card("load"))
    lv.addWidget(det, 0, Qt.AlignRight)
    g.addWidget(lc, 2, 1)

    # 카드를 누르면 자세한 화면으로 (M1 · 2026-11-03) — 카드가 커지는 움직임은 app.open_card
    cards = {"viol": tc, "topo": sc, "volt": vc, "load": lc,
             "conv": kp[0], "kvolt": kp[1], "kload": kp[2], "kdev": kp[3]}
    app._ov_cards = cards
    for key, fr in cards.items():
        fr.setCursor(Qt.PointingHandCursor)
        fr.mousePressEvent = (lambda e, k=key: app.open_card(k) if e.button() == Qt.LeftButton else None)
    g.setColumnStretch(0, 61); g.setColumnStretch(1, 39)
    # 위 줄은 내용 높이(표 6줄 · 요약 카드)만, 남는 높이는 아래 그래프 줄에 준다
    g.setRowStretch(1, 0); g.setRowStretch(2, 1)
    return w


# ── 점검 화면 (2026-11-15) ────────────────────────────────────────
class _EmptyBox(QWidget):
    """내용이 없는 칸 — 가운데 표시 + 한 줄 + 까닭."""

    def __init__(self, c, mark, title, note, parent=None):
        super().__init__(parent)
        self.c, self.args = c, (mark, title, note)
        self.setMinimumHeight(150)

    def paintEvent(self, _e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        _empty(p, QRectF(self.rect()), self.c, *self.args)
        p.end()


NEAR_LOAD = 90.0        # 선로 「근접」 = 부하율이 이 값(%) 이상 100 % 미만 (임시 기준 · 전압의 NEAR_PU 와 짝)


class NearChips(QWidget):
    """근접한 버스 · 선로를 **칩 줄**로 — 줄 수를 정해 두고 넘치면 「+ N」 (2026-11-15).

    근접 9곳을 표 9줄로 늘어놓으니 넘은 5곳보다 자리를 더 먹고, 옆 그래프가 세로로 길쭉해졌다.
    """
    H = 26

    def __init__(self, items, c, lines=2, parent=None):
        super().__init__(parent)
        self.items, self.c, self.lines = list(items), c, lines
        self.setFixedHeight(self.H * lines)

    def paintEvent(self, _e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        f = QFont(self.font()); f.setPixelSize(12); p.setFont(f)
        fm = p.fontMetrics()
        dark_bg = QColor(self.c["surface"]).lightness() < 128
        edge, txt = QColor("#e6b800"), QColor("#e6b800" if dark_bg else "#8a6d00")
        x, line, w = 0.0, 0, self.width()
        for k, t in enumerate(self.items):
            tw = fm.horizontalAdvance(t) + 20
            rest = len(self.items) - k
            more_w = fm.horizontalAdvance(f"+ {rest}") + 16
            if x + tw > w:
                x, line = 0.0, line + 1
            last = line == self.lines - 1
            if line >= self.lines or (last and rest > 1 and x + tw + 6 + more_w > w):
                p.setPen(QColor(self.c["muted"]))
                p.drawText(QRectF(x, min(line, self.lines - 1) * self.H, more_w + 20, 22),
                           Qt.AlignVCenter | Qt.AlignLeft, f"+ {rest}")
                break
            r = QRectF(x + .5, line * self.H + .5, tw - 1, 21)
            p.setPen(QPen(edge, 1)); p.setBrush(Qt.NoBrush); p.drawRoundedRect(r, 9, 9)
            p.setPen(txt); p.drawText(r, Qt.AlignCenter, t)
            x += tw + 6
        p.end()


def _section(c, title, count, warn):
    """점검 화면의 카드 하나 — 제목 + 건수 칩. (카드, 안 세로 배치)를 돌려준다."""
    f = _card(c)
    v = QVBoxLayout(f); v.setContentsMargins(20, 16, 20, 16); v.setSpacing(10)
    h = QHBoxLayout(); h.setSpacing(8)
    h.addWidget(_label(title, 15, c["text"], True))
    on_dark = QColor(c["surface"]).lightness() < 128
    if warn:
        bg, fg = ("rgba(245,163,0,.20)", AMB) if on_dark else ("#fff1d6", AMB_TEXT)
    else:
        bg, fg = c["accent_soft"], c["muted"]
    chip = QLabel(f"{count}건")
    chip.setStyleSheet(f"background:{bg}; color:{fg}; border-radius:9px; padding:2px 9px;"
                       "font-size:12px; font-weight:700;")
    h.addWidget(chip); h.addStretch()
    v.addLayout(h)
    return f, v


def check_board(app):
    """점검 화면 — 숫자 표만 있던 것을 개요와 같은 꼴로: 숫자 카드 넷 · 넘은 비율 막대 · 전압 그래프 · 부하율 막대.

    쓰는 값은 개요(`summary`)와 점검 표(`app.viol()`)가 쓰던 것 그대로다. 알림 카드(탭 자동 조정 등)는
    `app.check_page(parts="notes")` 를 아래에 붙인다.
    """
    c, sol, t = app.c, app.sol, app.t
    s = summary(sol, t)
    viol = app.viol()
    vrows = [r for r in s["work"] if r[0] == "넘음" and r[1] == "전압"]
    lrows = [r for r in s["work"] if r[0] == "넘음" and r[1] == "선로"]
    near = [r for r in s["work"] if r[0] == "근접"]
    top = s["top"]

    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(18); g.setVerticalSpacing(18)
    row = 0

    # (시간 고르개는 제목 줄 오른쪽에 있다 — `app.page_head`)

    # ── 숫자 카드 넷
    kp = [
        _kpi(c, "전압 위반", f"{len(vrows)} 곳",
             f"최대 {vrows[0][5]} pu" if vrows else f"근접 {len(near)}", bool(vrows), "↕", ok=not vrows),
        _kpi(c, "과부하 선로", f"{len(lrows)} 곳" if top else "—",
             f"최대 {top[0]:.0f} %" if top else "선로 정격이 안 적힘", bool(lrows), "≡",
             ok=bool(top) and not lrows),
        _kpi(c, "변환기 한계", f"{s['n_ic_lim']} 대",
             f"변환기 {s['n_ic']}대 중" if s["n_ic"] else "변환기 없음", s["n_ic_lim"] > 0, "⇄",
             ok=s["n_ic"] > 0 and s["n_ic_lim"] == 0),
        _kpi(c, "발전기 한계", f"{s['n_gen_lim']} 대", "출력 한계에 닿은 발전기", s["n_gen_lim"] > 0, "⚙",
             ok=s["n_gen_lim"] == 0),
    ]
    krow = QHBoxLayout(); krow.setSpacing(18)
    for k in kp:
        krow.addWidget(k, 1)
    g.addLayout(krow, row, 0, 1, 2); row += 1

    def rows_or_empty(lay, rows, near_items, near_note, mark, title, note):
        """넘은 것 = 표 줄(막대) · 근접한 것 = 칩 두 줄. 둘 다 없으면 가운데에 ✓."""
        if not rows and not near_items:
            lay.addWidget(_EmptyBox(c, mark, title, note), 1)
            return
        if rows:
            vt = ViolTable(rows, c, kind_col=False)
            vt.setFixedHeight(28 + 34 * len(rows) + 6)
            vt.setCursor(Qt.ArrowCursor)
            lay.addWidget(vt)
        else:
            lay.addWidget(_label(f"✓  {title}", 13, c["muted"], True))
        if near_items:
            lay.addSpacing(4)
            lay.addWidget(_label(f"근접 {len(near_items)}곳  ·  {near_note}", 12, c["muted"], True))
            lay.addWidget(NearChips(near_items, c, 2))
        lay.addStretch(1)

    # ── 전압 : 왼쪽 = 넘은 버스(막대) + 근접 칩 · 오른쪽 = 버스 전압 그래프(진한 카드)
    f, lay = _section(c, "전압 위반", len(vrows), bool(vrows))
    rows_or_empty(lay, vrows, [f"{r[2]}  {r[3].replace(' pu', '')}" for r in near],
                  f"한계까지 {NEAR_PU:g} pu 안", "✓", "전압이 모두 한계 안입니다",
                  "한계를 넘거나 한계에 가까운 버스가 없습니다")
    g.addWidget(f, row, 0)
    dk = CHART_STYLE == "bars"
    vc = _card(c, dark_card=dk)
    vv = QVBoxLayout(vc); vv.setContentsMargins(20, 16, 20, 12); vv.setSpacing(2)
    vh = QHBoxLayout(); vh.setSpacing(14)
    vh.addWidget(_label("버스 전압", 15, "#f2f2f4" if dk else c["text"], True)); vh.addStretch()
    _bt = charts._bus_table(sol, t)
    if volt_style(len(_bt[0])) == "dots":
        if any(k == "AC" for k in _bt[4]):
            vh.addWidget(_legend_chip(AC_COL, "AC", c, dk))
        if any(k == "DC" for k in _bt[4]):
            vh.addWidget(_legend_chip(DC_COL, "DC", c, dk))
    vh.addWidget(_legend_chip(AMB, "위반", c, dk))
    vv.addLayout(vh)
    vv.addWidget(_label(f"{s['vmin']:.3f} – {s['vmax']:.3f} pu", 13, "rgba(255,255,255,.55)" if dk else c["muted"]))
    vv.addSpacing(6)
    ch = VoltChart(sol, t, c, dk); ch.setMinimumHeight(210)
    vv.addWidget(ch, 1)
    g.addWidget(vc, row, 1); row += 1

    # ── 선로 : 왼쪽 = 넘은 선로(막대) + 근접 칩 · 오른쪽 = 부하율 높은 순
    f, lay = _section(c, "과부하 선로", len(lrows), bool(lrows))
    if top:
        lb = LoadBars(sol, t, c, 8)
        near_l = [f"{n}  {v:.0f} %" for n, v in LoadBars(sol, t, c, 999, cap=10_000).all
                  if NEAR_LOAD <= v < 100.0]
        rows_or_empty(lay, lrows, near_l, f"부하율 {NEAR_LOAD:g} % 이상", "✓", "과부하 선로가 없습니다",
                      f"가장 무거운 선로 {top[1]} 가 {top[0]:.0f} % 입니다")
        g.addWidget(f, row, 0)
        lc = _card(c)
        lv = QVBoxLayout(lc); lv.setContentsMargins(20, 16, 20, 14); lv.setSpacing(4)
        lv.addWidget(_label("선로 부하율", 15, c["text"], True))
        lv.addWidget(_label("높은 것부터 · 세로선 = 100 %", 13, c["muted"]))
        lv.addSpacing(6)
        lb.setMinimumHeight(30 * 6)
        lv.addWidget(lb, 1)
        g.addWidget(lc, row, 1)
    else:                # 정격이 없으면 오른쪽 막대 카드도 같은 말만 한다 — 한 칸으로 넓게
        eb = _EmptyBox(c, "—", "부하율을 잴 수 없습니다",
                       "선로에 정격(용량)이 안 적혀 있습니다 — 계통 데이터의 rateA 열에 넣으면 판정합니다")
        eb.setMinimumHeight(130)
        lay.addWidget(eb, 1)
        g.addWidget(f, row, 0, 1, 2)
    row += 1

    # ── 설비 한계 : 변환기 · 발전기 (없으면 한 줄짜리 낮은 카드 — 빈 카드가 크면 화면이 비어 보인다)
    for col, name, mark_ok in ((0, "변환기 한계", "한계에 닿은 변환기가 없습니다"),
                               (1, "발전기 한계", "한계에 닿은 발전기가 없습니다")):
        cols, rows = viol.get(name, ([], []))
        f, lay = _section(c, name, len(rows), bool(rows))
        if rows:
            tb = _table(c, list(cols), rows)
            tb.verticalHeader().setDefaultSectionSize(30)
            tb.setFixedHeight(40 + 30 * len(rows))
            tb.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            lay.addWidget(tb); lay.addStretch(1)
        else:
            lay.addWidget(_label(f"<span style='color:{c['ok']}'>✓</span>&nbsp;&nbsp;{mark_ok}", 13, c["muted"]))
        g.addWidget(f, row, col, Qt.AlignTop)
    row += 1

    # ── 알림(탭 자동 조정 · 무효 한계 안내 · 정격 없는 선로)
    notes = app.check_page(parts="notes")
    if notes is not None:
        g.addWidget(notes, row, 0, 1, 2); row += 1

    g.setColumnStretch(0, 1); g.setColumnStretch(1, 1)     # 좌우 반반 — 표와 그래프가 같은 폭
    g.setRowStretch(row, 1)
    return w


# ── 다이나믹 개요 (2026-11-15) ────────────────────────────────────
# 사용자: 「다이나믹 개요」. 여러 시각을 푼 결과에서 **언제 · 어디가** 한계를 넘는지 한 화면에 보인다.
# 스냅샷 개요(`page`)와 같은 꼴이고, 시각마다의 값은 `summary(sol, t)` 를 그대로 쓴다.
def _hour_step(n, room, need=26):
    """가로 눈금 글자를 몇 칸마다 찍을지 — 글자가 겹치지 않게."""
    return max(1, int(np.ceil(n * need / max(1.0, room))))


class HeatRows(QWidget):
    """시간대별 위반 — 가로 = 시각 · 세로 = 버스 · 선로. 칸이 진할수록 많이 넘었다. 칸을 누르면 그 시각으로."""
    LBL, RH, TOP = 120, 26, 22

    def __init__(self, keys, cells, n_t, c, on_pick=None, mark=None, parent=None):
        super().__init__(parent)
        self.keys, self.cells, self.n_t, self.c = keys, cells, n_t, c
        self.on_pick, self.mark = on_pick, mark
        self.setMinimumHeight(self.TOP + self.RH * len(keys) + 4)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def _hit(self, pos):
        cw = (self.width() - self.LBL) / max(1, self.n_t)
        k = int((pos.x() - self.LBL) // cw) if pos.x() >= self.LBL else -1
        r = int((pos.y() - self.TOP) // self.RH)
        return (k if 0 <= k < self.n_t else -1), (r if 0 <= r < len(self.keys) else -1)

    def mouseMoveEvent(self, e):
        k, r = self._hit(e.position())
        if k < 0:
            self.setToolTip(""); return
        tip = f"{k + 1} H — 누르면 이 시각의 개요로"
        if r >= 0:
            cell = self.cells[self.keys[r]][k]
            tip = f"{self.keys[r][1]} · {k + 1} H\n" + (f"{cell[1]}  ({cell[2]})" if cell else "한계 안") + "\n누르면 이 시각의 개요로"
        self.setToolTip(tip)

    def mousePressEvent(self, e):
        k, _r = self._hit(e.position())
        if k >= 0 and self.on_pick and e.button() == Qt.LeftButton:
            self.on_pick(k)

    def paintEvent(self, _e):
        c = self.c
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        W = self.width()
        cw = (W - self.LBL) / max(1, self.n_t)
        f = QFont(self.font()); f.setPixelSize(11); p.setFont(f)
        step = _hour_step(self.n_t, W - self.LBL)
        p.setPen(QColor(c["muted"]))
        for k in range(0, self.n_t, step):
            p.drawText(QRectF(self.LBL + k * cw, 0, cw, 18), Qt.AlignCenter, f"{k + 1}")
        if self.mark is not None:                    # 가장 나쁜 시각 — 세로 띠
            p.setPen(Qt.NoPen); p.setBrush(QColor(c["accent_soft"]))
            p.drawRoundedRect(QRectF(self.LBL + self.mark * cw, self.TOP - 2, cw,
                                     self.RH * len(self.keys) + 4), 6, 6)
        f.setPixelSize(12); p.setFont(f)
        for r, key in enumerate(self.keys):
            y = self.TOP + r * self.RH
            p.setPen(QColor(c["text"]))
            p.drawText(QRectF(2, y, self.LBL - 10, self.RH), Qt.AlignVCenter | Qt.AlignLeft,
                       key[1] + ("  선로" if key[0] == "선로" else ""))
            p.setPen(Qt.NoPen)
            for k, cell in enumerate(self.cells[key]):
                rc = QRectF(self.LBL + k * cw + 1.5, y + 3.5, cw - 3, self.RH - 7)
                if cell:
                    col = QColor(AMB); col.setAlphaF(min(1.0, 0.30 + cell[0] * 2.2))
                else:
                    col = QColor(c["hair"])
                p.setBrush(col); p.drawRoundedRect(rc, 4, 4)
        p.end()


class EnvChart(QWidget):
    """시간대별 버스 전압 범위 — 그 시각의 가장 높은 · 가장 낮은 버스 전압 사이를 띠로. 넘은 시각은 주황 점."""

    def __init__(self, vmin, vmax, bad, lo, hi, c, dark, on_pick=None, parent=None):
        super().__init__(parent)
        self.vmin, self.vmax, self.bad, self.lo, self.hi = vmin, vmax, bad, lo, hi
        self.c, self.dark, self.on_pick = c, dark, on_pick
        self.setMinimumHeight(200)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    L, T_, R_, B = 46, 10, 14, 24

    def _k(self, x):
        n = len(self.vmax)
        w = self.width() - self.L - self.R_
        k = int(round((x - self.L) / max(1.0, w) * (n - 1))) if n > 1 else 0
        return max(0, min(n - 1, k))

    def mouseMoveEvent(self, e):
        k = self._k(e.position().x())
        self.setToolTip(f"{k + 1} H · {self.vmin[k]:.4f} – {self.vmax[k]:.4f} pu\n누르면 이 시각의 개요로")

    def mousePressEvent(self, e):
        if self.on_pick and e.button() == Qt.LeftButton:
            self.on_pick(self._k(e.position().x()))

    def paintEvent(self, _e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        n = len(self.vmax)
        fg = QColor("#f2f2f4") if self.dark else QColor(self.c["text"])
        dim = QColor(255, 255, 255, 110) if self.dark else QColor(self.c["muted"])
        grid = QColor(255, 255, 255, 26) if self.dark else QColor(self.c["hair"])
        L, T_, R_, B = self.L, self.T_, self.R_, self.B
        w, h = self.width() - L - R_, self.height() - T_ - B
        y0 = min([min(self.vmin)] + ([self.lo] if self.lo is not None else [])) - 0.01
        y1 = max([max(self.vmax)] + ([self.hi] if self.hi is not None else [])) + 0.01
        X = lambda k: L + (w * k / (n - 1) if n > 1 else w / 2)
        Y = lambda v: T_ + h * (y1 - v) / (y1 - y0)
        f = QFont(self.font()); f.setPixelSize(11); p.setFont(f)
        for i in range(5):
            v = y0 + (y1 - y0) * i / 4
            p.setPen(QPen(grid, 1)); p.drawLine(QPointF(L, Y(v)), QPointF(L + w, Y(v)))
            p.setPen(dim); p.drawText(QRectF(0, Y(v) - 9, L - 8, 18), Qt.AlignRight | Qt.AlignVCenter, f"{v:.2f}")
        for lim, name in ((self.hi, "상한"), (self.lo, "하한")):          # 한계선 (버스마다 같을 때만)
            if lim is None:
                continue
            pen = QPen(dim, 1, Qt.DashLine); p.setPen(pen)
            p.drawLine(QPointF(L, Y(lim)), QPointF(L + w, Y(lim)))
            p.drawText(QRectF(L + w - 90, Y(lim) - 16, 90, 14), Qt.AlignRight | Qt.AlignVCenter, f"{name} {lim:g}")
        band = QPainterPath(QPointF(X(0), Y(self.vmax[0])))
        for k in range(1, n):
            band.lineTo(X(k), Y(self.vmax[k]))
        for k in range(n - 1, -1, -1):
            band.lineTo(X(k), Y(self.vmin[k]))
        band.closeSubpath()
        fill = QColor(255, 255, 255, 30) if self.dark else QColor(21, 23, 28, 22)
        p.setPen(Qt.NoPen); p.setBrush(fill); p.drawPath(band)
        p.setBrush(Qt.NoBrush); p.setPen(QPen(fg, 1.6))
        for arr in (self.vmax, self.vmin):
            for k in range(n - 1):
                p.drawLine(QPointF(X(k), Y(arr[k])), QPointF(X(k + 1), Y(arr[k + 1])))
        for k in range(n):                                             # 넘은 버스의 전압 자리에 주황 점
            for v in self.bad[k]:
                glow = QColor(AMB); glow.setAlpha(60)
                p.setPen(Qt.NoPen); p.setBrush(glow); p.drawEllipse(QPointF(X(k), Y(v)), 6, 6)
                p.setBrush(QColor(AMB)); p.drawEllipse(QPointF(X(k), Y(v)), 3.2, 3.2)
        step = _hour_step(n, w)
        p.setPen(dim)
        for k in range(0, n, step):
            p.drawText(QRectF(X(k) - 20, T_ + h + 5, 40, 16), Qt.AlignCenter, f"{k + 1}")
        p.end()


class HourBars(QWidget):
    """시간대별 최대 선로 부하율 — 시각마다 가장 무거운 선로 하나. 100 % 넘으면 주황."""

    def __init__(self, vals, names, c, on_pick=None, parent=None):
        super().__init__(parent)
        self.vals, self.names, self.c, self.on_pick = vals, names, c, on_pick
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    L, T_, R_, B = 44, 10, 10, 24

    def _k(self, x):
        n = len(self.vals)
        cw = (self.width() - self.L - self.R_) / max(1, n)
        return max(0, min(n - 1, int((x - self.L) // cw)))

    def mouseMoveEvent(self, e):
        k = self._k(e.position().x())
        v = self.vals[k]
        self.setToolTip(f"{k + 1} H · " + (f"{self.names[k]}  {v:.0f} %" if v is not None else "정격 없음")
                        + "\n누르면 이 시각의 개요로")

    def mousePressEvent(self, e):
        if self.on_pick and e.button() == Qt.LeftButton:
            self.on_pick(self._k(e.position().x()))

    def paintEvent(self, _e):
        c = self.c
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        have = [v for v in self.vals if v is not None]
        if not have:
            _empty(p, QRectF(self.rect()), c, "—", "부하율을 잴 수 없습니다",
                   "선로에 정격(용량)이 안 적혀 있습니다 — 계통 데이터의 rateA 열에 넣으면 그려집니다")
            p.end(); return
        L, T_, R_, B = self.L, self.T_, self.R_, self.B
        n = len(self.vals)
        w, h = self.width() - L - R_, self.height() - T_ - B
        mx = max(120.0, max(have) * 1.08)
        cw = w / n
        f = QFont(self.font()); f.setPixelSize(11); p.setFont(f)
        # 눈금 — 보통은 0 · 50 · 100. 부하율이 아주 크면(71bus: 1,890 %) 그 셋이 바닥에 겹쳐서 큰 눈금으로 바꾼다
        if mx <= 250:
            ticks = [0, 50, 100]
        else:
            big = 10 ** int(np.floor(np.log10(mx)))
            stepv = big if mx / big >= 2 else big / 2
            ticks = [0] + [int(stepv * i) for i in range(1, int(mx // stepv) + 1)]
        used = []
        for v in ticks + ([100] if 100 not in ticks else []):
            y = T_ + h * (1 - v / mx)
            p.setPen(QPen(QColor(c["muted"] if v == 100 else c["hair"]), 1, Qt.DashLine if v == 100 else Qt.SolidLine))
            p.drawLine(QPointF(L, y), QPointF(L + w, y))
            if all(abs(y - u) >= 13 for u in used):          # 글자는 안 겹칠 때만
                used.append(y)
                p.setPen(QColor(c["muted"]))
                p.drawText(QRectF(0, y - 9, L - 6, 18), Qt.AlignRight | Qt.AlignVCenter, f"{v:,}")
        p.setPen(Qt.NoPen)
        bw = max(3.0, cw * 0.62)
        for k, v in enumerate(self.vals):
            if v is None:
                continue
            bh = h * min(v, mx) / mx
            p.setBrush(QColor(AMB if v > 100 else c["accent"]))
            p.drawRoundedRect(QRectF(L + k * cw + (cw - bw) / 2, T_ + h - bh, bw, bh), 3, 3)
        step = _hour_step(n, w)
        p.setPen(QColor(c["muted"]))
        for k in range(0, n, step):
            p.drawText(QRectF(L + k * cw - 10, T_ + h + 5, cw + 20, 16), Qt.AlignCenter, f"{k + 1}")
        p.end()


def dyn_page(app):
    """다이나믹 개요 — 숫자 카드 넷 · 시간대별 위반 표 · 가장 나쁜 시각 · 전압 범위 · 최대 부하율."""
    c, sol = app.c, app.sol
    n_t = int(getattr(sol, "n_time", 1) or 1)
    per = [summary(sol, t) for t in range(n_t)]
    app._ov_cards = {}                       # 스냅샷 개요의 카드 자리는 더 안 맞는다

    hours_v = [t for t in range(n_t) if per[t]["n_v"]]
    hours_l = [t for t in range(n_t) if per[t]["n_l"]]
    hours_d = [t for t in range(n_t) if per[t]["n_gen_lim"] + per[t]["n_ic_lim"]]
    # 넘은 것마다 시각별 칸 — 줄 = (종류, 이름) · 칸 = (비율, 값, 넘은 양)
    cells, worst = {}, {}
    wv = wl = None                           # (비율, 시각, 이름, 값, 넘은 양)
    for t in range(n_t):
        for kind, name, val, _lim, ex, ratio in per[t]["rows"]:
            key = (kind, name)
            cells.setdefault(key, [None] * n_t)[t] = (float(ratio), val, ex)
            worst[key] = max(worst.get(key, 0.0), float(ratio))
            if kind == "전압" and (wv is None or ratio > wv[0]):
                wv = (ratio, t, name, val, ex)
            if kind == "선로" and (wl is None or ratio > wl[0]):
                wl = (ratio, t, name, val, ex)
    keys = sorted(cells, key=lambda k: -worst[k])
    tops = [per[t]["top"] for t in range(n_t)]
    rated = any(tp is not None for tp in tops)
    count = [per[t]["n_v"] + per[t]["n_l"] for t in range(n_t)]
    t_bad = int(np.argmax(count)) if max(count) > 0 else None

    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(18); g.setVerticalSpacing(18)

    # ── 숫자 카드 넷
    conv_ok = bool(getattr(sol, "converged", True))
    kp = [
        _kpi(c, "① 수렴", f"{n_t} 시각", "모두 수렴" if conv_ok else "수렴 못 한 시각 있음",
             not conv_ok, "✓" if conv_ok else "!", ok=conv_ok),
        _kpi(c, "② 버스 전압", f"{len(hours_v)} 시간",
             f"최대 {float(wv[4]):+.3f} · {wv[1] + 1} H" if wv else "넘은 시각 없음", bool(hours_v), "↕",
             ok=not hours_v),
        _kpi(c, "③ 열 용량", f"{len(hours_l)} 시간" if rated else "—",
             (f"최대 {float(wl[3].split()[0]):.0f} % · {wl[1] + 1} H" if wl else "넘은 시각 없음") if rated else "선로 정격이 안 적힘",
             bool(hours_l), "≡", ok=rated and not hours_l),
        _kpi(c, "④ 설비 한계", f"{len(hours_d)} 시간", "한계에 닿은 시각", bool(hours_d), "⚙",
             ok=not hours_d),
    ]
    krow = QHBoxLayout(); krow.setSpacing(18)
    for k in kp:
        krow.addWidget(k, 1)
    g.addLayout(krow, 0, 0, 1, 2)

    # ── 시간대별 위반 (가로 = 시각 · 세로 = 버스 · 선로)
    SHOW = 8              # 1440 × 900 창에서 아래 그래프 줄까지 한 화면에 들어오는 줄 수
    hc, hv = _section(c, "시간대별 위반", len(keys), bool(keys))
    hv.itemAt(0).layout().addWidget(_label("칸이 진할수록 많이 넘음 · 누르면 그 시각으로", 12, c["muted"]))
    if keys:
        hv.addWidget(HeatRows(keys[:SHOW], cells, n_t, c, on_pick=app.goto_time, mark=t_bad))
        if len(keys) > SHOW:
            hv.addWidget(_label(f"+ {len(keys) - SHOW}곳 더 — 많이 넘은 순으로 {SHOW}곳만 보입니다", 12, c["muted"]))
        hv.addStretch(1)
    else:
        hv.addWidget(_EmptyBox(c, "✓", f"{n_t}개 시각 모두 한계 안입니다", "전압 · 선로 용량을 넘은 시각이 없습니다"), 1)
    g.addWidget(hc, 1, 0)

    # ── 가장 나쁜 시각 (잘린 계통도 위에 글)
    sc = _card(c)
    sc.setMinimumHeight(264)
    t_show = t_bad if t_bad is not None else 0
    mini = TopoMini(sol, t_show, sc)
    sv = QVBoxLayout(sc); sv.setContentsMargins(20, 16, 20, 16); sv.setSpacing(2)
    if t_bad is not None:
        sv.addWidget(_label(f"{t_bad + 1} H 가 가장 나쁨", 19, c["text"], True))
        sv.addWidget(_label(f"위반 {count[t_bad]}건 — 전압 {per[t_bad]['n_v']} · 선로 {per[t_bad]['n_l']}", 13, c["muted"]))
        sv.addSpacing(12)
        r0 = per[t_bad]["rows"][0]
        sv.addWidget(_label(f"{r0[1]}  <span style='color:{AMB_TEXT}'>{r0[2]}</span>", 20, c["text"], True))
        sv.addWidget(_label("그 시각에 가장 많이 넘은 " + ("선로" if r0[0] == "선로" else "버스 전압"), 13, c["muted"]))
    else:
        sv.addWidget(_label("위반 없음", 19, c["text"], True))
        sv.addWidget(_label(f"{n_t}개 시각 모두 한계 안", 13, c["muted"]))
    sv.addSpacing(10)
    n_hours = len(set(hours_v) | set(hours_l))
    sv.addWidget(_label(f"{n_hours} / {n_t} 시각", 18, c["text"], True))
    sv.addWidget(_label("위반이 있는 시각", 13, c["muted"]))
    sv.addStretch()
    go = QPushButton(f"{t_show + 1} H 개요 보기 ↗")
    go.setCursor(Qt.PointingHandCursor)
    go.setStyleSheet(f"QPushButton {{ background:{c['accent']}; color:{c['on_accent']}; border:none;"
                     "border-radius:9px; padding:7px 14px; font-weight:600; font-size:13px; }")
    go.clicked.connect(lambda: app.goto_time(t_show))
    sv.addWidget(go, 0, Qt.AlignLeft)
    sc.resizeEvent = lambda e, m=mini, f=sc: m.setGeometry(0, 0, f.width(), f.height())
    mini.lower()
    g.addWidget(sc, 1, 1)

    # ── 시간대별 전압 범위 (진한 카드)
    dk = CHART_STYLE == "bars"
    vc = _card(c, dark_card=dk)
    vv = QVBoxLayout(vc); vv.setContentsMargins(20, 16, 20, 12); vv.setSpacing(2)
    vh = QHBoxLayout(); vh.setSpacing(14)
    vh.addWidget(_label("시간대별 버스 전압 범위", 15, "#f2f2f4" if dk else c["text"], True)); vh.addStretch()
    vh.addWidget(_legend_chip(AMB, "한계를 넘은 버스", c, dk))
    vv.addLayout(vh)
    vv.addWidget(_label("그 시각의 가장 높은 버스와 가장 낮은 버스 사이", 13,
                        "rgba(255,255,255,.55)" if dk else c["muted"]))
    vv.addSpacing(6)
    bt = charts._bus_table(sol, 0)
    # 한계선은 **모든 버스의 한계가 같을 때만** 긋는다 — 버스마다 다르면(CIGRE: AC · DC 한계가 다름)
    # 선 하나로는 어느 버스의 한계인지 말할 수 없다. 그때는 넘은 버스의 점만 보인다.
    lo_g = float(bt[2][0]) if len(bt[2]) and float(np.ptp(bt[2])) < 1e-9 else None
    hi_g = float(bt[3][0]) if len(bt[3]) and float(np.ptp(bt[3])) < 1e-9 else None
    over = [[float(r[2].split()[0]) for r in per[t]["rows"] if r[0] == "전압"] for t in range(n_t)]
    vv.addWidget(EnvChart([per[t]["vmin"] for t in range(n_t)], [per[t]["vmax"] for t in range(n_t)],
                          over, lo_g, hi_g, c, dk, on_pick=app.goto_time), 1)
    g.addWidget(vc, 2, 0)

    # ── 시간대별 최대 부하율
    lc = _card(c)
    lv = QVBoxLayout(lc); lv.setContentsMargins(20, 16, 20, 14); lv.setSpacing(4)
    lv.addWidget(_label("시간대별 최대 부하율", 15, c["text"], True))
    lv.addWidget(_label((f"<span style='color:{AMB_TEXT};font-weight:700'>{len(hours_l)}시간</span> 이 100 % 넘음"
                         if hours_l else "100 % 넘은 시각 없음") + " · 시각마다 가장 무거운 선로", 13, c["muted"]))
    lv.addSpacing(6)
    lv.addWidget(HourBars([tp[0] if tp else None for tp in tops], [tp[1] if tp else "" for tp in tops],
                          c, on_pick=app.goto_time), 1)
    det = QPushButton("그래프 · 표 자세히 →")
    det.setCursor(Qt.PointingHandCursor)
    det.setStyleSheet(f"QPushButton {{ background:transparent; color:{c['muted']}; border:none;"
                      "font-size:13px; font-weight:600; text-align:right; }")
    det.clicked.connect(app.open_details)
    lv.addWidget(det, 0, Qt.AlignRight)
    g.addWidget(lc, 2, 1)

    g.setColumnStretch(0, 61); g.setColumnStretch(1, 39)
    g.setRowStretch(1, 0); g.setRowStretch(2, 1)
    return w


# ── 카드 → 자세한 화면 움직임 (E2 · 2026-11-03 사용자 고름) ─────────────────
class ExpandOverlay(QWidget):
    """누른 카드가 커져 화면을 채우고, 나머지 카드는 옅어지며 뒤로 물러난다(E2).

    `back=True` 면 거꾸로 — 자세한 화면이 그 카드 자리로 줄어들고 개요가 앞으로 나온다.
    그림은 둘 다 미리 찍은 것(`QWidget.grab`)을 쓴다 — 움직이는 0.4초 동안 실제 위젯은 안 건드린다.
    """
    DUR = 380

    def __init__(self, host, page_pm, card_pm, rect, fill, ground, back=False):
        super().__init__(host)
        self.page_pm, self.card_pm, self.r0, self.fill, self.ground, self.back = (
            page_pm, card_pm, QRectF(rect), QColor(fill), QColor(ground), back)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(host.rect())
        self.t, self.fade = 0.0, 1.0
        self.show(); self.raise_()
        from PySide6.QtCore import QVariantAnimation, QEasingCurve
        self.a = QVariantAnimation(self, duration=self.DUR, easingCurve=QEasingCurve.OutCubic,
                                   startValue=0.0, endValue=1.0)
        self.a.valueChanged.connect(self._tick)
        self.a.finished.connect(self._fade_out)
        self.a.start()

    def _tick(self, v):
        # 새 화면은 막 만들어져 아직 제 크기가 아닐 수 있다 — 움직이는 동안 늘 판 전체를 덮는다
        host = self.parentWidget()
        if host is not None and self.geometry() != host.rect():
            self.setGeometry(host.rect()); self.raise_()
        self.t = float(v); self.update()

    def _fade_out(self):
        from PySide6.QtCore import QVariantAnimation
        if self.back:
            self.deleteLater(); return
        self.b = QVariantAnimation(self, duration=160, startValue=1.0, endValue=0.0)
        self.b.valueChanged.connect(lambda v: (setattr(self, "fade", float(v)), self.update()))
        self.b.finished.connect(self.deleteLater)
        self.b.start()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setOpacity(self.fade)
        full = QRectF(self.rect())
        u = self.t if not self.back else 1 - self.t        # u = 0 개요 · 1 자세히
        p.fillRect(full, self.ground)
        # 나머지 카드 — 옅어지며 물러남
        sc = 1 - .06 * u
        p.save()
        p.setOpacity(self.fade * (1 - u))
        cx, cy = full.center().x(), full.center().y()
        p.translate(cx, cy); p.scale(sc, sc); p.translate(-cx, -cy)
        p.drawPixmap(full.toRect(), self.page_pm)
        p.restore()
        # 누른 카드 — 그 자리에서 커짐
        r = QRectF(self.r0.x() * (1 - u), self.r0.y() * (1 - u),
                   self.r0.width() + (full.width() - self.r0.width()) * u,
                   self.r0.height() + (full.height() - self.r0.height()) * u)
        p.setPen(Qt.NoPen); p.setBrush(self.fill)
        p.setOpacity(self.fade)
        p.drawRoundedRect(r, 16, 16)
        # 커질 때는 카드 그림이 옅어지고, 줄어들 때는 자세한 화면 그림이 옅어진다
        p.setOpacity(self.fade * (min(1.0, u * 1.6) if self.back else max(0.0, 1 - u * 1.6)))
        p.drawPixmap(r.toRect(), self.card_pm)
        p.end()


# ── 카드가 떠서 커진다 (D2 · 2026-11-03 사용자 고름) ─────────────────────────
#    다른 페이지로 넘어가지 않는다 — 누른 카드가 개요 위에 떠서 판 크기 가까이 커지고,
#    뒤 개요는 흐리게 남는다. ✕ · 바깥 누르기 · Esc 로 그 카드 자리로 줄어든다.
#    카드 안 내용(첫 판) — 이미 있는 화면을 다시 쓴다:
#      위반 = 점검 화면 · 전압 = 큰 막대 + 버스 표 · 부하율 = 정격 선로 전부 ·
#      수급 = 버스별 발전 · 부하 표 · 계통도 = 진짜 계통도(위반 보기 켬)
TITLE = {"viol": "살펴볼 곳", "kviol": "살펴볼 곳", "kdev": "설비 한계 · 위반", "conv": "수렴", "volt": "버스 전압", "kvolt": "버스 전압",
         "load": "선로 부하율", "kload": "선로 부하율", "supply": "수급", "topo": "계통도"}


def _table(c, head, rows, bad=None):
    tb = QTableWidget(len(rows), len(head))
    tb.setHorizontalHeaderLabels(head)
    tb.verticalHeader().setVisible(False)
    tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tb.setSelectionMode(QAbstractItemView.NoSelection)
    tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    tb.setShowGrid(False)
    tb.setFrameShape(QFrame.NoFrame)
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            it = QTableWidgetItem(str(v))
            it.setTextAlignment(Qt.AlignVCenter | (Qt.AlignLeft if j == 0 else Qt.AlignRight))
            if bad and bad(i):
                it.setForeground(QColor(AMB_TEXT))
            tb.setItem(i, j, it)
    tb.setStyleSheet(f"QTableWidget {{ background:transparent; color:{c['text']}; font-size:13px; }}"
                     f"QHeaderView::section {{ background:transparent; color:{c['muted']}; border:none;"
                     f"border-bottom:1px solid {c['border']}; padding:6px; font-weight:700; }}")
    return tb


def _detail(app, key, dark):
    c, sol, t = app.c, app.sol, app.t
    k = key.lstrip("k") if key in ("kviol", "kvolt", "kload") else key
    if k == "kdev":
        k = "viol"
    if k == "conv":
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.NoFrame)
        sa.setWidget(app.conv_page())
        sa.setStyleSheet("QScrollArea { background:transparent; }")
        sa.viewport().setStyleSheet("background:transparent;")
        return sa
    if k == "viol":
        # 점검 화면의 표는 판 높이에 맞춰 눌리면 줄이 잘린다(5건 중 4줄만 보였음) —
        # 표마다 줄 수만큼 높이를 박고, 판 전체를 스크롤 상자에 담는다.
        pg = QWidget(); pv = QVBoxLayout(pg); pv.setContentsMargins(0, 0, 6, 0); pv.setSpacing(14)
        work = summary(sol, t)["work"]
        if work:        # 개요 표는 6줄에서 끊긴다 — 여기서는 근접까지 전부 (점검 표에는 근접이 없다)
            vt = ViolTable(work, c)
            vt.setFixedHeight(28 + 34 * len(work) + 6)
            vt.setCursor(Qt.ArrowCursor)
            pv.addWidget(vt)
        pv.addWidget(app.check_page())
        for tb in pg.findChildren(QTableWidget):
            h = tb.horizontalHeader().height() if tb.horizontalHeader().isVisible() else 0
            rows = sum(tb.rowHeight(i) for i in range(tb.rowCount()))
            sb = tb.horizontalScrollBar().sizeHint().height() if tb.horizontalScrollBar().isVisible() else 0
            tb.setFixedHeight(max(h, 32) + rows + 4 + sb)
            tb.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.NoFrame)
        sa.setWidget(pg)
        sa.setStyleSheet("QScrollArea { background:transparent; }")
        sa.viewport().setStyleSheet("background:transparent;")
        return sa
    if k == "volt":
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(12)
        ch = VoltChart(sol, t, c, dark); ch.setMinimumHeight(260)
        v.addWidget(ch, 3)
        names, vm, lo, hi, kind = charts._bus_table(sol, t)
        rows = [(("DC " if kind[i] == "DC" else "AC ") + str(names[i]).replace("DC", ""),
                 f"{vm[i]:.4f}", f"{lo[i]:.3f}", f"{hi[i]:.3f}",
                 (f"+{vm[i] - hi[i]:.4f}" if vm[i] > hi[i] else (f"{vm[i] - lo[i]:.4f}" if vm[i] < lo[i] else "—")))
                for i in range(len(names))]
        tc = dict(c, text="#f2f2f4", muted="rgba(255,255,255,.55)", border="rgba(255,255,255,.12)") if dark else c
        v.addWidget(_table(tc, ["버스", "V [pu]", "Vmin", "Vmax", "넘은 양"], rows,
                           bad=lambda i: vm[i] > hi[i] or vm[i] < lo[i]), 2)
        return w
    if k == "load":
        lb = LoadBars(sol, t, c, 999, cap=10_000)
        lb.setMinimumHeight(30 * max(1, len(lb.all)))
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.NoFrame)
        sa.setWidget(lb); sa.viewport().setStyleSheet("background:transparent;")
        sa.setStyleSheet("QScrollArea { background:transparent; }")
        return sa
    if k == "supply":
        rows = []
        for which in ("AC", "DC"):
            arr = sol.at(which, t)
            if not arr.size:
                continue
            ib, ig, il = (_col(sol, which, "Bus"), _col(sol, which, "Gen_P[MW]"), _col(sol, which, "Load_P[MW]"))
            for r in arr:
                g = float(r[ig]) if ig >= 0 else 0.0
                l = float(r[il]) if il >= 0 else 0.0
                if abs(g) > 1e-9 or abs(l) > 1e-9:
                    rows.append((f"{which} {int(r[ib])}", f"{g:,.1f}", f"{l:,.1f}", f"{g - l:+,.1f}"))
        return _table(c, ["버스", "발전 P [MW]", "부하 P [MW]", "발전 − 부하"], rows)
    if k == "topo":
        # 🚨 계통도 위 단추(위반 보기 ON/OFF · 퍼짐/층 · 배치 처음으로)는 `on_toggle` 로 «다시 그려 달라»고
        #    부른다. 자세히 화면에서는 앱이 통째로 다시 그리지만, 떠 있는 카드에서 그러면 카드가 사라진다 —
        #    카드 안 계통도만 갈아 끼운다(2026-11-03 사용자: 「퍼짐 층 전환이나 위반 on off 전환이 안돼」).
        import topology as TT
        from PySide6.QtCore import QTimer
        box = QWidget()
        lay = QVBoxLayout(box); lay.setContentsMargins(0, 0, 0, 0)
        state = {"viol": True, "first": True}

        def reset_places(name):
            if TT.clear_places(name):
                QTimer.singleShot(0, build)

        def build(v=None):
            if v is not None:
                state["viol"] = bool(v)
            while lay.count():
                it = lay.takeAt(0)
                if it.widget() is not None:
                    it.widget().deleteLater()
            tv = TT.topology_view(c, sol, t, show_violations=state["viol"],
                                  on_toggle=lambda x: QTimer.singleShot(0, lambda: build(x)),
                                  on_line_click=getattr(app, "show_line_profile", None),
                                  zoom=state.get("zoom", 1.0),
                                  on_zoom=lambda z: state.__setitem__("zoom", z),
                                  on_reset_places=reset_places,
                                  on_bus_click=getattr(app, "show_bus_profile", None))
            lay.addWidget(tv or QWidget())

            def fit(tv=tv):
                # 2026-11-15 — 카드보다 큰 계통도는 아래가 잘린 채 떴다. 처음 한 번 카드 안에 다 들어오게
                # 줄인다(그 뒤는 사용자가 정한 배율 그대로). 배율은 이 카드 안에서만 쓴다.
                try:
                    vs = tv.findChildren(TT.TopologyView) if tv is not None else []
                    sc = vs[0]._scroller() if vs else None
                    if sc is None or "zoom" in state:
                        return
                    vw = vs[0]
                    ah, aw = sc.viewport().height(), sc.viewport().width()
                    nh, nw = max(1, vw.minimumHeight()), max(1, vw.minimumWidth())
                    if nh > ah or nw > aw:
                        vw.set_zoom(max(vw.ZOOM_MIN, vw.zoom * min(ah / nh, aw / nw) * 0.98))
                except RuntimeError:
                    pass
            QTimer.singleShot(FloatCard.DUR + 80 if state["first"] else 0, fit)
            state["first"] = False
        build()
        return box
    return QWidget()


class _Dim(QWidget):
    def __init__(self, host, on_click):
        super().__init__(host)
        self.a, self.on_click = 0.0, on_click
        self.setGeometry(host.rect()); self.show(); self.raise_()

    def set_a(self, v):
        self.a = float(v); self.update()

    def paintEvent(self, _e):
        p = QPainter(self); p.fillRect(self.rect(), QColor(30, 30, 32, int(105 * self.a)))

    def mousePressEvent(self, _e):
        self.on_click()


class _Cover(QWidget):
    """카드 바탕색 덮개 — 커지는 동안 내용을 가리고, 다 커지면 옅어지며 걷힌다."""

    def __init__(self, card, col):
        super().__init__(card)
        self.col, self.a = col, 1.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.show(); self.raise_()

    def fade(self, a0, a1, ms):
        from PySide6.QtCore import QVariantAnimation
        self.an = QVariantAnimation(self, duration=ms, startValue=a0, endValue=a1)
        self.an.valueChanged.connect(lambda v: (setattr(self, "a", float(v)), self.update()))
        self.an.finished.connect(lambda: self.hide() if self.a <= 0.01 else None)
        self.an.start()

    def paintEvent(self, _e):
        p = QPainter(self)
        c = QColor(self.col); c.setAlphaF(self.a)
        p.fillRect(self.rect(), c)


class FloatCard(QFrame):
    DUR = 380

    def __init__(self, app, key, src_rect):
        host = app._center_w
        super().__init__(host)
        self.app, self.key, self.src = app, key, QRect(src_rect)
        dark = (key in ("volt", "kvolt")) and CHART_STYLE == "bars"
        c = app.c
        bg = "#15171c" if dark else c["surface"]
        fg = "#f2f2f4" if dark else c["text"]
        self.setObjectName("floatcard")
        self.setStyleSheet(f"#floatcard {{ background:{bg}; border-radius:18px; }}")
        sh = QGraphicsDropShadowEffect(self); sh.setBlurRadius(60); sh.setOffset(0, 24)
        sh.setColor(QColor(0, 0, 0, 70)); self.setGraphicsEffect(sh)
        self.dim = _Dim(host, self.close_card)
        v = QVBoxLayout(self); v.setContentsMargins(22, 16, 18, 18); v.setSpacing(8)
        hd = QHBoxLayout()
        hd.addWidget(_label(TITLE.get(key, ""), 17, fg, True)); hd.addStretch()
        x = QPushButton("✕"); x.setFixedSize(32, 32); x.setCursor(Qt.PointingHandCursor)
        x.setToolTip("닫기 (Esc)")
        x.setStyleSheet(f"QPushButton {{ background:rgba(127,127,127,.18); color:{fg}; border:none;"
                        "border-radius:9px; font-size:15px; font-weight:800; padding:0px; }"
                        "QPushButton:hover { background:rgba(127,127,127,.32); }")
        x.clicked.connect(self.close_card)
        hd.addWidget(x)
        v.addLayout(hd)
        self.body = _detail(app, key, dark)
        v.addWidget(self.body, 1)
        # 🚨 내용 위에 `QGraphicsOpacityEffect` 를 걸면 안에 든 스크롤 상자(계통도)가 카드 밖으로
        #    삐져나와 그려졌다(2026-11-03 맥 화면). 그래서 내용은 그대로 두고, 카드 바탕색 덮개를 얹었다가 걷는다.
        self.cover = _Cover(self, QColor(bg))
        self.setGeometry(self.src); self.show(); self.raise_()
        self.setFocusPolicy(Qt.StrongFocus); self.setFocus()
        m = 28
        self.dst = QRect(m, m, host.width() - 2 * m, host.height() - 2 * m)
        from PySide6.QtCore import QPropertyAnimation, QVariantAnimation, QEasingCurve
        self.ga = QPropertyAnimation(self, b"geometry", self)
        self.ga.setDuration(self.DUR); self.ga.setEasingCurve(QEasingCurve.OutCubic)
        self.ga.setStartValue(self.src); self.ga.setEndValue(self.dst)
        self.da = QVariantAnimation(self, duration=self.DUR, startValue=0.0, endValue=1.0)
        self.da.valueChanged.connect(self.dim.set_a)
        self.ga.finished.connect(self._show_body)
        self.ga.start(); self.da.start()
        self._closing = False

    def resizeEvent(self, e):
        self.cover.setGeometry(self.body.geometry() if self.body.geometry().isValid() else self.rect())
        super().resizeEvent(e)

    def _show_body(self):
        if self._closing:
            return
        self.cover.setGeometry(self.body.geometry())
        self.cover.fade(1.0, 0.0, 180)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close_card()
        else:
            super().keyPressEvent(e)

    def close_card(self):
        if self._closing:
            return
        self._closing = True
        self.cover.a = 1.0; self.cover.show(); self.cover.raise_(); self.cover.update()
        self.ga.stop(); self.da.stop()
        self.ga.setStartValue(self.geometry()); self.ga.setEndValue(self.src)
        self.da.setStartValue(self.dim.a); self.da.setEndValue(0.0)
        self.ga.finished.disconnect()
        self.ga.finished.connect(self._done)
        self.ga.start(); self.da.start()

    def _done(self):
        self.dim.deleteLater(); self.deleteLater()
        self.app._float = None


def open_float(app, key):
    host = getattr(app, "_center_w", None)
    card = getattr(app, "_ov_cards", {}).get(key)
    if host is None or card is None or getattr(app, "_float", None) is not None:
        return
    from PySide6.QtCore import QPoint
    r = QRect(card.mapTo(host, QPoint(0, 0)), card.size())
    app._float = FloatCard(app, key, r)
