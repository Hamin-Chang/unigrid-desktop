# -*- coding: utf-8 -*-
"""X1 (b) 엑셀로 만들기 — 변환 창을 앱에서 실제로 눌러 보고 찍는다.

  1) 창이 뜨고 단추 셋이 있나
  2) PSS/E 단추 → 파일 고르기 → 저장까지 **실제로 파일이 만들어지나**
  3) 만든 파일을 앱이 그대로 불러와 계산되나
  4) MatACDC 는 `.m` 두 개를 받아 AC/DC 케이스를 만들고 저장·계산되나
"""
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/unigrid-desktop")
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (QApplication, QFileDialog,      # noqa: E402
                               QMessageBox, QPushButton)

qapp = QApplication([])
import app as APP                                              # noqa: E402
import app_engine                                              # noqa: E402
from load_case import load_case                                # noqa: E402

bad = 0
seen = []


def ok(cond, name, extra=""):
    global bad
    print(f"  {'✅' if cond else '🚨'} {name}" + (f"  — {extra}" if extra else ""))
    if not cond:
        bad += 1


QMessageBox.information = staticmethod(lambda *a, **k: seen.append(("알림", a[2] if len(a) > 2 else "")))
QMessageBox.warning = staticmethod(lambda *a, **k: seen.append(("경고", a[2] if len(a) > 2 else "")))
# MatACDC 는 "AC 먼저, DC 다음" 안내를 띄우고 확인을 받는다 — 자동으로 눌러 준다.
QMessageBox.question = staticmethod(lambda *a, **k: (seen.append(("물음", a[2] if len(a) > 2 else "")), QMessageBox.Ok)[1])

tmp = Path(tempfile.mkdtemp(prefix="unigrid_shotconv_"))
RAW = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/03_전기연자문_2026_3/"
           "04_python_conversion/02_GitHub_unigrid/acdc_powerflow/grids/psse_3w_sample.raw")
SAVED = tmp / "psse_3w_sample_unigrid.xlsx"

win = APP.Proto()
win.resize(1500, 950)
win.show()


def pump(s=0.3):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


pump()

# ── 1. 창이 뜨나 ──────────────────────────────────────────────────────
print("1) 변환 창")
dlg = APP.ConvertDialog(win, APP.C if hasattr(APP, "C") else win.c)
dlg.show()
pump()
btns = [b.text().split("\n")[0] for b in dlg.findChildren(QPushButton)]
ok(any("MATPOWER" in t for t in btns), "MATPOWER 단추가 있다")
ok(any("PSS/E" in t for t in btns), "PSS/E 단추가 있다")
ok(any("MatACDC" in t for t in btns), "MatACDC 단추가 있다")
dlg.grab().save(str(OUT / "shot_convert_1_창.png"))

# ── 2. PSS/E → 저장까지 ───────────────────────────────────────────────
print("\n2) PSS/E 를 골라 엑셀로 저장")
if RAW.is_file():
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(RAW), ""))
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(SAVED), ""))
    seen.clear()
    dlg._pick("PSS/E  (.raw)", "PSS/E 계통 (*.raw *.RAW)")
    pump()
    ok(SAVED.is_file(), "엑셀이 실제로 만들어진다", SAVED.name)
    ok(any(k == "알림" for k, _ in seen), "만들었다고 알린다",
       seen[0][1].splitlines()[0] if seen else "")

    # ── 3. 만든 파일로 계산되나 ──────────────────────────────────────
    print("\n3) 만든 엑셀을 그대로 불러와 계산")
    s1 = app_engine.solve(load_case(str(RAW)))
    s2 = app_engine.solve(load_case(str(SAVED)))
    ok(s2.converged, "풀린다", f"반복 {s2.iters}회")
    import numpy as np
    dv = float(np.nanmax(np.abs(s1.AC[:, 1, 0] - s2.AC[:, 1, 0])))
    ok(dv < 1e-9, "원본과 같은 답이다", f"전압차 {dv:.2e} pu")
else:
    print("  ⏭  psse_3w_sample.raw 이 없어 건너뛴다")

# ── 4. MatACDC — `.m` 두 개를 받아 AC/DC 케이스를 만든다 ─────────────
print("\n4) MatACDC 단추 — .m 두 개로 AC/DC 케이스")
MC = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/"
          "matpower8.0/MatACDC1.0/Cases")
ACM = MC / "PowerflowAC/case5_stagg.m"
DCM = MC / "PowerflowDC/case5_stagg_MTDCslack.m"
SAVED2 = tmp / "matacdc_case5_unigrid.xlsx"
if ACM.is_file() and DCM.is_file():
    picks = iter([(str(ACM), ""), (str(DCM), "")])
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: next(picks))
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(SAVED2), ""))
    seen.clear()
    dlg._pick("MatACDC", "")
    pump()
    ok(SAVED2.is_file(), "AC/DC 엑셀이 만들어진다", SAVED2.name)
    import read_v2
    ok(read_v2.read_mode(SAVED2) == 0, "Mode 가 0(AC/DC 혼합)이다")
    s3 = app_engine.solve(load_case(str(SAVED2)))
    ok(s3.converged, "만든 파일이 풀린다", f"반복 {s3.iters}회")
    ok(s3.DC.shape[0] == 3, "DC 버스 3개가 들어 있다", f"{s3.DC.shape[0]}개")
else:
    print("  ⏭  MatACDC 케이스 폴더가 없어 건너뛴다")

app_engine.shutdown()
print(f"\n{'✅ 전부 통과' if bad == 0 else f'🚨 {bad}건 틀림'}")
print(f"찍은 그림: {OUT / 'shot_convert_1_창.png'}")
sys.stdout.flush()
os._exit(1 if bad else 0)
