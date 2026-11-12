**Current no-new-paid-resources UAT route:** use the existing App Service, `FileUat` persistent storage, Entra app registration and Environment variables. No Azure SQL, Key Vault or GitHub Actions build is needed for this route. Follow [the simple hosting steps](AZURE_SIMPLE_UAT.md). Existing plan charges/free-tier limits remain unchanged.

# ORBIT — native .NET 10 Azure UAT

Prepared 12 November 2026. Target: existing **OrbitPortal**, Windows App Service, **RG-RandD**, **North Europe**. No Azure resources have been changed from this workspace. It currently has no Azure outbound identity or Azure login. ACC customer testing is still pending.

## What this package is

`dotnet/Orbit.Api` is native ASP.NET Core 10. It does not proxy to Python or require Python to run. It serves the existing React UI. `dotnet/Orbit.Tests` tests the new backend; the Python regression suite is not evidence of .NET parity.

Implemented first slices: Entra OIDC sign-in; server-enforced tenant, role and project grants; CSRF; encrypted connection credentials and encrypted cookie key ring; Azure SQL persistence; project settings and audit; RedEye inventory/metadata reads and verification; bSDD dictionary/class/selected-property APIs; connection-based sample mapping, comparisons and optional bSDD value validation. Meridian Explorer has a native bounded reader for supported explicit credentials; Windows delegation/network access is not established.

**This is a migration candidate, not full feature parity.** Native Autodesk OAuth/discovery, SQL connector browsing/mapping previews, generic REST/MC adapters, full Procore scope/field-definition flows, bSDD document import and RedEye uncertain-write reconciliation still need completion and acceptance. Unsupported API operations explicitly return 501. Existing local Python data and credentials are not migrated or deleted. Re-enter approved credentials through the secured hosted portal; do not upload `.local` or its vault key.

A RedEye write port exists for further parity testing but the deployment configuration keeps `Orbit__EnableRedEyeWrites=false`. Do not enable it until full fresh-target, preserved-metadata, no-replay, crash/uncertain-outcome and manual-reconciliation tests pass. The existing local RedEye writer remains available separately.

## Information required from the Azure owner

- Azure subscription ID and the App Service's exact default hostname (copy Overview; do not guess).
- Entra directory/tenant ID, web application client ID, and the initial administrator's **object ID**. These are non-secret. The app registration must be single-tenant.
- Named testers' Entra object IDs; assign roles and project grants under Settings after the first administrator signs in.
- Application database choice. Azure SQL is configured in the deployment script; creating it requires approval for its Azure charges. It is separate from any source database connector.
- Existing or newly approved Key Vault and the ability to configure managed-identity access.
- A deployment identity/route. The provided GitHub Actions workflow uses Azure OIDC, with no publish-profile secret.

Never paste keys, passwords, client secrets, refresh tokens, publish profiles or database credentials into chat or source control.

## Azure/Entra preparation

1. Keep the existing Windows App Service. Use 64-bit workers, HTTPS only, TLS 1.2 minimum, .NET 10. The published package is self-contained `win-x64`, including its tested runtime. No runtime-stack swap to Python is required.
2. Create a single-tenant Entra app registration for the portal with platform **Web**, redirect URI `https://<exact-default-hostname>/signin-oidc`. Do not enable implicit grant. No Microsoft Graph API permission is needed for basic OIDC sign-in. Native authorization admits only configured administrators and explicit stored grants.
3. Create its client credential in Azure and store it directly in Key Vault as **Orbit-EntraClientSecret**. Generate a random 32-byte encryption key, Base64 encode it, and store it as **Orbit-EncryptionKey**. Preserve this key; replacing it breaks decryption of stored connector credentials and cookie key files. Do not use the all-zero test key.
4. Enable the App Service system-assigned managed identity. Give it **Key Vault Secrets User** on the chosen vault. The configuration script handles this assignment when the operator has permission. Key Vault networking must permit the App Service.
5. Provision the approved Azure SQL database in North Europe. Set a Microsoft Entra administrator on its logical server. Configure an explicit route/firewall/private endpoint for the App Service. Do not assume “Allow Azure services” is required or sufficient.
6. Run `deploy/Schema.sql` once in the **empty application database** as its schema administrator. This script is intentionally not run on every app startup. Do not run it in a construction source database.
7. Create a database user for the App Service managed identity and grant only runtime data access, e.g. (adjust identity name to the actual service principal):

   ```sql
   CREATE USER [OrbitPortal] FROM EXTERNAL PROVIDER;
   ALTER ROLE db_datareader ADD MEMBER [OrbitPortal];
   ALTER ROLE db_datawriter ADD MEMBER [OrbitPortal];
   ```

   Leave `Orbit__InitializeDatabase=false` for the running app. Initial schema creation is performed by the database administrator, not the runtime identity.
8. From signed-in Azure Cloud Shell **PowerShell**, run `deploy/Configure-OrbitAzure.ps1` with the non-secret IDs, SQL hostname/database name and vault name. It applies settings only; it does not deploy the code or create a database/server/vault.

## Deploy from GitHub

1. Create a deployment app/service principal with a federated credential for repository **JohnPentagon/Orbit**, GitHub environment **azure-uat**. Federated subject: `repo:JohnPentagon/Orbit:environment:azure-uat`, audience `api://AzureADTokenExchange`, issuer `https://token.actions.githubusercontent.com`.
2. Assign the deployment principal **Website Contributor** scoped to the OrbitPortal App Service, not the entire subscription. The deployment identity is separate from the portal sign-in app and the App Service runtime managed identity.
3. Configure GitHub environment `azure-uat` variables **AZURE_CLIENT_ID**, **AZURE_TENANT_ID**, **AZURE_SUBSCRIPTION_ID**, **ORBIT_HOSTNAME** (hostname only). These are non-secret IDs.
4. Run workflow **Build and deploy ORBIT .NET UAT**, choosing the development branch. `deploy=false` builds/tests and uploads a Windows package only. `deploy=true` also publishes to the existing app after tests succeed. It checks the native `/api/health` response and database `/api/readiness`.
5. Alternative local packaging on a computer with .NET 10, Node 24 and PowerShell: `deploy/Publish-Orbit.ps1`. Upload its ZIP using an already authorised Azure deployment tool. No secrets or local data belong in the package.

## Hosted UAT acceptance

- [ ] `/api/health` identifies **ASP.NET Core 10**, mode `hosted-workspace`; `/api/readiness` is ready.
- [ ] Signed-out browser shows Microsoft sign-in; no local owner-opening form or synthetic role picker.
- [ ] Initial administrator signs in; wrong-tenant/ungranted users are denied.
- [ ] Viewer sees only granted projects; cannot edit credentials or grants. Engineer can save rules/run comparisons but not configure credentials.
- [ ] Add RedEye API key through HTTPS; test reads, inspect a known artefact, verify a selected existing metadata field.
- [ ] Browse bSDD, pin a dictionary/class/properties; save and reload.
- [ ] Capture data, create mapping, compare; confirm missing sample counterparts and validation findings against known data.
- [ ] Restart app: projects, encrypted credentials, selected definitions, grants and reports persist. Confirm decryption still works and membership removal takes effect.
- [ ] Azure SQL backup/restore and key recovery procedure reviewed. Source APIs and private networks tested independently.
- [ ] ACC consent/discovery and remaining migration slices completed before declaring parity with the local application.
- [ ] RedEye write port and reconciliation accepted before enabling hosted writes.

Health is manual evidence, not continuous vendor monitoring. Sample comparisons do not prove complete registers or binary-file equality. Do not delete or alter the working local database/key pair during this migration.
