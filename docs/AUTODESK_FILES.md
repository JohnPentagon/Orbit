# Autodesk folders and files — v0.18.0

In Connections → Autodesk, open the connected project and load its top-level folders. Choose a starting folder, open subfolders, and use the breadcrumbs or Up one folder to return. File checkboxes select the exact documents for the next comparison sample. Save with Use selected files, or leave the selection empty and use the chosen folder.

Load more entries retrieves another page. Each page contains up to 25 entries; the browser supports up to 1,000 entries in one folder. Choose a visible comparison limit of 25, 100 or 250 files. New UI selections default to 100; older saved selections without a limit retain 25 until saved again. A folder read excludes subfolder records and does not recurse into their contents. Explicit file selection reads only those selected files, searching further pages as needed. Missing selected files cause an error rather than a silently incomplete snapshot. Metadata reads have time and response-size bounds and download no file bytes.

After saving a different folder, file selection or limit, edit an existing mapping profile, refresh its parameters, then save the profile before comparing. This preserves the deliberate source and destination scope of existing profiles.

The comparison coverage states the bound and whether more files are available. This is not a complete project inventory. Other connectors retain their own limits; recursive scans and large background comparisons remain future work.

## Acceptance checklist

- [x] Automated nested folders, breadcrumbs and later-page file selection.
- [x] Automated reads above 25 files, excluding folders.
- [x] Automated rejection of unknown folders, cross-folder selections and missing selected files.
- [x] Automated permission/configuration-change and repeated-page safeguards.
- [x] Browser workflow including saved selection, renewal and mobile layout (simulated vendor responses).
- [ ] Customer: open a real Autodesk subfolder and select files from a later page.
- [ ] Customer: refresh and save a mapping profile, then compare with RedEye.
- [ ] Customer: verify coverage and the 100/250 file limits against a suitable test folder.

Deploy the v0.18.0 Windows x86 ZIP using the existing Kudu process, restart OrbitPortal and check /api/health. No new environment variable, credential, database or paid resource is required. Existing settings and stored connections remain in place. Python local-backend folder browsing remains on its existing selector; this enhancement targets the hosted native .NET backend.
