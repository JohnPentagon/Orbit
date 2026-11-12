# ASP.NET Core 10 migration boundary

12 November 2026 update: a native ASP.NET Core 10 UAT candidate now exists under `dotnet/Orbit.Api`, with its own integration tests and Windows packaging. It is not yet deployed and does not yet have full feature parity. See [Azure UAT deployment and parity status](AZURE_DOTNET_UAT.md). The existing local Python launcher remains unchanged for rollback and continuing customer tests.

Original migration boundary (11 November 2026): the team primarily maintains C#/.NET. The agreed hosted target is ASP.NET Core 10 on the existing Windows App Service OrbitPortal (RG-RandD, North Europe), with React retained. At that point, the backend had **not** been ported yet. The current native status is linked above. The connection-first local UI continues to use the working Python adapters while their behaviour is validated.

## Preserve the UI/API contract

The new UI calls scoped workspace/project APIs, not the local SQLite database directly. Treat existing project, user and connection IDs as opaque strings; do not silently replace established IDs while migrating. Port the following slices behind compatible JSON contracts, verifying parity before switching the local launcher:

1. Entra identity, tenant/project grants and workspace summaries. Replace local operator bootstrap/session endpoints in hosted use; do not deploy a passwordless owner-opening route or synthetic identity API.
2. Durable connection/configuration storage, generations, audit, write-preview digests, session binding and uncertain-outcome receipts. Use EF Core/Azure SQL for application persistence; source SQL connections remain separate.
3. Proven RedEye metadata read/verify/update path, including explicit overwrite, full returned-metadata preservation, fresh preflight, per-preview durable no-replay and read-only/manual reconciliation. Customer reports a first write pass; broader contract coverage remains pending.
4. Anonymous bSDD reference discovery/cache and pinned selected definitions.
5. SQL source/destination inventory and mapping previews using Microsoft.Data.SqlClient, retaining quoted identifiers, parameterised catalog selection, timeouts, bounded projections, credential protection and SELECT-only privileges.
6. APS OAuth/refresh/discovery, Procore and Meridian/other configured readers. Use actual customer acceptance cases and existing fixture contracts; an implemented adapter is not proven customer connectivity.

ASP.NET Core authentication must validate Entra sign-in and resolve organisation/project permissions server-side. Keep CSRF/session protections for browser mutations, use HTTPS cookies and redacted errors. Do not trust arbitrary client-supplied identity/tenant headers or assume that App Service's runtime setting provides application authorisation.

Azure application-data access and Key Vault access should use managed identity. Re-enter approved connector credentials through the new secured portal, or design an explicit audited migration; do not export decrypted Fernet secrets into an artifact. Preserve the old local database/vault-key pair for rollback until migration acceptance.

## Windows and on-premises access

Windows App Service hosting does not automatically supply the user's domain identity, local SQL network access or Meridian SSPI delegation. Private endpoints/on-premises routes and any Windows worker require a deliberate design and validation. Do not move working local integrated-authentication assumptions into cloud code unchanged.

## Local cutover and deployment acceptance

- Build and run the .NET solution locally; no .NET SDK/host compatibility has been validated by the current UI increment.
- Validate response compatibility with the React shell and connector forms.
- Validate tenant/project boundaries, Entra role denial, token/session renewal, Key Vault access and source SQL/network reachability.
- Replay fixture coverage and perform approved customer connector tests without automatic retries of uncertain vendor writes.
- Prove persistence/restart behaviour, backup/restore, redacted logging, HTTPS, health checks and production configuration.
- Confirm App Service is available for UAT and review a concrete deployment configuration before publishing. No Azure resources have been changed.

The local UI cleanup is complete independently of this cutover. It must not be represented as a .NET migration or production-readiness result.
