@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-Orbit-SQL.ps1"
if errorlevel 1 echo Optional SQL support installation failed. Review the message above.
pause
