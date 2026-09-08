# -*- coding: utf-8 -*-
"""화면을 좌표로 훑어 **겹침·잘림**을 찾는다 (2026-09-08).

눈으로 보면 «괜찮아 보이는» 것이 숫자로는 겹쳐 있다(2026-09-08 버스 막대 28쌍).
그래서 세 가지를 잰다.

  1. 형제 겹침 — 같은 부모 아래 **보이는** 위젯 둘의 사각형이 겹치나
  2. 글자 잘림 — 단추·글자가 제 `sizeHint` 보다 좁게 눌렸나
  3. 판 밖 — 자식이 부모 사각형을 벗어나나
"""
import os, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import warnings; warnings.filterwarnings("ignore")
from PySide6.QtCore import QRect
from PySide6.QtWidgets import (QApplication, QMessageBox, QWidget, QLabel,
                               QPushButton, QComboBox, QTableWidget, QTabWidget,
                               QScrollArea, QSplitter, QAbstractScrollArea)
qapp = QApplication([])
import app as APP
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))

def pump(s=0.7):
    e = time.time() + s
    while time.time() < e:
        qapp.processEvents(); time.sleep(0.01)

def abs_rect(w, root):
    try:
        return QRect(w.mapTo(root, w.rect().topLeft()), w.size())
    except Exception:
        return None

SKIP = (QScrollArea, QSplitter, QAbstractScrollArea)

def check(root, tag, out):
    """한 화면을 훑는다."""
    # ── 1) 형제 겹침 ──
    parents = {}
    for w in root.findChildren(QWidget):
        if not w.isVisible() or w.width() <= 0 or w.height() <= 0:
            continue
        parents.setdefault(w.parent(), []).append(w)
    for par, kids in parents.items():
        # 레이아웃이 관리하는 형제만 본다(스크롤 안쪽 등은 겹쳐도 정상)
        if par is None or isinstance(par, SKIP):
            continue
        vis = [k for k in kids if not isinstance(k, SKIP)]
        for i in range(len(vis)):
            for j in range(i + 1, len(vis)):
                a, b = vis[i], vis[j]
                if a.isAncestorOf(b) or b.isAncestorOf(a):
                    continue
                ra, rb = a.geometry(), b.geometry()
                ov = ra.intersected(rb)
                if ov.width() > 2 and ov.height() > 2:
                    out.append(("겹침", tag,
                                f"{a.__class__.__name__}«{(a.text() if hasattr(a,'text') else '')[:14]}» "
                                f"× {b.__class__.__name__}«{(b.text() if hasattr(b,'text') else '')[:14]}» "
                                f"— {ov.width()}×{ov.height()}px"))
    # ── 2) 글자 잘림 ──
    texty = (root.findChildren(QLabel) + root.findChildren(QPushButton)
             + root.findChildren(QComboBox))
    for w in texty:
        if not w.isVisible() or w.width() <= 0:
            continue
        txt = w.text() if hasattr(w, "text") else (w.currentText() if isinstance(w, QComboBox) else "")
        if not txt or getattr(w, "wordWrap", lambda: False)():
            continue
        need = w.sizeHint().width()
        if need > w.width() + 1:
            out.append(("잘림", tag,
                        f"{w.__class__.__name__}«{txt[:20]}» {w.width()}px 인데 {need}px 필요"
                        f" (−{need - w.width()})"))
        needh = w.sizeHint().height()
        if needh > w.height() + 1:
            out.append(("눌림", tag,
                        f"{w.__class__.__name__}«{txt[:20]}» 높이 {w.height()}px 인데 {needh}px 필요"))
    # ── 3) 판 밖으로 ──
    # ⚠️ **스크롤 안쪽은 부모보다 커도 정상이다** — 그게 스크롤이 하는 일이다.
    #    이걸 안 걸렀더니 열 선택 목록의 단추 수백 개가 「판 밖」으로 잡혔다.
    def in_scroll(w):
        q = w.parent()
        while q is not None:
            if isinstance(q, QAbstractScrollArea):
                return True
            q = q.parent()
        return False

    for w in root.findChildren(QWidget):
        par = w.parent()
        if (not w.isVisible() or par is None or isinstance(par, SKIP)
                or w.width() <= 0 or w.height() <= 0 or in_scroll(w)):
            continue
        pr = par.rect()
        r = w.geometry()
        if not pr.contains(r):
            dx = max(0, r.left() * -1, r.right() - pr.right())
            dy = max(0, r.top() * -1, r.bottom() - pr.bottom())
            if dx > 2 or dy > 2:
                out.append(("판 밖", tag,
                            f"{w.__class__.__name__}#{w.objectName() or '-'} 이 "
                            f"{par.__class__.__name__}#{par.objectName() or '-'} 밖으로 "
                            f"가로 {dx}px · 세로 {dy}px  (자리 {r.x()},{r.y()} {r.width()}×{r.height()})"))

def check_tables(root, tag, out):
    """표의 **마지막 열**이 보이는 자리를 넘어가나 (2026-09-08 판 안쪽 여백 뒤).

    가로 스크롤이 있어 «못 보는» 것은 아니지만, 여백을 준 만큼 열이 밀려
    전에 다 보이던 표가 잘려 보일 수 있다.
    """
    for t in root.findChildren(QTableWidget):
        if not t.isVisible() or t.columnCount() == 0:
            continue
        need = sum(t.columnWidth(i) for i in range(t.columnCount()))
        if t.verticalHeader().isVisible():
            need += t.verticalHeader().width()
        vw = t.viewport().width()
        if need > vw + 1:
            out.append(("열 넘침", tag,
                        f"표 {t.columnCount()}열이 {need}px 인데 보이는 자리는 {vw}px"
                        f" (−{need - vw})"))


win = APP.Proto(); win.resize(1700, 1000); win.show(); pump(0.5)
win._start_solve(str(REPO / "cases" / "ACDC_case24_MatACDC_24h.xlsx"))
for _ in range(60):
    pump(0.5)
    if getattr(win, "sol", None) is not None:
        break
pump(1.2)

found = []
root = win.centralWidget()
check(root, "밝게·전압", found)
check_tables(root, "밝게·전압", found)

# 그래프 탭 넷을 돈다
gt = None
for tw in root.findChildren(QTabWidget):
    names = [tw.tabText(i) for i in range(tw.count())]
    if any("조류" in n for n in names):
        gt = tw; break
if gt is not None:
    for i in range(gt.count()):
        gt.setCurrentIndex(i); pump(0.7)
        check(win.centralWidget(), f"밝게·{gt.tabText(i)}", found)
        check_tables(win.centralWidget(), f"밝게·{gt.tabText(i)}", found)

# 어두운 화면
win.toggle_theme(); pump(1.0)
check(win.centralWidget(), "어둡게", found)
win.toggle_theme(); pump(0.6)

# 좁은 창
win.resize(1400, 900); pump(1.0)
check(win.centralWidget(), "1400×900", found)

seen, uniq = set(), []
for kind, tag, msg in found:
    key = (kind, msg)
    if key in seen:
        continue
    seen.add(key); uniq.append((kind, tag, msg))

import collections
cnt = collections.Counter(k for k, _, _ in uniq)
print(f"\n=== 찾은 것 {len(uniq)}건 ===  " + " · ".join(f"{k} {v}" for k, v in cnt.items()))
for want in ("겹침", "잘림", "눌림", "판 밖", "열 넘침"):
    rows = [(t, m) for k, t, m in uniq if k == want]
    if not rows:
        continue
    print(f"\n── {want} {len(rows)}건 ──")
    for t, m in rows[:25]:
        print(f"  ({t}) {m}")
    if len(rows) > 25:
        print(f"  … 그 밖 {len(rows)-25}건")
if not uniq:
    print("  없음")


# 판정 — 「열 넘침」은 가로 스크롤로 보는 구조라 실패로 세지 않는다
bad = [1 for k, _, _ in uniq if k != "열 넘침"]
print(f"\n>>> 대조 {len(uniq)}개 · 실패 {len(bad)}건")
