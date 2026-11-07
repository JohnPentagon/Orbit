$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host 'Optional Meridian Explorer authentication for this Windows executor.' -ForegroundColor Cyan
Write-Host 'Uses the Windows process identity, with delegation disabled. ORBIT does not store a Windows password.'
Write-Host 'Configure only administrator-approved HTTPS origins and least-privilege test access. This does not install a VPN or Meridian.'
if (-not (Test-Path "$PSScriptRoot\.venv\Scripts\python.exe")) {
    throw 'Run Setup-Orbit.ps1 first to create the local virtual environment.'
}
& "$PSScriptRoot\.venv\Scripts\python.exe" -m pip install -r "$PSScriptRoot\requirements-windows-auth.txt"
if ($LASTEXITCODE -ne 0) { throw 'Optional Windows authentication package installation failed.' }
Write-Host 'Optional packages installed locally. Authentication still requires Meridian API, Windows permissions, network and CA validation.'
