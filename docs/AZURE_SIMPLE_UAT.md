# Host ORBIT on the existing App Service — no new paid resources

12 November 2026. This is the current deployment route. It supersedes the Azure SQL/Key Vault prerequisites in the earlier migration candidate.

Use the existing **OrbitPortal**, **RG-RandD**, **North Europe**, **Windows / .NET 10**. Do not create a new plan, database, vault, Application Insights resource, deployment slot, or paid Entra subscription. Do not scale up. Existing App Service plan charges/free-tier limits still apply; this setup does not change that plan. It uses no GitHub Actions build, so Actions minutes/artifact storage are not required for this route.

The native migration is still a UAT candidate, with the connector parity limitations in [the migration status](AZURE_DOTNET_UAT.md#what-this-package-is). Hosting the UI does not complete those outstanding adapters. Hosted RedEye writes remain disabled.

## 1. Copy the hostname

Azure portal → App Services → **OrbitPortal** → **Overview** → **Default domain**. Copy the exact hostname, including any generated suffix. Do not invent it from the app name. The browser URL is `https://<that-hostname>`.

No subscription ID, Azure Cloud Shell, SQL server or Key Vault is needed for this deployment route.

## 2. Register Microsoft sign-in

Microsoft Entra ID → **App registrations** → **New registration**:

- Name: **ORBIT Portal UAT**.
- Supported accounts: **Accounts in this organizational directory only**.
- Redirect URI platform: **Web**.
- Redirect URI: `https://<exact-hostname>/signin-oidc`.
- Select **Register**. Do not select implicit grants or create a paid Entra plan.

On the registration's **Overview**, copy:

- **Directory (tenant) ID** → `Entra__TenantId`.
- **Application (client) ID** → `Entra__ClientId`.

Then **Certificates & secrets → Client secrets → New client secret**. Choose your organisation's expiry policy. Copy the new secret's **Value**, not its **Secret ID**, directly into the App Service setting `Entra__ClientSecret`. The value is shown only when created. Do not paste it in chat, GitHub or a document. Record its expiry so it can be renewed later.

The app handles sign-in itself; do not add a second authentication provider under App Service Authentication for this setup. No extra Microsoft Graph permissions are needed for this flow.

## 3. Get your administrator object ID

Microsoft Entra ID → **Users → All users → your account → Overview → Object ID**. Use that user object ID for `Orbit__AdminObjectIds`. This is **not** the app registration's Object ID and is not your email address.

After your first sign-in, add other people and project grants under ORBIT **Settings → People & project access**. They also use their Entra user object IDs.

## 4. Generate the encryption key locally

Run this in Windows PowerShell or PowerShell 7 on your computer; it creates no cloud resource:

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
[Convert]::ToBase64String($bytes)
$rng.Dispose()
```

Copy the generated value into `Orbit__EncryptionKey`. Keep a secure backup. Keep this value unchanged on later deployments; changing or losing it prevents decryption of saved credentials. Do not send the value in chat.

## 5. Add the App Service environment variables

App Services → **OrbitPortal → Settings → Environment variables → App settings** (older portal layouts call this Configuration → Application settings). Add the following, then **Apply/Save**. Double underscores in the names are intentional.

| Name | Value |
| --- | --- |
| `ASPNETCORE_ENVIRONMENT` | `Production` |
| `Entra__TenantId` | Directory/tenant ID from step 2 |
| `Entra__ClientId` | Application/client ID from step 2 |
| `Entra__ClientSecret` | Secret **Value** from step 2 |
| `Orbit__AdminObjectIds` | Your **user** Object ID from step 3 |
| `Orbit__EncryptionKey` | Generated Base64 value from step 4 |
| `Orbit__Storage` | `FileUat` |
| `Orbit__DataPath` | `D:\home\data\orbit` |
| `Orbit__KeyRingPath` | `D:\home\data\orbit\keys` |
| `Orbit__EnableRedEyeWrites` | `false` |
| `WEBSITE_DISABLE_OVERLAPPED_RECYCLING` | `1` |

Do not add a connection string for ORBIT. If an earlier ORBIT SQL connection string was configured, remove only that ORBIT-specific setting for this mode. Leave unrelated settings alone. `Orbit__InitializeDatabase` is not required: FileUat creates its empty local application tables automatically.

Keep the existing Windows/.NET 10 stack. Under Configuration/General settings, use a **32-bit** worker (the no-upgrade deployment script publishes `win-x86`) and **HTTPS Only**. Under **Scale out**, use **one instance** and no autoscale; do not change the plan or enable an upgrade. Don't enable add-on monitoring or create new resources.

The file database and encrypted authentication keys live outside `wwwroot`, so ordinary code deployments do not replace them. This is single-instance, small UAT storage, not the long-term multi-client database design. The app refuses to share its data directory with a second process. For later deployments, stop/restart the site if needed to release the old worker; do not delete the lock file or data folder. Persistence on the actual App Service storage still needs a restart test after first deployment.

## 6. Connect Deployment Centre

App Services → **OrbitPortal → Deployment Center**:

- Source: **GitHub**.
- Authorise your GitHub account if prompted.
- Organisation/account: **JohnPentagon**.
- Repository: **Orbit**.
- Branch: **orbit/local-test-foundation**.
- Build provider: **App Service Build Service** (also called **Kudu**), if offered.
- Save, then open **Logs** and wait for deployment success.

The root `.deployment` file selects `deploy/Deploy-AppService.cmd`. It publishes the native 32-bit Windows .NET executable on the existing App Service and copies the already-built branded frontend. It creates no Azure resources and does not run a GitHub Actions job.

If Deployment Centre offers only **GitHub Actions**, do not confirm a new workflow yet: copy the provider/options text and we can choose the available route without assuming free Actions quota. Likewise, do not press any **Upgrade** button. If .NET SDK 10 is missing from the Kudu build image, provide the fixed build error; the existing self-contained package can be used instead of changing the plan. This Windows/Kudu script has not been executed on your App Service yet.

## 7. Open and check

- Browse `https://<hostname>/api/health`: expect native **ASP.NET Core 10** and mode `hosted-workspace`.
- Browse `https://<hostname>/api/readiness`: expect `ready`.
- Open `https://<hostname>` and select **Sign in with Microsoft**.
- Your configured administrator account should open the empty UAT workspace. There is no passwordless owner picker.
- Add a connection and test a read; local Python credentials are not copied automatically.
- Restart OrbitPortal in Azure, then confirm the project and saved connection remain and can still decrypt their credential.

If sign-in fails, confirm the exact hostname, Web redirect URI, tenant/client IDs, client-secret **Value**, and your **user** object ID. Share only the fixed error text or deployment log error; never share a secret, authentication code, token, or complete environment-variable export.
