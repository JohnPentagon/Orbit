@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Orbit-ReadTests.ps1"
if errorlevel 1 (
  echo.
  echo ORBIT read testing could not start. Read the error above and see docs\AUTODESK_AND_REDEYE_SETUP.md.
  pause
)
