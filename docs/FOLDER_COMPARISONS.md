# Folder-to-folder checks — v0.20.0

## Set up the two scopes

1. Open Connections → Autodesk, browse to the required folder and select **Comparison scope → Whole folder — read every accessible file**.
2. Tick **Include all subfolders** if required. Leave it unticked to compare only the files directly in the folder.
3. Click **Use whole folder** (or **Use whole folder + subfolders**). You do not need to load every preview page or select file checkboxes. Whole-folder mode includes newly added files on subsequent reads.
4. Configure the destination connection's scope in the same way. Use two saved connections for independent A/B folder scopes, including when both use the same Autodesk account/project. Credentials and permissions are enforced independently; authorise each connection through the existing APS flow.
5. Open Mappings → Create mapping profile (or Edit an existing one). Choose connection A and connection B and **Load/Refresh parameters** for each.
6. Pair the parameters to compare. Under **Match documents for comparisons**, choose the identifier on each side: document number, file name, or **Relative file path** for recursive folder structures. Explicitly choose any case/space/extension transformation. Native platform IDs usually differ between platforms.
7. Save the profile, then compare. The profile retains both scopes, the recursion options, matching keys, transformations, field mappings and optional required-value/bSDD checks.

Each connection has one saved scope. Changing it changes the connection generation and invalidates earlier samples; edit affected profiles, refresh their parameters and save the new scope deliberately. It does not silently retarget saved profiles.

## Coverage and results

Whole-folder mode follows fixed Autodesk API pages and, when enabled, descendant folder IDs returned by that API. It does not stop at the 25/100/250 sample limit. The existing bounded sample and individual-file modes remain available.

The scan supports **5,000 files, 500 folders, 1,000 pages, 64 folder levels, 16 MB metadata and a 180-second overall deadline** per scope. This is a synchronous UAT scan; the UI shows that it is reading/preparing, not a live per-file progress counter. Larger background/resumable scans remain future work. No automatic retry after a failed scan is performed.

On an access error, timeout, repeated/empty continuation page, folder cycle or safety-limit violation, the scan returns an error and **does not save partial comparison evidence**. An existing older snapshot is not relabelled as a new successful scan. Live file changes during pagination and permission-hidden files cannot be detected; completion means all pages of the vendor-reported accessible selected scope were read, not an atomic inventory of the whole platform.

Reports show coverage independently on each side. **Both selected folder scopes complete** appears only when both captures completed a whole-folder scan. Missing counterparts are then labelled **Only in A/B (selected scope)**. Differences, required/property issues, missing identifiers and duplicate/ambiguous identifiers remain visible. Metadata agreement does not prove file-byte equality.

The dashboard labels these reports **Complete folder scopes** and retains the existing freshness rules. Run a fresh comparison after changes; refreshing the dashboard itself does not scan files.

## Other platforms

This whole-folder implementation is for the hosted native .NET Autodesk connector. A whole Autodesk folder can also be compared with another connector's supported capture, but coverage is **mixed/bounded** unless both sides completed their selected scope. **RedEye still captures up to five artefacts' metadata; complete group/register scans and full Meridian folder traversal are not implemented by this release.** They are never presented as complete folder-to-folder evidence. No document transfers or platform writes are added.

## Customer acceptance checklist

- [ ] Deploy v0.20.0 and confirm `/api/health`.
- [ ] Save a direct folder scope and compare more than 250 accessible files, if a suitable test folder is available.
- [ ] Save a recursive scope and confirm subfolder documents and relative paths are included.
- [ ] Configure two independent Autodesk folder connections; save the two scopes, key and mapped parameters in a profile.
- [ ] Check matched, different, unmatched, missing-key and duplicate-key results with controlled test data.
- [ ] Add a file to a selected folder, refresh comparison data and confirm the file is included without selecting its checkbox.
- [ ] Confirm report coverage and dashboard completion labels; check mixed RedEye coverage stays bounded.
- [ ] Test a denied subfolder/read failure and confirm no new partial snapshot/report is created.
- [ ] Change scope and confirm previous evidence needs refreshing and profiles require deliberate scope updates.

Automated checks use simulated vendors. They cover direct reads of 301 files, recursive traversal, mapping keys/rules, missing/duplicate identifiers, coverage flags, no partial evidence on failures, saved UI scope, legacy samples, dashboard and profile lifecycle. Real customer folder acceptance remains pending.

Deploy the Windows x86 ZIP through the existing Kudu process and restart. Preserve all App Service settings, encryption key, data and key ring. No new environment variables or paid resources are required.
