# Manual Azure UAT deployment package

Download **ORBIT-UAT-dotnet10-win-x86-5409ea9.zip** using GitHub's **Download raw file** button or **View raw** link while signed in. This is the published deployment package; GitHub's repository **Code → Download ZIP** is source code and is not a deployment package.

Built from source commit `5409ea9`: native .NET 10, self-contained Windows x86, branded frontend included. The 12 release tests passed. This is a UAT migration candidate; full connector parity remains in progress and hosted RedEye writes stay disabled. No credentials, encryption keys or local databases are included.

Upload the ZIP directly to Azure Kudu Zip Push Deploy after configuring the environment variables in [the simple hosting guide](../docs/AZURE_SIMPLE_UAT.md). Keep the worker 32-bit and use one instance. No new Azure resource or GitHub Actions build is required.

SHA-256: `ed166b47e172751558e10b0e6df6745d212e4361994a3517947c819752dca8a3`.

This copy is provided because the chat download link could not be used. It does not deploy or change Azure configuration.
