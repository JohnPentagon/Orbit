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
