# ORBIT tester checklist

Updated 6 November 2026. Keep this list for later; no testing is needed immediately.

The portal's **Connection preparation** page saves a checklist per project and intended connection, with Passed / Failed / Blocked / Not applicable / Untested and a non-secret evidence note. Owners edit; other project roles view. Export checklist downloads a JSON copy through your browser. Records are stored in your local `.local/orbit.db`; back up the database and its matching vault key securely before replacing a local installation. Never commit or share that folder.

Completed entries below are user-reported, not independently reproduced. They do not imply all environments or projects work. New portal plans intentionally start untested; record these results only against the connection you actually tested.

## User-reported baseline

- [x] RedEye connection confirmed by the owner.
- [x] RedEye Read artefacts succeeded.
- [x] RedEye Read groups succeeded.
- [x] RedEye Read metadata keys succeeded.

Evidence: owner reported “connection confirmed” and “they all worked” in this conversation. Exact response samples, installed environment, result counts and permission scope were not captured by the agent. Do not paste keys into test evidence.

## Next live tests — RedEye

- [ ] Record the applicable project, read connection ID, environment, date and account scope.
- [ ] Compare returned artefacts/groups/metadata-key IDs with the RedEye UI.
- [ ] Verify group filtering excludes unrelated groups; group listing success is not proof of isolation.
- [ ] Exercise empty results, multiple pages, rate limits, revoked/invalid key and access-denied cases.
- [ ] Check metadata value types, missing/duplicate keys and revision/approval semantics with a small sanitised sample.
- [ ] Confirm current bounded 25-row display and no import/file transfer are understood.

## Autodesk / Forma document management

- [ ] Register the APS application and exact local callback; obtain administrator-approved ACC provisioning.
- [ ] Test three-legged sign-in, consent denial, accessible hub/project/folder dropdowns and denied-project behaviour.
- [ ] Test two-legged mode only if that app is entitled to the intended resources.
- [ ] Test renewal, expiry, revocation and disconnect; confirm local disconnect versus vendor revocation.
- [ ] Compare names/IDs and first-page coverage with the ACC UI; test paging with more than 25 projects.
- [ ] Test no accessible hubs/projects, revoked membership and roles that cannot administer connections.

## Meridian — administrator discovery before live adapter

- [ ] Identify Enterprise + PowerWeb, Explorer, Mobile API Service or separate Portal/Cloud product.
- [ ] Record exact installed release and patch, target 2024 or later. Verify each supported release independently.
- [ ] Obtain the version-matched API documentation, API entitlement and non-production test account.
- [ ] Confirm the actual interface and installed HTTPS API URL; do not infer it from the PowerWeb browser address.
- [ ] Confirm vault, repository, view, internal filter names and repository synchronisation freshness.
- [ ] Confirm API authentication, identity delegation and least-privilege roles; browser SSO alone is insufficient evidence.
- [ ] Confirm original-file versus rendition availability, stable document/version IDs and business revision mapping.
- [ ] Resolve documented paging-index ambiguity and API Service path discrepancy with installed documentation/admin.
- [ ] Approve network execution location, DNS, private CA trust, proxy/firewall and secret-management requirements.
- [ ] Where Mobile API Service applies, administrator validates its documented health endpoint and installed API version.
- [ ] Once a real adapter exists, test authorised/denied views, empty/paged results, expiry, timeout and unavailable server.

Current Meridian support: saved preparation records and a hand-authored Explorer response preview only. No network adapter, login, private worker, API discovery or writes. A fixture preview never marks a manual test passed.

## bSDD public reference

- [x] Agent verified anonymous public dictionary listing and exact versioned URI resolution.
- [x] Agent verified paged classes and IfcWall class/property response parsing (233 definitions observed).
- [x] Automated checks cover project/role boundaries, safe fixed-host requests, saved selection protection and cache behaviour; browser service-fixture workflow passed.
- [ ] Owner chooses the actual project dictionary/version and reviews its status/licence.
- [ ] Owner tests dictionary URL input and class/property selection locally, then confirms mapping suggestions meet the project naming needs.
- [ ] Review desired type/unit/allowed-value enforcement before implementing document validation or vendor field creation.

## Other connectors and desktop versions

- [ ] Procore: developer app/customer installation, sandbox, OAuth contract, company/project document permissions and read API contract.
- [ ] Maintenance Connection: separate edition/deployment/release/API licence, asset IDs and document/attachment contract.
- [ ] Revit and Navisworks: define desktop bridge operations; validate add-in/runtime compatibility separately for every supported 2024+ release. Neither desktop bridge exists yet.
- [ ] Custom connectors: reviewed host/auth/capability contract and sandbox before admitting a live adapter.

## Portal and future transfer gates

- [ ] On Windows, validate setup/restart/update, data backup/restore, clipboard-free credential handling and browser checklist export.
- [ ] Verify each role, project grant removal and cross-organisation isolation locally. The synthetic identity picker is not production authentication.
- [ ] Check project/connection-specific mappings with real sanitised metadata after a controlled import exists.
- [ ] Test document identity links, revision/approval-state mapping, file hashes, original/rendition policy, duplicate handling and permissions before transfers.
- [ ] Before one-way writes: sandbox, dry run, explicit scope/approval, audit, retry/idempotency, cancellation and partial-failure recovery.
- [ ] Before bidirectional writes: ownership/conflicts, loop prevention, source changes during transfer and reconciliation.
- [ ] Decide ISO 19650 client/national/project rules; bSDD selection is now available, but neither supplies implemented document-compliance validation.
- [ ] Before cloud deployment: production identity, tenant isolation, managed secrets, storage/database, job execution, backups, retention and operational support.

Automated regression results are recorded separately in STATUS.md. They establish software behaviour under fixtures, not vendor connectivity or customer acceptance.
