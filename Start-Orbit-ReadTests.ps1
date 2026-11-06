$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host 'ORBIT local read tests: explicitly authorised metadata reads only. No vendor file writes.' -ForegroundColor Cyan
Write-Host 'Use only this trusted computer and approved test accounts. Never enter an API key or client secret here.'
$confirmation = Read-Host 'Type ENABLE to enable local live reads, or press Enter to cancel'
if ($confirmation -cne 'ENABLE') { Write-Host 'Cancelled. Use Run-ORBIT.cmd for the normal synthetic demo.'; exit 0 }
$vendorHost = (Read-Host 'Optional confirmed RedEye production API hostname (no https://). Leave blank for Autodesk or the documented QA host').Trim().ToLowerInvariant()
if ($vendorHost -and $vendorHost -notmatch '^[a-z0-9]+([.-][a-z0-9]+)*$') { throw 'Enter an exact hostname only, without a URL path, port or credentials.' }
$oldReads = $env:ORBIT_ENABLE_LIVE_READS
$oldHosts = $env:ORBIT_REDEYE_ALLOWED_HOSTS
try {
    $env:ORBIT_ENABLE_LIVE_READS = '1'
    if ($vendorHost) {
        $env:ORBIT_REDEYE_ALLOWED_HOSTS = (@($oldHosts -split ',') + @($vendorHost) | Where-Object { $_ } | Select-Object -Unique) -join ','
    }
    & "$PSScriptRoot\Start-Orbit.ps1"
} finally {
    $env:ORBIT_ENABLE_LIVE_READS = $oldReads
    $env:ORBIT_REDEYE_ALLOWED_HOSTS = $oldHosts
}
