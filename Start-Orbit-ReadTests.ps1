$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host 'ORBIT local read tests: explicitly authorised metadata reads only. No vendor file writes.' -ForegroundColor Cyan
Write-Host 'Use only this trusted computer and approved test accounts. Never enter an API key or client secret here.'
$confirmation = Read-Host 'Type ENABLE to enable local live reads, or press Enter to cancel'
if ($confirmation -cne 'ENABLE') { Write-Host 'Cancelled. Use Run-ORBIT.cmd for the normal synthetic demo.'; exit 0 }
$vendorHost = (Read-Host 'Optional confirmed RedEye production API hostname (no https://). Leave blank for Autodesk, the reference-client default or the documented QA host').Trim().ToLowerInvariant()
if ($vendorHost -and $vendorHost -notmatch '^[a-z0-9]+([.-][a-z0-9]+)*$') { throw 'Enter an exact hostname only, without a URL path, port or credentials.' }
$extraInput = (Read-Host 'Optional additional approved HTTPS origins, comma separated (e.g. https://api.procore.com,https://meridian.company:8443). No paths or credentials').Trim()
$extraOrigins = @()
if ($extraInput) {
    foreach ($entry in ($extraInput -split ',')) {
        $text = $entry.Trim()
        $parsed = $null
        if (-not [Uri]::TryCreate($text, [UriKind]::Absolute, [ref]$parsed) -or $parsed.Scheme -ne 'https' -or $parsed.UserInfo -or $parsed.Query -or $parsed.Fragment -or $parsed.AbsolutePath -ne '/') {
            throw 'Each additional origin must be HTTPS with hostname and optional port only. Put application paths in the portal.'
        }
        $extraOrigins += $parsed.GetLeftPart([UriPartial]::Authority).ToLowerInvariant()
    }
}
$oldLocal = $env:ORBIT_LOCAL_WORKSPACE
$oldUat = $env:ORBIT_UAT_MODE
$oldWrites = $env:ORBIT_ENABLE_REDEYE_WRITE_TESTS
$oldWriteTarget = $env:ORBIT_REDEYE_WRITE_TEST_TARGET
$oldExtra = $env:ORBIT_EXTRA_ALLOWED_ORIGINS
$oldReads = $env:ORBIT_ENABLE_LIVE_READS
$oldHosts = $env:ORBIT_REDEYE_ALLOWED_HOSTS
try {
    $env:ORBIT_LOCAL_WORKSPACE = $null
    $env:ORBIT_UAT_MODE = $null
    $env:ORBIT_ENABLE_REDEYE_WRITE_TESTS = $null
    $env:ORBIT_REDEYE_WRITE_TEST_TARGET = $null
    $env:ORBIT_ENABLE_LIVE_READS = '1'
    if ($vendorHost) {
        $env:ORBIT_REDEYE_ALLOWED_HOSTS = (@($oldHosts -split ',') + @($vendorHost) | Where-Object { $_ } | Select-Object -Unique) -join ','
    }
    if ($extraOrigins.Count -gt 0) {
        $env:ORBIT_EXTRA_ALLOWED_ORIGINS = (@($oldExtra -split ',') + $extraOrigins | Where-Object { $_ } | Select-Object -Unique) -join ','
    }
    & "$PSScriptRoot\Start-Orbit.ps1"
} finally {
    $env:ORBIT_LOCAL_WORKSPACE = $oldLocal
    $env:ORBIT_UAT_MODE = $oldUat
    $env:ORBIT_ENABLE_LIVE_READS = $oldReads
    $env:ORBIT_REDEYE_ALLOWED_HOSTS = $oldHosts
    $env:ORBIT_EXTRA_ALLOWED_ORIGINS = $oldExtra
    $env:ORBIT_ENABLE_REDEYE_WRITE_TESTS = $oldWrites
    $env:ORBIT_REDEYE_WRITE_TEST_TARGET = $oldWriteTarget
}
