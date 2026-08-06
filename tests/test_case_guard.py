# -*- coding: utf-8 -*-
"""위험한 케이스 파일이 `load_case` 에서 막히나.

  MATPOWER `.m` 은 자료 파일이 아니라 **함수**다. 어떤 파일은 숫자 표 아래에 단위 변환
  코드를 달아 두는데, 이 앱의 변환기는 정규식으로 표만 긁으므로 그 줄이 **안 돈다**
  → 부하 1000배·임피던스 16배짜리 계통이 조용히 만들어진다.

  🚨 2026-08-06 전에는 `app.py` 만 걸렀다 — 시험·스크립트로 읽으면 그냥 들어왔다.
     이제 `load_case()` 가 맨 먼저 건다. 이 검사가 그것을 지킨다.

      python tests/test_case_guard.py
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import case_guard                                   # noqa: E402
from load_case import load_case                     # noqa: E402

MP = Path("/Users/hamin/Desktop/GML/01_핵심_연구프로젝트/ACDC/01_Unigrid/matpower8.0/data")
bad = 0


def ok(cond, what, note=""):
    global bad
    print(f"  {'✅' if cond else '🚨'} {what}" + (f"  — {note}" if note else ""))
    if not cond:
        bad += 1


print("위험한 케이스가 load_case 에서 막히나")

if not MP.is_dir():
    print(f"  ⏭  MATPOWER 자료 폴더가 없어 건너뛴다 ({MP})")
    sys.exit(0)

# 1. 함정이 있는 파일 — 막혀야 한다
hits = case_guard.matpower_post_matrix_edits(MP / "case33bw.m")
ok(len(hits) >= 1, "case33bw.m 에서 표 아래 고치는 줄을 찾는다",
   f"{len(hits)}줄 · 예: {hits[0][1][:46]}" if hits else "")
try:
    load_case(str(MP / "case33bw.m"))
    ok(False, "case33bw.m 은 load_case 에서 막힌다")
except ValueError as exc:
    msg = str(exc)
    ok("그대로 읽으면 안 됩니다" in msg, "case33bw.m 은 load_case 에서 막힌다")
    ok("이렇게 하세요" in msg, "무엇을 하라고 알려 준다",
       "MATLAB 에서 내보내거나 UniGrid 엑셀을 열라고 안내")
    ok(any(str(n) in msg for n, _ in hits[:1]), "몇 행이 문제인지 짚어 준다",
       f"{hits[0][0]}행")

# 2. 멀쩡한 파일 — 그냥 읽혀야 한다
c = load_case(str(MP / "case14.m"))
ok(c.tables["AC_Bus_dat"].shape[0] == 14, "case14.m 은 그대로 읽힌다", "AC 버스 14개")
ok(not case_guard.matpower_post_matrix_edits(MP / "case14.m"),
   "case14.m 에는 걸릴 줄이 없다")

# 3. 엑셀은 이 함정이 없다 — 검사에 안 걸린다
c = load_case(str(REPO / "cases/AConly_case14.xlsx"))
ok(c.tables["AC_Bus_dat"].shape[0] == 14, "엑셀은 그대로 읽힌다")
case_guard.check_case_file(REPO / "cases/AConly_case14.xlsx")   # 예외가 안 나야 한다
ok(True, "엑셀은 검사가 통과시킨다 (.m 만 본다)")

# 4. MATPOWER 번들 전체에서 몇 개가 걸리나 — 숫자가 달라지면 알아채려고 못 박는다
caught = [p.name for p in sorted(MP.glob("case*.m"))
          if case_guard.matpower_post_matrix_edits(p)]
ok(len(caught) >= 20, "번들에서 걸리는 것이 20개 이상",
   f"{len(caught)}개 · {', '.join(caught[:4])} …")

print(f"\n{'✅ 전부 통과' if bad == 0 else f'🚨 {bad}건 틀림'}")
sys.exit(1 if bad else 0)
