@echo off
cd /d "%~dp0"
set "LOG=%~dp0install_log.txt"
echo DCS Strike Package install log > "%LOG%"
echo.
echo ==============================================
echo   DCS Strike Package: one-click install
echo ==============================================
echo This needs an internet connection and takes a few minutes.
echo You can leave this window open and come back.
echo.

echo [1/5] Looking for Python...
call "%~dp0find_python.bat"
if defined PY goto :have_python

echo       Python 3.10 or newer was not found. Installing Python 3.12 for you...
winget --version >nul 2>&1
if errorlevel 1 goto :no_winget
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements >> "%LOG%" 2>&1
call "%~dp0find_python.bat"
if defined PY goto :have_python
echo.
echo *** Python was installed but this window cannot see it yet.
echo *** Close this window and double-click setup.bat once more.
echo.
pause
exit /b 1

:no_winget
echo.
echo *** This Windows has no automatic installer ^(winget^), so Python has to be added by hand:
echo ***   1. Go to https://www.python.org/downloads/ and install Python.
echo ***   2. On the first screen TICK "Add python.exe to PATH", then Install Now.
echo ***   3. Double-click setup.bat again.
echo.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:have_python
%PY% -c "import sys,os; open(os.path.join(os.environ['TEMP'],'dcsgen_py.txt'),'w').write(sys.executable)"
set /p PYEXE=<"%TEMP%\dcsgen_py.txt"
echo       Using %PYEXE%
echo Using %PYEXE% >> "%LOG%"

echo [2/5] Installing pydcs ^(the library that writes DCS missions^)...
%PY% -m pip uninstall -y dcs >> "%LOG%" 2>&1
rem Tested with pydcs 1.0.0. Try that exact release first, then the newest GitHub copy, then any release.
%PY% -m pip install --upgrade "pydcs==1.0.0" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo       Release 1.0.0 was not available. Trying the newest pydcs from GitHub...
  %PY% -m pip install --upgrade https://github.com/pydcs/dcs/archive/refs/heads/master.zip >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo       Trying the standard release...
    %PY% -m pip install --upgrade pydcs >> "%LOG%" 2>&1
    if errorlevel 1 goto :failed
  )
)

echo [3/5] Installing Pillow ^(draws the briefing pictures and PDF^)...
%PY% -m pip install --upgrade pillow >> "%LOG%" 2>&1
if errorlevel 1 echo       Pillow failed. The program will still run, but without PDF and kneeboard pages.

echo [4/5] Downloading coastline and runway data ^(one time^)...
if not exist "%~dp0dcsgen\data\coast.json" %PY% -m dcsgen fetch-coast >> "%LOG%" 2>&1
if not exist "%~dp0dcsgen\data\runways.json" %PY% -m dcsgen fetch-runways >> "%LOG%" 2>&1
if not exist "%~dp0dcsgen\data\coast.json" echo       Coastline data could not be downloaded. Units may land near shores. Run fetch_coast.bat later.
if not exist "%~dp0dcsgen\data\runways.json" echo       Runway data could not be downloaded. Run fetch_runways.bat later.

echo [5/5] Making the desktop shortcut...
set "PYW=%PYEXE:python.exe=pythonw.exe%"
set "DCSGEN_PYW=%PYW%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_shortcut.ps1" >> "%LOG%" 2>&1

echo --- diagnose --- > "%~dp0setup_report.txt"
%PY% -m dcsgen diagnose >> "%~dp0setup_report.txt" 2>&1
%PY% -m dcsgen scan-mods >> "%~dp0setup_report.txt" 2>&1

echo.
echo ==============================================
echo   All done. Use the "DCS Strike Package" icon on your Desktop.
echo ==============================================
echo.
choice /c YN /m "Start it now"
if errorlevel 2 exit /b 0
start "" %PY% -m dcsgen gui
exit /b 0

:failed
echo.
echo *** Setup could not finish. The details are in install_log.txt in this folder.
echo *** If you ask for help, please send that file.
echo.
pause
exit /b 1
