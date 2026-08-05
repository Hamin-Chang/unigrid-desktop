"""case_guard.py — 케이스 파일을 읽기 전에 위험한 형태를 걸러낸다 (2026-08-03 신설).

왜 있나
    MATPOWER 케이스 `.m` 은 **자료 파일이 아니라 함수**다. 어떤 파일은 숫자 표 아래에
    단위 변환 코드를 달아 두고, MATPOWER 는 파일을 실행하므로 그 줄이 실제로 돈다.
    반면 공개 패키지의 변환기(`unigrid_convert.matpower_to_case`)는 **정규식으로 표만
    긁어** 읽으므로 그 줄이 **돌지 않는다** → 단위가 어긋난 계통이 조용히 만들어진다.

    실제로 겪은 것 (`case33bw.m`, 2026-08-03):
        mpc.bus(:, [PD, QD]) = mpc.bus(:, [PD, QD]) / 1e3;           부하가 kW 로 적혀 있다
        mpc.branch(:, [BR_R BR_X]) = ... / (Vbase^2 / Sbase);         임피던스가 ohm 으로 적혀 있다
    → 부하 **1000배**(3.715 MW 를 3715 MW 로), 임피던스 **16.03배** → 발산.
    ⚠️ 임피던스 쪽은 방향이 반대라 헷갈린다 — UniGrid `AC Line Data` 4·5열은 **ohm 단위**라
    표의 수가 이미 맞는 값인데, 변환기가 "MATPOWER 니까 pu 겠지" 하고 Zbase 를 한 번 더 곱한다.

    MATPOWER 8.0 번들 76개 중 **24개**가 여기 해당한다(전부 배전 계통).
    유형은 네 가지 — 부하 kW→MW(23) · 선로 ohm→pu(21) · 역률로 무효부하 배분(1) ·
    발전기 한계 덮어쓰기(1). **두 가지만 흉내 내면 나머지가 조용히 틀리므로 흉내 내지 않고 막는다.**

어디에 사는가
    공개 패키지(`acdc_powerflow`)는 건드리지 않는다. 이 앱에서만 거르므로
    `load_case` 를 부르는 대신 여기의 `load_case_checked` 를 부른다.
"""

from __future__ import annotations

import re
from pathlib import Path

# 주석을 뗀 뒤, mpc.bus/branch/gen/gencost 의 **일부를 지정해 값을 넣는** 줄.
# 표 정의(`mpc.bus = [`)는 괄호가 없어 걸리지 않는다. `==` 도 제외한다.
_POST_EDIT = re.compile(
    r"^[^%\n]*?\bmpc\.(bus|branch|gen|gencost)\s*\([^)]*\)\s*=(?!=)", re.MULTILINE)


def matpower_post_matrix_edits(path: str | Path) -> list[tuple[int, str]]:
    """표 아래에서 값을 고치는 줄을 찾는다. (줄번호, 그 줄) 목록 — 비었으면 안전."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if _POST_EDIT.match(line.split("%", 1)[0]):     # 주석 떼고 본다
            hits.append((i, line.strip()))
    return hits


def check_case_file(path: str | Path) -> None:
    """읽어도 되는 파일인지 본다. 위험하면 ValueError. 안전하면 아무 일도 안 한다."""
    p = Path(path)
    if p.suffix.lower() != ".m":
        return                                          # .xlsx · .raw 는 이 함정이 없다

    edits = matpower_post_matrix_edits(p)
    if not edits:
        return

    shown = "\n".join(f"    {n}행: {s}" for n, s in edits[:6])
    more = f"\n    … 그리고 {len(edits) - 6}줄 더" if len(edits) > 6 else ""
    raise ValueError(
        f"'{p.name}' 은(는) 숫자 표 아래에서 값을 고치는 코드가 있어 그대로 읽으면 안 됩니다.\n"
        f"{shown}{more}\n\n"
        "MATPOWER 케이스 파일은 자료 파일이 아니라 함수라서, MATPOWER 는 이 줄들을 실행합니다.\n"
        "이 앱의 변환기는 표만 읽으므로 그 줄이 돌지 않아 단위가 어긋납니다.\n"
        "  예) 부하가 kW 로 적혀 있으면 1000배, 임피던스가 ohm 으로 적혀 있으면 Zbase 배.\n\n"
        "이렇게 하세요:\n"
        "  1) MATLAB 에서 그 케이스를 실행해 값이 다 반영된 상태로 내보내거나,\n"
        "  2) 단위를 바로잡아 만든 UniGrid 엑셀(.xlsx)을 여세요.\n"
        "MATPOWER 8.0 번들에서는 배전 계통 케이스 24개가 여기에 해당합니다."
    )


def load_case_checked(load_case, path: str | Path):
    """`check_case_file` 을 거친 뒤 원래 `load_case` 로 읽는다.

    `load_case` 를 인자로 받는 이유: 이 파일이 공개 패키지 경로를 몰라도 되게 하려고.
    부르는 쪽(prototype.py)이 이미 그것을 들고 있다.
    """
    check_case_file(path)
    return load_case(path)
