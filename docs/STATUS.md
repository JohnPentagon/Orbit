# ORBIT foundation status

6 November 2026. Bounded implementation authorised; real vendor validation and cloud deployment remain pending.

## Implemented

Version 0.4: confidential APS app configuration, three-legged state/PKCE/browser/session-bound consent, app-only token exchange, encrypted refresh tokens and explicit renewal, local disconnect, named hub/project/top-level-folder discovery, project paging and cache-bound scope selection. Read setup can be revised with authorisation invalidation. RedEye QA/bearer presets reflect the documentation with its production-host and auth-conflict limitations. A separate optional Windows launcher simplifies local read opt-in. See AUTODESK_AND_REDEYE_SETUP.md.

Version 0.3: separate project-scoped read-test profiles, encrypted credential replacement/clear, offline fixture checks and bounded Autodesk/RedEye GET adapters. Live reads require explicit operator opt-in and authorised/confirmed settings; RedEye additionally requires an exact operator-approved host and confirmed API-key header. Returned resources are not imported into comparisons/handovers. The manual-token path is now an advanced alternative to the version 0.4 consent/app-only/renewal controls. See READ_CONNECTIONS.md.

New increment: exact project/connection integration profiles; multi-field mappings with transformations/defaults/value conversions; immutable configuration history and optimistic version checks; separate profile approval; selected-document synthetic handover manifests with validation, conflict/skip handling, 24-hour expiry and exact-digest approval; stale snapshot/credential-generation checks; owner creation of additional empty synthetic connections. Live file transfer remains disabled. See INTEGRATION_PROFILES.md for scope and update instructions.

React/TypeScript portal and FastAPI backend; persistent, clearly labelled synthetic Forma/RedEye document comparison; tenant/project permissions; five synthetic roles per organisation; owner management of existing synthetic memberships/project grants; connection catalogue; encrypted local development credentials; audited comparison and approval activity; mapping previews and separate-person digest-bound approval records; SQL migration tracking; responsive desktop/mobile layouts.

## Validation

83 backend tests passed, including the earlier suites plus OAuth state/PKCE/browser/session binding, replay/expiry, consent rejection, token exchange/refresh, discovery parent/cache/generation validation, paging and setup-change invalidation. All four Chromium workflows passed: original foundation, integration profiles/handovers, read-connection fixture setup and intercepted Autodesk app/discovery UI. The latter is explicitly a UI fixture, not live vendor authorisation. No JavaScript errors were observed. TypeScript/frontend production build passed. Screenshots reside in ignored `.local/screenshots/`. No live vendor request was made during validation.

Non-failing toolchain messages: Starlette's TestClient reports an httpx deprecation notice; the browser bundle reports ignored `use client` directives from the icon library. The portal is a client-rendered application and browser validation passed. Neither warning was suppressed or described as a failed application check.

## Not implemented / gates

Production OIDC, invitations/MFA, cloud deployment, managed vault/database, PostgreSQL/RLS and job queue; vendor-verified live Autodesk/RedEye setup, automatic renewal, exhaustive discovery and integration of real records into mappings; API-key transport verification; downloads and exports; executable mappings, vendor writes and bidirectional sync; AI tools; bSDD lookup; ISO 19650 rule profiles; Revit/Navisworks bridges; billing; public connector submissions. Do not interpret catalogue entries or planned labels as support.

## Next

Verify production identity/deployment design and vendor sandbox prerequisites. Add a tested provider interface and recorded contract fixtures, then authorised read-only live discovery. Establish reviewed identity/revision/field-ownership rules before enabling writes. Add approval lifecycle and execution checks before controlled one-way writes; add reconciliation/conflict/loop controls before bidirectional sync.
