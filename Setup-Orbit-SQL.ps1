$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) { & "$PSScriptRoot\Setup-Orbit.ps1" }
Write-Host 'Installing optional Python SQL support for this local ORBIT installation.'
& "$PSScriptRoot\.venv\Scripts\python.exe" -m pip install -r "$PSScriptRoot\requirements-sql.txt"
if ($LASTEXITCODE -ne 0) { throw 'Optional SQL package installation failed.' }
Write-Host 'Microsoft ODBC Driver 18 must also be installed. Official setup: https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server'
Write-Host 'No database connection or write was attempted. Restart ORBIT and configure SQL connections in the browser.'
