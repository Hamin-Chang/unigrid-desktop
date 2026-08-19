@echo off
REM UNIGRID 윈도우 설치본 만들기 (§7 6단계 B, 2026-08-19)
REM
REM   packaging\build_win.bat
REM
REM 만드는 것: packaging\dist\UNIGRID\  (한 폴더)  → 이어서 unigrid.iss 로 setup.exe
REM
REM 있어야 하는 것
REM   1) 파이썬 3.12 와 이 저장소용 가상환경 (아래 PY 를 그 자리로)
REM   2) 그 안에 PySide6 6.11.1 / numpy / pandas / openpyxl / pyinstaller
REM   3) engine\unigrid_app_win\unigrid_app_win.ctf  (윈도우 엔진 21차)
REM   4) 계산을 해 보려면 MATLAB Runtime R2024b
setlocal
cd /d "%~dp0.."

set "PY=%USERPROFILE%\venvs\unigrid-acdc\Scripts\python.exe"
if not exist "%PY%" (
    echo [UNIGRID] 파이썬을 못 찾음: %PY%
    echo           가상환경 자리를 이 파일의 PY 에 맞춰 주세요.
    exit /b 1
)

REM 🚨 넣을 것이 다 있는지 먼저 본다 — 없는 채로 만들면 앱은 뜨는데 계산이 안 되고
REM    그 원인을 고객 컴퓨터에서 찾게 된다.
for %%F in ("src\app.py" "src\app_worker.py" "engine\unigrid_app_win\unigrid_app_win.ctf") do (
    if not exist "%%~F" (
        echo [UNIGRID] 없다: %%~F
        exit /b 1
    )
)

echo [UNIGRID] 얼리는 중... (2~5분)
"%PY%" -m PyInstaller packaging\unigrid.spec --noconfirm ^
    --distpath packaging\dist --workpath packaging\build
if errorlevel 1 exit /b 1

echo.
echo [UNIGRID] 들어갔는지 확인
set OK=1
for %%F in ("src\app_worker.py" "engine\unigrid_app_win\unigrid_app_win.ctf" "EULA.txt") do (
    if exist "packaging\dist\UNIGRID\_internal\%%~F" (
        echo    [O] %%~F
    ) else (
        echo    [X] %%~F  없음
        set OK=0
    )
)
if "%OK%"=="0" (
    echo [UNIGRID] 빠진 것이 있다 - 설치본으로 쓰면 안 된다
    exit /b 1
)

echo.
echo [UNIGRID] 다 됐다: packaging\dist\UNIGRID\UNIGRID.exe
echo    켜 보기:  packaging\dist\UNIGRID\UNIGRID.exe
echo.
echo    설치본(setup.exe)까지 만들려면 Inno Setup 을 깔고:
echo       ISCC.exe packaging\unigrid.iss
