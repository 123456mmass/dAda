@echo off
title Relay Protection System Launcher
color 0B

echo ======================================================
echo    Starting Differential Relay Protection System
echo ======================================================
echo.

:: Set UTF-8 encoding so Thai texts in logs don't crash the console
set PYTHONUTF8=1

:: Run the launch_app Python script
python launch_app.py

:: Prevent window from closing instantly if it crashes
echo.
echo ======================================================
echo Application has stopped. Press any key to close.
pause >nul
