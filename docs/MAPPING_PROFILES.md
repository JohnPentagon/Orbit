# Mapping profiles — v0.17.0

13 November 2026. The user confirmed the hosted Autodesk connection; hosted RedEye read was already confirmed. Mapping-profile changes below are automated-tested, with customer UAT still pending.

## Map parameter A to parameter B

1. Open **Mappings → Create mapping profile** and enter a profile name.
2. Choose the **Source connection (A)** and **Target connection (B)**. Existing compatible field samples are reused. If none are available, select **Load parameters** on each side.
3. Under **Pair your parameters**, select a source parameter and its target parameter. Add another pair as needed.
4. Select **Save profile**. The profile persists for this project and connection pair, survives reload/restart, and appears in **Saved mapping profiles**.

Parameter names are shown in plain language where known: for example **File name** instead of `attributes.displayName`, and RedEye metadata/property names without their API prefix. API field identifiers remain available under **Options & validation** for disambiguation. The profile stores exact identifiers, not the friendly label.

You do not need to configure document matching just to save parameter pairs. Saving a profile does not copy documents, create fields, set values or write to either platform.

## Compare the intended documents

Parameter pairing and document matching are separate:

- A parameter pair defines **which values to compare**, e.g. Title → Title or Revision → Revision.
- **Match documents for comparisons** defines **which record on A represents the same document as a record on B**.

Open that expandable section and explicitly select an identifier on each side. A shared document number is often appropriate. If A uses `D-001.pdf` and B uses `D-001`, choose **Ignore file extension** on the file-name side. Do not match a file name to a project-name field simply because both are available. Native platform IDs usually differ.

Select **Save and compare**, or use **Compare data** on the saved profile. If document identifiers have not been configured, Compare opens the profile at that section. Expired samples are refreshed for their saved scopes when the operator has connection permission; if the connection's selected project/folder changed, review/edit the profile instead of silently comparing a different scope. Other roles must ask a connection owner to refresh data.

Comparisons remain bounded samples. Missing counterparts mean absent from the sample, not absent from the platform. Profiles retain their rules after sample expiry; current connection generations and fresh data are still required for comparisons. Editing rules can use an expired schema sample from the unchanged connection, but cannot make that data fresh.

## Edit, copy and delete

- **Edit** updates the same profile and increments its version. It no longer silently creates a copy. Old reports keep the original rule configuration and are marked as previous evidence after an edit.
- **Copy** creates a separate profile. Rename it, and change the connections/parameters if needed. Profiles are currently project-scoped; this is not a global cross-project template library.
- **Delete** asks for confirmation. It removes the profile from active mappings and dashboard totals, while preserving previous comparison reports, rule revisions and audit history. It does not delete connections or platform data. Deleted profiles cannot be edited or compared; restoration is not currently exposed in the UI.

Concurrent edits/deletions require the current profile version. Viewers cannot modify profiles. All operations remain tenant/project scoped. Legacy SQL previews stay in their separate expandable section.

## Advanced controls

**Sample options** contains prior sample selection and optional explicit RedEye artefact IDs. SQL source schema/table controls remain visible where relevant. Raw scope JSON is no longer shown in the primary form.

**Options & validation** on a parameter pair contains value transformations, required-value checks and optional pinned bSDD property/unit validation. No transformation or matching identifier is silently guessed.

## Deployment and customer checklist

Deploy the v0.17.0 Windows x86 ZIP using the existing Kudu process and restart OrbitPortal. Keep all existing environment variables, encryption key, data directory and key ring unchanged. No new paid resources or database schema migration are required. Existing v0.16 profiles remain available.

- [ ] Pair available Autodesk and RedEye parameters and save without document matching.
- [ ] Reload and confirm the named profile is retained.
- [ ] Edit the same profile without creating a duplicate; copy it deliberately when desired.
- [ ] Configure meaningful document identifiers, then compare known records.
- [ ] Delete a test profile, cancel once, then confirm deletion. Its past reports must remain available under Data validation.
- [ ] Existing Autodesk authorisation/renewal and RedEye read continue to work after deployment.
- [ ] Confirm profiles and their encrypted connections survive an Azure app restart.

Automated native tests cover profile lifecycle, optimistic versions, role/project denial, expired schema versus fresh-data comparisons and retained historical reports. Browser testing uses simulated connectors; customer metadata and live writes were not used to verify these UI changes. Hosted RedEye writes remain disabled as previously configured.
