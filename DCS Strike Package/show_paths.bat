@echo off
cd /d "%~dp0"
call "%~dp0find_python.bat"
%PY% -m dcsgen paths
echo.
pause
