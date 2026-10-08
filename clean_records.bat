@echo off
title MediConnect - Clean Database Records
cd /d "%~dp0"

echo ====================================================================
echo             MEDICONNECT - CLEAN DATABASE (FRESH START)
echo ====================================================================
echo.
echo This will remove all patient, maternal, child, immunization, and
echo symptom records to give you a clean slate.
echo User accounts (asha_sunita, asha_anita, admin_meena) will be kept.
echo.
set /p confirm="Are you sure you want to proceed? (Y/N): "
if /i "%confirm%" neq "Y" (
    echo Operation cancelled.
    pause
    exit /b 0
)

python clean_records.py

echo.
pause
