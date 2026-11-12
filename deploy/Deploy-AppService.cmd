@echo off
setlocal EnableExtensions
rem Build on the existing Windows App Service/Kudu. No GitHub Actions runner,
rem Azure SQL, Key Vault, new plan, or other Azure resources are created.
if not defined DEPLOYMENT_SOURCE set "DEPLOYMENT_SOURCE=%~dp0.."
if not defined DEPLOYMENT_TEMP (
  echo This script is intended for App Service Deployment Centre's build service.
  exit /b 1
)
if not defined DEPLOYMENT_TARGET (
  echo Missing App Service deployment target.
  exit /b 1
)
where dotnet >nul 2>nul
if errorlevel 1 (
  echo .NET SDK not found. Configure the existing Windows app for .NET 10.
  exit /b 1
)
set "ORBIT_PUBLISH_DIR=%DEPLOYMENT_TEMP%\orbit-publish"
pushd "%DEPLOYMENT_SOURCE%"
dotnet publish "dotnet\Orbit.Api\Orbit.Api.csproj" --configuration Release --runtime win-x86 --self-contained true --output "%ORBIT_PUBLISH_DIR%"
if errorlevel 1 goto failed
if not exist "frontend\dist\index.html" (
  echo The checked-in portal build is missing. No deployment was performed.
  goto failed
)
if not exist "%ORBIT_PUBLISH_DIR%\wwwroot" mkdir "%ORBIT_PUBLISH_DIR%\wwwroot"
robocopy "frontend\dist" "%ORBIT_PUBLISH_DIR%\wwwroot" /E /NFL /NDL /NJH /NJS
if errorlevel 8 goto failed
if not defined KUDU_SYNC_CMD (
  echo App Service Kudu Sync is unavailable. No package files have been copied to the site.
  goto failed
)
rem app_offline lets IIS release the native process and its single-instance data lease.
> "%DEPLOYMENT_TARGET%\app_offline.htm" echo ORBIT is updating. Please reload shortly.
call %KUDU_SYNC_CMD% -v 30 -f "%ORBIT_PUBLISH_DIR%" -t "%DEPLOYMENT_TARGET%" -n "%NEXT_MANIFEST_PATH%" -p "%PREVIOUS_MANIFEST_PATH%" -i ".git;.deployment;app_offline.htm"
if errorlevel 1 (
  echo Deployment could not finish. The site remains offline; inspect the deployment log before starting it.
  goto failed
)
del "%DEPLOYMENT_TARGET%\app_offline.htm" >nul 2>nul
popd
exit /b 0
:failed
popd
exit /b 1
