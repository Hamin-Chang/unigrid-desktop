# -*- coding: utf-8 -*-
"""사이드바 하나 (앱 2.3 · 2026-11-03 사용자가 칸마다 고른 꼴).

    로고
    [계통 파일 열기]                      ← K2 · 따로 둔 검은 단추
    ┌ 현재 케이스 카드 ┐                  ← V1 · 테두리 흰 카드
    조류계산 ──────                       ← N2 · 진한 묶음 제목 + 가는 선
      결과 [스냅샷 | 다이나믹 | 비교]      ← U1 · 결과 카드 안 단추 묶음
      점검 · 계통 데이터
    해석 ──────
      시나리오 · PV·QV 곡선
    ┌ 파일 카드 ┐                         ← W2 · 내보내기 · 엑셀로 만들기 + 화면 밝기 · 정보

움직임 — 고른 메뉴의 흰 판이 하나뿐이고 묶음을 넘어서도 미끄러진다(A1 + X1, 0.28초).
화면은 메뉴를 누를 때마다 통째로 다시 그려지므로, 흰 판 · 단추 묶음의 옛 자리를
창(`app`)에 맡겨 두었다가 새 사이드바에서 그 자리부터 움직인다.
"""
from __future__ import annotations

from PySide6.QtCore import (Qt, QRect, QRectF, QPointF, QTimer, QEasingCurve,
                            QPropertyAnimation, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QPainter, QPen, QLinearGradient, QPainterPath
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
                               QGraphicsDropShadowEffect, QPushButton)

WIDTH = 256
DUR = 280
EASE = QEasingCurve.OutCubic


def _shadow(w, blur=22, dy=8, a=18):
    sh = QGraphicsDropShadowEffect(w)
    sh.setBlurRadius(blur); sh.setOffset(0, dy); sh.setColor(QColor(0, 0, 0, a))
    w.setGraphicsEffect(sh)


INK = "#15171c"


def _dark_grad(r):
    """고른 칸 · 로고의 바탕. 2026-11-15 — 검은 그라데이션을 걷고 먹색 한 색으로."""
    return QColor(INK)


class IconSq(QWidget):
    """흰 네모 안 선 아이콘. 고른 칸이면 검은 네모 + 흰 선."""

    def __init__(self, kind, c, draw, on=False, size=30, dark=False, parent=None):
        super().__init__(parent)
        self.kind, self.c, self.draw, self.on, self.dark = kind, c, draw, on, dark
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -2)
        p.setPen(Qt.NoPen)
        if self.on:
            p.setBrush(QColor(self.c["text"]) if self.dark else _dark_grad(r))
        else:
            p.setBrush(QColor(0, 0, 0, 16)); p.drawRoundedRect(r.translated(0, 1.5), 9, 9)
            p.setBrush(QColor(self.c["surface"]))
        p.drawRoundedRect(r, 9, 9)
        fg = QColor(self.c["surface"] if self.on else self.c["text"])
        if not self.isEnabled():
            fg.setAlphaF(.35)
        pen = QPen(fg, 1.5); pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        s = (self.width() - 12) / 20
        if self.kind == "sun":
            cx = cy = self.width() / 2
            p.drawEllipse(QPointF(cx, cy), 3.2, 3.2)
            for k in range(8):
                import math
                a = k * math.pi / 4
                p.drawLine(QPointF(cx + 5.5 * math.cos(a), cy + 5.5 * math.sin(a)),
                           QPointF(cx + 7.2 * math.cos(a), cy + 7.2 * math.sin(a)))
        elif self.kind == "moon":
            cx = cy = self.width() / 2
            path = QPainterPath(); path.addEllipse(QPointF(cx, cy), 6, 6)
            cut = QPainterPath(); cut.addEllipse(QPointF(cx + 3.5, cy - 2.5), 5, 5)
            p.drawPath(path.subtracted(cut))
        else:
            self.draw(p, self.kind, 6, 6, s)


class NavItem(QWidget):
    """메뉴 한 줄 — 아이콘 네모 + 이름."""
    clicked = Signal()

    def __init__(self, kind, name, c, draw, dark, on=False, enabled=True, tip="", parent=None):
        super().__init__(parent)
        self.name = name
        self.setFixedHeight(46)
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        h = QHBoxLayout(self); h.setContentsMargins(12, 0, 8, 0); h.setSpacing(12)
        self.sq = IconSq(kind, c, draw, on, dark=dark)
        self.sq.setEnabled(enabled)
        h.addWidget(self.sq)
        self.lb = QLabel(name)
        self.c = c
        self._style(on, enabled)
        h.addWidget(self.lb, 1)
        self.setEnabled(enabled)
        if tip:
            self.setToolTip(tip)

    def _style(self, on, enabled=True):
        col = self.c["text"] if on else self.c["muted"]
        op = "" if enabled else "opacity:.4;"
        self.lb.setStyleSheet(f"color:{col}; font-size:14px; font-weight:{700 if on else 600};"
                              f"background:transparent;{op}")
        if not enabled:
            self.lb.setStyleSheet(self.lb.styleSheet() + f"color:{self.c['muted']};")

    def set_on(self, on):
        self.sq.on = on; self.sq.update()
        self._style(on, self.isEnabled())

    def mousePressEvent(self, e):
        if self.isEnabled() and e.button() == Qt.LeftButton:
            self.clicked.emit()

    def moveEvent(self, e):
        # 🚨 창 배치가 늦게 끝나면 줄이 나중에 자리를 옮긴다 — 흰 판이 옛 자리에 남아
        #    「점검」 아래로 어긋나 보였다(2026-11-03 사용자 화면). 줄이 움직이면 흰 판도 따라간다.
        super().moveEvent(e)
        nav = getattr(self, "nav", None)
        if nav is not None:
            nav._snap()


class SegSlide(QWidget):
    """「결과」 아래 단추 묶음 — 흰 단추가 옆으로 미끄러진다."""

    def __init__(self, opts, cur, locked, c, dark, on_pick, start=None, parent=None):
        super().__init__(parent)
        self.opts, self.cur, self.locked, self.c, self.dark, self.on_pick = opts, cur, locked, c, dark, on_pick
        self.setFixedHeight(34)
        self.setMouseTracking(True)
        self._x = float(start if start is not None else cur)
        self._anim = QVariantAnimation(self, duration=250, easingCurve=EASE)
        self._anim.valueChanged.connect(self._set_x)
        if start is not None and start != cur:
            QTimer.singleShot(0, lambda: self._go(cur))

    def _set_x(self, v):
        self._x = float(v); self.update()

    def _go(self, k):
        self._anim.stop(); self._anim.setStartValue(self._x); self._anim.setEndValue(float(k)); self._anim.start()

    def _cell(self, k):
        w = (self.width() - 6) / len(self.opts)
        return QRectF(3 + k * w, 3, w, self.height() - 6)

    def mouseMoveEvent(self, e):
        k = int((e.position().x() - 3) // ((self.width() - 6) / len(self.opts)))
        k = max(0, min(len(self.opts) - 1, k))
        tip = self.locked.get(self.opts[k], "")
        self.setToolTip(tip)
        self.setCursor(Qt.ArrowCursor if tip else Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        k = int((e.position().x() - 3) // ((self.width() - 6) / len(self.opts)))
        k = max(0, min(len(self.opts) - 1, k))
        if self.opts[k] in self.locked or k == self.cur:
            return
        self.cur = k
        self._go(k)
        QTimer.singleShot(DUR, lambda: self.on_pick(self.opts[k]))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.c["bg"]) if not self.dark else QColor(255, 255, 255, 20))
        p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        w = (self.width() - 6) / len(self.opts)
        th = QRectF(3 + self._x * w, 3, w, self.height() - 6)
        p.setBrush(QColor(0, 0, 0, 18)); p.drawRoundedRect(th.translated(0, 1), 8, 8)
        p.setBrush(QColor(self.c["surface"])); p.drawRoundedRect(th, 8, 8)
        f = p.font(); f.setPixelSize(12)
        for k, o in enumerate(self.opts):
            on = abs(self._x - k) < .5
            f.setBold(on); p.setFont(f)
            col = QColor(self.c["text"] if on else self.c["muted"])
            if o in self.locked:
                col.setAlphaF(.4)
            p.setPen(col)
            p.drawText(self._cell(k), Qt.AlignCenter, o)


class Tile(QPushButton):
    """파일 카드 안 칸 — 아이콘 네모 + 이름."""

    def __init__(self, kind, name, c, draw, dark, parent=None):
        super().__init__(name, parent)
        self.c, self.dark = c, dark
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(70)
        self.setStyleSheet(f"QPushButton {{ background:{c['bg']}; border:none; border-radius:12px;"
                           f"color:{c['text']}; font-size:12px; font-weight:700; padding-top:34px; }}"
                           f"QPushButton:hover {{ background:{c['border']}; }}"
                           "QPushButton:disabled { color:rgba(128,128,128,.6); }")
        self.sq = IconSq(kind, c, draw, False, dark=dark, parent=self)

    def resizeEvent(self, e):
        self.sq.move((self.width() - self.sq.width()) // 2, 8)
        super().resizeEvent(e)


class NavSide(QWidget):
    """사이드바 전체. `app` = Proto 창, `draw` = app 의 `_rail_icon`."""

    MENU = [("조류계산", [("result", "결과"), ("check", "점검"), ("grid", "계통 데이터")]),
            ("해석", [("scenario", "시나리오"), ("curve", "PV·QV 곡선")])]

    def __init__(self, app, draw, parent=None):
        super().__init__(parent)
        # 🚨 2026-11-15 — 사이드바는 **진한 먹색 판**이다(밝은 · 어두운 화면 모두). 안의 조각들은
        #    여태 쓰던 색 이름(`surface` · `text` · `muted` …)을 그대로 쓰므로, 그 이름에 진한 판용 색을
        #    물린 색표 `sc` 를 만들어 넘긴다. 앱 색표(`app.c`)는 판 바탕 · 테두리에만 쓴다.
        ac = app.c
        sc = dict(ac, bg=ac["nav"], surface=ac["nav_on"], text=ac["nav_text"], muted=ac["nav_fg"],
                  border=ac["nav_line"], hair=ac["nav_line"], accent=ac["nav_text"],
                  accent_soft=ac["nav_on"], on_accent=ac["nav"], glass=ac["nav_card"],
                  glass_edge=ac["nav_line"])
        self.app, self.c, self.draw, self.theme_dark = app, sc, draw, app.dark
        self.ac = ac
        self.dark = True                 # 안의 조각은 늘 진한 판 위에 그린다
        c = self.c
        self.setFixedWidth(WIDTH)
        self.setAttribute(Qt.WA_TranslucentBackground)
        v = QVBoxLayout(self); v.setContentsMargins(12, 16, 12, 12); v.setSpacing(0)

        # 로고
        lg = QHBoxLayout(); lg.setContentsMargins(10, 4, 0, 16); lg.setSpacing(10)
        sq = QWidget(); sq.setFixedSize(28, 28)
        sq.paintEvent = lambda _e, w=sq: self._paint_logo(w)
        lg.addWidget(sq)
        t = QLabel("UNIGRID"); t.setStyleSheet(f"color:{c['text']}; font-size:15px; font-weight:800;"
                                              "letter-spacing:1px; background:transparent;")
        lg.addWidget(t); lg.addStretch()
        v.addLayout(lg)

        # K2 — 계통 파일 열기
        ob = QPushButton("   계통 파일 열기")
        ob.setCursor(Qt.PointingHandCursor); ob.setFixedHeight(42)
        ob.setStyleSheet(f"QPushButton {{ background:#ffffff; color:{INK}; border:none; border-radius:12px;"
                         "font-size:14px; font-weight:700; text-align:left; padding-left:40px; }"
                         "QPushButton:hover { background:#e6e8ee; }")
        ob.setToolTip("계통 파일을 엽니다")
        ob.clicked.connect(app.do_import)
        oi = IconSq("open", dict(c, surface="#ffffff", text="#ffffff"), draw, True, size=26, dark=True, parent=ob)
        oi.on = False
        oi.paintEvent = lambda _e, w=oi: self._paint_open(w)
        oi.move(10, 8)
        v.addWidget(ob)
        v.addSpacing(10)

        # V1 — 현재 케이스
        if app.sol is not None or getattr(app, "base_case", None) is not None:
            app._c_over = sc                 # 케이스 카드의 글자색을 진한 판용으로
            try:
                cc = app.case_card()
            finally:
                app._c_over = None
            cc.setObjectName("navcase")
            cc.setStyleSheet(f"#navcase {{ background:{ac['nav_card']}; border:1px solid {c['border']};"
                             "border-radius:14px; }")
            v.addWidget(cc)

        # 메뉴 (흰 판 하나가 두 묶음을 다 덮는다 — X1)
        self.menu = QWidget(); self.menu.setAttribute(Qt.WA_TranslucentBackground)
        mv = QVBoxLayout(self.menu); mv.setContentsMargins(0, 0, 0, 0); mv.setSpacing(0)
        self.hl = QFrame(self.menu); self.hl.setObjectName("navhl")
        self.hl.setStyleSheet(f"#navhl {{ background:{c['surface']}; border-radius:14px; }}")
        _shadow(self.hl, 24, 8, 20 if not self.dark else 60)
        self.hl.hide()
        self.items = {}
        on = app._rail_on()
        has_case = app.sol is not None
        has_base = getattr(app, "base_case", None) is not None
        n_sc = len(app.book.items) if getattr(app, "book", None) is not None else 0
        why_curve = app.curve_why() if has_base else ""
        able = {"결과": (has_case, ""), "점검": (has_case, "한계를 넘은 것 · 한계에 도달한 것"),
                "계통 데이터": (has_case, ""),
                # 2026-11-15 — 하나뿐이어도 연다. 까닭이 풍선말에만 있었다 → 화면이 만드는 법을 적는다
                "시나리오": (has_case, "조건을 바꿔 푼 결과를 나란히 봅니다"),
                "PV·QV 곡선": (has_base and not why_curve, why_curve or "")}
        for gname, items in self.MENU:
            gh = QHBoxLayout(); gh.setContentsMargins(6, 18, 6, 6); gh.setSpacing(10)
            gl = QLabel(gname); gl.setStyleSheet(f"color:{c['text']}; font-size:14px; font-weight:800; background:transparent;")
            gh.addWidget(gl)
            ln = QFrame(); ln.setFixedHeight(1); ln.setStyleSheet(f"background:{c['border']};")
            gh.addWidget(ln, 1)
            mv.addLayout(gh)
            for kind, name in items:
                ok, tip = able[name]
                it = NavItem(kind, name, c, draw, self.dark, on=(name == on), enabled=ok, tip=tip)
                it.clicked.connect(lambda n=name: self._click(n))
                it.nav = self
                mv.addWidget(it)
                self.items[name] = it
                if name == "결과":
                    self.subw = QWidget(); self.subw.setAttribute(Qt.WA_TranslucentBackground)
                    sl = QVBoxLayout(self.subw); sl.setContentsMargins(10, 0, 10, 10)
                    locked = {}
                    wd = app.dynamic_why()
                    if wd:
                        locked["다이나믹"] = wd
                    modes = ["스냅샷", "다이나믹", "비교"]
                    cur = modes.index(app.mode) if app.mode in modes else 0
                    prev = getattr(app, "_nav_seg_prev", None)
                    def _pick(m, app=app, modes=modes):
                        app._nav_seg_prev = modes.index(m)
                        app.set_mode(m)
                    # 단추 묶음 — 흰 단추 + 먹색 글자(고른 줄의 판과 같은 색이면 단추가 안 보인다)
                    self.seg = SegSlide(modes, cur, locked, dict(c, surface=ac["nav_text"], text=ac["nav"]),
                                        True, _pick, start=prev)
                    app._nav_seg_prev = cur
                    sl.addWidget(self.seg)
                    self.SUB_H = 44
                    # 첫 배치부터 옛 화면의 펼침 상태로 둔다 — 안 그러면 첫 배치는 펼친 높이로 재고
                    # 곧 접혀 줄이 옮겨 가, 흰 판이 한 줄 아래에 남았다(2026-11-03)
                    self.subw.setMaximumHeight(self.SUB_H if getattr(app, "_nav_sub_prev", on == "결과") else 0)
                    mv.addWidget(self.subw)
        v.addWidget(self.menu)
        v.addStretch(1)

        # W2 — 파일 카드
        fc = QFrame(); fc.setObjectName("navfile")
        fc.setStyleSheet(f"#navfile {{ background:{ac['nav_card']}; border:1px solid {c['border']}; border-radius:16px; }}")
        fv = QVBoxLayout(fc); fv.setContentsMargins(12, 10, 12, 10); fv.setSpacing(8)
        cap = QLabel("파일"); cap.setStyleSheet(f"color:{c['muted']}; font-size:12px; font-weight:700; background:transparent;")
        fv.addWidget(cap)
        tr = QHBoxLayout(); tr.setSpacing(8)
        ex = Tile("export", "내보내기", c, draw, self.dark); ex.clicked.connect(app.do_export); ex.setEnabled(has_case)
        xl = Tile("excel", "엑셀로 만들기", c, draw, self.dark)
        xl.setToolTip("MATPOWER · PSS/E · MatACDC 파일을 UNIGRID 엑셀로")
        xl.clicked.connect(app.open_convert)
        tr.addWidget(ex); tr.addWidget(xl)
        fv.addLayout(tr)
        br = QHBoxLayout(); br.setSpacing(4)
        sw = QFrame(); sw.setObjectName("navsw")
        sw.setStyleSheet(f"#navsw {{ background:{c['bg']}; border-radius:10px; }}")
        sh = QHBoxLayout(sw); sh.setContentsMargins(3, 3, 3, 3); sh.setSpacing(2)
        for kind, want_dark in (("sun", False), ("moon", True)):
            b = QPushButton(); b.setFixedSize(34, 26); b.setCursor(Qt.PointingHandCursor)
            sel = (self.theme_dark == want_dark)
            b.setStyleSheet(f"QPushButton {{ background:{c['surface'] if sel else 'transparent'}; border:none; border-radius:8px; }}")
            b.setToolTip("밝은 화면" if not want_dark else "어두운 화면")
            ic = IconSq(kind, dict(c, surface=c["surface"] if sel else c["bg"]), draw, False, size=26,
                        dark=self.dark, parent=b)
            ic.move(4, 0)
            if not sel:
                b.clicked.connect(app.toggle_theme)
            sh.addWidget(b)
        br.addWidget(sw); br.addStretch()
        inf = QPushButton("ⓘ  정보"); inf.setCursor(Qt.PointingHandCursor)
        inf.setStyleSheet(f"QPushButton {{ background:transparent; border:none; color:{c['muted']};"
                          "font-size:13px; font-weight:600; }")
        inf.setToolTip("판·저작권·사용 조건")
        inf.clicked.connect(app.open_about)
        br.addWidget(inf)
        fv.addLayout(br)
        v.addWidget(fc)

        QTimer.singleShot(0, lambda: self._place(on, first=True))
        # 창 배치가 끝난 뒤 한 번 더 맞춘다 (움직임이 끝난 뒤)
        QTimer.singleShot(DUR + 80, self._snap)

    # ── 그리기 도움 ──
    def _paint_logo(self, w):
        p = QPainter(w); p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(w.rect())
        p.setPen(Qt.NoPen); p.setBrush(QColor("#ffffff")); p.drawRoundedRect(r, 8, 8)   # 진한 판 위 흰 네모
        path = QPainterPath(QPointF(15.5, 5)); path.lineTo(8.5, 15.5); path.lineTo(13.5, 15.5)
        path.lineTo(12.5, 23); path.lineTo(19.5, 12.5); path.lineTo(14.5, 12.5); path.closeSubpath()
        p.setBrush(QColor(INK)); p.drawPath(path)

    def _paint_open(self, w):
        p = QPainter(w); p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(INK), 1.5); pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen); self.draw(p, "open", 3, 3, 1.0)

    def paintEvent(self, _e):
        """사이드바 판 — 진한 먹색 둥근 판 하나. 어두운 화면에서는 가는 테두리로 바탕과 가른다."""
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(self.ac["nav_line"]), 1) if self.theme_dark else Qt.NoPen)
        p.setBrush(QColor(self.ac["nav"]))
        p.drawRoundedRect(r, 20, 20)

    # ── 흰 판 · 단추 묶음 ──
    def _snap(self):
        """움직이는 중이 아니면 흰 판을 지금 고른 줄 자리에 바로 맞춘다."""
        if getattr(self, "_busy", False) or not hasattr(self, "hl"):
            return
        name = getattr(self, "_on_name", None)
        tgt = self._target(name) if name else None
        if tgt is not None and self.hl.geometry() != tgt:
            self.hl.setGeometry(tgt)
            self.app._nav_prev_rect = QRect(tgt)

    def _target(self, name):
        it = self.items.get(name)
        if it is None:
            return None
        g = QRect(it.geometry())
        if name == "결과":
            g.setHeight(g.height() + self.SUB_H)
        return g

    def _place(self, name, first=False):
        app = self.app
        self._on_name = name
        sub_open = (name == "결과")
        prev_open = getattr(app, "_nav_sub_prev", False) if first else self.subw.maximumHeight() > 0
        # 최종 배치에서 목표 자리를 잰다
        self.subw.setMaximumHeight(self.SUB_H if sub_open else 0)
        self.menu.layout().activate()
        tgt = self._target(name)
        app._nav_sub_prev = sub_open
        if tgt is None:
            self.hl.hide()
            app._nav_prev_rect = None
            return
        start = getattr(app, "_nav_prev_rect", None) if first else QRect(self.hl.geometry())
        app._nav_prev_rect = QRect(tgt)
        self.hl.show(); self.hl.lower()
        if start is None or start == tgt:
            self.hl.setGeometry(tgt)
            return
        if prev_open != sub_open:      # 단추 묶음이 펼쳐지거나 접힌다
            a = QPropertyAnimation(self.subw, b"maximumHeight", self)
            a.setDuration(DUR); a.setEasingCurve(EASE)
            a.setStartValue(self.SUB_H if prev_open else 0); a.setEndValue(self.SUB_H if sub_open else 0)
            self.subw.setMaximumHeight(self.SUB_H if prev_open else 0)
            a.start(QPropertyAnimation.DeleteWhenStopped)
        self.hl.setGeometry(start)
        b = QPropertyAnimation(self.hl, b"geometry", self)
        b.setDuration(DUR); b.setEasingCurve(EASE)
        b.setStartValue(start); b.setEndValue(tgt)
        self._busy = True

        def _end():
            self._busy = False
            self._snap()                 # 움직이는 사이 배치가 바뀌었으면 마지막에 맞춘다
        b.finished.connect(_end)
        b.start(QPropertyAnimation.DeleteWhenStopped)

    def set_on(self, name):
        """화면을 안 다시 그리고 고른 칸만 바뀐 때."""
        for n, it in self.items.items():
            it.set_on(n == name)
        self._place(name)

    def _click(self, name):
        if name == self.app._rail_on() and not (name == "결과" and not getattr(self.app, "overview_on", True)):
            return
        for n, it in self.items.items():
            it.set_on(n == name)
        self._place(name)
        QTimer.singleShot(DUR, lambda: self.app.nav_go(name))
