@echo off
rem Starts Quiet Player with the Python that has PySide6 + python-mpv installed.
cd /d "%~dp0"
rem libmpv-2.dll sits in this folder; let Windows find it.
set "PATH=%~dp0;%PATH%"

set "PY="
set "PYW="
if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
    set "PYW=%LOCALAPPDATA%\Programs\Python\Python314\pythonw.exe"
    goto check
)
where py >nul 2>nul && (
    for /f "delims=" %%i in ('py -3.14 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
)
if not defined PY (
    for /f "delims=" %%i in ('where python 2^>nul') do if not defined PY set "PY=%%i"
)
if not defined PY (
    echo Could not find Python 3.14 on this PC.
    pause
    exit /b 1
)
set "PYW=%PY:python.exe=pythonw.exe%"

:check
"%PY%" -c "import PySide6, mpv" 2>"%TEMP%\quietplayer_err.txt"
if errorlevel 1 (
    echo Quiet Player couldn't start. Python used: %PY%
    echo.
    type "%TEMP%\quietplayer_err.txt"
    echo.
    echo Copy this message to Claude.
    pause
    exit /b 1
)
if not exist "%PYW%" set "PYW=%PY%"
start "" "%PYW%" "%~dp0quiet_player.py" %*
