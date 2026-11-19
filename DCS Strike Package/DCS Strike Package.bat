@echo off
cd /d "%~dp0"
call "%~dp0find_python.bat"
if not defined PY (
  echo Python was not found. Double-click setup.bat first.
  pause
  exit /b 1
)
%PY% -m dcsgen gui
if errorlevel 1 (
  echo.
  echo *** The program did not start. Read the message above, or run setup.bat again.
  echo.
  pause
)
