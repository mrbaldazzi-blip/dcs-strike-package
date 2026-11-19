@echo off
cd /d "%~dp0"
py -m dcsgen fetch-coast
echo.
echo Done. If it says Wrote ... coast.json you are finished; generate a mission as normal.
pause
