# Latest manual Azure UAT package: v0.19.0

Download **[ORBIT-UAT-0.19.0-dotnet10-win-x86.zip](ORBIT-UAT-0.19.0-dotnet10-win-x86.zip)** using **Download raw file** or **View raw** while signed in. Repository-wide Code → Download ZIP is source code, not a deployment package.

Source `d212dab6025c7abd2567aa9ee959d0b5904e21f7`: self-contained ASP.NET Core 10, Windows x86, branded frontend. Overview now opens the project dashboard: connection health, current comparison counts, different/unmatched records, property validation, bSDD reference, profiles needing attention and direct report links. Stale reports and deleted-profile history are excluded from current totals. Read checks are explicit and role-restricted; refreshing the dashboard reloads stored evidence only. Desktop and mobile layouts are included.

**46 native tests** and four browser workflows passed: dashboard, Autodesk authentication, Autodesk folder/file selection and mapping profile lifecycle. External services were simulated. Customer live dashboard acceptance remains pending. Existing connector limits and hosted write restrictions are unchanged.

Upload this ZIP through the existing Kudu ZIP deployment and restart OrbitPortal. Confirm `/api/health` reports **0.19.0**, then open **Overview**. Retain all existing environment variables, encryption key, data path, key ring and credentials. No database migration, new Azure resource or additional setting is needed.

[Dashboard workflow and customer acceptance checklist](../docs/DASHBOARD_UAT.md).

SHA-256: `e7e6ca699860e406a87a3b0c34d17c288654f28914378c6eaa70317130727014`.

Previous packages remain in Git history. This directory contains the current package to avoid selecting an outdated build.
