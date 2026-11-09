# Parameter definition and value imports

Version 0.7, 7 November 2026. **Executable against local synthetic registers only.** Real-platform writes remain unavailable. The environment access failure reported before this work cleared on retry; it is not the reason vendor writes remain disabled.

## Workflow

1. Select the project. Under **bSDD dictionaries**, enable a dictionary/class reference and save selected property definitions.
2. Open **Parameter imports**. Choose the exact destination connection. The list distinguishes local synthetic connections, real read-test connections and preparation records. They are separate IDs and cannot be substituted for one another.
3. Include the desired definitions, choose destination parameter names and mark required project values explicitly. Core document fields (`id`, `number`, `title`, `revision`, `status`) are reserved.
4. Optionally enable a common value per property and select destination documents. Typed values use JSON: `"Steel"`, `60`, `true`, or a list for a List-valued property. Leaving all documents unselected imports definitions only. The API also supports different value rows per document; the current UI applies common values to selected documents.
5. Leave **Overwrite existing values** off to preserve existing values. No value is deleted implicitly; omit a property to leave it unchanged. Null/blank-required values are rejected rather than treated as deletion requests.
6. Click **Preview parameter import**. Review create/reuse actions, before/after values, skips, definition conflicts and capability blockers. Nothing has been applied yet.
7. Use a separate project approver to approve the exact preview. A project owner can then click **Apply local parameter import** for an approved synthetic destination.
8. Inspect the completion receipt and **Check local parameter quality**. A definition-only import can succeed while required values are still missing on documents; these are distinct results.

The synthetic identity picker is for a trusted local tester; it does not establish production identity or separation of duties. Switch the test identity only to exercise workflow behaviour. Production identity remains a deployment gate.

## What actually runs

Local execution creates/reuses bSDD-backed field definitions and writes typed metadata values in the exact selected synthetic connection. Definitions retain the original class-property URI, property URI, source definition/type/constraints, explicit required flag and chosen unit. Values are separate from core synthetic document columns and from comparison/handover mappings.

Execution is a single SQLite transaction. The server rechecks the schema snapshot, destination generation, all destination definitions and selected document/value snapshots after approval and immediately before applying. It reads definitions and requested values back from the destination store. Any mismatch rolls back the entire local transaction. A completed request returns its original receipt on replay instead of writing again. There is no remote partial-failure or retry implementation because no remote writer runs.

Schema changes, destination/credential generation changes, selected document changes or concurrent parameter changes invalidate an outstanding preview. Generate and review a new preview instead of silently adjusting an approved plan. An expired (24-hour) or cancelled import cannot execute. The approver's current role and project grant must still be valid at execution. Definitions with different source bindings/types/units/required settings are blocked; changing an existing definition requires a future explicit migration flow. Duplicate names or aliases for the same property cannot silently create parallel bindings.

## Validation and quality

Implemented source data types: String, Boolean, Integer and Real. Single and List value kinds are supported. Values are not silently coerced, so JSON `true` is not integer `1`, and text `"60"` is not integer `60`. Numeric/Boolean allowed-value labels supplied by bSDD are interpreted for comparison, while the proposed value must already have the correct native type. Unsupported/unspecified source types or constraint contracts block the preview.

Units must match the supplied unit exactly; a single supplied unit can be selected automatically, while multiple supplied units require an explicit choice. There is no conversion. Unknown units are not invented. Only string unit identifiers currently participate in unit selection; more complex unit schemas need a reviewed extension.

Destination field names are matched case-insensitively. Existing compatible fields are reused. Incompatible definitions, duplicate bindings and reserved names block execution. Existing values are skipped unless overwrite is explicit; the preview and receipt identify skipped values. A retained invalid value remains a blocker. For selected document rows, a required property needs a valid proposed or existing value. A definitions-only import does not require document values.

The local quality endpoint scans the destination's imported field definitions against its synthetic documents, checking required values, native types and supported allowed values. Limits: 100 documents and 200 parameters per local quality scan, with at most 1,000 findings returned and an explicit truncation flag. This is not a complete vendor audit, classification assignment, IDS or ISO 19650 compliance result.

## Remote capability limits

| Platform | Current evidence | Required before a real writer |
| --- | --- | --- |
| RedEye | Official docs describe `POST /api/v1/artefacts/{Id}` metadata updates on the current revision. `GET /api/v1/artefacts/{Id}` describes the latest approved revision. The reviewed operation inventory does not document creating metadata keys. | Vendor/admin-confirmed key creation or supported administrative import; exact revision targeting; merge versus replacement behaviour; write permissions, bounded read-back, concurrency and retry semantics. |
| Forma / ACC Docs | Existing ORBIT adapter discovers/read-tests hubs, projects, folders and documents. This does not establish custom-attribute creation or writable version scope. | Verified definition/value endpoint contracts, folder/project inheritance, supported types and write-scoped consent/permissions, plus sandbox read-back and conflict tests. |
| Meridian / PowerWeb | PowerWeb is a client. Explorer documentation establishes reads. .NET/Connection API documentation is separate. | Installed edition/release/SDK, supported definition/value operations, vault privileges, authentication and a verified on-premises execution bridge. |
| Procore / Maintenance Connection / custom | Version 0.8 adds scoped Procore reads and administrator-configured REST readers; these do not establish write permission. | Product-specific definition/value contract and permission/sandbox validation. |

A live/preparation destination can produce a saved review preview, but receives capability/inventory blockers. It cannot be approved or executed. External IDs entered into a review package are unverified; no vendor inventory or permissions were queried. Even a local opt-in for metadata reads cannot enable these writes. No HTTP write path, endpoint guessing or credential forwarding is included in this increment.

**Download review package** exports `ORBIT_PARAMETER_IMPORT_REVIEW_V1`, including the preview/digest and proposed values. It is not a vendor-native import format, a completed transfer, or an instruction file that runs automatically. The full bSDD property snapshots are embedded in the field definitions. Packages are project data; share them only with appropriate recipients.

Official sources reviewed:

- [RedEye update artefact](https://api.redeyedms.com/#updateartefact) and [get artefact](https://api.redeyedms.com/#getartefact). The public page was retrieved again on 7 November. Authentication boilerplate/localhost examples are not treated as permission for anonymous writes.
- [Autodesk ACC introduction](https://aps.autodesk.com/en/docs/acc/v1/overview/introduction/). Candidate attribute-reference pages returned HTTP 406 during this research; they do not establish a usable write contract.
- [Meridian API landing page](https://help.accruent.com/meridianenterprise/Content/Online_Help/Common/API_LandingPage.htm); see MERIDIAN_AND_ON_PREMISES.md for reviewed product/interface distinctions.

## API summary

- `GET /api/projects/{project}/parameter-imports`: scoped destinations, capabilities and job history.
- `POST .../parameter-imports`: immutable preview request (`target_kind`, `target_id`, selected `fields`, optional per-document `value_rows`, explicit overwrite flag).
- `POST .../parameter-imports/{id}/approve`, `/execute`, `/cancel`: exact preview digest required.
- `GET .../parameter-imports/{id}/package`: project-scoped ORBIT review package.
- `GET /api/projects/{project}/parameter-register/{connection}` and `/quality`: local field/value register and bounded quality findings.

Engineers/owners can draft; a separate approver can approve; owners execute local imports. Project readers can view registers/history/packages/quality. Cancellation is available to the requester or an owner before execution. Tenant membership and project grants are checked server-side. Audit events record job IDs, not parameter values; values remain in protected project records.

Tests cover persistence, source/destination scope, role/grant changes, self-approval after role change, exact digests, expiry/cancellation, stale schema/credential/documents/fields/values, typed constraints, definitions-only quality, overwrite protection, distinct per-document rows, transactional read-back rollback and zero vendor HTTP on blocked remote previews. The isolated Chromium workflow uses a hand-authored bSDD fixture, but performs real local SQLite writes/read-back, approval, quality, package download, reload and viewer/mobile checks. It does not validate a live vendor import.

## Additional destinations in version 0.8

Additional connection profiles now appear as their own destination kind. Reviews include their exact generation/configuration digest, company/project IDs, resource-scope reference and manual field bindings. Procore company field-definition inventory can be read; conservative non-executable definition proposals may be included in review packages. Neither a manual binding nor a documented candidate payload enables execution. See ADDITIONAL_CONNECTIONS.md for exact mapping limits and required field-set/value-write validation.

## Dedicated RedEye pilot in version 0.9

The separate **RedEye import test** page now supports an explicitly opted-in, one-artefact existing-key value test with real GET preflight, isolated-target/operator revision confirmation, one guarded POST and read-back/no-retry handling. It does not change this general import executor's remote blockers or permit key creation/batches. Use REDEYE_IMPORT_TEST.md for scope, manual native-UI checks and Windows launcher instructions.
