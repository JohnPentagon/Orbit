> In v0.13, open Connections → SQL Server / Azure SQL. All SQL setup, browsing and mapping tools are in that workspace; saved previews are indexed under Mappings.

# Microsoft SQL Server / Azure SQL connections

Version 0.12, 10 November 2026. This increment connects to Microsoft SQL Server and Azure SQL Database through optional pyodbc and Microsoft ODBC Driver 18. It browses visible tables/views, reads column metadata and bounded samples, and saves mappings from SQL columns to another saved project connection. No SQL or destination-platform writer is exposed by this feature.

## Local setup and prerequisites

1. Update ORBIT, preserving `.local/orbit.db` and `.local/vault.key` together.
2. Install Microsoft's **ODBC Driver 18 for SQL Server** on the computer running ORBIT. Use the official installer, not an arbitrary DLL download.
3. Double-click **Setup-ORBIT-SQL.cmd** once to install optional `pyodbc==5.3.0` into ORBIT's existing virtual environment. This helper sends no database query and does not install/change a server, firewall or certificate.
4. Restart **Run-ORBIT.cmd**, then open **SQL connections**. The portal reports whether the Python package and required ODBC driver are available. Normal startup does not require the optional SQL dependency. The pinned pyodbc 5.3.0 release was checked against official PyPI metadata on 10 November 2026; this is package verification, not a native driver/database handshake.

Use an authorised SELECT-only database principal with the necessary object metadata visibility. ApplicationIntent=ReadOnly is a routing preference, not an authorisation boundary. Limit access with database grants. ORBIT generates SELECTs only; it does not accept user SQL, connection-string fragments, stored-procedure calls, DDL/DML or arbitrary ODBC options.

## Configure and browse in the portal

- Choose local/on-premises SQL Server or Azure SQL Database, a **TCP hostname**, explicit port and database name. Default port is 1433; an administrator may have configured another SQL Server port.
- Localhost means the computer executing ORBIT, not your browser device or a future cloud host. Named instances/LocalDB are not directly supported: ask the administrator for an approved TCP endpoint instead of entering `server\instance`.
- SQL login authentication works for local SQL Server or Azure SQL in this increment. Save the password only in the separate encrypted browser form. Replacing configuration clears credentials; replacing/clearing credentials invalidates older samples.
- Local Windows integrated authentication uses the current ORBIT Windows process identity. No browser impersonation, Windows password storage, delegation, Linux Kerberos setup, Azure Entra/MFA, service principal or managed identity flow is implemented here.
- Azure SQL uses the administrator-confirmed logical-server hostname, normally `<name>.database.windows.net`, and SQL login authentication. Sovereign-cloud hostnames and other Azure database services require a separate adapter/configuration increment.
- Confirm approved test access, then choose **Connect and browse tables**. Select a visible schema/table or view, then **Load columns and sample rows**.

Connections use Encrypt=yes and TrustServerCertificate=no. The server certificate must be trusted by the executor and match the hostname. For local development, install/configure a proper trusted certificate/issuer rather than turning verification off. Database/driver/network errors return a fixed safe message, never the connection string or password. Azure firewall/private endpoints, DNS, VPN and connection-policy ports must be configured by the administrator; this feature does not create access or publish a cloud environment.

The SQL adapter is a server-side direct TCP client. An HTTPS API allowlist alone does not establish SQL port access. When ORBIT is hosted later, on-premises servers will require an approved network route or local worker; none is automatically installed by this increment.

## Sample semantics

- Table/view inventory is capped at 200 visible objects, with an explicit more-results flag.
- Objects may have up to 200 visible columns. Column name/type, nullability, identity/computed status and primary-key membership are shown.
- Row previews are an **unordered sample of at most 25 rows**, with a 26th-row probe and more-results flag. A sample is not complete-table coverage, a stable page, change tracking or proof of unique keys across the database.
- String/XML projections are bounded in SQL before fetching; long strings are truncated and labelled. Binary/image/rowversion fields are replaced with omission markers without downloading their contents. Unsupported/custom types are labelled omitted. Use an administrator-approved view with supported types where necessary.
- Exact decimals and integers beyond JavaScript's exact range are represented as text. Dates/times are projected as ISO-style text. NULL remains null; copy mappings preserve these JSON representations. No automatic SQL/native field type conversion is claimed.
- Samples are capped at 250 KB and cached in project-scoped local SQLite for 15 minutes of mapping validity. The retained samples and saved previews are customer data in `.local`; protect backups and do not commit/share that directory. Expiry invalidates use, not physical deletion/retention cleanup.

## Mapping SQL data to another connection

Choose a **source record-matching column**, saved destination connection and explicit **destination matching field**. Map as many source columns as needed, using copy/trim/uppercase/lowercase, defaults and required-value checks.

- **RedEye:** load the destination's existing metadata-key inventory using its approved encrypted read connection. Select keys by displayed name. This discovery is separate from, and does not exercise, the existing RedEye value writer.
- **SQL:** browse a destination SQL connection/table and load its columns/sample, or select an existing prepared sample. The mapping is bound to that exact destination object and generation. Choose a destination matching column from that table. Identity/computed flags describe its schema, not proven write support.
- **Other saved API connections:** manual target-field references are available and explicitly marked as not natively verified. A saved profile is not evidence of platform write permissions or correct target paths.

Owners perform live discovery. Project engineers may use already prepared project samples/catalogues to draft/save mappings without SQL/vendor credentials or live-read permission. Project viewers can inspect saved mapping previews. All API access remains tenant/project scoped; current grants/generations/expiry are checked server-side. Production login/security is still outside this trusted local UAT foundation.

Preview shows transformed source sample values, missing/duplicate matching values within the sample, required-value findings and omitted/truncated data warnings. It **does not query or match destination records**, prove table-wide uniqueness, update RedEye, or insert/update SQL rows. An actual transfer requires verified destination matching, type/null/conflict policy, permissions, approval/atomicity and write/read-back execution. Reverse platform-to-SQL data loading is likewise not yet implemented. The downloaded JSON is an ORBIT review artifact, not vendor-native import data.

Save mappings per project/source/destination connection. Revisions use optimistic version checks. A saved preview is historical; reload fresh source/destination inventory to revise/revalidate after expiry or configuration changes. Composite-key matching is not automatic: use an approved view exposing a stable single matching key, and validate it across the full dataset before any future transfer.

## First customer test and references

Start with an approved small view, a SELECT-only account and two or three columns containing non-sensitive test rows. Compare the portal results with SSMS/Azure tools, then map one field to the working RedEye connection and review the preview. Record actual results in [TESTER_CHECKLIST.md](TESTER_CHECKLIST.md). The agent's tests use mocked ODBC/vendor responses; no customer SQL connection was independently reproduced.

Official setup/contract references (not a claim of live customer compatibility):

- [Microsoft ODBC Driver download](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- [ODBC connection-string attributes](https://learn.microsoft.com/en-us/sql/connect/odbc/dsn-connection-string-attribute)
- [Python connection to Azure SQL](https://learn.microsoft.com/en-us/azure/azure-sql/database/connect-query-python)
- [SQL Server catalog views](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/catalog-views-transact-sql)

Record the actual installed SQL Server release (for example 2022/2025), Azure SQL environment and ODBC driver version during acceptance testing; live release compatibility has not been independently validated.
