# Connection-first local workspace

Version 0.14.0, 11 November 2026.

## Open the application

Stop the old ORBIT server once, update the branch/ZIP while preserving `.local/orbit.db` and `.local/vault.key` together, then double-click **Run-ORBIT.cmd**. Keep that one server window open; all normal setup and testing is in the browser.

A fresh database starts empty. Enter a workspace name, your first project and an optional operator name. No sample organisations, document registers or connections are created. Existing installations can open their existing owner workspace, prioritised by saved real-connection count. Existing credentials, mappings and project IDs are preserved; rename the workspace/project in Settings if desired.

This is an explicitly local, single-operator workspace. It has no synthetic role selector and does not represent Entra/production authentication. Local API access is restricted to loopback peers. Sessions last up to eight hours; opening/signing out explicitly rotates/revokes the session. Ordinary page loads do not rotate it and invalidate write previews. The selected project is remembered on this browser, but server-side grants still determine access.

## Five places to work

- **Overview:** actual saved profile counts, recorded successful reads, saved SQL mapping count and selected bSDD properties. No generated comparison records or fake KPIs. Recorded reads are historical evidence, not continuous health monitoring.
- **Connections:** one platform hub for RedEye, Autodesk Forma/ACC Docs, SQL Server/Azure SQL, Procore, Meridian Explorer, buildingSMART bSDD, Maintenance Connection and custom REST. Choose the platform first; its setup form is scoped to that provider. Existing-profile setup is collapsed until needed.
- **Mappings:** saved SQL mapping previews and configured property-binding summaries. Editing occurs in the connection's workspace; property standards link to the same bSDD connection area. No duplicate synthetic integration/handover editor is shown.
- **Activity:** recorded connector, metadata, SQL, dictionary and local-project events. Old synthetic comparison/proposal events are not presented as connection activity; audit records are not deleted.
- **Settings:** real workspace/project names, additional empty projects, local session access and the current deployment/migration status.

## Connector flows

**RedEye:** Connections → RedEye → Connection. Add/edit the saved setup and encrypted API key, then Test connection. Use Documents & metadata in the same workspace to browse/select an artefact, verify any existing field, or review and confirm a value update. Existing before/after, explicit overwrite, revision confirmation, preservation and read-back controls remain. See [REDEYE_METADATA.md](REDEYE_METADATA.md).

**Autodesk:** Connections → Autodesk. Save setup, configure the APS application, sign in and select accessible hub/project/folder names. There is no separate catalogue/setup page. Real consent, application provisioning and customer-scope acceptance still need testing. OAuth callbacks return to the same Autodesk workspace.

**SQL:** Connections → SQL Server/Azure SQL. Optional ODBC 18/Python support remains a one-time prerequisite. Browse tables, inspect columns/sample rows and map fields to a saved project connection. Mappings → Open SQL workspace returns to that same tool. SQL transfers are not executed. See [SQL_CONNECTIONS.md](SQL_CONNECTIONS.md).

**Procore / Meridian / Maintenance Connection / Custom REST:** open the corresponding platform card. Provider selection is fixed by the chosen workspace. Existing encrypted credentials, discovery/read actions and field-binding tools are reused. For these additional profiles, confirming the saved endpoint and authorised access approves that exact HTTPS origin for local reads; no terminal hostname entry is needed. Legacy/test mode retains its operator allowlist. Read-adapter availability is not proof of customer access or permission. See [ADDITIONAL_CONNECTIONS.md](ADDITIONAL_CONNECTIONS.md).

**bSDD:** open buildingSMART bSDD, select a dictionary/class and save optional property references. These remain project scoped and do not create native fields by themselves.

## Data and migration boundaries

Normal local startup does not seed or display synthetic data. Old demo records on an existing installation are retained rather than deleting potentially related configuration/audit history. Explicit legacy developer/test mode remains available to existing automated fixtures; its identity API is disabled in local-workspace mode.

The React UI is ready for local connector acceptance testing. The working backend is still Python/FastAPI, not .NET. The agreed ASP.NET Core 10/Entra cutover, hosted persistence and secret management are required before publishing to OrbitPortal. No Azure environment was deployed or modified in this increment. See [DOTNET_MIGRATION.md](DOTNET_MIGRATION.md).

Use [TESTER_CHECKLIST.md](TESTER_CHECKLIST.md) to distinguish the already reported RedEye first write pass, automated simulated checks and the customer tests still pending.

## Interface preview

[Connection hub preview](images/connection-hub.png) shows the Constellation navy/cyan/amber brand treatment in an isolated browser-test workspace. Its example workspace name is entered by the test, not seeded into the application.


Mappings → Create mapping now selects any two saved connections, reads bounded samples, chooses matching keys and field rules, and runs Compare data. Swap direction supports reverse comparisons. Overview → Connection health provides manual checks; Data validation summarises current reports. Existing SQL mapping previews remain available in a collapsed section. Reports are scoped to captured data, not complete registers or file hashes.
