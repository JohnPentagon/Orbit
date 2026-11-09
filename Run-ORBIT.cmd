@echo off
setlocal
set "ORBIT_UAT_MODE=1"
set "ORBIT_ENABLE_LIVE_READS=1"
set "ORBIT_ENABLE_REDEYE_WRITE_TESTS="
set "ORBIT_REDEYE_WRITE_TEST_TARGET="
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Orbit.ps1"
if errorlevel 1 (
  echo.
  echo ORBIT could not start. Read the error above and see LOCAL_WINDOWS.md.
  pause
)

endlocal
