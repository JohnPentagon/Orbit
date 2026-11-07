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
