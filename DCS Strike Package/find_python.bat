@echo off
rem Sets PY to a working Python 3.10+ command, or leaves it empty if there is none.
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=py -3"
if defined PY goto :eof
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=python"
if defined PY goto :eof
for %%V in (313 312 311 310) do (
  if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" (
    "%LocalAppData%\Programs\Python\Python%%V\python.exe" -c "import sys" >nul 2>&1 && set "PY=%LocalAppData%\Programs\Python\Python%%V\python.exe"
  )
  if defined PY goto :eof
)
goto :eof
