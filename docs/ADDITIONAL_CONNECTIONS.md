> In v0.13, open Connections and choose the platform directly. In local-workspace mode, confirmed authorised profile settings approve that exact HTTPS origin without terminal entry. Legacy/test mode still requires its process allowlist.

# Additional connections and real-import preparation

Version 0.8, 7 November 2026. This adds executable bounded metadata readers and real-destination preparation. **It does not enable remote parameter writes.**

## Connection options

| Option | Implemented | Still to verify / build |
| --- | --- | --- |
| Procore | Encrypted existing OAuth bearer token; companies/projects v1.0 discovery; cached named scope selection; custom-field definition inventory v2.0; paged bounded reads. | Customer access/entitlements, API permissions, token expiry/replacement, browser OAuth/refresh, other regions/sandbox presets, field-set applicability and real write/read-back adapters. |
| Meridian Enterprise / Explorer | Administrator-confirmed HTTPS Explorer application/view/filter; first bounded GetDocuments response; current-Windows-process integrated auth using optional SSPI library. | Actual Windows/AD authentication, installed release/license/API, view/filter permissions, private route/CA, repository freshness and paging semantics. Other Meridian interfaces remain preparation-only. |
| Maintenance Connection | Administrator-configured HTTPS REST GET, confirmed auth/header and JSON collection/ID/name mapping; encrypted credential; saved non-secret scope filters. | Installed hosted/on-premises edition, API entitlement and exact vendor endpoint/auth/schema. This is not a preverified Maintenance Connection native contract. |
| Custom / on-premises REST | Same bounded configured reader, with Bearer, API key, Basic or public/no-credential options. | Administrator-confirmed contract, least privilege, resource scoping and customer test evidence. |
| Revit 2024+ | Dedicated connection preparation option and per-release/parameter binding checklist. | Installed desktop SDK/add-in, runtime, category and instance/type bindings, GUIDs and actual model writes. |
| Navisworks 2024+ | Dedicated connection preparation option and property ownership/release checklist. | Installed SDK/bridge and distinction between editable user-data and read-only authoring/source properties. |

Autodesk ACC and RedEye remain under **Read connections**. bSDD has its own project dictionary page. Desktop/cloud calendar-year versions are not interchangeable API versions; 2024+ is a compatibility target, not a tested blanket support claim.

## Configure an additional connection

Stop the previous ORBIT Python process before launching the updated folder. Copying frontend files alone does not load new API routes or migrations.

As a project owner, open **Additional connections**. Save the exact HTTPS API application URL, provider/auth mode, product release, non-secret resource scope/admin evidence and authorised-test confirmations. Saving setup makes no network request. Store a test credential separately, where applicable.

- Procore uses `https://api.procore.com` and an existing OAuth **access token only**, without a `Bearer` prefix in the credential input. ORBIT supplies that prefix. It does not accept a client secret as a token or initiate Procore OAuth/refresh in this increment.
- Meridian Explorer uses the installed application URL, for example `https://meridian.company:8443/BCEnterprise`. ORBIT appends `/api/GetDocuments.ashx`. Confirm the real application path, view ID and internal filter with the administrator. PowerWeb's browser address is not automatically the Explorer API address.
- Maintenance/custom API URLs and collection paths must come from the administrator's version-matched API contract. `/api/resources` is an editable example, not a discovered vendor route. Response mappings are JSON Pointers: empty for a raw array, `/data/items` for a wrapped collection, `/id` and `/name` for row fields. Missing pointers/unsupported shapes produce an error, not an empty-success result. The implemented pointer walker traverses object keys; array-index traversal is not implemented.
- Scope/filter query parameters are a saved JSON object of non-secret strings. Credentials are sent in headers, never query parameters. Filters require vendor verification; a label or user-entered filter does not prove tenant/project isolation.

Configuration revisions require the current generation, clear encrypted credentials and cached discovery, and invalidate previous results. Provider changes require a separate connection. Replacing/clearing a credential also increments generation. Local deletion is separate from vendor-side revocation. Basic credentials are entered as `username:password`, encrypted locally, and sent as an HTTPS Basic header only to the explicitly approved origin. Public endpoints do not accept a stored secret. API-key header/prefix must be administrator-confirmed; reserved/transport headers are rejected.

## Enable authorised reads

The normal demo launcher keeps these reads disabled. **Run-ORBIT-Read-Tests.cmd** asks for ENABLE and optional approved additional HTTPS origins. Origins include the exact host and any non-default port, but no application path:

```text
https://api.procore.com,https://meridian.company:8443
```

The application path belongs in the portal's API URL. The launcher sets `ORBIT_EXTRA_ALLOWED_ORIGINS` for its process and restores the previous environment after exit. This is separate from `ORBIT_REDEYE_ALLOWED_HOSTS`.

For a local shell, the equivalent settings are:

```bash
ORBIT_DEMO_MODE=1 ORBIT_ENABLE_LIVE_READS=1 \
ORBIT_EXTRA_ALLOWED_ORIGINS=https://api.procore.com \
.venv/bin/uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
```

Read readiness checks exact origin, live-read opt-in, saved confirmations/evidence and credential/Windows-auth prerequisites. Configuring an origin here does not change the managed cloud environment's egress policy. The current cloud policy does not establish access to api.procore.com or any customer private origin. No VPN, worker, bridge, firewall rule or public ingress is installed.

HTTPS verification is always enabled; redirects are not followed. Responses are capped at 1 MB decoded, with connection/read timeouts. At most 25 IDs/names/types (plus Meridian version/revision IDs) are displayed. No file URL is followed, records imported, field created or parameter value written. Successful reads prove only that operation's access to that bounded response. Failed reads do not expose provider error bodies or secrets, and role/grant/session or generation changes during a read discard its result.

## Procore selection and field inventory

1. Store an authorised OAuth access token and enable the origin.
2. **Read companies**. Choose a company by name; this saves its ID/name, retains the token and clears obsolete scope/discovery/field bindings.
3. **Read projects**, then choose one by name. The request uses the saved company ID as both `company_id` query parameter and `Procore-Company-Id` header.
4. **Read field definitions** to inspect company-level field IDs, labels and native types. Choose the documented permission context (Admin/Home/Timesheets) for that read.

Company/project choices are bound to this exact connection, generation and company parent, expire after 30 minutes, and accumulate up to 1,000 resources across manually requested pages 1–40 (25 per page). IDs not present in fresh matching discovery cannot be selected through the named-scope endpoint. Company listing has no company header; projects request the compact response. Procore's documented project list defaults to active projects. These controls do not establish complete discovery across inactive projects, all zones or regions.

Field definitions v2.0 require the documented `data` wrapper, and each returned definition must match the saved company. No fallback silently treats an unknown wrapper as an empty inventory. A field inventory read does not automatically bind a bSDD property, attach a field to project/tool field sets or establish value-update permission.

## On-premises Windows authentication

For Meridian Explorer, run on an authorised **Windows executor** that can reach the installed API. Its Windows account must have the required Explorer privileges. The portal's synthetic owner/approver roles do not choose or impersonate an AD account.

Run the normal setup first. If integrated authentication is required, inspect and run:

```powershell
.\Setup-Orbit-WindowsAuth.ps1
```

This installs the optional Windows-only top-level pinned dependencies from `requirements-windows-auth.txt` into the local `.venv`. It is separate from the default cross-platform setup. The adapter uses `HttpNegotiateAuth(delegate=False)` and never asks ORBIT to store a Windows password. The dependency metadata and constructor were checked; installation and actual SSPI negotiation were **not tested on Windows** by the agent. Transitive dependencies are resolved on that Windows computer.

For private CA/proxy requirements, have the administrator configure the executor's trust/proxy environment. The HTTPX path honours its standard inherited environment (including `SSL_CERT_FILE`); the requests/SSPI path uses standard requests settings (including an administrator-supplied `REQUESTS_CA_BUNDLE` where needed). A browser trusting a certificate does not prove Python trusts it. No insecure-TLS switch is offered.

The Explorer reader sends VIEWID, DOCFILTER, PAGEINDEX=0 and PAGESIZE=25, plus optional `pn` property identifiers. It deliberately does not implement next-page guessing because the reviewed documentation is ambiguous about index/page semantics. A synchronised Explorer repository may not represent the latest vault state. Mobile API Service, .NET/Connection API and Meridian Portal/Cloud are distinct interfaces; do not reuse their URLs/authentication interchangeably.

## Prepare parameter imports

Each additional connection can record desired definition/value operations, an explicit company/project or resource-scope reference, and manual bSDD-property-to-native-field bindings. Bindings must reference the selected project's bSDD properties, have distinct destination field IDs and include non-secret evidence. They remain **manual/unverified semantic bindings**. A checkbox or successful read does not enable a writer.

Additional connections appear as a separate destination kind under **Parameter imports**. Review snapshots pin connection generation, configuration digest, saved company/project IDs, scope reference and manual field bindings. The same preview remains blocked from remote execution and can be downloaded as an ORBIT review package.

For Procore, review packages can include **non-executable company custom-field creation proposals** based on its documented v2.0 request body. Direct candidates cover unqualified single String→string, Boolean→boolean and Real→decimal definitions. Integer-only, list, enumerated or unit-qualified requirements are not silently weakened into another native type. The package identifies those as requiring an explicit reviewed mapping. Every candidate still requires an existing-field check; company fields do not impose project required-value rules or attach themselves to document/asset/tool field sets. No POST is sent to Procore.

There is still no remote execution/partial-failure/reconciliation engine, automatic type/unit conversion, real document value writer or desktop SDK bridge. These remain explicit testing/implementation gates.

## Official evidence and validation boundaries

The official Procore documentation UI exposed these public OpenAPI contracts, retrieved on 7 November 2026:

- [Companies v1.0](https://developers.procore.com/api/v1/resource_groups/resource/companies?version=rest_v1.0): production base, bearer auth, GET companies, compact array, page/per_page, no company header required.
- [Projects v1.0](https://developers.procore.com/api/v1/resource_groups/resource/projects?version=rest_v1.0): required company_id, paging, active default and compact response.
- [Custom fields v2.0](https://developers.procore.com/api/v1/resource_groups/resource/custom-fields?version=rest_v2.0): company-scoped definition inventory/data wrapper and creation schema/native types.
- [Meridian Explorer Web API](https://help.accruent.com/meridianenterprise/Content/Online_Help/Enterprise_Server/Explorer/WebAPI/Web_API_reference.htm) and [GetDocuments](https://help.accruent.com/meridianenterprise/Content/Online_Help/Enterprise_Server/Explorer/WebAPI/GetDocuments.htm): previously reviewed official Enterprise 2026 documentation; release-specific compatibility remains pending.
- [Windows authentication library](https://pypi.org/project/requests-negotiate-sspi/): optional 0.5.2; source constructor confirms delegation can be disabled.

Maintenance Connection help retrieval returned a proxy 403 during research. No endpoint/authentication contract was invented to fill that gap. The configured reader requires administrator-supplied documentation.

Backend and browser tests use hand-authored provider responses, not customer credentials. The browser workflow uses real application persistence, encryption, scope caches and parameter review records with a fixture JSON transport. The SSPI test verifies guarded request options using a mocked Windows library; it does not establish Windows network authentication. Keep those distinctions when ticking the per-connection acceptance checklist.
