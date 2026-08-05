# -*- coding: utf-8 -*-
"""엔진을 일부러 못 찾게 만들고, 안내 대화상자와 [직접 고르기] 버튼이 실제로 도는지 본다.

확인하는 것
  1. 엔진을 못 찾으면 **안 죽고** 안내 대화상자가 뜬다 (R2)
  2. 그 상자에 [직접 고르기…] 버튼이 **실제로 있다** (안내문이 약속한 것)
  3. 자리를 고르면 기억하고, **그 자리로 다시 풀어** 결과가 들어온다

⚠️ `~/.unigrid/settings.json` 은 건드리지 않는다 — 시험용 임시 파일로 바꿔치기한다.
"""
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = Path(tempfile.mkdtemp(prefix="unigrid_shot_"))   # 확인용 그림을 남길 자리

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("MWPYTHON", None)
sys.path.insert(0, str(REPO / "src"))

from PySide6.QtCore import QTimer                                   # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

qapp = QApplication([])

import engine_path                                                  # noqa: E402
import app_engine                                                   # noqa: E402
import app as APP                                                   # noqa: E402

ORIGINAL_FIND = engine_path.find_mwpython   # 바꿔치기 전에 원본을 챙겨 둔다
REAL = engine_path.find_mwpython()          # 이 맥의 진짜 자리 (나중에 고르는 시늉에 쓴다)
print("이 맥의 진짜 mwpython:", REAL)

# 설정 파일을 임시 자리로 — 사용자 홈은 안 건드린다
tmp = Path(tempfile.mkdtemp(prefix="unigrid_test_"))
engine_path._SETTINGS = tmp / "settings.json"

# 아무것도 없는 컴퓨터인 척
blind_steps = engine_path.search(env={}, app_roots=[], runtime_roots=[], remembered=None)


def blind(*a, **k):
    raise engine_path.EngineNotFound(blind_steps)


engine_path.find_mwpython = blind
app_engine._Worker.shutdown()               # 이미 떠 있는 일꾼이 있으면 정리

w = APP.Proto()
w.resize(1400, 900)
w.show()

result = {"안내상자": False, "버튼": False, "기억함": False, "다시풀림": False}
CASE = str(REPO / "cases" / "AConly_case14.xlsx")


def step1_open():
    w._start_solve(CASE)
    QTimer.singleShot(6000, step2_dialog)


def step2_dialog():
    box = next((x for x in qapp.topLevelWidgets()
                if isinstance(x, QMessageBox) and x.isVisible()), None)
    if box is None:
        print("❌ 안내 상자가 안 떴다"); qapp.quit(); return
    result["안내상자"] = True
    print("✅ 안내 상자:", box.windowTitle())
    shot = OUT / "안내상자.png"
    box.grab().save(str(shot))
    print("   그림:", shot)

    names = [b.text() for b in box.buttons()]
    print("   버튼:", names)
    pick = next((b for b in box.buttons() if "직접" in b.text()), None)
    if pick is None:
        print("❌ [직접 고르기] 버튼이 없다"); box.reject(); qapp.quit(); return
    result["버튼"] = True

    # 파일 고르기 창 대신 진짜 자리를 돌려주게 바꿔치기
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(REAL), ""))
    # 기억한 뒤에는 진짜 찾기로 되돌린다 (기억한 자리를 실제로 쓰는지 보려고)
    engine_path.find_mwpython = ORIGINAL_FIND
    QTimer.singleShot(300, close_info)
    pick.click()


def close_info():
    """'자리를 기억했습니다' 안내를 닫아 준다 (그래야 다시 풀기가 이어진다)."""
    box = next((x for x in qapp.topLevelWidgets()
                if isinstance(x, QMessageBox) and x.isVisible()), None)
    if box is not None:
        print("   알림:", box.windowTitle())
        box.accept()
    QTimer.singleShot(300, check_remember)


def check_remember():
    saved = engine_path._read_settings().get("mwpython")
    print("   기억한 자리:", saved)
    result["기억함"] = saved == str(REAL)
    QTimer.singleShot(25000, step3_result)


def step3_result():
    sol = getattr(w, "sol", None)
    if sol is not None:
        result["다시풀림"] = True
        print(f"✅ 다시 풀림 — 수렴 {sol.converged} · 반복 {sol.iters}회 · "
              f"AC {sol.AC.shape[0]}버스")
        w.grab().save(str(OUT / "고른뒤_결과.png"))
    else:
        print("❌ 다시 풀리지 않았다")
    print("\n결과:", result)
    print("모두 통과" if all(result.values()) else "⚠️ 실패 있음")
    app_engine.shutdown()
    qapp.exit(0 if all(result.values()) else 1)



QTimer.singleShot(500, step1_open)
sys.exit(qapp.exec())
