$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host 'ORBIT isolated RedEye REAL value-write pilot' -ForegroundColor Yellow
Write-Host 'One existing key on one disposable, isolated test artefact. No key creation, nonempty-value overwrite, file transfer or automatic retry.'
Write-Host 'First use the read-test launcher and RedEye import test page to inspect and prepare the target. Never enter an API key here.'
$choice = Read-Host 'Type WRITE TEST to enable this one-target pilot, or press Enter to cancel'
if ($choice -cne 'WRITE TEST') { Write-Host 'Cancelled. No write capability enabled.'; exit 0 }
$connectionText = (Read-Host 'Exact saved RedEye read connection ID from the test page').Trim()
$connectionGuid = [Guid]::Empty
if (-not [Guid]::TryParse($connectionText, [ref]$connectionGuid)) { throw 'Enter the saved connection UUID shown in ORBIT.' }
$vendorHost = (Read-Host 'Exact RedEye API hostname, e.g. api.redeyedms.com (no https:// or path)').Trim().ToLowerInvariant()
if ($vendorHost -notmatch '^[a-z0-9]+([.-][a-z0-9]+)*$') { throw 'Enter an exact API hostname only.' }
$artefactText = (Read-Host 'Exact disposable artefact ID from the inspection').Trim()
$artefactId = [long]0
if (-not [long]::TryParse($artefactText, [ref]$artefactId) -or $artefactId -le 0 -or $artefactId -gt 9007199254740991) { throw 'Enter a positive artefact ID within the supported range.' }
$oldReads = $env:ORBIT_ENABLE_LIVE_READS
$oldHosts = $env:ORBIT_REDEYE_ALLOWED_HOSTS
$oldWrites = $env:ORBIT_ENABLE_REDEYE_WRITE_TESTS
$oldTarget = $env:ORBIT_REDEYE_WRITE_TEST_TARGET
try {
    $env:ORBIT_ENABLE_LIVE_READS = '1'
    $env:ORBIT_ENABLE_REDEYE_WRITE_TESTS = '1'
    $env:ORBIT_REDEYE_WRITE_TEST_TARGET = $connectionGuid.ToString('D') + '|' + $vendorHost + '|' + $artefactId.ToString()
    $env:ORBIT_REDEYE_ALLOWED_HOSTS = (@($oldHosts -split ',') + @($vendorHost) | Where-Object { $_ } | Select-Object -Unique) -join ','
    Write-Host 'Only this exact connection/host/artefact is write-enabled. The portal still requires a fresh preview, separate approval and typed execution confirmation.'
    & "$PSScriptRoot\Start-Orbit.ps1"
} finally {
    $env:ORBIT_ENABLE_LIVE_READS = $oldReads
    $env:ORBIT_REDEYE_ALLOWED_HOSTS = $oldHosts
    $env:ORBIT_ENABLE_REDEYE_WRITE_TESTS = $oldWrites
    $env:ORBIT_REDEYE_WRITE_TEST_TARGET = $oldTarget
}
