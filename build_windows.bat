@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install "pyinstaller>=6,<7"
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name FMFaceAutomator --add-data "fonts;fonts" --collect-all fmsave --collect-all backports.zstd --collect-all PIL app.py
if errorlevel 1 (
  pause
  exit /b 1
)
echo Build output: dist\FMFaceAutomator\FMFaceAutomator.exe
pause
