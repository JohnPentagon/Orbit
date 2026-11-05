# ORBIT foundation status

5 November 2026. Bounded implementation authorised; live integration and cloud deployment remain pending.

## Implemented

New increment: exact project/connection integration profiles; multi-field mappings with transformations/defaults/value conversions; immutable configuration history and optimistic version checks; separate profile approval; selected-document synthetic handover manifests with validation, conflict/skip handling, 24-hour expiry and exact-digest approval; stale snapshot/credential-generation checks; owner creation of additional empty synthetic connections. Live file transfer remains disabled. See INTEGRATION_PROFILES.md for scope and update instructions.

React/TypeScript portal and FastAPI backend; persistent, clearly labelled synthetic Forma/RedEye document comparison; tenant/project permissions; five synthetic roles per organisation; owner management of existing synthetic memberships/project grants; connection catalogue; encrypted local development credentials; audited comparison and approval activity; mapping previews and separate-person digest-bound approval records; SQL migration tracking; responsive desktop/mobile layouts.

## Validation

39 backend tests passed, including the original security suite plus profile version conflicts, scope boundaries, exact connection selection, mapped-number conflicts, stale source/destination/connection snapshots, expiry and upgrade preservation. The new Chromium integration smoke passed a four-field mapping/value conversion, separate profile approval, selected-document manifest and separate manifest approval, tenant separation and mobile overflow checks, with no JavaScript errors. TypeScript/frontend production build passed. Original frozen dependency checks remain unchanged. Screenshots reside in ignored `.local/screenshots/`. No live vendor test was run.

Non-failing toolchain messages: Starlette's TestClient reports an httpx deprecation notice; the browser bundle reports ignored `use client` directives from the icon library. The portal is a client-rendered application and browser validation passed. Neither warning was suppressed or described as a failed application check.

## Not implemented / gates

Production OIDC, invitations/MFA, cloud deployment, managed vault/database, PostgreSQL/RLS and job queue; live Autodesk/RedEye connections; API-key transport verification; downloads and exports; executable mappings, vendor writes and bidirectional sync; AI tools; bSDD lookup; ISO 19650 rule profiles; Revit/Navisworks bridges; billing; public connector submissions. Do not interpret catalogue entries or planned labels as support.

## Next

Verify production identity/deployment design and vendor sandbox prerequisites. Add a tested provider interface and recorded contract fixtures, then authorised read-only live discovery. Establish reviewed identity/revision/field-ownership rules before enabling writes. Add approval lifecycle and execution checks before controlled one-way writes; add reconciliation/conflict/loop controls before bidirectional sync.
