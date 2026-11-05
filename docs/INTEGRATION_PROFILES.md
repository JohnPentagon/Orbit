# Integration profiles and synthetic handover previews

## Try the new workflow

1. Sign in as Northstar engineer. Open **Integration profiles** and select **New profile**.
2. Choose the exact source and target connections. Name the profile and record its synthetic source/destination scope labels.
3. Keep the required `number`, `title` and `revision` destination mappings. Add further fields using **Add mapping**. Supported synthetic source fields are number, title, revision and status; target fields can include customer-defined names such as `handover.status`.
4. Set copy/trim/uppercase/lowercase transformations, required values, defaults and optional value conversions such as `{"approved":"Released"}`. Conversions are JSON string-to-string dictionaries, not executable expressions.
5. Save the profile. Changes to an existing profile create an immutable new version. Concurrent edits using a stale version are rejected. Each new version requires its own separate-person approval.
6. Switch to Northstar approver, select the profile, and **Approve profile version**. This approves only the configuration record; nothing is executed.
7. Switch back to the engineer and open **Handovers**. Select that profile, then document **C-005** for the simplest eligible synthetic example. **Create handover preview** freezes the selected current revision and transformed metadata.
8. Switch to approver and review the manifest. **Approve synthetic manifest** records approval only: **zero files are transferred**. The disabled live-transfer button is intentional.

To test validation, include C-002 (draft), C-004 (missing revision), or a record with a destination candidate. The default conflict policy blocks existing candidates. `Skip existing` never overwrites them and still reports source-validation problems. If everything is skipped or blocked, the manifest cannot be approved. Candidate matching uses the mapped destination number but does not prove stable cross-system identity.

Owners can add further synthetic Forma/RedEye connection profiles under **Connections**. These start with empty registers and never inherit records from another connection, even for the same provider. No vendor account sign-in or external request occurs. Creating a reverse-direction profile is explicit; there is no automatic bidirectional execution.

## Scope and lifecycle

Every profile belongs to one tenant/project and references exact persistent connection IDs. Credentials and sign-in session tokens are excluded from mapping configuration. Scope labels are descriptive placeholders, **not implemented vendor folder/group selectors**. The data-access boundary is the authorised project and exact synthetic connection.

Handover previews have a 24-hour expiry and record the profile version/digest, selected document IDs/revisions, target-register snapshot, connection generation, mapped metadata, validation results and manifest digest. Approval revalidates the current project permission, actor, profile approval/version, expiry, exact digest, source/destination snapshots and connection generation. Credential rotation increments connection generation and invalidates an older preview without deleting the profile.

Approved profile history is retained when a new draft version is created. Old manifests remain historical records; an old approval is never permission to execute a later version. There is no execution endpoint. A profile's `comparison` purpose currently stores configuration only and is not wired into the original seeded comparison screen.

## Upgrade behaviour

Migration `002_integration_profiles.sql` adds version/history/manifest tables and document-to-connection bindings. Existing documents are backfilled only when the old project/provider has exactly one matching connection. Ambiguous legacy assignments remain unbound and excluded from connection-specific previews until a reviewed assignment mechanism exists. No existing data is deleted. Each numbered migration and its version marker are committed atomically.

For a local Windows update, stop ORBIT and keep the old folder as a backup. Download the updated branch ZIP and extract it into a new folder. Run `Run-ORBIT.cmd` there for a fresh demo. If you want to preserve your previous synthetic state, copy the old `.local` folder **with its vault key** into the new folder before starting; migrations then upgrade the database. Do not copy `.venv` or node_modules. Never replace local data while the server is running.

## Not a completed file-handover engine

No source binary, historical attachment, rendition or checksum is fetched, verified or transferred. There are no background transfer jobs, retry/resume, destination writes, completion receipts or completeness certification. The manifest states these evidence gaps. Live handovers still need verified provider authentication/permissions/write operations, file staging and integrity verification, durable jobs, idempotency and conflict policies, scoped execution approval and destination reconciliation.

The mapping vocabulary is a synthetic canonical projection, not the verified native Forma or RedEye payload schema. bSDD, IDS and ISO 19650 project profiles remain future validation inputs.
