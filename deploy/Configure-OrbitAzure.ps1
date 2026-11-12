# Run from your signed-in Azure Cloud Shell (PowerShell). No secret values are accepted.
[CmdletBinding()]
param(
 [Parameter(Mandatory)][string]$SubscriptionId,
 [Parameter(Mandatory)][string]$TenantId,
 [Parameter(Mandatory)][string]$EntraClientId,
 [Parameter(Mandatory)][string]$AdminObjectId,
 [Parameter(Mandatory)][string]$SqlServerHostname,
 [Parameter(Mandatory)][string]$DatabaseName,
 [Parameter(Mandatory)][string]$KeyVaultName,
 [string]$ResourceGroup='RG-RandD',
 [string]$AppName='OrbitPortal'
)
$ErrorActionPreference='Stop'
function Assert-Az {if($LASTEXITCODE -ne 0){throw 'Azure CLI command failed. No later configuration was applied.'}}
az account set --subscription $SubscriptionId; Assert-Az
$app=az webapp show --resource-group $ResourceGroup --name $AppName --output json | ConvertFrom-Json; Assert-Az
if($app.reserved){throw 'This package targets the existing Windows App Service.'}
if($app.location -notmatch 'North Europe|northeurope'){throw 'Review the unexpected App Service region before proceeding.'}
az webapp identity assign --resource-group $ResourceGroup --name $AppName --output none; Assert-Az
$principal=az webapp identity show --resource-group $ResourceGroup --name $AppName --query principalId --output tsv; Assert-Az
$vault=az keyvault show --name $KeyVaultName --output json | ConvertFrom-Json; Assert-Az
if(-not $vault.properties.enableRbacAuthorization){throw 'Configure equivalent secret Get access in the vault access policy, then adapt this script; this script expects Key Vault RBAC.'}
$existing=az role assignment list --assignee $principal --scope $vault.id --query "[?roleDefinitionName=='Key Vault Secrets User'].id" --output tsv; Assert-Az
if(-not $existing){az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal --role 'Key Vault Secrets User' --scope $vault.id --output none; Assert-Az}
# These two secrets must already exist in Key Vault. Their values are never read by this script.
foreach($secret in @('Orbit-EntraClientSecret','Orbit-EncryptionKey')){az keyvault secret show --vault-name $KeyVaultName --name $secret --query id --output tsv | Out-Null; Assert-Az}
$settings=@{
 ASPNETCORE_ENVIRONMENT='Production'
 Entra__TenantId=$TenantId
 Entra__ClientId=$EntraClientId
 Entra__ClientSecret="@Microsoft.KeyVault(SecretUri=https://$KeyVaultName.vault.azure.net/secrets/Orbit-EntraClientSecret/)"
 Orbit__AdminObjectIds=$AdminObjectId
 Orbit__EncryptionKey="@Microsoft.KeyVault(SecretUri=https://$KeyVaultName.vault.azure.net/secrets/Orbit-EncryptionKey/)"
 Orbit__KeyRingPath='D:\home\data\orbit\keys'
 Orbit__EnableRedEyeWrites='false'
 Orbit__InitializeDatabase='false'
 ConnectionStrings__Orbit="Server=tcp:$SqlServerHostname,1433;Database=$DatabaseName;Authentication=Active Directory Managed Identity;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30"
}
$temp=Join-Path ([IO.Path]::GetTempPath()) ('orbit-settings-'+[guid]::NewGuid()+'.json')
try{
 $settings | ConvertTo-Json | Set-Content -LiteralPath $temp -Encoding utf8
 az webapp config appsettings set --resource-group $ResourceGroup --name $AppName --settings "@$temp" --output none; Assert-Az
 az webapp update --resource-group $ResourceGroup --name $AppName --https-only true --output none; Assert-Az
 az webapp config set --resource-group $ResourceGroup --name $AppName --net-framework-version v10.0 --use-32bit-worker-process false --min-tls-version 1.2 --ftps-state Disabled --generic-configurations '{"healthCheckPath":"/api/readiness"}' --output none; Assert-Az
}finally{Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue}
Write-Host "Configured $AppName. Deployment has not been performed."
Write-Host "Entra Web redirect URI: https://$($app.defaultHostName)/signin-oidc"
Write-Host "Managed identity object ID for database user: $principal"
Write-Host 'Create the database schema and least-privilege managed-identity user before starting the app. See docs/AZURE_DOTNET_UAT.md.'
