# Read-only connection testing

Current setup: [version 0.4 authorisation and named resource selectors](AUTODESK_AND_REDEYE_SETUP.md), with [version 0.4.1 RedEye reference-client defaults](REDEYE_REFERENCE_CLIENT.md). This page documents the underlying read-adapter controls; the manual-token path below remains an advanced option.

## What is implemented

The owner-only **Read connections** screen configures separate, project-scoped read-test profiles, stores/replaces/clears an encrypted credential, runs a synthetic fixture check, and optionally performs a bounded live GET. It is separate from synthetic Connections, Integration profiles and Handovers. Read-test resources are displayed transiently and never imported into comparison or mapping records. Audit events and last-success summaries omit response resource bodies and credentials.

Implemented resources are Autodesk Data Management hubs, projects in a configured hub, top-level folders in a configured hub/project and folder contents in a configured project/folder; RedEye supports the known artefact-list `items`/`results` variants and raw-array/`items` group and metadata-key lookups, based on the official example and owner-supplied client/models. See REDEYE_RESOLVERS_AND_MODELS.md for the evidence and limitations. Read operations use paths previously obtained from official Autodesk OpenAPI and the user-supplied RedEye API documentation. Tests use **hand-authored examples**, not vendor-recorded responses. There are no live test credentials in the code, download or tests, and no real vendor read was performed during development.

These are first-page diagnostic reads, not exhaustive discovery, full synchronisation or a permission inventory. At most 25 resource identities/labels/types are displayed and response bytes are capped. No pagination URL, file URL or redirect is followed. No business-data POST/PATCH/PUT/DELETE is sent to a provider; the version 0.4 OAuth flow sends documented token-acquisition/renewal POST requests to the fixed APS authentication endpoint. A successful operation establishes only that that specific read worked at that time; it does not verify every account, project or resource permission, or completeness of the returned register.

## Try it without vendor access

1. Start ORBIT normally and choose **Northstar Construction · owner**.
2. Open **Read connections**. Keep the Autodesk default host, choose a test-profile name and save. Checkboxes can remain unchecked for offline fixture testing.
3. Choose **Run fixture check**. The result is explicitly synthetic and does not contact a vendor or verify your credentials. Live reads remain disabled by default.
4. Credential entry is optional for a fixture check. If testing the encrypted-entry UI, use a clearly synthetic value. Clearing a stored credential does not revoke it with the vendor.

The demo identity picker gives anyone using this local application the ability to select owner. It is **not a security boundary between people sharing a machine or browser session**. Never expose this demo publicly or use it as a multi-user hosted portal. Production OIDC and a managed secret service remain outstanding.

## Prerequisites for an authorised local live read

Use only an account, resource scope and data set approved for this test, on your own trusted local machine. There is no requirement to enable live reads merely to try the new screen.

### Autodesk

- Have an authorised test application and provisioned account/project access.
- Obtain a short-lived OAuth access token through your administrator's approved application process, with least-privilege documented access for the intended reads (the reviewed read contracts declare `data:read`). Membership, provisioning and folder access remain necessary independently of the scope string.
- The API host is fixed to `https://developer.api.autodesk.com`.
- Enter approved hub/project/folder IDs for the resources you plan to inspect. The backend enforces these configured IDs for project/folder-specific requests.
- APS application registration remains an administrator prerequisite. ORBIT now implements confidential-app consent/callback, app-only token exchange and explicit token renewal; use the version 0.4 setup guide instead of manually obtaining tokens. Automatic refresh is not implemented. The advanced manual-token path remains available; do not use an untrusted third-party token generator.

### RedEye

- Ask the RedEye administrator/vendor for the actual test API host, API entitlement and bucket/resource permissions. The supplied public page lists localhost and QA examples, which are not proof of the customer's approved base URL.
- Confirm the exact API-key header and whether the value has a prefix. API-key authentication is confirmed by the product owner; ORBIT deliberately does not invent its transport format or a token-issuance flow.
- Ask about key creation, expiry/rotation and revocation, quotas, the list envelope/pagination and latest-approved-revision semantics.
- The documented QA hostname and owner-supplied reference client default api.redeyedms.com are exact built-in presets. Configure any administrator-confirmed production hostname in the local operator allowlist. No wildcard or suffix matching is used. Store only an approved test key, never put it into the profile name, evidence field, URL or a chat message.

## Explicitly enable local reads

Stop ORBIT first. In a PowerShell terminal in the extracted ORBIT folder:

```powershell
$env:ORBIT_ENABLE_LIVE_READS = '1'
# RedEye only: replace this placeholder with the vendor-confirmed hostname.
# Do not use api.redeyedms.com merely because it hosts documentation.
$env:ORBIT_REDEYE_ALLOWED_HOSTS = 'your-approved-redeye-test-host.example'
.\Run-ORBIT.cmd
```

For Autodesk-only tests, omit `ORBIT_REDEYE_ALLOWED_HOSTS`. These process-environment settings are inherited by the launcher; no Windows machine-wide settings or firewall openings are needed. Leave the bind address at `127.0.0.1`. To disable reads, stop ORBIT, remove `ORBIT_ENABLE_LIVE_READS` from that terminal and start again, or start from a fresh terminal where it is unset.

Create an unverified read-test connection with the administrator-confirmed settings, a non-secret evidence/approval reference and both confirmation boxes checked. Store the test token/key in the password field. Then explicitly choose one resource read. Saving a configuration, storing a key and running a fixture check never initiate a live read.

RedEye host validation rejects unapproved hosts, IP literals, embedded credentials, custom ports and non-HTTPS URLs. Redirects are refused so a credential is not forwarded to another host. The application preserves normal configured proxy/TLS trust settings. The environment/network must independently permit the vendor API host. A successful connection is not inferred from an allowlist entry or a stored credential.

## Failure handling and storage

401/403 produce a sanitised access-denied message; 429 produces a rate-limit message without automatic retries. Other HTTP errors, malformed envelopes, excessive payloads and refused redirects are sanitised. Raw error bodies and tokens are not returned or audited. Connection role/project grants and credential generation are rechecked after an outgoing read; responses are discarded if those permissions or credentials changed during the request.

Local credential replacement/clearing increments its generation and clears the last-success summary. Clear the local credential when finished, and revoke it with the vendor separately where appropriate. The `.local` key/database must remain private, excluded from Git and retained together if backing up. This is encrypted local development storage, not a managed production vault.

## Remaining scope

Production ORBIT authentication, live OAuth/contract verification, automatic renewal, exhaustive bounded pagination beyond the implemented project selector, RedEye connection-specific bucket discovery, field discovery/import into integration mappings, durable jobs, complete file handovers, uploads and bidirectional execution remain unimplemented. The next verification step needs your authorised test environments and confirmed configuration—not secret values in chat.

## Validation

The backend suite includes host/redirect controls, roles/tenant boundaries, missing confirmation/credential gates, configured-resource scope enforcement, malformed and oversized responses, safe errors, credential redaction/clearing and rotation during a read. The read-connection browser smoke uses fixtures only and checks setup, secret entry/clear, disabled live buttons, role visibility and mobile overflow. None establishes a successful real Autodesk or RedEye connection.
