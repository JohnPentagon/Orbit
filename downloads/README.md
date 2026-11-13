# Latest manual Azure UAT package: v0.17.0

Download **[ORBIT-UAT-0.17.0-dotnet10-win-x86.zip](ORBIT-UAT-0.17.0-dotnet10-win-x86.zip)** using **Download raw file** or **View raw** while signed in. Repository-wide Code → Download ZIP is source code, not a deployment package.

Source `1dd1949f87e721243558158576ae37b36bd9df3c`: self-contained ASP.NET Core 10, Windows x86, branded frontend. The mapping editor now prioritises parameter A → parameter B, clear Save profile, in-place versioned Edit, deliberate Copy and confirmed Delete. Document matching and validation options are separate expandable controls. Deleted profiles retain historical reports and audit history.

**38 native tests**, **406 local-backend tests**, mapping-profile browser workflow, hosted Autodesk browser workflow and the local portal smoke checks passed. External services were simulated for these checks. Customer mapping UAT remains pending; the user previously confirmed live hosted Autodesk and RedEye connections. Other migration gaps remain documented; hosted RedEye writes stay disabled.

Upload this ZIP directly through Kudu ZIP deployment and restart OrbitPortal. Confirm `/api/health` reports **0.17.0**. Keep existing environment variables, encryption key, data path and key ring unchanged. Existing profiles remain available; no schema migration or new paid resource is required.

[Mapping profile workflow and acceptance checks](../docs/MAPPING_PROFILES.md).

SHA-256: `9dcd96eb68badd2ba1fce3fb07535567dec2a4e1670adb5fac247f84675a3332`.

Previous packages remain in Git history. This directory contains the current package to avoid selecting an outdated build.
