"""symbols.py — 전력 단선도 기호를 코드로 그린다.

그림 파일(png)을 안 쓰는 이유: 파일마다 투명 여백이 제각각이라
(부하 아이콘은 가로의 63%가 빈칸) 버스에 딱 붙이는 게 불가능했고,
크기를 줄이면 뭉개졌다. 코드로 그리면 여백이 0이고 아무리 키워도 선명하다.

기호는 전력 단선도에서 쓰는 것을 따른다:
  발전기   원 안에 물결(교류를 뜻함)
  IBR      기울인 태양광 패널 (분산전원)
  계통연계  원 안에 빗금 (바깥 계통에서 들어옴)
  변압기   맞물린 원 두 개 / 3권선은 세 개
  변환기   네모를 대각선으로 가르고 한쪽 물결(교류) 다른 쪽 등호(직류)
  부하     버스에서 나온 짧은 선 끝에 속 채운 삼각형

모든 기호는 (cx, cy) 를 한가운데로 하고 s 를 지름 삼아 그린다.
"""
from __future__ import annotations

from math import cos, sin, pi

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPen, QPainterPath, QPolygonF, QColor


def _pen(p, color, w):
    pen = QPen(QColor(color))
    pen.setWidthF(w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    return pen


def _wave(p, cx, cy, w, h, color, lw):
    """물결표 — 교류를 뜻한다."""
    _pen(p, color, lw)
    path = QPainterPath()
    n = 24
    for i in range(n + 1):
        t = i / n
        x = cx - w / 2 + w * t
        y = cy - h * sin(2 * pi * t)
        path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


def generator(p, cx, cy, s, color, bg, lw):
    """동기발전기 — 원 안에 물결."""
    r = s / 2
    _pen(p, color, lw)
    p.setBrush(QColor(bg))
    p.drawEllipse(QPointF(cx, cy), r, r)
    _wave(p, cx, cy, s * 0.56, s * 0.13, color, lw)


def infeed(p, cx, cy, s, color, bg, lw):
    """계통 연계 — 송전탑. 바깥 계통에서 전력이 들어온다는 뜻.

    MATLAB 앱이 쓰던 송전탑 그림(AC_trans_icon.png)을 선으로 옮긴 것.
    예전엔 "원 안에 빗금"으로 그렸는데 그건 표준 기호가 아니라 지어낸 것이었고
    금지 표지판처럼 읽혔다. 동기기·IBR 이 둘 다 원이라 구분도 안 됐다.
    """
    _pen(p, color, lw)
    p.setBrush(Qt.NoBrush)
    top, bot = cy - s * 0.50, cy + s * 0.50
    wt, wb = s * 0.13, s * 0.40             # 탑 꼭대기 폭, 밑동 폭
    p.drawLine(QPointF(cx - wt, top), QPointF(cx - wb, bot))
    p.drawLine(QPointF(cx + wt, top), QPointF(cx + wb, bot))
    for f, arm in ((0.18, 0.40), (0.52, 0.50)):     # 가로대 두 개
        p.drawLine(QPointF(cx - s * arm, top + s * f),
                   QPointF(cx + s * arm, top + s * f))
    p.drawLine(QPointF(cx - wt * 1.6, top + s * 0.30),      # 가운데 X 보강재
               QPointF(cx + wt * 2.4, top + s * 0.62))
    p.drawLine(QPointF(cx + wt * 1.6, top + s * 0.30),
               QPointF(cx - wt * 2.4, top + s * 0.62))


def ibr(p, cx, cy, s, color, bg, lw):
    """IBR(분산전원) — 기울인 태양광 패널.

    후보 여섯 개(패널 / 해+패널 / 해 / IEC 광전지 / 패널+변환기 / 예전 것)를
    12버스·71버스 두 크기로 그려 놓고 고른 것. 작아져도(u≈20) 칸 나눔이
    안 뭉개지고, 버스 **옆**에 붙이기 좋은 가로로 넓은 모양이다.
    예전엔 원+변환기 네모였는데 실제 크기에서 검은 덩어리로 뭉갰다.

    ※ 데이터의 종류 3은 "IBR" 이지 "태양광" 이 아니다 — 풍력·배터리도 여기로
    들어온다. 그런 케이스가 들어오면 이 그림은 뜻이 어긋나므로, 손말풍선은
    "IBR" 로 둔다.

    가로 폭을 s 에 맞춘다 — 가운데 높이의 좌우 끝이 딱 s/2 라서 버스로 가는
    선이 패널 모서리에 딱 붙는다. 기울임(k) 때문에 위·아래 모서리는 그보다
    0.13s 씩 더 나가지만 자리 잡을 때 주는 여백(u*0.32) 안이라 안 겹친다.
    """
    W, H, k = s * 1.00, s * 0.62, s * 0.13
    tl = QPointF(cx - W / 2 + k, cy - H / 2)
    tr = QPointF(cx + W / 2 + k, cy - H / 2)
    br = QPointF(cx + W / 2 - k, cy + H / 2)
    bl = QPointF(cx - W / 2 - k, cy + H / 2)
    _pen(p, color, lw)
    p.setBrush(QColor(bg))
    p.drawPolygon(QPolygonF([tl, tr, br, bl]))
    for t in (1 / 3, 2 / 3):                    # 세로 칸 — 기울기를 따라간다
        p.drawLine(QPointF(tl.x() + (tr.x() - tl.x()) * t, tl.y()),
                   QPointF(bl.x() + (br.x() - bl.x()) * t, bl.y()))
    p.drawLine(QPointF((tl.x() + bl.x()) / 2, cy),          # 가로 칸
               QPointF((tr.x() + br.x()) / 2, cy))


def transformer(p, cx, cy, s, color, bg, lw, windings=2):
    """변압기 — 맞물린 원. 2권선은 두 개, 3권선은 세 개.

    원 안을 배경색으로 채운다 — 선로 위에 얹히므로 뒤로 지나는 선이 원 안에
    비쳐 보이면 지저분하다(사용자 지시). 먼저 배경색으로 원들을 채워 뒤 선을
    가린 뒤, 윤곽선을 다시 그려 맞물린 모양을 살린다.
    """
    r = s * 0.30
    if windings == 2:
        centers = [QPointF(cx - r * 0.55, cy), QPointF(cx + r * 0.55, cy)]
    else:
        centers = [QPointF(cx + r * 0.62 * cos(ang * pi / 180),
                           cy + r * 0.62 * sin(ang * pi / 180))
                   for ang in (-90, 30, 150)]
    p.setPen(Qt.NoPen); p.setBrush(QColor(bg))       # 1) 속 채우기(뒤 선 가림)
    for c in centers:
        p.drawEllipse(c, r, r)
    _pen(p, color, lw); p.setBrush(Qt.NoBrush)        # 2) 윤곽선
    for c in centers:
        p.drawEllipse(c, r, r)


def converter(p, cx, cy, s, color, bg, lw, left="~", right="="):
    """변환기 — 네모를 대각선으로 가르고 한쪽은 교류, 다른 쪽은 직류."""
    b = s * 0.92
    box = QRectF(cx - b / 2, cy - b / 2, b, b)
    _pen(p, color, lw)
    p.setBrush(QColor(bg))
    p.drawRect(box)
    p.drawLine(box.bottomLeft(), box.topRight())
    q = b * 0.24
    # 왼쪽 위
    if left == "~":
        _wave(p, cx - b * 0.22, cy - b * 0.20, q, q * 0.30, color, lw * 0.9)
    else:
        _equals(p, cx - b * 0.22, cy - b * 0.20, q, color, lw * 0.9)
    # 오른쪽 아래
    if right == "~":
        _wave(p, cx + b * 0.22, cy + b * 0.22, q, q * 0.30, color, lw * 0.9)
    else:
        _equals(p, cx + b * 0.22, cy + b * 0.22, q, color, lw * 0.9)


def _equals(p, cx, cy, w, color, lw):
    """등호 — 직류를 뜻한다."""
    _pen(p, color, lw)
    p.drawLine(QPointF(cx - w / 2, cy - w * 0.22), QPointF(cx + w / 2, cy - w * 0.22))
    p.drawLine(QPointF(cx - w / 2, cy + w * 0.22), QPointF(cx + w / 2, cy + w * 0.22))


def load(p, x, y, s, color, lw, angle=90.0):
    """부하 — 버스에서 나온 짧은 선 끝에 속 채운 삼각형.

    angle 은 삼각형이 향하는 방향(도). 기본은 아래쪽.
    버스에 **붙여서** 그리므로 떨어져 보이지 않는다.
    """
    a = angle * pi / 180
    ux, uy = cos(a), sin(a)
    x0, y0 = x + ux * s * 0.30, y + uy * s * 0.30      # 버스 바로 옆에서 시작
    x1, y1 = x + ux * s * 0.70, y + uy * s * 0.70      # 삼각형이 시작하는 곳
    _pen(p, color, lw)
    p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
    w = s * 0.24
    px, py = -uy, ux                                   # 진행 방향의 직각
    tri = QPolygonF([
        QPointF(x1 + px * w, y1 + py * w),
        QPointF(x1 - px * w, y1 - py * w),
        QPointF(x + ux * s * 1.15, y + uy * s * 1.15),
    ])
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawPolygon(tri)


def bus(p, cx, cy, r, color, bg, lw):
    """버스 — 작고 속 찬 점."""
    _pen(p, bg, lw)
    p.setBrush(QColor(color))
    p.drawEllipse(QPointF(cx, cy), r, r)


# 노드 성격 → 그리는 함수와 크기(버스 기본 크기의 몇 배인지)
NODE_DRAW = {
    "동기기": (generator, 1.00),
    # 패널은 가로 폭이 곧 s 라서 1.00 이면 발전기 원과 지름이 같아진다.
    # (예전 원+네모 기호는 위아래로 쌓느라 작아 보여서 1.05 로 키웠던 것)
    "IBR":    (ibr, 1.00),
    "송전":   (infeed, 1.00),
    "3권선":  (lambda p, x, y, s, c, bg, lw: transformer(p, x, y, s, c, bg, lw, 3),
               1.05),
}
EDGE_DRAW = {
    "변압기": (lambda p, x, y, s, c, bg, lw: transformer(p, x, y, s, c, bg, lw, 2),
               0.92),
    "IC":     (lambda p, x, y, s, c, bg, lw: converter(p, x, y, s, c, bg, lw,
                                                       "~", "="), 0.80),
    "DCDC":   (lambda p, x, y, s, c, bg, lw: converter(p, x, y, s, c, bg, lw,
                                                       "=", "="), 0.80),
}
