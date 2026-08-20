@echo off
REM UNIGRID import diagnosis (2026-08-20)
REM
REM   packaging\diag_win.bat
REM
REM The Windows installer opened but could not read any grid file:
REM app.py's `from load_case import load_case` failed and the app swallowed
REM the reason. load_case is the only module in src/ that imports pandas at
REM module level. This prints everything needed to find out why, in one run.
REM
REM NOTE: this file must stay ASCII-only with CRLF line endings.
REM       cmd.exe misreads UTF-8 Korean and chokes on LF-only blocks.
setlocal
cd /d "%~dp0.."

set "PY=%USERPROFILE%\venvs\unigrid-acdc\Scripts\python.exe"
if not exist "%PY%" (
    echo [DIAG] Python not found: %PY%
    exit /b 1
)

echo ==============================================================
echo [1] versions in the venv
"%PY%" -c "import sys,platform;print(' python     ',sys.version.split()[0],platform.machine())"
"%PY%" -c "import numpy;print(' numpy      ',numpy.__version__)"
"%PY%" -c "import pandas;print(' pandas     ',pandas.__version__)"
"%PY%" -c "import openpyxl;print(' openpyxl   ',openpyxl.__version__)"
"%PY%" -c "import PySide6;print(' PySide6    ',PySide6.__version__)"
"%PY%" -c "import PyInstaller;print(' PyInstaller',PyInstaller.__version__)"

echo.
echo ==============================================================
echo [2] import from source (not frozen)
"%PY%" -c "import sys;sys.path.insert(0,'src');import load_case;print(' load_case OK')"

echo.
echo ==============================================================
echo [3] what PyInstaller warned about in the last app build
set "WARN=packaging\build\unigrid\warn-unigrid.txt"
if exist "%WARN%" (
    findstr /i "load_case case_guard pandas openpyxl dateutil tzdata" "%WARN%"
) else (
    echo    no warn file yet: %WARN%
)

echo.
echo ==============================================================
echo [4] freezing the probe - same pathex and excludes as the app (30-60 s)
"%PY%" -m PyInstaller packaging\probe.spec --noconfirm --distpath packaging\probe_dist --workpath packaging\probe_build
if errorlevel 1 (
    echo    freezing FAILED
    exit /b 1
)

echo.
echo ==============================================================
echo [5] running the frozen probe  ^<-- THE ANSWER IS HERE
echo ==============================================================
packaging\probe_dist\PROBE\PROBE.exe

echo.
echo [DIAG] done. Send everything from [1] down.
