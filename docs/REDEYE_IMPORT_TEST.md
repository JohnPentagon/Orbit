# bSDD → RedEye isolated value import test

Version 0.9, 9 November 2026. The owner reports successful RedEye and bSDD reads. This is the next **single-value live pilot**, not a general dictionary/key import or document transfer. No customer write was performed by the agent.

## What to prepare

- A saved RedEye **Read connection** with your encrypted test API key and confirmed host/header/test scope. The key must have write permission for the intended test; successful reads do not prove that.
- An enabled project bSDD dictionary/class reference with at least one selected property. A simple String property without enum/unit constraints is easiest for an initial marker, but use a value that meets the selected definition.
- One **disposable isolated RedEye test artefact**, preferably in a dedicated test bucket. It must have one matching visible revision in detail and history, current and approved must be the same intended revision, and RedEye must report it modifiable. No other process/user may change it during the test.
- An existing RedEye metadata key that is **unassigned or has an empty-string value on that artefact**. Nonempty values are protected; null/unknown values require separate contract review. If a test key needs creating, have the administrator create it in RedEye first. The reviewed API does not document metadata-key creation. Do not infer that choosing a bSDD property creates a native key/type.

The first pilot rejects nonempty target values, multi-valued metadata, unknown keys, unsupported types/value kinds, missing evidence, ambiguous revisions and a changed destination. Core title/number/geometry/workflow fields are not sent in the write body. Source bSDD type/allowed-value/unit validation happens before encoding the scalar as a RedEye string metadata value. No unit conversion or native field typing is claimed.

## 1. Prepare with reads only

1. Stop the previous ORBIT process. Update to v0.9 while preserving the local database/vault-key pair securely, then start **Run-ORBIT-Read-Tests.cmd** and type ENABLE.
2. Open **http://127.0.0.1:8000**, choose your local owner role, then open **RedEye import test**.
3. Choose the saved RedEye connection. Load the bounded candidate list or enter the known disposable artefact ID; click **Inspect RedEye target**. This reads keys, artefact detail and version history. It does not POST to RedEye.
4. Review the exact number/title, ID, state, revision ID/status and returned metadata. The API says GET is latest approved, while POST updates current revision. Confirm in the native RedEye UI/admin documentation that these are the same target. The portal does not infer approval from an arbitrary status label.
5. Select one bSDD property, an existing empty key and a valid typed JSON value, such as `"ORBIT_TEST_2026-11-09"` for a free-text String property. Numeric/Boolean values remain native JSON until explicitly encoded as RedEye strings. Choose supplied units where applicable.
6. Review the complete metadata body. It includes every other returned single-valued metadata entry unchanged, plus the one intended target value (adding an unassigned key or filling a blank string). Confirm the explicit disposable-target, current/approved, payload-contract and semantic/type/unit checks. Record a non-secret test/admin reference.
7. Click **Prepare RedEye write preview**. Resolve all blockers. Use a separate project approver to **Approve RedEye test**. Approval does not send a write.

Inspections and previews expire after 15 minutes. The preview pins the full bSDD project reference, connection generation, existing keys/values, artefact identity/state and visible revisions. If any changes, inspect/review again. The source property identity and proposed native key ID/name are stored with the test.

## 2. Enable exactly one target

Stop the read-test server. Run **Run-ORBIT-RedEye-Import-Test.cmd**.

Enter:

- `WRITE TEST` at the explicit opt-in prompt.
- The saved RedEye read **connection UUID** shown on the test page.
- Its exact API **hostname only**, such as `api.redeyedms.com`, without HTTPS or a path.
- The exact disposable artefact ID.

**Never enter the API key in the launcher.** It reuses the encrypted credential already stored in the portal. The launcher sets only process-local read/write opt-in and the exact connection/host/artefact allowlist, then restores prior environment settings on exit. It does not publish an environment, change firewall rules or grant vendor permissions.

In the portal, return to the owner role and the approved test. Type **WRITE followed by that artefact ID** (for example `WRITE 12345`) in the execution confirmation, then click **Write this one RedEye test value**.

The launcher does not write automatically. The server checks the exact target, current approval/role/grants, expiry, unchanged dictionary/credential/connection and a fresh RedEye snapshot. It reserves the attempt durably before sending a single POST to `/api/v1/artefacts/{Id}` with only the reviewed `metadata` body. It then reads back keys/detail/history and compares the target plus **all returned pre-existing values** and stable identity/revision/content guards.

The normal `Run-ORBIT.cmd` clears inherited pilot flags for its process. The normal read-test launcher also explicitly clears/restores pilot flags. Neither enables this write path. Stop any old server before switching launchers; ORBIT refuses to start another listener on port 8000.

## 3. Check the outcome

- **verified:** the expected target value and all preserved metadata matched on read-back, with unchanged stable guards. Also verify the exact key/value and current/approved revision in the native RedEye UI, then record the result in TESTER_CHECKLIST.md.
- **needs_review / attempting:** no automatic second POST is permitted. A network timeout or lost acknowledgement may occur after a successful remote mutation. Inspect RedEye, then use **Recheck RedEye without writing** when appropriate. That performs GETs only.
- The receipt retains the initial recorded outcome, timestamps observations and separately records whether a complete bounded POST HTTP 200 response was observed. A later successful GET recheck proves the observed state; it does not manufacture an HTTP acknowledgement or prove who caused a change after an interrupted request. Do not mark an API write test passed solely because a later recheck observes a manually changed value.
- A connection/artefact pair has **one durable attempt slot** for this initial pilot. A duplicate request, new preview or process restart cannot issue another POST to that same target through this pilot. For a further test, use a new disposable artefact after reviewing the previous outcome. Do not delete databases/attempt records to force a retry.
- Clean up the disposable test manually in RedEye after preserving evidence. ORBIT does not automatically delete values, undo revisions, roll back remote writes or remove test artefacts.

## Limits that matter

There is no established vendor atomic revision/If-Match contract in the reviewed API. A read-before-write still has a remote race window. Single-target allowlisting, fresh snapshots and visible-history checks do not replace isolation and the operator's explicit current/approved confirmation. Local concurrent configuration changes are blocked during the bounded POST/read-back transaction, but the remote service is not transactionally locked.

The normal multi-platform **Parameter imports** page still runs local synthetic imports only; its RedEye review packages do not invoke this pilot. This dedicated pilot does not create keys, alter native definitions, process batches, overwrite nonempty target values, handle multi-valued properties, upload/download files, perform handovers or enable bidirectional sync. It does not prove general permission, complete bucket quality or ISO/IDS compliance.

All UI roles remain synthetic trusted-local test identities, not production authentication or guaranteed human separation. Use an authorised least-privilege test key and disposable data. API keys are never returned by pilot APIs; malformed/unverified base URLs are redacted, and credential-like test/evidence values are rejected before persistence.

## Evidence and verification

Official [RedEye API](https://api.redeyedms.com/#redeye-dms-api) rechecked 9 November 2026:

- [GET artefact](https://api.redeyedms.com/#getartefact): describes latest approved revision, metadata key IDs/names/string values, revisions and modifiable state.
- [Version history](https://api.redeyedms.com/#getversionhistory): documents a `revision` wrapper. The parser recognises a single object or an unambiguous array in that wrapper and records its shape; multiple/mismatching visible revisions block the pilot.
- [POST update](https://api.redeyedms.com/#updateartefact): describes current-revision updates with `metadata: [{name, value: [string]}]`, and HTTP 200 without a required response body.

Documentation authentication/localhost boilerplate is not treated as permission for anonymous access. The configured confirmed host and encrypted header/key remain mandatory. There is no documented key-creation endpoint in the reviewed inventory.

Backend tests simulate success, timeout after acceptance, failed read-back, incorrect preservation, changed inputs, revoked permissions, stale approvals, duplicate attempts and safe GET-only reconciliation. The Chromium workflow runs the actual app/DB approval and attempt handling against a **simulated RedEye transport**, never a customer write. The optional Windows batch/PowerShell launchers still need execution on the user's Windows machine.

For repeatable browser validation, run the test-only factory on loopback port 8003:

```bash
.venv/bin/uvicorn backend.redeye_pilot_fixture:create_fixture_app --factory --host 127.0.0.1 --port 8003
node frontend/redeye-import-test-smoke.mjs
```

That factory creates an isolated temporary DB, uses hand-authored data, simulates the POST and forbids real HTTP transport. It is not the normal app startup or evidence of vendor connectivity.
