# Foundation decisions

5 November 2026.

## Confirmed by the product owner

Cloud-first multi-client portal. Start with Forma/ACC document management and RedEye, read-only comparison before controlled one-way and eventual bidirectional writing. Roles and permissions belong in the foundation. Meridian is additional to Maintenance Connection. Target desktop versions 2024 onward, with exact compatibility to research. Customer sample data is unavailable. The owner authorised the bounded foundation build after research; live credentials, APIs and vendor writes remain gated.

## Implemented choices

Modular-monolith starting point: FastAPI/Pydantic API and React/TypeScript/Vite portal. Same-origin delivery avoids a development CORS dependency. Current stable package versions were checked against the configured registries and then pinned during the build.

SQLite and explicit SQL migrations provide a runnable local slice without assuming managed infrastructure. The published architecture's PostgreSQL/SQLAlchemy/Alembic/queue direction remains a production design task. SQLite is an explicit temporary implementation deviation, not a replacement commitment for cloud production.

Identity and all vendor connectors are synthetic, loudly labelled. Production startup refuses without the explicit development mode. Role changes are checked on each API call. Tenant IDs come from server-side session membership, never client-selected payload fields. Composite project/tenant keys prevent cross-tenant relationships. Project access is separate from tenant role.

Local credentials use Fernet encryption with a separately stored ignored development key. Production will require a managed vault implementation and OIDC identity. No secrets are returned from the API. Approval records bind requester, tenant, project and exact preview digest; separate actors and atomic state changes prevent self-approval/replay. The approved draft is not executable.

## Unresolved before live or production use

OIDC provider and cloud hosting, managed database/storage/vault, job durability, backup/restore, migrations to PostgreSQL, deploy-time isolation/security review, external user invitation/deprovisioning, approval expiry/rejection/cancellation, immutable audit export, operational support and retention.

Autodesk supported auth/provisioning, RedEye API-key transport/base URL/lifecycle and both vendors' licensed customer scopes and sandbox access. Neither undocumented API capabilities nor calendar-year cloud API versions should be invented.

Field ownership, document-identity links, approval/revision mapping, conflict resolution, idempotency and loop prevention precede bidirectional writes. bSDD dictionary/version selection and ISO 19650 project/national/client rules remain configurable proposals, not implemented validation or compliance claims.

## 6 November 2026 — commissioning records and Meridian boundary

Track delayed customer testing per project and intended vendor connection, with explicit manual evidence rather than inferring a pass from a fixture. Do not propagate one reported RedEye success across tenants. Plans are not executable integration profiles; changing relevant settings invalidates their checklist results.

PowerWeb is an Enterprise browser client. Start Meridian contract groundwork with documented Explorer read shapes, preserving stable document/version IDs and business revisions separately. Do not guess API Service login/auth or paths from Mobile installation examples; the documented path discrepancy and paging semantics need installation-specific confirmation. Keep .NET/Connection API and Portal/Cloud routes distinct. Model private execution options now without claiming a worker/tunnel exists.

## 6 November 2026 — optional public bSDD property references

Use the versioned public REST API, not direct identifier fetching or demonstration OAuth client IDs. Pin dictionary/version and selected class-property snapshots per project. Keep enablement optional, requirements explicit and private authentication out of the anonymous adapter. Reference field suggestions assist mapping design; do not silently change approved profiles or claim executable type/unit/compliance validation. Cache successful public metadata briefly after observed rate limiting, and preserve existing project settings during failures.

## 7 November 2026 — parameter provisioning and values

Separate definition import from optional value updates. Bind a reviewed bSDD/property and destination snapshot to each immutable job, preserve existing values by default, and verify applied local state by read-back in one transaction. Keep required-value quality distinct from successful definition creation. Real destinations are review-only until their definition/value/revision/concurrency contracts are established; the RedEye current-versus-approved distinction prevents assuming a read proves the intended write target. Do not represent ORBIT review JSON as a native vendor import.

## 7 November 2026 — remaining connection readers and write preparation

Implement bounded documented Procore metadata reads and scoped named selection. Use Windows SSPI only for confirmed Meridian Explorer API access on an authorised executor; keep other Meridian interfaces distinct. Where Maintenance/custom contracts are unknown, require explicit administrator URL/auth/JSON mapping rather than invent vendor endpoints. Keep desktop options as version/SDK preparation until real bridges exist.

Include per-connection native field references and scope in parameter review snapshots. Procore's published definition schema can produce review-only proposals for direct types; do not silently weaken integer, units, list or enum constraints. Company definitions, field-set applicability and record values remain separate capabilities. No write-enable flag bypass is introduced.

## 9 November 2026 — isolated RedEye value import test

Use successful RedEye/bSDD reads to prepare a concrete existing-key pilot, not claim metadata-key creation. Capture keys, artefact and visible history; require operator-confirmed disposable isolation/current-approved equivalence because the reviewed GET/POST revision semantics lack an established atomic precondition. Preserve all returned single-valued metadata and add only one validated value.

Keep real execution behind a separate exact-target process opt-in and short digest approval, apart from the general import executor. Reserve the attempt durably before POST, never replay, and allow GET-only reconciliation after uncertainty. Separate observed HTTP acknowledgement from read-back state. Source type validation does not create native RedEye definitions or prove whole-project compliance.

### 9 November 2026 — browser-based local UAT

The user requested a single locally running portal instead of terminal testing prompts and launcher switching. Run-ORBIT.cmd now starts UAT reads with no test prompts. The browser authorises one approved RedEye preview for at most 10 minutes, bound to its current session, exact digest and destination generation/host/artefact. Explicit final write confirmation and durable one-attempt handling remain. Grants are in memory only and consumed before POST. General writes, key creation and production identity are unchanged in scope.

### 10 November 2026 — selected-field metadata UAT

The user requested less restrictive selection and direct verification/update of any existing RedEye metadata field. A new owner UAT editor supports explicit overwrite, optional bSDD and multiple string-transport values. Verification uses fresh GETs; updating uses a session/digest-bound before/after preview and two final confirmations, with no separate approval/arming. The old permanent connection/artefact attempt slot is replaced in this editor by per-preview no-replay and unresolved-target exclusion; verified changes allow another fresh edit. Fixed revision counts and disposable-only evidence are removed, while current/approved targeting, modifiable state, preservation and real remote concurrency limits remain explicit. Key creation is not claimed.

### 10 November 2026 — actionable save conflicts

The customer reported only an execute 409 access-log entry, so its actual cause cannot be inferred. Add fixed safe conflict reasons/actions to the response and log; show the message beside the preview and scroll the banner into view. Split session rotation from expiry. Earlier pilot uncertainties need an explicit native-manual-review closure path, with receipt/audit/attempt history retained and no retry or success claim, so old records do not permanently block the new editor.

### 10 November 2026 — first RedEye write pass and Microsoft SQL connectivity

Owner reported the RedEye write worked and requested it count as a first pass; record that as user-reported acceptance without extending it to every type, revision or permission. Owner confirmed Microsoft SQL Server/Azure SQL as the new database family. Add optional pyodbc/ODBC 18 reads, explicit TCP profiles, encrypted SQL passwords/local Windows identity, verified TLS, generated SELECT-only metadata and bounded samples. Save project/connection-scoped SQL-to-destination mapping previews with native RedEye/SQL field inventories and explicit source/destination matching references. Real destination matching, SQL/platform writes, reverse imports and Entra/managed identity await separate implementation and validation.

### 11 November 2026 — connection-first local UI

The user requested a complete, friendly local connection experience, removal of synthetic content from the normal UI and restrained neon-orange accents. Replace duplicate catalogue/read/additional/tool navigation with Overview, Connections, Mappings, Activity and Settings. Scope setup to the selected provider and keep RedEye metadata in that same workspace. Start new local installations empty; preserve existing real connections/credentials and historic audit data instead of deleting the local database. Use explicit loopback-only local operator sessions, not a role picker or a production-authentication claim. Keep the proven Python adapters during this UI acceptance pass; the agreed ASP.NET Core 10/Entra cutover remains required before Azure publishing.
