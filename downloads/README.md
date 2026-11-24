# Latest manual Azure UAT package: v0.21.0

Download **[ORBIT-UAT-0.21.0-dotnet10-win-x86.zip](ORBIT-UAT-0.21.0-dotnet10-win-x86.zip)** using **Download raw file** or **View raw** while signed in. Repository-wide Code → Download ZIP is source code, not a deployment package.

Source `bee15b31451fc1d661c94085869421b26d3e6365`: self-contained ASP.NET Core 10, Windows x86, branded frontend. Adds Transfers for reviewed **Autodesk → RedEye file copies**, with optional mapped-value validation or explicit quality-check bypass, flat/path-metadata/existing-group routing, multipart originals, duplicate-content checks, durable upload reservations, byte/metadata/group read-back and rechecks that never upload again. Originals are retained. RedEye bucket rules determine whether an upload creates an artefact or revision; confirm them before testing. Other transfer directions and destination folder/group creation are not enabled.

UAT supports 1–10 selected files per batch, up to 20 MB per file. Previews are available immediately. **Execution defaults off:** add `Orbit__EnableFileTransfers=true` to the existing App Service environment and restart only when ready to copy. The metadata-edit flag is separate and unchanged. No new Azure resource is required.

**82 native tests** and five browser workflows passed using simulated services. No live customer file was copied; vendor upload rules, permissions and end-to-end acceptance remain customer testing.

Upload this ZIP through the existing Kudu ZIP deployment and restart OrbitPortal. Confirm `/api/health` reports **0.21.0**, then open **Transfers**. Retain existing Entra settings, encryption key, data path, key ring and credentials.

[Setup, official API contracts and live testing checklist](../docs/FILE_TRANSFERS.md).

SHA-256: `8ce6387170c74012415f8382f53b57a5530e43a36146bb4ba75e026392284210`.

Previous packages remain in Git history. This directory contains the current package to avoid selecting an outdated build.
