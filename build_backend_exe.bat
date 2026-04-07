@echo off
setlocal
cd /d "%~dp0"

echo [build] Cleaning old PyInstaller output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist backend.spec del /f /q backend.spec

echo [build] Building backend.exe...
python -m PyInstaller --onefile --name backend launch_app.py
if errorlevel 1 (
  echo [build] Build failed.
  exit /b 1
)

echo [build] Done.
echo [build] EXE path: %cd%\dist\backend.exe
endlocal
