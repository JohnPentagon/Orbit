# Latest manual Azure UAT package: v0.20.0

Download **[ORBIT-UAT-0.20.0-dotnet10-win-x86.zip](ORBIT-UAT-0.20.0-dotnet10-win-x86.zip)** using **Download raw file** or **View raw** while signed in. Repository-wide Code → Download ZIP is source code, not a deployment package.

Source `8649556bed43890c15ee7cc93656bc747ef3a7cf`: self-contained ASP.NET Core 10, Windows x86, branded frontend. Autodesk now supports whole-folder scopes with optional subfolders, paged reads beyond 250 files, relative-path matching and explicit complete-scope coverage. Save both connection scopes, matching keys and field mappings in a reusable profile. Duplicate/missing keys and unmatched records remain visible. A failed or oversized whole-folder scan saves no partial snapshot.

Whole-folder UAT limits: 5,000 files, 500 folders, 1,000 pages, 64 levels, 16 MB metadata and 180 seconds. Completion refers only to vendor-reported accessible contents at read time; permission-hidden data and concurrent changes are not detectable. RedEye retains its five-artefact metadata sample; full RedEye group/register and Meridian folder scans are not implemented. Mixed coverage is labelled accordingly. Platform writes and file transfers are unchanged.

**56 native tests** and five browser workflows passed using simulated services. Customer live folder acceptance remains pending.

Upload this ZIP through the existing Kudu ZIP deployment and restart OrbitPortal. Confirm `/api/health` reports **0.20.0**. Retain all existing environment variables, encryption key, data path, key ring and credentials. No new Azure resources or settings are needed.

[Folder comparison instructions and customer checklist](../docs/FOLDER_COMPARISONS.md).

SHA-256: `5a7ed7b84c46f9e6cf084278052601c668ac12544b1a10da20878326cab46018`.

Previous packages remain in Git history. This directory contains the current package to avoid selecting an outdated build.
