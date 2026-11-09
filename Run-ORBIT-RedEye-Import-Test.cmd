@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Orbit-RedEye-ImportTest.ps1"
if errorlevel 1 (
  echo RedEye import-test launcher stopped. Review the message above. No automatic write retry is performed.
  pause
  exit /b 1
)
endlocal
