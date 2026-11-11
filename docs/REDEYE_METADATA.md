> In v0.13, open Connections → RedEye → Documents & metadata. Setup and encrypted credentials are in the Connection tab of that same workspace; there is no separate sidebar test page.

# RedEye metadata verification and editing

Version 0.11, 10 November 2026. This replaces the restrictive one-value pilot in the portal navigation. The user requested arbitrary existing-field selection, verification and updates. No customer write was performed during implementation.

## Start

Stop the older ORBIT server once, update the `orbit/local-test-foundation` branch or download its ZIP, and preserve `.local/orbit.db` and `.local/vault.key` together. Double-click **Run-ORBIT.cmd**. Keep that single server window open; all connection setup and testing then happens in the browser at http://127.0.0.1:8000.

Use your local owner identity. Under **Read connections**, save/confirm the RedEye host and auth settings and store your key encrypted. Existing working connections are reused. Open **RedEye metadata**; no connection UUID or hostname needs copying into a terminal.

## Select and verify

1. Choose your saved RedEye connection. Browse a bounded artefact sample or enter a known artefact ID.
2. Click **Load metadata fields** and choose any existing metadata field. Its returned current values are shown, including populated or unassigned keys.
3. Choose **Verify only**. Click **Verify selected field** to read the field again without writing. Optionally select **Compare with an expected value** and specify that value; the result reports match or difference.
4. Leave bSDD validation as **None** for native-field checks. Optionally choose an enabled project bSDD property and unit to check the expected and observed values against that property.

Verification works with existing revision history and with artefacts that RedEye reports unmodifiable. It describes the latest approved revision returned by RedEye, not a guarantee about a different current/draft revision. A match reports observed state only and never proves a past API write.

## Update

1. Choose **Update value** on the selected field and enter the replacement value. Plain text needs no JSON quotes; blank text sets an empty string. It does not delete the assignment.
2. For a populated field, select **Replace existing value(s)**. Otherwise the server rejects an overwrite. Choose **Typed JSON / multiple values** for a number, Boolean or explicit array such as `["first", "second"]`.
3. bSDD is optional. For a selected numeric/Boolean bSDD definition use typed JSON with the correct source type, unit and allowed value. No unit conversion or native key-type creation occurs. RedEye receives string values.
4. Click **Preview metadata update**. Review the exact artefact, key, before/after values and optional complete metadata body. Every other returned metadata key/value is preserved, including multiple values.
5. Confirm the displayed change and the intended revision target, then click **Confirm and save to RedEye**. There is no separate approver role, arming step, typed artefact-ID confirmation or terminal opt-in for this local owner UAT flow.

RedEye documents GET as latest approved and POST as current revision. Confirm in RedEye that those are the same intended target before saving, and avoid concurrent edits. The writer does not establish or force equivalence between a different draft/current and approved revision. The UI no longer requires a fixed revision count or disposable-only evidence. RedEye must still report the artefact modifiable for an update.

A preview lasts 30 minutes and is bound to the browser session, project, connection/credential generation, complete inspected destination state and optional bSDD reference. Just before writing, the server rechecks the selected target and metadata under the local write lock. Changed inputs cause **not_sent**, requiring a fresh inspection/preview. Local UAT identities remain synthetic; do not expose this application as a shared/public service.

## Result and further edits

- **verified:** selected field values, every preserved metadata value, key identities and stable artefact/revision/content guards matched on read-back. Also inspect the result in native RedEye during acceptance testing.
- **not_sent:** preconditions or preflight failed before POST; inspect again. No update was sent by that preview.
- **needs_review / attempting:** an attempted/interrupted update needs checking. No automatic retry is allowed. Use **Recheck without writing** and inspect native RedEye. New writes to that same connection/artefact wait until the previous uncertain attempt is resolved. If rechecking cannot establish the expected result, inspect the original target in native RedEye and use **Close after manual review** with its explicit acknowledgement. This records operator review without claiming API success, retrying or rolling back. You can then inspect afresh and choose a new change. Earlier pilot uncertainties are also shown for read-only rechecking.

Each preview can attempt POST at most once, with its reservation persisted before the request. Replaying it returns its prior receipt/status. A **successful** update does not permanently lock the artefact: load metadata again and prepare another chosen-field change. Stale previews cannot overwrite that newer state.

Receipts retain the first outcome and separately report complete POST HTTP 200 acknowledgement and observed read-back state. A successful GET after a timeout proves observed state, not who made a change; do not mark an API write passed just because a manual change later matches. No automatic retry, remote rollback or deletion is performed.

## Supported contract and limits

The reviewed [RedEye API](https://api.redeyedms.com/#redeye-dms-api) documents [GET artefact](https://api.redeyedms.com/#getartefact) metadata with key IDs/names and string values, and [POST update](https://api.redeyedms.com/#updateartefact) as `metadata: [{name, value: [string]}]`. No metadata-key creation endpoint was established. Keys must already exist in RedEye; choosing a bSDD property does not create them.

The editor accepts up to 100 proposed scalar values, 10 KB of input and 100 KB of complete metadata update body. It reads a bounded inventory (2,000 keys, 1,000 artefact metadata entries, 1 MB per vendor response). Unknown/null/non-string native values or ambiguous key identities fail explicitly rather than being discarded. Empty arrays/key deletion, core title/number changes, bulk operations, file transfers and general multi-platform writes remain outside this editor.

The reviewed API provides no established atomic If-Match/revision precondition. A fresh read-before-write reduces stale updates but cannot eliminate the remote race window. The browser confirmation and native revision check remain necessary. History/read-back are observations, not continuous monitoring or proof of ISO/IDS compliance.

Automated tests use simulated vendor transport and isolated databases. Real API-key write permissions, revision behaviour, multivalue acceptance and Windows launcher execution still need customer validation in [TESTER_CHECKLIST.md](TESTER_CHECKLIST.md).

## Diagnosing a 409 when saving (v0.11.1)

A terminal access-log line such as `POST .../execute 409 Conflict` does not contain the rejection reason. The portal now scrolls to the error and repeats it beside the save preview; the server also logs a safe `ORBIT RedEye save blocked [reason_code]` line. Copy that reason rather than keys, request bodies or customer values.

| Reason code | Next step |
| --- | --- |
| `uat_not_enabled` | Stop the old server once; start Run-ORBIT.cmd from the updated folder and reload. |
| `preview_session_changed` | Another sign-in/identity change, including another tab, rotated the cookie. Remain signed in as owner and load/preview again. |
| `preview_expired` | Load metadata and preview again; validity is 30 minutes. |
| `preview_digest_mismatch` | Discard the stale preview and prepare the intended change again. |
| `confirmation_missing` | Check both final change/revision confirmations. |
| `connection_changed` | Reload metadata using the current saved connection/credential and prepare a fresh preview. |
| `earlier_update_unresolved` | Review the history entry or earlier-pilot card, use GET-only recheck, and inspect native RedEye before any manual closure. |

These coded execute rejections occur before this request reserves/sends a RedEye write; an earlier uncertain attempt may still have changed the remote target. The response identifies blocking attempts without copying their metadata. A frontend/server version mismatch also produces an update/restart message.

The earlier v0.9/v0.10 pilot now has **Close earlier pilot after manual review** on its card. Explicit acknowledgement closes only its local uncertain status, preserves the receipt, audit trail and durable attempt slot, and never retries/deletes/rolls back a vendor operation or claims verified success. It permits a fresh selected-field preview once the original outcome has been reviewed. An interrupted `attempting` pilot must first be rechecked before manual closure.
