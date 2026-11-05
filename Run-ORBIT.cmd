@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Orbit.ps1"
if errorlevel 1 (
  echo.
  echo ORBIT could not start. Read the error above and see LOCAL_WINDOWS.md.
  pause
)
