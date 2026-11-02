# -*- coding: utf-8 -*-
"""한계에 「닿은」 발전기도 포화로 표시하나 (2026-11-01, 앱 2.3).

  엔진은 `Q > Qmax` 로만 판정해 199.9999999998 같은 발전기를 「한계 안」으로 둔다.
  `app_engine._mark_touching` 이 표시만 고친다 — 엔진 계산은 안 건드린다.

      python tests/test_touch_limit.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import app_engine                                  # noqa: E402

inf = np.inf
# [종류, 버스, P, Pmin, Pmax, satP, Q, Qmin, Qmax, satQ, Qlim종류]
a = np.array([
    [3, 216, 0, -inf, inf, 0, 199.9999999998, -50, 200, 0, 0],   # Q 상한에 닿음
    [3, 218, 0, -inf, inf, 0, 137.4, -50, 200, 0, 0],            # 한계 안
    [3, 223, 0, -inf, inf, 0, -50.0000000001, -50, 200, 0, 0],   # Q 하한에 닿음
    [1, 101, 99.99999999, 0, 100, 0, 10, -inf, inf, 0, 0],       # P 상한 · Q 한계 없음
    [3, 230, 0, -inf, inf, 0, 0.8732, -1, 0.8732, 1, 2],         # 엔진이 이미 포화(용량 원)
    [3, 3, 0, 0, 100, 0, 28.39, 0, 40, 0, 0],                    # 전압제어 P=Pmin — P 는 입력값이라 안 찍음
])
b = app_engine._mark_touching(a.copy())
assert list(b[:, 9]) == [1, 0, -1, 0, 1, 0], b[:, 9]
assert list(b[:, 5]) == [0, 0, 0, 1, 0, 0], b[:, 5]
assert list(b[:, 10]) == [1, 0, 1, 0, 2, 0], b[:, 10]
print("전부 통과")
