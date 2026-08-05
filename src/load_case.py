"""load_acdc_case.py — AC/DC 하이브리드 계통 Excel을 수정 가능한 table(case)로 로딩.

MATLAB의 load_ACDC_data.m와 동일한 의미로 13개 시트를 numeric matrix로 읽는다.
사용자는 이 case의 table을 수정한 뒤 run_acdc(case)로 반복 계산할 수 있다.

    from load_acdc_case import load_acdc_case
    from run_acdc import run_acdc
    case = load_acdc_case("grids/ACDC_matacdc_case24_ieee_rts1996_3zones.xlsx")
    case.AC_PLoad_dat["Time_1"] *= 1.01     # 부하 파라미터 수정
    result = run_acdc(case)

주의: 각 시트의 numeric matrix는 MATLAB load_ACDC_data 출력과 1:1 대응해야 한다.
배포 전 반드시 MATLAB 결과와 대조 검증할 것(가이드 문서 참조).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


# runpfACDC_py.m 인자 순서와 동일 (= load_ACDC_data 출력 순서)
TABLE_ORDER = (
    "Base_dat",
    "AC_Bus_dat",
    "AC_Line_dat",
    "AC_gen_dat",
    "AC_3wtrans_dat",
    "DC_Bus_dat",
    "DC_Line_dat",
    "DC_gen_dat",
    "IC_dat",
    "DCDC_Conv_dat",
    "AC_PLoad_dat",
    "AC_QLoad_dat",
    "DC_PLoad_dat",
)

# 내부 키 → Excel 시트 이름
SHEET_MAP = {
    "Base_dat": "Sbase,frequency",
    "AC_Bus_dat": "AC Bus Data",
    "AC_Line_dat": "AC Line Data",
    "AC_gen_dat": "AC Gen Data",
    "AC_3wtrans_dat": "AC 3w Transformer Data",
    "DC_Bus_dat": "DC Bus Data",
    "DC_Line_dat": "DC Line Data",
    "DC_gen_dat": "DC Gen Data",
    "IC_dat": "ACDC IC Data",
    "DCDC_Conv_dat": "MVDC LVDC Converter Data",
    "AC_PLoad_dat": "AC P Consume Data",
    "AC_QLoad_dat": "AC Q Consume Data",
    "DC_PLoad_dat": "DC P Consume Data",
}

# 부하 시트: readmatrix 후 첫 행(시간 라벨)을 제거 (load_ACDC_data와 동일)
LOAD_SHEETS = {"AC_PLoad_dat", "AC_QLoad_dat", "DC_PLoad_dat"}

TABLE_NAMES = set(TABLE_ORDER)


@dataclass
class ACDCCase:
    case_name: str
    mode: float
    tables: dict[str, pd.DataFrame]

    def __getattr__(self, name: str) -> Any:
        tables = self.__dict__.get("tables", {})
        if name in tables:
            return tables[name]
        raise AttributeError(f"{type(self).__name__} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in TABLE_NAMES:
            self.tables[name] = value
            return
        super().__setattr__(name, value)

    def copy(self) -> "ACDCCase":
        return ACDCCase(
            case_name=self.case_name,
            mode=self.mode,
            tables={k: v.copy(deep=True) for k, v in self.tables.items()},
        )


def load_acdc_case(excel_path: str | Path) -> ACDCCase:
    path = Path(excel_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Excel 파일을 찾을 수 없습니다: {path}")

    mode = _read_mode(path)
    available = set(pd.ExcelFile(path).sheet_names)

    tables: dict[str, pd.DataFrame] = {}
    for key in TABLE_ORDER:
        sheet = SHEET_MAP[key]
        if sheet not in available:
            # 그 모드에 없는 시트(예: DC-only 파일엔 AC Gen/AC 3W 시트가 없음)는
            # 빈 표로 둔다. Mode에 맞는 솔버가 그 계열 테이블을 안 읽으므로 무해하다.
            tables[key] = pd.DataFrame()
            continue
        matrix = _read_numeric_sheet(path, sheet)
        if key in LOAD_SHEETS:
            matrix = _drop_first_row(matrix)            # 시간 라벨 행 제거
            matrix = _name_load_columns(matrix)
        tables[key] = matrix

    return ACDCCase(case_name=path.name, mode=mode, tables=tables)


def load_case(path: str | Path) -> ACDCCase:
    """입력 파일 확장자를 보고 알맞은 로더로 ACDCCase를 만든다.

        .xlsx / .xls → UniGrid Excel (load_acdc_case)
        .m           → MATPOWER m-file (unigrid_convert.matpower_to_case, AC-only)
        .raw         → PSS/E raw       (unigrid_convert.psse_to_case, AC-only)

    변환 파서는 순환 import를 피하려고 필요할 때 지연 import한다.
    """
    ext = Path(path).expanduser().suffix.lower()
    if ext in (".xlsx", ".xls"):
        return load_acdc_case(path)
    if ext == ".m":
        from unigrid_convert import matpower_to_case
        return matpower_to_case(path)
    if ext == ".raw":
        from unigrid_convert import psse_to_case
        return psse_to_case(path)
    raise ValueError(
        f"지원하지 않는 입력 형식입니다: '{ext}'. .xlsx / .xls / .m / .raw 만 지원합니다."
    )


def _read_mode(path: Path) -> float:
    raw = pd.read_excel(path, sheet_name="Mode", header=None)
    numeric = pd.to_numeric(raw.stack(), errors="coerce").dropna()
    if numeric.empty:
        # ACDC Hybrid는 보통 Mode=0. 값이 없으면 0으로 간주.
        return 0.0
    return float(numeric.iloc[0])


def _read_numeric_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    """MATLAB readmatrix와 동일하게 시트를 numeric body로 읽는다.

    - 텍스트 헤더 행/열은 NaN이 되어 전부-NaN 행/열로 제거됨(readmatrix 동작).
    - 내부의 부분 NaN은 보존.
    """
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    ncols = raw.shape[1]
    numeric = raw.apply(pd.to_numeric, errors="coerce")
    # 텍스트 헤더 행만 제거(전부-NaN 행). 열은 위치 보존을 위해 유지한다
    # (readmatrix는 헤더가 있는 열을 위치 그대로 NaN으로 유지하므로).
    numeric = numeric.dropna(axis=0, how="all")
    if numeric.shape[0] == 0 and ncols > 0:
        # 헤더만 있고 데이터가 없는 시트(예: 컨버터/DC발전기 없는 계통)는
        # MATLAB readmatrix가 1×N NaN 행으로 준다. 컴파일된 전처리기 일부가
        # `any(isnan(...))`로 '데이터 없음'을 감지하므로 그 형태를 맞춘다.
        numeric = pd.DataFrame([[float("nan")] * ncols])
    numeric = numeric.reset_index(drop=True)
    numeric.columns = range(numeric.shape[1])
    # 모든 수치 표를 float로 통일한다. 정수로 읽힌 열(부하·정수 파라미터 등)에
    # 실수를 곱하면(예: case.AC_PLoad_dat *= 1.1) pandas가 dtype 불일치 경고를
    # 내며 향후 에러가 되므로, 처음부터 float64로 둔다(엔진도 MATLAB 전달 시 float).
    return numeric.astype("float64")


def _drop_first_row(matrix: pd.DataFrame) -> pd.DataFrame:
    if matrix.empty:
        return matrix
    return matrix.iloc[1:, :].reset_index(drop=True)


def _name_load_columns(matrix: pd.DataFrame) -> pd.DataFrame:
    if matrix.empty:
        return matrix
    cols = ["Bus"] + [f"Time_{i}" for i in range(1, matrix.shape[1])]
    matrix = matrix.copy()
    matrix.columns = cols
    return matrix


if __name__ == "__main__":
    import sys

    case = load_acdc_case(sys.argv[1] if len(sys.argv) > 1 else "grids/ACDC_matacdc_case24_ieee_rts1996_3zones.xlsx")
    print("case:", case.case_name, "| mode:", case.mode)
    for key in TABLE_ORDER:
        df = case.tables[key]
        print(f"  {key:16s}: {df.shape}")
