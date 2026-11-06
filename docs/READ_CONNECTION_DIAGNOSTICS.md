# Version 0.4.3 — diagnosing a local 409

A POST to ORBIT's `/read` endpoint returning 409 does not establish that RedEye rejected an API key. It can be a local prerequisite failure before any vendor request, or a connection-change conflict while handling a response. A saved-key 200 establishes local storage only; fixture success establishes synthetic parser behaviour only.

Each connection card now shows its own saved vendor/test confirmations, unique connection ID, credential state and local readiness report. Editing checkboxes in the form does not update a card until changes to that specific saved connection are submitted. The form buttons now distinguish **Create connection** from **Save changes to this connection**.

Errors from the read action appear beside the card's controls, with a stable reason code and next action. The server writes a safe `ORBIT read blocked: connection=... reason=...` terminal line, with no API key, ciphertext or raw provider payload. `/api/health` and the connection-list response report the running backend version; the portal warns if it differs from the frontend. Copying new frontend files into a running installation does not restart its old Python process.

| Reason | Action |
|---|---|
| `live_reads_disabled` | Stop the old server; launch Run-ORBIT-Read-Tests.cmd and type ENABLE |
| `vendor_settings_unconfirmed` / `test_access_unconfirmed` | Edit the exact saved card, confirm the applicable setting and save |
| `evidence_missing` | Save a non-secret administrator/source reference on that connection |
| `credential_missing` | Store the key after saving revised setup, on the same card |
| `credential_unreadable` | The database and vault key may not match; restore them together or clear/replace the credential without deleting the database |
| `host_not_allowed` / `invalid_host` | Verify the saved API URL and custom-host allowlist; restart an older backend if needed |
| `invalid_credential` / `invalid_header` | Check credential line breaks and the saved header/prefix without pasting secrets into logs/chat |
| `resource_scope_mismatch` | Refresh Autodesk discovery and save the intended authorised selection |
| `credential_changed` | Wait until credential changes finish and retry |

The readiness report checks local settings/decryption/host policy; **ready** means ready to attempt a read, not a verified vendor connection. The software cannot infer the cause of a particular user's 409 from the HTTP status alone or inspect a database on that user's computer. Ask for the displayed reason/message rather than repeatedly replacing keys or assuming one checkbox is the cause.

To update locally, stop the existing ORBIT server and download/extract the current branch. Preserve your existing folder and its `.local` database/key together if retaining data. Restart from the updated folder; do not leave an older server on port 8000. No migration or secret reset is required by this diagnostic-only release.

Validation: 102 backend tests pass, including saved-setting failures, unreadable vault data, safe log/response redaction, version reporting and disabled read transport. The diagnostic browser test injects a synthetic 409 and an old backend version; the connection browser smoke checks fixture-only functionality. No real vendor request or customer key was used.
