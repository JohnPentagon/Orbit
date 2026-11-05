$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Program (exit $LASTEXITCODE)." }
}

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        Invoke-Checked $launcher.Source @('-3', '-c', 'import sys; assert sys.version_info >= (3,12), "Python 3.12 or newer is required"')
        Invoke-Checked $launcher.Source @('-3', '-m', 'venv', '.venv')
    } else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $python) { throw 'Install Python 3.12 or newer from python.org, enable its launcher/PATH option, then run ORBIT again.' }
        Invoke-Checked $python.Source @('-c', 'import sys; assert sys.version_info >= (3,12), "Python 3.12 or newer is required"')
        Invoke-Checked $python.Source @('-m', 'venv', '.venv')
    }
}

Write-Host 'Installing the locked Python dependencies. The first run needs internet access.' -ForegroundColor Cyan
Invoke-Checked "$PSScriptRoot\.venv\Scripts\python.exe" @('-m', 'pip', 'install', '-r', 'requirements.lock', '--disable-pip-version-check')
Invoke-Checked "$PSScriptRoot\.venv\Scripts\python.exe" @('-m', 'pip', 'check')
if (-not (Test-Path 'frontend\dist\index.html')) {
    throw 'The prebuilt portal is missing. Re-extract the full download, or follow LOCAL_WINDOWS.md to rebuild it.'
}
(Get-FileHash 'requirements.lock' -Algorithm SHA256).Hash | Set-Content '.venv\orbit-requirements.sha256'
Write-Host 'Setup complete.' -ForegroundColor Green
