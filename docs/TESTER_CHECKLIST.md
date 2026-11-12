# ORBIT tester checklist

Updated 11 November 2026. Keep this list for local connector acceptance and the later deployment cutover.

The portal's **Connection preparation** page saves a checklist per project and intended connection, with Passed / Failed / Blocked / Not applicable / Untested and a non-secret evidence note. Owners edit; other project roles view. Export checklist downloads a JSON copy through your browser. Records are stored in your local `.local/orbit.db`; back up the database and its matching vault key securely before replacing a local installation. Never commit or share that folder.

Completed entries below are user-reported, not independently reproduced. They do not imply all environments or projects work. New portal plans intentionally start untested; record these results only against the connection you actually tested.

## User-reported baseline

- [x] Owner reported a successful RedEye metadata write on 10 November 2026: “The Write worked, let's count that as a first pass.” This is a first customer-reported write pass, not independently reproduced or proof of all field types/revisions/permissions.
- [x] RedEye connection confirmed by the owner.
- [x] RedEye Read artefacts succeeded.
- [x] RedEye Read groups succeeded.
- [x] RedEye Read metadata keys succeeded.
- [x] Owner reconfirmed successful RedEye and bSDD reads on 9 November 2026. This is user-reported access, not proof of write permission.

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

Current Meridian support: saved preparation records, an offline Explorer preview and an optional Windows-authenticated first-response Explorer read adapter. Actual Windows/customer validation, other Meridian interfaces, private workers and all remote writes remain pending. A fixture preview never marks a manual test passed.

## bSDD public reference

- [x] Agent verified anonymous public dictionary listing and exact versioned URI resolution.
- [x] Agent verified paged classes and IfcWall class/property response parsing (233 definitions observed).
- [x] Automated checks cover project/role boundaries, safe fixed-host requests, saved selection protection and cache behaviour; browser service-fixture workflow passed.
- [ ] Owner chooses the actual project dictionary/version and reviews its status/licence.
- [ ] Owner tests dictionary URL input and class/property selection locally, then confirms mapping suggestions meet the project naming needs.
- [ ] Review desired type/unit/allowed-value enforcement before implementing document validation or vendor field creation.

## Parameter imports — version 0.7

- [x] Automated and browser checks validate local definition/value imports, explicit overwrite, exact approval, read-back, persistence and quality findings against synthetic destinations.
- [ ] Owner tries the Parameter imports workflow locally with chosen bSDD properties, including definitions-only and optional values.
- [ ] Confirm the chosen organisation, project, connection ID and environment before approving an import. Local synthetic connections and real read-test connections are separate destinations.
- [ ] Verify an approved local import changes only its selected connection; a second connection/project/organisation remains unchanged.
- [ ] Test definitions-only import: expected parameters appear, and document values remain unchanged.
- [ ] Test optional values on exact selected documents; unselected documents and unrelated parameters remain unchanged.
- [ ] Verify existing values are preserved with overwrite off; enable overwrite explicitly and confirm only the approved values change.
- [ ] Confirm project naming, supported types, required values and units before enabling a real destination.
- [ ] Check missing required values, incompatible types, disallowed values and units produce clear findings or blockers; successful field creation alone must not imply complete data quality.
- [ ] Change the dictionary, destination generation or document state after preview/approval and confirm a new review is required.
- [ ] RedEye: administrator confirms how metadata keys are created; verify current versus approved revision targeting, merge/replacement and write permissions in a sandbox.
- [ ] ACC: verify custom-attribute definition creation and version-value APIs, folder inheritance, supported types and write-scoped app/user access.
- [ ] Meridian: supply installed .NET/Connection API write contract, vault privileges and execution/identity route.
- [ ] Implement and sandbox-test each real writer with preconditions, partial failures, read-back, idempotency and reconciliation before remote execution is enabled.
- [ ] For each real connector separately, verify imported definitions in the vendor UI and API in the exact approved project/folder/vault or bucket scope.
- [ ] For each real connector separately, write an approved test value and read it back from the same document/asset and revision; compare with the vendor UI.
- [ ] Verify real writes are denied for insufficient permissions or a different connection/project, and that unrelated records/parameters remain unchanged.
- [ ] Test failed/partial writes, interruption and retry without duplicate fields, repeated changes or a false success receipt.

General Parameter imports behaviour: Apply local parameter import writes only to the selected synthetic connection register. It does not write to the real platform represented by that connection. Each real connector needs its own implemented and verified writer before the vendor-side checks above can pass.

General import destinations remain blocked; the separate v0.9 RedEye page provides the restricted pilot described below. Downloaded packages are ORBIT review records, not vendor-native import files. No test is marked passed merely because a review package can be downloaded.

## Connection-first local workspace — version 0.13

- [ ] Update/restart Run-ORBIT.cmd on Windows. Open the existing workspace and verify actual connection names/credentials remain usable; do not delete the database/vault pair.
- [ ] On a fresh test installation, create your workspace/project and confirm no sample organisations/documents/connections or synthetic role picker appear.
- [ ] Verify the five navigation areas and one platform-specific setup/data workspace per connector on desktop and mobile.
- [ ] Recheck the already working RedEye connection and a permitted field update through Connections → RedEye → Documents & metadata. Preserve the earlier first-pass evidence; this UI regression is a separate pending customer check.
- [ ] Test Autodesk sign-in/resource selectors, SQL table/sample/mapping and each other intended live connector using approved access. Automated fixtures do not replace these customer tests.
- [ ] Add/rename a project, switch projects and reload. Confirm counts and stored mappings remain correctly scoped and reflect actual recorded data.
- [ ] Inspect Activity and error/recovery visibility, including expired sessions and earlier uncertain write receipts.
- [ ] Complete ASP.NET Core 10/Entra/persistence/secret migration and local parity tests before planning Azure deployment. This UI release has not deployed anything.

## Microsoft SQL Server / Azure SQL — version 0.12

- [ ] Install optional Python SQL support and Microsoft ODBC Driver 18 on the ORBIT executor. Confirm the portal reports both available.
- [ ] Configure one authorised TCP server/port/database profile; SQL login password goes in the encrypted browser form. For local integrated authentication, confirm the Windows process identity and SELECT-only grants.
- [ ] Prove TLS certificate/hostname trust and network/firewall/private-endpoint reachability without disabling verification.
- [ ] Connect and compare the visible table/view list, column names/types/nullability and PK markers with SQL Server Management Studio/Azure tooling.
- [ ] Inspect the bounded sample; verify NULLs, dates, exact decimals/large integers, binary omission and long-value truncation. Confirm it is not complete-table coverage.
- [ ] Load destination RedEye keys or destination SQL columns; configure source matching column and destination match field, transformations/defaults/required values.
- [ ] Preview mapping, review duplicate/missing source keys, save per project/connection and reload/revise it. Check stale snapshots, changed credentials and another project's access boundaries.
- [ ] Confirm mapping previews/JSON exports execute no database or platform writes and do not establish actual destination matches.
- [ ] Record the installed SQL Server/Azure SQL edition, authentication and actual connection result. SQL transfer execution, Entra/MFA/managed identity and reverse platform-to-SQL data flows remain additional work.

## Save-conflict diagnostics — version 0.11.1

- [ ] Update/restart once and record the specific banner or `ORBIT RedEye save blocked [code]` reason for the customer's 409. The access-log status alone does not establish the cause.
- [ ] Confirm the error is visible beside the save button, with an actionable next step; verify no API key or metadata values appear in the diagnostic log.
- [ ] If an earlier pilot blocks the target, inspect native RedEye, recheck without writing, then explicitly close after manual review only if appropriate. Preserve the original outcome and distinguish manual review from verified API success.
- [ ] Prepare a fresh preview and record the actual live update/read-back result. No customer result is marked passed by the agent.

## Selected-field RedEye metadata — version 0.11

- [ ] Update/restart Run-ORBIT.cmd on Windows. Confirm RedEye metadata opens and reuses the saved working connection without terminal testing prompts.
- [ ] Load a chosen artefact and verify an existing field, first without an expected value, then with a matching and differing expected value. Confirm verification sends no write.
- [ ] Verify with bSDD disabled; optionally select a saved bSDD property and check actual/expected type, unit and allowed-value findings.
- [ ] Preview an existing-field replacement with explicit overwrite selection, confirm the revision and save. Check the exact native field, all other metadata and revision in RedEye.
- [ ] Fill an unassigned key, check empty-string behaviour and test multiple values only where native RedEye supports them. Key creation/deletion are not offered.
- [ ] After a verified update, freshly inspect and make another selected-field edit to the same artefact without a role switch, arming step or server restart.
- [ ] If uncertain, inspect native RedEye and use GET-only recheck. Record POST acknowledgement separately from observed state. Test explicit manual closure only after reviewing the original native target; it must not claim verified API success or send another POST. Do not delete attempts or force retries.
- [ ] Record observed API-key write permissions, revision semantics and cleanup in the authorised test environment.

No customer write is marked passed by the agent. Backend/browser fixture validation is recorded in STATUS.md; it is distinct from these customer acceptance items. See [REDEYE_METADATA.md](REDEYE_METADATA.md).

## bSDD → RedEye isolated value pilot — version 0.10

- [ ] Verify browser enable/disable, 10-minute expiry, identity-change and server-restart invalidation on the Windows UAT portal.
- [x] Fixture tests validate session-bound exact-preview UAT permissions and legacy exact target/write opt-in, metadata preservation, source constraints, fresh snapshots, separate approval and one durable POST attempt.
- [x] Fixture tests validate timeout-after-write, failed read-back, no replay after interruption, credential hygiene and GET-only rechecks.
- [x] Isolated browser test passes inspection, preview, approval, simulated write/read-back, replay protection, reload and viewer/mobile access; no customer write.
- [ ] Update/restart once using Run-ORBIT.cmd on Windows; confirm browser connection reads work without terminal prompts and opening the portal sends no write.
- [ ] Prepare an existing empty test metadata key and a disposable isolated artefact; confirm matching current/approved revision in the native UI and modifiable state. Do not infer approval from the API label alone.
- [ ] Inspect keys/detail/history using the existing encrypted connection. Record the observed response shape and any blockers without posting keys or customer values in chat.
- [ ] Select one valid bSDD property/value; verify exact native key meaning, units and source constraints; inspect the complete preservation payload and record non-secret evidence.
- [ ] Approve the exact preview, enable that approved test in the browser, type its confirmation and perform the single test write without restarting or entering identifiers in a terminal.
- [ ] Verify target value, every prior metadata value, revision/approval, title/number and other content in the API and native RedEye UI. Record HTTP acknowledgement separately from read-back state.
- [ ] If uncertain, stop writes and inspect/recheck with GET only. Confirm duplicate execution/new preview/restart does not send another POST to that target.
- [ ] Clean up the disposable target manually after preserving test evidence; do not delete attempt records or use automatic rollback/retry.

**No customer write test is marked complete by the agent.** This is an existing-key value pilot only. Key creation, overwrite, multi-valued metadata, general/batch writes, file handovers and production identity remain separate gates. See REDEYE_IMPORT_TEST.md.

## Additional connections — version 0.8

- [x] Official Procore company/project/custom-field OpenAPI contracts retrieved; backend fixtures validate headers, arrays/wrappers, IDs, scopes and paging.
- [x] Backend checks validate encrypted credentials, exact-origin gates, no redirect following, bounded responses, stale generation/permission rejection and non-executable parameter proposals.
- [x] Isolated browser tests validate named scope selection, field inventory, configured REST reads, manual bindings, credential invalidation and viewer/mobile controls using provider JSON fixtures.
- [ ] On Windows, test the updated read launcher with exact additional HTTPS origins and verify its environment is restored after exit.
- [ ] Procore: supply an authorised OAuth access token; test company/project dropdowns, paging, denied scopes, token expiry/replacement and field inventory for the intended company/tool context.
- [ ] Procore: review any definition proposal against duplicates, native types, field-set/project applicability and required-value rules. No proposal is executable yet.
- [ ] Meridian: install/test optional Windows auth dependencies on the actual executor; confirm the current process identity, AD/Explorer permissions, API application path, view/filter, proxy/private route and CA trust.
- [ ] Meridian: compare returned document/version IDs with Explorer; verify repository freshness. Resolve paging semantics before treating the sample as a complete register.
- [ ] Maintenance Connection: obtain the installed edition/version/licence and exact API/auth/response contract; configure and test the bounded reader against that approved scope.
- [ ] Custom/on-premises REST: verify saved path, query filters and JSON pointers; test missing wrappers, empty lists, private CA and permission failures. A configured filter alone does not prove isolation.
- [ ] Verify per-connection field bindings reference the intended bSDD/native IDs and scope; review packages must remain blocked from remote execution until the writer and native inventory semantics are verified.
- [ ] For each 2024+ Revit/Navisworks release, complete the new desktop preparation checks. Neither desktop bridge has been implemented.

These items are also available per connection under Connection preparation. Added parameter-definition/value/read-back/recovery tests default to untested on existing plans; manual marks do not enable adapters or remote writes.

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

## v0.14 — connection comparisons and dashboard

Automated tests use simulated data. These customer UAT checks remain pending:

- [ ] Open Overview: health is unverified before a check, then timestamped after Check read. Test a failed credential and expired evidence.
- [ ] Mappings → Create mapping: select RedEye and Autodesk, read samples, choose shared document-number fields (or explicitly choose filename_stem), map metadata fields, save, Compare data.
- [ ] Repeat RedEye → Meridian Explorer and reverse direction. Confirm Explorer property names and supported API/view with administrator. PowerWeb alone is not an Explorer endpoint.
- [ ] Compare two connections on the same platform and SQL ↔ document data where available.
- [ ] Check duplicate matching keys, missing counterparts, missing required values and differing metadata. Missing counterpart means not in the bounded sample.
- [ ] Select optional bSDD property/type/unit rules; test invalid values and unknown fields.
- [ ] Overview validation totals must match latest current comparison reports. Old reports remain visible as stale after sample expiry, credential/configuration or dictionary changes.
- [ ] Switch project: no connections, samples, mappings or reports leak between projects.

Comparison captures are bounded (RedEye: up to five artefact details; most REST: first 25; SQL: existing bounded table reader). No complete register, file equality or project compliance is claimed. Read sample performs external GETs through existing scoped adapters; Compare data uses saved samples and does not write either platform. Existing RedEye metadata update remains a separate explicit workflow. Procore currently exposes company/project/field-definition datasets, not document tools. Health checks are manual, not background uptime monitoring.


## Native .NET hosted candidate — 12 November 2026

Use [Azure .NET UAT acceptance](AZURE_DOTNET_UAT.md#hosted-uat-acceptance). .NET tests are separate from local Python tests. Entra customer sign-in, Azure SQL managed identity, Key Vault references, restart persistence and deployment have not been customer verified. Hosted writes stay disabled. Native Autodesk OAuth, SQL connector, generic REST/MC, complete Procore scope, and uncertain-write reconciliation remain parity work. Do not mark these complete based on local Python passes.
