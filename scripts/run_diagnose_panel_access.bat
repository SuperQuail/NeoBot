@echo off
setlocal enabledelayedexpansion
title NeoBot Dashboard Connectivity Check
cd /d "%~dp0"

rem Batch files must stay ASCII-only: cmd.exe parses them with the OEM codepage,
rem while the Python script prints Chinese through the Unicode console API.

set "CODE=1"
set "NOPAUSE="
set "SCRIPT=%~dp0diagnose_panel_access.py"
if not exist "%SCRIPT%" (
    echo [FAIL] diagnose_panel_access.py not found next to this .bat
    goto :end
)

rem ---- collect arguments (--no-pause is consumed here) ----
set "ARGS="
:parse
if "%~1"=="" goto :pick_python
if /I "%~1"=="--no-pause" (
    set "NOPAUSE=1"
    shift
    goto :parse
)
set "ARGS=!ARGS! %~1"
shift
goto :parse

rem ---- find Python: local .venv / parent .venv / py launcher / python ----
:pick_python
set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY if exist "%~dp0..\.venv\Scripts\python.exe" set "PY=%~dp0..\.venv\Scripts\python.exe"
if not defined PY (
    where py >nul 2>nul
    if !errorlevel! equ 0 set "PY=py"
)
if not defined PY (
    where python >nul 2>nul
    if !errorlevel! equ 0 set "PY=python"
)
if not defined PY (
    echo [FAIL] Python not found.
    echo        Run inside the deployment .venv, or install Python 3.10+ and add it to PATH.
    goto :end
)

echo Interpreter: %PY%
echo Script:      %SCRIPT%
if defined ARGS (echo Args:        !ARGS!) else (echo Args:        ^(none, local check^))
echo.

%PY% "%SCRIPT%" !ARGS!
set "CODE=!errorlevel!"
echo.
if "!CODE!"=="0" (
    echo Result: no blocking issue found.
) else (
    echo Result: problems found, please follow the hints above.
)

:end
echo.
if not defined NOPAUSE pause
exit /b %CODE%
