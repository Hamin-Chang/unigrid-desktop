# -*- coding: utf-8 -*-
"""머리 줄 전수 조사 고침 확인 (2026-09-01 「①②③④ 다 고쳐」).

  ① 표 드롭다운 둘에 이름표(「표」·「고칠 표」)가 붙었나
  ② 계통 데이터 고르개 항목에 「(N줄)」 단위가 붙었나
  ③ 결과용 컨트롤(VSC 표·찾기·N줄)이 계통 데이터에서는 숨고 결과 표에서는 보이나
     — 다시 그리는 길(rebuild)과 안 그리는 길(탭 신호) 둘 다
  ④ 위반 단추가 「⚠ 위반 N」 으로 정체를 밝히나
"""
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import warnings                                              # noqa: E402
warnings.filterwarnings("ignore")
from PySide6.QtWidgets import (QApplication, QMessageBox,    # noqa: E402
                               QComboBox, QLabel, QPushButton, QLineEdit)

qapp = QApplication([])
import app as APP                                            # noqa: E402
for _n in ("warning", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
import app_engine                                            # noqa: E402
from load_case import load_case                              # noqa: E402

CASE = V14 / "cases_v2/ACDC_case24_MatACDC_v2.xlsx"
OUT = Path(os.environ.get("SHOT_OUT", "/tmp"))
fails = []


def check(label, got, want):
    if got == want:
        print(f"  ✅ {label:<52} {got}")
    else:
        print(f"  ❌ {label:<52} {got}  (바라던 값 {want})")
        fails.append(label)


class Fake:
    def __init__(self, case):
        self.loaded_case = case
        self.case = None


def pump(t=0.7):
    end = time.time() + t
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


win = APP.Proto()
win.resize(1512, 950)
win.show()
pump(0.4)
case = load_case(str(CASE))
win.thread = Fake(case)
win._last_path = str(CASE)
win._solved(app_engine.solve(case))
win.rebuild()
pump(1.4)


def labels():
    return [w.text() for w in win.findChildren(QLabel) if w.isVisible()]


def vis(txt):
    """그 글의 라벨이 화면에 보이나."""
    return any(w.text() == txt and w.isVisible() for w in win.findChildren(QLabel))


def find_box_count():
    """보이는 「버스 번호로 찾기」 가 몇 벌인가."""
    return sum(1 for w in win.findChildren(QLabel)
               if w.text() == "버스 번호로 찾기" and w.isVisible())


print("[1] 이름표 — 결과 표를 보는 중")
check("「표」 이름표가 보이나", vis("표"), True)
check("찾기는 한 벌인가", find_box_count(), 1)
check("VSC 표 라벨이 보이나", vis("VSC 표"), True)

print("[2] 위반 단추")
vb = next((b for b in win.findChildren(QPushButton)
           if b.isVisible() and b.text().startswith("⚠")), None)
check("단추가 있나", vb is not None, True)
check("「위반」 이라고 밝히나", vb is not None and "위반" in vb.text(), True)

print("[3] 계통 데이터로 — 결과용 컨트롤이 숨나 (rebuild 길)")
win.table_tab = "계통 데이터"
win.rebuild()
pump(1.0)
win.grab().save(str(OUT / "head_grid.png"))
# 좁은 화면(`_narrow`)에서는 이름표를 접는다 — 화면 폭에 따라 기대값이 갈린다
check("「고칠 표」 이름표", vis("고칠 표"), not win._narrow())
check("찾기가 계통 데이터 것 한 벌뿐인가", find_box_count(), 1)
check("VSC 표 라벨이 숨나", vis("VSC 표"), False)
gp = [w for w in win.findChildren(QComboBox) if w.isVisible()
      and w.count() and w.itemText(0).endswith("줄")]
check("고르개 항목에 「N줄」 단위가 붙나", len(gp) >= 1, True)

print("[4] 결과 표로 돌아오면 도로 보이나 (rebuild 길)")
win.table_tab = "AC 결과"
win.rebuild()
pump(1.0)
win.grab().save(str(OUT / "head_res.png"))
check("VSC 표 라벨이 돌아왔나", vis("VSC 표"), True)
check("찾기가 결과 것 한 벌인가", find_box_count(), 1)

print("[5] 탭 신호 길 — 화면을 다시 안 그리고 옮겨도 맞나")
tt = win._tabs
for i in range(tt.count()):
    if tt.tabText(i).startswith("수렴"):
        tt.setCurrentIndex(i)
        pump(0.8)
        break
check("수렴에서 VSC 표가 숨나", vis("VSC 표"), False)
check("수렴에서 찾기가 숨나", find_box_count(), 0)
for i in range(tt.count()):
    if tt.tabText(i).startswith("AC 결과"):
        tt.setCurrentIndex(i)
        pump(0.8)
        break
check("돌아오면 VSC 표가 도로 보이나", vis("VSC 표"), True)
check("돌아오면 찾기가 도로 보이나", find_box_count(), 1)

print()
if fails:
    print(f"🚨 실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("✅ 전부 통과")
