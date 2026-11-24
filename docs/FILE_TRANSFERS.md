# File transfers — v0.21.0 UAT

## Implemented direction

**Autodesk/ACC original files → RedEye artefacts**, through the hosted native .NET portal's Transfers page. Originals remain in Autodesk. This is a file copy with optional mapped metadata, not a move or scheduled synchronisation. Other directions, uploading to Autodesk/Meridian, nested destination folder creation and large background jobs are not enabled in this release.

### Enable only when ready to copy

Deploy the v0.21.0 Windows x86 ZIP through the existing Kudu process. In **Azure Portal → OrbitPortal → Settings → Environment variables → App settings → Add**, enter:

- Name: `Orbit__EnableFileTransfers`
- Value: `true`

Apply the setting and restart. Keep existing Entra, encryption, data and key-ring settings. No new Azure resource, queue, database or service plan is needed. The setting defaults to false: source browsing and previews work before it is enabled. Set it false again to stop new copy/recheck operations. It is separate from `Orbit__EnableRedEyeWrites`; that metadata-edit flag is not changed or required by the transfer module.

Actual vendor API calls and file traffic remain subject to your existing Autodesk, RedEye and Azure agreements/quotas; no live file copy was performed during development.

## Test from the portal

1. Configure and test your existing Autodesk and RedEye connections. For Autodesk, save the intended folder, recursive scope or individual-file selection on Connections first.
2. Open **Transfers**, choose the source and **Load source files**. Select a small test file. UAT batches support **1–10 files, at most 20 MB per file**. File-name/path filtering locates files beyond the first 500 matching preview entries.
3. Choose the RedEye destination and **Load destination options**. The key uses its saved, confirmed API header and prefix. Read access alone does not prove upload or group-assignment permissions.
4. Optionally select a saved mapping profile for this exact source/target pair and unchanged source scope. The transfer reuses parameter/value transformations and required-value/bSDD rules. Matching keys identify documents for comparisons; this copy operation does not use them to select an overwrite target.
5. Choose **Validate mapped values before copying**, or explicitly **Skip quality validation and copy**. Validation findings block affected files. Skipping does not bypass permissions, version/size guards, vendor requirements or the confirmation step. If no profile is selected there are no mapped-value quality rules to check.
6. Choose the artefact type: document, drawing or media. Choose whether matching content hashes should skip a file or stop it for review.
7. Select destination handling:
   - **Flat destination / one existing group:** use the bucket rules, optionally adding a selected group.
   - **Preserve relative path in metadata:** specify a metadata key supported by the bucket rules. Each file receives its own original relative path; this preserves location information, not a physical directory tree.
   - **Map source folders to existing groups:** choose a destination group for each selected source parent folder. RedEye groups are associations, not nested directories; no groups are created.
8. Add any constant upload-rule keys needed by the bucket, then confirm those rules with the RedEye administrator. Names from `metadata.<name>` mappings become upload metadata key names; other names are passed as the rule keys shown in the preview. ORBIT does not invent a universal title/document-number/workflow routing key.
9. **Prepare transfer preview.** Review every file's version-derived filename, path, metadata, group and validation finding. Preparation sends no uploads. The preview binds connection generations, profile/reference versions, destination key/group inventory and the source version/storage identity. It expires after 30 minutes.
10. Confirm the reviewed batch and select **Confirm and copy ready files**. Keep the page open. Files run sequentially, with status recorded per item. Reloading does not silently resume a batch.

## RedEye revision and duplicate behaviour

The documented upload API delegates routing and revision decisions to the bucket upload rules. **An upload may create a new artefact or a revision of an existing artefact.** Confirm those rules on an approved test bucket before copying. This release cannot guarantee create-only behaviour or force a vendor-specific revision policy.

ORBIT checks SHA-256/MD5 content hashes through the documented duplicate endpoint and keeps a durable SHA-256 receipt per destination connection. A matching hash is handled using the selected skip/stop policy. This does not prevent a different file with the same document number from becoming a revision under the bucket rules. There is no automatic overwrite or destructive-delete API call issued by ORBIT itself; the upload's vendor-side revision effects are governed by the confirmed rules.

## Verification, retries and history

- Source version/metadata and permissions are rechecked before the copy. A source change needs a new preview. The operation copies the pinned original, not a preview rendition.
- Signed storage links come only from the vendor endpoints. Only supported signed S3, Azure Blob or Google Cloud Storage HTTPS hosts are accepted. API credentials are never sent to storage URLs; redirects are not followed. Other storage/auth contracts stop for review.
- Before upload, the content-hash reservation and in-progress row are saved atomically. There is no automatic HTTP upload retry. A repeated request for a verified item returns its recorded result without uploading again.
- The returned artefact's bytes are checked before changing groups. Final verification compares SHA-256, reviewed metadata and required group membership. Upload-rule-only keys that are consumed for routing but not retained as metadata will produce **Uploaded — review required**; the upload is not repeated. This is deliberate visibility, not a failed-file retry.
- A pre-upload failure records **Not uploaded — retry available**. Review and explicitly retry the ready/failed batch; completed/skipped items are omitted.
- A timeout, lost/malformed upload result or verification problem records **Outcome uncertain** or **Uploaded — review required** and pauses the batch. Do not prepare another copy to work around that state.
- Use **Transfer history → Destination artefact ID → Recheck destination — no upload**. For an unknown outcome, identify the artefact in RedEye first. Recheck verifies its bytes before optionally retrying the reviewed group assignment and read-back. It never sends the file a second time. Reconciliation can outlive the source preview expiry/profile change, but a destination connection-generation change requires administrator review; it does not silently use different destination credentials.
- RedEye detail/native-download reads may expose an approved revision rather than an unapproved new upload. If workflow approval or asynchronous processing is pending despite `async=false`, read-back may need a later explicit recheck. ORBIT does not advance approvals automatically. Unknown outcomes are not described as verified copies.

Owners with both connection and run permissions prepare/execute/recheck; other project roles can view the history. Server-side project grants, CSRF and current roles are enforced, including role changes during a transfer. The current single-instance UAT hosting model is retained. Per-file work has a 180-second deadline, with bounded HTTP reads; larger/resumable transfers remain future work.

History retains the reviewed metadata, outcomes, source version identity and content hash, not binary file contents, credentials or signed URLs. File bytes are buffered briefly in memory. The latest 50 batches are shown. Existing audit events record the acting user and transfer state without embedding file metadata values.

## Official contracts used

Reviewed 24 November 2026:

- [RedEye upload](https://api.redeyedms.com/#upload): `POST /api/v2/upload?async=false`, multipart `file` and JSON `data`; `InputUploadRequest` includes artefact type, metadata and hashes.
- [RedEye duplicate hashes](https://api.redeyedms.com/#checkfilesexist): `POST /api/v2/files/exist`.
- [RedEye group association](https://api.redeyedms.com/#addgroupstoartefacts): `POST /api/v1/artefact-groups`.
- [RedEye native download link](https://api.redeyedms.com/#downloadnativefile): `GET /api/v1/artefacts/{id}/download`; artefact detail is read back separately.
- [APS item detail](https://aps.autodesk.com/en/docs/data/v2/reference/http/projects-project_id-items-item_id-GET/) and [version detail](https://aps.autodesk.com/en/docs/data/v2/reference/http/projects-project_id-versions-version_id-GET/): current tip and storage object.
- [APS signed S3 download](https://aps.autodesk.com/en/docs/data/v2/reference/http/buckets-:bucketKey-objects-:objectKey-signeds3download-GET/): complete original download.

The RedEye generated examples use localhost and omit effective authentication detail; ORBIT uses your configured, previously confirmed production API origin/header, not those example hosts. Vendor contracts have been exercised with simulated HTTP responses; live tenant upload rules, download permissions and end-to-end transfers remain customer acceptance work.

## Customer checklist

- [ ] Deploy and confirm `/api/health` shows `0.21.0`.
- [ ] Prepare a one-file preview with execution disabled; confirm no destination artefact appears.
- [ ] Confirm test-bucket upload rules, metadata/routing keys, revision behaviour and API-key write/group permissions.
- [ ] Enable `Orbit__EnableFileTransfers=true`; copy one disposable original and inspect it in RedEye.
- [ ] Compare bytes/hash, metadata, group membership, revision action and retained source file.
- [ ] Test required/bSDD validation and the explicit skip-validation mode.
- [ ] Test path metadata and two source folders mapped to existing groups.
- [ ] Repeat the same batch/item and a matching-content preview; confirm no duplicate upload.
- [ ] Test a read-back/group failure and use destination recheck without uploading again.
- [ ] Test a changed source version, expired preview, viewer account and another project.
- [ ] Confirm audit/history persistence after an app restart and the narrow-screen layout.

Automated tests cover the three destination modes, multipart bytes and metadata, duplicate receipts/hashes, lost upload responses, group-only recovery, content mismatch before group changes, stale versions/configuration, preview/digest confirmation, CSRF/project/viewer boundaries, role revocation and concurrent requests. The browser fixture covers selection, mapping/quality options, group routing, disabled execution, confirmation, uncertain pause/recheck, persisted history, project switching and mobile layout. No live vendor credentials or customer files were used.
