# Latest manual Azure UAT package: v0.16.0

Download **[ORBIT-UAT-0.16.0-dotnet10-win-x86.zip](ORBIT-UAT-0.16.0-dotnet10-win-x86.zip)** using **Download raw file** or **View raw** while signed in to GitHub. GitHub's repository-wide Code → Download ZIP is source code, not a deployment package.

Built from source `8eeb3ced00fa1f06289fe8245cd37bd215eda2bb`: native ASP.NET Core 10, self-contained Windows x86, branded frontend. Includes the completed native APS OAuth/PKCE, app-only auth, explicit renewal, named hub/project/folder discovery and scoped document read. All **32 native release tests** and the hosted Autodesk UI fixture passed. Live Autodesk customer consent remains to be confirmed. Other migration gaps remain documented and hosted RedEye writes stay disabled.

Upload this ZIP directly through Kudu ZIP deployment and restart OrbitPortal. Check `/api/health` reports **0.16.0**. Keep the existing Entra environment variables, Orbit encryption key, data path and key-ring path unchanged; do not delete the data directory. No new paid resource is required.

Then follow [the hosted Autodesk setup steps](../docs/HOSTED_AUTODESK.md). For interactive consent, use an APS confidential web app that supports three-legged OAuth. Put the APS secret in ORBIT's Autodesk app settings, not the Entra environment variable.

SHA-256: `74d00092462eda67ce4d536bb020d99de5b0aec0b78d789fe6ebd42a27ea0015`.

The previous v0.15 deployment ZIP remains available in Git history. This directory provides the current package so outdated builds are not accidentally selected.
