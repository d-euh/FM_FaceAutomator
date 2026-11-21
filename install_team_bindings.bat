@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" team_bindings.py
set "team_bindings_exit=%errorlevel%"
pause
exit /b %team_bindings_exit%
