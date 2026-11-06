# ORBIT foundation status

6 November 2026. Bounded implementation authorised; real vendor validation and cloud deployment remain pending.

## Implemented

Version 0.5: project/tenant-scoped connection preparation records for Meridian, Procore, Maintenance Connection, Forma and RedEye; owner-only edits, project-role viewing, manual evidence, revision conflict detection, invalidation of checks after connection-setting changes and browser JSON export. Meridian Explorer has an offline response parser and hand-authored preview only. Cloud/on-premises routes are planning options, not running workers or tunnels. See MERIDIAN_AND_ON_PREMISES.md and TESTER_CHECKLIST.md.

Customer validation update: owner reports that RedEye artefact, group and metadata-key reads worked locally. These are recorded as user-reported results; no corresponding live requests were independently reproduced by the agent. Autodesk, group filtering, pagination, write/transfer paths and all Meridian connectivity remain unverified.

Version 0.4.3: per-card saved confirmation/readiness reports, structured read-block reasons and next actions, inline per-connection failures, safe terminal diagnostics, explicit create-versus-edit labels and running backend version checks. 102 backend tests plus diagnostic and read-connection browser checks passed. This fixes diagnosis/error placement; no customer's specific 409 is claimed resolved without its local reason message. See READ_CONNECTION_DIAGNOSTICS.md.

Version 0.4.2: reference DTO-backed RedEye envelope variants and read-only group/metadata-key operations; observed response-shape display; strict ambiguous/malformed-contract rejection; reference artefact title handling. Resolver weaknesses are documented rather than ported as automated decisions. 95 backend tests and the expanded fixture-only read-connection browser flow validate the bounded change. See REDEYE_RESOLVERS_AND_MODELS.md.

Version 0.4.1: RedEye connection defaults now reflect the owner-supplied C# reference client (`https://api.redeyedms.com`, `Authorization: Bearer <apiKey>`), with QA separately labelled. The URL is constructor-overridable and no live key was tested. Model/resolver files are needed before resolving response-envelope differences. All 83 backend tests, TypeScript/build and the updated read-connection browser smoke passed. See REDEYE_REFERENCE_CLIENT.md.

Version 0.4: confidential APS app configuration, three-legged state/PKCE/browser/session-bound consent, app-only token exchange, encrypted refresh tokens and explicit renewal, local disconnect, named hub/project/top-level-folder discovery, project paging and cache-bound scope selection. Read setup can be revised with authorisation invalidation. RedEye QA/bearer presets reflect the documentation with its production-host and auth-conflict limitations. A separate optional Windows launcher simplifies local read opt-in. See AUTODESK_AND_REDEYE_SETUP.md.

Version 0.3: separate project-scoped read-test profiles, encrypted credential replacement/clear, offline fixture checks and bounded Autodesk/RedEye GET adapters. Live reads require explicit operator opt-in and authorised/confirmed settings; RedEye additionally requires an exact operator-approved host and confirmed API-key header. Returned resources are not imported into comparisons/handovers. The manual-token path is now an advanced alternative to the version 0.4 consent/app-only/renewal controls. See READ_CONNECTIONS.md.

New increment: exact project/connection integration profiles; multi-field mappings with transformations/defaults/value conversions; immutable configuration history and optimistic version checks; separate profile approval; selected-document synthetic handover manifests with validation, conflict/skip handling, 24-hour expiry and exact-digest approval; stale snapshot/credential-generation checks; owner creation of additional empty synthetic connections. Live file transfer remains disabled. See INTEGRATION_PROFILES.md for scope and update instructions.

React/TypeScript portal and FastAPI backend; persistent, clearly labelled synthetic Forma/RedEye document comparison; tenant/project permissions; five synthetic roles per organisation; owner management of existing synthetic memberships/project grants; connection catalogue; encrypted local development credentials; audited comparison and approval activity; mapping previews and separate-person digest-bound approval records; SQL migration tracking; responsive desktop/mobile layouts.

## Validation

Version 0.5 validation: **121 backend tests passed**, including new project/tenant/role and grant-revocation checks, durable/repeatable migration, optimistic editing, evidence invalidation, configuration rejection and Meridian contract parsing. TypeScript/frontend production build passed. The new Chromium connection-preparation flow passed save/reload, manual evidence, offline preview, connection-setting invalidation, browser JSON export and viewer access, with no JavaScript errors. Existing foundation, read-connection and readiness browser regressions also passed against version 0.5. All new vendor contract tests and previews use fixtures, not live customer systems.

Earlier validation: version 0.4.3 passed 102 backend tests and diagnostic/read-connection browser checks. Version 0.4 recorded four Chromium regressions: foundation, integration profiles/handovers, read-connection fixtures and intercepted Autodesk app/discovery UI. These do not establish live OAuth or vendor compatibility. Screenshots reside in ignored `.local/screenshots/`. No live vendor request was made by the agent during validation.

Non-failing toolchain messages: Starlette's TestClient reports an httpx deprecation notice; the browser bundle reports ignored `use client` directives from the icon library. The portal is a client-rendered application and browser validation passed. Neither warning was suppressed or described as a failed application check.

## Not implemented / gates

Production OIDC, invitations/MFA, cloud deployment, managed vault/database, PostgreSQL/RLS and job queue; complete vendor-verified Autodesk/RedEye setup, automatic renewal, exhaustive discovery and integration of real records into mappings; broader API-key lifecycle/permission verification; downloads and exports; executable mappings, vendor writes and bidirectional sync; AI tools; bSDD lookup; ISO 19650 rule profiles; Revit/Navisworks bridges; billing; public connector submissions. Do not interpret catalogue entries or planned labels as support.

## Next

Use TESTER_CHECKLIST.md and the saved portal plans to resume customer testing later. Obtain the Meridian installed product/release, enabled interface, licensed API documentation, authentication contract and network route; then implement its authorised bounded live read transport. Continue Procore and Maintenance Connection contract discovery. Verify production identity/deployment design and vendor sandbox prerequisites. Establish reviewed identity/revision/field-ownership rules before enabling writes. Add approval lifecycle and execution checks before controlled one-way writes; add reconciliation/conflict/loop controls before bidirectional sync.
