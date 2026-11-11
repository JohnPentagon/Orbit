**Brand update (v0.13.1):** the supplied ORBIT / Pentagon Solutions Constellation identity is applied: navy, cyan, amber, paper and teal; constellation logo; company attribution; headline and tagline. [Brand application](docs/BRANDING.md) · [Interface preview](docs/images/connection-hub.png).

**Local workspace (v0.13):** one connection hub, five navigation areas and a dark/orange interface. Fresh workspaces start empty; the normal launcher no longer opens a synthetic-role dashboard. Existing real connection setup and credentials are preserved. [Start here](docs/LOCAL_WORKSPACE.md) · [Interface preview](docs/images/connection-hub.png). The backend remains Python until the agreed [.NET/Entra migration](docs/DOTNET_MIGRATION.md).

**SQL connections (v0.12):** Microsoft SQL Server/Azure SQL table and column browsing, bounded samples, and saved project/connection mapping previews are now available. Install the optional SQL support/ODBC driver once, then use the portal. [SQL setup and scope](docs/SQL_CONNECTIONS.md). RedEye's first customer-reported write pass is recorded in the testing checklist.

**Local UAT (v0.11):** double-click `Run-ORBIT.cmd`, then open **RedEye metadata**. Select any existing field, verify its current/expected value or preview and confirm an update—including replacing populated values. bSDD is optional. No role switching, per-test enabling or terminal target entry. [Metadata guide](docs/REDEYE_METADATA.md).

# ORBIT

Construction integration and intelligence foundation. Cloud-first product direction; this repository currently runs a **local synthetic development portal**, not a deployed cloud service.

For the downloadable Windows demo, follow [LOCAL_WINDOWS.md](LOCAL_WINDOWS.md) and double-click `Run-ORBIT.cmd`. That package includes the built portal, so Node.js is optional for trying it. Windows launcher execution still needs validation on a Windows computer.

## Run

Use Python 3.12+ and Node.js 24. The repository is already isolated in the cloud workspace; use this checkout, without creating a worktree unless explicitly requested.

```bash
cd /workspace/Orbit
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
cd frontend
npm ci
npm run build
cd ..
ORBIT_DEMO_MODE=1 .venv/bin/uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
```

Open the local server in a browser on the same machine. No public deployment or environment publication is performed by these commands. The API serves the compiled portal from `frontend/dist`.

Select a synthetic Northstar engineer to run the Forma/ACC Docs ↔ RedEye comparison. Open Approvals to draft a mapping, switch to Northstar approver to approve its exact preview, then inspect the audit trail. Switch to Southbank or a viewer to exercise tenant/role boundaries. Owners can manage existing synthetic memberships/project grants in Administration and store a test credential in Connections. Do not enter production credentials.

## What works

Version 0.9 adds **RedEye import test**: a separately opted-in one-value pilot using an existing native key on one isolated disposable artefact. It inspects real key/detail/history data, pins the bSDD reference and proposed body, requires separate approval and exact connection/host/artefact allowlisting, sends at most one guarded POST per target, then verifies preserved metadata/read-back. Unknown results permit GET-only rechecks, not automatic retries. This is not key creation or the general multi-platform writer. See [RedEye import-test instructions](docs/REDEYE_IMPORT_TEST.md).

Version 0.8 adds **Additional connections**: Procore company/project selection and field-definition inventory, optional Meridian Explorer Windows-authenticated reads, and administrator-configured Maintenance Connection/custom REST reads. Encrypted credentials, exact-origin opt-in, scope/generation checks, manual per-connection field bindings and non-executable Procore definition proposals prepare real imports. Revit/Navisworks/custom preparation options and parameter acceptance checks are included. Customer/Windows validation and all remote parameter writers remain pending. See [additional connection setup](docs/ADDITIONAL_CONNECTIONS.md).

Version 0.7 adds **Parameter imports**: immutable bSDD-backed definition/value previews, explicit overwrite policy, typed/allowed-value/unit checks, separate review and local test execution with transactional read-back. Imported local parameter registers include a bounded required-value/type quality check. Real connections produce blocked review packages; **no live platform parameter writer is implemented**. See [parameter imports and platform prerequisites](docs/PARAMETER_IMPORTS.md).

Version 0.6 adds optional **bSDD dictionaries** per project: live public dictionary/version selection or verified identifier URL, class/property browsing, saved property definitions and destination-field suggestions in the mapping editor. See [bSDD setup and verified connectivity](docs/BSDD_SETUP.md). No API key is required for these public reads.

Version 0.5 adds **Connection preparation**: saved, project-specific provider plans and manual tester checklists, JSON export, proposed cloud/on-premises execution routes, and a bounded offline Meridian Explorer contract preview. Owners edit; other project roles view. Meridian, Procore and Maintenance Connection remain preparation-only. See [tester checklist](docs/TESTER_CHECKLIST.md) and [Meridian/on-premises findings](docs/MERIDIAN_AND_ON_PREMISES.md).

Version 0.4.3 adds [saved-connection readiness and inline 409 diagnostics](docs/READ_CONNECTION_DIAGNOSTICS.md), safe terminal reason codes and frontend/backend version mismatch warnings. The exact local failed check is now visible on the connection card instead of hidden at the bottom of the page.

Version 0.4.2 adds explicit [RedEye resolver/model contract support](docs/REDEYE_RESOLVERS_AND_MODELS.md): artefact `items`/`results`, raw-array/`items` group and metadata-key lookups, title display and observed-shape reporting. Group/key reads and fixture checks are available in Read connections. No natural-language resolver, group filter or live-mapping import is enabled.

Version 0.4.1 incorporates the [owner-supplied RedEye client evidence](docs/REDEYE_REFERENCE_CLIENT.md): the overridable utility-default API host and bearer API-key format are now prefilled. Response-envelope and resolver behaviour remain to be checked before changing parsing.

Version 0.4 adds [Autodesk sign-in, token renewal and named resource selectors, plus documented RedEye presets](docs/AUTODESK_AND_REDEYE_SETUP.md). Three-legged PKCE consent and app-only token exchange are implemented for an approved APS application, with explicit renewal and encrypted local credentials. Select hub/project names rather than typing IDs. Optional live tests still require operator opt-in and approved access. No real vendor connection has been verified; fixture checks remain available without credentials.

New: [project/connection integration profiles and handover-preview walkthrough](docs/INTEGRATION_PROFILES.md). Multi-field mappings, immutable versions, separate profile approval and fixed synthetic handover manifests now work. These previews transfer zero files; live transfer remains disabled.

- Responsive React/TypeScript portal: overview, comparisons, connections/catalogue, approval records, audit and organisation access administration.
- FastAPI endpoints with server-side action permissions, tenant/project scoping and composite database foreign keys.
- Five test roles per organisation: owner, engineer, approver, viewer, auditor; session role/project revocation checked against current database state.
- Persistent synthetic comparisons with candidate matches, approval-basis differences, revision differences, missing metadata and unmatched records.
- Encrypted credential-reference foundation; submitted values are not returned to clients or written to audit records.
- Separate-person mapping approval tied to an exact payload digest, with atomic pending-state transition. Approval never activates a mapping or performs a vendor write.
- Numbered SQL migrations and repeatable initial seeding. Local state survives process restarts.

## Boundaries

The identity picker is deliberately **not production authentication**. It is enabled only by explicit demo mode; startup otherwise refuses to run. The HTTP server must remain bound to loopback. There is no OIDC, invitation flow, password management, MFA, hosted deployment, production vault, PostgreSQL/RLS or durable job queue yet. SQLite is a development persistence choice and has not established production cloud readiness.

Dashboard, catalogue, comparison and handover records remain synthetic. Separate read-test profiles can make explicit, gated metadata GET requests after local opt-in; no data is imported. Vendor health, sync throughput and completeness remain unknown. The owner reports successful RedEye artefact/group/metadata-key reads; this does not verify other accounts, scopes or all response contracts. The supplied RedEye client establishes its overridable URL and bearer-key defaults; effective configuration overrides, customer permissions/entitlement and live access still need verification. Autodesk provisioning and approved sandbox access remain gates. Meridian is additional to Maintenance Connection. Desktop compatibility from 2024 onward is a target, not validated support.

There is no AI assistant, live telemetry, file transfer, bidirectional sync, scheduled execution, document download/export or ISO 19650 validation yet. Those are future increments. The catalogue and planned governance labels do not imply these features work. No third-party connector marketplace or certification is claimed.

The comparison uses an explicitly synthetic complete local register. Matching document numbers and revision labels establish candidates only, never verified identity/content equality. No vendor approval state is inferred from a filename.

## Local storage and secrets

Ignored `.local/orbit.db` contains development data and encrypted secret ciphertext. `.local/vault.key` is a locally generated Fernet key with mode 0600. This local vault is not a managed cloud secret service. Back up the key with the encrypted database if preserving development state; loss of the key makes the ciphertext unrecoverable. Never commit either file. Existing secrets cannot be read through an API. No production keys should be placed here.

Demo session tokens are random, stored as SHA-256 hashes, expire after one hour, and use HttpOnly/SameSite=Strict cookies. Cookies are HTTP-only development cookies, not production TLS cookies. Host validation and origin checks constrain local operation. These controls do not make demo sign-in suitable for public hosting.

## Checks

```bash
cd /workspace/Orbit
.venv/bin/python -m pytest backend -q
.venv/bin/pip check
cd frontend
npm run build
node smoke.mjs
node integration-smoke.mjs
node read-connections-smoke.mjs
node autodesk-setup-smoke.mjs
node readiness-smoke.mjs
```

Browser smoke requires the server above running and Chromium at `/usr/bin/chromium`, or `CHROMIUM_PATH` set to its executable. It uses only synthetic data and creates comparison/proposal/audit records in the local demo database. It checks comparison, approval, viewer restrictions, tenant switching, mobile overflow and JavaScript errors. Screenshots are written under ignored `.local/screenshots/`.

Dependencies are pinned in `requirements.lock` and `frontend/package-lock.json`. Top-level choices are in `requirements.txt` and `frontend/package.json`. Preserve TLS/package-integrity verification during setup. No paid service is required for this synthetic foundation.

See [status](docs/STATUS.md), [decisions](docs/DECISIONS.md) and [security boundaries](docs/SECURITY.md).
