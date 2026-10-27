@echo off
rem Builds Quiet Player and installs (or updates) it for this user:
rem   %LOCALAPPDATA%\Programs\QuietPlayer\QuietPlayer.exe + a Start menu shortcut.
rem Safe to run again any time; that is how updates get installed.
setlocal
rem Full paths for Windows tools: another "find" (e.g. Git's) may come first on PATH.
set "SYS=%SystemRoot%\System32"
cd /d "%~dp0"
set "SRC=%~dp0"
set "DEST=%LOCALAPPDATA%\Programs\QuietPlayer"
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Quiet Player.lnk"

rem --- find the Python that has PySide6 + python-mpv -------------------------
set "PY="
where py >nul 2>nul && (
    for /f "delims=" %%i in ('py -3.14 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
)
if not defined PY (
    for /f "delims=" %%i in ('python -c "import sys;print(sys.executable)" 2^>nul') do if not defined PY set "PY=%%i"
)
if not defined PY (
    echo Could not find Python 3.14 on this PC.
    goto fail
)
rem (find_spec, not import: importing mpv needs libmpv-2.dll on PATH)
"%PY%" -c "import PySide6, importlib.util as u; assert u.find_spec('mpv')" 2>nul || (
    echo PySide6 or python-mpv is missing for %PY%
    echo Run: "%PY%" -m pip install PySide6 python-mpv
    goto fail
)
if not exist "%SRC%libmpv-2.dll" (
    echo libmpv-2.dll is missing from %SRC% ^(see TODO.md for where to get it^).
    goto fail
)
"%PY%" -m PyInstaller --version >nul 2>nul || (
    echo Installing PyInstaller...
    "%PY%" -m pip install --quiet pyinstaller || goto fail
)

rem --- build ------------------------------------------------------------------
echo Building Quiet Player...
"%PY%" -m PyInstaller --noconfirm --clean --log-level WARN ^
    --windowed --name QuietPlayer --icon "%SRC%quiet_player.ico" ^
    --contents-directory . ^
    --exclude-module PIL --exclude-module numpy --exclude-module tkinter ^
    --add-binary "%SRC%libmpv-2.dll;." ^
    --add-data "%SRC%quiet_player.ico;." ^
    --specpath "%SRC%build" --workpath "%SRC%build" --distpath "%SRC%dist" ^
    "%SRC%quiet_player.py"
if errorlevel 1 (
    echo Build failed.
    goto fail
)
if not exist "%SRC%dist\QuietPlayer\QuietPlayer.exe" (
    echo Build produced no QuietPlayer.exe.
    goto fail
)

rem --- close a running Quiet Player (it saves its position on close) ----------
call :running
if not errorlevel 1 (
    echo Closing Quiet Player...
    "%SYS%\taskkill.exe" /IM QuietPlayer.exe >nul 2>nul
    for /l %%n in (1,1,10) do (
        call :running || goto closed
        "%SYS%\ping.exe" -n 2 127.0.0.1 >nul
    )
    echo Quiet Player is still open. Close it, then run install.bat again.
    goto fail
)
:closed

rem --- copy to the install folder ---------------------------------------------
echo Installing to %DEST%
"%SYS%\robocopy.exe" "%SRC%dist\QuietPlayer" "%DEST%" /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo Copying failed.
    goto fail
)

rem --- point the existing registration at the installed .exe (in place) -------
start "" /wait "%DEST%\QuietPlayer.exe" --register
if errorlevel 1 (
    echo Registering with Windows failed.
    goto fail
)

rem --- Start menu shortcut (no desktop shortcut) ------------------------------
"%SYS%\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command ^
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);" ^
    "$s.TargetPath = \"$env:DEST\QuietPlayer.exe\"; $s.WorkingDirectory = $env:DEST;" ^
    "$s.IconLocation = \"$env:DEST\QuietPlayer.exe,0\"; $s.Description = 'Quiet Player';" ^
    "$s.Save()"
if errorlevel 1 (
    echo Creating the Start menu shortcut failed.
    goto fail
)

echo.
echo Quiet Player is installed: %DEST%\QuietPlayer.exe
pause
exit /b 0

:running
"%SYS%\tasklist.exe" /FI "IMAGENAME eq QuietPlayer.exe" /NH 2>nul | "%SYS%\find.exe" /I "QuietPlayer.exe" >nul
exit /b %errorlevel%

:fail
echo.
pause
exit /b 1
