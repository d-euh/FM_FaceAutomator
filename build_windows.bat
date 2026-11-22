@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install "pyinstaller==6.22.3"
if errorlevel 1 (
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\build_release.py %*
set "ffa_build_exit=%errorlevel%"
pause
exit /b %ffa_build_exit%
