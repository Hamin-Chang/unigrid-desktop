@echo off
REM UNIGRID Windows build (Phase 7 step 6-B, 2026-08-19)
REM
REM   packaging\build_win.bat
REM
REM Makes: packaging\dist\UNIGRID\   -> then unigrid.iss makes setup.exe
REM
REM Needs
REM   1) Python 3.12 venv (set PY below to its python.exe)
REM   2) PySide6 6.11.1 / numpy / pandas / openpyxl / pyinstaller in it
REM   3) engine\unigrid_app_win\unigrid_app_win.ctf   (Windows engine, 21st build)
REM   4) MATLAB Runtime R2024b to actually run a calculation
REM
REM NOTE: this file must stay ASCII-only with CRLF line endings.
REM       cmd.exe misreads UTF-8 Korean and chokes on LF-only blocks.
setlocal
cd /d "%~dp0.."

set "PY=%USERPROFILE%\venvs\unigrid-acdc\Scripts\python.exe"
if not exist "%PY%" (
    echo [UNIGRID] Python not found: %PY%
    echo           Edit PY in this file to point at your venv.
    exit /b 1
)

REM Check the inputs first. Building without them gives an app that
REM starts but cannot calculate, and you find out on a customer's PC.
if not exist "src\app.py" echo [UNIGRID] missing: src\app.py & exit /b 1
if not exist "src\app_worker.py" echo [UNIGRID] missing: src\app_worker.py & exit /b 1
if not exist "engine\unigrid_app_win\unigrid_app_win.ctf" echo [UNIGRID] missing: engine\unigrid_app_win\unigrid_app_win.ctf & exit /b 1
if not exist "EULA.txt" echo [UNIGRID] missing: EULA.txt & exit /b 1

REM The app imports pandas/openpyxl to read cases. If they are not in the
REM venv they are not frozen in either, and the app opens but cannot read
REM any grid file. Check here instead of finding out on a demo machine.
"%PY%" -c "import numpy, pandas, openpyxl, PySide6" 2>nul
if errorlevel 1 (
    echo [UNIGRID] missing packages in %PY%
    echo           run: "%PY%" -m pip install -r requirements.txt
    exit /b 1
)

echo [UNIGRID] freezing... (2-5 min)
"%PY%" -m PyInstaller packaging\unigrid.spec --noconfirm --distpath packaging\dist --workpath packaging\build
if errorlevel 1 exit /b 1

echo.
echo [UNIGRID] checking what went in
set OK=1
if exist "packaging\dist\UNIGRID\_internal\src\app_worker.py" (echo    [O] src\app_worker.py) else (echo    [X] src\app_worker.py MISSING & set OK=0)
if exist "packaging\dist\UNIGRID\_internal\engine\unigrid_app_win\unigrid_app_win.ctf" (echo    [O] engine\unigrid_app_win\unigrid_app_win.ctf) else (echo    [X] engine\unigrid_app_win\unigrid_app_win.ctf MISSING & set OK=0)
if exist "packaging\dist\UNIGRID\_internal\EULA.txt" (echo    [O] EULA.txt) else (echo    [X] EULA.txt MISSING & set OK=0)
if "%OK%"=="0" (
    echo [UNIGRID] something is missing - do NOT ship this
    exit /b 1
)

echo.
echo [UNIGRID] done: packaging\dist\UNIGRID\UNIGRID.exe
echo    try it:  packaging\dist\UNIGRID\UNIGRID.exe
echo.
echo    for setup.exe, install Inno Setup then:
echo       ISCC.exe packaging\unigrid.iss
