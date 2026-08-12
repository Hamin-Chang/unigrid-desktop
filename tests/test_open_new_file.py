# -*- coding: utf-8 -*-
"""다른 파일을 열면 앞 계통이 깨끗이 지워지나 (2026-08-12).

🚨 원래 있던 결함 — 아직 계산 안 한 「바꾼 것」을 둔 채 다른 파일을 열면
   `_solved` 의 원본 갱신 분기(`not self.changes`)가 건너뛰어져
   **화면은 새 계통인데 base_case·시나리오·곡선은 앞 계통 것**으로 남았다.
   (case14 에서 선로를 끈 채 case118 을 여니 화면 118버스 / base_case case14)

⚠️ 이 시험은 반드시 **진짜 여는 길**(`open_path` → `_start_solve`)로 가야 한다.
   `_solved` 만 직접 부르면 그 길에만 있는 처리를 건너뛰어 결함이 안 잡힌다
   (2026-08-12 에 실제로 여기서 갈렸다 — 고쳤는데도 '안 고쳐졌다'로 보였다).
"""
import os
import sys
import time
from pathlib import Path

REPO = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/unigrid-desktop")
V14 = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid"
           "/Phase A_Balance/newest/v14")
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox        # noqa: E402

qapp = QApplication([])
import app as APP                                              # noqa: E402
QMessageBox.warning = staticmethod(lambda *a, **k: None)
import scenario as SC                                          # noqa: E402

win = APP.Proto()
win.show()


def open_file(p):
    """진짜 [불러오기] 와 같은 길 — `_start_solve` 를 부르고 끝날 때까지 기다린다."""
    win.open_path(str(p))
    for _ in range(9000):
        qapp.processEvents()
        th = getattr(win, "thread", None)
        if th is not None and not th.isRunning() and win.sol is not None:
            break
        time.sleep(0.01)
    qapp.processEvents()


open_file(V14 / "cases_v2/AConly_case14_v2.xlsx")
print("연 파일     :", Path(win.base_case.case_name).name,
      "· 화면 버스", win.sol.AC.shape[0])

win.changes = [SC.Cell(table="AC_Line_dat", row=2, col=12, value=0.0,
                       label="선로 3 끄기")]
win.task = "PV·QV 곡선"

open_file(V14 / "cases_v2/AConly_case118_v2.xlsx")
print("다음 파일   : 화면 버스", win.sol.AC.shape[0],
      "· base_case", Path(win.base_case.case_name).name,
      "· 남은 바꾼 것", len(win.changes),
      "· 갈래", win.task)

ok = (win.sol.AC.shape[0] == 118
      and "case118" in win.base_case.case_name
      and not win.changes
      and win.cur is None)
print("✅ 새 계통으로 깨끗이 넘어갔다" if ok else "🚨 아직 앞 계통이 남아 있다")
sys.exit(0 if ok else 1)
