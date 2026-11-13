# Hosted Autodesk / ACC document connection — v0.16.0

13 November 2026. Native ASP.NET Core implementation of APS application settings, three-legged consent with PKCE, app-only tokens, explicit renewal, disconnect, named hub/project/top-folder discovery and scoped document metadata reads. No Python process, new Azure resource, paid database or Key Vault is required. Existing FileUat data and keys are preserved.

This replaces the hosted 501 response for Autodesk OAuth. Other unfinished provider operations remain separate migration work. Autodesk writes, file transfer and AEC Data Model GraphQL are not implemented by this read-only connection.

## Update the existing Azure app

1. Download the **v0.16.0 Windows x86 deployment ZIP** from the repository `downloads` folder. Download that file, not GitHub's source-code ZIP.
2. Upload it using the same Kudu ZIP deployment method used for the current portal, then restart OrbitPortal. Leave Windows/.NET 10/32-bit/one instance as configured.
3. Keep **all existing Entra settings, Orbit encryption key, data path and key-ring path unchanged**. Do not delete `D:\home\data\orbit` or upload the local Python database.
4. Open `/api/health` and confirm **version `0.16.0`**, runtime **ASP.NET Core 10**. Refresh the browser if it still has the previous frontend.

No new environment variable is needed for the usual Azure default hostname. The callback is derived from App Service's `WEBSITE_HOSTNAME`. If a custom hostname is used, set `Orbit__PublicOrigin` to the canonical HTTPS origin (no path/query), and use that same address to open ORBIT and register the callback. Cross-host consent is refused because browser cookies would not return to the initiating site.

## Register the correct APS application

For **Sign in with Autodesk / three-legged** mode, use an APS confidential web application that supports the authorization-code flow and a Client Secret. If the APS portal distinguishes app types, choose its traditional/web application option. A server-to-server-only app belongs in **App-only / two-legged** mode; it is not the same as interactive user consent.

Enable the document-management APIs required by the account (Data Management and ACC access where listed). Retain your APS **Client ID** and **Client Secret**. These are separate from ORBIT's Microsoft Entra credentials.

Register this exact APS callback URL:

```text
https://<exact-ORBIT-hostname>/api/autodesk/callback
```

ORBIT displays the actual value in **Connections → Autodesk → Register this exact callback in APS**. Use that value instead of typing resource IDs or a guessed hostname. Do not use Microsoft's `/signin-oidc` path as the APS callback.

An ACC account administrator may need to provision this APS Client ID under **Account Admin → Custom Integrations**. The consenting Autodesk user also needs the intended project/folder permissions. A token or empty list does not prove account provisioning or whole-project access.

## Connect in ORBIT

1. Open **Connections → Autodesk**. Use the existing saved Autodesk connection, or create one with the fixed `https://developer.api.autodesk.com` API URL.
2. Under **Edit setup**, confirm authorised test access, vendor settings and a non-secret reference. Save if changes are necessary; revising setup clears existing authorisation.
3. In **Authorise your APS application**, enter the APS Client ID and Client Secret. Choose **Sign in with Autodesk — three-legged**. Select **Save APS application**. The secret is encrypted and deliberately not displayed after saving.
4. Select **Sign in with Autodesk**, sign in on Autodesk's site, and approve read-only `data:read` consent. The browser returns to ORBIT and the originating project.
5. Select **Load accessible hubs**. Choose your named account/hub, then a named project. Choose **Load more projects** if needed. Choose a returned top-level folder such as **Project Files**.
6. Select **Use selected project and folder**, then **Read document sample**. This displays the first bounded folder-contents response; it may include subfolders, and is not a recursively imported document register.
7. Use **Mappings → Create mapping → Read sample** for this saved Autodesk connection when comparing captured data against another connection.

For an administrator-provisioned server-to-server application, select **App-only — two-legged** and **Connect application** instead. It requests only `data:read`; no browser consent callback is used for that exchange. App-only access still depends on ACC provisioning.

## Renewal, disconnect and diagnostics

- **Renew authorisation** explicitly refreshes the token (or obtains another app-only token). Refresh credentials are encrypted and rotated when APS returns a replacement. No automatic refresh/background vendor polling is enabled.
- Expired access is blocked with a renewal/sign-in instruction. Renewal invalidates cached discovery and old sample generations; refresh discovery before changing selections.
- **Disconnect and remove app** clears this connection's APS app secret, tokens, pending consent and cached choices. It does not revoke access at Autodesk; do that in Autodesk separately if required.
- Consent state is random, time-limited, browser/session/actor/project-bound, PKCE-protected and consumed before a code exchange. Denied, stale or replayed callbacks send no new code exchange. Settings/permission changes during a request discard the result.
- Hub/project/folder choices expire after ten minutes and are credential-generation-bound. A selection cannot be saved by inventing IDs or reusing a folder from a different discovered scope.
- Discovery displays at most 25 resources per response; project discovery allows up to 40 pages / 1,000 cached projects. Absent items are not proof of no access. Pagination URLs from response bodies are not followed.
- On a failed callback, check the APS app type, exact callback, Client ID/Secret, consent and ACC provisioning. Restart sign-in; do not reuse the callback URL or authorization code. Never send secrets or callback query strings in chat/log excerpts.

## Evidence and customer checks

Automated native tests cover confidential settings, three-legged PKCE/callback, app-only exchange, refresh rotation/fallback, replay/expiry/denial/wrong-session rejection, fixed discovery URLs, scoped choices, permission/configuration changes mid-request, role/tenant/project denial, document read, disconnect and FileUat restart. Browser tests simulate the hosted consent return, dropdowns, saved scope, document sample, renewal and mobile layout. No real Autodesk customer credentials or live consent were used in development.

- [ ] User deploys v0.16.0 ZIP; health reports the correct version.
- [ ] Live APS sign-in/consent succeeds with the intended web application and user.
- [ ] Live named hub/project/folder lists match the user's ACC permissions.
- [ ] Selected folder's bounded contents read matches known ACC records.
- [ ] Native comparison captures Autodesk fields against RedEye samples with an explicit business key.
- [ ] Live token renewal and App Service restart preserve the encrypted connection.
- [ ] Hosted RedEye read remains successful after the update (user previously reported its first pass).
