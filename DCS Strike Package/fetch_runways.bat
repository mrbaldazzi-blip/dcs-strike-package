@echo off
cd /d "%~dp0"
py -m dcsgen fetch-runways
echo.
echo Done. If it says Wrote ... runways.json you are finished; generate a mission as normal.
pause
