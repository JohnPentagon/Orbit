> In v0.13, open Connections → Autodesk or RedEye. The normal Run-ORBIT.cmd opens a local workspace without a tester-role picker; the older read-test launcher is an advanced test-mode alternative.

# Version 0.4 — easier Autodesk and RedEye setup

6 November 2026. This update implements local APS consent/app-only auth, explicit renewal, and authorised named hub/project/top-level-folder selectors. Vendor calls are mocked in tests; no real account or live token exchange was verified during development. Read-only discovery remains separate from synthetic comparison/mapping/handover records. No file transfer or provider business-data write is enabled.

## Start the appropriate local mode

- **Run-ORBIT.cmd:** normal synthetic demonstration; live reads are disabled unless you deliberately supplied the environment flag yourself.
- **Run-ORBIT-Read-Tests.cmd:** optional local read-testing launcher. It asks you to type ENABLE and optionally enter a confirmed RedEye production API hostname. It sets process-local read/host flags, then starts the same loopback-only server and browser. It never asks for secrets in the terminal or changes system-wide settings.

Stop the old server before starting either launcher. The extra Windows launcher is reviewed but cannot be executed in the Linux development workspace. Use only a trusted, single-user local test computer. The ORBIT demo identity picker is still not production authentication.

## Reference-client update (version 0.4.1)

The product owner subsequently supplied `RedEyeApiClient.cs`: its default is **https://api.redeyedms.com**, and `SetApiKey` sends **Authorization: Bearer <apiKey>**. This now appears as a labelled utility-default preset alongside QA/custom options. The constructor allows overrides, so inspect the calling/resolver configuration to establish its effective host. See [reference-client review](REDEYE_REFERENCE_CLIENT.md). This is additional user-supplied implementation evidence; it does not change what the public documentation itself establishes below.

## What the RedEye documentation actually confirms

Source: https://api.redeyedms.com/#redeye-dms-api, retrieved 6 November 2026 (HTTP 200). The page identifies itself as RedEye DMS API v3.0.0.

| Item | Finding |
|---|---|
| Listed remote base | `https://qa-api.redeyedms.com`, port 443; explicitly QA |
| Other listed base | `http://localhost`, port 8080; a development example, not a remote customer endpoint |
| Authentication heading | HTTP bearer scheme, conventionally `Authorization: Bearer <credential>` |
| Operation examples | Omit authentication and say no authentication required; this conflicts with the heading |
| Production base URL | Not established by the published page |
| Key lifecycle/entitlement/bucket binding | Not established by this page |

The portal now offers the documented QA host and a labelled bearer-header preset. This does **not** establish that a particular API key can be used as that bearer value; the customer/vendor must confirm applicability. Header/prefix remain editable for a vendor-confirmed alternative. Do not send a production key to QA by default. The public documentation alone does not establish a production host; the supplied client now provides separate evidence for `api.redeyedms.com` as its overridable default.

The QA and reference-client default hostnames are built-in exact-host presets, still behind explicit read opt-in and connection-level approval confirmations. Custom production hosts must be added through the local read-test launcher or the existing operator allowlist environment setting. No wildcard matching, custom ports or redirect following is enabled.

### Steps with your existing key

1. Confirm whether the key is QA or production, the approved API host, its bucket/access permissions and the key-header format with RedEye or the administrator who issued it. Do not send the key in chat.
2. Launch local read-test mode. For a production key, enter only the confirmed hostname at the launcher prompt.
3. Select **Northstar owner → Read connections → RedEye DMS**. Choose QA explicitly only if approved, otherwise enter the confirmed production HTTPS base URL.
4. Review the bearer preset and change it only if the vendor specifies another header. Add a non-secret approval reference and check the confirmed-settings/test-access boxes only when true. Save.
5. Choose **Set test credential**, enter the key in the password field, then **Read artefacts**. A successful response verifies that operation only; it does not establish full permissions or register completeness.

Existing configurations can be revised using **Edit setup**. Saving revised settings clears existing access credentials, cached discovery and last-result summaries so they cannot be reused against changed settings. App registration settings remain local until explicitly removed.

## Autodesk: setup once, then choose names

### What you need

- An APS application you are authorised to configure, its client ID and secret.
- For the recommended user-consent flow, register this **exact callback URL** in that application:

```text
http://127.0.0.1:8000/api/autodesk/callback
```

- Approved Autodesk account/project access and any required app provisioning by its administrator. Registering the app or obtaining a token does not grant hub/project/folder membership.
- The read-only scope used here is `data:read`, declared by the reviewed Data Management contracts. Additional vendor restrictions may apply.

### Connect and discover

1. Start local read-test mode, open **http://127.0.0.1:8000** and select Northstar owner. Using `localhost` instead will not match the fixed local consent callback cookie flow.
2. In **Read connections**, create or revise a Forma/ACC document-management profile with confirmed approved test settings. Hub/project IDs are no longer needed in the setup form.
3. Under that connection, enter APS client ID/secret and choose **Sign in with Autodesk — three-legged** (recommended first). Save the app settings; the secret is encrypted locally and not returned to the browser afterwards.
4. Choose **Sign in with Autodesk**, approve on Autodesk's own site, and return to ORBIT. A consent failure returns a generic message; audit events retain safe failure categories without codes/tokens.
5. Choose **Load accessible hubs**. Select a hub by name; its project dropdown loads automatically. Select a project by name; top-level folders then load. If the project list has 25 entries, **Load more projects** retrieves the next documented page, up to a local limit of 1,000 projects. Hub and top-level-folder results remain bounded to 25 per response.
6. Select an optional top-level folder and choose **Use selected project and folder**. ORBIT stores the provider IDs and labels for you. No document is imported. Without a folder, project/top-level-folder reads work, but folder-content reads still require an authorised folder selection.

The backend accepts only choices from current discovery lists, checks parent hub/project relationships and ties the cache to the current credential generation. Cache entries expire after 10 minutes and are removed on subsequent discovery or connection changes. Some project metadata is cached locally for that purpose; this is not a document-register import. Source IDs must not be replaced with similarly named resources from another hub/API.

**Renew authorisation** explicitly renews a consent token using its encrypted refresh token, or obtains a fresh application token for app-only mode. Renewal is not automatic; if it is unavailable or rejected, sign in again. Token expiry is shown. Renewing authorisation invalidates discovery caches, so refresh the lists afterwards.

**Disconnect and remove app** clears local app secrets, access/refresh tokens, pending consent and discovery. This does not revoke the app or key with Autodesk; revoke vendor-side access separately if required. Clearing/replacing a manually supplied token similarly invalidates stored token state and pending flows.

### Two-legged versus three-legged

The official authentication OpenAPI defines authorization-code, client-credentials and refresh-token grants at the v2 token endpoint. ORBIT supports a confidential server-backed app with Basic-authenticated token exchange. Three-legged consent uses a random state and S256 PKCE verifier, bound to the initiating local browser cookie, ORBIT session, tenant/project/connection and generation, with one-use/expiry enforcement. Switching identities, logging out or changing access invalidates pending consent. Callback query strings are redacted from Uvicorn access logs, and tokens are never returned to the UI.

The **App-only — two-legged** option is appropriate only where the actual resource/product and administrator provisioning support it. It obtains an app-context token rather than signing in a user, and cannot be assumed to see every ACC project. Empty lists or 403 errors require checking application provisioning, account context and permissions, not broadening scopes blindly.

The local implementation serialises sensitive app/token updates using database transactions; it is not a distributed OAuth service. Production deployment needs proper ORBIT identity, hosted callback configuration, managed vault/session storage, concurrency and recovery controls, and separate security validation.

## Why the supplied GraphQL link is separate

The supplied AEC Data Model reference describes `https://developer.api.autodesk.com/aec/graphql` in Autodesk's vendor-published documentation corpus. It is useful for model/element/property information and has separate service/schema/region applicability. The current document workflow deliberately uses Data Management REST hub/project/folder/item identities. AEC Data Model identifiers are not interchangeable with those document-management identifiers. No GraphQL connector, query execution or extra entitlement is claimed in this release.

## Research sources and evidence limits

- RedEye page above: substantive HTML read; source of the QA/bearer findings and conflicts.
- Supplied [two-legged tutorial](https://aps.autodesk.com/en/docs/oauth/v2/tutorials/get-2-legged-token/), [three-legged tutorial](https://aps.autodesk.com/en/docs/oauth/v2/tutorials/get-3-legged-token/) and [AEC GraphQL reference](https://aps.autodesk.com/en/docs/aecdatamodel/v1/reference/graphqlendpoint/): HTTP 200 with browser-style headers, but the retrieved content is the portal's JavaScript shell, not the full articles. No claim that their article contents were fully read.
- [Official Autodesk authentication OpenAPI](https://github.com/autodesk-platform-services/aps-sdk-openapi/blob/main/authentication/authentication.yaml): retrieved and read for v2 authorize/token grants, PKCE, callback parameters, confidential-client Basic authentication and token response schema.
- [Official Data Management OpenAPI](https://github.com/autodesk-platform-services/aps-sdk-openapi/blob/main/datamanagement/datamanagement.yaml): retrieved and read for hierarchy, read scopes and 0-based project-list pagination.
- [Official vendor-published AEC GraphQL corpus](https://github.com/autodesk-platform-services/llmstxt/blob/main/llms-graphql.txt): existing retrieved snapshot used for service distinction; not proof of the customer's entitlement or current live availability.

Validation uses mocked token exchanges and read responses and an intercepted UI fixture, plus the previous regression workflows. It proves the implemented local controls and screen behaviour, not a completed live Autodesk sign-in, RedEye key verification, vendor terms approval or Windows launcher execution.
