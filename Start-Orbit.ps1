$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$server = $null
$oldMode = $env:ORBIT_DEMO_MODE
try {
    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        & "$PSScriptRoot\Setup-Orbit.ps1"
    } else {
        $expected = (Get-FileHash 'requirements.lock' -Algorithm SHA256).Hash
        $stamp = Get-Content '.venv\orbit-requirements.sha256' -ErrorAction SilentlyContinue
        if ($stamp -ne $expected) { & "$PSScriptRoot\Setup-Orbit.ps1" }
    }
    if (-not (Test-Path 'frontend\dist\index.html')) { throw 'The prebuilt portal is missing. Re-extract the full ZIP.' }

    $portCheck = New-Object System.Net.Sockets.TcpClient
    try {
        $portCheck.Connect('127.0.0.1', 8000)
        throw 'Port 8000 is already in use. Close an existing ORBIT window or the application using that port, then retry.'
    } catch [System.Net.Sockets.SocketException] {
        # A refused connection means there is no listener; never stop unrelated processes.
    } finally { $portCheck.Dispose() }

    $env:ORBIT_DEMO_MODE = '1'
    if ($env:ORBIT_LOCAL_WORKSPACE -eq '1') {
        Write-Host 'Starting ORBIT local workspace. Use the browser for connections and mappings. Keep this window open; Ctrl+C stops it.' -ForegroundColor Cyan
    } elseif ($env:ORBIT_UAT_MODE -eq '1') {
        Write-Host 'Starting ORBIT local UAT. Connect and run tests in the browser; no terminal test prompts. Keep this server window open; Ctrl+C stops it.' -ForegroundColor Cyan
    } elseif ($env:ORBIT_ENABLE_REDEYE_WRITE_TESTS -eq '1') {
        Write-Host 'Starting ORBIT local test portal with the REAL one-target RedEye write pilot opted in. Keep this window open; Ctrl+C stops it.' -ForegroundColor Yellow
    } else {
        Write-Host 'Starting ORBIT local demo/read portal. RedEye test writes are disabled. Keep this window open; press Ctrl+C to stop.' -ForegroundColor Cyan
    }
    $server = Start-Process -FilePath "$PSScriptRoot\.venv\Scripts\python.exe" -ArgumentList @('-m', 'uvicorn', 'backend.main:create_app', '--factory', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $PSScriptRoot -NoNewWindow -PassThru
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($server.HasExited) { throw 'The ORBIT server stopped during startup. Read its error above.' }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
            if ($health.status -eq 'ok' -and $health.mode -in @('synthetic-development', 'local-workspace')) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'ORBIT did not become ready. Read the server output above.' }
    Write-Host 'Open http://127.0.0.1:8000 on THIS computer.' -ForegroundColor Green
    Start-Process 'http://127.0.0.1:8000'
    while (-not $server.HasExited) { Start-Sleep -Milliseconds 500 }
    if ($server.ExitCode -ne 0) { throw "ORBIT stopped with exit code $($server.ExitCode)." }
} finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -ErrorAction SilentlyContinue }
    $env:ORBIT_DEMO_MODE = $oldMode
}
