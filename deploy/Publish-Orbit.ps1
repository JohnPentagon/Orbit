[CmdletBinding()]
param([string]$OutputDirectory=(Join-Path $PSScriptRoot '../artifacts/orbit-windows'))
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Push-Location $root
try{
 npm --prefix frontend ci; if($LASTEXITCODE){throw 'Frontend dependency installation failed.'}
 npm --prefix frontend run build; if($LASTEXITCODE){throw 'Frontend build failed.'}
 dotnet test dotnet/Orbit.Tests/Orbit.Tests.csproj --configuration Release; if($LASTEXITCODE){throw '.NET tests failed.'}
 dotnet publish dotnet/Orbit.Api/Orbit.Api.csproj --configuration Release --runtime win-x64 --self-contained true --output $OutputDirectory; if($LASTEXITCODE){throw '.NET publish failed.'}
 $web=Join-Path $OutputDirectory 'wwwroot';New-Item -ItemType Directory -Force $web | Out-Null
 Copy-Item -Path frontend/dist/* -Destination $web -Recurse -Force
 $zip=$OutputDirectory.TrimEnd('/','\')+'.zip';if(Test-Path $zip){Remove-Item $zip}
 Compress-Archive -Path (Join-Path $OutputDirectory '*') -DestinationPath $zip
 Write-Host "Created $zip. No deployment was performed."
}finally{Pop-Location}
