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

Version 0.3 adds owner-only [read-connection setup and bounded provider adapters](docs/READ_CONNECTIONS.md). Fixture checks work without vendor credentials. Optional live reads are disabled by default and require local opt-in, approved test access, confirmed configuration and an encrypted test credential. No live provider connection has been verified. Autodesk currently accepts a short-lived approved OAuth access token; ORBIT's OAuth consent/refresh flow is not implemented.

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

Dashboard, catalogue, comparison and handover records remain synthetic. Separate read-test profiles can make explicit, gated metadata GET requests after local opt-in; no data is imported. Vendor health, sync throughput and completeness remain unknown. RedEye API-key authentication is user-confirmed, while exact header/base URL, permissions and entitlement still need verification. Autodesk provisioning and approved sandbox access remain gates. Meridian is additional to Maintenance Connection. Desktop compatibility from 2024 onward is a target, not validated support.

There is no AI assistant, live telemetry, file transfer, bidirectional sync, scheduled execution, document download/export, bSDD lookup or ISO 19650 validation yet. Those are future increments. The catalogue and planned governance labels do not imply these features work. No third-party connector marketplace or certification is claimed.

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
```

Browser smoke requires the server above running and Chromium at `/usr/bin/chromium`, or `CHROMIUM_PATH` set to its executable. It uses only synthetic data and creates comparison/proposal/audit records in the local demo database. It checks comparison, approval, viewer restrictions, tenant switching, mobile overflow and JavaScript errors. Screenshots are written under ignored `.local/screenshots/`.

Dependencies are pinned in `requirements.lock` and `frontend/package-lock.json`. Top-level choices are in `requirements.txt` and `frontend/package.json`. Preserve TLS/package-integrity verification during setup. No paid service is required for this synthetic foundation.

See [status](docs/STATUS.md), [decisions](docs/DECISIONS.md) and [security boundaries](docs/SECURITY.md).
