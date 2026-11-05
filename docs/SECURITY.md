# Development security boundary

Do not expose this demo on a public interface. All synthetic identities can be selected without passwords. An explicit `ORBIT_DEMO_MODE=1` is required; production startup is deliberately blocked. Only loopback/test hosts are allowed. Production needs a mature OIDC provider, TLS cookies, managed secrets, durable jobs, resource/retention limits, recovery and independent review before onboarding customer information.

Server-side membership resolves tenant context. Every project operation checks current project grants; credential and proposal identifiers are tenant-scoped. Membership/role changes take effect on existing sessions. Database composite keys prevent project/tenant relationship mismatches. No frontend hiding is treated as authorisation.

No connector executes network requests. No endpoint executes a vendor write, even after approval. Credential storage is limited to encrypted local development storage and never included in responses, validation errors or audit details. User directories, real documents, model data and production secrets are not imported.

Approval requests are immutable in this foundation and use a digest of the exact structured preview. The approving actor differs from the requester. Tenant/project permission, digest and pending state are checked at approval time, with an atomic update. Approval expiry, cancellation and execution preconditions must be implemented before any executable approval is introduced.

Tests cover cross-tenant/API access, database relationships, roles, project and membership revocation, session expiration/logout, cross-origin mutation, untrusted host, credential redaction/encryption and approval scoping/replay/self-approval. This is evidence for the bounded synthetic slice, not a penetration-test or production security claim.
