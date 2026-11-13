# Latest manual Azure UAT package: v0.18.0

Download **[ORBIT-UAT-0.18.0-dotnet10-win-x86.zip](ORBIT-UAT-0.18.0-dotnet10-win-x86.zip)** using **Download raw file** or **View raw** while signed in. Repository-wide Code → Download ZIP is source code, not a deployment package.

Source `250e4e25ae8749496feefc39dc103fbb6df1602d`: self-contained ASP.NET Core 10, Windows x86, branded frontend. Autodesk now supports nested folder navigation, breadcrumbs, individual file selection, Load more pages and comparison read limits of 25/100/250 files. Browsing supports up to 1,000 entries per folder. Reads exclude subfolders and are not recursive. Other connectors retain their existing limits.

**46 native tests** and both Autodesk browser workflows passed with simulated external responses. Customer live folder/file acceptance remains pending. Existing mapping profile functionality is retained. After changing Autodesk selection, edit the mapping profile, refresh parameters and save before comparing.

Upload this ZIP through the existing Kudu ZIP deployment and restart OrbitPortal. Confirm `/api/health` reports **0.18.0**. Keep existing environment variables, encryption key, data path and key ring unchanged. No schema migration or new paid resource is required. Hosted RedEye writes remain disabled.

[Autodesk folder/file workflow and acceptance checks](../docs/AUTODESK_FILES.md).

SHA-256: `03f78f9cad9573b5dfcbe4e8bac60b7adc6b559d92d351d49dfc0d6a0bcde412`.

Previous packages remain in Git history. This directory contains the current package to avoid selecting an outdated build.
