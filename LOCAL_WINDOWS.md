# Run ORBIT on your Windows computer

This is the synthetic foundation, not a live Forma/RedEye integration. It runs on your computer and does not require a hosting account, Docker, vendor credentials or a paid service.

## First run

1. Install **64-bit Python 3.12 or newer** from https://www.python.org/downloads/windows/. Enable the Python launcher / PATH option offered by the installer. If Python is already installed, `py -3 --version` should show 3.12 or newer.
2. Download `ORBIT_Local_Windows.zip`. Right-click the ZIP, select **Extract All**, and extract it to a normal local folder, for example `C:\Users\YourName\Projects\ORBIT`. Do not run it from inside the ZIP.
3. Open the extracted `ORBIT` folder and double-click **Run-ORBIT.cmd**. Administrator access is not needed. The first run downloads the pinned Python packages, creates an isolated `.venv`, starts the local server, and opens your browser when the health check succeeds.
4. Keep the terminal window open. If the browser does not open, enter **http://127.0.0.1:8000** manually on this same computer. Use HTTP, not HTTPS.
5. Choose **Northstar Construction · engineer**, click **Enter workspace**, then **Run comparison**. All records are labelled synthetic.

The launcher uses Windows PowerShell with an execution-policy override for that one process. It does not change your machine's execution policy. If your organisation prohibits local scripts, follow its IT policy rather than attempting to bypass that control. Source scripts are included for inspection.

## Test the roles

- **Engineer:** compare the synthetic registers; draft a mapping under Approvals.
- **Approver:** review and approve a draft from another identity. No mapping or vendor write is executed.
- **Viewer:** inspect results without permission to run comparisons or alter mappings.
- **Owner:** manage existing synthetic membership roles and project grants under Administration.
- **Auditor:** inspect permitted project history.
- Switch to **Southbank Estates** to see that another tenant does not inherit Northstar results.

No real account registration occurs. Do not enter production credentials in the local demo.

For the new multi-field editor and synthetic handover flow, follow **docs/INTEGRATION_PROFILES.md**. Start with Northstar engineer → Integration profiles, then use an approver identity for the separate review steps. C-005 is the simplest eligible document for a synthetic manifest. No files are actually transferred.

Version 0.4 provides **Read connections** with Autodesk consent/app-only authorisation, explicit token renewal and named hub/project/folder selectors. Use **Run-ORBIT-Read-Tests.cmd** only for approved local read testing; it prompts for an explicit opt-in and an optional confirmed RedEye production hostname. The default **Run-ORBIT.cmd** still supports fixture checks without vendor credentials. Follow **docs/AUTODESK_AND_REDEYE_SETUP.md** for app registration and exact callback configuration. No live sign-in was verified during development, and file transfers remain disabled.

## Stop and start again

Press **Ctrl+C** in the launcher window to stop ORBIT. Double-click `Run-ORBIT.cmd` to start again. The launcher only stops its own server process. If a previous run remains active, close it before restarting. Your local synthetic state is retained under `.local`.

## Troubleshooting

- **Python not found / Microsoft Store opens:** install Python from python.org with its launcher, then open a fresh terminal and try `py -3 --version`.
- **Dependency download fails:** the first setup needs outbound HTTPS to PyPI and its package file hosts. Check your internet connection or ask your IT team about their approved package proxy. Do not disable TLS verification.
- **Port 8000 in use:** close the previous ORBIT launcher or identify the application using that port. ORBIT will not kill unrelated processes or silently attach to them.
- **Browser connection refused:** keep the launcher open and check its error messages. The browser and server must be on the same computer.
- **Prebuilt portal missing:** extract the whole ZIP again; do not copy only the launcher.
- **Company policy blocks scripts:** ask IT for an approved run method. Administrator privileges or machine-wide policy changes are not required by ORBIT.

To run manually after setup, use PowerShell in the extracted folder:

```powershell
$env:ORBIT_DEMO_MODE = '1'
.\.venv\Scripts\python.exe -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
```

## Data and privacy

The ZIP contains **no existing database, credentials, vault key, session cookies, cloud virtual environment or node_modules**. The first run generates fresh synthetic data. `.local\orbit.db` stores local state and encrypted development credential ciphertext, and `.local\vault.key` holds its local encryption key. Neither is a production cloud vault. Deleting `.local` resets the demo and discards that state; do this only after stopping the server and deciding you do not need the existing local data.

The app is deliberately bound to `127.0.0.1`. Do not open firewall ports, change it to `0.0.0.0`, or publish this identity-picker demo to the internet. Production authentication is not implemented.

## Development (optional)

The prebuilt portal is included, so **Node.js is not needed just to try this demo**. To change or rebuild the frontend, install Node.js 24 LTS, open PowerShell in `frontend`, then run:

```powershell
npm.cmd ci
npm.cmd run build
```

Restart the launcher afterwards. Backend tests, after setup, can be run from the ORBIT folder with:

```powershell
.\.venv\Scripts\python.exe -m pytest backend -q
```

The Python API tests and Chromium workflow were validated in the Linux development workspace. The Windows launcher is supplied for Windows 11 but cannot be executed in that Linux environment; its Windows behaviour needs your first-run check. Windows package-wheel availability and your company's local restrictions are not assumed verified.

## Connection plans and tests to return to

In version 0.5, choose **Connection preparation** in the sidebar. As an owner, create a separate named plan for each intended connection in the selected project. Meridian includes Enterprise/PowerWeb context, interface selection, installed release, API URL reference and on-premises execution options. Save unknowns as untested or blocked with a short non-secret reason. Other project roles can view saved plans.

Edit a saved plan to update test statuses later; **Export checklist** downloads the current project's records as JSON. Manual results never enable vendor access. Changing connection settings resets existing checks to untested. **Preview Explorer fixture** uses a hand-authored response only and does not authenticate to Meridian.

The wider acceptance list is [docs/TESTER_CHECKLIST.md](docs/TESTER_CHECKLIST.md). Keep your existing `.local` database and matching vault key together when updating; do not publish or share them. The new table is added automatically on startup without replacing existing records.

## Optional bSDD dictionary

Version 0.6 adds **bSDD dictionaries** to the sidebar. As the project owner, browse public dictionaries or verify a versioned dictionary URL, optionally select class properties, enable the reference and save. No bSDD API key is needed. An enabled selection supplies field-name suggestions under Integration profiles. Existing mappings keep working with the reference disabled. Follow [docs/BSDD_SETUP.md](docs/BSDD_SETUP.md) for examples and limits.
