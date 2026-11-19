> v0.20.0 adds optional [whole-folder and recursive comparisons](FOLDER_COMPARISONS.md), alongside the existing bounded sample mode. Follow that checklist for the new workflow.

# Project dashboard — v0.19.0

Open **Overview** after deploying v0.19.0. Choose the project at the top of the page. The dashboard uses saved connections and captured comparison evidence; no synthetic customer data is installed.

## What is shown

- **Connections checked:** successful checks recorded within the last 30 minutes, out of all saved connections. Expired, unverified, failed and setup-required connections remain visible. This does not establish continuous availability.
- **Current comparisons:** latest non-stale report for each active mapping profile. Older revisions, deleted profiles and stale evidence are excluded from current totals.
- **Different values / unmatched documents:** comparison document-pair counts from current reports. A missing counterpart means not found in the captured sample, not absent from the entire platform.
- **Property validation:** invalid and unverified field findings, plus the selected bSDD dictionary and property count. These counts can overlap with differences and across profiles; they are not a unique whole-project document count.
- **Needs attention:** profiles not yet compared, profiles whose evidence needs refreshing, and reports with findings or no data.
- **Latest comparisons:** current, expired and not-yet-compared states with timestamps, connection pairs and report links. Report links support browser reload and remain subject to project access.

**Refresh dashboard** reloads recorded results only. **Check read** explicitly reads the selected connection scope; it does not run a comparison or refresh comparison samples. SQL reads stay in the SQL workspace, where a table is selected. Viewers can inspect the dashboard but do not receive connection-check controls. Existing server permissions and project isolation remain authoritative.

Use **Mappings & comparisons** to refresh parameters, save the intended scope and compare again. Use **View report** to inspect matching identifiers, field values, findings and read coverage. There is no automatic polling, platform write, scheduler or new Azure service.

## Customer acceptance checklist

- [ ] Deploy the Windows x86 v0.19.0 ZIP through Kudu; restart and confirm `/api/health` reports `0.19.0`.
- [ ] Open Overview and confirm the project name and saved connections are correct.
- [ ] Run Check read on RedEye and Autodesk; confirm timestamps/status update without creating a comparison report.
- [ ] Save and run an Autodesk ↔ RedEye comparison; confirm the latest profile result and findings appear after refreshing Overview.
- [ ] Open View report and confirm the selected folder/files, field values and read coverage match the test.
- [ ] Change a profile or connection scope, or allow evidence to expire; refresh and confirm old findings leave the current totals and Refresh needed is shown.
- [ ] Switch to another project and confirm its connections/results are separate.
- [ ] Test a read failure and confirm its status/error is visible without reporting a successful check.
- [ ] Test viewer access and confirm connection checks are unavailable.
- [ ] Check a narrow browser window or phone layout.

## Automated verification

The dashboard browser fixture checks latest-active-report rollups, stale and deleted-history exclusion, health filtering, explicit CSRF-protected reads, report deep links/reload, failed-refresh retention, empty projects, project switching, viewer controls and mobile layout. All vendor responses are simulated. Native backend and Autodesk/mapping browser regressions are also run before packaging. Real customer acceptance remains pending.

No additional environment variables or paid resources are needed. Retain the current encryption key, data path, key ring, Entra settings and connector configuration. Hosted write restrictions are unchanged.
