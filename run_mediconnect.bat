@echo off
title MediConnect Launcher
cd /d "%~dp0"

echo ====================================================================
echo        MEDICONNECT - ASHA FIELD EHR COMPANION LAUNCHER
echo ====================================================================
echo.

:: Check if Python is installed
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    echo and make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Launch the application
python run_app.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application stopped with an error code: %errorlevel%
    pause
)
